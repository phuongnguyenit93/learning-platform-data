# Xây dựng kho fixture UTF-8 với tiếng Việt, emoji, byte lỗi và kết quả kiểm chứng round-trip

> **Chương:** Thực hành tổng hợp  
> **Phạm vi:** Java 18 trở lên; JEP 400 đặt UTF-8 làm charset mặc định trên các bản triển khai JDK phù hợp, nhưng bài thực hành luôn chỉ định `StandardCharsets.UTF_8` để kết quả độc lập với cấu hình môi trường. Chỉ sử dụng API Java còn được hỗ trợ trên JDK hiện đại.

## 1. Bài toán và kết quả cần bàn giao

Nhóm phát triển cần một **kho fixture có dữ liệu byte xác định** để kiểm thử xử lý văn bản trong API, file storage, import/export và pipeline dữ liệu. Nếu chỉ kiểm tra chuỗi ASCII như `hello`, nhiều lỗi mã hóa sẽ không lộ ra. Nếu chỉ đọc một file được hệ điều hành tạo sẵn, rất khó chứng minh đầu vào là UTF-8 hợp lệ hay một chuỗi byte lỗi có chủ đích.

Bài này xây dựng kho fixture bằng **một chương trình Java thuần**. Chương trình tạo các file dưới thư mục `fixtures/`, đọc lại byte đã lưu, kiểm tra giải mã UTF-8 bằng bộ giải mã nghiêm ngặt, thử round-trip qua `String`, rồi ghi `report.tsv` có SHA-256 và trạng thái của từng ca.

Sau bài thực hành, bạn có thể:

- Tạo fixture tiếng Việt có dấu, emoji dùng nhiều code point, văn bản NFC/NFD và file có UTF-8 BOM.
- Tạo file nhị phân chứa byte UTF-8 không hợp lệ mà không phụ thuộc trình soạn thảo hoặc encoding hệ điều hành.
- Phân biệt giải mã **báo lỗi** (`CodingErrorAction.REPORT`) với giải mã **thay thế ký tự lỗi** (`U+FFFD`).
- Chứng minh round-trip với dữ liệu hợp lệ bằng **hai tiêu chí**: chuỗi không đổi và byte không đổi.
- Phát hiện rằng round-trip sau khi thay thế dữ liệu lỗi **không giữ nguyên byte nguồn**.
- Ghi báo cáo có thể đối chiếu trên các JDK khác nhau, không tự bịa kết quả hoặc benchmark.

## 2. Mô hình round-trip và các giới hạn

Với một tệp UTF-8 hợp lệ, ta kiểm chứng:

```text
String đầu vào
   |  encode UTF-8
   v
byte[] ghi ra file
   |  đọc byte[]
   v
decode UTF-8 (REPORT)
   |
   v
String đã giải mã -- so với String đầu vào
   |  encode UTF-8
   v
byte[] sau round-trip -- so với byte[] trong file
```

Đối với UTF-8 hợp lệ, phép giải mã và mã hóa lại theo cùng charset phải bảo toàn chuỗi Unicode và chính dãy byte hợp lệ ban đầu. Hai kiểm tra có mục đích khác nhau:

| Kiểm chứng | Cách kiểm tra | Lỗi giúp phát hiện |
| --- | --- | --- |
| **Text round-trip** | `expected.equals(decoded)` | Mất, thêm, đổi hoặc chuẩn hóa ngoài ý muốn ký tự Unicode |
| **Byte round-trip** | `Arrays.equals(original, decoded.getBytes(UTF_8))` | Mất byte, thay đổi dấu BOM, line ending hoặc biến đổi encoding không mong muốn |
| **Giải mã nghiêm ngặt** | Decoder có `onMalformedInput(REPORT)` | Chuỗi byte UTF-8 không hợp lệ, bị cắt cụt hoặc mã hóa Unicode sai |
| **Kiểm tra toàn vẹn fixture** | Hash SHA-256 của byte trên đĩa | Tệp bị đổi trong quá trình lưu, chuyển hoặc commit |

Với dãy byte **không hợp lệ**, không có một round-trip Unicode bảo toàn dữ liệu theo đường giải mã thay thế: byte lỗi có thể biến thành ký tự `U+FFFD` (replacement character), rồi được mã hóa thành một dãy byte UTF-8 khác. Đó là hành vi xử lý lỗi hữu ích cho hiển thị, **không phải cơ chế giữ nguyên dữ liệu nhị phân**.

Phân biệt kết quả kiểm thử: một ca byte lỗi được đánh dấu **PASS khi decoder nghiêm ngặt từ chối nó đúng như dự kiến**. `PASS` ở đây không đồng nghĩa file đó là văn bản UTF-8 hợp lệ.

## 3. Thiết kế danh mục fixture

Kho fixture dùng tên file và chính sách cố định để dễ dùng lại:

| File | Đầu vào | Tính hợp lệ | Điều cần chứng minh |
| --- | --- | --- | --- |
| `01-vietnamese-nfc.txt` | `Tiếng Việt: Xin chào, Hà Nội, Đắk Lắk, cà phê.` và LF | Hợp lệ | Dấu tiếng Việt và UTF-8 nhiều byte được giữ nguyên |
| `02-vietnamese-nfd.txt` | Cùng nội dung nhưng ở Unicode NFD | Hợp lệ | Chuỗi tương đương về chuẩn hóa vẫn có byte khác NFC; mỗi file round-trip độc lập |
| `03-emoji.txt` | `😀 🚀 👩‍💻 🇻🇳` cùng văn bản | Hợp lệ | Code point ngoài BMP, chuỗi emoji ZWJ, cặp regional indicators |
| `04-mixed.txt` | Ghép tiếng Việt NFC và emoji | Hợp lệ | Không mất ký tự hoặc dấu xuống dòng LF trong văn bản hỗn hợp |
| `05-bom.txt` | Ký tự `U+FEFF` đầu chuỗi và tiếng Việt | Hợp lệ | BOM được giữ như một code point/ba byte ở đầu fixture |
| `06-invalid-leading.bin` | `FF` | Không hợp lệ | Byte mở đầu không thuộc UTF-8 hợp lệ |
| `07-invalid-continuation.bin` | `C3 28` | Không hợp lệ | Byte sau byte dẫn không phải continuation byte |
| `08-truncated.bin` | `E2 82` | Không hợp lệ | Chuỗi ba byte bị thiếu byte cuối |
| `09-overlong.bin` | `C0 AF` | Không hợp lệ | Biểu diễn overlong bị UTF-8 hiện đại từ chối |
| `10-surrogate.bin` | `ED A0 80` | Không hợp lệ | Mã hóa trực tiếp một surrogate không hợp lệ trong UTF-8 |

Chọn đuôi `.bin` cho byte lỗi để hạn chế công cụ xem file mặc định coi chúng là văn bản. `report.tsv` là **bản ghi kiểm chứng**, không phải dữ liệu đầu vào. Với kho fixture thuộc source control, giữ cả các file dữ liệu và báo cáo (nếu cần lưu bằng chứng), kiểm tra thay đổi hash khi nâng cấp hoặc chuyển môi trường.

### 3.1. Vì sao cần NFC và NFD?

Unicode cho phép một số ký tự có dấu được biểu diễn bằng **một code point đã ghép** hoặc **một chuỗi code point cơ sở và dấu kết hợp**. Ví dụ chữ `é` có thể là `U+00E9` hoặc `U+0065 U+0301`.

`Normalizer.normalize(text, Normalizer.Form.NFC)` và `NFD` chuyển biểu diễn Unicode theo quy tắc chuẩn hóa. Hai chuỗi có thể tương đương sau chuẩn hóa nhưng **không bằng nhau theo `String.equals` và không có cùng byte UTF-8**. Encode/decode UTF-8 tự nó không chuẩn hóa Unicode.

Trong bài, mỗi fixture được đối chiếu với **chính chuỗi đầu vào của nó**, thay vì ép mọi file về NFC trước khi so sánh. Nếu ứng dụng cần chuẩn hóa, hãy định nghĩa nó như một bước biến đổi riêng rồi kiểm thử riêng.

### 3.2. Emoji và `String.length()`

Trong Java, `String.length()` đếm **UTF-16 code units**, còn `String.codePointCount(0, text.length())` đếm **Unicode code points**. Một emoji ngoài BMP thường chiếm hai UTF-16 code units; chuỗi `👩‍💻` chứa nhiều code point nối bởi `U+200D` (ZWJ). Vì vậy đừng dùng `length()` làm số lượng emoji, số ký tự người dùng nhìn thấy hay số byte UTF-8.

Để đếm byte thực, dùng `text.getBytes(StandardCharsets.UTF_8).length`. Để tính các cụm ký tự (grapheme clusters), cần quy tắc Unicode phù hợp với ứng dụng; không mặc định rằng một code point tương đương một emoji hiển thị.

## 4. Chương trình tạo fixture và báo cáo

Tạo file duy nhất `Utf8FixtureBank.java` theo nội dung dưới đây. Lưu **chính file nguồn** dưới UTF-8; lệnh biên dịch sẽ dùng `-encoding UTF-8`. Chương trình không cần thư viện bên ngoài và chỉ ghi thư mục `fixtures/` tương đối với nơi chạy.

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;

public final class Utf8FixtureBank {
    private static final Charset UTF8 = StandardCharsets.UTF_8;
    private static final Path ROOT = Path.of("fixtures");
    private static final List<String> REPORT = new ArrayList<>();
    private static int failures;

    // Decoder mới cho mỗi lần kiểm chứng để tránh chia sẻ trạng thái.
    private static String strictDecode(byte[] input)
            throws CharacterCodingException {
        return UTF8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(input))
                .toString();
    }

    private static String sha256(byte[] input) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(input);
        return HexFormat.of().formatHex(hash);
    }

    private static String yesNo(boolean value) {
        return value ? "YES" : "NO";
    }

    private static void addResult(
            String name, String kind, byte[] stored, String strict,
            String textEqual, String byteEqual, String replacement,
            boolean passed) throws Exception {

        REPORT.add(String.join("\t",
                name, kind, Integer.toString(stored.length),
                strict, textEqual, byteEqual, replacement,
                sha256(stored), passed ? "PASS" : "FAIL"));

        if (!passed) {
            failures++;
        }
    }

    private static void valid(String name, String expected)
            throws Exception {
        Path file = ROOT.resolve(name);
        Files.writeString(file, expected, UTF8);
        byte[] stored = Files.readAllBytes(file);

        // Decode nghiêm ngặt; lỗi ở ca VALID làm bài thực hành thất bại.
        String decoded = strictDecode(stored);
        boolean textEqual = expected.equals(decoded)
                && expected.equals(Files.readString(file, UTF8));
        boolean byteEqual = Arrays.equals(
                stored, decoded.getBytes(UTF8));
        boolean sourceBytesEqual = Arrays.equals(
                stored, expected.getBytes(UTF8));

        addResult(name, "VALID", stored, "OK",
                yesNo(textEqual), yesNo(byteEqual), "NO",
                textEqual && byteEqual && sourceBytesEqual);
    }

    private static void invalid(String name, byte[] expectedBytes)
            throws Exception {
        Path file = ROOT.resolve(name);
        Files.write(file, expectedBytes);
        byte[] stored = Files.readAllBytes(file);

        boolean rejected;
        try {
            strictDecode(stored);
            rejected = false;
        } catch (CharacterCodingException expected) {
            rejected = true;
        }

        // Constructor này thay thế chuỗi byte hỏng bằng U+FFFD.
        String lenient = new String(stored, UTF8);
        boolean replacement = lenient.indexOf('\uFFFD') >= 0;
        boolean byteEqual = Arrays.equals(
                stored, lenient.getBytes(UTF8));
        boolean storedUnchanged = Arrays.equals(stored, expectedBytes);

        // PASS = từ chối đúng dữ liệu sai, có replacement, mất byte identity.
        boolean passed = rejected && replacement
                && !byteEqual && storedUnchanged;
        addResult(name, "INVALID", stored,
                rejected ? "REJECTED" : "UNEXPECTED_OK",
                "N/A", yesNo(byteEqual), yesNo(replacement), passed);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 0) {
            throw new IllegalArgumentException("Run without arguments");
        }
        Files.createDirectories(ROOT);

        String vietnamese =
                "Tiếng Việt: Xin chào, Hà Nội, Đắk Lắk, cà phê.\n";
        String nfc = Normalizer.normalize(
                vietnamese, Normalizer.Form.NFC);
        String nfd = Normalizer.normalize(
                vietnamese, Normalizer.Form.NFD);
        String emoji = "Emoji: 😀 🚀 👩‍💻 🇻🇳\n";

        // Tự kiểm tra rằng cặp NFC/NFD phục vụ đúng mục đích.
        if (Arrays.equals(nfc.getBytes(UTF8), nfd.getBytes(UTF8))
                || !Normalizer.normalize(
                        nfd, Normalizer.Form.NFC).equals(nfc)) {
            throw new AssertionError("NFC/NFD fixture assumption failed");
        }

        REPORT.add("# java=" + Runtime.version());
        REPORT.add("# defaultCharset=" + Charset.defaultCharset().name());
        REPORT.add("file\tkind\tbytes\tstrict_utf8\ttext_equal\t"
                + "byte_equal\treplacement\tsha256\tstatus");

        valid("01-vietnamese-nfc.txt", nfc);
        valid("02-vietnamese-nfd.txt", nfd);
        valid("03-emoji.txt", emoji);
        valid("04-mixed.txt", nfc + emoji + "Kết thúc.\n");
        valid("05-bom.txt", "\uFEFFBOM: Xin chào.\n");

        invalid("06-invalid-leading.bin",
                new byte[] {(byte) 0xFF});
        invalid("07-invalid-continuation.bin",
                new byte[] {(byte) 0xC3, (byte) 0x28});
        invalid("08-truncated.bin",
                new byte[] {(byte) 0xE2, (byte) 0x82});
        invalid("09-overlong.bin",
                new byte[] {(byte) 0xC0, (byte) 0xAF});
        invalid("10-surrogate.bin",
                new byte[] {(byte) 0xED, (byte) 0xA0, (byte) 0x80});

        Files.writeString(ROOT.resolve("report.tsv"),
                String.join("\n", REPORT) + "\n", UTF8);

        REPORT.forEach(System.out::println);
        int total = 10;
        System.out.printf("TOTAL=%d PASS=%d FAIL=%d%n",
                total, total - failures, failures);
        if (failures != 0) {
            System.exit(1);
        }
    }
}
```

### 4.1. Vì sao đoạn mã cố ý không dùng charset mặc định?

JEP 400 chuẩn hóa UTF-8 thành charset mặc định từ Java 18 trong cấu hình thông thường, nhưng mã kiểm chứng phải thể hiện rõ giả định dữ liệu. `Files.writeString(file, text, UTF8)`, `Files.readString(file, UTF8)`, `getBytes(UTF8)` và `new String(bytes, UTF8)` dùng **cùng charset được chỉ định tường minh**. Điều này giúp tài liệu và fixture có ý nghĩa ngay cả khi chương trình chạy trong môi trường có điều chỉnh charset mặc định.

Thông tin `defaultCharset` trong report chỉ giúp **quan sát môi trường**; tính đúng đắn của các ca không được tính dựa trên giá trị này. Không cần thay đổi locale hoặc dùng thuộc tính JVM tùy biến để ép một kết quả PASS.

### 4.2. Vì sao decoder phải ở chế độ `REPORT`?

`new String(bytes, UTF8)` chọn cách thay thế chuỗi lỗi; nó **không** phù hợp khi nhiệm vụ là xác thực dữ liệu đầu vào có đúng UTF-8 hay không. Với kiểm chứng nghiêm ngặt, sử dụng:

```java
String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
```

Ở đây `bytes` là mảng byte được đọc từ file. Decoder sẽ ném `CharacterCodingException` (chẳng hạn `MalformedInputException`) khi gặp dữ liệu không hợp lệ. Với các fixture byte lỗi, **việc ném ngoại lệ** là hành vi đúng và được tính là ca PASS. Không so sánh nguyên văn thông điệp ngoại lệ, vì cách diễn đạt có thể khác theo phiên bản JDK.

### 4.3. Vì sao cần `sha256` trong báo cáo?

SHA-256 cho phép xác nhận byte thật của fixture sau khi lưu hoặc chuyển hệ thống có giữ nguyên hay không. Hash chỉ có ý nghĩa khi tính trên **byte của file**, không phải một chuỗi đã giải mã rồi chuẩn hóa. Hai file NFC và NFD có thể biểu diễn văn bản tương đương, nhưng có hash khác do dãy byte khác nhau.

Không suy rằng hai file có hash giống nhau thì chúng chắc chắn đến từ cùng nguồn nghiệp vụ; hash phục vụ kiểm tra toàn vẹn dữ liệu và không thay thế các kiểm thử hợp đồng Unicode.

## 5. Biên dịch, chạy và kiểm tra tệp sinh ra

Yêu cầu JDK 18 trở lên và một thư mục làm việc bạn có quyền ghi. Lưu nguồn Java ở định dạng UTF-8 vì trong source có tiếng Việt và emoji thực.

```bash
javac -encoding UTF-8 Utf8FixtureBank.java
java Utf8FixtureBank
```

Trong Windows PowerShell, hai lệnh `javac` và `java` vẫn dùng như trên. Chương trình tạo thư mục `fixtures` tương đối với **thư mục đang chạy lệnh**; không cần Gradle, Maven, network hoặc thư viện ngoài.

```text
fixtures/
  01-vietnamese-nfc.txt
  02-vietnamese-nfd.txt
  03-emoji.txt
  04-mixed.txt
  05-bom.txt
  06-invalid-leading.bin
  07-invalid-continuation.bin
  08-truncated.bin
  09-overlong.bin
  10-surrogate.bin
  report.tsv
```

**Chú ý:** chạy lại chương trình sẽ ghi đè các file cùng tên trong thư mục `fixtures/` bằng dữ liệu chuẩn xác của bài thực hành. Hãy dùng một thư mục làm việc riêng khi cần bảo toàn các fixture do người khác thêm vào. Trong repo thật, có thể giới hạn tập tệp đầu ra hoặc thêm kiểm tra để tránh ghi đè ngoài ý muốn.

### 5.1. Ý nghĩa các cột `report.tsv`

| Cột | Ý nghĩa |
| --- | --- |
| `file` | Tên fixture, là khóa để tìm tệp cần kiểm tra |
| `kind` | `VALID` hoặc `INVALID` theo mục tiêu của ca |
| `bytes` | Kích thước file tính bằng byte, không phải độ dài `String` |
| `strict_utf8` | `OK` nếu giải mã nghiêm ngặt thành công; `REJECTED` nếu decoder từ chối; `UNEXPECTED_OK` nếu dữ liệu lỗi bị chấp nhận |
| `text_equal` | Chuỗi sau giải mã có đúng bằng đầu vào mong đợi hay không; `N/A` với dữ liệu lỗi |
| `byte_equal` | Byte của file có bằng byte sau giải mã rồi mã hóa lại hay không |
| `replacement` | Với file lỗi, kết quả giải mã thay thế có chứa `U+FFFD` không; `NO` ở các file hợp lệ được tạo trong bài |
| `sha256` | Hash của byte đọc từ file |
| `status` | `PASS` nếu kết quả khớp hợp đồng của loại fixture; `FAIL` nếu sai |

Dòng `# java=...` và `# defaultCharset=...` ghi môi trường; toàn bộ phần sau dùng dấu tab. Có thể mở file bằng text editor hoặc công cụ đọc TSV để đối chiếu từng ca.

### 5.2. Bảng kết quả dự kiến

Đây là **kỳ vọng lý thuyết**, không phải kết quả được thực thi khi biên soạn bài. Số byte và SHA-256 của mỗi file sẽ do chương trình tính từ dữ liệu thực tế:

| Fixture | `strict_utf8` | `text_equal` | `byte_equal` | `replacement` | `status` |
| --- | --- | --- | --- | --- | --- |
| `01-vietnamese-nfc.txt` | OK | YES | YES | NO | PASS |
| `02-vietnamese-nfd.txt` | OK | YES | YES | NO | PASS |
| `03-emoji.txt` | OK | YES | YES | NO | PASS |
| `04-mixed.txt` | OK | YES | YES | NO | PASS |
| `05-bom.txt` | OK | YES | YES | NO | PASS |
| `06-invalid-leading.bin` | REJECTED | N/A | NO | YES | PASS |
| `07-invalid-continuation.bin` | REJECTED | N/A | NO | YES | PASS |
| `08-truncated.bin` | REJECTED | N/A | NO | YES | PASS |
| `09-overlong.bin` | REJECTED | N/A | NO | YES | PASS |
| `10-surrogate.bin` | REJECTED | N/A | NO | YES | PASS |

Với bộ fixture chưa bị sửa, chương trình **dự kiến** kết thúc bằng `TOTAL=10 PASS=10 FAIL=0` và mã thoát `0`. Nếu phát hiện ca lệch, chương trình ghi `FAIL` và kết thúc với mã thoát `1`. Trường hợp chương trình dừng sớm vì ngoại lệ I/O hoặc bất thường trong một ca `VALID`, cần xử lý ngoại lệ đó trước khi coi báo cáo là đầy đủ.

## 6. Phân tích các trường hợp dễ gây hiểu nhầm

### 6.1. NFD/NFC: tương đương sau chuẩn hóa nhưng byte khác nhau

Đầu vào `02-vietnamese-nfd.txt` được chuẩn hóa bằng `Normalizer.Form.NFD`. Nếu tự ý gọi `Normalizer.normalize(decoded, NFC)` trước khi so byte thì kết quả sẽ khác dữ liệu của fixture NFD. Đó là **thay đổi văn bản có chủ đích**, không phải lỗi của UTF-8. Khi kiểm chứng encoding, giữ nguyên chuỗi đầu vào; khi kiểm chứng normalize, viết ca riêng và mô tả chính xác tiêu chí.

### 6.2. BOM: ba byte đầu không phải lỗi

Ở file `05-bom.txt`, `U+FEFF` đứng đầu chuỗi. Khi mã hóa bằng UTF-8, ký tự này có dãy byte `EF BB BF`. Trong đường xử lý của ví dụ, dữ liệu được giải mã thành ký tự `U+FEFF` và được mã hóa lại thành ba byte ban đầu.

Không mặc định loại BOM trong chương trình rồi vẫn so byte với file gốc; nếu yêu cầu sản phẩm **phải bỏ BOM**, đó là một phép biến đổi phải có đặc tả, dữ liệu kỳ vọng và bài test riêng.

### 6.3. Replacement không phải round-trip byte

Với file `07-invalid-continuation.bin`, dữ liệu `C3 28` có một byte dẫn UTF-8 bị theo sau bởi dấu ngoặc `(` thay vì một continuation byte. Decoder dùng `REPORT` từ chối input. Khi dùng `new String(bytes, UTF8)`, phần lỗi có thể được thay bằng `U+FFFD`, sau đó mã hóa ra byte của replacement character. Đầu ra **không** bằng hai byte gốc.

Không suy luận số lượng ký tự thay thế từ một trường hợp rồi coi đó là cam kết cho mọi dãy byte hỏng. Kiểm thử ở đây yêu cầu hai bằng chứng bền vững: decoder nghiêm ngặt **từ chối**, và đường thay thế **không giữ byte identity**.

### 6.4. Dữ liệu lỗi không thể tự sửa bằng đổi charset

Một tệp `.bin` cố ý chứa byte lỗi là một fixture âm tính. Thay UTF-8 bằng một charset khác chỉ để đọc được file có thể che mất vấn đề hoặc tạo ký tự sai. Với dữ liệu người dùng thực, chính sách xử lý cần được nêu rõ: từ chối import, trả lỗi có vị trí, hoặc dùng replacement nếu nghiệp vụ cho phép mất dữ liệu.

### 6.5. Dấu xuống dòng, clipboard và công cụ chỉnh sửa

Trình soạn thảo có thể đổi LF thành CRLF, tự thêm/bỏ BOM hoặc tự chuẩn hóa Unicode. Với kho fixture kiểm chứng byte, các thao tác đó sẽ làm `sha256` đổi. Nên giữ dữ liệu fixture nhị phân trong kiểm soát phiên bản và so hash, thay vì sửa thủ công file rồi suy rằng văn bản vẫn 'trông giống nhau' là đủ.

## 7. Mở rộng phép thử cho lỗi ở phía `String`

Kho ở trên kiểm chứng **byte đầu vào không hợp lệ**. Một vấn đề khác là Java `String` có thể chứa một UTF-16 surrogate đơn lẻ, ví dụ `"\uD83D"`, mà không tạo thành Unicode scalar value hợp lệ. Nếu muốn kiểm tra encoding đầu ra theo chế độ nghiêm ngặt, sử dụng `CharsetEncoder` riêng:

```java
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;

String brokenUtf16 = "\uD83D"; // high surrogate không có low surrogate
try {
    StandardCharsets.UTF_8.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(CharBuffer.wrap(brokenUtf16));
    throw new AssertionError("Expected malformed input");
} catch (MalformedInputException expected) {
    // PASS: từ chối chuỗi UTF-16 sai thay vì làm mất dữ liệu âm thầm.
}
```

Đây là **đoạn minh họa đặt bên trong một method/test có xử lý ngoại lệ phù hợp**, không phải tệp Java độc lập. `String.getBytes(UTF_8)` sử dụng chính sách thay thế cho input lỗi; nếu hợp đồng đòi hỏi không chấp nhận mất dữ liệu, hãy chọn `CharsetEncoder` với `REPORT` và xử lý lỗi rõ ràng.

## 8. Tích hợp fixture vào kiểm thử ứng dụng

Khi đưa kho fixture vào một suite kiểm thử, đọc file dưới dạng **byte** trước và quyết định chính sách giải mã sau:

```java
Path fixture = Path.of("fixtures", "07-invalid-continuation.bin");
byte[] raw = Files.readAllBytes(fixture);

try {
    StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(raw));
    throw new AssertionError("Must reject malformed UTF-8");
} catch (CharacterCodingException expected) {
    // PASS cho ca âm tính.
}
```

Trong đoạn trên, cần import `Path`, `Files`, `ByteBuffer`, `StandardCharsets`, `CodingErrorAction` và `CharacterCodingException` theo API Java chuẩn. Khi kiểm thử thật, nên để framework test kiểm tra ngoại lệ và message lỗi do **chính ứng dụng** phát sinh, thay vì chỉ dựa vào ví dụ độc lập.

Với tệp hợp lệ, gọi `Files.readString(fixture, UTF_8)` và đối chiếu với chuỗi mong đợi; khi cần giữ nguyên BOM, normalization hoặc line ending, sử dụng kiểm tra byte trong report hoặc đối chiếu `Files.readAllBytes` với snapshot đã xác nhận.

## 9. Bảng tiêu chí nghiệm thu

| ID | Tiêu chí | Minh chứng mong đợi |
| --- | --- | --- |
| U01 | Tạo được 10 fixture đúng tên, không cần mạng | Có 5 file text hợp lệ và 5 file byte lỗi |
| U02 | UTF-8 được chỉ định tường minh ở mọi thao tác chuyển đổi | Dùng `StandardCharsets.UTF_8`, không phụ thuộc default charset |
| U03 | Tiếng Việt và emoji round-trip | Text và byte đều `YES` |
| U04 | NFC và NFD được phân biệt | Hai bộ byte khác nhau nhưng normalize về NFC cho cùng chuỗi |
| U05 | BOM được kiểm chứng | Byte `EF BB BF` ở đầu được bảo toàn trong round-trip |
| U06 | Byte lỗi bị decoder nghiêm ngặt từ chối | `strict_utf8=REJECTED` |
| U07 | Replacement cho dữ liệu lỗi không giữ byte nguồn | `replacement=YES`, `byte_equal=NO` |
| U08 | Ghi được checksum từng tệp | Cột SHA-256 không rỗng cho mọi fixture |
| U09 | Báo cáo tổng hợp đủ 10 ca | `TOTAL=10 PASS=10 FAIL=0` với dữ liệu chưa bị sửa |
| U10 | Có thể chạy lại trên JDK đích | Ghi `java -version`, lưu `report.tsv` và đối chiếu hash |

Để sử dụng báo cáo làm bằng chứng nâng cấp JDK, lưu lệnh chạy, phiên bản JDK, `report.tsv` và trạng thái thoát của tiến trình. **Không** kết luận hai JDK có hành vi khác nhau chỉ vì `defaultCharset` hoặc metadata khác: trước tiên phải xem các trường `strict_utf8`, `text_equal`, `byte_equal` và hash của cùng fixture.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `new String(bytes, UTF_8)` chưa đủ để chứng minh một file chứa UTF-8 hợp lệ?
2. Khi nào text round-trip có thể đúng nhưng việc so hash cho thấy dữ liệu nguồn đã bị thay đổi ở một bước khác?
3. Vì sao hai chuỗi tiếng Việt nhìn giống nhau vẫn có thể khác nhau theo `String.equals` và theo byte?
4. Vì sao `String.length()`, số code point và kích thước byte UTF-8 không phải lúc nào cũng bằng nhau?
5. Một file byte lỗi được đánh dấu `PASS` có nghĩa gì? Nó có phải file UTF-8 hợp lệ hay không?
6. Khi nào cần `CharsetEncoder` với `REPORT` thay vì chỉ `String.getBytes(UTF_8)`?
7. Nếu công cụ Git hoặc editor đổi line ending/BOM, phần nào của báo cáo sẽ giúp phát hiện?

**Ghi nhớ:** Hãy coi fixture là **dãy byte có hợp đồng rõ ràng**, kiểm chứng riêng đầu vào hợp lệ và đầu vào lỗi. Giải mã nghiêm ngặt, so sánh text, so sánh byte và SHA-256 cho những bằng chứng bổ sung nhau; UTF-8 mặc định theo JEP 400 không thay thế việc khai báo charset tường minh khi dữ liệu phải tái lập. Tài liệu nên đối chiếu trên JDK đang dùng: JEP 400, Javadoc của `StandardCharsets`, `CharsetDecoder`, `CharsetEncoder`, `Files`, `Normalizer` và `String`.
