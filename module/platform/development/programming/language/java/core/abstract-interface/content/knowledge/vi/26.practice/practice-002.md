# Tạo lớp trừu tượng chia sẻ kiểm tra dữ liệu và nhật ký

Khi nhiều lớp xử lý dữ liệu có cùng quy trình đầu vào, chúng thường lặp lại các bước như kiểm tra dữ liệu rỗng, chuẩn hóa chuỗi, ghi nhật ký bắt đầu/kết thúc và xử lý lỗi. Nếu mỗi lớp tự viết lại các bước này, quy tắc dễ lệch nhau: lớp này quên kiểm tra `null`, lớp khác ghi log không nhất quán, hoặc thứ tự kiểm tra và xử lý khác nhau.

Một **lớp trừu tượng** (*abstract class*) cho phép gom phần quy trình chung vào một nơi, đồng thời để lớp con định nghĩa phần xử lý riêng. Bài thực hành này xây dựng một bộ xử lý văn bản có chung bước xác thực và ghi nhật ký; các lớp con chỉ quyết định biến đổi dữ liệu đã hợp lệ như thế nào.

## 1. Xác định phần chung và phần thay đổi

Giả sử ứng dụng có hai yêu cầu: chuyển văn bản thành chữ hoa và đếm số từ. Hai yêu cầu khác nhau ở thao tác xử lý, nhưng cùng cần:

1. Ghi nhật ký khi bắt đầu.
2. Từ chối dữ liệu `null` hoặc chỉ chứa khoảng trắng.
3. Loại bỏ khoảng trắng ở hai đầu trước khi xử lý.
4. Chạy logic chuyên biệt của bộ xử lý.
5. Ghi nhật ký thành công hoặc ghi lại lỗi đầu vào.
6. Trả kết quả cho bên gọi.

Các bước này tạo thành một quy trình ổn định. Chỉ bước xử lý chuyên biệt cần thay đổi giữa các lớp. Ta sẽ đặt quy trình chung trong phương thức `process` của lớp trừu tượng và khai báo một phương thức trừu tượng `transform` để lớp con cài đặt.

Cách phân chia này giúp mọi bộ xử lý tuân theo cùng một trình tự mà không cần sao chép mã xác thực và nhật ký.

## 2. Vì sao dùng abstract class?

Lớp trừu tượng phù hợp khi nhiều lớp con cần dùng chung cả **hành vi** lẫn **trạng thái**. Lớp cơ sở có thể giữ tên bộ xử lý, triển khai logic xác thực và cung cấp phương thức ghi log. Lớp con chỉ cần triển khai điểm mở rộng.

Một interface thường mô tả hợp đồng mà lớp triển khai phải đáp ứng; interface cũng có thể có phương thức `default` và phương thức `static`, nhưng không cung cấp trạng thái instance thông thường bằng các trường instance. Abstract class phù hợp khi ta muốn chia sẻ trường, constructor, phương thức đã triển khai và các phương thức trừu tượng trong cùng một hệ phân cấp.

Không nên tạo lớp trừu tượng chỉ vì muốn tránh vài dòng lặp lại. Hãy dùng nó khi các lớp thực sự thuộc cùng một khái niệm và có một quy trình chung ổn định. Nếu chỉ cần truyền một quy tắc xử lý đơn giản, hàm lambda hoặc một interface chức năng có thể nhẹ nhàng hơn.

## 3. Thiết kế lớp cơ sở

Lớp `AbstractTextProcessor` có ba trách nhiệm:

- `process(String input)` là điểm vào công khai và điều phối quy trình chung.
- `validate(String input)` kiểm tra dữ liệu và trả về chuỗi đã loại bỏ khoảng trắng đầu/cuối.
- `transform(String input)` là điểm mở rộng để lớp con thực hiện công việc riêng.

Phương thức `process` được khai báo `final` để lớp con không thể ghi đè rồi vô tình bỏ qua xác thực hoặc ghi log. Phương thức `validate` và `log` là `private` vì chỉ lớp cơ sở cần gọi chúng. `transform` là `protected abstract` để các lớp con có thể cài đặt nhưng người gọi bên ngoài không thể trực tiếp gọi nó thông qua API công khai.

Quy trình dùng `try/catch` để ghi nhật ký khi xác thực hoặc xử lý ném `IllegalArgumentException`, rồi ném lại ngoại lệ để bên gọi vẫn biết thao tác thất bại. Việc ghi log không được âm thầm biến lỗi thành kết quả hợp lệ.

## 4. Chương trình Java 17+ hoàn chỉnh

Lưu toàn bộ mã dưới đây vào tệp `SharedValidationLoggingDemo.java`. Ví dụ đặt lớp trừu tượng, hai lớp con và lớp chạy trong cùng một tệp để dễ biên dịch; chỉ `SharedValidationLoggingDemo` là lớp `public`.

~~~java
import java.util.Locale;

abstract class AbstractTextProcessor {
    private final String name;

    protected AbstractTextProcessor(String name) {
        this.name = name;
    }

    public final String process(String input) {
        log("Bắt đầu xử lý");
        try {
            String validated = validate(input);
            String result = transform(validated);
            log("Xử lý thành công");
            return result;
        } catch (IllegalArgumentException ex) {
            log("Xử lý thất bại: " + ex.getMessage());
            throw ex;
        }
    }

    private String validate(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException(
                "Dữ liệu không được null hoặc chỉ chứa khoảng trắng"
            );
        }
        return input.strip();
    }

    protected abstract String transform(String input);

    private void log(String message) {
        System.out.println("[" + name + "] " + message);
    }
}

final class UppercaseProcessor extends AbstractTextProcessor {
    UppercaseProcessor() {
        super("UPPER");
    }

    @Override
    protected String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}

final class WordCountProcessor extends AbstractTextProcessor {
    WordCountProcessor() {
        super("WORDS");
    }

    @Override
    protected String transform(String input) {
        return "Số từ: " + input.split("\\s+").length;
    }
}

public class SharedValidationLoggingDemo {
    public static void main(String[] args) {
        AbstractTextProcessor uppercase = new UppercaseProcessor();
        AbstractTextProcessor wordCount = new WordCountProcessor();

        System.out.println("Kết quả: " + uppercase.process("  hello Java  "));
        System.out.println("Kết quả: " + wordCount.process("learn abstract class"));

        try {
            uppercase.process("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Đã bắt lỗi: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac SharedValidationLoggingDemo.java
java SharedValidationLoggingDemo
~~~

Kết quả stdout chính xác:

~~~text
[UPPER] Bắt đầu xử lý
[UPPER] Xử lý thành công
Kết quả: HELLO JAVA
[WORDS] Bắt đầu xử lý
[WORDS] Xử lý thành công
Kết quả: Số từ: 3
[UPPER] Bắt đầu xử lý
[UPPER] Xử lý thất bại: Dữ liệu không được null hoặc chỉ chứa khoảng trắng
Đã bắt lỗi: Dữ liệu không được null hoặc chỉ chứa khoảng trắng
~~~

Kết quả cho thấy hai lớp con có hành vi khác nhau nhưng cùng tuân theo trình tự xử lý. `UppercaseProcessor` chuyển chuỗi thành chữ hoa; `WordCountProcessor` đếm từ. Cả hai đều tự động dùng cùng bước kiểm tra và cùng định dạng log vì kế thừa `process` từ lớp cơ sở.

Lần gọi cuối truyền một chuỗi chỉ chứa khoảng trắng. Phương thức `validate` ném `IllegalArgumentException`; lớp cơ sở ghi log thất bại rồi ném lại ngoại lệ. Khối `catch` trong `main` xử lý ngoại lệ đó và in thông báo cuối cùng.

## 5. Hiểu luồng chạy và Template Method

Thiết kế trên là một ví dụ của mẫu **Template Method**. Phương thức `process` định nghĩa khung thuật toán: ghi log bắt đầu → xác thực → biến đổi → ghi log thành công. Bước `transform` được giao cho lớp con.

Luồng chạy thành công:

~~~text
process(input)
    |
    v
log("Bắt đầu xử lý")
    |
    v
validate(input)
    |
    v
transform(validated)
    |
    v
log("Xử lý thành công")
    |
    v
return result
~~~

Nếu xác thực hoặc `transform` ném `IllegalArgumentException`, luồng chuyển sang nhánh ghi log thất bại rồi ném lại ngoại lệ. Những ngoại lệ thuộc loại khác không bị bắt trong ví dụ này, nên sẽ truyền lên bên gọi. Đây là lựa chọn có chủ đích: chỉ những lỗi được xác định trong hợp đồng xử lý mới được ghi log theo nhánh lỗi dự kiến.

Từ khóa `final` trên `process` giúp bảo vệ khung thuật toán. Nếu không có nó, một lớp con có thể ghi đè phương thức và quên gọi `validate` hoặc bỏ qua nhật ký. Dùng `final` khi việc tuân thủ thứ tự chung là một bất biến của thiết kế; nếu lớp con thực sự cần thay đổi toàn bộ quy trình, có thể cần một kiến trúc khác.

## 6. Vai trò của constructor, mức truy cập và override

Constructor `AbstractTextProcessor(String name)` được khai báo `protected` để lớp con có thể gọi nó qua `super(...)`. Không thể khởi tạo trực tiếp một lớp trừu tượng bằng `new AbstractTextProcessor(...)`; phải tạo một lớp cụ thể triển khai phương thức trừu tượng.

Trường `name` là `private final`, nên chỉ lớp cơ sở truy cập và gán giá trị trong constructor. Điều này giữ tên logger nhất quán trong suốt vòng đời đối tượng. Trong ứng dụng thực tế, constructor cũng nên kiểm tra tên có hợp lệ hay không, ví dụ từ chối `null` hoặc chuỗi rỗng.

Các lớp con đánh dấu `transform` bằng `@Override` để trình biên dịch xác minh chữ ký ghi đè. Nếu viết sai tên phương thức hoặc sai kiểu tham số, lỗi sẽ được phát hiện lúc biên dịch. Phương thức trừu tượng không có thân; lớp cụ thể phải cung cấp phần cài đặt.

`UppercaseProcessor` dùng `Locale.ROOT` khi chuyển chữ hoa để tránh kết quả phụ thuộc locale mặc định của máy, điều hữu ích với phép chuẩn hóa mang tính kỹ thuật. Ví dụ đếm từ tách chuỗi đã chuẩn hóa bằng biểu thức chính quy `\\s+`; đây là cách đếm từ đơn giản cho văn bản phân tách bằng khoảng trắng, không phải bộ phân tích ngôn ngữ tự nhiên cho mọi ngôn ngữ.

## 7. Điều chỉnh thiết kế cho ứng dụng thật

Ví dụ dùng `System.out.println` để người học nhìn thấy kết quả ngay. Trong ứng dụng thực tế, hãy dùng hệ thống logging như SLF4J với Logback hoặc API logging phù hợp của dự án, để có cấp độ log, timestamp, thông tin tương quan và khả năng định tuyến đầu ra. Tránh ghi toàn bộ dữ liệu nhạy cảm của người dùng vào log.

Quy tắc xác thực nên phản ánh yêu cầu miền nghiệp vụ. Ví dụ, bộ xử lý mã đơn hàng có thể kiểm tra định dạng mã; bộ xử lý email có thể kiểm tra các điều kiện được ứng dụng yêu cầu. Không nên đặt quy tắc riêng của một lớp con vào lớp cơ sở nếu các lớp khác không có cùng điều kiện đó.

Cũng cần phân biệt xác thực đầu vào với xác thực kết quả. Lớp cơ sở hiện kiểm tra chuỗi đầu vào trước khi gọi `transform`. Nếu mọi kết quả đều phải tuân theo một hợp đồng chung, có thể thêm một bước kiểm tra kết quả sau `transform`; hãy làm điều đó chỉ khi có quy tắc chung rõ ràng.

Nếu cần ghi log thời lượng, có thể đo thời gian bắt đầu và kết thúc trong `process`. Nếu muốn log cả ngoại lệ ngoài `IllegalArgumentException`, cần quyết định rõ liệu phương thức có bắt `RuntimeException`, ngoại lệ có kiểm tra hay chỉ ghi log tại lớp gọi. Bắt quá rộng rồi nuốt lỗi sẽ che giấu sự cố và khiến bên gọi tưởng rằng xử lý thành công.

## 8. Lỗi thường gặp

- **Lặp lại validation trong từng lớp con:** tạo ra nguy cơ quy tắc khác nhau. Đặt quy tắc thực sự dùng chung ở lớp cơ sở.
- **Để lớp con ghi đè phương thức điều phối:** có thể phá vỡ thứ tự xác thực và log. Cân nhắc khai báo phương thức khung là `final`.
- **Gọi `transform` trước khi kiểm tra đầu vào:** dữ liệu rỗng có thể gây lỗi khó hiểu bên trong lớp con. Xác thực trước bước xử lý.
- **Ghi log rồi nuốt ngoại lệ:** làm bên gọi không biết rằng thao tác thất bại. Ghi log và ném lại lỗi, hoặc chuyển đổi sang ngoại lệ miền nghiệp vụ theo một hợp đồng rõ ràng.
- **Bắt mọi ngoại lệ mà không phân biệt:** có thể che lỗi lập trình hoặc lỗi hệ thống. Chỉ bắt những loại lỗi mà lớp có thể xử lý có ý nghĩa.
- **Đưa mọi thứ vào lớp cơ sở:** lớp cha sẽ khó bảo trì nếu chứa quá nhiều quy tắc chỉ đúng với một lớp con. Chỉ chia sẻ phần thật sự chung.
- **Dùng kế thừa chỉ để tái sử dụng một phương thức nhỏ:** có thể tạo quan hệ lớp cứng nhắc. Nếu các đối tượng không có quan hệ “là một”, hãy cân nhắc composition hoặc truyền một interface xử lý vào constructor.

## 9. Checklist khi xây dựng lớp trừu tượng dùng chung

Trước khi áp dụng mẫu này vào dự án, hãy tự kiểm tra:

1. Các lớp con có cùng một quy trình nghiệp vụ cốt lõi không?
2. Bước nào bắt buộc phải luôn chạy và nên nằm trong phương thức khung?
3. Bước nào thực sự khác nhau và nên trở thành phương thức trừu tượng hoặc hook?
4. Mức truy cập của từng trường/phương thức có giới hạn quyền truy cập phù hợp không?
5. Có nên dùng `final` để bảo vệ các bất biến của quy trình không?
6. Khi lỗi xảy ra, lớp cơ sở sẽ ghi log, chuyển đổi hay ném lại ngoại lệ nào?
7. Ví dụ có thể biên dịch, chạy và cho đầu ra dự đoán được không?

Nếu câu trả lời cho các bước chung và các bước thay đổi rõ ràng, abstract class có thể làm cho thiết kế dễ hiểu hơn, giảm trùng lặp và giữ hành vi nhất quán. Nếu ranh giới chưa rõ, hãy bắt đầu bằng hai lớp cụ thể và chỉ trích xuất lớp cơ sở sau khi đã nhận diện được quy trình chung.

## 10. Ghi nhớ

Một lớp trừu tượng hữu ích khi nhiều lớp con cần dùng chung trạng thái và một phần quy trình, nhưng vẫn có các bước xử lý riêng. Trong bài này, `process` là Template Method điều phối xác thực, biến đổi và ghi log; `transform` là điểm mở rộng của từng lớp con. Hãy bảo vệ các bước bắt buộc, kiểm tra dữ liệu trước khi xử lý, ghi log có ý nghĩa và để ngoại lệ tiếp tục truyền đến nơi có thể xử lý chúng.