# Giới hạn của equalsIgnoreCase và so sánh không phân biệt hoa–thường trong Java

## Mục tiêu

`"Hello".equalsIgnoreCase("hello")` trả `true`, nhưng điều đó **không có nghĩa `equalsIgnoreCase` là bộ so sánh chữ đúng cho mọi ngôn ngữ, mọi kiểu định danh và mọi nhu cầu tìm kiếm**. Unicode có chữ cái chuyển hoa/thường theo ngữ cảnh hoặc locale; một số ký tự chuyển thành nhiều ký tự; cùng một chữ có dấu có thể được lưu ở nhiều dạng chuẩn hóa. Vì vậy, khái niệm “không phân biệt hoa–thường” cần được định nghĩa theo bài toán.

Sau bài, bạn sẽ:

- Hiểu hợp đồng `String.equalsIgnoreCase`, khác biệt với `equals`, `compareToIgnoreCase` và `String.CASE_INSENSITIVE_ORDER`.
- Giải thích vì sao API này **không phụ thuộc `Locale`**, nhưng cũng không thực hiện **Unicode full case folding** hay chuẩn hóa `NFC/NFD`.
- Phân tích các trường hợp tiếng Thổ Nhĩ Kỳ (`I/i/İ/ı`), tiếng Đức (`ß/ẞ/SS`), tiếng Hy Lạp (`Σ/σ/ς`), tiếng Việt có dấu và các code point ngoài BMP.
- Biết khi nào dùng `String.toLowerCase(Locale.ROOT)`, `java.text.Normalizer` hoặc `java.text.Collator`.
- Thiết kế quy tắc riêng cho mã kỹ thuật, văn bản hiển thị, tìm kiếm không dấu, tên người và dữ liệu nhạy cảm.
- Kiểm thử ví dụ Java 17+ và tránh lỗi khi dùng case-insensitive comparator làm khóa collection.

**Trọng tâm:** giới hạn của các phép so sánh không phân biệt chữ hoa–thường, không phải khẳng định rằng mọi ứng dụng cần cùng một quy tắc.

## 1. So sánh chính xác và so sánh không phân biệt case

`String.equals` xét nội dung chuỗi chính xác; `String.equalsIgnoreCase` cho phép các chữ tương ứng khác hoa–thường theo thuật toán Java:

```java
System.out.println("Java".equals("java"));
System.out.println("Java".equalsIgnoreCase("java"));
System.out.println("Java".equalsIgnoreCase("JavaScript"));
System.out.println("Java".equalsIgnoreCase(null));
```

Stdout:

```text
false
true
false
false
```

Đây là các lệnh minh họa trong một phương thức Java. Không cần truyền `Locale` cho `equalsIgnoreCase`; phương thức không có overload nhận locale.

Những giới hạn quan trọng:

1. Phép so sánh **không tự gọi `Normalizer.normalize`**.
2. Nó không coi mọi ký tự có cùng hình dạng hoặc cùng âm đọc là tương đương.
3. Nó không bỏ dấu thanh của tiếng Việt.
4. Nó không áp dụng quy tắc riêng của locale hiện tại.
5. Nó không thực hiện đầy đủ các phép mở rộng một ký tự thành nhiều ký tự trong Unicode case folding.
6. Nó không có nghĩa hai dữ liệu thuộc cùng một danh tính hay có thể dùng thay nhau trong giao thức bảo mật.

Độ dài và cấu trúc chuỗi quan trọng: chuyển `ß` thành `SS` là phép chuyển đổi một ký tự thành hai ký tự, khác hẳn việc so sánh một cặp chữ hoa/thường đơn giản.

### Không nên đánh đồng “ký tự” với “một char”

Trong Java, `String` sử dụng UTF-16; `length()` đếm code unit, còn `codePointCount` đếm code point. Một số chữ hoa/thường ở ngoài BMP có hai code unit. Java hiện đại có khả năng nhận diện một số cặp case của chúng trong `equalsIgnoreCase`; không nên nói phương thức này chỉ làm việc với bảng chữ ASCII.

Tuy nhiên, việc nhận ra cặp chữ ở supplementary plane **không biến equalsIgnoreCase thành bộ xử lý toàn diện mọi quy tắc Unicode và ngôn ngữ**.

## 2. Turkish I: không theo ngôn ngữ người dùng

Tiếng Thổ Nhĩ Kỳ là ví dụ đặc biệt nổi tiếng:

| Ký tự | Code point | Ý nghĩa |
| --- | --- | --- |
| `I` | `U+0049` | Latin capital letter I |
| `i` | `U+0069` | Latin small letter i |
| `İ` | `U+0130` | Latin capital I with dot |
| `ı` | `U+0131` | Latin small dotless i |

Quy tắc tiếng Thổ Nhĩ Kỳ ghép cặp `I↔ı` và `i↔İ`. Nhưng `equalsIgnoreCase` áp dụng phép so sánh độc lập locale.

```java
String dottedCapital = "\u0130";
String dotlessSmall = "\u0131";

System.out.println("I".equalsIgnoreCase("i"));
System.out.println("I".equalsIgnoreCase(dotlessSmall));
System.out.println("i".equalsIgnoreCase(dottedCapital));
System.out.println(dottedCapital.equalsIgnoreCase(dotlessSmall));
```

Stdout trên Java 17+:

```text
true
true
true
true
```

Cả bốn cặp trên được phương thức nhận như tương đương khi bỏ qua case, dù không thể xem đó là phép đối chiếu chính xác theo riêng tiếng Thổ Nhĩ Kỳ.

**Bài học:** `equalsIgnoreCase` không có khái niệm “ngôn ngữ của người đọc”. Nếu người dùng cần so sánh/sắp xếp từ theo một locale, phải chọn giải pháp có tham số locale và kiểm thử quy tắc đó.

### toLowerCase còn có vấn đề default locale

```java
Locale tr = Locale.forLanguageTag("tr-TR");
System.out.println("I".toLowerCase(tr).codePointAt(0) == 0x0131);
System.out.println("I".toLowerCase(Locale.ROOT).equals("i"));
```

Đoạn minh họa trong phương thức có `import java.util.Locale;`, và cả hai dòng in `true`. Nghĩa là cùng chữ `I` nhưng kết quả chuyển chữ thường theo locale Turkic có thể khác ROOT. Đừng dùng `toLowerCase()` không tham số rồi kỳ vọng giống nhau trên mọi máy: overload này phụ thuộc default locale của JVM.

Không gọi `Locale.setDefault` theo từng request để “sửa” vấn đề; default là trạng thái chung cấp JVM. Truyền locale cụ thể khi cần.

## 3. German sharp S: chuyển case có thể đổi số ký tự

Chữ `ß` (`U+00DF`) và chữ hoa `ẞ` (`U+1E9E`) minh họa một trường hợp khác:

```java
String smallSharp = "\u00DF";
String capitalSharp = "\u1E9E";

System.out.println(smallSharp.equalsIgnoreCase("SS"));
System.out.println(smallSharp.equalsIgnoreCase(capitalSharp));
System.out.println(smallSharp.toUpperCase(Locale.ROOT));
```

Stdout:

```text
false
true
SS
```

`"ß".equalsIgnoreCase("SS")` trả `false`, nhưng khi `toUpperCase(Locale.ROOT)` xử lý toàn chuỗi `ß` lại có thể tạo `SS`. Lý do: phép chuyển đổi hoa/thường **toàn chuỗi** có thể mở rộng chiều dài, trong khi `equalsIgnoreCase` không triển khai đầy đủ Unicode full case folding nhiều ký tự.

Đây là lý do **không thể thay một cách vô điều kiện**:

```java
a.equalsIgnoreCase(b)
```

bằng:

```java
a.toUpperCase(Locale.ROOT)
        .equals(b.toUpperCase(Locale.ROOT))
```

Hai biểu thức có thể cho kết quả khác với `ß` và `SS`. Không nên dùng kết quả viết hoa như một khóa canonical vĩnh viễn nếu nghiệp vụ yêu cầu phân biệt những giá trị có thể bị gộp khi mở rộng case.

### Full case folding là một hợp đồng khác

Unicode có các quy tắc case folding, bao gồm ánh xạ có thể tạo nhiều code point, cùng những lựa chọn riêng cho Turkic. `equalsIgnoreCase` **không công bố một profile Unicode full case folding** để ứng dụng điều chỉnh. Nếu một hệ thống cần full folding theo một chuẩn xác định, phải chọn thư viện/profile thích hợp, ghi nhận phiên bản Unicode và chính sách normalization, không tự tuyên bố `equalsIgnoreCase` là tương đương.

`String.toUpperCase(Locale.ROOT)` cũng không phải tên khác của full case folding: nó thực hiện **chuyển chữ hoa toàn chuỗi** theo quy tắc riêng. Khi so sánh ID, các phép biến đổi làm thay đổi độ dài có thể tạo collision.

## 4. Greek sigma và case theo ngữ cảnh

Tiếng Hy Lạp có:

- `Σ` (`U+03A3`): sigma viết hoa.
- `σ` (`U+03C3`): sigma viết thường.
- `ς` (`U+03C2`): sigma viết thường dạng cuối từ.

`equalsIgnoreCase` có thể coi `Σ` và `ς` bằng nhau:

```java
System.out.println("\u03A3".equalsIgnoreCase("\u03C2"));
```

Stdout:

```text
true
```

Trong khi đó, việc đổi hoa/thường **một từ hoàn chỉnh** có thể cần xét vị trí chữ trong từ. Đó là hành vi ngôn ngữ theo ngữ cảnh, không chỉ ánh xạ từng ký tự riêng rẽ. Khi ứng dụng xử lý văn bản đa ngôn ngữ, cần phân biệt so sánh bỏ qua case, chuyển đổi case để hiển thị và chuẩn hóa cho tìm kiếm.

## 5. Tiếng Việt: dấu thanh không phải khác biệt hoa–thường

Với chữ tiếng Việt ghép sẵn, so sánh case đơn giản có thể đúng:

```java
System.out.println("ĐẮK".equalsIgnoreCase("đắk"));
System.out.println("ma".equalsIgnoreCase("má"));
```

Thông thường cho:

```text
true
false
```

Dấu sắc trong `má` không phải một biến thể chữ hoa của `a`. `ma`, `má`, `mà`, `mã`... có khác biệt ngôn ngữ. Khi thiết kế hệ thống, không được coi “so sánh không phân biệt hoa–thường” là “so sánh không dấu”.

### NFC/NFD: hai biểu diễn có thể nhìn giống nhau

Một chữ có dấu có thể là code point ghép sẵn hoặc chữ cơ sở cộng dấu kết hợp:

```java
String composed = "\u00E9"; // é
String decomposed = "e\u0301"; // e + combining acute

System.out.println(composed.equalsIgnoreCase(decomposed));
```

Stdout:

```text
false
```

Hai chuỗi có thể hiển thị giống hệt nhưng cấu trúc UTF-16 và số code point khác nhau; `equalsIgnoreCase` không tự gộp chúng.

Nếu hợp đồng hệ thống yêu cầu **các biểu diễn tương đương chuẩn tắc được xem như nhau**, nên áp dụng cùng một dạng chuẩn hóa Unicode cho hai phía, ví dụ `NFC`:

```java
import java.text.Normalizer;

String left = Normalizer.normalize(
        composed, Normalizer.Form.NFC);
String right = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

System.out.println(left.equalsIgnoreCase(right));
```

Stdout:

```text
true
```

NFC là **canonical normalization**; không phải quy tắc loại bỏ dấu và không kiểm tra chính tả. Cần phân biệt với `NFKC` có thể gộp các ký tự tương thích như `①` và `1`.

### Chữ đ không tự biến thành d

`Normalizer.Form.NFD` không phân rã `đ` thành `d`. Vì vậy không được giả định dùng NFD rồi xóa các Unicode combining mark sẽ tự coi `đ` và `d` là cùng chữ.

Nếu chức năng tìm kiếm không dấu muốn hỗ trợ `đ → d`, phải thêm quy tắc chuyển đổi riêng của sản phẩm. Nhưng kết quả đã bỏ dấu chỉ là **search key xấp xỉ**, không thay thế dữ liệu gốc hay ID có yêu cầu chính xác.

## 6. equalsIgnoreCase và toLowerCase(Locale.ROOT) không đồng nghĩa

Một chiến lược thường gặp:

```java
String key = input.toLowerCase(Locale.ROOT);
```

`Locale.ROOT` giúp tránh default locale của JVM, đặc biệt phù hợp với **mã kỹ thuật có bảng chữ giới hạn**, như tên lệnh ASCII. Nhưng phép chuyển chữ thường toàn chuỗi không có hợp đồng giống `equalsIgnoreCase`.

Ví dụ:

```java
String dottedI = "\u0130";
String lowered = dottedI.toLowerCase(Locale.ROOT);

System.out.println(dottedI.equalsIgnoreCase("i"));
System.out.println(lowered.equals("i"));
System.out.println(lowered.codePointCount(0, lowered.length()));
```

Stdout:

```text
true
false
2
```

Ở đây chữ `İ` có thể được lower-case ROOT thành **`i + combining dot above`** — hai code point. `equalsIgnoreCase` với `i` lại trả true. Đó là hai tiêu chí khác nhau.

### Một chính sách tốt cho mã ASCII

Nếu một protocol chỉ cho phép chữ ASCII, hãy kiểm tra **bộ ký tự hợp lệ** trước, rồi chuyển case:

```java
String canonicalCommand(String input) {
    if (input == null || !input.matches("[A-Za-z][A-Za-z0-9_-]*")) {
        throw new IllegalArgumentException("Invalid ASCII command");
    }
    return input.toLowerCase(Locale.ROOT);
}
```

Đây là phương thức minh họa nằm trong một lớp đã import `Locale`. Nó không phù hợp làm validation tên người vì sẽ loại chữ tiếng Việt có dấu hoặc chữ từ các hệ chữ khác.

Nếu chỉ viết `"LOGIN".equalsIgnoreCase(userInput)` mà không kiểm tra phạm vi ký tự, những ký tự Unicode có quan hệ case đặc biệt có thể được chấp nhận dù giao thức dự định chỉ dùng ASCII.

## 7. compareToIgnoreCase và CASE_INSENSITIVE_ORDER

Ngoài kiểm tra bằng nhau, Java có:

- `String.compareToIgnoreCase(other)`: so sánh thứ tự chuỗi bỏ qua case theo quy tắc String, không phải thứ tự từ điển của một locale.
- `String.CASE_INSENSITIVE_ORDER`: comparator có thể truyền cho `TreeSet`, `TreeMap` hoặc sắp xếp.

```java
import java.util.Set;
import java.util.TreeSet;

Set<String> files = new TreeSet<>(
        String.CASE_INSENSITIVE_ORDER);
files.add("File");
files.add("file");

System.out.println(files.size());
```

Stdout:

```text
1
```

Một `TreeSet` xem hai phần tử có comparator trả 0 là tương đương về khóa, nên chỉ giữ một phần tử. Nhưng `"File".equals("file")` là `false`.

Đây là ví dụ **comparator không nhất quán với `equals`**. Vì vậy:

- `HashSet`/`HashMap` dựa vào `equals/hashCode`.
- `TreeSet`/`TreeMap` dựa vào comparator để quyết định thứ tự và tính trùng khóa.
- Hai loại collection có thể chứa số entry khác nhau từ cùng dữ liệu.

Nếu thiết kế yêu cầu tên tệp, tên người hoặc mã định danh phải giữ khác biệt case, dùng `CASE_INSENSITIVE_ORDER` có thể làm mất entry. Nếu muốn trường hợp “File” và “file” là một key, phải ghi rõ đó là chính sách và xử lý collision theo nghiệp vụ.

`compareToIgnoreCase` cũng không phải API sắp xếp theo locale, vì thế không mặc nhiên phù hợp cho danh bạ tiếng Việt hay danh sách từ tiếng Thổ Nhĩ Kỳ.

## 8. Collator cho so sánh và sắp xếp theo locale

`java.text.Collator` được thiết kế để so sánh chuỗi theo quy ước của một locale. Ví dụ:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
collator.setStrength(Collator.SECONDARY);
collator.setDecomposition(
        Collator.CANONICAL_DECOMPOSITION);
```

`Collator` có các cấp strength:

| Strength | Khác biệt được xem xét | Điều cần thận trọng |
| --- | --- | --- |
| `PRIMARY` | Các khác biệt chữ cơ bản | Có thể gộp một số khác biệt dấu/case |
| `SECONDARY` | Bổ sung những khác biệt thứ cấp như dấu | Thường bỏ qua case nhưng xét nhiều dấu |
| `TERTIARY` | Bổ sung khác biệt về case/biến thể | Thứ tự theo locale/provider |
| `IDENTICAL` | Phân biệt rất chặt ở cấp collation | Không nên tự coi là equality theo byte |

Ở ví dụ sử dụng provider/JDK đã kiểm tra:

```java
System.out.println(collator.compare("Mai", "mai") == 0);
System.out.println(collator.compare("ma", "má") == 0);
```

Stdout:

```text
true
false
```

Ở strength `SECONDARY`, case của `Mai/mai` không làm hai chuỗi khác nhau trong ví dụ, nhưng dấu sắc của `ma/má` vẫn được phân biệt.

**Lưu ý:** dữ liệu collation và các chi tiết so sánh có thể phụ thuộc locale/provider/JDK. Khi hệ thống cần thứ tự từ điển đúng theo một thị trường, hãy kiểm tra trên cấu hình thực tế và tập dữ liệu phù hợp. `Collator` có trạng thái cấu hình nên không tùy tiện chia sẻ rồi thay `setStrength` giữa các request đồng thời.

### Collator không phải full case folding hay xác thực

`Collator.PRIMARY` có thể cho kết quả “bằng nhau” ở những từ khác nhau về dấu. Mức so sánh đó có thể hữu ích cho tìm kiếm, nhưng không đủ để quyết định hai tài khoản hay hai cá nhân là cùng một.

`CollationKey` cũng không nên được xem là chuỗi ID vĩnh viễn xuyên phiên bản JDK hoặc provider. Nó phục vụ so sánh theo cấu hình collation cụ thể.

## 9. Chuẩn hóa NFC rồi so sánh: một policy có giới hạn rõ ràng

Nếu hệ thống muốn **canonical equivalence + bỏ qua case đơn giản**, có thể xây helper:

```java
import java.text.Normalizer;

public final class TextEquality {
    private TextEquality() {}

    public static boolean sameNfcIgnoringCase(String a, String b) {
        if (a == null || b == null) {
            return a == b;
        }

        String left = Normalizer.normalize(
                a, Normalizer.Form.NFC);
        String right = Normalizer.normalize(
                b, Normalizer.Form.NFC);

        return left.equalsIgnoreCase(right);
    }
}
```

Đây là lớp biên dịch được thành `TextEquality.java`, không có `main` để chạy. Hàm áp dụng **một chính sách cụ thể**: hai null được xem bằng nhau; mọi chuỗi còn lại được chuẩn hóa NFC rồi gọi `equalsIgnoreCase`.

Hạn chế:

- Nó giúp so sánh hai dạng chuẩn tắc `é` và `e + ◌́`.
- Nó **không** tự gộp `ß` với `SS`.
- Nó không thực hiện Unicode full case folding.
- Nó không áp dụng riêng quy tắc Turkic.
- Nó không bỏ dấu thanh của tiếng Việt hay map `đ` sang `d`.
- Nó không làm input an toàn, đúng chính tả hay hợp lệ với một schema.

Nếu dữ liệu được dùng làm khóa cache, DB hoặc tìm kiếm, phải áp dụng cùng một policy ở **mọi đường tạo và đọc khóa**. Khi thêm normalization vào hệ thống đã có dữ liệu, hai giá trị khác nhau ở dạng raw có thể trùng sau NFC; cần lên kế hoạch xử lý collision trước migration.

## 10. Từng nhu cầu nên chọn công cụ nào?

### Mã lệnh và giao thức ASCII

Cho phép một alphabet rõ ràng, validate trước, rồi dùng chuyển case `Locale.ROOT` nếu protocol không phân biệt case. Nếu protocol phân biệt case thì dùng `equals` và giữ nguyên.

### Văn bản người dùng, tên và nội dung đa ngôn ngữ

Giữ nguyên giá trị gốc theo yêu cầu nghiệp vụ. Cân nhắc NFC để hợp nhất hai cách biểu diễn **tương đương chuẩn tắc**, nhưng không tự xóa dấu hoặc chuyển toàn bộ tên sang ASCII. `equalsIgnoreCase` không phải kiểm tra danh tính người thật.

### Tìm kiếm linh hoạt

Một tìm kiếm có thể muốn `ca phe` tìm `cà phê`. Có thể tạo chỉ mục tìm kiếm phụ theo policy bỏ dấu, case folding hoặc collation. Tuy nhiên, nhiều từ khác nghĩa có thể gộp thành cùng search key. **Giữ trường gốc** và không dùng search key làm ID duy nhất nếu không có quy tắc chấp nhận collision.

### Sắp xếp theo ngôn ngữ

Dùng `Collator` với locale, strength/decomposition phù hợp thay vì `compareToIgnoreCase` hoặc `CASE_INSENSITIVE_ORDER` khi thứ tự từ điển tự nhiên có ý nghĩa với người dùng.

### Mật khẩu, API token và dữ liệu bí mật

Không dùng `equalsIgnoreCase` chỉ để “dễ nhập hơn”. Điều đó có thể làm các giá trị bí mật vốn khác nhau bị xem như nhau. Với mật khẩu, dùng quy trình xác thực dựa trên password hash có salt và thuật toán chuyên dụng; với token hoặc chữ ký, dùng quy tắc byte/schema và cơ chế so sánh phù hợp, bao gồm xem xét timing khi cần. Chỉ chuẩn hóa Unicode nếu giao thức xác thực đã quy định chính sách đó một cách nhất quán.

### Các loại username hoặc identifier Unicode

Một hệ thống cho phép ID Unicode phải **công bố profile cụ thể**: tập ký tự được phép, normalization, case folding, quy tắc confusable, xử lý collision, độ dài và phiên bản Unicode. `equalsIgnoreCase` đơn lẻ không thể giải quyết các vấn đề này.

## 11. Ví dụ Java 17+ chạy độc lập

Tạo tệp `CaseComparisonDemo.java`. Ví dụ dùng Unicode escapes để không phụ thuộc khả năng hiển thị ký tự đặc biệt của source editor hoặc terminal.

```java
import java.text.Collator;
import java.text.Normalizer;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

public class CaseComparisonDemo {
    public static void main(String[] args) {
        String dottedI = "\u0130";
        String dotlessI = "\u0131";

        System.out.println("HELLO: "
                + "HELLO".equalsIgnoreCase("hello"));
        System.out.println("I/dotless: "
                + "I".equalsIgnoreCase(dotlessI));
        System.out.println("i/dotted: "
                + "i".equalsIgnoreCase(dottedI));

        String sharpS = "\u00DF";
        String upperSharpS = "\u1E9E";
        System.out.println("sharp/SS: "
                + sharpS.equalsIgnoreCase("SS"));
        System.out.println("sharp/upperSharp: "
                + sharpS.equalsIgnoreCase(upperSharpS));
        System.out.println("uppercased sharp: "
                + sharpS.toUpperCase(Locale.ROOT));

        System.out.println("sigma: "
                + "\u03A3".equalsIgnoreCase("\u03C2"));

        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("raw NFC/NFD: "
                + composed.equalsIgnoreCase(decomposed));
        System.out.println("normalized NFC: "
                + Normalizer.normalize(
                    composed, Normalizer.Form.NFC)
                  .equalsIgnoreCase(
                    Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));

        Collator vi = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        vi.setStrength(Collator.SECONDARY);
        vi.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        System.out.println("collator case: "
                + (vi.compare("Mai", "mai") == 0));
        System.out.println("collator accent: "
                + (vi.compare("ma", "m\u00E1") == 0));

        Set<String> names = new TreeSet<>(
                String.CASE_INSENSITIVE_ORDER);
        names.add("File");
        names.add("file");
        System.out.println("set size: " + names.size());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CaseComparisonDemo.java
java CaseComparisonDemo
```

Stdout theo môi trường JDK kiểm tra, với hai phép Collator phụ thuộc provider như đã lưu ý:

```text
HELLO: true
I/dotless: true
i/dotted: true
sharp/SS: false
sharp/upperSharp: true
uppercased sharp: SS
sigma: true
raw NFC/NFD: false
normalized NFC: true
collator case: true
collator accent: false
set size: 1
```

Giải thích: các dòng `I` cho thấy bỏ qua case không theo riêng tiếng Thổ Nhĩ Kỳ; `sharp/SS` và `uppercased sharp` cho thấy sự khác biệt giữa so sánh đơn giản và chuyển cả chuỗi; NFC giúp đưa hai dãy code point tương đương chuẩn tắc về cùng dạng; `Collator` minh họa việc tách case và dấu ở strength phù hợp; `TreeSet` thể hiện comparator có thể gộp hai key.

Ví dụ dùng `Locale` tường minh, không thay `Locale.setDefault` và không phụ thuộc ngày giờ hệ thống. Với yêu cầu cụ thể về thứ tự collation, hãy test JDK/provider của môi trường triển khai.

## 12. Các lỗi phổ biến

| Nhầm lẫn | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| `equalsIgnoreCase` phù hợp mọi ngôn ngữ | Turkish I và những ánh xạ đặc biệt có thể sai mong muốn | Chọn policy/locale rõ ràng |
| `equalsIgnoreCase` giống lowercase cả hai | Whole-string mapping có thể đổi độ dài | Kiểm tra case mapping và folding khác nhau |
| `ß` chắc chắn bằng `SS` | Simple comparison trả false | Dùng profile full folding nếu nghiệp vụ cần |
| Dùng `toLowerCase()` không tham số cho key kỹ thuật | Default locale có thể đổi kết quả | Dùng `Locale.ROOT` và validate alphabet |
| So sánh case tự xử lý NFC/NFD | Hai dãy code point vẫn khác | Chuẩn hóa cả hai phía khi cần |
| Bỏ case cũng là bỏ dấu tiếng Việt | `ma`/`má` không chỉ khác case | Không xóa dấu nếu không có yêu cầu |
| NFC sẽ biến `đ` thành `d` | Không có tương đương chuẩn tắc đó | Mapping riêng chỉ cho search khi cần |
| NFKC luôn tốt hơn NFC | Có thể gộp những ký tự tương thích ngoài ý muốn | Chọn dạng theo hợp đồng dữ liệu |
| `TreeSet` dùng CASE_INSENSITIVE_ORDER giữ mọi giá trị khác nhau | Comparator trả 0 có thể làm mất entry | Xác định chính sách key/collision |
| `compareToIgnoreCase` sắp xếp đúng mọi locale | Không có tham số locale | Dùng `Collator` khi cần |
| Collator PRIMARY chứng minh hai tài khoản là một | Có thể bỏ qua dấu/case | Không dùng collation linh hoạt làm định danh |
| Mật khẩu không phân biệt case là “tiện” | Làm yếu hoặc sai hợp đồng bí mật | Dùng cơ chế xác thực phù hợp |
| Chỉ test ABC/abc | Bỏ lỡ Unicode đặc biệt | Test Turkic, German, NFC/NFD, dấu tiếng Việt |

## 13. Bài tập tự kiểm tra

**Bài 1 — ASCII và Unicode.** So sánh `HELLO/hello` và `I/ı`. Tại sao cả hai có thể bằng theo `equalsIgnoreCase` dù trường hợp thứ hai có ngữ nghĩa khác khi xét locale?

**Bài 2 — German sharp S.** Với `ß`, `ẞ`, `SS`, hãy in kết quả `equalsIgnoreCase` và `toUpperCase(Locale.ROOT)`. Điều gì thay đổi khi một ký tự mở rộng thành hai ký tự?

**Bài 3 — NFC/NFD.** Tạo `"\u00E9"` và `"e\u0301"`, gọi `equalsIgnoreCase` trước và sau NFC. Vì sao normalization và case mapping là hai cơ chế độc lập?

**Bài 4 — tiếng Việt.** So sánh `"ma"`, `"má"` và `"MA"` theo nhu cầu: tên gốc, key tìm kiếm không dấu, và hiển thị. Những phép biến đổi nào có thể làm mất thông tin?

**Bài 5 — Collator.** Dùng `vi-VN` với strength SECONDARY để so sánh `Mai/mai` và `ma/má`. Thay strength thành PRIMARY rồi kiểm tra lại. Vì sao không dùng kết quả này để xác thực danh tính?

**Bài 6 — TreeSet.** Thêm `File` và `file` vào `HashSet` và `TreeSet<>(String.CASE_INSENSITIVE_ORDER)`. Vì sao kích thước có thể khác? Đây là lỗi hay tính năng tùy hợp đồng?

**Bài 7 — mã giao thức.** Một API cho phép ID ASCII không phân biệt case. Thiết kế bước validation rồi chuyển `Locale.ROOT`. Những ký tự Unicode nào cần bị từ chối để không mở rộng phạm vi ngoài mong muốn?

**Bài 8 — bảo mật.** Tại sao không nên dùng `equalsIgnoreCase` cho token hoặc mật khẩu? Nếu hệ thống cho phép username Unicode, cần công bố thêm những quy tắc nào về chuẩn hóa, case folding và xử lý collision?

## 14. Kết luận

`String.equalsIgnoreCase` hữu ích cho **so sánh hoa–thường đơn giản**, nhưng **không có tham số `Locale`**, không thực hiện đầy đủ Unicode full case folding, không tự chuẩn hóa NFC/NFD, không bỏ dấu tiếng Việt và không thay thế collation theo ngôn ngữ hay logic nhận dạng an toàn.

Hãy chọn giải pháp dựa trên mục tiêu: `equals` cho dữ liệu chính xác; validate ASCII + `Locale.ROOT` cho giao thức có bảng chữ giới hạn; `Normalizer` cho canonical equivalence; `Collator` cho so sánh theo ngôn ngữ; search index riêng cho tìm kiếm xấp xỉ. Đối với ID hoặc dữ liệu bí mật, quy tắc chuẩn hóa và so sánh phải được thiết kế như một phần của hợp đồng, không phải một tiện ích được thêm tùy hứng.

**Ghi nhớ:** *“Không phân biệt hoa–thường” là yêu cầu phải được định nghĩa, không phải một nút bật duy nhất đúng cho mọi ngôn ngữ.*

### Tài liệu tham khảo

- [`String` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Collator` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [`Normalizer` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Case Mappings – Unicode Standard](https://www.unicode.org/versions/latest/core-spec/chapter-4/)
- [Unicode Normalization (UAX #15)](https://unicode.org/reports/tr15/)
