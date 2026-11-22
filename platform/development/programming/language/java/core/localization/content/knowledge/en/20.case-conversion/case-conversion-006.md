# Phân biệt chữ hiển thị, khóa tìm kiếm và mã định danh trong Java

Trong ứng dụng đa ngôn ngữ, cùng một đối tượng có thể có **chữ hiển thị** (`displayName`), **khóa tìm kiếm** (`searchKey`) và **mã định danh** (`id`). Ba thành phần này liên quan với nhau nhưng mang trách nhiệm khác nhau. Nhầm chúng khiến đổi tên làm mất liên kết, tìm kiếm sai khi có ký tự Unicode, xử lý chữ hoa/thường phụ thuộc cấu hình máy chủ, hoặc gộp nhầm hai tài khoản có tên giống nhau.

Bài này thuộc nhóm **Chữ hoa và thường** của Java Core localization, giúp hiểu cách thiết kế ba lớp dữ liệu, chọn phép biến đổi chữ có chủ đích và nhận biết giới hạn của `String.toLowerCase`, Unicode normalization và các công cụ so sánh ngôn ngữ trong Java 17+.

## 1. Ba khái niệm cốt lõi

| Thành phần | Mục đích | Ví dụ | Tính chất |
| --- | --- | --- | --- |
| Chữ hiển thị (`displayName`) | Dùng trên UI, email, hồ sơ | `Éclair Café` | Có thể đổi; cần bảo toàn cách viết được người dùng cho phép |
| Khóa tìm kiếm (`searchKey`) | Tăng khả năng tìm khớp | `éclair café` | Dẫn xuất theo chính sách, có thể tái tạo |
| Mã định danh (`id`) | Xác định đúng thực thể, khóa ngoại, phân quyền | UUID `11111111-1111-4111-8111-111111111111` | Ổn định, độc lập locale và cách viết tên |

Ví dụ một bản ghi:

~~~text
id:          11111111-1111-4111-8111-111111111111
displayName: Éclair Café
searchKey:   éclair café
~~~

Nếu người dùng đổi tên thành `Cafe Nouveau`, hệ thống đổi `displayName` và tính lại `searchKey`, nhưng **giữ nguyên `id`**. Một đơn hàng, bài viết, quan hệ bạn bè hoặc tài khoản quyền truy cập không vì việc đổi tên mà biến thành thực thể khác.

**Nguyên tắc:** tên là thuộc tính có thể thay đổi; khóa tìm kiếm là công cụ truy xuất; ID là danh tính kỹ thuật. Không lấy bất kỳ chuỗi nào đã bỏ dấu hoặc đổi chữ hoa/thường làm ID mặc định.

## 2. Vì sao chữ hiển thị cần giữ đúng cách viết?

Tên người, thương hiệu và văn bản tự nhiên có dấu, chữ hoa/thường, nhiều hệ chữ, ký tự tổ hợp và lựa chọn cách viết được người dùng hoặc người biên tập quyết định:

~~~text
Đặng Thị Mai
İstanbul
Éclair Café
Αλέξανδρος
李明
~~~

Việc tự lưu lại dưới dạng chữ thường hoặc chữ hoa có thể thay đổi cách viết mà người dùng mong muốn. Vì thế:

- Lưu `displayName` theo hợp đồng nhập liệu, có thể áp Unicode normalization nếu có **chính sách rõ**.
- Không ghi đè nội dung gốc chỉ vì lập chỉ mục tìm kiếm cần khóa đã lowercase.
- Nếu UI muốn định dạng chữ hoa, thực hiện **chỉ ở tầng trình bày** và theo ngôn ngữ phù hợp, không biến phép trình bày thành thay đổi danh tính.
- Xử lý HTML escaping, SQL parameterization, validation, ký tự điều khiển và các yêu cầu bảo mật riêng; chuẩn hóa/casing không thay thế các bước đó.

Có trường hợp ứng dụng cần giữ nguyên bản gốc phục vụ kiểm toán, chữ ký, tên pháp lý hoặc nội dung do người dùng sáng tác. Việc chuẩn hóa Unicode cũng phải được xem xét tại đúng ranh giới dữ liệu, không tự sửa mọi văn bản mà không thông báo.

## 3. Chuyển chữ hoa/thường trong Java phụ thuộc Locale

`String.toLowerCase()` và `String.toUpperCase()` không có đối số sử dụng **locale mặc định của JVM**. Đó là nguồn lỗi nếu được dùng để tạo khóa máy ổn định:

~~~java
String code = "TITLE";
String unsafe = code.toLowerCase(); // tùy Locale.getDefault()
String stableExample = code.toLowerCase(Locale.ROOT);
~~~

Đây là đoạn minh họa cần import `java.util.Locale`.

Với locale tiếng Thổ Nhĩ Kỳ, chữ `I` có thể được lowercase thành `ı` (i không chấm), khác `i` trong nhiều ngữ cảnh tiếng Anh.

~~~text
"TITLE".toLowerCase(Locale.ROOT)  → "title"
"TITLE".toLowerCase(tr-TR)        → "tıtle"
~~~

Cách chuyển trong tiếng Thổ Nhĩ Kỳ có những cặp cần phân biệt:

| Ký tự | Unicode | Vai trò |
| --- | --- | --- |
| `I` | U+0049 | Chữ hoa của `ı` trong tiếng Thổ Nhĩ Kỳ |
| `ı` | U+0131 | i thường không chấm |
| `İ` | U+0130 | I hoa có chấm |
| `i` | U+0069 | i thường có chấm |

**Từ đó có hai quyết định khác nhau:**

1. Với **văn bản tự nhiên tiếng Thổ Nhĩ Kỳ**, phải xét quy tắc case mapping theo ngôn ngữ của nội dung.
2. Với **khóa giao thức không phụ thuộc ngôn ngữ**, phải chọn chính sách tường minh (thường là cú pháp ASCII xác định hoặc xử lý với `Locale.ROOT` khi phù hợp), thay vì dùng default locale của server.

Không có quy tắc “cứ `Locale.ROOT` là đúng cho mọi loại dữ liệu”. Trong search và identifier Unicode, nó là một công cụ, không phải hợp đồng hoàn chỉnh.

### Một ký tự có thể biến thành nhiều ký tự

Java `String.toUpperCase(Locale)` có thể làm thay đổi độ dài chuỗi, ví dụ tiếng Đức:

~~~java
"straße".toUpperCase(Locale.GERMAN); // "STRASSE" trong JDK đã thử
~~~

Nếu mã nguồn giả định phép chuyển chữ luôn 1:1 theo `char`, nó có thể xử lý sai độ dài, vị trí hoặc ràng buộc dữ liệu. Đừng tạo buffer cố định theo `original.length()` rồi cho rằng kết quả uppercase luôn bằng độ dài cũ.

## 4. Locale.ROOT không phải Unicode full case folding

Một so sánh thú vị:

~~~java
"straße".toLowerCase(Locale.ROOT); // "straße"
"STRASSE".toLowerCase(Locale.ROOT); // "strasse"
~~~

Hai chuỗi này **không bằng nhau** theo `String.equals`, dù chữ `straße` khi uppercase có thể trở thành `STRASSE`.

Do đó cần tách:

- **Case conversion:** đổi từ hoa sang thường, hoặc ngược lại, cho mục đích trình bày/xử lý.
- **Case folding:** thuật toán Unicode cho một chính sách so khớp không phân biệt chữ hoa/thường; có các cách áp dụng và biến thể.
- **Case-insensitive comparison:** so sánh theo yêu cầu của một trường dữ liệu hoặc ngôn ngữ.
- **Collation:** so sánh và sắp xếp chuỗi theo quy tắc ngôn ngữ.

`toLowerCase(Locale.ROOT)` không tự thực hiện mọi ánh xạ full case folding. `String.equalsIgnoreCase` cũng không phải giải pháp so sánh đầy đủ theo locale; tài liệu Java hướng dẫn dùng `Collator` cho những bài toán so sánh có tính ngôn ngữ.

Đừng lấy kết quả của một bước lower-case rồi tuyên bố toàn bộ username/search đa ngôn ngữ đã được canonical một cách an toàn.

## 5. Unicode normalization là một lớp độc lập với casing

Hai chuỗi có thể cùng hiển thị `é` nhưng chứa code point khác nhau:

~~~text
U+00E9            → é (dạng tổ hợp sẵn)
U+0065 U+0301     → e + dấu sắc kết hợp
~~~

`String.equals` chưa chuẩn hóa xem chúng khác nhau. `Normalizer.normalize(text, Normalizer.Form.NFC)` có thể đưa các biểu diễn tương đương chuẩn tắc về dạng ổn định.

Một pipeline tìm kiếm **minh họa** có thể là:

~~~text
displayName
   ↓ NFC
chuỗi chuẩn tắc
   ↓ toLowerCase(Locale.ROOT)
chuỗi xử lý chữ thường
   ↓ NFC lần nữa
searchKey
~~~

NFC lần thứ hai hữu ích vì case mapping có thể tạo ra chuỗi với combining marks. Nhưng pipeline trên **không tự bỏ dấu** và cũng không phải full casefold/search engine cho mọi ngôn ngữ. Cần thiết kế nó theo tập ngôn ngữ mà sản phẩm hỗ trợ.

Không nhầm:

- **UTF-8/UTF-16**: encoding bytes hoặc UTF-16 code units.
- **NFC/NFD**: chuẩn hóa tương đương chuẩn tắc của Unicode.
- **NFKC/NFKD**: chuẩn hóa có thêm tương đương tương thích, có thể làm mất khác biệt hình thức.
- **Case conversion**: đổi chữ hoa/thường.
- **Dịch/phiên âm/chuyển tự**: tác vụ ngôn ngữ khác.

### Tìm kiếm không dấu là yêu cầu riêng

Người dùng tiếng Việt có thể muốn tìm `"Đặng"` bằng `"Dang"`. NFC hoặc lower-case không tự chuyển `đ` thành `d`, và việc bỏ dấu từ NFD thường cũng không đủ cho mọi ký tự. Nếu tạo alias không dấu, đó là **dữ liệu tìm kiếm mất thông tin**, cần giữ nguồn gốc hiển thị.

Ví dụ `ma`, `má`, `mà`, `mạ`, `mã`, `mả` có thể thành cùng alias `ma` khi bỏ dấu. Điều này có thể chấp nhận cho **trả nhiều ứng viên tìm kiếm**, nhưng không thể dùng để kết luận họ cùng một người hoặc để cấp quyền đăng nhập.

## 6. Tạo searchKey: có chính sách, nguồn và phiên bản

Khóa tìm kiếm là dữ liệu **dẫn xuất từ nguồn**. Nó nên có những invariant:

- Cùng input và cùng phiên bản policy thì kết quả giống nhau.
- Mọi đường ingest (UI, API, import, batch) dùng cùng chính sách.
- Query và dữ liệu được index được xử lý tương thích.
- Khi displayName đổi, searchKey được tạo lại.
- Nếu nâng chính sách hoặc dữ liệu Unicode, có thể **rebuild index** từ nguồn.
- Những đối tượng có cùng searchKey vẫn có thể là hai ID khác nhau.

Một cấu trúc dễ hiểu:

~~~text
id:                UUID ổn định
displayName:       "Đặng Thị Mai"
searchKeyExact:    NFC + case policy đã chọn
searchIndexLoose:  alias phục vụ tìm không dấu (nếu cần)
~~~

Đây là **một mô hình**, không phải đề nghị mọi hệ thống bắt buộc có ba loại index. Search theo tên, full-text search, gợi ý/autocomplete, fuzzy matching hoặc multilingual search có thể yêu cầu analyzer và thư viện chuyên dụng.

### Đừng đưa searchKey ra làm trường chỉnh sửa tùy ý

Trong nhiều API, client chỉ cần gửi `displayName`. Backend phải tự tính searchKey theo policy, thay vì tin một `searchKey` do client gửi có thể giả mạo hoặc không nhất quán. Nếu search index bất đồng bộ, sản phẩm cần xác định độ trễ chấp nhận được; **ID không bao giờ phụ thuộc vào việc index đã cập nhật hay chưa**.

### Thay policy có thể tạo collision

Nếu policy v1 chỉ dùng NFC và v2 thêm bỏ dấu/casefold, những chuỗi trước đây khác nhau có thể cho cùng searchKey. Search index cần chấp nhận nhiều kết quả hoặc xử lý ranking; không được tự gộp thực thể. Khi cải tiến search, nên version policy, rebuild dữ liệu, so sánh collision và kiểm thử migration.

## 7. ID và tên đăng nhập là hai bài toán khác nhau

Một mã định danh ổn định có thể là:

- ID số nguyên do cơ sở dữ liệu cấp.
- UUID (trong Java có `java.util.UUID`, ví dụ `UUID.randomUUID()`).
- Khóa nghiệp vụ bất biến do hệ thống có thẩm quyền cấp.

Khác với displayName, ID không cần dựa vào ngôn ngữ. Với hệ thống có nhiều người trùng tên, hai người vẫn có **hai ID khác nhau**. Nếu tên đổi, ID và các khóa ngoại, quan hệ, log vẫn phải giữ.

### URL slug không mặc nhiên là ID

Một URL thân thiện có thể chứa slug `san-pham-mua-he` tạo từ tên `Sản phẩm mùa hè`. Tuy nhiên, slug có thể đổi khi tên đổi và có thể trùng khi hai đối tượng có tên giống nhau. Slug cần được quản lý như alias/đường dẫn có uniqueness và chính sách redirect nếu đưa ra ngoài. Một thiết kế có thể chứa cả ID bất biến và slug hiển thị trong URL, nhưng slug không tự động thay thế khóa chính.

### Username cần canonical policy riêng

`username` có thể là tên đăng nhập mà người dùng ghi nhớ, nhưng nó có yêu cầu **duy nhất và bảo mật** chặt hơn searchKey:

- Có cho phép Unicode hay chỉ ASCII?
- Giữ phân biệt hoa/thường hay so sánh không phân biệt?
- Nếu hỗ trợ Unicode, dùng NFC/NFKC, casefold và profile nào?
- Có cần chặn confusables, ký tự vô hình, script trộn không?
- Giới hạn độ dài tính theo ký tự Unicode, UTF-16, byte hay grapheme?
- Có tên dành riêng và chính sách chuyển tên không?
- Khi username đổi, có giữ alias hoặc khóa đăng nhập cũ hay không?

Một model có thể gồm:

~~~text
userId:             UUID, bất biến
displayName:        Chữ người dùng nhìn thấy
usernameDisplay:    Tên đăng nhập được hiển thị
usernameCanonical:  Biểu diễn được chính sách định danh chấp nhận
searchKey:          Khóa tìm tên, có thể trùng với người khác
~~~

Không bắt buộc mọi ứng dụng dùng đủ các trường, nhưng **không dùng một hàm searchKey mất thông tin làm canonical username nếu chưa có đặc tả**.

### Uniqueness phải bảo vệ ở database

Kiểm tra `SELECT` xem username chưa tồn tại rồi mới `INSERT` không ngăn race condition. Hai request có thể cùng kiểm tra thành công rồi cùng tạo một canonical key. Cần constraint/index duy nhất theo policy ở tầng lưu trữ và xử lý conflict có kiểm soát.

Khi thay đổi policy canonical của username, nếu hai tên cũ nay gộp vào một khóa, **không được tự động gộp tài khoản**. Cần kế hoạch phát hiện/giải quyết collision, bảo toàn ownership và lịch sử.

## 8. Ví dụ Java 17+ hoàn chỉnh: ba lớp dữ liệu

Chương trình dưới đây dùng một UUID cố định để dễ kiểm thử; trình diễn displayName được bảo toàn, tìm kiếm khớp khi Unicode ở dạng dấu kết hợp, ID giữ nguyên khi đổi tên, đồng thời nêu giới hạn của locale casing.

Tạo file **`DisplaySearchIdDemo.java`**:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.UUID;

public class DisplaySearchIdDemo {
    record Profile(UUID id, String displayName, String searchKey) {}

    static String makeSearchKey(String displayName) {
        String canonical = Normalizer.normalize(
                displayName, Normalizer.Form.NFC);
        String lowered = canonical.toLowerCase(Locale.ROOT);
        return Normalizer.normalize(lowered, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        UUID id = UUID.fromString(
                "11111111-1111-4111-8111-111111111111");

        String displayed = "\u00c9clair Caf\u00e9";
        Profile first = new Profile(
                id, displayed, makeSearchKey(displayed));

        String query = "E\u0301CLAIR CAFE\u0301";
        System.out.println("Display preserved: "
                + first.displayName().equals(displayed));
        System.out.println("Search match: "
                + first.searchKey().equals(makeSearchKey(query)));

        Profile renamed = new Profile(
                first.id(), "Cafe Nouveau",
                makeSearchKey("Cafe Nouveau"));

        System.out.println("ID stable after rename: "
                + first.id().equals(renamed.id()));
        System.out.println("Search key changed: "
                + !first.searchKey().equals(renamed.searchKey()));

        String title = "TITLE";
        Locale turkish = Locale.forLanguageTag("tr-TR");
        System.out.println("Turkish differs from ROOT: "
                + !title.toLowerCase(turkish)
                        .equals(title.toLowerCase(Locale.ROOT)));
        System.out.println("ROOT is title: "
                + title.toLowerCase(Locale.ROOT).equals("title"));

        System.out.println("German lowercase equals: "
                + "\u00dftest".toLowerCase(Locale.ROOT)
                        .equals("SSTEST".toLowerCase(Locale.ROOT)));
        System.out.println("German uppercase same: "
                + "stra\u00dfe".toUpperCase(Locale.GERMAN)
                        .equals("STRASSE"));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 DisplaySearchIdDemo.java
java DisplaySearchIdDemo
~~~

Stdout đã được kiểm tra:

~~~text
Display preserved: true
Search match: true
ID stable after rename: true
Search key changed: true
Turkish differs from ROOT: true
ROOT is title: true
German lowercase equals: false
German uppercase same: true
~~~

**Giải thích kết quả:**

1. `Display preserved: true` — chữ hiển thị không bị âm thầm đổi sang lowercase khi tạo searchKey.
2. `Search match: true` — query dùng `E + U+0301` và dạng chữ hoa, còn displayName có `É` tổ hợp sẵn; NFC + lower-case được áp cả hai phía nên khớp trong ca kiểm thử.
3. `ID stable after rename: true` — UUID của profile không đổi khi tên và searchKey đổi.
4. `Search key changed: true` — index phải cập nhật cùng thay đổi tên.
5. `Turkish differs from ROOT: true` — quy tắc chữ `I` không giống giữa tiếng Thổ Nhĩ Kỳ và ROOT.
6. `ROOT is title: true` — trong ví dụ khóa tiếng Anh, `Locale.ROOT` tránh phụ thuộc locale JVM.
7. `German lowercase equals: false` — `String.toLowerCase(Locale.ROOT)` không phải full Unicode case folding.
8. `German uppercase same: true` — case mapping có thể biến một ký tự thành nhiều ký tự, chẳng hạn ß thành SS.

`Profile` là record Java 17 minh họa, **không phải một hệ thống đăng nhập production**. Nó chưa validation null, giới hạn độ dài, uniqueness, xác thực, security profile hoặc chính sách versioning. Hàm `makeSearchKey` chỉ phù hợp làm ví dụ hoặc điểm xuất phát được kiểm thử trong một phạm vi cụ thể.

## 9. So sánh ngôn ngữ và tìm kiếm không đồng nghĩa

`java.text.Collator` có thể so sánh/sắp xếp chuỗi theo một locale. Ví dụ:

~~~java
Collator collator = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));

int order = collator.compare(leftDisplayText, rightDisplayText);
~~~

Đây là **đoạn minh họa**, cần import `java.text.Collator`, `java.util.Locale` và khai báo hai `String` đầu vào. Chọn `strength`/`decomposition` theo yêu cầu sẽ ảnh hưởng việc xét chữ hoa, dấu và các khác biệt khác.

Tuy nhiên, **Collator dành cho so sánh có tính ngôn ngữ**, không nên mặc định dùng `collator.compare(a,b)==0` để quyết định hai username hay hai tài khoản là cùng một người. Quan hệ danh tính cần policy định danh riêng.

Nếu sản phẩm cần search đa ngôn ngữ nâng cao, có thể cần ICU4J hoặc search engine có analyzer và quy tắc Unicode/locale thích hợp. Chọn công cụ theo yêu cầu thay vì mặc định một phép `toLowerCase` giải quyết tất cả.

## 10. An toàn Unicode và ký tự trông giống nhau

Các ký tự từ hai hệ chữ có thể trông giống nhau nhưng không canonically equivalent. Ví dụ một chữ `a` Latin và chữ hình dáng tương tự ở Cyrillic không nhất thiết bị NFC gộp lại. Unicode normalization và lowercase không tự loại bỏ mọi **confusables/homoglyph attacks**.

Với username, domain, mã định danh do con người nhập hoặc trường ảnh hưởng phân quyền:

- Quy định tập ký tự, script và normalization/casefold được phép.
- Kiểm tra ký tự điều khiển hoặc ký tự vô hình theo tiêu chuẩn của loại trường.
- Áp một identifier security profile thích hợp thay vì tin rằng `NFC + Locale.ROOT` luôn an toàn.
- Không sử dụng kết quả tìm kiếm “gần giống” hoặc alias không dấu để cấp quyền.
- Giữ quan hệ truy cập dựa trên ID bất biến và policy canonical username đã được duyệt.
- Render text bằng escaping; tham số hóa truy vấn SQL; normalization không thay thế phòng chống injection.

Hai người có cùng displayName là điều có thể hợp lệ. Vấn đề phát sinh khi hệ thống dùng **searchKey không duy nhất** thay cho identity. Cần đưa ra nhiều kết quả tìm kiếm và phân biệt bằng dữ liệu bổ sung được phép công khai, thay vì mặc định hai bản ghi là một.

## 11. Thiết kế database và API

Một schema SQL ở mức minh họa:

~~~sql
CREATE TABLE customer_profile (
    id VARCHAR(36) PRIMARY KEY,
    display_name VARCHAR(256) NOT NULL,
    search_key VARCHAR(512) NOT NULL
);

CREATE INDEX idx_customer_search
    ON customer_profile(search_key);
~~~

Đây là SQL khái niệm; database có thể có kiểu UUID native, cách xử lý collation, độ dài chuỗi và kiểu index khác nhau. **Đừng tạo UNIQUE cho search_key** nếu người dùng có thể trùng tên. Nếu có `username_canonical`, đặt unique constraint riêng cho trường ấy theo policy và collation được xác minh.

API trả về cho client thường chỉ cần:

~~~json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "displayName": "Éclair Café"
}
~~~

`searchKey` là dữ liệu index phía server; không nhất thiết là trường người dùng được chỉnh sửa. Trong cùng giao dịch cập nhật tên, có thể cập nhật index đồng bộ hoặc phát sự kiện cho index bất đồng bộ với yêu cầu idempotent và độ trễ rõ ràng. Dù cách index nào, ID vẫn phải là nguồn nhận diện thực thể.

### Khi thay phiên bản search policy

Một lộ trình an toàn là:

1. Gắn phiên bản/định nghĩa rõ pipeline index hiện tại.
2. Xây policy mới và test từng locale, đặc biệt Turkish I, German ß và tiếng Việt có dấu.
3. So sánh collision và khả năng tìm, tránh thay đổi quyền sở hữu hoặc uniqueness vô tình.
4. Rebuild index mới từ `displayName` đã lưu, có thể chạy song song trước khi chuyển traffic.
5. Đổi query pipeline đồng bộ với index mới.
6. Giữ nguyên ID và khóa ngoại; không coi migration search là migration danh tính.

Nếu dữ liệu Unicode/JDK hoặc thư viện search được nâng phiên bản, kiểm tra case mapping và behavior index có thể thay đổi ở các ký tự biên.

## 12. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Lowercase rồi lưu đè tên người | Mất cách viết hiển thị | Giữ displayName; tạo searchKey riêng |
| Dùng `toLowerCase()` không locale cho khóa máy | Phụ thuộc locale JVM, ví dụ Turkish I | Chính sách máy xác định; `Locale.ROOT` nếu phù hợp |
| Coi `Locale.ROOT` là full casefold | Lỗi với ánh xạ Unicode phức tạp | Dùng thuật toán/profile thích hợp |
| Lấy displayName làm khóa ngoại | Đổi tên phá liên kết | Dùng ID bất biến |
| Tạo ID bằng bỏ dấu/lowercase | Tên khác nhau thành cùng ID | ID cấp độc lập |
| Dùng slug như khóa chính mà không quản lý alias | Trùng slug hoặc mất liên kết khi đổi tên | ID và slug là hai trách nhiệm riêng |
| Chỉ normalize phía dữ liệu, không normalize query | Bỏ sót khớp khi combining marks khác | Xử lý tương thích hai phía |
| Dùng NFKC thay NFC tùy tiện | Mất một số khác biệt ký tự | Định nghĩa theo trường |
| Gộp các kết quả cùng searchKey | Nhầm người/đối tượng | SearchKey có thể trùng; trả nhiều ứng viên |
| Dùng searchKey bỏ dấu làm username canonical | Va chạm và rủi ro phân quyền | Username policy riêng |
| Chỉ check username trùng trước insert | Race condition | Unique constraint của DB |
| Dùng `equalsIgnoreCase` như bộ collation đa ngôn ngữ | Sai theo một số ngôn ngữ | Collator/engine thích hợp |
| Tin rằng lowercase loại hết homoglyph | Có thể bị giả mạo bằng Unicode | Identifier security profile riêng |
| Không rebuild index khi đổi policy | Kết quả search không đồng nhất | Versioned migration |
| Chuyển chữ rồi giả định độ dài không đổi | Sai ràng buộc/offset | Kiểm thử ánh xạ 1:n |
| Dùng locale của khách để thay đổi ID | ID phụ thuộc request | ID/canonical contract độc lập locale |

## 13. Checklist kiểm thử

- **Unicode:** `Éclair` precomposed vs `E + combining acute`; raw khác, search key theo NFC giống nhau.
- **Turkish casing:** `TITLE` trong `tr-TR` và `Locale.ROOT` có kết quả lower-case khác.
- **German casing:** `straße` và `STRASSE` cho thấy lowercase đơn giản không đủ full case folding.
- **Vietnamese:** `Ma`, `Má`, `Mà` không bị NFC hợp nhất; alias không dấu chỉ cho search nếu sản phẩm cần.
- **Identity:** đổi displayName một hoặc nhiều lần không làm `id` đổi.
- **Search:** nhiều thực thể có cùng searchKey vẫn tồn tại riêng; search trả danh sách kết quả.
- **Uniqueness:** hai request đăng ký username canonical trùng phải bị DB kiểm soát.
- **Security:** kiểm tra confusables, ký tự vô hình, input dài hoặc Unicode không hợp lệ theo profile.
- **Persistence:** DB collation và Java `String.equals` có thể khác; không suy ra uniqueness từ Java test đơn lẻ.
- **Migration:** thay quy tắc search không sửa khóa ngoại, có khả năng tái tạo index.
- **Defaults:** locale JVM/host khác nhau không làm thay đổi mã máy đã được định nghĩa theo policy cố định.
- **Presentation:** biến đổi chữ cho UI không ghi đè văn bản nguồn.

Một test property-based quan trọng: với mọi bản ghi có cùng ID, thay displayName rồi tái tạo searchKey **không làm thay đổi quan hệ tham chiếu ID**.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không dùng `displayName.toLowerCase()` làm khóa chính?

**Đáp án:** Tên có thể đổi và trùng; kết quả lowercase không tham số phụ thuộc locale mặc định. ID cần bất biến và duy nhất theo hệ thống.

**Câu 2.** `Locale.ROOT` có giải quyết mọi bài toán so sánh Unicode không phân biệt hoa/thường không?

**Đáp án:** Không. Nó tránh locale mặc định cho bước case conversion, nhưng không phải full case folding và không thay thế collation hoặc normalization.

**Câu 3.** Hai người có tên “Má” và “Mà” cùng search key “ma” nếu bỏ dấu. Có phải một tài khoản không?

**Đáp án:** Không. Search key bị mất thông tin, ID và chính sách username canonical phải độc lập.

**Câu 4.** Sau khi đổi tên, trường nào nên đổi?

**Đáp án:** `displayName` đổi theo người dùng; `searchKey` được tính lại; `id` giữ nguyên.

**Câu 5.** Khi hỗ trợ username Unicode case-insensitive, chỉ dùng `toLowerCase(Locale.ROOT)` có đủ không?

**Đáp án:** Chưa. Cần policy về tập ký tự, Unicode normalization/casefold, confusables và uniqueness nguyên tử, rồi kiểm thử theo các ngôn ngữ cần hỗ trợ.

**Bài thực hành:** Mở rộng `DisplaySearchIdDemo` bằng repository lưu hai người trùng displayName nhưng khác UUID; query searchKey phải trả nhiều kết quả, trong khi `findById` trả đúng một đối tượng. Thêm alias không dấu chỉ phục vụ search. Sau đó thiết kế riêng một `usernameCanonical` có chính sách uniqueness và test đổi tên không đổi quyền sở hữu.

## 15. Tài liệu chính thức

- [String — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `toLowerCase(Locale)`, `toUpperCase(Locale)` và `equalsIgnoreCase`, các ví dụ Turkish/German.
- [Normalizer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFKC và Unicode normalization.
- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `Locale.ROOT`.
- [UUID — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html): khóa UUID.
- [Collator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html): so sánh/sắp xếp văn bản theo ngôn ngữ.
- [Unicode Standard Annex #15](https://unicode.org/reports/tr15/): chuẩn hóa Unicode.
- [Unicode Case Folding](https://www.unicode.org/Public/UCD/latest/ucd/CaseFolding.txt): dữ liệu case folding khác case conversion.
- [Unicode Technical Standard #39](https://unicode.org/reports/tr39/): Unicode security/confusables.

**Kết luận:** **Chữ hiển thị dành cho con người; searchKey phục vụ truy xuất; ID là danh tính bền vững.** Phép đổi hoa/thường phải phù hợp locale và vai trò dữ liệu. NFC, case folding, bỏ dấu, collation và các bộ quy tắc identifier là những khái niệm riêng. Hãy lưu tên hiển thị theo chính sách của trường, xây searchKey có thể tái tạo và giữ ID độc lập để hệ thống an toàn khi đổi tên hoặc mở rộng đa ngôn ngữ.
