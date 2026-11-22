# Enum triển khai interface và hành vi riêng của từng hằng

## 1. Mục tiêu

Trong Java, enum biểu diễn một tập hữu hạn các giá trị được xác định trước. Enum có thể triển khai một hoặc nhiều interface, vì vậy các hằng enum có thể được dùng ở nơi chương trình yêu cầu kiểu interface đó. Khi từng hằng cần hành vi khác nhau, mỗi hằng có thể có một class body riêng để override phương thức.

Ví dụ điển hình là một tập phép toán: ADD cộng, SUBTRACT trừ và MULTIPLY nhân. Chúng cùng tuân theo hợp đồng IntBinaryOperator, nhưng cách thực hiện phép toán khác nhau.

Sau bài này, bạn cần biết cách:

- Cho enum triển khai interface và hiểu hợp đồng mà interface xác định.
- Viết hành vi riêng cho từng hằng bằng constant-specific class body.
- Dùng enum qua kiểu interface để tận dụng đa hình.
- Chọn giữa hành vi riêng của từng hằng, phương thức chung của enum và dữ liệu truyền qua constructor.
- Tránh các lỗi thường gặp khi thiết kế enum có hành vi.

## 2. Enum và interface kết hợp với nhau như thế nào?

Một enum có thể khai báo interface sau tên enum:

~~~java
enum Operation implements IntBinaryOperator {
    // Các hằng enum và phần thân enum
}
~~~

Từ khóa implements có ý nghĩa như khi một class thông thường triển khai interface: kiểu enum cung cấp hợp đồng phương thức của interface. Mỗi hằng enum là một instance của kiểu enum, vì thế có thể truyền hằng đó vào phương thức nhận kiểu interface tương ứng.

Có hai cách triển khai phổ biến:

1. **Hành vi chung cho mọi hằng:** khai báo phương thức một lần trong thân enum. Các hằng dùng cùng cách xử lý, thường lấy dữ liệu riêng từ constructor.
2. **Hành vi khác nhau theo từng hằng:** đặt class body ngay sau hằng và override phương thức trong body đó. Ví dụ, ADD và MULTIPLY dùng cùng chữ ký phương thức nhưng thực hiện các phép tính khác nhau.

Nếu interface có phương thức trừu tượng mà enum không cung cấp một cách triển khai chung, mỗi hằng phải cung cấp phần triển khai phù hợp. Có thể khai báo phương thức trừu tượng trong enum để compiler buộc từng hằng thực hiện hợp đồng đó.

Một enum đã có lớp cha là java.lang.Enum; Java không cho enum kế thừa thêm một lớp tùy ý. Enum vẫn có thể triển khai nhiều interface, phân tách các hợp đồng mà nó hỗ trợ.

## 3. Ví dụ chạy được với Java 17+

Tạo file Main.java với toàn bộ nội dung sau. Ví dụ dùng IntBinaryOperator từ thư viện chuẩn java.util.function, có phương thức applyAsInt(int, int).

~~~java
import java.util.function.IntBinaryOperator;

enum Operation implements IntBinaryOperator {
    ADD("+") {
        @Override
        public int applyAsInt(int left, int right) {
            return left + right;
        }
    },
    SUBTRACT("-") {
        @Override
        public int applyAsInt(int left, int right) {
            return left - right;
        }
    },
    MULTIPLY("*") {
        @Override
        public int applyAsInt(int left, int right) {
            return left * right;
        }
    };

    private final String symbol;

    Operation(String symbol) {
        this.symbol = symbol;
    }

    public String symbol() {
        return symbol;
    }

    @Override
    public abstract int applyAsInt(int left, int right);
}

public class Main {
    public static void main(String[] args) {
        int left = 3;
        int right = 4;

        for (Operation operation : Operation.values()) {
            int result = operation.applyAsInt(left, right);
            System.out.println(
                operation.symbol() + " " + left + " and " + right + " = " + result
            );
        }

        IntBinaryOperator operation = Operation.MULTIPLY;
        System.out.println("Through interface: " + operation.applyAsInt(6, 7));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~text
javac Main.java
java Main
~~~

Kết quả stdout chính xác:

~~~text
+ 3 and 4 = 7
- 3 and 4 = -1
* 3 and 4 = 12
Through interface: 42
~~~

### Đọc ví dụ theo từng phần

- enum Operation implements IntBinaryOperator khai báo enum hỗ trợ hợp đồng phép toán hai số nguyên.
- ADD("+"), SUBTRACT("-") và MULTIPLY("*") truyền ký hiệu vào constructor chung. Trường symbol là final, nên ký hiệu được gán khi instance enum được khởi tạo và không đổi sau đó.
- Mỗi hằng có một class body và override applyAsInt. Phương thức có cùng tên, tham số và kiểu trả về, nhưng Java gọi phần triển khai gắn với hằng đang được dùng.
- Dòng khai báo public abstract int applyAsInt(...) nêu rõ hợp đồng cần được từng hằng cung cấp. Nếu thêm hằng mới mà thiếu phần override cần thiết, compiler sẽ báo lỗi.
- Vòng lặp dùng Operation.values() để duyệt các hằng theo thứ tự khai báo. Với mỗi hằng, lời gọi applyAsInt được phân phối đến cách triển khai tương ứng.
- Biến operation ở cuối có kiểu IntBinaryOperator, nhưng vẫn nhận được Operation.MULTIPLY. Khi gọi qua interface, chương trình không cần biết kiểu enum cụ thể để sử dụng hợp đồng phép toán.

Đây là ví dụ đầy đủ, có thể biên dịch trực tiếp. Không cần tạo interface riêng vì ví dụ tận dụng interface có sẵn trong JDK.

## 4. Constant-specific class body là gì?

Phần nằm trong cặp ngoặc nhọn ngay sau một hằng enum được gọi là constant-specific class body. Ví dụ:

~~~java
ADD("+") {
    @Override
    public int applyAsInt(int left, int right) {
        return left + right;
    }
}
~~~

Phần thân này định nghĩa cách hằng ADD triển khai phương thức. Những hằng có body riêng có lớp triển khai cụ thể riêng ở phía Java; chúng vẫn là các hằng của cùng enum Operation, và vẫn có thể được gán cho biến kiểu Operation hoặc interface mà enum triển khai.

Cơ chế này là đa hình. Mã gọi chỉ cần biết hợp đồng phương thức. Việc triển khai nào được chạy phụ thuộc vào instance thực tế, nên không phải viết một câu lệnh switch ở mọi nơi để kiểm tra hằng đang là ADD, SUBTRACT hay MULTIPLY.

Không bắt buộc mọi hằng đều phải có body. Nếu enum cung cấp một phương thức cụ thể dùng chung và chỉ một vài hằng cần cách xử lý khác, có thể để các hằng dùng triển khai chung và chỉ override tại những hằng cần khác biệt. Nếu phương thức là trừu tượng, mọi hằng phải có triển khai phù hợp.

## 5. Khi nào nên dùng từng cách?

| Nhu cầu | Cách thiết kế phù hợp |
| --- | --- |
| Mọi hằng thực hiện cùng thuật toán nhưng khác dữ liệu | Dùng constructor và trường final, rồi viết phương thức chung trong enum |
| Hành vi là một phần bản chất của từng hằng | Dùng constant-specific class body để override phương thức |
| Muốn các đối tượng enum được truyền vào nơi nhận một hợp đồng chung | Cho enum triển khai interface và sử dụng qua kiểu interface |
| Có nhiều interface mô tả các khả năng độc lập | Cho enum triển khai các interface cần thiết, miễn là thiết kế vẫn dễ hiểu |
| Logic thuộc về bên gọi và không phải hành vi cốt lõi của enum | Có thể dùng switch hoặc một lớp xử lý bên ngoài thay vì nhồi mọi logic vào enum |

Ví dụ, nếu chỉ khác mức phí cố định, constructor nhận mức phí thường đơn giản hơn việc viết body riêng cho từng hằng. Nếu mỗi hằng có thuật toán riêng, như cách làm tròn hoặc cách tính khác nhau, body riêng sẽ diễn đạt rõ hơn.

Đừng tạo interface chỉ để làm cho thiết kế có vẻ trừu tượng. Interface hữu ích khi cần một hợp đồng có thể được dùng độc lập với enum cụ thể, hoặc khi nhiều kiểu khác nhau cùng cung cấp khả năng đó.

## 6. Ranh giới giữa hợp đồng interface và phương thức abstract

`IntBinaryOperator` xác định hợp đồng mà mã gọi nhìn thấy: `applyAsInt(int, int)`. `Operation` vừa triển khai interface đó, vừa khai báo phương thức `abstract` trong thân enum để khẳng định rằng **mỗi hằng phải tự cung cấp thuật toán**. Trong ví dụ này, ADD cộng, SUBTRACT trừ và MULTIPLY nhân nên không có thuật toán chung phù hợp.

Nếu mọi hằng chỉ khác dữ liệu, enum có thể triển khai phương thức interface một lần bằng phương thức cụ thể, thay vì khai báo phương thức abstract và tạo body riêng cho tất cả hằng. Nếu chỉ một vài hằng khác biệt, hãy dùng phương thức chung rồi chỉ override ở các hằng cần thiết.

Điểm thiết kế chính của bài là **interface cho phép nơi gọi phụ thuộc vào một hợp đồng**, còn constant-specific class body quyết định cách thực hiện hợp đồng theo từng hằng. Bài tiếp theo phân tích riêng cách phương thức abstract khiến trình biên dịch kiểm tra trách nhiệm của từng hằng.

## 7. Những điều cần nhớ về vòng đời và trạng thái

Mỗi hằng enum là một instance duy nhất trong tiến trình chạy thông thường của ứng dụng. Các trường của hằng được dùng chung bởi mọi nơi tham chiếu đến hằng đó. Vì vậy:

- Ưu tiên trường private final cho dữ liệu cấu hình như ký hiệu, mã hoặc tên hiển thị.
- Tránh lưu dữ liệu thay đổi theo từng yêu cầu, người dùng hoặc lần gọi vào trường có thể thay đổi của enum. Trạng thái dùng chung có thể làm các luồng ảnh hưởng lẫn nhau.
- Nếu phương thức chỉ tính kết quả từ tham số, giữ nó không có tác dụng phụ sẽ dễ kiểm thử và an toàn hơn khi dùng đồng thời.
- Constructor của enum không được khai báo public hoặc protected; thông thường để constructor ở phạm vi mặc định hoặc private.
- Các hằng được khởi tạo như những instance của enum. Không tạo hằng bằng new Operation(...) từ bên ngoài.

Enum còn có các phương thức tiện ích như values(), valueOf(String) và name(). valueOf tìm hằng theo đúng tên định danh, phân biệt chữ hoa chữ thường, và ném IllegalArgumentException nếu tên không khớp. ordinal() trả về vị trí khai báo bắt đầu từ 0; không nên dùng vị trí này làm mã lưu trữ hoặc mã nghiệp vụ vì việc sắp xếp lại hằng sẽ làm thay đổi giá trị ordinal. Nếu cần mã ổn định, hãy khai báo trường riêng như code.

## 8. Lỗi thường gặp và cách xử lý

**Quên triển khai phương thức bắt buộc.** Nếu enum hoặc hằng không cung cấp triển khai cần thiết cho phương thức trừu tượng, chương trình không biên dịch. Giữ khai báo phương thức rõ ràng và kiểm tra tất cả hằng khi thêm một giá trị mới.

**Viết logic phân nhánh lặp lại ở nhiều nơi.** Nếu mọi nơi đều kiểm tra loại enum bằng switch để chọn thuật toán, hãy cân nhắc chuyển hành vi về phương thức của enum hoặc constant-specific class body. Điều này gom hành vi liên quan vào cùng một nơi.

**Dùng body riêng dù chỉ khác dữ liệu.** Nếu các hằng chỉ khác một con số hoặc một nhãn, dùng constructor thường ngắn và dễ bảo trì hơn. Body riêng phù hợp khi thuật toán thực sự khác nhau.

**Cố kế thừa một lớp khác.** Enum đã kế thừa java.lang.Enum, nên không thể thêm một lớp cha tùy ý. Nếu cần chia sẻ khả năng với kiểu khác, hãy xem xét interface hoặc một đối tượng cộng tác.

**Đưa trạng thái biến đổi vào enum singleton.** Một trường có thể thay đổi trên enum sẽ được chia sẻ giữa các nơi gọi. Hãy truyền dữ liệu theo tham số hoặc tạo đối tượng riêng cho trạng thái theo yêu cầu.

**Dùng ordinal() làm mã nghiệp vụ.** Giá trị này phụ thuộc thứ tự khai báo. Dùng trường mã rõ ràng và ổn định nếu cần lưu hoặc trao đổi dữ liệu.

**Cho rằng kiểu interface làm mất hành vi đa hình.** Khi một biến interface tham chiếu đến hằng enum, lời gọi phương thức vẫn chạy triển khai cụ thể của hằng. Đó chính là mục tiêu của interface kết hợp với hành vi riêng từng hằng.

## 9. Quy trình áp dụng

1. Xác định tập giá trị hữu hạn và đặt tên enum constants rõ nghĩa.
2. Xác định hợp đồng mà các giá trị cần cung cấp. Nếu hợp đồng có thể được dùng ở nơi khác, chọn hoặc định nghĩa một interface phù hợp.
3. Nếu các hằng chỉ khác dữ liệu, khai báo trường final, constructor và phương thức chung.
4. Nếu từng hằng có thuật toán riêng, viết constant-specific class body và override phương thức cần thiết.
5. Dùng enum qua kiểu enum khi cần các tính năng đặc thù của enum; dùng kiểu interface ở nơi chỉ cần hợp đồng.
6. Biên dịch với Java 17+, chạy ví dụ, so sánh stdout với kết quả dự kiến và thêm kiểm thử cho các trường hợp biên của thuật toán thực tế.
7. Khi thêm hằng mới, kiểm tra lại mọi phương thức trừu tượng, hành vi mặc định và các nơi chuyển đổi dữ liệu từ/đến enum.

Thiết kế tốt làm cho mỗi hằng thể hiện hành vi đúng với ý nghĩa của nó, trong khi mã sử dụng chỉ phụ thuộc vào hợp đồng ổn định.