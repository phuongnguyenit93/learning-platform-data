# Hoàn thiện ví dụ tích hợp và bộ kiểm thử hợp đồng

Một API Java có thể kết hợp interface công khai, default method và abstract class hỗ trợ. Để các cách triển khai khác nhau vẫn tuân thủ cùng một hợp đồng, hãy kiểm thử hành vi quan sát được của interface trên **từng implementation**. Bộ kiểm thử hợp đồng (contract test suite) gom các điều kiện chung vào một nơi và chạy lại chúng cho mọi lớp triển khai.

Bài này xây dựng một ví dụ hoàn chỉnh về bộ định dạng văn bản. Một lớp triển khai interface trực tiếp; lớp còn lại kế thừa abstract class để dùng lại quy trình chung. Cả hai cùng chạy qua một bộ kiểm thử, sau đó các kiểm thử riêng xác nhận đầu ra đặc thù của từng lớp.

## 1. Hợp đồng cần kiểm thử

Interface `TextFormatter` cung cấp hai thao tác:

- `format(String)` định dạng văn bản. Đầu vào `null` bị từ chối bằng `NullPointerException`; khoảng trắng ở hai đầu không ảnh hưởng kết quả.
- `supports(String)` là default method, trả về `true` khi chuỗi khác `null` và không rỗng sau khi xét khoảng trắng. Với `null` hoặc chuỗi chỉ chứa khoảng trắng, kết quả là `false`.

Hợp đồng mô tả những gì người gọi được phép dựa vào, không yêu cầu mọi implementation phải tạo ra chuỗi giống hệt nhau. Ví dụ, một formatter có thể trả về `Java`, còn formatter khác trả về `[JAVA]`. Cả hai vẫn đáp ứng hợp đồng nếu chúng tuân thủ các điều kiện đã nêu.

Bộ kiểm thử sẽ xác nhận rằng mỗi formatter:

1. Hỗ trợ văn bản không trống.
2. Không tuyên bố hỗ trợ `null` hoặc chuỗi trống sau khi bỏ khoảng trắng.
3. Trả về kết quả khác `null` với đầu vào hợp lệ.
4. Cho kết quả tương đương khi đầu vào chỉ khác khoảng trắng ở hai đầu, kể cả ký tự khoảng trắng Unicode.
5. Có kết quả ổn định khi gọi lại với cùng đầu vào.
6. Xử lý chuỗi chỉ có khoảng trắng nhất quán với chuỗi rỗng.
7. Ném đúng `NullPointerException` khi `format` nhận `null`.

Các điều kiện này áp dụng cho mọi implementation. Kiểm thử riêng có thể bổ sung những khẳng định cụ thể về kiểu định dạng của từng lớp.

## 2. Vai trò của từng thành phần

```text
TextFormatter (hợp đồng công khai)
    ├── PlainTextFormatter (implements trực tiếp)
    └── AbstractTextFormatter (lớp hỗ trợ)
            └── BracketTextFormatter (extends)
```

`TextFormatter` là kiểu mà mã khách hàng phụ thuộc vào. Default method `supports` cung cấp một hành vi nhỏ, có thể tính được từ đầu vào và không cần trạng thái đối tượng.

`AbstractTextFormatter` dùng Template Method: phương thức `format` là `final`, kiểm tra đầu vào và chuẩn hóa khoảng trắng trước khi chuyển phần còn lại cho hook `formatTrimmed`. Lớp con chỉ quyết định cách trình bày chuỗi đã chuẩn hóa.

`PlainTextFormatter` triển khai interface trực tiếp để minh họa rằng abstract class là tùy chọn. Lớp này tự thực hiện quy tắc bỏ khoảng trắng ở hai đầu. Dù cấu trúc triển khai khác nhau, cả hai lớp phải vượt qua cùng bộ kiểm thử hợp đồng.

## 3. Ví dụ tích hợp chạy được trên Java 17+

Lưu toàn bộ mã sau vào tệp `FormatterContractDemo.java`. Các kiểu phụ không khai báo `public` nên có thể đặt cùng tệp với lớp chạy chính.

```java
import java.util.Locale;
import java.util.Objects;

interface TextFormatter {
    String format(String input);

    default boolean supports(String input) {
        return input != null && !input.isBlank();
    }
}

abstract class AbstractTextFormatter implements TextFormatter {
    @Override
    public final String format(String input) {
        Objects.requireNonNull(input, "input");
        return formatTrimmed(input.strip());
    }

    protected abstract String formatTrimmed(String trimmedInput);
}

class PlainTextFormatter implements TextFormatter {
    @Override
    public String format(String input) {
        Objects.requireNonNull(input, "input");
        return input.strip();
    }
}

class BracketTextFormatter extends AbstractTextFormatter {
    @Override
    protected String formatTrimmed(String trimmedInput) {
        return "[" + trimmedInput.toUpperCase(Locale.ROOT) + "]";
    }
}

public class FormatterContractDemo {
    private static int checks;

    private static void check(boolean condition, String description) {
        checks++;
        if (!condition) {
            throw new AssertionError("Contract check failed: " + description);
        }
    }

    private static void expectThrows(
            Class<? extends Throwable> expected,
            Runnable action,
            String description) {
        try {
            action.run();
        } catch (Throwable actual) {
            check(expected.isInstance(actual),
                    description + " (wrong exception: " + actual + ")");
            return;
        }
        check(false, description + " (no exception thrown)");
    }

    private static void verifyContract(String name, TextFormatter formatter) {
        check(formatter.supports("Java"), name + " supports nonblank text");
        check(!formatter.supports(null), name + " does not support null");
        check(!formatter.supports(" \t "), name + " does not support blank text");

        String expected = formatter.format("Java");
        check(expected != null, name + " returns a non-null result");
        check(expected.equals(formatter.format(" Java ")),
                name + " ignores leading and trailing whitespace");
        check(expected.equals(formatter.format("\u2003Java\u2003")),
                name + " ignores Unicode edge whitespace");
        check(expected.equals(formatter.format("Java")), name + " is deterministic");
        check(formatter.format("   ").equals(formatter.format("")),
                name + " treats whitespace-only input like empty input");
        expectThrows(NullPointerException.class, () -> formatter.format(null),
                name + " rejects null input");

        System.out.println("PASS " + name + ": 9 contract checks");
    }

    public static void main(String[] args) {
        TextFormatter plain = new PlainTextFormatter();
        TextFormatter bracketed = new BracketTextFormatter();

        verifyContract("PlainTextFormatter", plain);
        verifyContract("BracketTextFormatter", bracketed);

        check("Java".equals(plain.format(" Java ")),
                "plain formatter's specific output");
        check("[JAVA]".equals(bracketed.format(" Java ")),
                "bracket formatter's specific output");

        System.out.println("Plain: " + plain.format(" Java "));
        System.out.println("Bracket: " + bracketed.format(" Java "));
        System.out.println("Contract suite passed: " + checks + " checks");
    }
}
```

Ở đây `strip()` (Java 11+) xử lý khoảng trắng Unicode nhất quán với `String.isBlank()`, trong khi `trim()` không loại bỏ mọi ký tự khoảng trắng Unicode. Bộ kiểm thử thêm trường hợp `U+2003` (EM SPACE) ở hai đầu để xác minh điều này.

Biên dịch và chạy:

```text
javac -encoding UTF-8 FormatterContractDemo.java
java FormatterContractDemo
```

Kết quả chuẩn:

```text
PASS PlainTextFormatter: 9 contract checks
PASS BracketTextFormatter: 9 contract checks
Plain: Java
Bracket: [JAVA]
Contract suite passed: 20 checks
```

Bộ kiểm thử chạy chín điều kiện hợp đồng cho mỗi formatter, tổng cộng 18 kiểm tra chung, rồi chạy hai kiểm tra đầu ra riêng. Nếu bất kỳ điều kiện nào sai, `check` ném `AssertionError` và chương trình dừng với thông tin kiểm tra thất bại. Cách này cho phép chạy ví dụ ngay bằng JDK, không cần cài thêm thư viện kiểm thử.

## 4. Vì sao cần kiểm thử từng implementation?

Kiểm thử một lớp không chứng minh rằng mọi lớp tuân thủ interface đều đúng. `PlainTextFormatter` có thể bỏ khoảng trắng chính xác, trong khi một implementation khác vô tình trả lại đầu vào nguyên trạng. Nếu chỉ kiểm thử lớp thứ nhất, lỗi của lớp thứ hai sẽ không được phát hiện.

Lời gọi `verifyContract` nhận tên và một `TextFormatter`, vì vậy cùng logic kiểm thử được dùng lại cho cả hai đối tượng. Khi thêm implementation thứ ba, chỉ cần tạo đối tượng và gọi cùng hàm hợp đồng:

```java
TextFormatter another = new AnotherTextFormatter();
verifyContract("AnotherTextFormatter", another);
```

Dòng trên là đoạn minh họa để thêm vào chương trình; `AnotherTextFormatter` phải được định nghĩa và đáp ứng cùng hợp đồng trước khi biên dịch.

Nên chạy bộ kiểm thử hợp đồng trên mọi implementation công khai, kể cả implementation của module khác hoặc của bên thứ ba nếu dự án kiểm soát được việc kiểm thử đó. Khi thêm một default method mới vào interface, hãy bổ sung các điều kiện liên quan vào bộ hợp đồng để mọi implementation đều được kiểm tra theo cùng một chuẩn.

## 5. Kiểm thử hợp đồng và kiểm thử riêng khác nhau thế nào?

**Kiểm thử hợp đồng** xác nhận quy tắc chung mà người gọi được quyền dựa vào. Những quy tắc này không nên phụ thuộc vào chi tiết nội bộ của một lớp.

**Kiểm thử riêng của implementation** xác nhận hành vi đặc thù mà lớp đó cam kết. Trong ví dụ, hai kiểm tra sau chỉ thuộc về các formatter cụ thể:

- `PlainTextFormatter` trả về `Java` khi đầu vào là `" Java "`.
- `BracketTextFormatter` trả về `[JAVA]` cho cùng đầu vào.

Không nên đưa yêu cầu “mọi formatter phải trả về chuỗi viết hoa trong ngoặc vuông” vào bộ hợp đồng chung, vì điều đó sẽ loại bỏ hợp lệ các formatter có mục đích khác. Hãy phân biệt điều gì thuộc interface và điều gì thuộc riêng một implementation.

## 6. Abstract class giúp duy trì hợp đồng ra sao?

`AbstractTextFormatter` khai báo `format` là `final` để lớp con không thể vô tình bỏ qua các bước kiểm tra `null` và chuẩn hóa khoảng trắng. Các lớp con chỉ ghi đè `formatTrimmed`, nhận đầu vào đã được chuẩn hóa.

Đây là cách sử dụng Template Method để giữ các bước bất biến trong lớp cơ sở. Nó hữu ích khi nhiều lớp cần chung một quy trình và chỉ khác nhau ở một bước. Tuy nhiên, nó không tự đảm bảo toàn bộ hợp đồng của interface: phương thức hook vẫn có thể trả về `null` hoặc tạo kết quả không phù hợp. Bộ kiểm thử hợp đồng cần tiếp tục xác minh kết quả quan sát được.

Với `PlainTextFormatter`, quy tắc được thực hiện trực tiếp trong `format`. Việc lặp lại một chút mã là có chủ đích để minh họa lựa chọn triển khai interface mà không kế thừa abstract class. Trong API thực tế, cân nhắc chi phí bảo trì của phần lặp và mức độ cần thiết của lớp hỗ trợ.

## 7. Mở rộng sang JUnit

Trong dự án lớn, có thể chuyển cùng ý tưởng sang JUnit 5 để mỗi điều kiện là một test độc lập, dễ xem kết quả và dễ tích hợp vào CI. Một cách tổ chức phổ biến là tạo lớp kiểm thử hợp đồng cơ sở với một phương thức factory cung cấp đối tượng cần kiểm tra, rồi tạo lớp con cho từng implementation. Các test chung được kế thừa và chạy riêng cho từng lớp.

Ví dụ cấu trúc:

```text
src/
  main/java/
    TextFormatter.java
    AbstractTextFormatter.java
    PlainTextFormatter.java
    BracketTextFormatter.java
  test/java/
    TextFormatterContractTest.java
    PlainTextFormatterTest.java
    BracketTextFormatterTest.java
```

Lớp kiểm thử hợp đồng trong JUnit sẽ đặt các khẳng định về `supports`, xử lý `null`, chuẩn hóa đầu vào và tính ổn định vào một nơi. Mỗi lớp kiểm thử cụ thể cung cấp formatter thông qua factory hoặc phương thức khởi tạo. Các test riêng cho đầu ra `Java` và `[JAVA]` vẫn ở lớp kiểm thử của implementation tương ứng.

Dù dùng harness tự viết hay JUnit, nguyên tắc vẫn như nhau: cùng một bộ điều kiện phải chạy trên mọi implementation, còn các chi tiết riêng phải được kiểm tra tách biệt. Harness trong ví dụ chính là phiên bản độc lập, có thể biên dịch và chạy ngay mà không phụ thuộc công cụ ngoài.

## 8. Các lỗi thường gặp

- **Chỉ kiểm thử lớp hỗ trợ:** lớp triển khai interface trực tiếp vẫn có thể vi phạm hợp đồng.
- **Kiểm thử chi tiết nội bộ:** kiểm tra hook được gọi bao nhiêu lần hoặc trường nội bộ có giá trị gì thường làm test phụ thuộc cấu trúc, thay vì hành vi công khai.
- **Đưa đầu ra đặc thù vào hợp đồng chung:** yêu cầu mọi implementation tạo cùng một kiểu chuỗi sẽ làm hợp đồng quá chặt nếu interface chỉ cam kết những thuộc tính tổng quát.
- **Bỏ qua trường hợp biên:** `null`, chuỗi rỗng, chuỗi chỉ có khoảng trắng và đầu vào có khoảng trắng hai đầu thường phát hiện lỗi hợp đồng.
- **Không cập nhật bộ kiểm thử khi hợp đồng đổi:** nếu thêm một default method hoặc thay đổi quy tắc đầu vào, hãy cập nhật test chung và chạy lại trên tất cả implementation.
- **Chỉ nhìn số lượng test thành công:** các test phải kiểm tra điều kiện có ý nghĩa; một loạt assertion lặp lại cùng một hành vi không thay thế được độ bao phủ của hợp đồng.

## 9. Quy trình hoàn thiện ví dụ tích hợp

1. Xác định các điều kiện công khai mà mọi implementation phải tuân theo.
2. Đặt hợp đồng trong interface; chỉ dùng default method cho hành vi chung phù hợp.
3. Cung cấp abstract class khi có quy trình triển khai thực sự dùng chung, và để các lớp có thể triển khai interface trực tiếp khi cần.
4. Viết một bộ kiểm thử nhận interface làm kiểu đầu vào, không phụ thuộc lớp cụ thể.
5. Chạy bộ hợp đồng cho từng implementation, sau đó bổ sung test riêng cho hành vi đặc thù.
6. Biên dịch, chạy test và xác nhận kết quả đầu ra thực tế trước khi đưa ví dụ vào tài liệu.

Một ví dụ tích hợp hoàn chỉnh cần thể hiện cả thiết kế lẫn cách xác minh thiết kế đó. Interface xác định hành vi mà mã khách hàng được quyền trông đợi; abstract class hỗ trợ tái sử dụng các bước chung; bộ kiểm thử hợp đồng xác nhận mọi cách triển khai đều giữ đúng những bảo đảm công khai ấy.