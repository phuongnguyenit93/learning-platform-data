# `throw` để báo lỗi và `throws` để khai báo khả năng phát sinh (Java 17+)

## 1. Phân biệt ngay từ đầu

Java dùng hai từ khóa dễ nhầm:

- **`throw`** là một **câu lệnh** thực sự ném một đối tượng ngoại lệ tại vị trí đang thực thi, thường khi phát hiện dữ liệu hoặc trạng thái không hợp lệ.
- **`throws`** nằm trong **khai báo phương thức hoặc constructor**, liệt kê các loại ngoại lệ có thể được truyền ra cho người gọi. Nó không tự ném, bắt hoặc xử lý ngoại lệ.

Ví dụ cú pháp:

```java
static int requirePositive(int value) throws IllegalArgumentException {
    if (value <= 0) {
        throw new IllegalArgumentException("value must be positive");
    }
    return value;
}
```

Ở đây `throw new IllegalArgumentException(...)` tạo và ném ngoại lệ khi điều kiện đúng. Phần `throws IllegalArgumentException` chỉ khai báo khả năng xảy ra; vì đây là **unchecked exception**, khai báo `throws` là **tùy chọn**. Trong dự án, thường bỏ `throws` cho unchecked exception trừ khi nó giúp diễn đạt hợp đồng API. Ví dụ trên là một phương thức minh họa, chưa phải chương trình độc lập có `main`.

| Tiêu chí | `throw` | `throws` |
| --- | --- | --- |
| Vị trí | Trong thân phương thức, constructor hoặc khối có thể chứa câu lệnh | Sau danh sách tham số của phương thức/constructor, trước phần thân hoặc `;` |
| Vai trò | Ném một đối tượng thuộc `Throwable` | Khai báo một hay nhiều **loại** ngoại lệ có thể phát sinh |
| Dạng thường gặp | `throw new IOException("...");` | `void read() throws IOException` |
| Ảnh hưởng luồng chạy | Dừng luồng thực thi thông thường ở điểm ném, tìm handler phù hợp | Không tạo ngoại lệ và không tự đổi luồng chạy |
| Liên quan checked exception | Ném checked exception phải được bắt hoặc khai báo hợp lệ ở ngữ cảnh bao quanh | Giúp phương thức truyền checked exception cho caller |

Không viết `throws new IOException(...)` hoặc `throw IOException` để ném một instance mới: phải dùng `throw new IOException(...)`. Không dùng `throws` thay thế `catch` nếu yêu cầu nghiệp vụ là xử lý lỗi ngay tại phương thức.

## 2. Ngoại lệ được ném như thế nào?

Khi thực thi gặp `throw exceptionObject;`:

1. Biểu thức được đánh giá; đối tượng được ném phải thuộc lớp con của `java.lang.Throwable`.
2. Luồng thực thi thông thường của đoạn mã hiện tại bị ngắt; các câu lệnh phía sau trên nhánh đó không chạy.
3. Java tìm khối `catch` tương thích trong các `try` đang bao quanh. Nếu không có, ngoại lệ truyền ngược lên phương thức gọi theo call stack.
4. Các khối `finally` thích hợp và cơ chế đóng tài nguyên `try-with-resources` vẫn được thực hiện theo quy tắc ngôn ngữ khi rời phạm vi.
5. Nếu ngoại lệ không được xử lý đến đầu luồng thực thi, trình xử lý ngoại lệ không bắt được của luồng có thể in stack trace; chương trình hoặc luồng liên quan kết thúc bất thường.

Ví dụ:

```java
if (balance < amount) {
    throw new IllegalStateException("insufficient balance");
}
```

Dòng này **thực thi được** nếu nhánh `if` đúng. Nó không đơn thuần ghi chú rằng lỗi có thể xảy ra. `IllegalStateException` là unchecked exception; luật Java không bắt buộc đặt `throws IllegalStateException` trên chữ ký phương thức.

Câu lệnh `throw null;` có thể biên dịch trong ngữ cảnh phù hợp nhưng khi thực thi sẽ phát sinh `NullPointerException`; không nên dùng. Không ném các giá trị không thuộc `Throwable` như chuỗi `"error"` hoặc số `123`.

## 3. Vì sao `throws` bắt buộc với checked exception?

`throws` có vai trò quan trọng nhất khi phương thức có thể cho **checked exception** thoát ra: ví dụ `IOException` hoặc ngoại lệ tự tạo `extends Exception`. Nếu không xử lý bằng `catch`, phương thức phải khai báo `throws` phù hợp. Với `RuntimeException` và `Error` cùng các lớp con (**unchecked**), trình biên dịch không bắt buộc `throws`.

| Ví dụ | Nhóm | Nghĩa vụ khi ngoại lệ có thể thoát ra |
| --- | --- | --- |
| `IOException`, `InvalidScoreException extends Exception` | Checked | Catch hoặc khai báo throws |
| `IllegalArgumentException`, `NumberFormatException` | Unchecked | Có thể throw mà không khai báo |
| `StackOverflowError` | Unchecked Error | Không cần khai báo; không dùng như lỗi nghiệp vụ |

Điều này không có nghĩa checked luôn xảy ra hoặc unchecked luôn là lỗi lập trình. Bài sau phân tích cây `Throwable`, các lớp cụ thể và cách chọn hợp đồng. Trong bài này, hãy phân biệt rõ **`throw` ném một object tại runtime** với **`throws` liệt kê kiểu ngoại lệ ở chữ ký**.


## 4. Ví dụ đầy đủ: tự ném checked exception và khai báo `throws`

Ví dụ nhận điểm từ chuỗi. Nếu không phải số nguyên hoặc ngoài khoảng 0 đến 100, phương thức sẽ **`throw`** ngoại lệ tự định nghĩa. Vì `InvalidScoreException extends Exception`, phương thức phải **`throws InvalidScoreException`**, và `main` sẽ `catch` để xử lý từng đầu vào.

Tạo một tệp tên **`ThrowThrowsDemo.java`**:

```java
public class ThrowThrowsDemo {
    static int parseScore(String text) throws InvalidScoreException {
        final int score;
        try {
            score = Integer.parseInt(text);
        } catch (NumberFormatException cause) {
            throw new InvalidScoreException("invalid integer: " + text, cause);
        }

        if (score < 0 || score > 100) {
            throw new InvalidScoreException("score out of range: " + score);
        }
        return score;
    }

    public static void main(String[] args) {
        String[] inputs = {"95", "150", "abc"};

        for (String input : inputs) {
            try {
                System.out.println(input + " => " + parseScore(input));
            } catch (InvalidScoreException ex) {
                System.out.println(input + " => " + ex.getMessage());
            }
        }
    }
}

class InvalidScoreException extends Exception {
    InvalidScoreException(String message) {
        super(message);
    }

    InvalidScoreException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Chạy tại thư mục chứa tệp (JDK 17+, PowerShell, CMD, bash). Tạo thư mục `out` nếu chưa có:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out ThrowThrowsDemo.java
java -cp out ThrowThrowsDemo
```

**Stdout chính xác của chương trình:**

```text
95 => 95
150 => score out of range: 150
abc => invalid integer: abc
```

Giải thích theo luồng:

- Với `95`, `parseScore` trả về `95`, không ném ngoại lệ.
- Với `150`, điều kiện kiểm tra khoảng điểm đúng; `throw new InvalidScoreException(...)` chuyển điều khiển đến `catch` trong `main`. `return score;` không được thực hiện cho lần gọi đó.
- Với `abc`, `Integer.parseInt` ném `NumberFormatException` (unchecked); `catch` chuyển nó thành `InvalidScoreException` (checked) và truyền **nguyên nhân gốc** qua `super(message, cause)`.
- `throws InvalidScoreException` trong chữ ký giúp caller biết nghĩa vụ bắt hoặc khai báo ngoại lệ checked. Chính các câu lệnh `throw` mới làm ngoại lệ xuất hiện.
- Vòng `for` tiếp tục sau từng `catch`, nên cả ba dòng được in.

Kiểu `InvalidScoreException` là lớp top-level không `public` cùng tệp, hợp lệ vì tệp chỉ có một kiểu top-level `public` là `ThrowThrowsDemo`. Nếu chuyển ngoại lệ thành `public class InvalidScoreException`, cần đặt riêng trong `InvalidScoreException.java`.

## 5. Unchecked exception: có `throw`, không cần `throws`

Với tiền điều kiện của API, `IllegalArgumentException` thường phù hợp. Tạo **`UncheckedDemo.java`**:

```java
public class UncheckedDemo {
    static int percentage(int part, int total) {
        if (total <= 0) {
            throw new IllegalArgumentException("total must be positive");
        }
        if (part < 0 || part > total) {
            throw new IllegalArgumentException("part out of range");
        }
        return part * 100 / total;
    }

    public static void main(String[] args) {
        System.out.println("percent=" + percentage(3, 4));

        try {
            System.out.println(percentage(2, 0));
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```sh
javac -encoding UTF-8 --release 17 -d out UncheckedDemo.java
java -cp out UncheckedDemo
```

Output:

```text
percent=75
error=total must be positive
```

Không có `throws IllegalArgumentException` trong `percentage` nhưng chương trình vẫn hợp lệ. Caller có thể bắt ngoại lệ này khi có phương án xử lý hữu ích; việc bắt không phải điều kiện biên dịch. Trong code sản xuất, hãy cân nhắc phép tính phần trăm khi dùng số nguyên lớn vì `part * 100` có thể tràn `int`; ví dụ ở đây dùng số nhỏ để minh họa cơ chế ngoại lệ.

## 6. Caller bắt hoặc khai báo để truyền tiếp checked exception

Giả sử một phương thức thực thi `throw new java.io.IOException(...)`. Đối với checked exception, có hai cách hợp lệ ở caller:

**Cách A — bắt để xử lý tại chỗ:**

```java
try {
    readData();
} catch (java.io.IOException ex) {
    System.out.println("Read failed: " + ex.getMessage());
}
```

**Cách B — khai báo `throws` để trách nhiệm xử lý được chuyển lên caller tiếp theo:**

```java
static void relay() throws java.io.IOException {
    readData();
}
```

Hai đoạn trên chỉ minh họa phần thân phương thức; để chạy độc lập cần định nghĩa `readData()` và ngữ cảnh bao quanh. `throws` không tự bọc ngoại lệ bằng `try/catch`, nên nếu quá trình gọi không có handler, ngoại lệ vẫn có thể truyền lên.

Một ví dụ **đầy đủ, chạy được** chứng minh lan truyền: tạo `PropagationDemo.java`:

```java
import java.io.IOException;

public class PropagationDemo {
    static String readData() throws IOException {
        throw new IOException("sample read failure");
    }

    static String relay() throws IOException {
        return readData();
    }

    public static void main(String[] args) {
        try {
            System.out.println(relay());
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

Chạy:

```sh
javac -encoding UTF-8 --release 17 -d out PropagationDemo.java
java -cp out PropagationDemo
```

Output:

```text
caught=sample read failure
```

Chuỗi gọi là `main → relay → readData`. `readData` ném `IOException`; `relay` khai báo để truyền tiếp; `main` bắt và in thông báo. Đây là ngoại lệ được tạo có chủ đích để minh họa, không có thao tác đọc tệp thực tế.

## 7. Lỗi biên dịch phổ biến khi dùng `throw`/`throws`

### 7.1. Ném checked exception mà không bắt/khai báo

Đoạn dưới **cố ý không biên dịch được**:

```java
import java.io.IOException;

class InvalidChecked {
    static void load() {
        throw new IOException("cannot read");
    }
}
```

`javac` thường báo ngoại lệ `IOException` cần được bắt hoặc khai báo. Có thể sửa chữ ký thành:

```java
static void load() throws java.io.IOException {
    throw new java.io.IOException("cannot read");
}
```

Đây là phương thức minh họa; caller sau đó vẫn phải bắt hoặc khai báo checked exception thích hợp.

### 7.2. Caller không xử lý ngoại lệ được khai báo

Đoạn dưới cũng **cố ý sai**:

```java
static void caller() {
    relay(); // relay() khai báo throws IOException
}
```

Nếu phương thức `relay()` được định nghĩa như trong `PropagationDemo`, cần đổi thành `static void caller() throws IOException { relay(); }` (khi đã import `IOException`) hoặc đặt lời gọi trong `try/catch(IOException ex)`.

### 7.3. Khai báo rộng hơn mức cần thiết

`throws Exception` có thể hợp lệ nhưng làm giảm thông tin: caller không biết nhóm lỗi được dự kiến. Ưu tiên ngoại lệ cụ thể như `throws IOException` hoặc `throws InvalidScoreException`. Nếu cần nhiều checked exception độc lập, có thể liệt kê bằng dấu phẩy:

```java
void work() throws java.io.IOException, java.text.ParseException
```

Dòng này chỉ minh họa **chữ ký**; một khai báo phương thức đầy đủ cần có thân `{ ... }` hoặc dạng khai báo hợp lệ trong interface/abstract type.

### 7.4. Hiểu sai ý nghĩa của `throws`

Khai báo `throws IOException` **không bảo đảm** phương thức sẽ ném `IOException` mỗi lần gọi. Nó chỉ thể hiện ngoại lệ đó được phép truyền qua chữ ký. Ngược lại, chỉ đọc chữ ký mà không thấy `throws RuntimeException` không có nghĩa mã sẽ không gặp unchecked exception.

## 8. Giữ nguyên nguyên nhân và ngữ cảnh lỗi

Nếu chuyển một ngoại lệ thấp tầng thành ngoại lệ mang ý nghĩa nghiệp vụ, hãy bảo tồn nguyên nhân ban đầu:

```java
try {
    return Integer.parseInt(text);
} catch (NumberFormatException cause) {
    throw new InvalidScoreException("invalid integer: " + text, cause);
}
```

Đây là đoạn lấy từ ví dụ `ThrowThrowsDemo`; nó phụ thuộc vào lớp `InvalidScoreException` đã định nghĩa. Chuyển nguyên nhân vào constructor làm `ex.getCause()` còn giữ được `NumberFormatException`, phục vụ log/debug. Chỉ `throw new InvalidScoreException("...")` mà bỏ `cause` sẽ làm mất liên kết nguyên nhân. `throw cause;` trong khối `catch` lại là ném chính đối tượng đã bắt (rethrow), không phải chuyển sang một loại checked exception mới.

Đừng che giấu lỗi bằng `catch (Exception ex) { }` rỗng hoặc trả về giá trị mặc định không có căn cứ. Nếu handler không thể xử lý đúng, truyền tiếp ngoại lệ có thông điệp/nguồn gốc phù hợp thường tốt hơn.

Khi ném ngoại lệ sau khi đã mở tài nguyên, dùng `try-with-resources` với loại tài nguyên thực thi `AutoCloseable` để đóng tài nguyên kể cả khi có ngoại lệ. Hạn chế `return`/`throw` từ `finally` vì có thể làm khó nhận biết ngoại lệ trước đó; trong trường hợp đặc biệt, một ngoại lệ từ `finally` có thể thay thế ngoại lệ đang được truyền ra.

## 9. Lưu ý về phương thức ghi đè và constructor

- Phương thức **override** không được bổ sung hoặc mở rộng checked exception vượt những gì chữ ký phương thức được ghi đè cho phép. Ví dụ, nếu method cha không khai báo checked exception thì method override không được tự thêm `throws IOException`. Ngoại lệ unchecked không chịu giới hạn cùng kiểu này.
- Constructor có thể dùng `throws` để công bố checked exception khi khởi tạo. Caller tạo đối tượng phải bắt hoặc khai báo.
- `main(String[] args)` cũng có thể khai báo `throws Exception`; cách đó thuận tiện trong thử nghiệm nhỏ nhưng khi ngoại lệ không được bắt chương trình có thể kết thúc với stack trace. Ứng dụng thường cần xử lý lỗi tại ranh giới thích hợp.

Ví dụ minh họa một constructor có khai báo checked exception (chưa phải chương trình độc lập):

```java
class ConnectionConfig {
    ConnectionConfig(String address) throws java.io.IOException {
        if (address == null || address.isBlank()) {
            throw new java.io.IOException("missing address");
        }
    }
}
```

Khi gọi `new ConnectionConfig("")`, ngoại lệ phát sinh từ `throw`; `throws` ở constructor buộc caller xử lý hoặc truyền tiếp.

## 10. Quy tắc chọn cách viết trong thực tế

1. **Phát hiện trạng thái sai tại đúng chỗ:** dùng `throw new ...` với loại ngoại lệ, message và cause thích hợp.
2. **Ngoại lệ checked có thể truyền ra:** dùng `throws LoaiNgoaiLe` trong chữ ký nếu không xử lý tại chỗ; để caller quyết định chính sách phục hồi.
3. **Xử lý được ngay tại nơi gọi:** dùng `try/catch` có hành động hữu ích; kiểm thử cả nhánh thành công và thất bại.
4. **Không dùng exception làm nhánh điều khiển bình thường** cho dữ liệu dự kiến có thể kiểm tra đơn giản; kiểm tra đầu vào và dùng API báo kết quả thích hợp khi hợp đồng yêu cầu.
5. **Kiểm tra đầy đủ:** lỗi biên dịch (`unreported exception`), đường truyền ngoại lệ, thông điệp, cause và cách tài nguyên được đóng.

### Tự kiểm tra

- `throw` và `throws` khác nhau ở đâu? **`throw` ném đối tượng trong lúc chạy; `throws` khai báo loại ngoại lệ trong chữ ký.**
- Ném `IOException` khỏi một phương thức không có `try/catch` thì cần gì? **Khai báo `throws IOException` (hoặc loại supertype thích hợp) để compile hợp lệ.**
- Ném `IllegalArgumentException` có bắt buộc viết `throws` không? **Không**, vì unchecked.
- Chỉ thêm `throws IOException` có làm ngoại lệ biến mất không? **Không**. Nếu nó thực sự phát sinh, ngoại lệ sẽ truyền cho caller cho đến khi được xử lý hoặc không được bắt.
- Vì sao lưu `cause` khi ném ngoại lệ khác loại? **Để giữ bằng chứng của lỗi gốc** và giúp truy vết.

**Ghi nhớ:** `throw` là hành động báo lỗi; `throws` là cam kết về các checked exception có thể truyền ra theo hợp đồng phương thức. Viết đúng cả hai giúp xử lý lỗi có chủ đích và giữ thông tin chẩn đoán.
