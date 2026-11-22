# StringBuilder.compareTo và giới hạn dùng chuỗi khả biến làm key (Java 11+)

## 1. Mục tiêu và bối cảnh

`StringBuilder` là **chuỗi ký tự có thể thay đổi**: `append`, `insert`, `replace` và `setCharAt` đều có thể thay đổi nội dung của chính đối tượng. Từ **Java 11**, lớp này có phương thức `compareTo(StringBuilder)` và triển khai `Comparable<StringBuilder>`, nên có thể so sánh thứ tự từ điển giữa hai builder.

Nhưng có một khác biệt quan trọng: **`compareTo` so sánh nội dung, còn `equals` và `hashCode` của `StringBuilder` vẫn dùng hành vi kế thừa từ `Object`, dựa trên danh tính đối tượng.** Vì vậy, dùng builder làm khóa `Map` hay phần tử `Set` có thể cho kết quả trái với trực giác của người làm việc với chuỗi. Với `TreeMap`/`TreeSet`, nội dung thay đổi còn có thể phá hỏng giả định về thứ tự của cấu trúc dữ liệu.

Bài học làm rõ:
- `StringBuilder.compareTo` làm gì và mức độ tương thích từ Java 11.
- Liên hệ với biểu diễn Unicode bằng **UTF-16**: `char`, surrogate pair, chuẩn hóa Unicode và thứ tự ngôn ngữ tự nhiên.
- Vì sao `compareTo(a, b) == 0` **không kéo theo** `a.equals(b)` với `StringBuilder`.
- Sự khác nhau giữa `HashMap`/`HashSet` và `TreeMap`/`TreeSet` khi dùng builder làm khóa hoặc phần tử.
- Cách chuyển sang `String` bất biến để có khóa ổn định và so sánh theo nội dung.

## 2. `compareTo` của `StringBuilder` hoạt động ra sao?

Chữ ký trong Java 11 trở lên:

```java
public int compareTo(StringBuilder another)
```

`StringBuilder` triển khai `Comparable<StringBuilder>`. Phương thức trên so sánh hai dãy ký tự **theo thứ tự từ điển** (*lexicographic order*), theo quy tắc của `CharSequence.compare`:

1. So sánh từng giá trị `char` tại cùng vị trí từ trái sang phải.
2. Tại vị trí đầu tiên khác nhau, dãy có giá trị `char` nhỏ hơn đứng trước.
3. Nếu tất cả vị trí chung đều bằng nhau, dãy **ngắn hơn** đứng trước.
4. Nếu hai dãy có cùng độ dài và mọi giá trị `char` trùng nhau, kết quả bằng `0`.

Kết quả cần hiểu theo **dấu**, không giả định luôn chính xác `-1`, `0` hoặc `1`:

| `a.compareTo(b)` | Ý nghĩa |
| --- | --- |
| Nhỏ hơn `0` | Nội dung `a` đứng trước nội dung `b`. |
| Bằng `0` | Hai builder hiện chứa **cùng dãy giá trị `char`**, dù có thể là hai đối tượng khác nhau. |
| Lớn hơn `0` | Nội dung `a` đứng sau nội dung `b`. |

Ví dụ minh họa (đặt trong phương thức Java, từ Java 11):

```java
new StringBuilder("car").compareTo(new StringBuilder("cat")) < 0  // true
new StringBuilder("cat").compareTo(new StringBuilder("car")) > 0  // true
new StringBuilder("ca").compareTo(new StringBuilder("cat")) < 0   // true
new StringBuilder("cat").compareTo(new StringBuilder("cat")) == 0 // true
```

`compareTo` nhận **`StringBuilder`**, không nhận trực tiếp `String`. Nếu đang có chuỗi bất biến, có thể so sánh `builder.toString().compareTo(text)` hoặc sử dụng kiểu dữ liệu phù hợp với quy trình.

`another == null` gây `NullPointerException`. Không dùng `compareTo` để kiểm tra `null` hay để tìm kiếm chuỗi con; nó chỉ phục vụ **so sánh thứ tự hai dãy ký tự**.

## 3. Khác biệt cốt lõi giữa `compareTo`, `equals` và `hashCode`

Xét hai đối tượng có cùng nội dung:

```java
StringBuilder first  = new StringBuilder("cafe");
StringBuilder second = new StringBuilder("cafe");

System.out.println(first.compareTo(second) == 0);    // true
System.out.println(first.equals(second));            // false
System.out.println(first.toString().equals(second.toString())); // true
```

Giải thích:
- `first.compareTo(second) == 0` là **bằng nhau về dãy `char` tại thời điểm so sánh**.
- `first.equals(second)` gọi phương thức `Object.equals` kế thừa, vì `StringBuilder` **không override `equals(Object)`**. Hai đối tượng được tạo bằng hai lệnh `new` là hai danh tính khác nhau.
- `hashCode()` cũng là hành vi của `Object`, **không** là mã băm theo nội dung ký tự. Không suy ra rằng hai builder cùng chữ phải có cùng `hashCode`. Mã băm của hai đối tượng riêng biệt có thể tình cờ trùng, nên không dùng giá trị hash cụ thể để chứng minh danh tính.
- `String` thì khác: `String.equals`, `hashCode` và `compareTo` đều có hợp đồng dựa trên nội dung chuỗi, phù hợp cho khóa theo văn bản.

Hệ quả: thứ tự tự nhiên của `StringBuilder` **không nhất quán với `equals`** (*inconsistent with equals*). Đây là đặc điểm được chính Java API ghi rõ, không phải lỗi của người viết `compareTo`.

Quy ước chung của `Comparable` khuyến nghị hai biểu thức `a.compareTo(b) == 0` và `a.equals(b)` có cùng kết quả. `StringBuilder` là trường hợp cần chú ý vì vi phạm khuyến nghị này theo thiết kế.

## 4. `HashMap` và `HashSet`: khóa theo danh tính, không theo chữ

`HashMap` xét `hashCode` rồi `equals` để xác định khóa tương ứng. Do `StringBuilder` không định nghĩa `equals`/`hashCode` theo nội dung:

```java
Map<StringBuilder, Integer> hashed = new HashMap<>();
StringBuilder key = new StringBuilder("id");

hashed.put(key, 7);
System.out.println(hashed.get(new StringBuilder("id"))); // null

key.append("-2");
System.out.println(hashed.get(key));                      // 7
System.out.println(hashed.get(new StringBuilder("id-2"))); // null
```

Ba điểm cần hiểu đúng:

1. `new StringBuilder("id")` là **đối tượng khác** với `key`. Dù cùng chữ ban đầu, `HashMap` không tìm thấy khóa theo nội dung.
2. Sau `key.append("-2")`, `get(key)` **vẫn tìm được giá trị** trong ví dụ thông thường, vì khóa là **chính đối tượng đó** và `equals/hashCode` kế thừa theo danh tính. Không nói rằng chỉ việc sửa nội dung builder tự động làm `HashMap` mất entry.
3. `new StringBuilder("id-2")` tiếp tục là danh tính khác nên không tìm thấy entry, ngay cả khi chữ bằng nội dung sau khi sửa.

`HashSet<StringBuilder>` tương tự: hai builder khác nhau nhưng cùng nội dung vẫn có thể được lưu thành hai phần tử khác nhau, vì phép kiểm tra duy nhất theo `equals/hashCode`, không theo `compareTo`.

Nếu nhu cầu là **tra cứu theo nội dung văn bản** (mã người dùng, tên, token, đường dẫn...), `StringBuilder` là một kiểu khóa không phù hợp. Đổi sang `String` ở lúc khóa được chốt sẽ rõ ràng và an toàn hơn.

## 5. `TreeMap` và `TreeSet`: so sánh nội dung nhưng khóa lại khả biến

`TreeMap` và `TreeSet` không hoạt động giống bảng băm. Khi dùng thứ tự tự nhiên (không truyền `Comparator`), chúng so sánh khóa/phần tử bằng `compareTo`, vì vậy **hai `StringBuilder` khác đối tượng nhưng cùng nội dung có thể được xem như cùng khóa**:

```java
TreeMap<StringBuilder, Integer> sorted = new TreeMap<>();
sorted.put(new StringBuilder("cat"), 1);
sorted.put(new StringBuilder("cat"), 2);

System.out.println(sorted.size());                      // 1
System.out.println(sorted.get(new StringBuilder("cat"))); // 2
```

`size() == 1` vì lần `put` thứ hai có `compareTo(...) == 0` với khóa đã có, nên cập nhật giá trị cho khóa tương đương theo comparator. Điều này **không** có nghĩa hai builder là bằng nhau theo `equals`. `TreeSet` cũng xem hai builder có nội dung bằng nhau là một phần tử theo thứ tự tự nhiên.

### 5.1. Nguy cơ lớn hơn: sửa nội dung khóa đã nằm trong cây

Thứ tự của `TreeMap` được thiết lập tại thời điểm chèn hoặc thao tác tìm kiếm. Nếu sau đó nội dung của một builder được thay đổi, kết quả so sánh của khóa với các khóa khác có thể đổi **mà cấu trúc cây không được sắp xếp lại**.

```java
TreeMap<StringBuilder, Integer> unstable = new TreeMap<>();
StringBuilder middle = new StringBuilder("b");
unstable.put(new StringBuilder("a"), 1);
unstable.put(middle, 2);
unstable.put(new StringBuilder("c"), 3);

// Nguy hiểm: sửa khóa đã được chèn.
middle.replace(0, middle.length(), "z");
```

Về mặt từ điển, các ký tự hiện là `a`, `z`, `c`. Tuy nhiên, cây vẫn đang duy trì các liên kết theo những lần so sánh trước khi `b` biến thành `z`. Trên JDK được dùng để kiểm tra ví dụ ở phần sau, duyệt khóa cho thứ tự `a,z,c` và `get(new StringBuilder("c"))` trả `null` dù entry cho `c` đã được chèn.

**Đừng dựa vào chính xác dạng lỗi** (`null`, sai thứ tự hoặc thao tác khác) để viết logic: biểu hiện phụ thuộc trạng thái/cấu trúc cây. Quy tắc là **không sửa dữ liệu quyết định thứ tự của một khóa khi nó đang nằm trong `TreeMap` hoặc phần tử trong `TreeSet`**.

Với `TreeMap`, còn có vấn đề riêng ngay cả khi không sửa khóa: phép tương đương `compareTo == 0` không nhất quán với `equals`. Điều này khiến ý nghĩa “cùng khóa” khác với `HashMap` và có thể trái với hợp đồng `Map` dựa trên `equals`. Tương tự với `TreeSet` so với `HashSet`.

## 6. Unicode: `compareTo` so sánh đơn vị UTF-16

`StringBuilder` là một `CharSequence` chứa các giá trị `char` của Java. Mỗi `char` là một **đơn vị mã UTF-16 16-bit** (*code unit*), không nhất thiết là một ký tự mà con người nhìn thấy hoặc một Unicode code point hoàn chỉnh.

Do vậy, `StringBuilder.compareTo` theo thứ tự của **`char`**, không tự thực hiện:
- Chuẩn hóa Unicode `NFC`/`NFD`.
- Ghép các cặp surrogate để so sánh theo **giá trị số code point**.
- So sánh chữ không phân biệt hoa/thường.
- Sắp xếp đúng thứ tự từ vựng theo ngôn ngữ/locale (như quy tắc tiếng Việt).

### 6.1. Cùng cách hiển thị chưa chắc cùng chuỗi mã

Hai cách biểu diễn chữ “é”:
- `"\u00E9"`: một code point `U+00E9`.
- `"e\u0301"`: chữ `e` và dấu sắc kết hợp `U+0301`.

Hai dạng có thể hiển thị như nhau nhưng **dãy giá trị `char` khác nhau**, nên:

```java
StringBuilder composed = new StringBuilder("\u00E9");
StringBuilder decomposed = new StringBuilder("e\u0301");

System.out.println(composed.compareTo(decomposed) == 0); // false
```

Nếu nghiệp vụ yêu cầu xem hai dạng này tương đương về chuẩn hóa Unicode, dùng `java.text.Normalizer` để tạo **`String` chuẩn hóa theo một form nhất quán** trước khi so sánh hoặc đưa vào map:

```java
String a = Normalizer.normalize(composed.toString(), Normalizer.Form.NFC);
String b = Normalizer.normalize(decomposed.toString(), Normalizer.Form.NFC);

System.out.println(a.equals(b)); // true
```

`Normalizer` giải quyết tương đương Unicode theo form được chọn; **không tự thay thế** thuật toán sắp xếp từ điển theo một ngôn ngữ cụ thể.

### 6.2. Thứ tự UTF-16 khác thứ tự code point ở một số trường hợp

Một ký tự ngoài BMP (code point lớn hơn `U+FFFF`) được biểu diễn bằng **hai `char`** (surrogate pair). Ví dụ `U+10000` tương ứng `"\uD800\uDC00"`, trong khi `U+E000` là một `char` duy nhất.

```java
StringBuilder bmp = new StringBuilder("\uE000");
StringBuilder supplementary = new StringBuilder("\uD800\uDC00");

System.out.println(Integer.signum(bmp.compareTo(supplementary))); // 1
System.out.println(Integer.compare(
        bmp.codePointAt(0), supplementary.codePointAt(0)));       // -1
```

Theo `char` đầu tiên, `0xE000 > 0xD800` nên `compareTo` trả giá trị **dương**. Nhưng theo code point, `U+E000 < U+10000` nên `Integer.compare` trả **âm**. Không có mâu thuẫn: **đó là hai tiêu chí thứ tự khác nhau**.

Với yêu cầu sắp xếp văn bản theo thói quen ngôn ngữ, nên cân nhắc `java.text.Collator` cho `Locale` phù hợp và kiểm thử trên dữ liệu thật. Nếu dùng `Collator` làm comparator của `TreeMap`, cũng phải xác định rõ khi nào hai chuỗi được xem là *cùng khóa*, vì kết quả comparator bằng `0` có thể khác `String.equals` tùy cấu hình.

## 7. Ví dụ Java 11+ hoàn chỉnh và kết quả chạy thật

Lưu thành tệp **`BuilderCompareDemo.java`**. Ví dụ có đủ import và `main`, biên dịch được với `--release 11` trên compiler còn hỗ trợ mức 11.

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Map;
import java.util.TreeMap;

public class BuilderCompareDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("cafe");
        StringBuilder second = new StringBuilder("cafe");
        System.out.println("compareEqual=" + (first.compareTo(second) == 0));
        System.out.println("equalsEqual=" + first.equals(second));
        System.out.println("stringEqual=" + first.toString().equals(second.toString()));
        System.out.println("catVsCar=" +
                Integer.signum(new StringBuilder("cat").compareTo(new StringBuilder("car"))));
        System.out.println("caVsCat=" +
                Integer.signum(new StringBuilder("ca").compareTo(new StringBuilder("cat"))));

        Map<StringBuilder, Integer> hashed = new HashMap<>();
        StringBuilder mutableHashKey = new StringBuilder("id");
        hashed.put(mutableHashKey, 7);
        System.out.println("hashNewSameText=" + hashed.get(new StringBuilder("id")));
        mutableHashKey.append("-2");
        System.out.println("hashSameObjectAfterEdit=" + hashed.get(mutableHashKey));
        System.out.println("hashNewEditedText=" + hashed.get(new StringBuilder("id-2")));

        TreeMap<StringBuilder, Integer> sorted = new TreeMap<>();
        sorted.put(new StringBuilder("cat"), 1);
        sorted.put(new StringBuilder("cat"), 2);
        System.out.println("treeSizeSameText=" + sorted.size());
        System.out.println("treeNewSameText=" + sorted.get(new StringBuilder("cat")));

        TreeMap<StringBuilder, Integer> unstable = new TreeMap<>();
        StringBuilder middle = new StringBuilder("b");
        unstable.put(new StringBuilder("a"), 1);
        unstable.put(middle, 2);
        unstable.put(new StringBuilder("c"), 3);
        middle.replace(0, middle.length(), "z");
        StringBuilder traversal = new StringBuilder();
        for (StringBuilder key : unstable.keySet()) {
            if (traversal.length() > 0) traversal.append(",");
            traversal.append(key);
        }
        System.out.println("treeOrderAfterEdit=" + traversal);
        System.out.println("treeGetC=" + unstable.get(new StringBuilder("c")));

        StringBuilder work = new StringBuilder("id");
        String fixedKey = work.toString();
        Map<String, Integer> safe = new HashMap<>();
        safe.put(fixedKey, 99);
        work.append("-2");
        System.out.println("safeOldKey=" + safe.get("id"));
        System.out.println("safeNewText=" + safe.get("id-2"));

        StringBuilder composed = new StringBuilder("\u00E9");
        StringBuilder decomposed = new StringBuilder("e\u0301");
        System.out.println("unicodeSameUnits=" + (composed.compareTo(decomposed) == 0));
        System.out.println("unicodeSameNFC=" +
                Normalizer.normalize(composed.toString(), Normalizer.Form.NFC)
                .equals(Normalizer.normalize(decomposed.toString(), Normalizer.Form.NFC)));
        StringBuilder bmp = new StringBuilder("\uE000");
        StringBuilder supplementary = new StringBuilder("\uD800\uDC00");
        System.out.println("utf16Ordering=" + Integer.signum(bmp.compareTo(supplementary)));
        System.out.println("codePointOrdering=" +
                Integer.compare(bmp.codePointAt(0), supplementary.codePointAt(0)));
    }
}
```

Biên dịch và chạy với JDK có hỗ trợ mức Java 11 (ví dụ JDK 17/21/24):

```bash
javac --release 11 BuilderCompareDemo.java
java BuilderCompareDemo
```

**Đầu ra đã kiểm tra bằng JDK 24:**

```text
compareEqual=true
equalsEqual=false
stringEqual=true
catVsCar=1
caVsCat=-1
hashNewSameText=null
hashSameObjectAfterEdit=7
hashNewEditedText=null
treeSizeSameText=1
treeNewSameText=2
treeOrderAfterEdit=a,z,c
treeGetC=null
safeOldKey=99
safeNewText=null
unicodeSameUnits=false
unicodeSameNFC=true
utf16Ordering=1
codePointOrdering=-1
```

Cách đọc kết quả:
- Ba dòng đầu xác nhận bằng nhau theo `compareTo` không có nghĩa bằng nhau theo `equals` đối với builder.
- `catVsCar=1` và `caVsCat=-1` là **dấu so sánh**, được chuẩn hóa bằng `Integer.signum` để dễ quan sát.
- `HashMap` tìm theo **cùng đối tượng** `mutableHashKey`, không theo một builder mới có cùng nội dung.
- `TreeMap` xem hai builder chứa `"cat"` là cùng một khóa sắp xếp; việc sửa builder đang nằm trong cây phá giả định thứ tự. Hai dòng `treeOrderAfterEdit`/`treeGetC` là biểu hiện đã quan sát trên JDK được kiểm tra, **không phải kết quả được bảo đảm** cho mọi trạng thái cây.
- Khóa `String fixedKey` không đổi khi `work.append("-2")`.
- Hai dòng Unicode cuối xác nhận sự khác biệt giữa so sánh code unit UTF-16 và code point.

## 8. Giải pháp: chốt nội dung thành `String` bất biến trước khi làm khóa

Trong phần lớn bài toán cần truy xuất theo **nội dung chuỗi**, hãy dùng builder để **tạo** chuỗi và dùng `String` đã hoàn thiện làm khóa:

```java
StringBuilder draft = new StringBuilder();
draft.append("customer").append('-').append(42);

String key = draft.toString(); // snapshot bất biến của nội dung hiện tại
Map<String, Integer> counters = new HashMap<>();
counters.put(key, 1);

draft.append("-edited"); // Không ảnh hưởng key đã chốt
System.out.println(counters.get("customer-42")); // 1
```

Mẫu trên là **đoạn mã minh họa trong phương thức**; cần `import java.util.Map;` và `import java.util.HashMap;` khi chạy trong một lớp độc lập.

Lợi ích:
1. `String.equals/hashCode` so sánh theo nội dung; tạo một chuỗi khác nhưng cùng chữ vẫn tìm thấy khóa.
2. Đổi nội dung `StringBuilder` sau đó không làm thay đổi `String key` đã lưu.
3. `TreeMap<String, ...>` và `TreeSet<String>` có thứ tự tự nhiên nhất quán với `String.equals` đối với cùng chuỗi `String`.
4. Nếu dữ liệu có khả năng biểu diễn Unicode tương đương khác nhau, chuẩn hóa nội dung **trước** khi tạo khóa; nếu cần bỏ phân biệt hoa thường hoặc ghép dữ liệu theo quy tắc riêng, định nghĩa quy tắc chuẩn hóa rõ ràng và áp dụng nhất quán ở cả ghi và tra cứu.

Có thể chọn một kiểu khóa bất biến tự định nghĩa khi khóa gồm nhiều thành phần, nhưng hợp đồng `equals/hashCode` (và `compareTo` nếu cần sắp thứ tự) phải rõ và các trường quyết định khóa không thay đổi trong lúc đang nằm trong collection.

## 9. Lỗi thường gặp và hướng xử lý

| Tình huống | Hiểu nhầm | Cách xử lý đúng |
| --- | --- | --- |
| `a.compareTo(b) == 0` nhưng `a.equals(b)` là `false` | Tưởng `compareTo` và `equals` cùng so nội dung. | `StringBuilder` kế thừa `Object.equals`; dùng `a.toString().equals(b.toString())` nếu cần so nội dung. |
| `HashMap<StringBuilder, V>` không tìm bằng builder mới cùng chữ | Tưởng hash map tự so chuỗi bên trong builder. | Đổi khóa thành `String`; `HashMap` dùng `equals/hashCode` của khóa. |
| Đã `append` builder và vẫn `get(key)` được từ `HashMap` | Tưởng sửa khóa không bao giờ có rủi ro. | Lý do là danh tính builder không đổi; đây vẫn không phù hợp nếu nghiệp vụ cần khóa theo nội dung. |
| `TreeMap` gộp hai builder khác nhau cùng nội dung | Tưởng `TreeMap` cũng theo `Object.equals`. | Nó dùng `compareTo` cho thứ tự/tương đương khóa; ưu tiên `String` bất biến. |
| Sửa builder đã chèn vào `TreeMap`/`TreeSet` | Tưởng collection tự sắp xếp lại. | Không sửa khóa/phần tử ảnh hưởng thứ tự; tạo `String` mới rồi cập nhật collection bằng thao tác phù hợp. |
| Hai chuỗi trông giống nhau nhưng `compareTo != 0` | Tưởng `compareTo` tự chuẩn hóa Unicode. | Cân nhắc `Normalizer` theo yêu cầu nghiệp vụ. |
| Thứ tự so sánh khác giá trị code point hoặc thứ tự tiếng Việt | Tưởng `compareTo` là bộ sắp xếp ngôn ngữ. | Hiểu quy tắc UTF-16; dùng so sánh theo code point hoặc `Collator` khi bài toán thực sự cần. |

**Lưu ý về đồng thời:** `StringBuilder` không được thiết kế để an toàn khi nhiều luồng cùng truy cập/thay đổi không đồng bộ. Kết quả so sánh phụ thuộc nội dung tại thời điểm đọc; không thay đổi builder trong lúc thao tác sắp xếp/so sánh hoặc khi đối tượng đang tham gia cấu trúc dữ liệu dựa trên thứ tự.

## 10. Tự kiểm tra

**Câu 1.** Hai đối tượng `new StringBuilder("java")` và `new StringBuilder("java")` có `compareTo == 0` không? `equals == true` không?

**Đáp án:** `compareTo == 0` là **có**, vì cùng dãy `char`; `equals == true` là **không**, vì đó là hai đối tượng khác nhau.

**Câu 2.** Một `HashMap<StringBuilder, Integer>` đã `put(key, 1)`, sau đó gọi `key.append("!")`. Có thể nói chắc chắn entry mất vì thay đổi hash không?

**Đáp án:** **Không.** `StringBuilder` kế thừa `Object.hashCode/equals`, nên nội dung builder thay đổi không tự thay đổi hành vi danh tính. `get(key)` bằng cùng tham chiếu thường vẫn trả entry. Vấn đề là không tra cứu được theo một builder khác chứa cùng chữ; trường hợp khóa tùy biến có `equals/hashCode` theo nội dung là rủi ro khác.

**Câu 3.** Tại sao `TreeMap<StringBuilder,V>` có thể có `size() == 1` sau hai `put` dùng hai builder khác nhau chứa `"a"`?

**Đáp án:** Vì `TreeMap` dùng `compareTo` để xác định hai khóa tương đương; nội dung như nhau cho kết quả bằng `0`.

**Câu 4.** Sau khi chèn vào `TreeMap`, có nên dùng `replace` để sửa nội dung builder làm khóa không?

**Đáp án:** **Không.** Việc sửa có thể đổi kết quả so sánh mà cấu trúc cây không tự sắp xếp lại, gây sai thứ tự hoặc tra cứu thất bại.

**Câu 5.** `"\u00E9"` và `"e\u0301"` nhìn tương tự. Có phải `StringBuilder.compareTo` trả `0`?

**Đáp án:** **Không.** Dãy `char` khác nhau; nếu muốn tương đương theo Unicode canonical form, hãy chuẩn hóa nhất quán (ví dụ `Normalizer.Form.NFC`) trước khi so sánh hoặc tạo khóa.

**Câu 6.** Với chuỗi Unicode chứa code point ngoài BMP, có thể mặc định `compareTo` sắp thứ tự theo code point không?

**Đáp án:** **Không.** `compareTo` dựa trên từng code unit `char` UTF-16. Phải dùng thuật toán so sánh phù hợp nếu yêu cầu theo code point hoặc theo quy tắc ngôn ngữ.

## 11. Kết luận và nguồn tham khảo

- `StringBuilder.compareTo(StringBuilder)` được bổ sung từ **Java 11**, so sánh nội dung theo các giá trị `char` UTF-16.
- `StringBuilder` **không override `equals/hashCode`**, nên `compareTo == 0` và `equals == true` có thể khác nhau.
- `HashMap`/`HashSet` dùng hợp đồng `equals/hashCode`, còn `TreeMap`/`TreeSet` dùng so sánh thứ tự khi không có comparator tùy chỉnh. `StringBuilder` có thể tạo ra khác biệt lớn giữa hai nhóm collection.
- Khóa/phần tử dùng làm thứ tự trong cây **không được sửa nội dung quyết định thứ tự** khi còn ở trong cây.
- Với khóa theo văn bản, dùng `String` bất biến được tạo từ `builder.toString()`; thêm chuẩn hóa Unicode hay so sánh theo locale chỉ khi yêu cầu nghiệp vụ cần.

Tài liệu API chính thức còn áp dụng:
- [Java SE 11 — StringBuilder (`compareTo`, lưu ý `equals`)](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/StringBuilder.html).
- [Java SE 11 — CharSequence.compare](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/CharSequence.html#compare(java.lang.CharSequence,java.lang.CharSequence)).
- [Java SE 25 — Comparable và hợp đồng nhất quán với `equals`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Comparable.html).
- [Java SE 25 — TreeMap và yêu cầu thứ tự](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html).
- [Java SE 25 — Normalizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html).