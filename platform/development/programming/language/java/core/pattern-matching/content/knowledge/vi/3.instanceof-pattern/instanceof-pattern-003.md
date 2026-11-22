# Đọc pattern variable trong nhánh true của `instanceof` (Java 21)

Trong Java, câu lệnh `if` thường bắt đầu bằng một phép kiểm tra kiểu. Với **pattern matching for `instanceof`**, ta có thể vừa kiểm tra kiểu, vừa khai báo biến có kiểu chính xác ngay trong điều kiện. Bài này tập trung vào việc **đọc và sử dụng pattern variable khi điều kiện khớp và nhánh `true` được thực thi**.

Sau bài học, bạn cần hiểu được vì sao biến dùng được trong thân `if`, compiler biết kiểu của biến bằng cách nào, khi nào biến không còn dùng được và cách viết điều kiện kết hợp mà không gặp lỗi phạm vi biến.

## 1. Từ `instanceof` truyền thống đến pattern variable

Trước khi có pattern matching, người viết thường kiểm tra kiểu rồi ép kiểu bằng tay:

```java
Object value = "Java";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.toUpperCase());
}
```

Từ Java 16, dạng type pattern cho `instanceof` đã là tính năng ổn định. Trên Java 21, có thể viết tương đương:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Trong `value instanceof String text`:

- `value` là biểu thức được kiểm tra.
- `String` là kiểu cần khớp.
- `text` là **pattern variable**, có kiểu tĩnh `String`.
- Phép `instanceof` trả về `true` khi giá trị là đối tượng phù hợp kiểu `String` (bao gồm trường hợp kiểm tra kiểu supertype phù hợp trong các ví dụ khác), và `false` nếu không khớp hoặc giá trị là `null`.

Khi phép kiểm tra thành công, Java liên kết chính đối tượng trong `value` với biến `text`. **Không tạo một chuỗi mới và không cần viết cast `(String) value`**. Trình biên dịch đã biết `text` là `String`, nên gọi `length()`, `strip()`, `isBlank()` hay các method của `String` là hợp lệ.

> Phần quan trọng: pattern variable chỉ được dùng tại vị trí mà trình biên dịch chứng minh pattern đã khớp. Quy tắc này gọi là *flow scoping* — phạm vi biến phụ thuộc vào luồng điều khiển chương trình.

## 2. Tại sao đọc được biến trong nhánh `true`?

Xem câu lệnh:

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Luồng thực thi được hiểu như sau:

1. Java tính giá trị của `value` và kiểm tra `instanceof String`.
2. Nếu kiểm tra **đúng**, pattern `String text` khớp: biến `text` được gán tham chiếu tới đối tượng đã kiểm tra.
3. Chỉ lúc đó thân `if` mới chạy; đọc `text.length()` là an toàn về kiểu.
4. Nếu kiểm tra **sai**, thân `if` bị bỏ qua, nên chương trình không tìm cách đọc `text` khi biến chưa được gán.

Chẳng hạn, với `value = "abc"`, chương trình in `3`; với `value = 123` hoặc `value = null`, thân `if` không chạy và method không in gì.

Pattern variable ở đây là một biến có tên và kiểu rõ ràng, không phải giá trị boolean hay một “kết quả ép kiểu” vô danh. Bạn dùng `text` trực tiếp trong nhánh `true` giống một biến cục bộ `String` thông thường:

```java
if (value instanceof String text) {
    String normalized = text.strip();
    int length = text.length();
    System.out.println("normalized=" + normalized);
    System.out.println("length=" + length);
}
```

Đoạn này giả định `value` đã được khai báo trong method hoặc phạm vi chứa nó; đây là ví dụ minh họa, chưa phải chương trình độc lập.

## 3. Nhánh `else` và vị trí sau `if` không tự có biến

Với điều kiện không phủ định `value instanceof String text`, nhánh `true` là đường đi đã khớp, còn nhánh `else` là đường đi **không khớp**:

```java
static void inspect(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip()); // HỢP LỆ
    } else {
        System.out.println("Not a String");
        // System.out.println(text); // LỖI BIÊN DỊCH
    }

    // System.out.println(text); // LỖI trong cấu trúc if/else này
}
```

Đừng hiểu việc khai báo `text` trong điều kiện là khai báo nó cho toàn method. Compiler chỉ cho dùng ở những đoạn mã có bằng chứng rằng điều kiện khớp. Nếu biến cần dùng ở nhiều đường đi, hãy thiết kế lại luồng xử lý hoặc khai báo một biến thích hợp trong phạm vi chung.

Có một ngoại lệ quan trọng để tránh hiểu sai: **flow scoping không chỉ dựa trên cặp ngoặc nhọn**. Nếu nhánh không khớp kết thúc method, compiler có thể cho dùng biến sau `if`:

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length(); // HỢP LỆ: mọi đường đi tới đây đều đã khớp
}
```

Ở ví dụ này, `return 0` chặn mọi đường đi không khớp; vì vậy `text` được xác định chắc chắn tại câu lệnh cuối. Đây vẫn là cùng một nguyên tắc: **chỉ đọc khi compiler chứng minh pattern thành công**.

## 4. Kết hợp `&&`: đọc biến ngay trong điều kiện và trong nhánh `true`

Phép `&&` trong Java có tính chất **short-circuit**: vế phải chỉ được tính khi vế trái là `true`. Nhờ đó, ta có thể kiểm tra kiểu rồi sử dụng pattern variable để kiểm tra nội dung:

```java
static void printNonBlank(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        System.out.println(text.strip());
    }
}
```

Trật tự này an toàn:

1. `value instanceof String text` được đánh giá trước.
2. Chỉ khi khớp `String`, Java mới tính `!text.isBlank()` ở vế phải.
3. Nếu **cả hai** điều kiện đúng, thân `if` chạy và `text` có sẵn để đọc.

Với `null` hoặc một đối tượng không phải `String`, Java bỏ qua lời gọi `text.isBlank()`, vì vế trái `&&` đã sai. Với chuỗi chỉ chứa khoảng trắng, phép khớp kiểu đúng nhưng kiểm tra `!text.isBlank()` sai, nên thân `if` cũng không chạy.

Ngược lại, không được coi `||` tương đương `&&`. Với `||`, vế phải có thể làm toàn điều kiện đúng dù type pattern ở vế trái không khớp:

```java
// KHÔNG BIÊN DỊCH: text không chắc đã được gán trong nhánh true.
if (value instanceof String text || value == null) {
    System.out.println(text.length());
}
```

Nếu cần xử lý cả `null` và chuỗi, hãy tách các nhánh và chỉ dùng `text` trong nhánh đã khớp. Ví dụ:

```java
if (value == null) {
    System.out.println("missing");
} else if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("other type");
}
```

Các đoạn trong mục này là mã minh họa đặt trong method có biến `value` kiểu `Object`.

## 5. Phủ định điều kiện sẽ đổi nhánh nào được dùng biến

Xem điều kiện có dấu `!`:

```java
if (!(value instanceof String text)) {
    System.out.println("Not a String");
} else {
    System.out.println(text.length()); // HỢP LỆ
}
```

Nhánh `true` của **toàn biểu thức phủ định** bây giờ có nghĩa là phép khớp kiểu đã **thất bại**, nên không thể đọc `text` trong nhánh đó. Nhánh `else` mới là nơi compiler biết pattern đã khớp. Điều cần theo dõi là sự thật về phép khớp, không chỉ chữ `true` nằm ở nhánh nào.

Để học `instanceof` cơ bản dễ nhất, nên bắt đầu với dạng không phủ định `if (value instanceof String text)`: lúc ấy đọc biến trong thân `if` rất trực quan.

## 6. Ví dụ Java 21 chạy độc lập và stdout chính xác

Tạo file **`PatternVariableTrueBranchDemo.java`** với toàn bộ nội dung sau:

```java
public class PatternVariableTrueBranchDemo {

    static void inspect(Object value) {
        if (value instanceof String text) {
            System.out.println("Raw length: " + text.length());
            System.out.println("Trimmed: " + text.strip());
        } else {
            System.out.println("Not String");
        }
    }

    static void inspectNonBlank(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            System.out.println("Nonblank: " + text.strip());
        } else {
            System.out.println("Not nonblank String");
        }
    }

    public static void main(String[] args) {
        inspect("  Java 21  ");
        inspect(42);
        inspect(null);
        inspectNonBlank("  Hello  ");
        inspectNonBlank("   ");
    }
}
```

Dùng **JDK 21** để biên dịch và chạy (không cần bật preview feature):

```bash
javac --release 21 PatternVariableTrueBranchDemo.java
java PatternVariableTrueBranchDemo
```

Kết quả chuẩn trên stdout:

```text
Raw length: 11
Trimmed: Java 21
Not String
Not String
Nonblank: Hello
Not nonblank String
```

Giải thích theo thứ tự:

- `inspect("  Java 21  ")`: đối tượng là `String`, nên vào nhánh `true`; `text.length()` đếm 11 ký tự, kể cả hai khoảng trắng đầu và cuối; `text.strip()` trả về `Java 21`.
- `inspect(42)`: đối tượng thực tế là `Integer`, không khớp `String`, nên in `Not String`.
- `inspect(null)`: `null instanceof String` là `false`; không có `NullPointerException` chỉ vì phép `instanceof`.
- `inspectNonBlank("  Hello  ")`: vừa khớp kiểu, vừa không phải chuỗi trắng, nên in `Nonblank: Hello`.
- `inspectNonBlank("   ")`: vẫn khớp `String`, nhưng không qua điều kiện `!text.isBlank()`, nên vào nhánh `else`.

Ví dụ chứng minh hai vai trò khác nhau: `instanceof` bảo đảm **đúng kiểu**, còn `!text.isBlank()` kiểm tra thêm một **điều kiện về dữ liệu**. Pattern matching không tự xác nhận chuỗi hợp lệ theo yêu cầu nghiệp vụ.

## 7. Lỗi thường gặp khi đọc pattern variable

**Lỗi 1 — dùng biến ở nhánh không khớp.** Trong `else` của `if (value instanceof String text)`, `text` không được bảo đảm tồn tại. Chuyển thao tác dùng `text` vào nhánh đúng, hoặc viết lại luồng xử lý.

**Lỗi 2 — dùng biến sau `if` mà bỏ qua đường đi sai.** Với `if` thông thường có thể chạy tiếp dù phép khớp thất bại, không được đọc `text` sau khối. Chỉ một số cấu trúc flow scoping có nhánh không khớp kết thúc rõ ràng (như early return ở mục 3) mới cho phép.

**Lỗi 3 — dùng `||` như thể nhánh `true` luôn khớp pattern.** Một vế khác của `||` có thể làm điều kiện đúng. Dùng `&&` khi muốn kiểm tra thêm thuộc tính của chính biến pattern sau khi kiểm tra kiểu.

**Lỗi 4 — ép kiểu lại không cần thiết.** Trong nhánh `true`, `text` đã có kiểu `String`. Viết `((String) value).length()` là thừa, làm giảm tính rõ ràng và không tận dụng được biến vừa khai báo.

**Lỗi 5 — nghĩ rằng khớp `String` đồng nghĩa dữ liệu không trống.** Chuỗi `""` hoặc `"   "` vẫn làm `instanceof String` đúng. Nếu cần không rỗng, hãy thêm `!text.isEmpty()` hoặc `!text.isBlank()`, tùy yêu cầu.

**Lỗi 6 — nhầm pattern variable với một phép cast cho mọi loại dữ liệu.** `instanceof String text` chỉ thành công với đối tượng phù hợp `String`. Nó không chuyển `Integer` thành chuỗi hay tự động parse dữ liệu.

## 8. Tự kiểm tra

Cho `Object value = "abc";` và biểu thức:

```java
if (value instanceof String text && text.length() == 3) {
    System.out.println(text.toUpperCase());
}
```

Đây là đoạn mã hợp lệ bên trong một method; câu lệnh in `ABC`. Vì type pattern đã khớp, `text` có kiểu `String` cả trong vế phải của `&&` lẫn bên trong nhánh `true`.

Thay `value` bằng `null`: nhánh `if` không chạy và `text.length()` ở vế phải không được đánh giá. Thay `value` bằng `"ab"`: phép khớp kiểu thành công nhưng điều kiện độ dài sai, nên nhánh cũng không chạy. Nếu đổi `&&` thành `||`, chương trình không còn bảo đảm `text` đã khớp để đọc trong thân `if`.

Khi đọc bất kỳ pattern variable nào, hãy tự hỏi: **“Tại vị trí này, mọi đường đi có thể tới đây đều đã khớp pattern chưa?”** Nếu câu trả lời là có, compiler cho dùng biến; nếu không, cần đổi cấu trúc điều kiện hoặc xử lý dữ liệu ở nhánh phù hợp.
