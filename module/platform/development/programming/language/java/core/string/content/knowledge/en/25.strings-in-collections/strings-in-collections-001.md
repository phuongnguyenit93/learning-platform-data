# String làm khóa HashMap hoặc phần tử HashSet trong Java

## 1. Mục tiêu và bối cảnh

`String` là một trong những kiểu thường được dùng nhất làm **khóa** của `HashMap<String, V>` và làm **phần tử** của `HashSet<String>`: mã sản phẩm, tên cấu hình, nhãn trạng thái, token, tên đăng nhập, từ vựng hoặc chuỗi dùng để loại trùng. Hai collection này dựa vào cặp phương thức **`hashCode()` và `equals(Object)`** để nhận diện khóa/phần tử tương đương.

Ví dụ:

~~~java
Map<String, Integer> points = new HashMap<>();
points.put("java", 10);
points.put("spring", 20);
System.out.println(points.get("java")); // 10

Set<String> tags = new HashSet<>();
tags.add("backend");
tags.add("backend");
System.out.println(tags.size()); // 1
~~~

Trong các ví dụ, cần có import `java.util.Map`, `java.util.HashMap`, `java.util.Set` và `java.util.HashSet` nếu viết thành lớp Java độc lập. Các đoạn riêng lẻ chỉ nhằm minh họa; chương trình hoàn chỉnh có thể biên dịch bằng Java 17 ở phần 8.

**Điểm cốt lõi:** `HashMap` và `HashSet` quan tâm **nội dung logic được `equals` xem là bằng nhau**, không phải hai biến có tham chiếu đến cùng một đối tượng String hay không.

## 2. Vì sao `String` dùng tốt làm khóa và phần tử tập hợp?

`String` có **nội dung bất biến**, `equals` so sánh nội dung phân biệt hoa/thường, và `hashCode` nhất quán với `equals`. Vì thế, cùng nội dung được coi là cùng khóa/phần tử dù tạo bởi hai instance khác nhau:

~~~java
String first = new String("Java");
String other = new String("Java");
System.out.println(first == other);      // false
System.out.println(first.equals(other)); // true
System.out.println(first.hashCode() == other.hashCode()); // true
~~~

`HashMap` dùng hash để tìm vùng ứng viên rồi kiểm tra tính tương đương khóa; `HashSet` dùng nguyên tắc tương tự để loại phần tử lặp. **Cùng hash chưa chắc cùng giá trị**: `"FB"` và `"Ea"` có hash bằng nhau nhưng nội dung khác. Collection vẫn giữ chúng như hai khóa khác nhau. Công thức hash, va chạm và các điều kiện chi tiết của hợp đồng `equals–hashCode` được phân tích ở bài kế tiếp.

Điểm mạnh của `String` là key đã chèn không đổi nội dung. Nếu sau khi `put` bạn gán lại biến `key = key + "-admin"`, map vẫn giữ khóa cũ: phép gán đổi tham chiếu của biến, **không sửa String đã lưu**.

~~~java
String key = "user";
Map<String, Integer> map = new HashMap<>();
map.put(key, 7);
key = key + "-admin";
System.out.println(map.get("user")); // 7
System.out.println(map.get(key));    // null
~~~

Các đoạn là minh họa bên trong phương thức; chương trình độc lập có đầy đủ imports ở phần 8.

## 3. HashMap sử dụng String key như thế nào?

### 3.1. `put`, `get` và `containsKey`

Mô hình khái niệm: `HashMap` dùng hash code để xác định vị trí ứng viên, rồi sử dụng `equals` để phân biệt các khóa khác nhau nằm cùng vùng lưu trữ. Chi tiết bucket, resize và cấu trúc xử lý va chạm thuộc phần triển khai JDK; API bảo đảm hành vi theo hợp đồng Map.

~~~java
Map<String, Integer> scores = new HashMap<>();
String first = new String("Java");
String sameContent = new String("Java");

scores.put(first, 10);
System.out.println(scores.get(sameContent)); // 10

scores.put(sameContent, 20);
System.out.println(scores.size());          // 1
System.out.println(scores.get("Java"));     // 20
~~~

Lệnh `put` thứ hai **cập nhật giá trị của khóa tương đương** thay vì tạo entry mới. Java map không cho có hai khóa phân biệt theo `equals` cùng tồn tại. Trong khi đó `"Java"` và `"java"` mặc định là hai khóa khác nhau.

Các phương thức thường dùng:

| Thao tác | Ý nghĩa |
| --- | --- |
| `put(key, value)` | Thêm ánh xạ nếu chưa có khóa tương đương, hoặc thay giá trị gắn với khóa đó; trả về giá trị cũ hoặc `null` theo hợp đồng. |
| `get(key)` | Lấy giá trị của khóa tương đương; trả `null` nếu không có mapping, hoặc nếu mapping chứa giá trị `null`. |
| `containsKey(key)` | Kiểm tra tồn tại khóa, giúp phân biệt “không có khóa” với “khóa có giá trị null”. |
| `putIfAbsent(key, value)` | Thêm giá trị khi khóa chưa có mapping hoặc đang gắn với `null`; không phải lệnh cộng dồn. |
| `merge` / `computeIfAbsent` | Hỗ trợ cập nhật/tạo giá trị theo quy tắc, tiện cho đếm tần suất hay gom nhóm. |

Ví dụ đếm tần suất:

~~~java
Map<String, Integer> counts = new HashMap<>();
for (String token : new String[] {"java", "sql", "java"}) {
    counts.merge(token, 1, Integer::sum);
}
System.out.println(counts.get("java")); // 2
System.out.println(counts.get("sql"));  // 1
~~~

Việc dùng `String` làm key không có nghĩa map tự bỏ khoảng trắng, đổi chữ hoa hay chuẩn hóa Unicode: map lưu và tra cứu theo chuỗi **đúng như dữ liệu được đưa vào**.

### 3.2. Collision không phải key trùng

~~~java
Map<String, String> collisionMap = new HashMap<>();
collisionMap.put("FB", "first");
collisionMap.put("Ea", "second");

System.out.println(collisionMap.size());      // 2
System.out.println(collisionMap.get("FB"));   // first
System.out.println(collisionMap.get("Ea"));   // second
~~~

Hai chuỗi có hash code như nhau nhưng `equals` khác nhau, nên map chứa **hai** entry. Collision có thể làm lookup chậm hơn vì cần kiểm tra thêm, nhưng collision **không được gây mất dữ liệu** nếu các key tuân thủ `equals/hashCode`.

### 3.3. Null và giá trị null

`HashMap` cho phép **một** khóa `null` và cho phép value `null`. Đây là hành vi riêng của `HashMap`, không áp dụng mặc định cho mọi `Map`:

~~~java
Map<String, Integer> map = new HashMap<>();
map.put(null, 42);
map.put("pending", null);
System.out.println(map.get(null));             // 42
System.out.println(map.get("pending"));        // null
System.out.println(map.containsKey("pending"));// true
~~~

Trong hệ thống thật, nếu `null` không có nghĩa nghiệp vụ rõ ràng, có thể cấm nó tại ranh giới đầu vào để dữ liệu đơn giản hơn. `Map.of(...)` và một số implementation khác không chấp nhận khóa/value `null`.

## 4. HashSet sử dụng String element như thế nào?

### 4.1. Loại phần tử trùng theo equals/hashCode

`HashSet` là tập hợp không cho phép các phần tử bằng nhau theo `equals`. Nó được triển khai dựa trên `HashMap`, dùng phần tử làm khóa nội bộ và một giá trị giả làm value:

~~~java
Set<String> skills = new HashSet<>();

System.out.println(skills.add(new String("Java"))); // true
System.out.println(skills.add(new String("Java"))); // false
System.out.println(skills.add("java"));             // true
System.out.println(skills.size());                  // 2
System.out.println(skills.contains("Java"));        // true
~~~

`add` trả `true` khi tập hợp thay đổi và `false` nếu đã có phần tử tương đương. Hai đối tượng `String` khác tham chiếu nhưng cùng nội dung chỉ chiếm một phần tử; khác hoa/thường thì là hai phần tử mặc định.

Một tình huống đơn giản là lấy các nhãn duy nhất:

~~~java
List<String> input = List.of("red", "blue", "red", "green");
Set<String> unique = new HashSet<>(input);
System.out.println(unique.size()); // 3
~~~

**Không được dựa vào thứ tự** khi duyệt `HashSet`. Nếu yêu cầu giữ thứ tự xuất hiện đầu tiên, dùng `LinkedHashSet`; nếu cần thứ tự sắp xếp theo bộ so sánh, cân nhắc `TreeSet` với quy tắc so sánh phù hợp.

### 4.2. Một phần tử null, và khác biệt API

`HashSet` cho phép phần tử `null` (tối đa một lần), giống cách `HashMap` cho phép một khóa `null`:

~~~java
Set<String> set = new HashSet<>();
System.out.println(set.add(null)); // true
System.out.println(set.add(null)); // false
System.out.println(set.size());    // 1
~~~

Không suy rộng quy tắc này sang tất cả `Set`: ví dụ `Set.of(...)` không chấp nhận `null`.

## 5. Key nhìn giống nhau vẫn có thể là hai giá trị

`String.equals` so sánh chính xác nội dung UTF-16: khác kiểu chữ, khoảng trắng, dấu kết hợp hoặc ký tự vô hình đều có thể thành **khóa khác**. Ví dụ:

~~~java
Map<String, Integer> prices = new HashMap<>();
prices.put("Café", 120);
System.out.println(prices.get("café"));       // null: khác hoa/thường
System.out.println(prices.get("Cafe\u0301")); // null: Unicode khác biểu diễn
~~~

Không có thao tác chuẩn hóa ngầm khi `put`/`get`. Nếu định danh của ứng dụng thực sự **không phân biệt** một khác biệt nào đó, hãy tạo khóa canonical bằng **cùng một quy tắc** ở cả đường ghi và đường đọc. Ví dụ, mã kỹ thuật có thể dùng `strip().toLowerCase(Locale.ROOT)` nếu chính sách cho phép; muốn thống nhất biểu diễn Unicode chính tắc có thể cần `Normalizer.Form.NFC`. Riêng token, chữ ký hoặc mã phân biệt chữ hoa/thường **không được sửa tùy ý**. Bài “Chuẩn hóa khóa khác với bảo toàn văn bản hiển thị” trình bày thiết kế lưu riêng nhãn và khóa, xử lý va chạm sau chuẩn hóa.

Khi kết quả bất ngờ, hãy kiểm tra trực tiếp `equals` giữa khóa đã lưu và khóa tìm kiếm, kiểm tra khoảng trắng/ký tự vô hình, và dùng `containsKey` nếu value có thể là `null`. `intern` không giải quyết sự khác nhau của nội dung.

## 6. Vì sao String an toàn hơn khóa có thể thay đổi?

`HashMap`/`HashSet` yêu cầu giá trị tham gia `equals` và `hashCode` của một phần tử **không đổi trong thời gian nó còn nằm trong collection**. Nếu dùng một đối tượng tùy biến làm khóa rồi sửa trạng thái được dùng để tính hash, một lần `get` hoặc `remove` có thể không còn tìm được entry trước đó; tương tự `HashSet.contains` có thể thất bại. Vấn đề đến từ vi phạm hợp đồng của key, không phải một lỗi ngẫu nhiên của map.

`String` loại bỏ lớp rủi ro đó do nội dung bất biến. Nhưng biến tham chiếu vẫn có thể đổi sang string mới, điều này không ảnh hưởng đối tượng cũ đã lưu.

### 6.1. StringBuilder và các đối tượng mutable

`StringBuilder` có thể sửa nội dung bằng `append`/`replace` và không ghi đè `equals/hashCode` để so sánh theo nội dung như `String`. Vì vậy dùng một đối tượng `StringBuilder` làm khóa map thường không thể hiện đúng yêu cầu so sánh giá trị. Hãy tạo `String` snapshot nếu cần key theo nội dung:

~~~java
StringBuilder builder = new StringBuilder("part");
String safeKey = builder.toString();

Map<String, Integer> map = new HashMap<>();
map.put(safeKey, 5);
builder.append("-updated");

System.out.println(map.get("part")); // 5
~~~

Dữ liệu trong builder thay đổi nhưng `safeKey` vẫn có giá trị `"part"`. Nếu key phải bao gồm nhiều trường, ưu tiên một kiểu **immutable value object** có `equals/hashCode` nhất quán (ví dụ `record` chứa các thành phần cũng bất biến) hơn là nối chuỗi tùy tiện gây mơ hồ dấu phân cách.

### 6.2. Cùng một String cũng có thể bị “sai” vì chuẩn hóa đầu vào

Tính bất biến chỉ đảm bảo khóa **không biến đổi sau khi đưa vào collection**. Nó không bảo đảm tất cả dữ liệu cần được coi là một khóa đều đã cùng biểu diễn. Ví dụ nếu lúc `put` dùng `input.strip()` nhưng lúc `get` dùng input nguyên văn, ứng dụng vẫn truy vấn hụt. Hãy tập trung chính sách vào một hàm như `canonicalKey(raw)` và dùng nó ở cả hai đường.

## 7. Hiệu năng, thứ tự, luồng và lựa chọn collection

- **Độ phức tạp trung bình:** với hash phân tán tốt và kích thước hợp lý, `HashMap.get`/`put` và `HashSet.contains`/`add` thường đạt khoảng **O(1) trung bình**. Nếu collision cao hoặc resize, chi phí có thể tăng; tuyệt đối không bảo đảm O(1) cho mọi thao tác/mọi đầu vào.
- **Chi phí tính hash String:** tính `hashCode` ban đầu phụ thuộc chiều dài chuỗi; một số JDK ghi nhớ hash của `String` sau lần tính. Khi so sánh khóa trùng hash, `equals` có thể cần so sánh từng code unit đến khi gặp khác biệt.
- **Memory và intern:** không cần `intern()` để làm key. `HashMap` và `HashSet` đã xử lý cùng nội dung bằng `equals/hashCode`; dùng `intern` hàng loạt có thể tạo áp lực quản lý bộ nhớ và không giải quyết canonicalization nghiệp vụ.
- **Thứ tự duyệt:** `HashMap` và `HashSet` **không cam kết** thứ tự chèn hoặc thứ tự sắp xếp. Dùng `LinkedHashMap`/`LinkedHashSet` khi muốn giữ thứ tự chèn; dùng `TreeMap`/`TreeSet` khi thực sự cần sắp xếp (lưu ý comparator chi phối logic nhận diện khóa của cấu trúc sorted).
- **Đồng thời:** `String` bất biến **không làm cho `HashMap` hoặc `HashSet` trở thành thread-safe**. Nhiều luồng sửa collection cần đồng bộ hoặc một cấu trúc phù hợp như `ConcurrentHashMap` / `ConcurrentHashMap.newKeySet()`; các cấu trúc concurrent này có quy tắc riêng, ví dụ không cho key/value `null`.
- **Chọn dạng khóa:** nếu miền khóa là enum hữu hạn, `EnumMap`/`EnumSet` thường phù hợp hơn string key. Nếu miền có quy tắc chuẩn hóa hoặc nhiều thành phần, tạo kiểu khóa rõ ràng sẽ giảm lỗi hơn là trải khắp code các lệnh `trim` và `toLowerCase`.

## 8. Ví dụ Java 17+ độc lập, kết quả không phụ thuộc thứ tự duyệt

Lưu đoạn sau trong file **`StringHashCollectionsDemo.java`**:

~~~java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class StringHashCollectionsDemo {
    public static void main(String[] args) {
        String a = new String("Java");
        String b = new String("Java");

        System.out.println("sameReference=" + (a == b));
        System.out.println("sameContent=" + a.equals(b));
        System.out.println("sameHash=" + (a.hashCode() == b.hashCode()));

        Map<String, Integer> scores = new HashMap<>();
        scores.put(a, 10);
        scores.put(b, 20);
        scores.put("java", 30);
        System.out.println("mapSize=" + scores.size());
        System.out.println("JavaValue=" + scores.get("Java"));
        System.out.println("lowercaseValue=" + scores.get("java"));

        Set<String> unique = new HashSet<>();
        System.out.println("addFirst=" + unique.add(a));
        System.out.println("addEqual=" + unique.add(b));
        System.out.println("addDifferentCase=" + unique.add("java"));
        System.out.println("setSize=" + unique.size());

        System.out.println("hashCollision="
                + ("FB".hashCode() == "Ea".hashCode()));
        Map<String, String> collisions = new HashMap<>();
        collisions.put("FB", "first");
        collisions.put("Ea", "second");
        System.out.println("collisionMapSize=" + collisions.size());
        System.out.println("collisionValues="
                + collisions.get("FB") + "/" + collisions.get("Ea"));

        String original = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("unicodeEquals=" + original.equals(decomposed));
        String normalizedKey = Normalizer.normalize(
                original, Normalizer.Form.NFC);
        String normalizedLookup = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        Map<String, String> normalizedMap = new HashMap<>();
        normalizedMap.put(normalizedKey, "matched");
        System.out.println("unicodeLookup="
                + normalizedMap.get(normalizedLookup));

        StringBuilder builder = new StringBuilder("part");
        String snapshot = builder.toString();
        Map<String, Integer> stable = new HashMap<>();
        stable.put(snapshot, 5);
        builder.append("-updated");
        System.out.println("snapshotLookup=" + stable.get("part"));

        Map<String, Integer> nullable = new HashMap<>();
        nullable.put("pending", null);
        System.out.println("nullValue=" + (nullable.get("pending") == null));
        System.out.println("containsNullValueKey="
                + nullable.containsKey("pending"));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 17 StringHashCollectionsDemo.java
java StringHashCollectionsDemo
~~~

**Stdout chính xác:**

~~~text
sameReference=false
sameContent=true
sameHash=true
mapSize=2
JavaValue=20
lowercaseValue=30
addFirst=true
addEqual=false
addDifferentCase=true
setSize=2
hashCollision=true
collisionMapSize=2
collisionValues=first/second
unicodeEquals=false
unicodeLookup=matched
snapshotLookup=5
nullValue=true
containsNullValueKey=true
~~~

Đoạn chương trình **không in trực tiếp toàn bộ `HashMap` hoặc `HashSet`**, vì thứ tự phần tử/entry khi duyệt không phải hợp đồng được đảm bảo. Các giá trị truy vấn theo key, kích thước, boolean của `add` và so sánh `equals` cho output có thể dự đoán chính xác.

## 9. Quy trình thiết kế String key đáng tin cậy

1. **Định nghĩa thế nào là cùng một khóa** theo nghiệp vụ: có phân biệt hoa/thường không, có bỏ khoảng trắng hay không, có chấp nhận Unicode tương đương chuẩn tắc không?
2. **Chọn canonicalization** (nếu cần) và áp dụng nhất quán **trước `put`/`add` và trước `get`/`contains`/`remove`**.
3. **Dùng `String` hoặc một kiểu khóa bất biến**, không dựa vào object identity hay trạng thái có thể thay đổi.
4. **Chọn collection theo nhu cầu**: `HashMap` cho key → value; `HashSet` cho membership/uniqueness; biến thể có thứ tự hoặc concurrent khi thực sự cần.
5. **Kiểm thử các cặp đầu vào đặc biệt**: cùng nội dung khác đối tượng, khác hoa/thường, space đầu/cuối, ký tự zero-width, precomposed/decomposed Unicode, hash collision và `null` khi hợp lệ.

Một API nên thể hiện chính sách rõ ràng. Ví dụ nếu định danh kỹ thuật cho phép loại whitespace đầu/cuối và không phân biệt hoa/thường:

~~~java
import java.util.Locale;

static String canonicalKey(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("key must not be null");
    }
    return raw.strip().toLowerCase(Locale.ROOT);
}
~~~

Đây là **minh họa chính sách cụ thể**, không phải quy tắc chuẩn cho mọi loại khóa. Không dùng cho giá trị mà dấu cách/chữ hoa được định nghĩa là có ý nghĩa. Nếu áp dụng chuẩn hóa Unicode, thêm `Normalizer.normalize(...)` vào chính sách sau khi quyết định thứ tự xử lý, rồi xác minh bằng dữ liệu đầu vào thực tế.

## 10. Câu hỏi tự kiểm tra

1. Vì sao hai biến tham chiếu tới **hai đối tượng** `new String("x")` vẫn chỉ tạo **một** entry trong `HashMap`? → Vì `equals` bằng nhau và `hashCode` tương ứng bằng nhau.
2. Hai chuỗi có cùng `hashCode` có bắt buộc là một key không? → **Không**. Va chạm vẫn có thể chứa hai khóa khác nhau, ví dụ `"FB"` và `"Ea"`.
3. `HashSet.add(s)` trả `false` nghĩa là gì? → Đã tồn tại phần tử tương đương theo `equals` (trong điều kiện bộ hợp đồng hash/equals của phần tử hợp lệ).
4. `String` bất biến có đảm bảo `HashMap` an toàn khi nhiều luồng đồng thời sửa không? → **Không**; đó là đặc tính của collection và cách đồng bộ.
5. Vì sao nhập `"é"` đôi khi truy vấn không khớp? → Có thể khác dạng biểu diễn Unicode; cần định nghĩa và áp dụng chuẩn hóa nhất quán nếu nghiệp vụ muốn coi chúng như nhau.
6. Vì sao `map.get(key) == null` chưa chắc nghĩa là khóa không tồn tại? → Một `HashMap` có thể gán value `null` cho key; kiểm tra `containsKey` nếu cần phân biệt.

**Ghi nhớ:** `String` thích hợp làm key/element của cấu trúc hash vì **bất biến** và triển khai `equals/hashCode` theo **nội dung chuỗi**. `HashMap` quản lý ánh xạ, `HashSet` quản lý tính duy nhất; cả hai tuân theo quy tắc so sánh chuỗi đúng như giá trị được cung cấp, không tự chuẩn hóa dữ liệu.

## Tài liệu tham khảo

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `equals`, `hashCode`, `isEmpty`, `strip`.
- [Java SE 17 — Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): hợp đồng `equals` và `hashCode`.
- [Java SE 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): key tương đương, null, hiệu năng, thứ tự và vấn đề đồng thời.
- [Java SE 17 — HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): membership, `add`, hash và thứ tự.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD và tương đương chuẩn tắc.
