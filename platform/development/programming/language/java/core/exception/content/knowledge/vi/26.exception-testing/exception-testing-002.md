# Khẳng định đúng loại ngoại lệ thay vì chỉ khẳng định có lỗi

## 1. Vì sao “có lỗi” không đủ để kết luận test đúng?

Khi một phương thức Java thất bại, exception được ném ra không chỉ là tín hiệu cho biết có vấn đề. **Loại exception** là một phần của hợp đồng giữa phương thức và caller: đầu vào không hợp lệ thường được phân biệt với trạng thái đối tượng sai, lỗi nhập/xuất, lỗi task bất đồng bộ, hủy tác vụ hoặc timeout.

Giả sử một API phân tích cổng mạng được thiết kế theo quy tắc:

- Đầu vào null hoặc blank: **IllegalArgumentException** do thiếu dữ liệu.
- Đầu vào không thể chuyển thành số nguyên: **NumberFormatException**.
- Giá trị số ngoài phạm vi từ 1 tới 65535: **IllegalArgumentException** do vượt giới hạn.
- Giá trị hợp lệ: trả về số cổng.

Test chỉ xác nhận “một exception nào đó đã xuất hiện” có thể PASS dù mã bất ngờ ném **NullPointerException**, **IndexOutOfBoundsException** hoặc một lỗi hệ thống hoàn toàn không thuộc hợp đồng. Một bug mới đã làm thay đổi bản chất thất bại, nhưng test không phát hiện.

**Điểm học tập cốt lõi:** Khi test đường lỗi, cần xác định **đúng tình huống gây lỗi**, **đúng exception class theo hợp đồng**, và khi có ý nghĩa cả **message, cause, suppressed exceptions, trạng thái dữ liệu sau thất bại**. Đừng làm test quá rộng chỉ để nó luôn PASS.

Mục tiêu không phải luôn yêu cầu *runtime class chính xác* trong mọi hệ thống. Có API cam kết cả một **họ exception**, cố ý cho phép các subtype. Điều quan trọng là **chọn assertion khớp contract**, thay vì vô tình bỏ qua sai khác giữa kiểu cha và kiểu con.

## 2. Exception hierarchy ảnh hưởng trực tiếp tới assertion

Java có hệ phân cấp class, trong đó NumberFormatException kế thừa IllegalArgumentException. Một phần cấu trúc như sau:

~~~text
Throwable
├── Error
└── Exception
    ├── IOException
    └── RuntimeException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── IllegalStateException
        └── NullPointerException
~~~

Đây chỉ là những nhánh điển hình, không phải toàn bộ class trong JDK. Do tính kế thừa:

~~~java
// Mã minh họa có thể đặt trong main.
Throwable failure = new NumberFormatException("invalid number");

System.out.println(failure instanceof IllegalArgumentException); // true
System.out.println(failure.getClass() == IllegalArgumentException.class); // false
System.out.println(failure.getClass() == NumberFormatException.class); // true
~~~

So sánh **instanceof** hoặc **Class.isInstance** chấp nhận subclass. So sánh **failure.getClass() == Expected.class** yêu cầu đúng runtime class. Nếu test dự kiến IllegalArgumentException nhưng implementation ném NumberFormatException, cách thứ nhất PASS còn cách thứ hai FAIL.

Điều đó không tự nói một trong hai đúng về nghiệp vụ: nếu API cam kết IllegalArgumentException **hoặc subclass**, assertion assignable phù hợp; nếu API cam kết đúng IllegalArgumentException cho điều kiện null, assertion exact có giá trị phát hiện regression.

## 3. Các mức độ mạnh yếu của kiểm tra exception

| Mức kiểm tra | Ví dụ | Điều nó thực sự xác minh | Điều chưa xác minh |
| --- | --- | --- | --- |
| Exception bất kỳ | Catch Throwable rồi báo PASS | Có một Throwable phát sinh | Contract lỗi đúng hay sai |
| Class cha hoặc subtype | assertThrows(RuntimeException.class, ...) | Có RuntimeException hoặc subtype | Có phải lỗi mong muốn |
| Class cụ thể hoặc subtype | assertThrows(IllegalArgumentException.class, ...) | Thuộc họ IllegalArgumentException | Exact runtime class |
| Class chính xác | assertThrowsExactly(IllegalArgumentException.class, ...) | Runtime class đúng chính xác | Message/cause/state |
| Class và ngữ nghĩa | Exact type + message/cause/suppressed/state | Phần quan trọng của hành vi lỗi | Các nhánh input chưa test |

Một test mong đợi **Exception.class**, **RuntimeException.class** hoặc đặc biệt **Throwable.class** thường quá rộng. Nó có thể chấp nhận bug mới, lỗi setup hoặc thậm chí **AssertionError** của chính test nếu người viết đặt các assertion khác bên trong lambda.

Tuy nhiên, test exact class cũng có thể quá chặt nếu API chủ ý cho phép các subtype khác nhau giữa implementation. **Độ mạnh của assertion phải được cân bằng với mức cam kết của API.**

## 4. Một API ví dụ có nhiều điều kiện thất bại

Xét phương thức sau:

~~~java
// Minh họa trong một class Java.
static int parsePort(String input) {
    if (input == null || input.isBlank()) {
        throw new IllegalArgumentException("port required");
    }
    int port = Integer.parseInt(input);
    if (port < 1 || port > 65535) {
        throw new IllegalArgumentException("port out of range");
    }
    return port;
}
~~~

Theo chính implementation này:

- **parsePort(null)** ném chính xác IllegalArgumentException với message **port required**.
- **parsePort("  ")** cũng ném IllegalArgumentException với cùng message.
- **parsePort("abc")** ném NumberFormatException từ Integer.parseInt.
- **parsePort("70000")** ném IllegalArgumentException do ngoài khoảng cho phép.
- **parsePort("8080")** trả 8080.
- Chuỗi số dài không biểu diễn được trong kiểu int gây NumberFormatException từ Integer.parseInt trước bước kiểm tra phạm vi.

Những loại này là **hợp đồng được chọn cho ví dụ**, không phải quy tắc mọi parser đều bắt buộc làm giống hệt. Khi sản phẩm đổi hợp đồng, phải cập nhật tài liệu và test có chủ đích, không chỉ sửa test để làm chúng PASS.

Nếu ai đó vô ý xóa kiểm tra null, biểu thức **input.isBlank()** có thể ném NullPointerException. Test chỉ đòi “có RuntimeException” vẫn PASS, nhưng test đòi đúng IllegalArgumentException sẽ FAIL và chỉ ra regression.

## 5. Ví dụ Java 17+ hoàn chỉnh, không phụ thuộc JUnit

Chương trình sau cung cấp hai helper đơn giản để minh họa sự khác biệt:

- **expectExact**: chỉ chấp nhận đúng runtime class bằng so sánh getClass.
- **expectAssignable**: chấp nhận class dự kiến hoặc subclass bằng Class.isInstance.

Chương trình còn xác minh message do ứng dụng tạo, exception wrapping với cause, lỗi dọn dẹp nằm trong suppressed và một đường xử lý thành công. Đây là ví dụ học tập; với dự án thật nên dùng test framework như JUnit Jupiter để có reporting và test lifecycle đầy đủ.

Lưu file **ExactExceptionTestDemo.java**:

~~~java
import java.io.IOException;

public class ExactExceptionTestDemo {
    @FunctionalInterface
    interface ThrowingAction {
        void run() throws Exception;
    }

    static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static int parsePort(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("port required");
        }
        int port = Integer.parseInt(input);
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("port out of range");
        }
        return port;
    }

    static int loadPort() {
        try {
            return parsePort("not-a-number");
        } catch (NumberFormatException original) {
            throw new IllegalStateException("config invalid", original);
        }
    }

    static void writeWithCloseFailure() throws IOException {
        try (FailingClose resource = new FailingClose()) {
            throw new IOException("write failed");
        }
    }

    static <T extends Throwable> T expectExact(
            Class<T> type, ThrowingAction action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (actual.getClass() != type) {
                throw new AssertionError("Expected " + type.getSimpleName()
                        + ", got " + actual.getClass().getSimpleName(), actual);
            }
            return type.cast(actual);
        }
        throw new AssertionError("Expected " + type.getSimpleName()
                + ", but no exception was thrown");
    }

    static <T extends Throwable> T expectAssignable(
            Class<T> type, ThrowingAction action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (!type.isInstance(actual)) {
                throw new AssertionError("Expected a subtype of "
                        + type.getSimpleName(), actual);
            }
            return type.cast(actual);
        }
        throw new AssertionError("Expected " + type.getSimpleName()
                + ", but no exception was thrown");
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        IllegalArgumentException blank = expectExact(
                IllegalArgumentException.class, () -> parsePort(null));
        require("port required".equals(blank.getMessage()), "wrong message");
        System.out.println("blank: " + blank.getClass().getSimpleName());

        NumberFormatException badNumber = expectExact(
                NumberFormatException.class, () -> parsePort("abc"));
        System.out.println("malformed: " + badNumber.getClass().getSimpleName());

        IllegalArgumentException broad = expectAssignable(
                IllegalArgumentException.class, () -> parsePort("abc"));
        System.out.println("broad assertion accepts: "
                + broad.getClass().getSimpleName());

        boolean wrongTypeDetected = false;
        try {
            expectExact(IllegalArgumentException.class, () -> parsePort("abc"));
        } catch (AssertionError mismatch) {
            wrongTypeDetected = mismatch.getMessage().equals(
                    "Expected IllegalArgumentException, got NumberFormatException");
        }
        require(wrongTypeDetected, "exact assertion must reject subclasses");
        System.out.println("exact assertion rejects wrong subtype: true");

        IllegalStateException wrapped = expectExact(
                IllegalStateException.class, ExactExceptionTestDemo::loadPort);
        require(wrapped.getCause() instanceof NumberFormatException,
                "cause must be NumberFormatException");
        System.out.println("wrapped cause: "
                + wrapped.getCause().getClass().getSimpleName());

        IOException primary = expectExact(
                IOException.class, ExactExceptionTestDemo::writeWithCloseFailure);
        require("write failed".equals(primary.getMessage()), "wrong primary");
        require(primary.getSuppressed().length == 1, "missing close error");
        require("close failed".equals(primary.getSuppressed()[0].getMessage()),
                "wrong suppressed");
        System.out.println("primary: " + primary.getMessage());
        System.out.println("suppressed: " + primary.getSuppressed()[0].getMessage());

        require(parsePort("8080") == 8080, "valid input failed");
        System.out.println("valid result: " + parsePort("8080"));
        System.out.println("ALL CHECKS PASSED");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ExactExceptionTestDemo.java
java ExactExceptionTestDemo
~~~

Đây là stdout thực tế đã được kiểm chứng khi biên dịch và chạy:

~~~text
blank: IllegalArgumentException
malformed: NumberFormatException
broad assertion accepts: NumberFormatException
exact assertion rejects wrong subtype: true
wrapped cause: NumberFormatException
primary: write failed
suppressed: close failed
valid result: 8080
ALL CHECKS PASSED
~~~

Trong helper đào tạo, **catch(Throwable)** dùng để bắt cả loại Throwable sai rồi ném AssertionError; đây **không phải** cách xử lý exception nên sử dụng để lặng lẽ phục hồi trong mã nghiệp vụ. Những kiểm tra dùng AssertionError tường minh nên hoạt động mà không cần bật tùy chọn **-ea** của Java.

## 6. Diễn giải output: assertion quá rộng nhận sai subtype

Hai dòng quan trọng:

~~~text
broad assertion accepts: NumberFormatException
exact assertion rejects wrong subtype: true
~~~

Khi người kiểm thử yêu cầu **IllegalArgumentException hoặc subclass**, NumberFormatException là hợp lệ vì kế thừa IllegalArgumentException. Nhưng khi yêu cầu chính xác **IllegalArgumentException**, cùng exception không đạt assertion.

Điều này giúp ngăn một test “cho tất cả input sai đều phải ném IllegalArgumentException” vô tình bỏ qua yêu cầu phân biệt **malformed number** với **missing input**. Mỗi lỗi có ý nghĩa khác nhau đối với caller. Ngược lại, nếu hợp đồng chỉ cam kết **IllegalArgumentException family**, exact test có thể làm code bị ràng buộc vào một lựa chọn lớp con không cần thiết.

Khi review test, câu hỏi đúng là: **Caller được phép dựa vào class nào?** Nếu caller dùng catch(NumberFormatException) riêng để báo sai định dạng, thay NumberFormatException bằng IllegalArgumentException sẽ phá hợp đồng. Nếu caller chỉ dùng catch(IllegalArgumentException), subtype có thể được phép theo thiết kế.

## 7. JUnit Jupiter assertThrows chấp nhận subclass

Trong JUnit Jupiter 5, **assertThrows(Expected.class, executable)** chấp nhận exception thuộc class Expected **hoặc subtype của nó**. Ví dụ:

~~~java
// JUnit Jupiter, cần dependency JUnit và class ví dụ trong cùng package.
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PortExceptionFamilyTest {
    @Test
    void nonNumericPortBelongsToIllegalArgumentFamily() {
        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> ExactExceptionTestDemo.parsePort("abc"));
    }
}
~~~

Test này PASS vì NumberFormatException là một IllegalArgumentException. Nó **không chứng minh** runtime class chính xác là IllegalArgumentException.

**assertThrows trả về chính Throwable được bắt** dưới dạng kiểu generic phù hợp. Có thể tiếp tục kiểm tra message, cause, suppressed và thông tin liên quan. Đừng chỉ gọi assertThrows rồi bỏ mất thông tin trong một test mà contract còn yêu cầu các thuộc tính khác.

Khi nào kiểm tra họ exception là đủ? Ví dụ một abstraction có thể dùng nhiều implementation đọc file, contract chỉ bảo đảm IOException hoặc subtype. Khi đó assertThrows(IOException.class, ...) có thể đúng hơn việc buộc class chính xác mà implementation không cam kết.

## 8. JUnit Jupiter assertThrowsExactly yêu cầu runtime class đúng

JUnit Jupiter cung cấp **assertThrowsExactly(Class<T>, Executable)** trên các phiên bản hỗ trợ. Phương thức chỉ PASS khi exception có đúng runtime class; một subclass không đủ.

Ví dụ JUnit 5 dùng class từ chương trình Java SE ở mục 5:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExactPortExceptionJUnitTest {
    @Test
    void missingInputHasExactType() {
        IllegalArgumentException failure = assertThrowsExactly(
                IllegalArgumentException.class,
                () -> ExactExceptionTestDemo.parsePort(null));
        assertEquals("port required", failure.getMessage());
    }

    @Test
    void malformedNumberHasExactType() {
        assertThrowsExactly(
                NumberFormatException.class,
                () -> ExactExceptionTestDemo.parsePort("abc"));
    }

    @Test
    void outOfRangeHasExactType() {
        IllegalArgumentException failure = assertThrowsExactly(
                IllegalArgumentException.class,
                () -> ExactExceptionTestDemo.parsePort("70000"));
        assertEquals("port out of range", failure.getMessage());
    }

    @Test
    void validPortWorks() {
        int port = assertDoesNotThrow(
                () -> ExactExceptionTestDemo.parsePort("8080"));
        assertEquals(8080, port);
    }
}
~~~

Đây là test class hợp lệ theo ngữ cảnh **một project đã cấu hình JUnit Jupiter** và chứa **ExactExceptionTestDemo** trong cùng package/classpath. Nó không phải chương trình Java SE có thể chạy chỉ bằng lệnh javac không thêm JUnit dependency. Dùng test runner của build tool dự án.

Nếu phiên bản JUnit Jupiter quá cũ chưa có **assertThrowsExactly**, có thể gọi **assertThrows** rồi kiểm tra **assertEquals(Expected.class, failure.getClass())**. Điều quan trọng là thể hiện rõ đòi hỏi exact type, không phải tên API cụ thể.

**Tránh thắt quá chặt contract:** Dùng assertThrowsExactly khi runtime class thực sự được cam kết. Nếu API chỉ công bố IOException và cho phép subtype, exact IOException có thể khiến test FAIL khi implementation vẫn hợp lệ.

## 9. Trong Java thuần: isInstance khác getClass

Không sử dụng JUnit, có thể phân biệt:

~~~java
// Mã minh họa, failure là Throwable khác null.
boolean acceptsSubtype =
        IllegalArgumentException.class.isInstance(failure);
boolean exactClass =
        failure.getClass() == IllegalArgumentException.class;
~~~

Hoặc:

~~~java
// Mã minh họa.
if (!(failure instanceof IllegalArgumentException)) {
    throw new AssertionError("Wrong exception family");
}

if (failure.getClass() != IllegalArgumentException.class) {
    throw new AssertionError("Wrong exact exception class");
}
~~~

**instanceof** đúng với subtype và không ném NullPointerException khi failure là null; khi failure null, biểu thức instanceof cho false. **failure.getClass()** yêu cầu object khác null. Trong test có framework, assertion API thường cho thông báo lỗi rõ hơn một phép so boolean tự viết.

Không dùng **failure.toString().contains("IllegalArgumentException")** để xác định class. Message và tên class có thể trùng chuỗi mà không phải đúng runtime class; use **getClass()** hoặc kiểu dữ liệu Java.

## 10. Kiểm tra checked và unchecked exceptions đúng hợp đồng

**Checked exceptions** như IOException, SQLException, InterruptedException và ExecutionException thường được compiler buộc caller catch hoặc khai báo. **Unchecked exceptions** như IllegalArgumentException, IllegalStateException, NumberFormatException và CancellationException không có yêu cầu đó.

Nhưng khi kiểm thử, phân loại checked/unchecked **không thay thế** loại lỗi chính xác. Ví dụ:

~~~java
// Mã JUnit minh họa khi api.read() có thể ném IOException.
IOException error = assertThrows(
        IOException.class,
        () -> api.read());
~~~

Assertion này sẽ chấp nhận các subtype IOException. Nếu hợp đồng yêu cầu **FileNotFoundException** chính xác, cần assertion tương ứng; nếu API chỉ cam kết IOException family, assertion như trên đủ ý nghĩa.

Đừng dùng **assertThrows(Exception.class, ...)** để gom InterruptedException (caller bị ngắt), ExecutionException (worker thất bại) và IOException (I/O lỗi) vào cùng một nhánh thành công của test. Các exception này báo những điều kiện khác nhau và cần chính sách khác nhau.

Đừng bao mọi Error vào kiểm thử phục hồi như một loại exception bình thường. Test helper có thể bắt Throwable để xác định loại, nhưng ứng dụng sản phẩm không nên mặc nhiên “khôi phục” từ bất kỳ Error nào.

## 11. Exception wrapping: cần kiểm tra cả outer type lẫn cause

Một tầng service có thể bọc lỗi thấp thành lỗi trừu tượng cấp cao:

~~~java
// Phương thức loadPort từ ví dụ.
static int loadPort() {
    try {
        return parsePort("not-a-number");
    } catch (NumberFormatException original) {
        throw new IllegalStateException("config invalid", original);
    }
}
~~~

Exception mà caller bắt được là **IllegalStateException**; exception ban đầu là **NumberFormatException** ở **getCause()**. Chỉ assert có RuntimeException không xác minh được chính sách wrap và bảo toàn thông tin lỗi.

Mẫu JUnit:

~~~java
// Bên trong @Test, với static imports JUnit tương ứng.
IllegalStateException wrapper = assertThrowsExactly(
        IllegalStateException.class,
        ExactExceptionTestDemo::loadPort);

assertEquals("config invalid", wrapper.getMessage());
assertNotNull(wrapper.getCause());
assertEquals(NumberFormatException.class,
             wrapper.getCause().getClass());
~~~

Nếu developer thay bằng **new IllegalStateException(original.getMessage())**, test outer type vẫn PASS nhưng **assertNotNull(wrapper.getCause())** FAIL, giúp phát hiện việc làm mất exception gốc.

Khi API cam kết cause là một subtype bất kỳ của IOException, thay **assertEquals(IOException.class, cause.getClass())** bằng **assertInstanceOf(IOException.class, cause)** nếu subtype được phép. Trong test nào cũng phải phân biệt **outer exception class**, **cause class**, và **thông điệp nghiệp vụ**.

## 12. Kiểm tra suppressed exceptions: lỗi chính có bị che không?

Trong try-with-resources, khi công việc chính ném exception A và close() ném exception B, Java giữ A là **primary**, B được gắn vào **A.getSuppressed()** nếu suppression được bật.

Đoạn từ chương trình chạy được:

~~~java
static void writeWithCloseFailure() throws IOException {
    try (FailingClose resource = new FailingClose()) {
        throw new IOException("write failed");
    }
}
~~~

Test mạnh hơn việc chỉ assert IOException:

~~~java
// Trong JUnit @Test với imports Assertions phù hợp.
IOException primary = assertThrowsExactly(
        IOException.class,
        ExactExceptionTestDemo::writeWithCloseFailure);

assertEquals("write failed", primary.getMessage());
assertEquals(1, primary.getSuppressed().length);
assertEquals(IOException.class,
             primary.getSuppressed()[0].getClass());
assertEquals("close failed",
             primary.getSuppressed()[0].getMessage());
~~~

Nếu đoạn sản phẩm bị sửa thành finally đóng resource một cách sơ sài, lỗi **close failed** có thể che **write failed**. Test chỉ kiểm tra IOException vẫn PASS, còn bộ kiểm tra primary message và suppressed FAIL. Đây là ví dụ điển hình về việc **đúng class nhưng sai ngữ nghĩa vẫn là bug**.

**Suppressed không phải cause:** Cause diễn đạt quan hệ nguyên nhân/wrapping; suppressed ghi lỗi phụ trong quá trình dọn dẹp. Nếu service còn wrap primary thành exception khác, suppressed có thể nằm trên **wrapper.getCause()** chứ không được sao chép lên wrapper.

## 13. Kiểm tra message: khi nào nên so chính xác?

Message do chính ứng dụng cam kết có thể là một phần hợp đồng có ích cho test:

~~~java
// Minh họa JUnit.
IllegalArgumentException error = assertThrowsExactly(
        IllegalArgumentException.class,
        () -> ExactExceptionTestDemo.parsePort(null));
assertEquals("port required", error.getMessage());
~~~

Ngược lại, một message do JDK tự tạo như chi tiết NumberFormatException có thể khác theo phiên bản JDK/đầu vào. Nếu API chỉ cam kết **NumberFormatException**, không nên biến nguyên văn message JDK thành contract trừ khi cần thiết.

Một thứ tự ưu tiên hợp lý:

1. Đúng exception type hoặc họ exception theo hợp đồng.
2. Đúng message/error code **nếu ứng dụng công bố rõ**.
3. Đúng cause/suppressed nếu cần giữ thông tin lỗi.
4. Đúng trạng thái dữ liệu hoặc resource sau thất bại.
5. Đúng object identity nếu quy tắc là ném lại cùng Throwable.

Một test chỉ dùng **failure.getMessage().contains("error")** chưa chứng minh nguồn hay loại lỗi. Nhiều lỗi khác nhau có cùng từ khóa, và message có thể null.

## 14. Khi cần kiểm tra đúng instance exception

Có API chủ động **ném lại cùng đối tượng** lỗi gốc:

~~~java
// Mã minh họa trong một class phù hợp.
static void rethrow(IOException original) throws IOException {
    throw original;
}
~~~

JUnit có thể kiểm tra:

~~~java
// Bên trong @Test; rethrow được định nghĩa thích hợp.
IOException original = new IOException("disk failure");
IOException actual = assertThrowsExactly(
        IOException.class,
        () -> rethrow(original));
assertSame(original, actual);
~~~

**assertSame** mạnh hơn so message: nó đảm bảo không tạo một IOException mới chỉ có message giống original nhưng mất cause, suppressed hoặc dấu vết ngăn xếp.

Không dùng identity assertion khi API **có quyền** wrap exception. Khi đó nên kiểm tra **wrapper.getCause() == original**. Mục tiêu là giữ đúng contract quan hệ giữa những Throwable, không cố định implementation vô cớ.

## 15. Test trạng thái sau lỗi: đúng exception vẫn chưa đủ

Một lỗi chuyển tiền có thể ném đúng IllegalStateException khi ghi vào tài khoản nhận không thành công, nhưng đã trừ tiền ở tài khoản nguồn. Test chỉ kiểm tra class vẫn PASS dù dữ liệu bị thay đổi dở.

Ví dụ phản mẫu:

~~~java
// Mã minh họa theo ngữ cảnh.
from.debit(amount);
to.credit(amount); // Có thể ném IllegalStateException.
~~~

Nếu API cam kết thất bại không làm thay đổi trạng thái, bài test cần ghi snapshot trước rồi so sánh sau khi gọi:

~~~java
// JUnit theo ngữ cảnh; Account và transfer được định nghĩa bởi ứng dụng.
long sourceBefore = from.balance();
long targetBefore = to.balance();

assertThrowsExactly(IllegalStateException.class,
        () -> transfer(from, to, amount));

assertEquals(sourceBefore, from.balance());
assertEquals(targetBefore, to.balance());
~~~

Khi code có side effect ngoài bộ nhớ (file, database, remote service), cần thêm integration test, transaction test hoặc mô hình idempotency phù hợp. **Loại exception chính xác không tự chứng minh cleanup hoặc rollback đã hoàn tất.**

## 16. Kiểm tra đường thành công và assertDoesNotThrow

Nếu mọi test đều chỉ thử input lỗi, parser có thể từ chối cả những input hợp lệ mà vẫn vượt qua tất cả bài test đó. Cần kiểm tra đường thành công riêng:

~~~java
// JUnit theo ngữ cảnh.
int port = assertDoesNotThrow(
        () -> ExactExceptionTestDemo.parsePort("8080"));
assertEquals(8080, port);
~~~

**assertDoesNotThrow** xác nhận lambda không ném exception, nhưng **assertEquals** mới xác nhận giá trị đúng. Chỉ assertDoesNotThrow có thể PASS nếu phương thức trả sai giá trị nhưng không ném lỗi.

Trong chương trình Java SE đã chạy, điều kiện **require(parsePort("8080") == 8080, ...)** xác minh cả hành vi không lỗi và kết quả. Nếu fail, nó chủ động ném AssertionError chứ không chỉ in dòng thông báo.

Một sai lầm khác: test tự bắt mọi exception rồi ghi log mà không gọi **fail()** hoặc ném AssertionError. Khi đó test runner đánh dấu PASS vì method test kết thúc bình thường. Test phải để lỗi kiểm tra thất bại thực sự đi tới runner.

## 17. Bảng kiểm thử từng loại đầu vào

Với parser cụ thể ở bài này:

| Input | Điều kiện | Kết quả dự kiến |
| --- | --- | --- |
| null | Thiếu cổng | Exact IllegalArgumentException, message port required |
| Chuỗi hai dấu cách | Blank | Exact IllegalArgumentException, message port required |
| "abc" | Không phân tích được số | Exact NumberFormatException |
| "0" | Dưới khoảng 1–65535 | Exact IllegalArgumentException, message port out of range |
| "70000" | Vượt cổng tối đa | Exact IllegalArgumentException, message port out of range |
| "8080" | Hợp lệ | Trả 8080 |
| "65535" | Biên trên hợp lệ | Trả 65535 |
| "999999999999" | Không biểu diễn được kiểu int | Exact NumberFormatException |

Nếu dùng **@ParameterizedTest** trong JUnit, mỗi lần chạy nên có expected class và tên hiển thị tương ứng. Không gom tất cả input sai vào một test duy nhất chỉ mong **RuntimeException.class**, vì nó bỏ qua các quy tắc khác biệt của từng nhánh.

Tách trường hợp cũng giúp đọc thông báo thất bại: biết ngay đầu vào nào, loại lỗi nào, message nào không khớp. Một test dài gọi nhiều assertThrows mà không đặt tên kịch bản thường khó điều tra hơn một bảng test tường minh.

## 18. Async: ExecutionException, CompletionException và lỗi gốc

Ở bài kiểm thử bất đồng bộ, exception xuất hiện tại consumer có thể là một wrapper:

- **Future.get()** khi task lỗi thường ném ExecutionException với cause là lỗi worker.
- **CompletableFuture.join()** thường ném CompletionException với cause là lỗi stage.
- **CancellationException** có thể ném trực tiếp khi Future đã canceled.
- **Future.get(timeout)** có thể ném TimeoutException vì caller chờ quá hạn, task chưa chắc lỗi.
- **InterruptedException** từ get có thể là caller bị interrupt trong khi chờ, không đồng nghĩa worker bị hủy.

Ví dụ JUnit:

~~~java
// Minh họa theo ngữ cảnh với JUnit Jupiter.
CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad payload"));

CompletionException wrapper = assertThrowsExactly(
        CompletionException.class, failed::join);
assertEquals(IllegalArgumentException.class,
             wrapper.getCause().getClass());
~~~

Nếu viết **assertThrows(RuntimeException.class, failed::join)**, test chưa phân biệt CompletionException với CancellationException hay lỗi trực tiếp khác. Nếu chuyển sang **get()**, wrapper thường là ExecutionException thay vì CompletionException — phải sửa assertion theo hợp đồng mới.

Đối với concurrency, tránh dùng Thread.sleep với thời lượng ngẫu nhiên làm cách duy nhất tạo tình huống lỗi. Dùng CountDownLatch hoặc một CompletableFuture đã hoàn tất bất thường để test deterministic.

## 19. Đừng bắt AssertionError của chính bài test

Một phản mẫu:

~~~java
// Phản mẫu JUnit, đừng dùng.
try {
    assertEquals(1, actual);
} catch (Throwable ignored) {
    // Test runner không còn nhìn thấy lỗi assertion.
}
~~~

Còn nguy hiểm hơn:

~~~java
// Phản mẫu JUnit.
assertThrows(Throwable.class, () -> {
    assertEquals(1, 2);
});
~~~

AssertionError do **assertEquals** ném cũng là **Throwable**. Vì thế assertThrows(Throwable.class, ...) có thể PASS, dù exception không đến từ code sản phẩm mà chỉ từ một assertion cố ý sai!

Để tránh false positive:

- Chỉ đặt **thao tác đang kiểm thử** trong lambda của assertThrows.
- Dùng expected class cụ thể theo hợp đồng.
- Đặt assertion về message/cause/state **sau khi** đã nhận Throwable.
- Không catch Throwable rồi bỏ qua trong method test.
- Để JUnit report AssertionError bình thường nếu kiểm tra thất bại.

Helper **expectExact** của ví dụ chỉ bắt Throwable để kiểm tra exact runtime class, và chủ động ném AssertionError khi class không đúng hoặc không có exception; không nuốt lỗi.

## 20. Lỗi trong setup/cleanup có thể làm assertion PASS giả

Xét đoạn test muốn kiểm tra việc parse một stream:

~~~java
// Phản mẫu JUnit minh họa.
assertThrows(IOException.class, () -> {
    InputStream input = openInput(); // Chính bước mở có thể gây IOException.
    parse(input);                    // Thao tác thực sự cần test.
});
~~~

Nếu **openInput()** ném IOException vì file không tồn tại, test PASS dù **parse(input)** chưa từng chạy. Lỗi có **đúng class** nhưng **không đúng nguồn**.

Cách tổ chức rõ hơn là chuẩn bị input/fixture đáng tin ở ngoài lambda, rồi chỉ đặt thao tác cần test trong lambda. Nếu hợp đồng yêu cầu cả bước open+parse, có thể giữ chúng cùng nhau nhưng cần kiểm tra thêm message/cause, kết quả theo dõi hoặc side effect để xác minh đúng giai đoạn.

Cũng cần xét trường hợp **close()** trong finally hoặc try-with-resources ném IOException cùng loại với lỗi work. Nếu chỉ assertThrows(IOException.class), test có thể PASS khi primary của work bị lỗi close che khuất. **Kiểm tra suppressed và message hoặc identity** giúp bắt nhầm nguồn lỗi.

## 21. Mutation thinking: giả sử code bị sửa sai thì test có FAIL không?

Khi đánh giá chất lượng test, thử đặt các tình huống thay đổi sai:

1. Bỏ null check: parsePort(null) ném NullPointerException.
2. Wrap lỗi parse thành IllegalArgumentException mới: parsePort("abc") không còn exact NumberFormatException.
3. Bỏ kiểm tra range: parsePort("70000") trả số 70000.
4. Catch NumberFormatException rồi trả fallback: test mong exception không còn nhận lỗi.
5. Thay try-with-resources bằng finally che primary: vẫn IOException nhưng message/suppressed khác.
6. Tạo wrapper không truyền cause: outer type vẫn đúng nhưng cause bị mất.
7. Khi Future bị hủy, consumer nhận CancellationException thay vì exceptional completion từ worker.

Các test kiểu **assertThrows(Exception.class)** có thể bỏ sót một số mutation. Test exact type + cause/suppressed + state phát hiện được nhiều thay đổi quan trọng hơn.

Có thể sử dụng mutation testing framework để đánh giá sức mạnh test trong dự án, nhưng không phải công cụ nào cũng tự sinh mọi mutation nói trên. Mục tiêu chính là **tư duy kiểm thử hợp đồng**, không chỉ chạy test cho có.

## 22. Checklist khi review một test exception

1. **Input và trạng thái kích hoạt lỗi** đã được thiết lập chính xác chưa?
2. **Có khẳng định loại exception cụ thể**, hay chỉ có catch Exception / expect any error?
3. **Muốn đúng runtime class hay cho phép subclass?** Assertion đã thể hiện đúng lựa chọn chưa?
4. **JUnit assertThrows và assertThrowsExactly** đã được phân biệt chưa?
5. **Thao tác trong lambda** có đúng giai đoạn cần test, tránh setup/cleanup gây PASS giả?
6. **AssertionError của test** có bị nuốt hoặc được coi là Throwable mong đợi không?
7. **Wrapper/cause** có được kiểm tra khi API chuyển exception sang tầng cao hơn?
8. **Suppressed exceptions** có được kiểm tra khi work và close cùng lỗi?
9. **Message/error code** có ổn định và thuộc hợp đồng hay phụ thuộc một chuỗi JDK không được cam kết?
10. **State sau thất bại** có đáp ứng invariants và cam kết rollback/atomicity không?
11. **Happy path** có được kiểm tra cùng kết quả, không chỉ test đường lỗi?
12. **Async/timeout/interruption/cancellation** có được phân biệt đúng loại không?
13. **Mỗi input và nhánh lỗi** có test riêng hoặc parameterized case rõ ràng không?
14. **Nếu implementation ném một exception khác**, bộ test có thực sự FAIL hay vô tình PASS vì assertion quá rộng?

**Kết luận:** Một test exception đáng tin không dừng ở câu “có lỗi”. Nó xác minh **đúng loại lỗi theo hợp đồng và đúng ngữ nghĩa thất bại**. Trong JUnit Jupiter, **assertThrows** chấp nhận subtype, còn **assertThrowsExactly** yêu cầu đúng runtime class. Kết hợp kiểm tra **message, cause, suppressed, identity và trạng thái** khi cần sẽ giúp phát hiện cả lỗi đổi loại exception lẫn lỗi bị che/nuốt — những vấn đề mà một assertion quá rộng khó thấy được.
