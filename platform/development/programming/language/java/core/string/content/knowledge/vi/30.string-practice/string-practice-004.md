# Tách dữ liệu có phần tử rỗng và giữ đúng dấu phân cách trong Java

## Mục tiêu và bài toán

Khi đọc một dòng dữ liệu có cấu trúc, **phần tử rỗng vẫn là một phần tử hợp lệ**. Ví dụ chuỗi `,A,,B,` phân cách bằng dấu phẩy có **5 trường**, theo thứ tự: `""`, `"A"`, `""`, `"B"`, `""`. Dấu phẩy đầu tạo trường đầu rỗng; hai dấu phẩy kề nhau tạo trường giữa rỗng; dấu phẩy cuối tạo trường cuối rỗng. Bỏ bất kỳ trường nào có thể làm lệch vị trí cột.

Có hai nhu cầu cần phân biệt:

1. **Giữ các trường rỗng** trong mảng kết quả, trong khi dấu phân cách có thể bỏ đi. Dùng `String.split(regex, -1)`.
2. **Giữ nguyên cả dấu phân cách đã xuất hiện** (chẳng hạn chuỗi có cả `,` và `;`, hoặc số lượng/ký tự phân cách mang ý nghĩa). Dùng `Matcher` để lấy riêng các trường và các chuỗi phân cách, hoặc `splitWithDelimiters` trên Java 21+.

Không nên mặc định rằng `split` vừa giữ trường cuối rỗng, vừa trả về các dấu phân cách. Đó là hai thuộc tính khác nhau.

## 1. Hiểu chính xác `String.split` và tham số `limit`

`String.split(String regex)` tương đương `split(regex, 0)`: các trường rỗng **ở cuối** bị loại khỏi kết quả. Trường rỗng ở đầu do một kết quả khớp có độ dài dương và trường rỗng ở giữa vẫn được giữ.

| Lệnh | Kết quả (viết rõ chuỗi rỗng) | Ý nghĩa |
| --- | --- | --- |
| `",A,,B,".split(",")` | `["", "A", "", "B"]` | Mất trường rỗng ở cuối |
| `",A,,B,".split(",", 0)` | `["", "A", "", "B"]` | Giống lời gọi một tham số |
| `",A,,B,".split(",", -1)` | `["", "A", "", "B", ""]` | Giữ cả trường cuối rỗng |
| `"A,,B,".split(",", 2)` | `["A", ",B,"]` | Tách tối đa 1 lần; phần còn lại giữ nguyên |
| `",,".split(",", -1)` | `["", "", ""]` | Hai dấu phân cách tạo ba trường rỗng |
| `"abc".split(",", -1)` | `["abc"]` | Không có dấu phân cách |
| `"".split(",", -1)` | `[""]` | Chuỗi đầu vào rỗng, kết quả có một phần tử |

Ba chế độ `limit`:

- `limit > 0`: tối đa `limit - 1` lần tách; phần tử cuối chứa toàn bộ phần chưa tách. Dùng khi cố tình muốn giữ phần còn lại, ví dụ phân tách `key=value=more` bằng `split("=", 2)`.
- `limit == 0`: tách hết và **loại các trường rỗng liên tiếp ở cuối**.
- `limit < 0`: tách hết và **giữ mọi trường rỗng**, kể cả ở cuối. `-1` là giá trị quen dùng; `-2` có cùng hành vi về việc giữ trường rỗng.

**Quy tắc thực hành:** dữ liệu dạng bản ghi mà số thứ tự trường cần chính xác thường nên dùng `split(delimiterRegex, -1)`. Đừng `trim()` hoặc `filter(s -> !s.isEmpty())` sau khi tách nếu khoảng trắng/trường rỗng có ý nghĩa.

## 2. Dấu phân cách được hiểu là regex, không mặc định là ký tự literal

Đối số thứ nhất của `split` là **biểu thức chính quy**. Vì vậy:

- Dấu phẩy `,` và dấu chấm phẩy `;` không có ý nghĩa regex đặc biệt trong ngữ cảnh đơn giản này.
- Dấu gạch đứng `|`, dấu chấm `.`, dấu sao `*`, dấu ngoặc vuông... có thể mang ý nghĩa regex. Viết `text.split("|", -1)` để tách theo dấu `|` là sai.
- Với dấu phân cách **cố định/literal**, đặc biệt lấy từ cấu hình hoặc người dùng, dùng `Pattern.quote(delimiter)`. Ví dụ `"a|b||".split(Pattern.quote("|"), -1)` trả về `["a", "b", "", ""]`.
- Với dấu phân cách **là quy tắc regex có chủ đích**, viết regex rõ ràng: `"a,b;c".split("[,;]", -1)` tách theo từng dấu phẩy hoặc chấm phẩy. Nhưng mảng kết quả không cho biết tại vị trí nào đã dùng dấu nào.
- Khi muốn gộp chuỗi dấu phân cách liên tiếp thành **một** dấu tách, regex `[,;]+` sẽ bỏ cấu trúc trường rỗng giữa các dấu. Chỉ dùng nếu nghiệp vụ thật sự cho phép.

Regex có thể khớp chuỗi có độ dài bằng 0 (zero-width match), dẫn đến cách phân tách không trực quan. Với bài toán tách bản ghi có dấu phân cách hữu hình, nên chọn pattern luôn tiêu thụ ít nhất một ký tự. Cũng không thể lấy đúng toàn bộ dấu phân cách ban đầu chỉ từ `String[]` đã tách bằng regex cho nhiều ký tự phân cách khác nhau.

## 3. Ví dụ Java 17+: giữ trường rỗng và giữ chính xác dấu phân cách

Chương trình dưới đây minh họa cả hai hướng: `split(..., -1)` cho dấu phân cách cố định, và `Matcher.find()` khi cần giữ từng dấu đã khớp. Lớp `Tokenized` giữ hai danh sách theo thứ tự; với `n` dấu phân cách sẽ có `n + 1` trường, kể cả trường rỗng.

Tạo tệp `SplitPreservingDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SplitPreservingDemo {
    public static void main(String[] args) {
        String line = ",A,,B,";
        String[] defaultFields = line.split(",");
        String[] allFields = line.split(",", -1);

        System.out.println("Default: " + quoted(defaultFields));
        System.out.println("Preserved: " + quoted(allFields));
        System.out.println("Field count: " + allFields.length);
        System.out.println("Same text: " + String.join(",", allFields).equals(line));

        String pipeLine = "red|blue||";
        String[] pipeFields = pipeLine.split(Pattern.quote("|"), -1);
        System.out.println("Pipe: " + quoted(pipeFields));

        String mixed = "A,,B;C;";
        Tokenized tokens = tokenize(mixed, Pattern.compile("[,;]"));
        System.out.println("Fields: " + quoted(tokens.fields.toArray(new String[0])));
        System.out.println("Separators: " + quoted(tokens.separators.toArray(new String[0])));
        System.out.println("Mixed same text: " + rebuild(tokens).equals(mixed));
    }

    // Phục vụ minh họa: làm rõ vị trí các chuỗi rỗng trong output.
    private static String quoted(String[] fields) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < fields.length; i++) {
            if (i > 0) {
                out.append(", ");
            }
            out.append('"').append(fields[i]).append('"');
        }
        return out.append(']').toString();
    }

    private static Tokenized tokenize(String text, Pattern separatorPattern) {
        Matcher matcher = separatorPattern.matcher(text);
        List<String> fields = new ArrayList<>();
        List<String> separators = new ArrayList<>();
        int from = 0;

        while (matcher.find()) {
            if (matcher.start() == matcher.end()) {
                throw new IllegalArgumentException(
                    "Separator pattern must consume at least one character"
                );
            }
            fields.add(text.substring(from, matcher.start()));
            separators.add(matcher.group());
            from = matcher.end();
        }
        fields.add(text.substring(from));
        return new Tokenized(fields, separators);
    }

    private static String rebuild(Tokenized tokens) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < tokens.fields.size(); i++) {
            out.append(tokens.fields.get(i));
            if (i < tokens.separators.size()) {
                out.append(tokens.separators.get(i));
            }
        }
        return out.toString();
    }

    private static class Tokenized {
        final List<String> fields;
        final List<String> separators;

        Tokenized(List<String> fields, List<String> separators) {
            this.fields = fields;
            this.separators = separators;
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SplitPreservingDemo.java
java SplitPreservingDemo
```

Kết quả chuẩn:

```text
Default: ["", "A", "", "B"]
Preserved: ["", "A", "", "B", ""]
Field count: 5
Same text: true
Pipe: ["red", "blue", "", ""]
Fields: ["A", "", "B", "C", ""]
Separators: [",", ",", ";", ";"]
Mixed same text: true
```

Diễn giải:

- `split(",", -1)` trả về đúng 5 trường; ghép lại bằng **chính dấu phẩy cố định** tái tạo chuỗi đầu vào.
- `Pattern.quote("|")` bảo đảm `|` được hiểu là một dấu phân cách literal; hai dấu `|` cuối làm phát sinh hai phần tử rỗng ở cuối (sau `blue`).
- Trong `"A,,B;C;"`, trường thứ hai và trường cuối rỗng. Danh sách `separators` giữ nguyên từng dấu `,`/`;`, nên `rebuild` có thể khôi phục đúng chuỗi gốc.
- Với pattern tiêu thụ ký tự, `matcher.start()` là chỉ số đầu dấu phân cách, `matcher.end()` là vị trí ngay sau nó; `substring(from, matcher.start())` nhận chính xác trường trước dấu tách, kể cả chuỗi rỗng. `matcher.group()` chứa **chuỗi khớp thực tế**, hữu ích cả khi dấu phân cách dài hơn một ký tự.
- Hàm `quoted` chỉ nhằm hiển thị minh bạch các phần tử trong ví dụ; nếu dữ liệu có dấu nháy hoặc ký tự điều khiển, cần cách escape khi hiển thị phù hợp.

### Vì sao cần giữ danh sách dấu phân cách?

Ví dụ `a,b;c` dùng regex `[,;]` và tách được `["a", "b", "c"]`, nhưng nếu ghép lại bằng dấu phẩy sẽ thành `a,b,c`, mất dấu chấm phẩy gốc. `String.join` chỉ bảo toàn bản gốc khi **mọi dấu phân cách thực sự là cùng một chuỗi cố định** và các trường đã được giữ đầy đủ, không có quy tắc escape/quote phức tạp.

Trong đoạn `Matcher` ở trên, `fields.size() == separators.size() + 1` là bất biến đáng kiểm tra. Không chuẩn hóa khoảng trắng, không đổi dấu và không bỏ trường rỗng nếu mục tiêu là lưu/tái tạo dữ liệu nguyên trạng.

## 4. Java 21+: `String.splitWithDelimiters`

Java 21 bổ sung `String.splitWithDelimiters(String regex, int limit)` và `Pattern.splitWithDelimiters(CharSequence input, int limit)`. Kết quả **xen kẽ trường, dấu phân cách, trường, dấu phân cách...**, thay vì chỉ trả các trường.

Ví dụ Java 21 (đoạn minh họa, đặt trong một phương thức):

```java
String input = "A,,B;";
String[] pieces = input.splitWithDelimiters("[,;]", -1);
// pieces: ["A", ",", "", ",", "B", ";", ""]
boolean same = String.join("", pieces).equals(input); // true
```

Dùng `limit = -1` để giữ cả phần rỗng cuối; `limit = 0` vẫn bỏ phần rỗng ở cuối theo quy tắc API. Với `limit > 0`, tối đa `limit - 1` lần tách và phần cuối giữ phần chưa tách; mảng có tối đa `2 * limit - 1` phần tử. API này **không có trong Java 17**; trên Java 17 dùng cách `Matcher` phía trên.

Nếu cần thao tác nghiệp vụ theo trường, cặp danh sách `fields`/`separators` thường dễ hiểu hơn mảng xen kẽ; nếu chỉ cần tái tạo nguyên văn, mảng xen kẽ của Java 21 rất tiện.

## 5. Các bẫy làm hỏng dữ liệu

1. **Bỏ `-1`**: trường cuối rỗng biến mất, khiến số cột không còn đúng. Hãy thử `"id,name,"`.
2. **Dùng regex sai**: `split(".")` không có nghĩa tách theo dấu chấm; hãy dùng `split(Pattern.quote("."), -1)` hoặc regex escape đúng.
3. **Dùng `[,;]+` thay `[,;]`**: các dấu liền nhau thành một lần tách, làm mất trường rỗng ở giữa.
4. **Xóa trường rỗng sau tách**: `filter(s -> !s.isBlank())` cũng loại các trường chỉ chứa khoảng trắng; làm thay đổi cả dữ liệu lẫn vị trí cột.
5. **Tự động `trim()`**: `" A "` và `"A"` không giống nhau nếu giao thức xem khoảng trắng là dữ liệu.
6. **Ghép bằng một dấu cố định dù nguồn dùng nhiều dấu**: không thể bảo đảm round-trip khi nguồn trộn `,` và `;`.
7. **Nhầm dữ liệu phân cách đơn giản với CSV hoàn chỉnh**: `A,"B,C",D` có dấu phẩy **nằm trong trường được quote**; `split(",", -1)` vẫn cắt sai. CSV thật có escaping, quote đôi và thậm chí xuống dòng trong trường. Hãy dùng parser tuân theo định dạng (chẳng hạn thư viện Apache Commons CSV), đồng thời chỉ định dialect/quote/escape rõ ràng.
8. **Tin vào cách in mặc định của mảng**: `Arrays.toString` có thể hiển thị phần tử rỗng khó phân biệt; khi kiểm tra hãy in `length` và bọc từng giá trị trong dấu nháy.

`String.split` cũng có quy tắc riêng với regex khớp zero-width tại đầu chuỗi: nó **không** tạo trường rỗng đầu giống một dấu phân cách có độ dài dương. Vì thế không suy diễn kết quả của zero-width regex từ các ví dụ về dấu phẩy.

## 6. Checklist và bài tự kiểm tra

Với mỗi dòng dữ liệu phân cách, hãy trả lời bốn câu:

1. Dấu phân cách là **chuỗi cố định** hay một **regex** được chủ ý thiết kế?
2. Trường rỗng ở **đầu, giữa, cuối** có phải giữ lại hay không?
3. Có cần bảo toàn **ký tự và độ dài của dấu phân cách thực tế** để khôi phục chuỗi ban đầu không?
4. Đầu vào có **quote/escape/nested syntax** khiến tách regex đơn giản không đúng đặc tả không?

Tự kiểm tra: với `"|a||"` và dấu literal `|`, `split(Pattern.quote("|"), -1)` phải cho `["", "a", "", ""]`, số trường là 4. Với `"a|b;c|"`, nếu yêu cầu giữ nguyên dấu đã gặp, phải ghi nhớ lần lượt `"|", ";", "|"`; chỉ lưu các trường là chưa đủ.

**Kết luận kỹ thuật:** dùng `split(Pattern.quote(delimiter), -1)` khi cần giữ tất cả trường rỗng với một delimiter cố định. Khi cần giữ chính xác từng dấu phân cách hỗn hợp, dùng `Matcher` (Java 17+) hoặc `splitWithDelimiters(regex, -1)` (Java 21+), rồi xác minh bằng phép tái tạo chuỗi gốc.

## Tài liệu API tham khảo

- Java 17 `String.split`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java 17 `Pattern.quote` và `Matcher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
- Java 21 `Pattern.splitWithDelimiters`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html
