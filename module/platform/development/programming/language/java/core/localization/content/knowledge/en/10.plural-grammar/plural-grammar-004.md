# Kết hợp ChoiceFormat với MessageFormat

## 1. Bài toán: số lượng làm thay đổi cả câu

Trong ứng dụng đa ngôn ngữ, nội dung thông báo thường phụ thuộc số lượng:

- Không có tệp nào.
- Có một tệp.
- Có 2 tệp.

Với tiếng Anh, ví dụ tương ứng là “No files”, “One file”, “2 files”. Một cách triển khai thiếu linh hoạt là ghép số lượng với một danh từ đã dịch:

```java
String text = "You have " + count + " files.";
```

Câu này không đúng khi `count == 1`: “You have 1 files.”. Thêm điều kiện `if (count == 1)` chỉ xử lý một vài trường hợp tiếng Anh, trong khi ngữ pháp của ngôn ngữ khác có thể thay đổi cả động từ, danh từ, lời xưng hô hoặc dấu câu.

Java có hai API trong `java.text` giúp xử lý **một số dạng câu thay đổi theo khoảng giá trị số**:

- **`ChoiceFormat`** chọn một nhánh văn bản dựa trên các ngưỡng số. Ví dụ, từ 0 trở xuống chọn câu A, đúng 1 chọn câu B, lớn hơn 1 chọn câu C.
- **`MessageFormat`** chèn tham số vào một **câu hoàn chỉnh** có cú pháp `{0}`, `{1}`, …; khi nhánh `choice` chứa một placeholder lồng nhau, `MessageFormat` có thể diễn giải tiếp nhánh đó để chèn số lượng.

Kết hợp hai API cho phép viết một thông điệp duy nhất với các lựa chọn:

```text
You have {0,choice,0#no files|1#one file|1<{0,number,integer} files}.
```

Với `0` là “You have no files.”, `1` là “You have one file.” và `2` là “You have 2 files.”. Những phần văn bản thay đổi được giữ trong cùng mẫu thay vì ép người dịch ghép từng mảnh.

**Phạm vi quan trọng:** `ChoiceFormat` là cơ chế **chọn theo ngưỡng số**, không phải bộ giải đầy đủ quy tắc số nhiều của mọi ngôn ngữ. Điều này ảnh hưởng cách thiết kế bài toán thực tế.

## 2. ChoiceFormat hoạt động thế nào?

`java.text.ChoiceFormat` biểu diễn một dãy ngưỡng và những chuỗi tương ứng. Với giá trị số đầu vào, nó tìm nhánh có giới hạn phù hợp theo các khoảng được khai báo. Các giới hạn phải có thứ tự tăng.

Mẫu `ChoiceFormat` cơ bản:

```text
0#No files|1#One file|1<Many files
```

Ý nghĩa cú pháp:

| Thành phần | Ý nghĩa |
| --- | --- |
| `0`, `1` | Mốc số dùng để chọn nhánh |
| `#` | Nhánh áp dụng **từ mốc đó trở lên**, gồm chính mốc |
| `<` | Nhánh áp dụng cho giá trị **lớn hơn** mốc, không gồm mốc |
| `|` | Ký tự phân cách các lựa chọn |
| Văn bản sau dấu phân cách mốc | Giá trị trả về khi chọn nhánh đó |

Với `0#No files|1#One file|1<Many files`:

- `0` chọn `No files`.
- `1` chọn `One file`.
- `2` chọn `Many files`.

Ở nhánh `1<`, mốc số lớn hơn 1 bắt đầu ngay sau `1` trong biểu diễn `double`; các giá trị `1.1` cũng nằm trong nhánh này. Vì thế cách phân nhánh này **chỉ phù hợp** khi hợp đồng chấp nhận các đầu vào được dùng, ví dụ số lượng nguyên không âm.

**Một lỗi tinh vi:** nếu giá trị nhỏ hơn mốc đầu tiên, `ChoiceFormat` vẫn chọn lựa chọn đầu. Vì vậy mẫu bắt đầu từ `0#` có thể hiển thị “No files” cho một số âm. Nếu số âm là dữ liệu không hợp lệ, hãy kiểm tra đầu vào trước khi định dạng, thay vì hy vọng ChoiceFormat tự chặn.

Một `ChoiceFormat` có thể được tạo từ chuỗi pattern hoặc từ hai mảng cùng kích thước: `double[] limits` và `String[] formats`. Đây là hai cách tạo ra cùng một cơ chế chọn nhánh theo ngưỡng.

## 3. MessageFormat bổ sung điều gì?

`MessageFormat` có cú pháp tham số:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

Ví dụ:

- `{0}`: dùng đối số thứ nhất.
- `{0,number,integer}`: trình bày đối số thứ nhất như số nguyên.
- `{0,choice,0#none|1#one|1<many}`: chọn nhánh theo số.
- `{1}`: dùng đối số thứ hai, có thể là tên người nhận thông báo.

Khi `MessageFormat` xử lý tham số `choice`:

1. Lấy đối số số học tương ứng.
2. Đưa giá trị đó cho `ChoiceFormat`.
3. Chọn văn bản của một nhánh.
4. Nếu văn bản nhánh chứa placeholder kiểu `{0,number,integer}`, `MessageFormat` xử lý nhánh như một **mẫu thông điệp lồng nhau** với cùng danh sách đối số.

Nhờ bước thứ tư, nhánh “nhiều” có thể chứa **số lượng thực**; nếu chỉ gọi trực tiếp `ChoiceFormat.format(2)`, chuỗi `{0,number,integer} files` chỉ là đầu ra văn bản chưa được MessageFormat diễn giải tiếp.

Ví dụ mẫu:

```text
Có {0,choice,0#không có tệp nào|1#một tệp|1<{0,number,integer} tệp}.
```

Người dùng nhìn thấy:

| Đầu vào `count` | Kết quả |
| ---: | --- |
| 0 | `Có không có tệp nào.` |
| 1 | `Có một tệp.` |
| 2 | `Có 2 tệp.` |

Mẫu trên **đúng về cơ chế nhưng không tự nhiên ở câu 0** (“Có không có tệp nào”). Đây là bài học quan trọng: thuật toán chọn nhánh có thể đúng mà **toàn câu vẫn sai ngữ pháp**. Người dịch cần được phép thay **cả mệnh đề** trong mỗi nhánh, không bị trói vào một prefix cứng.

## 4. Ví dụ hoàn chỉnh: mỗi nhánh là một câu tự nhiên

Đặt nguyên thông điệp vào từng nhánh, để ngữ pháp được điều chỉnh trọn vẹn:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceMessageDemo {
    public static void main(String[] args) {
        String pattern =
                "{0,choice,0#Không có tệp nào.|1#Có một tệp.|1<Có {0,number,integer} tệp.}";

        MessageFormat message = new MessageFormat(
                pattern, Locale.forLanguageTag("vi-VN"));

        for (int count : new int[] {0, 1, 2, 5}) {
            System.out.println(message.format(new Object[] {count}));
        }
    }
}
```

Lưu thành tệp `ChoiceMessageDemo.java` với UTF-8. Chạy trên JDK 17+:

```bash
javac -encoding UTF-8 ChoiceMessageDemo.java
java ChoiceMessageDemo
```

Stdout:

```text
Không có tệp nào.
Có một tệp.
Có 2 tệp.
Có 5 tệp.
```

Giải thích:

- `0#` là nhánh đầu, bao gồm giá trị `0`.
- `1#` dành cho giá trị `1`.
- `1<` dành cho các giá trị lớn hơn `1`.
- `{0,number,integer}` ở nhánh cuối được xử lý tiếp sau khi `ChoiceFormat` chọn nhánh, nên kết quả chứa chính con số đầu vào.

Đây là ví dụ cho **số đếm nguyên không âm**, nơi những câu trên phù hợp. Trước khi áp dụng trong ứng dụng, cần quyết định rõ ứng xử với số âm, số thập phân và giá trị lớn. Nếu người dùng nhập `-2` mà hệ thống hiển thị “Không có tệp nào”, đó là lỗi quy tắc nghiệp vụ cần xử lý trước khi render.

## 5. Không phải lúc nào cũng cần nhúng choice trực tiếp trong pattern

Có hai cách kết hợp thường dùng:

**Cách A — cú pháp `choice` nằm trong MessageFormat pattern**

```java
MessageFormat message = new MessageFormat(
        "{0,choice,0#No files.|1#One file.|1<{0,number,integer} files.}",
        Locale.US);
```

**Cách B — tạo `ChoiceFormat` bằng Java rồi gắn vào một argument của `MessageFormat`**

```java
ChoiceFormat choice = new ChoiceFormat(limits, labels);
MessageFormat message = new MessageFormat("{0}", Locale.US);
message.setFormatByArgumentIndex(0, choice);
```

Cả hai đều dùng `MessageFormat` để xử lý tham số. Cách A thuận tiện khi pattern được bản địa hóa trong file tài nguyên; cách B phù hợp khi các mốc chọn nhánh được xây dựng từ chính sách do code kiểm soát. Tuy nhiên, nếu muốn người dịch thay đổi cấu trúc câu, nên giữ **mẫu hoàn chỉnh** trong tệp bản dịch thay vì cố định mọi nhánh trong Java.

### Ví dụ chạy được với ChoiceFormat tạo từ mảng

```java
import java.text.ChoiceFormat;
import java.text.MessageFormat;
import java.util.Locale;

public class ProgrammaticChoiceDemo {
    public static void main(String[] args) {
        double[] limits = {0, 1, 2};
        String[] labels = {
                "No files",
                "One file",
                "{0,number,integer} files"
        };

        ChoiceFormat choices = new ChoiceFormat(limits, labels);
        MessageFormat message =
                new MessageFormat("Result: {0}.", Locale.US);

        message.setFormatByArgumentIndex(0, choices);

        for (int count : new int[] {0, 1, 2, 5}) {
            System.out.println(
                    message.format(new Object[] {count})
            );
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ProgrammaticChoiceDemo.java
java ProgrammaticChoiceDemo
```

Stdout:

```text
Result: No files.
Result: One file.
Result: 2 files.
Result: 5 files.
```

Ở đây `limits` có ba mốc 0, 1, 2. Với đầu vào 2 hoặc 5, `ChoiceFormat` chọn phần tử cuối trong `labels`. `MessageFormat` sau đó nhận thấy chuỗi đã chọn chứa `{0,number,integer}`, nên chèn số lượng thực.

**Phân biệt:** khi dùng mảng với `new ChoiceFormat(limits, labels)`, mỗi mốc của mảng là **giới hạn đầu khoảng có bao gồm chính giới hạn đó**. Với pattern dạng text, `1<` là cách biểu đạt mốc mở, thích hợp cho đầu vào lớn hơn 1. Không nên thay `1<` thành `2#` nếu có thể nhận số thực 1.5; chúng chỉ tương đương khi hợp đồng đầu vào đã giới hạn số nguyên.

## 6. Kết hợp thêm tham số khác, như tên người nhận

Thông báo thường chứa cả số lượng và tên người dùng. Có thể dùng `{0}` cho số lượng, `{1}` cho tên:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class NamedChoiceDemo {
    public static void main(String[] args) {
        String pattern =
                "{1}, {0,choice,0#bạn không có tin nhắn mới.|1#bạn có một tin nhắn mới.|1<bạn có nhiều tin nhắn mới.}";
        MessageFormat message = new MessageFormat(pattern, Locale.US);

        System.out.println(message.format(new Object[] {0, "Mai"}));
        System.out.println(message.format(new Object[] {1, "Mai"}));
    }
}
```

Ví dụ này in hai trường hợp số lượng 0 và 1. Nhánh `1<` hợp lệ cho mọi số lượng lớn hơn 1; nếu muốn hiện số lượng thực tế ở nhánh đó, dùng mẫu đầy đủ sau:

```text
{1}, {0,choice,0#bạn không có tin nhắn mới.|1#bạn có một tin nhắn mới.|1<bạn có {0,number,integer} tin nhắn mới.}
```

Dữ liệu động có thể xuất hiện ở vị trí khác nhau theo ngôn ngữ. Điều này đặc biệt quan trọng khi câu có nhiều tham số. Một bản dịch khác có thể đặt tên `{1}` ở cuối câu, hoặc lược bỏ lời xưng hô nếu phù hợp ngữ cảnh. **Đừng chia bản dịch thành các mảnh rồi nối cố định ở Java.**

## 7. Tách pattern theo locale qua ResourceBundle

Trong dự án đa ngôn ngữ, mỗi locale nên có **toàn bộ thông điệp**, bao gồm các nhánh của `ChoiceFormat`. Ví dụ tổ chức tệp:

```text
src/main/resources/
├── messages.properties
├── messages_en.properties
└── messages_vi.properties
```

Nội dung `messages_en.properties`:

```properties
files.summary={0,choice,0#No files.|1#One file.|1<{0,number,integer} files.}
```

Nội dung `messages_vi.properties`:

```properties
files.summary={0,choice,0#Không có tệp nào.|1#Có một tệp.|1<Có {0,number,integer} tệp.}
```

Nội dung bundle gốc `messages.properties` nên có key cùng ý nghĩa và một mẫu dự phòng đầy đủ:

```properties
files.summary={0,choice,0#No files.|1#One file.|1<{0,number,integer} files.}
```

Java lấy pattern theo key và định dạng:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleChoiceDemo {
    static String render(Locale locale, int count) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", locale);

        String pattern = bundle.getString("files.summary");
        MessageFormat formatter = new MessageFormat(pattern, locale);
        return formatter.format(new Object[] {count});
    }

    public static void main(String[] args) {
        System.out.println(render(Locale.US, 1));
        System.out.println(render(Locale.US, 3));
        System.out.println(render(Locale.forLanguageTag("vi-VN"), 0));
        System.out.println(render(Locale.forLanguageTag("vi-VN"), 2));
    }
}
```

Đặt `BundleChoiceDemo.java` cạnh ba tệp tài nguyên để chạy độc lập:

```bash
javac -encoding UTF-8 BundleChoiceDemo.java
java -cp . BundleChoiceDemo
```

Stdout:

```text
One file.
3 files.
Không có tệp nào.
Có 2 tệp.
```

Trong dự án Maven hoặc Gradle, khi `messages*.properties` nằm ở `src/main/resources`, build tool thường đưa chúng vào classpath. Chạy `ResourceBundle.getBundle("messages", locale)` tại root classpath không cần tự mở file bằng `FileInputStream`.

**Hai nhiệm vụ tách biệt:** `ResourceBundle` chọn **mẫu văn bản** theo locale và key; `MessageFormat`/ `ChoiceFormat` chọn **nhánh và chèn tham số**. Nếu bộ tài nguyên thiếu locale hoặc key, quy tắc fallback/`MissingResourceException` của ResourceBundle vẫn áp dụng; `ChoiceFormat` không giải quyết việc chọn bản dịch.

## 8. Tại sao phải dịch cả các nhánh, không dịch từng từ?

Một số cách tiếp cận sai:

```java
// Mẫu phụ thuộc cấu trúc tiếng Anh.
String result = count + " " + bundle.getString("file.label")
        + bundle.getString("files.suffix");
```

Cách này giả định thứ tự **số → danh từ → phần còn lại** giống nhau ở mọi ngôn ngữ. Ngay cả khi dịch `file.label`, hệ thống vẫn không có quyền thay đổi cả câu hoặc động từ.

Cách tốt hơn: một key `files.summary` có toàn bộ pattern, và mỗi nhánh chứa mệnh đề tự nhiên. Tiếng Anh có “No files”, “One file”, “2 files”; tiếng Việt có thể dùng “Không có tệp nào”, “Có một tệp”, “Có 2 tệp”. Các chi tiết như vị trí chủ ngữ, đại từ, dấu câu và hình thức danh từ được xử lý bên trong bản dịch.

Người dịch cần biết:

- `{0}` là số lượng tệp, phải là số nguyên không âm.
- `0#`, `1#`, `1<` là **cú pháp điều khiển nhánh**, không được tùy tiện đổi.
- `{0,number,integer}` là placeholder của Java, không phải một phần câu để dịch.
- Những đoạn văn nằm sau các dấu `#` hoặc `<` có thể được dịch sao cho ngữ pháp hoàn chỉnh.
- Nếu ngôn ngữ cần các nhóm số khác 0/1/nhiều, phải báo cho người thiết kế giải pháp i18n, không cố ép một mẫu tiếng Anh.

Cần có **ngữ cảnh dịch** cho key, ví dụ vị trí hiển thị, đơn vị của số lượng, kiểu dữ liệu đầu vào, yêu cầu dấu câu và những giá trị thử nghiệm. Pattern hợp lệ về cú pháp vẫn có thể sai ngữ pháp.

## 9. Các giới hạn ngữ pháp của ChoiceFormat

`ChoiceFormat` chủ yếu dựa trên **các khoảng số tăng dần**. Điều đó đủ cho các thông điệp có nhánh:

- Không có kết quả (`count == 0`).
- Đúng một kết quả (`count == 1`).
- Nhiều hơn một kết quả (`count > 1`).

Nhưng quy tắc số nhiều của các ngôn ngữ không phải lúc nào cũng chia thành các khoảng liên tục.

Ví dụ, một số ngôn ngữ sử dụng dạng danh từ khác nhau tùy chữ số cuối cùng hoặc hai chữ số cuối của số đếm. Khi ấy hai số xa nhau có thể thuộc cùng một loại ngữ pháp, trong khi hai số kề nhau thuộc loại khác. `ChoiceFormat` dạng ngưỡng thuần túy khó biểu diễn chính xác loại quy tắc theo modulo đó. Một số ngôn ngữ còn cần nhiều plural category như `zero`, `one`, `two`, `few`, `many`, `other`; quy tắc không thể suy ra chỉ từ tiếng Anh.

**Không được kết luận rằng mẫu `0#...|1#...|1<...` là “cách làm số nhiều cho mọi locale”.** Nó là một **quy tắc nghiệp vụ cụ thể dựa trên ngưỡng**, được kiểm tra với số lượng nguyên không âm và những ngôn ngữ thực sự hỗ trợ.

Khi dự án có nhiều ngôn ngữ với plural/gender phức tạp:

1. Xác định các ngôn ngữ và quy tắc plural thực tế.
2. Tham khảo quy tắc CLDR, ví dụ số 0/1/2/5/11/21/101 có thể cần các nhánh khác nhau tùy ngôn ngữ.
3. Cân nhắc thư viện i18n hỗ trợ plural rules như ICU4J hoặc cơ chế framework đã được kiểm chứng.
4. Vẫn để **toàn bộ mệnh đề** trong từng nhánh và kiểm thử bằng người hiểu ngôn ngữ đó.

Đây không phải lý do loại bỏ ChoiceFormat: API rất hữu ích với các lựa chọn dựa trên ngưỡng như số kết quả, khoảng điểm, mức cảnh báo hoặc nhóm số đơn giản. Chỉ cần không dùng nó vượt phạm vi ngữ pháp mà nó biểu diễn được.

## 10. Giá trị biên, số thực và độ chính xác

### 10.1. Giá trị âm

Một `ChoiceFormat` bắt đầu bằng `0#No files` cũng có thể chọn nhánh đầu nếu đầu vào nhỏ hơn 0. Nếu phép đếm phải không âm, hãy kiểm tra:

```java
if (count < 0) {
    throw new IllegalArgumentException("count must be non-negative");
}
```

Đây là **đoạn mã minh họa**, phải đặt trong hàm có biến `count`. Không nên gọi `Math.max(0, count)` theo thói quen vì làm mất khả năng phát hiện dữ liệu nghiệp vụ không hợp lệ.

### 10.2. Số không nguyên

`1<` áp dụng cho mọi số lớn hơn 1, gồm `1.5`, không chỉ `2, 3, 4`. Nếu thông điệp nói “tệp”, “người”, “sản phẩm” và đầu vào phải là số đếm, nên dùng `int`/`long` và kiểm tra phạm vi hợp lệ.

### 10.3. Số rất lớn

`ChoiceFormat` xử lý các mốc theo `double`; không nên dựa vào phép chọn ngưỡng khi số lượng nguyên vượt phạm vi có thể biểu diễn chính xác của `double` (khoảng `2^53`). Nếu nghiệp vụ đòi hỏi số nguyên lớn, cần thiết kế phân loại bằng kiểu dữ liệu và điều kiện chính xác hơn ở tầng logic, rồi chọn mẫu câu phù hợp.

### 10.4. NaN và vô cực

Kết quả chọn nhánh cho `NaN` hoặc vô cực không nên được xem là cách xác nhận dữ liệu hợp lệ. Với đầu vào là số lượng, hãy chặn `NaN` và giá trị không hữu hạn nếu kiểu dữ liệu có thể chứa chúng. Dùng kiểu nguyên khi bài toán đếm là số nguyên.

### 10.5. Các mốc và giá trị ngang nhau

Pattern chọn nhánh phải có các giới hạn được sắp theo thứ tự tăng. Đổi thứ tự hay làm trùng những mốc sẽ dẫn đến mẫu không như dự định hoặc lỗi cú pháp. Với dữ liệu số thực, phân biệt `1#` (bao gồm 1) và `1<` (lớn hơn 1); với các mốc 0, 1, 2 trong mảng constructor, từng mốc được tính từ giới hạn đó trở lên.

## 11. Dấu nháy, dấu phân cách và pattern lồng nhau

`MessageFormat` dùng dấu nháy đơn `'` để quote literal, và dấu `''` để biểu diễn một dấu nháy đơn. `ChoiceFormat` còn dùng các ký tự `|`, `#`, `<` để phân tách nhánh và ngưỡng.

Vì vậy khi đặt ChoiceFormat vào MessageFormat:

- Pattern có **hai tầng cú pháp**: phần chọn nhánh và mẫu thông điệp.
- Không tự chèn dấu `'` để “escape” theo cách của Java string; quy tắc quote trong runtime pattern khác với escaping trong Java source.
- Nếu dịch giả cần in ra dấu `|` hoặc dấu ngoặc nhọn, phải dùng cơ chế quote thích hợp và kiểm thử đầu ra sau khi cả hai tầng parser xử lý.
- Tránh ghép dữ liệu người dùng vào phần **pattern**; hãy truyền dữ liệu đó dưới dạng **argument**. Người dùng không nên quyết định quy tắc parser.
- Khi pattern nằm trong `.properties`, còn phải kiểm tra cú pháp `.properties` và encoding. Dấu `#` ở **giữa value** không phải comment bắt đầu dòng, nhưng dấu `\\` và ký tự escape vẫn có ý nghĩa theo quy tắc properties.

Một ví dụ không cần ChoiceFormat nhưng nhấn mạnh quoting:

```java
MessageFormat formatter =
        new MessageFormat("You''re invited, {0}!", Locale.US);
System.out.println(formatter.format(new Object[] {"Mai"}));
```

Kết quả:

```text
You're invited, Mai!
```

Nếu viết `You're invited, {0}!` với một dấu nháy trong pattern, `MessageFormat` có thể coi phần sau dấu nháy là literal và không thay `{0}` đúng như mong muốn.

## 12. Thread safety và hiệu năng

`MessageFormat` và `ChoiceFormat` là các đối tượng formatter có trạng thái và có phương thức chỉnh pattern/định dạng. Không nên coi một instance mutable dùng chung giữa nhiều request là mặc nhiên an toàn cho mọi thao tác đồng thời.

Ví dụ trong API service, lựa chọn đơn giản là tạo formatter từ pattern và locale cho một thao tác render; khi tối ưu hiệu năng, có thể cân nhắc cache **pattern bất biến** hoặc quản lý bản sao formatter một cách có kiểm soát. Nếu các định dạng được tái cấu hình bằng `applyPattern`, `setFormat` hoặc `setFormatByArgumentIndex`, cần tránh chia sẻ trạng thái đang thay đổi giữa các luồng.

Không dùng `Locale.setDefault` để chuyển ngôn ngữ của từng request: đó là trạng thái JVM dùng chung. Hãy truyền locale cụ thể trong `new MessageFormat(pattern, locale)` và dùng locale đã chọn khi lấy ResourceBundle.

## 13. Kiểm thử ChoiceFormat + MessageFormat

Các ca kiểm thử tối thiểu cho mẫu `0#...|1#...|1<...`:

| Đầu vào | Kỳ vọng | Mục tiêu |
| ---: | --- | --- |
| 0 | Câu “không có” | Đúng nhánh đầu |
| 1 | Câu “một” | Đúng nhánh thứ hai |
| 2 | Câu “nhiều” có số 2 | Đúng mốc mở và chèn số |
| 5 | Câu “nhiều” có số 5 | Không cố định thành số 2 |
| -1 | Bị business validation từ chối | Tránh chọn nhầm nhánh đầu |
| 1.5 | Được xử lý theo chính sách rõ ràng | Nhận biết `1<` không chỉ áp dụng số nguyên |

Thử bổ sung:

1. **Đổi locale:** hiển thị tiếng Việt và tiếng Anh từ ResourceBundle với cùng `count`, xác minh mỗi câu hoàn chỉnh, đúng dấu câu.
2. **Tham số lồng nhau:** nhánh `1<` chứa `{0,number,integer}` và hiển thị đúng giá trị, đặc biệt khi có phân tách hàng nghìn theo locale.
3. **Thiếu key:** nếu `files.summary` không có trong bundle/parent, kiểm chứng lỗi `MissingResourceException` hoặc fallback do sản phẩm quyết định.
4. **Ký tự đặc biệt:** apostrophe, `|`, dấu `{`, `}`, dấu xuống dòng, chuỗi Unicode từ file.
5. **Ngữ pháp:** kiểm tra bằng người hiểu ngôn ngữ mục tiêu, không chỉ so sánh những chuỗi máy tạo ra.
6. **Dữ liệu động:** tên người chứa dấu nháy hoặc ký tự HTML; `MessageFormat` không tự HTML-escape, nên tầng web phải escape theo ngữ cảnh đầu ra.
7. **Bất biến đa luồng:** nếu formatter được cache hoặc dùng chung, kiểm tra chiến lược quản lý instance; không cập nhật pattern của một instance đang được dùng ở thread khác.

Với Java test, có thể giữ các pattern nhỏ dễ hiểu và kiểm tra từng mốc. Đừng chỉ kiểm thử `count = 2`, vì trường hợp `0`, `1` và giá trị không hợp lệ mới dễ bộc lộ lỗi ranh giới.

## 14. Những hiểu lầm thường gặp

1. **“ChoiceFormat tự dịch đúng số nhiều của mọi ngôn ngữ.”** Sai; nó chỉ chọn theo khoảng giá trị số. Quy tắc plural phức tạp thường cần CLDR/ICU hoặc logic riêng đã xác minh.
2. **“Cứ nối số + danh từ đã dịch là được.”** Sai; thay đổi có thể ảnh hưởng cả mệnh đề và dấu câu.
3. **“ChoiceFormat chọn trực tiếp nhánh có `{0}` thì số tự được thay.”** Không với `ChoiceFormat.format` đơn thuần. Việc diễn giải placeholder lồng nhau diễn ra khi ChoiceFormat được sử dụng trong `MessageFormat`.
4. **“Nhánh `1<` là số nguyên từ 2.”** Với số thực, `1.1` cũng lớn hơn 1. Chỉ tương đương “từ 2” khi đầu vào đã là số nguyên.
5. **“Các mốc không cần tăng dần.”** ChoiceFormat dựa trên các giới hạn có thứ tự; pattern sai thứ tự có thể bị từ chối hoặc hoạt động không đúng ý định.
6. **“Đầu vào âm sẽ tự lỗi.”** Một giá trị dưới mốc đầu có thể chọn nhánh đầu tiên; business validation cần xử lý.
7. **“Đặt pattern vào ResourceBundle là đủ.”** Cần thêm kiểm tra key, fallback, syntax, dấu nháy, plural và ngữ pháp của từng locale.
8. **“MessageFormat sẽ HTML-escape dữ liệu.”** Không; đó là formatter, không phải cơ chế encode an toàn cho HTML hay SQL.
9. **“Mỗi ngôn ngữ phải dùng cùng một thứ tự từ.”** Không; mỗi bản dịch được phép tổ chức lại mệnh đề và vị trí các placeholder.
10. **“Có thể dùng chung một formatter mutable và chỉnh pattern theo request.”** Không an toàn khi nhiều luồng cùng sử dụng; cần quản lý trạng thái đúng cách.

## 15. Khi nào chọn ChoiceFormat và khi nào chọn giải pháp khác?

`ChoiceFormat` phù hợp khi bạn có **một số điều kiện theo ngưỡng số**: ví dụ 0 kết quả, 1 kết quả, nhiều kết quả; các mức đánh giá dựa trên điểm; hoặc các nhánh thông điệp đơn giản mà ngôn ngữ thực tế hỗ trợ có thể diễn đạt chính xác.

Với pluralization phức tạp theo ngôn ngữ, hãy tra cứu quy tắc của locale cụ thể và cân nhắc công cụ i18n hỗ trợ phân loại số nhiều và biến thể ngữ pháp. Dù dùng ChoiceFormat, ICU4J hay một cơ chế khác, ý tưởng ổn định là:

- **Giữ toàn câu trong tài nguyên dịch.**
- **Cho người dịch ngữ cảnh và quyền đổi vị trí tham số.**
- **Phân biệt giá trị nghiệp vụ và pattern điều khiển định dạng.**
- **Kiểm tra các mốc, giá trị biên và tính tự nhiên của câu.**
- **Chọn locale và fallback ở tầng ứng dụng một cách tường minh.**

## 16. Bài tập áp dụng

1. Chạy `ChoiceMessageDemo` với `count` lần lượt là 0, 1, 2 và 5. Giải thích vì sao `1<` chọn nhánh cuối khi `count=2`.
2. Thay `1<` bằng `2#`, chạy với `count=1.5` kiểu `double`, quan sát sự khác biệt và xác định điều kiện để hai mẫu được coi là tương đương.
3. Lấy `ProgrammaticChoiceDemo` và đổi các giới hạn thành `{0,1,2,10}`, viết thêm nhánh cho từ 10 trở lên. Kiểm chứng thứ tự tăng của các giới hạn.
4. Chuyển pattern thành key `files.summary` trong `messages_en.properties` và `messages_vi.properties`, xác nhận code chỉ gọi một key cho cả hai locale.
5. Dịch thông điệp có tên người nhận và số lượng, để một ngôn ngữ đặt tên ở đầu, ngôn ngữ khác ở cuối; giữ nguyên danh sách argument của Java.
6. Kiểm tra đầu vào âm và `NaN` ở ranh giới nghiệp vụ trước khi format. Giải thích vì sao kết quả “không có” không được dùng để che giấu lỗi dữ liệu.
7. Chọn một ngôn ngữ có plural categories phức tạp trong CLDR. Phân tích vì sao `0#|1#|1<` không đủ và đề xuất cách quản lý mẫu dịch với công cụ hỗ trợ plural rules.

## Tài liệu chính thức

- [Oracle JDK 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html)
- [Oracle JDK 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Oracle JDK 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
