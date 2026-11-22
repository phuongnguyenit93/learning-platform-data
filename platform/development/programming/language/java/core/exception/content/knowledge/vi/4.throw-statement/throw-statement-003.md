# Phân biệt tạo ngoại lệ với ném ngoại lệ trong Java

Trong Java, **tạo một đối tượng ngoại lệ** và **ném đối tượng đó** là hai hành động khác nhau. Hai hành động thường xuất hiện chung trong câu lệnh `throw new ...` nên dễ bị nhầm là một. Phân biệt chúng giúp bạn đọc đúng luồng thực thi, hiểu tại sao có đối tượng `Exception` mà chương trình vẫn tiếp tục chạy bình thường, vì sao một đối tượng có thể được ném lại, và vì sao stack trace đôi khi ghi điểm tạo ngoại lệ thay vì dòng `throw`.

Bài học tập trung vào **lệnh `throw`**, thời điểm đối tượng ngoại lệ được tạo, cách đối tượng ấy đi vào cơ chế xử lý ngoại lệ, các ảnh hưởng đến checked exception và thông tin chẩn đoán.

## 1. Hai hành động có ý nghĩa khác nhau

| Hoạt động | Ví dụ | Kết quả tức thời |
| --- | --- | --- |
| **Tạo ngoại lệ** | `new IllegalArgumentException("Sai tuổi")` | Tạo đối tượng Java thuộc một lớp con `Throwable`; bản thân biểu thức này **không làm phương thức thoát vì ngoại lệ vừa tạo**. |
| **Giữ ngoại lệ trong biến** | `IllegalArgumentException ex = new IllegalArgumentException("Sai tuổi");` | Biến `ex` tham chiếu tới đối tượng; các câu lệnh tiếp theo vẫn chạy bình thường. |
| **Ném ngoại lệ đã có** | `throw ex;` | Kích hoạt luồng điều khiển ngoại lệ bằng đối tượng `ex`; câu lệnh `throw` kết thúc bất thường và tìm bộ xử lý phù hợp. |
| **Tạo rồi ném ngay** | `throw new IllegalArgumentException("Sai tuổi");` | Đánh giá `new` để tạo đối tượng, sau đó `throw` đối tượng vừa tạo. |
| **Khai báo khả năng ném** | `void read() throws IOException` | Mô tả hợp đồng của phương thức ở mức biên dịch; **không tự tạo và không tự ném** ngoại lệ. |

Các lớp như `IOException`, `IllegalArgumentException` hoặc `RuntimeException` cuối cùng đều là lớp con của `java.lang.Throwable`. Từ góc độ ngôn ngữ, ngoại lệ là một đối tượng có kiểu, tham chiếu, thông điệp, nguyên nhân và thông tin stack trace. Tính chất đặc biệt xuất hiện khi **đối tượng đó được ném**.

Ví dụ:

~~~java
// Đoạn minh họa trong một phương thức.
IllegalArgumentException problem =
        new IllegalArgumentException("Số tuổi âm");

System.out.println("Đã tạo ngoại lệ");
System.out.println(problem.getMessage());
System.out.println("Vẫn chạy bình thường");
~~~

Đầu ra khi đoạn trên được thực thi:

~~~text
Đã tạo ngoại lệ
Số tuổi âm
Vẫn chạy bình thường
~~~

Không có dòng `throw`, vì vậy `problem` vẫn chỉ là một đối tượng. Việc đọc `getMessage()`, truyền đối tượng sang phương thức khác, hoặc trả về đối tượng ngoại lệ cũng **không tương đương với ném** nó.

**Lưu ý về tính chính xác:** biểu thức `new` vẫn có thể không hoàn thành bình thường nếu constructor hoặc phần khởi tạo của lớp phát sinh lỗi khác; thông thường, câu `new IOException("...")` thành công sẽ chỉ tạo đối tượng. Không được suy ra rằng mọi lệnh `new` đều tuyệt đối không thể ném bất kỳ ngoại lệ nào.

## 2. Java thực hiện `throw new ...` theo thứ tự nào?

Xem câu lệnh:

~~~java
throw new IllegalStateException("Không kết nối được");
~~~

Có hai giai đoạn về mặt ngữ nghĩa:

1. **Đánh giá biểu thức bên phải `throw`:** Java khởi tạo đối tượng `IllegalStateException` với chuỗi thông điệp đã cho (và thực hiện logic constructor tương ứng).
2. **Thực hiện câu lệnh `throw`:** nếu biểu thức trả về một tham chiếu đối tượng ngoại lệ khác `null`, Java ném đối tượng đó; câu lệnh kết thúc bất thường, làm rời luồng thực thi bình thường.

Hai dòng dưới đây có hành vi ném cùng một kiểu ngoại lệ nếu quá trình tạo hoàn tất:

~~~java
// Cách 1: tạo và ném trong cùng một câu lệnh.
throw new IllegalStateException("Không kết nối được");
~~~

~~~java
// Cách 2: tạo trước rồi ném đối tượng có sẵn.
// Hai dòng nằm trong một phương thức.
IllegalStateException error =
        new IllegalStateException("Không kết nối được");
throw error;
~~~

Tuy nhiên, **thời điểm tạo** có thể khác. Ở cách 2, có thể có xử lý khác giữa `new` và `throw`; đối tượng ngoại lệ có thể đã được truyền sang nơi khác, được lưu và được ghi nhận stack trace từ trước. Một đối tượng mới ở mỗi lần `throw new` cũng khác với việc ném lại cùng một đối tượng đã tồn tại.

## 3. Chương trình Java 17+ hoàn chỉnh: tạo trước, ném sau

Tạo tệp `CreateVsThrowDemo.java`:

~~~java
public class CreateVsThrowDemo {
    static IllegalArgumentException prepare() {
        System.out.println("1. Tạo ngoại lệ");
        return new IllegalArgumentException("tuổi phải >= 0");
    }

    static void validate(int age, IllegalArgumentException prepared) {
        System.out.println("3. Bắt đầu kiểm tra");
        if (age < 0) {
            throw prepared;
        }
        System.out.println("Tuổi hợp lệ");
    }

    public static void main(String[] args) {
        IllegalArgumentException prepared = prepare();
        System.out.println("2. Đã tạo, chương trình vẫn chạy");
        try {
            validate(-1, prepared);
            System.out.println("Không in dòng này");
        } catch (IllegalArgumentException ex) {
            System.out.println("4. Đã bắt: " + ex.getMessage());
            System.out.println("5. Cùng đối tượng: " + (ex == prepared));
        }
        System.out.println("6. Kết thúc bình thường");
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CreateVsThrowDemo.java
java CreateVsThrowDemo
~~~

**Đầu ra chính xác:**

~~~text
1. Tạo ngoại lệ
2. Đã tạo, chương trình vẫn chạy
3. Bắt đầu kiểm tra
4. Đã bắt: tuổi phải >= 0
5. Cùng đối tượng: true
6. Kết thúc bình thường
~~~

Phân tích từng thời điểm:

1. `prepare()` tạo `IllegalArgumentException` và **trả về chính đối tượng ngoại lệ**. Việc trả về một `Throwable` hợp lệ về ngôn ngữ và không làm chương trình ném ngoại lệ.
2. `main()` vẫn thực thi lệnh in số 2, chứng minh chương trình chưa chuyển sang xử lý ngoại lệ.
3. `validate(-1, prepared)` bắt đầu; điều kiện `age < 0` đúng nên thực hiện `throw prepared;`.
4. `validate()` kết thúc bất thường tại `throw`. Câu `System.out.println("Tuổi hợp lệ")` không chạy; câu in `Không in dòng này` tại `main()` cũng bị bỏ qua.
5. Khối `catch (IllegalArgumentException ex)` trong `main()` nhận **đúng đối tượng đã chuẩn bị**: biểu thức `ex == prepared` cho ra `true`.
6. Vì `catch` đã xử lý và hoàn thành bình thường, chương trình tiếp tục sau cấu trúc `try/catch`.

Nếu đổi `validate(-1, prepared)` thành `validate(18, prepared)`, nhánh `throw` không chạy; ngoại lệ đã tạo vẫn chỉ là đối tượng. Điều này cho thấy **tạo đối tượng không đồng nghĩa với một lỗi thực sự đã phát sinh**.

## 4. `throw` thay đổi luồng điều khiển; `new` thông thường thì không

Các đoạn sau có ý nghĩa khác nhau:

~~~java
// A. Tạo đối tượng và bỏ tham chiếu trả về.
new IllegalArgumentException("Sai dữ liệu");
System.out.println("Vẫn đến đây");
~~~

~~~java
// B. Ném, nếu đoạn được đặt trong một phương thức.
throw new IllegalArgumentException("Sai dữ liệu");
~~~

Trường hợp A biên dịch khi đặt trong phương thức phù hợp và vẫn in `Vẫn đến đây`. Trường hợp B làm phương thức kết thúc bất thường nếu không có cơ chế xử lý ngay tại ngữ cảnh bao quanh.

Một ví dụ khác minh họa lệnh sau `throw` chỉ bị bỏ qua ở **nhánh thực sự được chọn**:

~~~java
// Đoạn minh họa trong một phương thức.
if (age < 0) {
    throw new IllegalArgumentException("Tuổi âm");
}
System.out.println("Đã qua bước kiểm tra");
~~~

Với `age < 0`, câu in không được thực thi. Với `age >= 0`, không có `throw` nên câu in sẽ chạy bình thường.

Nếu đặt một câu lệnh thông thường ngay sau một `throw` vô điều kiện trong cùng khối mà không có nhánh khác, trình biên dịch có thể báo `unreachable statement`:

~~~java
// Minh họa sai; KHÔNG biên dịch khi đặt trong phương thức.
throw new IllegalArgumentException("Lỗi");
System.out.println("Không thể tới đây");
~~~

Khi ném ngoại lệ, Java tìm `catch` phù hợp trong những khối `try` bao quanh động. Nếu không có, ngoại lệ tiếp tục đi lên các lời gọi đang hoạt động. Nhưng đây là hệ quả của **`throw`**, không phải của việc tạo đối tượng.

## 5. `throw` phải nhận kiểu gì?

Theo Java Language Specification, toán hạng của câu lệnh `throw` phải là một biểu thức có kiểu tham chiếu tương thích với `Throwable`; trường hợp ném tham chiếu `null` được giải quyết theo quy tắc runtime riêng.

Ví dụ hợp lệ:

~~~java
throw new IllegalArgumentException("Không hợp lệ");
~~~

~~~java
// Đoạn minh họa trong phương thức có biến Throwable problem.
throw problem;
~~~

Trường hợp không hợp lệ:

~~~java
// Không biên dịch: String không phải một Throwable.
throw new String("Lỗi");
~~~

Bạn không thể dùng `throw 5;`, `throw "Lỗi";` hoặc `throw new Object();` để kích hoạt xử lý ngoại lệ. Phải ném đối tượng thuộc một lớp con của `Throwable`, ví dụ một lớp ngoại lệ tùy chỉnh kế thừa `Exception` hoặc `RuntimeException`.

**Khi biểu thức của `throw` có giá trị `null`:**

~~~java
// Đoạn minh họa trong một phương thức.
RuntimeException problem = null;
throw problem;
~~~

Đoạn trên **biên dịch**; lúc chạy, thực hiện `throw` với tham chiếu `null` gây `NullPointerException`. Đây không phải “không ném gì”; cũng không phải chương trình rơi qua dòng `throw`.

Để kiểm soát lỗi rõ ràng, bạn nên bảo đảm tham chiếu cần ném khác `null`, hoặc trực tiếp tạo ngoại lệ phù hợp với tình huống.

## 6. Đừng nhầm `throw` với `throws`

Hai từ khóa chỉ khác một chữ cái nhưng phục vụ hai mục đích:

- `throw expression;` là **câu lệnh thực thi**: ném một đối tượng ngoại lệ được đánh giá từ biểu thức.
- `throws Type1, Type2` là **khai báo trong chữ ký phương thức/constructor**: mô tả các loại ngoại lệ kiểm tra (checked) mà phương thức có thể để thoát ra, đồng thời có thể liệt kê unchecked nếu muốn.

Ví dụ hợp lệ về checked exception:

~~~java
import java.io.IOException;

// Đoạn minh họa đặt bên trong một lớp.
static void failRead() throws IOException {
    IOException failure = new IOException("Không đọc được tệp");
    throw failure;
}
~~~

Ở đây:

1. `new IOException(...)` chỉ tạo đối tượng `IOException`, dù bản thân kiểu của nó là checked exception.
2. `throw failure;` **ném checked exception**, nên phương thức phải bắt hoặc khai báo `IOException` (hoặc kiểu cha thích hợp).
3. `throws IOException` trên chữ ký thông báo yêu cầu đó cho người gọi. Người gọi `failRead()` lại phải bắt hoặc khai báo khi cần.

Nhưng phương thức sau **biên dịch được mà không cần `throws IOException`**:

~~~java
import java.io.IOException;

// Đoạn minh họa đặt bên trong một lớp.
static IOException prepareFailure() {
    return new IOException("Không đọc được tệp");
}
~~~

Bởi vì nó **trả về một đối tượng** `IOException`, không ném đối tượng ấy. Kiểu trả về `IOException` không có nghĩa phương thức sẽ kết thúc bất thường.

Ví dụ người gọi:

~~~java
// Đoạn minh họa trong một phương thức.
IOException prepared = prepareFailure();
System.out.println(prepared.getMessage()); // Chỉ đọc thông điệp.
~~~

Người gọi không phải khai báo `throws IOException` chỉ vì nhận một đối tượng có lớp là checked exception. Quy tắc bắt hoặc khai báo áp dụng cho **khả năng ngoại lệ checked thoát ra**, không phải cho mọi nơi khởi tạo biến có kiểu `Exception`.

## 7. Bắt và ném lại: cùng đối tượng hay đối tượng mới?

`catch` nhận tham chiếu đến ngoại lệ đã được ném. Bạn có thể:

1. Xử lý và kết thúc khối `catch` bình thường — quá trình lan truyền của ngoại lệ đó kết thúc.
2. Ném lại chính đối tượng với `throw ex;`.
3. Tạo ngoại lệ mới và ném bằng `throw new ...;`, thường giữ ngoại lệ cũ làm **cause**.

Ví dụ cùng đối tượng:

~~~java
// Đoạn minh họa trong phương thức tương thích với unchecked exception.
try {
    performTask();
} catch (IllegalStateException ex) {
    System.err.println("Gặp sự cố trong performTask");
    throw ex; // Ném lại cùng tham chiếu, không tạo đối tượng mới.
}
~~~

Ném lại bằng `throw ex` không tự thêm một lớp nguyên nhân `Caused by`; đó vẫn là cùng một đối tượng `Throwable`. Nếu tầng trên bắt lại, đối chiếu tham chiếu bằng `==` vẫn có thể cho kết quả `true`.

Ngược lại:

~~~java
// Đoạn minh họa trong phương thức tương thích với unchecked exception.
try {
    performTask();
} catch (IllegalStateException ex) {
    throw new IllegalStateException("Tác vụ không hoàn thành", ex);
}
~~~

Câu `new IllegalStateException(..., ex)` tạo một **đối tượng khác** và thiết lập `ex` làm nguyên nhân. Câu `throw` ném đối tượng mới này; `getCause()` giúp truy đến ngoại lệ cũ. Khi ghi stack trace, thường có phần `Caused by:` thể hiện nguyên nhân gốc.

Không nên cứ bắt một ngoại lệ rồi tạo mới mà **không truyền `cause`**, vì như vậy dễ làm mất đường dẫn chẩn đoán tới lỗi ban đầu.

Với checked exception, quy tắc biên dịch vẫn áp dụng khi ném lại: phương thức phải khai báo hoặc xử lý các loại checked exception có thể thoát ra. Java có **precise rethrow analysis** trong một số trường hợp `catch` từ Java 7, cho phép compiler suy luận kiểu checked được ném lại chính xác hơn; điều này không thay đổi khác biệt nền tảng giữa tạo và ném.

## 8. Stack trace gắn với thời điểm nào?

Một điểm tinh tế: với các constructor `Throwable` thông thường, **stack trace được ghi nhận khi đối tượng ngoại lệ được tạo**, không phải tự động chụp lại tại từng dòng `throw`. Vì vậy nếu bạn tạo ở phương thức A và sau đó ném ở phương thức B, stack trace mặc định có thể bắt đầu bằng A.

Chương trình độc lập `TraceCreationDemo.java`:

~~~java
public class TraceCreationDemo {
    static IllegalStateException createProblem() {
        return new IllegalStateException("sự cố");
    }

    static void throwProblem(IllegalStateException problem) {
        throw problem;
    }

    public static void main(String[] args) {
        IllegalStateException problem = createProblem();
        try {
            throwProblem(problem);
        } catch (IllegalStateException ex) {
            System.out.println("Cùng đối tượng: " + (problem == ex));
            System.out.println("Frame đầu: " + ex.getStackTrace()[0].getMethodName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 TraceCreationDemo.java
java TraceCreationDemo
~~~

Stdout với đối tượng `IllegalStateException` thông thường:

~~~text
Cùng đối tượng: true
Frame đầu: createProblem
~~~

**Giải thích:** `createProblem()` đã xây dựng ngoại lệ và ghi nhận stack trace; `throwProblem()` chỉ ném tham chiếu có sẵn. JVM không tự thay thế trace bằng đường gọi đến `throwProblem()` mỗi lần đối tượng được ném.

Các trường hợp cần biết:

- `throw new IllegalStateException(...)` thực hiện tạo gần sát điểm ném nên vị trí đầu trace thường trùng với câu lệnh `throw new`.
- `throw oldException;` có thể giữ trace từ lúc `oldException` được tạo trước đó. Việc dùng một ngoại lệ tái sử dụng để ném nhiều lần thường tạo thông tin vị trí lỗi thiếu chính xác cho những lần sau.
- `Throwable.fillInStackTrace()` có thể cập nhật thông tin trace theo ngăn xếp hiện tại; đây là thao tác tường minh, không phải điều xảy ra mặc định ở mỗi `throw`.
- Một số loại `Throwable` tùy chỉnh có thể vô hiệu hóa writable stack trace, hoặc ứng dụng chủ động thay đổi stack trace qua API. Vì vậy ví dụ về phần tử đầu trong `getStackTrace()` nói trên giả định đối tượng Java thông thường với stack trace khả dụng.

Trong thiết kế ứng dụng, thường nên **tạo ngoại lệ khi thực sự phát hiện lỗi**, để trace phản ánh vị trí có ý nghĩa. Chỉ tách riêng khâu tạo và ném khi có lý do rõ ràng; đừng tạo sẵn một ngoại lệ dùng chung cho nhiều yêu cầu hay luồng rồi mong stack trace thể hiện đúng từng sự kiện lỗi.

## 9. Tại sao đôi khi chỉ cần tạo, không nên ném?

Một ngoại lệ có thể được tạo hoặc lưu trữ như một đối tượng dữ liệu trong các tình huống chuyên biệt:

- Tầng code chuẩn bị ngữ cảnh cho lỗi rồi chuyển đối tượng cho tầng khác lựa chọn có ném hay không.
- Một kết quả bất đồng bộ có thể **lưu một đối tượng ngoại lệ** dưới dạng nguyên nhân thất bại. Bên nhận quan sát trạng thái thất bại hoặc một ngoại lệ bọc khi lấy kết quả; không nên đánh đồng thời điểm lưu đối tượng với thời điểm một luồng khác ném ngoại lệ.
- Một API chẩn đoán có thể giữ `Throwable` để ghi lại ngăn xếp tại thời điểm nhất định, nhưng việc tạo như vậy có chi phí và phải có mục đích.

Dù hợp lệ, việc `return new IOException(...)` thay cho ném ngoại lệ thường **không phải phong cách xử lý lỗi Java thông thường**. Nó có thể làm người gọi nhầm rằng thao tác đã thành công. Nếu API có ý định trả lỗi như dữ liệu, hợp đồng nên nói rõ kiểu kết quả và cách sử dụng, thay vì dùng `Exception` lẫn với dữ liệu thành công.

Ở chiều ngược lại, một phương thức khai báo `throws` cũng không nhất thiết ném ngoại lệ trong mỗi lượt gọi. `throws` cho biết khả năng, còn lệnh `throw` chỉ chạy khi đường thực thi thật sự đi đến đó.

## 10. Ngoại lệ tùy chỉnh: constructor không thay thế cho `throw`

Có thể tự định nghĩa lớp ngoại lệ bằng cách kế thừa `Exception` (checked) hoặc `RuntimeException` (unchecked):

~~~java
// Đoạn minh họa là lớp Java độc lập.
class InvalidOrderException extends Exception {
    InvalidOrderException(String message) {
        super(message);
    }
}
~~~

Hai thao tác sau có kết quả khác nhau:

~~~java
// Đoạn minh họa trong một phương thức.
InvalidOrderException problem = new InvalidOrderException("Đơn hàng trống");
// Chỉ tạo và lưu; không phát sinh luồng xử lý ngoại lệ.
~~~

~~~java
// Đoạn minh họa trong phương thức có throws InvalidOrderException.
throw new InvalidOrderException("Đơn hàng trống");
// Phương thức kết thúc bất thường và người gọi phải bắt hoặc khai báo.
~~~

Constructor `InvalidOrderException(String)` chỉ chuẩn bị trạng thái đối tượng và gọi `super(message)`. Bản thân `extends Exception` không khiến câu `new InvalidOrderException(...)` tự động bị ném. Cũng không cần tự thêm `throw this` trong constructor; đó không phải cách đúng để định nghĩa lớp ngoại lệ.

Đặt tên ngoại lệ theo thất bại có ý nghĩa và sử dụng checked/unchecked nhất quán với hợp đồng API. Bất kể loại checked hay unchecked, việc **khởi tạo thành công** vẫn khác với việc **ném**.

## 11. Lưu ý khi thiết kế và chẩn đoán lỗi

| Sai lầm phổ biến | Hệ quả | Cách hiểu/sửa |
| --- | --- | --- |
| Chỉ viết `new Exception("Lỗi");` và tin rằng chương trình báo lỗi | Đối tượng được tạo rồi có thể bị bỏ qua; luồng chạy tiếp. | Dùng `throw new ...` khi cần kích hoạt luồng ngoại lệ. |
| Dùng `return new Exception(...)` và tin rằng người gọi phải `catch` | Trả về giá trị thường không đòi `catch`. | Chỉ trả lỗi như dữ liệu khi API quy định rõ; nếu là checked failure, dùng `throw`/`throws`. |
| Nhầm `throw` với `throws` | Khai báo chữ ký nhưng mong runtime tự ném. | `throw` là câu lệnh, `throws` là khai báo. |
| Ném `String`, `Object` hoặc kiểu số | Lỗi biên dịch do không tương thích `Throwable`. | Dùng đối tượng thuộc lớp con của `Throwable`. |
| `throw null` và nghĩ là bỏ qua ném | Gây `NullPointerException` tại runtime. | Bảo đảm tham chiếu khác `null` hoặc tạo lỗi phù hợp. |
| Dùng chung một ngoại lệ tạo từ trước rồi ném nhiều lần | Trace có thể chỉ tới thời điểm tạo, gây khó tìm vị trí lần thất bại mới. | Thông thường tạo ngoại lệ mới tại điểm lỗi xảy ra. |
| Bắt lỗi cũ rồi `throw new ...` nhưng bỏ `cause` | Làm mất quan hệ nguyên nhân cần thiết để debug. | Dùng constructor `(message, cause)` khi bọc. |
| Ghi log rồi `throw` ở mọi tầng | Một lỗi có thể tạo nhiều log trùng và nhiễu. | Chuyển tiếp hợp lý, ghi log tại ranh giới giám sát phù hợp. |
| Đưa câu lệnh thường ngay sau `throw` vô điều kiện | Có thể nhận lỗi `unreachable statement`. | Tổ chức lại nhánh điều kiện và đường trả về. |

Một lưu ý về hiệu năng: tạo một đối tượng `Throwable` thông thường có thể phải thu thập stack trace nên **không nên lạm dụng chỉ để điều khiển luồng bình thường**. Khi đầu vào không hợp lệ thật sự là tình huống thất bại theo hợp đồng, ném ngoại lệ rõ ràng là hợp lý; với các kết quả có thể dự đoán và diễn ra thường xuyên, cân nhắc kiểu trả về hoặc điều kiện kiểm tra phù hợp.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Với đoạn `IOException e = new IOException("x");`, phương thức có bắt buộc ghi `throws IOException` không?

**Trả lời:** Không, nếu chỉ tạo đối tượng và không có lời gọi nào khác ném checked exception. Việc tạo đối tượng `IOException` không đồng nghĩa với ném nó.

**Câu 2.** `throw e;` và `throw new IOException("x");` có luôn giống hệt nhau không?

**Trả lời:** Cả hai đều ném một đối tượng nếu thành công, nhưng câu đầu ném lại đối tượng đang được tham chiếu, câu sau tạo đối tượng mới trước khi ném. Khác nhau về danh tính đối tượng, thời điểm tạo và thông tin stack trace.

**Câu 3.** Ngoại lệ được tạo ở `make()`, sau đó ném ở `send()`. Stack trace mặc định có thể bắt đầu tại đâu?

**Trả lời:** Với `Throwable` thông thường, tại `make()` — nơi đối tượng được tạo, trừ khi trace được làm mới hoặc thay đổi.

**Câu 4.** Nếu `throw new IllegalArgumentException(...)` chạy, câu lệnh bình thường ngay sau nó trong cùng nhánh có chạy không?

**Trả lời:** Không. `throw` kết thúc bất thường, trừ khi trình tự điều khiển đã xử lý ở một ngữ cảnh bao quanh phù hợp và chương trình tiếp tục từ điểm sau cấu trúc xử lý.

**Câu 5.** Ném tham chiếu `null` sẽ làm gì?

**Trả lời:** `throw null` gây `NullPointerException` tại runtime.

**Câu 6.** `catch (Exception ex) { throw ex; }` có tạo ngoại lệ mới không?

**Trả lời:** Không; đó là cùng đối tượng `ex`. Với checked exception, compiler còn áp dụng các quy tắc về `throws` và có thể có phân tích ném lại chính xác.

**Câu 7.** Muốn tạo ngữ cảnh lỗi mới nhưng giữ lỗi gốc, nên viết gì?

**Trả lời:** Dùng constructor nhận nguyên nhân, ví dụ `throw new IllegalStateException("Nạp cấu hình thất bại", ex);`.

## Tài liệu tham khảo

- [Java Language Specification 17, §14.18 — The `throw` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): biểu thức được ném, ngữ nghĩa ném `null`, kết thúc bất thường.
- [Java Language Specification 17, §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exception và quy tắc bắt hoặc khai báo.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): ngữ nghĩa tạo đối tượng bằng `new`.
- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): constructor, cause, stack trace, `fillInStackTrace()`.
- [Java SE 17 API — `IllegalArgumentException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html): ngoại lệ unchecked minh họa.

**Điểm cần nhớ:** `new SomeException(...)` tạo một đối tượng mang thông tin lỗi; `throw exception;` mới dùng đối tượng đó để chuyển luồng điều khiển sang cơ chế xử lý ngoại lệ. `throw new SomeException(...);` kết hợp cả hai, trong khi `throws SomeException` chỉ khai báo hợp đồng phương thức.
