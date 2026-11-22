# Biên bao gồm, biên loại trừ và các nhánh choice trong Java MessageFormat

## 1. Bài toán: một con số có thể cần cách diễn đạt khác nhau

Thông báo chứa số lượng thường không thể ghép một chuỗi cố định cho mọi giá trị:

- `0` tệp: “Không có tệp”.
- `1` tệp: “Một tệp”.
- `2` tệp: “2 tệp”.

Trong Java, `java.text.ChoiceFormat` định nghĩa **các nhánh văn bản theo khoảng giá trị số**. `java.text.MessageFormat` tích hợp cơ chế đó thông qua cú pháp:

```text
{argumentIndex,choice,limit#text|limit<text|...}
```

Một mẫu cơ bản:

```text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

Khi đối số thứ `0` là `0`, chọn `no files`; khi bằng `1`, chọn `one file`; khi lớn hơn `1`, chọn nhánh thứ ba rồi định dạng giá trị số trong `{0,number,integer}`.

Điểm cốt lõi của bài này là hiểu **biên bao gồm (`#`), biên loại trừ (`<`), thứ tự các nhánh**, cách Java quyết định nhánh tại đúng ranh giới và cách phối hợp `ChoiceFormat` với `MessageFormat`.

Lưu ý phạm vi: `choice` là phép chọn theo **ngưỡng số học**. Nó có thể diễn đạt vài trường hợp số lượng đơn giản, nhưng **không tự thay thế các quy tắc số nhiều đầy đủ theo ngôn ngữ tự nhiên**.

## 2. Cú pháp của một choice pattern

Mỗi lựa chọn có ba phần:

```text
limit comparator format
```

Trong đó:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| `limit` | Ngưỡng số để bắt đầu áp dụng nhánh | `0`, `1`, `2.5` |
| `comparator` | Quan hệ với ngưỡng: `#` hoặc `<` | `1#`, `1<` |
| `format` | Chuỗi được xuất ra khi nhánh được chọn | `one file`, `many files` |
| `|` | Dấu phân cách các lựa chọn | `0#zero|1#one` |

Ví dụ:

```text
0#none|1#one|1<many
```

Ở đây không có các câu lệnh `if/else` độc lập. Java chuyển mỗi lựa chọn thành một **ngưỡng hiệu lực**, rồi tìm nhánh tương ứng với giá trị số.

### `#` — biên bao gồm

`1#one` có nghĩa nhánh `one` **bắt đầu được áp dụng từ giá trị 1, bao gồm chính 1**. Khi chưa chạm ngưỡng của nhánh phía sau, giá trị có thể tiếp tục ở nhánh này.

Cụ thể, trong chuỗi `0#none|1#one|1<many`:

- `0` chọn `none`.
- `1` chọn `one`.
- `1.5` chọn `many`.

### `<` — biên loại trừ

`1<many` có nghĩa nhánh `many` chỉ bắt đầu khi giá trị **lớn hơn 1 một cách nghiêm ngặt**. Tại đúng `1`, nhánh này chưa có hiệu lực; tại một giá trị lớn hơn `1`, nó có hiệu lực.

Đặt hai mốc cạnh nhau:

```text
1#one|1<many
```

Điều này đặc biệt hữu ích để tách **bằng 1** và **lớn hơn 1** mà không phải viết vô số mốc nguyên `2`, `3`, `4`.

### `|` ngăn cách các nhánh

`|` là dấu phân cách trong choice pattern. Mẫu:

```text
0#zero|1#one|1<more
```

có đúng **ba lựa chọn**. Khi một phần nội dung đòi hỏi dùng ký tự mang nghĩa đặc biệt trong cú pháp pattern, cần xử lý quy tắc quote/escape của `ChoiceFormat` và `MessageFormat`; không thể đơn giản chèn văn bản bất kỳ chứa `|` hoặc dấu nháy rồi mong parser hiểu đúng. Nên để mẫu đơn giản, và kiểm thử kỹ khi phải chứa ký tự cú pháp.

## 3. Mô hình khoảng giá trị: hiểu toàn bộ chứ không chỉ ranh giới

Với pattern:

```text
0#zero|1#one|1<more
```

ta có thể xem kết quả như sau, trong miền các số thông thường:

| Giá trị đầu vào `n` | Nhánh chọn | Giải thích |
|---:|---|---|
| `-2` | `zero` | Dưới ngưỡng đầu tiên: Java vẫn chọn nhánh đầu |
| `0` | `zero` | `0#` bao gồm 0 |
| `0.5` | `zero` | Chưa đến ngưỡng `1#` |
| `1` | `one` | `1#` bao gồm 1; `1<` chưa áp dụng |
| `1.0001` | `more` | Đã lớn hơn 1 |
| `2` | `more` | Vẫn thuộc nhánh cuối |
| `10` | `more` | Không có nhánh tiếp theo, nên dùng nhánh cuối |

Một cách diễn đạt thực tế là:

- Nhánh đầu: mọi `n < 1`, bao gồm cả các giá trị dưới 0.
- Nhánh thứ hai: chỉ `n = 1` trong mô hình `double` có hai giới hạn liên tiếp `1#` và `1<`.
- Nhánh thứ ba: mọi `n > 1`.

**Cảnh báo về nhánh đầu tiên:** `ChoiceFormat` không tự báo “không có lựa chọn” khi số nhỏ hơn mọi limit. Nó dùng **nhánh đầu**. Vì vậy, nếu số lượng âm là dữ liệu không hợp lệ, phải kiểm tra trước; đừng coi pattern trên đã tự ngăn việc hiển thị `-2` tệp như `zero`.

## 4. Cơ chế chọn nhánh thực tế

`ChoiceFormat` lưu các limit đã được chuẩn hóa thành các ngưỡng số `double`. Về mặt khái niệm, Java chọn nhánh có **ngưỡng hiệu lực lớn nhất nhưng không lớn hơn giá trị cần format**; nếu không vượt được ngưỡng đầu tiên thì vẫn dùng nhánh đầu.

Với toán tử:

- `#`: ngưỡng hiệu lực là chính số được viết.
- `<`: ngưỡng hiệu lực được dịch đến giá trị `double` biểu diễn được kế tiếp phía trên số được viết, để bảo đảm dấu **lớn hơn** mang tính loại trừ.

Đó là lý do `1#one` và `1<many` có thể cùng ghi mốc `1` nhưng vẫn là hai giới hạn hiệu lực khác nhau. Với Java `double`:

```text
1#one  -> effective limit 1.0
1<many -> effective limit 1.0000000000000002
```

Số `1.0000000000000002` là `Math.nextUp(1.0)`, tức số `double` nhỏ nhất lớn hơn `1.0`. Đây **không phải** quy tắc “cộng 0.0000000000000002” cho mọi ngưỡng; khoảng cách giữa các số dấu phẩy động phụ thuộc độ lớn của ngưỡng.

Vì vậy, khi cần xét đúng ranh giới của dữ liệu `double`, hãy hiểu `<` là một biên loại trừ chính xác theo biểu diễn số, không phải “bằng ngưỡng cộng một” theo đơn vị đếm.

## 5. Ví dụ chạy được: kiểm chứng các giá trị sát biên

Tạo tệp `ChoiceBoundaryDemo.java`:

```java
import java.text.ChoiceFormat;
import java.util.Arrays;

public class ChoiceBoundaryDemo {
    public static void main(String[] args) {
        ChoiceFormat choices =
                new ChoiceFormat("0#zero|1#one|1<more");

        double[] values = {-2.0, 0.0, 0.5, 1.0, 1.5, 2.0};

        for (double value : values) {
            System.out.println(value + " => " + choices.format(value));
        }

        System.out.println("limits=" +
                Arrays.toString(choices.getLimits()));

        double justAboveOne = Math.nextUp(1.0);
        System.out.println("nextUp(1.0) => " +
                choices.format(justAboveOne));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ChoiceBoundaryDemo.java
java ChoiceBoundaryDemo
```

Output được kiểm chứng trên JDK:

```text
-2.0 => zero
0.0 => zero
0.5 => zero
1.0 => one
1.5 => more
2.0 => more
limits=[0.0, 1.0, 1.0000000000000002]
nextUp(1.0) => more
```

Điểm quan trọng nằm ở hai dòng cuối: `getLimits()` cho thấy Java lưu mốc `1<` bằng số `double` kế tiếp sau 1. `Math.nextUp(1.0)` đi vào nhánh `more`, còn chính `1.0` ở nhánh `one`.

Ví dụ này dùng `double` vì `ChoiceFormat` kế thừa `NumberFormat` và xác định các khoảng bằng ngưỡng số học. Trong nghiệp vụ đếm đối tượng, bạn thường dùng số nguyên không âm; vậy cần validate trước khi gửi vào formatter.

## 6. Thứ tự các lựa chọn bắt buộc tăng dần

Các nhánh trong một choice pattern phải được khai báo theo **thứ tự giới hạn hiệu lực tăng dần**. Ví dụ hợp lệ:

```text
0#none|1#one|1<more
```

Một mẫu sai:

```text
0#none|2#two|1#one
```

Các ngưỡng `0` → `2` → `1` không tăng dần. Khi khởi tạo `ChoiceFormat` hoặc parse `MessageFormat` chứa mẫu choice tương ứng, Java ném `IllegalArgumentException`.

Đoạn kiểm chứng độc lập, lưu `InvalidChoiceOrder.java`:

```java
import java.text.ChoiceFormat;

public class InvalidChoiceOrder {
    public static void main(String[] args) {
        try {
            new ChoiceFormat("0#none|2#two|1#one");
            System.out.println("Unexpected success");
        } catch (IllegalArgumentException exception) {
            System.out.println("Invalid choice order");
        }
    }
}
```

Chạy `javac InvalidChoiceOrder.java` và `java InvalidChoiceOrder`:

```text
Invalid choice order
```

Ngay cả khi các mốc viết ra trông giống nhau, hãy xét **toán tử**:

- `1#one|1<more` có ngưỡng hiệu lực tăng (1.0 rồi nextUp(1.0)), nên hợp lệ.
- `1<more|1#one` đi ngược lại thứ tự ngưỡng hiệu lực, nên không hợp lệ.

Đừng sắp xếp choice theo độ dài câu, thứ tự từ điển hoặc thứ tự “zero, many, one”; sắp theo **mốc toán học đã xác định**.

## 7. Cạm bẫy: `2#many` không đồng nghĩa `>1`

Hai pattern nhìn gần giống nhưng khác logic:

```text
0#zero|1#one|2#many
0#zero|1#one|1<many
```

Với **số nguyên không âm**, cả hai thường cho cùng kết quả ở 0, 1, 2, 3. Nhưng với số thực:

| Giá trị | `...|2#many` | `...|1<many` |
|---:|---|---|
| `1.0` | `one` | `one` |
| `1.1` | `one` | `many` |
| `1.5` | `one` | `many` |
| `2.0` | `many` | `many` |

Nếu yêu cầu thật sự là “nằm trong nhánh nhiều khi **n > 1**”, phải dùng `1<`. Còn nếu nghiệp vụ chỉ chấp nhận số đếm nguyên, `2#` có thể diễn tả cùng ranh giới mong muốn nhưng làm giả định “số lượng là nguyên” trở thành điều kiện quan trọng cần được kiểm tra.

Tương tự:

```text
0#non-positive|0<positive
```

sẽ chọn `non-positive` cho mọi số `n <= 0` và `positive` cho `n > 0`. Trong cách dùng này, nhánh đầu cũng bao trùm các giá trị âm nhỏ hơn mốc đầu tiên.

## 8. Các nhánh choice bên trong MessageFormat

`ChoiceFormat` tự format một giá trị `Number` thành chuỗi. `MessageFormat` kết hợp nhiều tham số trong một thông báo, cho phép viết `choice` ngay bên trong placeholder:

```text
Found {0,choice,0#no files|1#one file|1<{0,number,integer} files}.
```

Ở đây:

- `0` đầu tiên là **vị trí đối số** (argument index), không phải giá trị số 0.
- `choice` yêu cầu dùng logic ngưỡng của `ChoiceFormat`.
- `0#no files`, `1#one file`, `1<...` là ba nhánh.
- Trong nhánh thứ ba, `{0,number,integer}` là placeholder con để format lại **cùng đối số số 0** với kiểu hiển thị số nguyên.

### Chương trình Java 17+ độc lập

Lưu thành `MessageChoiceDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageChoiceDemo {
    public static void main(String[] args) {
        String pattern =
                "Found {0,choice,0#no files|1#one file|" +
                "1<{0,number,integer} files}.";

        MessageFormat formatter = new MessageFormat(pattern, Locale.US);

        for (int count : new int[] {0, 1, 2, 12}) {
            System.out.println(formatter.format(new Object[] {count}));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac MessageChoiceDemo.java
java MessageChoiceDemo
```

Output:

```text
Found no files.
Found one file.
Found 2 files.
Found 12 files.
```

Với `count = 2`, `MessageFormat` chọn nhánh `1<`, sau đó nhận thấy chuỗi nhánh chứa placeholder `{0,number,integer}` và định dạng tiếp nó với locale `Locale.US`.

**Phân biệt hai tầng xử lý:**

1. **Chọn nhánh:** dựa vào số đầu vào và các giới hạn `#` / `<`.
2. **Tạo thông điệp:** sử dụng chuỗi của nhánh đã chọn; nếu có placeholder lồng, `MessageFormat` xử lý theo quy tắc của nó.

Không đặt `{0,number,integer}` trong toàn bộ nhánh nếu bạn chỉ muốn hiển thị “one” ở trường hợp bằng 1. Kỹ thuật dùng placeholder lồng hữu ích khi cùng một nhánh cần đưa số thật vào câu.

## 9. Tại sao MessageFormat xử lý mẫu choice lồng được?

Theo hành vi `MessageFormat` của Java, nếu một nhánh của `ChoiceFormat` được chọn và **chuỗi kết quả chứa dấu `{`**, hệ thống có thể phân tích tiếp chuỗi đó như một mẫu `MessageFormat`, dùng cùng tập đối số để thay các placeholder lồng.

Điều này giải thích tại sao đoạn:

```text
1<{0,number,integer} files
```

có thể hiển thị `2 files` thay vì trả nguyên văn `{0,number,integer} files`.

Tuy nhiên, sự lồng pattern dẫn đến hai điều cần cẩn thận:

- Nếu thông điệp hiển thị cần dấu ngoặc nhọn literal, dấu nháy đơn hoặc ký tự cú pháp `|`, phải tuân thủ quy tắc quoting của `MessageFormat` và `ChoiceFormat`; việc escape ở một tầng chưa chắc đủ ở tầng tiếp theo. Kiểm thử các chuỗi thực tế chứa ký tự đặc biệt.
- Không đưa văn bản người dùng không đáng tin vào **pattern** rồi biên dịch như cú pháp `MessageFormat`. Đưa dữ liệu người dùng vào **arguments**; pattern nên nằm trong resource/config đã được kiểm soát.

Trong ứng dụng đa ngôn ngữ, các bản dịch của pattern nên giữ chính xác chỉ số argument. Khi nhánh chứa placeholder lồng, kiểm thử toàn bộ trường hợp theo từng locale để phát hiện ngoặc và dấu nháy sai.

## 10. Chọn nhánh theo giá trị gốc, không theo số đã làm tròn để hiển thị

Một điểm gây lỗi hiển thị: `ChoiceFormat` so sánh **giá trị số thật**, không chọn nhánh dựa trên chuỗi đã được làm tròn bởi `{0,number,integer}`.

Ví dụ chương trình độc lập `ChoiceRoundingDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceRoundingDemo {
    public static void main(String[] args) {
        MessageFormat formatter = new MessageFormat(
                "{0,choice,0#zero|1#one|1<{0,number,integer} items}",
                Locale.US);

        System.out.println(formatter.format(new Object[] {1.0}));
        System.out.println(formatter.format(new Object[] {1.4}));
        System.out.println(formatter.format(new Object[] {2.0}));
    }
}
```

Chạy:

```bash
javac ChoiceRoundingDemo.java
java ChoiceRoundingDemo
```

Output đã kiểm tra:

```text
one
1 items
2 items
```

Tại `1.4`, nhánh **`1<`** được chọn đúng vì 1.4 lớn hơn 1, nhưng `{0,number,integer}` làm tròn phần hiển thị thành **1**. Kết quả `1 items` nghe có vẻ mâu thuẫn. Đó không phải lỗi của `ChoiceFormat`; đó là hậu quả khi nghiệp vụ cho phép số thực trong khi mẫu từ ngữ giả định một số đếm nguyên.

Nếu số là **số lượng đối tượng**, hãy xác thực là số nguyên không âm trước khi định dạng; nếu số là đại lượng liên tục, hãy chọn pattern phù hợp với số thập phân và ngữ nghĩa thực tế.

## 11. Trường hợp bằng 0, số âm và miền không mong muốn

Pattern `0#none|1#one|1<many` chỉ ổn khi đã xác định miền đầu vào. Với số âm, `ChoiceFormat` thường chọn nhánh đầu (`none`), vì nó không có nhánh nào có giới hạn thấp hơn `0`. Trong ứng dụng quản lý số lượng, cách xử lý đúng là **không đưa số âm hợp lệ hóa ngầm** bằng cách đổi thành “không có”.

Một hàm tự kiểm tra số đếm trước khi format có thể viết như sau (đoạn code dùng trong class đã import `MessageFormat`):

```java
static String filesMessage(MessageFormat formatter, int count) {
    if (count < 0) {
        throw new IllegalArgumentException("count must be >= 0");
    }
    return formatter.format(new Object[] {count});
}
```

Không dùng số thực `double` có giá trị không hữu hạn như `NaN` hay các giá trị vô cực từ input không được kiểm soát làm số lượng. Nếu số đến từ JSON, database hoặc phép tính, hãy kiểm tra loại dữ liệu và miền hợp lệ trước khi chọn nhánh.

Nếu cần nhánh riêng cho số âm để **hiển thị lỗi hoặc trạng thái**, có thể thiết kế ngưỡng bắt đầu bằng số âm hoặc `-∞`, nhưng phải bảo đảm tính liên tục, đúng thứ tự và ý nghĩa cho tất cả giá trị. Với nghiệp vụ thông thường, validate và báo lỗi rõ ràng dễ bảo trì hơn.

## 12. ChoiceFormat không tự hiểu mọi quy tắc số nhiều

Ngữ cảnh cha “Số nhiều và ngữ pháp” khiến `choice` thường được dùng cho phân biệt `0`, `1` và `n > 1`. Tuy nhiên, **quy tắc số nhiều không giống nhau ở mọi ngôn ngữ**.

Một số ngôn ngữ dùng các nhóm phụ thuộc chữ số cuối, bội số, phần thập phân hoặc hình thái ngữ pháp. `ChoiceFormat` chọn theo **các khoảng liên tiếp của một giá trị số**, không tự áp dụng các hạng plural theo CLDR. Vì thế, một pattern đơn giản cho tiếng Anh không thể tự suy ra quy tắc đầy đủ của tiếng Ả Rập, Nga, Ba Lan và nhiều ngôn ngữ khác.

Điều nên làm:

1. Dùng `ChoiceFormat` khi bài toán thật sự là **chia các khoảng số rõ ràng** hoặc vài trường hợp số lượng đơn giản do sản phẩm quy định.
2. Đừng sao chép cùng một pattern `0#...|1#...|1<...` sang mọi locale mà không xem xét quy tắc ngôn ngữ.
3. Với sản phẩm i18n lớn, cần quy tắc plural theo locale, ordinal, gender, case hoặc các dạng ngữ pháp phức tạp, hãy cân nhắc thư viện có hỗ trợ **plural rules** thực sự (ví dụ ICU4J) và quản lý bản dịch theo ngôn ngữ.
4. Dù dùng thư viện nào, vẫn kiểm thử các giá trị **0, 1, 2**, những mốc quan trọng theo từng locale và số thập phân nếu sản phẩm chấp nhận.

Choice là cơ chế rẽ nhánh theo **giá trị**, còn plural là quy tắc về **ngôn ngữ**; chúng có vùng giao nhau nhưng không hoàn toàn trùng nhau.

## 13. Các lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Viết `1#many` và mong >1 | `#` bao gồm cả 1 | Dùng `1<many` nếu muốn nghiêm ngặt >1 |
| Viết `2#many` và cho phép số thực | `1.5` vẫn ở nhánh `one` | Dùng `1<` hoặc validate số nguyên |
| Đảo `0, 2, 1` | Limit phải tăng dần | Sắp theo ngưỡng tăng |
| Chỉ có `0#zero|1#one` | Mọi số >1 vẫn vào nhánh cuối `one` | Thêm nhánh `1<many` |
| Cho rằng dưới limit đầu sẽ không có kết quả | `ChoiceFormat` dùng nhánh đầu | Validate miền số hoặc chọn limit phủ toàn bộ miền |
| Cho rằng `<` là “bằng hoặc lớn hơn” | `<` có biên loại trừ | Dùng `#` khi cần bao gồm giá trị limit |
| Dùng `Math.nextUp(1)` rồi so output `double` | Literal `1` có thể chọn overload kiểu float | Viết `Math.nextUp(1.0)` để lấy kết quả double |
| Định dạng `1.4` thành số nguyên rồi chọn theo “1” | Choice chọn theo số gốc, format là bước sau | Validate miền hoặc tránh làm tròn gây mâu thuẫn |
| Chèn `|`, `'` và `{` tùy ý vào pattern | Ký tự có nghĩa cú pháp | Quote đúng từng tầng; viết test với bản dịch thật |
| Giả định `choice` là CLDR plural | Chỉ có lựa chọn bằng ngưỡng | Sử dụng plural rules theo ngôn ngữ khi cần |

## 14. Bộ trường hợp biên nên kiểm thử

Với pattern `0#zero|1#one|1<more`, một bộ kiểm thử tối thiểu:

| Test input | Kết quả kỳ vọng | Mục đích |
|---:|---|---|
| `0.0` | `zero` | Biên bao gồm đầu |
| `0.5` | `zero` | Giá trị giữa hai giới hạn |
| `1.0` | `one` | Chạm chính xác biên `1#` |
| `Math.nextUp(1.0)` | `more` | Giá trị double đầu tiên lớn hơn 1 |
| `2.0` | `more` | Sau biên loại trừ |
| `-1.0` | `zero` | Hiểu hành vi dưới giới hạn đầu |
| `1.4` trong MessageFormat dùng định dạng integer | `1 items` | Phát hiện sự khác nhau giữa chọn nhánh và hiển thị |

Với các pattern dùng trong bản dịch, nên kiểm thử cả **chuỗi được hiển thị** và **ý nghĩa của lựa chọn**, không chỉ kiểm tra code không ném ngoại lệ. Nếu count được giới hạn là nguyên không âm, test thêm validation `-1` phải bị từ chối trước khi vào formatter.

## 15. Tự kiểm tra kiến thức

**Câu 1.** `1#one` có bao gồm số 1 không?  
**Đáp án:** Có. `#` là biên bao gồm.

**Câu 2.** `1<more` có bao gồm 1 không?  
**Đáp án:** Không. Nó chỉ áp dụng khi lớn hơn 1.

**Câu 3.** `0#zero|1#one|1<more`, input 0.75 chọn nhánh nào?  
**Đáp án:** `zero`; ngưỡng `1#` chưa đạt.

**Câu 4.** Với cùng pattern, input 1.0001 chọn nhánh nào?  
**Đáp án:** `more` vì lớn hơn 1.

**Câu 5.** `0#zero|1#one|2#many` có phân biệt đúng 1.5 và 2 không?  
**Đáp án:** 1.5 vẫn chọn `one`, 2 chọn `many`. Nếu cần mọi số thực lớn hơn 1 vào `many`, dùng `1<many`.

**Câu 6.** Tại sao `0#zero|2#two|1#one` không hợp lệ?  
**Đáp án:** Các giới hạn không tăng dần; Java ném `IllegalArgumentException`.

**Câu 7.** Vì sao MessageFormat có thể hiện `1 items` cho giá trị 1.4?  
**Đáp án:** `ChoiceFormat` chọn nhánh lớn hơn 1 theo số gốc; placeholder `number,integer` làm tròn cách hiển thị sau đó.

**Câu 8.** Có thể dùng một pattern choice để thay mọi quy tắc số nhiều của tất cả ngôn ngữ không?  
**Đáp án:** Không. ChoiceFormat chia khoảng số, không tự thực thi toàn bộ plural rules theo locale.

**Ghi nhớ:** Trong `ChoiceFormat`, **`#` nghĩa là “từ mốc này, kể cả mốc”**, còn **`<` nghĩa là “lớn hơn mốc, loại trừ mốc”**. Các nhánh phải được xếp theo giới hạn hiệu lực tăng dần. Khi nhúng vào `MessageFormat`, lựa chọn nhánh và định dạng số là hai giai đoạn; cần kiểm thử cả hai.

**Tài liệu chính thức:** [Java SE 17 — ChoiceFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html) · [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) · [Java SE 17 — Math.nextUp](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#nextUp(double)).
