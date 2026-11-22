# Kiểm thử bất biến, null, exception và hành vi biên

## Mục tiêu

Kiểm thử tốt cần xác minh cả kết quả đúng và cách chương trình phản ứng khi dữ liệu không hợp lệ hoặc rơi vào trường hợp đặc biệt. Với Java, bốn nhóm cần chú ý là bất biến của đối tượng, đầu vào `null`, ngoại lệ và giá trị biên.

Bài này giới thiệu cách xác định hợp đồng cần kiểm tra, thiết kế các trường hợp kiểm thử có ý nghĩa, và dùng một ví dụ Java 17 chạy độc lập để minh họa. Cuối bài có mẫu tương đương bằng JUnit 5 để áp dụng trong dự án thực tế.

## 1. Bắt đầu từ hợp đồng của chương trình

Trước khi viết test, hãy mô tả điều gì phải luôn đúng đối với đối tượng hoặc phương thức. Hợp đồng có thể bao gồm:

- **Điều kiện trước (precondition):** những điều kiện đầu vào phải đáp ứng, chẳng hạn tham số không được `null` hoặc một khoảng số phải có cận dưới không lớn hơn cận trên.
- **Bất biến (invariant):** điều kiện phải đúng đối với trạng thái hợp lệ của đối tượng trong suốt vòng đời công khai của nó.
- **Điều kiện sau (postcondition):** kết quả hoặc trạng thái cần đạt sau khi phương thức hoàn tất thành công.
- **Hành vi lỗi:** loại ngoại lệ được ném ra khi điều kiện đầu vào không được đáp ứng, hoặc cách lỗi được báo cáo theo hợp đồng.

Một test hữu ích kiểm tra hành vi mà người gọi có thể quan sát. Test không nên phụ thuộc vào chi tiết triển khai riêng tư nếu chi tiết đó không thuộc hợp đồng công khai.

### Bố cục Arrange–Act–Assert

Nên tách test thành ba phần:

1. **Arrange:** tạo dữ liệu và đối tượng cần kiểm tra.
2. **Act:** gọi phương thức hoặc thực hiện hành động.
3. **Assert:** xác nhận kết quả, trạng thái hoặc ngoại lệ mong đợi.

Tách ba phần giúp test dễ đọc và khi thất bại, dễ xác định điều kiện nào không được đáp ứng. Mỗi test nên tập trung vào một hành vi chính; các kiểm tra liên quan có thể được nhóm bằng công cụ như `assertAll` trong JUnit.

## 2. Kiểm thử bất biến (invariant)

Bất biến là điều kiện phải luôn đúng đối với mọi trạng thái hợp lệ của đối tượng. Nó thường được bảo vệ trong constructor và các phương thức làm thay đổi trạng thái. Với đối tượng bất biến, constructor là điểm quan trọng vì trạng thái được thiết lập một lần và không thay đổi sau đó.

Ví dụ, một đối tượng biểu diễn khoảng số nguyên có thể yêu cầu:

`min <= max`

Nếu `min` lớn hơn `max`, đối tượng không nên được tạo thành công. Có thể kiểm tra bất biến bằng hai nhóm test:

- **Trường hợp hợp lệ:** cận dưới bằng cận trên, hoặc cận dưới nhỏ hơn cận trên.
- **Trường hợp không hợp lệ:** cận dưới lớn hơn cận trên và constructor phải ném ngoại lệ theo hợp đồng.

Khi đối tượng có nhiều phương thức thay đổi trạng thái, kiểm tra bất biến sau mỗi loại thao tác công khai có thể phát hiện lỗi làm hỏng trạng thái. Không cần kiểm tra lại mọi chi tiết nội bộ; hãy xác minh những điều kiện ảnh hưởng đến hành vi người gọi.

## 3. Kiểm thử đầu vào null

Trong Java, biến tham chiếu có thể mang giá trị `null`. Mỗi API cần quy định rõ `null` có hợp lệ hay không:

- Nếu `null` là đầu vào hợp lệ, test kết quả và trạng thái tương ứng.
- Nếu `null` bị cấm, test xác nhận phương thức từ chối nó theo hợp đồng, thường bằng `NullPointerException`.
- Nếu tham số tùy chọn được biểu diễn bằng `Optional`, kiểm tra cả trường hợp `Optional.empty()` và trường hợp có giá trị khi cả hai đều thuộc hợp đồng.

`Objects.requireNonNull(value, "value")` là cách phổ biến để từ chối `null` với lỗi rõ ràng. Không nên mặc định mọi tham số đều phải từ chối `null`; quyết định phải xuất phát từ hợp đồng của API. Cũng không nên bắt `NullPointerException` rồi bỏ qua, vì điều đó có thể che lỗi lập trình.

Test `null` nên gọi trực tiếp phương thức công khai với `null` và xác nhận hành vi được cam kết. Nếu chỉ kiểm tra rằng chương trình không bị crash ở một đường đi thông thường, test có thể bỏ sót hợp đồng xử lý đầu vào không hợp lệ.

## 4. Kiểm thử exception

Khi một thao tác không thể hoàn tất, Java có thể ném ngoại lệ. Test nên xác nhận ngoại lệ đúng loại được ném ở đúng tình huống:

- Dữ liệu không hợp lệ thường dùng `IllegalArgumentException` hoặc loại cụ thể hơn theo hợp đồng.
- Tham chiếu `null` bị cấm thường dẫn đến `NullPointerException`.
- Lỗi I/O có thể được biểu diễn bằng `IOException` hoặc một subtype phù hợp.
- Trạng thái đối tượng không cho phép thao tác có thể được biểu diễn bằng `IllegalStateException`, nếu đó là hợp đồng đã chọn.

Đừng chỉ kiểm tra rằng “có một ngoại lệ bất kỳ”. Một test bắt quá rộng như `catch (Exception)` có thể vô tình chấp nhận lỗi không liên quan. Trong JUnit, `assertThrows(ExpectedType.class, executable)` xác nhận loại ngoại lệ mong đợi và trả về ngoại lệ để kiểm tra thêm nếu cần.

Chỉ kiểm tra thông điệp ngoại lệ khi thông điệp đó là một phần của hợp đồng hoặc có giá trị thực sự cho người gọi. Nếu thông điệp chỉ là chi tiết nội bộ, kiểm tra loại ngoại lệ sẽ bền vững hơn khi mã được bảo trì. Với checked exception, chữ ký phương thức và cách gọi test cũng phải tuân theo quy tắc Java.

Ngoài ra, test cần phân biệt hai trường hợp: ngoại lệ được ném ra như dự kiến và phương thức hoàn tất bình thường. Nếu không có ngoại lệ nhưng test yêu cầu phải có, test phải thất bại.

## 5. Kiểm thử hành vi biên (boundary values)

Lỗi thường xuất hiện tại ranh giới của điều kiện, vì vậy đừng chỉ kiểm thử một giá trị ở giữa miền hợp lệ. Với một khoảng đóng từ `min` đến `max`, các giá trị đáng chú ý là:

- `min`: giá trị hợp lệ nhỏ nhất.
- `max`: giá trị hợp lệ lớn nhất.
- `min - 1`: ngay ngoài phía dưới, nếu phép tính không tràn số.
- `max + 1`: ngay ngoài phía trên, nếu phép tính không tràn số.

Cần xác định rõ ranh giới có bao gồm cận hay không. Với khoảng đóng, cả `min` và `max` đều thuộc khoảng. Với khoảng nửa mở `[min, max)`, cận trên không thuộc khoảng. Test phải phản ánh chính xác định nghĩa đó.

Các nhóm biên khác tùy dữ liệu:

| Loại dữ liệu | Các trường hợp nên cân nhắc |
|---|---|
| Số nguyên | Giá trị nhỏ nhất/lớn nhất được hỗ trợ, 0, số âm, ngay trong và ngoài giới hạn |
| Chuỗi | `null`, chuỗi rỗng, chuỗi chỉ có khoảng trắng, độ dài tối thiểu/tối đa, ký tự Unicode |
| Collection | `null`, rỗng, một phần tử, nhiều phần tử |
| Ngày giờ | Ngay trước/đúng/ngay sau mốc, cuối tháng, năm nhuận, múi giờ nếu liên quan |
| Phân trang | Trang đầu, trang cuối, kích thước 0 nếu được cho phép, chỉ số ngoài miền |
| Tài nguyên | Trạng thái chưa mở, đang mở, đã đóng; thao tác lặp lại theo hợp đồng |

Tránh tạo `min - 1` hoặc `max + 1` nếu các phép tính đó có thể tràn số. Với miền gần `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE`, hãy thiết kế test trực tiếp cho các giá trị cực trị thay vì tính một giá trị nằm ngoài kiểu dữ liệu.

## 6. Ví dụ Java 17 chạy độc lập

Ví dụ dưới đây tạo một record `IntRange` biểu diễn khoảng đóng. Bất biến của nó là `min <= max`. Phương thức `contains` nhận `Integer` để minh họa hợp đồng với `null`, và kiểm tra cả hai cận.

Lưu toàn bộ mã vào `Main.java`:

~~~java
import java.util.Objects;

record IntRange(int min, int max) {
    IntRange {
        if (min > max) {
            throw new IllegalArgumentException("min must be <= max");
        }
    }

    boolean contains(Integer value) {
        Objects.requireNonNull(value, "value");
        return value >= min && value <= max;
    }
}

public class Main {
    private static int passed = 0;

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError("FAIL: " + name);
        }
        passed++;
        System.out.println("PASS: " + name);
    }

    private static <T extends Throwable> T expectThrows(
            Class<T> expectedType, Runnable action, String name) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (expectedType.isInstance(actual)) {
                passed++;
                System.out.println("PASS: " + name);
                return expectedType.cast(actual);
            }
            throw new AssertionError(
                    name + " expected " + expectedType.getSimpleName()
                            + " but got " + actual, actual);
        }
        throw new AssertionError(
                name + " expected " + expectedType.getSimpleName()
                        + " but nothing was thrown");
    }

    public static void main(String[] args) {
        IntRange range = new IntRange(10, 20);

        check("lower boundary is included", range.contains(10));
        check("upper boundary is included", range.contains(20));
        check("below lower boundary is excluded", !range.contains(9));
        check("above upper boundary is excluded", !range.contains(21));

        expectThrows(IllegalArgumentException.class,
                () -> new IntRange(20, 10),
                "invalid range violates invariant");
        expectThrows(NullPointerException.class,
                () -> range.contains(null),
                "null input is rejected");

        System.out.println("All " + passed + " checks passed.");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac Main.java
java Main
~~~

Đầu ra chuẩn chính xác:

~~~text
PASS: lower boundary is included
PASS: upper boundary is included
PASS: below lower boundary is excluded
PASS: above upper boundary is excluded
PASS: invalid range violates invariant
PASS: null input is rejected
All 6 checks passed.
~~~

Trong ví dụ, constructor từ chối khoảng đảo ngược trước khi tạo được đối tượng không hợp lệ. Hai test đầu xác nhận khoảng đóng bao gồm cả cận dưới và cận trên; hai test tiếp theo xác nhận giá trị ngay ngoài khoảng bị loại. Hai test cuối xác nhận đầu vào vi phạm hợp đồng gây ra đúng loại ngoại lệ.

Hàm `expectThrows` chỉ là bộ trợ giúp nhỏ cho ví dụ chạy độc lập, không phải thư viện kiểm thử thay thế JUnit. Nó ném `AssertionError` nếu không có ngoại lệ hoặc ngoại lệ sai loại, nên chương trình không thể in báo cáo thành công khi một kiểm tra thất bại.

## 7. Cách viết các kiểm thử tương tự bằng JUnit 5

Trong dự án sử dụng JUnit 5, hãy đặt lớp cần kiểm thử và lớp test theo cấu trúc dự án. Ví dụ dưới đây giả sử `IntRange` nằm trong cùng package và có thể truy cập từ test:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class IntRangeTest {
    @Test
    void includesBothBoundaries() {
        IntRange range = new IntRange(10, 20);

        assertTrue(range.contains(10));
        assertTrue(range.contains(20));
    }

    @ParameterizedTest
    @ValueSource(ints = {9, 21})
    void excludesValuesOutsideRange(int value) {
        IntRange range = new IntRange(10, 20);

        assertFalse(range.contains(value));
    }

    @Test
    void rejectsInvertedRange() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new IntRange(20, 10));
    }

    @Test
    void rejectsNullValue() {
        IntRange range = new IntRange(10, 20);

        assertThrows(
                NullPointerException.class,
                () -> range.contains(null));
    }
}
~~~

`@Test` đánh dấu một test. `@ParameterizedTest` chạy cùng một hành vi với nhiều dữ liệu, trong ví dụ là hai giá trị nằm ngoài khoảng. `@ValueSource` cung cấp dữ liệu cho các lần chạy. `assertThrows` xác nhận loại ngoại lệ mong đợi; nếu không có ngoại lệ hoặc loại không khớp, test thất bại.

Đoạn JUnit ở trên là mã test cho một dự án đã cấu hình JUnit 5, không phải chương trình độc lập có thể chạy chỉ với `javac` mặc định. Dùng hệ thống build của dự án (chẳng hạn Maven hoặc Gradle) để thêm JUnit và chạy test suite. Ví dụ độc lập ở mục trước không cần thư viện bên ngoài.

## 8. Chất lượng test và chẩn đoán khi thất bại

Một test tốt cần thất bại vì lý do rõ ràng khi hành vi bị phá vỡ. Hãy áp dụng các nguyên tắc sau:

- **Đặt tên theo hành vi:** chẳng hạn `rejectsInvertedRange`, thay vì `test1`.
- **Mỗi test có mục tiêu rõ:** tránh gom nhiều hành vi không liên quan vào một test dài.
- **Dùng dữ liệu xác định:** không phụ thuộc vào thời gian thực, mạng hoặc trạng thái dùng chung nếu điều đó không phải mục tiêu kiểm thử.
- **Kiểm tra kết quả quan sát được:** đầu ra, trạng thái công khai, loại ngoại lệ và các tác dụng phụ thuộc hợp đồng.
- **Tránh bắt ngoại lệ quá rộng:** không để lỗi bất ngờ được coi là thành công.
- **Giữ test độc lập:** một test không nên cần chạy sau một test khác mới thành công.
- **Đọc thông báo thất bại:** xác định đầu vào, giá trị mong đợi, giá trị thực tế và vị trí lỗi trước khi sửa mã.
- **Tái chạy nhóm test liên quan:** sau khi sửa, xác nhận test mới và các hành vi lân cận vẫn đúng.

Đừng chỉ viết test cho nhánh thành công. Test ngoại lệ và giá trị biên thường làm rõ hợp đồng của API hơn, nhưng cũng tránh khẳng định chi tiết không được cam kết. Ví dụ, nếu hợp đồng chỉ yêu cầu từ chối dữ liệu không hợp lệ, test loại ngoại lệ có thể đủ; kiểm tra chính xác chuỗi thông điệp chỉ nên làm khi thông điệp đó có ý nghĩa công khai.

## Quy trình kiểm thử gợi ý

1. Viết ra bất biến, điều kiện đầu vào, kết quả và hành vi lỗi mong đợi.
2. Tạo ít nhất một trường hợp hợp lệ và một trường hợp không hợp lệ cho mỗi hợp đồng quan trọng.
3. Với giới hạn, kiểm tra ngay tại cận và ngay bên ngoài cận ở cả hai phía khi áp dụng.
4. Kiểm tra `null` theo hợp đồng của từng tham số tham chiếu.
5. Dùng `assertThrows` hoặc bộ kiểm tra ngoại lệ tương đương để xác nhận loại lỗi.
6. Chạy test, đọc lỗi thất bại, sửa nguyên nhân rồi chạy lại test liên quan.

## Ghi nhớ

Bất biến xác định trạng thái nào được xem là hợp lệ; kiểm thử `null` xác minh hợp đồng đầu vào; kiểm thử exception xác minh cách lỗi được báo cáo; còn kiểm thử biên tập trung vào các giá trị ngay tại và quanh giới hạn. Kết hợp bốn nhóm này giúp phát hiện nhiều lỗi mà chỉ kiểm tra một vài kết quả thông thường sẽ bỏ qua.