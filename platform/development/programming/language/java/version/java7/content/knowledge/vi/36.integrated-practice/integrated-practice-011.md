# Kiểm chứng văn bản Unicode, locale và kho ZIP bằng Java 17+

## 1. Mục tiêu thực hành

Một ứng dụng Java có thể đọc được tệp mà vẫn xử lý **sai nội dung**: chuỗi UTF-8 bị thay ký tự, hai chuỗi nhìn giống nhau nhưng không bằng nhau, số và ngày được định dạng theo locale khác, hoặc tên tệp trong ZIP bị hiểu nhầm, trùng sau chuẩn hóa hay chứa đường dẫn nguy hiểm. Bài thực hành này kết hợp ba nhóm kỹ thuật **Unicode, locale và ZIP** để kiểm chứng dữ liệu một cách có chủ đích.

Bạn sẽ xây dựng công cụ `UnicodeLocaleZipAudit.java`, chạy với **JDK 17+**, có các lệnh:

```text
java UnicodeLocaleZipAudit demo
java UnicodeLocaleZipAudit text <duong-dan-tep-UTF8>
java UnicodeLocaleZipAudit locale
java UnicodeLocaleZipAudit zip <duong-dan-tep-ZIP>
```

- **`demo`:** tạo tệp UTF-8 và ZIP mẫu trong thư mục tạm, kiểm tra normalization, giải mã, locale, CRC/size và dọn tệp tạm.
- **`text`:** kiểm tra UTF-8 nghiêm ngặt (không im lặng thay dữ liệu lỗi), thống kê số byte, `char` UTF-16 và code point, nhận biết BOM và trạng thái NFC.
- **`locale`:** chứng minh cùng một con số có cách hiển thị phụ thuộc `Locale`, kiểm tra round-trip parse/format, dùng `Collator` sắp xếp văn bản theo locale và làm rõ khác biệt của quy tắc chữ hoa.
- **`zip`:** duyệt các entry trong ZIP, kiểm tra tên entry, giới hạn tài nguyên, tự tính CRC-32 và byte đã giải nén, kiểm tra UTF-8 cho entry văn bản và phát hiện tên trùng sau chuẩn hóa NFC.

**Phạm vi và nguyên tắc:** đây là công cụ **audit/đọc**, không giải nén entry thành tệp trên ổ đĩa. Nó minh họa một profile kiểm chứng cụ thể, không thay thế antivirus, signature verification, kiểm toán ZIP toàn định dạng hoặc hệ thống giải nén an toàn ở production.

Các API được dùng gồm `java.nio.charset`, `java.text.Normalizer`, `java.text.Collator`, `java.util.Locale`, `java.util.zip` và `java.nio.file`. Chúng vẫn là Java SE API hiện hành; việc chủ đề nằm trong Java 7 chỉ nói đến nền tảng kiến thức, còn mã ở đây nhắm đến Java 17+.

## 2. Những điều phải phân biệt trước khi kiểm chứng

| Khái niệm | Ví dụ | Điều cần biết |
| --- | --- | --- |
| **Byte** | UTF-8 của `é` thường gồm 2 byte | Đơn vị của tệp, luồng và checksum |
| **UTF-16 code unit** (`char`) | Ký tự ngoài BMP dùng cặp surrogate (2 `char`) | `String.length()` đếm đơn vị UTF-16 |
| **Unicode code point** | `U+1F31F` (🌟) là một code point | `String.codePointCount(...)` không đếm ký tự hiển thị |
| **Grapheme cluster** | Một chữ cái + dấu kết hợp có thể là một cụm nhìn thấy | Không luôn trùng với một code point |
| **Encoding / charset** | `UTF-8`, `UTF-16` | Biến chuỗi thành byte và ngược lại |
| **Normalization** | `"café"` và `"cafe\u0301"` | Hai chuỗi có thể khác byte nhưng tương đương Unicode |
| **Locale** | `vi-VN`, `en-US`, `tr-TR` | Quy tắc định dạng, sắp xếp, chuyển chữ hoa/thường và biểu diễn địa phương |
| **ZIP entry name** | `docs/café.txt` | Tên entry có charset/UTF-8 flag, không được tự suy ra đường dẫn an toàn |
| **ZIP CRC-32** | CRC của byte giải nén | Phát hiện một số hỏng dữ liệu ngẫu nhiên, không chứng minh nguồn gốc |

**Ba lớp “bằng nhau” khác nhau:**

1. **Byte bằng nhau:** dữ liệu lưu trữ giống hệt ở cấp byte; hữu ích cho checksum, chữ ký, so sánh file.
2. **Chuỗi Unicode tương đương chuẩn tắc:** hai biểu diễn NFC/NFD có thể khác byte nhưng cùng một chuỗi chuẩn tắc khi normalize.
3. **So sánh theo ngôn ngữ (collation):** `Collator` có thể coi các dấu/chữ hoa khác nhau là tương đương ở một mức strength nhất định. Đây là quy tắc **so sánh phục vụ người dùng**, không phải thay thế so sánh byte hay identifier an toàn.

Vì vậy, câu “hai bản văn bản giống nhau” phải có **định nghĩa kiểm chứng**: bằng byte, bằng Unicode sau NFC, bằng sau chuyển đổi newline, hay bằng theo một locale/collation cụ thể?

## 3. UTF-8: đọc được không có nghĩa là đọc đúng

### 3.1. Luôn chọn charset tường minh

`Files.readString(path, StandardCharsets.UTF_8)` hoặc `InputStreamReader(stream, StandardCharsets.UTF_8)` là những lựa chọn thông dụng. Từ JDK 18 (JEP 400), UTF-8 là charset mặc định ở nhiều cấu hình Java SE chuẩn, nhưng code cần di chuyển qua Java 17, JDK tùy biến hoặc môi trường với thiết lập đặc biệt vẫn nên **chỉ định `StandardCharsets.UTF_8` rõ ràng**.

Với dữ liệu cần kiểm chứng, phải quyết định chính sách khi byte **không hợp lệ** theo UTF-8. `CharsetDecoder` và `CodingErrorAction` cho phép:

- `REPORT`: báo lỗi bằng `CharacterCodingException` cho malformed/unmappable input;
- `REPLACE`: thay bằng ký tự thay thế, dễ làm mất thông tin về nguồn lỗi;
- `IGNORE`: bỏ byte/chuỗi lỗi, có thể làm sai nội dung âm thầm.

Đối với audit, dùng **`REPORT` cho cả malformed và unmappable**. Ví dụ hai byte `C3 28` không tạo thành một chuỗi UTF-8 hợp lệ, nên chương trình phải từ chối thay vì biến thành nội dung trông có vẻ hợp lệ.

### 3.2. Vì sao không dùng `new String(bytes, UTF_8)` để xác thực?

`new String(byte[], Charset)` có thể thay byte lỗi bằng ký tự mặc định thay vì báo lỗi cho caller. Vì vậy dù phù hợp việc chuyển đổi thông thường, nó **không phải phép kiểm tra nghiêm ngặt** để kết luận đầu vào UTF-8 hợp lệ. Phải dùng `CharsetDecoder` cấu hình `REPORT` hoặc API có hợp đồng lỗi tương đương.

**Giới hạn bộ nhớ của ví dụ:** lệnh `text` giới hạn **1 MiB byte đầu vào** trước khi đọc và decode vào RAM. Với log lớn, triển khai decoder đọc luồng với buffer và xử lý cả chuỗi byte UTF-8 bị tách giữa hai chunk; không tăng giới hạn tùy tiện rồi gọi `readAllBytes()` trên dữ liệu không tin cậy.

## 4. Normalization: NFC và NFD không phải chỉnh sửa mỹ thuật

Unicode cho phép một số ký tự được biểu diễn theo nhiều cách:

```java
String precomposed = "caf\u00E9";
String decomposed  = "cafe\u0301";
System.out.println(precomposed.equals(decomposed)); // false
System.out.println(
        java.text.Normalizer.normalize(
                decomposed, java.text.Normalizer.Form.NFC)
                .equals(precomposed));             // true
```

Đây là **đoạn code minh họa trong một method**, không phải chương trình độc lập. Cả hai chuỗi có thể nhìn thành “café” trên màn hình nhưng có số code point, số UTF-16 unit và byte UTF-8 khác nhau.

Các dạng phổ biến:

| Dạng | Mục đích | Lưu ý |
| --- | --- | --- |
| **NFC** | Canonical composition, thường phù hợp lưu trữ/so sánh văn bản thông thường | Không tự động xóa dấu, không tự chuyển thành lowercase |
| **NFD** | Canonical decomposition | Có thể tạo nhiều code point cho một grapheme |
| **NFKC** | Compatibility composition | Có thể gộp ký tự tương thích có ý nghĩa biểu diễn khác nhau; **không dùng mù quáng** cho nội dung pháp lý, mật khẩu, tên riêng |
| **NFKD** | Compatibility decomposition | Tương tự, có thể mất khác biệt về cách biểu diễn |

Đối với tên file của ZIP, một chính sách hợp lý là **ghi nhận tên chưa NFC**, và từ chối **hai entry có tên trùng sau NFC** vì chúng có thể trở thành cùng một tên sau khi một hệ thống đích chuẩn hóa. Tuy nhiên **NFC không giải quyết mọi xung đột tên**: case sensitivity, Unicode case folding, ký tự cấm theo hệ điều hành, tên thiết bị Windows, dấu chấm cuối tên và symlink đều cần chính sách riêng nếu thực sự giải nén.

**Không nên tự normalize toàn bộ nội dung tải lên trước khi tính checksum.** CRC/SHA trên byte gốc và checksum của nội dung đã normalize là hai thứ khác nhau. Nếu nghiệp vụ cần so sánh văn bản chuẩn tắc, lưu rõ cả bản gốc và quy tắc chuẩn hóa.

## 5. Locale: định dạng và so sánh khác kiểm chứng byte

### 5.1. Thao tác với `Locale`

`Locale.forLanguageTag("vi-VN")` tạo locale theo BCP 47, không phụ thuộc vào locale mặc định của tiến trình. Các API quan trọng:

- `NumberFormat.getNumberInstance(locale)`: định dạng/parse số theo cách viết địa phương.
- `DateTimeFormatter.ofLocalizedDate(style).withLocale(locale)`: định dạng ngày theo dữ liệu locale; thời gian múi giờ phải được xử lý **riêng** qua `ZoneId` khi cần.
- `Collator.getInstance(locale)`: so sánh/sắp xếp theo ngôn ngữ. `Collator.PRIMARY`, `SECONDARY`, `TERTIARY` xác định mức khác biệt được xét.
- `String.toUpperCase(locale)` / `toLowerCase(locale)`: chuyển chữ hoa/thường theo ngôn ngữ. Trường hợp chữ “i” trong tiếng Thổ Nhĩ Kỳ khác quy tắc tiếng Anh.
- `Locale.ROOT`: locale không phụ thuộc ngôn ngữ cụ thể, hữu ích cho một số thao tác lập trình với protocol/cấu trúc, nhưng **không thay thế** Unicode case folding và quy tắc bảo mật identifier.

### 5.2. Không hard-code một chuỗi formatted duy nhất

Số `12345.5` có thể được hiển thị với dấu nhóm và dấu thập phân khác nhau tùy locale, các locale data provider, phiên bản CLDR/JDK và runtime image. Đặc biệt, một runtime nhỏ tạo bằng `jlink` có thể lược bỏ locale data. Vì vậy nên **kiểm tra round-trip theo chính formatter và parser** của cùng locale thay vì khẳng định một kết quả tiếng Việt cố định cho mọi JDK.

`NumberFormat.parse(...)` có thể chấp nhận một **tiền tố** mà bỏ phần đuôi không hợp lệ. Khi kiểm chứng toàn bộ input, sử dụng `ParsePosition` và yêu cầu `position.getIndex() == input.length()`. Với số tiền tệ và dữ liệu nghiệp vụ, thêm kiểm tra precision, rounding, currency và định dạng được chấp nhận; không dùng formatter locale làm parser duy nhất cho protocol dữ liệu máy.

### 5.3. Collation không phải danh tính dữ liệu

`Collator` phù hợp sắp xếp tên người dùng hay tiêu đề theo locale, nhưng không nên dùng một mức `PRIMARY` làm khóa duy nhất mặc định cho username hoặc xác minh chữ ký dữ liệu. Ở mức strength thấp, những chuỗi khác nhau có thể so sánh bằng nhau. Dữ liệu collation có thể thay đổi qua bản JDK/provider; muốn thứ tự tái lập chính xác giữa các hệ thống, lưu version/rule của thuật toán hoặc dùng một quy tắc so sánh đã chuẩn hóa độc lập.

## 6. ZIP: ba phần cần kiểm chứng

Một kho ZIP có nhiều entry với tên, metadata và byte nội dung. Việc “mở ZIP thành công” chỉ chứng minh một số cấu trúc có thể được đọc, chưa đủ để nói archive đáng tin.

### 6.1. Tên entry và đường dẫn

Tên ZIP thường dùng `/` làm dấu phân tách, **không phải một đường dẫn đã được JVM xác minh an toàn**. Các ví dụ nên từ chối trong profile audit này:

```text
../../secrets.txt
/absolute/secret.txt
C:/private/data.txt
docs\..\outside.txt
docs//data.txt
docs/./data.txt
docs/../data.txt
```

Mã sẽ không giải nén, nhưng vẫn kiểm tra các tên này trước khi công bố “PASS”. Kiểm tra normalize/`startsWith` là bước bổ sung khi **thực sự giải nén**, chưa đủ chống symlink race trong một thư mục đích do người khác sửa đồng thời.

### 6.2. Đọc byte rồi tự tính CRC-32 và size

`ZipFile` có thể liệt kê entry và mở `InputStream` của từng entry. Không nên mặc định rằng mọi đường code đọc entry bằng `ZipFile.getInputStream` **đã kiểm tra CRC cho bạn**. Profile này đọc **toàn bộ byte giải nén**, cập nhật `CRC32` và so sánh với `ZipEntry.getCrc()`; số byte đọc thật cũng được so sánh với `ZipEntry.getSize()`.

**CRC-32 phát hiện hỏng dữ liệu ngẫu nhiên, không xác thực người tạo.** Một bên độc hại có thể sửa dữ liệu đồng thời tính lại CRC. Nếu cần bằng chứng nguồn gốc/toàn vẹn chống sửa đổi, dùng manifest băm SHA-256 được ký, hoặc cơ chế chữ ký đã được kiểm chứng từ một kênh tin cậy.

### 6.3. Giới hạn tài nguyên và ZIP bomb

Để tránh archive nhỏ giải nén thành dữ liệu khổng lồ, chương trình minh họa đặt giới hạn:

| Hạn mức | Giá trị minh họa | Ý nghĩa |
| --- | ---: | --- |
| Số entry | 10.000 | Tránh duyệt vô hạn lượng mục rất lớn |
| Byte giải nén của một entry | 32 MiB | Không một entry nào được ăn quá quota |
| Tổng byte giải nén mọi entry | 64 MiB | Chặn tổng dung lượng uncompressed quá lớn |
| Tệp ZIP đầu vào | 64 MiB | Tránh mở archive quá lớn trong bài thực hành |
| Entry văn bản `.txt`/`.csv`/`.json` | 1 MiB mỗi entry | Giới hạn phần text phải decode vào RAM |

Các giá trị trên **không phải giới hạn mặc định của Java** và không thay cho việc đặt hạn mức theo nghiệp vụ thật. Mã kiểm tra **byte thực tế trong vòng lặp đọc**, ngoài việc kiểm tra metadata đã khai báo. Nếu một hệ thống xử lý ZIP lồng nhiều tầng, phải áp dụng **ngân sách tích lũy xuyên các tầng** và giới hạn CPU/thời gian; chương trình bên dưới không mở tiếp ZIP con.

**ZIP64** cho phép biểu diễn kích thước/số entry lớn hơn ZIP cổ điển khi runtime hỗ trợ; nó **không** loại bỏ rủi ro ZIP bomb hay ngân sách bộ nhớ/đĩa. API `java.util.zip` hiện hành mô tả khả năng ZIP64 là tùy chọn theo implementation. Trên runtime cụ thể, cần kiểm tra tương thích với archive đối tác.

## 7. Mã Java 17+ hoàn chỉnh: `UnicodeLocaleZipAudit.java`

Lưu toàn bộ mã dưới đây thành **`UnicodeLocaleZipAudit.java`**, dùng `javac -encoding UTF-8`. Công cụ có `main` độc lập, không cần thư viện bên ngoài Java SE. Các số giới hạn minh họa được đặt ở đầu class để dễ tìm và thay đổi khi có yêu cầu nghiệp vụ.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Collator;
import java.text.Normalizer;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public final class UnicodeLocaleZipAudit {
    private static final int MAX_TEXT_BYTES = 1 * 1024 * 1024;
    private static final long MAX_ZIP_BYTES = 64L * 1024 * 1024;
    private static final long MAX_ENTRY_BYTES = 32L * 1024 * 1024;
    private static final long MAX_TOTAL_BYTES = 64L * 1024 * 1024;
    private static final int MAX_ENTRIES = 10_000;

    private UnicodeLocaleZipAudit() { }

    private record TextReport(
            int bytes, int utf16Units, int codePoints,
            boolean normalizedNfc, boolean hasBom) { }

    private record ZipReport(
            int entries, int textEntries, long uncompressedBytes,
            int nonNfcNames, int nonNfcTextEntries) { }

    public static void main(String[] args) {
        try {
            if (args.length == 0) {
                demo();
                return;
            }
            switch (args[0]) {
                case "demo" -> {
                    requireCount(args, 1);
                    demo();
                }
                case "text" -> {
                    requireCount(args, 2);
                    TextReport r = inspectText(Path.of(args[1]));
                    printTextReport(r);
                }
                case "locale" -> {
                    requireCount(args, 1);
                    localeReport();
                }
                case "zip" -> {
                    requireCount(args, 2);
                    printZipReport(inspectZip(Path.of(args[1])));
                }
                default -> throw new IllegalArgumentException(
                        "Unknown command: " + args[0]);
            }
        } catch (IOException | IllegalArgumentException ex) {
            System.err.println("Error: " + ex.getMessage());
            System.exit(1);
        }
    }

    private static void requireCount(String[] args, int expected) {
        if (args.length != expected) {
            throw new IllegalArgumentException(
                    "Expected " + (expected - 1)
                    + " argument(s) after " + args[0]);
        }
    }

    private static String decodeStrictUtf8(byte[] input)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(input))
                .toString();
    }

    private static TextReport analyzeText(byte[] bytes)
            throws CharacterCodingException {
        String text = decodeStrictUtf8(bytes);
        return new TextReport(
                bytes.length,
                text.length(),
                text.codePointCount(0, text.length()),
                Normalizer.isNormalized(text, Normalizer.Form.NFC),
                text.startsWith("\uFEFF"));
    }

    private static byte[] readBoundedText(Path path)
            throws IOException {
        try (InputStream input = Files.newInputStream(path)) {
            // Chi doc toi da 1 MiB + 1 byte de phat hien vuot quota.
            byte[] data = input.readNBytes(MAX_TEXT_BYTES + 1);
            if (data.length > MAX_TEXT_BYTES) {
                throw new IOException(
                        "Text exceeds 1 MiB audit limit: " + path);
            }
            return data;
        }
    }

    private static TextReport inspectText(Path path)
            throws IOException {
        return analyzeText(readBoundedText(path));
    }

    private static void printTextReport(TextReport r) {
        System.out.println("UTF-8 valid: true");
        System.out.println("Bytes: " + r.bytes());
        System.out.println("UTF-16 units: " + r.utf16Units());
        System.out.println("Code points: " + r.codePoints());
        System.out.println("NFC: " + r.normalizedNfc());
        System.out.println("UTF-8 BOM: " + r.hasBom());
    }

    private static Locale vietnamese() {
        return Locale.forLanguageTag("vi-VN");
    }

    private static boolean localeNumberRoundtrip() {
        NumberFormat format =
                NumberFormat.getNumberInstance(vietnamese());
        String rendered = format.format(12345.5);
        ParsePosition pos = new ParsePosition(0);
        Number parsed = format.parse(rendered, pos);
        return parsed != null
                && pos.getIndex() == rendered.length()
                && parsed.doubleValue() == 12345.5;
    }

    private static void localeReport() {
        Locale vi = vietnamese();
        NumberFormat format = NumberFormat.getNumberInstance(vi);
        String shown = format.format(12345.5);

        Collator collator = Collator.getInstance(vi);
        List<String> names = new ArrayList<>(
                List.of("Hoa", "Hòa", "Hà", "Anh"));
        names.sort(collator);

        Locale turkish = Locale.forLanguageTag("tr-TR");
        System.out.println("Locale: " + vi.toLanguageTag());
        System.out.println("Number formatted: " + shown);
        System.out.println(
                "Number full roundtrip: " + localeNumberRoundtrip());
        System.out.println(
                "Collator order: " + String.join(" | ", names));
        System.out.println(
                "Turkish dotted I: "
                + "\u0130".equals("i".toUpperCase(turkish)));
    }

    private static boolean isTextEntry(String name) {
        String lower = name.toLowerCase(Locale.ROOT);
        return lower.endsWith(".txt")
                || lower.endsWith(".csv")
                || lower.endsWith(".json");
    }

    private static void checkZipName(String name)
            throws IOException {
        if (name.isEmpty() || name.startsWith("/")
                || name.indexOf('\\') >= 0
                || name.indexOf('\0') >= 0
                || name.matches("^[A-Za-z]:.*")
                || name.codePoints().anyMatch(Character::isISOControl)) {
            throw new IOException(
                    "Unsafe ZIP entry name: " + name);
        }

        String core = name.endsWith("/")
                ? name.substring(0, name.length() - 1)
                : name;
        if (core.isEmpty()) {
            throw new IOException("ZIP entry has empty path");
        }

        // split(..., -1) giu ca phan rong o giua.
        for (String segment : core.split("/", -1)) {
            if (segment.isEmpty()
                    || segment.equals(".")
                    || segment.equals("..")) {
                throw new IOException(
                        "Unsafe ZIP path segment in: " + name);
            }
        }
    }

    private static ZipReport inspectZip(Path path)
            throws IOException {
        if (Files.size(path) > MAX_ZIP_BYTES) {
            throw new IOException("ZIP exceeds 64 MiB limit");
        }

        int entries = 0;
        int textEntries = 0;
        int nonNfcNames = 0;
        int nonNfcTexts = 0;
        long totalBytes = 0;
        Set<String> canonicalNames = new HashSet<>();
        byte[] buffer = new byte[8192];

        try (ZipFile zip =
                     new ZipFile(path.toFile(), StandardCharsets.UTF_8)) {
            Enumeration<? extends ZipEntry> iterator = zip.entries();

            while (iterator.hasMoreElements()) {
                ZipEntry entry = iterator.nextElement();
                if (++entries > MAX_ENTRIES) {
                    throw new IOException("Too many ZIP entries");
                }

                String name = entry.getName();
                checkZipName(name);

                String nfcName = Normalizer.normalize(
                        name, Normalizer.Form.NFC);
                if (!canonicalNames.add(nfcName)) {
                    throw new IOException(
                            "Duplicate NFC ZIP path: " + name);
                }
                if (!name.equals(nfcName)) {
                    nonNfcNames++;
                }

                if (entry.isDirectory()) {
                    if (entry.getSize() > 0) {
                        throw new IOException(
                                "Directory entry contains data: " + name);
                    }
                    continue;
                }

                if (entry.getSize() < 0
                        || entry.getCrc() < 0) {
                    throw new IOException(
                            "Missing ZIP size or CRC: " + name);
                }
                if (entry.getSize() > MAX_ENTRY_BYTES) {
                    throw new IOException(
                            "Declared entry too large: " + name);
                }

                boolean textFile = isTextEntry(name);
                if (textFile && entry.getSize() > MAX_TEXT_BYTES) {
                    throw new IOException(
                            "ZIP text entry exceeds 1 MiB: " + name);
                }

                ByteArrayOutputStream textBuffer =
                        textFile ? new ByteArrayOutputStream() : null;
                CRC32 crc = new CRC32();
                long entryBytes = 0;

                InputStream raw = zip.getInputStream(entry);
                if (raw == null) {
                    throw new IOException(
                            "Cannot read ZIP entry: " + name);
                }

                try (raw) {
                    int n;
                    while ((n = raw.read(buffer)) != -1) {
                        if (n == 0) {
                            continue;
                        }
                        if (n > MAX_ENTRY_BYTES - entryBytes
                                || n > MAX_TOTAL_BYTES - totalBytes) {
                            throw new IOException(
                                    "Decompressed size limit: " + name);
                        }

                        entryBytes += n;
                        totalBytes += n;
                        crc.update(buffer, 0, n);

                        if (textBuffer != null) {
                            if (n > MAX_TEXT_BYTES - textBuffer.size()) {
                                throw new IOException(
                                        "Text size limit: " + name);
                            }
                            textBuffer.write(buffer, 0, n);
                        }
                    }
                }

                if (entryBytes != entry.getSize()) {
                    throw new IOException(
                            "Uncompressed size mismatch: " + name);
                }
                if (crc.getValue() != entry.getCrc()) {
                    throw new IOException(
                            "CRC-32 mismatch: " + name);
                }

                if (textBuffer != null) {
                    textEntries++;
                    TextReport text =
                            analyzeText(textBuffer.toByteArray());
                    if (!text.normalizedNfc()) {
                        nonNfcTexts++;
                    }
                }
            }
        }

        return new ZipReport(
                entries, textEntries, totalBytes,
                nonNfcNames, nonNfcTexts);
    }

    private static void printZipReport(ZipReport r) {
        System.out.println("ZIP entries: " + r.entries());
        System.out.println(
                "UTF-8 text entries verified: " + r.textEntries());
        System.out.println(
                "Uncompressed bytes verified: " + r.uncompressedBytes());
        System.out.println(
                "Non-NFC names: " + r.nonNfcNames());
        System.out.println(
                "Non-NFC text entries: " + r.nonNfcTextEntries());
        System.out.println("ZIP CRC/size: PASS");
    }

    private static void demo() throws IOException {
        String sample = "Xin chào, café 🌟\n";
        Path text = Files.createTempFile(
                "unicode-locale-zip-", ".txt");
        Path archive = Files.createTempFile(
                "unicode-locale-zip-", ".zip");

        try {
            Files.writeString(
                    text, sample, StandardCharsets.UTF_8);

            try (ZipOutputStream output = new ZipOutputStream(
                    Files.newOutputStream(archive),
                    StandardCharsets.UTF_8)) {
                ZipEntry entry =
                        new ZipEntry("docs/café.txt");
                output.putNextEntry(entry);
                output.write(
                        sample.getBytes(StandardCharsets.UTF_8));
                output.closeEntry();
            }

            TextReport report = inspectText(text);
            ZipReport zipReport = inspectZip(archive);

            System.out.println("Strict UTF-8: PASS");
            System.out.println(
                    "Sample NFC: " + report.normalizedNfc());
            System.out.println(
                    "Canonical equivalent after NFC: "
                    + Normalizer.normalize(
                            "cafe\u0301", Normalizer.Form.NFC)
                            .equals("café"));

            boolean malformedRejected;
            try {
                decodeStrictUtf8(
                        new byte[] {(byte) 0xC3, (byte) 0x28});
                malformedRejected = false;
            } catch (CharacterCodingException expected) {
                malformedRejected = true;
            }
            System.out.println(
                    "Malformed UTF-8 rejected: "
                    + malformedRejected);
            System.out.println(
                    "Locale number roundtrip: "
                    + localeNumberRoundtrip());
            System.out.println(
                    "ZIP entries: " + zipReport.entries());
            System.out.println(
                    "ZIP UTF-8 text entries: "
                    + zipReport.textEntries());
            System.out.println("ZIP CRC/size: PASS");
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(text);
        }
    }
}
```

### Biên dịch

Trong thư mục chứa mã:

```bash
javac -encoding UTF-8 UnicodeLocaleZipAudit.java
```

Chạy bài kiểm tra nội bộ, không cần chuẩn bị tệp mẫu:

```bash
java UnicodeLocaleZipAudit demo
```

**Stdout dự kiến chính xác khi chạy thành công trên JDK 17+ đầy đủ Java SE:**

```text
Strict UTF-8: PASS
Sample NFC: true
Canonical equivalent after NFC: true
Malformed UTF-8 rejected: true
Locale number roundtrip: true
ZIP entries: 1
ZIP UTF-8 text entries: 1
ZIP CRC/size: PASS
```

Chương trình tạo một tệp UTF-8 và một ZIP trong thư mục temp của hệ điều hành; `finally` cố gắng xóa chúng sau khi kiểm tra. Nếu môi trường không cho phép tạo tệp tạm, không có quyền đọc/ghi hoặc gặp lỗi I/O, chương trình báo lỗi, và không in đầy đủ output thành công ở trên. Một số lỗi giải phóng tệp tạm cũng có thể làm chương trình báo lỗi.

### Kiểm tra văn bản từ tệp thực tế

```bash
java UnicodeLocaleZipAudit text "data/ban-ghi.txt"
```

**Định dạng output**, các số bên dưới phụ thuộc nội dung tệp:

```text
UTF-8 valid: true
Bytes: <so-byte>
UTF-16 units: <so-don-vi>
Code points: <so-code-point>
NFC: <true-hoac-false>
UTF-8 BOM: <true-hoac-false>
```

Đây là **mẫu định dạng output**, không phải stdout cố định. Khi UTF-8 sai, code ném `CharacterCodingException` (được `main` bắt như `IOException`), thông báo `Error: ...` trên stderr và exit code 1. `NFC: false` là **thông tin phát hiện**, không phải tự động từ chối tệp hợp lệ UTF-8; chuẩn hóa hay giữ nguyên là quyết định nghiệp vụ.

### Xem tác động của locale

```bash
java UnicodeLocaleZipAudit locale
```

Output có các dòng `Locale: vi-VN`, `Number formatted: ...`, `Number full roundtrip: ...`, `Collator order: ...` và `Turkish dotted I: true`. **Không hard-code** chuỗi định dạng số hay thứ tự tên ở đây vì chúng phụ thuộc quy tắc/dữ liệu locale của runtime. Chương trình dùng chính formatter/parser của cùng locale và kiểm tra parser đã tiêu thụ **toàn bộ** chuỗi số.

`Collator` được khởi tạo riêng cho lệnh locale, không dùng chung trên nhiều thread. Nếu cần sắp xếp nhiều thread, tạo `Collator` theo từng tác vụ hoặc đồng bộ phù hợp; không giả định instance của nó thread-safe.

### Kiểm tra ZIP đã có

```bash
java UnicodeLocaleZipAudit zip "archives/tai-lieu.zip"
```

Với ZIP hợp lệ trong hạn mức, chương trình in số entry, số entry text UTF-8 đã decode, tổng byte uncompressed đã kiểm, số tên chưa NFC, số nội dung chưa NFC và `ZIP CRC/size: PASS`. Tệp đã mã hóa, entry có phương pháp nén không được `java.util.zip` hỗ trợ hoặc tên không dùng charset tương thích có thể bị từ chối; đó là giới hạn/điều kiện kiểm tra, không chứng minh archive là mã độc.

## 8. Giải thích chi tiết các kiểm chứng trong mã

### 8.1. Giới hạn bộ nhớ khi đọc UTF-8

`readBoundedText` gọi `readNBytes(MAX_TEXT_BYTES + 1)` nên phát hiện vượt hạn mức mà **không tự đọc cả file vào heap**. Phần text sau khi giới hạn có kích thước đủ nhỏ để decode một lần. `decodeStrictUtf8` nhận `byte[]` và trả `String`, dùng `REPORT`. Nếu byte bị lỗi, báo exception thay vì trả nội dung được thay ký tự.

`TextReport.bytes` là kích thước **byte UTF-8 thực tế đã đọc**. `utf16Units` là `String.length()` và `codePoints` là `codePointCount(0, text.length())`. Với emoji ngoài BMP, `utf16Units > codePoints` là điều bình thường. Khi có dấu kết hợp, **số code points vẫn không phải số ký tự người dùng nhìn thấy**.

Mã chỉ **phát hiện BOM** `U+FEFF` đầu chuỗi. Nó không tự loại bỏ BOM; việc bỏ đi một ký tự đầu nội dung có thể làm thay đổi checksum/byte gốc. Nếu hệ thống cần chấp nhận hoặc từ chối BOM, hãy đặt quy định rõ ràng và kiểm tra trước khi xử lý nghiệp vụ.

### 8.2. Kiểm chứng parser của locale theo toàn bộ input

`localeNumberRoundtrip` sử dụng `NumberFormat.format(12345.5)` rồi `parse` với `ParsePosition`, kiểm tra parser đã đi đến cuối chuỗi. Điều này tốt hơn việc chỉ gọi `parse` và tin kết quả nếu vẫn còn ký tự thừa.

Ví dụ, một API nhận “tổng tiền” phải thêm kiểm tra chính xác decimal, đơn vị tiền tệ và số chữ số thập phân. `NumberFormat` tiện cho **hiển thị và nhập liệu địa phương**, nhưng số tiền nên dùng `BigDecimal` với quy định scale/rounding. Với JSON, CSV máy đọc hoặc chữ ký số, ưu tiên định dạng dữ liệu **bất biến theo locale**.

### 8.3. Vì sao tên ZIP được kiểm tra riêng?

`checkZipName` từ chối tên rỗng, tên tuyệt đối kiểu `/root/...` hoặc `C:/...`, backslash, path segment rỗng, `.`, `..` và control characters. Đó là **một profile chặt cho tài liệu nhận từ bên ngoài**, không có nghĩa ZIP specification cấm mọi trường hợp này hoặc mọi hệ điều hành có chung tên hợp lệ.

`Normalizer.normalize(name, NFC)` được áp dụng cho **khóa phát hiện tên trùng**, không sửa tên thật của archive. Một ZIP có `docs/café.txt` và `docs/cafe\u0301.txt` sẽ bị từ chối vì hai tên có thể quy về một khi hệ thống đích chuẩn hóa. Nhưng ZIP có một tên chưa NFC vẫn được chấp nhận và **được đếm để cảnh báo**.

**Điều cần bổ sung nếu sẽ giải nén:** case-insensitive collision, file-vs-directory collision, reserved names trên Windows, symlink trong thư mục đích và kiểm tra containment sau khi resolve. Không dùng một hàm kiểm tra tên đơn giản làm hàng rào bảo mật duy nhất.

### 8.4. Vì sao tự đọc toàn bộ entry để kiểm CRC?

Mã dùng `ZipFile` mở archive và duyệt central directory. Với mỗi file entry, nó:

1. Xác định size/CRC đã khai báo và loại bỏ entry vượt hạn mức;
2. Đọc `InputStream` thành các block 8 KiB;
3. Kiểm tra số byte **thực tế** của entry và tổng archive;
4. Cập nhật `CRC32` trên các byte đã giải nén;
5. So sánh số byte và CRC thực với metadata `ZipEntry`;
6. Nếu tên có `.txt`, `.csv` hoặc `.json` thì giải mã nghiêm ngặt UTF-8 với hạn mức 1 MiB và ghi nhận trạng thái NFC.

Vì vậy kết quả “PASS” nói rằng **những entry được đọc đã vượt qua các phép kiểm tra được cài đặt**. Nó không xác thực người gửi, không phát hiện mọi cấu trúc ZIP cố ý gây lỗi và không chứng minh rằng dữ liệu nghiệp vụ bên trong file đúng schema (JSON có thể là UTF-8 hợp lệ nhưng sai JSON).

### 8.5. Vì sao không giải nén ra file?

Đọc entry trong memory có giới hạn cho phép kiểm tra byte/CRC mà **chưa tạo ra đường dẫn trên đĩa**. Nếu giải nén, tên entry phải được chuyển thành đường dẫn đích, lúc đó mới phát sinh các rủi ro như ZIP Slip và symlink traversal. Công cụ audit hiện tại chỉ nhận diện tên có khả năng nguy hiểm; phần triển khai extraction cần security design riêng.

### 8.6. Bản ghi thư mục và entry đặc biệt

Mã tính `entries` cho cả file và directory. Với directory entry, nó kiểm tra size không lớn hơn 0 và không tính byte nội dung. Không có giả định rằng mọi thư mục phải có directory entry riêng: nhiều ZIP hợp lệ chỉ chứa `docs/file.txt` và không tạo `docs/` như một mục riêng. Vì thế **số entry ZIP khác số file + số thư mục vật lý sau khi giải nén**.

Không được suy ra filesystem permissions, ACL, symbolic link hoặc executable bit chỉ từ `ZipEntry.isDirectory()`. Một số thuộc tính ngoài `java.util.zip` cơ bản cần thư viện/file format support khác; nếu nghiệp vụ đòi giữ quyền, dùng công cụ/format thích hợp và kiểm thử hệ điều hành đích.

## 9. Mở rộng kiểm tra Unicode trong nội dung

### 9.1. Kiểm tra newline có chủ đích

Một tài liệu có thể dùng `LF` (`\n`), `CRLF` (`\r\n`) hoặc `CR` (`\r`). Unicode NFC **không chuẩn hóa newline**. Hai tệp chứa cùng chữ nhưng khác kiểu xuống dòng có SHA-256 và CRC khác nhau.

Nếu yêu cầu so sánh nội dung “tương đương về dòng”, hãy:

1. decode UTF-8 nghiêm ngặt;
2. quyết định chấp nhận LF, CRLF hay cả hai;
3. chuẩn hóa newline **cho phép so sánh**, không ghi đè bản gốc nếu chưa được yêu cầu;
4. cân nhắc trailing newline và dòng rỗng cuối cùng;
5. tính hash của **byte gốc** riêng nếu cần xác minh toàn vẹn.

Không gọi `trim()` hoặc `strip()` lên toàn bộ văn bản để “chuẩn hóa” nếu không có hợp đồng: chúng có thể làm mất khoảng trắng có ý nghĩa trong CSV, YAML, Markdown, chữ ký hoặc code.

### 9.2. Nhận diện ký tự trông giống nhau (confusables)

Chữ cái Latin và chữ cái từ một hệ chữ khác có thể trông gần giống (ví dụ ký tự Latin `a` và một ký tự Cyrillic tương tự). NFC **không tự ngăn homograph attack** và `Collator` không phải API kiểm tra identifier bảo mật.

Với username, tên domain hoặc định danh từ dữ liệu không tin cậy, cần quy tắc whitelist/script restriction, kiểm tra Unicode security profile và cơ chế chống tên trùng phù hợp. Không dùng một phép `toLowerCase(Locale.ROOT)` đơn lẻ rồi coi định danh đã an toàn.

### 9.3. Code point vẫn chưa bằng “ký tự nhìn thấy”

`String.length()` đếm UTF-16 code unit. `String.codePointCount` đếm Unicode code point. Một emoji có biến thể màu da, một cụm emoji có Zero Width Joiner hoặc một ký tự có nhiều dấu có thể gồm nhiều code point nhưng hiển thị như một grapheme cluster.

Java có `BreakIterator.getCharacterInstance(locale)` để duyệt ranh giới ký tự theo dữ liệu/thuật toán của runtime. Dù vậy, **khả năng phân cụm emoji phức tạp** phụ thuộc bản JDK và Unicode version; nếu nghiệp vụ thật sự cần đúng extended grapheme clusters của một phiên bản Unicode cụ thể, kiểm tra khả năng thư viện và bộ dữ liệu Unicode tương ứng. Không lấy `String.length` làm số ký tự hiển thị cho giới hạn UI.

## 10. Kiểm chứng dữ liệu ZIP: CRC, SHA và chữ ký

| Cơ chế | Phát hiện lỗi do truyền/lưu | Chống sửa đổi có chủ đích | Khi dùng |
| --- | --- | --- | --- |
| **CRC-32 của ZIP** | Có ích với hỏng dữ liệu ngẫu nhiên | **Không** | Kiểm tính nhất quán entry với metadata ZIP |
| **SHA-256 do cùng bên gửi đính kèm trong ZIP** | Có thể | **Không** nếu attacker sửa cả ZIP và manifest | Đối chiếu nội dung, phân phối file có kênh tin cậy riêng |
| **SHA-256 từ kênh tin cậy độc lập** | Có | Có khả năng phát hiện sửa đổi so với giá trị tin cậy | Xác thực nội dung khi hash được cung cấp an toàn |
| **Chữ ký số được xác minh bằng khóa tin cậy** | Có | Có, theo mô hình tin cậy/chữ ký | Gói cập nhật, phát hành, dữ liệu nhạy cảm |

Muốn kiểm SHA-256 cho entry khi đang đọc, có thể cập nhật `MessageDigest` trong cùng vòng lặp với `CRC32`. Nhưng **đừng chỉ in một digest** rồi coi là “validated”: phải có **digest kỳ vọng từ nguồn tin cậy** và so sánh. Khi đó thông báo nên phân biệt rõ “checksum computed”, “checksum matched” và “signature verified”.

## 11. Tình huống kiểm thử bắt buộc trước khi dùng thật

| Fixture / input | Kết quả kỳ vọng | Ý nghĩa |
| --- | --- | --- |
| UTF-8 có tiếng Việt và emoji | `UTF-8 valid: true`; code unit/code point có thể khác | Giải mã và đếm đúng cấp biểu diễn |
| `"café"` so với `"cafe\u0301"` | `equals` false trước normalize; tương đương sau NFC | Kiểm chứng canonical equivalence |
| Dãy byte `C3 28` | Giải mã nghiêm ngặt **thất bại** | Không âm thầm thay byte lỗi |
| File có UTF-8 BOM | `UTF-8 BOM: true` | Phát hiện dấu BOM mà không xóa dữ liệu |
| File lớn hơn 1 MiB | Lệnh `text` báo lỗi limit | Bộ nhớ audit có giới hạn |
| Thay locale từ `vi-VN` sang `en-US` | Hiển thị số có thể đổi, round-trip cần vẫn đúng | Tách dữ liệu máy với hiển thị locale |
| Sắp xếp tên có dấu bằng `Collator` | Thứ tự do locale/JDK quy định | Không dùng thứ tự từ một JVM làm quy luật tuyệt đối |
| ZIP nhỏ chứa một file UTF-8 | CRC/size và text audit PASS | Chuỗi kiểm tra tích hợp |
| ZIP có tên `../bad.txt` | Báo lỗi tên nguy hiểm | Chặn đầu vào có dấu hiệu traversal |
| ZIP chứa tên trùng sau NFC | Báo lỗi duplicate NFC path | Ngăn xung đột chuẩn hóa |
| ZIP có entry text UTF-8 sai | Ném lỗi decode | Nội dung archive không được coi là văn bản UTF-8 hợp lệ |
| ZIP khai báo size nhỏ nhưng khi đọc vượt quota | Báo lỗi quota theo byte thực | Không chỉ tin metadata |
| ZIP bị cắt giữa chừng | Có thể lỗi mở ZIP/đọc entry | Phát hiện một phần archive không hợp lệ |
| ZIP có CRC không khớp | Báo lỗi CRC | Kiểm tra nội dung trên những entry đã đọc |
| ZIP có nhiều mục/hàm nén chưa hỗ trợ | Báo lỗi limit/format | Không tự suy luận hỗ trợ mọi ZIP extension |

Để có phép kiểm thử lặp lại, nên lưu các fixture nhỏ trong bộ test và ghi rõ JDK/version, filesystem, locale data, charset, cùng expected output. Tạo ZIP hỏng để test chỉ trong môi trường kiểm thử; không dùng file có dữ liệu nghiệp vụ thật để cố ý làm hỏng.

## 12. Lỗi thường gặp và cách tránh

1. **Nhầm `String.length()` là số ký tự người dùng nhìn thấy.** Đó là số UTF-16 code units; dùng code point hoặc grapheme segmentation theo nhu cầu.
2. **Dùng charset mặc định rồi kết luận mọi tệp đều UTF-8.** Chỉ định charset; lựa chọn tự động theo tên file không chứng minh encoding.
3. **Chấp nhận `REPLACE`/`IGNORE` rồi nói text hợp lệ.** Dùng `CharsetDecoder` với `REPORT` cho kiểm chứng.
4. **Normalize NFC rồi thay đổi file gốc không lưu vết.** So sánh canonical và so sánh byte là hai mục tiêu riêng.
5. **Dùng NFKC đại trà để “dọn” văn bản.** Compatibility normalization có thể gộp thông tin quan trọng.
6. **Dùng `toLowerCase()` không truyền locale để xử lý identifier.** Default locale có thể thay đổi; cần quy tắc chuẩn hóa định danh rõ ràng.
7. **Cho rằng `Collator.PRIMARY` là phép kiểm tra chuỗi bằng nhau tuyệt đối.** Nó có thể bỏ qua một số khác biệt, tùy locale.
8. **Dùng formatter theo locale cho dữ liệu giao tiếp máy.** Chọn ISO 8601, JSON number hoặc format định nghĩa rõ ràng, độc lập locale.
9. **Tin rằng tên entry trong ZIP là đường dẫn an toàn.** Phải kiểm tra và thiết kế extraction để chặn traversal/symlink.
10. **Mở ZIP thành công rồi báo CRC đã được kiểm.** Trong công cụ audit cần đọc nội dung, tính CRC thực và so sánh.
11. **Chỉ nhìn `ZipEntry.getSize()`.** Metadata có thể thiếu/sai; phải giới hạn số byte giải nén thực tế.
12. **Nhầm CRC với xác thực mật mã.** CRC không có khóa bí mật và dễ tính lại.
13. **Giải mã mọi entry ZIP thành text.** ZIP có thể chứa binary; chỉ decode khi schema hoặc tên loại tệp yêu cầu.
14. **Cho rằng UTF-8 luôn là encoding của mọi ZIP đời cũ.** Archive legacy có thể không dùng UTF-8 flag và cần charset gốc.
15. **Chỉ kiểm tên trùng chính xác ở dạng byte.** Tên có thể trùng sau NFC hoặc theo quy tắc filesystem đích.
16. **Không kiểm hạn mức thời gian hoặc nested ZIP.** Quota của một ZIP cấp đầu không bảo đảm an toàn nếu hệ thống xử lý đệ quy archive.
17. **Cho rằng Java SE đọc mọi ZIP đã mã hóa.** Hỗ trợ tùy phương pháp nén/extension; không giả định có password/AES ZIP trong `java.util.zip` chuẩn.
18. **Dùng một ví dụ nhỏ làm cam kết cho archive lớn.** Production cần thử giới hạn số entry, ZIP64, latency, bộ nhớ và compatibility của runtime đang dùng.

## 13. Mở rộng cho một pipeline kiểm chứng production

Một pipeline ingestion nội dung ZIP có thể gồm các bước:

```text
Nhận tệp và áp byte limit
      |
      v
Kiểm tra ZIP structure + entry count + tên an toàn
      |
      v
Đọc stream từng entry + quota tổng + CRC/size
      |
      +--> binary: chỉ kiểm theo schema/băm mong muốn
      |
      +--> text: decode strict UTF-8 -> NFC diagnostic
                  -> parse/validate định dạng dữ liệu
                  -> locale dùng cho hiển thị, không đoán khi parse
      |
      v
Đối chiếu manifest/chữ ký từ nguồn tin cậy
      |
      v
Công bố kết quả audit / lưu kho cách ly / xử lý lỗi
```

**Khi nhận ZIP lớn**, đừng giữ tất cả nội dung trong RAM để kiểm một lần. Sử dụng stream và bộ giải mã theo chunk, đặt byte/time quotas, giới hạn số entry, độ sâu và CPU. Nếu tệp ZIP nằm trong object storage, cân nhắc chỉ tải khi đủ ngân sách, kiểm tra digest lúc truyền, rồi đọc từ file tạm; `ZipFile` cần file có thể truy cập ngẫu nhiên. Nếu dữ liệu đến từ network stream chưa có file, `ZipInputStream` thuận tiện cho duyệt tuần tự nhưng metadata có thể chưa đầy đủ cho tới khi đọc hết entry, và nó không phải bộ kiểm chứng hoàn chỉnh của central directory.

**Khi hỗ trợ nhiều charset**, chọn charset theo hợp đồng truyền dữ liệu hoặc metadata đáng tin. Phát hiện charset bằng heuristic có độ bất định, đặc biệt với đoạn văn bản ngắn; không tự kết luận “đúng Unicode” chỉ vì có thể decode thành một `String`.

**Khi có nghiệp vụ đa quốc gia**, tách phần parser dữ liệu chuẩn (ISO 8601, JSON, BigDecimal/decimal contract) khỏi phần presentation với `Locale`, `NumberFormat` và `DateTimeFormatter`. Kiểm thử locale data trên đúng JDK runtime image và cập nhật kết quả kỳ vọng khi nền tảng đổi dữ liệu địa phương.

## 14. Bài tập nâng cao

### Bài A — So sánh text theo hai tiêu chí

Viết lệnh `compare-text <a> <b>` nhận hai tệp UTF-8 có hạn mức. In **byte-identical** và **NFC-equivalent** dưới hai cột khác nhau. Đạt khi `café` và `cafe\u0301` cho `byte-identical=false` nhưng `NFC-equivalent=true`. Thêm kiểm thử CRLF/LF và không âm thầm strip whitespace.

### Bài B — Định dạng theo nhiều locale

Nhận locale tag từ tham số, parse bằng `Locale.forLanguageTag`, rồi định dạng một số và một ngày cố định. Đạt khi output có locale tag, timezone nếu định dạng thời gian, và parser kiểm hết input. Không hard-code nhóm dấu của locale từ một bản JDK duy nhất.

### Bài C — Manifest SHA-256 từ nguồn tin cậy

Thêm danh sách entry names và SHA-256 kỳ vọng, dùng `MessageDigest.getInstance("SHA-256")` trong lúc đọc stream. Đạt khi ZIP có byte bị sửa báo mismatch dù CRC metadata đã được sửa theo, và digest kỳ vọng được bảo vệ bằng kênh/chữ ký tin cậy.

### Bài D — Hạn mức ZIP bomb nhiều tầng

Cho phép nested ZIP tối đa hai tầng, truyền **cùng một ngân sách tổng byte** và entry count xuống mọi tầng. Đạt khi một nested archive vượt tổng quota bị từ chối dù từng tầng riêng lẻ không vượt. Thêm watchdog/timeout và test dữ liệu nén tỷ lệ cao.

### Bài E — Quyết định normalization policy

Tạo hai ZIP entry có tên canonical-equivalent và một ZIP không NFC nhưng không trùng. Đạt khi chương trình **báo xung đột với trường hợp đầu**, và **chỉ cảnh báo không NFC ở trường hợp sau**. Mở rộng xử lý xung đột case-insensitive của filesystem đích nếu ứng dụng có chức năng extraction.

## 15. Checklist tổng kết

- [ ] Nêu rõ đang kiểm **byte**, **code points**, **canonical-equivalent text** hay **collation**.
- [ ] Chỉ định UTF-8 tường minh; sử dụng decoder `REPORT` khi dữ liệu phải hợp lệ.
- [ ] Phân biệt code units, code points và grapheme clusters; không đo độ dài UI bằng `String.length()`.
- [ ] Lưu văn bản gốc khi cần toàn vẹn; chỉ normalize theo yêu cầu nghiệp vụ.
- [ ] Dùng `Locale` tường minh, kiểm full parse và không dùng locale rendering cho protocol.
- [ ] Với ZIP: kiểm entry names, trùng sau normalization, count, byte quota và CRC/size thực tế.
- [ ] Không mở mọi nội dung ZIP như văn bản; định nghĩa loại file và charset đầu vào.
- [ ] Không coi CRC-32 là chữ ký; dùng digest/chữ ký với nguồn tin cậy khi cần.
- [ ] Chưa giải nén thì vẫn kiểm tên; khi giải nén cần thiết kế chống traversal và symlink race riêng.
- [ ] Thử các fixture UTF-8 sai, BOM, NFD, locale khác nhau, ZIP hỏng, ZIP64 và archive lớn nếu hệ thống sẽ nhận chúng.
- [ ] Ghi rõ JDK/vendor, OS, locale provider/CLDR version và hạn mức trong báo cáo kết quả.

## Tài liệu tham khảo hiện hành

- [Oracle Java SE 27 — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [`CodingErrorAction`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CodingErrorAction.html): giải mã nghiêm ngặt.
- [Oracle Java SE 27 — `Normalizer`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD.
- [Unicode Consortium — Unicode Normalization FAQ](https://www.unicode.org/faq/normalization.html): canonical và compatibility normalization.
- [Oracle Java SE 27 — `Locale`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.html), [`NumberFormat`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/NumberFormat.html), [`Collator`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Collator.html): locale-aware formatting và collation.
- [Oracle JDK 27 — Supported Locales](https://www.oracle.com/java/technologies/javase/jdk27-suported-locales.html): dữ liệu locale và các provider có sẵn theo runtime.
- [Oracle Java SE 27 — `ZipFile`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/ZipFile.html), [`ZipEntry`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/ZipEntry.html), [`ZipOutputStream`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/ZipOutputStream.html), [`CRC32`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/CRC32.html): đọc/ghi và kiểm CRC archive.
- [Oracle Java SE 27 — `java.util.zip` package](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/package-summary.html): các cơ chế ZIP/ZIP64 và UTF-8 flag.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định từ Java 18, lý do vẫn cần chỉ định rõ encoding.
