# Kiểm thử lớp trừu tượng qua lớp con cụ thể tối thiểu

Không thể tạo trực tiếp một đối tượng từ abstract class, nhưng vẫn có thể kiểm thử các phương thức concrete đã được định nghĩa trong lớp đó. Cách thông dụng là tạo một **lớp con cụ thể tối thiểu** dành cho kiểm thử: lớp con chỉ cung cấp phần triển khai cần thiết cho các phương thức abstract, rồi bài kiểm thử gọi các phương thức kế thừa của lớp trừu tượng.

## 1. Vì sao cần lớp con cụ thể?

Một abstract class có thể chứa cả hai loại phương thức:

- **Phương thức abstract:** chỉ khai báo hợp đồng, không có thân phương thức; lớp con cụ thể phải triển khai tất cả phương thức abstract còn lại.
- **Phương thức concrete:** có thân phương thức và có thể chứa logic chung cần được kiểm thử trực tiếp.

Java không cho phép viết `new AbstractFormatter()` nếu `AbstractFormatter` là abstract. Thay vào đó, tạo một lớp con như `TestFormatter extends AbstractFormatter`. Lớp con này làm cho kiểu có thể khởi tạo và cho phép gọi logic concrete của lớp cha.

Điều quan trọng là lớp con kiểm thử nên **bổ sung phần còn thiếu tối thiểu**, không ghi đè phương thức concrete đang muốn kiểm thử. Nếu ghi đè phương thức đó, bài kiểm thử có thể vô tình kiểm tra logic của lớp con thay vì logic thực sự nằm trong lớp trừu tượng.

## 2. Mẫu triển khai

Giả sử lớp trừu tượng cung cấp một phương thức `format` hoàn chỉnh, nhưng giao việc chuyển đổi nội dung cho phương thức abstract `transform`:

```java
abstract class AbstractFormatter {
    public final String format(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        String cleaned = input.strip();
        if (cleaned.isBlank()) {
            throw new IllegalArgumentException("input must not be blank");
        }
        return "[" + transform(cleaned) + "]";
    }

    protected abstract String transform(String value);
}
```

`format` là phương thức concrete: nó kiểm tra đầu vào, loại bỏ khoảng trắng ở hai đầu và thêm dấu ngoặc. Phương thức `transform` là điểm mở rộng do lớp con cung cấp. Bài kiểm thử có thể dùng một triển khai đơn giản, dễ dự đoán để xác nhận logic của `format`.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Lưu toàn bộ mã sau vào tệp `AbstractClassTestDemo.java`. Chương trình sử dụng một lớp con nhỏ cùng các hàm assertion tự viết, nên không cần thư viện kiểm thử bên ngoài.

```java
public class AbstractClassTestDemo {
    abstract static class AbstractFormatter {
        public final String format(String input) {
            if (input == null) {
                throw new IllegalArgumentException("input must not be null");
            }
            String cleaned = input.strip();
            if (cleaned.isBlank()) {
                throw new IllegalArgumentException("input must not be blank");
            }
            return "[" + transform(cleaned) + "]";
        }

        protected abstract String transform(String value);
    }

    // Lớp con tối thiểu cho bài kiểm thử: chỉ triển khai hook abstract.
    static final class TestFormatter extends AbstractFormatter {
        @Override
        protected String transform(String value) {
            return "<" + value + ">";
        }
    }

    public static void main(String[] args) {
        AbstractFormatter formatter = new TestFormatter();

        assertEquals("[<hello>]", formatter.format("  hello  "), "trim và format");
        assertEquals("[<Java core>]", formatter.format(" Java core "), "nội dung thường");
        assertThrows(IllegalArgumentException.class,
                () -> formatter.format(null), "đầu vào null");
        assertThrows(IllegalArgumentException.class,
                () -> formatter.format(" \t "), "đầu vào chỉ có khoảng trắng");

        System.out.println("PASS: 4 checks");
    }

    private static void assertEquals(String expected, String actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected <" + expected
                    + "> but got <" + actual + ">");
        }
    }

    private static void assertThrows(
            Class<? extends RuntimeException> expectedType,
            Runnable action,
            String label) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            if (expectedType.isInstance(actual)) {
                return;
            }
            throw new AssertionError(label + ": expected "
                    + expectedType.getSimpleName() + " but got "
                    + actual.getClass().getSimpleName(), actual);
        }
        throw new AssertionError(label + ": expected "
                + expectedType.getSimpleName() + " but no exception was thrown");
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac AbstractClassTestDemo.java
java AbstractClassTestDemo
```

Stdout chính xác:

```text
PASS: 4 checks
```

Bốn kiểm tra xác nhận rằng `format` xử lý khoảng trắng đúng cách, giữ nguyên nội dung sau khi đi qua hook, và từ chối cả `null` lẫn chuỗi chỉ có khoảng trắng. Nếu bất kỳ kết quả nào sai hoặc ngoại lệ mong đợi không xuất hiện, chương trình ném `AssertionError` và kết thúc với lỗi thay vì in thông báo PASS.

## 4. Điều gì đang được kiểm thử?

Trong dòng `AbstractFormatter formatter = new TestFormatter();`, biến tham chiếu có kiểu abstract class, còn đối tượng thực tế là instance của lớp con cụ thể. Khi gọi `formatter.format(...)`, Java chạy phương thức concrete `format` được định nghĩa trong `AbstractFormatter`. Khi phương thức đó gọi `transform`, Java dispatch đến phần triển khai trong `TestFormatter`.

| Phần | Vai trò trong bài kiểm thử |
| --- | --- |
| `AbstractFormatter.format` | Logic concrete cần kiểm tra: kiểm tra null, chuẩn hóa chuỗi, kiểm tra rỗng và ghép kết quả. |
| `AbstractFormatter.transform` | Điểm mở rộng abstract mà mọi lớp con cụ thể phải triển khai. |
| `TestFormatter.transform` | Triển khai tối thiểu, dễ dự đoán để cho phép tạo đối tượng và cung cấp kết quả cho phương thức concrete. |
| `assertEquals` | So sánh giá trị thực tế với kết quả mong đợi. |
| `assertThrows` | Xác nhận một thao tác ném đúng loại ngoại lệ dự kiến. |

Kiểu của biến tham chiếu không quyết định việc khởi tạo đối tượng; lớp runtime cụ thể mới là kiểu được tạo. Nhưng việc khai báo biến theo kiểu abstract class giúp bài kiểm thử thể hiện đúng API mà người sử dụng lớp cha sẽ nhìn thấy.

## 5. Cách áp dụng trong JUnit 5

Trong dự án thực tế, nên dùng framework kiểm thử hiện có như JUnit 5 thay cho hàm assertion tự viết. Giữ nguyên ý tưởng lớp con tối thiểu, rồi tách mỗi trường hợp thành một test riêng:

```java
@Test
void formatTrimsInputAndUsesTransformHook() {
    AbstractFormatter formatter = new TestFormatter();
    assertEquals("[<hello>]", formatter.format("  hello  "));
}

@Test
void formatRejectsNull() {
    AbstractFormatter formatter = new TestFormatter();
    assertThrows(IllegalArgumentException.class,
            () -> formatter.format(null));
}
```

Đoạn trên là phần minh họa dùng bên trong một lớp test JUnit 5 đã khai báo các import phù hợp; nó không phải tệp độc lập. Với JUnit, mỗi test có tên rõ ràng, báo cáo lỗi chi tiết hơn và có thể chạy tự động trong build.

## 6. Khi lớp trừu tượng phụ thuộc vào constructor hoặc dịch vụ bên ngoài

Nếu abstract class có constructor nhận tham số, lớp con kiểm thử phải gọi constructor đó bằng `super(...)`. Hãy truyền các giá trị cấu hình nhỏ, xác định hoặc một dependency giả phù hợp. Nếu phương thức concrete gọi cơ sở dữ liệu, mạng hoặc đồng hồ hệ thống, hãy xem xét tách dependency thành interface và cung cấp fake/mock trong bài kiểm thử.

```java
abstract class AbstractRepositoryClient {
    private final String endpoint;

    protected AbstractRepositoryClient(String endpoint) {
        this.endpoint = endpoint;
    }

    public String endpointLabel() {
        return "endpoint=" + endpoint;
    }

    protected abstract boolean isAvailable();
}

final class TestRepositoryClient extends AbstractRepositoryClient {
    TestRepositoryClient() {
        super("test://local");
    }

    @Override
    protected boolean isAvailable() {
        return true;
    }
}
```

Đây là ví dụ cấu trúc minh họa, không phải phần của chương trình chạy ở mục trước. Lớp con gọi constructor của cha và cung cấp một giá trị ổn định cho hook abstract. Không cần khởi chạy dịch vụ thật nếu mục tiêu là kiểm tra logic độc lập của lớp cha.

## 7. Các lỗi thường gặp

| Lỗi | Vì sao có vấn đề | Cách xử lý |
| --- | --- | --- |
| Thử tạo `new AbstractFormatter()` | Abstract class không thể được khởi tạo trực tiếp. | Tạo lớp con cụ thể triển khai các phương thức abstract còn thiếu. |
| Lớp con kiểm thử không triển khai đủ phương thức abstract | Bản thân lớp con vẫn là abstract và không thể khởi tạo. | Triển khai tất cả phương thức abstract chưa được thực hiện ở lớp cha. |
| Ghi đè phương thức concrete đang muốn kiểm thử | Bài kiểm thử có thể chạy logic của lớp con, bỏ qua logic gốc cần kiểm tra. | Chỉ triển khai hook abstract cần thiết; giữ nguyên phương thức concrete cần kiểm thử. |
| Lớp con kiểm thử chứa nhiều logic riêng | Lỗi trong fixture có thể khiến kết quả khó diễn giải. | Giữ fixture nhỏ, dễ dự đoán; chỉ thêm hành vi cần thiết để gọi được logic của lớp cha. |
| Chỉ kiểm tra kết quả thành công | Nhánh kiểm tra đầu vào và xử lý lỗi có thể bị bỏ sót. | Kiểm tra cả đầu vào hợp lệ, biên và các trường hợp phải ném ngoại lệ. |
| Kiểm tra qua lớp con nhưng quên kiểm tra hook abstract | Có thể chưa xác minh rằng lớp con cung cấp đúng hành vi mà lớp cha cần. | Viết riêng các kiểm tra cho hợp đồng hook nếu hành vi đó thuộc phạm vi trách nhiệm của module. |
| Dùng assertion của Java mà quên bật `-ea` | Câu lệnh `assert` mặc định có thể không chạy nếu thiếu cờ bật assertions. | Dùng framework kiểm thử hoặc kiểm tra điều kiện tường minh như ví dụ trên; nếu dùng `assert`, chạy `java -ea ...`. |

## 8. Checklist khi viết test cho abstract class

- [ ] Xác định phương thức concrete nào của lớp trừu tượng cần được kiểm tra.
- [ ] Liệt kê các phương thức abstract và triển khai chúng trong lớp con test tối thiểu.
- [ ] Không ghi đè phương thức concrete đang là đối tượng kiểm thử.
- [ ] Cung cấp constructor arguments hoặc dependency giả nếu lớp cha yêu cầu.
- [ ] Kiểm tra kết quả đúng, đầu vào biên và ngoại lệ theo hợp đồng.
- [ ] Chạy test bằng lệnh build hoặc `javac`/`java` tương ứng, rồi xác nhận kết quả thực tế.
- [ ] Nếu có nhiều lớp con triển khai khác nhau, cân nhắc kiểm thử hợp đồng chung qua cùng một bộ test cho từng lớp con.

Nguyên tắc cốt lõi: hãy kiểm thử logic concrete của abstract class thông qua một lớp con cụ thể tối thiểu. Lớp con chỉ nên lấp đầy những điểm mở rộng bắt buộc, để kết quả kiểm thử phản ánh hành vi thật của lớp trừu tượng.
