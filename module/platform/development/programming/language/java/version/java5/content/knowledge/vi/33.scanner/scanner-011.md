# Tìm mẫu bằng findInLine(), findWithinHorizon() và skip()

## 1. Khi ranh giới token không còn đủ

Đọc bằng `next()` hoặc `nextInt()` phù hợp khi đầu vào gồm các giá trị tách bởi delimiter. Nhưng đôi khi ta cần tìm `age=20` trong một dòng có nhiều thông tin, tìm một nhãn trong phạm vi giới hạn, hoặc yêu cầu một dấu phân cách xuất hiện đúng tại vị trí đang đọc.

Scanner có ba thao tác dành cho các tình huống đó:

- `findInLine(pattern)`: tìm lần khớp tiếp theo trong phần còn lại của dòng hiện tại.
- `findWithinHorizon(pattern, horizon)`: tìm lần khớp tiếp theo trong phạm vi cho trước, có thể đi qua dòng.
- `skip(pattern)`: bỏ qua đoạn khớp **bắt đầu ngay tại vị trí đọc hiện tại**.

Cả ba đều dùng biểu thức chính quy (regex) và không phân tách dữ liệu theo delimiter để thực hiện thao tác này. Chọn đúng phương thức phụ thuộc vào hai câu hỏi: **được tìm xa đến đâu** và **có được bỏ qua phần đứng trước mẫu hay không**.

## 2. Đối chiếu hành vi

| Phương thức | Có tìm tiến về phía trước không? | Phạm vi | Thành công | Không khớp |
| --- | --- | --- | --- | --- |
| `findInLine(p)` | Có | Đến dấu kết thúc dòng kế tiếp | Trả String khớp, tiến đến sau kết quả | Trả `null`, không đổi vị trí |
| `findWithinHorizon(p, h)` | Có | Theo horizon; 0 là không giới hạn | Trả String khớp, tiến đến sau kết quả | Trả `null`, không đổi vị trí |
| `skip(p)` | Không tìm một vị trí bắt đầu khác | Phải bắt đầu tại vị trí hiện tại | Tiêu thụ đoạn khớp, trả lại Scanner | Ném `NoSuchElementException`, không tiêu thụ dữ liệu |

Điểm chung “bỏ qua delimiter” không có nghĩa là tự tiêu thụ khoảng trắng trước mẫu. Đặc biệt, `skip("id=")` thất bại nếu con trỏ đang ở dấu cách trước `id=`.

Các hợp đồng phương thức được mô tả trong [Scanner API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Scanner.html).

## 3. findInLine(): tìm trong dòng hiện tại

Ví dụ đầu vào:

```text
name=An; age=20
id=7
```

Nếu tìm `age=([0-9]+)` từ đầu nguồn, Scanner đi qua phần `name=An; `, trả `age=20`, rồi dừng ngay sau `20`. Phần trước mẫu cũng đã bị vượt qua; phép tìm không giữ lại nó để lần đọc sau xử lý.

Sau đó tìm `id=...` bằng `findInLine()` vẫn không đi sang dòng thứ hai. Cần chủ động tiến sang dòng tiếp theo nếu đó là yêu cầu.

### Chương trình hoàn chỉnh

Lưu thành `FindInLineDemo.java`:

```java
import java.util.Scanner;
import java.util.regex.MatchResult;
import java.util.regex.Pattern;

public class FindInLineDemo {
    public static void main(String[] args) {
        Pattern agePattern = Pattern.compile("age=([0-9]+)");
        Pattern idPattern = Pattern.compile("id=([0-9]+)");
        String data = "name=An; age=20\nid=7\n";

        try (Scanner scanner = new Scanner(data)) {
            String ageText = scanner.findInLine(agePattern);
            System.out.println("age match = " + ageText);

            if (ageText == null) {
                throw new IllegalArgumentException("Missing age");
            }
            MatchResult ageMatch = scanner.match();
            System.out.println("age group = " + ageMatch.group(1));

            System.out.println("id in current line = "
                    + scanner.findInLine(idPattern));
            System.out.println("line remainder = ["
                    + scanner.nextLine() + "]");

            String idText = scanner.findInLine(idPattern);
            System.out.println("id in next line = " + idText);
            if (idText != null) {
                System.out.println("id group = " + scanner.match().group(1));
            }

            // Bản chụp đã lưu không phụ thuộc phép tìm thành công sau đó.
            System.out.println("saved age group = " + ageMatch.group(1));
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 FindInLineDemo.java
java FindInLineDemo
```

Stdout chính xác:

```text
age match = age=20
age group = 20
id in current line = null
line remainder = []
id in next line = id=7
id group = 7
saved age group = 20
```

`line remainder = []` xuất hiện vì sau `age=20` là dấu kết thúc dòng, không còn ký tự nội dung. Lần tìm `id` thất bại trước đó không tự tiêu thụ dấu xuống dòng.

Một vòng lặp chỉ gọi lại `findInLine()` sau kết quả `null` sẽ tiếp tục tìm ở cùng vị trí. Muốn xét nhiều dòng, phải có chiến lược tiến nguồn rõ ràng, chẳng hạn đọc từng dòng rồi dùng Matcher, hoặc xử lý phần dòng còn lại và chuyển sang dòng sau.

## 4. Nhóm bắt và Pattern

Trong `age=([0-9]+)`:

- `age=` khớp nhãn.
- `[0-9]+` khớp một hoặc nhiều chữ số ASCII.
- Cặp ngoặc tạo nhóm bắt số 1.
- `group(0)` là toàn bộ đoạn khớp; `group(1)` là nội dung nhóm đầu.

Sau một phép tìm thành công, có thể lấy bản chụp bằng `scanner.match()`. Hãy lấy ngay khi đã xác nhận kết quả khác `null`, trước khi thực hiện thao tác Scanner khác. Nếu phép tìm gần nhất thất bại, không được giả định `match()` vẫn cho phép truy cập kết quả cũ; nó có thể ném `IllegalStateException`.

Lưu đối tượng `MatchResult` như ví dụ để giữ kết quả cần dùng. Nó chứa bản chụp của lần khớp thành công đó.

Các phương thức tìm và bỏ qua có dạng nhận String hoặc Pattern. Với mẫu dùng lặp lại, có thể biên dịch một lần bằng `Pattern.compile(...)`. Khi tìm một chuỗi văn bản nguyên nghĩa từ biến, dùng `Pattern.quote(text)` để các ký tự như `.`, `+`, `[` không bị hiểu thành cú pháp regex. Xem [Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html).

Đoạn minh họa, giả sử đã có biến Scanner và String:

```java
Pattern literalLabel = Pattern.compile(Pattern.quote(label));
String found = scanner.findInLine(literalLabel);
```

Không cần đặt delimiter mới chỉ để tìm mẫu trong một dòng. Đổi delimiter là thay quy tắc đọc token; đó là một quyết định khác.

## 5. findWithinHorizon(): tìm với giới hạn

Horizon được tính từ vị trí hiện tại, không phải từ đầu tệp và không phải số lần khớp cần tìm:

- `horizon > 0`: giới hạn phạm vi tìm.
- `horizon == 0`: tìm không giới hạn theo horizon, không phải “không đọc ký tự nào”.
- `horizon < 0`: lỗi tham số, ném `IllegalArgumentException`.

Tài liệu API mô tả đơn vị horizon là điểm mã Unicode (code point), không phải byte. Các ví dụ dưới đây chỉ dùng ASCII để thể hiện ranh giới một cách trực tiếp; không suy ra số byte của nguồn từ horizon.

Phạm vi có thể cắt kết quả khớp. Với `[0-9]+` và nguồn `12345Z`, giới hạn 3 có thể cho `123`; nếu mở phạm vi lớn hơn, đoạn khớp có thể dài hơn. Vì thế tìm được một đoạn số chưa bảo đảm đã nhận toàn bộ trường dữ liệu.

### Chương trình hoàn chỉnh

Lưu thành `HorizonSearchDemo.java`:

```java
import java.util.Scanner;
import java.util.regex.Pattern;

public class HorizonSearchDemo {
    public static void main(String[] args) {
        Pattern idPattern = Pattern.compile("ID=42");

        try (Scanner scanner = new Scanner("xxID=42 tail")) {
            System.out.println("horizon 6 = "
                    + scanner.findWithinHorizon(idPattern, 6));
            System.out.println("horizon 7 = "
                    + scanner.findWithinHorizon(idPattern, 7));
            System.out.println("remainder = [" + scanner.nextLine() + "]");
        }

        try (Scanner scanner = new Scanner("12345Z")) {
            System.out.println("clipped digits = "
                    + scanner.findWithinHorizon("[0-9]+", 3));
            System.out.println("after clip = [" + scanner.nextLine() + "]");
        }

        try (Scanner scanner = new Scanner("first\nID=42\n")) {
            System.out.println("unbounded across lines = "
                    + scanner.findWithinHorizon(idPattern, 0));
        }
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 HorizonSearchDemo.java
java HorizonSearchDemo
```

Stdout chính xác:

```text
horizon 6 = null
horizon 7 = ID=42
remainder = [ tail]
clipped digits = 123
after clip = [45Z]
unbounded across lines = ID=42
```

Lần tìm với horizon 6 không đủ chứa toàn bộ `ID=42`. Nó thất bại và giữ nguyên vị trí, nên lần sau mở horizon thành 7 vẫn tìm từ đầu `xxID=42...`.

Ở ví dụ qua nhiều dòng, chính phép tìm có quyền tiếp tục qua dấu xuống dòng. Pattern `ID=42` không cần tự khớp dấu xuống dòng vì nó bắt đầu ở vị trí nằm sau dấu đó.

### Giới hạn này không thay thế mọi giới hạn của hệ thống

Horizon không phải thời gian chờ, số byte đọc tối đa từ ổ đĩa, hay cam kết chi phí tính toán cố định. Regex phức tạp vẫn có thể tốn nhiều thời gian.

Theo hợp đồng API, horizon là biên trong suốt và không tạo điểm neo riêng cho regex. Với biểu thức nhìn trước/nhìn sau, không nên coi đây là một chuỗi con hoàn toàn tách biệt. Nếu cần kiểm tra chính xác một trường đã được giới hạn độ dài, đọc trường theo định dạng rồi dùng Matcher trên phần dữ liệu đó thường dễ kiểm soát hơn.

## 6. skip(): yêu cầu khớp đúng vị trí

`skip(pattern)` không phải “tìm mẫu ở đâu đó phía sau rồi bỏ đến đó”. Nó chỉ bỏ đoạn mẫu bắt đầu tại vị trí hiện tại. Tính chất này hữu ích để kiểm tra cấu trúc như nhãn, dấu `=` hoặc dấu `;` giữa các trường.

Giả sử vị trí đọc ban đầu ở `|`:

```text
|  id=42;name=An
```

`skip("id=")` thất bại ngay vì trước `id` có hai dấu cách. Nếu định dạng cho phép khoảng trắng đó, phải đưa quy tắc vào mẫu hoặc tiêu thụ khoảng trắng riêng.

### Chương trình hoàn chỉnh

Lưu thành `AnchoredSkipDemo.java`:

```java
import java.util.NoSuchElementException;
import java.util.Scanner;

public class AnchoredSkipDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("  id=42;name=An")) {
            try {
                scanner.skip("id=");
            } catch (NoSuchElementException ex) {
                System.out.println("first skip failed at current position");
            }

            scanner.skip("[ \\t]+");
            scanner.skip("id=");

            String id = scanner.findWithinHorizon("[0-9]+", 0);
            if (id == null) {
                throw new IllegalArgumentException("Missing id");
            }
            System.out.println("id = " + id);

            scanner.skip(";name=");
            System.out.println("name = " + scanner.next());
        }

        try (Scanner scanner = new Scanner("ABC")) {
            scanner.skip("[ \\t]*");
            System.out.println("optional spaces matched length = "
                    + scanner.match().group().length());
            System.out.println("still unread = " + scanner.nextLine());
        }
    }
}
```

Chạy:

```shell
javac -encoding UTF-8 AnchoredSkipDemo.java
java AnchoredSkipDemo
```

Stdout chính xác:

```text
first skip failed at current position
id = 42
name = An
optional spaces matched length = 0
still unread = ABC
```

Lần skip thất bại không tiêu thụ hai dấu cách; phép `skip("[ \\t]+")` tiếp theo vẫn đọc được chúng.

Ở ví dụ thứ hai, dấu `*` cho phép không có ký tự trắng nào. Skip thành công nhưng vị trí không tiến. Thành công của mẫu có thể khớp rỗng không chứng minh đã bỏ qua dữ liệu.

**Lưu ý về ví dụ id:** `findWithinHorizon("[0-9]+", 0)` có thể tìm số nằm xa hơn vị trí hiện tại. Nếu yêu cầu số phải bắt đầu ngay sau `id=`, nên dùng thao tác khớp tại chỗ, chẳng hạn `skip("([0-9]+)")` rồi lấy `scanner.match().group(1)`, hoặc kiểm tra toàn bộ bản ghi bằng Matcher. Chương trình trên dùng đầu vào cố định để minh họa riêng sự khác nhau giữa tìm và skip; nó không phải bộ xác thực bản ghi tổng quát.

## 7. Regex cần diễn đạt đúng thứ được phép bỏ

| Mẫu trong Java String | Ý nghĩa phù hợp cần nhớ |
| --- | --- |
| `"[ \\t]+"` | Ít nhất một dấu cách hoặc tab |
| `"[ \\t]*"` | Không hoặc nhiều dấu cách/tab; có thể khớp rỗng |
| `"\\s+"` | Regex ký tự trắng có thể gồm xuống dòng |
| `";name="` | Đoạn nhãn và dấu phân cách đúng tại vị trí hiện tại khi dùng skip |

Trong mã Java thực tế, để truyền regex `\s+` thì viết String literal `"\\s+"`. Ví dụ:

```java
scanner.skip("\\s+");
```

Đoạn này có thể bỏ cả xuống dòng, nên không phù hợp nếu chỉ được bỏ khoảng trắng ngang trong một bản ghi. Dùng `"[ \\t]+"` khi chỉ cho phép dấu cách và tab. Đừng dùng `skip(".*")` để “dọn rác” nếu định dạng không cho phép bỏ tùy ý phần còn lại.

Ngoài ra, tránh vòng lặp tìm bằng mẫu khớp rỗng mà không có chiến lược tiến vị trí. Hai lần tìm cùng một mẫu rỗng có thể thành công ở cùng chỗ; vòng lặp chỉ kiểm tra kết quả khác null có nguy cơ không kết thúc.

## 8. Chọn tìm kiếm hay xác thực

Tìm kiếm trả lời “có một đoạn phù hợp ở phía sau không?”. Xác thực trả lời “toàn bộ phần dữ liệu cần kiểm tra có đúng định dạng không?”. Hai câu hỏi khác nhau.

Chẳng hạn tìm được `id=42` trong `garbage id=42 ???` không chứng minh cả dòng là bản ghi hợp lệ. Nếu phần đứng trước hoặc sau mẫu không được phép tồn tại, có thể đọc dòng rồi dùng `Matcher.matches()` với mẫu mô tả toàn dòng.

Đoạn minh họa với biến `String line` đã có:

```java
Pattern record = Pattern.compile("id=([0-9]+);name=([A-Za-z]+)");
var matcher = record.matcher(line);

if (!matcher.matches()) {
    throw new IllegalArgumentException("Invalid record");
}
String id = matcher.group(1);
String name = matcher.group(2);
```

Mẫu này cố ý quy định tên chỉ có chữ ASCII để minh họa cấu trúc. Khi xử lý tên người thật, cần một hợp đồng phù hợp hơn; không áp dụng giới hạn này một cách mặc định.

## 9. Chặn đọc, bộ đệm và xử lý thất bại

Các phương thức này có thể chờ thêm dữ liệu từ nguồn. `findInLine()` có thể cần tìm dấu kết thúc dòng; tìm không giới hạn có thể phải đọc đến EOF; mẫu skip quá rộng có thể khiến Scanner giữ nhiều dữ liệu.

Với nguồn không đáng tin hoặc dữ liệu rất lớn, cần giới hạn kích thước bản ghi và thiết kế thời gian chờ ở lớp I/O phù hợp. Không dựa vào một lần gọi regex để bảo đảm mọi giới hạn đó.

Các lỗi thường gặp:

- Nhầm `null` của find với ngoại lệ của skip.
- Gọi lại phép tìm thất bại mà không tiến nguồn.
- Cho rằng delimiter tự được tiêu thụ trước skip.
- Xem đoạn số bị cắt bởi horizon là một giá trị hoàn chỉnh.
- Gọi `match()` sau một phép tìm thất bại thay vì lưu kết quả thành công trước đó.
- Dùng mẫu regex quá rộng và vô tình bỏ dữ liệu có ý nghĩa.

String pattern sai cú pháp có thể gây `PatternSyntaxException`. Scanner đã đóng gây `IllegalStateException`. Với nguồn I/O, kiểm tra `ioException()` khi cần phân biệt không tìm thấy do kết thúc bình thường với lỗi đọc nguồn.

## 10. Thực hành

1. Thêm `;status=ok` sau `age=20` trong ví dụ đầu. `nextLine()` sẽ trả phần dư này thay vì chuỗi rỗng.
2. Giảm horizon từ 7 xuống 6 với mẫu cố định `ID=42`. Giải thích vì sao thất bại nhưng lần tìm sau vẫn bắt đầu ở vị trí cũ.
3. Đổi `[0-9]+` thành `[0-9]{5}` khi horizon chỉ bằng 3. Mẫu yêu cầu đủ năm chữ số nên không trả đoạn ba chữ số.
4. Đổi đầu vào skip thành `"id=42;name=An"`. Nếu khoảng trắng là tùy chọn, đổi mẫu đầu thành `[ \\t]*` thay vì `[ \\t]+`.
5. Thử bản ghi `"id=oops42;name=An"`. So sánh tìm số phía sau với khớp số ngay sau nhãn để thấy vì sao tìm được dữ liệu không đồng nghĩa với cấu trúc hợp lệ.

Trước mỗi thao tác, xác định vị trí hiện tại, phạm vi tìm, phần nào sẽ bị tiêu thụ khi thành công và việc phải làm nếu thất bại. Bốn điều này giúp dùng tìm mẫu mà không bỏ mất dữ liệu hoặc mắc kẹt tại cùng một vị trí.
