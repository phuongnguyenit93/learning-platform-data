# Thay thế nhiều lần và giới hạn của việc dùng regex thay bộ phân tích

## 1. Hai kiểu thay thế “nhiều lần”

Trong Java, `String.replaceAll(String regex, String replacement)` tìm các đoạn văn bản **khớp regex và không chồng lấn** trong chuỗi đầu vào, rồi thay tất cả các đoạn đó trong **một lượt**. Nó không tự tiếp tục tìm trong chính phần văn bản vừa được thay.

Điều này khác với việc chương trình **gọi thay thế lặp nhiều lượt**, ví dụ lặp cho đến khi kết quả ổn định, hoặc lần lượt áp dụng nhiều quy tắc thay thế.

```java
String once = "aaaa".replaceAll("aa", "a"); // "aa", không phải "a"

String twice = once.replaceAll("aa", "a");  // "a"
```

Trong lượt đầu, hai phần `"aa"` của `"aaaa"` được thay bằng hai chữ `a`, tạo `"aa"`. Lượt thứ hai mới tạo `"a"`. Một lần gọi `replaceAll` thay **tất cả match của lượt hiện tại**, không có nghĩa là “lặp đến khi không còn match”.

`String` là kiểu bất biến: mỗi phương thức trả về một chuỗi mới hoặc chuỗi hiện tại khi không đổi; muốn dùng kết quả tiếp thì phải gán lại biến.

## 2. Chọn quy tắc phù hợp trước khi lặp

**String.replace** thay văn bản cố định theo nghĩa literal; **String.replaceFirst** và **String.replaceAll** tìm theo regex, lần lượt thay match đầu tiên hoặc mọi match không chồng lấn của một lượt. Nếu dùng cùng regex trên nhiều đầu vào, biên dịch một **Pattern** rồi tạo **Matcher** riêng cho mỗi đầu vào.

Một replacement template cố định có thể tham chiếu nhóm bằng **$1** hoặc **${name}**; giá trị nguyên văn chứa dấu đô la hoặc gạch chéo ngược cần **Matcher.quoteReplacement**. Nếu replacement phụ thuộc từng match, Java 9+ có **Matcher.replaceAll(Function<MatchResult,String>)**, còn **appendReplacement/appendTail** hỗ trợ khi muốn kiểm soát quá trình ghép văn bản. Việc chọn API đúng không thay thế yêu cầu phân tích khả năng hội tụ và giới hạn của dữ liệu cấu trúc ở các mục sau.

## 3. Ví dụ Java 17+ biên dịch và chạy được

Tạo file `RepeatedRegexReplacementDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RepeatedRegexReplacementDemo {
    // Chỉ dùng khi quy tắc có cơ sở để hội tụ.
    private static String replaceUntilStable(
            String input, Pattern pattern, String replacement, int maxPasses) {
        if (maxPasses < 1) {
            throw new IllegalArgumentException("maxPasses must be positive");
        }

        String current = input;
        for (int pass = 0; pass < maxPasses; pass++) {
            String next = pattern.matcher(current).replaceAll(replacement);
            if (next.equals(current)) {
                return current;
            }
            current = next;
        }
        throw new IllegalStateException("No convergence within limit");
    }

    public static void main(String[] args) {
        // Một lượt gộp các nhóm khoảng trắng liên tiếp.
        String text = "red  green\tblue";
        System.out.println("Normalize: "
                + text.replaceAll("\\s+", " ").trim());

        // Một lượt khác với lặp nhiều lượt đến khi ổn định.
        System.out.println("Single pass: " + "aaaa".replaceAll("aa", "a"));
        System.out.println("Until stable: "
                + replaceUntilStable("aaaa", Pattern.compile("aa"), "a", 10));

        // replace nguyên văn khác replaceAll nhận regex.
        System.out.println("Literal dot: " + "a.b".replace(".", "|"));
        System.out.println("Regex dot: " + "a.b".replaceAll(".", "|"));

        // match đầu tiên khác tất cả match.
        System.out.println("First: " + "foo foo".replaceFirst("foo", "bar"));
        System.out.println("All: " + "foo foo".replaceAll("foo", "bar"));

        // Replacement nguyên văn có ký tự đặc biệt của cú pháp replacement.
        String price = "$5\\item";
        String safe = Pattern.compile("\\{\\{price\\}\\}")
                .matcher("cost={{price}}")
                .replaceAll(Matcher.quoteReplacement(price));
        System.out.println("Safe literal: " + safe);

        // Tính riêng replacement cho mỗi match (Java 9+).
        String calculated = Pattern.compile("(\\w+)=(\\d+)")
                .matcher("a=3;b=42")
                .replaceAll(match ->
                        match.group(1).toUpperCase()
                                + "=" + (Integer.parseInt(match.group(2)) + 1));
        System.out.println("Calculated: " + calculated);

        // Regex không hiểu quy tắc dấu nháy kép của CSV.
        String csv = "a,\"b,c\",d";
        System.out.println("Naive CSV: " + csv.replaceAll(",", "|"));

        // Mẫu zero-width có thể dẫn tới chèn ký tự.
        System.out.println("Zero width: " + "aa".replaceAll("(?=a)", "X"));
    }
}
```

Biên dịch và chạy:

```bash
javac RepeatedRegexReplacementDemo.java
java RepeatedRegexReplacementDemo
```

Đầu ra:

```text
Normalize: red green blue
Single pass: aa
Until stable: a
Literal dot: a|b
Regex dot: |||
First: bar foo
All: bar bar
Safe literal: cost=$5\item
Calculated: A=4;B=43
Naive CSV: a|"b|c"|d
Zero width: XaXa
```

Ở phần `Until stable`, dữ liệu đi qua `"aaaa" → "aa" → "a"`: cần **hai lượt có thay đổi** và một lượt kiểm tra thấy không còn thay đổi. Phần `Calculated` tính kết quả riêng cho từng match: `a=3` thành `A=4`, còn `b=42` thành `B=43`. Phần `Naive CSV` cho thấy regex thay cả dấu phẩy nằm **bên trong trường được nháy kép**, vốn không phải dấu phân cách giữa các trường theo quy tắc CSV.

## 4. Thay thế theo nhiều quy tắc: thứ tự quan trọng

Có thể ghép nhiều quy tắc để xử lý văn bản đơn giản:

```java
String input = "  Hello,\tJava!!  ";
String result = input
        .replaceAll("\\s+", " ")  // Gom các nhóm khoảng trắng.
        .replaceAll("!+", "!")    // Gom nhiều dấu ! liên tiếp.
        .trim();                  // Bỏ khoảng trắng hai đầu.

System.out.println(result);      // Hello, Java!
```

Đây là **đoạn minh họa trong phương thức hoặc khối lệnh**, không phải một lớp Java độc lập. Mỗi lời gọi dùng kết quả của lời gọi trước, nên đổi thứ tự có thể đổi kết quả. Ví dụ, nếu quy tắc thứ nhất đổi `"ab"` thành `"b"`, và quy tắc thứ hai đổi `"b"` thành `"c"`, chuỗi `"ab"` có thể đi tới `"c"` khi dùng đúng thứ tự; nếu đảo thứ tự sẽ còn `"b"`.

Khi dùng một regex nhiều lần, biên dịch `Pattern` một lần:

```java
Pattern whitespace = Pattern.compile("\\s+");
String first = whitespace.matcher("a   b").replaceAll(" ");
String second = whitespace.matcher("c\t d").replaceAll(" ");
```

`Pattern` được thiết kế để tái sử dụng. `Matcher` giữ trạng thái tìm kiếm, nên tạo `Matcher` mới cho từng chuỗi hoặc quản lý trạng thái bằng API phù hợp; đừng chia sẻ một `Matcher` đồng thời giữa nhiều luồng.

Nếu cần thay thế theo nhóm bắt, có thể dùng cú pháp replacement:

```java
String result = "2026-10-23".replaceAll(
        "(\\d{4})-(\\d{2})-(\\d{2})", "$3/$2/$1");
// result = "23/10/2026"
```

Nhóm bắt giúp đổi thứ tự dữ liệu có cấu trúc **đơn giản, đã kiểm soát**. Chuỗi replacement lấy từ bên ngoài cần `Matcher.quoteReplacement` nếu muốn chèn nguyên văn. Ngay cả hàm `Matcher.replaceAll(match -> ...)` cũng trả về một **replacement string** có cú pháp `$`/`\\`; bọc kết quả bằng `Matcher.quoteReplacement` nếu nó có thể chứa các ký tự đặc biệt và phải được chèn nguyên văn.

## 5. Lặp đến khi ổn định: không phải lúc nào cũng kết thúc

Quy tắc `"aa" → "a"` có số chữ `a` giảm qua mỗi lượt, vì vậy có cơ sở hội tụ. Nhưng không phải phép thay thế nào cũng có tính chất này:

- `"a" → "aa"`: mỗi lượt làm chuỗi dài thêm, không ổn định nếu đầu vào vẫn chứa `a`.
- Quy tắc luân phiên `"a" → "b"` và `"b" → "a"`: có thể quay lại trạng thái cũ, tạo chu trình.
- Có quy tắc tạo ra thêm nhiều mẫu mới, khiến kích thước đầu ra tăng nhanh và chi phí xử lý tăng theo.

Vòng lặp `replaceUntilStable` trong ví dụ dùng giới hạn `maxPasses` và **ném lỗi** khi chưa hội tụ, giúp tránh vòng lặp vô hạn do chỉ chờ hai chuỗi liên tiếp bằng nhau. Tuy nhiên, giới hạn số lượt **không tự giới hạn kích thước chuỗi**: trong thực tế có thể cần thêm giới hạn kích thước đầu ra, thời gian thực thi và kiểm tra chu trình dài hơn một trạng thái.

Khi thiết kế một pipeline lặp, nên xác định:

1. **Điều kiện dừng:** không đổi so với lượt trước, không còn token cần thay, hoặc đã đạt số lượt quy định.
2. **Lý do hội tụ:** ví dụ có đại lượng không âm giảm nghiêm ngặt qua mỗi lượt. Nếu chưa chứng minh được, phải xử lý trường hợp không hội tụ.
3. **Giới hạn tài nguyên:** số lượt, kích thước đầu vào/đầu ra và bộ nhớ cần cấp phát.
4. **Quy tắc khi thất bại:** báo lỗi rõ ràng, không âm thầm trả một kết quả chưa hoàn tất nếu caller chờ kết quả ổn định.

Một lần `replaceAll` không tìm tất cả **match chồng lấn**. Chẳng hạn, `"aaa"` có hai vị trí bắt đầu cho mẫu `"aa"` nếu xét chồng lấn, nhưng `replaceAll("aa", "X")` chỉ lấy match đầu tiên và cho `"Xa"`. Nếu bài toán thật sự cần xử lý match chồng lấn, hãy thiết kế lookahead một cách có chủ đích hoặc viết bộ quét chỉ số ký tự; lặp `replaceAll` một cách tùy tiện không phải lời giải tổng quát.

Mẫu có **độ rộng 0** (zero-width), như `(?=a)`, có thể chèn thay vì xóa ký tự: `"aa".replaceAll("(?=a)", "X")` tạo `"XaXa"`. Engine quản lý việc tiến qua các match zero-width trong một lượt, nhưng đầu ra vẫn cần được kiểm thử kỹ ở đầu/cuối chuỗi, chuỗi rỗng và khi có Unicode.

## 6. Giới hạn của việc dùng regex thay bộ phân tích

Regex mô tả **mẫu văn bản** và phù hợp với các phép biến đổi cục bộ, như chuẩn hóa khoảng trắng, che một chuỗi ID có định dạng đơn giản, đổi một tiền tố có ranh giới rõ ràng hoặc thay một token cố định. Một **bộ phân tích cú pháp** (parser) hiểu vai trò các thành phần trong ngữ pháp, chẳng hạn “ký tự này nằm trong chuỗi được nháy kép”, “đây là thuộc tính của thẻ nào” hoặc “dấu ngoặc này thuộc cấp lồng nào”.

| Dữ liệu | Vì sao regex thay thế đơn giản dễ sai? | Cách tiếp cận phù hợp |
| --- | --- | --- |
| CSV | Dấu phẩy bên trong trường có dấu nháy kép không ngăn cách cột; còn có escape dấu nháy và xuống dòng trong trường. | Dùng parser CSV để nhận từng trường rồi ghi dữ liệu theo quy tắc CSV. |
| JSON | Dấu phẩy, dấu hai chấm, ngoặc và dấu nháy có vai trò khác nhau theo trạng thái; object/array lồng nhau, chuỗi có escape. | Parse JSON thành cây/đối tượng, sửa đúng node, rồi serialize. |
| HTML/XML | Thẻ, thuộc tính, entity, bình luận, text node và cấu trúc cây; `>` có thể xuất hiện trong giá trị thuộc tính được quote. | Dùng parser HTML/XML để thao tác node hoặc attribute. |
| SQL và mã nguồn | Dấu câu trong string literal, comment và cấu trúc lồng nhau không có cùng ý nghĩa với token cú pháp. | Dùng lexer/parser/AST hoặc API chuyên biệt. |
| Ngoặc lồng nhau tùy độ sâu | Mẫu cần nhớ các cấp cấu trúc; regex Java thông thường không phải parser tổng quát cho ngữ pháp lồng vô hạn. | Dùng parser hoặc bộ quét có stack/trạng thái rõ ràng. |

Ví dụ, đoạn CSV `a,"b,c",d` có **3 trường**. Thay tất cả dấu phẩy bằng `|` theo regex tạo `a|"b|c"|d`, đặt một dấu `|` vào giữa trường `"b,c"`; sau đó không thể mặc nhiên coi mỗi `|` là dấu phân cách mới của ba trường. Một parser CSV phân biệt dấu phẩy **ở ngoài** và **ở trong** cặp nháy kép, kể cả nháy được escape.

Tương tự, một biểu thức như `<[^>]*>` không tạo ra parser HTML hoàn chỉnh: dấu `>` có thể nằm trong thuộc tính được nháy, và ngữ cảnh thẻ/comment/text có thể khác nhau. Thêm các regex để vá từng trường hợp dễ làm giải pháp khó hiểu và dễ phá dữ liệu hợp lệ.

**Tiêu chí quyết định:** Nếu cách thay thế phụ thuộc vào ngữ cảnh quote, escape, cấu trúc cây, phạm vi lồng nhau hoặc ngữ pháp tài liệu, dùng mô hình **parse → sửa cấu trúc → serialize**. Nếu mẫu khớp chỉ phụ thuộc vào một đoạn văn bản cục bộ đã biết, regex có thể phù hợp.

Không phải mọi thay đổi trong JSON, HTML hay CSV đều tuyệt đối cấm dùng regex: chẳng hạn có thể thay một đoạn text độc lập đã được lấy ra bởi parser. Điều cần tránh là dùng regex để **đoán ranh giới cấu trúc** của cả tài liệu phức tạp.

## 7. Hiệu năng và các lỗi thường gặp

**Backtracking quá mức.** Một số regex có lượng từ lồng hoặc nhánh mơ hồ như `(a+)+$` có thể rất chậm với chuỗi dài gồm nhiều `a` rồi một ký tự không khớp. Java `Pattern` dùng cơ chế có backtracking; với đầu vào hoặc pattern không đáng tin, cần giới hạn kích thước dữ liệu, tránh các mẫu mơ hồ và kiểm tra trường hợp xấu. Không ghép chuỗi do người dùng nhập trực tiếp thành regex nếu yêu cầu chỉ là khớp nguyên văn.

**Quét lặp lại và cấp phát nhiều chuỗi.** Mỗi lượt regex có thể quét lại một chuỗi lớn và tạo kết quả mới. Nếu thuật toán cần lặp rất nhiều lượt, hãy cân nhắc một bộ quét trạng thái qua dữ liệu một lần hoặc một parser phù hợp.

**Nhầm `replaceAll` với `replace`.** `.`, `|`, `*`, `[` và `\\` có cú pháp riêng trong regex. Thay văn bản cố định thì `String.replace` dễ đọc và ít gây nhầm hơn. Nếu vẫn dùng regex với dấu phân cách nguyên văn, hãy áp `Pattern.quote` cho pattern.

**Nhầm ký tự `$` và `\\` trong replacement.** Nếu muốn chèn nguyên văn `"$5\item"`, hãy dùng `Matcher.quoteReplacement`. Nếu định dùng nhóm bắt, cú pháp `$1` hoặc `${name}` cần nhóm bắt tồn tại, nếu không có thể phát sinh lỗi.

**Quy tắc tưởng như vô hại nhưng làm hỏng cú pháp.** Thay dấu phẩy toàn cục trong CSV, thay từ trong string literal của mã nguồn, hoặc đổi key JSON bằng regex quét nguyên tài liệu có thể làm thay sai vị trí. Với cấu trúc dữ liệu, dùng parser.

**Thiếu kiểm thử biên.** Kiểm thử đầu/cuối chuỗi, không có match, nhiều match liên tiếp, chuỗi rỗng, zero-width, `$`, gạch chéo ngược, Unicode, xuống dòng và dữ liệu lớn. Các cờ regex `DOTALL`, `MULTILINE`, `CASE_INSENSITIVE` có thể thay đổi ý nghĩa của mẫu; cần dùng có chủ đích và có ca kiểm thử phù hợp.

## 8. Tự kiểm tra

**Câu 1.** Vì sao `"aaaa".replaceAll("aa", "a")` trả `"aa"`, còn gọi thêm một lần trả `"a"`? Hãy giải thích theo khái niệm match không chồng lấn và không tự quét lại đầu ra.

**Câu 2.** Nếu người dùng gửi văn bản thay thế `"$5\item"`, vì sao đưa trực tiếp vào `replaceAll` có thể làm lỗi hoặc đổi dữ liệu? Hãy chỉ ra API dùng để quote phần replacement và API dùng để quote phần pattern.

**Câu 3.** Muốn thay dấu phân cách giữa các trường CSV `a,"b,c",d` nhưng giữ dấu phẩy trong `"b,c"`, vì sao một `replaceAll(",", "|")` không đủ? Mô tả các bước với parser CSV.

**Câu 4.** Một quy tắc thay `"a"` thành `"aa"` có hội tụ khi lặp đến lúc không đổi hay không? Nếu không, vòng lặp phải kiểm soát những giới hạn nào?

**Ghi nhớ:** `replaceAll` thay mọi match không chồng lấn **trong một lượt**. Khi lặp nhiều lượt cần kiểm soát điều kiện dừng và tài nguyên; khi việc thay phụ thuộc vào cấu trúc/ngữ pháp của dữ liệu, dùng parser để thay đúng thành phần.