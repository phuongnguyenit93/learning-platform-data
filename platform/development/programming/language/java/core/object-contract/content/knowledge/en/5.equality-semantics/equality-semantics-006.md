# So sánh không phân biệt hoa thường và quy tắc nghiệp vụ tường minh

## 1. Vấn đề: “bằng nhau” phụ thuộc vào quy tắc nào?

Trong Java, hai chuỗi có cùng chữ nhưng khác chữ hoa/chữ thường có thể được xem là bằng nhau hoặc khác nhau **tùy ngữ cảnh nghiệp vụ**:

- Mã coupon `Save10` và `SAVE10` có thể là **hai mã khác nhau** nếu hệ thống quy định mã phân biệt hoa/thường.
- Tên đăng nhập `Alice_7` và `alice_7` có thể được xem là **cùng một username** nếu hệ thống công bố username không phân biệt hoa/thường.
- Nhãn tìm kiếm `Java` và `JAVA` có thể được khớp không phân biệt hoa/thường, nhưng thao tác “khớp khi tìm kiếm” chưa chắc đã là quy tắc để xác định **danh tính** của đối tượng.
- Tên người, văn bản tự nhiên và từ ngữ đa ngôn ngữ có thể cần quy tắc phụ thuộc ngôn ngữ, dấu, cách viết và mục đích sử dụng.

Vì vậy, câu hỏi đầu tiên không phải “dùng `equalsIgnoreCase` hay `equals`?” mà là **trường dữ liệu này cần quan hệ bằng nhau nào?** Chỉ sau khi xác định quy tắc nghiệp vụ mới chọn API Java, bước chuẩn hóa và cách lưu/truy vấn.

Điểm giới hạn quan trọng: `String.equals(Object)` vẫn phân biệt hoa/thường. Gọi `equalsIgnoreCase` cho một thao tác không làm thay đổi định nghĩa `equals` của `String`; muốn lớp giá trị tự coi hai biểu diễn là bằng nhau, phải thiết kế `equals` và `hashCode` của **lớp đó** một cách nhất quán.

## 2. Những công cụ Java thường gặp

| Công cụ | Điều nó kiểm tra | Phù hợp khi nào |
| --- | --- | --- |
| `left.equals(right)` | Nội dung chuỗi bằng nhau theo `String.equals`, phân biệt hoa/thường. | Mã, khóa, giá trị có quy tắc khớp chính xác. |
| `left.equalsIgnoreCase(right)` | So sánh ký tự không phân biệt hoa/thường theo quy tắc Unicode mà Java áp dụng, **không dựa vào `Locale` được truyền vào**. | So khớp chuỗi không phân biệt hoa/thường khi quy tắc Java này đúng với nghiệp vụ. |
| `left.toLowerCase(Locale.ROOT)` | Tạo một chuỗi đã chuyển về chữ thường theo quy tắc locale trung lập. | Một bước của chiến lược tạo **khóa chuẩn hóa** được thiết kế trước. |
| `String.CASE_INSENSITIVE_ORDER` | `Comparator<String>` sắp thứ tự chuỗi không phân biệt hoa/thường theo quy tắc tương thích với `compareToIgnoreCase`. | Tập/cây sắp xếp có chính sách coi chữ hoa/thường là cùng khóa. |
| `Collator` | So sánh theo quy tắc đối chiếu ngôn ngữ, locale và mức phân biệt (strength). | Sắp xếp hoặc tìm kiếm văn bản theo ngôn ngữ của người dùng. |
| `Normalizer.normalize(text, Form.NFC)` | Chuẩn hóa những biểu diễn Unicode tương đương về một dạng chuẩn. | Khi dữ liệu có thể chứa ký tự Unicode dạng tổ hợp/dạng dựng sẵn. |

Các công cụ trên **không hoàn toàn thay thế được nhau**. Ví dụ, chuyển hai chuỗi sang chữ thường rồi gọi `equals` không luôn trùng với `equalsIgnoreCase` trên mọi ký tự Unicode. `Collator` còn có thể xem hai chuỗi chỉ khác dấu là tương đương ở một mức so sánh, điều mà một chính sách “bỏ qua chữ hoa/thường nhưng giữ dấu” không mong muốn.

### `equals` so với `equalsIgnoreCase`

```java
"Java".equals("JAVA");            // false
"Java".equalsIgnoreCase("JAVA");  // true
"Java".equalsIgnoreCase(null);    // false
```

Đây là **các biểu thức minh họa**, không phải chương trình Java độc lập. Nếu tham chiếu bên trái là `null` thì cả lời gọi `left.equals(...)` lẫn `left.equalsIgnoreCase(...)` đều gây `NullPointerException`; phải quy định rõ xử lý đầu vào `null` và dùng kiểm tra hoặc tiện ích phù hợp.

Không nhầm “không phân biệt hoa/thường” với “không phân biệt dấu”, “bỏ khoảng trắng”, “không phân biệt cách viết Unicode” hoặc “gần giống khi tìm kiếm”. Mỗi yêu cầu là một quy tắc riêng.

## 3. Thiết kế quy tắc nghiệp vụ một cách tường minh

Trước khi lập trình, cần trả lời các câu hỏi sau cho **từng loại dữ liệu**:

1. **Đối tượng so sánh là gì?** Username, coupon, SKU, mã đơn hàng, nhãn hiển thị hay từ khóa tìm kiếm? Hai trường trong cùng một đối tượng có thể có quy tắc khác nhau.
2. **Phân biệt chữ hoa/thường hay không?** Nếu không, dùng so khớp không phân biệt case trực tiếp hay tạo khóa chuẩn hóa để lưu trữ?
3. **Có bỏ khoảng trắng đầu/cuối không?** Nếu có, bỏ theo quy tắc nào? `strip()` và `trim()` không đồng nghĩa trên mọi ký tự; đừng tự loại bỏ khoảng trắng bên trong.
4. **Chấp nhận ký tự nào?** Chỉ ASCII (`A-Z`, `a-z`, số, dấu gạch dưới) hay Unicode nhiều ngôn ngữ? Miền ký tự quyết định độ phức tạp của chuẩn hóa.
5. **Có xét dấu và chuẩn hóa Unicode không?** `é` dựng sẵn và `e` + dấu sắc kết hợp có thể biểu diễn cùng văn bản nhưng là hai dãy mã khác nhau.
6. **Locale có ảnh hưởng không?** Khớp mã máy thường cần quy tắc độc lập với locale; tên hoặc văn bản hiển thị có thể cần locale người dùng.
7. **`null`, chuỗi rỗng và chuỗi chỉ có khoảng trắng có hợp lệ không?** Trả về `false`, coi cả hai `null` là bằng nhau hay từ chối đầu vào đều là lựa chọn nghiệp vụ cần công bố.
8. **Định nghĩa danh tính có ổn định không?** Nếu giá trị quyết định `equals`/`hashCode` được phép thay đổi, đối tượng đang làm khóa `HashMap`/`HashSet` sẽ có rủi ro mất khả năng tra cứu.

Ví dụ một đặc tả username có thể viết rõ:

> “Chấp nhận 3–20 ký tự ASCII, chỉ gồm chữ cái, chữ số và `_`. Bỏ khoảng trắng đầu/cuối trước khi kiểm tra. Username là duy nhất không phân biệt chữ hoa/chữ thường ASCII. Khóa lưu/truy vấn là chữ thường theo `Locale.ROOT`. Không chấp nhận các kiểu chữ Unicode khác hoặc cách viết có dấu.”

Đây chỉ là **ví dụ về chính sách**. Nó cho kết quả dự đoán được vì dữ liệu hợp lệ chỉ nằm trong ASCII; hệ thống hỗ trợ username quốc tế cần đặc tả, kiểm thử và chính sách Unicode riêng.

Chính sách tên đăng nhập không tự áp dụng cho email, tên khách hàng hoặc mã hàng. Với địa chỉ email, phần domain không phân biệt hoa/thường, còn quy tắc xử lý phần local có thể tùy nhà cung cấp và ứng dụng; không được tự động xóa dấu chấm, dấu cộng hoặc đổi toàn bộ địa chỉ thành chữ thường rồi coi đó là danh tính chuẩn cho mọi hệ thống.

## 4. Ví dụ Java 17+ chạy độc lập

Chương trình sau minh họa **ba chính sách tách biệt**:

- `sameTag` cho phép khớp nhãn không phân biệt hoa/thường bằng `equalsIgnoreCase`.
- `sameCouponCode` dùng khớp chính xác, phân biệt hoa/thường.
- `Username` là **lớp giá trị bất biến**; `equals`/`hashCode` cùng dựa trên một khóa username ASCII đã chuẩn hóa. Đây là ví dụ miền giá trị, không mặc định rằng danh tính của mọi tài khoản người dùng phải dựa trên username.

Lưu đúng tệp `CasePolicyDemo.java`:

```java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class CasePolicyDemo {
    static boolean sameTag(String left, String right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.equalsIgnoreCase(right);
    }

    static boolean sameCouponCode(String left, String right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.equals(right);
    }

    static String canonicalUsername(String raw) {
        Objects.requireNonNull(raw, "raw");

        String cleaned = raw.strip();
        if (!cleaned.matches("[A-Za-z0-9_]{3,20}")) {
            throw new IllegalArgumentException("Invalid username");
        }
        return cleaned.toLowerCase(Locale.ROOT);
    }

    static final class Username {
        private final String key;

        Username(String raw) {
            this.key = canonicalUsername(raw);
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Username that
                    && key.equals(that.key));
        }

        @Override
        public int hashCode() {
            return key.hashCode();
        }
    }

    public static void main(String[] args) {
        System.out.println("tag ignore case: "
                + sameTag("Java", "JAVA"));
        System.out.println("coupon exact: "
                + sameCouponCode("Save10", "SAVE10"));
        System.out.println("canonical username: "
                + canonicalUsername("  Alice_7  "));

        Username a = new Username("Alice_7");
        Username b = new Username("alice_7");
        Username c = new Username("ALICE_7");
        System.out.println("username equal: " + a.equals(b));
        System.out.println("reflexive: " + a.equals(a));
        System.out.println("symmetric: " + (a.equals(b) == b.equals(a)));
        System.out.println("transitive: "
                + (!a.equals(b) || !b.equals(c) || a.equals(c)));
        System.out.println("hash agreement: "
                + (a.hashCode() == b.hashCode()));

        Set<Username> usernames = new HashSet<>();
        usernames.add(a);
        System.out.println("HashSet contains b: " + usernames.contains(b));

        Set<String> exactStrings = new HashSet<>();
        exactStrings.add("Java");
        exactStrings.add("JAVA");

        Set<String> ignoreCaseStrings =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        ignoreCaseStrings.add("Java");
        ignoreCaseStrings.add("JAVA");

        System.out.println("HashSet strings size: " + exactStrings.size());
        System.out.println("TreeSet strings size: " + ignoreCaseStrings.size());
        System.out.println("sharp-s expansion: "
                + "straße".equalsIgnoreCase("STRASSE"));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 CasePolicyDemo.java
java CasePolicyDemo
```

Đầu ra:

```text
tag ignore case: true
coupon exact: false
canonical username: alice_7
username equal: true
reflexive: true
symmetric: true
transitive: true
hash agreement: true
HashSet contains b: true
HashSet strings size: 2
TreeSet strings size: 1
sharp-s expansion: false
```

**Giải thích:**

- `sameTag("Java", "JAVA")` trả về `true` vì thao tác so nhãn được phép bỏ qua chữ hoa/thường. `sameCouponCode("Save10", "SAVE10")` trả về `false` vì chính sách coupon phân biệt case.
- `canonicalUsername` loại bỏ khoảng trắng ở biên theo chính sách ví dụ, sau đó **kiểm tra miền ASCII trước khi đổi chữ thường**. Vì chỉ cho phép ASCII, thao tác `toLowerCase(Locale.ROOT)` không gặp các tình huống mở rộng Unicode khó kiểm soát.
- `Username` là lớp `final` với trường `key` bất biến. Ba đối tượng `a`, `b`, `c` có cùng khóa chuẩn hóa, nên `equals` phản xạ, đối xứng và bắc cầu trong bộ dữ liệu ví dụ. Kết quả in ra chỉ kiểm tra bộ dữ liệu này; việc đúng hợp đồng còn dựa vào định nghĩa khóa và các phép thử khác.
- `hashCode` tính từ cùng `key` như `equals`. Vì thế `HashSet` có thể nhận ra `b` là cùng giá trị với `a` đã lưu.
- `HashSet<String>` dùng `String.equals`/`hashCode`, nên chứa cả `Java` và `JAVA`. `TreeSet<String>` ở đây dùng comparator không phân biệt case, nên chỉ giữ một phần tử đối với cặp đó. Comparator có quan hệ tương đương **khác với `String.equals`**; đây là quyết định về semantics của tập, cần biết trước khi dùng.
- `"straße"` và `"STRASSE"` có số ký tự khác nhau, nên `equalsIgnoreCase` trả về `false`. Nó không thực hiện mọi phép chuyển đổi nhiều ký tự được dùng trong một số khái niệm Unicode case folding.

## 5. Vì sao chuẩn hóa khóa giúp thiết kế `equals` đúng?

Giả sử chỉ so sánh hai đối tượng `Username` theo chuỗi gốc bằng `String.equals`: `"Alice_7"` và `"alice_7"` khác nhau. Nhưng nghiệp vụ đã xác nhận chúng là cùng username. Vì thế lớp giá trị lưu **khóa đại diện cho quan hệ bằng nhau**, ví dụ `"alice_7"`, và dùng khóa đó nhất quán.

Nếu mọi đầu vào được chấp nhận đi qua **cùng một hàm chuẩn hóa xác định**, ta định nghĩa:

```text
x ~ y  khi và chỉ khi  canonical(x).equals(canonical(y))
```

Đó là phép bằng nhau của các khóa chuỗi chuẩn hóa; nó có phản xạ, đối xứng và bắc cầu. Quy tắc này dễ kiểm chứng hơn một loạt điều kiện “gần giống” được viết vào `equals`. Nhớ rằng quan hệ tương đương chỉ xét **các giá trị hợp lệ trong miền dữ liệu**; đầu vào không hợp lệ nên được xử lý theo hợp đồng constructor/API.

Quy tắc quan trọng nhất khi triển khai value object:

1. **Định nghĩa một hàm chuẩn hóa thống nhất** cho mọi đường tạo dữ liệu, nhập khẩu, API, batch job và tra cứu.
2. **Không tách tiêu chí `equals` và `hashCode`.** Nếu `equals` bỏ qua chữ hoa/thường còn `hashCode` dựa vào chuỗi gốc, hai đối tượng bằng nhau có thể sinh hash khác nhau và vi phạm hợp đồng.
3. **Khóa phải ổn định** khi đối tượng được dùng làm phần tử `HashSet` hoặc khóa `HashMap`. Trường `final` của lớp giá trị là một lựa chọn an toàn.
4. **Định nghĩa rõ miền kiểu**. Ví dụ `Username` chỉ bằng một `Username` khác; nó không so bằng một `String` dù nội dung giống nhau. Việc cho phép `Username.equals("alice_7")` thường phá đối xứng vì `String.equals(Username)` trả về `false`.
5. **Cùng quy tắc ở ứng dụng và nơi lưu trữ**. Nếu ứng dụng chuẩn hóa username nhưng database index chỉ kiểm tra chuỗi gốc, hai yêu cầu tạo username có thể vượt qua kiểm tra rồi gây trùng danh tính. Dùng khóa đã chuẩn hóa, unique constraint và thao tác ghi phù hợp để bảo đảm duy nhất, kể cả có request đồng thời.

Chú ý: một **thực thể tài khoản** có thể cần định danh bằng `userId` ổn định chứ không phải username nếu tên đăng nhập được phép đổi. Lớp `Username` ở ví dụ là *value object đại diện cho tên đăng nhập*, không phải toàn bộ thực thể người dùng. Quy tắc `equals` của entity phải phản ánh danh tính thực tế của entity đó.

## 6. Unicode, locale và những trường hợp dễ hiểu sai

### 6.1. Không phân biệt hoa/thường không phải full Unicode case folding

`String.equalsIgnoreCase` là phép so sánh không phân biệt chữ hoa/thường theo cách Java quy định. Nó **không tự động** chuẩn hóa Unicode, không chạy quy trình full Unicode case folding trên chuỗi và không dùng một locale do người dùng chỉ định.

Ví dụ `"straße".equalsIgnoreCase("STRASSE")` trả về `false` vì độ dài hai chuỗi khác nhau. Không được suy từ ví dụ ASCII `"java"` so với `"JAVA"` rằng mọi cặp cách viết tương đương theo ngôn ngữ tự nhiên đều được Java xem là giống nhau.

Nếu nghiệp vụ hỗ trợ username hoặc khóa Unicode quốc tế, cần có **chính sách canonicalization riêng, phiên bản quy tắc rõ ràng và test với dữ liệu đại diện**. `toLowerCase(Locale.ROOT)` đơn lẻ không tương đương với một thuật toán nhận diện danh tính Unicode được chuẩn hóa đầy đủ.

### 6.2. Các dạng Unicode tổ hợp và dựng sẵn

Ví dụ chữ `é` có thể biểu diễn bằng một code point dựng sẵn hoặc bằng `e` cộng dấu sắc kết hợp. Trong Java, hai chuỗi ấy khác dãy mã và thường không bằng nhau qua `String.equals` hoặc `equalsIgnoreCase`. Khi chính sách cho phép coi chúng là cùng văn bản, có thể chuẩn hóa về **NFC** trước khi so sánh:

```java
import java.text.Normalizer;

String composed = "\u00E9";    // é dựng sẵn
String decomposed = "e\u0301"; // e và dấu sắc kết hợp

boolean before = composed.equals(decomposed); // false
boolean after = Normalizer.normalize(
        composed, Normalizer.Form.NFC
).equals(Normalizer.normalize(
        decomposed, Normalizer.Form.NFC
)); // true
```

Đây là **đoạn minh họa**, không phải một chương trình độc lập. `NFC` bảo toàn phân biệt những văn bản khác nhau ngoài các trường hợp tương đương chuẩn; `NFKC` còn chuẩn hóa một số khác biệt tương thích và có thể hợp nhất những ký tự vốn được hiển thị hay dùng với ý nghĩa khác. Chỉ dùng `NFKC` nếu đặc tả nghiệp vụ cho phép. Chuẩn hóa Unicode cũng không có nghĩa tự động “bỏ dấu tiếng Việt”.

### 6.3. Locale ảnh hưởng đến cách đổi hoa/thường

Java có các phép đổi case phụ thuộc locale: `toLowerCase()` không truyền tham số sử dụng locale mặc định của môi trường, có thể tạo ra kết quả khác khi đổi cấu hình máy. Một ví dụ quen thuộc là quy tắc chữ `I`/`i` trong tiếng Thổ Nhĩ Kỳ.

- Với khóa **máy** độc lập vị trí/ngôn ngữ, hãy xét `Locale.ROOT` khi chính sách dùng chuyển case. Trong ví dụ username ASCII, điều này cho khóa có thể dự đoán được.
- Với **văn bản dành cho con người**, hãy chọn locale của dữ liệu/người dùng và hành vi tìm kiếm được đặc tả. Tránh giả định mọi ngôn ngữ có quy tắc hoa/thường giống tiếng Anh.
- `equalsIgnoreCase` không nhận tham số `Locale`, nên không thể điều chỉnh chính xác cho từng ngôn ngữ chỉ bằng lời gọi này.

### 6.4. Sắp xếp ngôn ngữ với `Collator`

Khi so sánh tên hoặc văn bản hiển thị theo ngôn ngữ, `java.text.Collator` cho phép chọn locale và độ phân biệt. Ví dụ **đoạn mã minh họa**:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator =
        Collator.getInstance(Locale.forLanguageTag("vi-VN"));
collator.setStrength(Collator.SECONDARY);

boolean sameForCollation = collator.compare(left, right) == 0;
```

Trong nhiều bộ quy tắc collation, mức `SECONDARY` bỏ qua khác biệt case nhưng còn phân biệt dấu. Tuy nhiên kết quả chi tiết phụ thuộc locale, dữ liệu ngôn ngữ và nhà cung cấp collation của môi trường. Không thay `equals` của khóa lưu trữ bằng một `Collator` tùy biến mà chưa xác định chính xác hợp đồng, phiên bản và tính ổn định giữa các lần chạy.

`Collator` hữu ích cho hiển thị và tìm kiếm theo ngôn ngữ; việc dùng nó định nghĩa danh tính lâu dài trong database đòi hỏi chính sách và kiểm chứng riêng.

## 7. Tách “so khớp tìm kiếm” khỏi “bằng nhau của đối tượng”

Một hệ thống có thể đồng thời có ba câu hỏi khác nhau:

| Tình huống | Câu hỏi nghiệp vụ | Ví dụ về API/quy tắc |
| --- | --- | --- |
| Tìm nhãn trong giao diện | “`Java` và `JAVA` có được hiển thị như cùng kết quả khớp?” | `equalsIgnoreCase` hoặc tìm kiếm dùng analyzer/collation phù hợp. |
| Xác định mã coupon | “`SAVE10` có phải mã `Save10`?” | `equals` nếu mã phân biệt hoa/thường; lựa chọn này được ghi trong đặc tả. |
| Ngăn trùng tên đăng nhập | “`ALICE_7` có tạo username mới so với `alice_7`?” | Dùng khóa chuẩn hóa bất biến, unique constraint trên khóa, `equals`/`hashCode` tương ứng cho value object. |

Đừng triển khai một phương thức tên chung `equalsIgnoreCaseForEverything` rồi dùng cho mọi trường. Một hàm tên theo ý nghĩa như `canonicalUsername`, `sameCouponCode` hoặc `matchesSearchLabel` làm chính sách rõ ràng tại điểm gọi; khi yêu cầu thay đổi, có thể sửa theo phạm vi nghiệp vụ mà không vô tình đổi ý nghĩa các trường khác.

Đối với dữ liệu lưu lâu dài, quy tắc tạo khóa và version/migration cần được xem như một phần của hợp đồng dữ liệu. Khi đổi chính sách chuẩn hóa, hai khóa trước đây khác nhau có thể trở thành một; cần kiểm tra và giải quyết trùng lặp trước khi chuyển index/constraint hoặc tái tạo khóa.

## 8. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi `equalsIgnoreCase` cho tất cả chuỗi “vì thân thiện” | Có thể làm hai mã bảo mật, coupon hoặc sản phẩm khác nhau bị gộp sai. | Xác định policy theo từng trường và từng thao tác. |
| Dùng `String.equals` rồi kỳ vọng username không phân biệt case | `Alice_7` và `alice_7` bị coi là hai khóa. | Chuẩn hóa theo policy và so sánh các khóa đã chuẩn hóa. |
| Dùng `toLowerCase()` không truyền locale cho khóa hệ thống | Khóa có thể phụ thuộc locale mặc định của môi trường. | Truyền `Locale.ROOT` khi tương ứng policy; giới hạn tập ký tự hoặc định nghĩa Unicode canonicalization kỹ hơn. |
| Tưởng `equalsIgnoreCase` xử lý mọi phép tương đương Unicode | Không xử lý mọi biểu diễn tổ hợp hoặc phép mở rộng nhiều ký tự. | Đặc tả normalization/case folding và test Unicode nếu dữ liệu cho phép. |
| Chỉ normalize bên lúc đăng ký, quên normalize lúc đăng nhập | Một username có thể được lưu nhưng không tìm lại được. | Dùng một đường chuẩn hóa cho tạo, tra cứu và kiểm tra uniqueness. |
| `equals` dùng khóa chuẩn hóa, `hashCode` dùng chuỗi gốc | Đối tượng bằng nhau có hash khác nhau, làm hỏng logic collection băm. | Cùng dùng một trường key đã chuẩn hóa, bất biến. |
| Dùng `String.CASE_INSENSITIVE_ORDER` mà tưởng `TreeSet` có quan hệ bằng nhau y như `HashSet` | Hai tập khác nhau về số phần tử với `Java`/`JAVA`. | Hiểu `TreeSet` xác định trùng bằng comparator (`compare == 0`); chọn cấu trúc/comparator theo semantics mong muốn. |
| Coi username và tài khoản có cùng khái niệm danh tính | Đổi username có thể làm đổi quan hệ bằng nhau của account. | Phân biệt value object username với entity account định danh bằng ID ổn định. |
| Bỏ qua trùng lặp sau chuẩn hóa trong DB | Có thể tạo hai bản ghi có khóa nghiệp vụ giống nhau, đặc biệt dưới truy cập đồng thời. | Unique constraint theo khóa chuẩn hóa đã chọn và xử lý va chạm rõ ràng. |
| Tự ý bỏ dấu hoặc xóa dấu chấm/dấu cộng trong email | Gộp những địa chỉ không được bảo đảm là cùng mailbox. | Theo policy email được xác minh cho hệ thống; không áp quy tắc nhà cung cấp cụ thể lên mọi email. |

## 9. Bộ kiểm tra nên có khi đưa vào ứng dụng

Với bất kỳ quy tắc so sánh case-insensitive nào, hãy xây dựng test với **giá trị thật của miền nghiệp vụ**:

- **ASCII case:** `Alice_7`, `alice_7`, `ALICE_7` có được coi là một khóa? Kiểm tra cả tạo và tra cứu.
- **Phân biệt quy tắc:** `Save10` và `SAVE10` khác nhau đối với coupon nếu policy quy định chính xác, dù tag `Java` và `JAVA` có thể so khớp.
- **Khoảng trắng:** `" Alice_7 "` có được chuẩn hóa thành `Alice_7`? Khoảng trắng giữa chuỗi hoặc ký tự không hợp lệ có bị từ chối đúng không?
- **`null`/rỗng:** API có từ chối hoặc xử lý theo hợp đồng? Đừng để một đường gọi trả `false` còn đường khác vô tình gây lỗi không mong muốn.
- **Unicode và locale:** Thử dữ liệu có dấu, chuỗi dựng sẵn/tổ hợp, chữ `I` trong locale đặc biệt, chữ `ß`, và xác nhận kết quả phù hợp phạm vi ký tự hỗ trợ.
- **Hợp đồng `equals`:** Với ba value object tương đương, thử phản xạ, đối xứng, bắc cầu; với cặp bằng nhau, bảo đảm `hashCode` giống nhau; với khác kiểu và `null`, bảo đảm hành vi đúng.
- **Tính duy nhất khi lưu trữ:** Hai yêu cầu đồng thời tạo `Alice_7` và `ALICE_7` phải được kiểm soát bằng quy tắc uniqueness ở nơi lưu, không chỉ bằng kiểm tra trước khi insert.
- **Tính ổn định:** Kiểm tra dữ liệu cũ sau khi cập nhật Unicode rules, locale provider, database collation hoặc chính sách chuẩn hóa; nếu có thay đổi, cân nhắc migration.

Có thể viết các phép kiểm tra dạng property-based tests cho rất nhiều bộ ba đầu vào, đặc biệt với Unicode. Tuy nhiên một test trả về `true` với ba chuỗi cụ thể không tự chứng minh chính sách đúng với toàn miền dữ liệu; cơ sở của tính bắc cầu phải đến từ định nghĩa quan hệ bằng nhau nhất quán.

## 10. Ghi nhớ

“So sánh không phân biệt hoa thường” là **một lựa chọn nghiệp vụ có phạm vi**, không phải thuộc tính mặc nhiên của mọi chuỗi. `equalsIgnoreCase` là công cụ tiện cho một số phép khớp; chuẩn hóa khóa cho phép biểu diễn rõ danh tính của value object; `Collator` phục vụ so sánh văn bản theo ngôn ngữ. Hãy công bố miền ký tự, cách xử lý case, khoảng trắng, Unicode, locale và `null`, sau đó dùng cùng policy ở mọi đường tạo/truy vấn dữ liệu. Nếu policy trở thành `equals` của một lớp giá trị, `hashCode` bắt buộc dùng cùng khóa tương đương và khóa đó nên bất biến.