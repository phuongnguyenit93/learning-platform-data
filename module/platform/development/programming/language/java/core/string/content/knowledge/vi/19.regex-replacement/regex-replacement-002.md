# Nhóm bắt và tham chiếu nhóm trong chuỗi thay thế — Java Regex

Khi xử lý văn bản, ta có thể cần **đảo vị trí, giữ lại hoặc kết hợp những phần của đoạn khớp**. Java Regex cho phép dùng *nhóm bắt* (capturing group) trong biểu thức tìm kiếm và *tham chiếu nhóm* (group reference) trong chuỗi thay thế để tái sử dụng chính dữ liệu đã khớp.

Ví dụ đổi ngày `2026-10-23` thành `23/10/2026`:

```java
String result = "2026-10-23".replaceAll(
        "(\\d{4})-(\\d{2})-(\\d{2})",
        "$3/$2/$1");
System.out.println(result); // 23/10/2026
```

Ba nhóm lần lượt bắt năm, tháng, ngày. Chuỗi thay thế dùng `$3` (ngày), `$2` (tháng), `$1` (năm). Đây là cách **sắp xếp lại dữ liệu từ match** thay vì cắt chuỗi thủ công.

## 1. Nhóm bắt được tạo và đánh số như thế nào?

Cặp ngoặc tròn `(...)` trong regex tạo **nhóm bắt**. Khi tìm thấy một đoạn khớp, Java ghi lại chuỗi con mà mỗi nhóm đã khớp.

Xét regex:

```regex
(\d{4})-(\d{2})-(\d{2})
```

Với đầu vào `2026-10-23`:

| Số nhóm | Giá trị | Ý nghĩa |
| --- | --- | --- |
| 0 | `2026-10-23` | **Toàn bộ** đoạn khớp |
| 1 | `2026` | Nhóm đầu: năm |
| 2 | `10` | Nhóm thứ hai: tháng |
| 3 | `23` | Nhóm thứ ba: ngày |

Quy tắc đánh số: đếm **theo thứ tự dấu ngoặc mở `(` của các nhóm bắt, từ trái qua phải**, bắt đầu từ 1. Nhóm 0 luôn là toàn bộ match và không đòi hỏi cặp ngoặc riêng.

Với nhóm lồng nhau `((ab)(cd))` trên `abcd`, nhóm 1 là `abcd`, nhóm 2 là `ab`, nhóm 3 là `cd`, do vị trí ba dấu ngoặc mở.

Khi cần gom các phần của regex nhưng **không muốn tạo nhóm bắt**, dùng `(?:...)` (non-capturing group):

```regex
(?:Mr\.|Ms\.)\s+([A-Za-z]+)
```

`(?:Mr\.|Ms\.)` gom hai lựa chọn tiền tố mà không chiếm số nhóm; `([A-Za-z]+)` là **nhóm 1** để lấy tên. Không cần tham chiếu đến một nhóm thì nên dùng `(?:...)` nhằm tránh thay đổi thứ tự các nhóm quan trọng.

## 2. Tham chiếu nhóm trong chuỗi thay thế

`String.replaceAll(regex, replacement)` và `String.replaceFirst(regex, replacement)` sử dụng cú pháp replacement của `Matcher`:

| Cú pháp trong replacement | Ý nghĩa |
| --- | --- |
| `$1`, `$2`, ... | Chèn văn bản đã khớp bởi nhóm bắt số 1, 2, ... |
| `$0` | Chèn **toàn bộ** match (nhóm 0) |
| `${name}` | Chèn văn bản khớp bởi **nhóm có tên** |
| `\$` ở runtime | Chèn ký tự `$` literal |
| `\\` ở runtime | Chèn dấu `\` literal |

Trong mã nguồn Java, `"$1"` không cần escape dấu `$`. Khi muốn viết dấu `$` literal trực tiếp trong replacement Java, giá trị runtime `\$` được biểu diễn bằng `"\\$"`; khi muốn chèn ký tự `\` literal, cần biểu diễn runtime `\\`, tức Java string `"\\\\"`. Với dữ liệu runtime không cố định, sử dụng `Matcher.quoteReplacement` sẽ đơn giản và an toàn hơn.

`${name}` chỉ dành cho **tên nhóm**, không viết `${1}` để thay cho `$1`.

Ví dụ dùng nhóm 0 và nhóm 1:

```java
String s = "id=42";
System.out.println(s.replaceAll("(\\d+)", "<$0|$1>"));
// id=<42|42>
```

Cả nhóm 0 và nhóm 1 đều là `42` trong ví dụ này vì regex chứa một nhóm bao trọn match. Nếu regex có phần nằm ngoài ngoặc, nhóm 0 và nhóm 1 có thể khác.

### Phân biệt tham chiếu khi tìm kiếm và khi thay thế

**Trong regex tìm kiếm**, `\1` nghĩa là yêu cầu phần văn bản tiếp theo bằng chính nội dung nhóm 1 đã khớp (backreference); trong chuỗi Java cần viết `"\\1"`.

**Trong replacement**, `$1` nghĩa là chèn nội dung nhóm 1 vào đầu ra.

```java
System.out.println(
        "ha ha".replaceAll("(\\w+)\\s+\\1", "$1"));
// ha
```

Regex `(\\w+)\\s+\\1` nhận ra một từ đứng cạnh chính nó sau khoảng trắng; `"$1"` giữ lại một từ.

## 3. Nhóm đặt tên: `(?<name>...)` và `${name}`

Với regex có nhiều nhóm, `$1` và `$2` dễ gây nhầm. Java cho phép đặt tên bằng `(?<name>regex)`, sau đó tham chiếu bằng `${name}` trong replacement.

Ví dụ đổi `"Họ, Tên"` thành `"Tên Họ"`:

```java
String names = "Nguyen, An; Tran, Binh";
String reordered = names.replaceAll(
        "(?<last>[A-Za-z]+),\\s*(?<first>[A-Za-z]+)",
        "${first} ${last}");

System.out.println(reordered);
// An Nguyen; Binh Tran
```

Giải thích: `(?<last>[A-Za-z]+)` bắt họ, `,\\s*` khớp dấu phẩy và các khoảng trắng ngay sau nó, `(?<first>[A-Za-z]+)` bắt tên; `${first} ${last}` đưa tên lên trước họ.

Nhóm đặt tên **vẫn được đánh số** như nhóm thường; nó không làm mất khả năng truy cập theo số. Tên nhóm bắt đầu bằng chữ, theo sau là chữ hoặc số, và mỗi tên phải duy nhất trong regex.

Regex `[A-Za-z]+` ở đây dùng cho dữ liệu minh họa chữ Latin không dấu. Họ tên thực tế có thể gồm dấu tiếng Việt, dấu nối, khoảng trắng và quy tắc phức tạp hơn; không nên dùng regex minh họa này để phân tích tên người hoàn chỉnh.

## 4. Ví dụ Java chạy được độc lập

Tạo file `RegexGroupReplacementDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexGroupReplacementDemo {
    public static void main(String[] args) {
        String date = "2026-10-23";
        System.out.println("date     = " + date.replaceAll(
                "(\\d{4})-(\\d{2})-(\\d{2})",
                "$3/$2/$1"));

        String names = "Nguyen, An; Tran, Binh";
        System.out.println("names    = " + names.replaceAll(
                "(?<last>[A-Za-z]+),\\s*(?<first>[A-Za-z]+)",
                "${first} ${last}"));

        // (?:...) gom regex mà không tạo nhóm bắt.
        System.out.println("noncap   = " + "a1 b2".replaceAll(
                "(?:[a-z])([0-9])",
                "[$1]"));

        // $0 là toàn bộ match; $1 là nhóm đầu.
        System.out.println("full     = " + "id=42".replaceAll(
                "(\\d+)",
                "<$0|$1>"));

        // Nhóm tùy chọn không khớp thì thay bằng chuỗi rỗng.
        System.out.println("optional = " + "ab1 a2".replaceAll(
                "(a)(b)?(\\d)",
                "[$1|$2|$3]"));

        // Dấu $ và \ trong replacement là ký tự literal.
        String literal = "$5\\path";
        System.out.println("literal  = " + "amount=42".replaceAll(
                "\\d+",
                Matcher.quoteReplacement(literal)));

        // Thay theo giá trị tính riêng cho từng match.
        Matcher matcher = Pattern.compile("(\\d+)").matcher("a12 b3");
        StringBuilder out = new StringBuilder();
        while (matcher.find()) {
            int doubled = Integer.parseInt(matcher.group(1)) * 2;
            matcher.appendReplacement(
                    out, Matcher.quoteReplacement("[" + doubled + "]"));
        }
        matcher.appendTail(out);
        System.out.println("computed = " + out);
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac RegexGroupReplacementDemo.java
java RegexGroupReplacementDemo
```

Kết quả stdout chính xác:

```text
date     = 23/10/2026
names    = An Nguyen; Binh Tran
noncap   = [1] [2]
full     = id=<42|42>
optional = [a|b|1] [a||2]
literal  = amount=$5\path
computed = a[24] b[6]
```

`String` trong Java là immutable; `replaceAll` trả kết quả mới, không sửa chuỗi gốc. Nếu không có đoạn nào khớp, nội dung trả về bằng đầu vào. Mỗi match của `replaceAll` sẽ sử dụng **những nhóm được bắt trong chính match ấy**.

## 5. Nhóm tùy chọn, nhóm lặp và nhiều match

### Nhóm có thể không khớp

Với regex `(a)(b)?(\\d)` trên `"ab1 a2"`:

- Match `ab1`: nhóm 1 là `a`, nhóm 2 là `b`, nhóm 3 là `1`.
- Match `a2`: nhóm 1 là `a`, **nhóm 2 không tham gia match**, nhóm 3 là `2`.

Do nhóm 2 tồn tại trong pattern, tham chiếu `$2` là hợp lệ. Nhưng khi nhóm này không tham gia vào một match, Java chèn **chuỗi rỗng**:

```java
System.out.println(
        "ab1 a2".replaceAll("(a)(b)?(\\d)", "[$1|$2|$3]"));
// [a|b|1] [a||2]
```

**Nhóm có tồn tại nhưng không khớp** khác với **nhóm không được khai báo**. Tham chiếu đến nhóm không tồn tại sẽ gây lỗi.

### Nhóm đặt dưới lượng từ

Ví dụ regex `([a-z])+` khớp `abc` nhưng nhóm 1 chứa **lần bắt cuối**, là `c`; nhóm không lưu danh sách tất cả lần lặp. Nếu muốn nhóm 1 chứa cả `abc`, đưa lượng từ vào bên trong: `([a-z]+)`.

### Thay nhiều match

`replaceAll` duyệt các match **không chồng lấp**, theo thứ tự từ trái sang phải, và áp dụng chuỗi replacement cho mỗi match:

```java
System.out.println(
        "A=12; B=345".replaceAll("(\\d+)", "[$1]"));
// A=[12]; B=[345]
```

`$1` lần đầu là `12`, lần sau là `345`. `replaceFirst` chỉ thay match đầu tiên.

## 6. Giữ regex và replacement đúng vai trò

Trong **regex tìm kiếm**, tham chiếu ngược yêu cầu phần văn bản sau khớp lại với một nhóm đã bắt; trong **replacement**, **$1**, **$2** và **${name}** chèn dữ liệu từ nhóm vào kết quả. **String.replace** thì làm việc với chuỗi literal, nên không mở rộng tham chiếu nhóm.

Khi cần chèn nội dung ngoài hệ thống như giá tiền hoặc đường dẫn có **$** và dấu gạch chéo ngược, dùng **Matcher.quoteReplacement**. Nhưng nếu cố ý dùng **$1** để tái sử dụng nhóm bắt, không quote toàn bộ template. Những bài kế tiếp trình bày riêng cú pháp escape và kỹ thuật chèn nguyên văn.

## 7. Truy cập nhóm để tính giá trị riêng cho từng match

**String.replaceAll** phù hợp khi mọi match dùng cùng một template nhóm bắt. Khi cần tính kết quả khác nhau, **Matcher.find()** kết hợp **group(1)**, **appendReplacement** và **appendTail** cho phép lấy nhóm, tính chuỗi mới và giữ phần đuôi chưa khớp; chương trình ở mục 4 đã minh họa quy trình này.

Từ Java 9, **Matcher.replaceAll(Function<MatchResult, String>)** rút gọn việc thay riêng từng match. Trong Java 17, callback **MatchResult** cho phép đọc nhóm bằng chỉ số, còn **Matcher** cũng hỗ trợ nhóm theo tên. Cả giá trị truyền vào appendReplacement lẫn chuỗi callback trả về vẫn tuân theo cú pháp replacement, nên quote khi muốn chèn nguyên văn.

## 8. Những lỗi thường gặp

1. **Đặt `$1` vào regex tìm kiếm.** Tham chiếu nhóm trong *regex* là `\1`; `$1` dành cho *replacement*.
2. **Nhầm nhóm không bắt với nhóm bắt.** `(?:...)` không tạo nhóm và không có số để tham chiếu. Với regex chỉ gồm nhóm không bắt, replacement `$1` là không hợp lệ.
3. **Đánh số theo dấu ngoặc đóng.** Phải đánh số từ trái sang phải theo **ngoặc mở** của nhóm bắt, kể cả với nhóm lồng nhau.
4. **Quên nhóm có thể không tham gia match.** Nhóm có tồn tại nhưng không khớp được thay bằng chuỗi rỗng; nhóm hoàn toàn không tồn tại gây lỗi.
5. **Đưa nguyên chuỗi người dùng làm replacement.** Ký tự `$` và `\` có thể mang nghĩa đặc biệt. Nếu cần literal, dùng `Matcher.quoteReplacement`.
6. **Dùng `$10` rồi hiểu nhầm.** Cú pháp numeric được đọc đủ dài theo số nhóm thực sự tồn tại. Với mười nhóm, `$10` tham chiếu nhóm 10; với một nhóm, `$10` có thể là nhóm 1 rồi ký tự `0`. Nhóm đặt tên giúp hạn chế mơ hồ.
7. **Mong nhóm lặp chứa toàn bộ các lần bắt.** `([a-z])+` thường chỉ để lại lần bắt cuối; `([a-z]+)` giữ cả dãy ký tự trong cùng một match.
8. **Dùng `String.replace` rồi mong `$1` hoạt động.** `String.replace(CharSequence, CharSequence)` thực hiện thay literal; không diễn giải regex hay tham chiếu nhóm.
9. **Dùng regex minh họa làm parser dữ liệu phức tạp.** Có thể cần xử lý Unicode, quoted values, dấu escape hay định dạng nhiều tầng; cần chọn parser phù hợp thay vì dựa vào vài nhóm bắt đơn giản.

Regex không hợp lệ có thể gây `PatternSyntaxException`; replacement sai cú pháp hoặc tham chiếu tới nhóm không tồn tại có thể gây `IllegalArgumentException` hoặc `IndexOutOfBoundsException` tùy tình huống. Phải xác định rõ dữ liệu bên ngoài được phép mang cú pháp regex/replacement hay chỉ là văn bản literal.

## 9. Bài tự luyện

**Bài 1.** Đổi `user:100` thành `100 (user)` bằng hai nhóm:

```java
"user:100".replaceAll("([a-z]+):(\\d+)", "$2 ($1)")
// "100 (user)"
```

**Bài 2.** Vì sao `"a1 b2".replaceAll("(?:[a-z])(\\d)", "$1")` tạo `"1 2"`?

Vì `(?:[a-z])` khớp chữ nhưng **không tạo nhóm bắt**, nên nhóm 1 chính là `(\\d)`. Chữ bị bỏ khi toàn bộ match được thay bằng mỗi chữ số.

**Bài 3.** Muốn chèn đúng hai ký tự `$1` theo nghĩa literal khi thay chữ số:

```java
"abc42".replaceAll("\\d+", Matcher.quoteReplacement("$1"))
// "abc$1"
```

**Bài 4.** Với regex `(?<area>\\d{3})-(?<number>\\d{4})`, replacement nào chỉ giữ số phía sau dấu gạch ngang?

`${number}` (cũng có thể dùng `$2`, nhưng tên nhóm giúp rõ nghĩa).

**Bài 5.** Tại sao `"abc".replaceAll("([a-z])+", "$1")` là `"c"`? Nhóm 1 được lặp và chỉ giữ lần bắt cuối. Muốn giữ cả chuỗi, dùng `([a-z]+)`.

**Ghi nhớ:** `(...)` tạo nhóm bắt; `(?:...)` chỉ nhóm cú pháp; `$1` và `${name}` tái sử dụng nội dung nhóm trong replacement; `Matcher.quoteReplacement` bảo vệ văn bản thay thế literal; `Matcher` phù hợp khi thay thế đòi hỏi tính toán riêng cho từng match.

**Tham khảo chính thức:** [`String.replaceAll` (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#replaceAll(java.lang.String,java.lang.String)), [`Matcher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Matcher.html), [`Pattern`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html).
