# Matcher.replaceAll với hàm tính chuỗi thay thế trong Java

Khi dùng regex, nhiều trường hợp ta muốn mỗi đoạn khớp nhận **một chuỗi thay thế khác nhau**, được tính dựa trên chính đoạn đó. Ví dụ: nhân đôi từng số trong câu, chuẩn hóa từng mã định danh, che bớt dữ liệu theo độ dài, hoặc tra cứu giá trị để điền placeholder. Từ **Java 9**, lớp **java.util.regex.Matcher** có phương thức **replaceAll(Function<MatchResult, String>)** để giải quyết những bài toán này.

Điểm cốt lõi: với **mỗi đoạn khớp**, Matcher gọi hàm do ta cung cấp, đưa vào thông tin match hiện tại và lấy **chuỗi thay thế do hàm trả về**. Những đoạn không khớp vẫn được giữ nguyên. Bài này hướng dẫn API, cơ chế, ví dụ Java 17 chạy độc lập và các lỗi cần tránh.

## 1. Khác nhau giữa thay thế cố định và thay thế bằng hàm

| Cách dùng | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| matcher.replaceAll(String replacement) | Áp dụng một khuôn chuỗi thay thế cho tất cả các lần khớp; có thể tham chiếu nhóm bắt. | Mọi match dùng cùng khuôn, ví dụ nối lại group 2 trước group 1. |
| matcher.replaceAll(Function<MatchResult, String> replacer) | Tính riêng chuỗi thay thế cho mỗi match bằng hàm/lambda. | Có chuyển đổi số, tra cứu, điều kiện hay biến đổi chuỗi phức tạp. |
| input.replaceAll(regex, replacement) | Phương thức của String nhận regex và **chuỗi thay thế**. | Cách viết nhanh khi không cần lambda. |

Chữ ký API, viết gọn:

~~~java
String replaceAll(Function<MatchResult, String> replacer)
~~~

Function là giao diện hàm trong java.util.function; MatchResult thuộc java.util.regex. Lambda thường nhận một tham số như match và trả về String. **String.replaceAll không có overload nhận lambda**: nếu muốn callback, phải tạo Pattern/Matcher rồi gọi overload của Matcher.

Với cùng một biểu thức dùng nhiều lần, nên biên dịch Pattern một lần, sau đó tạo Matcher cho đầu vào đang xử lý. Pattern bất biến và an toàn để chia sẻ; Matcher chứa trạng thái thay đổi, không nên dùng chung giữa các luồng.

## 2. Ví dụ hoàn chỉnh: nhân đôi các số vừa khớp

Tạo tệp **NumberReplacementDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class NumberReplacementDemo {
    private static final Pattern NUMBER = Pattern.compile("\\d+");

    public static void main(String[] args) {
        String input = "Điểm A=7, B=12, C=3.";
        Matcher matcher = NUMBER.matcher(input);

        String output = matcher.replaceAll(match -> {
            int number = Integer.parseInt(match.group());
            return Integer.toString(number * 2);
        });

        System.out.println(input);
        System.out.println(output);
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 NumberReplacementDemo.java
java NumberReplacementDemo
~~~

Kết quả tiêu chuẩn:

~~~text
Điểm A=7, B=12, C=3.
Điểm A=14, B=24, C=6.
~~~

**Diễn giải từng bước:** biểu thức \d+ tìm ra ba đoạn lần lượt là 7, 12, 3. Matcher gọi lambda ba lần; mỗi lần match.group() là dãy chữ số đang được xử lý. Lambda chuyển chuỗi thành số nguyên, nhân đôi và trả về chuỗi mới. Java lắp những chuỗi thay thế vào vị trí tương ứng, giữ nguyên toàn bộ dấu cách, chữ cái và dấu câu ngoài các match. Biến input không đổi vì String trong Java bất biến.

Trong ví dụ, Integer.parseInt phù hợp vì đầu vào nhỏ và có kiểm soát. Với dữ liệu tùy ý, số quá lớn có thể gây NumberFormatException, phép nhân int có thể tràn; cần chọn BigInteger/long hoặc áp dụng giới hạn nghiệp vụ. Mẫu \d+ cũng không có nghĩa là bộ phân tích đầy đủ số âm, số thập phân và Unicode theo mọi quy ước địa phương.

## 3. Đọc group để tính replacement theo cấu trúc

Regex có thể chia kết quả khớp thành nhiều **nhóm bắt**. Đối tượng MatchResult cung cấp:

- group() hoặc group(0): toàn bộ đoạn khớp.
- group(1), group(2), ...: nội dung các nhóm bắt theo chỉ số.
- start() và end(): biên của toàn bộ match; end() là vị trí ngay sau ký tự cuối.
- start(n), end(n): biên nhóm bắt n. Một nhóm tùy chọn không tham gia có thể có group(n) bằng null, start/end bằng -1.

Ví dụ: chuẩn hóa mã dạng hai chữ cái, dấu gạch ngang, một đến ba chữ số. Chữ cái chuyển thành in hoa; số được thêm 0 bên trái để có ba chữ số.

Tạo tệp **CodeNormalizeDemo.java**:

~~~java
import java.util.Locale;
import java.util.regex.Pattern;

public class CodeNormalizeDemo {
    public static void main(String[] args) {
        Pattern code = Pattern.compile("(?i)\\b([a-z]{2})-(\\d{1,3})\\b");
        String input = "Đơn ab-7 và Cd-42; ghi chú giữ nguyên.";

        String output = code.matcher(input).replaceAll(match -> {
            String prefix = match.group(1).toUpperCase(Locale.ROOT);
            int number = Integer.parseInt(match.group(2));
            return String.format(Locale.ROOT, "%s-%03d", prefix, number);
        });

        System.out.println(output);
    }
}
~~~

~~~bash
javac -encoding UTF-8 CodeNormalizeDemo.java
java CodeNormalizeDemo
~~~

~~~text
Đơn AB-007 và CD-042; ghi chú giữ nguyên.
~~~

Ở đây (?i) bật phân biệt hoa/thường không nghiêm ngặt cho các chữ ASCII trong mẫu; group(1) là tiền tố, group(2) là chữ số. Regex chỉ nhận các đoạn đúng cấu trúc để lambda có thể biến đổi hai phần riêng biệt.

**Điểm cần chú ý với Java 17:** tham số lambda được suy luận là giao diện **MatchResult**, không phải Matcher. Trong Java 17, nên truy cập nhóm theo **chỉ số** bằng group(1), group(2); lời gọi group("tenNhom") không có trong giao diện MatchResult của Java 17. Không ép tham số này thành Matcher để đổi trạng thái.

## 4. Replacement do lambda trả về vẫn có cú pháp đặc biệt

Đây là điểm thường gây lỗi nhất. Mặc dù replacement được tính bằng hàm, chuỗi trả về **vẫn được Matcher diễn giải theo cú pháp chuỗi thay thế**, thay vì luôn được chèn như văn bản thuần.

Trong cú pháp replacement:
- $1, $2, ... có thể tham chiếu các nhóm bắt bằng số.
- Cú pháp dấu đô la kèm tên nhóm trong ngoặc nhọn có thể tham chiếu nhóm được đặt tên.
- Dấu gạch chéo ngược \ có thể dùng để thoát ký tự kế tiếp.

Vì thế nếu một hàm trả về nguyên văn **Giá $5** hoặc đường dẫn **C:\data\test**, ký tự $ và \ có thể bị hiểu thành cú pháp replacement. Đầu ra có thể sai hoặc gây ngoại lệ. Khi muốn trả về **văn bản nguyên trạng**, hãy dùng:

~~~java
String literal = "Giá $5";
String safe = Matcher.quoteReplacement(literal);
~~~

Hàm **Matcher.quoteReplacement(String)** tạo chuỗi có thể dùng làm replacement mà vẫn giữ nguyên nội dung literal sau khi thay. Nếu lambda đã ghép chuỗi đích xong, cách an toàn là:

~~~java
return Matcher.quoteReplacement(computedValue);
~~~

Phân biệt với **Pattern.quote(String)**: Pattern.quote dùng để biến dữ liệu người dùng thành một **mẫu tìm kiếm** theo nghĩa literal; Matcher.quoteReplacement dùng để biến dữ liệu thành **chuỗi thay thế** theo nghĩa literal. Chúng phục vụ hai phía khác nhau của phép tìm và thay thế.

Khi **muốn** replacement thực thi tham chiếu nhóm như $1, $2, có thể chủ động trả về cú pháp ấy mà **không quote**. Nếu đã dùng match.group(1) để tạo kết quả hoàn chỉnh trong lambda, thông thường nên quote chuỗi kết quả để tránh $ hoặc \ phát sinh từ dữ liệu.

## 5. Ví dụ hoàn chỉnh: thay placeholder bằng Map, giữ nguyên ký tự đặc biệt

Yêu cầu: chuỗi mẫu chứa các placeholder dạng {{key}}. Tìm giá trị tương ứng từ Map, giữ nguyên placeholder nếu chưa có dữ liệu. Đặc biệt, giá trị có thể chứa $ và \ mà kết quả vẫn phải giữ đúng các ký tự đó.

Tạo tệp **TemplateReplacementDemo.java**:

~~~java
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TemplateReplacementDemo {
    private static final Pattern PLACEHOLDER =
            Pattern.compile("\\{\\{([A-Za-z][A-Za-z0-9_]*)\\}\\}");

    public static void main(String[] args) {
        String input = "Người: {{person}}; thư mục: {{path}}; thiếu: {{unknown}}";
        Map<String, String> values = Map.of(
                "person", "Lan$1",
                "path", "C:\\data\\test"
        );

        String output = PLACEHOLDER.matcher(input).replaceAll(match -> {
            String key = match.group(1);
            String value = values.getOrDefault(key, match.group());
            return Matcher.quoteReplacement(value);
        });

        System.out.println(output);
    }
}
~~~

~~~bash
javac -encoding UTF-8 TemplateReplacementDemo.java
java TemplateReplacementDemo
~~~

~~~text
Người: Lan$1; thư mục: C:\data\test; thiếu: {{unknown}}
~~~

**Giải thích:** regex chỉ nhận các placeholder theo cấu trúc {{tên}}. Nhóm 1 là tên khóa như person, path, unknown. Lambda lấy giá trị từ Map; nếu không có, dùng match.group() để giữ nguyên placeholder. Sau đó quoteReplacement bảo đảm dấu $ trong Lan$1 và các dấu \ trong đường dẫn được giữ nguyên. Nếu bỏ quoteReplacement, giá trị Lan$1 có thể bị hiểu thành tham chiếu nhóm $1, còn dấu \ có thể bị tiêu thụ khi xử lý replacement.

Đây là ví dụ thay thế văn bản, **không phải hệ thống template hoàn chỉnh**: nó không giải quyết escaping HTML, URL, SQL, JavaScript hay ngữ cảnh đầu ra khác. Khi đưa dữ liệu bên ngoài vào những ngữ cảnh đó, vẫn cần escaping phù hợp hoặc truy vấn tham số hóa.

## 6. Trình tự xử lý và trạng thái Matcher

Về mặt hành vi, replaceAll(Function) bắt đầu lại quá trình tìm kiếm, lần lượt tìm các đoạn khớp, gọi replacer cho mỗi đoạn và ghép kết quả thành một chuỗi đầu ra:

1. **Không có match:** hàm không được gọi, chuỗi đầu vào được giữ nguyên về nội dung.
2. **Có nhiều match:** hàm được gọi theo các kết quả tìm được, thông thường từ trái sang phải; các match do find() tìm là những đoạn không chồng lấn.
3. **Phần văn bản không khớp:** luôn được đưa vào kết quả nguyên vẹn.
4. **Replacement không được tìm tiếp trong cùng lượt:** nếu đoạn thay thế mới cũng khớp regex, nó không được xử lý thêm một lần nữa trong lời gọi hiện tại.
5. **Matcher chứa trạng thái duyệt:** replaceAll bắt đầu lượt thay thế từ đầu vùng đầu vào của Matcher; không trông chờ vị trí tìm kiếm trước đó được giữ nguyên. Nếu cần duyệt lại, tạo Matcher mới hoặc reset() đúng cách.
6. **Không sửa Matcher bên trong replacer:** gọi find(), reset(), region() hoặc phương thức thay đổi trạng thái trên chính Matcher đang thực hiện replaceAll có thể gây ConcurrentModificationException. Callback nên đọc tham số MatchResult và tạo chuỗi trả về.

Không lưu đối tượng MatchResult được callback cấp cho để dùng sau khi Matcher tiếp tục làm việc; nếu cần ghi nhận dữ liệu, sao chép group/start/end ngay trong callback. Pattern bất biến có thể dùng lại từ nhiều luồng, nhưng mỗi luồng/yêu cầu nên sử dụng Matcher của riêng mình.

## 7. So với find() + appendReplacement() + appendTail()

Trước Java 9, người lập trình thường dùng vòng lặp find() để tính replacement riêng từng match. Hai phương thức appendReplacement() và appendTail() hỗ trợ ghép kết quả: appendReplacement thêm phần chưa xử lý cùng replacement hiện tại; appendTail thêm phần còn lại của chuỗi gốc.

Đoạn minh họa sau giả định **pattern**, **input** và một phương thức tự viết **transform(String)** đã tồn tại (không phải chương trình biên dịch độc lập):

~~~java
Matcher matcher = pattern.matcher(input);
StringBuffer output = new StringBuffer();

while (matcher.find()) {
    String replacement = transform(matcher.group());
    matcher.appendReplacement(
            output,
            Matcher.quoteReplacement(replacement)
    );
}
matcher.appendTail(output);
String result = output.toString();
~~~

Với Java 9+, khi thao tác chỉ là tạo replacement từ từng match, có thể viết ngắn hơn:

~~~java
String result = pattern.matcher(input).replaceAll(
        match -> Matcher.quoteReplacement(transform(match.group()))
);
~~~

Hai cách đều cần quan tâm đến cú pháp replacement, và hai cách đều nên được thử với dữ liệu chứa $ và \. Vòng lặp thủ công vẫn hữu ích khi phải quản lý thêm trạng thái hoặc ghép đầu ra theo quy tắc riêng; callback tiện hơn cho phép biến đổi độc lập của từng match.

## 8. Điều kiện trong lambda: chỉ đổi một số match

Có những trường hợp regex nhận đúng tất cả đoạn cần xét, nhưng không phải đoạn nào cũng cần thay. Callback có thể quyết định giữ nguyên bằng cách trả lại chính group().

Đoạn mã sau giả định **input** đã được khai báo; mục đích là đưa ngoặc vuông quanh các số một chữ số và giữ nguyên các số khác:

~~~java
Pattern numbers = Pattern.compile("\\b\\d+\\b");
String result = numbers.matcher(input).replaceAll(match -> {
    int value = Integer.parseInt(match.group());
    String replacement = value < 10
            ? "[" + value + "]"
            : match.group();
    return Matcher.quoteReplacement(replacement);
});
~~~

Ngay cả ở nhánh giữ nguyên, lambda vẫn được gọi cho match đó. Nếu muốn tối ưu, thiết kế regex sao cho chỉ tìm đúng những đoạn thực sự cần thay khi khả thi. Cần xử lý trường hợp số quá lớn hoặc có định dạng khác trước khi parseInt.

Callback nên tập trung vào **tính toán chuỗi**. Tránh ghi database, gọi HTTP, thay đổi biến dùng chung hoặc tương tác bên ngoài trong một phép replaceAll; những side effect này dễ gây kết quả khó đoán nếu xử lý lỗi hoặc chạy lại. Nếu tính toán tốn kém cho mỗi match, hiệu suất thực tế phụ thuộc cả số match, độ phức tạp regex và công việc của hàm.

## 9. Lỗi thường gặp và cách phòng tránh

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Không biên dịch lambda cho replaceAll | Dùng Java 8 hoặc gọi String.replaceAll thay vì Matcher.replaceAll. | Sử dụng Java 9+, gọi Pattern.compile(...).matcher(input).replaceAll(lambda). |
| Bị lỗi khi giá trị chứa dấu $ | Dữ liệu bị hiểu là tham chiếu nhóm trong replacement. | Dùng Matcher.quoteReplacement cho chuỗi literal. |
| Dấu \ mất hoặc làm thay đổi ký tự phía sau | Replacement diễn giải \ như ký tự thoát. | Quote replacement literal; kiểm tra lại cách escape trong chuỗi Java. |
| match.group("name") không biên dịch trên Java 17 | MatchResult trong Java 17 dùng chỉ số nhóm. | Dùng group(1), group(2) theo vị trí. |
| NullPointerException khi xử lý group | Nhóm tùy chọn không tham gia, hoặc giá trị tra cứu là null. | Kiểm tra null, trả về chuỗi mặc định khác null. |
| NumberFormatException | Dữ liệu số quá dài hoặc không hợp lệ cho kiểu đang parse. | Giới hạn định dạng/giá trị; dùng long/BigInteger nếu cần. |
| ConcurrentModificationException | Lambda làm thay đổi trạng thái chính Matcher đang thay thế. | Chỉ dùng đối số MatchResult, không gọi find/reset trên Matcher đó. |
| Hàm không chạy | Không có match, hoặc regex không nhận dạng đoạn mong đợi. | Kiểm tra biểu thức, cờ biên dịch và đầu vào. |
| Thay quá nhiều phần nội dung | Regex quá rộng, ví dụ .* không có ràng buộc. | Thu hẹp mẫu, thêm các ranh giới phù hợp và test trường hợp phản ví dụ. |
| Quá chậm với dữ liệu dài | Regex gây backtracking hoặc hàm chạy nặng cho từng match. | Đo đạc, viết regex rõ ràng và tối ưu công việc của callback. |

## 10. Chọn giải pháp trong thực tế

Chọn **replaceAll(Function)** khi chuỗi thay thế cần được tính riêng theo nội dung match: chuyển đổi số, chuẩn hóa nhóm bắt, tra Map hay áp dụng điều kiện. Chọn **replaceAll(String)** khi chỉ cần khuôn cố định hoặc tham chiếu nhóm trong replacement. Chọn vòng lặp **find + appendReplacement + appendTail** khi cần kiểm soát việc ghép kết quả hoặc duy trì tương thích với Java cũ.

Khi kiểm thử, hãy bao phủ ít nhất: input không có match; nhiều match liền nhau; nhóm bắt tùy chọn; replacement chứa $ hoặc \; số vượt giới hạn; regex có thể khớp chuỗi rỗng; và callback báo lỗi. Một lỗi trong callback có thể làm toàn bộ lời gọi replaceAll thất bại, vì vậy hãy kiểm tra dữ liệu và quyết định chiến lược xử lý lỗi trước khi sử dụng trong ứng dụng.

Ghi nhớ: **Pattern xác định đoạn nào được chọn; Function quyết định từng chuỗi thay thế; Matcher diễn giải replacement và ghép kết quả.** Hiểu rõ ba bước này giúp sử dụng replaceAll với hàm chính xác, dễ kiểm thử và an toàn hơn.