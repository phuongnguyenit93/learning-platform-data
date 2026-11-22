# Gán lại tham chiếu không làm thay đổi chuỗi được chia sẻ

Trong Java, nhiều biến có thể cùng tham chiếu đến một đối tượng `String`. Khi **gán lại một biến** sang chuỗi khác, chỉ giá trị tham chiếu lưu trong biến đó thay đổi; các biến còn lại vẫn tham chiếu đến đối tượng cũ. Đây là hệ quả của cơ chế biến tham chiếu trong Java. Với `String`, tính **bất biến (immutability)** còn bảo đảm các thao tác xử lý chuỗi không sửa trực tiếp nội dung đối tượng ban đầu.

Bài này tập trung phân biệt hai hành động hay bị nhầm:

- **Gán lại tham chiếu:** `b = "New"`, `b = a + "!"`, hoặc `b = a.replace(...)`; `b` nhận một tham chiếu được tính ra ở vế phải. Không có lệnh nào trong số đó tự gán lại `a`.
- **Thay đổi trạng thái đối tượng:** một đối tượng mutable có thể bị sửa thông qua bất kỳ tham chiếu nào trỏ tới nó. `String` không hỗ trợ kiểu sửa nội dung tại chỗ này bằng API thông thường.

## 1. Hai biến có thể cùng trỏ đến một `String`

Xét:

```java
String first = "Java";
String second = first;
```

Dòng đầu tạo một biến tham chiếu `first` trỏ đến chuỗi `"Java"`. Dòng sau **sao chép giá trị tham chiếu** từ `first` sang `second`. Vì vậy hai biến trỏ đến cùng một đối tượng `String`:

```text
first  ────┐
           ├────────> String "Java"
second ────┘
```

Ở thời điểm này, `first == second` trả về `true` vì toán tử `==` so sánh xem hai biến có giữ cùng một tham chiếu đối tượng hay không.

Quan trọng: «hai biến chia sẻ chuỗi» nghĩa là **hai tham chiếu đang cùng trỏ tới một đối tượng**. Nó không có nghĩa là hai biến được gắn chặt để mọi phép gán vào biến này tự động cập nhật biến kia.

## 2. Gán lại chỉ đổi tham chiếu của biến nhận phép gán

Thêm một dòng:

```java
second = "Kotlin";
```

Sau phép gán, sơ đồ trở thành:

```text
first  ─────────────> String "Java"

second ─────────────> String "Kotlin"
```

Không có thao tác nào sửa `String "Java"` thành `"Kotlin"`. Biến `first` vẫn giữ tham chiếu cũ. Biến `second` nhận tham chiếu đến một chuỗi khác; quan hệ cùng trỏ trước đó chấm dứt.

Trong Java, **biến** chứa một giá trị tham chiếu; phép gán `second = ...` thay thế giá trị lưu trong chính `second`. Nó không đi theo tham chiếu để ghi đè nội dung đối tượng mà `second` từng trỏ đến, và cũng không tìm những biến khác để thay đổi chúng.

### Ví dụ Java 17+ chạy độc lập

Tạo tệp `ReferenceReassignmentDemo.java`:

```java
public class ReferenceReassignmentDemo {
    public static void main(String[] args) {
        String first = "Java";
        String second = first;

        System.out.println("Before:");
        System.out.println("first = " + first);
        System.out.println("second = " + second);
        System.out.println("same object = " + (first == second));

        second = "Kotlin";

        System.out.println("After:");
        System.out.println("first = " + first);
        System.out.println("second = " + second);
        System.out.println("same object = " + (first == second));
    }
}
```

Biên dịch và chạy:

```bash
javac ReferenceReassignmentDemo.java
java ReferenceReassignmentDemo
```

Kết quả:

```text
Before:
first = Java
second = Java
same object = true
After:
first = Java
second = Kotlin
same object = false
```

Ở nửa đầu, `second = first` tạo thêm tên tham chiếu tới cùng `String`. Ở nửa sau, `second = "Kotlin"` chỉ đổi biến `second`. `first` vẫn in `Java`.

## 3. Ngay cả khi gọi phương thức xử lý chuỗi, đối tượng nguồn vẫn không bị sửa

Một số lệnh trông giống «sửa chuỗi»:

```java
String original = "cat";
String alias = original;

alias = alias.toUpperCase();
alias = alias.replace("A", "O");
```

Kết quả là `original` vẫn là `"cat"` còn `alias` là `"COT"`. Lý do gồm **hai bước riêng**:

1. `toUpperCase()` hoặc `replace(...)` trả về một giá trị `String`, không sửa nội dung `String` nguồn.
2. Phép gán `alias = ...` thay thế tham chiếu trong biến `alias`; `original` vẫn giữ tham chiếu cũ.

Tạo tệp `ImmutableOperationDemo.java`:

```java
public class ImmutableOperationDemo {
    public static void main(String[] args) {
        String original = "cat";
        String alias = original;

        alias = alias.toUpperCase();
        alias = alias.replace("A", "O");

        System.out.println(original);
        System.out.println(alias);
        System.out.println(original.equals(alias));

        String appended = original.concat("!");
        System.out.println(original);
        System.out.println(appended);
    }
}
```

```bash
javac ImmutableOperationDemo.java
java ImmutableOperationDemo
```

Kết quả:

```text
cat
COT
false
cat
cat!
```

Các phương thức như `concat`, `replace`, `toUpperCase` hoặc `substring` không cung cấp phép sửa nội dung tại chỗ cho `String`. Một số phương thức có thể trả lại chính đối tượng cũ nếu kết quả không đổi; điều đó không làm thay đổi tính bất biến của chuỗi.

Đừng nhầm «biến vẫn mang tên cũ» với «đối tượng cũ đã bị sửa». Sau `alias = alias.toUpperCase()`, chính **biến alias** được gán lại; đối tượng `"cat"` không trở thành `"CAT"`.

## 4. Bất biến và gán lại tham chiếu là hai khái niệm khác nhau

Cần tách bạch:

| Hành động | Điều thay đổi | Điều không bị thay đổi |
| --- | --- | --- |
| `String b = a;` | Biến `b` giữ tham chiếu đang có trong `a` | Nội dung đối tượng `String` |
| `b = "Other";` | Tham chiếu trong biến `b` | Tham chiếu trong `a`, đối tượng cũ |
| `b = b.concat("!");` | Giá trị tham chiếu trong `b` sau khi có kết quả chuỗi | Nội dung `String` ban đầu |
| `a = null;` | Tham chiếu trong biến `a` thành `null` | Biến `b` và đối tượng mà `b` đang giữ |
| `mutable.append("!");` với `StringBuilder` | Nội dung đối tượng mutable | Không có bảo đảm bất biến như `String` |

Điểm đáng chú ý: **việc gán lại một biến không tự thay đổi biến khác cũng đúng đối với tham chiếu tới đối tượng mutable**. Khác biệt của mutable là một phép gọi phương thức qua một tham chiếu có thể **sửa chính đối tượng** mà những tham chiếu còn lại cũng quan sát được.

### Phản ví dụ với `StringBuilder`

Tạo tệp `MutableContrastDemo.java`:

```java
public class MutableContrastDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("Java");
        StringBuilder second = first;

        second.append(" 21");
        System.out.println(first);
        System.out.println(second);
        System.out.println(first == second);

        second = new StringBuilder("Kotlin");
        System.out.println(first);
        System.out.println(second);
        System.out.println(first == second);
    }
}
```

```bash
javac MutableContrastDemo.java
java MutableContrastDemo
```

Kết quả:

```text
Java 21
Java 21
true
Java 21
Kotlin
false
```

`second.append(" 21")` sửa nội dung của **cùng một `StringBuilder`** mà `first` cũng trỏ đến, nên cả hai in `Java 21`. Trái lại, `second = new StringBuilder("Kotlin")` chỉ đổi tham chiếu của `second`; `first` vẫn trỏ đến builder cũ. Ví dụ cho thấy phải phân biệt **gọi phương thức sửa đối tượng** với **gán lại biến**.

## 5. Điều gì xảy ra khi truyền một `String` vào phương thức?

Java dùng **truyền tham trị (pass-by-value)** cho mọi tham số. Với kiểu tham chiếu như `String`, giá trị được sao chép là *tham chiếu tới đối tượng*, không phải bản thân đối tượng và cũng không phải biến gốc của người gọi.

Xem chương trình `ParameterReassignmentDemo.java`:

```java
public class ParameterReassignmentDemo {
    static void renameLocally(String name) {
        name = "Changed";
        System.out.println("Inside = " + name);
    }

    static String makeUpperCase(String name) {
        return name.toUpperCase();
    }

    public static void main(String[] args) {
        String shared = "Java";
        String alias = shared;

        renameLocally(shared);
        System.out.println("Caller = " + shared);
        System.out.println("Alias = " + alias);

        String updated = makeUpperCase(shared);
        System.out.println("Updated = " + updated);
        System.out.println("Still shared = " + shared);
    }
}
```

```bash
javac ParameterReassignmentDemo.java
java ParameterReassignmentDemo
```

Kết quả:

```text
Inside = Changed
Caller = Java
Alias = Java
Updated = JAVA
Still shared = Java
```

Khi gọi `renameLocally(shared)`, tham số `name` là **một biến cục bộ khác** nhận bản sao giá trị tham chiếu trong `shared`. Lệnh `name = "Changed"` chỉ gán lại biến cục bộ đó. Người gọi không bị đổi `shared` và `alias`.

Nếu muốn người gọi nhận giá trị chuỗi đã biến đổi, một cách dễ hiểu là **trả về kết quả và gán rõ ràng**:

```java
String shared = "Java";
String result = shared.toUpperCase();
// shared vẫn là "Java", result là "JAVA".
```

Hoặc nếu muốn chính biến `shared` đổi giá trị:

```java
shared = shared.toUpperCase();
// Biến shared bây giờ trỏ đến "JAVA".
```

Cả hai đều không sửa nội dung đối tượng `"Java"` trước đó.

## 6. Một ngoại lệ dễ hiểu nhầm: thay đổi đối tượng chứa trường `String`

Giả sử hai biến trỏ tới cùng một đối tượng lớp `Message` có trường `text`. Nếu một biến cập nhật **trường text của đối tượng Message**, biến kia sẽ nhìn thấy giá trị trường mới khi đọc lại. Điều này không hề mâu thuẫn với tính bất biến của `String`: **đối tượng Message mutable**, còn hai chuỗi cũ và mới vẫn là những giá trị `String` bất biến.

Tạo tệp `SharedHolderDemo.java`:

```java
public class SharedHolderDemo {
    static class Message {
        String text;

        Message(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        Message first = new Message("Original");
        Message second = first;
        String snapshot = first.text;

        second.text = "Updated";

        System.out.println(first.text);
        System.out.println(second.text);
        System.out.println(snapshot);
    }
}
```

```bash
javac SharedHolderDemo.java
java SharedHolderDemo
```

Kết quả:

```text
Updated
Updated
Original
```

`first` và `second` cùng trỏ tới một `Message`, vì vậy việc gán `second.text = "Updated"` làm **trường của đối tượng Message** trỏ đến chuỗi mới. `snapshot` là biến `String` đã nhận tham chiếu đến `"Original"` trước đó nên vẫn không đổi.

Phân biệt hai câu:

- «Gán lại một **biến tham chiếu** `second`» — không tự thay đổi biến `first`.
- «Gán lại **trường của đối tượng dùng chung** `second.text`» — thay đổi trạng thái của đối tượng `Message` mà `first` cũng nhìn thấy.

Tương tự, phần tử mảng, phần tử danh sách mutable hay trạng thái trong một đối tượng dùng chung có thể được cập nhật. Tính bất biến của `String` không khiến **đối tượng chứa nó** trở thành bất biến.

## 7. `final` có liên quan thế nào?

`final String name = "Java";` ngăn **gán lại biến name** sau khi biến đã được khởi tạo:

```java
final String name = "Java";
// name = "Kotlin"; // Lỗi biên dịch: không thể gán lại biến final.
```

Nhưng `final` không phải nguyên nhân làm `String` bất biến: ngay cả `String ordinary = "Java";` không có `final` thì đối tượng `String` vẫn bất biến.

Ngược lại, một tham chiếu `final` tới một đối tượng mutable vẫn có thể dùng để thay đổi **nội dung đối tượng**:

```java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" 21"); // Hợp lệ: không gán lại biến builder.
```

Do đó:

- `final` hạn chế gán lại **một biến/trường tham chiếu**.
- `String` bất biến vì hợp đồng của **kiểu đối tượng** không cho sửa nội dung qua API thông thường.
- Tính bất biến của `String` và tính cố định tham chiếu nhờ `final` có thể cùng tồn tại, nhưng không thay thế nhau.

## 8. Lưu ý về `==`, `equals` và string pool

Một câu hỏi khác với chủ đề gán lại là «hai biến còn cùng trỏ tới đối tượng nào?». Ta có thể kiểm tra bằng `==` khi thực sự cần tìm hiểu **identity**, nhưng với nghiệp vụ cần so sánh văn bản nên dùng `equals`.

```java
String a = "Java";
String b = a;
b = new String("Java");

System.out.println(a == b);       // false
System.out.println(a.equals(b));   // true
```

Ở đây phép gán lại `b` làm hai biến không còn chia sẻ cùng đối tượng. Nội dung vẫn bằng nhau, nên `equals` đúng. Chuỗi literal được intern qua *string pool*, nhưng gọi `new String(...)` tạo một đối tượng `String` có danh tính khác. Sự tồn tại của pool không làm hai biến tự gắn kết khi một bên đổi tham chiếu.

Không viết logic nghiệp vụ theo giả định rằng mọi `String` có cùng chữ đều phải `== true`.

## 9. Những nhầm lẫn và lỗi thường gặp

**Nhầm 1 — «Hai biến cùng trỏ nên đổi `b` thì `a` phải đổi».** Sai. `b = ...` chỉ ghi giá trị tham chiếu mới vào biến `b`. Không tồn tại quan hệ đồng bộ phép gán giữa hai biến.

**Nhầm 2 — «`b = b + "!"` là sửa cùng đối tượng cũ».** Sai với `String`. Phép nối tạo ra giá trị chuỗi kết quả, rồi `b` được gán tham chiếu đến kết quả; chuỗi trước đó không bị sửa.

**Nhầm 3 — «Không chia sẻ tham chiếu thì phải dùng `new String(a)`».** Việc gán lại `a` sẽ không ảnh hưởng biến khác ngay cả khi cùng trỏ đến một `String`. Vì `String` bất biến, hầu như không cần tạo bản sao `new String(a)` để chống thay đổi ngoài ý muốn.

**Nhầm 4 — «Truyền tham chiếu nghĩa là phương thức có thể gán lại biến của người gọi».** Java truyền tham trị. Một hàm nhận bản sao giá trị tham chiếu; gán lại tham số chỉ thay đổi biến tham số của hàm.

**Nhầm 5 — «`final` và immutable là một».** `final` áp dụng cho khả năng gán lại biến hoặc trường; bất biến mô tả nội dung của một đối tượng. `final StringBuilder` vẫn có thể `append`.

**Nhầm 6 — «Đối tượng chứa `String` cũng tự động bất biến».** Không. Một trường kiểu `String` có thể được gán giá trị chuỗi khác trong một đối tượng mutable. Các tham chiếu tới chính đối tượng chứa sẽ nhìn thấy trạng thái trường mới.

**Nhầm 7 — «Biến không còn trỏ tới đối tượng cũ thì đối tượng cũ biến mất ngay».** Không nhất thiết. Nếu còn tham chiếu như `first`, đối tượng vẫn có thể được sử dụng. Khi không còn tham chiếu đến đối tượng, JVM mới có thể thu gom nó khi thích hợp; thời điểm thu gom không được bảo đảm.

## 10. Tự luyện tập: dự đoán trước khi chạy

### Bài 1: gán lại nhiều lần

```java
String a = "one";
String b = a;
String c = b;

b = "two";
c = c.concat("!");

System.out.println(a);
System.out.println(b);
System.out.println(c);
```

Kết quả:

```text
one
two
one!
```

Ba biến ban đầu có cùng tham chiếu. Sau đó mỗi phép gán chỉ làm thay đổi **biến ở vế trái**: `b` đổi sang `"two"`; `c` nhận kết quả nối từ `"one"` thành `"one!"`. `a` tiếp tục giữ `"one"`.

### Bài 2: biến đổi trong phương thức có được áp dụng không?

```java
static void update(String value) {
    value = value.replace("a", "o");
}
```

Nếu người gọi có `String text = "Java";` rồi gọi `update(text)`, giá trị `text` có đổi không? **Không.** Biến tham số `value` chỉ được gán lại trong phương thức. Muốn nhận kết quả, hãy đổi phương thức trả về `String` và để người gọi tự gán kết quả.

### Bài 3: đối tượng chứa dùng chung

```java
class Box {
    String value = "A";
}

Box x = new Box();
Box y = x;
String saved = x.value;

y.value = "B";
```

Sau đó `x.value` là `"B"`, `y.value` là `"B"`, nhưng `saved` vẫn là `"A"`. Trường của `Box` dùng chung đã được cập nhật; bản thân hai `String` không bị sửa.

## Kết luận cần ghi nhớ

**Gán lại tham chiếu là cập nhật một biến; không phải sửa đối tượng được tham chiếu, càng không phải cập nhật mọi biến đang trỏ đến đối tượng đó.** Với `String`, tính bất biến bảo đảm các phương thức xử lý chuỗi không làm thay đổi nội dung chuỗi ban đầu. Hãy hỏi chính xác «đang gán lại biến nào?» và «đang sửa trạng thái của đối tượng nào?» khi đọc hoặc viết code. Hai câu hỏi đó giúp tránh nhầm lẫn giữa tham chiếu, object identity và tính bất biến của `String`.