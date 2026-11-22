# Lớp ký tự, lượng từ, neo và nhóm bắt trong Java Regex

Biểu thức chính quy (regular expression, regex) mô tả mẫu ký tự để **kiểm tra**, **tìm kiếm**, **trích xuất** hoặc **thay thế** chuỗi. Bốn thành phần quan trọng là: **lớp ký tự** quyết định một vị trí được phép chứa ký tự gì; **lượng từ** quyết định một đơn vị xuất hiện bao nhiêu lần; **neo/ranh giới** giới hạn vị trí khớp; và **nhóm bắt** gom mẫu, lưu đoạn đã khớp để truy xuất hoặc tham chiếu lại. Trong Java, các mẫu này được thực thi qua `java.util.regex.Pattern` và `Matcher`.

## 1. Đọc regex đúng trong Java

Có hai lớp cú pháp cần phân biệt:

- **Regex**: `\d{2}` nghĩa là hai chữ số; `\b` nghĩa là ranh giới từ.
- **Java string literal**: dấu `\` phải được viết thành `\\`. Vì vậy regex `\d{2}` được truyền bằng chuỗi Java `"\\d{2}"`, regex `\b` bằng `"\\b"`. Nếu viết `"\b"`, Java tạo ký tự backspace thay cho ranh giới từ.

| Mẫu regex thực tế | Chuỗi Java tương ứng | Ý nghĩa |
| --- | --- | --- |
| `\d+` | `"\\d+"` | Một hoặc nhiều chữ số |
| `\bcat\b` | `"\\bcat\\b"` | Từ `cat` độc lập |
| `^[A-Z]{2}\d{3}$` | `"^[A-Z]{2}\\d{3}$"` | Toàn chuỗi là hai chữ hoa rồi ba chữ số |
| `\.` | `"\\."` | Dấu chấm thật, không phải ký hiệu `.` của regex |

`Pattern.compile(regex)` biên dịch mẫu; `pattern.matcher(input)` tạo `Matcher` cho một đầu vào. Ba cách kiểm tra thường gặp:

- `matcher.matches()` yêu cầu **toàn bộ đầu vào** khớp mẫu.
- `matcher.find()` tìm **đoạn con kế tiếp** khớp mẫu; gọi lặp để duyệt các đoạn khớp.
- `matcher.lookingAt()` yêu cầu khớp **từ đầu vùng tìm kiếm**, nhưng không bắt buộc tới hết.

Ví dụ: với regex `\d+` và đầu vào `"abc123xyz"`, `find()` thành công và lấy `123`, còn `matches()` và `lookingAt()` đều trả về `false`. Chỉ gọi `group()`, `start()` hoặc `end()` sau khi một thao tác khớp thành công, nếu không có thể gặp `IllegalStateException`.

## 2. Lớp ký tự (character classes)

Lớp ký tự thường khớp **một ký tự** trong tập cho phép; lượng từ phía sau mới làm nó lặp nhiều lần.

| Cú pháp regex | Ý nghĩa | Ví dụ khớp |
| --- | --- | --- |
| `[abc]` | Một trong `a`, `b`, `c` | `b` |
| `[^abc]` | Một ký tự không thuộc tập `a`, `b`, `c` | `x` |
| `[a-z]` | Một ký tự trong khoảng từ `a` đến `z` | `m` |
| `[A-Za-z0-9_]` | Một chữ Latin, chữ số ASCII hoặc `_` | `T`, `7`, `_` |
| `[a-f&&[^b-d]]` | Giao của `a`–`f` với phần bù `b`–`d` | `a`, `e`, `f` |
| `\d` / `\D` | Chữ số / không phải chữ số | `5` / `Z` |
| `\s` / `\S` | Ký tự trắng / không phải ký tự trắng | dấu cách / `A` |
| `\w` / `\W` | Ký tự thuộc nhóm *word* / không thuộc *word* | `a` / `!` |
| `\p{L}` | Một ký tự Unicode thuộc nhóm chữ cái | `Đ`, `ê`, `A` |

Phủ định trong lớp ký tự là dấu `^` **ngay sau `[`**: `[^0-9]` nhận một ký tự không phải chữ số ASCII. Dấu `^` đứng ngoài lớp ký tự là neo đầu dòng/đầu vùng (phần 4), không phải phủ định. Dấu gạch nối `-` có thể tạo khoảng: `[a-z]`; nếu muốn dấu `-` thật, có thể đặt đầu/cuối như `[-+]` hoặc escape phù hợp. Các ký tự `]`, `\`, `^`, `-` có ý nghĩa tùy vị trí trong lớp, nên cần kiểm tra cách đặt/escape thay vì giả định chúng luôn là ký tự thường.

**Chú ý về Unicode:** mặc định trong Java, `\d`, `\w` và nhiều lớp viết tắt theo cách dùng ASCII; đừng mặc nhiên cho rằng `\w+` bao trùm mọi tên tiếng Việt. Dùng `\p{L}` khi cần các chữ cái Unicode, hoặc bật `Pattern.UNICODE_CHARACTER_CLASS` (cờ nhúng `(?U)`) để các lớp viết tắt và POSIX class được diễn giải theo Unicode. Quy tắc dữ liệu còn quan trọng hơn regex: tên người có thể gồm dấu cách, dấu nháy, gạch nối hoặc dấu kết hợp; một lớp chữ cái đơn thuần chưa đủ làm bộ kiểm tra tên hoàn chỉnh.

**Dấu chấm `.` không phải lớp `[.]`:** `.` khớp gần như mọi ký tự nhưng mặc định **không khớp ký tự kết thúc dòng**; cờ `Pattern.DOTALL` (`(?s)`) cho phép `.` khớp cả các ký tự đó. `\.` hoặc `[.]` mới khớp dấu chấm thật. Lớp `[\s\S]` có thể khớp cả ký tự trắng lẫn không trắng, nhưng thường khó đọc hơn một mẫu rõ ràng có `DOTALL`.

## 3. Lượng từ (quantifiers)

Lượng từ tác động lên **đơn vị ngay trước nó**: một ký tự, một lớp ký tự hoặc một nhóm. Chẳng hạn `ab+` là `a` rồi một hoặc nhiều `b`, còn `(ab)+` lặp cả cặp `ab`.

| Lượng từ | Số lần xuất hiện | Ví dụ |
| --- | --- | --- |
| `X?` | 0 hoặc 1 | `colou?r` nhận `color`, `colour` |
| `X*` | 0 trở lên | `a*` nhận cả chuỗi rỗng |
| `X+` | 1 trở lên | `a+` nhận `a`, `aaa` |
| `X{n}` | Chính xác `n` | `\d{4}` nhận bốn chữ số |
| `X{n,}` | Ít nhất `n` | `[A-Z]{2,}` |
| `X{n,m}` | Từ `n` đến `m` (gồm hai đầu) | `\d{2,4}` |

Một lượng từ có ba chiến lược:

1. **Tham lam (greedy)**, ví dụ `.*`, `a+`, `a{2,4}`: thử lấy nhiều nhất có thể, **có thể quay lui** để phần còn lại khớp.
2. **Tiết chế (reluctant/lazy)**, ví dụ `.*?`, `a+?`, `a{2,4}?`: thử lấy ít nhất trước, rồi mở rộng nếu cần.
3. **Sở hữu (possessive)**, ví dụ `.*+`, `a++`, `a{2,4}+`: lấy nhiều nhất **và không trả lại ký tự** qua backtracking.

Đối với đầu vào `<a><b>`, mẫu `<.*>` nhận cả `<a><b>` do tham lam; mẫu `<.*?>` cho `find()` trả về `<a>` rồi `<b>`. Tuy nhiên cách tìm thẻ XML/HTML đúng nghĩa cần parser tương ứng: regex minh họa này không xử lý thẻ lồng nhau, dấu nháy và cấu trúc ngôn ngữ đánh dấu.

~~~java
// QuantifierDemo.java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class QuantifierDemo {
    public static void main(String[] args) {
        String input = "<a><b>";
        Matcher greedy = Pattern.compile("<.*>").matcher(input);
        if (greedy.find()) {
            System.out.println("Greedy: " + greedy.group());
        }

        Matcher reluctant = Pattern.compile("<.*?>").matcher(input);
        while (reluctant.find()) {
            System.out.println("Reluctant: " + reluctant.group());
        }

        System.out.println("a+a on aaa: " + Pattern.matches("a+a", "aaa"));
        System.out.println("a++a on aaa: " + Pattern.matches("a++a", "aaa"));
    }
}
~~~

Chạy bằng `javac --release 17 QuantifierDemo.java` rồi `java QuantifierDemo`:

~~~text
Greedy: <a><b>
Reluctant: <a>
Reluctant: <b>
a+a on aaa: true
a++a on aaa: false
~~~

Ở hai dòng cuối, `a+a` có thể trả lại một `a` để phần `a` cuối khớp. `a++a` đã chiếm hết `aaa`, không backtrack nên thất bại. `*?` không có nghĩa là “không bao giờ lấy thêm”: nó vẫn mở rộng khi phần mẫu phía sau yêu cầu.

## 4. Neo và ranh giới (anchors, boundaries)

Neo kiểm tra **vị trí**, thường không tiêu thụ ký tự. Vì vậy `^\d+$` mô tả một dãy chữ số chiếm cả chuỗi trong cách kiểm tra thông thường; chỉ `\d+` có thể tìm một đoạn chữ số nằm giữa văn bản.

| Ký hiệu regex | Vị trí được khớp |
| --- | --- |
| `^` | Đầu đầu vào/vùng; với `MULTILINE`, còn là đầu từng dòng |
| `$` | Cuối đầu vào/vùng, có quy tắc đặc biệt trước ký tự kết thúc dòng cuối; với `MULTILINE`, còn là cuối từng dòng |
| `\A` | Đầu tuyệt đối của đầu vào theo vùng áp dụng |
| `\z` | Cuối tuyệt đối của đầu vào theo vùng áp dụng |
| `\Z` | Cuối đầu vào, có thể ngay trước ký tự kết thúc dòng cuối |
| `\b` | Ranh giới từ: vị trí chuyển giữa ký tự *word* và không-*word* |
| `\B` | Vị trí không phải ranh giới từ |
| `\G` | Cuối lần khớp trước (hữu ích khi muốn các lần `find()` liền kề) |

`Pattern.MULTILINE` (cờ `(?m)`) thay đổi cách `^` và `$` hoạt động quanh các dòng. Ví dụ `Pattern.compile("^foo$", Pattern.MULTILINE).matcher("foo\nbar").find()` là `true` vì khớp dòng `foo`; nhưng `matches()` trên toàn chuỗi đó vẫn là `false`. `DOTALL` thay đổi hành vi của **`.`**, không thay vai trò của `^` và `$`.

`\bcat\b` tìm từ `cat` độc lập trong `"a cat!"`, trong khi mẫu `cat` có thể khớp cả trong `"concatenate"`. Ranh giới từ **không giống dấu cách**: dấu câu, số, dấu gạch dưới, dấu kết hợp và Unicode có thể làm kết quả khác trực giác ngôn ngữ tự nhiên. Nếu quy tắc nghiệp vụ là “từ” trong một ngôn ngữ cụ thể, phải kiểm thử chuỗi thực tế.

Khi kiểm tra **toàn chuỗi**, ưu tiên `matcher.matches()` vì ý định rõ; khi muốn đọc **từng dòng** bằng `find()`, dùng `MULTILINE` có chủ đích; khi cần neo kết thúc tuyệt đối trong mẫu có thể được dùng bằng `find()`, cân nhắc `\A` và `\z` thay vì giả định `$` luôn có cùng nghĩa.

## 5. Nhóm bắt (capturing groups) và nhóm không bắt

Dấu ngoặc tròn làm hai việc: **gom các nhánh/đơn vị để lượng từ tác động** và, theo mặc định, **ghi nhớ đoạn đã khớp**.

| Cú pháp | Công dụng |
| --- | --- |
| `(ab)+` | Nhóm bắt `ab`, lặp ít nhất một lần |
| `(?:ab)+` | Nhóm **không bắt**: gom `ab` để lặp nhưng không tạo chỉ số nhóm |
| `(cat|dog)` | Nhóm bắt một trong hai nhánh |
| `(?<day>\d{2})` | Nhóm bắt có tên `day` |
| `\1` | Tham chiếu lại **nội dung** đã khớp ở nhóm bắt số 1 |
| `\k<day>` | Tham chiếu lại nội dung nhóm tên `day` |

Các nhóm bắt được đánh số **1, 2, ...** theo thứ tự dấu `(` mở của nhóm bắt khi duyệt mẫu từ trái sang phải; nhóm `0` là **toàn bộ lần khớp**. `(?:...)` không tăng số nhóm. Sau khi `find()` hoặc `matches()` thành công, `group(1)`, `group("day")`, `start(1)`, `end(1)` truy xuất nội dung và vị trí; `end()` là chỉ số **exclusive**. Vị trí Java dùng chỉ số UTF-16, nên với ký tự bổ sung Unicode (ngoài BMP) không đồng nhất với chỉ số ký tự hiển thị. `groupCount()` cho biết số nhóm bắt, không tính nhóm `0`.

Nếu một nhánh hoặc một nhóm tùy chọn không tham gia lần khớp, `group(n)` của nhóm đó là `null` (và `start(n)`, `end(n)` là `-1`). Phân biệt “không tham gia” với nhóm có khớp **chuỗi rỗng**. Nếu nhóm nằm dưới lượng từ và khớp nhiều lần, `group(n)` không phải danh sách tất cả lần bắt; thông thường nó giữ giá trị bắt sau cùng. Muốn lấy mọi lần xuất hiện, hãy thiết kế mẫu và lặp `find()` phù hợp.

Tên nhóm trong Java có dạng tên chữ Latin bắt đầu bằng chữ, theo sau là chữ/số; ví dụ `day`, `year2`. Không dùng lại cùng một tên trong một mẫu. Nhóm không bắt phù hợp khi chỉ cần gom, ví dụ `(?:https?://)?`, giúp chỉ số nhóm bắt ổn định hơn.

### Ví dụ chạy được: kiểm tra, bắt nhóm có tên và vị trí

~~~java
// RegexDemo.java
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexDemo {
    public static void main(String[] args) {
        Pattern username = Pattern.compile("^[A-Za-z][A-Za-z0-9_]{2,11}$");
        for (String value : List.of("an", "anh_2026", "3abc", "abc_DEF012")) {
            System.out.println(value + " -> " + username.matcher(value).matches());
        }

        Pattern date = Pattern.compile("(?<day>\\d{2})/(?<month>\\d{2})/(?<year>\\d{4})");
        Matcher matcher = date.matcher("Due: 03/11/2026; 25/12/2026.");
        while (matcher.find()) {
            System.out.println(matcher.group(0) + " -> "
                    + matcher.group("day") + "/" + matcher.group("month")
                    + "/" + matcher.group("year")
                    + " [" + matcher.start() + ", " + matcher.end() + ")");
        }
    }
}
~~~

Chạy `javac --release 17 RegexDemo.java` và `java RegexDemo`:

~~~text
an -> false
anh_2026 -> true
3abc -> false
abc_DEF012 -> true
03/11/2026 -> 03/11/2026 [5, 15)
25/12/2026 -> 25/12/2026 [17, 27)
~~~

Mẫu tên đăng nhập dùng **lớp ký tự** và **lượng từ `{2,11}`**: ký tự đầu là chữ Latin, 2–11 ký tự còn lại là chữ/số/`_`, nghĩa là tổng cộng **3–12 ký tự**. `matches()` kiểm tra toàn bộ. Mẫu ngày dùng ba nhóm có tên; `find()` tìm từng đoạn con. Đây là ví dụ **trích xuất theo hình dạng `dd/MM/yyyy`**, không xác nhận ngày hợp lệ: `99/99/2026` vẫn khớp regex; hãy dùng `java.time` để kiểm tra giá trị ngày thực tế.

### Tham chiếu ngược: tìm từ bị lặp

Regex `\b(?<word>[A-Za-z]+)\s+\k<word>\b` tìm hai từ giống nhau ngăn bởi khoảng trắng. Từ thứ hai phải có **đúng nội dung nhóm `word` vừa bắt**, không đơn thuần là một từ bất kỳ. Cần cờ `CASE_INSENSITIVE` nếu muốn `Go go` khớp:

~~~java
// BackreferenceDemo.java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class BackreferenceDemo {
    public static void main(String[] args) {
        Pattern repeatedWord = Pattern.compile(
                "\\b(?<word>[A-Za-z]+)\\s+\\k<word>\\b",
                Pattern.CASE_INSENSITIVE);
        Matcher matcher = repeatedWord.matcher("Go go, step ahead, Java java.");
        while (matcher.find()) {
            System.out.println(matcher.group());
        }
    }
}
~~~

Chạy `javac --release 17 BackreferenceDemo.java` và `java BackreferenceDemo`:

~~~text
Go go
Java java
~~~

**Phân biệt:** tham chiếu ngược `\1` hoặc `\k<word>` yêu cầu lặp lại **chính giá trị đã khớp**; còn `([A-Za-z]+)\s+([A-Za-z]+)` chỉ đòi hai từ bất kỳ. Trong Java string literal, viết tham chiếu số 1 là `"\\1"`, tham chiếu tên là `"\\k<word>"`.

## 6. Ghép các thành phần để giải bài toán

Quy trình xây mẫu dễ kiểm tra:

1. Viết rõ **định dạng dữ liệu** và các chuỗi hợp lệ/không hợp lệ; quyết định cần so toàn chuỗi hay tìm đoạn con.
2. Chọn **lớp ký tự** cho từng vị trí (`[A-Z]`, `\d`, `\p{L}`, ...), xét cả Unicode.
3. Thêm **lượng từ** diễn tả độ dài (`{4}`, `{2,8}`, `+`), đặt ngoặc cho đơn vị cần lặp (`(?:ab){3}`).
4. Thêm **neo/ranh giới** khi thực sự cần, rồi chọn `matches()` hay `find()` tương ứng.
5. Chỉ tạo **nhóm bắt** cho dữ liệu cần lấy/so sánh; dùng `(?:...)` cho phần gom còn lại.
6. Thử cả trường hợp rỗng, dài quá, ký tự lạ, xuống dòng, Unicode và chuỗi gây nhiều cách backtracking.

Ví dụ biểu diễn một mã có hai chữ Latin viết hoa, dấu `-` rồi bốn chữ số là `^[A-Z]{2}-\d{4}$` (Java string: `"^[A-Z]{2}-\\d{4}$"`). Mẫu cho phép `AB-1234`, bác bỏ `A-1234`, `AB_1234` và `AB-12345` khi dùng `matches()`. Nếu bắt phần mã để xử lý riêng: `^([A-Z]{2})-(\d{4})$`; lấy mã chữ qua `group(1)`, mã số qua `group(2)` sau khi khớp thành công.

## 7. Các lỗi thường gặp và cách tránh

- **Quên hai mức escape**: Java `"\\d"` mới truyền regex `\d`; Java `"\b"` là backspace. Nếu regex viết ở tệp cấu hình hay được đọc từ đầu vào, quy tắc escape của **Java source** không còn áp dụng nguyên xi.
- **Nhầm `find()` với `matches()`**: `find()` có thể chấp nhận một phần input. Với kiểm tra định dạng toàn chuỗi, dùng `matches()` để tránh lọt tiền tố/hậu tố không hợp lệ.
- **Nhầm `.` với dấu chấm thật**, `^` trong/ngoài `[]`, hoặc `ab+` với `(ab)+`; cần xác định đơn vị regex mà toán tử tác động.
- **Cho rằng lazy luôn nhận đúng cấu trúc**: `<.*?>` minh họa sự khác biệt với greedy, không thay parser HTML/XML/JSON. Regex không tự kiểm tra được cấu trúc lồng nhau phức tạp.
- **Dùng quá nhiều nhóm bắt**: thay nhóm chỉ để gom bằng `(?:...)` để `group(1)`, `group(2)` không bị đổi nghĩa khi sửa mẫu.
- **Không xử lý nhóm tùy chọn**: `group(n)` có thể là `null`; không gọi `group()` khi `find()`/`matches()` thất bại.
- **Đồng nhất Unicode với ASCII**: `[A-Z]`, `\w`, `\d` có các phạm vi khác nhau; thử dữ liệu có dấu, ký tự bổ sung, dấu kết hợp và bật cờ Unicode khi phù hợp.
- **Backtracking tốn kém**: các lượng từ lồng nhau mơ hồ như `(a+)+$` có thể rất chậm trên chuỗi dài gần khớp. Hạn chế đầu vào, dùng lớp ký tự cụ thể, cấu trúc không mơ hồ, hoặc lượng từ sở hữu khi bảo toàn đúng ý nghĩa. `Pattern` biên dịch tái sử dụng được và an toàn khi chia sẻ; mỗi `Matcher` giữ trạng thái riêng, không dùng chung đồng thời giữa các thread.
- **Nhúng văn bản người dùng vào regex**: nếu cần tìm chuỗi **nguyên văn**, dùng `Pattern.quote(userText)` thay vì ghép trực tiếp các ký tự đặc biệt vào regex. Khi thay thế và muốn đưa chuỗi thay thế vào nguyên văn, xét `Matcher.quoteReplacement(replacementText)` vì `$` và `\` có nghĩa đặc biệt trong replacement.

## 8. Tự kiểm tra hiểu bài

1. Vì sao `Pattern.matches("a+", "baaa")` là `false` nhưng `Pattern.compile("a+").matcher("baaa").find()` là `true`?
2. Với chuỗi `"abab"`, `(ab){2}` và `ab{2}` có cùng kết quả khi dùng `matches()` không? Lượng từ đang áp dụng lên đơn vị nào?
3. Trên `<a><b>`, `.*` và `.*?` khiến `<...>` nhận đoạn khác nhau thế nào, và vì sao `.*+` có thể làm mẫu thất bại?
4. Viết mẫu bắt riêng `year`, `month`, `day` trong chuỗi `"2026-10-23"` rồi kiểm tra vì sao regex định dạng vẫn chưa thay thế kiểm tra ngày lịch.
5. Khi cần kiểm tra một chuỗi kết thúc **thực sự** tại vị trí cuối đầu vào, tại sao `\z` rõ ràng hơn `$`?

**Ghi nhớ:** lớp ký tự = *ký tự gì*; lượng từ = *bao nhiêu lần*; neo/ranh giới = *ở vị trí nào*; nhóm bắt = *phần nào cần gom/lấy lại*. Chọn `matches()` cho kiểm tra toàn chuỗi, `find()` cho tìm/trích xuất, và dùng ví dụ kiểm thử với dữ liệu thật để xác minh từng lớp quy tắc.
