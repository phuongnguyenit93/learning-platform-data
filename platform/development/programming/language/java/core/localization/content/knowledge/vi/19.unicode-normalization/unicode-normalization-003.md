# Tương đương chính tắc so với tương đương tương thích trong chuẩn hóa Unicode

Trong Java, hai chuỗi có thể **trông giống nhau nhưng không có cùng dãy mã Unicode**. Chẳng hạn chữ **é** có thể được biểu diễn bởi một code point dựng sẵn **U+00E9 LATIN SMALL LETTER E WITH ACUTE**, hoặc hai code point **U+0065 LATIN SMALL LETTER E** rồi **U+0301 COMBINING ACUTE ACCENT**. Cả hai có cùng ý nghĩa ký tự theo quan hệ **tương đương chính tắc (canonical equivalence)**, nhưng **String.equals** so sánh nội dung UTF-16 nên có thể trả về **false** nếu không chuẩn hóa.

Unicode còn định nghĩa quan hệ rộng hơn là **tương đương tương thích (compatibility equivalence)**. Ví dụ ký tự số khoanh tròn **①** có thể được chuẩn hóa tương thích thành chữ số **1**, nhưng hai ký tự không tương đương chính tắc: chúng có chức năng trình bày khác nhau. Đây là khác biệt quan trọng trong tìm kiếm, làm khóa so sánh, lưu trữ, định danh và bảo toàn dữ liệu.

Bài học giải thích chính xác hai quan hệ này, các dạng chuẩn hóa **NFC, NFD, NFKC, NFKD**, cách sử dụng **java.text.Normalizer** trên Java 17+, cùng những tình huống nên và không nên dùng từng dạng. Trọng tâm là hiểu **chuẩn hóa nào giữ sự phân biệt ngữ nghĩa/kiểu chữ, chuẩn hóa nào có thể hợp nhất những ký tự vốn khác nhau**.

## 1. Unicode code point không đồng nghĩa ký tự người dùng nhìn thấy

Trước khi bàn đến tương đương, cần phân biệt một số khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Code point** | Giá trị mã Unicode, viết U+XXXX | **U+00E9**, **U+0301** |
| **UTF-16 code unit** | Đơn vị 16 bit mà **String.length()** đếm | Một code point ngoài BMP thường cần hai code unit |
| **Combining mark** | Dấu kết hợp với ký tự trước hoặc xung quanh | **U+0301** là dấu sắc kết hợp |
| **Grapheme cluster** | Cụm ký tự thường được người dùng nhận như một đơn vị | **e + U+0301** nhìn giống một chữ é |
| **Unicode normalization** | Biến đổi về một dạng mã chuẩn xác định | **NFC, NFD, NFKC, NFKD** |

Các chuỗi hiển thị giống nhau không nhất thiết có **String.length()**, số code point, số byte UTF-8 hoặc kết quả **String.equals** giống nhau.

Ví dụ:

~~~java
String precomposed = "\u00E9";  // é
String decomposed = "e\u0301"; // e + dấu sắc

System.out.println(precomposed.length()); // 1
System.out.println(decomposed.length());  // 2
System.out.println(precomposed.equals(decomposed)); // false
~~~

Đoạn trên minh họa bên trong phương thức Java. Hai cách viết có thể cho hình ảnh gần như không phân biệt bằng mắt, nhưng chuỗi thứ nhất gồm một code point BMP, chuỗi thứ hai gồm hai code point. **String.equals** không tự chuẩn hóa.

**Chú ý:** Unicode normalization không phải thuật toán đếm grapheme cluster. Một grapheme có thể gồm nhiều code point, và **String.length()** không phải số ký tự người dùng cảm nhận. Việc cắt văn bản hiển thị theo code unit có thể làm tách đôi surrogate pair hoặc dấu kết hợp.

## 2. Tương đương chính tắc là gì?

Hai chuỗi được gọi là **tương đương chính tắc (canonically equivalent)** nếu chúng biểu diễn cùng nội dung văn bản theo các quy tắc **canonical decomposition** và sắp xếp dấu kết hợp của Unicode. Chúng có thể khác cách mã hóa nhưng không khác ý nghĩa ký tự được tiêu chuẩn xem là cùng một nội dung.

Ví dụ kinh điển:

~~~text
U+00E9                    LATIN SMALL LETTER E WITH ACUTE
U+0065 U+0301             LATIN SMALL LETTER E + COMBINING ACUTE ACCENT
~~~

Cả hai biểu diễn chữ **é**. Sau chuẩn hóa **NFD**, cả hai trở thành dãy **U+0065 U+0301**. Sau chuẩn hóa **NFC**, cả hai thường trở thành dãy **U+00E9**.

Các điều quan trọng:

- **Canonical equivalence** không bắt buộc chuỗi gốc có cùng byte hay cùng code point.
- Quan hệ tương đương được định nghĩa bằng dữ liệu và quy tắc Unicode, không bằng việc so hai hình ảnh render.
- **NFD** dùng phân rã chính tắc; **NFC** dùng phân rã chính tắc rồi kết hợp lại theo quy tắc composition.
- Nếu hai chuỗi đã là tương đương chính tắc, chuẩn hóa chúng về **cùng một dạng NFC hoặc NFD** sẽ cho chuỗi có thể so sánh trực tiếp.
- Tương đương chính tắc **không** đồng nghĩa “bỏ dấu”: **é** và **e** không tương đương chính tắc, vì dấu sắc mang thông tin.

Ngoài ký tự dựng sẵn và dấu kết hợp, Unicode còn có quy tắc **canonical ordering** cho một số dấu kết hợp. Hai dãy có các dấu kết hợp khác thứ tự có thể vẫn tương đương chính tắc nếu quy tắc Unicode cho phép sắp xếp về cùng thứ tự chuẩn. Không nên tự sắp xếp mọi dấu theo code point hoặc vị trí ASCII: thứ tự chuẩn dựa trên **canonical combining class**, với các điều kiện và ngoại lệ được định nghĩa.

## 3. Tương đương tương thích là gì?

**Compatibility equivalence** là quan hệ rộng hơn. Unicode định nghĩa **compatibility decomposition** nhằm đưa về dạng chung những ký tự được mã hóa riêng vì lý do bố cục, kiểu chữ hoặc tương thích lịch sử.

Ví dụ:

| Ký tự gốc | Code point | Sau NFKC thường thành | Lý do |
| --- | --- | --- | --- |
| **①** | U+2460 CIRCLED DIGIT ONE | **1** (U+0031) | Bỏ dạng chữ số khoanh tròn |
| **ﬃ** | U+FB03 LATIN SMALL LIGATURE FFI | **ffi** | Mở rộng chữ ghép trình bày |
| **Ａ** | U+FF21 FULLWIDTH LATIN CAPITAL LETTER A | **A** | Bỏ chiều rộng fullwidth |
| **²** | U+00B2 SUPERSCRIPT TWO | **2** | Bỏ dạng chữ số mũ |
| **Ⅳ** | U+2163 ROMAN NUMERAL FOUR | **IV** | Chuyển chữ số La Mã dạng ký tự thành chữ |
| **U+00A0** | NO-BREAK SPACE | **U+0020 SPACE** | Bỏ tính chất no-break của khoảng trắng |

Các ví dụ này có thể hữu ích cho **khóa tìm kiếm** hoặc đầu vào cần giảm khác biệt kiểu trình bày, nhưng cũng chỉ ra rủi ro: **①** và **1** không luôn thay thế nhau về mặt ý nghĩa giao diện, **²** và **2** khác nhau trong công thức toán học, **Ⅳ** có thể là nhãn mục La Mã, còn **NO-BREAK SPACE** giúp điều khiển ngắt dòng.

**Compatibility equivalence không có nghĩa hai chuỗi là hai cách mã hóa hoàn toàn tương đương về mọi mục đích.** Nó chủ đích hợp nhất một số khác biệt mang tính trình bày/di sản. Một ứng dụng cần bảo tồn nguyên văn biểu thức toán, mã sản phẩm, tên thương hiệu hoặc nội dung có ý nghĩa kiểu chữ phải thận trọng trước khi áp dụng NFKC/NFKD.

**Quan hệ tập hợp:** mọi cặp tương đương chính tắc cũng được xem là tương đương tương thích; chiều ngược lại không đúng. Chẳng hạn **①** và **1** tương đương tương thích nhưng không tương đương chính tắc.

## 4. Bốn dạng chuẩn hóa Unicode: NFC, NFD, NFKC, NFKD

Unicode định nghĩa bốn normalization forms. Trong Java, chúng nằm trong **java.text.Normalizer.Form**:

| Dạng | Cơ chế chính | Tính chất |
| --- | --- | --- |
| **NFD** | Canonical Decomposition | Phân rã chính tắc, sắp xếp dấu kết hợp theo chuẩn |
| **NFC** | Canonical Decomposition rồi Canonical Composition | Kết hợp về dạng chính tắc đã composed khi có thể |
| **NFKD** | Compatibility Decomposition | Phân rã tương thích, bao gồm các phân rã chính tắc |
| **NFKC** | Compatibility Decomposition rồi Canonical Composition | Hợp nhất tương thích, sau đó kết hợp chính tắc |

**Chữ K** trong **NFKC/NFKD** là dấu phân biệt dạng **compatibility**. Đừng đoán NFKC chỉ là “NFC nhanh hơn” hoặc “NFC mạnh hơn về bảo mật”: hai dạng phục vụ mục đích so sánh khác nhau.

Mối quan hệ trên cùng ví dụ:

~~~text
Dữ liệu ban đầu: é
  NFC  -> é
  NFD  -> e + dấu sắc
  NFKC -> é
  NFKD -> e + dấu sắc

Dữ liệu ban đầu: ①
  NFC  -> ①
  NFD  -> ①
  NFKC -> 1
  NFKD -> 1

Dữ liệu ban đầu: ﬃ
  NFC  -> ﬃ
  NFD  -> ﬃ
  NFKC -> ffi
  NFKD -> ffi
~~~

**NFC không bảo đảm mọi code point có dạng dựng sẵn đều được kết hợp.** Chuẩn composition có các quy tắc và danh sách loại trừ; một số ký tự không có composed form tương ứng. **NFD không đơn giản là “tách mọi ký tự thành nhiều ký tự”**: những ký tự không có canonical decomposition có thể giữ nguyên.

### 4.1. Vì sao NFC thường được chọn khi lưu trữ văn bản?

NFC có các đặc điểm hữu ích:

- Chuẩn hóa những cách mã hóa khác nhau vốn tương đương chính tắc.
- Không cố tình hợp nhất rộng các ký tự kiểu **①**, **ﬃ**, **²** giống NFKC.
- Khi có composed form được phép, thường sử dụng biểu diễn gọn hơn cho các ký tự có dấu.
- Thuận tiện để so sánh sau khi đặt chính sách chuẩn hóa ở ranh giới dữ liệu.

Tuy vậy, **NFC không phải cam kết kích thước luôn nhỏ hơn NFD** và không xử lý mọi khác biệt cảm nhận bằng mắt. Nếu dữ liệu của hệ thống đã có hợp đồng biểu diễn khác, không nên tự chuyển mà không hiểu ảnh hưởng đến chữ ký, vị trí ký tự hoặc tương thích khách hàng.

### 4.2. Vì sao NFKC thường có ích cho khóa tìm kiếm?

NFKC có thể gom những biến thể dạng đầy đủ/thu hẹp và ký hiệu trang trí về các chuỗi chung, giúp người dùng tìm bằng **A** có thể khớp **Ａ** khi ứng dụng đặt khóa tìm kiếm tương thích.

Nhưng **NFKC làm mất một số khác biệt đã được Unicode mã hóa có chủ đích**. Vì vậy nó phù hợp hơn cho **search index**, **normalization key** hoặc dữ liệu với hợp đồng rõ ràng, thay vì thay thế không điều kiện bản gốc dùng cho hiển thị.

## 5. API Java 17+: java.text.Normalizer

Java cung cấp:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        input, Normalizer.Form.NFC);

boolean alreadyNormalized = Normalizer.isNormalized(
        input, Normalizer.Form.NFC);
~~~

Đây là đoạn minh họa cần biến **input** là một chuỗi không null. **Normalizer.normalize(CharSequence, Normalizer.Form)** trả về một **String** đã chuẩn hóa. **Normalizer.isNormalized(CharSequence, Normalizer.Form)** kiểm tra chuỗi hiện ở dạng được yêu cầu hay chưa.

Bốn giá trị enum:

~~~java
Normalizer.Form.NFC
Normalizer.Form.NFD
Normalizer.Form.NFKC
Normalizer.Form.NFKD
~~~

**Normalizer không thay đổi String gốc:** String là immutable. Mã mới nhận chuỗi kết quả riêng; không có thao tác in-place.

Một API đơn giản cho biên dữ liệu:

~~~java
public static String canonicalKey(String text) {
    if (text == null) {
        throw new IllegalArgumentException("text is null");
    }
    return Normalizer.normalize(
            text, Normalizer.Form.NFC);
}
~~~

Đoạn trên là phương thức đặt trong class Java có import **java.text.Normalizer**. Đây là ví dụ về **key so sánh chính tắc**, không phải key tìm kiếm không phân biệt hoa/thường, không phải validator tên người và cũng không phải cách đảm bảo chống giả mạo Unicode.

**Normalizer.normalize** không tự giải quyết bảo mật, không thay đổi Locale, không dịch chữ và không chuyển mọi ký tự trông giống nhau thành một mã.

## 6. Ví dụ Java 17+ đầy đủ: canonical so với compatibility

Ví dụ sau dùng các ký tự được biểu diễn bằng Unicode escape trong source để tránh nhầm encoding khi sao chép. Nó chỉ in kết quả ASCII rõ ràng cho các phép so sánh.

**File UnicodeEquivalenceDemo.java**

~~~java
import java.text.Normalizer;
import java.text.Normalizer.Form;

public class UnicodeEquivalenceDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        String circledOne = "\u2460";
        String digitOne = "1";
        String ligature = "\uFB03";
        String fullwidth = "\uFF21";

        System.out.println(
                "rawEqual=" + composed.equals(decomposed));

        System.out.println(
                "canonicalNFC=" +
                Normalizer.normalize(composed, Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed, Form.NFC)));

        System.out.println(
                "canonicalNFD=" +
                Normalizer.normalize(composed, Form.NFD)
                        .equals(Normalizer.normalize(
                                decomposed, Form.NFD)));

        System.out.println(
                "circledNFC=" +
                Normalizer.normalize(circledOne, Form.NFC)
                        .equals(digitOne));

        System.out.println(
                "circledNFKC=" +
                Normalizer.normalize(circledOne, Form.NFKC)
                        .equals(digitOne));

        System.out.println(
                "ligatureNFKC=" +
                Normalizer.normalize(ligature, Form.NFKC));

        System.out.println(
                "fullwidthNFKC=" +
                Normalizer.normalize(fullwidth, Form.NFKC));

        String once = Normalizer.normalize(
                decomposed, Form.NFC);
        String twice = Normalizer.normalize(
                once, Form.NFC);

        System.out.println(
                "idempotent=" + once.equals(twice));
    }
}
~~~

Biên dịch và chạy trong thư mục có file:

~~~bash
javac -encoding UTF-8 UnicodeEquivalenceDemo.java
java UnicodeEquivalenceDemo
~~~

Stdout:

~~~text
rawEqual=false
canonicalNFC=true
canonicalNFD=true
circledNFC=false
circledNFKC=true
ligatureNFKC=ffi
fullwidthNFKC=A
idempotent=true
~~~

**Giải thích theo từng phép thử:**

1. **rawEqual=false:** Java String.equals so sánh UTF-16, không tự chuẩn hóa.
2. **canonicalNFC=true:** cả hai cách mã hóa chữ é thành cùng NFC.
3. **canonicalNFD=true:** cả hai thành chuỗi e + dấu sắc kết hợp.
4. **circledNFC=false:** NFC không làm mất vòng tròn của chữ số **①**.
5. **circledNFKC=true:** NFKC hợp nhất **①** với **1** theo mapping tương thích.
6. **ligatureNFKC=ffi:** chữ ghép trình bày được mở rộng.
7. **fullwidthNFKC=A:** dạng fullwidth được chuyển về chữ Latin A thông thường.
8. **idempotent=true:** khi đã chuẩn hóa theo một form, chuẩn hóa tiếp theo **cùng form** không đổi nội dung.

Đây là một chương trình hoàn chỉnh có class trùng tên file và dùng API có trong Java 17. Các phép so sánh được chọn để kiểm chứng **quy tắc cốt lõi** thay vì dựa vào font hiện trên terminal.

## 7. Quan sát code point thay vì nhìn hình chữ

Khi hai chuỗi in ra giống hệt, nên xem **codePoints()**. Unicode normalization hoạt động trên chuỗi code point; quan sát code point giúp phát hiện dấu kết hợp, chữ ghép, fullwidth và các khoảng trắng đặc biệt.

**File NormalizationCodePoints.java**

~~~java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Locale;
import java.util.stream.Collectors;

public class NormalizationCodePoints {
    private static String describe(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static void show(String label, String value) {
        System.out.println(label
                + " | NFC=" + describe(
                        Normalizer.normalize(value, Form.NFC))
                + " | NFD=" + describe(
                        Normalizer.normalize(value, Form.NFD))
                + " | NFKC=" + describe(
                        Normalizer.normalize(value, Form.NFKC))
                + " | NFKD=" + describe(
                        Normalizer.normalize(value, Form.NFKD)));
    }

    public static void main(String[] args) {
        show("accent", "\u00E9");
        show("circled", "\u2460");
        show("ligature", "\uFB03");
        show("fullwidth", "\uFF21");
        show("nbsp", "\u00A0");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NormalizationCodePoints.java
java NormalizationCodePoints
~~~

Stdout:

~~~text
accent | NFC=U+00E9 | NFD=U+0065 U+0301 | NFKC=U+00E9 | NFKD=U+0065 U+0301
circled | NFC=U+2460 | NFD=U+2460 | NFKC=U+0031 | NFKD=U+0031
ligature | NFC=U+FB03 | NFD=U+FB03 | NFKC=U+0066 U+0066 U+0069 | NFKD=U+0066 U+0066 U+0069
fullwidth | NFC=U+FF21 | NFD=U+FF21 | NFKC=U+0041 | NFKD=U+0041
nbsp | NFC=U+00A0 | NFD=U+00A0 | NFKC=U+0020 | NFKD=U+0020
~~~

**Tại sao dùng codePoints thay vì chars?** Java String dùng UTF-16; **chars()** đi theo từng code unit, còn **codePoints()** kết hợp surrogate pair thành code point khi hợp lệ. Các ví dụ trong bảng đều thuộc BMP, nhưng cách viết codePoints vẫn đúng hướng cho nhiều ngôn ngữ và ký tự ngoài BMP.

**Tại sao dùng Locale.ROOT trong String.format?** Chỉ để in mã hex và nhãn kỹ thuật nhất quán, không tác động tới kết quả Normalizer. API Normalizer không lấy locale của trình duyệt hay máy chủ để quyết định canonical/compatibility decomposition.

## 8. Tương đương chính tắc: cả phân rã và thứ tự dấu kết hợp

Một cách hiểu thiếu chính xác là “canonical normalization chỉ thay mỗi chữ có dấu dựng sẵn thành chữ cơ sở + một dấu”. Thực tế, NFD gồm:

1. Phân rã các ký tự có **canonical decomposition** theo Unicode.
2. Đưa các dấu kết hợp về thứ tự chuẩn khi quy tắc **canonical combining class** cho phép.
3. Xử lý một số hệ chữ đặc biệt theo thuật toán Unicode, nổi bật là các âm tiết **Hangul**.

**NFC** tiếp tục thực hiện canonical composition theo điều kiện tiêu chuẩn cho phép.

Điều này tạo tính chất hữu ích: nếu hai chuỗi **tương đương chính tắc**, ta có thể chuẩn hóa cả hai về NFD hoặc NFC để so sánh. Nhưng không được tự viết một thuật toán “xóa dấu rồi nối lại”, vì có những dấu kết hợp, ngoại lệ composition, ký tự không có decomposition và quy tắc thứ tự không trực quan.

### 8.1. Hangul và canonical equivalence

Các âm tiết Hangul dựng sẵn trong Unicode có thể được phân rã thành các Jamo tương ứng rồi tái kết hợp theo quy tắc Unicode. Do đó, NFD/NFC không chỉ dành cho chữ Latin có dấu. Khi ứng dụng hỗ trợ tiếng Hàn, không nên coi mọi dữ liệu Hangul phải gồm đúng một code point cho mỗi âm tiết nhìn thấy.

Điều này cũng cho thấy **code point count** không phải số ký tự hiển thị. Chuẩn hóa có thể làm tăng hoặc giảm số code point mà không làm thay đổi nội dung ở cấp tương đương chính tắc.

### 8.2. Trường hợp dễ nhầm về ký hiệu Angstrom

Ký tự **U+212B ANGSTROM SIGN (Å)** có **canonical decomposition** liên quan tới **U+00C5 LATIN CAPITAL LETTER A WITH RING ABOVE (Å)**. Đây là một ví dụ đáng lưu ý: dù tên Unicode của nó trông giống “ký hiệu chuyên biệt”, không thể quyết định nó chỉ tương đương tương thích bằng cách nhìn hình thức hoặc tên.

**Phải dựa vào bảng thuộc tính và quy tắc Unicode**, không dựa trên suy đoán “có hình thức đặc biệt thì chắc là compatibility”.

Ngược lại, **U+2460 ①** có compatibility decomposition về chữ số **1**, không phải canonical decomposition; vì vậy NFC không gộp cặp này.

## 9. Khi nào hai chuỗi được xem là bằng nhau?

Có nhiều khái niệm về “bằng nhau”, không thể thay lẫn:

| Tiêu chí | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Bằng nhau theo String.equals** | Chuỗi UTF-16 có giống tuyệt đối? | é dựng sẵn khác e+dấu sắc |
| **Canonical equivalence** | Có cùng dạng NFC/NFD? | Hai cách biểu diễn é tương đương |
| **Compatibility equivalence** | Có cùng dạng NFKC/NFKD? | ① và 1 tương đương |
| **Case-insensitive** | Bỏ qua khác biệt hoa/thường theo chính sách? | A và a có thể khớp, nhưng NFKC đơn lẻ chưa làm việc này |
| **Accent-insensitive** | Bỏ qua một số dấu? | café và cafe có thể khớp trong tìm kiếm, không phải do NFC |
| **Collation** | Sắp xếp/so sánh ngôn ngữ theo quy tắc locale? | Tên có dấu có thể có thứ tự khác theo ngôn ngữ |
| **Visual similarity/confusables** | Hai chuỗi có thể trông giống nhau? | Latin a và Cyrillic а có thể giống hình |
| **Application-specific equality** | Sản phẩm có quy tắc đồng nhất riêng? | Tên đăng nhập, mã sản phẩm, khóa tìm kiếm |

**Đừng viết “NFKC biến mọi chuỗi nhìn giống nhau thành cùng một chuỗi”.** Có nhiều ký tự trông giống nhưng Unicode không coi là compatibility-equivalent; chẳng hạn **a Latin** và **а Cyrillic** (hai code point khác nhau) không bị Java Normalizer thông thường tự gộp.

**Đừng viết “NFC bỏ dấu”.** NFC giữ sự phân biệt giữa **é** và **e**; ngay cả NFD cũng giữ dấu sắc dưới dạng combining mark.

## 10. Unicode normalization không phải transliteration hay case folding

Một số nhu cầu tìm kiếm thường bị gộp chung một cách sai lầm:

- **Normalization:** chọn biểu diễn Unicode chuẩn (NFC/NFD/NFKC/NFKD).
- **Case conversion:** biến đổi chữ hoa/chữ thường theo Locale hoặc quy tắc riêng.
- **Case folding:** cơ chế Unicode cho so sánh không phân biệt case; không đồng nhất hoàn toàn với **String.toLowerCase**.
- **Transliteration:** chuyển chữ viết này sang dạng chữ viết khác, ví dụ phiên âm.
- **Diacritic removal:** bỏ một số dấu kết hợp, có thể làm mất khác biệt ngôn ngữ.
- **Collation:** so sánh/sắp thứ tự văn bản theo quy tắc ngôn ngữ.
- **Confusable detection:** phát hiện các ký tự dễ giả mạo trực quan.

**java.text.Normalizer** chỉ thực hiện phần **normalization**. Nó không tự chuyển Cyrillic sang Latin, không dịch tiếng Việt sang tiếng Anh và không xử lý toàn bộ case folding hay confusable detection.

### 10.1. Kết hợp lowercase khi sản phẩm yêu cầu

Ví dụ một key tìm kiếm không phân biệt chữ hoa/thường ở mức cơ bản:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public class SearchKey {
    public static String simpleKey(String input) {
        return Normalizer.normalize(
                input, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT);
    }
}
~~~

Đây là class tiện ích, không có main. **Locale.ROOT** giúp tránh lấy locale mặc định của JVM khi lowercase, nhưng **lowercase không tương đương đầy đủ với Unicode case folding**. Ngoài ra, thứ tự phối hợp case và normalization có thể quan trọng đối với các ký tự đặc biệt; sản phẩm cần so sánh quốc tế phức tạp phải dùng thuật toán và test phù hợp, không tự khẳng định helper trên xử lý mọi ngôn ngữ.

**Lưu ý với tiếng Thổ Nhĩ Kỳ:** các ký tự liên quan tới **I/i** có quy tắc case đặc biệt. Dùng locale người dùng hoặc Locale.ROOT tùy hợp đồng so sánh; đừng để locale của server tự quyết định.

### 10.2. Bỏ dấu là quy tắc khác

Một công thức minh họa thường gặp là chuẩn hóa NFD rồi lọc ký tự thuộc loại **Mark**. Công thức đó có thể biến **é** thành **e**, nhưng đây không còn là so sánh canonical-equivalent: nó là **biến đổi mất thông tin**.

Trong tiếng Việt, bỏ dấu có thể làm nhiều từ khác nghĩa trở thành cùng một chuỗi. Không áp dụng mặc định cho tên người, thông tin pháp lý, dữ liệu tiếng Việt nguyên bản hoặc kiểm tra định danh chính xác.

## 11. NFC và NFKC có thể tạo ra các loại va chạm khác nhau

**Collision** xảy ra khi hai chuỗi gốc khác nhau được đưa về một khóa chuẩn giống nhau.

### 11.1. Va chạm được chấp nhận về mặt chính tắc

~~~text
"é"           -> NFC -> "é"
"e\u0301"      -> NFC -> "é"
~~~

Ở cấp canonical equivalence, hai chuỗi vốn được Unicode coi là cùng nội dung. Nếu sản phẩm muốn người dùng không tạo hai tên tài khoản chỉ khác cách đặt dấu kết hợp, NFC có thể giúp đồng nhất.

Tuy nhiên, nếu hai record cũ đã tồn tại trước khi chuẩn hóa, việc thêm UNIQUE constraint lên cột NFC có thể gây trùng. Cần migration xác định dữ liệu trùng và quyết định cách giải quyết, không ghi đè tự động.

### 11.2. Va chạm thêm khi dùng compatibility

~~~text
"①"           -> NFKC -> "1"
"1"           -> NFKC -> "1"

"Ａ"          -> NFKC -> "A"
"A"           -> NFKC -> "A"
~~~

Đối với một hệ thống tìm kiếm, va chạm này có thể là điều mong muốn. Nhưng trong **mã đơn hàng**, **tên tài khoản**, **nhãn kỹ thuật** hoặc **ký hiệu toán học**, hai giá trị có thể cần được phân biệt. NFKC không phải lựa chọn mặc định an toàn cho mọi trường dữ liệu.

**Quy tắc thiết kế:** xác định loại dữ liệu, hợp đồng so sánh và mức mất thông tin cho phép trước khi chọn normalization form. Dạng chuẩn hóa là một phần của **semantics** của trường, không chỉ là bước làm sạch ký tự.

## 12. Đầu vào, lưu trữ, tìm kiếm và hiển thị nên xử lý thế nào?

Có thể phân loại như sau:

| Loại dữ liệu | Hướng tiếp cận hợp lý | Cảnh báo |
| --- | --- | --- |
| Nội dung văn bản thông thường | Cân nhắc NFC khi cần canonical consistency | Phải tôn trọng hợp đồng cũ và dữ liệu nguyên gốc |
| Tên người, địa chỉ, văn bản pháp lý | Ưu tiên bảo toàn bản gốc; có thể tạo key NFC riêng | Không làm mất dấu/ngôn ngữ |
| Search index | Có thể dùng NFKC nếu sản phẩm muốn gom biến thể compatibility | Dùng key riêng, giải thích collision |
| Username | Xác định policy chuẩn hóa, case, script, confusables | NFKC không tự đảm bảo an toàn |
| Mã sản phẩm/mã QR/định danh giao thức | Theo định nghĩa protocol; thường cần so byte chính xác | Không tự NFKC khi không được quy định |
| Mật khẩu | Theo chuẩn xử lý mật khẩu của hệ thống | Không tự thay đổi trước khi hash/so khớp nếu chính sách không xác định |
| Nội dung toán học/kỹ thuật | Giữ những phân biệt ký hiệu có ý nghĩa | NFKC có thể chuyển **²** thành **2** |
| Rich text/biểu diễn cần no-break space | Cân nhắc giữ nguyên hoặc NFC | NFKC có thể đổi NBSP thành SPACE |

Trong nhiều ứng dụng, một thiết kế hợp lý là giữ cả:

1. **originalText:** dữ liệu người dùng đã nhập, phục vụ hiển thị/chỉnh sửa.
2. **canonicalText:** nếu cần so sánh canonical, dùng NFC.
3. **searchKey:** biến đổi tương thích và case theo policy, có thể dùng NFKC và các bước đã được thiết kế riêng.

Các trường này không được tùy tiện đồng nhất. **Search key không phải nội dung gốc**, và việc thay đổi quy tắc key có thể làm thay đổi kết quả truy vấn hoặc gây trùng unique index.

## 13. Ví dụ thiết kế lưu original và canonical key

Một record Java có thể lưu cả bản gốc và bản chuẩn hóa:

~~~java
import java.text.Normalizer;

public record LocalizedLabel(
        String originalText,
        String canonicalText) {

    public static LocalizedLabel from(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input is null");
        }
        return new LocalizedLabel(
                input,
                Normalizer.normalize(
                        input, Normalizer.Form.NFC));
    }
}
~~~

Đây là một record Java 17 hợp lệ và không có main. Nó giữ nguyên văn bản đã nhận cùng một biến thể NFC để so sánh theo quan hệ chính tắc. Việc tạo searchKey NFKC nên là phương thức riêng theo hợp đồng sản phẩm, không tự thay thế **originalText**.

Ví dụ một hệ thống có hai tên nhãn nhập như nhau về mặt hiển thị nhưng khác cách mã hóa:

~~~text
Original #1: U+00E9
Original #2: U+0065 U+0301
Canonical #1: U+00E9
Canonical #2: U+00E9
~~~

Hai bản gốc vẫn có thể được giữ để audit hoặc xuất lại đúng dữ liệu, trong khi unique key canonical có thể phát hiện trùng.

Nếu đã có dữ liệu lịch sử, chạy migration ở chế độ chỉ đọc để **thống kê va chạm trước** khi áp dụng constraint/ghi lại nội dung. Không tự hợp nhất hai tài khoản hoặc hai hồ sơ chỉ vì NFKC tạo cùng một key: có thể ảnh hưởng quyền truy cập và dữ liệu nghiệp vụ.

## 14. Idempotence: chuẩn hóa cùng form hai lần không đổi kết quả

Một thuộc tính cơ bản:

~~~text
normalize(normalize(s, NFC), NFC)   = normalize(s, NFC)
normalize(normalize(s, NFD), NFD)   = normalize(s, NFD)
normalize(normalize(s, NFKC), NFKC) = normalize(s, NFKC)
normalize(normalize(s, NFKD), NFKD) = normalize(s, NFKD)
~~~

Trong code:

~~~java
String once = Normalizer.normalize(
        text, Normalizer.Form.NFC);
String twice = Normalizer.normalize(
        once, Normalizer.Form.NFC);

assert once.equals(twice);
~~~

Đoạn minh họa nằm trong một phương thức, có import Normalizer và biến text. Thuộc tính idempotence giúp test pipeline: dữ liệu đã lưu ở NFC không nên tự thay đổi sau nhiều lượt chuẩn hóa NFC.

**Nhưng không nên kết luận rằng trộn các form luôn cho kết quả giống nhau.** NFKC có thể làm mất phân biệt compatibility trong khi NFC giữ chúng; một lần chuyển sang NFKC rồi quay về NFC không thể khôi phục **①** từ **1**.

### 14.1. isNormalized không có nghĩa “text sạch”

**Normalizer.isNormalized(s, NFC) == true** chỉ nói rằng s đang ở NFC. Nó không xác nhận:

- Người dùng không nhập ký tự giả mạo tương tự hình chữ.
- Chuỗi không chứa control characters không mong muốn.
- Chuỗi đúng ngôn ngữ hay đúng định dạng email.
- Không có homoglyph khác script.
- Không có ký tự zero-width hoặc bidi ngoài chính sách.
- Chuỗi an toàn làm tên file hoặc tên tài khoản.

Đây là một phép kiểm tra chuẩn hóa, không phải validator bảo mật hay nghiệp vụ tổng quát.

## 15. Chuẩn hóa và phân tách chuỗi trong Java

Java String lưu UTF-16. Sau chuẩn hóa:

- **length()** có thể tăng hoặc giảm.
- **codePointCount(...)** có thể thay đổi.
- **getBytes(StandardCharsets.UTF_8).length** có thể thay đổi.
- **substring** hoặc index đã lưu ở vị trí ký tự cũ có thể không còn trỏ vào cùng vị trí.
- Cursor, highlight và offset trong editor có thể cần mapping lại nếu phải hiển thị bản đã chuẩn hóa.

Ví dụ **é** dạng dựng sẵn là một code point, còn NFD thành hai code point; điều đó ảnh hưởng chỉ số. Một ứng dụng dùng offsets để đánh dấu kết quả tìm kiếm trong nguyên bản không nên áp trực tiếp offsets từ searchKey NFKC lên originalText mà không có mapping.

**Cẩn thận với text segmentation:** chữ có dấu không phải chuỗi “một code point bằng một ký tự người dùng”. Để cắt theo ký tự hiển thị cần giải pháp xử lý grapheme cluster phù hợp; **String.codePoints()** chỉ đi theo code point chứ không gom toàn bộ các dấu kết hợp thành một cụm.

## 16. Chuẩn hóa có ảnh hưởng tới chữ ký, hash và giao thức không?

Có. Mã hóa UTF-8 của **é** dựng sẵn và **e + dấu sắc** khác nhau. Do đó:

~~~text
SHA-256(UTF-8(original-1)) != SHA-256(UTF-8(original-2))
~~~

Hai chuỗi tương đương chính tắc vẫn có thể tạo hash khác vì **hash nhận byte đầu vào**, không biết Unicode equivalence. Nếu giao thức yêu cầu cả hai cách biểu diễn được coi là giống nhau, **phải quy định chuẩn hóa và encoding trước hash/signature** ở tất cả các bên tham gia.

Ngược lại, nếu protocol định nghĩa chữ ký dựa trên **byte gốc**, tự chuẩn hóa trước khi xác thực chữ ký có thể làm kết quả sai hoặc tạo bất đồng giữa client/server. Không đổi normalization form trong hệ thống chữ ký đã triển khai mà không có phiên bản hợp đồng.

Với mật khẩu, tự ý áp NFKC/NFC trước khi hash khi trước đây không làm vậy có thể khiến người dùng không đăng nhập được. Thay đổi bất kỳ cách xử lý mật khẩu Unicode nào phải đi theo thiết kế/chuẩn được hệ thống áp dụng và kế hoạch chuyển đổi an toàn, không coi đó là một bước “làm sạch” không cần thảo luận.

## 17. Chuẩn hóa và Unicode security: đừng nhầm mục tiêu

Unicode security không thể giải quyết chỉ bằng NFC hoặc NFKC.

### 17.1. Homoglyph / confusables

Một chữ **a** Latin và một chữ **а** Cyrillic có hình dạng dễ giống nhau ở nhiều font nhưng là hai code point thuộc hai hệ chữ. NFKC không mặc định chuyển mọi Cyrillic sang Latin. Nếu tên người dùng hoặc domain cần phòng chống giả mạo bằng chữ tương tự, phải xem xét **script restrictions**, phát hiện **confusable** và các quy tắc riêng của tiêu chuẩn định danh phù hợp.

### 17.2. Bidi và ký tự vô hình

Chuỗi có thể chứa dấu điều hướng bidirectional, zero-width joiners hoặc non-joiners. Normalizer không phải công cụ “xóa toàn bộ ký tự vô hình”; một số ký tự giữ nguyên vì có chức năng ngôn ngữ.

Nếu ứng dụng phục vụ các hệ chữ như Ả Rập, một hành động lọc bừa có thể làm hỏng văn bản. Hãy xác định miền dữ liệu (username, chat, mã kỹ thuật) trước khi áp quy tắc control/default-ignorable characters.

### 17.3. Unicode normalization không thay thế escaping

Trước khi đưa văn bản lên HTML, SQL, URL hay shell, phải dùng biện pháp escape/binding phù hợp. Normalizer không ngăn XSS, SQL injection hoặc path traversal. Không dùng **NFKC** như một “bộ lọc bảo mật” duy nhất.

### 17.4. Thứ tự validate và normalize

Với định danh có chính sách nghiêm ngặt, thứ tự các bước có thể thay đổi kết quả. Ví dụ nếu validate trước, một chuỗi chứa ký tự fullwidth có thể không qua regex ASCII; nếu NFKC trước, nó có thể thành ASCII và vượt qua. Đây là **quyết định của giao thức**, không phải cách nào luôn đúng.

Một pipeline phải nêu rõ: nhận dữ liệu → chọn normalization form → validate ký tự/độ dài/giới hạn → so unique key → lưu. Đồng thời kiểm tra dữ liệu gốc và các hậu quả của việc normalization thay đổi nội dung. Nếu không rõ chính sách, tốt hơn là giữ nguyên và chặn những dạng đầu vào ngoài hợp đồng.

## 18. Normalization và cơ sở dữ liệu

Ứng dụng Java có thể dùng NFC cho key, nhưng database có thể:

- So sánh byte hoặc dùng một collation riêng.
- Có collation case-insensitive/accent-insensitive không trùng thuật toán Java.
- Có index unique dựa trên dạng bình thường hóa/biến đổi khác.
- Có dữ liệu cũ chưa qua chuẩn hóa.

Không nên suy rằng **NFKC trong Java** tương đương hoàn toàn với **LOWER**, **UNACCENT** hoặc một collation database cụ thể. Các thuật toán có phạm vi khác nhau.

Một thiết kế thực tế:

~~~text
Người dùng gửi text
       |
       v
Kiểm tra hợp đồng đầu vào
       |
       +------> Lưu originalText
       |
       v
Tạo canonicalKey (NFC) theo policy
       |
       +------> Unique index nếu mục đích là canonical equality
       |
       v
Tạo searchKey (NFKC/case/... theo policy)
       |
       +------> Search index, không thay originalText
~~~

Khi thay đổi version chuẩn hóa hoặc policy, thực hiện backfill kiểm soát và **kiểm tra collision trước**. Không gộp record chỉ dựa trên key đã làm mất thông tin nếu không có quy tắc nghiệp vụ.

## 19. Khi nào nên dùng NFC, NFD, NFKC, NFKD?

### Chọn NFC nếu

- Cần so sánh các cách mã hóa tương đương chính tắc.
- Muốn nhất quán dữ liệu văn bản mà vẫn giữ khác biệt compatibility.
- Muốn tạo canonical key cho tên, nhãn hoặc một số nội dung Unicode.
- Giao thức/ứng dụng của bạn định nghĩa NFC làm dạng lưu hoặc trao đổi.

### Chọn NFD nếu

- Cần kiểm tra dấu kết hợp hoặc thành phần phân rã để thực hiện xử lý văn bản chuyên biệt.
- Công cụ downstream cần canonical decomposed form.
- Bạn hiểu việc tăng số code point và những ảnh hưởng tới offsets/hiển thị.

**NFD không phải lệnh bỏ dấu**; nó giữ dấu dưới dạng combining mark. Nếu một pipeline sau đó xóa marks, đó là một bước mất thông tin riêng.

### Chọn NFKC nếu

- Cần giảm khác biệt giữa fullwidth và chữ Latin thường, chữ số khoanh tròn và số bình thường, một số ligature và chuỗi mở rộng.
- Có policy rõ rằng những dạng compatibility được coi là tương đương.
- Bạn đang tạo searchKey/identifier profile mà tiêu chuẩn của nó yêu cầu dạng này.

**Không chọn NFKC chỉ vì “chữ nhìn giống nhau” hoặc “chuẩn mạnh nhất”.** Nó có thể làm mất ý nghĩa của ký hiệu toán, typography và khoảng trắng no-break.

### Chọn NFKD nếu

- Cần phân rã compatibility thành các thành phần để xử lý/tra cứu tiếp.
- Có thuật toán downstream cần compatibility decomposition thay vì composed form.
- Bạn đã xác định rõ việc giữ hoặc bỏ các dấu kết hợp sau phân rã.

**NFKD cũng giữ dấu kết hợp**, không tự bỏ chúng. Nó không phải transliteration hoặc ASCII conversion tổng quát.

## 20. Những lỗi phổ biến khi học và áp dụng normalization

### Lỗi 1 – Cho rằng Unicode trông giống thì equals phải true

Hai dãy **é** dựng sẵn và **e + dấu sắc** có thể trông giống nhưng String.equals trả false. Chuẩn hóa cả hai theo NFC/NFD trước khi so canonical-equivalence.

### Lỗi 2 – Nhầm NFC với NFKC

NFC không chuyển **①** thành **1**; NFKC có thể làm điều đó. Nếu dùng nhầm NFKC cho dữ liệu cần bảo toàn ký hiệu, bạn có thể làm thay đổi nội dung.

### Lỗi 3 – Tưởng compatibility luôn có nghĩa “hoàn toàn tương đương”

**²** và **2** liên quan qua compatibility decomposition nhưng không mang nghĩa trình bày giống nhau trong toán học. Tương đương tương thích không phải quyền tự động thay mọi bản gốc.

### Lỗi 4 – Tưởng chuẩn hóa sẽ xóa dấu

NFC và NFD đều phân biệt **café** với **cafe**. NFD chỉ có thể tách dấu ra code point riêng; xóa dấu là một thuật toán khác có thể gây mất thông tin.

### Lỗi 5 – Dùng NFKC để chống mọi homoglyph

Latin và Cyrillic có thể có các ký tự nhìn giống nhau nhưng không compatibility-equivalent. Cần chính sách script/confusable riêng cho định danh an toàn.

### Lỗi 6 – Dùng toLowerCase mặc định JVM

Nếu cần lowercase key, không nên lấy Locale ngẫu nhiên của môi trường. Chọn Locale.ROOT hoặc locale nghiệp vụ; vẫn nhớ lowercase chưa phải Unicode full casefold.

### Lỗi 7 – Chuẩn hóa tại một dịch vụ nhưng không tại dịch vụ khác

Hai hệ thống so key theo hai chính sách khác nhau có thể chấp nhận trùng hoặc không tìm được dữ liệu. Chuẩn hóa là một phần của hợp đồng dữ liệu, phải áp dụng nhất quán ở mọi biên.

### Lỗi 8 – Xóa bản gốc sau khi tạo searchKey

NFKC có thể biến đổi chi tiết kiểu chữ; không phải lúc nào có thể khôi phục. Giữ bản gốc khi ứng dụng cần render đúng nội dung người dùng.

### Lỗi 9 – Lấy length trước khi normalize rồi dùng offset sau

Độ dài UTF-16 và code-point count có thể đổi sau NFC/NFD/NFKC/NFKD. Offset trên bản gốc và bản chuẩn hóa có thể khác. Phải theo dõi mapping nếu highlight kết quả.

### Lỗi 10 – Không kiểm tra trùng trước khi thêm UNIQUE constraint

Chuỗi gốc khác nhau có thể đổ về cùng canonical/search key. Migrate dữ liệu có kiểm soát, thống kê collision và xử lý trước khi bật ràng buộc.

### Lỗi 11 – Chuẩn hóa byte tùy ý mà không biết encoding

Unicode normalization hoạt động trên chuỗi ký tự/code point. Trước tiên phải decode bytes theo encoding được định nghĩa, thường UTF-8. Chuẩn hóa không tự phát hiện UTF-8, UTF-16 hay sửa mọi bytes hỏng.

### Lỗi 12 – Trộn normalization với xử lý XSS/SQL

Normalizer không escape HTML, không parameterize SQL và không validate quyền truy cập. Cần công cụ đúng cho từng lớp bảo mật.

## 21. Ma trận kiểm thử khuyến nghị

| Input A | Input B | Bằng nhau nguyên bản? | Bằng nhau sau NFC? | Bằng nhau sau NFKC? |
| --- | --- | --- | --- | --- |
| **é** U+00E9 | **e + U+0301** | Không | Có | Có |
| **①** | **1** | Không | Không | Có |
| **ﬃ** | **ffi** | Không | Không | Có |
| **Ａ** | **A** | Không | Không | Có |
| **²** | **2** | Không | Không | Có |
| **NBSP U+00A0** | **SPACE U+0020** | Không | Không | Có |
| **é** | **e** | Không | Không | Không |
| **A** | **a** | Không | Không | Không |
| **Latin a** | **Cyrillic а** | Không | Không | Không |

Bảng trên minh họa những cặp tiêu biểu; nó không có nghĩa NFKC phù hợp làm chính sách so sánh cho mọi trường dữ liệu.

Ngoài các cặp trên, cần kiểm tra:

1. **Idempotence:** normalize hai lần cùng form cho cùng kết quả.
2. **Canonical ordering:** những dãy dấu kết hợp đã được Unicode định nghĩa tương đương vẫn cho cùng NFC/NFD.
3. **Hangul:** phân rã/tái kết hợp chính tắc.
4. **Dữ liệu ngoài BMP:** không cắt surrogate pair.
5. **NBSP và các ký tự định dạng:** không làm mất khoảng trắng có ý nghĩa khi bảo toàn nội dung.
6. **Thay đổi version JDK/Unicode:** hợp đồng ứng dụng được giữ như mong muốn.
7. **Collision dữ liệu hiện hữu:** những key mới không ghi đè record cũ.
8. **Case và accent:** phân biệt rõ normalization với lowercase/diacritic removal.
9. **Confusables khác script:** không giả định Normalizer xử lý.
10. **Đầu vào null, rỗng, dài:** xử lý theo chính sách an toàn, tránh tiêu tốn tài nguyên không cần thiết.

### 21.1. Một phép kiểm thử property-based đơn giản

Với bất kỳ chuỗi **s** hợp lệ theo hợp đồng:

~~~java
String nfc = Normalizer.normalize(
        s, Normalizer.Form.NFC);

if (!nfc.equals(Normalizer.normalize(
        nfc, Normalizer.Form.NFC))) {
    throw new AssertionError("NFC is not idempotent");
}
~~~

Đoạn minh họa nằm trong phương thức và cần import Normalizer, biến s. Trong test, thêm nhiều bộ ký tự của các ngôn ngữ thực tế. Không nên chỉ test văn bản ASCII, vì ASCII thường không phơi bày những vấn đề về combining marks hoặc compatibility.

## 22. Quy trình ra quyết định cho một trường Unicode

Nếu đang thiết kế một trường văn bản trong ứng dụng:

**Bước 1:** Xác định cần **giữ nguyên bản gốc** hay có quyền hợp nhất biểu diễn.

**Bước 2:** Nếu chỉ muốn coi hai cách mã hóa canonical là giống nhau, cân nhắc **NFC**.

**Bước 3:** Nếu muốn bỏ khác biệt kiểu trình bày như fullwidth, circled digits, ligatures, cân nhắc **NFKC** nhưng đánh giá mất thông tin và collision.

**Bước 4:** Nếu yêu cầu không phân biệt hoa/thường, xử lý case theo hợp đồng **riêng**; đừng xem NFKC là casefold.

**Bước 5:** Nếu yêu cầu tìm không dấu, xác định chính xác ngôn ngữ và mức mất thông tin; **không áp một thuật toán xóa dấu mặc định cho dữ liệu gốc**.

**Bước 6:** Nếu trường là identifier hoặc có liên quan bảo mật, xem xét script, confusables, giới hạn ký tự, độ dài sau normalization và quy tắc chuẩn được hệ thống áp dụng.

**Bước 7:** Kiểm tra dữ liệu cũ trước khi chuyển policy; tính trước collision và tác động đến unique indexes.

**Bước 8:** Tạo test cho canonical pair, compatibility pair, emoji/combining sequences, whitespace, case và dữ liệu ngôn ngữ thực tế.

**Bước 9:** Ghi rõ normalization form trong hợp đồng API hoặc tài liệu dữ liệu để các hệ thống khác không tự chọn một form khác.

## 23. Câu hỏi tự đánh giá

1. Vì sao hai chuỗi **é** và **e + dấu sắc** có thể khác **String.equals** nhưng vẫn tương đương chính tắc?
2. Vì sao **①** và **1** chỉ được hợp nhất khi dùng NFKC/NFKD, không phải NFC/NFD?
3. Nếu ứng dụng lưu nội dung toán học có **²**, có nên luôn NFKC toàn bộ văn bản không? Vì sao?
4. Nếu đã NFD, dấu sắc có tự biến mất không?
5. NFKC có tự làm **A** và **a** bằng nhau không? Có biến Cyrillic а thành Latin a không?
6. Khi dùng NFC để tạo unique key, hệ thống cần làm gì với các record lịch sử vốn khác mã Unicode nhưng cùng canonical form?
7. Khi tạo searchKey NFKC, có nên xóa originalText không?
8. Khi tính hash hoặc chữ ký, vì sao quy định normalization và encoding phải xuất hiện trong giao thức?
9. Khi chuẩn hóa làm thay đổi số code point, điều gì xảy ra nếu UI vẫn dùng offset của bản gốc?
10. Trong Java 17, API nào kiểm tra một chuỗi đã nằm ở NFC và API nào chuyển nó về NFC?

**Gợi ý:** (1) Hai mã Unicode khác nhau, String.equals không chuẩn hóa; (2) circled digit có compatibility decomposition; (3) không, sẽ mất phân biệt dạng mũ; (4) không; (5) không; (6) phát hiện collision/migration; (7) không nếu cần bảo toàn; (8) byte khác có hash khác; (9) cần mapping vị trí; (10) **Normalizer.isNormalized** và **Normalizer.normalize**.

## 24. Checklist áp dụng thực tế

- [ ] Đã phân biệt **canonical equivalence** với **compatibility equivalence**.
- [ ] Đã xác định **NFC/NFD/NFKC/NFKD** theo mục đích sử dụng, không theo suy đoán “mạnh hơn”.
- [ ] Đã hiểu **String.equals** so sánh biểu diễn UTF-16 thô.
- [ ] Đã giữ nguyên dấu/combining marks nếu nội dung cần bảo toàn.
- [ ] Đã biết NFKC có thể chuyển **① → 1**, **ﬃ → ffi**, **Ａ → A**, **NBSP → SPACE**.
- [ ] Đã tách normalization khỏi case folding, bỏ dấu, transliteration, collation và confusable detection.
- [ ] Đã chọn rõ có giữ **originalText** và tạo **searchKey/canonicalKey** riêng hay không.
- [ ] Đã thiết kế xử lý collision và migration dữ liệu cũ.
- [ ] Đã tránh làm thay đổi byte của thông điệp được ký hoặc dữ liệu mật khẩu khi protocol không quy định.
- [ ] Đã kiểm thử dấu kết hợp, fullwidth, ligature, circled digits, whitespace và chuỗi nhiều hệ chữ.
- [ ] Đã quan sát **codePoints()** khi chuỗi trông giống nhưng kết quả equals khác.
- [ ] Đã tính đến offsets/length UTF-16 thay đổi sau normalization.
- [ ] Đã kiểm thử trên những phiên bản JDK mục tiêu nếu cần nhất quán qua nâng cấp.
- [ ] Đã áp dụng một normalization policy thống nhất tại các ranh giới dữ liệu.

## 25. Kết luận

**Tương đương chính tắc** nói về những cách mã hóa khác nhau của cùng nội dung ký tự theo Unicode; **NFC/NFD** đưa chúng về cùng biểu diễn để so sánh hoặc xử lý. **Tương đương tương thích** cho phép hợp nhất thêm nhiều biến thể mang tính trình bày/lịch sử như **①** với **1**, **ﬃ** với **ffi**, **Ａ** với **A**; **NFKC/NFKD** thực hiện việc đó, đôi khi mất sự phân biệt cần thiết.

Trong Java 17+, **java.text.Normalizer** cung cấp các phép chuẩn hóa và kiểm tra dạng chuẩn. Chọn **NFC** khi cần nhất quán tương đương chính tắc và bảo toàn khác biệt compatibility; chọn **NFKC** khi có chính sách rõ rằng những biến thể tương thích phải chung khóa. Luôn tách **chuỗi gốc** khỏi **khóa tra cứu/so sánh** khi dữ liệu có giá trị hiển thị hoặc nghiệp vụ. Không nhầm Unicode normalization với bỏ dấu, lowercase, transliteration, phát hiện ký tự giả mạo hoặc validation bảo mật.
