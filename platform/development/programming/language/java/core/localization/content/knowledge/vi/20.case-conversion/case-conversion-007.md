# Không áp dụng cùng một chính sách chữ hoa và chữ thường cho mọi trường dữ liệu

Trong ứng dụng đa ngôn ngữ, các chuỗi `"Lan"`, `"LAN"`, `"lan"` có thể biểu thị **cùng một username** nếu sản phẩm quy định username không phân biệt hoa/thường. Nhưng với **mật khẩu, mã truy cập, chuỗi chữ ký, định danh phân biệt hoa/thường** hoặc tên được người dùng nhập, ba chuỗi đó có thể mang **ý nghĩa khác nhau**. Do đó, thao tác `toLowerCase()` hoặc `equalsIgnoreCase()` áp dụng đồng loạt cho mọi cột là một lỗi thiết kế dữ liệu, không phải cách làm ứng dụng “hỗ trợ localization”.

Bài Knowledge này thuộc chủ đề **Chữ hoa và thường** của Java Core Localization. Trọng tâm là **chọn và thực thi chính sách case mapping / so sánh / lưu trữ theo ý nghĩa từng trường**, thay vì đưa toàn bộ dữ liệu qua một hàm chuẩn hóa chung. Bài dùng **Java 17+**, mã chạy được và các trường hợp Turkish `I`/`ı`, German `ß`, Unicode NFC, khóa định danh, nội dung hiển thị, email và dữ liệu cần bảo toàn chính xác.

**Nguyên tắc nền:** Trước khi đổi hoa/thường, phải xác định **dữ liệu này là gì, ai định nghĩa quy tắc tương đương, có cần bảo toàn cách viết gốc không, dùng để hiển thị hay làm khóa so sánh, và quy tắc ấy có ổn định giữa các hệ thống không**.

## 1. Ba thao tác thường bị gộp làm một

Có ba nhu cầu khác nhau:

1. **Biến đổi cách viết để hiển thị** (*case conversion*): ví dụ dựng một tiêu đề bằng chữ hoa theo ngôn ngữ người xem.
2. **So sánh không phân biệt kiểu chữ** (*case-insensitive comparison*): ví dụ tìm hai username được quy định tương đương.
3. **Tạo khóa dữ liệu ổn định** (*canonical key/identity policy*): ví dụ mọi phiên bản hợp lệ của cùng một mã người dùng phải tra cứu trúng một bản ghi.

Không phải thao tác nào cũng được giải quyết đúng bằng một `String.toLowerCase(...)`. Đối với tên người, tiêu đề và câu văn, đổi chữ có thể ảnh hưởng quy tắc của ngôn ngữ; với khóa giao thức, lại cần quy ước độc lập locale và có thể chỉ chấp nhận **ASCII**; với mật khẩu hoặc token, việc thay đổi bất kỳ code point nào có thể làm giá trị khác hoàn toàn.

| Dữ liệu | Câu hỏi cần trả lời trước | Hành vi minh họa |
| --- | --- | --- |
| Tên hiển thị | Có phải giữ cách viết người dùng không? | Giữ `Nguyễn Thị Lan` nguyên bản; search có chỉ mục riêng |
| Username | Quy định có phân biệt hoa/thường không? | Nếu sản phẩm chọn không phân biệt, `Lan_01` và `LAN_01` cùng khóa |
| Password/passphrase | Giao thức xác thực có cho phép đổi ký tự không? | Không tự đổi hoa/thường |
| Access token, API key | Có phải chuỗi phân biệt byte/ký tự tuyệt đối không? | Bảo toàn đúng dữ liệu, so sánh theo giao thức |
| Mã giao thức ASCII | Chuẩn định nghĩa quy ước chữ hoa hay không? | Mã tiền tệ ISO dạng `USD`; kiểm tra tập mã hợp lệ |
| Email | Phần địa phương và domain có cùng quy tắc không? | Không tự lower-case toàn bộ địa chỉ |
| Tên file, đường dẫn | Hệ điều hành/file system có phân biệt hoa/thường không? | Không áp đặt một chính sách trên mọi nền tảng |
| Văn bản tìm kiếm | Có muốn bỏ qua case, dấu, biến thể Unicode không? | Chính sách search riêng, không nhất thiết đổi nội dung gốc |

Kết luận quan trọng: **“không phân biệt hoa/thường” phải là một phần của hợp đồng của trường dữ liệu**, không phải “tính năng tiện lợi” được áp dụng sau khi dữ liệu đã dùng làm khóa.

## 2. Java có những API nào và giới hạn ra sao?

Các thao tác thường gặp:

```java
String a = "TITLE";
String lower = a.toLowerCase(Locale.ROOT);
String upper = a.toUpperCase(Locale.ROOT);
boolean equal = a.equalsIgnoreCase("title");
```

Đây là **fragment** trong phương thức đã import `java.util.Locale`.

| API | Ý nghĩa | Điều không được ngầm suy ra |
| --- | --- | --- |
| `String.toLowerCase()` | Chuyển chữ thường theo **default locale của JVM** | Kết quả không ổn định nếu môi trường có locale khác |
| `String.toUpperCase()` | Chuyển chữ hoa theo **default locale của JVM** | Không thích hợp làm chuẩn cho khóa máy đọc độc lập môi trường |
| `toLowerCase(Locale)` | Case mapping theo locale được chỉ định | Không phải luôn phép ánh xạ một-một |
| `toUpperCase(Locale)` | Case mapping theo locale được chỉ định | Chuỗi có thể dài hơn chuỗi ban đầu |
| `equalsIgnoreCase(String)` | So sánh case-insensitive theo thuật toán `String`, **không nhận Locale** | Không phải so sánh ngôn ngữ học đầy đủ hay Unicode full case folding |
| `compareToIgnoreCase(String)` | So sánh thứ tự không phân biệt case bằng quy tắc Java `String` | Không thay thế sort văn bản theo locale |
| `java.text.Collator` | So sánh văn bản theo locale, hỗ trợ mức nhạy case/accent tùy cấu hình | Không phải quy tắc định danh chung cho token/API key |
| `java.text.Normalizer` | Canonical/compatibility Unicode normalization | Không tự thực hiện case conversion hoặc full case folding |

**Lưu ý phiên bản:** bài này chỉ dựa trên API có ở **Java 17**. Khi muốn Unicode case folding toàn diện hơn hoặc một profile bảo mật định danh, cần xem thư viện/chuẩn có triển khai tương ứng, ví dụ ICU4J hoặc Unicode identifier/security profile; không tự xem `equalsIgnoreCase` tương đương toàn bộ hệ thống đó.

## 3. Locale mặc định có thể làm hỏng khóa nội bộ

Java documentation nêu rõ `toLowerCase()` tương đương `toLowerCase(Locale.getDefault())`. Điều này nguy hiểm với protocol identifiers, từ khóa, tên trường cấu hình hoặc username nếu hợp đồng khóa không theo ngôn ngữ máy chủ.

Ví dụ tiếng Thổ Nhĩ Kỳ có **`I`** và **`ı`** (dotless i); khi lower-case trong locale `tr-TR`, chữ `I` ASCII không trở thành chữ `i` ASCII quen thuộc.

**Chương trình độc lập — `DefaultLocaleTrapDemo.java`:**

```java
import java.util.Locale;

public class DefaultLocaleTrapDemo {
    public static void main(String[] args) {
        String input = "TITLE";
        Locale turkish = Locale.forLanguageTag("tr-TR");

        String rootKey = input.toLowerCase(Locale.ROOT);
        String trKey = input.toLowerCase(turkish);

        System.out.println("ROOT key: " + rootKey);
        System.out.println("Turkish equals title: "
                + trKey.equals("title"));
        System.out.println("Turkish contains dotless i: "
                + trKey.contains("\u0131"));
        System.out.println("Same key: "
                + rootKey.equals(trKey));
    }
}
```

```bash
javac -encoding UTF-8 DefaultLocaleTrapDemo.java
java DefaultLocaleTrapDemo
```

Stdout:

```text
ROOT key: title
Turkish equals title: false
Turkish contains dotless i: true
Same key: false
```

Đây là ví dụ **truyền locale tường minh**, không thay đổi locale toàn JVM, nên chạy ở hệ thống có default locale khác vẫn thể hiện cùng phép so sánh.

**Nên chọn như thế nào?** Với **mã máy do sản phẩm tự định nghĩa và chỉ cho phép ASCII**, `Locale.ROOT` là lựa chọn ổn định hơn default locale khi cần case conversion. Tuy nhiên, `Locale.ROOT` **không** là định nghĩa thay thế cho mọi quy tắc Unicode case folding; với username hỗ trợ Unicode, phải định nghĩa chính sách đầy đủ hơn, gồm tập ký tự, normalization, case equivalence, collision và kiểm thử các ngôn ngữ mục tiêu.

Không gọi `Locale.setDefault(...)` để đổi ngôn ngữ mỗi HTTP request. Default locale là trạng thái chung của JVM; nếu nhiều người dùng thực hiện đồng thời, thay đổi này có thể ảnh hưởng những request khác. Hãy **truyền Locale của request vào nơi thực sự cần nó**.

## 4. Chữ hoa/chữ thường không luôn có độ dài bằng nhau

Case mapping trong Unicode không bắt buộc là phép thay từng ký tự bằng đúng một ký tự. Ví dụ tiếng Đức, chữ **`ß`** có thể thành **`SS`** khi gọi `String.toUpperCase(Locale.ROOT)`. Chữ Latin capital I with dot `İ` có thể lower-case theo `Locale.ROOT` thành **`i` + dấu chấm kết hợp**, tăng số code point.

**File `CaseExpansionDemo.java`:**

```java
import java.util.Locale;

public class CaseExpansionDemo {
    public static void main(String[] args) {
        String sharpS = "\u00DF";
        String expanded = sharpS.toUpperCase(Locale.ROOT);

        System.out.println("Sharp S upper: "
                + expanded.equals("SS"));
        System.out.println("Sharp S lengths: "
                + sharpS.length() + " -> " + expanded.length());

        String dottedI = "\u0130";
        String rootLower = dottedI.toLowerCase(Locale.ROOT);
        System.out.println("Dotted I ROOT length: "
                + rootLower.length());

        String trLower = dottedI.toLowerCase(
                Locale.forLanguageTag("tr-TR"));
        System.out.println("Dotted I Turkish equals i: "
                + trLower.equals("i"));
    }
}
```

```bash
javac -encoding UTF-8 CaseExpansionDemo.java
java CaseExpansionDemo
```

Stdout:

```text
Sharp S upper: true
Sharp S lengths: 1 -> 2
Dotted I ROOT length: 2
Dotted I Turkish equals i: true
```

**Hệ quả:** Không tạo một chuỗi chữ thường/hoa rồi giả định `length()` và số byte UTF-8 không đổi. Nếu database index giới hạn độ dài khóa hoặc protocol cấm một số ký tự, phải **kiểm tra lại độ dài/tập ký tự sau biến đổi**. Nếu case mapping tạo collision, hai đầu vào khác nhau có thể trở thành một khóa.

Về mặt kỹ thuật, `String.length()` là số đơn vị mã UTF-16, không hẳn là số code point hay số ký tự người dùng nhìn thấy (*grapheme cluster*). Đối với văn bản đa ngôn ngữ, xác định rõ đơn vị khi áp đặt độ dài.

## 5. Trường tên người và nội dung hiển thị: bảo toàn cách viết gốc

Một tên như `Đặng`, `McDonald`, `van Gogh` hoặc một thương hiệu có chữ hoa đặc thù không nên bị ép thành uppercase/lowercase chỉ vì “chuẩn hóa dữ liệu”. Ngoài ra, cách chuyển case có thể phụ thuộc ngôn ngữ người dùng nhập, không nhất thiết trùng ngôn ngữ đang xem UI.

Chính sách hợp lý tùy sản phẩm:

- **Lưu bản gốc:** giữ tên/câu chữ theo cách người dùng nhập nếu có nghĩa trong ngữ cảnh pháp lý, văn hóa hoặc biểu diễn cá nhân.
- **Có thể chuẩn hóa Unicode NFC khi hợp đồng cho phép:** NFC chuẩn hóa *canonical equivalence* như hai cách viết cùng một chữ có dấu, **không** tự đổi chữ hoa thành chữ thường.
- **Tạo trường tìm kiếm riêng:** nếu cần case-insensitive/diacritic-insensitive search, xây khóa hoặc index riêng và có thể giữ nội dung gốc để hiển thị.
- **Case cho đầu ra** chỉ khi thiết kế UI đòi hỏi, bằng quy tắc locale/biên tập phù hợp. “Title case” theo từng từ bằng `split(" ")` rồi `toUpperCase` không đúng với mọi ngôn ngữ và mọi tên riêng.

Không thể suy luận ngôn ngữ cần dùng cho tên chỉ từ `Locale` của máy chủ hoặc quốc gia cư trú. Người dùng có thể đặt ngôn ngữ giao diện khác ngôn ngữ trong tên.

**Fragment minh họa việc lưu tên và khóa so canonical riêng:**

```java
String originalName = "Đặng";
String canonicalForMatching = java.text.Normalizer.normalize(
        originalName,
        java.text.Normalizer.Form.NFC);
// Lưu/display originalName theo policy, không tự uppercase/lowercase.
```

Chuẩn hóa NFC có thể giúp so các chuỗi cùng chữ Unicode nhưng cách mã hóa khác nhau. Tuy nhiên, nếu muốn tìm kiếm không phân biệt case, NFC **chưa đủ** và cần chính sách khác được thiết kế rõ.

## 6. Username: chọn chính sách danh tính trước khi đăng ký tài khoản

Username là **định danh**, không chỉ là chuỗi để hiển thị. Có hai thiết kế hợp lệ khác nhau, tùy yêu cầu:

**A. Case-sensitive username.** `Lan_01` và `LAN_01` là hai giá trị khác nhau. Hệ thống phải thống nhất cách đăng nhập, URL profile, cache key, database UNIQUE constraint và API theo quy tắc đó.

**B. Case-insensitive username.** Hai giá trị trên cùng một danh tính. Lúc này hệ thống phải định nghĩa **cách tạo canonical key**, dùng cùng chính sách ở đăng ký, đăng nhập, tra cứu, cập nhật và migration; đồng thời quyết định giữ `displayHandle` nguyên bản hay hiển thị chính canonical key.

Một cấu hình **đơn giản và dễ kiểm soát** cho username nội bộ là **giới hạn ASCII** rồi dùng lowercase `Locale.ROOT`. Đây là *quy tắc của ứng dụng*, không phải chuẩn chung cho mọi username trên thế giới.

### Ví dụ runnable: username ASCII có quy tắc rõ

Lưu **`UsernamePolicyDemo.java`**:

```java
import java.util.Locale;

public class UsernamePolicyDemo {
    public static String key(String raw) {
        if (raw == null
                || !raw.matches("[A-Za-z][A-Za-z0-9_]{2,15}")) {
            throw new IllegalArgumentException(
                    "Invalid username syntax");
        }
        return raw.toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String first = key("Lan_01");
        String second = key("LAN_01");

        System.out.println("First: " + first);
        System.out.println("Second: " + second);
        System.out.println("Same identity: "
                + first.equals(second));

        try {
            key("Lăn_01");
            System.out.println("Unexpected acceptance");
        } catch (IllegalArgumentException ex) {
            System.out.println("Non-ASCII rejected by this policy");
        }
    }
}
```

```bash
javac -encoding UTF-8 UsernamePolicyDemo.java
java UsernamePolicyDemo
```

Stdout:

```text
First: lan_01
Second: lan_01
Same identity: true
Non-ASCII rejected by this policy
```

**Đọc đúng giới hạn ví dụ:** Đây là sản phẩm **cố ý** không hỗ trợ Unicode trong username, nhưng có thể hỗ trợ Unicode ở `displayName`. Không nói rằng tên người dùng Unicode là sai nói chung; những sản phẩm cho phép Unicode phải thiết kế identifier profile riêng, bao gồm normalization, case folding, xử lý confusables và uniqueness.

Regex giới hạn từ 3 đến 16 ký tự ASCII, ký tự đầu là chữ cái ASCII. Quy tắc nghiệp vụ còn có thể cấm tên đã được hệ thống giữ riêng, từ nhạy cảm, trùng tên cũ, và yêu cầu lưu bản hiển thị gốc. Đừng chỉ dùng regex làm toàn bộ chính sách tài khoản.

## 7. Collision: thay đổi case policy có thể nhập nhằng danh tính

Nếu hai người dùng hiện đã tồn tại với `Lan_01` và `LAN_01` trong database case-sensitive, việc chuyển sang case-insensitive mà không kiểm tra dữ liệu sẽ đưa cả hai về `lan_01`. Một unique index trên key mới sẽ gặp xung đột; tệ hơn, code đăng nhập có thể chọn nhầm tài khoản nếu xử lý collision tùy tiện.

**File `CaseCollisionDemo.java`:**

```java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public class CaseCollisionDemo {
    public static void main(String[] args) {
        String[] existing = {
                "Lan_01", "LAN_01", "Minh_2"
        };

        Map<String, String> firstByKey = new LinkedHashMap<>();
        for (String raw : existing) {
            String key = raw.toLowerCase(Locale.ROOT);
            String prior = firstByKey.putIfAbsent(key, raw);
            if (prior == null) {
                System.out.println(raw + ": accepted");
            } else {
                System.out.println(raw
                        + ": conflict with " + prior);
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 CaseCollisionDemo.java
java CaseCollisionDemo
```

Stdout:

```text
Lan_01: accepted
LAN_01: conflict with Lan_01
Minh_2: accepted
```

Chương trình này **chỉ phát hiện** collision, không tự xử lý tranh chấp danh tính. Một migration thật cần quyết định rõ người sở hữu khóa, cách liên lạc chủ tài khoản, cập nhật foreign keys/URLs, lịch sử đăng nhập, cache, khóa phiên bản chính sách và rollback nếu cần.

**Chính sách nhất quán** quan trọng hơn việc chọn lower hay upper: nếu đăng ký dùng `Locale.ROOT` nhưng đăng nhập dùng `Locale.getDefault()` hoặc backend và database dùng collation khác nhau, hệ thống có thể chấp nhận những tài khoản không tìm lại được hoặc nhầm tài khoản.

## 8. Mật khẩu, passphrase, token: không tự sửa ký tự

Các trường liên quan xác thực thường có hợp đồng **giữ chính xác giá trị người dùng hoặc giao thức gửi tới**. Vì thế:

- Không tự `trim()`, `toLowerCase()`, `toUpperCase()` hoặc normalize Unicode cho **password** nếu chính sách xác thực của hệ thống/giao thức không định nghĩa phép biến đổi đó.
- Không hiển thị lại password hoặc ghi vào log để “so sánh case”.
- Không dùng `equalsIgnoreCase` khi xác minh **access token, API secret, cryptographic signature**, trừ khi một chuẩn riêng thực sự định nghĩa so sánh không phân biệt case (không được giả định).
- Password nên được xử lý bằng **password hashing/KDF có salt và tham số bảo mật thích hợp**, chứ không lưu plain text. Việc chọn Unicode normalization/encoding ở password phải tuân thủ chuẩn và lịch sử tương thích của chính hệ xác thực.
- Token dạng chuỗi cần tuân thủ **định dạng cụ thể**: ví dụ Base64/Base64URL là case-sensitive. Nếu server hạ chữ hoa/thường một token như `aB0`, nó sẽ không còn cùng chuỗi đầu vào.

**Không đồng nhất “được gõ trên bàn phím” với “được phép tự đổi theo locale”.** Hệ thống có thể yêu cầu người dùng nhập lại để xác nhận nhưng không nên bí mật thay đổi dữ liệu cần xác thực.

Đối với dữ liệu nhạy cảm, cần xem xét giới hạn thời gian lưu trong bộ nhớ, log, truyền tải qua TLS, bảo vệ khóa/secret và cơ chế so sánh an toàn theo thư viện bảo mật. `String.equalsIgnoreCase` hoàn toàn không phải một password verifier.

## 9. Email: miền và local part không nhất thiết có cùng quy tắc

Một địa chỉ email nhìn như một trường đơn lẻ `user@domain.example`, nhưng thực tế có hai phần khác nhau:

1. **Domain:** DNS domain names không phân biệt chữ hoa/thường ở khâu tra cứu DNS. Có thể canonicalize theo quy tắc tên miền và IDNA đã được chọn, ví dụ vùng ASCII `Example.COM` và `example.com` thường chỉ cùng một tên DNS.
2. **Local part:** theo mô hình giao thức SMTP, phần trước `@` *về nguyên tắc có thể phân biệt chữ hoa/thường*; các provider thực tế có chính sách khác nhau. Không mặc định rằng `Sales@example.com` và `sales@example.com` luôn cùng một mailbox trên mọi máy chủ.

Vì vậy **đừng lower-case toàn bộ địa chỉ email** rồi coi đó là identity canonical an toàn. Một số ứng dụng xử lý địa chỉ của provider họ kiểm soát có thể có quy tắc riêng, nhưng phải do provider và sản phẩm định nghĩa, không dựa vào cảm tính.

Các biến thể như dấu chấm trong local part, dấu `+` để gắn tag hay Unicode trong EAI/IDN còn phụ thuộc chuẩn và nhà cung cấp. Càng không nên xóa dấu chấm, bỏ phần sau `+` hoặc chuyển toàn email sang lower-case bằng một hàm chung khi xây hệ thống đăng ký đa nhà cung cấp.

### Cách tổ chức dữ liệu gợi ý

- Lưu **địa chỉ người dùng cung cấp** theo policy để có thể gửi mail lại đúng nơi.
- Xác thực định dạng bằng parser/validator phù hợp, không tự `split("@")` đơn giản để xử lý mọi trường hợp cú pháp email hợp lệ.
- Có thể quản lý một **lookup key** theo hợp đồng sản phẩm, nhưng không tuyên bố nó nhận diện chính xác mọi mailbox trên Internet.
- Dùng cơ chế **xác minh quyền sở hữu email** và chính sách chống trùng tài khoản; không coi việc lower-case hay bỏ dấu chấm là chứng cứ hai địa chỉ thuộc cùng một người.
- Khi áp dụng IDN, phân biệt Unicode domain với ASCII label (IDNA/Punycode) và sử dụng thư viện/quy tắc tương ứng. Case conversion đơn giản **không thay thế** IDNA.

## 10. Mã giao thức, enum, khóa JSON và tên cấu hình

Với dữ liệu được một **protocol hoặc schema** định nghĩa, tuân thủ đúng hợp đồng:

| Trường | Chính sách đúng là gì? | Ví dụ |
| --- | --- | --- |
| Mã tiền tệ ISO 4217 | Sử dụng mã đăng ký có quy ước ASCII; kiểm tra thuộc tập mã hợp lệ | `USD`, `VND` |
| Mã ngôn ngữ/locale | BCP 47 cùng quy tắc viết language/script/region | `vi-VN`, `zh-Hant-TW` |
| Enum của API | Theo schema: có thể case-sensitive hoặc có alias được công bố | `"PAID"` khác `"paid"` nếu schema nói vậy |
| JSON object key | Là string, mặc định phải xử lý chính xác theo schema | `"userId"` không tự đồng nghĩa `"userid"` |
| HTTP field name | Theo chuẩn HTTP, tên header không phân biệt chữ hoa/thường | `Content-Type` và `content-type` |
| ResourceBundle key | Theo tên key khai báo trong bundle, không tự lower-case khi lookup | `message.title` |
| UUID dạng text | Theo parser/serialization của UUID và hợp đồng API | Không dùng lower-case chung cho mọi loại ID |

Không suy ra “chuẩn Internet thì mọi thứ case-insensitive”. **HTTP header names** không phân biệt case, nhưng **header values** có thể có quy tắc riêng. JSON keys thường được so khớp đúng tên schema; hệ thống không được tự gộp `userID` và `userId` nếu hợp đồng không cho phép.

### Chọn cách chuẩn hóa mã ASCII có kiểm soát

Nếu một field nhận **mã tiền tệ ba chữ cái ASCII** và sản phẩm muốn chấp nhận nhập lowercase, một pipeline có thể:

1. Kiểm tra cú pháp `[A-Za-z]{3}` (không cho phép khoảng trắng, dấu hoặc số).
2. Chuyển upper bằng `Locale.ROOT`.
3. Kiểm tra mã đó **thực sự tồn tại/hợp lệ** theo nghiệp vụ và danh sách tiền tệ được hỗ trợ.
4. Lưu mã chuẩn, không coi mọi chuỗi ba chữ cái là tiền tệ.

**File `ProtocolCodeDemo.java`:**

```java
import java.util.Currency;
import java.util.Locale;

public class ProtocolCodeDemo {
    private static String currencyCode(String raw) {
        if (raw == null || !raw.matches("[A-Za-z]{3}")) {
            throw new IllegalArgumentException("Bad syntax");
        }
        String uppercase = raw.toUpperCase(Locale.ROOT);
        return Currency.getInstance(uppercase).getCurrencyCode();
    }

    public static void main(String[] args) {
        System.out.println("Code: " + currencyCode("usd"));
        System.out.println("Language tag: "
                + Locale.forLanguageTag("EN-us").toLanguageTag());

        try {
            currencyCode("u$d");
            System.out.println("Unexpected acceptance");
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid syntax rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 ProtocolCodeDemo.java
java ProtocolCodeDemo
```

Stdout:

```text
Code: USD
Language tag: en-US
Invalid syntax rejected
```

Đối với `Locale`, API `toLanguageTag()` xử lý thẻ BCP 47 đúng dạng hơn `String.toLowerCase(Locale.ROOT)`; các phần như region được quy ước viết hoa. Với API cần reject thẻ BCP 47 sai cú pháp, dùng `Locale.Builder.setLanguageTag(...)` cùng kiểm tra locale được hỗ trợ, vì `Locale.forLanguageTag(...)` có xử lý đầu vào tương đối khoan dung.

## 11. Tên file và đường dẫn: phụ thuộc hệ thống, không phải một quy tắc Java duy nhất

Các hệ thống file và nền tảng có thể khác nhau về việc `Report.csv` và `report.csv` có cùng đường dẫn hay không. Ngay cả trong cùng hệ điều hành, loại filesystem hoặc cấu hình volume cũng có thể quyết định cách so tên. Vì vậy:

- Không dùng `path.toString().toLowerCase()` làm “đường dẫn chuẩn trên mọi máy”.
- Khi kiểm tra đuôi file như `.CSV`, có thể chọn **quy tắc cho riêng phần đuôi** nếu sản phẩm cho phép. Không tự đổi toàn bộ directory/file name vì có thể làm hỏng đường dẫn thật.
- Khi dùng đường dẫn từ user input, cần phòng chống path traversal và kiểm tra quyền; đổi case không giúp giải quyết các rủi ro này.
- Nếu file path được đưa lên API hoặc giữ trong database, quyết định lưu **ID của file** tách khỏi tên hiển thị và quy tắc tìm kiếm khi có thể.
- Đừng kết luận một đường dẫn an toàn chỉ vì hai cách viết được `equalsIgnoreCase` coi như bằng nhau.

Tương tự, một URL có nhiều thành phần khác nhau: phần **host** có quy tắc tên miền, nhưng **path/query** do dịch vụ đích xác định. Dùng URI/parser và quy tắc giao thức của thành phần tương ứng, không lower-case cả URL rồi coi đó là cùng resource.

## 12. equalsIgnoreCase, Locale.ROOT và Unicode case folding không đồng nghĩa

Ba chiến lược có mức độ và mục đích khác nhau:

- `equalsIgnoreCase`: so không phân biệt case theo thuật toán của `String`. **Không nhận locale** và không bảo đảm tương đương với so sánh ngôn ngữ học.
- `toLowerCase(Locale.ROOT)` rồi `equals`: tạo hai khóa lower-case độc lập locale, nhưng **không phải một định nghĩa Unicode full case folding hoàn chỉnh**.
- **Unicode full case folding**: được Unicode định nghĩa cho matching không phân biệt case theo quy tắc rộng hơn, có thể có ánh xạ nhiều code point và cần cơ chế triển khai thích hợp.

Ví dụ tiếng Đức cho thấy khác biệt: `"Straße"` chứa `ß`, còn `"STRASSE"` dùng hai chữ `SS`. `equalsIgnoreCase` không nên được xem như thao tác tạo một khóa tương đương đầy đủ trong các trường hợp mở rộng như vậy.

**Chương trình `ComparisonStrategiesDemo.java`:**

```java
import java.text.Normalizer;
import java.util.Locale;

public class ComparisonStrategiesDemo {
    public static void main(String[] args) {
        String a = "Stra\u00DFe";
        String b = "STRASSE";

        System.out.println("equalsIgnoreCase: "
                + a.equalsIgnoreCase(b));
        System.out.println("Upper strings equal: "
                + a.toUpperCase(Locale.ROOT)
                        .equals(b.toUpperCase(Locale.ROOT)));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("Raw ignore case composed: "
                + composed.equalsIgnoreCase(decomposed));

        String nfcA = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String nfcB = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("NFC exact equal: "
                + nfcA.equals(nfcB));
    }
}
```

```bash
javac -encoding UTF-8 ComparisonStrategiesDemo.java
java ComparisonStrategiesDemo
```

Stdout:

```text
equalsIgnoreCase: false
Upper strings equal: true
Raw ignore case composed: false
NFC exact equal: true
```

**Không dùng dòng “Upper strings equal: true” làm lý do chuẩn hóa mọi định danh bằng uppercase.** Nó chứng minh **một cặp ví dụ cụ thể** có thể so bằng uppercase, không chứng minh uppercase là full case folding hoặc identity policy phù hợp với mọi hệ chữ.

`Normalizer` xử lý canonical/compatibility Unicode equivalence nhưng **không tự đổi case**. Với identifier Unicode dùng ở nhiều dịch vụ và ngôn ngữ, cần thiết kế profile cụ thể (ví dụ được chuẩn Unicode/UTS #39 hoặc thư viện cung cấp), kiểm soát Unicode version, xử lý collision và tích hợp với database collation.

## 13. Collator cho so sánh ngôn ngữ, không thay thế identity rule

`java.text.Collator` cung cấp so sánh văn bản theo **Locale**. Tùy strength, kết quả có thể nhạy hoặc không nhạy với dấu và chữ hoa/thường:

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(
        Locale.forLanguageTag("fr-FR"));
collator.setStrength(Collator.PRIMARY);
int comparison = collator.compare(left, right);
```

Đây là **fragment**, cần biến `left` và `right` được khai báo. `Collator.PRIMARY` thường ưu tiên chữ cơ sở hơn phân biệt dấu/case, nhưng hành vi cụ thể còn phụ thuộc quy tắc locale/provider. Đừng khẳng định mọi chữ có dấu đều bằng chữ không dấu trên mọi locale.

**Dùng Collator khi nào?** Khi **sắp xếp danh sách hoặc tìm kiếm văn bản** theo quy ước ngôn ngữ của người dùng. Ví dụ thứ tự tên người hay tên sản phẩm cần thuận mắt người đọc. Với khóa định danh dùng cho cache, database UNIQUE hay API, việc dùng so sánh Collator theo default locale có thể gây thay đổi hành vi giữa môi trường, Unicode/CLDR versions hoặc việc nâng cấp JDK.

Nếu cần so sánh văn bản theo locale, hãy dùng **Locale được chọn cho thao tác đó**, không dùng locale ngẫu nhiên của server. Một người có thể sắp xếp tên tiếng Việt theo quy tắc khác tiếng Anh, nhưng mã đơn hàng vẫn phải giữ policy máy đọc độc lập ngôn ngữ.

## 14. Thiết kế hợp đồng trường dữ liệu trước khi viết utility

Một bảng policy ở cấp thiết kế có thể gồm:

| Field | Lưu bản gốc? | Quy tắc so/tra cứu | Locale dùng | Rủi ro cần kiểm tra |
| --- | --- | --- | --- | --- |
| `displayName` | Có | Chỉ mục tìm kiếm riêng nếu cần | Locale cho UI/search | Mất cách viết tên, nhầm dấu |
| `username` ASCII | Có thể giữ display | Key lowercase ASCII sau validation | `Locale.ROOT` | Collision khi đăng ký/migration |
| `password` | Không lưu plaintext | Xác minh theo giao thức password hashing | Không tùy tiện dùng locale | Mất chính xác input |
| `accessToken` | Theo giao thức/secure storage | Exact matching | Không | Từ chối hợp lệ hoặc nhận nhầm token |
| `currencyCode` | Lưu canonical | ASCII uppercase + mã hợp lệ | `Locale.ROOT` cho chuyển chữ | Mã không đăng ký, nhầm currency |
| `localeTag` | Lưu BCP 47 | Parse/serialize bằng `Locale` | API BCP 47 | Tag cú pháp sai, locale không hỗ trợ |
| `email` | Nên giữ input đã xác minh | Xác minh mailbox/provider policy | Không lower-case toàn bộ | Nhầm mailbox |
| `orderId` | Theo schema | Exact hoặc alias do hệ thống quy định | Thường không | Trùng ID, phá chữ ký/URL |
| `searchQuery` | Có thể giữ query | Collation/index/search policy | Locale tìm kiếm | Kết quả không phù hợp ngôn ngữ |
| `filePath` | Theo filesystem | OS/filesystem-specific | Không suy diễn từ locale | Không tìm thấy file |
| `resourceKey` | Đúng chính tả | Match chính xác theo hệ resource | Không tự đổi | Missing key |

Hợp đồng cần trả lời thêm: **null/empty/whitespace được xử lý thế nào, ký tự nào được phép, normalization có dùng NFC/NFKC không, so sánh bằng chuỗi hay collation DB, Unicode version nào, phiên bản API nào, khi xung đột phải trả lỗi nào**.

Không nhất thiết mọi trường đều cần một bảng policy riêng trong code. Nhưng những nhóm có semantics khác nhau **không nên ép vào một “normalize(String)” chung** chỉ làm `trim().toLowerCase()`.

## 15. Ví dụ service nhỏ: mỗi field có policy riêng

Thay vì tạo hàm `normalizeAllFields`, ta định nghĩa các thao tác theo mục đích. Ví dụ sau có chính sách rõ ràng:

- `displayName`: giữ nguyên kiểu chữ; chỉ áp dụng NFC ở đầu vào khi hợp đồng ứng dụng đã cho phép.
- `username`: chỉ ASCII và canonical lowercase `Locale.ROOT`.
- `currencyCode`: ASCII, uppercase, và kiểm tra mã tiền tệ thực.
- `orderId`: giữ nguyên nếu schema định nghĩa case-sensitive.
- `secret`: **không biến đổi**, và không in nội dung nhạy cảm.

**File `FieldSpecificPolicyDemo.java`:**

```java
import java.text.Normalizer;
import java.util.Currency;
import java.util.Locale;

public class FieldSpecificPolicyDemo {
    static String displayName(String text) {
        return Normalizer.normalize(text, Normalizer.Form.NFC);
    }

    static String usernameKey(String input) {
        if (!input.matches("[A-Za-z][A-Za-z0-9_]{2,15}")) {
            throw new IllegalArgumentException("Bad username");
        }
        return input.toLowerCase(Locale.ROOT);
    }

    static String currencyCode(String input) {
        if (!input.matches("[A-Za-z]{3}")) {
            throw new IllegalArgumentException("Bad currency code");
        }
        return Currency.getInstance(
                input.toUpperCase(Locale.ROOT))
                .getCurrencyCode();
    }

    static String orderId(String input) {
        return input;
    }

    static String secretUnmodified(String input) {
        return input;
    }

    public static void main(String[] args) {
        System.out.println("Display: " + displayName("Đặng"));
        System.out.println("Username: "
                + usernameKey("LAN_01"));
        System.out.println("Currency: "
                + currencyCode("vnd"));
        System.out.println("Order ID: "
                + orderId("Ab-07"));

        String providedSecret = "SeCrEt!";
        System.out.println("Secret unchanged: "
                + secretUnmodified(providedSecret)
                        .equals(providedSecret));
    }
}
```

```bash
javac -encoding UTF-8 FieldSpecificPolicyDemo.java
java FieldSpecificPolicyDemo
```

Stdout trên Java 17+ với console UTF-8:

```text
Display: Đặng
Username: lan_01
Currency: VND
Order ID: Ab-07
Secret unchanged: true
```

Đây là **mô hình dạy chính sách**, không phải service xác thực đầy đủ. Với dữ liệu bí mật trong sản phẩm thực, không lưu/ghi log plaintext, áp dụng password hashing hoặc secret management đúng ngữ cảnh. Tương tự, `Normalizer.normalize` với đầu vào null sẽ lỗi; các phương thức trên có hợp đồng đầu vào **non-null**, cần validation khi tích hợp API.

**Vì sao không gọi `displayName(...).toLowerCase(ROOT)`?** Vì cách viết gốc có ý nghĩa hiển thị. **Vì sao không hạ `orderId`?** Vì ví dụ này giả định mã đơn hàng case-sensitive; chỉ đổi nếu schema của mã đó định nghĩa khác. **Vì sao không hạ `secret`?** Vì nó là dữ liệu cần giữ nguyên theo giao thức. Cùng một `String` ở Java nhưng vai trò nghiệp vụ khác dẫn đến policy khác.

## 16. Database, index và các hệ thống không cùng một quy tắc

Chính sách ở Java không tự đảm bảo cơ sở dữ liệu, cache hay hệ thống khác so chuỗi giống nhau. Một database dùng **case-insensitive collation** có thể coi hai chuỗi bằng nhau, trong khi `String.equals` không. Một database khác có thể phân biệt dấu hoặc dùng phiên bản Unicode khác. Bởi vậy:

1. Xác định **quy tắc canonical key** cho trường danh tính.
2. Tạo **cột khóa tra cứu** với policy được thực thi ở ranh giới ghi, nếu cần.
3. Đặt **unique constraint** theo cách nhất quán với policy; review collation và độ dài index.
4. Kiểm tra collision khi chuyển policy hoặc nâng cấp Unicode/library/DB.
5. Dùng cùng key ở register/login/find/update/cache, không lặp normalization bằng nhiều hàm khác nhau.
6. Giữ **bản gốc hiển thị** khi có yêu cầu; không biến key canonical thành nội dung thay cho tên người.

Ví dụ dữ liệu cũ `Lan_01` và `LAN_01` đang là hai tài khoản khác nhau không thể tự gộp sau khi chuyển thành `lan_01`. Cần migration có kiểm tra, quyết định xử lý va chạm và audit, thay vì chạy một câu SQL `LOWER(username)` rồi coi xong.

**Giới hạn của case mapping:** `toLowerCase(Locale.ROOT)` ở JDK 17 và hàm `LOWER(...)` ở database không nhất thiết dựa vào cùng phiên bản Unicode hoặc cùng quy tắc collation. Nếu identity policy phải ổn định lâu dài, định nghĩa profile rõ và lưu version khi cần; kiểm thử trên các runtime/DB mà sản phẩm hỗ trợ.

## 17. API, JSON và versioning: đừng âm thầm thay nghĩa trường

Giả sử API công bố `"username"` không phân biệt case nhưng `"orderId"` có phân biệt case. Nếu một bản nâng cấp backend đổi cả hai thành lower-case mà không cập nhật contract, client có thể gặp lỗi:

- Các liên kết hoặc cache keys cũ không tra cứu được mã đơn hàng.
- Hai giá trị trước đây khác nhau trở thành trùng nhau.
- Chữ ký số của payload không còn khớp do byte đã thay đổi.
- Người dùng thấy tên hiển thị mất kiểu chữ đã nhập.
- Các bộ lọc tìm kiếm hoạt động khác giữa app mobile và web.

Vì vậy, cần **hợp đồng** xác định case policy của từng field; việc thay đổi policy có thể là **thay đổi tương thích ngược** chứ không phải chỉnh sửa trình bày đơn giản.

Đặc biệt với JSON:

- **Tên thuộc tính** như `userId`, `userID` có ý nghĩa theo schema và parser; không tự lowercase tất cả keys.
- **Giá trị string** có semantics do chính field định nghĩa; JSON không tự quyết định cách case-insensitive.
- Đối với trường có chữ ký/hashing/canonical JSON, mọi phép đổi case phải tuân theo profile ký và xảy ra đúng thứ tự.
- Dùng serializer/parser chuẩn của framework; không tự nối JSON hoặc viết regex `replaceAll` để ép lowercase trên payload thô.

**Locale tag** là ví dụ ngược lại: dữ liệu có syntax quốc tế và API chuẩn. Dùng `Locale.forLanguageTag(...)` hoặc `Locale.Builder` để parse, `toLanguageTag()` để serialize. Không tự hạ toàn bộ `en-US` thành `en-us` rồi coi đó là cách viết canonical muốn lưu (language và region có quy ước chữ riêng).

## 18. QA: kiểm thử theo loại dữ liệu, không chỉ thử ASCII

Một bộ test cần có những nhóm sau:

| Trường | Các input nên thử | Điều cần xác minh |
| --- | --- | --- |
| Username ASCII | `Lan_01`, `LAN_01` | Hai input cùng key nếu sản phẩm case-insensitive |
| Username Unicode | `Lăn_01` | Từ chối **theo policy ASCII đã công bố**, không mặc định tất cả username đều phải ASCII |
| Case theo locale | `TITLE` ở ROOT và tr-TR | Không để default server đổi key |
| Case expansion | `ß`, `İ` | Chuỗi sau case mapping có thể thay độ dài |
| Tên hiển thị | `Đặng`, `McDonald` | Bảo toàn kiểu chữ |
| Tên có Unicode decomposition | `é` và `e` + U+0301 | NFC canonical equivalence nếu hợp đồng cho phép |
| Email | `Sales@example.com`, `sales@example.com` | Không gộp mặc định local part |
| Token/secret | Các chuỗi khác nhau chỉ bởi case | Không đổi hoặc so ignore-case ngoài giao thức |
| Mã tiền tệ | `usd`, `USD`, `u$d` | Quy tắc ASCII uppercase + mã tồn tại |
| Locale tag | `EN-us`, `zh-hant-tw` | Parse/serialize bằng BCP 47 API |
| File path | `Report.csv`, `report.csv` | Không giả định mọi filesystem giống nhau |
| JSON property | `userId`, `userid` | Parser/schema xử lý đúng tên trường |
| DB collision | Hai key khác case đang tồn tại | Migration phát hiện trùng khi đổi policy |
| Cache/index | Cùng identity với biến thể case | Sử dụng một key đã thỏa policy |
| Unicode confusable | Chữ Latin/Cyrillic trông giống | Không coi case conversion đủ bảo mật |

**Kiểm thử đổi default locale:** nên chạy những test kỹ thuật quan trọng trong JVM khởi động với locale khác nhau, ví dụ English và Turkish, để chứng minh canonical keys không phụ thuộc `Locale.getDefault()`. Không thay default JVM liên tục giữa test đang chạy đồng thời.

**Kiểm thử sau khi nâng cấp:** nếu chuyển JDK, database collation hoặc thư viện Unicode, hãy chạy lại các test equivalence, uniqueness và đăng nhập. Một policy định danh được dùng lâu dài cần tính ổn định cao hơn tiện ích UI thông thường.

## 19. Những lỗi phổ biến cần tránh

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Hạ chữ thường mọi `String` khi lưu | Mất cách viết tên, làm hỏng token/case-sensitive IDs | Định nghĩa theo từng field |
| Dùng `toLowerCase()` không tham số cho khóa | Phụ thuộc default locale, lỗi Turkish I | Dùng policy độc lập môi trường cho khóa |
| Nghĩ `Locale.ROOT` là full Unicode case folding | Không bao trùm mọi equivalence Unicode | Chọn profile case-fold/normalization nếu cần |
| Dùng `equalsIgnoreCase` cho password hoặc access token | Có thể chấp nhận chuỗi không đúng | Exact semantics theo giao thức |
| Cho rằng mọi email đều case-insensitive | Có thể gộp nhầm mailbox | Xác minh provider và quy tắc local part |
| Lower-case cả URL | Làm thay đổi path/query có ý nghĩa | Parse URI, xử lý theo từng thành phần |
| Lower-case mọi filename/path | Không tìm được file trên filesystem case-sensitive | Theo quy tắc nền tảng, giữ nguyên tên |
| Lower-case JSON field names | Làm sai schema | Dùng tên key đúng hợp đồng |
| Chuyển mọi display name thành Title Case | Sai tên riêng và quy tắc đa ngôn ngữ | Giữ tên gốc hoặc format theo yêu cầu rõ |
| Dùng một cột sau lower-case làm unique mà không scan dữ liệu cũ | Collision và nhầm danh tính | Pre-migration collision audit |
| Tin DB collation giống Java `String` | Có thể so khác và làm mất uniqueness | Kiểm thử/JDBC integration, schema đúng |
| Áp NFC rồi tin đã bỏ qua case | Normalizer không phải case folding | Tách canonical Unicode và case policy |
| Hạ tên mã tiền nhưng bỏ validation | Có thể nhận mã không tồn tại | Dùng `Currency`/supported-code validation |
| Tự viết regex thay toàn bộ payload JSON | Phá dữ liệu hoặc ký tự escape | Parse JSON theo schema/typed DTO |
| Đổi policy giữa register và login | Đăng ký được nhưng tìm không thấy tài khoản | Dùng chung một canonicalizer được version |
| Cắt chuỗi sau case conversion mà không kiểm tra | Có thể cắt giữa code point hoặc vi phạm key length | Validate cả trước và sau, rõ đơn vị độ dài |

## 20. Bài tập ứng dụng

**Bài 1 — Phân loại field.** Với đối tượng gồm `displayName`, `username`, `password`, `email`, `currencyCode`, `orderId` và `localeTag`, viết policy cho mỗi trường: có giữ input gốc không, so sánh theo case nào, chọn locale nào, có dùng Unicode normalization không, và collision xử lý ra sao.

**Bài 2 — Thử Turkish I.** Dùng `"TITLE".toLowerCase(Locale.ROOT)` và `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))`. So code point/`String.equals`. Giải thích lý do dùng default locale ở backend có thể phá khóa kỹ thuật.

**Bài 3 — Thay đổi độ dài.** Dùng `"\u00DF"` và `"\u0130"`. Thử `toUpperCase(Locale.ROOT)`/`toLowerCase(Locale.ROOT)` và kiểm tra độ dài UTF-16 trước/sau. Nếu key có giới hạn 16 ký tự, kiểm tra độ dài ở bước nào?

**Bài 4 — Collision.** Cho bảng có `Lan_01` và `LAN_01` đã tồn tại. Chuyển sang username lowercase ASCII: xác định collision và thiết kế phương án migration mà không chiếm nhầm tài khoản.

**Bài 5 — Phân biệt matching strategies.** So sánh `"Straße"` với `"STRASSE"` bằng `equalsIgnoreCase` rồi uppercase ROOT. Tiếp tục so `"\u00E9"` với `"e\u0301"` và NFC. Từ đó lý giải tại sao một hàm so sánh duy nhất không phục vụ cả search, token và identity.

**Bài 6 — Contract của API.** Thiết kế JSON schema cho `username` (case-insensitive ASCII), `orderId` (case-sensitive) và `localeTag` (BCP 47). Viết test với payload đổi case trên từng field, ghi rõ trường nào được xem là cùng giá trị.

## 21. Tài liệu chính thức

- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `toLowerCase(Locale)`, `toLowerCase()`, `toUpperCase(Locale)`, `equalsIgnoreCase`; cảnh báo default locale/Turkish I.
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `Locale.ROOT`, `forLanguageTag`, `toLanguageTag` và quy tắc language/script/region.
- [Java SE 21 — Collator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Collator.html): so sánh văn bản theo locale và strength.
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD cho Unicode normalization, không đồng nhất với case folding.
- [Unicode Standard — Default Case Algorithms](https://www.unicode.org/versions/latest/core-spec/chapter-3/#G33992): Unicode case mappings/case folding và những khác biệt về context.
- [Unicode Technical Standard #39](https://www.unicode.org/reports/tr39/): unicode security profiles và confusable identifiers.

## 22. Ghi nhớ

**Không có một chính sách chữ hoa/chữ thường đúng cho mọi `String`.** Tên hiển thị có thể phải giữ cách viết gốc; username chỉ không phân biệt case khi sản phẩm quy định rõ canonical key; password, token, mã định danh và chữ ký thường cần giữ nguyên chính xác; email cần tách local part khỏi domain; mã tiền tệ và BCP 47 có chuẩn riêng; tìm kiếm và sắp xếp cần chính sách locale khác với khóa định danh.

Với **mã ASCII máy đọc** do chính ứng dụng định nghĩa, `Locale.ROOT` giúp tránh phụ thuộc default JVM khi chuyển case. Với **văn bản đa ngôn ngữ**, cần hiểu case expansion, canonical Unicode normalization, case folding, collation và ngữ nghĩa miền dữ liệu. Hãy thiết kế policy theo từng field, lưu bản gốc khi cần, kiểm tra collision, nhất quán giữa Java/database/API/cache và kiểm thử những trường hợp không chỉ gồm ASCII.