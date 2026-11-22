# RuleBasedCollator và quy tắc sắp xếp tùy chỉnh trong Java

## 1. Vì sao so sánh ngôn ngữ không thể chỉ dùng String.compareTo?

Khi xây dựng ứng dụng Java có dữ liệu đa ngôn ngữ, người dùng thường mong danh sách tên, mục từ hoặc tiêu đề được sắp xếp theo **quy ước ngôn ngữ** chứ không đơn thuần theo giá trị UTF-16 của từng ký tự.

Ví dụ, thứ tự chữ hoa/chữ thường, dấu thanh, ký tự ghép, hai chữ cái được xem như một đơn vị xếp thứ tự hoặc ký hiệu đặc biệt có thể khác nhau giữa các ngôn ngữ. `String.compareTo` so sánh theo thứ tự từ điển của **đơn vị mã UTF-16**, không hiểu ý nghĩa ngôn ngữ học của các chuỗi.

Java cung cấp `java.text.Collator` để thực hiện **collation**: so sánh hai chuỗi theo quy tắc văn hóa/ngôn ngữ. Với quy tắc sắp xếp đặc thù, `java.text.RuleBasedCollator` là một lớp con cụ thể của `Collator`, cho phép tạo bảng collation bằng một **chuỗi quy tắc**.

Chẳng hạn, một danh mục lịch sử có thể yêu cầu chữ ghép `ch` được xử lý như một đơn vị sắp xếp đứng **sau c nhưng trước d**. Hoặc hệ thống cần xếp một ký hiệu/viết tắt theo thứ tự nội bộ đã được chủ sản phẩm xác nhận. `RuleBasedCollator` hỗ trợ biểu diễn những quan hệ đó.

**Mục tiêu của bài:** hiểu cấu trúc chuỗi rule, dấu quan hệ `<`, `;`, `,`, `=`, phép reset `&`, mức độ khác biệt `strength`, contraction/expansion, chuẩn hóa Unicode, cách kiểm tra lỗi và thiết kế comparator an toàn.

## 2. Chọn Collator thông thường hay RuleBasedCollator?

Trong phần lớn trường hợp, hãy **bắt đầu với Collator được cung cấp cho locale**:

~~~java
Collator vietnamese = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
~~~

Đây là câu lệnh minh họa trong một phương thức Java, cần import `java.text.Collator` và `java.util.Locale`.

`Collator.getInstance(locale)` chọn bộ so sánh do runtime và locale provider hỗ trợ. Bạn không cần tự định nghĩa bảng chữ cái, dấu hoặc hàng trăm quan hệ Unicode. Nếu chỉ cần sắp xếp danh sách theo ngôn ngữ người dùng, đây thường là điểm khởi đầu phù hợp.

Dùng `RuleBasedCollator` khi bạn **có yêu cầu sắp xếp khác quy tắc locale mặc định**, ví dụ:

- Một danh mục tra cứu có thứ tự chữ cái đặc thù theo tài liệu nghiệp vụ.
- Một hệ thống từ điển cũ xem `ch` như một contraction.
- Cần kiểm thử một tập quan hệ primary/secondary/tertiary xác định.
- Muốn thay đổi một phần thứ tự của một `RuleBasedCollator` có sẵn, với sự kiểm soát đối với toàn bộ rule kết quả.

Đừng tự thay thế bộ collation đầy đủ của một ngôn ngữ bằng một danh sách ngắn `a < b < c` trong môi trường production: lớp này đặt **những ký tự không được đề cập ở cuối thứ tự collation**, dễ khiến từ Unicode ngoài bảng bị xếp sai. Tài liệu JDK cũng ghi nhận thiết kế bảng rule-based có giới hạn; các bài toán collation phức tạp hơn có thể cần cơ chế/chuyên thư viện phù hợp.

## 3. Cú pháp nền tảng của RuleBasedCollator

Constructor:

~~~java
RuleBasedCollator custom = new RuleBasedCollator(
        "< a < b < c < d");
~~~

Đây là đoạn minh họa trong một phương thức Java. Constructor nhận **rule string**, biên dịch thành bảng collation và có thể ném `java.text.ParseException` nếu cú pháp hoặc vị trí reset không hợp lệ.

Một chuỗi rule có thể gồm:

1. **Quan hệ** đặt một text argument so với mục đã nêu trước đó.
2. **Reset** `&` để quay lại một vị trí có sẵn rồi thêm hoặc thay đổi quan hệ.
3. **Modifier** tác động tới cách sắp xếp trong toàn bảng theo mô tả của JDK.

### 3.1. Dấu quan hệ và cấp độ khác biệt

| Ký hiệu | Quan hệ trong rules | Ý nghĩa thường dùng |
| --- | --- | --- |
| `<` | Primary difference | Khác biệt cơ bản như thứ tự chữ cái |
| `;` | Secondary difference | Khác biệt mức dấu/biến thể phụ |
| `,` | Tertiary difference | Khác biệt mức chữ hoa–thường/biến thể nhỏ |
| `=` | Equal | Hai mục tương đương theo bảng rule |
| `&` | Reset | Quay về vị trí mục đã có để chèn quan hệ tiếp theo |

Ví dụ:

~~~text
< a , A ; á < b < c < ch < d
~~~

Ý nghĩa theo rule này:

- `a` và `A` có cùng trọng số primary và secondary; tại **tertiary** thì phân biệt.
- `á` khác `a` ở cấp **secondary**, nên `PRIMARY` có thể xem chúng bằng nhau trong quan hệ của bảng này.
- `b`, `c`, `ch`, `d` khác nhau ở cấp primary.
- Chuỗi `ch` được mô tả thành một **đơn vị so sánh** (contraction) trong bảng này; nó vẫn gồm hai code point `c` và `h` trong `String`.

Các quan hệ này **không phải luật cho toàn bộ tiếng Việt, tiếng Tây Ban Nha hoặc mọi ngôn ngữ**. Chúng chỉ thể hiện quy tắc ví dụ đã được chủ động khai báo.

### 3.2. Dấu cách, dấu câu và quoting

Rule string có cú pháp riêng. Nhiều khoảng trắng ngoài phần argument bị bỏ qua; với text argument, một số ký tự dấu câu thuộc **ký tự đặc biệt của cú pháp**. Nếu muốn sắp xếp một chuỗi thật sự chứa dấu câu đặc biệt, bạn cần **đặt text argument trong dấu nháy đơn** theo cú pháp RuleBasedCollator.

Ví dụ:

~~~java
String rules = "< a < b < 'x-y' < c";
RuleBasedCollator c = new RuleBasedCollator(rules);
~~~

Đây là đoạn minh họa (không phải file Java độc lập). Dấu gạch ngang trong `x-y` được quote để không bị parser hiểu sai. Tương tự, `'&'` có thể diễn đạt ký tự `&` như dữ liệu thay vì phép reset.

Cần đặc biệt nhớ:

- Viết `< a < b` thay vì giả định `a < b` là một chuỗi rule đầy đủ; `<` đầu tiên khởi tạo quan hệ của mục đầu.
- Unquoted whitespace có thể bị parser bỏ qua; nếu cần **khoảng trắng thực** như một mục trong rule, dùng quote theo quy định.
- `< a < b-c < d` có dấu `-` chưa quote và có thể gây `ParseException`.
- Không tự dùng cú pháp `[before 1]`, `[reorder ...]` hoặc cú pháp riêng của ICU cho `java.text.RuleBasedCollator`: hai bộ rule language **không đồng nhất**.

## 4. Reset với &: thêm thứ tự tương đối

`&` không có nghĩa nối chuỗi hoặc toán tử bitwise trong rule; nó đặt lại điểm chèn trong bảng collation.

Ví dụ:

~~~text
< a < b < c < d & b < bb
~~~

Trước phần reset: `a`, `b`, `c`, `d` đã được xác lập thứ tự. Phần `& b < bb` thêm `bb` vào vị trí **ngay sau b** ở cấp primary; vì vậy `bb` nằm **trước c**.

Một ví dụ khác:

~~~text
< a < c & a < b
~~~

Nghĩa là `b` được chèn sau `a` và trước `c`. Đặt các reset khác nhau có thể làm thay đổi thứ tự cuối: quy tắc có tính **thứ tự**, không phải tập hợp các ký hiệu có thể hoán đổi.

**Điều kiện reset:** text argument của `&` hoặc tiền tố thích hợp của nó phải đã có trong chuỗi rule trước đó. Nếu chưa tồn tại vị trí cần reset, constructor báo `ParseException`. Ví dụ không hợp lệ:

~~~java
new RuleBasedCollator("< a < b & z < zz");
~~~

`z` chưa xuất hiện trong bảng đã khai báo, nên việc yêu cầu chèn `zz` sau `z` không có điểm đặt xác định. Chương trình ở mục 8 kiểm tra đúng lỗi này.

### 4.1. Contraction và expansion là hai ý khác nhau

- **Contraction:** một chuỗi **nhiều ký tự** được xét như một đơn vị trọng số trong collation. Ví dụ `< c < ch < d` dùng `ch` như một mục riêng đứng giữa `c` và `d`.
- **Expansion:** một mục có thể được xem như chuỗi trọng số của nhiều mục đã tồn tại; dạng reset đặc biệt có thể mô tả điều đó. Tài liệu Oracle đưa ví dụ `< a < b & ae < e`, trong đó `ae` là cách chỉ vị trí dựa trên `a`, làm phần mở rộng có ý nghĩa so sánh.

Những quy tắc này là **quy ước sắp xếp**, không có nghĩa `String.length()` thay đổi, `ch` trở thành một Unicode code point, hoặc chuỗi được chỉnh sửa khi so sánh.

## 5. Strength: khi nào xem hai chuỗi giống hay khác?

`RuleBasedCollator` kế thừa các mức strength từ `Collator`:

| Strength | Đặc điểm |
| --- | --- |
| `Collator.PRIMARY` | Chỉ xét khác biệt chính; bỏ qua khác biệt secondary/tertiary |
| `Collator.SECONDARY` | Xét primary và secondary; có thể phân biệt dấu |
| `Collator.TERTIARY` | Xét cả primary, secondary và tertiary; có thể phân biệt case |
| `Collator.IDENTICAL` | Mức so sánh nghiêm ngặt hơn sau ba cấp trên; không đồng nghĩa mọi chuỗi Unicode thô khác nhau đều phải xếp khác, vì normalization cũng có thể liên quan |

`Collator` mặc định có mức strength theo cấu hình instance và locale provider. Với quy tắc tùy chỉnh, nên **đặt tường minh** khi nghiệp vụ có tiêu chí kiểm tra cụ thể:

~~~java
custom.setStrength(Collator.PRIMARY);
int result = custom.compare("a", "\u00E1");
~~~

Đây là đoạn minh họa, cần `custom` là collator đã tạo. Trong bảng rule `< a , A ; á < b`, so sánh ở PRIMARY trả **0** vì khác biệt giữa `a` và `á` chỉ là secondary.

Khi đổi sang `SECONDARY`, so sánh `a` với `á` cho giá trị **âm** (a đứng trước á). Khi đổi sang `TERTIARY`, `a` và `A` cũng khác thứ tự như đã được khai báo.

**Lưu ý:** `Collator.compare` trả giá trị âm/0/dương; **không đảm bảo luôn trả đúng -1 hoặc +1**. Nếu cần in định tính, dùng `Integer.signum(compare(...))` như ví dụ ở mục 8.

### 5.1. Equal trong collation không phải equals của String

Một rule có `=`:

~~~text
< a = á < b
~~~

cho phép collator trong ví dụ xem `a` và `á` có cùng trọng số collation. Nhưng:

~~~java
"a".equals("\u00E1")  // false
~~~

So sánh `String.equals` vẫn dựa trên nội dung Java `String` và không bị rule thay đổi.

Điều này ảnh hưởng trực tiếp đến collection:

- `TreeSet<String>` khi nhận comparator `Collator` có thể coi hai chuỗi `compare(a, b) == 0` là cùng một phần tử theo quan hệ thứ tự.
- `HashSet<String>` dựa vào `String.equals` và `hashCode`, vì vậy có thể giữ **cả hai**.
- Dùng collation để **sắp xếp** không mặc nhiên thích hợp để xác định khóa định danh duy nhất của người dùng.

Nếu cần lưu danh sách có thứ tự mà vẫn giữ nguyên mọi giá trị, có thể dùng `List.sort(collator)` và một tie-breaker riêng theo hợp đồng. Nhưng cần quyết định rõ yêu cầu: tie-breaker `String.compareTo` sẽ phá việc coi hai chuỗi tương đương khi dùng làm tiêu chí trùng khóa.

## 6. Tạo rule độc lập hay tùy biến từ một locale?

### 6.1. Rule độc lập: hữu ích để học và cho alphabet khép kín

~~~java
RuleBasedCollator simple =
        new RuleBasedCollator("< a < b < c < ch < d");
~~~

Đoạn trên là ví dụ độc lập cho tập mục được liệt kê. **Các ký tự không nhắc tới có thể được xếp ở cuối**, nên rule rất ngắn này không phù hợp để sắp toàn bộ tiếng Việt, chữ có dấu, emoji, ký tự Hy Lạp, Nhật hoặc dữ liệu nhập tự do.

### 6.2. Lấy rule của locale rồi mở rộng có kiểm soát

Nếu runtime trả về `RuleBasedCollator`, bạn có thể đọc `getRules()` và xây một đối tượng mới từ chuỗi rule ấy cộng phần điều chỉnh:

~~~java
Collator base = Collator.getInstance(Locale.US);
if (base instanceof RuleBasedCollator rb) {
    String tailored = rb.getRules() + " & c < ch";
    RuleBasedCollator custom = new RuleBasedCollator(tailored);
    custom.setStrength(Collator.TERTIARY);
    // Dùng custom để thử quy tắc trên tập dữ liệu thực tế.
}
~~~

Đây là **snippet minh họa** cần các import `java.text.*` và `java.util.Locale`, đặt trong phương thức xử lý `ParseException`. Phải xác minh tại runtime rằng base là `RuleBasedCollator`; `Collator.getInstance(locale)` không hứa mọi provider đều trả chính lớp này.

**Không nối rule mới một cách mù quáng**:

1. `rb.getRules()` có thể rất dài và chứa nhiều quan hệ, contraction/expansion, modifier.
2. Phần nối `& c < ch` chỉ có ý nghĩa nếu điểm reset có thể nhận diện và không phá quy tắc đã có.
3. Kiểm tra xem `ch` đã được định nghĩa như contraction hay có thứ tự đặc biệt chưa.
4. Biên dịch rule mới có thể ném `ParseException`; mọi thay đổi đều cần regression test với từ có dấu, chữ hoa, dữ liệu trộn script.
5. Phiên bản JDK/CLDR/locale provider có thể thay đổi quy tắc nền, nên chuỗi rule nối thành một bảng mới có thể sinh khác biệt giữa môi trường.

Với sản phẩm đa ngôn ngữ quy mô lớn, ưu tiên khả năng **collation tailoring** được thư viện và dữ liệu locale hỗ trợ, thay vì tái tạo toàn bộ ngôn ngữ chỉ bằng các rule thủ công.

## 7. Unicode decomposition, dấu và các modifier đặc biệt

### 7.1. Decomposition khi so sánh chuỗi có dấu

Một chữ có dấu có thể được lưu ở dạng **precomposed** (ví dụ `á`, U+00E1) hoặc **decomposed** (`a` + U+0301). Người dùng thường nhìn thấy cùng một chữ, nhưng chuỗi UTF-16 khác nhau.

`RuleBasedCollator` tự xử lý một số tương đương chuẩn tắc khi tạo bảng rule, nhưng không phải mọi dữ liệu có dấu tổ hợp đều tự động cho kết quả mong muốn khi người dùng nhập các chuỗi dấu theo thứ tự lạ. Có thể cấu hình:

~~~java
custom.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
~~~

Điều đó yêu cầu xử lý decomposition chuẩn tắc trong so sánh. Với các dạng **compatibility decomposition**, như full-width/half-width trong một số hệ chữ, có thể phải cân nhắc `Collator.FULL_DECOMPOSITION`, với chi phí và semantics khác.

Các lựa chọn của `Collator`:

- `NO_DECOMPOSITION`: không phân rã dữ liệu đầu vào theo chế độ này trước so sánh.
- `CANONICAL_DECOMPOSITION`: dùng chuẩn hóa tương đương chuẩn tắc, phù hợp nhiều trường hợp dấu tổ hợp.
- `FULL_DECOMPOSITION`: xét cả tương đương compatibility theo cơ chế của collator.

**Không suy ra** rằng bật `CANONICAL_DECOMPOSITION` sẽ làm hai chuỗi trở thành bằng nhau theo `String.equals`, hoặc thay đổi nội dung nguồn. Đó chỉ là cách collator xử lý khi so sánh.

### 7.2. Hai modifier đặc biệt

JDK 17 mô tả thêm:

- `@`: bật cách xét **trọng số dấu (secondary) ngược hướng** trong bảng, phục vụ kiểu sắp xếp dấu theo truyền thống Pháp.
- `!`: bật **đảo thứ tự nguyên âm–phụ âm** cho những trường hợp tương ứng trong tiếng Thái và Lào.

Chúng không tương ứng với một cấp khác biệt riêng như `<` hay `;`, và có thể tác động tới **toàn collator**. Không thêm `@` hoặc `!` vào rule chỉ vì muốn “sắp xếp Unicode tốt hơn”; chỉ dùng khi nghiệp vụ/ngôn ngữ cụ thể cần và đã kiểm thử từ điển thực tế.

## 8. Chương trình Java 17 hoàn chỉnh: contraction, reset, strength và lỗi rule

Ví dụ dưới đây cố ý dùng một bảng chữ cái **nhỏ** để quan sát hành vi. Kết quả được in theo **nhãn ASCII** thay vì phụ thuộc console font/encoding khi hiển thị chữ `á`.

**Tệp `CustomCollationDemo.java`:**

~~~java
import java.text.CollationKey;
import java.text.Collator;
import java.text.ParseException;
import java.text.RuleBasedCollator;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class CustomCollationDemo {
    static int sign(RuleBasedCollator c, String a, String b) {
        return Integer.signum(c.compare(a, b));
    }

    public static void main(String[] args) throws ParseException {
        String rules = "< a , A ; \u00E1 < b < c < ch < d & b < bb";
        RuleBasedCollator c = new RuleBasedCollator(rules);

        c.setStrength(Collator.PRIMARY);
        System.out.println("PRIMARY a/A=" + sign(c, "a", "A"));
        System.out.println("PRIMARY a/acute=" +
                sign(c, "a", "\u00E1"));

        c.setStrength(Collator.SECONDARY);
        System.out.println("SECONDARY a/A=" + sign(c, "a", "A"));
        System.out.println("SECONDARY a/acute=" +
                sign(c, "a", "\u00E1"));

        c.setStrength(Collator.TERTIARY);
        System.out.println("TERTIARY a/A=" + sign(c, "a", "A"));
        System.out.println("TERTIARY c/ch=" + sign(c, "c", "ch"));
        System.out.println("TERTIARY ch/d=" + sign(c, "ch", "d"));
        System.out.println("TERTIARY bb/c=" + sign(c, "bb", "c"));

        List<String> words = new ArrayList<>(
                Arrays.asList("d", "ch", "c", "bb", "b", "\u00E1", "A", "a"));
        words.sort(c);
        String sortedLabels = words.stream()
                .map(s -> s.equals("\u00E1") ? "a-acute" : s)
                .collect(Collectors.joining(", "));
        System.out.println("sorted=" + sortedLabels);

        CollationKey keyCh = c.getCollationKey("ch");
        CollationKey keyD = c.getCollationKey("d");
        System.out.println("key ch/d=" +
                Integer.signum(keyCh.compareTo(keyD)));

        RuleBasedCollator equivalent =
                new RuleBasedCollator("< a = \u00E1 < b");
        System.out.println("equal-rule a/acute=" +
                sign(equivalent, "a", "\u00E1"));

        try {
            new RuleBasedCollator("< a < b & z < zz");
            System.out.println("invalid reset=ACCEPTED");
        } catch (ParseException ex) {
            System.out.println("invalid reset=REJECTED");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CustomCollationDemo.java
java CustomCollationDemo
~~~

**Stdout đã kiểm tra trên JDK:**

~~~text
PRIMARY a/A=0
PRIMARY a/acute=0
SECONDARY a/A=0
SECONDARY a/acute=-1
TERTIARY a/A=-1
TERTIARY c/ch=-1
TERTIARY ch/d=-1
TERTIARY bb/c=-1
sorted=a, A, a-acute, b, bb, c, ch, d
key ch/d=-1
equal-rule a/acute=0
invalid reset=REJECTED
~~~

Ý nghĩa:

1. Ở **PRIMARY**, `a`/`A` và `a`/`á` giống nhau theo trọng số chính.
2. Ở **SECONDARY**, dấu sắc làm `a` đứng trước `á`, còn `a`/`A` vẫn bằng nhau vì khác biệt case nằm ở tertiary.
3. Ở **TERTIARY**, `a` đứng trước `A` **theo rule mẫu**. Đây không phải tuyên bố rằng trong mọi locale chữ thường đều trước chữ hoa.
4. Quan hệ `c < ch < d` được giữ; `ch` là contraction trong bảng so sánh.
5. `& b < bb` đặt `bb` sau `b` và trước `c`.
6. `List.sort(c)` dùng comparator đã thiết lập, tạo thứ tự ổn định của đầu vào mẫu.
7. `CollationKey.compareTo` được sinh từ **cùng collator/cấu hình** phù hợp với chiều so sánh `ch` và `d`.
8. Với rule `=`, `a` và `á` được coi là tương đương theo collation.
9. Reset đến `z` chưa tồn tại bị parser từ chối bằng `ParseException`.

**Giới hạn quan trọng:** bảng rule ngắn không mô tả toàn bộ ký tự của ngôn ngữ; các dữ liệu không được liệt kê có thể xếp ở cuối. Không đưa nguyên rule demo vào hệ thống sắp xếp địa chỉ, tên người hoặc văn bản quốc tế lớn mà không mở rộng và kiểm tra.

## 9. CollationKey: cách tối ưu khi so sánh lặp lại

Nếu cùng một tập chuỗi cần được so sánh nhiều lần (chẳng hạn trong một phép sort lớn), `CollationKey` cho phép tính trước trọng số so sánh của từng chuỗi:

~~~java
CollationKey a = custom.getCollationKey("ch");
CollationKey b = custom.getCollationKey("d");
int relation = a.compareTo(b);
~~~

Đây là snippet minh họa; `custom` là `RuleBasedCollator` đã tạo. Trong ví dụ, `relation` âm vì `ch` đứng trước `d`.

Không dùng key từ **hai collator/cấu hình khác nhau** như thể chúng có cùng chuẩn:

- Mức `strength` có thể khác.
- Chế độ `decomposition` có thể khác.
- Rule table hoặc locale provider khác nhau.
- Phiên bản JDK có thể mang dữ liệu collation khác nhau.

Vì vậy không nên lưu `CollationKey` dài hạn rồi so với key mới được sinh sau khi đổi rule hoặc nâng phiên bản runtime. Nếu cần persistence, hãy xác định cơ chế versioning/rebuild key và kiểm chứng tính tương thích.

`CollationKey` có thể tăng chi phí bộ nhớ; với danh sách nhỏ hoặc số phép so sánh ít, gọi `collator.compare` trực tiếp thường đơn giản hơn. Nếu hiệu năng là lý do chính, hãy **benchmark** với dữ liệu thực, không giả định key luôn nhanh hơn trong mọi tình huống.

## 10. Thread safety, tính ổn định và cơ sở dữ liệu

`Collator` có các setter như `setStrength`, `setDecomposition`; `RuleBasedCollator` còn giữ bảng quy tắc. **Không dùng chung một instance có trạng thái biến đổi giữa nhiều thread** mà không có quản lý đồng bộ phù hợp. Một mẫu thường dùng là tạo/cấu hình comparator trước khi sort, giữ nó riêng cho thao tác, hoặc clone từ một mẫu đã cấu hình:

~~~java
RuleBasedCollator configured =
        new RuleBasedCollator("< a < b < c");
configured.setStrength(Collator.SECONDARY);

RuleBasedCollator forThisTask =
        (RuleBasedCollator) configured.clone();
~~~

Đây là đoạn minh họa trong phương thức ném hoặc bắt `ParseException`; bản clone có thể được dùng cho một thao tác riêng, không đổi strength của đối tượng đang được dùng ở thao tác khác.

**Đừng nhầm Java collation và database collation**: việc danh sách đã được sort bởi `RuleBasedCollator` trên JVM không đảm bảo `ORDER BY` trong cơ sở dữ liệu dùng cùng quy tắc. Nếu phân trang ở DB rồi sắp lại từng trang ở Java, thứ tự toàn cục có thể sai. Cần thống nhất hợp đồng sort/pagination/search trên một tầng hoặc định nghĩa dữ liệu collation tương thích trên cả hai.

Khi nâng JDK/locale provider hoặc sửa rule, mọi thay đổi thứ tự đều có thể ảnh hưởng cache, index, số trang, danh mục đã xuất và kiểm thử snapshot. Với ứng dụng cần thứ tự ổn định lâu dài, nên có **version rule** và bộ dữ liệu hồi quy kiểm tra thứ tự.

## 11. Các lỗi thường gặp

| Lỗi | Tại sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng `String.compareTo` cho tên người đa ngôn ngữ | So UTF-16, không hiểu quy ước bản địa | Dùng `Collator` theo locale |
| Dùng rule demo ngắn cho toàn bộ Unicode | Ký tự chưa khai báo xếp cuối | Bắt đầu từ rules locale hoặc bộ tailoring đầy đủ |
| Viết `a < b` thay vì một rule hoàn chỉnh | Thiếu quan hệ khởi tạo | Viết `< a < b` |
| Bỏ quote cho dấu câu trong text argument | Parser hiểu nhầm cú pháp/ParseException | Quote ký tự đặc biệt |
| Reset `& z` khi chưa khai báo `z` | Không có vị trí chèn | Dùng reset có điểm đã tồn tại |
| Nhầm `;` và `,` | Sai mức trọng số | Ghi rõ secondary/tertiary, kiểm thử strength |
| Nghĩ `ch` contraction thay đổi `String.length()` | Collation chỉ thay trọng số so sánh | Tách xử lý Unicode với sort |
| Đặt `PRIMARY` rồi dùng compare==0 làm ID duy nhất | Bỏ qua dấu/case theo policy | Dùng tiêu chí duy nhất độc lập, rõ ràng |
| Dùng `TreeSet` với collator mà không xét trùng | Có thể bỏ các chuỗi compare==0 | Quyết định tie-breaker/semantics |
| Ghép `CollationKey` từ hai rule/version khác nhau | Không cùng tiêu chuẩn so sánh | Tạo key từ cùng collator/cấu hình |
| Dùng chung instance và đổi strength giữa nhiều thread | Kết quả không ổn định | Quản lý instance/clone/synchronization |
| Tin rule Java = rule của ICU | Cú pháp/tính năng không hoàn toàn trùng | Dùng đúng API/tài liệu implementation |
| Tin JVM sort tự quyết định thứ tự DB | DB dùng collation khác | Thống nhất sort contract trên toàn hệ thống |
| Không kiểm tra Unicode decomposition | Chuỗi dấu tổ hợp có thể xử lý khác ý muốn | Kiểm thử và đặt decomposition phù hợp |

## 12. Kiểm thử nên viết trước khi triển khai

Hãy tạo tập dữ liệu có tối thiểu:

1. Chữ cơ sở `a`, `A`, `b`, `c`, `d`.
2. Chữ có dấu, ví dụ `á` và dạng `a` + U+0301.
3. Contraction `ch` và các từ có `ch` ở đầu, giữa hoặc cuối.
4. Vị trí reset `bb` và các chuỗi gần `b`/`c`.
5. Dấu câu, khoảng trắng, ký hiệu chưa được khai báo trong rules.
6. Chữ số, chữ hoa/thường, các ngôn ngữ khác nếu có trong dữ liệu thực.
7. Rule thiếu quote, thiếu argument hoặc reset đến ký tự chưa có.
8. Trường hợp `compare(a, b) == 0` nhưng `!a.equals(b)`.
9. Chênh lệch khi chuyển `PRIMARY`, `SECONDARY`, `TERTIARY`, `IDENTICAL`.
10. Ảnh hưởng của `CANONICAL_DECOMPOSITION` và `FULL_DECOMPOSITION` nếu ứng dụng cần.
11. `CollationKey` so với `compare` trên cùng cấu hình.
12. Tính ổn định của thứ tự sau khi cập nhật JDK, rule và DB.

Các bất biến comparator nên giữ: phản đối xứng về dấu (`sign(compare(a,b)) = -sign(compare(b,a))`), tính bắc cầu và tính nhất quán của equivalence. Đặc biệt khi thêm **tie-breaker**, hãy thử trên tập dữ liệu thật để không tạo thứ tự mâu thuẫn.

Nếu nghiệp vụ cần sắp xếp **tiếng Việt chuẩn**, không tự viết một vài relation rồi coi là tiêu chuẩn. Hãy dùng nguồn collation được quản lý theo locale và tham chiếu quy ước sản phẩm, sau đó chỉ chỉnh rule khi có yêu cầu ngoại lệ cụ thể.

## 13. Bài tập thực hành

1. Đổi `< c < ch < d` thành `< c < d < ch`; so thứ tự danh sách để thấy vai trò của contraction.
2. Đổi `& b < bb` thành `& c < bb` trong rule có c; dự đoán và kiểm thử vị trí mới của `bb`.
3. Bỏ `;` trước `á` và dùng `<`; so kết quả ở `PRIMARY` và `SECONDARY`.
4. Thay `< a , A` bằng `< a < A`; chỉ ra vì sao từ nay `PRIMARY` có thể phân biệt case.
5. Tạo bảng có `< a = á < b`; thử `TreeSet` so với `HashSet` khi thêm hai chuỗi.
6. Thử rules `< a < b < 'x-y' < c` và so `x-y` với `b`, `c`. Tiếp đó bỏ quote để kiểm tra lỗi parser.
7. Tạo danh sách từ có `á` ở dạng NFC và NFD; thử `NO_DECOMPOSITION`, `CANONICAL_DECOMPOSITION`.
8. Đọc `Collator.getInstance(Locale.forLanguageTag("vi-VN"))`, quan sát class trả về, chỉ đọc `getRules()` nếu thực sự là `RuleBasedCollator`.
9. Clone một collator rồi đặt `PRIMARY` cho bản sao, `TERTIARY` cho bản gốc; chứng minh không thay đổi strength của nhau.
10. Viết test lưu thứ tự danh sách mẫu; chạy lại sau khi nâng JDK hoặc thay đổi rule.
11. Thử so sánh `ch` với `c`, `d` bằng `CollationKey` và so dấu với `compare`.
12. Đề xuất chính sách sắp xếp cho danh sách khách hàng chứa tên Việt, tên Latin và ID kỹ thuật; chỉ rõ phần nào dùng `Collator`, phần nào dùng thứ tự kỹ thuật.

## 14. Tóm tắt

`RuleBasedCollator` cho phép xây bộ so sánh chuỗi theo một **bảng quy tắc văn bản** thay vì dựa trên thứ tự UTF-16. Dấu `<`, `;`, `,` xác định primary/secondary/tertiary, `=` biểu diễn tương đương collation, và `&` reset để chèn quy tắc tại vị trí đã có. Contraction và expansion thay đổi **cách so sánh**, không thay đổi nội dung chuỗi.

Trong ứng dụng bản địa hóa, ưu tiên `Collator.getInstance(locale)` cho ngôn ngữ thông thường; dùng custom rules khi có yêu cầu rõ, đã kiểm tra cú pháp, Unicode/decomposition, strength, các trường hợp tie và regression test. Nhớ rằng rule ngắn sẽ không bao phủ toàn bộ ký tự và có thể sắp xếp không đúng mong đợi; thứ tự của Java còn phải nhất quán với cơ sở dữ liệu và quy tắc nghiệp vụ.

**Tài liệu tham khảo:**

- Java SE 17, `RuleBasedCollator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/RuleBasedCollator.html
- Java SE 17, `Collator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html
- Java SE 17, `CollationKey`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CollationKey.html
- Java SE 17, `Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
