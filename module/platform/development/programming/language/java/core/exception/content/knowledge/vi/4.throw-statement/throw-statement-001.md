# Cú pháp `throw` và yêu cầu kiểu `Throwable` trong Java

> **Phạm vi:** Java Core → Exception → Lệnh `throw`. Câu lệnh `throw` dùng để **ném một đối tượng biểu diễn lỗi hoặc tình huống bất thường**, làm luồng thực thi rời khỏi đường đi bình thường. Trong Java, biểu thức sau `throw` phải có kiểu phù hợp với `java.lang.Throwable`; kiểm tra kiểu lúc biên dịch khác với việc xác định đối tượng nào thực sự được ném khi chạy.

## 1. Cú pháp chuẩn của `throw`

Dạng tổng quát:

```java
throw expression;
```

Trong đó:

- `throw` là từ khóa Java.
- `expression` phải là biểu thức có kiểu tham chiếu có thể gán cho `Throwable` (bao gồm trường hợp biểu thức `null`; xem Mục 7).
- Dấu chấm phẩy `;` kết thúc **câu lệnh**.
- Khi chạy, biểu thức được đánh giá, sau đó đối tượng `Throwable` tương ứng được ném. Nếu giá trị nhận được là `null`, JVM ném `NullPointerException` thay thế.
- `throw` là một **statement**, không phải một toán tử trả giá trị hoặc một expression thông thường.

Cách viết thường gặp nhất:

```java
throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
```

`new IllegalArgumentException(...)` tạo đối tượng ngoại lệ; `throw` ném đối tượng đó. Chỉ khởi tạo ngoại lệ mà không ném thì không làm luồng thực thi chuyển sang đường xử lý lỗi:

```java
new IllegalArgumentException("Giá trị không hợp lệ"); // Chỉ tạo đối tượng.
```

**Kết luận đầu tiên:** `throw` không phải lời gọi hàm trả về một giá trị đặc biệt. Nó là câu lệnh điều khiển luồng thực thi bằng một `Throwable`.

### 1.1. Những hình thức hợp lệ

Các đoạn sau là **mảnh code minh họa bên trong một method**, chưa phải chương trình độc lập:

```java
// Tạo rồi ném một unchecked exception.
throw new IllegalArgumentException("Sai tham số");
```

```java
// Ném đối tượng exception đã có (phương thức phải khai báo/bắt nếu checked).
java.io.IOException cause = new java.io.IOException("Lỗi đọc");
throw cause;
```

```java
// Dùng biểu thức điều kiện tạo ra một trong hai RuntimeException.
throw invalidInput
        ? new IllegalArgumentException("Dữ liệu sai")
        : new IllegalStateException("Trạng thái sai");
```

Đoạn thứ ba giả định `invalidInput` đã được khai báo là `boolean`. Toàn bộ biểu thức điều kiện trả về một đối tượng phù hợp với `Throwable`. Tuy nhiên bản thân `throw` vẫn là **câu lệnh**; không thể đặt tùy ý như một nhánh trả giá trị của toán tử `?:`.

Ví dụ sai:

```java
// KHÔNG hợp lệ: throw là statement, không là expression trong toán tử ?:.
// int value = condition ? 10 : throw new IllegalArgumentException();
```

Cách diễn đạt đúng là dùng `if`/`throw` rồi trả giá trị hợp lệ ở nhánh còn lại.

### 1.2. `throw` không phải `throws`

| Tiêu chí | `throw` | `throws` |
| --- | --- | --- |
| Vị trí | Trong thân phương thức, constructor, khối lệnh phù hợp | Trong khai báo phương thức hoặc constructor |
| Vai trò | Thực sự ném một đối tượng `Throwable` | Khai báo các loại exception có thể thoát ra, đặc biệt là checked exceptions |
| Dạng | `throw new IOException("...");` | `void read() throws IOException { ... }` |
| Số đối tượng/loại | Mỗi câu lệnh ném một giá trị `Throwable` tại lần chạy đó | Có thể liệt kê nhiều kiểu sau dấu phẩy |
| Ảnh hưởng lên control flow | Làm đường thực thi bình thường tại đó dừng | Tự nó không ném đối tượng nào |
| Có thể dùng cùng nhau? | Có | Có; một method có thể `throw` exception checked và khai báo `throws` tương ứng |

Ví dụ method minh họa:

```java
static void requireData(String data) throws java.io.IOException {
    if (data == null) {
        throw new java.io.IOException("Thiếu dữ liệu");
    }
}
```

`throws IOException` thông báo cho caller nghĩa vụ xử lý/khai báo; `throw new IOException(...)` mới phát sinh ngoại lệ khi `data == null`. Lựa chọn `IOException` trong ví dụ nhằm diễn đạt lỗi dữ liệu từ nguồn I/O; để kiểm tra tham số đầu vào thuần túy, `IllegalArgumentException` hoặc `NullPointerException` có thể đúng ngữ nghĩa hơn.

## 2. Vì sao bắt buộc phải tương thích với `Throwable`?

Java định nghĩa cây kế thừa của các đối tượng có thể ném qua `throw`:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   ├── java.io.IOException
    │   └── java.lang.RuntimeException
    │       ├── IllegalArgumentException
    │       ├── NullPointerException
    │       └── IllegalStateException
    └── java.lang.Error
        ├── AssertionError
        ├── LinkageError
        └── VirtualMachineError
```

Đây là một phần tiêu biểu của cây, không phải danh sách đầy đủ.

- `Throwable` là lớp cha chung của `Exception` và `Error`.
- `Exception` là nhánh thường dùng cho các tình huống ngoại lệ của chương trình.
- `RuntimeException extends Exception`: những exception này là **unchecked**.
- `Error extends Throwable`: cũng là unchecked, nhưng thông thường không nên tạo/bắt để mô phỏng lỗi nghiệp vụ.
- Có thể tạo lớp `extends Throwable` trực tiếp; Java cho phép về cú pháp, nhưng thực tế thường chọn `Exception` hoặc `RuntimeException` cho API ứng dụng.

Việc kiểu phải là `Throwable` bảo đảm cơ chế `throw`/`catch` làm việc với đối tượng có đặc tính của Throwable, như thông điệp lỗi, nguyên nhân, stack trace, suppressed exceptions và phân cấp kiểu rõ ràng. Nó cũng giúp trình biên dịch kiểm tra hợp đồng checked exception.

### 2.1. Biểu thức `throw` có thể là những gì?

Một biểu thức hợp lệ có thể có dạng:

- `new SomeException(...)` — tạo và ném ngay.
- `throw e;` — ném biến tham chiếu đến một ngoại lệ.
- `throw createException();` — ném giá trị trả về từ phương thức có kiểu phù hợp.
- `throw condition ? exceptionA : exceptionB;` — ném kết quả của một biểu thức điều kiện có kiểu tương thích.
- `throw null;` — hợp lệ cú pháp nhưng khi chạy ném `NullPointerException`, không phải cách khuyến khích viết.

Kiểu được xem xét khi biên dịch là **kiểu tĩnh của biểu thức**; đối tượng cụ thể được ném khi chạy mang kiểu runtime thực tế, quyết định `catch` nào phù hợp.

## 3. Ví dụ Java 17 chạy được: kiểm tra đầu vào bằng `throw`

Tạo tệp `ThrowBasicDemo.java`:

```java
public class ThrowBasicDemo {
    static int requirePositive(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("Giá trị phải dương");
        }
        return value;
    }

    public static void main(String[] args) {
        for (int input : new int[] {5, 0, -2}) {
            try {
                int result = requirePositive(input);
                System.out.println("OK: " + result);
            } catch (IllegalArgumentException e) {
                System.out.println("Lỗi " + input + ": " + e.getMessage());
            }
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ThrowBasicDemo.java
java ThrowBasicDemo
```

Stdout chính xác:

```text
OK: 5
Lỗi 0: Giá trị phải dương
Lỗi -2: Giá trị phải dương
```

**Đường đi với từng input:**

1. `5`: điều kiện `value <= 0` sai, trả về `5` rồi in `OK: 5`.
2. `0`: tạo `IllegalArgumentException`, ném bằng `throw`; câu `return value` không chạy. `catch` ở `main` nhận đối tượng và in thông điệp.
3. `-2`: tương tự `0`; vòng lặp vẫn tiếp tục sau khi `catch` hoàn thành.

Một ngoại lệ **không tự động kết thúc toàn bộ JVM**. Nó làm luồng thực thi thay đổi; có thể được xử lý ở caller, truyền tiếp, hoặc nếu không được xử lý có thể làm thread kết thúc bất thường.

### 3.1. Vì sao dùng `IllegalArgumentException`?

Phương thức `requirePositive` có tiền điều kiện tham số phải dương. `IllegalArgumentException` diễn đạt rõ việc caller truyền dữ liệu vi phạm hợp đồng, là unchecked exception nên không cần khai báo `throws`. Nếu đầu vào sai là trạng thái thường xuyên dự kiến (chẳng hạn kiểm tra form), một API trả về kết quả validation có cấu trúc cũng có thể phù hợp. Chọn cách nào là quyết định thiết kế, không phải một yêu cầu của cú pháp `throw`.

## 4. Các kiểu không hợp lệ sau `throw`

Các ví dụ sau **cố ý sai để giải thích quy tắc**, không dùng trong tệp Java chạy:

```java
throw "Không hợp lệ";           // Sai: String không extends Throwable.
throw 123;                     // Sai: int là primitive.
throw new Object();            // Sai: Object không phải Throwable.
throw System.out.println("x"); // Sai: println() trả về void.
```

Không thể chỉ có tên `Error`/`Exception` trong text mà biến nó thành exception. Cần một **đối tượng thực tế thuộc kiểu Throwable** hoặc biểu thức hợp lệ có kiểu phù hợp.

Ví dụ muốn báo lỗi từ chuỗi, viết:

```java
throw new IllegalStateException("Không hợp lệ");
```

Java không có cơ chế chuyển mọi đối tượng `Object` thành một Throwable bằng ép kiểu. Thử `(Throwable) new Object()` có thể qua kiểm tra kiểu trong một số ngữ cảnh nếu cast reference được cho phép, nhưng tại runtime sẽ thất bại do đối tượng không phải Throwable; không nên dùng cast để né yêu cầu kiểu.

### 4.1. Kiểu tĩnh quan trọng ngay cả khi đối tượng runtime đúng

Đoạn minh họa dưới đây:

```java
Object problem = new IllegalArgumentException("Dữ liệu sai");
// throw problem; // Không biên dịch: kiểu tĩnh Object không gán được cho Throwable.
```

Cùng một đối tượng nhưng được giữ trong biến kiểu `Object`. Để ném, cần thu hẹp kiểu một cách hợp lệ, ví dụ:

```java
Object problem = new IllegalArgumentException("Dữ liệu sai");
if (problem instanceof Throwable failure) {
    throw failure; // Kiểu tĩnh Throwable: còn phải xét quy tắc checked exception.
}
```

Đoạn trên **không phải chương trình hoàn chỉnh**. `failure` có kiểu tĩnh `Throwable`, nên method chứa nó thông thường phải bắt hoặc khai báo `throws Throwable`, mặc dù đối tượng cụ thể lúc chạy là `IllegalArgumentException`. Không nên lạm dụng `throws Throwable` chỉ để phù hợp với một biến quá tổng quát; nếu biết chắc chỉ ném unchecked exception, nên biểu đạt kiểu `RuntimeException` ngay trong hợp đồng.

### 4.2. `Throwable` là kiểu tham chiếu, không phải một chuỗi/mã lỗi

`throw` không nhận mã lỗi `404`, text `"not found"` hay giá trị `false` như một vài ngôn ngữ khác. Có thể đặt những dữ liệu đó trong exception (message, field, mã trạng thái) nhưng đối tượng được ném vẫn phải là `Throwable`.

## 5. Checked và unchecked ảnh hưởng đến `throw` thế nào?

Hãy tách hai bước:

1. **Kiểm tra kiểu:** biểu thức sau `throw` phải có kiểu phù hợp với `Throwable`.
2. **Kiểm tra checked exception:** nếu exception có thể thoát ra là checked, code phải bắt hoặc khai báo phù hợp.

Hai điều kiện độc lập. Một biểu thức có kiểu `Throwable` hợp lệ vẫn có thể bị compiler từ chối nếu checked exception chưa được xử lý.

| Kiểu được ném | Nằm trong cây Throwable? | Checked/unchecked | Có cần `catch` hoặc `throws` khi thoát khỏi method? |
| --- | --- | --- | --- |
| `IOException` | Có | Checked | Có |
| `Exception` | Có | Checked | Có |
| `Throwable` | Có | Checked | Có |
| `IllegalArgumentException` | Có | Unchecked (`RuntimeException`) | Không bắt buộc |
| `NullPointerException` | Có | Unchecked (`RuntimeException`) | Không bắt buộc |
| `AssertionError` | Có | Unchecked (`Error`) | Không bắt buộc |
| `String` | Không | Không áp dụng | Không thể `throw` trực tiếp |

**Quy tắc:** các lớp con của `RuntimeException` và `Error` là unchecked. Những lớp con khác của `Throwable` là checked theo hệ thống ngôn ngữ Java. Vì thế không thể đồng nhất `Exception` với toàn bộ checked exception hay `Throwable` với một kiểu unchecked.

### 5.1. Ví dụ sai do chưa xử lý checked exception

Trong một method **không khai báo `throws`** và không có handler phù hợp:

```java
static void fail() {
    throw new java.io.IOException("Không đọc được");
}
```

Đoạn trên không biên dịch vì `IOException` là checked exception. Thông báo compiler thường có dạng “unreported exception IOException; must be caught or declared to be thrown”.

Hai cách xử lý hợp lệ:

**Cách A — khai báo cho caller:**

```java
static void fail() throws java.io.IOException {
    throw new java.io.IOException("Không đọc được");
}
```

**Cách B — bắt tại nơi có thể xử lý:**

```java
static void fail() {
    try {
        throw new java.io.IOException("Không đọc được");
    } catch (java.io.IOException e) {
        System.out.println("Đã xử lý: " + e.getMessage());
    }
}
```

Hai đoạn là ví dụ trong thân lớp, không phải các tệp độc lập. Khi xử lý thực tế, đừng bắt checked exception rồi im lặng nếu không có hướng phục hồi; caller có thể tưởng thao tác đã thành công.

### 5.2. `throws` không phải sự bảo đảm “chỉ có exception này”

`static void process() throws IOException` cho biết method có thể để `IOException` thoát ra. Nó không cấm một `IllegalArgumentException`, `NullPointerException` hoặc `Error` xuất hiện khi chạy. `throws` cũng không bảo đảm method chắc chắn sẽ ném exception.

Tương tự, viết `throw new RuntimeException("...")` không cần `throws RuntimeException`; việc khai báo unchecked exception là tùy chọn và thường dùng Javadoc `@throws` để diễn đạt hợp đồng rõ hơn.

## 6. Chương trình Java 17: ném checked exception rồi xử lý ở caller

Ví dụ dùng `BufferedReader` trên dữ liệu nằm trong RAM để tránh phụ thuộc file và vẫn minh họa API đọc có khả năng ném `IOException`. Khi không có dòng nào, method chủ động ném `EOFException` (một lớp con checked của `IOException`).

Tạo tệp `ThrowCheckedDemo.java`:

```java
import java.io.BufferedReader;
import java.io.EOFException;
import java.io.IOException;
import java.io.StringReader;

public class ThrowCheckedDemo {
    static String requireFirstLine(String content) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(content))) {
            String line = reader.readLine();
            if (line == null) {
                throw new EOFException("Không có dòng dữ liệu");
            }
            return line;
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("Dòng đầu: "
                    + requireFirstLine("Java\nException"));
            System.out.println("Dòng đầu: " + requireFirstLine(""));
        } catch (EOFException e) {
            System.out.println("Hết dữ liệu: " + e.getMessage());
        } catch (IOException e) {
            System.out.println("Lỗi I/O: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ThrowCheckedDemo.java
java ThrowCheckedDemo
```

Stdout chính xác:

```text
Dòng đầu: Java
Hết dữ liệu: Không có dòng dữ liệu
```

Giải thích:

- `readLine()` trả `"Java"` khi có dòng đầu; method `return` bình thường.
- Với chuỗi rỗng, `readLine()` trả `null`; `throw new EOFException(...)` được chạy. `EOFException` là checked exception nên phải được bắt hoặc khai báo khi thoát khỏi method.
- `requireFirstLine` khai báo `throws IOException`, bao gồm `EOFException` vì nó là lớp con của `IOException`.
- `main` có `catch (EOFException e)` trước `catch (IOException e)`. Nếu đảo thứ tự, handler cho `EOFException` không thể tới được và chương trình không biên dịch.
- Khi ném `EOFException`, câu `return line` bị bỏ qua. Try-with-resources đóng `reader` khi rời khối.
- Dữ liệu ở ví dụ là in-memory; trường hợp file thật có thể phát sinh thêm lỗi môi trường ngoài dự kiến.

Chú ý: trong thực tế, EOF là kết quả bình thường của nhiều API đọc, không luôn cần ném exception. Ở đây ta **chủ động xây hợp đồng** “phải có ít nhất một dòng”, nên không có dòng được coi là thất bại cần báo.

## 7. Các trường hợp mở rộng — nhận diện quy tắc cần thiết

Những trường hợp dưới đây giúp người học áp dụng **cú pháp `throw`** mà không lặp lại toàn bộ chương trình minh họa của những bài chuyên sâu riêng về `throw null`, rethrow, unreachable code và switch.

### 7.1. Ném tham chiếu null

```java
throw null; // Biên dịch hợp lệ, runtime ném NullPointerException.
```

Giá trị null không phải đối tượng `Throwable`. Nếu biểu thức được đánh giá thành null, JVM ném một `NullPointerException`. Biến có kiểu `RuntimeException` vẫn có thể chứa null; code nghiệp vụ nên tạo exception có message rõ thay vì cố ý dùng `throw null`.

### 7.2. Ném lại hoặc bọc lỗi

```java
try {
    loadSettings();
} catch (java.io.IOException e) {
    throw new IllegalStateException("Không tải được cấu hình", e);
}
```

Đây là snippet minh họa, `loadSettings` được định nghĩa trong ứng dụng. `throw e;` ném lại **cùng đối tượng** đã bắt; `throw new ...(..., e)` tạo exception mới với `e` làm cause. Ném lại checked exception tuân thủ `catch-or-declare`, với quy tắc `precise rethrow` trong một số `catch` effectively final.

### 7.3. Sau `throw` và trong `switch`

```java
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
System.out.println("valid");
```

Đây là đoạn minh họa với `quantity` đã khai báo. `throw` không hoàn tất bình thường: lệnh ngay sau một `throw` vô điều kiện **trong cùng khối** là unreachable, nhưng đường ngoài nhánh `if` vẫn có thể chạy. Trong Java 17, `switch expression` cũng cho phép một nhánh `default -> throw new IllegalArgumentException(...)` bên cạnh các nhánh cung cấp giá trị hoặc `yield`; `throw` vẫn là statement, không phải một expression trả giá trị.

### 7.4. Bối cảnh rộng hơn

`throw` có thể nằm trong constructor, thân khối lambda, vòng lặp hoặc khai báo một lỗi tùy biến theo cú pháp phù hợp; ngoại lệ được ném vẫn phải thuộc nhánh `Throwable`, và checked exception còn chịu giới hạn chữ ký method/functional interface. Thường định nghĩa exception nghiệp vụ bằng cách kế thừa `Exception` hoặc `RuntimeException`, không lạm dụng `Error`. `finally`/`try-with-resources` thực hiện cleanup theo contract nhưng **không tự rollback** dữ liệu đã thay đổi.

Phần này là bản đồ cú pháp. Các bài riêng trong chương phân tích identity, stack trace, null semantics, reachability theo JLS và `yield` trong `switch` qua ví dụ chuyên sâu, tránh lặp các walkthrough đó tại đây.

## 8. Lỗi thường gặp khi dùng `throw`

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `throw "Lỗi";` | `String` không phải `Throwable`. | `throw new IllegalArgumentException("Lỗi");` hoặc loại phù hợp. |
| `throw new Object();` | `Object` không tương thích `Throwable`. | Dùng exception thuộc hệ `Throwable`. |
| `throw new IOException(...);` nhưng không xử lý checked | Compiler yêu cầu bắt hoặc khai báo. | Thêm `throws IOException` hoặc `catch` đúng tầng. |
| Tưởng `throws IOException` tự phát sinh lỗi | `throws` chỉ khai báo, không thực thi. | Dùng `throw` khi điều kiện thất bại xảy ra. |
| Tạo `new Exception(...)` nhưng không `throw` | Chỉ tạo object. | Viết `throw new Exception(...)` và xử lý checked. |
| `throw null;` để báo thiếu dữ liệu | Runtime ném `NullPointerException` thay thế, khó hiểu. | Chủ động tạo exception rõ nghĩa. |
| `Throwable x = new RuntimeException(...); throw x;` rồi bất ngờ phải khai báo | Kiểu tĩnh `Throwable` được kiểm tra như checked. | Dùng kiểu hẹp hợp lý; hiểu precise rethrow khi bắt. |
| Bắt lỗi rồi `throw new RuntimeException(e.getMessage())` | Mất cause/chuỗi lỗi. | Dùng constructor nhận `cause` khi bọc lỗi. |
| Đặt code sau `throw` vô điều kiện | Code không thể tới được. | Dùng `if`, sắp xếp control flow rõ ràng. |
| Tưởng `throw` sẽ rollback | Java không tự hoàn tác mọi side effect. | Xây hợp đồng trạng thái, validate trước hoặc transaction thích hợp. |
| `catch (Exception)` để bắt `Error` tự ném | `Error` không kế thừa `Exception`. | Hiểu cây `Throwable`; không tùy tiện bắt rộng. |
| Sử dụng exception để điều khiển mọi nhánh bình thường | Code khó đọc và khó phân biệt lỗi thực. | Dùng điều kiện/kết quả thông thường cho tình huống có thể biểu diễn đơn giản. |

### 8.1. Lỗi về tên tệp, import và output

- `public class ThrowBasicDemo` phải nằm trong `ThrowBasicDemo.java`. Tên tệp Java phân biệt chữ hoa/chữ thường trên các hệ thống tương ứng.
- `java.lang.RuntimeException`, `IllegalArgumentException`, `Throwable` được import tự động từ `java.lang`; `IOException` và `EOFException` thuộc `java.io` nên ví dụ có `import`.
- Stack trace của một exception không được bắt thường được in ra **stderr**, có line number phụ thuộc phiên bản tệp. Các stdout được ghi trong bài đều xuất phát từ chương trình đã chủ động bắt lỗi và in thông tin ổn định.
- Mã được đánh dấu “minh họa” có thể dựa vào biến, phương thức hoặc lớp bao quanh chưa được cung cấp. Chỉ những chương trình có tên tệp, `public class` và `main` ở các Mục 3 và 6 là các ví dụ biên dịch/chạy độc lập.

## 9. Bài tập có đáp án định hướng

### Bài 1 — Chọn câu lệnh `throw` hợp lệ

Đánh giá:

```java
throw new RuntimeException("A");
throw new java.io.IOException("B");
throw new Throwable("C");
throw null;
throw "D";
```

Các dòng được hiểu **độc lập**, không viết nối nhau trong cùng một block như chương trình hoàn chỉnh.

- `new RuntimeException`: kiểu hợp lệ, unchecked, không cần `throws`.
- `new IOException`: kiểu hợp lệ nhưng checked; cần bắt/khai báo nếu thoát ra.
- `new Throwable`: kiểu hợp lệ nhưng checked; cần bắt/khai báo nếu thoát ra.
- `throw null`: cú pháp hợp lệ; khi chạy ném `NullPointerException`.
- `throw "D"`: không hợp lệ vì kiểu `String` không tương thích với `Throwable`.

### Bài 2 — Dự đoán đầu ra

Với `ThrowBasicDemo`, thêm `7` vào cuối mảng. Kết quả sẽ thêm dòng `OK: 7` sau các dòng đã có. Nếu thay `catch (IllegalArgumentException)` bằng `catch (Exception)`, các lỗi được ném trong ví dụ vẫn bị bắt, nhưng kiểu handler rộng hơn và dễ che các loại lỗi không mong muốn.

### Bài 3 — Biến kiểu rộng

Cho:

```java
Object value = new IllegalStateException("Sai");
```

Tại sao `throw value;` không biên dịch? Bởi kiểu tĩnh của `value` là `Object`, không thỏa ràng buộc kiểu của `throw`. Nếu sử dụng pattern matching `instanceof Throwable error` rồi `throw error`, tại sao còn nghĩa vụ checked? Vì biến `error` có kiểu tĩnh `Throwable`.

### Bài 4 — Khác biệt giữa `throw e` và bọc cause

Trong `ThrowCauseDemo`, thử thay:

```java
throw new ConfigurationException("Cổng không hợp lệ", e);
```

bằng `throw e;`. Method `loadPort` vẫn có thể biên dịch vì `NumberFormatException` là unchecked, nhưng hợp đồng/thông tin mà `main` chờ sẽ thay đổi: handler `catch (ConfigurationException)` không còn bắt được exception gốc. Thiết kế loại wrapper cần nhất quán với hợp đồng của caller.

### Bài 5 — Kiểm thử đường lỗi

Viết một method `parseAge(String input)`:

1. Nếu chuỗi không phải số nguyên, cho `NumberFormatException` lan lên.
2. Nếu parse được nhưng giá trị ngoài khoảng hợp lệ do bạn xác định, `throw new IllegalArgumentException(...)`.
3. Nếu hợp lệ, trả về `int`.
4. Từ `main`, thử các chuỗi hợp lệ, chữ, âm và vượt phạm vi `int`.
5. Kiểm tra rằng phương thức không sửa trạng thái dùng chung trước khi ném exception, và ghi rõ hợp đồng của từng kiểu lỗi.

## 10. Checklist trước khi sử dụng `throw` trong API

- [ ] Biểu thức sau `throw` có kiểu tĩnh phù hợp với `Throwable` không?
- [ ] Có hiểu rằng giá trị `null` ở đây sinh `NullPointerException` khi chạy không?
- [ ] Đã phân biệt `throw` thực thi với `throws` khai báo chưa?
- [ ] Đã xác định ngoại lệ là checked hay unchecked và nghĩa vụ của caller chưa?
- [ ] Đã chọn exception diễn đạt đúng ngữ nghĩa, thay vì lạm dụng `Error` chưa?
- [ ] Nếu ném lại exception, có giữ nguyên thông tin lỗi cần thiết không?
- [ ] Nếu bọc exception, có truyền nguyên nhân gốc qua `cause` không?
- [ ] Code phía sau `throw` có đường chạy hợp lệ hay đã vô tình thành unreachable?
- [ ] Các tài nguyên cần đóng và trạng thái đã thay đổi trước `throw` có được xử lý đúng hợp đồng không?
- [ ] Có test cả đường thành công và đường ném lỗi, bao gồm loại exception và trạng thái sau lỗi không?
- [ ] Đã xác định vị trí `catch` có thể xử lý phù hợp chưa?

**Ghi nhớ:** `throw expression;` ném một giá trị phù hợp với `Throwable` và kết thúc bất thường đường chạy hiện tại. Chữ ký `throws` và cơ chế checked exception quyết định nghĩa vụ compile-time; phân cấp runtime quyết định handler `catch`; còn dữ liệu đã thay đổi và tài nguyên cần dọn phải được thiết kế riêng — chúng không tự hoàn tác chỉ vì có `throw`.