# Chuẩn hóa khóa khác với bảo toàn văn bản hiển thị trong Java Collections

## 1. Vấn đề: cùng cách tìm kiếm, khác cách trình bày

Giả sử ứng dụng lưu tên một sản phẩm, thẻ nội dung hoặc một mục từ điển trong `Map<String, ...>`. Người dùng nhập `"  Café  "`, sau đó tìm bằng `"café"`, `"CAFÉ"` hay chuỗi Unicode `"Cafe\u0301"` (chữ `e` rồi dấu sắc kết hợp). Ứng dụng có thể muốn tất cả lần tra cứu này trỏ đến **cùng mục**, nhưng khi hiển thị lại muốn giữ nguyên tên người dùng đã đặt, gồm chữ hoa, dấu, khoảng trắng hoặc cách viết thương hiệu.

Đó là hai yêu cầu khác nhau:

- **Khóa tra cứu đã chuẩn hóa (normalized/canonical key)**: biểu diễn được định nghĩa thống nhất để so sánh, tìm kiếm, nhóm hoặc phát hiện trùng lặp.
- **Văn bản hiển thị (display text)**: chuỗi gốc hoặc phiên bản đã được người dùng duyệt để hiển thị lại đúng ý nghĩa và hình thức mong muốn.

**Không nên thay văn bản hiển thị bằng khóa đã chuẩn hóa.** Phép chuẩn hóa có thể làm mất thông tin không khôi phục được: chẳng hạn chữ hoa/thường, dấu cách đầu/cuối, hoặc một số phân biệt ký tự nếu chính sách chuẩn hóa quá mạnh.

Ngữ cảnh của bài là **dùng `String` làm khóa trong các collection Java**, đặc biệt `HashMap`, `HashSet` và `TreeMap`. Tùy bài toán, không phải dữ liệu nào cũng nên được chuẩn hóa: tên hiển thị, tên tài khoản, mã sản phẩm, mã định danh và mật khẩu có chính sách khác nhau.

## 2. `String.equals()` và khóa trong `HashMap`

`String.equals()` so sánh nội dung các chuỗi theo chính xác các đơn vị mã UTF-16. `HashMap<String, V>` dựa vào `hashCode()` và `equals()` của khóa khi thêm hoặc tra cứu phần tử; bản thân `HashMap` **không tự bỏ khoảng trắng, chuyển chữ thường hoặc chuẩn hóa Unicode**.

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> prices = new HashMap<>();
prices.put("Café", 100);

System.out.println(prices.get("Café"));   // 100
System.out.println(prices.get("café"));   // null
System.out.println(prices.get("Cafe\u0301")); // null
```

`"Café"` ở ví dụ thứ nhất chứa ký tự `é` dựng sẵn; `"Cafe\u0301"` chứa `e` và dấu sắc kết hợp. Chúng có thể trông giống nhau khi render nhưng không nhất thiết `equals()` nhau. Chuỗi chữ thường `"café"` cũng khác `"Café"`.

Tương tự, `HashSet<String>` có thể giữ nhiều chuỗi nhìn giống nhau vì từng chuỗi vẫn là phần tử khác nhau theo `equals()`. Muốn các biến thể được xem là cùng khóa thì phải **định nghĩa và áp dụng một quy tắc chuẩn hóa** trước khi thao tác với collection.

## 3. Các tầng chuẩn hóa: chọn theo nhu cầu

### 3.1. Khoảng trắng ở đầu/cuối

`String.strip()` (Java 11+) bỏ các ký tự đầu/cuối mà `Character.isWhitespace` xem là khoảng trắng. `trim()` dùng tiêu chí cũ hơn (`char <= U+0020`), nên hai phương thức không tương đương với mọi ký tự Unicode.

```java
String raw = "  Java  ";
String keyPart = raw.strip();

System.out.println(raw.length());     // 8
System.out.println(keyPart.length()); // 4
```

Không phải mọi loại dấu cách Unicode đều được `strip()` loại bỏ; ví dụ non-breaking space (`U+00A0`) cần chính sách riêng nếu dữ liệu của bạn xem nó là khoảng trắng biên. Không nên tự động xóa **mọi** dấu cách trong chuỗi vì `"New York"` và `"NewYork"` có thể mang ý nghĩa khác nhau.

### 3.2. Chữ hoa/thường

Với khóa tìm kiếm cần hành vi nhất quán, `toLowerCase(Locale.ROOT)` thường phù hợp hơn `toLowerCase()`, vì phiên bản không truyền `Locale` dùng locale mặc định của quá trình chạy và có thể thay đổi kết quả giữa các môi trường.

```java
import java.util.Locale;

String keyPart = "JAVA".toLowerCase(Locale.ROOT);
System.out.println(keyPart); // java
```

`Locale.ROOT` giúp có một quy tắc chung, nhưng **chuyển chữ thường chưa phải Unicode case folding đầy đủ**. Đừng mặc định rằng mọi cặp chuỗi mà người dùng coi là tương đương ở các ngôn ngữ đều trở thành cùng khóa. Chẳng hạn xử lý các chữ cái liên quan đến `I/i` trong tiếng Thổ Nhĩ Kỳ có quy tắc ngôn ngữ riêng. Nếu ứng dụng cần phân loại từ vựng theo ngôn ngữ, phải xác định và kiểm thử chính sách theo ngôn ngữ đó.

### 3.3. Unicode normalization: NFC và NFKC

`java.text.Normalizer` cung cấp các dạng chuẩn hóa Unicode, đặc biệt:

| Dạng | Ý nghĩa tiêu biểu | Khi nào cân nhắc |
| --- | --- | --- |
| `Normalizer.Form.NFC` | Chuẩn hóa **tương đương chính tắc** và ưu tiên dạng ký tự kết hợp sẵn | Phù hợp khi muốn thống nhất các cách mã hóa Unicode tương đương mà vẫn giữ nhiều phân biệt có ý nghĩa |
| `Normalizer.Form.NFD` | Tách thành dạng phân rã chính tắc | Có ích cho một số bước xử lý ký tự có dấu; không phải thao tác mặc định để làm khóa |
| `Normalizer.Form.NFKC` | Chuẩn hóa **tương đương tương thích** rồi kết hợp | Chỉ dùng khi nghiệp vụ chủ ý coi một số dạng trình bày hoặc ký tự tương thích là cùng nhau |
| `Normalizer.Form.NFKD` | Phân rã tương thích | Dùng cho mục đích chuyên biệt; có thể làm mất các phân biệt về cách biểu diễn |

NFC thống nhất hai cách biểu diễn chữ `é`:

```java
import java.text.Normalizer;

String composed = "\u00E9";   // é: một code point
String decomposed = "e\u0301"; // e và dấu sắc kết hợp

System.out.println(composed.equals(decomposed)); // false
System.out.println(
        Normalizer.normalize(composed, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC))
); // true
```

**NFC không xóa dấu.** Theo chính sách NFC, `"cafe"` và `"café"` vẫn khác nhau. NFKC có thể gộp thêm một số biểu diễn tương thích (chẳng hạn ký tự toàn chiều rộng với ký tự ASCII tương ứng), nên không được coi là lựa chọn luôn an toàn cho tên riêng, mã nhận diện hoặc nội dung người dùng.

Việc bỏ dấu hoàn toàn là **một chính sách khác**, có thể tạo va chạm không mong muốn giữa các từ hoặc tên khác nghĩa. Không trộn chính sách đó vào NFC nếu không có yêu cầu rõ ràng.

## 4. Một hàm chuẩn hóa khóa có chủ đích

Ví dụ sau chọn chính sách cụ thể cho một mục danh mục được tìm kiếm không phân biệt chữ hoa/thường và chấp nhận Unicode tương đương chính tắc:

1. Bỏ khoảng trắng đầu/cuối theo `strip()`.
2. Chuyển sang chữ thường theo `Locale.ROOT`.
3. Chuẩn hóa NFC **sau** bước chuyển chữ thường, bảo đảm dạng kết quả cuối cùng được chuẩn hóa chính tắc.

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

static String keyOf(String input) {
    Objects.requireNonNull(input, "input");
    String stripped = input.strip();
    String lower = stripped.toLowerCase(Locale.ROOT);
    return Normalizer.normalize(lower, Normalizer.Form.NFC);
}
```

Đây là **đoạn phương thức minh họa**, đặt bên trong một lớp Java. Nó không phải quy tắc bắt buộc cho tất cả hệ thống. Mỗi hệ thống cần quyết định riêng liệu có được bỏ khoảng trắng, bỏ phân biệt chữ hoa/thường, xử lý tương đương Unicode hoặc chấp nhận khóa rỗng hay không.

Một vài tính chất quan trọng:

- `keyOf("  Café ")` và `keyOf("cafe\u0301")` cho cùng khóa theo chính sách trên.
- `keyOf("Cafe")` và `keyOf("Café")` **khác nhau** vì NFC không xóa dấu.
- Hàm không chỉnh sửa `input` vì `String` bất biến; nó trả về một chuỗi đại diện dùng trong cấu trúc dữ liệu.
- Giá trị `null` không là khóa hợp lệ ở ví dụ: `Objects.requireNonNull` từ chối rõ ràng thay vì tạo khóa đặc biệt ngoài ý muốn.
- Sau `strip()`, chuỗi có thể trở thành `""`. Nếu khóa rỗng không hợp lệ cho nghiệp vụ, hãy kiểm tra và trả lỗi trước khi lưu.

Cần **áp dụng đúng cùng hàm** cho cả thao tác ghi, tìm kiếm, cập nhật và xóa. Nếu chỉ chuẩn hóa khi `put` nhưng không chuẩn hóa khi `get`, việc tra cứu vẫn thất bại.

## 5. Thiết kế dữ liệu: lưu khóa và văn bản hiển thị riêng

Một mô hình đơn giản sử dụng `Map<String, Item>`:

```java
record Item(String displayName) {}

Map<String, Item> items = new HashMap<>();

String submittedName = "  Cafe\u0301  ";
String lookupKey = keyOf(submittedName);

items.put(lookupKey, new Item(submittedName));
Item found = items.get(keyOf("CAF\u00C9"));
```

Trong ví dụ này:

- **Khóa trong `Map`** là kết quả `keyOf(submittedName)`; nó dùng cho so khớp.
- **Giá trị `Item.displayName`** chứa đúng `submittedName` ban đầu, kể cả hai dấu cách mỗi bên và dạng Unicode phân rã.
- Khi hiển thị, lấy `found.displayName()`, không dùng chuỗi khóa từ `Map` làm nhãn.
- Nếu muốn loại bỏ dấu cách *trên giao diện*, hãy xác định yêu cầu đó riêng cho dữ liệu hiển thị; không suy diễn từ phép chuẩn hóa khóa.

Trong một ứng dụng lớn hơn, có thể dùng `record Item(String id, String displayName, ...)` với **ID ổn định** riêng. Chuỗi chuẩn hóa phù hợp làm khóa chỉ mục tìm kiếm hoặc nhóm; không nhất thiết nên là ID vĩnh viễn của đối tượng.

### Khi có nhiều đầu vào cùng khóa

Ví dụ `"  Café  "` và `"cafe\u0301"` có cùng khóa đã chuẩn hóa. Nếu dùng:

```java
items.put(keyOf(submittedName), new Item(submittedName));
```

cho nhiều lượt thêm, lần thêm sau có thể **ghi đè giá trị** ở cùng khóa. `HashMap.put` trả về giá trị cũ (nếu có), nhưng nếu bỏ qua giá trị trả về thì rất dễ mất nhãn hiển thị cũ.

Một số chiến lược rõ ràng hơn:

- **Khóa phải duy nhất:** dùng `putIfAbsent` hoặc kiểm tra va chạm trong tầng lưu trữ và báo cho người dùng khi tên đã tồn tại.
- **Nhiều mục có thể cùng khóa tìm kiếm:** dùng `Map<String, List<Item>>` hoặc chỉ mục đảo để một khóa trả về nhiều đối tượng.
- **Mục có ID riêng:** lưu bản ghi theo ID, còn khóa đã chuẩn hóa chỉ để tìm danh sách ID; tên hiển thị không phải nguồn nhận diện duy nhất.

Đối với hệ thống nhiều luồng hoặc có cơ sở dữ liệu, phép kiểm tra trước rồi ghi sau **không tự bảo đảm tính nguyên tử**. `HashMap` không thread-safe cho cập nhật đồng thời. `putIfAbsent` trên `HashMap` hữu ích trong đoạn mã một luồng nhưng không thay thế giao dịch/unique constraint của cơ sở dữ liệu hoặc cấu trúc đồng thời phù hợp.

## 6. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo tệp `KeyNormalizationDemo.java`:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class KeyNormalizationDemo {

    record Item(String displayName) {}

    static String keyOf(String input) {
        Objects.requireNonNull(input, "input");
        return Normalizer.normalize(
                input.strip().toLowerCase(Locale.ROOT),
                Normalizer.Form.NFC
        );
    }

    public static void main(String[] args) {
        // Cafe + dấu sắc kết hợp; có hai khoảng trắng mỗi bên.
        String original = "  Cafe\u0301  ";
        String query = "CAF\u00C9";

        Map<String, Item> items = new HashMap<>();
        items.put(keyOf(original), new Item(original));

        System.out.println(
                "Same key: " + keyOf(original).equals(keyOf(query))
        );
        System.out.println(
                "Found: " + (items.get(keyOf(query)) != null)
        );
        System.out.println(
                "Display preserved: "
                        + items.get(keyOf(query)).displayName().equals(original)
        );

        Item existing = items.putIfAbsent(
                keyOf(query), new Item(query)
        );
        System.out.println("Collision: " + (existing != null));
        System.out.println("Size: " + items.size());
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 KeyNormalizationDemo.java
java KeyNormalizationDemo
```

Kết quả chính xác:

```text
Same key: true
Found: true
Display preserved: true
Collision: true
Size: 1
```

**Vì sao?** `original` có khoảng trắng và dạng Unicode phân rã; `query` viết hoa và dùng `É` dựng sẵn. Sau `strip()`, `toLowerCase(Locale.ROOT)` và `Normalizer.Form.NFC`, hai khóa bằng nhau. `Map.get` tìm được giá trị từ khóa chuẩn hóa; trong khi `displayName` vẫn bằng đúng chuỗi gốc, không bị đổi chữ, cắt khoảng trắng hoặc chuyển dạng Unicode. `putIfAbsent` phát hiện đã có một mục ở khóa đó và không thay giá trị, nên kích thước `Map` vẫn là `1`.

Ở đây `record` được khai báo lồng trong lớp; cú pháp hoạt động trong Java 17+.

## 7. `HashSet`, `TreeMap` và comparator

### `HashSet<String>`

Với tập hợp cần coi các biến thể là cùng một phần tử, lưu **khóa chuẩn hóa**:

```java
Set<String> keys = new HashSet<>();
keys.add(keyOf("  Café "));
keys.add(keyOf("cafe\u0301"));

System.out.println(keys.size()); // 1
```

Nếu cần hiển thị các nhãn do người dùng nhập, đừng lấy trực tiếp các phần tử của tập `keys` làm nội dung hiển thị. Hãy lưu chúng ở cấu trúc khác hoặc gắn vào đối tượng dữ liệu.

### `TreeMap<String, V>` và `TreeSet<String>`

Các collection dạng cây dùng `compareTo` hoặc `Comparator` để xác định **thứ tự và khi nào khóa được coi là bằng nhau** (khi `compare(a,b) == 0`). Điều này khác với cơ chế `equals/hashCode` của `HashMap/HashSet`.

Ví dụ:

```java
Map<String, Integer> sorted = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
sorted.put("Java", 1);
sorted.put("JAVA", 2);

System.out.println(sorted.size()); // 1
System.out.println(sorted.get("java")); // 2
```

Comparator trên so sánh không phân biệt hoa/thường theo quy tắc của Java, nhưng **không thay thế một chính sách chuẩn hóa đầy đủ**: nó không tự loại bỏ khoảng trắng biên, và không bảo đảm tương đương Unicode chính tắc giống NFC. Đừng cho rằng một `TreeMap` với comparator bất kỳ có cùng quy tắc đồng nhất khóa như `HashMap` lưu các khóa đã chuẩn hóa.

Nếu muốn dùng cùng một quy tắc giữa các collection, thường dễ hiểu nhất là **lưu và so sánh chính các khóa được tạo bởi `keyOf`**. Khi thiết kế comparator tùy chỉnh, phải bảo đảm tính nhất quán, phản xạ và bắc cầu của quan hệ sắp xếp; comparator coi hai khóa là bằng nhau có thể làm collection chỉ giữ một trong hai mục.

## 8. Khi không nên chuẩn hóa khóa theo cách này

Định nghĩa `keyOf` ở trên phù hợp với ví dụ **tìm kiếm tên trong danh mục**; nó không phải bộ quy tắc dùng cho mọi `String`.

| Dữ liệu | Hướng xử lý cần cân nhắc |
| --- | --- |
| Nhãn hiển thị, tên thương hiệu, tên tác phẩm | Bảo toàn nội dung đã chấp nhận; nếu cần tìm kiếm, lưu thêm khóa chỉ mục |
| Mã định danh phân biệt hoa/thường, token bí mật, chữ ký, dữ liệu cần kiểm chứng từng byte | Không tự bỏ dấu cách, hạ chữ, chuẩn hóa Unicode; thực hiện đúng đặc tả của hệ thống |
| Tên đăng nhập mà sản phẩm quy định không phân biệt chữ hoa/thường | Xác định chính sách từ lúc tạo tài khoản; áp dụng ở đăng ký, đăng nhập, thay đổi tên và kiểm tra trùng |
| Tìm kiếm tiếng Việt không phân biệt dấu | Cần đặc tả riêng cho bỏ dấu, chữ `đ`, chuẩn hóa khoảng trắng và xử lý va chạm; NFC tự nó không bỏ dấu |
| Tìm kiếm theo ngôn ngữ tự nhiên | Cân nhắc `Collator` với locale phù hợp, full-text search hoặc chỉ mục chuyên dụng; không mặc định lowercase luôn đúng |
| Dữ liệu Unicode có ký tự dễ gây nhầm hình dạng | NFC không giải quyết toàn bộ vấn đề ký tự trông giống nhau (confusables); cần thêm kiểm tra phù hợp nếu đây là rủi ro nghiệp vụ |

**Cẩn thận với chuẩn hóa mất dữ liệu.** `strip()` bỏ khoảng trắng ở hai đầu; `toLowerCase(Locale.ROOT)` bỏ phân biệt kiểu chữ; `NFKC` và bỏ dấu có thể gộp thêm các đầu vào khác nhau. Nếu hai mục phân biệt có ý nghĩa nghiệp vụ rơi vào cùng khóa thì phải xử lý va chạm có chủ đích, không tùy tiện ghi đè hay tự gộp bản ghi.

Đặc biệt, xác định chính sách **trước khi có dữ liệu thật**. Nếu sau này sửa hàm chuẩn hóa, khóa cũ trong bộ nhớ, tệp, cache hoặc cơ sở dữ liệu có thể không khớp khóa mới. Hãy thiết kế việc tính lại chỉ mục và giải quyết va chạm khi cần migration; với hệ thống lưu trữ lâu dài có thể ghi phiên bản chính sách để hỗ trợ chuyển đổi an toàn.

## 9. Những lỗi thường gặp

1. **Chỉ chuẩn hóa lúc lưu.** `map.put(keyOf(name), item)` nhưng `map.get(userInput)` khiến các biến thể không tìm thấy. Phải dùng `map.get(keyOf(userInput))`.
2. **Dùng khóa làm văn bản hiển thị.** Một nhãn do người dùng đặt như `"  Cafe\u0301  "` bị đổi thành `"café"` nếu luôn hiển thị khóa. Lưu nhãn gốc ở giá trị hoặc trường riêng.
3. **Cho rằng `equalsIgnoreCase` hoặc `CASE_INSENSITIVE_ORDER` là Unicode normalization.** Chúng giải quyết một phần khác của bài toán; vẫn cần xác định dạng Unicode, khoảng trắng và locale.
4. **Tự động dùng `toLowerCase()`.** Locale mặc định có thể thay đổi theo máy/chạy ứng dụng. Với chính sách khóa độc lập locale, truyền `Locale.ROOT`.
5. **Xem `NFKC`, bỏ dấu và NFC là như nhau.** Chúng có phạm vi biến đổi khác nhau; chuẩn hóa rộng hơn có thể làm hai tên riêng hoặc mã khác nhau trở thành cùng khóa.
6. **Ghi đè im lặng khi hai nhãn cùng khóa.** Nếu tính duy nhất không được đảm bảo, hãy giữ danh sách mục hoặc báo rõ va chạm.
7. **Dùng tên hiển thị chuẩn hóa làm ID vĩnh viễn.** Tên có thể đổi và chính sách chuẩn hóa có thể đổi. Với bản ghi dài hạn, thường cần một ID độc lập ổn định.
8. **Thay đổi chính sách mà không di chuyển dữ liệu.** Key ở cache/database tính bằng quy tắc cũ có thể gây tìm thiếu hoặc tạo trùng sau nâng cấp.

## 10. Tự kiểm tra

**Câu 1.** Với hàm `keyOf` ở trên, `keyOf("Cafe")` có bằng `keyOf("Café")` không?

**Đáp án:** Không. NFC thống nhất dạng ký tự tương đương chính tắc, nhưng không xóa dấu sắc của `é`.

**Câu 2.** Vì sao lưu `Map<String, Item>` thường tốt hơn chỉ lưu `Set<String>` các khóa chuẩn hóa khi ứng dụng có yêu cầu hiển thị nguyên văn?

**Đáp án:** `Map` giữ khóa để tra cứu và một giá trị mang nhãn hiển thị riêng. Chỉ lưu khóa đã chuẩn hóa sẽ không đủ thông tin để khôi phục chữ hoa, khoảng trắng hoặc những khác biệt đã bị bỏ.

**Câu 3.** Hai tên `"Café"` và `"cafe\u0301"` trùng sau chuẩn hóa. Có nên dùng `put` để mục sau ghi đè mục trước?

**Đáp án:** Chỉ khi nghiệp vụ chủ ý cho phép thay thế. Nếu cần duy nhất, báo trùng; nếu cần nhiều mục, lưu nhiều giá trị theo một khóa; nếu cần ID, gắn từng bản ghi với ID ổn định.

**Câu 4.** Có nên chuẩn hóa mật khẩu bằng `strip().toLowerCase(Locale.ROOT)` theo bài này không?

**Đáp án:** Không áp dụng tự động. Mật khẩu/token cần giữ đúng quy ước đầu vào của cơ chế xác thực; việc biến đổi thêm có thể thay đổi ý nghĩa bí mật và hành vi xác minh.

## Ghi nhớ

**Khóa chuẩn hóa dùng để xác định “khi nào các chuỗi được coi là cùng nhau”; văn bản hiển thị dùng để giữ “người dùng muốn nhìn thấy chuỗi như thế nào”.** Với `String` trong collection, hãy định nghĩa một hàm `keyOf` phù hợp nghiệp vụ, áp dụng nhất quán trên mọi đường đọc/ghi, xử lý va chạm rõ ràng và lưu riêng nhãn hiển thị cần bảo toàn.
