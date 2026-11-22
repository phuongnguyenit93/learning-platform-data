# Collator trong Java: các mức PRIMARY, SECONDARY, TERTIARY và IDENTICAL

## 1. Vấn đề: “bằng nhau” và “đứng trước” phụ thuộc ngôn ngữ

Khi xử lý dữ liệu đa ngôn ngữ, việc sắp xếp tên người, danh mục, sản phẩm hoặc kết quả tìm kiếm không thể luôn dựa vào thứ tự mã ký tự. Ví dụ các chuỗi sau có thể được người dùng xem là gần nhau nhưng có những khác biệt thực sự:

- `cafe` và `café`: khác dấu.
- `cafe` và `Cafe`: khác chữ hoa/thường.
- `café` viết bằng ký tự dựng sẵn `\u00E9` và `cafe\u0301` dùng `e` cùng dấu kết hợp: có thể giống về hình thức và tương đương chuẩn tắc Unicode.
- `A` và chữ Latin full-width `Ａ`: khác biểu diễn tương thích, không phải mặc nhiên có cùng identity.

`String.compareTo()`, `String.equals()` và `String.equalsIgnoreCase()` không được thiết kế để diễn đạt đầy đủ các quy tắc thứ tự từ vựng của mọi ngôn ngữ. Java cung cấp **`java.text.Collator`** cho phép so sánh chuỗi theo `Locale`, đồng thời điều chỉnh **mức độ phân biệt** bằng `setStrength(int)`.

Bốn mức cơ bản là:

```java
Collator.PRIMARY
Collator.SECONDARY
Collator.TERTIARY
Collator.IDENTICAL
```

Vì vậy, thay vì hỏi một cách chung chung “hai chuỗi này có bằng nhau không?”, hệ thống cần xác định: **bằng nhau theo mức độ phân biệt nào, theo quy tắc locale nào, và dùng cho tìm kiếm, sắp xếp hay định danh dữ liệu?**

Đây là một bài về **so sánh theo ngôn ngữ (collation)**. Nó không thay thế toàn bộ Unicode normalization, full-text search hay quy tắc tạo khóa định danh.

## 2. Collator là gì và được tạo như thế nào?

`Collator` là lớp trừu tượng cho việc so sánh chuỗi có tính đến ngôn ngữ. Cách tạo thường dùng:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(Locale.US);
```

Sau khi có đối tượng, dùng:

```java
int result = collator.compare(left, right);
```

Ý nghĩa trả về:

| Giá trị trả về | Ý nghĩa |
|---|---|
| Số âm | `left` đứng trước `right` theo collator |
| `0` | Hai chuỗi được coi tương đương theo cấu hình collator |
| Số dương | `left` đứng sau `right` theo collator |

**Không giả định kết quả đúng bằng `-1` hoặc `1`.** Điều đúng theo hợp đồng `Comparator` là so dấu âm, bằng 0 hay dương. Có thể sử dụng `Integer.signum(result)` khi chỉ cần dấu.

Ví dụ:

```java
if (collator.compare(a, b) == 0) {
    // Tương đương theo locale, strength và decomposition đã cấu hình.
}
```

Điều kiện này **không đồng nghĩa** với `a.equals(b)`. Hai chuỗi khác nhau về ký tự có thể có `collator.compare(a,b)==0`, đặc biệt ở `PRIMARY`.

Khi cần sắp xếp danh sách, có thể dùng `List.sort(collator)` vì `Collator` triển khai `Comparator<Object>` và nhận các đối tượng `String` trong `compare`. Với mã ứng dụng kiểu hóa rõ hơn, có thể dùng lambda `(a,b) -> collator.compare(a,b)` cho `List<String>`.

## 3. Strength quyết định những khác biệt nào có ý nghĩa

`Collator.setStrength(...)` chọn một **mức độ nhạy**. Các mức tương ứng với những lớp khác biệt trong phép đối chiếu ngôn ngữ: mức sau thông thường xem xét thêm những khác biệt mà mức trước bỏ qua.

### PRIMARY: khác biệt cơ bản của chữ

`PRIMARY` tập trung vào khác biệt *primary* theo collation rules. Trong nhiều locale, mức này có thể coi chuỗi khác dấu hoặc khác hoa/thường là tương đương:

```text
cafe ~ café
cafe ~ Cafe
```

Trong ví dụ với `Locale.US` trên Java 17, cả hai cặp trả về `0` ở `PRIMARY`.

**Không có quy tắc toàn cầu rằng PRIMARY luôn bỏ mọi dấu cho mọi ngôn ngữ.** Một khác biệt được xem là primary hay secondary còn phụ thuộc bảng collation của locale và phiên bản dữ liệu. Một số chữ được coi là chữ riêng biệt trong ngôn ngữ có thể không tương đương ở `PRIMARY`.

Ứng dụng: sắp xếp hoặc so khớp **ít phân biệt** trong một ngữ cảnh ngôn ngữ đã xác định.

### SECONDARY: thêm khác biệt thứ cấp, thường gồm dấu

`SECONDARY` xét thêm các khác biệt secondary, thường là dấu phụ (*accents/diacritics*):

```text
cafe != café
cafe ~ Cafe
```

Trong ví dụ US, dấu sắc làm hai chuỗi không còn tương đương; khác biệt viết hoa thường vẫn chưa làm chúng khác nhau.

Ứng dụng: yêu cầu phân biệt dấu nhưng không nhất thiết coi chữ hoa và chữ thường là hai từ khác nhau.

### TERTIARY: thêm khác biệt cấp ba, thường gồm hoa/thường

`TERTIARY` xét thêm khác biệt tertiary; trong nhiều ngôn ngữ, đây là cấp liên quan đến **case** hoặc một số biến thể trình bày:

```text
cafe != café
cafe != Cafe
```

Với ví dụ US, cả hai khác biệt này đều được coi là có ý nghĩa. `TERTIARY` cũng là mức mặc định thường gặp của các collator trong JDK, nhưng ứng dụng nên **đặt mức rõ ràng** thay vì ngầm phụ thuộc default.

Đừng hiểu rằng mức này **luôn trùng với `String.equals()`**. Collation vẫn áp dụng quy tắc ngôn ngữ, normalization/decomposition và cách xử lý các thành phần khác nhau của văn bản.

### IDENTICAL: phân biệt cao nhất theo Collator

`IDENTICAL` xét những khác biệt còn lại sau khi các mức thấp hơn không phân biệt được. Nó hữu ích khi muốn một mức so sánh gần với biểu diễn ký tự hơn, nhưng vẫn nằm trong cơ chế Collator.

**Điểm đặc biệt:** kết quả `IDENTICAL` còn chịu ảnh hưởng bởi **decomposition**. Ví dụ `café` dạng dựng sẵn và dạng chữ `e` + dấu kết hợp có thể:

- So sánh **khác nhau** ở `IDENTICAL` khi `NO_DECOMPOSITION`.
- So sánh **bằng nhau** ở `IDENTICAL` khi bật `CANONICAL_DECOMPOSITION`, vì hai biểu diễn tương đương chuẩn tắc được xử lý nhất quán.

Do đó, không nên nói rằng “IDENTICAL luôn là String.equals” hoặc “IDENTICAL luôn phân biệt mọi chuỗi Unicode có byte khác nhau”. Nếu nghiệp vụ yêu cầu **khớp chính xác nội dung String**, hãy sử dụng `String.equals()`; nếu yêu cầu **khớp byte**, cần so chính byte của encoding/giao thức đã chọn.

## 4. Bảng ý nghĩa và phạm vi sử dụng

| Strength | Các khác biệt thường bắt đầu được phân biệt | Trường hợp điển hình | Cần cảnh giác |
|---|---|---|---|
| `PRIMARY` | Khác biệt chữ cơ bản theo ngôn ngữ | Sắp xếp/matching tương đối linh hoạt | Có thể gộp nhiều chuỗi khác nhau |
| `SECONDARY` | Thêm khác biệt dấu phụ | Muốn phân biệt `e`/`é` nhưng có thể bỏ qua case | Dấu không được phân cấp giống nhau ở mọi locale |
| `TERTIARY` | Thêm hoa/thường và biến thể cấp ba | Sắp xếp hiển thị có độ phân biệt cao | Không đồng nghĩa `String.equals` |
| `IDENTICAL` | Thêm các khác biệt còn lại theo cơ chế Collator | Tie-break/collation ở độ nhạy cao | Phụ thuộc decomposition; không thay thế byte equality |

Khi từ `PRIMARY` lên `IDENTICAL`, mức phân biệt được tăng lên, nhưng **quy tắc cụ thể của từng locale** mới quyết định cặp nào có kết quả bằng 0. Không nên tự viết một bảng “dấu luôn là secondary” cho mọi ngôn ngữ trên thế giới.

## 5. Chương trình Java 17+ kiểm chứng cả bốn mức

Tạo tệp `CollationStrengthDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class CollationStrengthDemo {
    public static void main(String[] args) {
        Collator collator =
                Collator.getInstance(Locale.US);

        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        String plain = "cafe";
        String accented = "caf\u00E9";
        String upper = "Cafe";
        String decomposed = "cafe\u0301";

        int[] strengths = {
                Collator.PRIMARY,
                Collator.SECONDARY,
                Collator.TERTIARY,
                Collator.IDENTICAL
        };

        String[] labels = {
                "PRIMARY",
                "SECONDARY",
                "TERTIARY",
                "IDENTICAL"
        };

        for (int i = 0; i < strengths.length; i++) {
            collator.setStrength(strengths[i]);

            boolean sameAccent =
                    collator.compare(plain, accented) == 0;
            boolean sameCase =
                    collator.compare(plain, upper) == 0;
            boolean sameCanonical =
                    collator.compare(accented, decomposed) == 0;

            System.out.printf(
                    "%s accent=%s case=%s canonical=%s%n",
                    labels[i],
                    sameAccent,
                    sameCase,
                    sameCanonical);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac CollationStrengthDemo.java
java CollationStrengthDemo
```

Kết quả đã kiểm chứng bằng JDK cho `Locale.US`:

```text
PRIMARY accent=true case=true canonical=true
SECONDARY accent=false case=true canonical=true
TERTIARY accent=false case=false canonical=true
IDENTICAL accent=false case=false canonical=true
```

Ở đây:

- `accent` so sánh `cafe` với `café` dựng sẵn.
- `case` so sánh `cafe` với `Cafe`.
- `canonical` so sánh `café` dựng sẵn với `cafe` + dấu sắc kết hợp.
- `CANONICAL_DECOMPOSITION` được đặt tường minh, nên cặp tương đương chuẩn tắc vẫn so sánh bằng nhau cả ở `IDENTICAL` trong ví dụ.

**Đọc bảng theo từng cột**, không xem `true` là “hai chuỗi hoàn toàn giống nhau”: đó chỉ là “Collator không phân biệt cặp đó với cấu hình đang xét”.

Khi ứng dụng dùng locale khác hoặc runtime khác, cần kiểm chứng quy tắc với bộ dữ liệu thực tế. Các mức có ý nghĩa khái quát ổn định, nhưng cách phân cấp từng ký tự là trách nhiệm của dữ liệu collation theo locale.

## 6. Strength và decomposition là hai cấu hình độc lập

`setStrength` trả lời câu hỏi: **những mức khác biệt nào được xét?**

`setDecomposition` trả lời câu hỏi: **trước khi đối chiếu, parser collation xử lý các dạng tổ hợp Unicode ở mức nào?**

Java có ba lựa chọn:

| Decomposition mode | Ý nghĩa |
|---|---|
| `Collator.NO_DECOMPOSITION` | Không thực hiện decomposition trước so sánh |
| `Collator.CANONICAL_DECOMPOSITION` | Xử lý canonical decomposition |
| `Collator.FULL_DECOMPOSITION` | Xử lý cả compatibility decomposition |

Ví dụ Unicode:

```text
U+00E9       -> é (ký tự dựng sẵn)
U+0065 U+0301 -> e + combining acute (ký tự tổ hợp)
```

Hai biểu diễn này có thể về cùng dạng khi dùng canonical decomposition. Với `FULL_DECOMPOSITION`, hệ thống còn có thể đồng nhất một số biểu diễn tương thích như chữ full-width và dạng ASCII tương ứng, tùy các quy tắc collation.

**Không được đồng nhất “IDENTICAL” với “không phân rã”.** `IDENTICAL` là strength, còn `NO_DECOMPOSITION` là decomposition. Hai cài đặt dùng hai phương thức và mô tả hai trục hành vi khác nhau.

### Khi nào dùng decomposition nào?

- `NO_DECOMPOSITION` có thể hữu ích trong những kịch bản đã đảm bảo dữ liệu ở form phù hợp và ưu tiên không chạy decomposition trong collator; nhưng phải hiểu kết quả `IDENTICAL` giữa các dạng canonical-equivalent.
- `CANONICAL_DECOMPOSITION` thích hợp nếu nguồn có thể chứa các dạng dựng sẵn/tổ hợp khác nhau và ứng dụng muốn chúng được xử lý như tương đương chuẩn tắc.
- `FULL_DECOMPOSITION` có thể gộp thêm các ký tự tương thích. **Chỉ chọn nếu ứng dụng chấp nhận mất phân biệt** giữa những dạng ký tự đó trong hoạt động so sánh.

Decomposition không thay thế một chính sách normalizing khi **lưu trữ dữ liệu**. `Collator.compare` so sánh; nó không làm thay đổi nội dung hai `String`.

## 7. Ví dụ Java 17+: IDENTICAL vẫn thay đổi khi đổi decomposition

Tạo `CollationDecompositionDemo.java`:

```java
import java.text.Collator;
import java.util.Locale;

public class CollationDecompositionDemo {
    public static void main(String[] args) {
        Collator collator =
                Collator.getInstance(Locale.US);

        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        collator.setStrength(Collator.IDENTICAL);
        collator.setDecomposition(Collator.NO_DECOMPOSITION);
        System.out.println("identical_no_decomp=" +
                (collator.compare(composed, decomposed) == 0));

        collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
        System.out.println("identical_canonical=" +
                (collator.compare(composed, decomposed) == 0));

        String asciiA = "A";
        String fullWidthA = "\uFF21";

        collator.setDecomposition(Collator.FULL_DECOMPOSITION);
        collator.setStrength(Collator.IDENTICAL);
        System.out.println("identical_full_compat=" +
                (collator.compare(asciiA, fullWidthA) == 0));

        collator.setDecomposition(Collator.NO_DECOMPOSITION);
        System.out.println("identical_no_compat=" +
                (collator.compare(asciiA, fullWidthA) == 0));
    }
}
```

Chạy:

```bash
javac CollationDecompositionDemo.java
java CollationDecompositionDemo
```

Kết quả được kiểm chứng với JDK:

```text
identical_no_decomp=false
identical_canonical=true
identical_full_compat=true
identical_no_compat=false
```

Giải thích:

1. Ở `NO_DECOMPOSITION` + `IDENTICAL`, hai dạng viết `é` khác nhau ở mức biểu diễn.
2. Bật `CANONICAL_DECOMPOSITION` giúp xử lý sự tương đương chuẩn tắc trong ví dụ.
3. Khi bật `FULL_DECOMPOSITION`, cặp `A` thông thường và `Ａ` full-width có thể được xem là tương đương dưới cơ chế collation đang dùng.
4. Quay lại `NO_DECOMPOSITION`, sự khác biệt của cặp full-width lại xuất hiện ở `IDENTICAL`.

Các kết quả cụ thể dựa trên collator `Locale.US` và bộ dữ liệu JDK đã kiểm chứng; không suy rộng chúng thành quy luật duy nhất cho mọi locale/provider và mọi ký tự tương thích.

**Lưu ý về form Unicode:** `Normalizer.Form.NFC/NFD/NFKC/NFKD` là một API khác (`java.text.Normalizer`). Nó biến đổi hoặc kiểm tra nội dung chuỗi; `Collator` chỉ áp dụng quy tắc đối chiếu. Các mode decomposition của Collator có khái niệm liên quan nhưng không phải lời gọi đồng nghĩa với việc thay chuỗi đầu vào bằng `Normalizer.normalize(...)` rồi lưu lại.

## 8. Vì sao IDENTICAL không nên được gọi là “so sánh nhị phân”?

Ba khái niệm cần tách bạch:

| Phép so sánh | Tính chất |
|---|---|
| `String.equals(a)` | So chính nội dung UTF-16 của hai `String` |
| `Collator.compare(a,b) == 0` | So theo locale + strength + decomposition |
| So dãy byte sau encoding, ví dụ UTF-8 | So theo byte, thích hợp khi giao thức quy định chính xác |

Một `Collator` có thể coi hai chuỗi tương đương ở `IDENTICAL` vì decomposition đã gộp khác biệt biểu diễn. Ngược lại, `String.equals()` sẽ không coi hai dãy UTF-16 khác nhau là bằng nhau.

Điều này quan trọng với:

- Token/secret và định danh cần khớp chính xác.
- Chữ ký số và dữ liệu băm.
- Mã định danh phải duy trì byte-for-byte theo giao thức.
- Tính duy nhất trong database, nơi collation của DB có thể khác collation của JVM.

Với dữ liệu là *secret* hoặc *canonical bytes*, không dùng Collator để “nới lỏng” equality. Nếu hợp đồng yêu cầu Unicode normalization trước so sánh, hãy thực hiện rõ ràng tại một tầng xác định, tránh biến strength thành cách thay đổi identity ngầm.

`Collator.IDENTICAL` là **mức nhạy cao nhất của Collator**, không phải API để xác minh toàn vẹn byte.

## 9. Locale là thành phần bắt buộc của quy tắc so sánh

Hai ngôn ngữ có thể đặt các chữ có dấu, chữ ghép và thứ tự từ khác nhau. Vì vậy:

```java
Collator vietnamese = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));

Collator french = Collator.getInstance(
        Locale.FRENCH);
```

Cả hai collator đều có bốn strength, nhưng **không bảo đảm cùng quan hệ thứ tự cho mọi cặp từ**. Mục đích dùng `Locale` là để ứng dụng mô tả đúng quy tắc ngôn ngữ của dữ liệu.

Trong môi trường nhiều người dùng, đừng gọi `Collator.getInstance()` không tham số và mặc định rằng nó phù hợp cho mọi bản ghi. `getInstance()` dùng default locale của JVM; default locale có thể khác giữa máy phát triển, container và production.

Một cách rõ ràng là nhận `Locale` như tham số từ hợp đồng nghiệp vụ/UI:

```java
static Collator createDisplayCollator(Locale locale) {
    Collator collator = Collator.getInstance(locale);
    collator.setStrength(Collator.TERTIARY);
    collator.setDecomposition(
            Collator.CANONICAL_DECOMPOSITION);
    return collator;
}
```

Đây là **mảnh mã** sử dụng trong class có import `Collator` và `Locale`. Nó không nói rằng `TERTIARY` luôn là mức đúng nhất; đó là **một chính sách cụ thể** cần được thống nhất trước khi dùng.

Đối với dữ liệu tổng hợp từ nhiều locale, ứng dụng cần trả lời **sắp xếp theo locale của người xem, ngôn ngữ gốc của từng bản ghi, hay locale chung được quy định?** Trộn các comparator tùy bản ghi trong cùng một lượt sort có thể phá tính nhất quán của quan hệ thứ tự.

## 10. Sắp xếp danh sách bằng Collator

Một kiểu sử dụng phổ biến là:

```java
List<String> names = new ArrayList<>(...);
Collator collator = Collator.getInstance(Locale.US);
collator.setStrength(Collator.SECONDARY);

names.sort((a, b) -> collator.compare(a, b));
```

Mảnh mã trên cho thấy cách đưa Collator vào `List.sort`. Trong code thực tế, danh sách phải chứa các `String` hợp lệ; xử lý `null` riêng nếu miền dữ liệu có cho phép `null`.

Ở `SECONDARY`, một số khác biệt case có thể coi là bằng nhau. Với các phần tử mà comparator trả `0`, hàm sort ổn định có thể giữ thứ tự tương đối như đầu vào. Nếu ứng dụng đòi một thứ tự phụ hoàn toàn xác định khi hai chuỗi tương đương về collation, có thể thêm tie-breaker rõ ràng:

```java
names.sort((a, b) -> {
    int order = collator.compare(a, b);
    return order != 0 ? order : a.compareTo(b);
});
```

Khi đó:

1. Ưu tiên thứ tự theo ngôn ngữ đã cấu hình.
2. Chỉ khi Collator xem hai chuỗi như tương đương, dùng thứ tự `String.compareTo` để có thứ tự phụ nhất quán.

**Quan trọng:** tie-breaker này làm thay đổi định nghĩa “bằng nhau” của comparator tổng thể. Nếu định nghĩa logic ứng dụng muốn `cafe` và `café` thực sự cùng khóa tại `PRIMARY`, không thể vừa dùng tie-breaker phân biệt chúng rồi mong `TreeSet` tự gộp chúng. Sắp xếp hiển thị và xét uniqueness nên là hai chính sách tách biệt.

## 11. Collator trong TreeSet/TreeMap: nguy cơ mất khóa

`TreeSet` và `TreeMap` quyết định tính trùng khóa bằng comparator, không phải chỉ dựa vào `String.equals()`. Nếu comparator trả `0` cho hai chuỗi khác nhau, cấu trúc có thể coi chúng **cùng một khóa**.

Ví dụ, với `Locale.US` ở `PRIMARY`, cả `cafe`, `café` và `Cafe` có thể tương đương theo collation.

Tạo `CollationTreeSetDemo.java`:

```java
import java.text.CollationKey;
import java.text.Collator;
import java.util.Locale;
import java.util.TreeSet;

public class CollationTreeSetDemo {
    public static void main(String[] args) {
        Collator collator =
                Collator.getInstance(Locale.US);
        collator.setStrength(Collator.PRIMARY);
        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        TreeSet<String> set = new TreeSet<>(collator);
        set.add("cafe");
        set.add("caf\u00E9");
        set.add("Cafe");

        System.out.println("treeSize=" + set.size());
        System.out.println("stringEquals=" +
                "cafe".equals("caf\u00E9"));

        CollationKey first =
                collator.getCollationKey("cafe");
        CollationKey second =
                collator.getCollationKey("caf\u00E9");
        System.out.println("keysEqual=" +
                (first.compareTo(second) == 0));
    }
}
```

Biên dịch/chạy:

```bash
javac CollationTreeSetDemo.java
java CollationTreeSetDemo
```

Kết quả kiểm chứng:

```text
treeSize=1
stringEquals=false
keysEqual=true
```

**Giải thích quan trọng:** `TreeSet` chỉ giữ một phần tử bởi comparator `PRIMARY` coi cả ba biểu diễn tương đương; nhưng `String.equals` vẫn cho thấy ít nhất hai raw strings khác nhau.

Vì vậy:

- Nếu muốn sắp xếp danh sách **nhưng vẫn giữ mọi dòng**, dùng `List.sort`.
- Nếu muốn loại bản ghi trùng theo chính sách collation, `TreeSet` có thể làm điều đó, nhưng phải là quyết định **có chủ đích**.
- Nếu muốn uniqueness theo nội dung raw, dùng `HashSet<String>` hoặc `TreeSet` với comparator nhất quán với equality đó.
- Nếu muốn uniqueness theo key đã canonicalize, thiết kế key riêng và thực thi constraint ở database.

Không dùng `TreeMap` với `PRIMARY` để lưu tài khoản theo tên rồi mặc định rằng không bao giờ có collision. Khi hai khóa compare bằng 0, map có thể ghi đè hoặc trả về value của cùng mục tùy cách cập nhật.

## 12. CollationKey: tối ưu khi phải so sánh lặp lại

`Collator.compare(a,b)` thực hiện quá trình đối chiếu trên chuỗi. Khi cần sắp xếp nhiều chuỗi hoặc so sánh cùng chuỗi nhiều lần, có thể cân nhắc `CollationKey`:

```java
CollationKey key = collator.getCollationKey("café");
```

Key này biểu diễn thông tin collation đã tính sẵn. Hai `CollationKey` có thể so qua `compareTo`, và thứ tự thường phù hợp với `Collator.compare` **nếu được sinh từ cùng quy tắc collation**.

Khi dùng:

- Tạo key bằng **cùng locale, strength và decomposition**, với cùng bộ quy tắc và version phù hợp.
- Không trộn keys được tạo từ những collator cấu hình khác nhau.
- Không dùng byte của `CollationKey.toByteArray()` làm ID ổn định xuyên JVM/version, vì định dạng/sắp xếp collation có thể thay đổi khi provider hoặc dữ liệu locale được nâng cấp.
- Nếu cấu hình của collator thay đổi, các keys đã tạo trước đó cần được xây dựng lại để sắp xếp nhất quán.

`CollationKey` là công cụ **so sánh hiệu quả hơn trong những workload thích hợp**, không phải normalization key cho database hoặc canonical username theo nghĩa bảo mật.

Không nên tối ưu trước khi đo: với danh sách rất nhỏ, tạo key cho tất cả phần tử có thể không đáng chi phí bộ nhớ; với tập dữ liệu lớn, cần benchmark và xem xét khả năng index/sort từ database hoặc search engine.

## 13. Collator không đồng nghĩa bộ máy tìm kiếm văn bản

`Collator.compare(a,b)` so sánh **hai chuỗi hoàn chỉnh** theo quy tắc collation. Nó không tự giải quyết tất cả những yêu cầu:

- Tìm một từ nằm giữa đoạn văn dài.
- Tokenization theo tiếng Việt và các ngôn ngữ khác.
- Phân tích từ viết tắt, lỗi gõ, chuyển tự.
- Bỏ dấu có chọn lọc hoặc xếp hạng mức độ liên quan.
- Lọc theo tiền tố/suffix và highlighting với offset đúng Unicode.

Ví dụ `Collator.PRIMARY` có thể coi `cafe` và `café` tương đương trong phép so sánh hai chuỗi, nhưng **không biến `String.contains("cafe")` thành tìm kiếm bỏ dấu**. `String.contains` không nhận `Collator`.

Nếu xây dựng search index, phải xác định analyzer, normalization, collation, tokenization và locale. Có thể dùng các ý tưởng collation để xác định điều kiện khớp, nhưng search đầy đủ cần pipeline và cấu trúc dữ liệu riêng.

Một điểm dễ sai: nếu dùng `Normalizer.normalize` rồi thay đổi độ dài UTF-16, offset tìm kiếm trên chuỗi normalized không tự khớp với offset trên chuỗi gốc. Chức năng highlight phải xây dựng và bảo quản ánh xạ phù hợp.

## 14. Mối quan hệ với Unicode normalization

`java.text.Normalizer` và `Collator` có liên quan nhưng không thay thế nhau:

| Công cụ | Câu hỏi nó giải quyết |
|---|---|
| `Normalizer.normalize(text, NFC)` | Chuỗi được chuyển về dạng chuẩn tắc nào? |
| `Collator.setDecomposition(CANONICAL_DECOMPOSITION)` | Khi đối chiếu, xử lý khác biệt biểu diễn tổ hợp ra sao? |
| `Collator.setStrength(PRIMARY...)` | Mức khác biệt nào được xét trong quan hệ thứ tự? |
| `String.equals` | Hai `String` chứa đúng cùng nội dung UTF-16 hay không? |

Ứng dụng có thể chọn một **canonical key** cho dữ liệu lưu trữ bằng `Normalizer`, trong khi dùng `Collator` cho việc **sắp xếp danh sách hiển thị**. Chúng không cần có cùng định nghĩa về hai chuỗi “tương đương”.

Ví dụ chính sách:

```text
original_title  -> giữ nguyên để hiển thị
canonical_code  -> normalize theo hợp đồng định danh
search_text     -> index bằng analyzer riêng
sort_order      -> dùng Collator theo locale người dùng
```

Nếu kết quả compare bằng 0 tại `PRIMARY`, không suy ra hai dòng dữ liệu có cùng identity. Đừng hợp nhất khách hàng, tài khoản hay giao dịch chỉ vì collator bỏ qua dấu hoặc case.

## 15. Những khác biệt do provider và nâng cấp JDK

`Collator.getInstance(locale)` trả một implementation từ Java runtime. Các quy tắc và bộ dữ liệu locale có thể khác nhau theo:

- Phiên bản JDK.
- Locale provider cấu hình trên JVM.
- Locale thực tế được yêu cầu và mức dữ liệu được hỗ trợ.
- Các cập nhật Unicode/CLDR và thiết lập của triển khai.

Các ví dụ `Locale.US` ở trên được kiểm chứng trên JDK sử dụng cho bài học. Khi đổi locale/provider, không nên hardcode **dấu của phép compare** cho những cặp ký tự phức tạp mà chưa kiểm chứng.

Nếu bạn lưu thứ tự hoặc collation keys trong cache/index, việc nâng cấp runtime có thể yêu cầu reindex hoặc kiểm thử tính nhất quán. Đặc biệt với sản phẩm đa quốc gia, hãy có dữ liệu test từ ngôn ngữ thực tế của người dùng thay vì dùng riêng tiếng Anh.

### Locale.US không đại diện cho mọi ngôn ngữ

Nhiều ngôn ngữ có chữ cái riêng, quy tắc dấu phụ và dạng viết hoa thường đặc biệt. Ví dụ việc phân loại dấu hoặc nhóm ký tự của một ngôn ngữ có thể có nghĩa primary thay vì secondary. Thế nên câu “PRIMARY = không dấu” chỉ là cách nhớ **gần đúng trong một số trường hợp**, không phải định nghĩa chuẩn của Java.

Không dùng một test `cafe`/`café` để chứng minh hệ thống đã xử lý đúng toàn bộ tiếng Việt hoặc các ngôn ngữ có bảng chữ cái khác.

## 16. Thread safety và việc thay đổi cấu hình

`Collator` là đối tượng có trạng thái cấu hình (`strength`, `decomposition`). Không nên chia sẻ một instance mutable giữa nhiều request/threads rồi thay `setStrength` liên tục:

```java
sharedCollator.setStrength(Collator.PRIMARY);
sharedCollator.compare(a, b);
```

Nếu thread khác sửa strength giữa hai thao tác, kết quả có thể khác chính sách dự kiến. Với môi trường đa luồng, nên tạo instance theo ngữ cảnh hoặc dùng bản sao `clone()` theo chiến lược rõ ràng, sau đó **không sửa cấu hình khi đang so sánh**. Nếu có shared state, cần đồng bộ phù hợp.

Tương tự, đừng thay comparator của `TreeSet/TreeMap` sau khi dữ liệu đã được đưa vào. Với comparator mutable, quan hệ thứ tự có thể biến đổi nhưng cấu trúc cây không được xây dựng lại, gây kết quả truy vấn không nhất quán. Muốn đổi locale/strength, tạo cấu trúc mới và nạp lại dữ liệu.

## 17. Bộ ca kiểm thử cần có

Với `Locale.US` và `CANONICAL_DECOMPOSITION`, có thể bắt đầu từ các cặp sau:

| Cặp | PRIMARY | SECONDARY | TERTIARY | IDENTICAL |
|---|---|---|---|---|
| `cafe` / `café` | Tương đương | Khác nhau | Khác nhau | Khác nhau |
| `cafe` / `Cafe` | Tương đương | Tương đương | Khác nhau | Khác nhau |
| `café` / `cafe\u0301` | Tương đương | Tương đương | Tương đương | Tương đương |

Đây là kết quả từ cấu hình cụ thể được kiểm chứng, không phải quy luật cho tất cả locale. Nên có thêm:

1. Cùng cặp canonical-equivalent với `IDENTICAL + NO_DECOMPOSITION` để thấy ảnh hưởng decomposition.
2. Full-width/compatibility characters với `FULL_DECOMPOSITION`, có test ứng dụng chấp nhận hay không.
3. Chữ có dấu và chữ cái riêng trong những locale sản phẩm hỗ trợ, ví dụ tiếng Việt.
4. Cùng một danh sách trước/sau sắp xếp để kiểm tra tiêu chí thứ tự và tie-breaker.
5. `TreeSet`/`TreeMap` dùng comparator trả 0 cho hai chuỗi raw khác nhau để không vô tình xóa dữ liệu.
6. Các cặp ký tự khác script nhưng nhìn tương tự để xác nhận collator không được dùng làm lớp bảo mật giả mạo.
7. Kết quả trước/sau nâng cấp JDK nếu hệ thống lưu sort keys hoặc index phụ thuộc collation.
8. Thử concurrency khi ứng dụng có thể chia sẻ Collator, tránh thay cấu hình khi đang format/compare.

Một test tốt không chỉ khẳng định “compare không ném lỗi”, mà phải ghi rõ **điều kiện nào nên được xem là tương đương** và **trường hợp nào tuyệt đối không được gộp dữ liệu**.

## 18. Lỗi phổ biến

**1. Cho rằng `PRIMARY` chỉ đơn giản là bỏ mọi dấu trên tất cả ngôn ngữ.** Thực tế, phân cấp khác biệt phụ thuộc quy tắc collation theo locale.

**2. Cho rằng `SECONDARY` chắc chắn bỏ qua mọi khác biệt case.** Đây là một cách nhớ thường gặp, nhưng chi tiết phải kiểm chứng theo bộ quy tắc thực tế.

**3. Cho rằng `TERTIARY` giống `String.equals()`.** Collator vẫn chịu ảnh hưởng locale/decomposition.

**4. Cho rằng `IDENTICAL` là so byte.** `IDENTICAL` là mức strength cao nhất, nhưng `CANONICAL_DECOMPOSITION` có thể khiến hai biểu diễn UTF-16 khác nhau được coi tương đương.

**5. Quên cấu hình decomposition.** Kết quả IDENTICAL với dạng dựng sẵn và tổ hợp có thể khác khi `NO_DECOMPOSITION`.

**6. Bật `FULL_DECOMPOSITION` mà không hiểu compatibility mapping.** Một số ký tự khác hình thức có thể thành tương đương.

**7. Dùng `collator.compare(a,b)==0` làm bằng chứng tài khoản trùng nhau.** So sánh theo ngôn ngữ không định nghĩa identity trừ khi nghiệp vụ quy định như vậy.

**8. Dùng `TreeSet` với PRIMARY rồi không hiểu tại sao mất phần tử.** Comparator trả 0 khiến cấu trúc coi chúng là một khóa.

**9. Trộn CollationKey từ các collator khác nhau.** Key chỉ so sánh có ý nghĩa khi cùng quy tắc cấu hình.

**10. Dùng default locale của JVM mà không kiểm soát.** Kết quả có thể thay đổi giữa môi trường hoặc theo người dùng.

**11. Thay comparator mutable sau khi đã nạp TreeMap.** Quan hệ thứ tự thay đổi làm cấu trúc cây không còn nhất quán.

**12. Đồng nhất Collator với full-text search.** Nó là phép đối chiếu chuỗi, không tokenization, ranking hay substring matching.

**13. Sử dụng compare result như thể chỉ có -1/0/1.** Chỉ dấu âm/bằng/dương là điều được bảo đảm.

**14. Cho rằng Collator luôn chống confusable/homograph.** Một chuỗi có thể bị giả mạo hình ảnh mà không có quan hệ collation như mong muốn; bảo mật định danh cần giải pháp riêng.

**15. Lưu byte của CollationKey như ID bền vững qua mọi phiên bản.** Quy tắc collation và dữ liệu JDK có thể thay đổi; cần chiến lược reindex.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `Collator.PRIMARY`, `SECONDARY` và `TERTIARY` khác nhau như thế nào?

**Đáp án:** Chúng tăng dần những mức khác biệt được xét: từ khác biệt chữ cơ bản, thêm khác biệt secondary thường gồm dấu, đến tertiary thường gồm case/biến thể. Chi tiết phụ thuộc locale.

**Câu 2.** Với `Locale.US` và canonical decomposition, `cafe` có bằng `café` ở PRIMARY không?

**Đáp án:** Có trong ví dụ kiểm chứng; ở SECONDARY trở lên, chúng khác nhau.

**Câu 3.** `cafe` và `Cafe` trong ví dụ khác nhau từ strength nào?

**Đáp án:** TERTIARY trở lên.

**Câu 4.** Hai cách biểu diễn `é` dựng sẵn và tổ hợp có thể bằng nhau tại IDENTICAL không?

**Đáp án:** Có, nếu cấu hình `CANONICAL_DECOMPOSITION` phù hợp. Với `NO_DECOMPOSITION`, ví dụ kiểm chứng cho kết quả khác nhau.

**Câu 5.** Dùng PRIMARY làm comparator cho `TreeSet` có thể làm mất hai raw strings khác nhau không?

**Đáp án:** Có, nếu comparator trả 0 cho chúng. `TreeSet` coi hai chuỗi như cùng một phần tử theo comparator.

**Câu 6.** `String.equals()` có bị ảnh hưởng khi gọi `collator.setStrength(PRIMARY)` không?

**Đáp án:** Không. Collator chỉ thay đổi cách so sánh bằng đối tượng đó; không sửa `String` hoặc nghĩa của `equals()`.

**Câu 7.** Vì sao không nên dùng `CollationKey.toByteArray()` như khóa lâu dài của một database?

**Đáp án:** Nó gắn với quy tắc, cấu hình và implementation collation; không phải mã định danh độc lập với locale/provider/version.

**Câu 8.** Một ứng dụng muốn người dùng tìm `café` bằng query `cafe` cần phải làm gì?

**Đáp án:** Xác định chính sách tìm kiếm bỏ dấu/locale và dùng pipeline search thích hợp. `Collator.PRIMARY` giúp diễn tả một phép so sánh mềm giữa chuỗi, nhưng không tự làm `String.contains()` tìm kiếm linh hoạt.

## 20. Ghi nhớ

- **PRIMARY:** mức phân biệt cơ bản.
- **SECONDARY:** thêm các khác biệt cấp hai như dấu trong nhiều locale.
- **TERTIARY:** thêm khác biệt cấp ba như hoa/thường trong nhiều locale.
- **IDENTICAL:** mức phân biệt cao nhất **trong Collator**, vẫn chịu ảnh hưởng của decomposition.

Chọn `Locale`, `strength` và `decomposition` **một cách tường minh** theo nhiệm vụ sắp xếp hoặc so khớp. Không dùng quan hệ tương đương theo collation để thay thế quy tắc identity, khóa dữ liệu, chữ ký số hoặc so sánh byte. Với danh sách, `Collator` rất hữu ích cho thứ tự ngôn ngữ; với uniqueness hoặc security, cần chính sách khác được thiết kế riêng.

**Tài liệu chính thức:** [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) · [Java SE 17 — RuleBasedCollator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/RuleBasedCollator.html) · [Java SE 17 — CollationKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CollationKey.html) · [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html).
