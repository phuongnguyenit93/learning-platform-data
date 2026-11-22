# Pattern và Matcher cho nhiều lần xử lý trong Java

Trong Java, lớp **java.util.regex.Pattern** biểu diễn một biểu thức chính quy đã được biên dịch; lớp **java.util.regex.Matcher** dùng Pattern đó để kiểm tra, tìm kiếm, trích xuất hoặc thay thế nội dung trên một chuỗi đầu vào. Khi cần xử lý nhiều chuỗi hoặc tìm nhiều kết quả trong một chuỗi, hãy **biên dịch Pattern một lần và tạo Matcher phù hợp cho từng lượt xử lý**. Đây là cách sử dụng tự nhiên, dễ kiểm soát trạng thái và tránh biên dịch lại cùng một regex không cần thiết.

Bài này tập trung vào xử lý lặp: một regex dùng với nhiều đầu vào, một đầu vào chứa nhiều kết quả, tái sử dụng Matcher theo tuần tự, kiểm soát trạng thái và những lỗi thường gặp.

## 1. Phân biệt vai trò của Pattern và Matcher

| Thành phần | Chức năng | Trạng thái và khả năng chia sẻ |
| --- | --- | --- |
| Pattern | Lưu regex đã biên dịch và các cờ (flags). Tạo Matcher bằng matcher(input). | Bất biến (immutable), an toàn để nhiều luồng cùng dùng. |
| Matcher | Thực thi regex trên CharSequence; giữ đầu vào, vùng tìm kiếm, vị trí khớp vừa tìm, nhóm bắt, vị trí cho lần tìm tiếp theo. | Có trạng thái thay đổi (mutable), **không an toàn để dùng chung đồng thời giữa các luồng**. |
| PatternSyntaxException | Báo regex không hợp lệ tại thời điểm biên dịch. | Cần xử lý khi regex được nhập hoặc cấu hình động. |

Ví dụ minh họa ý tưởng (đoạn mã, chưa phải chương trình chạy độc lập):

~~~java
Pattern pattern = Pattern.compile("\\d+");   // Biên dịch một lần
Matcher first = pattern.matcher("Mã 17");    // Matcher cho đầu vào thứ nhất
Matcher second = pattern.matcher("Mã 42");   // Matcher khác cho đầu vào thứ hai

System.out.println(first.find());            // true
System.out.println(second.find());           // true
~~~

Hai Matcher độc lập có thể tiến qua đầu vào của mình mà không làm thay đổi trạng thái của nhau. Nếu cùng một regex được dùng thường xuyên, có thể lưu Pattern dưới dạng hằng số static final, trong một service hoặc trong một đối tượng được tái sử dụng.

### Vì sao không biên dịch trong mỗi vòng lặp?

Cách sau biên dịch lại regex mỗi lần duyệt phần tử:

~~~java
for (String line : lines) {
    Matcher matcher = Pattern.compile("\\bID-\\d{3}\\b").matcher(line);
    // ...
}
~~~

Nên chuyển phần biên dịch ra ngoài:

~~~java
Pattern idPattern = Pattern.compile("\\bID-\\d{3}\\b");
for (String line : lines) {
    Matcher matcher = idPattern.matcher(line);
    // ...
}
~~~

Tương tự, String.matches(regex) và Pattern.matches(regex, input) phù hợp khi kiểm tra nhanh một lần, nhưng chúng biên dịch regex cho mỗi lần gọi. Trong xử lý lặp với cùng regex, Pattern đã biên dịch cùng matcher(input).matches() tránh việc đó. Lợi ích thực tế phụ thuộc độ phức tạp regex và tần suất gọi; tối ưu quan trọng nhất vẫn là tính đúng của regex.

## 2. Một Pattern xử lý nhiều dòng, mỗi dòng có nhiều kết quả

Yêu cầu: tìm tất cả mã đúng định dạng ID- theo sau bởi **đúng ba chữ số**, xuất mã, phần số và vị trí. Từ ranh giới \b giúp không nhận mã dính sát ký tự thuộc từ; ký hiệu (?<number>...) đặt tên cho nhóm bắt số.

Tệp **RegexReuseDemo.java** (Java 17+):

~~~java
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexReuseDemo {
    private static final Pattern ID_PATTERN =
            Pattern.compile("\\bID-(?<number>\\d{3})\\b");

    public static void main(String[] args) {
        List<String> lines = List.of(
                "Đơn ID-123, ID-045; mã ID-7 không hợp lệ.",
                "ID-999 kết thúc; xid-111 không khớp."
        );

        for (String line : lines) {
            Matcher matcher = ID_PATTERN.matcher(line);
            while (matcher.find()) {
                System.out.printf(
                        "%s | mã=%s | vị trí=[%d,%d)%n",
                        matcher.group(),
                        matcher.group("number"),
                        matcher.start(),
                        matcher.end()
                );
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RegexReuseDemo.java
java RegexReuseDemo
~~~

Kết quả:

~~~text
ID-123 | mã=123 | vị trí=[4,10)
ID-045 | mã=045 | vị trí=[12,18)
ID-999 | mã=999 | vị trí=[0,6)
~~~

Giải thích:

1. **ID_PATTERN** chỉ biên dịch một lần khi lớp được khởi tạo. Mỗi dòng nhận một Matcher mới bằng matcher(line).
2. **find()** tìm kết quả tiếp theo. Gọi liên tiếp trong vòng while duyệt các kết quả không chồng lấn từ trái sang phải; khi hết kết quả, find() trả về false.
3. **group()** (hay group(0)) là toàn bộ đoạn khớp; **group("number")** là nội dung của nhóm được đặt tên.
4. **start()** là vị trí bắt đầu, **end()** là vị trí *ngay sau* ký tự cuối. Vì vậy khoảng vị trí là [start, end). Chỉ số tính theo đơn vị char/UTF-16 của Java, không nhất thiết tương đương số ký tự người đọc thấy nếu có ký tự Unicode bổ sung.
5. ID-7 không đủ ba chữ số. xid-111 không khớp vì chữ ID viết hoa trong regex và không nằm tại ranh giới từ thích hợp.

Dấu ngoặc nhọn \d{3} quy định số lượng, còn \b định nghĩa ranh giới từ; nếu quy tắc nghiệp vụ yêu cầu một mã đứng độc lập theo cách khác (chẳng hạn dấu gạch dưới, ký tự Unicode hoặc quy tắc mã riêng), cần thiết kế ranh giới đúng yêu cầu. Regex trên minh họa một định dạng cụ thể, không phải bộ kiểm tra mọi loại mã định danh.

## 3. Tái sử dụng chính đối tượng Matcher bằng reset()

Trong một luồng xử lý tuần tự, khi muốn giảm số Matcher được tạo ra, có thể giữ một Matcher và gọi **reset(newInput)** trước mỗi đầu vào. Matcher sẽ quên kết quả tìm kiếm trước đó và bắt đầu lại trên chuỗi mới.

Tệp **MatcherResetDemo.java**:

~~~java
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MatcherResetDemo {
    public static void main(String[] args) {
        Pattern numberPattern = Pattern.compile("\\b\\d+\\b");
        Matcher matcher = numberPattern.matcher("");

        for (String line : List.of("A: 17, B: 22", "C: 8")) {
            matcher.reset(line);
            while (matcher.find()) {
                System.out.printf("%s -> %s%n", line, matcher.group());
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MatcherResetDemo.java
java MatcherResetDemo
~~~

Kết quả:

~~~text
A: 17, B: 22 -> 17
A: 17, B: 22 -> 22
C: 8 -> 8
~~~

Có hai kiểu reset thường gặp:

- **reset()**: dùng lại đầu vào hiện tại, bắt đầu tìm lại từ đầu.
- **reset(CharSequence input)**: đổi sang đầu vào mới, đặt lại trạng thái tìm kiếm và vùng tìm kiếm mặc định về toàn bộ đầu vào mới.

Sau reset, nhóm bắt và vị trí khớp trước đó không còn hợp lệ. Chỉ gọi group(), start(), end() sau khi matches(), lookingAt() hoặc find() đã trả về true. Nếu chưa có kết quả khớp hợp lệ, các phương thức này ném IllegalStateException.

**Lựa chọn mặc định:** dùng Pattern chung + Matcher mới cho từng đầu vào vì mã rõ ràng, ít lỗi trạng thái. Chỉ tái sử dụng chính Matcher khi xử lý tuần tự, kiểm soát vòng đời của nó và có lý do đo đạc được. Không chia sẻ một Matcher tái sử dụng cho các tác vụ chạy song song.

## 4. Chọn phương thức khi tái sử dụng Pattern

Một `Pattern` đã biên dịch có thể dùng cho cả ba cách kiểm tra; **phương thức gọi trên Matcher** quyết định câu hỏi của từng lượt xử lý:

| Phương thức | Với regex `\d+` và input `"123abc456"` | Dùng khi |
| --- | --- | --- |
| `matches()` | `false`: còn phần `abc456` ngoài mẫu | Xác thực toàn bộ vùng dữ liệu |
| `lookingAt()` | `true`: tiền tố `"123"` khớp | Nhận diện token ở đầu vùng |
| `find()` | `true`: tìm `"123"`, lần kế tiếp tìm `"456"` | Duyệt nhiều đoạn khớp liên tiếp |

Khi kiểm tra các chế độ **độc lập**, hãy gọi `digits.matcher(input)` để tạo Matcher riêng cho mỗi phép thử. Khi cần thu mọi kết quả của `find()`, giữ **một Matcher xuyên suốt vòng lặp** để vị trí tìm kiếm tiến đúng; chỉ `reset()` nếu cố ý bắt đầu lại. Phân biệt phạm vi của ba phương thức là nền tảng, còn trọng tâm của bài này là quản lý vòng đời `Pattern` và trạng thái `Matcher` trong xử lý nhiều lần.

## 5. Làm việc với các nhóm và vị trí khi lặp find()

- group(0) hoặc group(): toàn bộ đoạn khớp.
- group(1), group(2), ...: các nhóm bắt theo thứ tự dấu ngoặc tròn mở. group("name") truy cập nhóm đặt tên.
- start(), end() là vị trí của toàn bộ đoạn khớp; start(1), end(1) là vị trí nhóm số 1; tương tự có phiên bản nhận tên nhóm.
- Một nhóm bắt là tùy chọn có thể không tham gia vào lần khớp: group tương ứng trả về null, còn start/end của nhóm trả về -1. Điều này khác với nhóm tham gia nhưng khớp chuỗi rỗng.
- Dùng (?:...) khi chỉ cần gom biểu thức mà **không muốn tạo nhóm bắt**; điều này giúp chỉ số nhóm ổn định và dễ đọc hơn.

Ví dụ ý tưởng: regex (ID)-(\\d{3}) có group(1) là "ID" và group(2) là ba chữ số; regex (?:ID)-(\\d{3}) chỉ có một nhóm bắt số. Với dữ liệu trích xuất theo nhiều nhóm, kiểm tra sự hiện diện của nhóm tùy chọn trước khi chuyển đổi kiểu hoặc thao tác chuỗi.

Cẩn thận với biểu thức có thể khớp **chuỗi rỗng** (chẳng hạn .* hoặc các lượng từ tùy chọn). find() xử lý việc tiến tới vị trí tiếp theo cho các lần khớp độ dài bằng không, nhưng đoạn mã tự cập nhật chỉ số quét bằng end() có thể mắc vòng lặp nếu không xử lý trường hợp start() == end(). Đừng mặc định mọi lần find() đều tiêu thụ ít nhất một ký tự.

## 6. Các cờ biên dịch và cách thoát ký tự

Có thể khai báo cờ ở thời điểm biên dịch:

~~~java
Pattern keyword = Pattern.compile(
        "\\bjava\\b",
        Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE
);
~~~

- **CASE_INSENSITIVE**: khớp không phân biệt hoa/thường; kết hợp UNICODE_CASE khi cần đối chiếu chữ cái Unicode theo quy tắc case-insensitive của Java.
- **MULTILINE**: thay đổi cách ^ và $ nhận diện đầu/cuối dòng trong một chuỗi nhiều dòng; không biến matches() thành thao tác tìm từng dòng.
- **DOTALL**: dấu chấm . có thể khớp cả ký tự xuống dòng. Không liên quan trực tiếp đến việc tái sử dụng Matcher.

Trong **chuỗi Java**, một dấu gạch chéo ngược của cú pháp regex thường phải viết thành hai dấu: regex \d được truyền vào Pattern từ chuỗi Java "\\d"; regex \b từ "\\b". Nếu viết "\b" đơn lẻ bên trong chuỗi Java, đó là ký tự backspace của Java, không phải biểu thức ranh giới từ của regex.

Nếu đầu vào của người dùng phải được tìm **theo nghĩa văn bản nguyên trạng**, dùng Pattern.quote(text) thay vì ghép trực tiếp vào regex; nếu nội dung thay thế có ký tự $ hoặc \, dùng Matcher.quoteReplacement(replacement) để giữ nguyên nghĩa. Đoạn mã minh họa sau giả định đã có ba biến kiểu String:

~~~java
Pattern literal = Pattern.compile(Pattern.quote(searchText));
Matcher matcher = literal.matcher(sourceText);
String result = matcher.replaceAll(Matcher.quoteReplacement(replacementText));
~~~

Nếu không quote, ký tự đặc biệt trong searchText có thể trở thành toán tử regex; ký tự $ hoặc dấu \ trong replacementText có thể được hiểu là tham chiếu nhóm hoặc cú pháp thoát. Khi cần thay thế có chủ đích theo nhóm, hãy dùng đúng cú pháp tham chiếu nhóm của Matcher thay vì quoteReplacement.

## 7. Xử lý nhiều lần trong chương trình và ứng dụng đa luồng

Với API/service nhận nhiều request hoặc worker chạy song song, Pattern có thể dùng chung an toàn:

~~~java
private static final Pattern TOKEN = Pattern.compile("[A-Za-z0-9]+");

static boolean containsToken(String input) {
    return TOKEN.matcher(input).find();
}
~~~

Mỗi lần gọi containsToken tạo Matcher cục bộ. Vì Matcher giữ vị trí duyệt và tham chiếu đến chuỗi đang xử lý, không lưu một Matcher duy nhất vào biến static hoặc chia sẻ nó giữa các request. Đồng bộ hóa có thể ngăn truy cập đồng thời nhưng thường tạo ra thiết kế khó hiểu và không cần thiết; Pattern bất biến + Matcher cục bộ là đủ cho đa số trường hợp.

Khi regex được người dùng cung cấp, nên xác thực và kiểm soát cấu hình: Pattern.compile có thể ném PatternSyntaxException; một số biểu thức bị backtracking mạnh có thể tốn nhiều CPU trên dữ liệu dài hoặc cố ý gây khó. Việc **cache Pattern** chỉ tránh biên dịch lặp, **không loại bỏ** rủi ro regex xử lý chậm. Với regex động, cần cân nhắc số mẫu cache, giới hạn kích thước dữ liệu, thử nghiệm tình huống xấu và thiết kế biểu thức tránh các nhánh lặp mơ hồ.

## 8. Những lỗi dễ gặp và cách sửa

| Tình huống | Nguyên nhân | Cách làm phù hợp |
| --- | --- | --- |
| Chỉ thu được kết quả đầu tiên | Dùng một lần if (matcher.find()) rồi dừng. | Dùng while (matcher.find()) khi cần toàn bộ kết quả. |
| Không tìm lại được từ đầu | Matcher đã tiến đến cuối sau nhiều lần find(). | Gọi reset() trước một lượt quét mới hoặc tạo matcher(input) khác. |
| Kết quả dòng mới sai / không có | Tái sử dụng Matcher mà quên reset(newInput). | Reset đúng đầu vào trước mỗi lượt. |
| group()/start()/end() ném IllegalStateException | Chưa có lần khớp thành công đang hợp lệ, hoặc đã reset. | Chỉ truy cập sau kết quả true và trước khi làm mất trạng thái đó. |
| Xác thực toàn chuỗi nhưng vẫn chấp nhận đoạn con | Dùng find() thay vì matches(). | Dùng matches() cho toàn bộ đầu vào. |
| Chậm khi lặp hàng nghìn dòng | Gọi Pattern.compile hoặc String.matches lặp lại với cùng regex; hoặc regex gây backtracking nặng. | Biên dịch Pattern một lần, đo hiệu năng và điều chỉnh biểu thức nếu cần. |
| Lỗi khi chạy song song | Nhiều luồng dùng chung một Matcher mutable. | Chia sẻ Pattern, tạo Matcher riêng theo mỗi tác vụ. |
| Tìm chuỗi ký tự literal sai | Nội dung nhập chứa ., +, [, (, ... và bị hiểu là regex. | Dùng Pattern.quote() cho mẫu literal. |
| Thay thế có $ hoặc \ bị lỗi | Chuỗi thay thế bị hiểu thành cú pháp nhóm/escape. | Dùng Matcher.quoteReplacement() cho phần thay thế literal. |

## 9. Cách chọn thiết kế cho từng nhu cầu

- **Cùng regex, nhiều chuỗi:** biên dịch Pattern một lần; với mỗi chuỗi, gọi pattern.matcher(input).
- **Một chuỗi, nhiều đoạn khớp:** một Matcher với while (matcher.find()); đọc group/start/end ngay trong mỗi lần lặp.
- **Một Matcher quét lại hoặc đổi đầu vào theo thứ tự:** gọi reset() hoặc reset(newInput) trước lần quét tiếp theo.
- **Chỉ xác thực một chuỗi:** gọi matcher(input).matches(); đừng nhầm với find().
- **Cùng Pattern trên nhiều luồng:** chia sẻ Pattern; Matcher thuộc về từng luồng/từng tác vụ.
- **Regex hoặc nội dung thay thế từ bên ngoài:** kiểm tra lỗi cú pháp, quote nội dung literal đúng cách và đánh giá rủi ro hiệu năng.

Điểm cần nắm vững là **Pattern giữ quy tắc; Matcher giữ trạng thái của một lượt xử lý**. Quản lý hai vòng đời này đúng giúp mã regex vừa rõ ràng vừa ổn định khi phải xử lý nhiều chuỗi và nhiều kết quả.