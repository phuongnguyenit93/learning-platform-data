# Exception và RuntimeException trong Java

`Exception` và `RuntimeException` đều thuộc hệ thống ngoại lệ của Java, nhưng chúng khác nhau ở **quy tắc kiểm tra của trình biên dịch** và cách khai báo, xử lý khi một phương thức có thể thất bại. Hiểu đúng mối quan hệ kế thừa giúp bạn đọc chữ ký API, đặt `try/catch` đúng chỗ và chọn loại ngoại lệ phù hợp khi thiết kế mã Java.

## 1. Vị trí trong phân cấp `Throwable`

~~~text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    └── java.lang.Exception
        ├── java.io.IOException
        ├── java.text.ParseException
        └── java.lang.RuntimeException
            ├── java.lang.IllegalArgumentException
            │   └── java.lang.NumberFormatException
            ├── java.lang.IllegalStateException
            ├── java.lang.IndexOutOfBoundsException
            └── java.lang.NullPointerException
~~~

- `Throwable` là kiểu gốc của những đối tượng Java cho phép ném bằng `throw` và bắt bằng `catch`.
- `Exception` là lớp con trực tiếp của `Throwable`, biểu diễn các tình huống bất thường mà ứng dụng có thể cần xử lý hoặc chuyển tiếp.
- `RuntimeException` **kế thừa `Exception`**. Vì vậy mọi `RuntimeException` cũng là một `Exception`, nhưng không phải mọi `Exception` đều là `RuntimeException`.
- `Error` là nhánh khác của `Throwable`, không nằm dưới `Exception`. Phần lớn ứng dụng không chủ động phục hồi các lỗi hệ thống nghiêm trọng như `OutOfMemoryError`.

Sơ đồ trên chỉ thể hiện **một số lớp tiêu biểu**, không phải toàn bộ phân cấp. Hai nhánh `RuntimeException` và `Error` thuộc nhóm *unchecked*; các lớp `Exception` còn lại thuộc nhóm *checked*.

## 2. Khác biệt quan trọng nhất: checked và unchecked

| Tiêu chí | `Exception` không thuộc nhánh `RuntimeException` | `RuntimeException` và lớp con |
| --- | --- | --- |
| Phân loại | Checked exception | Unchecked exception |
| Ví dụ | `IOException`, `ParseException`, `Exception` trực tiếp | `IllegalArgumentException`, `NullPointerException`, `NumberFormatException` |
| Trình biên dịch yêu cầu gì? | Phải **bắt** hoặc **khai báo** ngoại lệ có thể phát sinh | Không bắt buộc bắt hoặc khai báo |
| Có được khai báo `throws`? | Có; thường cần nếu không xử lý bên trong | Có, nhưng tùy chọn |
| Khi chạy có tự biến mất không? | Không; lan truyền nếu chưa được xử lý | Không; cũng lan truyền nếu chưa được xử lý |
| Có bắt được bằng `catch (Exception e)`? | Có | Có, vì là lớp con của `Exception` |

Trong Java, thuật ngữ *checked* chỉ quy tắc kiểm tra **tại thời điểm biên dịch**. Nó không bảo đảm ngoại lệ là nhẹ hoặc luôn phục hồi được. Ngược lại, *unchecked* không có nghĩa ngoại lệ bị bỏ qua: nếu được ném mà không có nơi bắt phù hợp, ngoại lệ vẫn thoát ra khỏi luồng gọi hiện tại.

Lưu ý quan trọng: bản thân lớp `Exception` là **checked** khi kiểu đó xuất hiện ở vị trí cần kiểm tra, chẳng hạn `throw new Exception(...)` hoặc chữ ký `throws Exception`. Riêng nhánh `RuntimeException` (và các lớp con) được miễn quy tắc này.

## 3. Cơ chế biên dịch và lan truyền

Khi một đoạn mã gọi phương thức có thể ném checked exception, nó phải chọn một trong hai cách:

1. **Xử lý tại đây** bằng `try/catch` phù hợp.
2. **Chuyển trách nhiệm cho nơi gọi** bằng `throws` trong khai báo phương thức.

Ví dụ chữ ký sau cho biết người gọi phải cân nhắc `IOException`:

~~~java
static String loadText(java.nio.file.Path path) throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Đây là **đoạn minh họa khai báo phương thức**, chưa phải chương trình độc lập. Nếu gọi `loadText(path)` trong một phương thức không khai báo `throws IOException` và không bắt ngoại lệ, mã sẽ không biên dịch. Lệnh `throws` **không ném** ngoại lệ; nó mô tả những checked exception có thể thoát khỏi phương thức. Lệnh `throw` mới trực tiếp ném một đối tượng ngoại lệ.

Với unchecked exception, trình biên dịch không yêu cầu `catch` hoặc `throws`:

~~~java
static void requireNonNegative(int value) {
    if (value < 0) {
        throw new IllegalArgumentException("value phải >= 0");
    }
}
~~~

Đây cũng là **đoạn phương thức minh họa**. `IllegalArgumentException` vẫn thật sự được ném khi `value < 0`. Nó lan lên các phương thức gọi cho đến khi gặp `catch` nhận được kiểu tương ứng, hoặc trở thành ngoại lệ không được xử lý của luồng đang thực thi. Ghi `throws IllegalArgumentException` vẫn hợp lệ nếu hữu ích cho tài liệu API, nhưng không bắt buộc.

Khi phương thức khai báo một **kiểu checked rộng**, ví dụ `throws Exception`, người gọi thông thường phải xử lý hoặc khai báo kiểu đó, ngay cả khi một cách triển khai cụ thể thường chỉ ném lớp con unchecked. Quy tắc biên dịch dựa trên hợp đồng kiểu mà mã nhìn thấy.

## 4. Ví dụ Java 17+ chạy độc lập

Ví dụ dưới đây đặt checked và unchecked exception cạnh nhau, đồng thời minh họa cách giữ lại nguyên nhân ban đầu khi chuyển đổi ngoại lệ.

Tạo tệp `ExceptionDemo.java`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ExceptionDemo {
    public static void main(String[] args) {
        try {
            System.out.println("Dòng đầu: " + readFirstLine("Java\nException"));
        } catch (IOException e) {
            System.out.println("Không đọc được dòng đầu");
        }

        for (String input : new String[] {"20", "abc", "-1"}) {
            try {
                System.out.println("Tuổi hợp lệ: " + parseAge(input));
            } catch (IllegalArgumentException e) {
                System.out.println("Input '" + input + "': " + e.getMessage());
                if (e.getCause() != null) {
                    System.out.println(
                            "Nguyên nhân: " + e.getCause().getClass().getSimpleName());
                }
            }
        }
    }

    // readLine() có chữ ký throws IOException: checked exception.
    static String readFirstLine(String text) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(text))) {
            return reader.readLine();
        }
    }

    // IllegalArgumentException là unchecked: không bắt buộc "throws".
    static int parseAge(String input) {
        final int age;
        try {
            age = Integer.parseInt(input);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("phải là số nguyên", e);
        }

        if (age < 0) {
            throw new IllegalArgumentException("không được âm");
        }
        return age;
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac ExceptionDemo.java
java ExceptionDemo
~~~

Kết quả chuẩn:

~~~text
Dòng đầu: Java
Tuổi hợp lệ: 20
Input 'abc': phải là số nguyên
Nguyên nhân: NumberFormatException
Input '-1': không được âm
~~~

**Giải thích từng điểm:**

- `BufferedReader.readLine()` khai báo `throws IOException`. Phương thức `readFirstLine` chọn **chuyển tiếp** bằng `throws IOException`; `main` chọn **bắt** `IOException`. Dữ liệu nằm trong `StringReader` nên nhánh lỗi I/O không được kích hoạt ở lần chạy này, nhưng chữ ký API vẫn phải được tuân thủ khi biên dịch.
- `Integer.parseInt("abc")` ném `NumberFormatException`, một lớp con của `IllegalArgumentException` và `RuntimeException`. Không cần khai báo `throws` cho `parseAge`.
- Khi đổi lỗi phân tích số thành lỗi tham số có ý nghĩa ở mức nghiệp vụ, `new IllegalArgumentException("phải là số nguyên", e)` giữ ngoại lệ gốc trong `getCause()`. Nhờ đó việc chẩn đoán vẫn truy được nguyên nhân.
- Giá trị `-1` là số nguyên hợp lệ về cú pháp nhưng không hợp lệ theo quy tắc của phương thức; chương trình chủ động ném `IllegalArgumentException`. Trường hợp này không có `cause` vì không chuyển đổi từ lỗi thấp hơn.
- `catch (IllegalArgumentException e)` bắt được cả `NumberFormatException` trực tiếp lẫn `IllegalArgumentException` vì quan hệ kế thừa. Đoạn mã không nuốt ngoại lệ một cách im lặng: nó hiển thị kết quả xử lý phù hợp với ví dụ.

Cú pháp `try (resource) { ... }` là **try-with-resources**: `BufferedReader` được đóng tự động sau khi rời khối. Nó không thay thế nghĩa vụ xử lý checked exception nếu phương thức tài nguyên có thể khai báo ngoại lệ.

## 5. Chọn kiểu ngoại lệ khi viết API

Không có quy tắc tuyệt đối rằng mọi lỗi từ bên ngoài đều phải là checked, hoặc mọi lỗi lập trình đều phải là unchecked. Hãy xác định **hợp đồng của phương thức** và hành động thực tế người gọi có thể thực hiện.

| Tình huống | Lựa chọn thường gặp | Cách nghĩ |
| --- | --- | --- |
| Đọc tệp, mở luồng I/O có thể thất bại | `IOException` (checked) | Người gọi có thể thử đường dẫn khác, thông báo lỗi hoặc chuyển tiếp |
| Tham số vi phạm điều kiện phương thức | `IllegalArgumentException` (unchecked) | Người gọi cần sửa giá trị đầu vào |
| Trạng thái đối tượng không cho phép thao tác | `IllegalStateException` (unchecked) | Cần sửa thứ tự thao tác hoặc trạng thái |
| Truy cập đối tượng `null` sai kỳ vọng | `NullPointerException` (unchecked) | Thường là vấn đề hợp đồng/logic; cần xử lý nguyên nhân |
| Chuỗi không thể chuyển thành số | `NumberFormatException` (unchecked) | Xác thực dữ liệu, hiển thị thông báo hoặc chuyển thành lỗi miền phù hợp |

Khi **có hành động phục hồi cụ thể**, bắt ngoại lệ tại tầng hiểu được lỗi. Khi không thể giải quyết, hãy cho ngoại lệ truyền lên đúng hợp đồng API. Với ngoại lệ checked, chuyển tiếp qua `throws` hoặc chuyển thành loại phù hợp và **giữ cause** khi cần. Với unchecked, ưu tiên sửa nguyên nhân hay xác thực dữ liệu đầu vào thay vì bao quanh mọi lệnh bằng `try/catch`.

Một ngoại lệ checked chỉ nên được khai báo rộng như cần thiết: `throws IOException` cho người gọi biết nhiều hơn `throws Exception`. Ngược lại, nếu API chọn checked exception, lớp triển khai và bên gọi phải tuân thủ hợp đồng này; không nên tự ý đổi toàn bộ thành `RuntimeException` chỉ để loại bỏ các khai báo `throws`.

## 6. Quy tắc bắt ngoại lệ liên quan đến kế thừa

### Bắt từ loại cụ thể đến loại tổng quát

~~~java
try {
    // Gọi một thao tác có thể ném IOException hoặc RuntimeException.
} catch (java.io.IOException e) {
    // Xử lý lỗi I/O.
} catch (RuntimeException e) {
    // Xử lý lỗi unchecked phù hợp ở tầng này.
} catch (Exception e) {
    // Các Exception còn lại, nếu có.
}
~~~

Đây là **cấu trúc minh họa**, không phải chương trình độc lập. Khi áp dụng vào mã thật, các `catch` cho checked exception phải phù hợp với các ngoại lệ mà khối `try` thực sự có thể ném. Mọi nhánh bắt đặt sau phải còn có khả năng nhận kiểu khác nhánh trước.

Vì `RuntimeException extends Exception`, đặt `catch (Exception e)` **trước** `catch (RuntimeException e)` sẽ khiến nhánh sau không thể chạy và gây lỗi biên dịch. `catch (Exception e)` bắt được cả checked và unchecked exception trong nhánh `Exception`, nhưng **không** bắt được `Error`.

Có thể dùng multi-catch với các loại không có quan hệ kế thừa, chẳng hạn `catch (IOException | IllegalArgumentException e)`, nếu các kiểu checked được khai báo phù hợp trong khối `try`. Không được viết `catch (Exception | RuntimeException e)` vì hai kiểu có quan hệ cha–con.

### Bắt hay chuyển tiếp?

- **Bắt** nếu mã biết cách xử lý: đổi thông báo sang ngữ cảnh người dùng, sử dụng phương án dự phòng đã xác định, hoặc hủy một thao tác ở đúng tầng.
- **Chuyển tiếp** nếu tầng hiện tại thiếu thông tin để phục hồi. Với checked exception, khai báo `throws` đúng loại; với unchecked exception, nó có thể tự lan truyền.
- **Chuyển đổi kiểu ngoại lệ** khi cần phản ánh hợp đồng tầng cao hơn; truyền ngoại lệ cũ làm `cause` để giữ khả năng truy vết.

Không nên bắt `Exception` hay `Throwable` ở mọi nơi chỉ để chương trình tiếp tục: việc đó có thể che lỗi logic, bỏ mất trạng thái thất bại hoặc vô tình chặn xử lý của tầng cao hơn. Một số ranh giới như bộ điều phối tác vụ hoặc tầng nhận yêu cầu có thể cố ý có xử lý tổng quát, nhưng cần chính sách lỗi rõ ràng.

## 7. Những hiểu lầm thường gặp

**“`RuntimeException` không thuộc `Exception`.”** Sai. Nó kế thừa trực tiếp `Exception`; vì vậy `catch (Exception e)` có thể nhận `RuntimeException`.

**“`Exception` luôn checked.”** Cần nói chính xác: `Exception` trực tiếp và các lớp con **không nằm trong nhánh `RuntimeException`** là checked. Các ngoại lệ nằm dưới `RuntimeException` là unchecked dù vẫn có quan hệ `is-a Exception`.

**“Unchecked exception sẽ không làm hỏng chương trình.”** Sai. Không có yêu cầu biên dịch không đồng nghĩa với việc ngoại lệ được tự động xử lý. Nếu không được bắt, nó có thể kết thúc luồng đang chạy và được runtime hoặc framework báo lại theo ngữ cảnh.

**“Mọi checked exception đều có thể phục hồi, mọi runtime exception đều là lỗi lập trình.”** Không nhất thiết. `IOException` có thể gặp vấn đề không thể khắc phục tại chỗ; `NumberFormatException` cũng có thể là dữ liệu người dùng nhập sai mà ứng dụng chủ động báo lỗi thân thiện.

**“Ghi `throws` là đã xử lý ngoại lệ.”** Sai. `throws` thông báo khả năng lan truyền; `try/catch` mới tạo điểm xử lý. `throw` là lệnh phát sinh một ngoại lệ cụ thể.

**“Bắt `Exception` là bắt mọi `Throwable`.”** Sai. `Error` thuộc nhánh song song. Không nên bắt toàn bộ `Throwable` nếu không có lý do và chính sách đặc biệt.

**“Đổi thành `RuntimeException` là đủ, không cần giữ ngoại lệ gốc.”** Không tốt cho chẩn đoán. Khi bọc lỗi ở tầng thấp, ưu tiên constructor nhận `cause`, ví dụ `new IllegalStateException("Không nạp được cấu hình", e)`.

## 8. Câu hỏi tự kiểm tra

1. Tại sao `IOException` thường phải được bắt hoặc khai báo, còn `NumberFormatException` thì không? Hãy chỉ ra nhánh kế thừa quyết định quy tắc.
2. Nếu một hàm khai báo `throws Exception`, bên gọi có được bỏ cả `catch` và `throws` vì hàm hiện tại chỉ ném `IllegalArgumentException` không?
3. `catch (Exception e)` có bắt `NullPointerException` và `OutOfMemoryError` không? Giải thích bằng sơ đồ lớp.
4. Trong ví dụ `parseAge`, tại sao nên truyền `NumberFormatException` vào constructor của `IllegalArgumentException`?
5. Khi một phương thức đọc tệp không thể phục hồi tại chỗ, bạn sẽ bắt để bỏ qua lỗi hay khai báo `throws IOException` cho tầng gọi?

**Đáp án ngắn:** (1) `IOException` là checked, `NumberFormatException` nằm dưới `RuntimeException`; (2) không, hợp đồng `throws Exception` vẫn là checked; (3) bắt `NullPointerException`, không bắt `OutOfMemoryError`; (4) giữ nguyên nhân cho việc chẩn đoán; (5) chuyển tiếp `IOException` nếu tầng gọi mới đủ ngữ cảnh quyết định.

**Ghi nhớ:** Sự phân biệt cốt lõi là *checked versus unchecked* tại lúc biên dịch. `RuntimeException` vẫn là `Exception`, và cả hai loại đều có thể lan truyền khi chạy; chọn nơi xử lý theo khả năng phục hồi và hợp đồng API.