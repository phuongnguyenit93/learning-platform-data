# Biên dịch lại regex so với tái sử dụng Pattern trong Java

Trong Java, regular expression (regex) thường được dùng để kiểm tra định dạng, tìm kiếm hoặc tách dữ liệu trong chuỗi. Khi **cùng một regex được áp dụng cho nhiều chuỗi**, gọi `Pattern.compile(regex)` lặp lại có thể tạo chi phí không cần thiết. Cách thông thường để giảm chi phí là **biên dịch regex một lần thành `Pattern` rồi tạo `Matcher` mới cho từng đầu vào**.

Điểm quan trọng: tái sử dụng `Pattern` chủ yếu tránh việc phân tích/biên dịch lại biểu thức. Nó không làm mất chi phí quét văn bản, không bảo đảm cải thiện tốc độ trong mọi tình huống và không chữa được regex có thuật toán khớp quá tốn kém.

## 1. Pattern, Matcher và hai giai đoạn xử lý

Ví dụ:

~~~java
Pattern pattern = Pattern.compile("[A-Za-z][A-Za-z0-9_]{2,11}");
boolean valid = pattern.matcher("anna_27").matches();
~~~

- **`Pattern.compile(regex)`** phân tích cú pháp regex, kiểm tra tính hợp lệ, xây dựng biểu diễn nội bộ để sử dụng khi khớp. Việc này có chi phí CPU và có thể cấp phát bộ nhớ; biểu thức sai cú pháp gây `PatternSyntaxException` (unchecked exception).
- **`Pattern`** là đối tượng biểu diễn regex đã biên dịch. Theo hợp đồng API Java, `Pattern` **bất biến và an toàn để dùng chung giữa các thread**.
- **`pattern.matcher(input)`** tạo `Matcher` cho đầu vào cụ thể. `Matcher` giữ trạng thái tìm kiếm (vị trí, nhóm bắt được, vùng tìm kiếm, v.v.), nên **không an toàn để nhiều thread cùng thao tác**.
- **`matcher.matches()`** kiểm tra **toàn bộ chuỗi đầu vào** có phù hợp regex không.
- **`matcher.find()`** tìm một đoạn con khớp, bắt đầu tại vị trí tìm kiếm hiện tại. **`matcher.lookingAt()`** kiểm tra khớp từ đầu vùng tìm kiếm, nhưng không bắt buộc phải phủ hết vùng đó.

Đừng nhầm việc *biên dịch regex* với việc *so khớp một chuỗi*: giữ `Pattern` loại bỏ bước biên dịch lại, nhưng mỗi lượt kiểm tra vẫn cần một `Matcher` (hoặc reset một matcher dùng tuần tự, trong phạm vi có kiểm soát).

## 2. Những cách viết và tác động hiệu năng

Giả sử `regex` là một biểu thức cố định và `value` là chuỗi cần kiểm tra:

| Cách viết | Hành vi khi gọi lặp lại |
| --- | --- |
| `value.matches(regex)` | Tiện lợi cho một lần kiểm tra; gọi `Pattern.matches(regex, value)`, có bước biên dịch regex trong lời gọi. |
| `Pattern.matches(regex, value)` | Phương thức tiện ích thực hiện biên dịch regex rồi kiểm tra toàn bộ đầu vào; không giữ lại `Pattern` để tái sử dụng cho lần sau. |
| `Pattern.compile(regex).matcher(value).matches()` | Thể hiện rõ một lần biên dịch mới trên mỗi lượt gọi. |
| `PATTERN.matcher(value).matches()` với `PATTERN` đã được biên dịch trước | Dùng lại `Pattern`; mỗi lượt vẫn tạo `Matcher` và thực hiện so khớp. |

Ba cách đầu có thể phù hợp với kiểm tra đơn lẻ hoặc đoạn mã ít khi chạy. Khi nằm trong vòng lặp xử lý hàng nghìn bản ghi với cùng regex, chi phí biên dịch lại có thể đáng kể. Mức chênh lệch thực tế phụ thuộc vào độ phức tạp regex, độ dài đầu vào, tần suất gọi, cách JVM tối ưu và phần việc khác của ứng dụng; **không nên khẳng định một tỷ lệ tăng tốc cố định nếu chưa đo**.

Phương thức `String.matches(regex)` **không tương đương** `String.contains(text)`: đối số của `matches` là regex và nó kiểm tra toàn bộ chuỗi. Với mục tiêu tìm chuỗi con thông thường, dùng phương thức thao tác chuỗi phù hợp thường rõ ràng hơn.

## 3. Ví dụ Java 17+ chạy được: biên dịch mỗi lượt và tái sử dụng

Lưu chương trình sau thành **PatternReuseDemo.java** (UTF-8). Regex yêu cầu tên bắt đầu bằng chữ ASCII, tiếp theo là 2–11 ký tự chữ/số/gạch dưới: tổng cộng 3–12 ký tự. Chương trình minh họa ba cách kiểm tra cùng một tập đầu vào; bộ đếm chỉ ghi nhận số lệnh `compile()` **mà vòng lặp đầu tiên gọi trực tiếp**, không phải phép đo tổng số thao tác nội bộ của JVM.

~~~java
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class PatternReuseDemo {
    private static final String USERNAME_REGEX =
            "[A-Za-z][A-Za-z0-9_]{2,11}";

    // Biên dịch một lần khi lớp được khởi tạo.
    private static final Pattern USERNAME_PATTERN =
            Pattern.compile(USERNAME_REGEX);

    private static final Pattern DIGITS = Pattern.compile("\\d+");

    public static void main(String[] args) {
        List<String> names = List.of("anna_27", "ab", "9tom", "bob");

        int explicitCompilations = 0;
        int countCompileAgain = 0;
        for (String name : names) {
            // Chi phí biên dịch lặp lại dù regex không đổi.
            Pattern p = Pattern.compile(USERNAME_REGEX);
            explicitCompilations++;

            if (p.matcher(name).matches()) {
                countCompileAgain++;
            }
        }

        int countReuse = 0;
        for (String name : names) {
            // Mỗi input có Matcher riêng; dùng chung Pattern.
            Matcher matcher = USERNAME_PATTERN.matcher(name);
            if (matcher.matches()) {
                countReuse++;
            }
        }

        int countStringMatches = 0;
        for (String name : names) {
            if (name.matches(USERNAME_REGEX)) {
                countStringMatches++;
            }
        }

        System.out.println("Explicit compile() in loop: "
                + explicitCompilations);
        System.out.println("Matches (compile each time): "
                + countCompileAgain);
        System.out.println("Matches (reuse Pattern): "
                + countReuse);
        System.out.println("Matches (String.matches): "
                + countStringMatches);

        String text = "Order #42";
        System.out.println("matches() for digits: "
                + DIGITS.matcher(text).matches());
        System.out.println("find() for digits: "
                + DIGITS.matcher(text).find());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PatternReuseDemo.java
java PatternReuseDemo
~~~

Kết quả:

~~~text
Explicit compile() in loop: 4
Matches (compile each time): 2
Matches (reuse Pattern): 2
Matches (String.matches): 2
matches() for digits: false
find() for digits: true
~~~

**Giải thích:** Tên `anna_27` và `bob` hợp lệ, còn `ab` quá ngắn và `9tom` không bắt đầu bằng chữ. Cả ba cách tạo cùng kết quả, nhưng vòng lặp đầu tiên gọi `Pattern.compile` bốn lần. `USERNAME_PATTERN` chỉ biên dịch một lần khi lớp khởi tạo, sau đó được tái sử dụng. Kết quả `matches() for digits: false` do `"Order #42"` không hoàn toàn gồm các chữ số; `find()` là `true` vì tìm thấy đoạn `42`.

Đây là **minh họa về số lần biên dịch và tính đúng đắn**, không phải benchmark hiệu năng. Đầu ra trên không cho biết một cách nào nhanh hơn bao nhiêu nanosecond.

## 4. Những mẫu tổ chức code nên dùng

### Regex cố định, được gọi thường xuyên

Biên dịch một lần thành hằng dùng chung:

~~~java
import java.util.regex.Pattern;

public final class Usernames {
    private static final Pattern VALID_NAME =
            Pattern.compile("[A-Za-z][A-Za-z0-9_]{2,11}");

    private Usernames() {}

    public static boolean isValid(String value) {
        return value != null
                && VALID_NAME.matcher(value).matches();
    }
}
~~~

Đây là ví dụ **lớp tiện ích riêng**; khi dùng, lưu thành `Usernames.java` và gọi `Usernames.isValid("anna_27")`. Việc dùng `static final` phù hợp khi regex là hằng, được dùng nhiều nơi hoặc nhiều lần trong vòng đời ứng dụng. `final` cố định tham chiếu; tính an toàn khi dùng chung đến từ hợp đồng `Pattern` bất biến. Mỗi lần gọi phương thức tạo `Matcher` mới nên không chia sẻ trạng thái khớp giữa các luồng.

### Regex thay đổi theo yêu cầu nhưng dùng cho nhiều chuỗi

Không nhất thiết biến mọi regex thành `static final`. Nếu regex được tạo theo một tham số của tác vụ, hãy biên dịch **một lần cho tác vụ đó**, rồi dùng lại trong vòng lặp:

~~~java
Pattern selected = Pattern.compile(regexForThisRequest, flags);

for (String value : values) {
    if (selected.matcher(value).find()) {
        // Xử lý giá trị khớp.
    }
}
~~~

Đây là **đoạn minh họa trong phương thức hiện có**: `regexForThisRequest` (kiểu `String`), `flags` (kiểu `int`), `values` (tập chuỗi) và phần xử lý phải được cung cấp bởi chương trình gọi. Khi giữ lại một `Pattern`, phải giữ **cùng regex và flags** như khi biên dịch ở từng vòng lặp. Thay đổi `Pattern.CASE_INSENSITIVE`, `Pattern.MULTILINE`, `Pattern.UNICODE_CASE` hoặc flags khác có thể đổi kết quả so khớp.

Nếu regex thực sự thay đổi sau mỗi bản ghi, tái sử dụng một `Pattern` khác regex là **sai logic**. Chỉ áp dụng cache cho cùng cặp biểu thức và cấu hình cờ.

### Nhiều regex động, có lặp lại

Cache `Pattern` chỉ có ích khi biểu thức được gọi lại đủ thường xuyên để bù chi phí tra cứu và lưu bộ nhớ. Với regex động từ nhiều người dùng:

- Dùng cache **có giới hạn số phần tử** hoặc chính sách hết hạn; cache không giới hạn theo regex tùy ý có thể tăng bộ nhớ liên tục.
- Khóa cache cần phân biệt **regex và flags**. Các biểu thức chỉ giống tên nhưng khác flags không phải cùng cấu hình.
- Xem xét tần suất trùng lặp thực tế trước khi thêm cache phức tạp. Nếu mỗi regex chỉ dùng một lần, cache có thể tăng overhead.
- Nếu biểu thức được người dùng nhập vào có ý nghĩa là **văn bản thuần** cần tìm, chuyển thành regex literal với `Pattern.quote(userText)`. Đây là xử lý ý nghĩa ký tự đặc biệt, không phải tối ưu biên dịch.

Ví dụ: `Pattern.compile(Pattern.quote("a.b"))` nhận dấu chấm là ký tự `.` thực, còn `Pattern.compile("a.b")` dùng dấu chấm như metacharacter khớp một ký tự bất kỳ.

## 5. Tái sử dụng Pattern trong môi trường đa luồng

Một `Pattern` có thể dùng đồng thời cho nhiều luồng; mỗi luồng tạo `Matcher` riêng:

~~~java
private static final Pattern ID_PATTERN =
        Pattern.compile("[A-Z]{2}-\\d{4}");

// Trong một phương thức được nhiều thread gọi:
boolean valid = ID_PATTERN.matcher(value).matches();
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập: `value` là đầu vào `String` và code đặt trong lớp có import `java.util.regex.Pattern`. Dùng chung `Matcher` giữa nhiều thread hoặc giữ một `Matcher` tĩnh để gọi `reset()` đồng thời là sai vì trạng thái của nó có thể bị thay đổi xen kẽ.

Nếu xử lý rất nhiều giá trị trong **một thread** và muốn giảm thêm cấp phát `Matcher`, có thể tái sử dụng matcher trong phạm vi đó bằng `matcher.reset(nextInput)`. Tuy nhiên đây là một tối ưu bổ sung cần benchmark và quản lý trạng thái/nhóm kết quả cẩn thận; phương án mặc định đơn giản, an toàn và dễ kiểm thử hơn là **Pattern chung, Matcher mới cho mỗi input**.

## 6. Khi nào biên dịch lại vẫn hợp lý?

Biên dịch mới mỗi lần có thể chấp nhận được nếu biểu thức chỉ dùng một lần, đoạn code không nằm trên đường xử lý nóng, hoặc regex không lặp lại. Việc duy trì thêm cache hay hằng toàn cục cho một thao tác thưa thớt đôi khi không mang lại giá trị rõ rệt.

Nếu một regex có nguy cơ `PatternSyntaxException`, chuyển sang biên dịch một lần thường khiến lỗi xuất hiện sớm hơn, ví dụ khi khởi tạo lớp hoặc khởi động tác vụ. Đó là thay đổi **thời điểm phát hiện lỗi**, không phải tự động thay đổi cú pháp regex. Với biểu thức do người dùng nhập, vẫn cần xử lý lỗi cú pháp ở ranh giới nhập liệu phù hợp.

## 7. Đo hiệu năng thế nào cho đáng tin?

Đừng dùng một lần đo ngắn `System.nanoTime()` để kết luận về tốc độ regex, vì JIT, khởi động JVM, GC, tối ưu dead-code, dữ liệu đầu vào và khác biệt máy có thể che lấp kết quả. Khi cần quyết định tối ưu, hãy dùng công cụ benchmark Java phù hợp như **JMH** và so sánh hai đường đi có cùng ý nghĩa:

1. **Compile-and-match:** mỗi lượt xử lý gọi `Pattern.compile(regex)`, tạo matcher và so khớp.
2. **Reuse-and-match:** biên dịch `Pattern` ngoài phần đo đang lặp, trong lượt xử lý chỉ tạo matcher và so khớp.
3. Sử dụng cùng regex, flags, đầu vào và thao tác `matches()`/`find()`; tiêu thụ kết quả để công việc không bị loại bỏ bởi tối ưu biên dịch.
4. Chạy warmup và nhiều lần đo; thử cả regex đơn giản/phức tạp, đầu vào ngắn/dài, chuỗi khớp/không khớp, và tải có/không có cạnh tranh giữa thread. Xem cả throughput, độ trễ và cấp phát bộ nhớ nếu chúng ảnh hưởng ứng dụng.

Để diễn giải đúng, cần nhớ rằng `Pattern.compile` thường là phần overhead dễ tránh khi **một regex được dùng lại nhiều lần**; nhưng công việc khớp regex trên input thực tế có thể chiếm phần lớn thời gian. Tối ưu luôn nên bắt đầu từ hồ sơ hiệu năng và yêu cầu nghiệp vụ của chương trình.

### Tái sử dụng Pattern không chữa được regex tốn kém

Ví dụ các biểu thức có nhiều phép lặp lồng nhau hoặc nhiều nhánh mơ hồ có thể gây backtracking nặng trên input xấu, ngay cả khi chỉ biên dịch một lần. Với input không tin cậy, cần giới hạn độ dài, thiết kế regex giảm khả năng backtracking, đặt ranh giới thời gian/tài nguyên phù hợp hoặc chọn phương thức phân tích cú pháp phù hợp hơn. Tăng tốc bước biên dịch không đồng nghĩa bảo đảm an toàn trước tấn công từ chối dịch vụ qua regex (ReDoS).

## 8. Sai lầm thường gặp

| Sai lầm | Vì sao sai hoặc tốn kém | Cách làm đúng |
| --- | --- | --- |
| Gọi `value.matches(regex)` trong vòng lặp lớn khi regex không đổi | Dùng lại biểu thức dạng text nhưng vẫn chịu bước biên dịch theo API tiện ích. | Tạo `Pattern` trước vòng lặp, dùng `pattern.matcher(value).matches()`. |
| Gọi `Pattern.compile(regex)` trong hàm được gọi hàng triệu lần | Cùng biểu thức phải phân tích lại trên từng lượt. | Khởi tạo một lần ở phạm vi phù hợp và tái sử dụng. |
| Chia sẻ một `Matcher` giữa các thread | `Matcher` lưu trạng thái và không an toàn cho thao tác đồng thời. | Chia sẻ `Pattern`, mỗi lượt/thread tạo `Matcher` riêng. |
| Đổi `matches()` thành `find()` khi tối ưu | Có thể thay đổi hoàn toàn ý nghĩa kiểm tra. | Giữ nguyên thao tác so khớp và flags khi so sánh. |
| Cache vô hạn mọi regex từ đầu vào động | Tích lũy `Pattern` và key không cần thiết, làm tăng bộ nhớ. | Cache có giới hạn, đo mức trùng lặp hoặc chỉ dùng mỗi tác vụ. |
| Tin rằng mọi phiên bản JVM luôn cache `Pattern.matches`/`String.matches` | API không cam kết một bộ nhớ cache có thể dựa vào để tối ưu. | Chủ động giữ tham chiếu `Pattern` khi cần tái sử dụng. |
| Regex phức tạp bị backtracking nhưng chỉ tối ưu compile | Thời gian so khớp có thể lớn hơn nhiều chi phí compile. | Xem lại biểu thức, input và hồ sơ hiệu năng. |

## 9. Tự kiểm tra

1. Với cùng một regex được dùng để kiểm tra 100.000 chuỗi, chỗ nào nên đặt `Pattern.compile` để tránh biên dịch lặp lại?
2. Vì sao `private static final Pattern` có thể được nhiều thread dùng chung nhưng `private static final Matcher` thường là lựa chọn sai?
3. Khi input là `"Order #42"` và regex là `"\\d+"`, vì sao `matches()` trả `false` nhưng `find()` trả `true`?
4. Nếu regex được tạo mới từ mỗi yêu cầu và chỉ sử dụng một lần, cache có chắc cải thiện hiệu năng không?
5. Vì sao phép đo benchmark phải giữ nguyên regex, flags, input và thao tác khớp giữa hai phương án?

**Ghi nhớ:** Khi regex được dùng thường xuyên, biên dịch một lần và tái sử dụng `Pattern`; tạo `Matcher` mới cho mỗi đầu vào (đặc biệt trong chương trình đa luồng). Chỉ thêm cache cho biểu thức động sau khi thấy sự lặp lại, và dùng benchmark trên tải thực để xác định hiệu quả.