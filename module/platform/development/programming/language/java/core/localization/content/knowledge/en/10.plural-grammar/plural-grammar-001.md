# Vì sao không ghép hậu tố số nhiều theo một quy tắc chung?

## 1. Vấn đề khi địa phương hóa câu chứa số lượng

Một chương trình tiếng Anh có thể bắt đầu bằng ý tưởng đơn giản:

```java
String text = count + " file" + (count == 1 ? "" : "s");
```

Kết quả như `1 file` và `2 files` có vẻ hợp lý trong một số trường hợp. Nhưng đó **không phải** thuật toán số nhiều tổng quát cho ứng dụng đa ngôn ngữ. Ngay trong tiếng Anh, `child → children`, `person → people`, `mouse → mice` là các ngoại lệ hình thái; một câu như `0 files` cũng có thể muốn hiển thị tự nhiên hơn là `No files`. Với tiếng Việt, `1 tệp` và `2 tệp` đều dùng danh từ `tệp`, nên tự thêm `s` là vô nghĩa. Tiếng Nga, tiếng Ả Rập và nhiều ngôn ngữ khác có hơn hai hình thức tùy số lượng.

**Nguyên tắc cốt lõi:** không dựng câu đa ngôn ngữ bằng công thức `danh_từ + hậu_tố(count)`. Hãy chọn **mẫu thông điệp hoàn chỉnh** phù hợp với ngôn ngữ, ngữ pháp và loại số; sử dụng dữ liệu plural được chuẩn hóa (như Unicode CLDR) khi hỗ trợ nhiều locale.

Bài này giải thích **vì sao không ghép hậu tố số nhiều theo một quy tắc chung** và cách thiết kế thay thế trong Java Core Localization.

Sau khi học, bạn cần phân biệt:

- Quy tắc **hình thái danh từ** (một danh từ đổi đuôi thế nào) với quy tắc **plural category theo số** (dựa trên ngôn ngữ và cách biểu diễn con số).
- **Cardinal** (số lượng: 1, 2, 5...) với **ordinal** (thứ tự: 1st, 2nd, 3rd...).
- Các category `zero`, `one`, `two`, `few`, `many`, `other` với ý nghĩa từ vựng như "số ít" và "số nhiều".
- Cách tránh dịch từng mảnh, nối chuỗi sai trật tự từ, sai thỏa thuận ngữ pháp.
- Khả năng của `java.text.MessageFormat`, `ChoiceFormat` và khi nào cần ICU4J hoặc thư viện i18n có hỗ trợ CLDR plural rules.

## 2. Ba tầng khác nhau: số, ngữ pháp và toàn bộ câu

Xét hai câu tiếng Anh:

```text
1 new message
2 new messages
```

Có ít nhất ba vấn đề:

1. **Số được biểu diễn thế nào:** `1`, `2`, hoặc số thập phân; dấu phân cách và chữ số có thể phụ thuộc locale.
2. **Hình thức từ ngữ:** `message` hay `messages`; tính từ, động từ, đại từ và các thành phần khác cũng có thể thay đổi ở ngôn ngữ khác.
3. **Cấu trúc câu:** các phần có thể đổi thứ tự hoặc có cách nói tự nhiên khác, chẳng hạn `No new messages` thay cho `0 new messages`.

Nếu ứng dụng chia bản dịch thành:

```text
prefix + number + noun + guessedPluralSuffix
```

người dịch không thể sắp xếp lại trật tự câu hoặc thay toàn bộ cấu trúc. Hậu tố là một đặc điểm của **một từ cụ thể**, không phải của tất cả danh từ trong một ngôn ngữ và càng không phải của mọi ngôn ngữ.

**Giải pháp đúng:** quản lý một khóa thông điệp có nhiều **dạng hoàn chỉnh**. Mỗi dạng được lựa chọn theo số lượng và ngôn ngữ, rồi định dạng placeholder với giá trị thực. Ví dụ với tiếng Anh: `noFiles="No files"`, `oneFile="{count} file"`, `otherFiles="{count} files"`. Với tiếng Việt, có thể chọn cùng một mẫu `"{count} tệp"` cho mọi lượng nếu đó là cách diễn đạt phù hợp ngữ cảnh.

Việc cho phép dạng riêng cho `0` không có nghĩa mọi ngôn ngữ có category CLDR `zero`. Đây còn có thể chỉ là **quyết định nội dung** cho trường hợp đặc biệt.

## 3. Unicode CLDR Plural Rules là gì?

**Unicode Common Locale Data Repository (CLDR)** cung cấp dữ liệu quy tắc plural theo locale để phần mềm lựa chọn dạng thông điệp phù hợp. CLDR định nghĩa các **tên category dùng chung**:

| Category | Diễn giải thực tiễn | Điều không nên suy ra |
| --- | --- | --- |
| `zero` | Một dạng riêng cho những số theo quy tắc zero của locale | Không đồng nghĩa mọi số bằng 0 đều thuộc `zero` trong mọi ngôn ngữ |
| `one` | Một dạng thường gắn với lượng một | Không khẳng định chỉ số nguyên 1 mới thuộc loại này |
| `two` | Dạng dùng cho lượng hai ở một số ngôn ngữ | Không phải locale nào cũng có |
| `few` | Một nhóm số ít theo quy tắc locale | Không phải điều kiện toàn cục `2 ≤ n ≤ 4` |
| `many` | Một nhóm số khác theo quy tắc locale | Không mặc định là `n > 5` |
| `other` | Nhóm còn lại; luôn cần hỗ trợ | Không nhất thiết là "số nhiều" theo nghĩa tiếng Anh |

Tên category là **nhãn kỹ thuật** của quy tắc so sánh những thông điệp tối thiểu theo số. Chúng không phải tên các biến thể ngữ pháp được hiểu giống hệt ở mọi ngôn ngữ.

**Mỗi ngôn ngữ chỉ dùng tập category phù hợp với nó.** Ví dụ tiếng Việt và tiếng Nhật thường chỉ cần `other` cho cardinal trong quy tắc CLDR; tiếng Anh có `one` và `other`; tiếng Nga và tiếng Ả Rập cần phân biệt nhiều nhóm hơn. Đặc biệt, **số 0 không bắt buộc tương ứng category `zero`**; tiếng Anh thông thường dùng `other` cho `0`.

### Cardinal và ordinal không dùng chung bộ quy tắc

- **Cardinal plural:** câu về số lượng: `1 file`, `2 files`.
- **Ordinal plural:** biểu đạt thứ tự: `1st`, `2nd`, `3rd`, `4th` trong tiếng Anh.

Ví dụ tiếng Anh, thứ tự `11th`, `12th`, `13th` đều dùng `th`, trong khi `21st`, `22nd`, `23rd` lại khác. Cố lấy quy tắc cardinal `n == 1` để xây ordinal sẽ sai. ICU MessageFormat dùng `plural` cho cardinal và `selectordinal` cho ordinal; không được hoán đổi hai kiểu.

## 4. Cùng một số, các ngôn ngữ có thể chọn dạng khác nhau

### Tiếng Anh: hai category cardinal không đủ để suy mọi từ

Ví dụ thông thường:

```text
1 file
2 files
0 files
```

Cardinal English theo CLDR có `one` và `other`, nhưng biến đổi `file/files` chỉ áp dụng cho **danh từ này**. Các danh từ bất quy tắc hoặc không đếm được không tuân theo thao tác nối `s`:

```text
1 child -> 2 children
1 person -> 2 people
1 sheep -> 2 sheep
1 piece of information -> 2 pieces of information
```

Thậm chí số lượng bản dịch có thể liên quan đến động từ: `There is one message` so với `There are two messages`. Nối `s` vào danh từ không chỉnh được `is/are`.

### Tiếng Việt: số lượng thường không làm thay đổi hình thái danh từ

Ví dụ:

```text
1 tệp
2 tệp
5 tệp
```

Không có lý do để ghép hậu tố "s". Tuy nhiên điều đó **không** có nghĩa việc dịch mọi câu tiếng Việt chỉ đơn giản thay từ tiếng Anh bằng từ tiếng Việt. Danh từ loại, cách đếm và diễn đạt tự nhiên tùy ngữ cảnh: `một quyển sách`, `hai cuốn sách`, `ba người`; một UI có thể chọn `Không có tệp nào` khi lượng bằng 0. Quy tắc cardinal `other` không tự giải quyết toàn bộ ngữ pháp và biên tập câu.

### Tiếng Nga: nhóm theo chữ số cuối và hai chữ số cuối

Đối với nhiều danh từ đếm được, tiếng Nga có những dạng thể hiện qua ví dụ:

```text
1 файл
2 файла
5 файлов
21 файл
22 файла
25 файлов
```

Quy tắc không phải `count == 1 ? singular : plural`: `21` dùng dạng giống `1` trong ví dụ này, `22` giống `2`, còn `11` và `12` rơi vào nhóm khác do phần hai chữ số cuối. Với số thập phân, quy tắc còn xét chữ số sau dấu thập phân và dạng hiển thị số.

Đừng lấy ví dụ tiếng Nga trên rồi tự viết điều kiện `count % 10` để áp dụng cho mọi ngôn ngữ. Mỗi locale có biểu thức CLDR riêng; hơn nữa hình thái của danh từ/tính từ/đơn vị đo phải do người dịch cung cấp.

### Tiếng Ả Rập: nhiều nhóm số hơn

Tiếng Ả Rập thường có các category cardinal `zero`, `one`, `two`, `few`, `many` và `other`. Với số nguyên không âm, các trường hợp tiêu biểu là:

| Số | Category minh họa cho tiếng Ả Rập |
| --- | --- |
| `0` | `zero` |
| `1` | `one` |
| `2` | `two` |
| `3`, `10` | `few` |
| `11`, `99` | `many` |
| `100` | `other` |

Bảng cho thấy **không thể có một hàm thêm đuôi chung** cho các nhóm số này. Đây là minh họa các category theo CLDR, không phải từ điển cách biến cách danh từ hay hướng dẫn viết câu tiếng Ả Rập đầy đủ.

### So sánh nhanh

| Ngôn ngữ | Phân biệt cardinal nổi bật | Kết luận triển khai |
| --- | --- | --- |
| Tiếng Việt | Thường chỉ `other` | Không tạo hậu tố dựa trên số |
| Tiếng Anh | `one`, `other` | Vẫn cần bản dịch từng câu/từng danh từ, tránh tự nối `s` |
| Tiếng Nga | `one`, `few`, `many`, `other` trong dữ liệu CLDR hiện hành | Không thể kiểm tra `n == 1` |
| Tiếng Ả Rập | Có thể có cả sáu category | Phải chọn dạng từ rule theo locale và dùng thông điệp hoàn chỉnh |

Độ chính xác của các biểu thức rule và tập category phải lấy từ **phiên bản CLDR triển khai trong sản phẩm**, không hardcode bằng cách nhìn một vài số mẫu rồi suy ra mọi trường hợp.

## 5. Các trường hợp biên: 0, số thập phân và số hiển thị

### 5.1. `0` không có nghĩa luôn dùng `zero`

Ví dụ tiếng Anh `0 files` thuộc category cardinal `other`, nhưng về mặt nội dung UX có thể muốn `No files`. Một mẫu plural có thể hỗ trợ nhánh riêng `=0` để viết câu tự nhiên mà không giả định category của `0` là `zero` trong CLDR.

Phân biệt:

- **Exact-value branch:** chọn khi số *đúng bằng* một giá trị, ví dụ `=0`.
- **Locale plural category:** chọn dựa trên các phép tính và quy tắc CLDR, ví dụ `one`, `few`, `other`.

Hai lớp điều kiện có thể cùng tồn tại và phục vụ mục đích khác nhau. Đừng đồng nhất `=0` với category `zero`.

### 5.2. `1` và `1.0` có thể khác category

CLDR xét không chỉ giá trị số học, mà trong nhiều trường hợp còn xét **số chữ số thập phân hiển thị**, đặc biệt các số 0 theo sau. Các toán hạng của plural rules như `n`, `i`, `v`, `w`, `f`, `t` mô tả đặc trưng của con số ở dạng hiển thị.

Vì vậy có thể tồn tại khác biệt giữa:

```text
1
1.0
1.00
1.5
```

Mặc dù `1 == 1.0` theo phép so sánh giá trị số học, **không thể mặc định chúng có cùng plural category ở mọi locale**. Một API chỉ nhận `double` mà làm mất thông tin số chữ số phần thập phân cũng có thể khiến phép chọn dạng không khớp với cách hiển thị dự kiến. Chọn thư viện có hỗ trợ đúng ngữ nghĩa CLDR và kiểm thử số sau khi làm tròn/định dạng.

### 5.3. Số âm, số lớn và phép làm tròn

Số đếm thực tế có thể xuất hiện ở trạng thái signed, thập phân, hoặc được compact-format:

```text
-1
1.2
1000
1K
```

Cần thống nhất ứng dụng đang truyền **số gốc** hay **số đã được hiển thị/làm tròn** cho selector. Đừng suy từ chuỗi `"1K"` rằng cần áp dụng quy tắc của số `1`. Các cơ chế plural-range cho đoạn số như `1–2` cũng là chủ đề khác với cardinal số đơn lẻ.

## 6. Vì sao nối hậu tố làm sai cả câu, không riêng danh từ?

Một câu bản địa hóa là **đơn vị ngữ nghĩa**. Thử các trường hợp:

- **Thỏa thuận chủ-vị:** `One item is ready` và `Two items are ready` khác cả `item/items` lẫn `is/are`.
- **Giới từ/cách/giống của danh từ:** một số ngôn ngữ thay hình thái của tính từ, danh từ hoặc đại từ theo số, giống, cách.
- **Danh từ không đếm được:** `information`, `advice` không thể tự đổi bằng hậu tố `s` giống `file`.
- **Trật tự từ:** bản dịch tự nhiên có thể đảo cụm lượng, đơn vị và động từ.
- **Nội dung cho số 0:** `No results found` có thể tốt hơn `0 results found`, nhưng không thể suy đoán trực tiếp từ số hoặc tên category.
- **Thông điệp có placeholder khác:** số lượng, giới tính ngữ pháp, đối tượng, danh từ đi cùng nhau; đôi khi cần cơ chế `select` và `plural` lồng nhau.

Các chuỗi theo kiểu `translate("There are ") + count + translate(" items")` hạn chế quyền của người dịch và có thể sai ngữ pháp. Nên đưa **cả câu có placeholder** vào hệ thống bản dịch, thay vì dịch và ghép nhiều mảnh cố định.

## 7. Java 17+: ví dụ cách làm sai và cách làm đúng trong phạm vi nhỏ

Tạo `PluralMessagesDemo.java`. Ví dụ không cố gắng tái triển khai đầy đủ CLDR; nó **chỉ hỗ trợ hai ngôn ngữ trong phạm vi đã nêu** và dùng các câu hoàn chỉnh cho từng trường hợp.

```java
import java.util.Locale;

public class PluralMessagesDemo {
    // Cách naive chỉ đúng tình cờ với một tập từ tiếng Anh.
    static String naiveFiles(int count) {
        return count + " file" + (count == 1 ? "" : "s");
    }

    // Mẫu thông điệp có chủ đích cho phạm vi ví dụ.
    static String describeFiles(int count, Locale locale) {
        if (count < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }

        return switch (locale.getLanguage()) {
            case "en" -> switch (count) {
                case 0 -> "No files";
                case 1 -> "1 file";
                default -> count + " files";
            };
            case "vi" -> count + " tệp";
            default -> throw new IllegalArgumentException(
                    "Unsupported language: " + locale.toLanguageTag());
        };
    }

    public static void main(String[] args) {
        Locale english = Locale.forLanguageTag("en-US");
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        System.out.println("Naive: " + naiveFiles(0));
        System.out.println("EN 0: " + describeFiles(0, english));
        System.out.println("EN 1: " + describeFiles(1, english));
        System.out.println("EN 2: " + describeFiles(2, english));
        System.out.println("VI 0: " + describeFiles(0, vietnamese));
        System.out.println("VI 1: " + describeFiles(1, vietnamese));
        System.out.println("VI 2: " + describeFiles(2, vietnamese));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PluralMessagesDemo.java
java PluralMessagesDemo
```

Kết quả:

```text
Naive: 0 files
EN 0: No files
EN 1: 1 file
EN 2: 2 files
VI 0: 0 tệp
VI 1: 1 tệp
VI 2: 2 tệp
```

Bài học từ ví dụ:

1. `naiveFiles` là công thức ghép hậu tố cố định. Nó không biết `No files` là lựa chọn câu tự nhiên cho `0`, và hoàn toàn không phù hợp với tiếng Việt hay đa dạng danh từ tiếng Anh.
2. `describeFiles` chọn **thông điệp theo language**, không thay `Locale.setDefault()` toàn cục; người dùng khác nhau có thể yêu cầu locale khác nhau trên cùng server.
3. Code chủ động từ chối ngôn ngữ chưa hỗ trợ, tránh mặc định tùy tiện một bản dịch không đúng.
4. Đây là **minh họa cách đặt chính sách** trong phạm vi tiếng Anh/tiếng Việt, **không** phải một plural engine cho mọi locale. Khi ứng dụng nhiều ngôn ngữ, sử dụng dữ liệu quy tắc được bảo trì (CLDR/ICU) cùng nguồn bản dịch thay vì viết một switch lớn hoặc tự chế các công thức cho tiếng Nga/Ả Rập.

Bản dịch nên nằm trong file/resource catalog riêng để người dịch bảo trì; logic ứng dụng truyền `count` và `Locale` vào hệ thống format message.

## 8. `MessageFormat` và `ChoiceFormat` trong JDK: có ích nhưng giới hạn

Java SE có hai lớp:

- `java.text.MessageFormat`: thay tham số và định dạng số/ngày theo locale; trong JDK truyền thống, pattern có thể gọi `choice`.
- `java.text.ChoiceFormat`: chọn chuỗi theo các ngưỡng số; có thể giúp mô tả một số câu đơn giản.

### Ví dụ Java 17+ với `choice`

File `EnglishChoiceDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class EnglishChoiceDemo {
    public static void main(String[] args) {
        MessageFormat formatter = new MessageFormat(
                "{0,choice,0#no files|1#one file|1<{0,number,integer} files}",
                Locale.forLanguageTag("en-US"));

        for (int count : new int[] {0, 1, 2, 21}) {
            System.out.println(count + " => "
                    + formatter.format(new Object[] {count}));
        }
    }
}
```

```bash
javac EnglishChoiceDemo.java
java EnglishChoiceDemo
```

Stdout:

```text
0 => no files
1 => one file
2 => 2 files
21 => 21 files
```

Trong pattern trên:

- `0#no files`: nhánh tính từ ngưỡng 0.
- `1#one file`: nhánh tính từ ngưỡng 1.
- `1<{0,number,integer} files`: nhánh lớn hơn 1, có định dạng số bên trong.

Đây là lựa chọn **theo ngưỡng cho một câu tiếng Anh cụ thể**, không phải quy tắc CLDR; nếu áp dụng cho `ru` hoặc `ar` mà không thay logic và bản dịch sẽ sai. Với số âm, các số không nguyên, giá trị ngoài domain đang giả định, pattern minh họa này cần thiết kế lại. Đừng coi `ChoiceFormat` là công cụ đa ngôn ngữ tự nhận biết category.

### Điều JDK `MessageFormat` không tự cung cấp

Trong Java 17/21, `java.text.MessageFormat` truyền thống **không có cú pháp ICU `plural` hoặc `selectordinal`**, cũng không tự động ánh xạ mọi con số sang category CLDR tương ứng. Việc tạo instance với locale `ru-RU` không khiến `ChoiceFormat` hiểu quy tắc tiếng Nga. Nếu phải hỗ trợ nhiều ngôn ngữ có hệ số nhiều phức tạp, nên chọn thư viện có khả năng áp dụng CLDR.

*Lưu ý về phiên bản:* các API định dạng thông điệp có thể phát triển ở các phiên bản Java tương lai; nhận định trên nói cụ thể về `java.text.MessageFormat`/`ChoiceFormat` phổ biến ở Java 17+ với phạm vi JDK 17/21.

## 9. ICU4J: chọn plural category theo locale và giữ cả câu trong template

**ICU4J** là thư viện Java độc lập (không nằm sẵn trong JDK) cung cấp xử lý plural theo dữ liệu ICU/CLDR. API `com.ibm.icu.text.MessageFormat` hỗ trợ pattern `plural` và `selectordinal`.

Ví dụ **pattern ICU minh họa** (không phải pattern của `java.text.MessageFormat`):

```text
{count, plural,
    =0 {No files}
    one {# file}
    other {# files}
}
```

Với locale tiếng Anh và `count` là 0, 1, 2, pattern này tạo câu tương ứng `No files`, `1 file`, `2 files` (với cách định dạng số của locale). Ở đây:

- `=0` là nhánh chọn **giá trị chính xác** nhằm tạo câu "No files"; không phải category `zero`.
- `one` và `other` là các nhãn category plural cardinal theo locale.
- `#` trong một nhánh plural đại diện số được định dạng theo logic ICU và locale; không cần nối thêm dấu `s` ngoài template.

Ví dụ mẫu Java **phụ thuộc ICU4J**, không phải chương trình chạy độc lập chỉ với JDK:

```java
// Cần thêm dependency ICU4J phù hợp vào dự án.
com.ibm.icu.text.MessageFormat formatter =
        new com.ibm.icu.text.MessageFormat(
                "{count, plural, =0{No files} one{# file} other{# files}}",
                java.util.Locale.forLanguageTag("en-US"));

java.util.Map<String, Object> arguments =
        java.util.Map.of("count", 2);
String result = formatter.format(arguments); // "2 files"
```

Trong ứng dụng thật, **đặt các pattern ở resource catalog của mỗi ngôn ngữ**; đừng viết cố định template tiếng Anh rồi chỉ đổi `Locale` thành `vi-VN` hoặc `ru-RU` và cho rằng nội dung đã được dịch. Locale quyết định cách chọn category và định dạng số, **không tự dịch từ ngữ**. Sự có mặt của thư viện cũng không thay thế đánh giá bản dịch của người bản ngữ.

Với thứ tự tiếng Anh, ICU hỗ trợ dạng `selectordinal` khác `plural`, ví dụ pattern ý tưởng:

```text
{rank, selectordinal,
    one {#st}
    two {#nd}
    few {#rd}
    other {#th}
}
```

Pattern này minh họa suffix cho **thứ tự tiếng Anh**, không phải phương pháp tạo dạng số nhiều của danh từ. Nó không thể áp dụng chung cho mọi ngôn ngữ, và với cụm câu ordinal phức tạp vẫn cần bản dịch hoàn chỉnh.

## 10. Thiết kế resource catalog và API an toàn

Thay vì key tách mảnh kiểu `file.name` + `file.suffix`, dùng một key **theo ý nghĩa câu** có đủ các nhánh plural. Mô hình khái niệm:

```text
key: inbox.unreadCount

locale en:
  =0: No unread messages
  one: You have # unread message
  other: You have # unread messages

locale vi:
  other: Bạn có # tin nhắn chưa đọc

locale ru:
  one: <câu tiếng Nga dạng one>
  few: <câu tiếng Nga dạng few>
  many: <câu tiếng Nga dạng many>
  other: <câu tiếng Nga dạng other, nếu dữ liệu yêu cầu>
```

Đây là **sơ đồ dữ liệu minh họa**, không phải cú pháp bắt buộc của Java `.properties` và không phải bản dịch tiếng Nga đã hoàn thành. Phần nội dung tiếng Nga cần được người dịch cung cấp, gồm mọi thành phần câu thay đổi theo số.

Luồng xử lý đề xuất:

1. **Resolve locale theo người dùng/request** từ nguồn preference hợp lệ; áp dụng supported-locale whitelist và chính sách fallback.
2. **Xác định domain của count**: số nguyên không âm, thập phân, giá trị âm, số sau làm tròn hay số hiển thị. Không ngầm ép `1.0` thành `1` nếu quy tắc yêu cầu phân biệt.
3. **Chọn message key theo ý nghĩa**, ví dụ `inbox.unreadCount`, không ghép các mảnh tự dịch.
4. **Dùng plural selector của thư viện** theo locale và count. Ưu tiên exact-value branch khi nội dung UX đòi hỏi (ví dụ `=0`); với các giá trị khác, áp dụng category.
5. **Format placeholder và toàn bộ câu** theo locale, escape/quote đúng cú pháp engine đang dùng.
6. **Kiểm tra đủ các nhánh cần thiết**, đặc biệt `other`, và không để rơi sang câu tiếng Anh nếu quy tắc fallback nội dung không cho phép.
7. **Kiểm thử các nhóm số thực** và cho người bản ngữ duyệt ngữ pháp, trật tự từ, danh từ loại, giống/cách và câu mang nghĩa đặc biệt.

Đối với Java Core thuần JDK mà chưa có nhu cầu đa ngôn ngữ phức tạp, có thể dùng switch theo **ngôn ngữ đã hỗ trợ và ngữ cảnh hẹp** như ví dụ `PluralMessagesDemo`. Nhưng khi quy mô bản dịch tăng, logic code phải được tách khỏi bản dịch và dùng nguồn plural rules đáng tin cậy.

## 11. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Nối `s` khi `count != 1` cho mọi locale | Ngữ pháp không đồng nhất giữa các ngôn ngữ | Dùng bản dịch và plural rules theo locale |
| Dùng `n == 1` để xử lý mọi ngôn ngữ | Có `few`, `many`, `two` và ngoại lệ teens | Chọn category từ CLDR |
| Cho `0` luôn thuộc `zero` | Không phải ngôn ngữ nào có category `zero` | Phân biệt `=0` với category `zero` |
| Chỉ dịch danh từ, giữ nguyên động từ/tính từ | Cả câu có thể đổi cấu trúc | Dịch mẫu câu hoàn chỉnh |
| Dùng `ChoiceFormat` như CLDR engine | Chỉ chọn theo ngưỡng do lập trình viên đặt | ICU4J/thư viện tương đương hoặc logic giới hạn rõ ràng |
| Coi `plural` và `selectordinal` là một | Cardinal và ordinal khác quy tắc | Chọn đúng cơ chế |
| Xem `1` và `1.0` luôn là cùng một dạng | Dấu 0 thập phân hiển thị có thể ảnh hưởng category | Giữ thông tin precision theo API |
| Tự tính `n % 10` cho mọi ngôn ngữ | Rule phụ thuộc locale, nhóm teens và thập phân | Sử dụng dữ liệu CLDR có phiên bản rõ |
| Chỉ kiểm thử `1` và `2` | Bỏ qua `0`, `3`, `5`, `11`, `21`, số lẻ | Lập ma trận test phù hợp từng locale |
| Chỉ đổi `Locale` của formatter nhưng giữ template tiếng Anh | Locale không dịch ngôn ngữ của câu | Resource catalog riêng theo ngôn ngữ |
| Dùng `Locale.setDefault()` theo request | Thay trạng thái JVM dùng chung, dễ xung đột | Truyền `Locale` tường minh |
| Bỏ qua vấn đề danh từ loại/giống/cách | Category đúng vẫn có thể sinh câu sai | Review bản dịch nguyên câu với người bản ngữ |

## 12. Bài tập và câu hỏi tự kiểm tra

1. Vì sao `count == 1 ? "file" : "files"` không phải giải pháp đa ngôn ngữ? **Vì nó chỉ mô tả một danh từ tiếng Anh, không xử lý hình thái, câu và category của các ngôn ngữ khác.**
2. Tiếng Việt `1 tệp` và `2 tệp` có cần thay hậu tố danh từ không? **Không theo dạng ví dụ; thay vì gắn suffix, dùng mẫu câu tiếng Việt phù hợp.**
3. Tại sao tiếng Nga `21 файл` khác logic `n == 1`? **Nhóm plural được xác định bởi quy tắc số của ngôn ngữ, gồm chữ số cuối và trường hợp ngoại lệ.**
4. `0` có phải luôn thuộc category `zero` trong CLDR không? **Không.** Exact branch `=0` có thể dùng cho nội dung đặc biệt.
5. `1` với `1.0` có thể khác nhau khi chọn dạng không? **Có ở một số ngôn ngữ**, vì các toán hạng CLDR có thể xét số chữ số thập phân hiển thị.
6. Java 17 `java.text.MessageFormat` có tự hiểu pattern ICU `{count, plural, ...}` không? **Không.** Đó là cú pháp của ICU MessageFormat, cần dependency tương ứng.
7. Có thể chỉ dịch suffix thay vì cả câu không? **Không nên**, vì trật tự từ, động từ, tính từ và ngữ pháp có thể thay đổi.
8. Nếu muốn cách nói `No files` khi count=0 nhưng CLDR English dùng category `other` cho 0, xử lý thế nào? **Dùng nhánh exact value `=0` trong mẫu hỗ trợ hoặc chính sách rõ ràng; không sửa định nghĩa category `other`.**
9. Với một công cụ i18n mới, các số nào nên xuất hiện trong test? **Ít nhất 0, 1, 2, 3, 5, 11, 21; cùng các số thập phân, dạng 1.0/1.00 nếu được hỗ trợ và có ý nghĩa theo locale.**
10. Khi nào nên để người bản ngữ đánh giá? **Sau khi quy tắc chọn category đúng, kiểm tra cả câu hoàn chỉnh, vì category không tự giải quyết mọi hiện tượng ngữ pháp.**

## Tài liệu tham khảo

- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules): khái niệm category, minimal pairs và khác biệt số nguyên/thập phân.
- [Unicode CLDR — Language Plural Rules](https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html): bảng dạng số nhiều theo ngôn ngữ cho phiên bản CLDR tương ứng.
- [Unicode TR35 — Numbers and Plural Rules](https://unicode.org/reports/tr35/tr35-numbers.html): các toán hạng và quy tắc plural.
- [ICU4J — MessageFormat](https://unicode-org.github.io/icu-docs/apidoc/released/icu4j/com/ibm/icu/text/MessageFormat.html): pattern `plural`/`selectordinal` và khác biệt với JDK `MessageFormat`.
- [Java SE 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html): mẫu định dạng thông điệp chuẩn JDK.
- [Java SE 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html): chọn chuỗi theo ngưỡng số, không thay thế đầy đủ CLDR plural rules.
