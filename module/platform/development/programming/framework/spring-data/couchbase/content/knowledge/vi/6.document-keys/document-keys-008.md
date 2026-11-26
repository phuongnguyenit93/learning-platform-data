# Giới hạn độ dài khóa theo byte và dữ liệu Unicode trong Spring Data Couchbase

## 1. Vì sao phải đo document key bằng byte?

Trong Couchbase, **document ID (document key)** xác định duy nhất một document trong phạm vi **collection**. Các thao tác key-value (KV) như `get`, `insert`, `replace` và `remove` cần đúng document ID và đúng collection. Spring Data Couchbase ánh xạ khóa này qua thuộc tính `@Id`; repository có thể đọc bằng `findById(id)` khi ứng dụng đã biết ID.

Một ràng buộc phải kiểm tra trước khi lưu là: **document ID Couchbase không được dài quá 250 byte**. Đơn vị ở đây là **byte trong biểu diễn UTF-8**, không phải số ký tự hiển thị, số Unicode code point hoặc kết quả `String.length()` của Java.

Ví dụ, ứng dụng đào tạo đa tenant có khóa:

```text
course::acme::JAVA-101
course::acme::lập-trình-java
course::acme::khóa-học-🎓
```

Các ID đều có thể được biểu diễn dưới dạng Unicode, nhưng dấu tiếng Việt và emoji thường cần nhiều byte hơn ký tự ASCII. Một khóa nhìn có vẻ ngắn vẫn có thể vượt giới hạn nếu nó chứa nhiều ký tự Unicode, có prefix dài hoặc đã trải qua encoding.

**Mục tiêu bài học:** đo độ dài đúng, lựa chọn quy tắc Unicode nhất quán, tránh va chạm do chuẩn hóa/ghép khóa và triển khai việc kiểm tra ngay tại tầng truy cập Spring Data Couchbase.

## 2. Phân biệt ký tự hiển thị, code point, UTF-16 và UTF-8

Java lưu `String` theo các **code unit UTF-16**. `String.length()` trả về số code unit UTF-16, không phải số Unicode code point và càng không phải kích thước UTF-8 của document ID.

Để tránh nhầm lẫn, cần phân biệt bốn phép đo:

| Khái niệm | Ý nghĩa | Cách kiểm tra trong Java |
| --- | --- | --- |
| Ký tự người dùng nhìn thấy (*grapheme cluster*) | Một đơn vị hiển thị có thể gồm nhiều code point | Cần thư viện/thuật toán phân đoạn Unicode phù hợp |
| Unicode code point | Giá trị Unicode như U+00E9 hoặc U+1F600 | `s.codePointCount(0, s.length())` |
| Code unit UTF-16 | Đơn vị của chuỗi Java | `s.length()` |
| Byte UTF-8 | Kích thước chuỗi mã hóa khi dùng UTF-8 | `s.getBytes(StandardCharsets.UTF_8).length` |

Một vài ví dụ minh họa:

| Chuỗi | Code unit UTF-16 | Code point | Byte UTF-8 | Giải thích |
| --- | ---: | ---: | ---: | --- |
| `A` | 1 | 1 | 1 | ASCII |
| `é` (U+00E9) | 1 | 1 | 2 | Ký tự dựng sẵn |
| `e` + U+0301 | 2 | 2 | 3 | Chữ `e` cộng dấu kết hợp |
| `ắ` (U+1EAF) | 1 | 1 | 3 | Chữ tiếng Việt dựng sẵn |
| `a` + U+0306 + U+0301 | 3 | 3 | 5 | Cách viết phân rã của `ắ` |
| `😀` (U+1F600) | 2 | 1 | 4 | Emoji ngoài BMP dùng cặp surrogate trong UTF-16 |

Hai biểu diễn của chữ `é` có thể trông giống nhau nhưng Java và Couchbase có thể nhận những **chuỗi byte khác nhau** nếu ứng dụng không thống nhất chuẩn hóa. Tương tự, chữ `ắ` có thể biểu diễn bằng một code point U+1EAF hoặc dạng phân rã **`a` + dấu breve (U+0306) + dấu sắc (U+0301)**. Phải kiểm tra code point và dạng chuẩn hóa thay vì so sánh bằng mắt.

### 2.1. Một chương trình Java để quan sát số byte

```java
import java.nio.charset.StandardCharsets;

public class UnicodeLengthDemo {
    public static void main(String[] args) {
        report("A");
        report("\u00E9");       // é dựng sẵn, NFC
        report("e\u0301");      // e + dấu sắc kết hợp
        report("\u1EAF");       // ắ dựng sẵn
        report("a\u0306\u0301"); // a + breve + acute
        report("\uD83D\uDE00"); // 😀, một code point ngoài BMP
    }

    private static void report(String s) {
        System.out.printf(
            "UTF16=%d, codePoints=%d, UTF8Bytes=%d%n",
            s.length(),
            s.codePointCount(0, s.length()),
            s.getBytes(StandardCharsets.UTF_8).length
        );
    }
}
```

Trong thực tế, hiển thị một emoji hoặc một chữ ghép dấu có thể phụ thuộc font và trình kết xuất. **Chỉ byte UTF-8 của document ID cuối cùng** mới là đại lượng cần so với giới hạn 250 byte.

### 2.2. Ví dụ ranh giới 250 byte

```java
import java.nio.charset.StandardCharsets;

String a = "\u00E9".repeat(125);
String b = "\u00E9".repeat(126);

System.out.println(a.length()); // 125 UTF-16 code units
System.out.println(a.getBytes(StandardCharsets.UTF_8).length); // 250
System.out.println(b.getBytes(StandardCharsets.UTF_8).length); // 252
```

Chuỗi `a` đạt đúng 250 byte nếu dùng **toàn bộ chuỗi làm ID**. Nhưng nếu thêm prefix `course::acme::` thì tổng vượt giới hạn. Không được kiểm tra riêng thành phần nghiệp vụ rồi quên phần namespace hoặc delimiter.

## 3. Tính ngân sách byte cho toàn bộ khóa ghép

Một khóa có thể gồm các thành phần:

```text
<type>::<tenant>::<stable-id>
```

Nếu tất cả là ASCII, kích thước đơn giản là tổng số byte của từng thành phần và dấu phân cách. Ví dụ:

```text
order::acme::<uuid>
     ^^    ^^
```

- `order`: 5 byte.
- Hai dấu `::`: 4 byte.
- `acme`: 4 byte.
- UUID chuẩn ở dạng chuỗi: 36 byte.
- **Tổng: 49 byte** cho `order::acme::<uuid>` khi UUID đúng 36 ký tự ASCII.

Do vậy, phần cố định `order::acme::` chiếm **13 byte**, còn tối đa **237 byte** dành cho phần ID động nếu không có thành phần nào khác.

Một công thức dễ áp dụng:

```text
totalKeyBytes = UTF8_BYTES(prefixes + delimiters + encodedComponents + suffixes)

totalKeyBytes <= 250
```

Điểm quan trọng là **đếm sau tất cả các bước biến đổi**: chuẩn hóa Unicode, escaping, encoding, chèn prefix/suffix và delimiter.

### 3.1. Emoji cho thấy lỗi kiểm tra bằng `String.length()`

```java
import java.nio.charset.StandardCharsets;

String prefix = "order::acme::"; // 13 byte
String emoji = "\uD83D\uDE00";   // 😀, 4 byte UTF-8

String fits = prefix + emoji.repeat(59);     // 13 + 59*4 = 249 byte
String tooLong = prefix + emoji.repeat(60);  // 13 + 60*4 = 253 byte

System.out.println(fits.getBytes(StandardCharsets.UTF_8).length);    // 249
System.out.println(tooLong.getBytes(StandardCharsets.UTF_8).length); // 253
```

Cả hai chuỗi đều có số code unit UTF-16 ít hơn 250. Một hàm chỉ kiểm tra `key.length() <= 250` sẽ chấp nhận cả chuỗi không hợp lệ `tooLong`.

### 3.2. Encoding làm phần ID dài thêm

Nếu ứng dụng mã hóa một thành phần Unicode thành Base64 URL-safe để tránh ký tự phân cách, kích thước ID sau encoding có thể **lớn hơn** byte UTF-8 gốc. Base64 thường cần khoảng bốn ký tự ASCII cho mỗi ba byte đầu vào, tùy phần dư và có dùng dấu `=` đệm hay không.

Vì vậy, không thể cấp ngân sách 237 byte cho **dữ liệu gốc** rồi mặc định Base64 vẫn vừa giới hạn; phải đo **chuỗi ID cuối cùng**. Nếu yêu cầu chỉ dùng ASCII, URI-encoding hoặc các cách escape khác cũng có chi phí độ dài tương tự cần tính đến.

## 4. Unicode normalization: hai chuỗi trông giống nhau có thể khác byte

Unicode cho phép một số ký tự hiển thị theo nhiều biểu diễn. Chẳng hạn:

```text
café          // chữ é dựng sẵn: U+00E9
cafe + ◌́     // ký tự e và dấu sắc kết hợp: U+0065 U+0301
```

Trong Java:

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

String composed = "caf\u00E9";
String decomposed = "cafe\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.getBytes(StandardCharsets.UTF_8).length);   // 5
System.out.println(decomposed.getBytes(StandardCharsets.UTF_8).length); // 6

String normalized = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
```

Nếu không có chính sách chuẩn hóa, ứng dụng có thể lưu hai document với hai ID khác nhau mà người dùng nhìn thấy cùng một tên. Couchbase không nên bị giả định sẽ tự chuẩn hóa các thành phần Unicode theo cách ứng dụng mong muốn.

### 4.1. NFC và NFD

- **NFC** (*Normalization Form C*): ưu tiên biểu diễn chuẩn đã tổ hợp khi có thể.
- **NFD** (*Normalization Form D*): phân rã chuẩn thành các thành phần cơ sở và dấu kết hợp.

Cả hai là những cách biểu diễn **tương đương chuẩn** của Unicode, nhưng chuỗi byte thu được có thể khác. Chọn **một chính sách** và áp dụng tại tất cả điểm tạo, đọc, cập nhật và xóa document key.

Ví dụ nếu miền nghiệp vụ xem hai dạng của `café` là cùng một mã, chuẩn hóa NFC là một lựa chọn phù hợp. Nếu định danh đến từ một hệ thống bên ngoài mà **chính xác từng byte** mới là danh tính, không được tự chuẩn hóa mà chưa có thỏa thuận: phép biến đổi có thể làm mất khả năng phân biệt các ID mà hệ thống nguồn coi là khác nhau.

### 4.2. Cẩn thận với NFKC và thay đổi chữ hoa/thường

**NFKC** là dạng chuẩn hóa tương thích: nó có thể chuyển một số ký tự tương thích về dạng khác, rộng hơn NFC. Việc dùng NFKC, lower-case, bỏ dấu hoặc bỏ khoảng trắng có thể hợp nhất hai mã vốn khác nhau.

Ví dụ:

```text
SKU-A   và   sku-a
a-b     và   ab
```

Không được tự cho rằng hai cặp này tương đương. Nếu nghiệp vụ yêu cầu so sánh không phân biệt hoa/thường, phải công bố rõ quy tắc canonicalization và kiểm tra xung đột dữ liệu trước khi áp dụng; nếu mã phân biệt hoa/thường, giữ nguyên.

**Một policy tốt là policy phiên bản hóa và kiểm thử được**, không phải các bước “làm sạch” âm thầm có thể gây va chạm.

### 4.3. Ký tự trông giống nhau chưa chắc tương đương Unicode

Một số ký tự thuộc những hệ chữ khác nhau có hình dáng giống hoặc gần giống nhau. NFC/NFD **không** biến mọi ký tự trông giống nhau thành một giá trị. Nếu mã định danh cho phép nhiều hệ chữ, hãy xác định quy tắc chấp nhận đầu vào, kiểm tra spoofing/confusables khi cần; đừng dùng việc “nhìn thấy giống nhau” làm ràng buộc duy nhất.

## 5. Chọn cách biểu diễn Unicode trong key

Có ba phương án thường gặp tùy nguồn dữ liệu và nhu cầu truy cập.

| Phương án | Ví dụ | Ưu điểm | Rủi ro hoặc đánh đổi |
| --- | --- | --- | --- |
| **ID ASCII ổn định** | `course::acme::<uuid>` | Dễ đo kích thước, ít vấn đề Unicode | Muốn tìm theo tên/mã hiển thị phải có truy vấn hoặc ánh xạ |
| **Unicode trực tiếp** | `course::acme::lập-trình` | Dễ đọc trong log | Phải chuẩn hóa, escape delimiter và kiểm soát byte |
| **Mã hóa thành phần Unicode** | `course::acme::<base64url(UTF8(NFC(code)))>` | Phân cách không nhập nhằng nếu có quy ước | Tăng độ dài, khó đọc, Base64 không che giấu dữ liệu |

Với **dữ liệu cá nhân** như email, số điện thoại hoặc tên người, ưu tiên một ID kỹ thuật ổn định thay vì nhúng trực tiếp vào key. Base64 chỉ là mã hóa biểu diễn có thể đảo ngược, **không phải mã hóa bảo mật**; dữ liệu nhạy cảm vẫn có thể bị khôi phục từ log hoặc URL.

### 5.1. Delimiter và Unicode có liên quan thế nào?

Giả sử dùng `::` làm delimiter nhưng một thành phần nghiệp vụ cũng chứa `::`:

```text
["course", "acme::school", "JAVA-101"]
["course", "acme", "school::JAVA-101"]
```

Nếu nối chuỗi trực tiếp, cả hai tạo ra:

```text
course::acme::school::JAVA-101
```

Đây là **va chạm do định dạng**, không phải do Unicode có bao nhiêu byte. Có thể giải bằng:

1. Chỉ cho phép định danh nội bộ thuộc bộ ký tự không chứa `:`.
2. Hoặc encode từng thành phần theo một phép ánh xạ một-một trước khi ghép.
3. Hoặc dùng một định dạng có độ dài tường minh cho từng thành phần và parser tương ứng.

Nếu dùng Base64 URL-safe *không padding* cho mỗi thành phần, kết quả chỉ dùng các ký tự chữ-số, `-`, `_`; sẽ không xuất hiện `:` bên trong thành phần đã mã hóa. Tuy nhiên, mọi thành phần phải được encode nhất quán và key hoàn chỉnh phải vượt qua kiểm tra byte.

## 6. Viết hàm kiểm tra UTF-8 nghiêm ngặt trong Java

Đối với các ID đã được kiểm soát là Unicode hợp lệ, phép đo thường dùng là:

```java
int bytes = key.getBytes(StandardCharsets.UTF_8).length;
```

Nhưng trong Java, `String` về mặt kỹ thuật có thể chứa **surrogate không tạo thành cặp hợp lệ**. `String.getBytes(StandardCharsets.UTF_8)` có thể thay thế dữ liệu lỗi trong quá trình encoding. Nếu cần một hợp đồng ID không âm thầm biến dữ liệu không hợp lệ thành cùng chuỗi byte, nên dùng `CharsetEncoder` ở chế độ **REPORT**:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class Utf8KeyLengths {
    public static final int MAX_DOCUMENT_KEY_BYTES = 250;

    private Utf8KeyLengths() {}

    public static byte[] encodeStrict(String value) {
        if (value == null) {
            throw new IllegalArgumentException("Document ID không được null");
        }

        try {
            ByteBuffer encoded = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(value));

            byte[] bytes = new byte[encoded.remaining()];
            encoded.get(bytes);
            return bytes;
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException(
                "Document ID chứa chuỗi Unicode không hợp lệ", ex);
        }
    }

    public static String requireValidDocumentKey(String key) {
        int bytes = encodeStrict(key).length;

        if (bytes == 0) {
            throw new IllegalArgumentException(
                "Document ID không được rỗng");
        }
        if (bytes > MAX_DOCUMENT_KEY_BYTES) {
            throw new IllegalArgumentException(
                "Document ID dài " + bytes + " byte, vượt giới hạn 250 byte");
        }
        return key;
    }
}
```

Lớp trên đo đúng **byte UTF-8** và chủ động báo lỗi nếu chuỗi không mã hóa hợp lệ. Đây là phần kiểm tra kỹ thuật; ứng dụng vẫn phải xác minh ý nghĩa nghiệp vụ, bộ ký tự được phép, quyền tenant, delimiter, dạng chuẩn hóa và khả năng định danh duy nhất.

Một document key bằng đúng **250 byte** là trường hợp nằm trong giới hạn; **251 byte** là không hợp lệ. Không tự giảm giới hạn về 250 *ký tự* và không cắt ID dài.

## 7. KeyFactory Unicode cho Spring Data Couchbase

Xây dựng một factory có hợp đồng rõ:

- `kind` cố định là `course`.
- `tenantId` là ID nội bộ ASCII đã chuẩn hóa và kiểm tra quyền trước khi gọi.
- `courseCode` có thể chứa tiếng Việt hoặc emoji và được ứng dụng quy định **NFC tương đương về nghiệp vụ**.
- Mỗi `courseCode` được chuyển thành UTF-8 nghiêm ngặt, rồi Base64 URL-safe **không padding** để tránh delimiter.
- Toàn bộ key được kiểm tra giới hạn byte sau khi ghép.

```java
import java.text.Normalizer;
import java.util.Base64;
import java.util.Objects;
import java.util.regex.Pattern;

public final class CourseDocumentKeys {
    private static final Pattern TENANT =
        Pattern.compile("[a-z0-9][a-z0-9-]{0,39}");

    private CourseDocumentKeys() {}

    public static String byCode(String authorizedTenantId,
                                String courseCode) {
        Objects.requireNonNull(authorizedTenantId, "tenantId");
        Objects.requireNonNull(courseCode, "courseCode");

        if (!TENANT.matcher(authorizedTenantId).matches()) {
            throw new IllegalArgumentException(
                "tenantId chưa chuẩn hóa hoặc không hợp lệ");
        }
        if (courseCode.isBlank()) {
            throw new IllegalArgumentException("courseCode không được rỗng");
        }
        if (courseCode.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException(
                "courseCode không được chứa ký tự điều khiển");
        }

        // Policy nghiệp vụ minh họa: dạng tương đương chuẩn dùng cùng mã.
        String canonical = Normalizer.normalize(
            courseCode, Normalizer.Form.NFC);

        byte[] payload = Utf8KeyLengths.encodeStrict(canonical);
        String safeComponent = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(payload);

        String documentId =
            "course::" + authorizedTenantId + "::" + safeComponent;

        return Utf8KeyLengths.requireValidDocumentKey(documentId);
    }
}
```

Các điều kiện ở đây **minh họa một chính sách cụ thể**. Không tự chuẩn hóa NFC mọi mã ngoài nếu hệ thống nguồn yêu cầu phân biệt chính xác chuỗi đầu vào. Nếu mã course có thể thay đổi, dùng UUID bất biến cho ID của course và giữ `courseCode` dưới dạng thuộc tính truy vấn.

Với cùng input sau canonicalization, factory luôn trả cùng chuỗi. Ví dụ:

```java
String first = CourseDocumentKeys.byCode("acme", "caf\u00E9");
String second = CourseDocumentKeys.byCode("acme", "cafe\u0301");

System.out.println(first.equals(second)); // true với policy NFC
System.out.println(first); // course::acme::Y2Fmw6k
```

**Vì sao cùng ID?** Ứng dụng đã **chủ động tuyên bố** hai dạng Unicode là cùng một mã nghiệp vụ bằng normalization NFC. Đây là một quyết định về định danh; trước khi sử dụng trên dữ liệu đã có, cần phát hiện liệu hai giá trị gốc từng được dùng cho **hai thực thể khác nhau** hay không.

### 7.1. Kiểm tra trước và sau mã hóa

Không nên chỉ đo:

```java
int rawBytes = Utf8KeyLengths.encodeStrict(courseCode).length;
```

vì prefix và Base64 có thể khiến ID cuối dài hơn. Trong `CourseDocumentKeys`, bước `requireValidDocumentKey(documentId)` nằm **sau** normalization, encoding và ghép tất cả thành phần. Đây là vị trí kiểm tra phù hợp.

Nếu nghiệp vụ dùng ID Unicode trực tiếp thay vì Base64, vẫn phải kiểm tra sau khi ghép delimiter; đồng thời từ chối/escape dấu phân cách để không có hai bộ thành phần tạo cùng key.

### 7.2. Dùng Unicode trực tiếp khi nào?

Nếu mã nghiệp vụ gồm tập ký tự nhỏ, đã chuẩn hóa và bị giới hạn chiều dài chặt chẽ, một key dễ đọc như `course::acme::lập-trình` có thể thuận tiện. Tuy nhiên, cần:

- Một danh sách ký tự được phép rõ ràng.
- Một policy NFC/NFD thống nhất nếu chọn chuẩn hóa.
- Quy tắc dấu phân cách không nhập nhằng.
- Kiểm tra byte sau khi thêm mọi prefix/suffix.
- Kế hoạch migration nếu sau này đổi policy.

Trong hệ thống có nhiều nguồn mã không kiểm soát được, cách dùng surrogate ID thường đơn giản hơn về lâu dài.

## 8. Ánh xạ entity và repository trong Spring Data Couchbase

Khi cần một bước encoding Unicode riêng, cách dễ kiểm soát là **cấp document ID tường minh** từ factory thay vì trông chờ `@GeneratedValue(USE_ATTRIBUTES)` tự áp dụng các bước normalization/Base64 của ứng dụng.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class CourseDocument {
    @Id
    private String id;

    private String tenantId;
    private String courseCode;
    private String normalizedCourseCode;
    private String displayName;

    @Version
    private Long version;

    protected CourseDocument() {}

    public CourseDocument(String id,
                          String tenantId,
                          String courseCode,
                          String normalizedCourseCode,
                          String displayName) {
        this.id = id;
        this.tenantId = tenantId;
        this.courseCode = courseCode;
        this.normalizedCourseCode = normalizedCourseCode;
        this.displayName = displayName;
    }

    public String getId() { return id; }
}
```

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CourseRepository
        extends CouchbaseRepository<CourseDocument, String> {
}
```

Một service có thể tạo khóa trước khi lưu:

```java
import java.text.Normalizer;
import java.util.Optional;

public final class CourseService {
    private final CourseRepository repository;

    public CourseService(CourseRepository repository) {
        this.repository = repository;
    }

    public CourseDocument prepareNewCourse(
            String authorizedTenantId,
            String courseCode,
            String displayName) {

        String key = CourseDocumentKeys.byCode(
            authorizedTenantId, courseCode);
        String canonical = Normalizer.normalize(
            courseCode, Normalizer.Form.NFC);

        return new CourseDocument(
            key, authorizedTenantId, courseCode, canonical, displayName);
    }

    public Optional<CourseDocument> findByCode(
            String authorizedTenantId,
            String courseCode) {

        String key = CourseDocumentKeys.byCode(
            authorizedTenantId, courseCode);
        return repository.findById(key);
    }
}
```

Đoạn service dùng `prepareNewCourse` để minh họa giai đoạn **xác định ID**. Khi thực sự tạo document, ứng dụng còn cần chọn ngữ nghĩa ghi phù hợp; `repository.save(...)` không nên bị mặc định coi là thao tác chống tạo trùng trong mọi tình huống.

Lưu ý `normalizedCourseCode` trong body có thể hỗ trợ tra cứu/report; khi xử lý ghi hoặc cập nhật cần đảm bảo nó được tính bằng **cùng policy NFC** với key. Nếu `courseCode` là giá trị định danh bất biến, không đổi nó trong body mà giữ key cũ. Nếu business cho phép đổi mã, chọn surrogate ID hoặc thiết kế migration.

### 8.1. Còn `@GeneratedValue(USE_ATTRIBUTES)` thì sao?

Spring Data Couchbase có thể ghép các field được đánh dấu `@IdPrefix`, `@IdAttribute` và `@IdSuffix` khi dùng `@GeneratedValue(strategy = GenerationStrategy.USE_ATTRIBUTES)`. Ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationStrategy.USE_ATTRIBUTES,
                delimiter = "::")
private String id;

@IdPrefix(order = 0)
private String kind = "course";

@IdAttribute(order = 0)
private String tenantId;

@IdAttribute(order = 1)
private String courseCode;
```

Cách này thích hợp khi policy key được biểu diễn đúng bằng các thành phần và delimiter của framework. **Không tự giả định** framework sẽ thực hiện cùng normalization Unicode, escaping hoặc Base64 URL-safe như factory riêng. Nếu đường ghi dùng annotation mà đường đọc dùng factory đã encode, cần integration test với phiên bản Spring Data Couchbase thực tế; tốt nhất chọn một hợp đồng duy nhất và kiểm thử đường ghi/đọc khớp nhau.

Dù dùng annotation, vẫn cần kiểm tra **kích thước ID cuối cùng theo UTF-8** trước khi đưa vào Couchbase. Đừng coi việc các field riêng lẻ ngắn là đủ.

## 9. Khi key quá dài: xử lý thế nào?

Nếu ID cuối vượt 250 byte, có một số lựa chọn:

| Lựa chọn | Khi nào nên dùng? | Lưu ý |
| --- | --- | --- |
| Giới hạn chiều dài dữ liệu đầu vào | Mã nghiệp vụ được phép ngắn theo hợp đồng | Giới hạn theo **byte sau toàn bộ encoding**, kiểm tra thông báo lỗi |
| Dùng UUID/surrogate ID | Tên hoặc mã bên ngoài có thể dài/biến động | Lưu mã bên ngoài trong body để truy vấn |
| Dùng token/digest ổn định | Cần dựng key xác định từ input dài | Chọn thuật toán, kích thước, namespace, xử lý va chạm và ràng buộc bảo mật |
| Thiết kế lại phần định danh | Prefix quá dài hoặc chứa thuộc tính không cần thiết | Không bỏ tenant/loại nếu làm mất tính duy nhất |

**Không cắt cụt** document key xuống 250 byte. Ví dụ hai tên đều bắt đầu bằng một chuỗi dài giống nhau nhưng khác ở cuối sẽ trở thành cùng key sau khi cắt.

Nếu dùng digest như SHA-256 rồi biểu diễn thành hex/Base64url, hãy nhớ:

- Digest là một **giá trị dẫn xuất**, không phải phép mã hóa có thể đảo ngược.
- Về lý thuyết vẫn có xác suất va chạm; thiết kế phải chọn kích thước đủ phù hợp và có cách phát hiện xung đột nghiệp vụ.
- Với email hoặc dữ liệu dễ đoán, hash không khóa **không bảo vệ bí mật**; có thể cần HMAC với khóa bí mật và chính sách quay vòng khóa rõ ràng.
- Phải giữ bản gốc/canonical code trong body để xác minh ID có thực sự thuộc cùng một thực thể.
- Đừng thay thuật toán/digest length tùy ý vì thay kết quả ID đồng nghĩa migration dữ liệu.

### 9.1. Tại sao không nên chỉ xử lý lỗi từ server?

Nếu request đi đến Couchbase rồi mới bị từ chối vì ID quá dài, việc phát hiện lỗi sẽ phụ thuộc vào SDK, log và luồng retry. Kiểm tra sớm tại tầng service giúp trả lỗi đầu vào có ý nghĩa, kiểm thử ranh giới dễ dàng và tránh lặp những thao tác không thể thành công.

Kiểm tra ở client/application không loại bỏ việc xử lý lỗi của SDK hoặc kiểm soát đồng thời khi ghi. Cả hai lớp đều có vai trò riêng.

## 10. Duy nhất theo byte, idempotency và ghi đồng thời

Cùng một khóa Unicode có thể bị xử lý thành nhiều document ID nếu hai đường code dùng policy khác nhau:

```text
Writer A: key từ "café" ở dạng NFC
Writer B: key từ "cafe\u0301" ở dạng NFD
```

Nếu chúng tạo ra hai key byte khác nhau, thao tác `insert` cho cả hai có thể đều thành công trong cùng collection. Điều này tạo **trùng lặp nghiệp vụ** dù không vi phạm tính duy nhất vật lý theo document ID.

Ngược lại, nếu hai input khác nhau bị canonicalization quá mức làm thành cùng key, chúng có thể **tranh chấp** một document ngoài dự kiến.

Các bước phòng tránh:

1. Xác định chính sách canonicalization theo nghĩa của định danh nghiệp vụ.
2. Tạo key bằng **một factory thống nhất** ở mọi đường đọc/ghi.
3. Kiểm tra cấu trúc, byte length và khả năng nhập nhằng trước khi gọi Couchbase.
4. Dùng `insert-if-absent` cho hành động tạo-mới khi không được phép ghi đè.
5. Khi gặp `DocumentExistsException`, phân biệt retry cùng yêu cầu với hai thực thể khác nhau tranh chấp cùng ID.

Ví dụ với Couchbase Java SDK:

```java
import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

public void createCourseIfAbsent(Collection collection,
                                 String authorizedTenantId,
                                 String courseCode) {
    String id = CourseDocumentKeys.byCode(
        authorizedTenantId, courseCode);

    JsonObject body = JsonObject.create()
        .put("tenantId", authorizedTenantId)
        .put("courseCode", courseCode);

    try {
        collection.insert(id, body);
    } catch (DocumentExistsException ex) {
        throw new IllegalStateException(
            "Khóa học với mã này đã tồn tại", ex);
    }
}
```

Đây là ví dụ **SDK độc lập** để minh họa `insert`. Khi ứng dụng trộn SDK với Spring Data, cần giữ body/metadata tương thích với mapping của repository; không mặc định JSON tối giản do SDK ghi có thể được ánh xạ hoàn chỉnh qua mọi cấu hình Spring Data.

Lưu ý thêm: nếu một request retry tạo một UUID **mới** mỗi lần, ID khác nhau có thể khiến hai lần `insert` đều thành công. Vì vậy, idempotency cần một ID hoặc requestId **ổn định qua retry**. Với document đang tồn tại, `@Version`/CAS bảo vệ cập nhật đồng thời trong các đường mapping phù hợp; nó không thay đổi quy tắc mã hóa ID. TTL khiến document có thể hết hạn và cùng ID được dùng lại sau đó.

## 11. SQL++ và chỉ mục cho tìm kiếm Unicode

Khi document key là UUID hoặc một token Base64url, API có thể không biết ID khi chỉ có tên/mã hiển thị. Hãy lưu thuộc tính tra cứu trong body rồi thiết kế index SQL++.

Giả sử ứng dụng cần tìm course theo mã đã chuẩn hóa NFC trong một tenant:

```sql
-- Bucket learning, scope academy, collection courses là ví dụ.
CREATE INDEX ix_course_tenant_normalized_code
ON `learning`.`academy`.`courses`(
    tenantId, normalizedCourseCode
);
```

```sql
SELECT META(c).id AS documentId,
       c.courseCode,
       c.displayName
FROM `learning`.`academy`.`courses` AS c
WHERE c.tenantId = $tenantId
  AND c.normalizedCourseCode = $normalizedCode;
```

Giá trị `$normalizedCode` phải được tạo theo **cùng policy canonicalization** dùng khi ghi và bind qua API query, không nối chuỗi SQL++ bằng input của người dùng.

SQL++ và chỉ mục phục vụ tìm kiếm, phân trang, sắp xếp. Chúng **không tự tạo ràng buộc unique theo mã nghiệp vụ**. Nếu phải bảo đảm một mã chỉ thuộc một course, cần mô hình ID/ghi có kiểm tra tồn tại hoặc một cơ chế giữ chỗ duy nhất được đồng bộ đúng.

Tương tự, key có prefix `course::acme::` không tạo API KV để quét tất cả course theo prefix. Truy vấn SQL++ cần trường body/index tương ứng, và mức scan consistency phải được lựa chọn nếu yêu cầu nhìn thấy ngay dữ liệu vừa ghi. Khi đã biết chính xác ID, KV `findById` thường là con đường đọc gọn hơn.

## 12. Thay đổi Unicode policy là thay hợp đồng ID

Một hệ thống ban đầu có thể lưu trực tiếp:

```text
course::acme::café
course::acme::cafe◌́
```

Sau đó nhóm phát triển quyết định **chuẩn hóa NFC và dùng Base64url**. Nếu chỉ đổi factory, các document cũ vẫn tồn tại theo key cũ; `findById` theo key mới sẽ không tìm thấy chúng.

Một quá trình migration cần:

1. Kiểm kê dữ liệu theo policy cũ, đặc biệt những mã khác byte nhưng trở thành tương đương sau normalization.
2. Quy định cách giải quyết hai document cũ có thể ánh xạ về **cùng key mới**; không tự ghi đè rồi mất dữ liệu.
3. Chọn thời điểm hoặc cách phối hợp writer/reader để tránh lưu dữ liệu dưới hai policy song song.
4. Tạo document key mới, di chuyển body và cập nhật các tham chiếu, cache, sự kiện, idempotency record.
5. Đảm bảo TTL/tuổi thọ document và ngữ nghĩa CAS/transaction phù hợp khi chuyển dữ liệu.
6. Xác minh đầy đủ các thao tác đọc mới trước khi xóa key cũ.
7. Giữ test vectors của policy cũ và mới trong thời gian hỗ trợ tương thích.

Nếu chỉ thay biểu diễn Unicode của một trường **hiển thị**, hãy giữ ID kỹ thuật ổn định và cập nhật body; không buộc đổi khóa mỗi lần tên học viên hoặc tên khóa học được sửa.

## 13. Kiểm thử ranh giới byte và Unicode

Nên có **unit test cho factory/encoding** và **integration test cho thao tác Spring Data/Couchbase**.

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class DocumentKeyUnicodeTest {

    @Test
    void acceptsExactly250Utf8Bytes() {
        String key = "\u00E9".repeat(125);
        assertEquals(250, key.getBytes(StandardCharsets.UTF_8).length);
        assertEquals(key, Utf8KeyLengths.requireValidDocumentKey(key));
    }

    @Test
    void rejects251OrMoreBytes() {
        String key = "a".repeat(251);
        assertThrows(IllegalArgumentException.class,
            () -> Utf8KeyLengths.requireValidDocumentKey(key));
    }

    @Test
    void countsEmojiAsFourBytes() {
        String prefix = "order::acme::";
        String emoji = "\uD83D\uDE00";
        assertEquals(249, (prefix + emoji.repeat(59))
            .getBytes(StandardCharsets.UTF_8).length);
        assertEquals(253, (prefix + emoji.repeat(60))
            .getBytes(StandardCharsets.UTF_8).length);
    }

    @Test
    void canonicalUnicodeFormsProduceSameKeyByPolicy() {
        assertEquals(
            CourseDocumentKeys.byCode("acme", "caf\u00E9"),
            CourseDocumentKeys.byCode("acme", "cafe\u0301"));
    }

    @Test
    void tenantSeparatesNamespaces() {
        assertNotEquals(
            CourseDocumentKeys.byCode("acme", "JAVA-101"),
            CourseDocumentKeys.byCode("globex", "JAVA-101"));
    }

    @Test
    void illegalTenantAndEmptyCourseCodeAreRejected() {
        assertThrows(IllegalArgumentException.class,
            () -> CourseDocumentKeys.byCode("acme::sales", "JAVA-101"));
        assertThrows(IllegalArgumentException.class,
            () -> CourseDocumentKeys.byCode("acme", "  "));
    }
}
```

Các unit test trên kiểm tra logic ứng dụng. Integration test bổ sung nên xác minh rằng key được Spring Data/Couchbase chấp nhận ở ranh giới đúng, trả lỗi khi vượt giới hạn, và document đọc lại bằng `findById` đúng collection.

### 13.1. Ma trận lỗi nên kiểm tra

| Đầu vào | Điều phải xác nhận |
| --- | --- |
| 250 byte UTF-8 | Được chấp nhận theo giới hạn |
| 251 byte UTF-8 | Bị từ chối trước khi lưu |
| 125 ký tự `é` dựng sẵn | Tương ứng 250 byte nếu không có prefix |
| 60 emoji `😀` sau `order::acme::` | Vượt giới hạn 250 byte |
| NFC/NFD tương đương | Cùng key **nếu policy chọn NFC** |
| Hai ID khác nhau sau canonicalization | Không vô tình trùng do bỏ dấu/lower-case |
| Thành phần chứa `::` | Không gây va chạm key ghép |
| Unicode lỗi/chuỗi surrogate không hợp lệ | Bị từ chối trong strict encoder |
| Dữ liệu chứa ký tự điều khiển | Bị từ chối theo policy |
| Base64url của dữ liệu rất dài | Kiểm tra kích thước **sau encoding** |
| Prefix hoặc tenant tăng độ dài | Tính vào tổng byte budget |
| Hai tenant cùng mã course | Hai key khác nhau |
| Đổi policy đang chạy | Có migration và giải quyết trùng khóa |

## 14. Bài tập tình huống: mã khóa học đa ngôn ngữ

Một nền tảng học trực tuyến cho phép quản trị viên đặt mã khóa học chứa tiếng Việt và emoji. Các tenant dùng chung collection `courses`. API tạo và tra cứu course theo `tenantId + courseCode`. Một course có thể đổi **tên hiển thị**, nhưng `courseCode` được quy định bất biến.

Yêu cầu:

1. Thiết kế key có namespace tenant.
2. Chỉ ra vì sao kiểm tra `courseCode.length() <= 200` chưa đủ.
3. Quy định chính sách khi courseCode ở dạng NFC hoặc NFD.
4. Đề xuất cách tránh va chạm nếu courseCode chứa delimiter.
5. Nêu thao tác ghi phù hợp khi hai request cùng tạo một course và cách xử lý khi code vượt 250 byte sau encoding.

**Gợi ý giải pháp:** dùng `CourseDocumentKeys.byCode(tenantId, courseCode)` với policy NFC, Base64url của UTF-8 và kiểm tra tổng độ dài. Nếu ID cuối quá dài, từ chối mã hoặc chuyển thiết kế sang surrogate ID và truy vấn bằng `normalizedCourseCode`. Dùng `insert-if-absent` để ngăn hai creator ghi đè; nếu có retry, phải nhận diện đúng yêu cầu đã xử lý. Tên hiển thị nằm trong body và thay đổi không làm đổi ID.

## 15. Checklist đưa vào production

1. Document ID được kiểm tra **theo UTF-8 byte**, không dùng riêng `String.length()`?
2. Tính đủ prefix, tenant, delimiter, suffix và **phần đã encoding** trước khi so với 250 byte?
3. Unicode policy (giữ nguyên, NFC, NFD hoặc khác) đã được quyết định **theo ý nghĩa nghiệp vụ**?
4. Policy được dùng chung cho create, read, update, delete, job và các service tích hợp?
5. Có kiểm soát đầu vào không hợp lệ, surrogate lỗi, ký tự điều khiển hoặc delimiter nhập nhằng?
6. Không xóa dấu, cắt key hay lower-case tùy tiện làm mất tính duy nhất?
7. Có giới hạn kích thước đầu vào sớm để tránh chi phí xử lý dữ liệu quá dài?
8. Nếu dùng Base64url, có hiểu đây không phải mã hóa bảo mật và có tính chi phí tăng byte?
9. Không đưa PII/bí mật hoặc trường dễ thay đổi vào key nếu có giải pháp định danh ổn định khác?
10. `@Id` và mọi key factory tạo đúng một hợp đồng; nếu dùng `@GeneratedValue` đã kiểm chứng kết quả và byte limit?
11. Repository/`CouchbaseTemplate`/SDK KV trỏ đúng collection?
12. Create có điều kiện tồn tại, update có CAS/`@Version` khi cần, retry có idempotency rõ ràng?
13. Nhu cầu tìm kiếm theo chuỗi Unicode có trường body và SQL++ index đúng với canonicalization?
14. Có test NFC/NFD, emoji, 250/251 byte, delimiter và policy migration?

## Kết luận

Trong Spring Data Couchbase, giới hạn document key **250 byte UTF-8** khiến việc thiết kế khóa Unicode cần chính xác ở cấp biểu diễn byte. `String.length()` của Java, số code point và số ký tự người dùng nhìn thấy không thể thay cho phép đo UTF-8. Hãy chọn policy Unicode rõ ràng, chuẩn hóa hoặc encode theo hợp đồng không nhập nhằng, kiểm tra **toàn bộ ID sau khi ghép**, và giữ định danh bất biến xuyên suốt vòng đời document. Sau đó mới kết hợp `@Id`, repository/`CouchbaseTemplate`, KV insert, CAS, TTL và SQL++/index để bảo đảm hệ thống truy cập dữ liệu đúng, nhất quán và có thể vận hành lâu dài.
