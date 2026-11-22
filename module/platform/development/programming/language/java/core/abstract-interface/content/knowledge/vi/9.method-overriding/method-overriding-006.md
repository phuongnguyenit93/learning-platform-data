# Unchecked exception và trách nhiệm của mã gọi khi ghi đè phương thức trong Java

Unchecked exception gồm RuntimeException và các lớp con của nó, cùng Error và các lớp con của nó. Compiler không buộc caller phải catch hoặc khai báo chúng. Một override có thể ném unchecked exception mới dù phương thức cha không có mệnh đề throws; điều đó vẫn có thể làm thay đổi hành vi mà người dùng API quan sát được.

## 1. Không khai báo throws không có nghĩa là không thể thất bại

~~~java
interface TextProcessor {
    String process(String input);
}

final class UpperProcessor implements TextProcessor {
    @Override
    public String process(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        if (input.isBlank()) {
            throw new IllegalArgumentException("input must not be blank");
        }
        return input.strip().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

IllegalArgumentException là unchecked, nên chữ ký không cần ghi throws. Tuy vậy, lời gọi với null hoặc chuỗi trắng vẫn có thể ném exception tại runtime. throws X là khai báo; throw new X(...) là câu lệnh thực sự ném đối tượng.

## 2. Ví dụ caller xử lý lỗi đầu vào

~~~java
public class UncheckedDemo {
    public static void main(String[] args) {
        TextProcessor processor = new UpperProcessor();
        show(processor, "  Java  ");
        show(processor, "   ");
        show(processor, null);
    }

    private static void show(TextProcessor processor, String input) {
        try {
            System.out.println("Result: " + processor.process(input));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
~~~

Khi ghép với interface và implementation ở mục 1, chương trình in:

~~~text
Result: JAVA
Rejected: input must not be blank
Rejected: input must not be null
~~~

Caller bắt đúng lỗi đầu vào tại nơi có thể trình bày thông báo và tiếp tục xử lý. Nếu không có catch, unchecked exception có thể lan truyền lên stack và kết thúc luồng khi không có handler phù hợp.

## 3. Compiler không kiểm tra toàn bộ hợp đồng hành vi

Java cho phép override thêm unchecked exception, nhưng khả năng thay thế kiểu vẫn quan trọng. Nếu lớp cha cam kết thao tác thành công với mọi đầu vào hợp lệ, lớp con tự ý ném IllegalStateException với các đầu vào đó có thể phá hợp đồng dù vẫn biên dịch.

Bên viết implementation nên:

- Nêu rõ tiền điều kiện như non-null, giá trị dương hoặc trạng thái cần thiết.
- Dùng loại exception có ý nghĩa: IllegalArgumentException cho đối số sai, IllegalStateException cho trạng thái không phù hợp, hoặc exception tùy chỉnh khi thực sự cần.
- Tránh thay đổi trạng thái một phần trước khi báo lỗi nếu có thể; Java không tự động rollback mọi thay đổi khi có RuntimeException.
- Giữ nguyên cause khi chuyển exception để không mất thông tin chẩn đoán.

## 4. Trách nhiệm của caller

Caller không cần bọc mọi lời gọi trong catch RuntimeException. Thay vào đó:

- Xác thực dữ liệu do người dùng cung cấp khi có thể đưa ra thông báo tốt hơn.
- Bắt loại exception dự kiến tại ranh giới có cách xử lý cụ thể.
- Để lỗi bất ngờ lan truyền tới cơ chế xử lý phù hợp thay vì âm thầm nuốt lỗi.
- Dọn dẹp tài nguyên bằng try-with-resources hoặc finally khi cần; không giả định exception tự đóng mọi tài nguyên hay rollback transaction.

Không nên bắt Throwable hoặc Error như lỗi đầu vào thông thường. Việc một exception đã được bắt cũng không bảo đảm thao tác chưa tạo tác dụng phụ.

## 5. Phân biệt với checked exception

Quy tắc khai báo checked exception khi override được trình bày ở bài trước: lớp con không được mở rộng checked exceptions mà hợp đồng cha không cho phép. Với unchecked exceptions, compiler không áp dụng giới hạn throws tương tự, nên JavaDoc và hợp đồng hành vi càng quan trọng.

**Ghi nhớ:** compiler xác nhận luật kiểu và checked exceptions; nó không chứng minh mọi implementation tuân thủ ý nghĩa nghiệp vụ của kiểu cha. Người viết API phải mô tả lỗi có thể dự đoán, còn caller cần xử lý các tình huống thất bại ở đúng ranh giới.