# `try-catch` để xử lý tình huống có thể thất bại trong Java

## 1. Vì sao cần `try-catch`?

Khi chạy một chương trình Java, có những thao tác có thể thất bại: chuyển chuỗi không hợp lệ thành số, đọc tệp, sử dụng một chỉ số mảng không đúng hoặc gọi dịch vụ bên ngoài. Java biểu diễn nhiều tình huống như vậy bằng **ngoại lệ** (*exception*). Thay vì để ngoại lệ không được xử lý làm luồng thực thi hiện tại kết thúc bất thường, ta có thể dùng `try-catch` để **phản ứng có chủ đích**.

Cấu trúc cơ bản:

```java
try {
    // Những lệnh có thể ném ngoại lệ.
} catch (SomeException ex) {
    // Xử lý đúng loại ngoại lệ đã bắt được.
}
```

- Khối **`try`** chứa thao tác cần bảo vệ.
- Khi một câu lệnh ném ngoại lệ, các câu lệnh còn lại trong phần `try` **không tiếp tục thực hiện theo đường thông thường**.
- Java tìm một `catch` có kiểu phù hợp với đối tượng ngoại lệ, xét theo thứ tự các `catch`.
- **`ex`** là tham số tham chiếu đến đối tượng ngoại lệ, cho phép truy cập thông tin như `getMessage()` hoặc dùng `printStackTrace()`.
- Sau một `catch` xử lý xong và không ném tiếp/return, chương trình tiếp tục ở câu lệnh phía sau cấu trúc `try-catch`.
- Nếu **không có `catch` phù hợp**, ngoại lệ lan tới nơi gọi. Nếu không ai xử lý, nó có thể kết thúc luồng với stack trace.

`try-catch` không tự sửa phép tính sai hay làm dữ liệu đầu vào trở nên hợp lệ; nó chỉ xác định **cách ứng xử khi xảy ra thất bại**.

## 2. Ví dụ tối thiểu: chuyển chuỗi thành số

`Integer.parseInt(String)` chuyển văn bản thành `int`, nhưng chuỗi không biểu diễn số nguyên hợp lệ gây `NumberFormatException`.

```java
String input = "abc";

try {
    int value = Integer.parseInt(input);
    System.out.println("Gia tri: " + value);
} catch (NumberFormatException ex) {
    System.out.println("Du lieu khong phai so nguyen hop le");
}

System.out.println("Tiep tuc chuong trinh");
```

Đây là **đoạn minh họa đặt trong một phương thức**, không phải tệp chạy độc lập. Khi `input = "abc"`, dòng in giá trị không chạy, nhánh `catch` in thông báo, rồi lệnh bên ngoài `try-catch` được thực hiện.

Với `input = "123"`, nhánh `catch` không chạy, biến `value` bằng `123`. Biến `value` khai báo **bên trong `try`** không nằm trong scope của câu lệnh sau khối, nên nếu cần dùng kết quả về sau, có thể trả về từ một phương thức hoặc thiết kế trạng thái phù hợp.

Đừng coi mọi lỗi chuyển đổi thành số đều có thể sửa bằng cách thay giá trị tùy ý. Tùy yêu cầu, lựa chọn đúng có thể là báo cho người dùng nhập lại, từ chối dữ liệu, ghi log rồi chuyển tiếp ngoại lệ hoặc trả về một kết quả thể hiện thất bại.

## 3. Bắt loại ngoại lệ cụ thể trước

Mỗi `catch` bắt một loại ngoại lệ được khai báo hoặc các kiểu con của nó. Vì thế, nên **bắt loại cụ thể trước**, loại tổng quát sau:

```java
try {
    // Xử lý đầu vào, tính toán.
} catch (NumberFormatException ex) {
    System.out.println("Sai dinh dang so");
} catch (IllegalArgumentException ex) {
    System.out.println("Doi so khong hop le");
}
```

`NumberFormatException` là kiểu con của `IllegalArgumentException`. Nếu đặt `catch (IllegalArgumentException ...)` **lên trước**, khối bắt `NumberFormatException` sau đó sẽ trở nên không thể tới được, gây **lỗi biên dịch**. Trong ví dụ trên, thứ tự được viết đúng.

Đừng bắt `Exception` hoặc `Throwable` thật rộng ở mọi tầng của chương trình:

- Bắt quá rộng khiến lỗi lập trình không mong đợi bị xử lý như lỗi dữ liệu thông thường.
- `Throwable` còn bao gồm nhánh `Error` như `OutOfMemoryError` mà chương trình ứng dụng thông thường không nên cố “nuốt”.
- `catch` rỗng làm mất tín hiệu thất bại, khiến việc gỡ lỗi khó khăn.
- Khi không thể khôi phục tại chỗ, có thể **để ngoại lệ lan lên**, hoặc bọc nguyên nhân vào ngoại lệ mang ý nghĩa cấp cao hơn.

Ví dụ một cách chuyển tiếp có nguyên nhân rõ ràng:

```java
static int parseAge(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Age must be a whole number", ex);
    }
}
```

Đây là **phương thức minh họa đặt trong lớp**. Constructor `IllegalArgumentException(String, Throwable)` giữ lại ngoại lệ gốc ở `getCause()`; hữu ích khi xử lý lỗi ở tầng có đủ ngữ cảnh. Không nên bọc ngoại lệ một cách máy móc khi nó không bổ sung ý nghĩa.

## 4. Nhiều `catch` và multi-catch

Nếu các loại ngoại lệ cần cách xử lý riêng, dùng nhiều `catch`. Nếu chúng cần **cùng cách xử lý**, có thể dùng multi-catch (Java 7+):

```java
try {
    String text = args[0];
    int value = Integer.parseInt(text);
    System.out.println(value);
} catch (ArrayIndexOutOfBoundsException | NumberFormatException ex) {
    System.out.println("Can mot doi so nguyen hop le");
}
```

Đây là đoạn minh họa bên trong phương thức có biến `args` thích hợp. Hai ngoại lệ cùng cần phản hồi “không có đầu vào hợp lệ”. Các kiểu trong cùng một multi-catch **không được có quan hệ kiểu con/kiểu cha trực tiếp**; ví dụ `catch (NumberFormatException | IllegalArgumentException ex)` là lỗi biên dịch do một nhánh đã bao hàm nhánh kia.

Khi thiết kế chương trình thật, tốt hơn nên kiểm tra `args.length` để nhận diện thiếu đối số, rồi dùng `catch (NumberFormatException)` cho lỗi chuyển đổi. Không nên dùng ngoại lệ để thay cho mọi nhánh điều kiện thông thường.

**Khi ngoại lệ đã được bắt**, chỉ đúng một `catch` phù hợp đầu tiên được chạy, không tự “rơi tiếp” sang `catch` bên dưới. Một `catch` có thể ném ngoại lệ mới; ngoại lệ mới đó không được các `catch` khác của **cùng cấu trúc `try`** xử lý, mà phải được xử lý ở phạm vi bao ngoài phù hợp.

## 5. Xử lý checked/unchecked theo hợp đồng của thao tác

Nếu một API có thể ném checked `IOException`, như `Files.readString`, caller phải **catch** hoặc khai báo `throws` theo luật Java. Ngược lại, `Integer.parseInt("abc")` ném unchecked `NumberFormatException`, không bắt buộc khai báo nhưng vẫn có thể `catch` khi dữ liệu không hợp lệ là tình huống dự kiến.

~~~java
static String readText(java.nio.file.Path file)
        throws java.io.IOException {
    return java.nio.file.Files.readString(file);
}
~~~

`throws` chỉ cho phép ngoại lệ checked thoát khỏi phương thức; nó không phải handler. `Error` như `OutOfMemoryError` cũng unchecked nhưng thường không phù hợp để bắt và tiếp tục nghiệp vụ. Cây phân loại `Throwable`, quy tắc compiler và việc tự ném được giải thích sâu ở hai bài tiếp theo.

## 6. `finally` vẫn thực hiện phần dọn dẹp thông thường

~~~java
try {
    System.out.println("start");
    throw new IllegalStateException("bad");
} catch (IllegalStateException ex) {
    System.out.println("caught");
} finally {
    System.out.println("cleanup");
}
~~~

Ba dòng trên in lần lượt `start`, `caught`, `cleanup`. `finally` thông thường chạy khi có exception hoặc `return` làm rời khối, nhưng **không cam kết khi JVM/process bị chấm dứt đột ngột**. Tránh `return` hay ném lỗi mới trong `finally` nếu có thể che kết quả/ngoại lệ trước đó.

## 7. Đóng tài nguyên bằng `try-with-resources`

~~~java
static String firstLine(java.nio.file.Path file)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(file)) {
        return reader.readLine();
    }
}
~~~

Tài nguyên phải hỗ trợ `AutoCloseable`; Java tự đóng khi rời khối theo đường bình thường hoặc ngoại lệ. Nếu nhiều tài nguyên, chúng được **đóng ngược thứ tự khởi tạo**. Khi thân và thao tác đóng cùng thất bại, ngoại lệ đóng có thể nằm trong `getSuppressed()`; I/O checked exception **vẫn phải bắt/khai báo**, không tự biến thành thành công.

Ở bài `try-catch`, phần cần nắm là **xử lý thất bại hợp lý**. Bài riêng về `finally`/try-with-resources giải thích chuyên sâu return, masking, thứ tự đóng và suppressed exception.


## 8. Chương trình Java 17+ độc lập với kết quả xác định

Tạo tệp **`TryCatchDemo.java`**:

```java
import java.io.IOException;

public class TryCatchDemo {
    static class TrackedResource implements AutoCloseable {
        void use() {
            System.out.println("Dang su dung tai nguyen");
        }

        @Override
        public void close() {
            System.out.println("Da dong tai nguyen");
        }
    }

    static String checkValue(int value) throws IOException {
        if (value < 0) {
            throw new IOException("Gia tri am");
        }
        return "OK";
    }

    public static void main(String[] args) {
        try {
            int number = Integer.parseInt("abc");
            System.out.println("So: " + number);
        } catch (NumberFormatException ex) {
            System.out.println("Sai dinh dang: " + ex.getClass().getSimpleName());
        }

        int divisor = 0;
        try {
            int result = 12 / divisor;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("Khong the chia cho 0");
        } finally {
            System.out.println("Finally da chay");
        }

        try {
            String value = checkValue(-1);
            System.out.println(value);
        } catch (IOException ex) {
            System.out.println("Checked: " + ex.getMessage());
        }

        try (TrackedResource resource = new TrackedResource()) {
            resource.use();
        }

        int[] numbers = {3, 5};
        try {
            System.out.println(numbers[2]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("Chi so vuot gioi han");
        }

        System.out.println("Chuong trinh van tiep tuc");
    }
}
```

Dùng JDK 17 trở lên. Trong thư mục chứa `TryCatchDemo.java`, chạy giống nhau trên Windows PowerShell/CMD hoặc Linux/macOS:

```bash
javac -encoding UTF-8 TryCatchDemo.java
java TryCatchDemo
```

**Stdout chính xác** (khi biên dịch thành công, `javac` không in gì):

```text
Sai dinh dang: NumberFormatException
Khong the chia cho 0
Finally da chay
Checked: Gia tri am
Dang su dung tai nguyen
Da dong tai nguyen
Chi so vuot gioi han
Chuong trinh van tiep tuc
```

Giải thích theo trình tự:

1. `Integer.parseInt("abc")` ném `NumberFormatException`; dòng `So:` bị bỏ qua và `catch` phù hợp in tên ngoại lệ.
2. `12 / divisor` với `divisor == 0` gây `ArithmeticException`; `catch` in thông báo và `finally` luôn chạy trong đường thực thi bình thường này.
3. `checkValue(-1)` chủ động ném `IOException` (checked exception), được `catch` xử lý với thông điệp `Gia tri am`.
4. `TrackedResource` được tạo trong try-with-resources; `resource.use()` in một dòng rồi `close()` in dòng kế tiếp khi ra khỏi khối.
5. Truy cập `numbers[2]` trên mảng có hai phần tử gây `ArrayIndexOutOfBoundsException`, được xử lý; chương trình tiếp tục tới dòng in cuối.

Việc bắt các ngoại lệ ở đây nhằm **minh họa**, không có nghĩa trong ứng dụng thật nên bắt lỗi chỉ số mảng để che đi việc dùng chỉ số sai. Hãy sửa điều kiện truy cập mảng và dùng `catch` cho thất bại mà ứng dụng có cách xử lý hợp lý.

## 9. Chọn cách xử lý thay vì “nuốt” ngoại lệ

Có vài chiến lược tùy yêu cầu nghiệp vụ.

| Tình huống | Chiến lược thường phù hợp |
| --- | --- |
| Người dùng nhập chuỗi không phải số | Bắt `NumberFormatException`, thông báo rõ và yêu cầu nhập lại |
| Tệp đầu vào không tồn tại hoặc không đọc được | Bắt `IOException` tại tầng biết nên thử lại, báo lỗi hay hủy thao tác |
| Đối số vi phạm điều kiện trước khi xử lý | Kiểm tra trước và ném `IllegalArgumentException` khi đó là lỗi sử dụng API |
| Thành phần tầng thấp thất bại nhưng tầng trên cần ngữ cảnh | Ném một exception thích hợp có **cause** gốc |
| Không có cách khôi phục ở tầng hiện tại | Để ngoại lệ lan lên hoặc khai báo `throws` phù hợp |
| Tài nguyên phải được đóng | `try-with-resources` nếu tài nguyên hỗ trợ |

Ví dụ **không nên viết**:

```java
try {
    doWork();
} catch (Exception ex) {
    // Bo qua tat ca loi
}
```

Đây chỉ là minh họa với phương thức `doWork()` chưa định nghĩa. Cách bắt quá rộng và im lặng như vậy có thể khiến chương trình tưởng rằng công việc đã thành công dù dữ liệu chưa được lưu hoặc tài nguyên chưa được xử lý đúng.

Thay vào đó, hãy lựa chọn rõ **hậu điều kiện**: nếu chuyển đổi thất bại thì không trả giá trị sai như thể hợp lệ; nếu ghi tệp thất bại thì không thông báo “đã lưu”; nếu một request thất bại thì phản hồi trạng thái tương ứng thay vì tiếp tục với dữ liệu thiếu.

## 10. Lỗi thường gặp khi dùng `try-catch`

1. **Đặt `try` quanh quá nhiều mã:** khó biết dòng nào có thể thất bại và vô tình bắt lỗi không mong muốn. Đặt phạm vi `try` đủ nhỏ để xử lý rõ ràng.
2. **Bắt lớp cha trước lớp con:** có thể gây unreachable catch và lỗi biên dịch; bắt cụ thể trước, tổng quát sau.
3. **Dùng multi-catch cho kiểu có quan hệ kế thừa:** `catch (NumberFormatException | IllegalArgumentException ex)` không hợp lệ.
4. **Bắt `Exception` rồi bỏ qua:** che lỗi, phá khả năng chẩn đoán, có thể để chương trình trong trạng thái không hợp lệ.
5. **Nhầm `throws` với `catch`:** `throws` khai báo khả năng lan ngoại lệ; `catch` thực hiện xử lý tại chỗ.
6. **Cho rằng `finally` bảo đảm chạy cả khi JVM chết/tiến trình bị giết:** không có bảo đảm như vậy.
7. **Đóng tài nguyên thủ công thiếu an toàn:** dùng try-with-resources khi có thể.
8. **Bắt `Error` hoặc `Throwable` tùy tiện:** thường không thể khôi phục tình trạng lỗi hệ thống như ứng dụng mong muốn.
9. **Tạo ngoại lệ mới mà không giữ cause:** làm mất nguồn gốc lỗi; khi bọc cần cân nhắc `new SomeException(message, cause)`.
10. **Dùng ngoại lệ thay cho kiểm tra điều kiện thông thường:** kiểm tra `args.length`, chỉ số mảng, tiền điều kiện trước; chỉ dùng `catch` khi thao tác thực sự có thể thất bại.

**Ghi nhớ:** `try` xác định thao tác có thể thất bại; `catch` xử lý đúng **loại ngoại lệ** khi có cách ứng xử thích hợp; `finally` cho các bước cần thực hiện khi rời khối, còn `try-with-resources` giúp đóng tài nguyên. Mục tiêu là giữ hành vi chương trình **rõ ràng, đúng yêu cầu và dễ chẩn đoán**, không phải loại bỏ mọi thông báo lỗi bằng mọi giá.