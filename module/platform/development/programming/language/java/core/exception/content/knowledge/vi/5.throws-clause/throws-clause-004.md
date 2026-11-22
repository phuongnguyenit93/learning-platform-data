# Phân biệt `throw` với `throws` trong Java

> **Chủ đề:** Java Core → Exception → Mệnh đề `throws`. Hai từ khóa có tên gần giống nhưng đảm nhiệm **hai công việc khác nhau**: `throw` là **câu lệnh thực sự ném một đối tượng ngoại lệ**; `throws` là **mệnh đề trong khai báo phương thức/constructor** cho biết những loại ngoại lệ có thể thoát ra, đặc biệt để đáp ứng quy tắc **checked exception** của compiler. Nắm được khác biệt này giúp đọc đúng API Java, hiểu cách exception lan truyền và thiết kế hợp đồng xử lý lỗi rõ ràng.

## 1. Nhìn ngay sự khác nhau qua cú pháp

```java
// Câu lệnh thực thi trong thân phương thức:
throw new IllegalArgumentException("Giá trị không hợp lệ");

// Mệnh đề trong chữ ký phương thức:
static void read() throws java.io.IOException {
    // Thân phương thức.
}
```

Hai đoạn trên chỉ minh họa cú pháp, chưa phải một chương trình độc lập. Điểm phân biệt:

- **`throw expression;`** đánh giá một biểu thức có kiểu phù hợp với `Throwable` và ném đối tượng đó tại vị trí đang thực thi. Nó làm luồng chạy kết thúc bất thường, trừ khi ngoại lệ được bắt ở phạm vi phù hợp.
- **`throws ExceptionType1, ExceptionType2`** xuất hiện sau danh sách tham số và trước thân phương thức (hoặc dấu `;` đối với khai báo không có thân). Đây là phần **khai báo**, bản thân nó không tạo hay ném đối tượng nào.

Đặc biệt: một method có thể có `throws` nhưng **không bao giờ thực hiện lệnh `throw` trực tiếp**; exception có thể đến từ phương thức con. Ngược lại, một method có thể dùng `throw` với unchecked exception mà **không cần `throws`**.

### 1.1. Bảng so sánh cốt lõi

| Tiêu chí | `throw` | `throws` |
| --- | --- | --- |
| Bản chất | Statement điều khiển luồng | Thành phần chữ ký khai báo |
| Nơi đặt | Trong thân method, constructor, lambda block hoặc ngữ cảnh cho phép statement | Sau danh sách tham số của method/constructor và trước thân hoặc dấu `;` |
| Cú pháp | `throw new IOException("Lỗi");` | `void load() throws IOException, SQLException` |
| Đi theo sau | **Một biểu thức** có kiểu tương thích `Throwable` | **Danh sách một hoặc nhiều kiểu** ngoại lệ là lớp con của `Throwable` |
| Có ném thật không? | Có, khi dòng lệnh được thực thi | Không |
| Ảnh hưởng đến chương trình | Đưa luồng đi theo đường exception; câu lệnh bình thường phía sau điểm ném không chạy | Góp phần xác định nghĩa vụ compile-time của caller với checked exceptions |
| Có phải luôn viết cùng nhau? | Không | Không |
| Checked/unchecked | Có thể ném cả hai | Checked exceptions phải được bắt hoặc khai báo nếu có thể thoát; unchecked không bắt buộc kê khai |

**Cách nhớ:** `throw` trả lời “**ném cái gì, ngay lúc nào?**”; `throws` trả lời “**method có thể để những loại lỗi nào thoát ra cho caller xử lý?**”.

## 2. `throw` hoạt động như thế nào?

Cú pháp tổng quát:

```java
throw expression;
```

`expression` phải có kiểu có thể chuyển thành `java.lang.Throwable` theo quy tắc ngôn ngữ. Ví dụ:

```java
throw new IllegalArgumentException("Số lượng âm");
```

Điều xảy ra:

1. Tạo một đối tượng `IllegalArgumentException`.
2. Đánh giá biểu thức `new ...` được viết sau `throw`.
3. Ném đối tượng đó; đường đi bình thường từ câu lệnh này dừng.
4. Java tìm `catch` tương thích trong các khối `try` đang hoạt động; nếu không có, lỗi lan ra ngoài theo chuỗi gọi.

Không nên nhầm việc **khởi tạo** với việc **ném**:

```java
new IllegalArgumentException("Lỗi");       // Chỉ tạo đối tượng.
throw new IllegalArgumentException("Lỗi"); // Tạo rồi thực sự ném.
```

Đây là các dòng minh họa riêng biệt. Dòng đầu không khiến chương trình đi vào `catch`; nếu không còn tham chiếu, đối tượng có thể được thu gom như những đối tượng khác. Dòng thứ hai thay đổi luồng điều khiển.

### 2.1. Kiểu nào được phép sau `throw`?

```text
java.lang.Throwable
├── java.lang.Exception
│   ├── java.io.IOException
│   └── java.lang.RuntimeException
│       ├── IllegalArgumentException
│       ├── IllegalStateException
│       └── NumberFormatException
└── java.lang.Error
    ├── AssertionError
    └── LinkageError
```

`Throwable` là gốc của hệ ngoại lệ; `Exception` và `Error` đều là lớp con. Lệnh `throw` có thể ném đối tượng ở các nhánh này về mặt ngôn ngữ, nhưng ứng dụng thông thường **không nên sử dụng `Error` như ngoại lệ nghiệp vụ**.

Các biểu thức sau là sai kiểu:

```java
// CÁC VÍ DỤ CỐ Ý KHÔNG BIÊN DỊCH:
throw 42;              // int không phải Throwable.
throw "Có lỗi";        // String không phải Throwable.
throw new Object();    // Object không phải Throwable.
```

Ví dụ đúng:

```java
throw new IllegalArgumentException("Số không hợp lệ");
```

`throw null;` là trường hợp đặc biệt: Java cho phép cú pháp, nhưng nếu đánh giá biểu thức sau `throw` ra `null`, runtime ném `NullPointerException` thay thế. Đây không phải kỹ thuật báo lỗi tốt; nên tạo exception diễn đạt rõ nguyên nhân.

### 2.2. Biến kiểu tĩnh và kiểu đối tượng thực tế

Giả sử:

```java
Object error = new IllegalStateException("Trạng thái sai");
// throw error; // Không hợp lệ vì kiểu tĩnh Object không phải Throwable.
```

Dù đối tượng bên trong là `IllegalStateException`, kiểu của **biểu thức** `error` là `Object` nên compiler không cho `throw error`.

Nếu có một biến khai báo `Throwable error`, `throw error` đúng yêu cầu **kiểu của lệnh throw**, nhưng có thể cần `throws Throwable` hoặc `catch` vì compiler xử lý nó như checked ở kiểu rộng `Throwable`. Phân biệt kiểm tra kiểu và quy tắc checked exception là điểm quan trọng trong các phần tiếp theo.

### 2.3. `throw` không đồng nghĩa với `return`

`return` hoàn tất bình thường và có thể trả giá trị. `throw` kết thúc bất thường, không trả về một giá trị cùng loại với kiểu trả về của method. Ví dụ:

```java
static int divide(int a, int b) {
    if (b == 0) {
        throw new ArithmeticException("Không thể chia cho 0");
    }
    return a / b;
}
```

Đây là phương thức minh họa, cần đặt trong một lớp. Nhánh `b == 0` không thực hiện `return a / b`. Trong Java, đặt một câu lệnh thực thi ngay sau `throw` **vô điều kiện** trong cùng khối sẽ gây lỗi “unreachable statement”.

## 3. `throws` hoạt động như thế nào?

Cú pháp khái quát:

```java
ReturnType methodName(Parameters...) throws ExceptionType1, ExceptionType2 {
    // Nội dung.
}
```

Mệnh đề `throws` được viết trong **khai báo** method hoặc constructor; các tên theo sau là **kiểu Throwable**, không phải đối tượng `new Exception(...)`. Không thể viết `throws new IOException("...")`.

Ví dụ một phương thức đọc:

```java
static String readFirstLine(java.io.BufferedReader reader)
        throws java.io.IOException {
    return reader.readLine();
}
```

Method này **không có câu lệnh `throw`**. Nhưng `reader.readLine()` có thể ném `IOException`, và method cho phép ngoại lệ đó lan ra caller, vì vậy khai báo `throws IOException` là hợp lý. Nếu caller không xử lý hoặc khai báo tiếp checked exception này, compiler sẽ báo lỗi.

### 3.1. `throws` là phần hợp đồng, không phải một lệnh chạy

Nhìn:

```java
static void maybeFail(boolean failed) throws java.io.IOException {
    if (failed) {
        throw new java.io.IOException("Không thể đọc");
    }
}
```

Ở mỗi lời gọi, `throws IOException` vẫn nằm trong chữ ký. Nhưng chỉ khi `failed == true` thì lệnh `throw` mới được thực hiện. Khi `failed == false`, method kết thúc bình thường. **Không có ngoại lệ nào tự phát sinh chỉ vì chữ ký có `throws`.**

### 3.2. `throws` có thể có nhiều kiểu

```java
static void process() throws java.io.IOException,
        java.text.ParseException {
    // Hoạt động có thể ném IOException hoặc ParseException.
}
```

Các kiểu được phân cách bằng dấu phẩy. Điều đó không có nghĩa cả hai ngoại lệ sẽ cùng được ném tại mỗi lần gọi. Một lần kết thúc bất thường thường có một đối tượng Throwable đang lan truyền (nó có thể mang cause hoặc suppressed exceptions khác).

Cũng không cần khai báo `throws` trùng lặp khi kiểu cha đã bao phủ các kiểu con được ném. Ví dụ `throws IOException` đủ cho `FileNotFoundException extends IOException`. Tuy nhiên, khai báo quá rộng như `throws Exception` hay `throws Throwable` thường khiến caller khó biết cách xử lý cụ thể, nên hãy ưu tiên kiểu diễn đạt đúng hợp đồng.

### 3.3. `throws` dùng được trong constructor và khai báo interface

```java
interface DocumentReader {
    String read() throws java.io.IOException;
}

final class ReaderSetup {
    ReaderSetup(String path) throws java.io.IOException {
        if (path == null) {
            throw new java.io.IOException("Thiếu đường dẫn");
        }
    }
}
```

Đây là các khai báo loại, không có `main`. Mệnh đề `throws` phù hợp ở method trong interface và constructor. Ngược lại, `throw` xuất hiện **trong thân** constructor khi thật sự gặp tình huống sai.

## 4. Quan hệ với checked và unchecked exceptions

**Checked exception:** các lớp con của `Throwable` không thuộc nhánh `RuntimeException` hoặc `Error`, ví dụ `IOException` và `ParseException`. Nếu checked exception có thể thoát khỏi một method, method phải bắt hoặc khai báo bằng `throws` đủ bao phủ.

**Unchecked exception:** `RuntimeException`, `Error` và các lớp con. Compiler không yêu cầu bắt hoặc kê khai bằng `throws`, dù có thể ném chúng bằng `throw` và nên tài liệu hóa các trường hợp dự kiến.

| Lệnh ném | Loại | Khi thoát khỏi method có cần `throws`/`catch` không? |
| --- | --- | --- |
| `throw new IOException("Lỗi I/O");` | Checked | Có |
| `throw new ParseException("Sai định dạng", 0);` | Checked | Có |
| `throw new Exception("Lỗi");` | Checked | Có |
| `throw new IllegalArgumentException("Sai");` | Unchecked (`RuntimeException`) | Không bắt buộc |
| `throw new AssertionError("Sai giả định");` | Unchecked (`Error`) | Không bắt buộc, nhưng không nên dùng cho lỗi nghiệp vụ |
| `throw new Throwable("Lỗi");` | Checked | Có, thường phải `throws Throwable` hoặc handler phù hợp |

Lưu ý: **`Exception` không đồng nghĩa với checked exception**: `RuntimeException` là lớp con của `Exception` nhưng thuộc loại unchecked. Cũng không phải mọi `Throwable` thuộc nhánh `Exception`: `Error` là nhánh khác.

### 4.1. Checked exception: hai cách biên dịch hợp lệ

Giả sử cần phát ra `IOException` khi thiếu dữ liệu.

**Cách 1 — để caller chịu trách nhiệm bằng `throws`:**

```java
static void readOrFail(String data) throws java.io.IOException {
    if (data == null) {
        throw new java.io.IOException("Thiếu dữ liệu");
    }
}
```

**Cách 2 — xử lý trong chính method bằng `try/catch`:**

```java
static void readOrReport(String data) {
    try {
        if (data == null) {
            throw new java.io.IOException("Thiếu dữ liệu");
        }
    } catch (java.io.IOException e) {
        System.out.println("Đã nhận lỗi: " + e.getMessage());
    }
}
```

Hai ví dụ là **phương thức**, không phải file chương trình độc lập. Hai cách đều biên dịch khi đặt trong một lớp, nhưng **khác nhau về hợp đồng**: cách 1 đẩy khả năng xử lý lỗi lên caller; cách 2 tự báo lỗi ở đây và kết thúc bình thường sau `catch`. Nếu chỉ in log rồi bỏ qua lỗi làm caller hiểu lầm thao tác thành công, cách 2 không phù hợp.

### 4.2. Unchecked exception: `throw` không cần `throws`

```java
static int requirePositive(int n) {
    if (n <= 0) {
        throw new IllegalArgumentException("Phải lớn hơn 0");
    }
    return n;
}
```

Đây là unchecked exception. Viết thêm `throws IllegalArgumentException` là hợp lệ nhưng không bắt buộc; nó cũng **không ép caller** phải bắt hoặc khai báo. JavaDoc `@throws` thường thích hợp để mô tả các tiền điều kiện sai mà API dự kiến báo ra.

### 4.3. Khai báo `throws` không giới hạn mọi lỗi runtime

Method khai báo `throws IOException` vẫn có thể gặp `NullPointerException`, `IllegalArgumentException` hoặc `Error`. Khai báo này nói về những checked exception mà compiler/caller cần xét theo hợp đồng; nó **không hứa rằng method chỉ có thể ném IOException** hoặc đã kiểm tra toàn bộ lỗi.

## 5. Ví dụ Java 17 đầy đủ: `throw` và `throws` phối hợp

Lưu thành `ThrowVsThrowsDemo.java`:

```java
import java.io.IOException;

public class ThrowVsThrowsDemo {
    static int parsePositive(String text) {
        int number = Integer.parseInt(text);
        if (number <= 0) {
            throw new IllegalArgumentException("Số phải dương");
        }
        return number;
    }

    static int readCount(String text) throws IOException {
        if (text == null) {
            throw new IOException("Nguồn dữ liệu trống");
        }
        return parsePositive(text);
    }

    static void show(String input) {
        try {
            System.out.println("Số lượng: " + readCount(input));
        } catch (IOException e) {
            System.out.println("Lỗi nguồn: " + e.getMessage());
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi đầu vào: "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        show("7");
        show("0");
        show("abc");
        show(null);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 ThrowVsThrowsDemo.java
java ThrowVsThrowsDemo
```

Stdout:

```text
Số lượng: 7
Lỗi đầu vào: IllegalArgumentException
Lỗi đầu vào: NumberFormatException
Lỗi nguồn: Nguồn dữ liệu trống
```

**Tại sao đúng?**

- `parsePositive("7")` trả `7`, `readCount` cũng trả về bình thường.
- `parsePositive("0")` thực thi `throw new IllegalArgumentException(...)`. Nó không có `throws` vì đây là unchecked exception; `show` bắt bằng `catch (IllegalArgumentException)`.
- `Integer.parseInt("abc")` ném `NumberFormatException`. Loại này kế thừa `IllegalArgumentException` nên vẫn bị `catch (IllegalArgumentException)` bắt.
- `readCount(null)` **trực tiếp ném** `new IOException(...)` qua `throw`. Vì `IOException` checked, `readCount` khai báo `throws IOException`; `show` nhận trách nhiệm bắt.
- Các exception không xuất hiện cùng lúc trong một lời gọi. Mỗi lần `show` có thể thành công hoặc rẽ sang một nhánh xử lý lỗi.

**Bài học về trách nhiệm:** method cấp thấp có thể **ném**, method trung gian có thể **khai báo cho lan truyền**, và tầng gần người dùng có thể **bắt để hiển thị kết quả phù hợp**. `throw`, `throws`, `catch` không cạnh tranh nhau: chúng đảm nhiệm các khâu khác nhau trong cùng đường đi của ngoại lệ.

## 6. Exception propagation: có `throws` nhưng không có `throw` tại tầng giữa

Một trong các công dụng phổ biến nhất của `throws` là **truyền tiếp** checked exception từ method bên dưới, thay vì bắt nó ở một tầng chưa có đủ ngữ cảnh để xử lý.

Tạo `ThrowsPropagationDemo.java`:

```java
import java.io.IOException;

public class ThrowsPropagationDemo {
    static void readSource() throws IOException {
        throw new IOException("Không đọc được nguồn");
    }

    static void prepareReport() throws IOException {
        readSource();
    }

    static void run() {
        try {
            prepareReport();
            System.out.println("Báo cáo đã sẵn sàng");
        } catch (IOException e) {
            System.out.println("Báo cáo thất bại: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        run();
        System.out.println("Đã xử lý xong yêu cầu");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ThrowsPropagationDemo.java
java ThrowsPropagationDemo
```

Stdout:

```text
Báo cáo thất bại: Không đọc được nguồn
Đã xử lý xong yêu cầu
```

Luồng xử lý:

```text
main()
  └── run()
        └── prepareReport() throws IOException
              └── readSource() throws IOException
                    └── throw new IOException(...)
        ◀──── IOException lan ngược qua prepareReport()
  └── catch (IOException) trong run()
```

`readSource` có cả `throw` và `throws`. `prepareReport` chỉ có `throws`, không có `throw` trực tiếp; ngoại lệ phát ra từ `readSource()` lan tiếp qua nó. `run` bắt tại ranh giới có thể báo một kết quả thất bại có ý nghĩa. Dòng “Báo cáo đã sẵn sàng” bị bỏ qua, vì lời gọi `prepareReport()` không trở về bình thường.

**Không phải có `throws` là ngoại lệ sẽ được tự động ném thêm lần nữa.** Runtime truyền cùng ngoại lệ chưa được xử lý qua chuỗi gọi; không tạo một đối tượng mới chỉ vì đi qua chữ ký `throws`.

## 7. `throw e` và `throw new ...`: ném lại, chuyển loại, giữ nguyên nguyên nhân

Sau khi bắt một ngoại lệ, code có thể:

- xử lý và hoàn tất bình thường;
- ném lại chính đối tượng bằng `throw e;`;
- tạo một đối tượng ngoại lệ mới rồi ném bằng `throw new ...`, thường cần giữ `cause`.

Ví dụ mô tả một đoạn method:

```java
try {
    loadData();
} catch (java.io.IOException e) {
    recordFailure(e);
    throw e;
}
```

Mã này phụ thuộc vào `loadData`/`recordFailure` đã được định nghĩa và method chứa nó phải khai báo hoặc bắt checked exception phù hợp. `throw e;` không tạo exception mới. Tùy ngữ cảnh, compiler có thể áp dụng **precise rethrow** cho biến `catch` không gán lại, giúp suy luận những checked exception cụ thể có thể được ném từ khối `try`.

Nếu muốn bổ sung ý nghĩa:

```java
try {
    loadData();
} catch (java.io.IOException e) {
    throw new IllegalStateException("Không nạp được dữ liệu", e);
}
```

Ở đây `IllegalStateException` là unchecked, nguyên nhân `IOException` được giữ qua `getCause()`. **Không nên viết `throw new RuntimeException(e.getMessage())` chỉ để bỏ nghĩa vụ `throws`**, vì cách đó đánh mất đối tượng nguyên nhân và không tự phục hồi chương trình.

### 7.1. Ví dụ chạy độc lập để nhìn thấy wrapper và cause

Tạo `WrapCauseDemo.java`:

```java
import java.io.IOException;

public class WrapCauseDemo {
    static void lowLevel() throws IOException {
        throw new IOException("Lỗi kết nối");
    }

    static void service() {
        try {
            lowLevel();
        } catch (IOException e) {
            throw new IllegalStateException("Tác vụ không thể hoàn tất", e);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalStateException e) {
            System.out.println("Loại: "
                    + e.getClass().getSimpleName());
            System.out.println("Thông điệp: " + e.getMessage());
            System.out.println("Nguyên nhân: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 WrapCauseDemo.java
java WrapCauseDemo
```

Stdout:

```text
Loại: IllegalStateException
Thông điệp: Tác vụ không thể hoàn tất
Nguyên nhân: IOException
```

`service` có `throw new IllegalStateException(...)` nhưng không cần `throws` vì exception mới là unchecked. `lowLevel` có `throw new IOException(...)` và `throws IOException` vì checked. Wrapper không xóa nghĩa vụ **về hành vi**: caller vẫn cần hiểu thất bại và trạng thái sau thất bại; chuyển sang unchecked chỉ thay ràng buộc của compiler.

## 8. `throws` và quy tắc ghi đè phương thức (override)

Mệnh đề `throws` là một phần quan trọng của hợp đồng checked exception trong cơ chế đa hình Java.

Khi một method ở lớp con override method của lớp cha/interface:

- Method override **không được khai báo checked exception mới hoặc rộng hơn** so với những gì phương thức bị override cho phép.
- Method override có thể khai báo checked exception **cụ thể hơn** hoặc ít hơn, kể cả không khai báo checked exception nào.
- Unchecked exceptions không chịu ràng buộc này.
- Quy tắc áp dụng cho **override**, không phải mọi method cùng tên (overload có chữ ký tham số khác là câu chuyện khác).

### 8.1. Ví dụ Java 17 biên dịch được

Tạo `ThrowsOverrideDemo.java`:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class ThrowsOverrideDemo {
    interface Source {
        String get() throws IOException;
    }

    static final class MemorySource implements Source {
        @Override
        public String get() {
            return "Bộ nhớ";
        }
    }

    static final class MissingSource implements Source {
        @Override
        public String get() throws FileNotFoundException {
            throw new FileNotFoundException("Không thấy tài liệu");
        }
    }

    public static void main(String[] args) {
        Source[] sources = {
                new MemorySource(),
                new MissingSource()
        };

        for (Source source : sources) {
            try {
                System.out.println("Dữ liệu: " + source.get());
            } catch (IOException e) {
                System.out.println("Lỗi: " + e.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ThrowsOverrideDemo.java
java ThrowsOverrideDemo
```

Stdout:

```text
Dữ liệu: Bộ nhớ
Lỗi: Không thấy tài liệu
```

`Source.get() throws IOException` định nghĩa hợp đồng chung. `MemorySource.get()` bỏ hẳn `throws` vì không phát sinh checked exception. `MissingSource.get() throws FileNotFoundException` hợp lệ vì `FileNotFoundException` là lớp con của `IOException`.

Dù đối tượng runtime có thể là `MemorySource`, biến của vòng lặp có kiểu tĩnh `Source`, nên lời gọi `source.get()` vẫn được compiler xét theo hợp đồng `throws IOException` của interface. Đây là một ví dụ cho thấy **kiểu tham chiếu dùng tại nơi gọi** cũng ảnh hưởng nghĩa vụ xử lý.

### 8.2. Ví dụ override sai

Các dòng sau là **minh họa lỗi biên dịch**, không đặt vào tệp ví dụ chạy:

```java
interface Api {
    void execute() throws java.io.IOException;
}

class BadImplementation implements Api {
    @Override
    public void execute() throws java.sql.SQLException {
        // Không hợp lệ: SQLException không là lớp con của IOException.
    }
}
```

Một caller chỉ biết `Api` không được yêu cầu bất ngờ xử lý checked exception hoàn toàn khác do implementation mở rộng hợp đồng. Java ngăn tình huống này ở compile-time.

Đừng đồng nhất quy tắc override với việc method **không thể** ném một unchecked exception trong lúc chạy. Một override vẫn có thể `throw new IllegalStateException(...)` dù chữ ký interface không khai báo loại đó.

## 9. `throws` với lambda và functional interface

Một điểm dễ gặp khi dùng Java hiện đại: lambda phải tuân theo chữ ký của **functional interface**. Không thể thêm checked exception vào lambda chỉ vì ta muốn viết `throw`.

Ví dụ mảnh code minh họa:

```java
Runnable task = () -> {
    // throw new java.io.IOException("I/O"); // Không hợp lệ ở đây.
    throw new IllegalStateException("Tác vụ không hợp lệ");
};
```

`Runnable.run()` không khai báo `throws IOException`; do đó lambda không thể để checked `IOException` thoát khỏi phần thân mà không tự xử lý. Nhưng unchecked `IllegalStateException` thì được.

Một callback có interface của riêng mình có thể khai báo checked exception:

```java
@FunctionalInterface
interface CheckedJob {
    void run() throws java.io.IOException;
}
```

Khi một lambda được gán cho `CheckedJob`, nó được phép ném `IOException` theo đúng hợp đồng của phương thức trừu tượng. Đây là ví dụ dùng chữ ký `throws` để truyền nghĩa vụ xử lý qua interface, không phải đặc quyền riêng của lambda.

Trong mã Java 17+, đừng đổi sang `throws Exception` cho mọi callback chỉ để “cho qua compiler”; hãy chọn loại exception phù hợp với người sử dụng API.

## 10. `throws` và try-with-resources: lỗi có thể đến từ `close()`

Mệnh đề `throws` không chỉ liên quan đến câu lệnh `throw` bạn tự viết. Nhiều API khai báo checked exceptions do thao tác I/O hoặc dọn dẹp tài nguyên. Với `AutoCloseable`, `close()` có thể khai báo checked exception, và try-with-resources có thể làm exception đó thoát ra khi rời khối.

Ví dụ method minh họa:

```java
static void openAndClose() throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.StringReader("abc"))) {
        System.out.println(reader.readLine());
    }
}
```

Method **không có câu lệnh `throw`**. Nhưng `BufferedReader.readLine()` và `BufferedReader.close()` có khai báo `IOException`, nên chữ ký `throws IOException` là phù hợp. Với dữ liệu `StringReader` cụ thể, ví dụ thường chạy thành công, nhưng hợp đồng kiểu không suy luận riêng theo giá trị đầu vào.

Nếu thân khối và `close()` cùng ném exception, try-with-resources giữ lỗi từ thân khối làm ngoại lệ chính và ghi lỗi đóng trong `getSuppressed()` theo quy tắc tương ứng. Đừng nhầm “đã có `throws`” với “đã tự động đóng tài nguyên”, hoặc “đã đóng” với “đã hoàn tác các thay đổi trước lỗi”.

## 11. Những hiểu nhầm thường gặp

| Nhầm lẫn | Sự thật cần nhớ |
| --- | --- |
| “`throw` và `throws` là hai cách viết cùng một chức năng.” | `throw` thực thi thao tác ném; `throws` khai báo khả năng lỗi thoát khỏi method/constructor. |
| “Chỉ cần thêm `throws` thì exception tự phát sinh.” | Không; phải có exception thực sự do lệnh `throw` hoặc thao tác/lời gọi khác tạo ra. |
| “Có lệnh `throw` thì bắt buộc thêm `throws`.” | Chỉ checked exception có thể thoát ra mới buộc bắt hoặc khai báo. Unchecked không cần. |
| “Method có `throws` chắc chắn có dòng `throw`.” | Exception có thể đến từ method con, constructor, resource close, thư viện hoặc JVM. |
| “`throws` dùng với đối tượng `new IOException(...)`.” | `throws` nhận **tên kiểu**, còn `throw` nhận **biểu thức** có kiểu Throwable. |
| “`throws IOException` có nghĩa chỉ IOException được ném.” | Unchecked exceptions và Errors vẫn có thể xảy ra; chữ ký không bảo đảm độc quyền. |
| “`throws Exception` luôn tiện hơn khai báo cụ thể.” | Nó tăng gánh nặng cho caller và che thông tin về loại lỗi có thể xử lý. |
| “`RuntimeException` là unchecked nên không thể `catch`.” | Unchecked nghĩa là không bắt buộc xử lý ở compile-time; vẫn có thể bắt theo kiểu tương thích. |
| “`throw null` sẽ ném một đối tượng null.” | Khi chạy Java tạo/ném `NullPointerException` thay thế. |
| “`throw new Exception("x")` trong method không `throws` luôn được.” | `Exception` là checked; phải bắt hoặc khai báo nếu thoát ra. |
| “Ghi đè method có thể thêm bất kỳ checked `throws` nào.” | Override không được mở rộng checked exception trái với hợp đồng của method cha/interface. |
| “Thêm `throws` giúp tự rollback.” | Java không tự hoàn tác side effect do có exception. |
| “Đổi checked exception thành RuntimeException là đã sửa lỗi.” | Chỉ thay ràng buộc compiler; lỗi gốc, cause, trạng thái và chính sách xử lý vẫn phải quan tâm. |
| “`throw e` tạo exception mới.” | `throw e` ném lại đối tượng mà `e` tham chiếu. |

### 11.1. Các thông báo compiler hay gặp

- **“unreported exception ...; must be caught or declared to be thrown”**: method gọi API có checked exception hoặc thực hiện `throw` với checked exception, nhưng không bắt/khai báo.
- **“incompatible types ... cannot be converted to Throwable”**: biểu thức sau `throw` không thuộc hệ kiểu Throwable.
- **“overridden method does not throw ...”**: method override cố thêm checked exception vượt hợp đồng cha/interface.
- **“exception ... has already been caught”**: handler cụ thể bị một handler rộng hơn ở trước che khuất.

Thông điệp chính xác phụ thuộc compiler/JDK; cần đọc nguyên nhân và sửa hợp đồng hoặc luồng xử lý, không chỉ thêm `throws Exception` tùy tiện.

## 12. Quy trình quyết định khi nào dùng `throw`, khi nào dùng `throws`

### Bước 1 — Xác định điều kiện thất bại

Ví dụ phương thức nhận số lượng và phải bảo đảm `quantity > 0`. Khi phát hiện điều kiện sai, `throw new IllegalArgumentException(...)` diễn đạt vi phạm hợp đồng.

### Bước 2 — Chọn kiểu exception phù hợp

Nếu lỗi do tham số/caller không hợp lệ hoặc trạng thái không cho phép, unchecked exception có thể phù hợp. Nếu API đọc file hoặc giao tiếp với nguồn I/O dùng checked `IOException`, giữ đúng cơ chế khai báo của nó. Không có quy tắc “mọi lỗi người dùng là checked” hoặc “mọi lỗi nghiệp vụ là unchecked”.

### Bước 3 — Xác định tầng có khả năng xử lý

Nếu method cấp thấp không biết nên yêu cầu nhập lại, thử nguồn khác hay hủy thao tác, nó có thể cho checked exception lan lên bằng `throws`. Tầng có ngữ cảnh thực sự mới nên `catch` để phản ứng đúng.

### Bước 4 — Viết chữ ký rõ ràng

Khai báo những checked exceptions dự kiến theo loại có ý nghĩa. Tránh `throws Throwable`, `throws Exception` khi có thể thu hẹp. Với unchecked exceptions quan trọng cho hợp đồng, mô tả bằng Javadoc `@throws` và kiểm thử điều kiện gây lỗi.

### Bước 5 — Kiểm thử cả thành công và lỗi

Đừng chỉ kiểm tra “đúng loại exception”. Kiểm tra input biên, đường lan truyền, trạng thái dữ liệu/tài nguyên sau thất bại, wrapper/cause và vị trí handler thích hợp.

## 13. Javadoc: `@throws` không phải từ khóa `throws`

Một API Java thường có cả mệnh đề `throws` trong chữ ký và thẻ `@throws` trong phần tài liệu. Hai thứ cũng **khác nhau**:

```java
/**
 * Đọc mã từ nguồn dữ liệu.
 *
 * @param input dữ liệu phải khác null
 * @return mã được đọc
 * @throws IllegalArgumentException nếu input sai hợp đồng
 * @throws java.io.IOException nếu nguồn dữ liệu không đọc được
 */
static String readCode(String input) throws java.io.IOException {
    if (input == null) {
        throw new IllegalArgumentException("input không được null");
    }
    return input;
}
```

Đây là một method minh họa. `@throws` trong Javadoc là **mô tả cho người đọc và công cụ sinh tài liệu**, không trực tiếp thay đổi nghĩa vụ của compiler. `throws IOException` trong chữ ký mới là khai báo ngôn ngữ cho checked exception có thể thoát. `throw new IllegalArgumentException(...)` trong thân mới là câu lệnh thực sự ném.

Trong đoạn ví dụ, `IOException` được khai báo để mô tả một biến thể API đọc nguồn; implementation cụ thể trả lại input và không tự phát sinh `IOException`. Compiler Java cho phép một method **khai báo checked exception mà đường thực thi hiện tại chưa ném**; việc ghi hợp đồng quá rộng khi không có lý do thực tế vẫn có thể gây bất tiện cho caller.

## 14. Bài tập tự luyện

### Bài 1 — Phân biệt vai trò từng dòng

Xét đoạn method:

```java
static void verify(boolean valid) throws java.io.IOException {
    if (!valid) {
        throw new java.io.IOException("Không hợp lệ");
    }
}
```

Trả lời:

1. Từ khóa nào có trong **chữ ký**?
2. Dòng nào **thực sự tạo và ném** exception?
3. Gọi `verify(true)` có tự động phát sinh `IOException` vì `throws` hay không?
4. Nếu caller gọi `verify(false)` mà không bắt/khai báo checked exception, compiler báo gì?

**Định hướng:** `throws` đứng ở chữ ký; `throw` đứng trong thân. Với `true`, method kết thúc bình thường; caller vẫn phải thỏa nghĩa vụ compile-time mà chữ ký đã công bố.

### Bài 2 — Sửa lỗi biên dịch

Đoạn sau cố ý sai:

```java
static void reject() {
    throw new java.io.IOException("Đọc thất bại");
}
```

Hãy sửa theo hai phương án: thêm `throws IOException` cho method và cập nhật caller; hoặc dùng `try/catch` trong method để xử lý thật sự. Mô tả sự khác nhau trong trách nhiệm xử lý.

### Bài 3 — Không thấy `throw` mà vẫn cần `throws`

Viết `readFirstLine(BufferedReader reader)` chỉ gọi `reader.readLine()` rồi trả kết quả. Giải thích vì sao phương thức có thể cần `throws IOException` mặc dù không tự gọi `throw`. Sau đó viết `main` bắt `IOException` và hiển thị thông báo có ngữ cảnh.

### Bài 4 — Giữ nguyên cause

Trong `WrapCauseDemo`, thay constructor `new IllegalStateException("...", e)` bằng `new IllegalStateException("...")` rồi chạy lại. `getCause()` khi đó là `null`; mã in `getCause().getClass()` sẽ gây `NullPointerException`. Giải thích tại sao giữ nguyên cause là quan trọng khi bọc lỗi và tại sao không được giả định mọi exception đều có cause.

### Bài 5 — Override và kiểu tham chiếu

Trong `ThrowsOverrideDemo`, thử khai báo `Source source = new MemorySource();`. Mặc dù implementation không khai báo checked exception, vì sao `source.get()` vẫn phải tuân theo hợp đồng `throws IOException` của interface tại điểm biên dịch? Đổi kiểu biến sang `MemorySource` và so sánh nghĩa vụ compile-time.

### Bài 6 — Tự thiết kế API

Tạo hai method: `parseAge(String input)` và `loadAgeFromFile(Path path)`. Method đầu kiểm tra input không âm và ném unchecked exception phù hợp; method thứ hai đọc file, có thể khai báo checked `IOException`, rồi gọi method đầu. Viết Javadoc mô tả từng lỗi; test đường thành công, số âm, chuỗi không phải số, file không tồn tại và dữ liệu sau thất bại.

## 15. Checklist ghi nhớ

- [ ] Viết đúng dạng `throw expression;` và `method(...) throws Type1, Type2`.
- [ ] Biết `throw` là statement thực thi còn `throws` là mệnh đề khai báo.
- [ ] Phân biệt biểu thức đối tượng sau `throw` với **tên kiểu** sau `throws`.
- [ ] Nêu được vì sao `throw "error";` không biên dịch, còn `throw new IOException("error");` đúng kiểu nhưng cần xử lý checked.
- [ ] Giải thích được `throw` unchecked không buộc `throws`.
- [ ] Giải thích được một method có `throws IOException` dù không có lệnh `throw` trực tiếp.
- [ ] Dự đoán chính xác stdout của `ThrowVsThrowsDemo` và `ThrowsPropagationDemo`.
- [ ] Hiểu cách `catch` xử lý sau khi checked exception truyền qua nhiều tầng gọi.
- [ ] Phân biệt `throw e;` với `throw new WrapperException("...", e);` và giữ cause.
- [ ] Nêu được giới hạn của checked exceptions khi override/interface/lambda.
- [ ] Phân biệt Javadoc `@throws` và mệnh đề Java `throws`.
- [ ] Không coi `throws` là cơ chế tự động rollback, tự log hay tự phục hồi.
- [ ] Biết chọn nơi xử lý dựa trên hợp đồng và khả năng khôi phục thật sự.

**Ghi nhớ:** **`throw` làm lỗi xảy ra trên một đường chạy cụ thể; `throws` công bố loại lỗi có thể thoát khỏi phương thức và giúp compiler/caller thực hiện nghĩa vụ với checked exception.** Dùng đúng cả hai giúp đường thành công rõ ràng, đường thất bại có trách nhiệm và các tầng gọi phối hợp dự đoán được.