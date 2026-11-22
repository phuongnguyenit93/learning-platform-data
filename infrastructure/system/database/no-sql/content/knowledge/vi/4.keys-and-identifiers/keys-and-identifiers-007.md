# Chuẩn hóa chuỗi khóa, Unicode, chữ hoa/thường và ký tự phân tách

## 1. Vì sao chuẩn hóa khóa là một yêu cầu về tính đúng đắn?

Trong cơ sở dữ liệu NoSQL, khóa thường là đường truy cập chính đến dữ liệu: ứng dụng ghi một bản ghi bằng khóa rồi tìm lại đúng khóa đó. Các hệ key–value có thể lấy khóa làm định danh trực tiếp; document database dùng định danh của document; hệ phân tán có thể dùng partition key và sort/clustering key để định tuyến và tổ chức dữ liệu.

Một sai khác rất nhỏ trong **chuỗi khóa** có thể khiến thao tác đọc không tìm thấy dữ liệu, tạo thêm bản ghi trùng về mặt nghiệp vụ, hoặc truy cập nhầm dữ liệu:

~~~text
user:alice
user:Alice
user:ALICE
~~~

Ba chuỗi trên là ba giá trị khác nhau ở mức ký tự. Chúng có phải cùng một định danh người dùng hay không phụ thuộc **quy tắc nghiệp vụ**, không phụ thuộc sở thích người lập trình. Nếu tài khoản được định danh không phân biệt hoa/thường, ứng dụng phải tạo một biểu diễn chuẩn nhất quán. Nếu mã sản phẩm phân biệt hoa/thường, tự chuyển về chữ thường có thể gộp hai mã khác nhau.

Vấn đề còn tinh vi hơn với Unicode: hai chuỗi hiển thị giống hệt nhau có thể chứa các chuỗi mã Unicode khác nhau, trong khi hai ký tự trông giống nhau lại có ý nghĩa và mã Unicode khác nhau.

Ví dụ:

~~~text
Café     = "Caf" + U+00E9 (é dạng ký tự ghép sẵn)
Café     = "Cafe" + U+0301 (dấu sắc kết hợp)
~~~

Một người nhìn thường thấy cùng chữ “Café”. Tuy nhiên, biểu diễn thứ nhất có một code point cho **é**, còn biểu diễn thứ hai dùng **e** và một dấu kết hợp. Nếu ứng dụng ghi bằng một dạng rồi tìm bằng dạng còn lại mà không có quy tắc chuẩn hóa nhất quán, việc so khớp khóa có thể thất bại.

**Mục tiêu của chuẩn hóa khóa** là xác định một phép biến đổi có chủ đích và ổn định từ giá trị đầu vào sang định danh được lưu/truy vấn. Mục tiêu không phải biến mọi chuỗi nhìn gần giống nhau thành cùng một khóa.

## 2. Tách bốn lớp dễ bị trộn lẫn

Trước khi thiết kế, cần phân biệt:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Giá trị gốc | Người dùng hoặc hệ thống gửi gì? | **Alice**, **Café**, mã đơn **Ab-09** |
| Giá trị chuẩn theo nghiệp vụ | Những biến thể nào được xem là cùng định danh? | **Alice** và **alice** có cùng tài khoản? |
| Thành phần đã mã hóa | Biểu diễn thế nào để ghép khóa không nhập nhằng? | Mã hóa riêng tenantId, userId, orderId |
| Khóa lưu trữ cuối cùng | Hệ quản trị dùng gì để đọc, định tuyến, sắp xếp? | **PK**, **SK**, document **_id**, key Redis |

Một sơ đồ chuyển đổi điển hình:

~~~mermaid
flowchart LR
    A["Giá trị đầu vào"] --> B["Kiểm tra quy tắc nghiệp vụ"]
    B --> C["Chuẩn hóa từng thành phần"]
    C --> D["Mã hóa từng thành phần"]
    D --> E["Ghép khóa có phiên bản"]
    E --> F["Ghi/đọc bằng đúng khóa"]
~~~

Tại mỗi bước, ứng dụng phải biết trường nào được phép biến đổi. **Dữ liệu hiển thị** nên được lưu riêng khi cần giữ cách người dùng nhập ban đầu. Ví dụ, khóa tìm kiếm tài khoản có thể là **alice**, còn tên hiển thị là **Alice**.

Một mô hình dữ liệu gợi ý:

~~~json
{
  "userId": "u_8f12c9",
  "usernameOriginal": "Alice",
  "usernameCanonical": "alice",
  "displayName": "Alice Nguyễn"
}
~~~

**userId** là ID nội bộ ổn định; **usernameCanonical** phục vụ quy tắc tìm và chống trùng tên. Khi người dùng đổi tên hiển thị, không nhất thiết phải đổi toàn bộ khóa lưu trữ.

## 3. Unicode: ký tự, code point và byte không phải một

### 3.1. Ba cách đo độ dài khác nhau

Một chuỗi Unicode có thể được quan sát qua:

- **Code point:** giá trị Unicode như U+0065 (**e**) hoặc U+1F600 (emoji).
- **Code unit:** đơn vị của bộ mã hóa trong bộ nhớ. Java **String** dùng UTF-16, nên một code point ngoài Basic Multilingual Plane có thể chiếm hai code unit.
- **Byte:** dữ liệu sau khi mã hóa, thường là UTF-8 trong giao tiếp và khóa lưu trữ. Một code point có thể cần một đến bốn byte UTF-8.

Ví dụ với Java:

~~~java
String s = "😀";

System.out.println(s.length());                         // 2 code unit UTF-16
System.out.println(s.codePointCount(0, s.length()));    // 1 code point
System.out.println(s.getBytes(
    java.nio.charset.StandardCharsets.UTF_8
).length);                                               // 4 byte UTF-8
~~~

Vì vậy, nếu NoSQL quy định giới hạn kích thước khóa bằng **byte**, không được kiểm tra bằng **String.length()** rồi cho rằng đã đủ. Cần mã hóa đúng charset và đo số byte thực tế, kể cả ký tự phân tách, tên miền khóa và các tiền tố.

### 3.2. NFC và NFD: hai dạng chính tắc

Unicode có các hình thức chuẩn hóa:

| Dạng | Ý tưởng | Minh họa |
| --- | --- | --- |
| NFC | Canonical composition: ghép những chuỗi tương đương chính tắc khi có thể | **e + U+0301** thành **é** |
| NFD | Canonical decomposition: tách thành chuỗi thành phần chính tắc | **é** thành **e + U+0301** |
| NFKC | Compatibility composition: còn gộp một số biến thể tương thích về dạng chung | Chữ Latin toàn chiều rộng **Ａ** thành **A** |
| NFKD | Compatibility decomposition | Phân tách thêm các dạng tương thích |

**NFC** thường là một lựa chọn phù hợp cho khóa văn bản khi muốn coi các cách biểu diễn Unicode tương đương chính tắc là một. **NFD** cũng hợp lệ nếu toàn hệ thống thống nhất, nhưng có thể làm chuỗi dài hơn theo code point. Hai dạng NFC/NFD không thể tự ý trộn trong các đường ghi/đọc.

**NFKC/NFKD** mạnh hơn: chúng có thể làm mất sự phân biệt giữa các ký tự mà người dùng hoặc nghiệp vụ coi là khác nhau. Ví dụ, NFKC có thể quy đổi chữ số/chữ cái toàn chiều rộng và một số ký tự trình bày sang dạng thông thường. Không dùng NFKC mặc định cho mọi mã nghiệp vụ, tên người, mã hàng hoặc chuỗi mật khẩu.

Ví dụ Java 21:

~~~java
import java.text.Normalizer;

String composed = "Caf\u00e9";
String decomposed = "Cafe\u0301";

System.out.println(composed.equals(decomposed)); // false

String key1 = Normalizer.normalize(composed, Normalizer.Form.NFC);
String key2 = Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(key1.equals(key2));          // true
~~~

Chuẩn hóa Unicode là phép biến đổi có quy tắc và **không đồng nghĩa với bỏ dấu tiếng Việt**. Ví dụ **ma**, **má**, **mà** và **mã** là những chuỗi có nghĩa khác nhau; chuyển hết thành **ma** có thể phá hỏng tính duy nhất của định danh.

### 3.3. Chuẩn hóa Unicode không đồng nghĩa với chống giả mạo tên

Hai ký tự có thể trông gần giống nhưng vẫn không tương đương chính tắc. Chẳng hạn:

~~~text
a        (Latin: U+0061)
а        (Cyrillic: U+0430)
~~~

Đây là hai ký tự khác nhau. NFC không gộp chúng. Tương tự, ký tự không hiển thị, dấu điều khiển hướng chữ và các chữ cái từ hệ chữ viết khác có thể tạo tên khó phân biệt bằng mắt.

Nếu định danh được dùng để đăng nhập, phân quyền hoặc điều hướng tài nguyên, cần có **chính sách ký tự được phép**, kiểm tra chuỗi gây nhầm lẫn (confusable) hoặc cảnh báo phù hợp. Không thể dựa riêng vào NFC hay lowercase để xử lý mọi dạng giả mạo bằng Unicode.

Đối với ID nội bộ không cần người đọc, dùng ID sinh tự động trong bảng ký tự hạn chế (UUID/ULID hoặc định danh ngẫu nhiên theo chính sách của hệ thống) thường đơn giản hơn dùng tên tự nhiên làm primary key.

## 4. Chữ hoa, chữ thường và quy tắc so khớp

### 4.1. Case-sensitive hay case-insensitive là lựa chọn nghiệp vụ

Cần xác định quy tắc **cho từng trường**:

| Loại trường | Chính sách khả thi | Lý do |
| --- | --- | --- |
| ID nội bộ do hệ thống sinh | Dạng cố định, kiểm tra cú pháp | Tránh phụ thuộc cách nhập của người dùng |
| Mã tenant do hệ thống cấp | Một canonical form, thường dùng ASCII | Làm khóa định tuyến ổn định |
| Username nếu quy định không phân biệt hoa/thường | Chuẩn hóa Unicode + case policy | Chống tạo hai tài khoản theo biến thể chữ hoa |
| Mã sản phẩm do bên ngoài cấp | Giữ nguyên hoặc theo hợp đồng nhà cung cấp | **AB-01** có thể khác **ab-01** |
| Tên hiển thị của người dùng | Giữ bản gốc | Trình bày đúng ý người dùng |
| Email | Chính sách riêng theo sản phẩm | Phần local và domain không nhất thiết có cùng quy tắc; tránh tự ý chuẩn hóa toàn bộ |
| Secret, token, mật khẩu | Giữ đúng quy tắc xác thực tương ứng | Thường không được tự lowercase hoặc chuẩn hóa tùy tiện |

**Không nên gọi lowerCase() trên mọi chuỗi trước khi ghi NoSQL.** Làm vậy có thể thay đổi ý nghĩa hoặc phá tính duy nhất của dữ liệu.

### 4.2. Vấn đề locale: chữ I trong tiếng Thổ Nhĩ Kỳ

Chữ hoa/thường không phải lúc nào cũng là ánh xạ ASCII đơn giản:

~~~text
I  (Latin capital I)
i  (Latin small i)
İ  (Latin capital I with dot)
ı  (Latin small dotless i)
~~~

Kết quả chuyển chữ thường phụ thuộc quy tắc ngôn ngữ khi dùng locale-specific casing. Trong Java, nên **quy định rõ locale** hoặc dùng chuẩn Unicode case folding khi nghiệp vụ cần so khớp Unicode không phân biệt hoa/thường:

~~~java
import java.util.Locale;

String raw = "IDENTIFIER";

String stable = raw.toLowerCase(Locale.ROOT);
System.out.println(stable); // identifier
~~~

**Locale.ROOT** tránh phụ thuộc locale mặc định của máy chạy. Nhưng Java **toLowerCase(Locale.ROOT)** không phải thuật toán **Unicode full case folding**. Một số cặp chuỗi có thể được Unicode case-fold coi là tương đương dù phép lowercase thông thường không cho cùng kết quả.

Ví dụ tên **Straße** và **STRASSE**: muốn hai tên này được xem là một cần chính sách phù hợp, thường dựa vào Unicode case folding hơn là chỉ lowercase. Khi yêu cầu case-insensitive đầy đủ, có thể dùng thư viện Unicode chuyên dụng có phiên bản và hợp đồng rõ ràng (ví dụ ICU4J), hoặc sử dụng collation của hệ quản trị với kiểm chứng về tính duy nhất. Không nên giả định mọi thư viện và mọi database dùng cùng thuật toán hay cùng phiên bản Unicode.

### 4.3. Thứ tự thao tác phải nhất quán

Một pipeline minh họa cho trường **username được quy định không phân biệt hoa/thường theo quy tắc lowercase đơn giản**:

~~~text
nhận username
    -> kiểm tra giá trị hợp lệ
    -> Unicode NFC
    -> lowercase theo Locale.ROOT
    -> Unicode NFC lần nữa
    -> kiểm tra giới hạn ký tự/byte sau chuẩn hóa
    -> dùng làm usernameCanonical
~~~

Chuẩn hóa NFC lần nữa sau chuyển chữ thường giúp giữ canonical form trong trường hợp phép biến đổi tạo lại chuỗi chứa ký tự kết hợp.

Không có một thứ tự chung thích hợp cho tất cả hệ thống. Nếu ứng dụng đã cam kết dùng Unicode full case folding hoặc collation do database định nghĩa, cả đường tạo tài khoản, tìm kiếm, cập nhật và chống trùng phải dùng **đúng hợp đồng đó**.

## 5. Khoảng trắng và ký tự không hiển thị

Các chuỗi dưới đây trông tương tự nhưng có thể không giống nhau:

~~~text
"alice"
" alice"
"alice "
"alice  "       (hai space)
"alice<TAB>"
"alice<NBSP>"    (non-breaking space U+00A0)
~~~

Quy tắc nghiệp vụ cần nêu rõ:

- Có cho phép khoảng trắng đầu/cuối không? Nếu không, **từ chối** hay **tự cắt bỏ**?
- Có phân biệt một space và hai space không?
- Có cho phép tab, xuống dòng, non-breaking space, zero-width space hoặc ký tự điều khiển hướng chữ không?
- Có cho phép username từ nhiều hệ chữ viết không?

Trong Java, **trim()** và **strip()** không hoàn toàn giống nhau; cả hai cũng không phải “xóa mọi ký tự mà người dùng không nhìn thấy”. Không nên dùng một hàm cắt khoảng trắng bất kỳ rồi coi đó là quy tắc định danh chính thức.

Ví dụ, nếu sản phẩm quyết định cấm space ở đầu/cuối username thì trả lỗi rõ ràng sẽ dễ kiểm soát hơn âm thầm sửa thành một tài khoản khác. Ngược lại, với trường tìm kiếm tự do, việc trim đầu/cuối có thể là hành vi mong muốn. Hai trường có mục đích khác nhau nên không dùng chung một pipeline mù quáng.

Với khóa dùng trong log hoặc công cụ dòng lệnh, ký tự xuống dòng và điều khiển có thể gây đọc nhầm hoặc làm giả nội dung log. Cần kiểm soát chúng trước khi ghi khóa, đồng thời không ghi bí mật hoặc token thô ra log.

## 6. Ký tự phân tách: dễ đọc nhưng có thể gây va chạm

Ứng dụng thường ghép khóa bằng dấu hai chấm, gạch đứng, gạch chéo hoặc dấu thăng:

~~~text
tenant:T01:user:alice:profile
tenant|T01|user|alice|profile
TENANT#T01#USER#alice
~~~

Kiểu khóa này có ưu điểm dễ xem log và nhóm theo miền nghiệp vụ. Nhưng khi thành phần chứa dấu phân tách, cách nối thông thường có thể mất tính một-một.

### 6.1. Va chạm do nối trực tiếp

~~~text
(tenant="AB", user="C") -> "ABC"
(tenant="A",  user="BC") -> "ABC"
~~~

Hai bộ thành phần tạo cùng một khóa: đây là **lỗi va chạm do mã hóa**, không phải va chạm hàm băm.

Thêm một dấu phân tách cố định vẫn chưa đủ nếu đầu vào có thể chứa chính dấu đó:

~~~text
(tenant="A|B", user="C") -> "A|B|C"
(tenant="A", user="B|C") -> "A|B|C"
~~~

Sau khi lưu, không còn cách tách khóa thành hai trường như ban đầu bằng một phép split đơn giản.

### 6.2. Những cách mã hóa thành phần an toàn hơn

| Cách | Minh họa | Điểm cần chú ý |
| --- | --- | --- |
| Cấm delimiter trong thành phần | ID chỉ gồm **[a-z0-9_-]** | Hợp với ID sinh nội bộ; giới hạn dữ liệu người dùng |
| Escape delimiter | **A\|B** thành dạng escape theo quy tắc | Phải escape cả ký tự escape; parser cần giải mã đúng một lần |
| Length-prefix | **3:A\|B1:C** | Độ dài phải quy định theo byte hay ký tự; parser phải nhất quán |
| Base64url từng thành phần | UTF-8 → base64url không padding | Không chứa ký tự **\|**; thứ tự từ điển của bản gốc không được bảo toàn |
| Tuple codec có hợp đồng rõ | Encoder của nền tảng/SDK | Phải tuân phiên bản, giới hạn và quy tắc so sánh của codec |
| Các trường khóa tách biệt | **tenantId**, **userId** là trường riêng | Thường tốt hơn khi NoSQL trực tiếp hỗ trợ khóa nhiều thành phần |

Ví dụ, nếu định dạng gồm **độ dài byte UTF-8 + dấu hai chấm + nội dung**, khóa hai trường có thể là:

~~~text
3:A|B1:C
~~~

Vì **A|B** có 3 byte ASCII, parser đọc đúng 3 byte rồi tiếp tục đọc thành phần sau. Với tiếng Việt hoặc emoji, độ dài phải tính bằng **UTF-8 bytes**, không thể lấy Java **String.length()** rồi giả định bằng byte. Nên dùng bộ mã hóa/giải mã có kiểm tra độ dài và biên rõ ràng.

### 6.3. Escape phải có quy tắc giải mã một lần

Một quy tắc tự chế như thay **|** thành **\|** rất dễ sai khi dữ liệu có sẵn dấu **\\** hoặc chuỗi escape. Ví dụ, nếu escape delimiter nhưng không escape backslash, parser khó phân biệt dấu escape thực và ký tự gốc.

Nếu dùng percent encoding kiểu URL, phải xác định rõ bảng ký tự được phép, bộ mã UTF-8, dạng chữ hoa/chữ thường của mã hex và thứ tự encode/decode. Không **decode hai lần**: chuỗi đầu vào chứa dấu phần trăm có thể thay đổi ý nghĩa ở lần giải mã tiếp theo. Nếu dùng slash trong đường dẫn tài nguyên, cần phân biệt khóa dữ liệu với **URL path**: quy tắc escape của URL và API gateway có thể khác quy tắc lưu khóa.

Một phương án dễ xác định hơn cho định danh khóa chuỗi là **mã hóa từng thành phần UTF-8 bằng base64url không padding**, rồi mới nối bằng dấu **|**. Vì bảng chữ base64url không chứa **|**, ranh giới thành phần không còn nhập nhằng. Cách này phù hợp cho tra cứu **theo nguyên thành phần**; không phù hợp khi muốn quét prefix theo **một phần chuỗi gốc** hoặc cần sort theo bản gốc.

## 7. Một thiết kế khóa có phiên bản, ranh giới và phạm vi rõ ràng

Giả sử hệ thống cần lưu dữ liệu cài đặt của một username trong từng tenant. Ta muốn:

- Hai tenant khác nhau có thể dùng cùng username.
- Username được coi là không phân biệt chữ hoa/thường theo chính sách đã chọn.
- Ký tự **|**, **:** hay **#** trong tên không thể làm lệch ranh giới khóa.
- Khóa có phiên bản để sau này thay đổi quy tắc chuẩn hóa.
- Không dùng tên hiển thị làm ID nội bộ vĩnh viễn.

Một thiết kế minh họa:

~~~text
Key = v1|tenant|<encoded-tenant>|user|<encoded-canonical-username>|settings

v1       : phiên bản bộ quy tắc và định dạng khóa
tenant   : nhãn phân biệt loại thành phần
user     : nhãn phân biệt loại thực thể
settings : loại tài nguyên
~~~

Giả sử:

~~~text
tenantId       = T01
usernameInput  = A|B
usernameCanon  = a|b
~~~

Sau khi mã hóa UTF-8 thành base64url:

~~~text
T01 -> VDAx
a|b -> YXxi
~~~

Khóa cuối:

~~~text
v1|tenant|VDAx|user|YXxi|settings
~~~

Không có tình huống username chứa ký tự **|** làm tăng số thành phần được tách bởi dấu phân cách. Một username khác như **A**, **B** không thể tạo cùng chuỗi khóa với username **A|B** chỉ bằng cách sắp xếp delimiter.

Lưu ý: các literal **v1**, **tenant**, **user**, **settings** là những nhãn cố định do ứng dụng sinh, không phải dữ liệu do người dùng nhập. Nếu chúng thay đổi, phải cập nhật cả nơi ghi và nơi truy vấn.

## 8. Ví dụ Java 21: chuẩn hóa và mã hóa khóa theo hợp đồng

Đoạn mã sau minh họa một **chính sách cụ thể**:

1. Tenant ID chỉ nhận chữ/số ASCII cùng dấu gạch dưới, gạch ngang, tối đa 48 ký tự; được đưa về chữ thường.
2. Username không được rỗng, không tự trim và không chứa control character hoặc surrogate không hợp lệ. Sản phẩm yêu cầu username không phân biệt hoa/thường bằng **NFC + lowercase(Locale.ROOT)**; đây là lowercase đơn giản, không phải Unicode full case folding.
3. Mỗi thành phần sau chuẩn hóa được mã hóa UTF-8 rồi base64url độc lập.
4. Khóa cuối cùng có phiên bản cố định, các đoạn phân tách rõ ràng.
5. Kích thước byte của khóa hoàn chỉnh được kiểm tra theo giới hạn giả định của ứng dụng; khi triển khai phải dùng giới hạn thực của database.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Base64;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

public final class UserSettingsKeys {
    private static final Pattern TENANT_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,48}");

    // Chỉ là giới hạn ví dụ của ứng dụng, không phải giới hạn chung của NoSQL.
    private static final int MAX_KEY_BYTES = 512;

    private UserSettingsKeys() {}

    public static String canonicalTenant(String raw) {
        Objects.requireNonNull(raw, "tenantId");
        if (!TENANT_ID.matcher(raw).matches()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        return raw.toLowerCase(Locale.ROOT);
    }

    public static String canonicalUsername(String raw) {
        Objects.requireNonNull(raw, "username");
        if (raw.isEmpty()) {
            throw new IllegalArgumentException("Empty username");
        }
        // Không trim ngầm: khoảng trắng là dữ liệu hoặc bị chặn
        // bởi một quy tắc kiểm tra riêng của sản phẩm.
        String normalized = Normalizer.normalize(
                raw, Normalizer.Form.NFC);

        String lower = normalized.toLowerCase(Locale.ROOT);
        String canonical = Normalizer.normalize(
                lower, Normalizer.Form.NFC);

        if (canonical.codePoints().anyMatch(cp ->
                Character.isISOControl(cp)
                || (cp >= 0xD800 && cp <= 0xDFFF))) {
            throw new IllegalArgumentException(
                    "Control character or invalid surrogate");
        }
        if (canonical.isEmpty()) {
            throw new IllegalArgumentException("Empty username");
        }
        return canonical;
    }

    private static String segment(String canonical) {
        byte[] bytes = canonical.getBytes(StandardCharsets.UTF_8);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static String settingsKey(String tenantId, String username) {
        String key = "v1|tenant|"
                + segment(canonicalTenant(tenantId))
                + "|user|"
                + segment(canonicalUsername(username))
                + "|settings";

        int bytes = key.getBytes(StandardCharsets.UTF_8).length;
        if (bytes > MAX_KEY_BYTES) {
            throw new IllegalArgumentException("Key too large");
        }
        return key;
    }

    public static void main(String[] args) {
        String a = settingsKey("T01", "Caf\u00e9");
        String b = settingsKey("t01", "Cafe\u0301");
        System.out.println(a.equals(b));  // true

        String c = settingsKey("T01", "A|B");
        String d = settingsKey("T01", "A");
        System.out.println(c.equals(d));  // false
    }
}
~~~

Đây là ví dụ **định dạng khóa và chính sách chuẩn hóa**, chưa phải thành phần quản lý tài khoản hoàn chỉnh. Trước khi dùng trong sản phẩm thực, phải bổ sung giới hạn độ dài username, chính sách khoảng trắng, tập ký tự chấp nhận, chống giả mạo tên khi phù hợp, xử lý trùng tên bằng thao tác ghi có điều kiện, và kiểm tra tương thích với cơ sở dữ liệu cụ thể.

Chú ý: với code Java trong ví dụ, hai tên Unicode khác nhau sau **full case folding** có thể vẫn khác nhau sau lowercase đơn giản. Nếu yêu cầu so khớp Unicode không phân biệt hoa/thường theo chuẩn khác, thay hàm canonical bằng một thư viện/thuật toán có **phiên bản được kiểm soát**; đồng thời lập kế hoạch di chuyển các khóa đã tạo.

## 9. Tính lặp lại, idempotency và tính duy nhất

Một bộ chuẩn hóa tốt cần có các tính chất có thể phát biểu rõ:

### 9.1. Ổn định khi chạy lại

Với cùng dữ liệu hợp lệ và cùng phiên bản chính sách, khóa sinh ra phải giống nhau ở mọi nơi:

~~~text
canonicalize(canonicalize(x)) = canonicalize(x)

makeKey(T01, Alice) == makeKey(T01, ALICE)
// Chỉ đúng nếu chính sách quy định Alice và ALICE là cùng định danh.
~~~

Tính lặp lại giúp client, API, worker và job chạy lại cùng truy cập một bản ghi. Nhưng điều đó chỉ đạt được khi tất cả thành phần dùng cùng thuật toán, cùng phiên bản Unicode/case policy và cùng cách mã hóa.

### 9.2. Hai giá trị nghiệp vụ khác nhau không được vô tình nhập làm một

Nếu sản phẩm cho phép hai mã hàng **SKU-Ab** và **SKU-ab** tồn tại độc lập, lowercase sẽ phá tính một-một. Nếu sản phẩm cho phép tên **A|B** và **A** là hai giá trị khác nhau, bộ mã hóa thành phần phải giữ được sự khác biệt đó.

**Canonical collision** là trường hợp hai giá trị đầu vào bị chính sách chuẩn hóa đưa về cùng định danh. Trong một hệ case-insensitive, **Alice** và **ALICE** trùng canonical là **có chủ đích**. Ngược lại, hai mã sản phẩm khác nhau bị nhập lại thành một khóa là lỗi nghiệp vụ. Vì vậy phải xác định rõ các lớp tương đương được phép trước khi tạo unique index hoặc ghi dữ liệu.

### 9.3. Chuẩn hóa không thay thế thao tác ghi nguyên tử

Giả sử hai yêu cầu cùng đăng ký username **Alice** và **ALICE** tại một thời điểm. Cả hai tạo cùng **usernameCanonical = alice**; điều đó chưa đủ ngăn việc tạo trùng nếu cả hai cùng thực hiện:

~~~text
READ usernameCanonical=alice -> chưa tồn tại
READ usernameCanonical=alice -> chưa tồn tại
WRITE user A
WRITE user B
~~~

Cần bảo đảm tính duy nhất bằng cơ chế ghi phù hợp của database, ví dụ **conditional put**, **unique index**, hoặc giao dịch có ràng buộc theo key. Không dùng “đọc trước rồi ghi sau” như một bảo đảm độc lập cho nghiệp vụ cạnh tranh.

Trong multi-tenant, uniqueness phải đúng phạm vi: **(tenantId, usernameCanonical)**, thay vì vô tình cấm hai tenant dùng cùng username.

## 10. Chuỗi khóa và hành vi của các hệ NoSQL cụ thể

### 10.1. Redis: key là byte sequence, tránh phụ thuộc tên trông giống nhau

Trong Redis, key có thể chứa nhiều dạng byte. Khi ứng dụng dùng chuỗi UTF-8 làm key, **user:Alice** và **user:alice** là hai tên key khác nhau nếu không có lớp chuẩn hóa ở ứng dụng. Các tên chứa dấu phân tách không được Redis tự bóc thành trường nghiệp vụ.

~~~text
SET user:Alice 1
GET user:alice
~~~

Trong trường hợp không có key **user:alice**, kết quả GET là null dù key **user:Alice** tồn tại. Để triển khai case-insensitive, cả thao tác SET và GET phải chuyển tên qua cùng bộ sinh khóa.

Không nên lạm dụng lệnh duyệt key để khắc phục việc chọn khóa thiếu cấu trúc: **SCAN MATCH user:*** không biến Redis thành chỉ mục có khả năng tìm kiếm tiền tố theo nghiệp vụ hiệu quả và không thay thế một bảng tra cứu có thiết kế. Nếu cần danh sách user của tenant, cân nhắc một set/sorted set hoặc nguồn dữ liệu chính với cơ chế đồng bộ tương ứng.

Trong Redis Cluster, phần đặt trong **{...}** có ý nghĩa đặc biệt với hash slot. Nếu tự tạo hash tag từ đầu vào, cần hiểu cả quy tắc chọn hash tag, cách escape và nguy cơ dồn quá nhiều khóa vào một slot. Không nên đưa ký tự **{** hoặc **}** do người dùng nhập vào mẫu hash tag nếu chưa xác định cách mã hóa an toàn.

### 10.2. DynamoDB: partition key phải khớp toàn bộ giá trị

DynamoDB có primary key là partition key đơn hoặc cặp partition key + sort key. Với thuộc tính kiểu String, chuẩn hóa và encode thường nằm ở ứng dụng. **PK = "TENANT#T01#USER#alice"** khác **PK = "TENANT#T01#USER#Alice"** nếu ứng dụng gửi đúng hai chuỗi đó.

~~~text
PK = TENANT#T01
SK = USER#alice#SETTINGS
~~~

Nếu muốn Query tất cả dữ liệu của tenant, điều kiện **PK = TENANT#T01** là điểm bắt đầu. Nếu cần Query nhóm user, có thể cân nhắc cấu trúc SK có phần tiền tố phù hợp và phép **begins_with** trên sort key. Nhưng tiền tố của **partition key** không cho phép Query các partition key chỉ khớp một đoạn đầu; Query cần giá trị partition key đầy đủ.

Chuỗi số/ngày dùng trong SK cần encoding giữ thứ tự mong muốn, vì sắp xếp chuỗi không giống so sánh số học tự động. Việc base64url tất cả thành phần thuận tiện cho ranh giới khóa nhưng **không bảo toàn thứ tự thời gian hoặc số**; đừng dùng nó cho phần SK cần range scan có ý nghĩa nếu chưa chọn encoding đúng.

Tính nhất quán khi đổi tên người dùng cũng cần thiết kế: nếu dùng username làm một phần PK, đổi username thực chất có thể là tạo item khóa mới và xóa item cũ; việc thay đổi key không giống cập nhật một trường thông thường. ID nội bộ ổn định thường tránh phải di chuyển toàn bộ dữ liệu phụ thuộc tên.

### 10.3. MongoDB: document ID và collation là hai cơ chế khác nhau

Trong MongoDB, một document có **_id** để định danh. Nếu lưu username trong trường riêng, có thể tạo chỉ mục phục vụ truy vấn và uniqueness. So sánh chuỗi theo **collation** có thể thay đổi quy tắc phân biệt hoa/thường hoặc dấu, tùy cấu hình.

Ví dụ minh họa khi sản phẩm muốn uniqueness theo tenant và username có collation riêng:

~~~javascript
db.users.createIndex(
  { tenantId: 1, username: 1 },
  {
    unique: true,
    collation: { locale: "en", strength: 2 }
  }
);
~~~

Đây chỉ là ví dụ về cơ chế **collation**: strength và locale quyết định cách so sánh, có thể không đồng nhất với hàm **NFC + Locale.ROOT lowercase** ở Java. Đặc biệt, nếu một bên dùng cột **usernameCanonical** và một bên dùng collation khác, có thể xuất hiện khác biệt về việc hai tên có bị coi là trùng hay không.

Ứng dụng cần chọn một hợp đồng:

- Hoặc chuẩn hóa ở tầng ứng dụng và tạo unique index trên **(tenantId, usernameCanonical)** theo semantics phù hợp.
- Hoặc dùng collation do database định nghĩa, bảo đảm các truy vấn và index tương ứng cùng sử dụng collation đó.

Không gộp tùy tiện cả hai cơ chế khi chưa hiểu trường hợp khác nhau về chữ hoa, dấu và ký tự đặc biệt. Nếu dùng collation cho index, truy vấn cần dùng collation tương ứng để tận dụng index đúng như kỳ vọng.

### 10.4. Cassandra: text key và byte representation phải thống nhất

Trong Cassandra, primary key có thể chứa trường **text**; ứng dụng phải gửi nhất quán giá trị của các trường thuộc partition/clustering key. Nếu **tenant_id** hoặc **username** là thành phần khóa, việc thay canonical form có thể đổi partition hoặc vị trí sắp xếp.

~~~sql
CREATE TABLE user_preferences (
    tenant_id text,
    username_key text,
    setting_name text,
    setting_value text,
    PRIMARY KEY ((tenant_id, username_key), setting_name)
);
~~~

Ví dụ, ứng dụng ghi với **username_key = "alice"** rồi đọc bằng **"Alice"** có thể không tìm thấy bản ghi. Với username không phân biệt hoa/thường, phải chuẩn hóa đầu vào trước khi ghi/truy vấn. Nếu muốn tìm theo tên hiển thị hoặc tìm gần đúng, cần đường truy cập riêng; primary key không tự cung cấp semantics tìm kiếm ngôn ngữ tự nhiên.

## 11. Khóa ghép và khả năng truy vấn theo tiền tố: tương thích với chuẩn hóa ra sao?

Có hai nghĩa khác nhau của **tiền tố**:

1. **Tiền tố thành phần**: đã biết tenantId và userId hoàn chỉnh, muốn lấy mọi resource của user đó.
2. **Tiền tố nội dung**: biết vài ký tự đầu của tên (ví dụ **al**), muốn tìm mọi tên bắt đầu bằng các ký tự đó.

Hai bài toán cần thiết kế khác nhau.

### 11.1. Tiền tố theo thành phần đầy đủ

Với ordered key store hỗ trợ prefix range, một cấu trúc:

~~~text
v1|tenant|VDAx|user|YWxpY2U|settings
v1|tenant|VDAx|user|YWxpY2U|profile
v1|tenant|VDAx|user|YWxpY2U|sessions
~~~

cho phép tìm nhóm khóa theo prefix **v1|tenant|VDAx|user|YWxpY2U|**, nếu cấu trúc lưu trữ thật sự hỗ trợ quét theo tiền tố. Việc mã hóa riêng từng thành phần bằng base64url và thêm ranh giới **|** tránh trường hợp prefix của username **ali** vô tình khớp username **alice** khi chỉ muốn tìm nguyên user.

Trong hash key–value store không có prefix range, việc các tên key có cùng đoạn ký tự đầu không tạo ra một chỉ mục tự động.

### 11.2. Tiền tố theo ký tự đầu của giá trị

Nếu muốn tìm người dùng có tên bắt đầu bằng **al**, mã hóa base64url từng thành phần không bảo toàn prefix của chuỗi gốc theo nghĩa tìm kiếm. Với một hệ chỉ lưu key đã mã hóa, ứng dụng có thể cần:

- Secondary index trên trường **usernameCanonical**, có khả năng hỗ trợ tiền tố phù hợp.
- Một cấu trúc search index riêng cho autocomplete.
- Bộ dữ liệu/trie/sorted set phù hợp với đặc tính và tải của ứng dụng.

Thậm chí khi index có hỗ trợ prefix string, phải xác định semantics: “bắt đầu bằng” dựa trên **byte**, **code point**, hay **collation**? Có phân biệt dấu, chữ hoa, ký tự kết hợp và biến thể tương đương không? Không được coi tìm kiếm prefix trên tên hiển thị là phép so sánh byte đơn giản nếu trải nghiệm người dùng đòi hỏi tìm kiếm ngôn ngữ tự nhiên.

### 11.3. Chuẩn hóa phải áp dụng trước khi tính prefix và index

Nếu hệ thống tạo index tìm kiếm theo **usernameCanonical** nhưng truy vấn lại dùng chuỗi gốc chưa chuẩn hóa, những tên như **Café** ở NFC/NFD có thể bị lệch. Nên chuẩn hóa nguồn dữ liệu và đầu vào truy vấn bằng **cùng chính sách và phiên bản**, rồi mới dựng điều kiện prefix hoặc query index.

Nếu quy tắc có thao tác không giữ thứ tự, ví dụ base64url, băm hoặc hash partition, không được kỳ vọng phép tìm kiếm khoảng trên giá trị trước mã hóa vẫn hoạt động sau mã hóa.

## 12. Cẩn trọng với hash, sort và tính ổn định giữa các ngôn ngữ

Nếu dùng hàm băm để chọn partition hoặc dựng khóa, phải chuẩn hóa **trước khi băm**:

~~~text
input
  -> validate
  -> canonicalize
  -> encode UTF-8
  -> hash / derive key
~~~

Nếu Java băm dạng NFC, nhưng một service khác băm dạng NFD, hai service có thể đến hai partition khác nhau dù cùng một định danh nghiệp vụ.

**Không dùng String.hashCode() của Java** làm ID bền vững liên hệ thống. Nó có miền giá trị hẹp, có thể va chạm và không phải định dạng băm giao thức chung giữa các nền tảng. Nếu cần định danh băm, chọn thuật toán, encoding, cách biểu diễn đầu ra và chiến lược xử lý va chạm rõ ràng; đối với dữ liệu nhạy cảm cần xem cả nguy cơ đoán ngược từ miền đầu vào nhỏ.

Thứ tự chuỗi cũng cần thống nhất:

~~~text
"2", "10"   -> thứ tự từ điển có thể là "10" trước "2"
"02", "10"  -> dạng cố định chiều rộng giữ thứ tự số trong miền đã chọn
~~~

Dạng timestamp dùng làm sort key nên chuẩn hóa UTC, độ chính xác và định dạng cố định, ví dụ:

~~~text
2026-11-03T09:05:07.000Z
2026-11-14T08:30:00.000Z
2026-12-01T00:00:00.000Z
~~~

Hai timestamp cùng thời điểm nhưng viết với offset khác nhau có thể có thứ tự chuỗi khác mong muốn. Việc chuyển timestamp sang UTC cố định giúp biểu diễn có thứ tự nhất quán khi hệ so sánh chuỗi theo từ điển/byte phù hợp.

## 13. Phiên bản chuẩn hóa và thay đổi khóa theo thời gian

Quy tắc chuẩn hóa là một phần của **hợp đồng lưu trữ**. Sau khi hàng triệu bản ghi đã được ghi, thay đổi từ NFC sang NFKC, từ lowercase đơn giản sang Unicode full case folding, hay thay dấu phân tách đều có thể làm thay đổi key của dữ liệu cũ.

Giả sử hệ đang dùng:

~~~text
v1|tenant|...|user|...|settings
~~~

và quyết định chuyển sang chính sách mới:

~~~text
v2|tenant|...|user|...|settings
~~~

Không nên cập nhật hàm sinh key và giả định dữ liệu cũ tự “đi theo” quy tắc mới. Một quá trình chuyển đổi có thể gồm:

1. **Định nghĩa chính sách v2** cùng quy tắc Unicode, case mapping, encoding và validation rõ ràng.
2. **Kiểm tra khả năng nhập khóa**: hai tên phân biệt ở v1 có thể gộp thành một ở v2. Phải có cách giải quyết va chạm nghiệp vụ, không ghi đè âm thầm.
3. **Backfill** dữ liệu hoặc tạo secondary index v2. Tính toán chi phí đọc/ghi, tốc độ và khả năng chạy lại.
4. **Chuyển đổi có kiểm soát**: trong một giai đoạn có thể dual-read hoặc dual-write theo kế hoạch. Quy định rõ nguồn dữ liệu chính và cách xử lý lỗi một phần.
5. **Đo sai lệch và xác nhận đọc lại**: truy cập dữ liệu bằng v2, so sánh số lượng, phát hiện khóa mồ côi.
6. **Ngừng hỗ trợ v1** khi mọi dữ liệu, client và job phụ thuộc đã di chuyển an toàn.

Nếu một service chạy phiên bản mã Unicode hoặc thư viện khác và tạo ra canonical khác, cần phát hiện trước khi triển khai rộng. Việc ghi **version** trong tên key giúp nhận biết quy ước, nhưng chỉ an toàn nếu toàn bộ hệ thống thực thi theo version đó.

### 13.1. Đổi username có thể là đổi khóa chính

Nếu khóa lưu trữ lấy username làm thành phần:

~~~text
PK = TENANT#T01#USER#alice
~~~

Đổi tên sang **alice.new** có thể là di chuyển dữ liệu sang khóa mới. Tùy NoSQL, không có thao tác “đổi primary key” tại chỗ; ứng dụng có thể phải tạo bản ghi mới, chuyển dữ liệu liên quan và xóa khóa cũ có kiểm soát.

Thiết kế bền vững hơn cho nhiều nghiệp vụ:

~~~text
Primary identity: tenantId + userId (ID ổn định)
Unique lookup:    tenantId + usernameCanonical -> userId
Display value:    usernameOriginal
~~~

Khi username thay đổi, chỉ cần cập nhật bản đồ tra cứu tên và tên hiển thị theo cơ chế bảo đảm uniqueness phù hợp. Tài nguyên khác vẫn liên kết với **userId** ổn định. Cần xác định giao dịch hoặc bước bù trừ khi đổi mapping, tránh khoảng thời gian hai tên cùng trỏ sai hoặc tên cũ bị tái sử dụng trước khi thao tác hoàn tất.

## 14. Bảo mật và multi-tenant trong thiết kế khóa

### 14.1. Không để dữ liệu người dùng thay đổi ranh giới tenant

Giả sử ứng dụng tự nối:

~~~text
tenant:{tenantId}:user:{username}:profile
~~~

Nếu tenantId hoặc username chứa ký tự phân tách và parser dùng split theo vị trí, một input được tạo khéo léo có thể làm lệch các thành phần. Đây có thể là lỗi phân quyền nếu tầng truy vấn dùng các thành phần tách ra không đúng.

Cách phòng tránh: tenantId từ ngữ cảnh xác thực của server; validate/canonicalize từng phần; mã hóa ranh giới không nhập nhằng; kiểm tra quyền trên **định danh tenant đã xác thực** khi đọc/ghi, thay vì chỉ tin vào tên key được client gửi.

**Đặt tenantId trong key không tự tạo cách ly bảo mật.** Quy tắc phân quyền vẫn phải được cưỡng chế tại ứng dụng hoặc cơ chế truy cập của database.

### 14.2. Không để tên dễ nhầm trở thành đường dẫn truy cập nhạy cảm

Ký tự có hình dáng giống nhau (homoglyph), ký tự không hiển thị hoặc trình bày từ phải sang trái có thể gây nhầm trong màn hình quản trị và nhật ký. Với username, tên tenant hoặc namespace do người dùng tự tạo, nên có chính sách ký tự cho phép, cảnh báo tên gần giống và hiển thị ID ổn định khi xác minh thao tác nhạy cảm.

Chuẩn hóa Unicode không thay thế quy trình xác thực, phân quyền hoặc chống lạm dụng tên.

### 14.3. Tránh lộ dữ liệu nhạy cảm qua tên khóa

Tên key đôi khi xuất hiện trong trace, metric, log, dashboard hoặc bản sao lưu. Không nên gắn mật khẩu, token truy cập, email hoặc số điện thoại thô vào key chỉ vì cách này thuận tiện để debug. Dùng định danh nội bộ, hoặc cơ chế mã hóa/băm phù hợp với mô hình đe dọa và nhu cầu tra cứu. Hash đơn giản của một giá trị dễ đoán vẫn có thể bị tấn công dò đoán; không xem hash là bảo mật mặc định.

## 15. Tình huống thực tế: thiết kế một kho cấu hình theo tenant và người dùng

Một ứng dụng SaaS lưu cài đặt màn hình. Người dùng có thể nhập username gồm Unicode, tên có thể đổi, mỗi tenant có tập user riêng.

### Phương án dễ gặp nhưng rủi ro

~~~text
key = tenantId + ":" + username + ":" + settingName
~~~

Những vấn đề có thể xuất hiện:

| Tình huống | Hậu quả |
| --- | --- |
| Ghi bằng **Alice**, đọc bằng **alice** | Không tìm thấy nếu hai key khác nhau |
| Username có dấu **:** | Khóa bị phân tách sai nếu parser dùng split |
| Username **Café** nhập bằng NFC/NFD | Hai khóa khác nhau nếu không chuẩn hóa |
| Người dùng đổi username | Mọi dữ liệu khóa theo username cần chuyển hoặc alias |
| Hai tenant có cùng username | Dễ nhầm nếu quy trình bỏ qua tenantId |
| Hai yêu cầu đăng ký tên đồng thời | Kiểm tra đọc trước ghi sau có thể tạo race |

### Phương án có ranh giới rõ

Giữ một **userId** ổn định và một mapping duy nhất từ tên chuẩn theo tenant sang userId:

~~~text
Users:
  PK = TENANT#<tenantId>
  SK = USER#<userId>

Username lookup:
  PK = TENANT#<tenantId>
  SK = USERNAME#<encoded-usernameCanonical>
  value = <userId>

Settings:
  PK = TENANT#<tenantId>#USER#<userId>
  SK = SETTING#<encoded-settingName>
~~~

Đây là cấu trúc logic minh họa, không phải schema tối ưu mặc định cho mọi sản phẩm. Khi triển khai trong DynamoDB, Cassandra, Redis hoặc MongoDB phải điều chỉnh theo cách biểu diễn khóa, giới hạn kích thước, tính năng query và transaction của từng hệ.

Một luồng tạo tài khoản có thể là:

~~~mermaid
flowchart TD
    A["Nhận username + tenant từ phiên xác thực"] --> B["Validate và canonicalize"]
    B --> C["Tính khóa mapping"]
    C --> D{"Mapping chưa tồn tại?"}
    D -->|"Có, ghi có điều kiện thành công"| E["Tạo userId và dữ liệu user"]
    D -->|"Đã tồn tại / tranh chấp"| F["Báo tên đã được sử dụng"]
    E --> G["Cấp quyền theo userId, tenantId ổn định"]
~~~

Trình tự trong sơ đồ nhấn mạnh **ý định xử lý trùng tên**. Trong hệ thống thật, tạo mapping và bản ghi user cần được phối hợp bằng transaction hỗ trợ nhiều item hoặc một quy trình có idempotency và xử lý bù trừ, tránh mapping tồn tại nhưng user chưa được tạo.

Khi đổi tên, cập nhật mapping theo cơ chế phù hợp và giữ userId không đổi. Cách này giúp tách chính sách hiển thị tên khỏi cấu trúc dữ liệu nghiệp vụ.

## 16. Bộ tình huống nên chuẩn bị khi kiểm chứng quy tắc

Để hiểu hợp đồng khóa trước khi dùng rộng, xây dựng một tập trường hợp có kết quả kỳ vọng rõ. Đây là những trường hợp **thiết kế cần xác định**, không phải tuyên bố một cách so khớp đúng cho mọi sản phẩm:

| Đầu vào A | Đầu vào B | Câu hỏi cần chốt |
| --- | --- | --- |
| **Alice** | **alice** | Username có không phân biệt hoa/thường? |
| **Café** dạng U+00E9 | **Café** dạng e + U+0301 | Có dùng NFC/NFD nhất quán? |
| **Ａ** toàn chiều rộng | **A** ASCII | Có cố ý dùng NFKC không? |
| **Straße** | **STRASSE** | Lowercase đơn giản hay full case folding? |
| **I**, **İ**, **ı** | **i** | Có phụ thuộc locale hoặc quy tắc Unicode? |
| **a** Latin | **а** Cyrillic | Có kiểm tra tên dễ gây nhầm không? |
| **alice** | **alice** + khoảng trắng cuối | Tự trim hay từ chối? |
| **A|B** | Hai thành phần **A**, **B** | Encoding delimiter có tránh va chạm? |
| Chữ Việt nhiều dấu | Cùng chữ dưới dạng tổ hợp code point | Chuẩn hóa có giữ ý nghĩa và cho cùng key? |
| Emoji trong username | Emoji có chuỗi code point/variation selector khác | Những chuỗi nào được xem là tương đương? |
| Timestamp cùng thời điểm nhưng khác timezone | Biểu diễn UTC cố định | Sort key có cùng thứ tự thời gian? |
| Username chứa tab/newline | Username thông thường | Có chặn ký tự điều khiển? |
| Một username đã tồn tại | Hai đăng ký đồng thời | Cơ chế uniqueness có nguyên tử không? |

Nên kiểm tra cùng một tập chuỗi trên mọi thành phần sinh key (API Java, batch, script di chuyển, công cụ hỗ trợ, service viết bằng ngôn ngữ khác). Khi phát hiện hai thành phần cho kết quả khác nhau, nguyên nhân có thể là charset, Unicode version, locale, escape rule hoặc thứ tự transform.

## 17. Bài tập vận dụng

### Bài 1: Phân tích va chạm

Ứng dụng ghép khóa theo công thức:

~~~text
key = tenant + "|" + department + "|" + username
~~~

Cho hai bộ giá trị:

~~~text
A: tenant = "T01|D02", department = "sales", username = "alice"
B: tenant = "T01", department = "D02|sales", username = "alice"
~~~

**Yêu cầu:** Tính chuỗi key của A và B, giải thích lỗi và đưa ra hai cách sửa.

**Gợi ý:** Cả hai tạo cùng **T01|D02|sales|alice**. Có thể cấm dấu **|** trong các ID thuộc miền nội bộ hoặc mã hóa từng thành phần (length-prefix/base64url/tuple codec). Ngoài ra, tenant phải được xác định từ ngữ cảnh tin cậy của server.

### Bài 2: Chuẩn hóa Unicode

Cho hai chuỗi Java:

~~~java
String a = "Ma\u0301i";
String b = "M\u00e1i";
~~~

**Yêu cầu:** Giải thích vì sao chúng có thể khác nhau trước NFC; tính kết quả chuẩn hóa NFC; đánh giá xem có nên bỏ dấu tiếng Việt để làm khóa hay không.

**Gợi ý:** Hai cách biểu diễn dấu có thể về cùng chuỗi sau NFC. Bỏ dấu có thể làm nhiều từ/tên khác nhau nhập thành một; chỉ thực hiện khi sản phẩm định nghĩa rõ cơ chế tìm kiếm không dấu, thường trên trường tìm kiếm riêng thay vì primary ID.

### Bài 3: Lựa chọn chính sách case

Một hệ thống có hai trường:

~~~text
username = "Alice"
externalProductCode = "Ab-009"
~~~

**Yêu cầu:** Nếu username không phân biệt hoa/thường, nhưng nhà cung cấp quy định mã sản phẩm có phân biệt hoa/thường, hãy mô tả canonical form cho từng trường.

**Gợi ý:** Username có thể cần chính sách case-insensitive rõ ràng. Mã sản phẩm phải giữ đúng semantics của nhà cung cấp; không áp dụng chung hàm lowercase cho mọi trường.

### Bài 4: Đọc theo tiền tố

Một hệ thống lưu khóa base64url theo từng thành phần:

~~~text
v1|tenant|<enc(tenant)>|user|<enc(username)>|settings
~~~

**Yêu cầu:** Phân biệt truy vấn “mọi settings của username chính xác” và “mọi username bắt đầu bằng **al**”.

**Gợi ý:** Với kho hỗ trợ prefix range, prefix đã mã hóa của **nguyên username** có thể nhóm tài nguyên cho user đó. Phần base64url không có tính chất bảo toàn prefix của text gốc, vì vậy autocomplete theo vài ký tự đầu cần index hoặc cơ chế tìm kiếm riêng.

### Bài 5: Đổi thuật toán

Hệ thống v1 dùng NFC + lowercase đơn giản. Nhóm phát triển muốn chuyển sang Unicode full case folding để gộp thêm một số cặp username.

**Yêu cầu:** Nêu điều gì xảy ra nếu hai username trước đây khác nhau lại có cùng canonical mới; mô tả hướng di chuyển không làm ghi đè bản ghi.

**Gợi ý:** Phải phát hiện va chạm và giải quyết theo nghiệp vụ trước khi backfill. Dùng version, migration, quy tắc chuyển đọc/ghi và kiểm tra dữ liệu; không chỉ thay hàm canonicalize.

## 18. Kết luận

Trong NoSQL, **chuẩn hóa chuỗi khóa là một phần của thiết kế định danh và truy cập dữ liệu**. Unicode có nhiều cách biểu diễn tương đương; quy tắc hoa/thường phụ thuộc nghiệp vụ và locale; dấu phân tách có thể làm hai bộ thành phần khác nhau tạo cùng một khóa. Các quyết định về NFC/NFKC, case folding, khoảng trắng, escape/encoding và thứ tự thành phần phải được viết thành một hợp đồng nhất quán, thực hiện trước mọi thao tác ghi, đọc và lập chỉ mục.

Một thiết kế bền vững thường dùng **ID nội bộ ổn định**, **giá trị canonical riêng cho trường cần tìm/đảm bảo duy nhất**, **mã hóa từng thành phần không mơ hồ**, và **phiên bản quy tắc khi có khả năng thay đổi**. Cần kiểm tra giới hạn byte, khả năng sort/prefix thực tế của hệ quản trị, ghi có điều kiện để chống trùng, và kế hoạch di chuyển khi thay đổi cách sinh khóa. Những bước này bảo vệ tính đúng đắn của dữ liệu ngay cả khi ứng dụng có nhiều service, nhiều ngôn ngữ lập trình và nhiều loại cơ sở dữ liệu.
