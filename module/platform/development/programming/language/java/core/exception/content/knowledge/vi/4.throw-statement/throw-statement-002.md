# Tạo đối tượng ngoại lệ bằng constructor trong Java

Trong Java, ngoại lệ là **đối tượng**. Trước khi một ngoại lệ có thể được ném bằng lệnh `throw`, chương trình cần có một tham chiếu đến đối tượng thuộc lớp kế thừa `Throwable`. Cách thường gặp nhất là gọi **constructor** với toán tử `new`:

~~~java
throw new IllegalArgumentException("Tuổi phải lớn hơn hoặc bằng 0");
~~~

Câu lệnh này gồm **hai hành động khác nhau**:

1. `new IllegalArgumentException("...")` tạo một đối tượng ngoại lệ, truyền thông điệp vào constructor.
2. `throw` ném tham chiếu đến đối tượng đó, làm luồng thực thi bình thường bị ngắt và bắt đầu quá trình tìm `catch` phù hợp.

Có thể tạo đối tượng trước rồi ném sau; riêng việc tạo đối tượng **chưa làm phát sinh luồng điều khiển ngoại lệ**. Bài này giải thích constructor của các lớp ngoại lệ, cách truyền message và cause, cách tự định nghĩa ngoại lệ và những lỗi dễ mắc khi sử dụng `throw new`.

## 1. Ngoại lệ là đối tượng kế thừa `Throwable`

Phân cấp rút gọn:

~~~text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    └── java.lang.Exception
        ├── java.io.IOException
        └── java.lang.RuntimeException
            ├── java.lang.IllegalArgumentException
            │   └── java.lang.NumberFormatException
            ├── java.lang.IllegalStateException
            └── java.lang.NullPointerException
~~~

Các lớp này sở hữu hoặc kế thừa trạng thái và hành vi như:

- `getMessage()`: lấy thông điệp mô tả lỗi.
- `getCause()`: lấy ngoại lệ/nguyên nhân gốc được liên kết, nếu có.
- `getStackTrace()` và `printStackTrace()`: phục vụ chẩn đoán vị trí tạo/ghi nhận stack trace.
- `getSuppressed()`: lấy các ngoại lệ bị kèm theo, chẳng hạn khi đóng tài nguyên trong try-with-resources.

Constructor là nơi chương trình **khởi tạo** đối tượng này. Constructor không quyết định ngoại lệ có checked hay unchecked: điều đó phụ thuộc **kiểu lớp** của đối tượng. Ví dụ:

- `new IOException("...")` tạo checked exception.
- `new IllegalArgumentException("...")` tạo unchecked exception.
- Cả hai đều có thể được lưu vào biến, truyền cho phương thức hoặc ném bằng `throw`.

Với một lớp `Throwable`, `new` không tự động đồng nghĩa với `throw`.

## 2. Phân biệt khởi tạo ngoại lệ với ném ngoại lệ

`new IllegalArgumentException("x")` tạo đối tượng exception và **không tự truyền lỗi tới caller**; `throw new IllegalArgumentException("x");` vừa tạo vừa ném. Nếu đã có biến `e` phù hợp với `Throwable`, `throw e;` ném đối tượng đang tham chiếu mà không gọi constructor mới. `throws IOException` ở chữ ký method chỉ mô tả khả năng checked exception thoát ra, không tạo hay ném đối tượng.

```java
IllegalArgumentException ex = new IllegalArgumentException("Sai");
System.out.println(ex.getMessage()); // Vẫn chạy bình thường.
throw ex; // Bắt đầu chuyển điều khiển theo exception.
```

Đây là snippet trong một method. Tạo `new IOException(...)` cũng không tự phát sinh nghĩa vụ `catch-or-declare` nếu không có đường thực sự ném checked exception. Trọng tâm của bài này là **constructor, message, cause và super(...)**; diễn biến chi tiết của `new` so với `throw` được trình bày trong bài phân biệt hai thao tác.

## 3. Những dạng constructor phổ biến

Các lớp ngoại lệ chuẩn có thể cung cấp một hay nhiều constructor trong số các dạng sau. **Không phải mọi lớp ngoại lệ đều có đầy đủ tất cả dạng này**; phải kiểm tra API của kiểu cụ thể.

### Constructor không tham số

~~~java
RuntimeException issue = new RuntimeException();
~~~

Ở ví dụ này, `issue.getMessage()` là `null` vì không có thông điệp được truyền vào. Một số lớp cũng cung cấp constructor không tham số, nhưng không nên mặc định mọi lớp đều có.

### Constructor nhận thông điệp: `(String message)`

~~~java
IllegalArgumentException issue =
        new IllegalArgumentException("age phải >= 0");
~~~

Thông điệp thường được lưu lại để trả về qua `getMessage()`. Message nên nói rõ **điều kiện nào không đạt**, đủ để người đọc log hiểu ngữ cảnh:

- Hữu ích: `"age phải nằm trong khoảng 0..150"`.
- Khó chẩn đoán: `"Lỗi"` hoặc `"Có vấn đề"`.

Message là dữ liệu chẩn đoán, không phải lựa chọn tốt để điều khiển luồng bằng cách so sánh chuỗi; văn bản có thể thay đổi hoặc được bản địa hóa.

### Constructor nhận nguyên nhân: `(Throwable cause)`

~~~java
IllegalStateException issue =
        new IllegalStateException(
                new java.io.IOException("Không đọc được cấu hình"));
~~~

Ví dụ dùng constructor `IllegalStateException(Throwable)` có sẵn. `issue.getCause()` trả về đối tượng `IOException` đã truyền vào. Với constructor dạng này được kế thừa theo thiết kế của `Throwable`, thông điệp của ngoại lệ mới thường được tạo từ `cause.toString()` nếu nguyên nhân khác `null`. Thông điệp đó không nhất thiết mô tả đủ ngữ cảnh ở tầng cao hơn.

### Constructor nhận cả thông điệp và nguyên nhân: `(String message, Throwable cause)`

~~~java
java.io.IOException lowLevel =
        new java.io.IOException("Tệp không tồn tại");

IllegalStateException issue =
        new IllegalStateException(
                "Không thể khởi tạo ứng dụng", lowLevel);
~~~

Khi cần chuyển đổi loại ngoại lệ giữa các tầng, constructor dạng này thường hữu ích nhất:

- `issue.getMessage()` trả về `"Không thể khởi tạo ứng dụng"`.
- `issue.getCause() == lowLevel` là `true`.
- Ngoại lệ tầng cao giải thích **thao tác nào thất bại**; cause giữ nguyên thông tin gốc để điều tra.

Nếu chỉ gọi `new IllegalStateException("Không thể khởi tạo ứng dụng")` khi đang bọc lỗi thấp tầng, liên kết cause sẽ mất, trừ khi được thiết lập riêng bằng cách hợp lệ.

### Constructor nào thực sự có sẵn?

Các ví dụ trên dùng constructor tồn tại ở `RuntimeException`, `IllegalStateException`, `IOException` và `IllegalArgumentException` trong Java 17+. Một lớp cụ thể có thể chỉ hỗ trợ vài dạng hoặc yêu cầu tham số đặc biệt. Chẳng hạn:

~~~java
NumberFormatException bad =
        new NumberFormatException("Không phải số nguyên");
~~~

Constructor `NumberFormatException(String)` hợp lệ; tuy nhiên không thể mặc định lớp này có constructor `NumberFormatException(String, Throwable)` chỉ vì một số lớp cha có constructor tương tự. **Constructor không được kế thừa** như phương thức thông thường. Hãy tra chữ ký constructor của chính lớp cần tạo.

## 4. Chọn message và cause để bảo toàn thông tin lỗi

Giả sử ứng dụng chuyển một chuỗi cấu hình sang số nguyên:

~~~java
static int parsePort(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "Cổng không phải số nguyên: " + raw, cause);
    }
}
~~~

Đây là một **phương thức minh họa**, không phải chương trình độc lập. Khi đầu vào không thể phân tích, `Integer.parseInt` ném `NumberFormatException`. Khối `catch` tạo một đối tượng `IllegalArgumentException` mới với:

- Message cho biết đầu vào nào không hợp lệ trong ngữ cảnh cổng mạng.
- Cause là `NumberFormatException` gốc.

Vì `NumberFormatException` cũng là lớp con của `IllegalArgumentException`, việc bọc ngoại lệ ở đây chủ yếu nhằm **bổ sung ngữ cảnh**, không thay đổi nhánh checked/unchecked. Cần cân nhắc liệu tầng gọi có cần biết lỗi đã được chuyển đổi không; không bắt rồi bọc mọi ngoại lệ nếu không có lý do.

### Không dùng message để giả lập cause

Ví dụ ít hữu ích:

~~~java
throw new IllegalStateException(
        "Không đọc được cấu hình: " + original.getMessage());
~~~

Nếu `original` là một biến ngoại lệ có thật trong phạm vi, đoạn này chỉ sao chép một phần văn bản; `getCause()` của ngoại lệ mới vẫn là `null`. Thay vào đó:

~~~java
throw new IllegalStateException(
        "Không đọc được cấu hình", original);
~~~

Đây là hai dòng **minh họa trong ngữ cảnh có biến `original`**, chưa phải chương trình hoàn chỉnh. Constructor nhận cause giữ liên kết có cấu trúc đến ngoại lệ gốc.

### Cẩn thận với dữ liệu nhạy cảm

Message có thể xuất hiện trong log, stack trace hoặc phản hồi lỗi nếu ứng dụng cấu hình thiếu chặt chẽ. Tránh đưa mật khẩu, token, thông tin xác thực hoặc toàn bộ nội dung tài liệu riêng tư vào chuỗi lỗi. Chỉ ghi những thông tin cần thiết và an toàn, ví dụ tên tham số, mã thao tác hoặc định danh đã được làm sạch.

## 5. Chương trình Java 17+ chạy độc lập

Ví dụ dưới đây minh họa bốn điều quan trọng:

1. Constructor tạo đối tượng trước khi ném.
2. `throw new` dùng constructor ngay tại điểm thất bại.
3. Ngoại lệ riêng nhận cả message và cause.
4. `getMessage()` và `getCause()` cho kết quả chính xác và có thể kiểm tra.

Tạo tệp **`ExceptionConstructorDemo.java`**:

~~~java
public class ExceptionConstructorDemo {

    static class ConfigurationException extends Exception {
        ConfigurationException(String message) {
            super(message);
        }

        ConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        IllegalArgumentException prepared =
                new IllegalArgumentException("Tên không được trống");

        System.out.println("Tạo trước: " + prepared.getMessage());

        try {
            throw prepared;
        } catch (IllegalArgumentException e) {
            System.out.println("Bắt sau: " + e.getMessage());
            System.out.println("Cùng đối tượng: " + (e == prepared));
        }

        try {
            System.out.println("Cổng: " + readPort("abc"));
        } catch (ConfigurationException e) {
            System.out.println("Lỗi cấu hình: " + e.getMessage());
            System.out.println(
                    "Cause: " + e.getCause().getClass().getSimpleName());
        }

        try {
            System.out.println("Cổng: " + readPort("70000"));
        } catch (ConfigurationException e) {
            System.out.println("Lỗi cấu hình: " + e.getMessage());
            System.out.println("Cause: " + e.getCause());
        }

        System.out.println("Cổng: " + readPortOrDefault("8080", 80));
        System.out.println("Cổng mặc định: " + readPortOrDefault("abc", 80));
    }

    static int readPort(String raw) throws ConfigurationException {
        final int port;
        try {
            port = Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new ConfigurationException(
                    "Cổng không phải số nguyên: " + raw, cause);
        }

        if (port < 1 || port > 65535) {
            throw new ConfigurationException(
                    "Cổng phải nằm trong khoảng 1..65535");
        }

        return port;
    }

    static int readPortOrDefault(String raw, int fallback) {
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ExceptionConstructorDemo.java
java ExceptionConstructorDemo
~~~

Kết quả stdout:

~~~text
Tạo trước: Tên không được trống
Bắt sau: Tên không được trống
Cùng đối tượng: true
Lỗi cấu hình: Cổng không phải số nguyên: abc
Cause: NumberFormatException
Lỗi cấu hình: Cổng phải nằm trong khoảng 1..65535
Cause: null
Cổng: 8080
Cổng mặc định: 80
~~~

**Diễn giải:**

- `prepared` được tạo từ `new IllegalArgumentException(...)` rồi mới ném bằng `throw prepared;`. So sánh `e == prepared` cho `true` vì khối `catch` nhận **cùng tham chiếu** đối tượng đã ném; `throw` không tự tạo bản sao.
- `readPort("abc")` gặp lỗi chuyển đổi chuỗi. Constructor `ConfigurationException(String, Throwable)` gọi `super(message, cause)` nên giữ nguyên `NumberFormatException`; vì thế tên lớp cause được in là `NumberFormatException`.
- `readPort("70000")` chuyển được sang số nhưng vi phạm miền giá trị. Ngoại lệ được tạo bởi constructor chỉ nhận message; `getCause()` là `null`.
- `readPortOrDefault` minh họa lựa chọn xử lý tại tầng có giá trị dự phòng: `Integer.parseInt("abc")` ném ngoại lệ unchecked và phương thức chọn trả `80`. Hàm này chỉ kiểm tra khả năng phân tích số, **không kiểm tra miền cổng 1..65535**; với API thật, phải xác thực thêm nếu đó là yêu cầu hợp đồng.
- `ConfigurationException` là checked exception vì kế thừa `Exception` và không thuộc nhánh `RuntimeException`; các lời gọi `readPort` được đặt trong `try/catch` tương ứng.

Việc chủ động `new` và `throw` làm rõ ranh giới: **constructor xác định dữ liệu của ngoại lệ; `throw` chuyển điều khiển sang cơ chế xử lý ngoại lệ**.

## 6. Constructor của ngoại lệ tùy biến

Khi ngoại lệ chuẩn không biểu đạt đủ ý nghĩa của một lỗi trong miền ứng dụng, có thể khai báo lớp ngoại lệ riêng. Hai lựa chọn thường gặp:

### Ngoại lệ tùy biến loại checked

~~~java
public class ImportException extends Exception {
    public ImportException(String message) {
        super(message);
    }

    public ImportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là **nội dung một lớp độc lập** nếu đặt trong `ImportException.java`. Kiểu này là checked, nên phương thức ném nó phải bắt hoặc khai báo theo quy tắc Java:

~~~java
static void importData() throws ImportException {
    throw new ImportException("Dữ liệu nhập thiếu trường bắt buộc");
}
~~~

Phương thức minh họa này cần nằm trong một lớp Java. Nếu thông tin nhập liệu có thể được người gọi xử lý một cách có cấu trúc, loại checked có thể giúp hợp đồng API yêu cầu người gọi cân nhắc thất bại.

### Ngoại lệ tùy biến loại unchecked

~~~java
public class InvalidOrderStateException extends RuntimeException {
    public InvalidOrderStateException(String message) {
        super(message);
    }

    public InvalidOrderStateException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là **nội dung một lớp độc lập** nếu lưu trong `InvalidOrderStateException.java`. Ngoại lệ này không bắt buộc được khai báo `throws` hay bắt ở bên gọi vì kế thừa `RuntimeException`.

Không có quy tắc “ngoại lệ riêng luôn phải checked” hoặc “mọi lỗi nghiệp vụ đều unchecked”. Chọn loại theo hợp đồng, khả năng xử lý của người gọi và quy ước thiết kế API.

### Vì sao constructor của lớp con gọi `super(...)`?

Constructor của lớp con **không tự động kế thừa constructor** của lớp cha. Khi viết `super(message)` hoặc `super(message, cause)`, bạn chuyển dữ liệu tới cơ chế khởi tạo của `Throwable` thông qua lớp cha tương ứng.

Nếu một lớp ngoại lệ tự định nghĩa constructor chỉ viết:

~~~java
public MyException(String message) {
    // Không gọi super(message).
}
~~~

thì nếu lớp có constructor cha không tham số phù hợp và mã biên dịch được, Java sẽ gọi `super()` ngầm định. Chuỗi `message` **không tự động được gán** vào trạng thái message của `Throwable`, nên `getMessage()` thường trả `null`. Để sử dụng được constructor như ví dụ, `MyException` phải được khai báo hợp lệ với lớp cha có constructor tương ứng; đoạn này chỉ minh họa khác biệt của việc gọi `super`.

Không nên tạo một trường `message` trùng nghĩa chỉ để “sửa” vấn đề trên. Hãy ưu tiên `super(message)` để giữ hành vi nhất quán với các API xử lý ngoại lệ trong Java.

## 7. Cause, `initCause` và chuỗi nguyên nhân

Các lớp ngoại lệ được xây dựng trên `Throwable` có thể giữ **chuỗi nguyên nhân**:

~~~text
IllegalStateException: Không thể khởi tạo ứng dụng
└── caused by IOException: Không đọc được cấu hình
    └── caused by FileNotFoundException: Thiếu file cấu hình
~~~

Hình trên mô tả ý tưởng của liên kết `getCause()`, không phải nguyên văn một stack trace do JVM in ra.

Thông thường, hãy ưu tiên constructor nhận cause:

~~~java
throw new IllegalStateException(
        "Không thể khởi tạo ứng dụng", original);
~~~

Nếu một lớp không có constructor nhận cause nhưng cho phép thiết lập cause sau khi tạo, `Throwable.initCause(Throwable)` có thể gán cause **một lần**:

~~~java
Exception wrapper = new Exception("Không thể xử lý");
wrapper.initCause(new java.io.IOException("Kết nối bị ngắt"));
~~~

Hai câu lệnh trên hợp lệ khi đặt trong phương thức Java. Tuy nhiên:

- `initCause` không thể gọi lại nhiều lần thành công trên cùng một đối tượng; gọi lại sẽ ném `IllegalStateException`.
- Không được đặt một ngoại lệ làm cause của chính nó.
- Nếu constructor đã **khởi tạo cause** (kể cả truyền `null` vào constructor nhận cause), `initCause` không thể thay thế lại.
- Khi lớp có constructor nhận `Throwable` hoặc `(String, Throwable)`, hãy dùng nó trực tiếp thay cho `initCause`.

**Cause** và **suppressed exceptions** là hai cơ chế khác nhau. Cause mô tả quan hệ nguyên nhân gây ra ngoại lệ bên ngoài; suppressed exceptions có thể giữ thêm các lỗi xảy ra trong cùng quá trình dọn dẹp, đặc biệt với try-with-resources. Không dùng `addSuppressed` làm bản thay thế tùy tiện cho cause.

## 8. Stack trace được tạo khi nào?

Mặc định, các constructor của `Throwable` thường ghi nhận stack trace tại thời điểm đối tượng được **khởi tạo**, thông qua cơ chế điền stack trace của lớp cha. Vì vậy:

~~~java
RuntimeException ex = new RuntimeException("Ví dụ");
// Có thể kiểm tra ex.getStackTrace() ở đây, dù chưa throw.
~~~

Đây là đoạn minh họa; stack trace không đồng nghĩa ngoại lệ đã bị ném hoặc được ghi log. Việc gọi `new RuntimeException(...)` thường đã tạo thông tin phục vụ chẩn đoán.

Một số tình huống quan trọng:

- Nếu tạo ngoại lệ ở một nơi rồi ném ở nơi khác, stack trace của chính đối tượng thường phản ánh **vị trí tạo** ngoại lệ.
- Ném lại **cùng đối tượng** bằng `throw e;` không tự động tạo một stack trace hoàn toàn mới tại điểm ném lại.
- Có thể tùy chỉnh cách ghi stack trace, ví dụ các constructor `Throwable`/`Exception`/`RuntimeException` có tùy chọn `writableStackTrace` dành cho các trường hợp đặc biệt; không nên tắt stack trace nếu cần điều tra lỗi.
- Tránh tái sử dụng cùng một đối tượng ngoại lệ cho nhiều sự cố độc lập; stack trace và cause có thể không còn phản ánh đúng bối cảnh từng lần.
- Tự gọi `fillInStackTrace()` có thể cập nhật dấu vết của đối tượng, nhưng làm thay đổi thông tin chẩn đoán; đa số ứng dụng không cần thực hiện thủ công.

Đặc biệt, *message*, *cause* và *stack trace* là ba thứ riêng biệt: message giải thích nội dung lỗi; cause liên kết nguồn gốc; stack trace giúp định vị đường gọi tại điểm ghi nhận.

## 9. Constructor và checked exception: phân loại không phụ thuộc tham số

Hai lệnh:

~~~java
new java.io.IOException("Không đọc được");
new IllegalStateException("Đối tượng chưa sẵn sàng");
~~~

đều chỉ **tạo đối tượng**. Khi ném:

~~~java
static void checkedExample() throws java.io.IOException {
    throw new java.io.IOException("Không đọc được");
}

static void uncheckedExample() {
    throw new IllegalStateException("Đối tượng chưa sẵn sàng");
}
~~~

Đây là hai phương thức minh họa. `checkedExample` khai báo `throws IOException` vì `IOException` là checked; `uncheckedExample` không bị buộc khai báo vì `IllegalStateException` là unchecked.

Thay constructor từ `(String)` sang `(String, Throwable)` **không làm thay đổi** ngoại lệ checked thành unchecked hay ngược lại. Đó là đặc điểm của **lớp ngoại lệ**, được quyết định bởi quan hệ kế thừa với `RuntimeException` và `Error`.

## 10. Các lỗi phổ biến khi tạo ngoại lệ

### Quên `throw`

~~~java
if (age < 0) {
    new IllegalArgumentException("age không được âm");
}
~~~

Đây là **phản ví dụ**: chương trình tạo đối tượng rồi bỏ qua; nó không ném ngoại lệ. Cách đúng:

~~~java
if (age < 0) {
    throw new IllegalArgumentException("age không được âm");
}
~~~

Hai đoạn giả định biến `age` đã tồn tại và nằm trong một phương thức.

### Dùng constructor không tồn tại

Không phải mọi kiểu ngoại lệ đều có đủ bốn overload chuẩn. Constructor không được kế thừa, nên `new SomeException("message", cause)` chỉ hợp lệ khi **lớp `SomeException` thực sự khai báo constructor tương ứng**. Với lớp tùy biến, hãy định nghĩa overload và gọi `super` phù hợp.

### Bỏ mất cause khi chuyển đổi ngoại lệ

~~~java
catch (java.io.IOException e) {
    throw new IllegalStateException("Không tải được dữ liệu");
}
~~~

Đoạn minh họa trên đánh mất liên kết cause. Khi thích hợp, nên viết:

~~~java
catch (java.io.IOException e) {
    throw new IllegalStateException("Không tải được dữ liệu", e);
}
~~~

Đây là các **đoạn `catch` minh họa** gắn với một `try` thực sự có thể ném `IOException`. Giữ cause giúp đọc được quan hệ `Caused by` khi in stack trace.

### Dùng ngoại lệ quá chung chung

~~~java
throw new RuntimeException("Sai");
~~~

Câu lệnh hợp lệ nhưng mơ hồ. Nếu tham số đầu vào không hợp lệ, `IllegalArgumentException` với message cụ thể thường có ích hơn. Nếu thao tác không hợp lệ vì trạng thái đối tượng, cân nhắc `IllegalStateException`. Chọn kiểu tương ứng hợp đồng thay vì lúc nào cũng dùng `Exception` hoặc `RuntimeException`.

### Đưa bí mật vào message

Thông điệp nên cung cấp ngữ cảnh có ích nhưng không phải nơi để chép token, mật khẩu hoặc dữ liệu riêng tư. Đọc log cũng là một phần của mô hình bảo mật ứng dụng.

### Tạo ngoại lệ một lần và ném đi ném lại không kiểm soát

Mỗi sự cố mới thường nên có đối tượng ngoại lệ riêng để phản ánh đúng bối cảnh và nguyên nhân. Dùng lại cùng một đối tượng ở nhiều vị trí có thể gây hiểu nhầm về stack trace, cause và lịch sử sự cố, đặc biệt giữa nhiều luồng.

### Nhầm cause với kiểu ngoại lệ đang được ném

~~~java
RuntimeException wrapper =
        new IllegalStateException(
                "Lỗi miền", new java.io.IOException("Lỗi I/O"));
throw wrapper;
~~~

Đoạn này ném một `IllegalStateException`. `catch (IOException e)` **không** tự động nhận nó, dù `getCause()` trả về `IOException`. Trình xử lý so khớp kiểu ngoại lệ hiện đang truyền. Muốn xử lý nguồn gốc, tầng phù hợp có thể xem `getCause()` hoặc thiết kế API khác.

### Gọi `initCause` sau constructor đã khởi tạo cause

~~~java
Exception e = new Exception("Lỗi", null);
e.initCause(new java.io.IOException("Nguyên nhân mới"));
~~~

Đây là **phản ví dụ**: constructor `Exception(String, Throwable)` đã khởi tạo trạng thái cause dù tham số là `null`. Lệnh `initCause` sau đó ném `IllegalStateException`. Tránh kiểu khởi tạo hai bước khi đã có constructor nhận cause.

## 11. Tiêu chí chọn constructor phù hợp

| Nhu cầu | Cách chọn thường dùng | Mục đích |
| --- | --- | --- |
| Lỗi mới, mô tả trực tiếp | `new IllegalArgumentException("...")` | Cung cấp message cho điều kiện vi phạm |
| Chuyển đổi từ ngoại lệ thấp tầng | `new IllegalStateException("...", cause)` | Giữ cause và bổ sung ngữ cảnh |
| Đã có đối tượng ngoại lệ | `throw e;` | Ném tiếp cùng đối tượng khi hợp đồng cho phép |
| API checked exception riêng | Lớp `extends Exception` với `super(message, cause)` | Người gọi phải xét nghĩa vụ catch/throws |
| API unchecked exception riêng | Lớp `extends RuntimeException` với `super(message, cause)` | Biểu diễn lỗi không có nghĩa vụ bắt/khai báo |
| Cần lưu thêm mã lỗi có cấu trúc | Constructor tùy biến nhận `code` và chuyển message/cause qua `super` | Máy xử lý theo mã ổn định; người đọc xem message |

Nếu lớp lỗi riêng cần trường mã lỗi, có thể viết:

~~~java
public final class ValidationException extends RuntimeException {
    private final String code;

    public ValidationException(
            String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

Đây là **lớp độc lập** nếu lưu trong `ValidationException.java`. Cách dùng:

~~~java
throw new ValidationException(
        "INVALID_AGE", "Tuổi không hợp lệ", originalCause);
~~~

Dòng sử dụng là minh họa trong phạm vi có biến `originalCause` thích hợp. Hợp đồng có thể kiểm tra `getCode()` thay vì so sánh chuỗi `getMessage()`, bởi message có thể thay đổi.

## 12. Câu hỏi tự kiểm tra

1. Điểm khác nhau giữa `new IllegalArgumentException("x")` và `throw new IllegalArgumentException("x");` là gì?
2. Tạo `new IOException("x")` nhưng không ném thì có bắt buộc khai báo `throws IOException` không?
3. Khi nào bạn dùng constructor `(String message, Throwable cause)` thay vì chỉ `(String message)`?
4. Tại sao constructor lớp ngoại lệ riêng nên gọi `super(message, cause)` khi được truyền hai tham số?
5. Constructor có được kế thừa từ `RuntimeException` sang lớp con một cách tự động không?
6. Một `IllegalStateException` có cause là `IOException` sẽ được `catch (IOException e)` bắt trực tiếp không?
7. Stack trace thông thường gắn với thời điểm tạo ngoại lệ hay chỉ xuất hiện lần đầu khi `throw`?
8. Điều gì xảy ra nếu gọi `initCause` trên ngoại lệ đã được khởi tạo cause bằng constructor nhận `(String, Throwable)`?
9. Vì sao một API nên tránh để caller suy luận loại lỗi bằng cách so sánh chuỗi message?
10. Khi nào cần tạo một lớp ngoại lệ riêng thay vì sử dụng `IllegalArgumentException` hoặc `IllegalStateException`?

**Đáp án tóm tắt:** (1) `new` tạo đối tượng, `throw` ném đối tượng; (2) không, nghĩa vụ checked phát sinh khi ném/gọi mã có thể ném; (3) khi bọc lỗi và cần giữ nguyên nhân; (4) để khởi tạo message/cause tại `Throwable`; (5) không; (6) không, vì đối tượng đang truyền là `IllegalStateException`; (7) thông thường khi khởi tạo đối tượng `Throwable`; (8) ném `IllegalStateException`; (9) vì message không phải hợp đồng máy đọc ổn định; (10) khi cần ngữ nghĩa lỗi, mã lỗi hoặc hợp đồng API riêng.

**Ghi nhớ:** **Constructor tạo và khởi tạo thông tin của một đối tượng ngoại lệ; lệnh `throw` mới phát sinh đường truyền ngoại lệ.** Chọn overload phù hợp để cung cấp message hữu ích, giữ cause khi bọc lỗi và dùng đúng kiểu checked/unchecked theo hợp đồng phương thức.