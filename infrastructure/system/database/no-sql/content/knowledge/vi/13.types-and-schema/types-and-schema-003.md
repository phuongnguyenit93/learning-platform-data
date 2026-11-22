# Chuỗi, Unicode, dữ liệu nhị phân và chuẩn hóa giá trị

Trong các cơ sở dữ liệu NoSQL, một trường có vẻ đơn giản như `name`, `email`, `sku` hay `payload` có thể dẫn đến nhiều lỗi khó phát hiện nếu nhóm phát triển không thống nhất **giá trị được biểu diễn, so sánh, lưu trữ và truy vấn như thế nào**. Hai chuỗi hiển thị giống nhau chưa chắc chứa cùng dãy mã Unicode; hai giá trị được mã hóa thành những byte khác nhau có thể mang cùng một ý nghĩa; còn dữ liệu nhị phân không thể mặc nhiên chuyển thành chuỗi UTF-8 mà vẫn giữ nguyên nội dung.

Vì schema của nhiều hệ NoSQL linh hoạt, sự khác biệt này dễ xuất hiện khi dữ liệu đi qua nhiều ứng dụng, ngôn ngữ lập trình, phiên bản API hoặc nguồn nhập liệu. Một dịch vụ ghi khóa người dùng dưới dạng `"Nguyễn Văn A"`, dịch vụ khác tra cứu bằng một biến thể tổ hợp dấu; kết quả có thể là **không tìm thấy bản ghi**, dù giao diện hiển thị gần như giống hệt. Một dịch vụ lưu ảnh dưới dạng Base64 trong JSON mà không giới hạn kích thước có thể khiến document phình to, tốn băng thông và vượt giới hạn của cơ sở dữ liệu.

Bài học trình bày cách thiết kế dữ liệu dựa trên bốn lớp:

1. **Giá trị logic:** một trường mang ý nghĩa nghiệp vụ gì?
2. **Biểu diễn chuỗi và Unicode:** ký tự được mã hóa và chuẩn hóa thế nào?
3. **Biểu diễn nhị phân:** byte được lưu trực tiếp, mã hóa để truyền hay đặt ở kho đối tượng?
4. **Quy tắc canonicalization, validation và truy vấn:** làm sao để mọi đường ghi/đọc sử dụng cùng một contract?

Mục tiêu không phải chuẩn hóa mọi trường theo một công thức chung, mà là **chọn đúng quy tắc cho từng loại dữ liệu và giữ quy tắc ấy nhất quán từ API tới khóa, index và dữ liệu lưu trữ**.

## 1. Kiểu dữ liệu kỹ thuật khác ý nghĩa nghiệp vụ

Giả sử một document chứa:

~~~json
{
  "userId": "000123",
  "displayName": "Nguyễn An",
  "email": "An@example.com",
  "postalCode": "07000",
  "phone": "+84901234567",
  "balance": "125000.50",
  "createdAt": "2026-11-14T08:00:00Z"
}
~~~

Mặc dù nhiều trường được biểu diễn bằng chuỗi JSON, ý nghĩa của chúng rất khác:

| Trường | Ý nghĩa | Không nên làm |
|---|---|---|
| `userId` | Định danh ổn định, có thể có số 0 đầu | Ép thành số `123` và làm mất `000` |
| `displayName` | Chuỗi hiển thị do người dùng chọn | Tự động viết thường hoặc bỏ dấu trong bản gốc |
| `email` | Địa chỉ liên lạc có quy tắc riêng | Mặc định mọi phần của email đều so sánh không phân biệt hoa/thường |
| `postalCode` | Mã định danh địa lý | Ép thành số và mất số 0 đầu |
| `phone` | Số điện thoại đã phân tích theo quy tắc viễn thông | Chỉ xóa khoảng trắng là coi mọi số cùng định dạng |
| `balance` | Số tiền cần quy tắc độ chính xác | Dùng số thực nhị phân rồi so sánh bằng tuyệt đối |
| `createdAt` | Thời điểm trên trục thời gian | So sánh các chuỗi có múi giờ/định dạng tùy ý |

Thiết kế schema tốt cần phân biệt **kiểu lưu trữ** và **quy tắc của miền dữ liệu**. Một trường được lưu dưới dạng string không có nghĩa nó nên được `trim`, chuyển sang chữ thường hoặc loại dấu theo cùng một cách như mọi string khác.

### 1.1. NoSQL schema linh hoạt không có nghĩa dữ liệu tùy ý

Một collection document có thể cho phép:

~~~json
{"userId": "U-1", "age": 23}
~~~

và ở nơi khác:

~~~json
{"userId": "U-2", "age": "23"}
~~~

Hai giá trị `23` dạng số và `"23"` dạng chuỗi có thể dẫn tới kết quả khác khi lọc, sắp xếp hoặc tính toán. Tương tự, một trường `payload` đôi khi là string, đôi khi là binary có thể làm bộ đọc khó xác định semantics.

Vì vậy, ngoài schema của database, ứng dụng cần có **data contract**: kiểu, giới hạn, ý nghĩa, cách chuẩn hóa, quy tắc so sánh và cách xử lý dữ liệu không hợp lệ.

## 2. Chuỗi trong máy tính không phải một dãy “ký tự” đơn giản

Unicode chuẩn hóa việc gán **code point** cho các ký tự và ký hiệu văn bản. Nhưng để lưu chúng, hệ thống còn cần một **encoding** như UTF-8 hoặc UTF-16. Để người dùng nhìn thấy và nhập liệu, lại xuất hiện khái niệm **grapheme cluster** (một đơn vị chữ viết có thể gồm nhiều code point).

Cần phân biệt:

- **Byte:** đơn vị dữ liệu lưu trữ và truyền tải; một byte có 8 bit.
- **Code unit:** đơn vị của một encoding, ví dụ byte trong UTF-8 hoặc đơn vị 16 bit trong UTF-16.
- **Code point:** giá trị Unicode, thường biểu diễn dạng `U+XXXX`.
- **Grapheme cluster:** một ký tự mà người dùng thường cảm nhận, có thể chứa nhiều code point.

### 2.1. Một chữ có thể chiếm nhiều byte UTF-8

Ví dụ:

| Nội dung | Code point minh họa | Số byte UTF-8 |
|---|---|---:|
| `A` | U+0041 | 1 |
| `é` | U+00E9 | 2 |
| `ắ` | U+1EAF | 3 |
| `😀` | U+1F600 | 4 |

Các con số trên áp dụng cho **cách viết bằng một code point đã nêu**. Nếu cùng chữ được biểu diễn bằng một ký tự cơ sở cộng dấu tổ hợp, số code point và số byte có thể khác.

Vì thế:

~~~text
Số ký tự nhìn thấy ≠ số code point ≠ số đơn vị UTF-16 ≠ số byte UTF-8
~~~

Nếu NoSQL giới hạn khóa, document, một thuộc tính string hay request theo **byte**, không thể kiểm tra chỉ bằng “chuỗi có dưới 100 ký tự” rồi chắc chắn an toàn.

### 2.2. Java String.length() không đếm ký tự người dùng nhìn thấy

Trong Java, `String` sử dụng đơn vị **UTF-16 code unit** cho các thao tác như `length()`. Ký hiệu nằm ngoài Basic Multilingual Plane thường được biểu diễn bằng surrogate pair.

~~~java
import java.nio.charset.StandardCharsets;

public class UnicodeLengths {
    public static void main(String[] args) {
        String text = "A😀";

        System.out.println(text.length()); // 3 UTF-16 code units
        System.out.println(
            text.codePointCount(0, text.length())
        ); // 2 Unicode code points
        System.out.println(
            text.getBytes(StandardCharsets.UTF_8).length
        ); // 5 bytes: A (1) + 😀 (4)
    }
}
~~~

Ngay cả `codePointCount()` cũng không phải hàm đếm mọi ký tự hiển thị. Một chữ có dấu tổ hợp hoặc emoji dùng **zero-width joiner (ZWJ)** có thể được hiển thị thành một cụm nhưng gồm nhiều code point.

### 2.3. Grapheme cluster có thể gồm nhiều code point

Ví dụ:

~~~text
é:
  U+00E9               (một code point)

é:
  U+0065 U+0301        (chữ e + dấu sắc tổ hợp)
~~~

Hai dạng có thể hiển thị gần như giống nhau nhưng là hai dãy code point khác nhau.

Một emoji gia đình hoặc emoji có biến thể màu da có thể chứa nhiều code point và dấu nối đặc biệt. Đếm số code point để giới hạn “10 ký tự hiển thị” có thể cho kết quả không như người dùng mong đợi.

**Gợi ý:** Khi giới hạn độ dài cần phù hợp trải nghiệm nhập liệu, hãy xác định rõ giới hạn theo **grapheme cluster** hay theo byte. Các thuật toán phân đoạn grapheme có quy tắc Unicode riêng; thư viện và phiên bản Java có thể hỗ trợ khác nhau đối với các chuỗi emoji phức tạp. Với ứng dụng yêu cầu đầy đủ extended grapheme clusters, cần kiểm chứng thư viện Unicode thích hợp trên dữ liệu thực.

## 3. Unicode normalization: một nội dung, nhiều biểu diễn

Unicode cho phép một số nội dung tương đương được biểu diễn bằng những chuỗi code point khác nhau. **Unicode normalization** đưa những biến thể đó về một dạng chuẩn xác định.

### 3.1. Canonical equivalence: NFC và NFD

Xét chữ `é`:

~~~text
Precomposed:
  U+00E9                 é

Decomposed:
  U+0065 U+0301          e + combining acute accent
~~~

Trong nhiều ngữ cảnh, hai chuỗi này có ý nghĩa văn bản tương đương. Nhưng so sánh trực tiếp theo code unit hoặc byte có thể cho kết quả khác.

Các dạng normalization thường gặp:

- **NFC (Normalization Form C):** canonical decomposition rồi composition theo quy tắc Unicode; thường phù hợp làm dạng chuẩn cho dữ liệu văn bản tổng quát khi chính sách yêu cầu.
- **NFD (Normalization Form D):** canonical decomposition, dùng trong một số pipeline xử lý ký tự/dấu.
- **NFKC (Normalization Form KC):** compatibility decomposition rồi composition; gộp thêm một số dạng trình bày tương thích.
- **NFKD (Normalization Form KD):** compatibility decomposition mà không composition.

Ví dụ NFC có thể đưa chuỗi `e` + dấu sắc tổ hợp về dạng code point U+00E9. Với tiếng Việt, một chữ như `ắ` cũng có thể có cách biểu diễn thành chữ cơ sở và các dấu tổ hợp. Vì vậy người dùng có thể nhập **cùng tên nhìn thấy** nhưng database nhận **những byte khác nhau** nếu không có quy tắc normalization nhất quán.

### 3.2. Ví dụ Java: hai chuỗi trông giống nhau

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;

public class UnicodeNormalizeDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(composed.equals(decomposed)); // false

        String a = Normalizer.normalize(
            composed, Normalizer.Form.NFC
        );
        String b = Normalizer.normalize(
            decomposed, Normalizer.Form.NFC
        );

        System.out.println(a.equals(b)); // true
        System.out.println(
            a.getBytes(StandardCharsets.UTF_8).length
        );
        System.out.println(
            b.getBytes(StandardCharsets.UTF_8).length
        );
    }
}
~~~

Lưu ý rằng normalization chuẩn Unicode không mặc định biến mọi ký tự “nhìn hơi giống nhau” thành cùng một giá trị. Ví dụ chữ Latin `a` và chữ Cyrillic `а` là hai code point khác nhau, có thể tạo **confusable/homoglyph**. NFC không giải quyết triệt để giả mạo tên người dùng, tên miền hoặc định danh bằng ký tự tương tự hình dạng.

### 3.3. NFKC có thể thay đổi những phân biệt có ý nghĩa

Khác với NFC, **NFKC** còn thực hiện một số chuyển đổi tương thích, chẳng hạn các dạng chữ fullwidth hoặc ký hiệu trình bày đặc biệt. Điều đó hữu ích khi tạo khóa tìm kiếm hoặc canonical identifier theo chính sách rõ ràng, nhưng cũng có thể làm mất phân biệt mà người dùng hoặc nghiệp vụ muốn giữ.

Ví dụ có thể có:

~~~text
Chuỗi để hiển thị:  ＡＢＣ
Khóa tìm kiếm theo NFKC: ABC
~~~

Đừng áp dụng NFKC cho mọi trường dữ liệu gốc rồi ghi đè giá trị người dùng nhập. Với tài liệu pháp lý, tên sản phẩm cần giữ cách viết, nội dung nghệ thuật hoặc một định danh có quy tắc riêng, phép chuyển đổi tương thích có thể không được phép.

### 3.4. Nên lưu gì: giá trị gốc hay giá trị chuẩn?

Một chiến lược hữu ích là lưu cả hai:

~~~json
{
  "displayName": "Nguyễn An",
  "displayNameSearchKey": "nguyễn an",
  "normalizationVersion": 2
}
~~~

Trong ví dụ:

- `displayName` bảo toàn nội dung được chọn để hiển thị.
- `displayNameSearchKey` là dữ liệu dẫn xuất theo chính sách đã định nghĩa.
- `normalizationVersion` giúp biết quy tắc nào đã tạo ra khóa nếu hệ thống có kế hoạch thay đổi.

**Không nên mặc định search key trong ví dụ là một định dạng chuẩn Unicode có sẵn.** Nó có thể là kết quả của NFC, một quy tắc chữ hoa/thường, xử lý khoảng trắng và analyzer; mọi bước phải được tài liệu hóa.

## 4. Chuẩn hóa Unicode khác chuyển chữ hoa/thường và bỏ dấu

Ba việc này có thể đi cùng nhau, nhưng không giống nhau:

1. **Unicode normalization:** điều chỉnh dạng biểu diễn tương đương của code point.
2. **Case conversion/case folding:** xử lý phân biệt chữ hoa và chữ thường theo chính sách.
3. **Accent folding/transliteration:** chuyển hoặc bỏ dấu và có thể thay đổi cách viết.

Ví dụ tên người:

~~~text
Nguyễn
NGUYỄN
Nguyen
~~~

Chúng có thể liên quan trong tìm kiếm, nhưng **không nên mặc định là cùng định danh chính xác**. Tên có dấu và không dấu là hai giá trị hiển thị khác nhau; tìm kiếm có thể nới lỏng điều kiện theo yêu cầu sản phẩm.

### 4.1. Chữ hoa/thường phụ thuộc ngôn ngữ và mục đích

Chuyển chữ thường không phải phép so sánh không phân biệt hoa/thường hoàn chỉnh cho mọi ngôn ngữ. Một ví dụ điển hình là chữ `I` và các biến thể của tiếng Thổ Nhĩ Kỳ; quy tắc tại một locale có thể khác quy tắc không phụ thuộc locale.

Với một **khóa kỹ thuật được định nghĩa là case-insensitive**, nhóm phải chọn thuật toán và locale rõ ràng. Trong Java, nếu dùng `toLowerCase()` cho khóa kỹ thuật, hãy chỉ định locale phù hợp, thường là `Locale.ROOT` cho quy tắc không phụ thuộc ngôn ngữ. Tuy nhiên, lowercase vẫn không thay thế đầy đủ **Unicode case folding** trong mọi trường hợp.

~~~java
import java.text.Normalizer;
import java.util.Locale;

public class SearchKey {
    public static String makeKey(String input) {
        String nfc = Normalizer.normalize(
            input, Normalizer.Form.NFC
        );
        return nfc.toLowerCase(Locale.ROOT);
    }
}
~~~

Hàm trên chỉ thực hiện **NFC + lowercase ROOT**. Nó chưa xử lý khoảng trắng, accent folding, giới hạn độ dài, ký tự confusable hoặc quy tắc của một sản phẩm cụ thể. Không nên dùng nó như một canonicalization phổ quát cho username, email, số điện thoại và toàn bộ text.

### 4.2. Bỏ dấu chỉ phù hợp với một số loại tìm kiếm

Khi tạo trường tìm kiếm cho một danh sách địa điểm, ứng dụng có thể muốn truy vấn `"Ha Noi"` tìm thấy `"Hà Nội"`. Nhưng với tên hiển thị hoặc định danh cần chính xác, việc bỏ dấu có thể làm hai tên hợp lệ trùng nhau.

Một pipeline tìm kiếm có thể:

~~~text
display value -> NFC -> phân tích từ -> lowercase
                                  -> accent folding (nếu sản phẩm cần)
                                  -> tokens trong search index
~~~

Giữ nguyên bản hiển thị. Các bộ phân tích từ/tokenizer và collation nên được thiết kế riêng cho use case, không áp dụng một chuỗi xử lý cố định cho mọi collection.

### 4.3. Zero-width và ký tự điều khiển

Unicode có các ký tự điều khiển, định dạng và ký tự không có độ rộng hiển thị thông thường. Một chuỗi có thể trông giống nhau nhưng chứa:

- Zero-width joiner dùng hợp lệ trong một số cụm ký tự hoặc emoji.
- Các ký tự điều khiển hướng văn bản.
- Ký tự khoảng trắng khác nhau.
- Dấu tổ hợp ở vị trí đặc biệt.

Xóa tất cả ký tự “không nhìn thấy” có thể phá nội dung hợp lệ; chấp nhận vô điều kiện có thể gây nhầm lẫn hoặc lạm dụng trong identifier. Cách đúng là **định nghĩa chính sách theo từng trường**: trường hiển thị có thể cho phép nhiều ký tự hơn trường định danh kỹ thuật; các trường nhạy cảm cần phát hiện ký tự gây giả mạo hoặc hiển thị khó hiểu.

## 5. Không tồn tại một hàm normalize() dùng cho mọi dữ liệu

Với từng trường, cần chốt **mục đích sử dụng** trước khi chuyển đổi:

| Dữ liệu | Giá trị lưu để hiển thị | Khóa so sánh/truy vấn | Gợi ý chính sách |
|---|---|---|---|
| Tên hiển thị | Bảo toàn nội dung hợp lệ | Có thể có search key riêng | NFC nếu contract yêu cầu; không tự bỏ dấu ở bản gốc |
| Username | Theo quy tắc đặt tên sản phẩm | Canonical ID được version hóa | Giới hạn tập ký tự, case policy, uniqueness |
| SKU | Mã theo quy tắc catalog | Khớp chính xác hoặc canonical SKU | Chỉ thay hoa/thường/khoảng trắng nếu đặc tả cho phép |
| Email | Chuỗi địa chỉ được xác minh | Quy tắc của ứng dụng và hệ email | Không mặc định mọi phần đều không phân biệt hoa/thường |
| Phone | Số theo quốc gia/vùng | Dạng chuẩn từ thư viện viễn thông | Cần country context, không chỉ xóa dấu `+` |
| Postal code | Chuỗi mã | Chính sách từng quốc gia | Giữ số 0 đầu, không ép số |
| Free text | Nội dung gốc | Search index/analyzer riêng | Tránh thay nội dung gốc khi tối ưu tìm kiếm |
| Mật khẩu | Giá trị bí mật theo contract đăng nhập | Không dùng khóa tìm kiếm thường | Không tùy tiện trim, lowercase hay NFKC; lưu bằng cơ chế băm mật khẩu phù hợp |
| Binary object | Dãy byte nguyên vẹn | ID/hash nếu dùng | Không diễn giải thành text nếu chưa biết encoding |

### 5.1. Username cần quy tắc duy nhất

Giả sử sản phẩm muốn xem `"AN123"` và `"an123"` là cùng username. Có thể lưu:

~~~json
{
  "userId": "U-123",
  "usernameDisplay": "An123",
  "usernameKey": "an123",
  "usernameKeyVersion": 1
}
~~~

Nhưng **uniqueness phải được bảo vệ tại database hoặc trong giao thức ghi cạnh tranh**, không thể chỉ kiểm tra bằng truy vấn rồi insert:

~~~text
Request A: lookup usernameKey="an123" -> chưa có
Request B: lookup usernameKey="an123" -> chưa có
Request A: insert
Request B: insert
~~~

Nếu cả hai cùng thành công, hai tài khoản có cùng định danh logic. Cần unique index, conditional put, compare-and-set hoặc cơ chế tương đương theo sản phẩm. Có thể dùng record giữ chỗ riêng cho usernameKey nếu mô hình dữ liệu yêu cầu; thao tác này cũng phải có idempotency và recovery rõ ràng.

### 5.2. Email cần chính sách riêng

Email có phần local trước `@` và phần domain sau `@`, với quy tắc xử lý khác nhau. Domain có thể được chuẩn hóa theo quy tắc tên miền thích hợp; phần local về mặt tiêu chuẩn có những trường hợp phân biệt chữ hoa/thường và quốc tế hóa.

Vì vậy, đừng tự động kết luận chỉ cần `email.toLowerCase()` là chuẩn cho toàn bộ hệ. Nếu ứng dụng chọn email làm định danh đăng nhập không phân biệt hoa/thường, đó là **quyết định sản phẩm** cần được triển khai nhất quán với xác minh email, ràng buộc duy nhất, dữ liệu lịch sử và các trường hợp quốc tế hóa.

### 5.3. Số điện thoại không chỉ là chuỗi gồm chữ số

Đầu vào `090 123 4567` và `+84 90 123 4567` có thể chỉ cùng một số trong bối cảnh quốc gia phù hợp, nhưng không phải có thể suy ra bằng cách bỏ khoảng trắng. Chuẩn hóa số điện thoại cần thông tin vùng, mã quốc gia, extension, đầu số và thư viện chuyên dụng.

Mã bưu chính như `"07000"` hoặc định danh `"000123"` phải giữ dạng chuỗi nếu số 0 đầu là một phần ý nghĩa.

## 6. So sánh, sắp xếp và collation trong NoSQL

Một chuỗi có thể được so sánh theo nhiều cơ chế:

- So sánh byte nhị phân.
- So sánh code point/code unit.
- So sánh không phân biệt hoa/thường.
- So sánh theo **collation** của locale.
- Tìm kiếm qua analyzer/tokenizer đã biến đổi từ.

Các cơ chế này không tương đương.

### 6.1. Binary equality và canonical equality

Giả sử hai biến thể chữ `é` được lưu theo byte khác nhau. Một truy vấn **exact match** dựa trên byte/string trực tiếp có thể không trả cả hai. Nếu ứng dụng muốn xem chúng là cùng khóa, phải thống nhất normalization trước khi ghi và trước khi truy vấn hoặc sử dụng cơ chế collation phù hợp đã được kiểm chứng.

Điểm quan trọng: **không nên đoán rằng database tự áp dụng NFC**, vì mỗi hệ có semantics riêng và một index có thể sử dụng binary equality.

### 6.2. Sort theo ngôn ngữ khác sort theo byte

Danh sách tên tiếng Việt như `"An"`, `"Ánh"`, `"Anh"`, `"Ân"` có thể được sắp xếp khác nhau tùy quy tắc collation. Thứ tự dựa trên UTF-8 byte không đồng nghĩa thứ tự từ điển tiếng Việt người dùng mong đợi.

Khi thiết kế màn hình danh sách, xác định:

1. Locale nào áp dụng?
2. Có phân biệt hoa/thường và dấu không?
3. Có sắp theo số trong chuỗi hay không, ví dụ `item2` và `item10`?
4. Có cần tie-breaker ổn định để phân trang?
5. Index có dùng cùng collation với truy vấn không?

### 6.3. Collation và index phải khớp

Một database document có thể hỗ trợ index hoặc truy vấn theo collation; sản phẩm khác chỉ hỗ trợ so sánh byte hoặc cần trường normalized key riêng.

Ví dụ conceptual:

~~~text
Index:
    key = (tenantId, usernameKey)

Query:
    tenantId = T-1
    usernameKey = normalizeUsername(input)
~~~

Nếu index được tạo trên bản gốc nhưng ứng dụng truy vấn bản lowercase, query có thể không sử dụng index như mong đợi hoặc trả kết quả khác. Cần thiết kế từ access pattern, đo query plan và xác định chính xác cách DB xử lý collation.

### 6.4. Phiên bản Unicode/collation có thể thay đổi

Unicode và thư viện collation được cập nhật theo thời gian. Khi service hoặc database nâng phiên bản, một số trường hợp đặc biệt có thể đổi cách phân đoạn, so sánh hoặc sắp xếp. Với khóa có ràng buộc uniqueness hoặc pagination dựa trên sort key, đây là thay đổi cần được quản lý như **schema migration**, không chỉ là nâng dependency vô hại.

Nếu thay thuật toán canonicalization, nên có version và kế hoạch xử lý những khóa trước đây được xem là khác nhau nhưng nay thành trùng.

## 7. Chuẩn hóa giá trị: rộng hơn Unicode

“Chuẩn hóa giá trị” trong một hệ NoSQL không chỉ là đưa text về NFC. Nó còn có nghĩa **chọn một biểu diễn ổn định cho cùng một khái niệm nghiệp vụ**, để các hệ thống không lưu kiểu hoặc đơn vị khác nhau.

### 7.1. Số, tiền và độ chính xác

Ví dụ hai service ghi giá tiền:

~~~json
{"amount": 125000.5, "currency": "VND"}
~~~

và:

~~~json
{"amount": "125000.50", "currency": "VND"}
~~~

Đó là hai kiểu dữ liệu khác nhau trong JSON. Nếu một hệ dùng số thực nhị phân, phép cộng tiền có thể phát sinh sai số biểu diễn. Một lựa chọn tốt có thể là **số nguyên theo đơn vị nhỏ nhất** hoặc kiểu decimal có độ chính xác quy định, tùy loại tiền và nghiệp vụ.

~~~json
{
  "amountMinor": 12500050,
  "currency": "VND",
  "scale": 2
}
~~~

Ví dụ dùng scale 2 chỉ là một contract giả định; không có quy tắc rằng mọi loại tiền đều dùng hai chữ số thập phân. Cần chọn đơn vị và độ chính xác theo miền nghiệp vụ, và dùng kiểu hỗ trợ trong DB phù hợp.

### 7.2. Số nguyên rất lớn trong JSON

JSON chỉ mô tả cú pháp number, không bắt buộc mọi runtime giữ độ chính xác như nhau. Một số môi trường dùng số thực IEEE-754 binary64 cho JSON number, không thể biểu diễn chính xác mọi số nguyên lớn hơn giới hạn an toàn 53 bit.

Nếu ID hoặc counter có thể rất lớn, cần contract nhất quán giữa client và server, ví dụ lưu **ID dạng chuỗi** hoặc dùng typed integer/decimal và serializer phù hợp. Tránh biến định danh `"00123"` thành số vì sẽ mất số 0 đầu.

### 7.3. Thời gian và múi giờ

Các chuỗi:

~~~text
2026-11-14T08:00:00Z
2026-11-14T15:00:00+07:00
~~~

biểu diễn **cùng một thời điểm** trên trục UTC. Nhưng so sánh hai chuỗi ký tự một cách máy móc chưa chắc đúng nếu chúng có offset/độ chính xác/định dạng khác nhau.

Với dữ liệu cần so sánh thời điểm, nên lưu kiểu timestamp hoặc định dạng UTC chuẩn đã được thống nhất, kèm timezone nếu nghiệp vụ cần biết vùng gốc. Với lịch hẹn theo giờ địa phương, chỉ lưu UTC có thể không đủ để giữ quy tắc “9 giờ sáng theo múi giờ của địa điểm” khi cần tính lại lịch.

### 7.4. Null, missing và chuỗi rỗng

Trong document NoSQL, ba trạng thái có thể khác nhau:

~~~json
{"nickname": null}
~~~

~~~json
{}
~~~

~~~json
{"nickname": ""}
~~~

**Null** có thể nghĩa “được biết là không có”, **missing** nghĩa “chưa được cung cấp hoặc không thuộc schema phiên bản này”, còn chuỗi rỗng là một giá trị. Ngữ nghĩa tùy domain, nhưng phải chốt rõ để validation, indexing và migration không coi mọi trạng thái là tương đương một cách vô tình.

### 7.5. Khoảng trắng và dạng nhập liệu

Tự động `trim` có thể hữu ích với một số trường tên hoặc mã do con người nhập, nhưng không nên áp dụng vô điều kiện cho nội dung văn bản, mật khẩu, mã có khoảng trắng hợp lệ hoặc dữ liệu nhị phân.

Ngay cả chữ “khoảng trắng” cũng bao gồm nhiều code point. Nếu chính sách muốn gộp chuỗi nhiều khoảng trắng thành một dấu cách, cần xác định chính xác những loại whitespace nào được xử lý và có mất thông tin có ý nghĩa không.

## 8. Binary data không phải string

**Dữ liệu nhị phân (binary data)** là một dãy byte mà ứng dụng có thể diễn giải bằng một định dạng cụ thể: ảnh, PDF, file âm thanh, dữ liệu nén, ciphertext, protobuf hoặc một payload tùy biến.

Không phải mọi byte đều tạo thành một chuỗi UTF-8 hợp lệ. Nếu cố giải mã bytes tùy ý thành text, có thể xảy ra lỗi, ký tự thay thế hoặc mất dữ liệu khi mã hóa lại.

### 8.1. Phân biệt text và bytes

~~~text
Text:
    "Xin chào"

Encoding:
    UTF-8

Bytes:
    dãy byte biểu diễn đoạn text đó theo UTF-8
~~~

Ngược lại, một file PNG chứa header và dữ liệu nhị phân không nên được đọc như nội dung văn bản. Dù có thể mã hóa toàn bộ file thành một chuỗi Base64, bản chất dữ liệu vẫn là **binary**, không trở thành text thông thường.

### 8.2. Dùng kiểu binary gốc nếu database hỗ trợ

Tùy sản phẩm, kiểu có thể tên là `blob`, `bytes`, `Binary` hoặc một kiểu tương đương. Ví dụ:

- Một hệ CQL có kiểu `blob`.
- Một hệ document BSON có kiểu binary riêng.
- Một key–value/document service có thể hỗ trợ thuộc tính binary.

Các giới hạn kích thước item/document vẫn áp dụng theo sản phẩm, và binary có thể bị giới hạn riêng. Không nên suy luận cứ có kiểu binary là có thể lưu file nhiều gigabyte trong một record.

### 8.3. JSON không có kiểu byte array chuẩn

JSON cung cấp string, number, boolean, null, array và object; nó không định nghĩa một kiểu binary nguyên thủy. Khi truyền bytes qua một API JSON, thường cần **quy ước mã hóa**, phổ biến nhất là Base64:

~~~json
{
  "objectId": "F-91",
  "contentType": "image/png",
  "encoding": "base64",
  "data": "iVBORw0KGgoAAAANSUhEUg..."
}
~~~

Chuỗi trên chỉ minh họa một phần payload, không phải một file PNG hoàn chỉnh. Client cần biết trường `encoding` và giải mã đúng một lần.

### 8.4. Base64 không phải nén hoặc mã hóa bảo mật

Base64 biểu diễn mỗi nhóm 3 byte thành 4 ký tự ASCII (có thể thêm padding). Với payload lớn, kích thước tăng xấp xỉ **33%** trước các overhead khác:

~~~text
100 bytes binary -> 4 × ceil(100 / 3) = 136 ký tự Base64
~~~

Nếu lưu Base64 vào JSON rồi lưu chuỗi đó vào database, ta có thể tăng kích thước document, băng thông và chi phí xử lý. Base64 **không mã hóa bảo mật**: bất kỳ ai có dữ liệu đều có thể giải mã lại bytes.

### 8.5. Ví dụ Java: chuyển đúng giữa String và bytes

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;

public class BinaryRoundTrip {
    public static void main(String[] args) {
        String original = "Tiếng Việt: ắ 😀";

        byte[] utf8 = original.getBytes(
            StandardCharsets.UTF_8
        );

        String base64 = Base64.getEncoder()
            .encodeToString(utf8);

        byte[] decoded = Base64.getDecoder()
            .decode(base64);

        String restored = new String(
            decoded, StandardCharsets.UTF_8
        );

        System.out.println(Arrays.equals(utf8, decoded)); // true
        System.out.println(original.equals(restored));     // true
    }
}
~~~

Ví dụ này hợp lệ vì bytes ban đầu được **chủ động tạo từ một String UTF-8**. Với ảnh hoặc ciphertext, cần giữ bytes nguyên trạng; không cố chuyển chúng thành String rồi chuyển ngược nếu chưa biết định dạng.

### 8.6. Endianness và serialization

Với định dạng binary chứa số nguyên, floating-point hoặc cấu trúc nhiều trường, hai chương trình còn phải thống nhất **endianness, chiều dài, signed/unsigned, version và field layout**.

Ví dụ:

~~~text
Payload:
  version: 1 byte
  temperatureScaled: 4 bytes, signed, big-endian
  measuredAtEpochMillis: 8 bytes, signed, big-endian
~~~

Đây chỉ là thiết kế giả định. Nếu một service đọc little-endian và service khác ghi big-endian, bytes có thể được diễn giải thành giá trị sai dù truyền tải không mất byte. Những định dạng có schema/version như protobuf hoặc Avro giải quyết một phần vấn đề, nhưng vẫn đòi hỏi quản lý contract và tương thích phiên bản.

## 9. Lưu file nhị phân trong document hay object storage?

Một ảnh đại diện vài kilobyte có thể được lưu trực tiếp dưới dạng binary trong một số hệ nếu giới hạn và workload cho phép. Nhưng file ảnh, video, bản ghi âm hoặc tài liệu lớn thường cần đánh giá một **object storage** bên ngoài database.

### 9.1. Lưu inline

~~~json
{
  "attachmentId": "ATT-1",
  "fileName": "avatar.png",
  "contentType": "image/png",
  "byteLength": 28192,
  "binaryPayload": "<native binary field in DB>"
}
~~~

Ưu điểm: một record có đủ metadata và bytes; vòng đời lưu có thể đơn giản cho object nhỏ.

Đánh đổi: document lớn hơn, ghi/read amplification, replication, backup và giới hạn kích thước; các API chỉ cần metadata có thể bị ảnh hưởng nếu lưu chung với file lớn.

### 9.2. Lưu bằng object reference

~~~json
{
  "attachmentId": "ATT-1",
  "ownerId": "U-42",
  "storageKey": "tenant/T-1/attachments/ATT-1",
  "contentType": "image/png",
  "byteLength": 28192,
  "sha256": "6fbf...example...3d2a",
  "status": "READY",
  "createdAt": "2026-11-14T08:00:00Z"
}
~~~

Bytes nằm trong object storage; document giữ metadata, ID, trạng thái và khóa tham chiếu. Trường `sha256` ở đây chỉ minh họa định danh checksum, không phải một digest hợp lệ để dùng thực tế.

~~~mermaid
flowchart LR
    CLIENT["Client upload"] --> UP["Upload service"]
    UP --> STORE[("Object storage: bytes")]
    UP --> META[("NoSQL: attachment metadata")]
    API["Attachment read API"] --> META
    API --> AUTH["Kiểm tra quyền"]
    AUTH --> STORE
~~~

Một số vấn đề mới phát sinh:

- Làm sao bảo đảm metadata không trỏ tới object chưa upload thành công?
- Nếu upload thành công nhưng ghi metadata thất bại thì xử lý object mồ côi ra sao?
- Nếu xóa metadata thì object và các bản sao có được dọn không?
- Ai có quyền đọc file, URL tải có hết hạn hay không?
- Kiểm tra kích thước thực, định dạng nội dung và mã độc như thế nào?

### 9.3. Một workflow upload có trạng thái

~~~text
1. Tạo Attachment metadata: status = PENDING.
2. Upload bytes tới object storage theo objectId ổn định.
3. Xác minh checksum, kích thước và chính sách nội dung.
4. Chuyển Attachment sang READY bằng thao tác an toàn.
5. Job đối soát dọn PENDING quá hạn và object mồ côi.
~~~

Khi không có transaction chung giữa NoSQL và object storage, workflow cần **idempotency, trạng thái bền, retry và garbage collection có kiểm soát**. Không nên tuyên bố hai hệ được commit nguyên tử chỉ vì được gọi trong một request HTTP.

### 9.4. Content type không phải bằng chứng file an toàn

Trường MIME type hoặc đuôi file do client gửi có thể sai. Nếu cần xử lý file upload, phải kiểm tra magic bytes/định dạng, kích thước, quyền truy cập, chính sách mã độc và cách phục vụ download. Hash như SHA-256 có thể dùng kiểm tra toàn vẹn bytes; hash đơn thuần không chứng minh nội dung không độc hại hoặc đáp ứng mọi yêu cầu bảo mật.

## 10. Hashing, canonical keys và tính đúng đắn của định danh

Một số hệ dùng chuỗi sau khi chuẩn hóa làm **partition key**, **unique key** hoặc thành phần của một hash. Khi đó mọi phiên bản thuật toán chuẩn hóa đều ảnh hưởng trực tiếp tới nơi dữ liệu được lưu và cách truy vấn.

### 10.1. Hash bytes của giá trị sau khi canonicalize

Nếu muốn dùng một chuỗi làm input cho hash:

~~~text
input
  -> field-specific validation
  -> field-specific canonicalization
  -> encode as UTF-8
  -> hash bytes
~~~

Hai service phải thực hiện cùng từng bước để cho ra cùng hash. Nếu một service dùng NFC còn service khác dùng NFD, hash có thể khác dù chữ hiển thị giống nhau.

### 10.2. Hash không thay thế so sánh và uniqueness

Hash có thể có collision về lý thuyết, tùy thuật toán và độ dài digest. Trong nhiều hệ, nếu hash dùng làm bucket hoặc lookup key, vẫn cần giữ canonical value hoặc cơ chế xác minh tương đương để kiểm tra đúng bản ghi. Nếu khóa là thông tin nhạy cảm như email, việc băm trực tiếp không nhất thiết bảo vệ khỏi suy đoán từ tập giá trị nhỏ; cần mô hình bảo vệ dữ liệu theo threat model.

### 10.3. Canonicalization policy phải version hóa

Ví dụ:

~~~json
{
  "userId": "U-42",
  "usernameOriginal": "An123",
  "usernameKey": "an123",
  "usernameKeyPolicy": "username-v1"
}
~~~

Khi nâng quy tắc v1 lên v2, có thể có hai username trước đây khác nhau nhưng nay tạo cùng key. Nếu âm thầm ghi đè giá trị normalized, có thể tạo collision, mất quyền truy cập hoặc phân phối khóa sang partition khác.

Quy trình đổi policy cần tìm và giải quyết collision, migration index, dual-read/cutover nếu cần và bảo đảm mọi service thống nhất phiên bản.

### 10.4. Confusable cần xử lý theo threat model

Unicode có các ký tự tương tự hình dạng qua nhiều bảng chữ. Ví dụ Latin `a` và Cyrillic `а` có thể khiến một tên nhìn như tên khác. NFC/NFKC không phải một công cụ hoàn chỉnh để phát hiện spoofing.

Với username, tên miền, tenant slug hoặc định danh có ảnh hưởng bảo mật, cần quy tắc cho phép bảng chữ, phát hiện mixed-script/confusable hoặc kiểm duyệt thích hợp. Không áp dụng những ràng buộc đó tùy tiện cho nội dung văn bản tự do hợp lệ của người dùng.

## 11. Data contract cho string và binary

Mỗi trường quan trọng nên có **contract rõ ràng**:

~~~text
Field: username
Type: string
Required: true
Normalization: NFC + domain-specific case policy
Allowed characters: documented set
Maximum length: measured in code points and UTF-8 bytes
Equality: canonical usernameKey
Uniqueness: enforced at storage/conditional write boundary
Display value: preserved separately
Policy version: username-v2
~~~

Với file:

~~~text
Field: attachment
Type: binary object reference
Required: optional
Maximum size: enforced by upload service
Content type: validated after upload
Checksum: SHA-256 over original bytes
Storage: object storage
Metadata status: PENDING / READY / FAILED
Retention: policy per owner/content category
Access: checked through application authorization
~~~

### 11.1. Validation ở nhiều lớp

Việc kiểm tra cần nhất quán:

- **API boundary:** parse đúng encoding, xác thực kiểu và kích thước, đưa lỗi rõ ràng.
- **Domain layer:** kiểm tra ý nghĩa nghiệp vụ và canonicalization theo field.
- **Storage layer:** bảo vệ uniqueness/atomicity, document size và các constraint hỗ trợ.
- **Ingestion/background jobs:** dùng cùng policy, tránh import lách qua validation.
- **Read/query layer:** chuẩn hóa input theo đúng policy trước khi tra khóa.

Chỉ kiểm tra trong giao diện không đủ: import, job, consumer và dịch vụ khác có thể ghi trực tiếp vào NoSQL.

### 11.2. Thứ tự các bước có thể thay đổi kết quả

Một pipeline có thể là:

~~~text
Raw input
    |
    v
Decode UTF-8 có kiểm tra lỗi
    |
    v
Field validation cơ bản
    |
    v
Normalize Unicode theo policy
    |
    v
Domain-specific canonicalization
    |
    v
Kiểm tra độ dài sau chuyển đổi
    |
    v
Unique/conditional write
    |
    v
Lưu original + canonical value
~~~

Một số trường có thể cần kiểm tra cả **trước và sau** chuẩn hóa. Ví dụ giới hạn request bytes để chống payload quá lớn trước khi làm việc nặng; sau chuẩn hóa lại kiểm tra chiều dài canonical key và các ký tự được phép. Thứ tự chính xác tùy domain, nhưng phải được quy định và thử nghiệm.

### 11.3. Không âm thầm sửa dữ liệu nhạy cảm

Với nội dung pháp lý, mật khẩu, khóa API, chữ ký hoặc byte đã được ký số, normalization có thể làm thay đổi giá trị và khiến xác minh thất bại. Chỉ áp dụng các biến đổi khi contract cho phép; nếu không, nên kiểm tra và từ chối đầu vào không hợp lệ thay vì tự sửa.

## 12. Ví dụ Java: chuẩn hóa, đo byte và xử lý binary

Đoạn Java dưới đây minh họa một hàm tạo key đơn giản theo một **policy đã định nghĩa**, không phải giải pháp chuẩn hóa cho mọi loại dữ liệu.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Locale;

public final class UserKeyPolicy {
    private static final int MAX_KEY_BYTES = 128;

    private UserKeyPolicy() {}

    public static String canonicalize(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("username is required");
        }

        String nfc = Normalizer.normalize(
            raw, Normalizer.Form.NFC
        );
        String canonical = nfc.toLowerCase(Locale.ROOT);

        if (canonical.isEmpty()) {
            throw new IllegalArgumentException("username is empty");
        }

        int bytes = canonical.getBytes(
            StandardCharsets.UTF_8
        ).length;

        if (bytes > MAX_KEY_BYTES) {
            throw new IllegalArgumentException(
                "username key exceeds byte limit"
            );
        }

        return canonical;
    }
}
~~~

Hàm cố ý **không trim, không accent fold và không kiểm tra tập ký tự** để nhấn mạnh rằng các bước ấy phải xuất phát từ policy. Nếu sản phẩm không cho phép khoảng trắng hoặc ký tự điều khiển, phải bổ sung validation cụ thể. Nếu cần case folding Unicode đầy đủ, dùng thư viện/thuật toán phù hợp thay vì coi lowercase ROOT tương đương case folding cho mọi ngôn ngữ.

### 12.1. Độ dài của chuỗi

~~~java
import java.nio.charset.StandardCharsets;

public class StringMeasurements {
    public static void main(String[] args) {
        String s = "ắ😀";

        int utf16Units = s.length();
        int codePoints = s.codePointCount(0, s.length());
        int utf8Bytes = s.getBytes(
            StandardCharsets.UTF_8
        ).length;

        System.out.println("UTF-16 units: " + utf16Units);
        System.out.println("Code points: " + codePoints);
        System.out.println("UTF-8 bytes: " + utf8Bytes);
    }
}
~~~

Với hai code point minh họa, các phép đo lần lượt là **3 đơn vị UTF-16**, **2 code point** và **7 byte UTF-8**. Điều này không đồng nghĩa với số grapheme cluster trong trường hợp chuỗi phức tạp hơn.

### 12.2. Binary encoding không thay đổi nội dung gốc

~~~java
import java.util.Base64;
import java.util.Arrays;

public class BytePayload {
    public static void main(String[] args) {
        byte[] data = new byte[] {
            (byte) 0x00, (byte) 0xFF, (byte) 0x10
        };

        String encoded = Base64.getEncoder()
            .encodeToString(data);

        byte[] decoded = Base64.getDecoder()
            .decode(encoded);

        System.out.println(encoded);
        System.out.println(Arrays.equals(data, decoded)); // true
    }
}
~~~

Ví dụ binary này cố tình có byte `0xFF`, vốn không phải một byte đơn có thể giải mã thành UTF-8 hợp lệ ở vị trí độc lập. Vì vậy không nên chuyển arbitrary bytes qua String bằng encoding đoán mò.

## 13. Case study: tài khoản người dùng, tra cứu và ảnh đại diện

Giả sử ứng dụng có yêu cầu:

- Người dùng chọn display name có dấu tiếng Việt.
- Username dùng để đăng nhập, không phân biệt hoa/thường theo policy sản phẩm.
- Tên hiển thị có thể tìm kiếm theo cả dạng có dấu và không dấu.
- Mỗi người dùng có avatar có thể thay đổi.
- Có import dữ liệu từ hệ thống cũ.
- Nhiều request có thể đồng thời đăng ký username giống nhau.

### 13.1. Mô hình dữ liệu đề xuất

~~~json
{
  "userId": "U-42",
  "usernameDisplay": "An123",
  "usernameKey": "an123",
  "usernameKeyVersion": 1,
  "displayName": "Nguyễn An",
  "displayNameNfc": "Nguyễn An",
  "avatarAttachmentId": "ATT-91",
  "createdAt": "2026-11-14T08:00:00Z",
  "schemaVersion": 2
}
~~~

Những trường phục vụ mục đích khác nhau:

- `userId` là định danh ổn định, không nên dựa trên display name.
- `usernameKey` phục vụ exact lookup/uniqueness.
- `displayName` phục vụ hiển thị theo nội dung đã chấp nhận.
- `displayNameNfc` là dạng normalized nếu policy cần.
- Tìm kiếm không dấu có thể dùng search index riêng, thay vì thay bản hiển thị.
- `avatarAttachmentId` tham chiếu metadata file, không nhúng tất cả bytes vào User.

### 13.2. Đăng ký username

~~~text
Client gửi username
  -> xác thực định dạng, độ dài và policy
  -> tạo usernameKey
  -> tạo User và giữ usernameKey duy nhất
     bằng transaction/conditional write phù hợp
  -> trả userId
~~~

Khi hai request đồng thời gửi `"AN123"` và `"an123"`, cả hai phải được chuẩn hóa cùng policy. Bảo đảm duy nhất phải nằm ở ranh giới storage, không dựa vào hai lần truy vấn “kiểm tra đã có username chưa”.

### 13.3. Tìm kiếm display name

Một người tìm `"Nguyen An"` có thể muốn thấy `"Nguyễn An"`, nhưng màn hình hồ sơ vẫn phải hiển thị đúng tên gốc.

Có thể dùng:

~~~text
displayName
  -> Unicode normalization
  -> tokenizer
  -> lowercase
  -> accent folding (nếu được cho phép)
  -> search index tokens
~~~

Không dùng search key này để quyết định uniqueness của user nếu chính sách username khác. **Tìm thấy gần giống** và **định danh bằng nhau** là hai phép kiểm tra khác nhau.

### 13.4. Avatar

User chỉ giữ attachmentId. Metadata avatar lưu content type đã kiểm tra, byte length, checksum, storage key và trạng thái READY. Bytes lưu ở object storage, có quyền truy cập và workflow xóa/đổi avatar.

Đổi avatar có thể tạo object mới, cập nhật tham chiếu trong User và đưa object cũ vào quy trình dọn. Nếu ghi metadata hoặc object storage lỗi giữa chừng, trạng thái và job đối soát giúp tránh file mồ côi hoặc tham chiếu hỏng.

### 13.5. Kết quả thiết kế

Ta tách được:

1. Bản hiển thị giữ đúng ngôn ngữ người dùng.
2. Khóa username ổn định để truy vấn và bảo vệ uniqueness.
3. Search index tối ưu matching mà không thay đổi định danh.
4. Binary avatar có vòng đời và giới hạn riêng.

Đây là ví dụ cho thấy **kiểu dữ liệu, normalization, access pattern và bất biến dữ liệu** phải được quyết định cùng nhau.

## 14. Migration dữ liệu cũ khi thay quy tắc chuẩn hóa

Thay đổi chuẩn hóa của một trường đã dùng làm khóa/index là một **data migration**, không chỉ sửa một hàm Java.

Giả sử hệ trước đây lưu username nguyên bản và so sánh phân biệt hoa/thường. Nay yêu cầu username không phân biệt hoa/thường. Hai tài khoản `"An123"` và `"an123"` trước đây khác nhau, nhưng sẽ tạo cùng canonical key.

### Bước 1: Chốt policy mới

Ghi tài liệu rõ thuật toán Unicode normalization, case policy, tập ký tự, giới hạn byte, uniqueness scope theo tenant, phiên bản policy và hành vi nếu đầu vào không hợp lệ.

### Bước 2: Đo phân bố dữ liệu hiện tại

Liệt kê bản ghi theo schema/field type, phát hiện chuỗi không hợp lệ, dữ liệu binary bị lưu nhầm text, trường thiếu và các biến thể Unicode. Không tự ý sửa ngay vì có thể làm thay đổi định danh người dùng.

### Bước 3: Tính key mới và phát hiện collision

Với mỗi record, tạo key mới theo policy v2 và phân nhóm những record có cùng canonical key. Những nhóm collision phải được giải quyết theo quy trình nghiệp vụ/ownership, không cho một bản ghi ghi đè bản còn lại.

### Bước 4: Chuẩn bị index và đường ghi mới

Tạo trường `usernameKeyV2` hoặc bảng/index mới, đảm bảo mọi writer mới dùng cùng policy. Nếu cần chuyển đổi trong lúc có traffic, phải có cách ngăn bản ghi mới tạo collision với bản cũ chưa được backfill.

### Bước 5: Backfill idempotent

Tính lại key theo batch, giữ tiến độ và xử lý retry. Không ghi đè display name hoặc dữ liệu gốc nếu nhiệm vụ chỉ cần một normalized key mới.

### Bước 6: Đối soát và cutover

So sánh số record, số collision đã giải quyết, tỷ lệ tra cứu, các trường hợp dấu Unicode và khác biệt của query/index. Chuyển đường đọc/ghi khi dữ liệu mới nhất và cũ được xử lý đúng.

### Bước 7: Dọn trường và index cũ

Chỉ loại bỏ sau khi các dịch vụ không còn dùng policy cũ, có phương án rollback thích hợp và retention cho phép. Ghi rõ version của thuật toán canonicalization trong code và tài liệu vận hành.

~~~mermaid
flowchart TD
    OLD["Stored values v1"] --> CALC["Compute canonical values v2"]
    CALC --> COLL{"Collision?"}
    COLL -->|Có| RESOLVE["Giải quyết theo quy tắc nghiệp vụ"]
    COLL -->|Không| INDEX["Populate v2 index"]
    RESOLVE --> INDEX
    INDEX --> CHECK["Reconcile + shadow reads"]
    CHECK --> CUT["Cut over readers and writers"]
~~~

## 15. Quan sát và vận hành

Vấn đề biểu diễn và chuẩn hóa thường âm thầm tích lũy nhiều năm trước khi gây lỗi. Nên theo dõi:

| Chỉ số hoặc cảnh báo | Mục tiêu |
|---|---|
| Tỷ lệ lỗi decode UTF-8 | Phát hiện nguồn gửi bytes không hợp lệ |
| Số record sai kiểu so với contract | Phát hiện schema drift |
| Kích thước string theo byte p95/p99/max | Tránh vượt giới hạn khóa, item, document |
| Số canonical-key collisions | Đánh giá thay đổi policy và dữ liệu trùng |
| Tỷ lệ lỗi unique/conditional write | Phát hiện concurrency và đầu vào va chạm |
| Lookup miss theo biến thể normalization | Phát hiện ứng dụng dùng khác policy |
| Kích thước Base64/inline binary | Phát hiện document phình to và băng thông tăng |
| Upload PENDING/FAILED quá hạn | Dọn object mồ côi và metadata không hoàn tất |
| Lỗi checksum/content-type validation | Phát hiện file hỏng hoặc sai định dạng |
| Search index lag và mismatch | Kiểm soát sự khác biệt giữa bản gốc và projection |

Với multi-region hoặc nhiều ngôn ngữ lập trình, cần bảo đảm các dịch vụ sử dụng thuật toán canonicalization tương thích. Một dịch vụ Java và một dịch vụ Node.js có thể khác về version thư viện hoặc cách xử lý Unicode/collation.

### 15.1. Không ghi log dữ liệu nhạy cảm chỉ để debug

Khi điều tra một lỗi “username nhìn giống nhưng không tìm thấy”, có thể cần in mã code point, byte length hoặc một định danh truy vết. Nhưng không nên log password, token, ảnh riêng tư hay toàn bộ email/phone ở mức debug không kiểm soát.

Cần tuân thủ phân quyền, masking và retention log. Dữ liệu để chẩn đoán encoding cũng có thể chứa thông tin cá nhân.

## 16. Những sai lầm phổ biến

### “String.length() là số ký tự hiển thị”

Trong Java, đó là số đơn vị UTF-16. Emoji có thể cần surrogate pair; một grapheme có thể gồm nhiều code point. Nếu giới hạn theo byte thì phải đo byte sau encoding.

### “Hai chuỗi nhìn giống nhau thì khóa database chắc chắn giống nhau”

Unicode cho phép nhiều dãy code point tương đương về mặt canonical. Nếu key dùng byte/string equality, truy vấn có thể không khớp khi không có normalization nhất quán.

### “NFC cũng là lowercase và bỏ dấu”

NFC xử lý canonical representation, không phải thuật toán xóa dấu hay so sánh chữ hoa/thường. Cần thiết kế các bước riêng theo mục đích.

### “NFKC luôn tốt hơn NFC”

NFKC thực hiện thêm compatibility transformations, có thể làm mất phân biệt mà nghiệp vụ cần giữ. Chỉ dùng khi policy rõ ràng cho phép.

### “Mọi trường string đều nên trim và lowercase”

Mật khẩu, nội dung pháp lý, định danh có ý nghĩa case-sensitive và dữ liệu ký số có thể bị thay đổi không hợp lệ. Chuẩn hóa phải theo field.

### “Chỉ cần normalize ở lúc ghi”

Nếu query input không áp dụng cùng policy, exact lookup vẫn có thể thất bại. Mọi writer, reader, import và consumer cần dùng cùng contract.

### “Đã normalize thì không cần unique constraint”

Hai request có thể đồng thời kiểm tra cùng canonical key rồi cùng ghi. Uniqueness cần bảo đảm tại storage/concurrency boundary.

### “Base64 làm file nhỏ hơn và an toàn hơn”

Base64 tăng dung lượng khoảng một phần ba và có thể giải mã lại dễ dàng. Nó không phải nén hoặc encryption.

### “Bytes bất kỳ chuyển qua String đều round-trip được”

Dữ liệu binary không nhất thiết là UTF-8 hợp lệ. Đoán encoding có thể mất thông tin, đặc biệt với byte như `0xFF`.

### “Có kiểu binary thì nên nhúng toàn bộ video vào document”

Giới hạn item/document, replication, query cost và backup có thể khiến cách này không phù hợp. File lớn thường nên cân nhắc object storage với metadata tham chiếu.

### “Content-Type do client gửi đã chứng minh file là ảnh”

MIME type và đuôi file có thể bị giả mạo. Cần validation định dạng, kích thước, quyền, checksum và chính sách an toàn.

### “Đổi hàm normalize không ảnh hưởng schema”

Nếu normalized value dùng làm khóa, unique index hoặc hash, đổi policy có thể làm collision, thay đường truy cập và ảnh hưởng các bản ghi cũ. Cần migration có version và đối soát.

## 17. Quy trình thiết kế kiểu dữ liệu và chuẩn hóa

Trước khi thêm một trường string hoặc binary vào NoSQL:

1. **Xác định ý nghĩa:** đây là nội dung hiển thị, định danh, khóa tìm kiếm, giá trị tiền, thời gian hay bytes?
2. **Chọn kiểu và encoding:** native string/binary/decimal/timestamp hay biểu diễn qua API; thống nhất UTF-8 khi trao đổi text.
3. **Định nghĩa normalization:** NFC/NFKC, case policy, whitespace, accent folding chỉ khi thực sự cần.
4. **Phân biệt original và canonical:** nếu cần bảo toàn nội dung, lưu bản gốc và trường dẫn xuất riêng.
5. **Chọn phép so sánh:** exact equality, collation hay full-text search; xác định locale và version.
6. **Thiết kế key/index:** canonical value phải được tạo giống nhau ở mọi đường ghi/đọc; uniqueness phải nguyên tử.
7. **Đặt giới hạn:** byte length, code point/grapheme nếu liên quan UX, kích thước binary, document và request.
8. **Chuẩn hóa các giá trị khác:** tiền, số nguyên lớn, thời gian, missing/null, mã số có số 0 đầu.
9. **Thiết kế lưu bytes:** inline binary hay object storage, metadata, checksum, quyền và retention.
10. **Lập kế hoạch migration:** schema/policy version, backfill, collision, cutover và rollback.
11. **Kiểm thử quốc tế hóa và edge cases:** tiếng Việt có dấu, chuỗi decomposed, emoji, mixed scripts, empty/missing, binary không hợp lệ.
12. **Giám sát:** lỗi encoding, record sai kiểu, kích thước, collision, lookup miss và upload orphan.

## 18. Bài tập thực hành

### Bài 1 — Unicode và độ dài

Cho ba giá trị:

~~~text
"A"
"é" (U+00E9)
"e" + U+0301
~~~

Hãy:

1. So sánh số code point và số byte UTF-8.
2. Giải thích vì sao hai dạng `é` có thể không bằng nhau trong so sánh byte.
3. Viết hàm Java chuẩn hóa NFC trước khi so sánh.
4. Giải thích vì sao NFC không giải quyết mọi confusable.

### Bài 2 — Username không phân biệt hoa/thường

Hệ thống có hai tài khoản cũ `"AN123"` và `"an123"`; phiên bản mới yêu cầu username không phân biệt chữ hoa/thường.

Hãy thiết kế canonical key, index uniqueness, cách phát hiện collision khi migration và quy trình xử lý người dùng bị ảnh hưởng.

### Bài 3 — Tìm kiếm tiếng Việt

Màn hình địa điểm cần tìm `"Hà Nội"` khi người dùng nhập `"Ha Noi"`, nhưng phải giữ bản hiển thị và phân biệt các định danh kỹ thuật.

Hãy thiết kế trường bản gốc, pipeline search analyzer và tiêu chí xác định khi nào được accent fold. Vì sao không nên dùng search key làm ID duy nhất?

### Bài 4 — Kích thước file Base64

Một file ảnh có kích thước 3.000.000 byte. API đề xuất lưu trực tiếp ảnh dưới dạng Base64 trong document JSON.

Hãy ước lượng số ký tự Base64, phân tích overhead, giới hạn document và đề xuất mô hình object storage + metadata phù hợp.

### Bài 5 — Binary round-trip

Cho byte array gồm `0x00`, `0xFF`, `0x10`. Viết Java chuyển sang Base64 rồi trở lại bytes và kiểm tra bằng `Arrays.equals`. Giải thích vì sao không nên tạo một String UTF-8 trực tiếp từ ba byte đó.

### Bài 6 — Schema drift

Collection chứa các bản ghi `amount` kiểu string và kiểu number, `createdAt` lúc có `Z`, lúc có offset, và `postalCode` đôi khi bị chuyển thành number.

Hãy thiết kế một data contract mới, chỉ ra dữ liệu không thể tự khôi phục nếu đã mất số 0 đầu, và đề xuất kế hoạch backfill an toàn.

### Bài 7 — Unicode trong khóa phân vùng

Một dịch vụ dùng NFC trước khi hash username, dịch vụ khác dùng raw UTF-8. Người dùng có tên gồm ký tự có dấu tổ hợp.

Hãy phân tích tại sao record có thể bị ghi và đọc ở các khóa khác nhau, cách phát hiện và migration, và vì sao đổi policy cần triển khai đồng bộ giữa các service.

### Bài 8 — Upload không có transaction chung

API upload file lên object storage rồi ghi metadata vào NoSQL. Upload thành công nhưng ghi metadata thất bại.

Hãy đề xuất trạng thái PENDING/READY, idempotent retry, checksum, kiểm tra quyền và job dọn object mồ côi. Nếu xóa tài khoản, dữ liệu nào phải được kiểm kê để hoàn tất retention?

### Bài 9 — Collation và pagination

Một API sắp tên người dùng theo locale tiếng Việt và phân trang 20 kết quả bằng cursor. Một lần nâng cấp thư viện collation thay đổi thứ tự một số tên.

Hãy giải thích rủi ro đối với cursor cũ, index và kết quả hiển thị. Đề xuất cách version sort policy và dùng tie-breaker ổn định.

---

**Kết luận:** Chuỗi, Unicode và dữ liệu nhị phân không chỉ là lựa chọn kiểu lưu trữ. Chúng quyết định **giá trị có bằng nhau không, khóa có tra cứu đúng không, index có hoạt động nhất quán không và dữ liệu có còn nguyên vẹn sau khi trao đổi giữa các hệ không**. Thiết kế NoSQL vững chắc phải phân biệt byte, code point và grapheme; chọn normalization theo từng trường; bảo toàn dữ liệu gốc khi cần; giữ cùng canonicalization policy ở mọi đường ghi/đọc; và không nhầm Base64 với binary storage hay bảo mật. Khi những quy tắc này được xem như một phần của schema và được version hóa cùng migration, hệ thống sẽ tránh được nhiều lỗi dữ liệu âm thầm nhưng tốn kém.
