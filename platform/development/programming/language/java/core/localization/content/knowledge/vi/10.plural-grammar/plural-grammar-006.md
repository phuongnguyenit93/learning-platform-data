# Giới hạn của ChoiceFormat với quy tắc số nhiều và giới tính ngữ pháp trong Java

## 1. Đặt vấn đề: ngưỡng số không phải ngữ pháp

Trong ứng dụng đa ngôn ngữ, cùng một thông báo có thể cần nhiều cách viết tùy theo **số lượng**, **danh từ**, **giới tính ngữ pháp**, **cách (grammatical case)** hoặc những thông tin ngữ cảnh khác. Chẳng hạn, tiếng Anh có thể viết:

- `0 files` → “no files”
- `1 file` → “one file”
- `2 files` → “2 files”

Java cung cấp `java.text.ChoiceFormat` để **chọn một chuỗi theo các khoảng giá trị số**. Khi nhúng vào `java.text.MessageFormat`, cú pháp phổ biến là:

```text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

Với các số nguyên không âm và câu tiếng Anh đơn giản, cách viết này có thể đáp ứng nhu cầu. Tuy nhiên, nó không đồng nghĩa với bộ máy ngữ pháp đa ngôn ngữ:

1. Nhiều ngôn ngữ có **plural categories** phụ thuộc phép chia lấy dư, số chữ số thập phân và cách biểu diễn số, không phải các khoảng tăng tuyến tính.
2. **Grammatical gender** của danh từ, đại từ hoặc từ cần hòa hợp không thể suy ra từ số lượng.
3. **Số nhiều + giới tính + cách ngữ pháp** có thể ảnh hưởng nhiều từ trong cùng câu, thay vì chỉ thay một hậu tố của danh từ.
4. `ChoiceFormat` không hỗ trợ trực tiếp các biểu thức ngữ pháp như `plural` và `select` của ICU MessageFormat. Đó là hai cơ chế khác nhau.

**Mục tiêu:** hiểu chính xác `ChoiceFormat` làm được gì, nhận diện trường hợp dùng sai, và biết cách thiết kế thông điệp bản địa hóa đúng khi có plural rules và grammatical gender.

## 2. ChoiceFormat thực chất chọn theo giới hạn số

`ChoiceFormat` định nghĩa một tập ranh giới số có thứ tự và thông điệp tương ứng. Một pattern như:

```text
0#none|1#one|1<many
```

được diễn giải theo các ngưỡng sau:

| Điều kiện đầu vào | Nhánh | Kết quả |
| --- | --- | --- |
| `n = 0` | `0#none` | `none` |
| `n = 1` | `1#one` | `one` |
| `n > 1` | `1<many` | `many` |

Ở đây:

- `#` (và ký hiệu bao gồm tương ứng trong ChoiceFormat) chỉ nhánh bắt đầu từ **ngưỡng được tính vào**.
- `<` biểu thị **lớn hơn nghiêm ngặt** ngưỡng.
- `|` phân tách các nhánh.
- Những ngưỡng được xem theo thứ tự tăng; mỗi lựa chọn tương ứng một khoảng trên trục số.
- Với số **nhỏ hơn giới hạn đầu tiên**, `ChoiceFormat` vẫn sử dụng chuỗi của nhánh đầu tiên; nó không tự báo rằng dữ liệu không hợp lệ.

Có thể tạo `ChoiceFormat` độc lập:

```java
ChoiceFormat format =
        new ChoiceFormat("0#none|1#one|1<many");
System.out.println(format.format(2)); // many
```

Hoặc dùng `MessageFormat` để chèn lại số vào kết quả của nhánh:

```java
MessageFormat format = new MessageFormat(
        "{0,choice,0#no files|1#one file|1<{0,number,integer} files}",
        Locale.US);
System.out.println(format.format(new Object[] {2})); // 2 files
```

Hai đoạn trên là mã minh họa bên trong phương thức Java, cần import các class tương ứng. Điểm đáng chú ý: `MessageFormat` có thể xử lý **format element lồng trong phần kết quả của choice**, nhưng điều đó chỉ giúp chèn giá trị; nó không tự biết plural rules của tiếng Nga hay tiếng Ả Rập.

### Các ngộ nhận về điều kiện

`ChoiceFormat` không có API biểu thức điều kiện tổng quát trong pattern:

- Không viết trực tiếp điều kiện kiểu `n % 10 == 1`.
- Không tự tính ngữ cảnh của từ đếm hoặc gender của danh từ.
- Không lấy quy tắc số nhiều từ `Locale` để sinh các nhánh `one/few/many`.
- Không tự giới hạn đầu vào là số nguyên không âm.
- Không tự bảo đảm số được in lồng trong nhánh `{0,number,integer}` phản ánh đúng giá trị thập phân ban đầu: formatter có thể làm tròn.

Vì vậy, nên xem `ChoiceFormat` là **bộ chọn khoảng số**, không phải **plural grammar engine**.

## 3. Plural rules: phân loại theo ngôn ngữ, không chỉ theo số

Unicode CLDR định nghĩa các **plural categories** để diễn tả cách dùng số lượng theo locale. Các tên category thường gặp là `zero`, `one`, `two`, `few`, `many` và `other`. Tên này là **nhãn quy tắc**, không phải nghĩa đen rằng giá trị luôn bằng 0, 1, 2. Mỗi ngôn ngữ có thể sử dụng chỉ một tập con.

Ví dụ khái quát:

| Ngôn ngữ/nhóm | Điều cần chú ý |
| --- | --- |
| Tiếng Anh | Card​​inal singular thường dành cho giá trị nguyên `1`, còn các giá trị khác dùng dạng khác; dữ liệu có chữ số thập phân hiển thị cần xét riêng. |
| Tiếng Việt | Không dùng biến tố số ít/số nhiều kiểu tiếng Anh cho danh từ; lựa chọn câu vẫn phụ thuộc ngữ cảnh, lượng từ và cách diễn đạt. |
| Tiếng Nga | Với số nguyên, các dạng phụ thuộc chữ số cuối và **hai chữ số cuối**, không chỉ thứ tự `1, 2, 5, 21...`. |
| Tiếng Ả Rập | Có các nhóm như `zero`, `one`, `two`, `few`, `many`, `other`, với các điều kiện riêng theo locale. |
| Tiếng Ba Lan | Có nhiều lớp plural, trong đó các dạng thập phân và quy tắc phần dư có thể khác số nguyên. |

CLDR sử dụng các toán hạng như `n` (giá trị tuyệt đối), `i` (phần nguyên), `v` (số chữ số phần thập phân hiển thị), `w` (số chữ số thập phân bỏ số 0 cuối) và các chữ số thập phân để xác định category. Chi tiết quan trọng là **dạng hiển thị có thể ảnh hưởng category**. Các cách viết `1` và `1.0` có thể được phân loại khác nhau bởi các quy tắc xét `v`, mặc dù giá trị số học bằng nhau.

Trong hệ thống thực, không thể luôn khôi phục số chữ số thập phân mà người dùng đã nhập chỉ từ `double`. Nếu chính sách plural phụ thuộc biểu diễn, dữ liệu đầu vào hoặc tầng định dạng phải giữ thông tin cần thiết.

### Cardinal khác ordinal

Các quy tắc **cardinal** dùng cho đếm số lượng (1 file, 2 files), trong khi **ordinal** dùng cho thứ tự (1st, 2nd, 3rd). Một ngôn ngữ có thể có hệ nhóm ordinal khác cardinal. `ChoiceFormat` không phân biệt hay tự chọn loại quy tắc này từ ngữ cảnh; đó phải là một phần thiết kế message.

## 4. Vì sao các ngưỡng cố định thất bại với tiếng Nga?

Với **số nguyên không âm** trong ví dụ tiếng Nga, một cách phân loại giản lược thường gặp là:

- `one` khi chữ số cuối là 1, **trừ** các số có hai chữ số cuối bằng 11.
- `few` khi chữ số cuối là 2, 3, 4, **trừ** các số có hai chữ số cuối là 12, 13, 14.
- `many` cho các số nguyên không âm còn lại, trong ngữ cảnh này.

Vì vậy:

| Số | Nhóm minh họa | Giải thích |
| ---: | --- | --- |
| 1 | `one` | Kết thúc bằng 1, không kết thúc bằng 11. |
| 2 | `few` | Kết thúc bằng 2, không phải 12. |
| 5 | `many` | Không thuộc `one/few`. |
| 11 | `many` | Ngoại lệ với hai chữ số cuối 11. |
| 21 | `one` | Chữ số cuối 1, hai chữ số cuối 21. |
| 22 | `few` | Chữ số cuối 2, hai chữ số cuối 22. |
| 25 | `many` | Chữ số cuối 5. |

Hãy thử diễn tả các nhóm này bằng pattern `ChoiceFormat` ngây thơ:

```text
0#many|1#one|2#few|5#many
```

Mẫu hoạt động cho 1, 2, 5, 11 nhưng tại **21** vẫn chọn `many`, trong khi nhóm đúng cho số nguyên đó là `one`; tại **22** vẫn chọn `many`, trong khi nhóm đúng là `few`.

Ta có thể thêm các ngưỡng `21`, `22`, `25`, nhưng chu kỳ sẽ lại lặp cho `31`, `32`, `41`, `42`... Một danh sách **hữu hạn những ngưỡng liên tiếp** không biểu diễn tổng quát quy tắc modulo lặp vô hạn trên mọi số nguyên không âm. Đó là hạn chế về mô hình, không phải lỗi cú pháp pattern.

**Giới hạn của quy tắc minh họa ở trên:** nó chỉ dùng cho các **số nguyên không âm** để cho thấy vấn đề modulo. Với số thập phân, plural rule tiếng Nga có thể chọn `other`; không áp dụng các phép modulo trên `int` rồi coi là engine CLDR hoàn chỉnh. Trong ứng dụng thực, hãy dùng dữ liệu plural rule cho locale tương ứng thay vì tự viết quy tắc dựa trên một vài ví dụ.

## 5. Grammatical gender: ChoiceFormat không nhận được ngữ cảnh cần thiết

**Giới tính ngữ pháp** là đặc tính của những từ/cấu trúc trong một ngôn ngữ, ví dụ một danh từ giống đực hoặc giống cái trong tiếng Tây Ban Nha. Đây **không đồng nhất** với giới tính hay bản dạng giới của người dùng.

Ví dụ tiếng Tây Ban Nha:

- `un archivo nuevo` — “một tệp mới”, danh từ `archivo` thuộc giống đực; mạo từ `un` và tính từ `nuevo` tương ứng.
- `una carpeta nueva` — “một thư mục mới”, danh từ `carpeta` thuộc giống cái; mạo từ `una` và tính từ `nueva` tương ứng.

Giả sử cả hai đều có **số lượng 1**. Nếu chỉ truyền số 1 vào `ChoiceFormat` thì không có đủ dữ liệu để phân biệt `archivo` với `carpeta`, chọn `un/una` hay `nuevo/nueva`. Việc thêm hàng loạt ngưỡng không thể biến dữ liệu numeric thành thông tin về gender của danh từ.

Trong một số ngôn ngữ, biến đổi còn liên quan đại từ, động từ, tính từ, cách ngữ pháp, số lượng hoặc vai trò của người được nhắc tới. Lựa chọn hình thái cần **ngữ cảnh ngôn ngữ rõ ràng** và bản dịch phù hợp, không nên đoán từ tên người, địa chỉ hay một thuộc tính không liên quan.

### Dữ liệu cần truyền vào message

Tùy yêu cầu sản phẩm, một message có thể cần các biến:

| Biến | Ví dụ | Ghi chú |
| --- | --- | --- |
| `count` | `21` | Cần plural category theo locale, có thể phải giữ biểu diễn thập phân. |
| `nounKey` | `file`, `folder` | Danh từ có từ vựng và gender ngữ pháp. |
| `grammaticalGender` | `masculine`, `feminine`, `neuter`, `other` | Có thể thuộc về danh từ; không suy từ số. |
| `grammaticalCase` | `nominative`, `accusative`... | Chỉ khi ngôn ngữ/câu cần. |
| `formality` | `formal`, `informal` | Phong cách xưng hô có thể ảnh hưởng câu. |
| `locale` | `es-ES`, `ru-RU` | Xác định bộ quy tắc/ngôn ngữ của thông điệp. |

Không phải sản phẩm nào cũng cần truyền mọi biến. Thiết kế **hợp đồng tham số tối thiểu nhưng đủ** cho từng key dịch giúp tránh code quá tổng quát, đồng thời không làm mất ngữ cảnh quan trọng.

## 6. Ví dụ Java 17+ chạy độc lập: điểm mạnh và điểm yếu

Tệp **`ChoiceFormatLimitsDemo.java`** dưới đây có ba phần:

1. Dùng `MessageFormat` với `choice` để hiển thị thông báo tiếng Anh đơn giản về số tệp.
2. Dùng `ChoiceFormat` ngưỡng số để tạo nhóm `one/few/many` giả lập, đối chiếu với một phép tính minh họa cho **số nguyên tiếng Nga** nhằm thấy lỗi ở 21 và 22.
3. Chọn cụm từ Tây Ban Nha dựa trên gender ngữ pháp được truyền tường minh, không dựa trên số.

**Lưu ý:** hàm `russianIntegerExampleCategory` chỉ giải thích trường hợp số nguyên không âm trong bài học. Nó **không phải** một thư viện plural rules cho production: không xử lý số thập phân, cách viết số, quy tắc các locale khác hoặc thay đổi của dữ liệu CLDR.

```java
import java.text.ChoiceFormat;
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceFormatLimitsDemo {

    enum Gender {
        MASCULINE,
        FEMININE
    }

    // Minh họa giới hạn ở số nguyên không âm.
    private static String russianIntegerExampleCategory(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }

        int last = n % 10;
        int lastTwo = n % 100;

        if (last == 1 && lastTwo != 11) {
            return "one";
        }
        if (last >= 2 && last <= 4
                && (lastTwo < 12 || lastTwo > 14)) {
            return "few";
        }
        return "many";
    }

    // Chỉ là hai ví dụ từ vựng, không phải bộ biến hình
    // tiếng Tây Ban Nha cho mọi danh từ.
    private static String spanishPhrase(Gender gender, String noun) {
        return switch (gender) {
            case MASCULINE -> "un " + noun + " nuevo";
            case FEMININE -> "una " + noun + " nueva";
        };
    }

    public static void main(String[] args) {
        MessageFormat english = new MessageFormat(
                "{0,choice,0#no files|1#one file"
                + "|1<{0,number,integer} files}",
                Locale.US);

        for (int n : new int[] {0, 1, 2, 21}) {
            System.out.println("en(" + n + ")="
                    + english.format(new Object[] {n}));
        }

        ChoiceFormat naiveRu = new ChoiceFormat(
                "0#many|1#one|2#few|5#many");

        for (int n : new int[] {1, 2, 5, 11, 21, 22, 25}) {
            System.out.println("ru(" + n + ")=choice:"
                    + naiveRu.format(n)
                    + ", rule:" + russianIntegerExampleCategory(n));
        }

        System.out.println("es(m)="
                + spanishPhrase(Gender.MASCULINE, "archivo"));
        System.out.println("es(f)="
                + spanishPhrase(Gender.FEMININE, "carpeta"));
    }
}
```

Để biên dịch và chạy trong thư mục chứa tệp, dùng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 ChoiceFormatLimitsDemo.java
java ChoiceFormatLimitsDemo
```

**Stdout chính xác:**

```text
en(0)=no files
en(1)=one file
en(2)=2 files
en(21)=21 files
ru(1)=choice:one, rule:one
ru(2)=choice:few, rule:few
ru(5)=choice:many, rule:many
ru(11)=choice:many, rule:many
ru(21)=choice:many, rule:one
ru(22)=choice:many, rule:few
ru(25)=choice:many, rule:many
es(m)=un archivo nuevo
es(f)=una carpeta nueva
```

### Phân tích kết quả

- Các dòng `en(...)` cho thấy `choice` hữu ích cho thông điệp nhỏ, miền giá trị số nguyên không âm và các nhánh do người dịch xác nhận.
- `ru(21)` và `ru(22)` là **mâu thuẫn cố ý** giữa phân loại theo khoảng của `ChoiceFormat` và phân loại dựa trên phép chia lấy dư trong ví dụ tiếng Nga.
- `ru(11)` minh họa ngoại lệ: chữ số cuối 1 nhưng hai chữ số cuối 11, nên không thuộc nhóm `one`.
- Hai dòng `es(...)` giữ số lượng ngầm là một nhưng thay mạo từ và tính từ do gender ngữ pháp của danh từ được đưa vào hàm. Logic này **được viết riêng**, không phải chức năng native của `ChoiceFormat`.
- Nếu ứng dụng cần xử lý hàng trăm danh từ, nhiều ngôn ngữ và các hình thái khác, phương thức `spanishPhrase` này không đủ; cần nguồn dữ liệu từ vựng và chuỗi dịch chính xác.

## 7. Ví dụ phản chứng bổ sung: số thập phân và số âm

Ngay cả với ngôn ngữ có plural tương đối đơn giản, một pattern dùng ngưỡng có thể tạo output gây hiểu nhầm nếu đầu vào không đúng miền đã xác định.

### Số âm

Với:

```text
0#no files|1#one file|1<many files
```

`ChoiceFormat` có thể cho kết quả `no files` ngay cả khi đầu vào là `-1`, vì `-1` nằm dưới giới hạn đầu tiên. Đây không phải một quy tắc ngữ pháp cho số âm, mà là hành vi chọn nhánh ngoài khoảng bắt đầu. Cần quyết định riêng rằng **count phải là số nguyên không âm** và validate trước khi format.

### Số thập phân

Nếu nhánh cho “lớn hơn 1” chứa `{0,number,integer}` và đầu vào là `1.5`, phần số được trình bày dưới dạng số nguyên bằng cơ chế làm tròn của formatter. Như vậy, thông điệp có thể xuất hiện số khác giá trị ban đầu dù việc chọn nhánh `choice` dựa trên `1.5`.

Dữ liệu số nhiều cho sản phẩm có thể bao gồm cân nặng, khối lượng, thời lượng hoặc các đại lượng không nguyên. Không nên ép mọi loại số vào mẫu đếm tệp `integer`. Các quy tắc PLURAL cho số thập phân có thể phụ thuộc cả số chữ số sau dấu thập phân được thể hiện; `ChoiceFormat` đơn giản không quản lý được ngữ nghĩa đó.

### Giá trị bị giới hạn trong một domain

Nếu domain thực sự là đúng ba mức `0`, `1`, `>=2` với giá trị đếm nguyên không âm, có thể dùng `ChoiceFormat` sau kiểm tra đầu vào. Vấn đề là **tính đúng của giả định domain**, không phải việc `ChoiceFormat` luôn vô dụng.

## 8. Không nên dùng ChoiceFormat để mã hóa giới tính bằng số

Một “mẹo” dễ gặp là biến `masculine=0`, `feminine=1` rồi viết pattern `choice` để chọn văn bản theo chỉ số. Cách này chỉ tạo ra một **lookup số giả**, không đem lại khả năng hiểu ngữ pháp:

- Khi thêm `neuter` hoặc `other`, các số magic trở nên khó bảo trì.
- Không mô tả được quan hệ giữa danh từ, mạo từ, tính từ, động từ và cách ngữ pháp.
- Dễ nhầm `gender` của người dùng với `grammaticalGender` của một từ, dẫn đến suy diễn không phù hợp.
- Không giúp biên dịch/kiểm tra sự đầy đủ của bản dịch theo locale.
- Không tự phối hợp với plural categories đúng của ngôn ngữ.

Nếu danh sách lựa chọn hữu hạn và thuộc nghiệp vụ, có thể dùng `enum` hoặc key định danh rõ ràng để chọn **message key** trước khi format. Nhưng các biến thể bản dịch vẫn cần người dịch kiểm tra; không biến `gender` thành chỉ số số học.

Ví dụ một thiết kế key tường minh:

```text
file.created.masculine=...
folder.created.feminine=...
notification.formal=...
notification.informal=...
```

Đây là **mẫu minh họa cách tổ chức khóa**, không phải quy tắc dịch mọi ngôn ngữ. Trên quy mô lớn, việc tạo mọi tổ hợp key thủ công có thể khó bảo trì. Khi cần plural + gender + select phức tạp, dùng định dạng message hỗ trợ selector là hợp lý hơn.

## 9. Java MessageFormat chuẩn khác ICU MessageFormat

Rất dễ nhầm các API có tên tương tự:

| API/cơ chế | Khả năng chính | Giới hạn |
| --- | --- | --- |
| `java.text.ChoiceFormat` (JDK) | Chọn văn bản theo giới hạn số. | Không có native CLDR plural/gender selector. |
| `java.text.MessageFormat` (JDK) | Ghép tham số, định dạng number/date/time, chứa format element `choice`. | Không hỗ trợ sẵn cú pháp ICU `plural`/`select`. |
| ICU4J `com.ibm.icu.text.MessageFormat` | Hỗ trợ cú pháp ICU MessageFormat với `plural`, `selectordinal` và `select` theo dữ liệu locale. | Là thư viện ngoài JDK; cần dependency và bản dịch phù hợp. |
| `ResourceBundle` (JDK) | Chọn tệp/nguồn message theo locale và fallback key. | Chỉ tra tài nguyên; không tự giải quyết plural hay giới tính ngữ pháp. |

ICU MessageFormat có thể thể hiện ý tưởng:

```text
{count, plural,
    one {# file}
    other {# files}
}
```

Đây là **cú pháp minh họa cho ICU MessageFormat**, không phải pattern hợp lệ cho `java.text.MessageFormat` tiêu chuẩn. `#` ở trong nhánh plural của ICU có ngữ nghĩa thay bằng số lượng theo quy tắc của nó. Dữ liệu locale quyết định nhánh plural áp dụng, thay vì yêu cầu người viết tự chia các khoảng số.

Tương tự, ICU có selector theo thuộc tính phi số:

```text
{grammaticalGender, select,
    masculine {un archivo nuevo}
    feminine {una carpeta nueva}
    other {un elemento nuevo}
}
```

Đây vẫn chỉ là ví dụ với ba thông điệp đã viết trước. **`select` không tự biến đổi mọi danh từ/tính từ**. Nó chọn nhánh theo giá trị selector được cung cấp. Phần đúng ngữ pháp vẫn thuộc bản dịch và hợp đồng dữ liệu đầu vào.

Trong thực tế, pattern chứa plural và select có thể lồng nhau khi thông điệp phụ thuộc cả count và gender. Sự kết hợp đó làm phát sinh **nhiều hình thức ngữ pháp**, và có thể cần cách diễn đạt mới của người dịch thay vì nối mảnh câu. Hãy xem xét các ICU plural category thực sự dùng ở locale đó, không cố viết một pattern “dùng chung cho mọi ngôn ngữ”.

### Quy tắc chọn công cụ

- Nếu câu có vài lựa chọn theo **ngưỡng số hữu hạn**, và đã xác thực domain cũng như văn bản của locale: `ChoiceFormat` là lựa chọn phù hợp.
- Nếu câu cần **plural categories thực** cho nhiều locale, số thập phân hoặc cardinal/ordinal: dùng ICU4J hoặc một localization framework có dữ liệu CLDR tương đương.
- Nếu câu cần **chọn theo gender, formality, role**: dùng selector theo enum/message key hoặc engine hỗ trợ `select`.
- Nếu câu cần **hòa hợp phức tạp**, đôi khi nên dịch nguyên câu theo biến thể cụ thể thay vì cố ghép mạo từ, tính từ và danh từ bằng chuỗi con.

Không cần ICU4J cho mọi chương trình nhỏ; cần nó khi bài toán ngôn ngữ đã vượt khả năng lựa chọn theo khoảng số của JDK.

## 10. Thiết kế thông điệp và hợp đồng dữ liệu

Trước khi tạo một localization key, hãy phân biệt thông tin thuộc từng lớp:

1. **Nghiệp vụ:** số lượng nào là hợp lệ, count có luôn nguyên không âm không, có một hay nhiều loại đối tượng, số liệu có giữ chữ số thập phân không?
2. **Ngôn ngữ:** locale nào được hỗ trợ, cần plural cardinal hay ordinal, cần agreement của từ nào, giới tính ngữ pháp thuộc về danh từ nào?
3. **Hiển thị:** cấu trúc toàn câu, vị trí tham số, có cần rút gọn/chuyển câu cho tự nhiên không, có cần accessibility text riêng không?
4. **Công cụ:** JDK `MessageFormat` hay ICU4J, phiên bản dữ liệu locale, bộ kiểm thử message tại build time.

Đừng viết trực tiếp:

```java
String message = count + " file" + (count == 1 ? "" : "s");
```

cho một sản phẩm đa ngôn ngữ rồi kỳ vọng người dịch có thể sửa đúng. Logic này giả định quy tắc tiếng Anh và cứng hóa thứ tự câu trong code. Nếu chương trình chỉ chạy cho tiếng Anh, domain chỉ là số nguyên không âm, vẫn phải có kiểm thử 0/1/2 và quy định rõ đó là phạm vi có chủ ý.

Một hợp đồng message tốt nên nói rõ:

- `count` có kiểu gì, có chấp nhận fractional hay không, đơn vị là gì.
- `noun` hoặc `entityType` có những giá trị được hỗ trợ nào.
- `grammaticalGender` lấy từ dữ liệu ngôn ngữ nào; **không suy đoán về con người** từ số đếm.
- Người dịch được phép đảo thứ tự, đổi cả câu, dùng placeholder như thế nào.
- Nếu thiếu bản dịch của một category, chính sách fallback và kiểm tra CI ra sao.

## 11. Kiểm thử số nhiều: boundary test là chưa đủ

Với `ChoiceFormat`, test các điểm ngay dưới, đúng bằng, và ngay trên giới hạn sẽ bắt lỗi `#`/`<`. Nhưng khi ứng dụng cần plural theo locale, **chỉ kiểm tra 0, 1, 2, 5 là không đủ**. Những số như 11, 12, 14, 21, 22, 25, 101 có thể phơi bày điều kiện theo modulo; số thập phân phơi bày cách dùng các chữ số phần lẻ.

Ma trận gợi ý:

| Nhóm kiểm thử | Giá trị minh họa | Mục đích |
| --- | --- | --- |
| Nhánh English đơn giản | 0, 1, 2 | Thấy đúng message và thứ tự placeholder. |
| Ranh giới choice | -1, 0, 1, 1.0001, 2 | Kiểm tra giới hạn dưới, `#` và `<`; validate miền đầu vào. |
| Quy tắc chu kỳ Slavic | 1, 2, 5, 11, 12, 14, 21, 22, 25, 101 | Phân biệt phân loại theo modulo với ngưỡng. |
| Số thập phân | 1.0, 1.5, 2.0, 2.5 | Đánh giá biểu diễn số và quy tắc thập phân của locale. |
| Arabic cardinal | 0, 1, 2, 3, 11, 100 | Không giả định chỉ có one/other. |
| Gender của danh từ | Hai danh từ khác giống nhưng có cùng count | Kiểm tra mạo từ/tính từ được lựa chọn theo dữ liệu từ vựng. |
| Phối hợp count + gender | Mỗi plural category × từng variant liên quan | Kiểm tra nguyên câu, không chỉ hậu tố. |
| Locale fallback | Bản dịch thiếu một nhánh/key | Bảo đảm không hiển thị nhánh sai hoặc placeholder chưa thay. |

Với CLDR, nên xây các **golden tests dựa trên category đúng của từng locale**, không lấy output của `ChoiceFormat` làm ground truth. Giữ dữ liệu test ổn định và ghi nhận phiên bản localization library nếu sản phẩm yêu cầu kết quả hoàn toàn tái lập.

### Chú ý số 1 so với 1.0

Nếu engine xét `v` (số chữ số thập phân được hiển thị), `1` và `1.0` có thể nhận category khác. Một bộ test dùng `double 1.0` mà không lưu precision presentation sẽ không đủ mô tả điều kiện này. Xác định kiểu dữ liệu và API plural-selection phù hợp, đặc biệt khi số lượng lấy từ dữ liệu đo lường hoặc báo cáo.

## 12. Những lỗi triển khai phổ biến

| Sai lầm | Tại sao sai | Cách làm đúng |
| --- | --- | --- |
| Áp `0#...|1#...|1<...` cho mọi locale | Ngôn ngữ khác có thể dùng nhiều category và phép modulo. | Dựa trên plural rules theo locale hoặc dịch nguyên câu. |
| Nghĩ `one` luôn bằng 1 | Category là nhãn ngữ pháp, có thể phụ thuộc dạng số. | Dùng engine plural đúng và giữ biểu diễn số khi cần. |
| Dùng `ChoiceFormat` để chọn giống đực/cái bằng số magic | Không thể mô hình hóa agreement và dễ nhầm loại dữ liệu. | Dùng enum/select/message key và văn bản ngữ pháp đúng. |
| Gộp grammatical gender với giới tính người dùng | Hai khái niệm khác nhau và không thể suy ra thay nhau. | Chỉ sử dụng metadata ngôn ngữ cần thiết, minh bạch. |
| Đưa danh từ và hậu tố vào các placeholder tách rời | Có thể sai thứ tự từ hoặc sai hòa hợp. | Ưu tiên bản dịch toàn câu và biến thể cụ thể. |
| Test chỉ 1 và 2 | Bỏ sót 11, 21, 22, 101 và thập phân. | Kiểm thử các tập phản ví dụ theo locale. |
| Dùng `{0,number,integer}` cho count không nguyên | Có thể làm tròn khi hiển thị. | Kiểm tra domain và chọn formatter phù hợp. |
| Cho rằng `java.text.MessageFormat` hiểu `plural`/`select` | Đây không phải cú pháp của JDK MessageFormat. | Chọn ICU4J hoặc framework hỗ trợ tương ứng. |
| Truyền mỗi count, không truyền noun context | Không có đủ dữ liệu chọn mạo từ/tính từ. | Thiết kế hợp đồng message đủ thông tin. |
| Tự mã hóa bảng plural của mọi locale bằng `if` | Khó bảo trì, dễ thiếu trường hợp và sai với CLDR. | Sử dụng thư viện được cập nhật, kiểm thử trên locale thật. |

## 13. Bài tập thực hành

**Bài 1 — Xác định phạm vi ChoiceFormat:** tạo thông điệp tiếng Anh có ba nhánh `0`, `1` và `>1`. Test các số nguyên 0, 1, 2, 20, đồng thời thử -1 và 1.5. Nêu rõ giá trị nào nằm ngoài domain đếm file và cơ chế kiểm tra cần bổ sung.

**Bài 2 — Phản ví dụ tiếng Nga:** với pattern `0#many|1#one|2#few|5#many`, thử 1, 2, 5, 11, 21, 22, 25, 101. Phân tích vì sao thêm vài mốc vẫn không tạo thành quy tắc đúng cho **mọi** số nguyên không âm. Không dùng đoạn modulo minh họa cho số thập phân.

**Bài 3 — Gender độc lập với count:** cho `archivo` và `carpeta` đều có count=1. Thiết kế một `enum` chứa lexical metadata cần thiết, sau đó chọn bản dịch cho hai danh từ. Giải thích tại sao count không đủ xác định mạo từ và tính từ.

**Bài 4 — Chọn engine:** ứng dụng cần tiếng Anh, tiếng Việt, tiếng Nga và tiếng Ả Rập; số lượng có thể là 1, 2, 21, 22 và 1.5. So sánh cách xử lý nếu dùng JDK `ChoiceFormat` với dùng framework có CLDR plural/select. Chỉ rõ tình huống nào có thể dùng pattern choice giản đơn và tình huống nào không.

**Bài 5 — Thử nghiệm bản dịch:** lấy một message có count và grammatical gender. Viết test matrix bao phủ các category cardinal mà locale thật dùng, các giá trị enum hợp lệ, bản dịch fallback và trường hợp thiếu tham số. Kiểm tra **câu hoàn chỉnh** sau format thay vì chỉ kiểm tra chuỗi chứa count.

## 14. Tóm tắt và tiêu chí tự đánh giá

- **`ChoiceFormat` chọn một nhánh theo giới hạn numeric**, không tính CLDR plural category.
- Các quy tắc plural như tiếng Nga có chu kỳ theo chữ số cuối/hai chữ số cuối; các ngôn ngữ khác có thể xét decimal operands, ordinal hoặc các category khác.
- **Grammatical gender là dữ liệu từ vựng/ngữ pháp**, không phải giá trị đếm và không đồng nghĩa giới tính người dùng.
- `java.text.MessageFormat` chuẩn hỗ trợ `choice`, nhưng **không hỗ trợ cú pháp ICU `plural`/`select`**.
- Với ngữ pháp phức tạp, hãy dùng engine plural/select theo locale, bản dịch toàn câu và hợp đồng tham số rõ ràng; tránh tự “bẻ” `ChoiceFormat` thành bộ ngữ pháp chung.

Người học đạt mục tiêu khi có thể chỉ ra **một trường hợp ChoiceFormat phù hợp**, **một phản ví dụ số nhiều theo modulo**, **một trường hợp gender không thể suy từ số**, và giải thích cách chọn API để xử lý mỗi vấn đề đúng về localization.
