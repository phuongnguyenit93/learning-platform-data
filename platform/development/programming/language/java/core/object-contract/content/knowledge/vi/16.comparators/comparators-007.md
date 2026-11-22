# Chọn quy tắc so sánh chuỗi theo yêu cầu nghiệp vụ với Comparator trong Java

## 1. Vì sao một chuỗi có nhiều cách sắp xếp đúng?

Một ứng dụng có thể cần sắp xếp tên người theo tiếng Việt, mã sản phẩm theo số thứ tự, nhãn theo chữ cái không phân biệt hoa/thường, hoặc khóa kỹ thuật theo thứ tự byte/Unicode ổn định. Những quy tắc ấy **khác nhau**. Không thể có một `Comparator<String>` đúng cho mọi trường hợp.

Chẳng hạn với bốn chuỗi `"A"`, `"a"`, `"B"`, `"b"`:
- `String.compareTo` theo thứ tự từ điển của các đơn vị mã UTF-16: `A, B, a, b`.
- `String.CASE_INSENSITIVE_ORDER` xem `"A"` với `"a"` bằng nhau về thứ tự; khi sort một `List` ổn định, thứ tự tương đối của hai phần tử này được giữ lại.
- Quy tắc *không phân biệt hoa/thường trước, rồi dùng thứ tự tự nhiên để phân xử* cho `A, a, B, b`, tức có thứ tự xác định ngay cả giữa những biến thể hoa/thường.

Với `"item2"` và `"item10"`, thứ tự từ điển thông thường xếp `"item10"` trước `"item2"`, vì so ký tự `'1'` với `'2'`. Nếu nghiệp vụ muốn mã có hậu tố số tăng dần, ta phải định nghĩa quy tắc khác.

Trong bối cảnh **Java core – Object Contract / Comparator**, bài này hướng dẫn chọn quy tắc dựa vào ý nghĩa nghiệp vụ, xây dựng comparator đúng hợp đồng, kiểm tra hệ quả với `TreeSet`/`TreeMap`, và phân biệt so sánh kỹ thuật với so sánh ngôn ngữ.

## 2. Trước khi viết mã: đặc tả dữ liệu và quy tắc

Hãy làm rõ sáu câu hỏi:

1. **Đang sắp xếp gì?** Mã kỹ thuật, tên người, nhãn giao diện, mã hàng có chữ và số, hay chuỗi đầu vào tự do?
2. **Có locale không?** Danh sách tên tiếng Việt thường cần quy tắc ngôn ngữ tiếng Việt; khóa kỹ thuật lại cần kết quả ổn định không lệ thuộc ngôn ngữ.
3. **Hoa/thường và dấu có ý nghĩa không?** `"A"` so với `"a"`, `"ma"` so với `"má"` có được coi cùng mức ưu tiên không?
4. **Khoảng trắng, dấu câu, định dạng Unicode có ý nghĩa không?** Có chuẩn hóa trước khi so không; phải phân biệt chuẩn hóa hiển thị với thay đổi định danh thật.
5. **Có phần số không?** `"SKU-2"` và `"SKU-10"` cần so như số; `"SKU-02"` và `"SKU-2"` được coi cùng nhóm hay hai mã khác nhau?
6. **`compare(a,b)==0` có nghĩa gì?** Chỉ là cùng thứ hạng để sắp xếp danh sách, hay phải coi là trùng khóa trong `TreeSet`/`TreeMap`?

Ví dụ ma trận quyết định:

| Nhu cầu | Quy tắc khởi đầu | Điểm cần quyết định |
|---|---|---|
| Khóa máy, mã phân biệt hoa/thường | `Comparator.naturalOrder()` | Thứ tự là UTF-16; không phải thứ tự đọc của con người |
| Lọc/xếp nhóm bỏ qua hoa/thường | `String.CASE_INSENSITIVE_ORDER` | So bằng 0 cho một số chuỗi khác nhau theo `String.equals` |
| Xếp chữ không phân biệt hoa/thường nhưng giữ mọi biến thể | Case-insensitive rồi tie-break bằng natural order | Giữ phân biệt `"A"` và `"a"` trong sorted set |
| Tên/nhãn hiển thị tiếng Việt | `Collator` với `Locale.forLanguageTag("vi-VN")` | Phải chọn strength, phân biệt dấu và tie-break |
| Mã có hậu tố là số | Tách, kiểm tra rồi so số; sau đó tie-break | Số 2 và 02 có tương đương không? |
| Giá trị có `null` | `nullsFirst` hoặc `nullsLast` | Thống nhất `null` là dữ liệu hợp lệ hay lỗi |
| Xếp theo nhiều tiêu chí | `comparing`, `thenComparing` | Thứ tự ưu tiên và xử lý trùng là gì? |

Một yêu cầu cụ thể tốt là: “Danh sách tên sản phẩm hiển thị cho người dùng vi-VN; dùng thứ tự ngôn ngữ Việt, giữ dấu phân biệt, không loại mất sản phẩm chỉ vì tên gần giống; trường hợp collator xem bằng nhau thì so chuỗi gốc để kết quả lặp lại nhất quán”.

## 3. Hợp đồng `Comparator<T>` cần giữ

Chính sách so chuỗi không chỉ quyết định ai đứng trước; nó còn quyết định hai chuỗi nào thuộc cùng nhóm khi `compare(a,b)==0`. Với bất kỳ quy tắc nào (natural, bỏ qua hoa/thường, `Collator`, hay so phần số), vẫn phải có đối dấu, bắc cầu và dấu so sánh nhất quán giữa những phần tử được xem ngang hàng.

Ví dụ `String.CASE_INSENSITIVE_ORDER.compare("A","a")==0` nhưng `"A".equals("a")` là `false`. Đây là một comparator hợp lệ để hiển thị, song `TreeSet` có thể gộp hai khóa ấy. Thêm `thenComparing(Comparator.naturalOrder())` nếu cần giữ từng biến thể String khác nhau; **đừng thêm tie-breaker** nếu nghiệp vụ thật sự muốn định danh không phân biệt hoa/thường.

Đối với chuỗi có dấu hoặc mã số, cần xác định normalization, locale, case policy, leading zero và khóa định danh trước khi chọn cách phá hòa. Comparator không nên phụ thuộc random, thời gian, cấu hình `Collator` đang bị sửa hoặc nguồn ngoài thay đổi trong lúc sort. Với các tiêu chí số, dùng factory chuẩn (`comparingInt/Long`) thay cho phép trừ có nguy cơ tràn. Khi so trong `TreeSet/TreeMap`, kiểm tra cả hai chiều của quan hệ `compare==0` và `equals` với dữ liệu đại diện.
## 4. Lựa chọn một: thứ tự kỹ thuật của `String`

`String.compareTo` so các đơn vị mã UTF-16 theo thứ tự từ trái sang phải, khác với việc dùng quy tắc bảng chữ cái tự nhiên của bất kỳ locale cụ thể nào. Với các chuỗi có dấu hoặc surrogate pair, không suy luận rằng so UTF-16 đồng nghĩa với so “ký tự người dùng nhìn thấy” theo ngôn ngữ.

```java
Comparator<String> technical = Comparator.naturalOrder();
List<String> labels = new ArrayList<>(List.of("b", "A", "a", "B"));
labels.sort(technical);
System.out.println(labels); // [A, B, a, b]
```

Đây là đoạn minh họa trong phương thức có import `java.util.*` hoặc các import tương đương. Thứ tự này thích hợp với mã kỹ thuật có schema cố định nếu yêu cầu đúng là thứ tự so sánh String. Nó **không** phải cách chuẩn để hiển thị tên tiếng Việt cho con người.

### Unicode normalization và biểu diễn cùng ký tự

Hai chuỗi trông giống nhau có thể dùng các dãy Unicode khác nhau: một ký tự có dấu dựng sẵn, hoặc ký tự cơ sở cộng dấu kết hợp. `String.equals` và `compareTo` nhìn vào dãy mã nên có thể cho kết quả khác nhau. Nếu miền nghiệp vụ coi các biểu diễn tương đương chuẩn Unicode là cùng dữ liệu, có thể chuẩn hóa về NFC khi nhận dữ liệu:

```java
import java.text.Normalizer;

String normalized = Normalizer.normalize(raw, Normalizer.Form.NFC);
```

Đoạn trích này cần biến `raw` đã khai báo. Không mặc định chuẩn hóa tất cả trường như mật khẩu, token, mã ký hoặc ID bên ngoài: chuẩn hóa có thể làm thay đổi dữ liệu mang ý nghĩa định danh. Hãy thống nhất cả lúc nhập, lưu, tìm kiếm và so sánh.

## 5. Lựa chọn hai: so sánh bỏ qua hoa/thường

`String.CASE_INSENSITIVE_ORDER` và `String.compareToIgnoreCase` thực hiện so sánh không phân biệt hoa/thường theo cơ chế dựa trên ánh xạ chữ hoa/chữ thường của Java, **không phải bộ sắp xếp ngôn ngữ có locale**. Chúng không đồng nghĩa với `Collator`, và không tự xử lý mọi biến thể Unicode, dấu hay cách ghép chữ theo từng ngôn ngữ.

```java
Comparator<String> ignoreCase = String.CASE_INSENSITIVE_ORDER;
Comparator<String> ignoreCaseThenNatural =
        ignoreCase.thenComparing(Comparator.naturalOrder());
```

Với `List.of("b", "A", "a", "B")`:
- Sắp xếp `ignoreCase` bằng `List.sort` (stable) cho `[A, a, b, B]`. Hai giá trị không phân biệt được bằng comparator giữ tương đối thứ tự xuất hiện trong list đầu vào.
- Sắp xếp `ignoreCaseThenNatural` cho `[A, a, B, b]`. Tiêu chí phụ dùng `String.compareTo` tách `A/a` và `B/b`.
- Thêm cả bốn chuỗi vào `TreeSet<>(ignoreCase)` chỉ có **hai phần tử**, vì `compare==0` được coi là trùng.

**Câu hỏi nghiệp vụ trọng yếu:** muốn nhóm `"A"` và `"a"` như cùng tên, hay chỉ muốn chúng nằm gần nhau nhưng vẫn là hai khóa riêng? Câu trả lời quyết định có dùng tie-breaker hay không.

### Không lạm dụng `toLowerCase()`

Có thể thấy code dạng `Comparator.comparing(s -> s.toLowerCase())`. Cách này:
- Phụ thuộc default locale nếu không truyền `Locale`.
- Có thể tạo chuỗi mới nhiều lần trong khi sort.
- Có thể có hành vi khác với `compareToIgnoreCase` vì Unicode case conversion phụ thuộc locale và có thể thay đổi chiều dài.
- Không giải quyết luôn quy tắc dấu, biến thể chuẩn Unicode hoặc tính nhất quán với khóa database.

Nếu thật sự cần một khóa canonical không phụ thuộc locale, hãy chọn và ghi rõ một chính sách như `toLowerCase(Locale.ROOT)`, cân nhắc Unicode normalization, kiểm tra các ngôn ngữ liên quan và xử lý tie-break. `Locale.ROOT` không có nghĩa là “đúng theo mọi ngôn ngữ”; nó phù hợp hơn cho một số biến đổi kỹ thuật không hướng đến quy tắc hiển thị của một quốc gia.

## 6. Lựa chọn ba: so sánh ngôn ngữ bằng `Collator`

Với tên người, tên địa danh hoặc nhãn hiển thị, thường cần **collation** theo locale. Java có `java.text.Collator`:

```java
import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;

Locale vietnamese = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(vietnamese);
collator.setStrength(Collator.TERTIARY);

Comparator<String> vietnameseOrder = collator::compare;
Comparator<String> vietnameseWithTieBreaker =
        vietnameseOrder.thenComparing(Comparator.naturalOrder());
```

Ở đây:
- Chọn locale **tường minh** (`vi-VN`) thay vì mặc định phụ thuộc máy chạy.
- `Collator` đưa ra thứ tự ngôn ngữ cho locale đã chọn, phù hợp hơn `String.compareTo` khi sort tên tiếng Việt.
- `setStrength` quy định mức khác biệt được xét: `PRIMARY` chủ yếu phân biệt chữ cơ sở; `SECONDARY` thêm mức khác biệt phụ như nhiều loại dấu; `TERTIARY` thêm khác biệt ở mức sâu hơn như một số khác biệt về hoa/thường. Cách sắp chính xác phụ thuộc quy tắc và dữ liệu locale do JDK cung cấp.
- `thenComparing(Comparator.naturalOrder())` phá hòa khi collator cho kết quả `0`, nhờ đó các chuỗi khác nhau theo `String.equals` không bị nhập làm một trong `TreeSet`.
- Không khẳng định dấu thanh tiếng Việt luôn thuộc đúng một mức strength trong mọi provider và bản dữ liệu; cần kiểm thử các trường hợp thực tế bằng JDK, locale data và chính sách sản phẩm đang triển khai.

### Chọn mức strength theo yêu cầu

| Strength | Phù hợp khi | Điều cần kiểm tra |
|---|---|---|
| `Collator.PRIMARY` | Muốn nhóm nhiều biến thể nhỏ lại theo chữ cơ sở | Có thể xem những tên khác nhau là đồng hạng |
| `Collator.SECONDARY` | Cần phân biệt thêm mức dấu/biến thể phụ theo collation | Quy tắc phân biệt cụ thể của locale |
| `Collator.TERTIARY` | Muốn phân biệt sâu hơn, có thể gồm hoa/thường | Không mặc nhiên đồng nhất với `String.equals` |
| `Collator.IDENTICAL` | Cần mức phân biệt cao nhất theo collator | Vẫn phải xác định yêu cầu về các dạng chuẩn Unicode, provider và tie-break |

`Collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION)` có thể cần khi muốn xử lý nhất quán những chuỗi khác nhau ở dạng ký tự dựng sẵn và ký tự cơ sở + dấu kết hợp. Chi phí xử lý và kết quả cần được kiểm thử theo yêu cầu thực tế. Đừng thay thế việc xác định chính sách normalization dữ liệu bằng một cờ collator mà không đánh giá.

**Không dùng giả định rằng thứ tự `"Hà"`, `"Hoa"`, `"Hòa"` sẽ giống nhau trên mọi phiên bản JDK và mọi cấu hình collation provider.** Dữ liệu locale có thể khác giữa các bản JDK/CLDR. Nếu cần thứ tự tuyệt đối ổn định giữa hệ thống hoặc lưu vào DB/index, cần định nghĩa phiên bản quy tắc collation được quản lý.

### `Collator` là object có trạng thái cấu hình

Các lời gọi như `setStrength`, `setDecomposition` làm thay đổi cách so sánh. Tránh chia sẻ rồi thay đổi cùng một `Collator` trong nhiều luồng hoặc khi collection đã dùng comparator đó. Nếu cần xử lý đồng thời, dùng instance riêng hoặc bản clone theo worker/thread phù hợp; đừng thay chính sách comparator trong lúc `TreeSet`/`TreeMap` đang có dữ liệu.

## 7. Lựa chọn bốn: mã chứa phần số

Với `item1`, `item2`, `item10`, sort theo thứ tự `String.compareTo` trả `item1, item10, item2` vì so ký tự. Nếu code hợp lệ luôn có tiền tố `item` và một dãy chữ số ASCII, so **giá trị số phần hậu tố** sẽ cho `item1, item2, item10`.

Quy tắc rõ ràng:
1. Xác thực cú pháp mã trước hoặc trong hàm trích số: `item[0-9]+`.
2. Parse phần sau `item` bằng `BigInteger` nếu không muốn giới hạn chiều dài hoặc overflow của `int`/`long`.
3. So giá trị số trước.
4. Quyết định `item02` với `item2`: hai mã có cùng giá trị số nhưng khác biểu diễn; nếu muốn giữ cả hai như hai khóa khác nhau, bổ sung natural-order tie-breaker.
5. Với mã có nhiều đoạn số/chữ không đồng nhất, phải xây dựng parser/tokenizer rõ ràng; không cắt cố định ở ký tự thứ năm cho mọi domain.

```java
static BigInteger itemNumber(String code) {
    if (!code.matches("item[0-9]+")) {
        throw new IllegalArgumentException("Not item + digits: " + code);
    }
    return new BigInteger(code.substring(4));
}

Comparator<String> byNumber = Comparator.comparing(
        StringComparatorDemo::itemNumber)
        .thenComparing(Comparator.naturalOrder());
```

Đoạn trích này thuộc lớp `StringComparatorDemo` của ví dụ hoàn chỉnh phía sau. Với `item02` và `item2`, số đều là 2 nhưng tiêu chí phụ phân biệt chuỗi gốc. **Không** xử lý số bằng `return Integer.parseInt(aSuffix) - Integer.parseInt(bSuffix)` vì phép trừ có thể overflow và các số dài có thể vượt miền.

Một chính sách khác có thể muốn các mã số `02` và `2` là **cùng định danh**. Nếu vậy cần chuẩn hóa khóa ngay khi ghi hoặc so `0` một cách có chủ đích; cần cân nhắc tác động lên `TreeSet`/`TreeMap` và uniqueness của dữ liệu.

## 8. Lựa chọn năm: null, khoảng trắng, nhiều tiêu chí

### Null

`Comparator.naturalOrder()` và nhiều comparator khác không nhận `null`; nếu dữ liệu cho phép `null`, định nghĩa thứ tự:

```java
Comparator<String> nullLast =
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER
                .thenComparing(Comparator.naturalOrder()));
```

Nếu `null` phải đứng đầu dùng `Comparator.nullsFirst(...)`. Với danh sách có `null`, tránh `List.of(...)` vì factory này không chấp nhận null; dùng `Arrays.asList(...)` hoặc list mutable theo nhu cầu. Nếu null là dữ liệu không hợp lệ, fail fast ở biên input còn tốt hơn âm thầm xếp null cuối.

### Khoảng trắng và tiêu chí phụ

Nếu yêu cầu là “bỏ khoảng trắng đầu/cuối khi xếp nhưng vẫn phân biệt chuỗi gốc”, có thể:

```java
Comparator<String> trimThenNatural =
        Comparator.comparing(String::strip)
                .thenComparing(Comparator.naturalOrder());
```

`String.strip` dựa trên Unicode whitespace theo `Character.isWhitespace` và khác `String.trim`. Một số ký tự không bị xử lý theo cách người dùng mong đợi, nên cần kiểm thử dữ liệu thực. Comparator trên **không sửa chính chuỗi gốc**; chỉ sử dụng bản transform để so, rồi so chuỗi gốc khi bằng nhau.

Nếu cần chính sách “không phân biệt hoa/thường; độ dài tăng; cuối cùng chữ gốc”, viết thứ tự tiêu chí tường minh. Hãy kiểm tra trường hợp hai comparator khác nhau về tính tương đương để tránh gộp khóa ngoài ý muốn.

## 9. Ví dụ Java 17 hoàn chỉnh, output có thể kiểm chứng

Tệp **`StringComparatorDemo.java`** sau đây chạy độc lập bằng JDK 17+. Nó minh họa kết quả xác định cho natural order, case-insensitive, tie-breaker, hậu tố số và null. Phần `Collator` không in danh sách đã sắp vì thứ tự chữ tiếng Việt có thể phụ thuộc phiên bản dữ liệu locale; chương trình vẫn thiết lập và chạy comparator thực tế.

```java
import java.math.BigInteger;
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;

public class StringComparatorDemo {
    static List<String> sorted(List<String> source, Comparator<String> order) {
        List<String> copy = new ArrayList<>(source);
        copy.sort(order);
        return copy;
    }

    static BigInteger itemNumber(String code) {
        if (!code.matches("item[0-9]+")) {
            throw new IllegalArgumentException("Not item + digits: " + code);
        }
        return new BigInteger(code.substring(4));
    }

    public static void main(String[] args) {
        List<String> labels = List.of("b", "A", "a", "B");
        System.out.println("natural: "
                + sorted(labels, Comparator.naturalOrder()));
        System.out.println("ignore case: "
                + sorted(labels, String.CASE_INSENSITIVE_ORDER));

        Comparator<String> totalCaseOrder = String.CASE_INSENSITIVE_ORDER
                .thenComparing(Comparator.naturalOrder());
        System.out.println("tie breaker: "
                + sorted(labels, totalCaseOrder));

        TreeSet<String> ignoreCaseSet =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        ignoreCaseSet.addAll(labels);
        System.out.println("set ignoring case size: "
                + ignoreCaseSet.size());

        List<String> ids = List.of("item10", "item2", "item1", "item02");
        Comparator<String> byNumber = Comparator.comparing(
                StringComparatorDemo::itemNumber)
                .thenComparing(Comparator.naturalOrder());
        System.out.println("IDs natural: "
                + sorted(ids, Comparator.naturalOrder()));
        System.out.println("IDs numeric: " + sorted(ids, byNumber));

        Comparator<String> nullLast =
                Comparator.nullsLast(totalCaseOrder);
        System.out.println("null last: " + sorted(
                java.util.Arrays.asList(null, "b", "A"), nullLast));

        Collator vi = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        vi.setStrength(Collator.TERTIARY);
        Comparator<String> viOrder = vi::compare;
        List<String> names = sorted(
                List.of("Hòa", "Hoa", "Hà", "Anh"),
                viOrder.thenComparing(Comparator.naturalOrder()));
        System.out.println("vi collator configured: "
                + (vi.getStrength() == Collator.TERTIARY));
        System.out.println("vi names count: " + names.size());
    }
}
```

Chạy tại thư mục lưu tệp:

```bash
javac --release 17 StringComparatorDemo.java
java StringComparatorDemo
```

Output chính xác của các dòng in dưới đây:

```text
natural: [A, B, a, b]
ignore case: [A, a, b, B]
tie breaker: [A, a, B, b]
set ignoring case size: 2
IDs natural: [item02, item1, item10, item2]
IDs numeric: [item1, item02, item2, item10]
null last: [A, b, null]
vi collator configured: true
vi names count: 4
```

Ví dụ này đã được kiểm tra biên dịch/chạy với `javac --release 17`. Giải thích chi tiết:

- `natural`: ký tự đầu `A`/`B` đứng trước `a`/`b` theo quy tắc UTF-16.
- `ignore case`: `List.sort` ổn định, nên trong các nhóm so bằng nhau (`A/a` và `b/B`) nó giữ thứ tự tương đối lúc đầu.
- `tie breaker`: tiêu chí phụ natural order phân biệt hoa/thường, khiến các giá trị khác nhau có thứ tự rõ.
- `TreeSet` bỏ bớt các phần tử khi comparator trả `0` cho những chuỗi khác nhau về `String.equals`.
- `IDs natural`: so chuỗi thuần, nên `item02` đứng trước `item1` và `item10` đứng trước `item2`.
- `IDs numeric`: parse hậu tố số, rồi natural order phá hòa `item02`/`item2`.
- `null last`: comparator xác định vị trí `null`.
- `vi collator`: kiểm tra một instance `Collator` cho locale Việt đã được cấu hình và đã dùng sort 4 tên. Chương trình cố tình chỉ in **số phần tử** để không phụ thuộc thứ tự ngôn ngữ được cung cấp ở từng JDK.

## 10. Tie-breaker khi sắp xếp đối tượng có tên

Khi có dữ liệu đối tượng, hãy so theo trường đã chọn và thêm một khóa bất biến để phân biệt các bản ghi nếu business yêu cầu thứ tự tổng:

```java
record Customer(long id, String displayName) {}

Comparator<Customer> byDisplayNameThenId =
        Comparator.comparing(
                Customer::displayName,
                String.CASE_INSENSITIVE_ORDER)
        .thenComparingLong(Customer::id);
```

Đoạn trên là ví dụ minh họa, không nằm trong file chạy ở mục 9. Nếu hai khách hàng khác nhau có tên giống nhau khi bỏ qua hoa/thường, ID dùng làm tiêu chí phụ. Điều kiện là ID có ý nghĩa định danh duy nhất và ổn định. Nếu cùng ID vẫn có thể xuất hiện nhiều bản ghi khác nhau trong list, cần kiểm tra lại mô hình.

Trường hợp hiển thị tiếng Việt, có thể thay `String.CASE_INSENSITIVE_ORDER` bằng một comparator dựa trên `Collator` được cấu hình. Nhưng phải xác định việc khác dấu/hòa khi collation trả `0` sẽ được phân xử bởi ID hay chuỗi gốc để đáp ứng nghiệp vụ.

### Khi tie-breaker là sai chủ ý

Nếu hệ thống xem hai tên tài khoản `"ADMIN"` và `"admin"` là cùng một định danh không phân biệt hoa/thường, comparator cho kết quả `0` có thể đúng với *quan hệ duy nhất* đó. Thêm `thenComparing(naturalOrder())` sẽ khiến chúng trở thành hai khóa khác nhau trong `TreeMap`. Vì vậy **tie-breaker là một quyết định nghiệp vụ**, không phải quy tắc máy móc.

Đặc biệt cần kiểm tra consistency giữa application và database: nếu database dùng collation khác hoặc unique index bỏ qua hoa/thường/dấu khác Java comparator, ứng dụng có thể cho phép khóa mà cơ sở dữ liệu từ chối, hoặc ngược lại.

## 11. Hiệu năng và tính ổn định trong hệ thống

Một comparator được gọi nhiều lần khi sort, có thể khoảng `O(n log n)` lần đối với thuật toán sort so sánh thường dùng. Vì vậy:

- Không gọi HTTP/database trong `compare`.
- Không parse một mã phức tạp hoặc normalize chuỗi hàng nghìn lần nếu có thể chuẩn bị khóa sort một lần cho từng phần tử. Với dataset lớn, mô hình dữ liệu nên lưu sẵn khóa chuẩn hóa hoặc sử dụng sort key thích hợp và kiểm soát version.
- Không thay đổi `Collator` đang được dùng bởi `TreeSet`/`TreeMap` sau khi collection đã có phần tử.
- Không dùng comparator dựa trên thời gian, random hoặc trạng thái volatile thay đổi trong lúc sort.
- Với nhiều luồng, mỗi luồng nên có cấu hình `Collator` riêng hoặc cơ chế clone/quản lý instance phù hợp; tránh sửa một instance dùng chung.
- Kiểm tra kết quả sort khi nâng JDK, thay đổi locale provider/CLDR, hoặc di chuyển sang database có collation khác. Nếu thứ tự là hợp đồng dữ liệu hoặc ảnh hưởng pagination, phải quản trị rõ phiên bản và tie-breaker ổn định.
- Sắp xếp trong DB cần `ORDER BY` tương ứng và tie-breaker duy nhất để pagination ổn định; một comparator Java chỉ sắp được dữ liệu đã được nạp vào bộ nhớ, không đảm bảo thứ tự trang phía DB.

Nếu mục tiêu chỉ là hiển thị tên, có thể chấp nhận phụ thuộc dữ liệu collation của JDK. Nếu mục tiêu là định danh, chống trùng hoặc chữ ký/canonicalization, hãy dùng quy tắc riêng **cố định và kiểm thử được**.

## 12. Kiểm thử comparator theo nghiệp vụ

Đừng chỉ kiểm thử một danh sách happy path. Hãy tạo tập test gồm:

| Loại trường hợp | Ví dụ | Cần xác minh |
|---|---|---|
| Hoa/thường | `A`, `a`, `B`, `b` | Có gộp hay phân biệt, tie-break ra sao |
| Dấu tiếng Việt | `ma`, `má`, `mà`, `MÁ` | Thứ tự phù hợp rule, locale và strength |
| Khác dạng Unicode | Ký tự dựng sẵn và ký tự gốc + dấu | Chính sách NFC/NFD và collation nhất quán |
| Số trong mã | `item2`, `item10`, `item02` | Parse số, leading zero, tie-break |
| Khoảng trắng | `" An"`, `"An"`, `"An "` | Có strip/trim hay giữ nguyên |
| Null | `null`, `""`, `"a"` | Xếp đầu/cuối hoặc từ chối dữ liệu |
| Chuỗi rỗng | `""` | Chấp nhận hay validation fail |
| Kiểu hỗn hợp | Chữ, số, emoji, ký tự ngoài BMP | Không giả định UTF-16 tương đương collation |
| Nhiều object cùng tên | Hai khách ID khác nhau | Có mất phần tử trong `TreeSet` không |

Ngoài thứ tự kỳ vọng, kiểm thử **hợp đồng toán học** của comparator:
1. Với mỗi `a,b`: dấu của `compare(a,b)` đối nghịch dấu của `compare(b,a)`.
2. Với `a,b,c`: nếu `a<=b` và `b<=c` thì `a<=c`.
3. Khi `compare(a,b)==0`, so `a` và `b` với từng `c` khác phải cho dấu tương đương.
4. Khi comparator làm khóa `TreeSet`/`TreeMap`, kiểm tra các cặp khác nhau theo `equals` có bị gộp ngoài mong muốn không.
5. Kiểm tra sắp xếp lặp lại ra cùng kết quả dưới cùng bộ dữ liệu, cùng quy tắc và cấu hình locale.

Có thể tạo một unit test có comparator chuẩn, dùng `Collections.sort` hoặc `List.sort`, rồi assert danh sách chính xác. Với `Collator`, test trên JDK/provider/locale data của môi trường hỗ trợ, đồng thời ghi rõ phiên bản nếu thứ tự phải tái lập.

## 13. Những sai lầm thường gặp

**1. Dùng `String.compareTo` cho mọi ngôn ngữ.** Đây là thứ tự kỹ thuật UTF-16, không giải quyết đầy đủ collation theo tiếng Việt.

**2. Dùng `compareToIgnoreCase` rồi giả định mọi cách viết đều tương đương.** Nó không phải full Unicode case folding hoặc collation, và không tự bỏ dấu.

**3. Dùng `Collator.getInstance()` không truyền locale.** Kết quả có thể phụ thuộc môi trường JVM; cần chọn locale theo chức năng.

**4. Cho comparator trả `0` với mọi tên “gần giống” rồi đưa vào `TreeSet`.** Nhiều phần tử khác nhau có thể bị xem như một. Nếu mục tiêu chỉ là sort, cần tie-breaker.

**5. Thêm tie-breaker vào quy tắc unique không phân biệt hoa/thường.** Có thể vô tình cho phép hai khóa mà nghiệp vụ muốn coi là trùng.

**6. So số bằng cách so string hoặc phép trừ.** `item10` đứng trước `item2` theo từ điển; phép trừ số có thể overflow.

**7. Chuẩn hóa dữ liệu không kiểm soát.** `strip`/`toLowerCase`/NFC có thể hợp lý cho một nhóm trường nhưng làm biến đổi token hoặc khóa bên ngoài.

**8. Comparator phụ thuộc trạng thái mutable.** Thay đổi thông tin của khóa đang trong `TreeMap`/`TreeSet` có thể phá tính tổ chức của cây, tương tự vấn đề hash collection khi key đổi hash.

**9. Test một bản JDK rồi khẳng định thứ tự locale bất biến.** Với tên hiển thị, nên xác nhận cả dữ liệu locale và môi trường triển khai.

## 14. Bài tập thực hành có tiêu chí rõ ràng

### Bài 1 — Sắp tên giao diện theo tiếng Việt

Tạo list `["Hoa", "Hòa", "Hà", "Anh"]`. So bằng `String.compareTo` và một `Collator` locale `vi-VN` ở các mức strength. Ghi nhận kết quả trên môi trường thực tế; giải thích vì sao so sánh UTF-16 khác ngôn ngữ. Đánh giá xem cần giữ hoa/thường, dấu và tie-break chuỗi gốc hay không.

### Bài 2 — Từ danh sách sang tập hợp

Dùng `["Admin", "admin", "ADMIN"]` trong `ArrayList` và `TreeSet` với `String.CASE_INSENSITIVE_ORDER`. So số lượng phần tử và giải thích tại sao. Thử `thenComparing(Comparator.naturalOrder())`. Quyết định cách đúng cho danh sách hiển thị và cho khóa tài khoản không phân biệt hoa/thường.

### Bài 3 — Sắp mã sản phẩm có số

Nhập `item1`, `item02`, `item2`, `item10`. Viết comparator so BigInteger hậu tố rồi tie-break theo biểu diễn gốc. Bổ sung validation từ chối `item-2` và `itemX`. Thử số dài hơn giới hạn `long`.

### Bài 4 — Tên có khoảng trắng

Thiết kế comparator sắp `" An"`, `"An"` và `"An "` theo chuỗi sau `strip`, sau đó theo chuỗi gốc. Nêu lý do có hoặc không chuẩn hóa dữ liệu ngay lúc nhập.

### Bài 5 — Ba tiêu chí cho đối tượng

Với record `Customer(id, displayName, priority)`, viết comparator: priority tăng dần, tên theo quy tắc đã chọn, ID tăng dần để phá hòa. Kiểm tra không mất bản ghi khi đưa vào `TreeSet` nếu ID là duy nhất và không đổi.

### Bài 6 — Test hợp đồng

Sinh một tập chuỗi gồm ASCII, chữ có dấu, emoji, chuỗi rỗng; kiểm tra tính đối dấu và bắc cầu trên mọi bộ ba trong tập hữu hạn. Khi phát hiện tình huống kết quả `compare==0` cho hai chuỗi khác `equals`, quyết định đó là quy tắc grouping có chủ đích hay lỗi cần sửa.

## 15. Checklist ra quyết định cuối bài

- Đã biết rõ dữ liệu là mã kỹ thuật, tên/ngôn ngữ hay mã có phần số.
- Đã chọn chính sách locale, hoa/thường, dấu, Unicode normalization và khoảng trắng.
- Đã giải thích đúng ý nghĩa `compare(a,b)==0` trong nghiệp vụ.
- Đã phân biệt yêu cầu **sort** với yêu cầu **uniqueness** của `TreeSet`/`TreeMap`.
- Đã có tie-breaker ổn định khi muốn giữ mọi bản ghi khác nhau.
- Đã xử lý hợp lệ `null`, dữ liệu sai cấu trúc và số có leading zero.
- Comparator giữ tính đối dấu, bắc cầu, và kết quả nhất quán trên dữ liệu không đổi.
- Đã kiểm tra locale/provider/JDK khi cần thứ tự ngôn ngữ ổn định.
- Đã kiểm tra sự tương thích với collation ở database nếu so sánh diễn ra cả hai nơi.
- Chạy được `StringComparatorDemo.java`, giải thích được các dòng stdout và đánh đổi từng comparator.

**Kết luận:** Chọn `Comparator<String>` bắt đầu từ **ý nghĩa nghiệp vụ của thứ tự và tính tương đương**, rồi mới chọn API. `String.compareTo` thích hợp cho thứ tự kỹ thuật, `CASE_INSENSITIVE_ORDER` cho nhóm bỏ qua hoa/thường, `Collator` cho quy tắc ngôn ngữ, và comparator tách số cho mã có phần số. Sử dụng tie-breaker có chủ đích để tránh làm mất khóa trong sorted collections; luôn kiểm thử các trường hợp Unicode, locale và ID thực tế.