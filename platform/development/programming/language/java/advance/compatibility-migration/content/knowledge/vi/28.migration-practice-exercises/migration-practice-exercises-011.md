# Phát hiện hồi quy charset, locale hoặc dữ liệu tuần tự hóa

Trong **Java Advance Compatibility Migration**, ứng dụng có thể vượt qua compile, unit test thông thường và startup smoke test nhưng vẫn xử lý sai dữ liệu từng được ghi bởi phiên bản cũ. Ba nhóm vấn đề dễ bị bỏ qua là **charset**, **locale** và **serialization** (tuần tự hóa dữ liệu). Ví dụ, một file cũ ghi bằng ISO-8859-1 được Java mới đọc mặc định thành UTF-8; một mã định danh bị đổi chữ hoa theo locale của máy CI; hoặc dữ liệu được lưu qua `ObjectOutputStream` không còn khôi phục được sau khi đổi class/package/`serialVersionUID`.

Bài thực hành này thuộc chương **Bài thực hành** của **Java Advance Compatibility Migration**. Người học sẽ xây một phòng thí nghiệm nhỏ gồm **producer V1** và **reader V2**, tạo dữ liệu kiểm thử bằng phiên bản cũ, lưu fixtures bất biến rồi viết các regression tests để bắt lỗi trước khi phát hành. Ví dụ chọn JDK 17 làm baseline và JDK 21 làm target để dễ minh họa, nhưng quy trình áp dụng cho những cặp JDK được dự án chính thức hỗ trợ. Mọi ví dụ dữ liệu đều là dữ liệu tổng hợp, không cần secrets hoặc hệ thống production.

**Kết quả mong đợi:** biết phân biệt hồi quy do encoding với hồi quy do dữ liệu locale và serialization; biết thiết kế test *old writer → new reader*; biết dùng fixtures có provenance, negative tests và ma trận chạy nhiều môi trường; biết khi nào cần sửa source, dữ liệu, cấu hình hoặc hợp đồng định dạng.

## 1. Mục tiêu, điều kiện tiên quyết và sản phẩm bàn giao

Sau khi hoàn thành, người học có thể:

1. Giải thích vì sao `new String(bytes)` và các API text dùng default charset là rủi ro cho dữ liệu lưu trữ lâu dài.
2. Dùng `CharsetDecoder` với chế độ `REPORT` để phát hiện bytes không hợp lệ thay vì thay ký tự im lặng.
3. Phân biệt locale của người dùng với locale dùng cho **machine identifiers**, định dạng số và ngày giờ.
4. Tái hiện sự khác nhau giữa `Locale.ROOT` và locale như `tr-TR` khi xử lý chữ hoa/thường.
5. Đọc object stream V1 trên binary V2 có thay đổi class nhưng giữ compatibility contract hợp lệ.
6. Nhận biết `InvalidClassException`, `ClassNotFoundException`, field default sau deserialize và rủi ro native Java serialization.
7. Dùng golden fixtures, checksums và regression tests để không tự hợp thức hóa một behavior sai.
8. Báo cáo rõ những chiều tương thích đã kiểm chứng và những chiều chưa được bảo đảm.

**Điều kiện:** có JDK baseline và target đã được phép dùng (minh họa 17 và 21), `javac`/`java`, một thư mục làm việc riêng, và JUnit 5 nếu muốn chạy test tự động. Maven hoặc Gradle chỉ dùng để điều phối test; kiến thức cốt lõi nằm ở Java standard APIs. Không cần database, Docker hay tải dữ liệu ngoài để hiểu bài.

**Sản phẩm bàn giao thực hành**:
- Bộ fixtures `customer-v1.ser`, `name-v1-latin1.txt`, `name-v1-utf8.txt` do V1 tạo.
- Metadata producer version, charset, schema/class identity và SHA-256.
- Các bài JUnit tests cho charset, locale, serialization và trường hợp sai.
- Kết quả chạy trên JDK baseline/target, có ghi môi trường.
- Báo cáo quyết định: PASS, FAIL hoặc BLOCKED cho từng hợp đồng.

## 2. Bối cảnh lỗi cần phát hiện

Giả sử dịch vụ Customer V1 đã lưu ba loại dữ liệu:

| Dữ liệu | V1 ghi theo cách nào | V2 cần bảo đảm |
|---|---|---|
| Tên khách hàng cũ | Text bytes theo ISO-8859-1 | Giải mã đúng chữ `Café` |
| Mã định danh | Chuỗi được chuẩn hóa thành chữ hoa | Mã `id` phải thành `ID`, không phụ thuộc locale máy |
| Snapshot khách hàng | Java `Serializable` class V1 | V2 đọc được ID, tên, số dư và gán default cho trường mới |

**Lỗi cố ý được đưa vào bài**:
- V2 dùng `new String(bytes)` trên bytes Latin-1 → có thể ra ký tự thay thế ở JDK dùng UTF-8 mặc định.
- V2 dùng `raw.toUpperCase()` → kết quả phụ thuộc `Locale.getDefault()`.
- V2 thay `serialVersionUID` hoặc package của class → object stream V1 không còn tương thích.
- V2 thêm field mới nhưng quên xử lý giá trị mặc định khi đọc stream cũ → downstream code gặp `null`.

Bài không nhằm chứng minh JDK 21 có lỗi. Những sự cố này là **lỗi hợp đồng dữ liệu của ứng dụng** bị bộc lộ khi thay môi trường Java, runtime defaults hoặc source.

### 2.1. Vòng đời kiểm thử

~~~text
Producer V1 (JDK baseline)
       |
       +-- ghi byte fixtures và metadata
       |
       v
Golden fixtures bất biến
       |
       v
Reader V2 (JDK target)
       |
       +-- Test decode charset
       +-- Test locale-independent identifiers
       +-- Test native serialized object
       +-- Test semantic invariants
       |
       v
PASS / FAIL + nguyên nhân + bằng chứng
~~~

Quan trọng nhất: **không tạo fixture bằng V2 rồi cho V2 đọc lại**. Đó chỉ là round-trip test của bản mới, không phát hiện compatibility regression.

## 3. Thiết kế thư mục phòng thí nghiệm

Một cấu trúc có thể dùng:

~~~text
charset-locale-serialization-lab/
  v1-producer/
    src/
      org/example/lab/model/SavedCustomer.java
      org/example/lab/fixture/WriteFixtures.java
  v2-reader/
    pom.xml
    src/
      main/java/org/example/lab/model/SavedCustomer.java
      test/java/org/example/lab/LegacyCompatibilityTest.java
      test/resources/legacy/
        customer-v1.ser
        name-v1-latin1.txt
        name-v1-utf8.txt
        README.md
  output/
    v1-classes/
    generated-fixtures/
  reports/
~~~

**Lý do tách source V1 và V2:** cả hai có thể định nghĩa cùng fully-qualified class name `org.example.lab.model.SavedCustomer`, nhưng bytecode phải được biên dịch riêng. Không đặt cả hai file class cùng tên vào một source set và mong classpath tự phân biệt version.

### 3.1. Quy tắc fixture

- Fixture được tạo bằng **source/tag/release V1**, không được tạo lại tự động khi test V2 fail.
- Tên file thể hiện format/version/charset; không đặt chung chung `sample.dat`.
- Bytes gốc phải được giữ nguyên, đặc biệt khi Git line-ending conversion có thể tác động file text.
- Có expected business values được review độc lập.
- Có manifest/hash để biết dữ liệu có bị thay.
- Fixture phải là **synthetic/trusted input**. Không deserialize object stream lấy ngẫu nhiên từ mạng.

Nếu có dữ liệu thật cần dùng để bổ sung coverage, chỉ sử dụng bản đã được xử lý theo quy trình masking và data governance. Không commit raw production snapshots/PII/secrets.

## 4. Phần A — Tạo model V1 cho native serialization

Tạo file `v1-producer/src/org/example/lab/model/SavedCustomer.java`:

~~~java
package org.example.lab.model;

import java.io.Serial;
import java.io.Serializable;
import java.math.BigDecimal;

public final class SavedCustomer implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String customerId;
    private String displayName;
    private BigDecimal credit;

    public SavedCustomer(
            String customerId,
            String displayName,
            BigDecimal credit) {
        this.customerId = customerId;
        this.displayName = displayName;
        this.credit = credit;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getDisplayName() {
        return displayName;
    }

    public BigDecimal getCredit() {
        return credit;
    }
}
~~~

Class có `Serializable` và **explicit `serialVersionUID = 1L`**. Việc chọn `1L` chỉ phục vụ ví dụ, không phải quy tắc nên áp cho mọi class. Đối với class thực tế đã có stream lịch sử, giá trị UID phải khớp với định dạng đã được ghi; không tự đặt lại cho “đẹp”.

### 4.1. Tại sao dùng BigDecimal?

Credit là một số decimal nghiệp vụ. `BigDecimal("10.25")` giữ đúng giá trị cần assert; dùng `double` rồi so trực tiếp có thể đưa lỗi biểu diễn nhị phân vào một bài kiểm thử vốn đang tập trung vào serialization.

### 4.2. Tại sao class và package quan trọng?

Java object serialization gắn với **class identity, stream class descriptor, UID và field descriptors**. Nếu V2 tùy ý đổi `org.example.lab.model.SavedCustomer` thành `org.example.app.Customer`, `ObjectInputStream` không tự suy ra đó là cùng schema. Có thể cần explicit migration reader/compatibility adapter hoặc giải pháp format độc lập tên Java class.

## 5. Phần A — Viết chương trình V1 sinh fixtures

Tạo file `v1-producer/src/org/example/lab/fixture/WriteFixtures.java`:

~~~java
package org.example.lab.fixture;

import java.io.ObjectOutputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.example.lab.model.SavedCustomer;

public final class WriteFixtures {
    private WriteFixtures() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: WriteFixtures <output-directory>");
        }

        Path output = Path.of(args[0]);
        Files.createDirectories(output);

        // Bốn bytes: 43 61 66 E9. Ký tự é là U+00E9.
        Files.write(
                output.resolve("name-v1-latin1.txt"),
                "Café".getBytes(StandardCharsets.ISO_8859_1)
        );

        // Dữ liệu tiếng Việt được lưu UTF-8 theo contract riêng.
        Files.write(
                output.resolve("name-v1-utf8.txt"),
                "Đặng Ánh".getBytes(StandardCharsets.UTF_8)
        );

        SavedCustomer legacy = new SavedCustomer(
                "000042",
                "Café",
                new BigDecimal("10.25")
        );

        try (ObjectOutputStream out = new ObjectOutputStream(
                Files.newOutputStream(
                        output.resolve("customer-v1.ser")))) {
            out.writeObject(legacy);
        }

        System.out.println(
                "Created V1 fixtures in " + output.toAbsolutePath()
        );
    }
}
~~~

Đoạn code cố tình sử dụng **encoding tường minh ngay ở V1** để fixtures có bytes xác định. Đây là bài tập tương thích dữ liệu, không dựa vào may rủi máy V1 hiện dùng default charset nào.

### 5.1. Biên dịch và chạy V1 trên JDK baseline

Ví dụ shell POSIX/Git Bash:

~~~bash
mkdir -p output/v1-classes output/generated-fixtures

javac --release 17 \
  -d output/v1-classes \
  v1-producer/src/org/example/lab/model/SavedCustomer.java \
  v1-producer/src/org/example/lab/fixture/WriteFixtures.java

java -cp output/v1-classes \
  org.example.lab.fixture.WriteFixtures \
  output/generated-fixtures
~~~

Ở bước này, đặt `JAVA_HOME` hoặc chọn executable để **cả `javac` và `java` thực sự là JDK baseline**. Dùng `java -version` và đường dẫn executable để xác nhận, không suy từ IDE settings.

Trên PowerShell, tạo thư mục bằng `New-Item -ItemType Directory -Force` và dùng cùng hai source paths theo cú pháp PowerShell; dấu `\` ở ví dụ trên là ký tự nối dòng cho shell POSIX, **không phải** ký tự nối dòng của PowerShell.

### 5.2. Bằng chứng phải lưu

Kiểm tra ba file tồn tại, ghi checksum:

~~~bash
sha256sum output/generated-fixtures/*
~~~

Nếu môi trường không có `sha256sum`, dùng công cụ hash sẵn có của hệ điều hành. Trong PowerShell có `Get-FileHash -Algorithm SHA256`. Hash giúp phát hiện fixture bị đổi khi checkout, transfer hoặc “cập nhật snapshot” vô ý.

Đối với Latin-1 fixture, bytes dự kiến:

~~~text
43 61 66 E9
 C  a  f  é
~~~

Trong UTF-8, `é` thường là bytes `C3 A9`. Đây là điểm khác biệt để test decoder.

### 5.3. Đóng băng fixture

Copy ba file đã tạo sang `v2-reader/src/test/resources/legacy/`. Lưu manifest/README bằng text:

~~~text
Fixture set: customer-v1
Producer application: lab V1
Producer JDK: baseline 17 (vendor/build cụ thể khi chạy thật)
Producer class: org.example.lab.model.SavedCustomer
Serialization UID: 1
Latin-1 file: ISO-8859-1, expected text "Café"
UTF-8 file: UTF-8, expected text "Đặng Ánh"
Serialized customer: id="000042", name="Café", credit="10.25"
SHA-256: ghi hash thực của từng file, không điền placeholder khi commit
Change control: không regenerate bằng reader V2
~~~

Đối với file text nếu repository có line-ending normalization, có thể cấu hình quy tắc Git attributes phù hợp để giữ bytes fixtures. Với binary `.ser`, phải đánh dấu là binary để không bị tool chỉnh nội dung.

## 6. Phần B — Tái hiện hồi quy charset

### 6.1. Code đọc sai

Trong Java, constructor:

~~~java
String decoded = new String(bytes);
~~~

dùng **default charset** của JVM. Nếu V1 ghi `0xE9` theo ISO-8859-1 nhưng V2 dùng UTF-8, byte đó đứng một mình **không phải chuỗi UTF-8 hợp lệ**. Tùy API, decoder có thể thay ký tự bằng `�` hoặc báo lỗi.

Một test chỉ so sánh “không ném exception” có thể xanh dù người dùng nhìn thấy tên bị lỗi dấu.

### 6.2. Code đọc đúng theo hợp đồng lưu trữ

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

byte[] bytes = Files.readAllBytes(
        Path.of("src/test/resources/legacy/name-v1-latin1.txt")
);

String decoded = new String(
        bytes,
        StandardCharsets.ISO_8859_1
);
~~~

Nếu file được ghi theo ISO-8859-1, việc chuyển JVM default sang UTF-8 không làm thay đổi giá trị đã giải mã.

### 6.3. Dùng decoder strict để phát hiện dữ liệu sai

`new String(bytes, StandardCharsets.UTF_8)` có thể thay các chuỗi byte lỗi bằng replacement characters, khiến data corruption không hiển thị dưới dạng exception. Với luồng dữ liệu cần toàn vẹn, dùng decoder:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String strictUtf8(byte[] bytes)
        throws CharacterCodingException {

    return StandardCharsets.UTF_8
            .newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
~~~

Với `name-v1-latin1.txt`, strict UTF-8 decode phải **báo lỗi**. Với `name-v1-utf8.txt`, nó phải trả về `Đặng Ánh`.

Điểm cần học: “bytes không phải UTF-8” **không tự có nghĩa dữ liệu hỏng**; nếu V1 contract là Latin-1, việc cố decode UTF-8 mới là lỗi của reader. Ngược lại, nếu contract là UTF-8, gặp malformed bytes phải có policy fail/quarantine/log, không tự giả định chuyển sang Latin-1 là an toàn.

## 7. Phần B — Viết test charset

Một test JUnit 5 có thể dùng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class CharsetRegressionTest {

    private byte[] fixture(String path) throws Exception {
        try (InputStream in = getClass().getResourceAsStream(path)) {
            assertNotNull(in, "Missing legacy fixture: " + path);
            return in.readAllBytes();
        }
    }

    @Test
    void latin1FixtureMustDecodeAsLatin1() throws Exception {
        byte[] bytes = fixture("/legacy/name-v1-latin1.txt");

        assertArrayEquals(
                new byte[]{0x43, 0x61, 0x66, (byte) 0xE9},
                bytes
        );

        String decoded = new String(
                bytes, StandardCharsets.ISO_8859_1
        );
        assertEquals("Café", decoded);
    }

    @Test
    void latin1FixtureIsNotValidUtf8() throws Exception {
        byte[] bytes = fixture("/legacy/name-v1-latin1.txt");

        var decoder = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        assertThrows(
                java.nio.charset.MalformedInputException.class,
                () -> decoder.decode(ByteBuffer.wrap(bytes))
        );
    }

    @Test
    void utf8FixtureKeepsVietnameseCharacters() throws Exception {
        byte[] bytes = fixture("/legacy/name-v1-utf8.txt");

        String decoded = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();

        assertEquals("Đặng Ánh", decoded);
    }
}
~~~

Ví dụ dùng `InputStream.readAllBytes()` (Java 9+) và `var` (Java 10+), phù hợp với lab Java 17/21. Khi dùng trên JDK cũ hơn, điều chỉnh API hoặc Java source level.

**Lưu ý:** test thứ hai cố ý assert lỗi UTF-8. Đây là **negative test PASS khi nhận đúng exception**, không phải bug của decoder.

### 7.1. Dấu hiệu regression cần ghi nhận

| Hiện tượng | Kết luận |
|---|---|
| Latin-1 decoded đúng thành `Café` | Reader đang dùng đúng codec |
| Latin-1 decoded thành `Caf�` | Reader decode sai hoặc thay malformed bytes |
| UTF-8 Vietnamese mất dấu | Encoding hoặc pipeline fixture không đúng |
| Một OS pass, OS khác fail | Có khả năng dùng default charset/source conversion |
| Test file đổi hash sau checkout | Artifact fixture không được bảo toàn bytes |

### 7.2. Không chỉ test với ASCII

Chuỗi `Hello123` có cùng bytes ở nhiều charset phổ biến; một test chỉ dùng ASCII **không phát hiện sai charset**. Nên có ký tự ngoài ASCII, ký tự tiếng Việt, dấu kết hợp Unicode, emoji nếu format hỗ trợ, và bytes invalid theo contract.

## 8. Phần C — Tái hiện hồi quy locale

**Locale** mô tả quy tắc ngôn ngữ/vùng khi case conversion, sorting, format số, format ngày, resource bundles và display text. Nó **không** là charset: một chuỗi Unicode có thể decode đúng nhưng vẫn bị normalize sai vì locale.

### 8.1. Bug: toUpperCase() không chỉ rõ locale

~~~java
String key = "id".toUpperCase();
~~~

Kết quả phụ thuộc `Locale.getDefault()`. Chẳng hạn với Turkish locale `tr-TR`, ký tự `i` khi viết hoa thành **`İ`** (Latin capital letter I with dot above), không phải `I`. Một identifier dùng làm key hoặc field name có thể không khớp hệ thống khác.

### 8.2. Sửa: dùng Locale.ROOT cho identifier độc lập ngôn ngữ

~~~java
import java.util.Locale;

String canonical = "id".toUpperCase(Locale.ROOT);
// "ID" theo một quy tắc ổn định cho identifier ngôn ngữ-độc lập.
~~~

Đừng áp `Locale.ROOT` cho mọi trường hợp: UI tiếng Thổ Nhĩ Kỳ nên có thể cần quy tắc `tr-TR`; tên người hoặc văn bản đa ngôn ngữ có chính sách riêng. Phân biệt **machine key** và **human-facing text**.

### 8.3. Viết test không thay global Locale

Một số bài test đổi `Locale.setDefault(...)` rồi quên restore, gây flakiness khi JUnit chạy song song. Thay vì sửa global mutable state, test với locale tường minh:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class LocaleRegressionTest {

    @Test
    void identifierIsStableAcrossLocale() {
        String raw = "id";

        assertEquals(
                "ID",
                raw.toUpperCase(Locale.ROOT)
        );

        assertEquals(
                "İD",
                raw.toUpperCase(
                        Locale.forLanguageTag("tr-TR"))
        );
    }

    @Test
    void machineIdentifierUsesRootLocale() {
        String raw = "invoice-id";
        String canonical = raw.toUpperCase(Locale.ROOT);

        assertEquals("INVOICE-ID", canonical);
    }
}
~~~

Test đầu cho thấy **các quy tắc locale khác nhau là hợp lệ**; nó không chứng minh Turkish locale sai. Regression xuất hiện khi code **không chỉ rõ locale** cho dữ liệu cần contract ổn định.

### 8.4. Cách tạo bài “fail first”

1. Viết implementation tạm dùng `raw.toUpperCase()`.
2. Chạy dưới default locale khác (ví dụ Turkish) trong process riêng.
3. Quan sát key mismatch.
4. Sửa implementation thành `toUpperCase(Locale.ROOT)` nếu field thuộc loại machine identifier.
5. Chạy lại dưới nhiều locale.

Với CI, có thể chạy test JVM bằng `-Duser.language=tr -Duser.country=TR` để chủ động phơi bày lỗi; điều này tác động **chỉ process được cấu hình**. Nếu build tool fork test JVM, phải truyền flags vào đúng test fork, không chỉ shell/daemon.

## 9. Locale trong số thập phân: format để đọc hay để hiển thị?

Một số số tiền:
- `1,234.50` thường phù hợp quy tắc tiếng Anh Mỹ.
- `1.234,50` thường phù hợp quy tắc tiếng Đức.

Nếu machine protocol chỉ cam kết dấu chấm cho decimal và không grouping, dùng **canonical decimal format**, ví dụ `BigDecimal.toPlainString()` và parser rõ. Không dùng `NumberFormat.getInstance()` không locale cho dữ liệu lưu lâu dài.

### 9.1. Test dùng DecimalFormatSymbols rõ ràng

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class DecimalLocaleTest {

    @Test
    void germanNumberHasExpectedDisplayFormat() {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY)
        );

        String displayed = format.format(
                new BigDecimal("1234.50")
        );

        assertEquals("1.234,50", displayed);
    }

    @Test
    void parseLegacyGermanDecimalFully() {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY)
        );
        format.setParseBigDecimal(true);

        String raw = "1.234,50";
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(raw, position);

        assertNotNull(parsed);
        assertEquals(raw.length(), position.getIndex());
        assertEquals(-1, position.getErrorIndex());
        assertInstanceOf(BigDecimal.class, parsed);
        assertEquals(
                0,
                ((BigDecimal) parsed).compareTo(
                        new BigDecimal("1234.50"))
        );
    }
}
~~~

**Vì sao dùng ParsePosition?** Một parser có thể chỉ đọc được một tiền tố hợp lệ rồi bỏ phần còn lại. Test đầy đủ chuỗi phải kiểm cả số ký tự đã tiêu thụ, không chỉ giá trị trả về.

### 9.2. UI formatting và wire format nên có chính sách khác

- **UI:** format phù hợp locale người dùng, nhưng test output có thể cần cập nhật có kiểm soát khi locale data/CLDR thay theo JDK.
- **Wire/data storage:** format độc lập locale, schema rõ, không phụ thuộc default.
- **Money:** ưu tiên `BigDecimal`/minor units với currency/scale/rounding policy.
- **Identifiers:** không được áp number formatting có grouping vào ID.

Tránh khẳng định mọi string do JDK format phải giống byte-for-byte qua mọi release. Nếu đó là hợp đồng xuất file, hãy đóng băng format và test cụ thể; nếu chỉ là UI display, xét mục tiêu người dùng và bản locale data mới.

## 10. Locale trong ngày giờ và timezone

Timezone và locale là **hai thứ khác nhau**:
- `Locale` ảnh hưởng cách trình bày tên tháng, thứ, dấu phân cách theo ngôn ngữ.
- `ZoneId` ảnh hưởng cách chuyển instant thành ngày/giờ ở một khu vực.
- `Instant` là mốc thời gian, không chứa timezone địa phương.
- `LocalDateTime` không biểu diễn một instant nếu thiếu zone/offset.

### 10.1. Dữ liệu máy cần định dạng thời gian ổn định

~~~java
import java.time.Instant;
import java.time.format.DateTimeFormatter;

Instant timestamp = Instant.parse(
        "2024-10-26T14:30:00Z"
);

String encoded = DateTimeFormatter.ISO_INSTANT
        .format(timestamp);
~~~

Nếu protocol dùng ISO instant, test so đúng contract `2024-10-26T14:30:00Z`. Nếu dữ liệu là cuộc hẹn theo giờ địa phương, không được tự chuyển tất cả thành UTC mà bỏ mất timezone region/business semantics.

### 10.2. Sử dụng locale tường minh cho tên tháng

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate date = LocalDate.of(2024, 10, 26);

String english = date.format(
        DateTimeFormatter.ofPattern(
                "d MMM yyyy", Locale.ENGLISH
        )
);
~~~

String output có thể chịu ảnh hưởng phiên bản locale data của JDK. Nếu format hiển thị là part of public contract, cần có tests theo JDK target và quyết định về backward compatibility. Với machine protocols, dùng ISO formats hoặc formatter với symbols/schema được cố định.

### 10.3. Đừng dựa vào ngày hiện tại

Test kiểu:

~~~java
assertEquals(
        "2026-11-12",
        java.time.LocalDate.now().toString()
);
~~~

sẽ thất bại theo thời gian hoặc timezone. Inject `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Clock clock = Clock.fixed(
        Instant.parse("2026-11-12T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);

LocalDate date = LocalDate.now(clock);
~~~

Đây là cách cố định đầu vào test, không phải lời khuyên dùng cố định thời gian trong production.

## 11. Phần D — Định nghĩa model V2 để đọc Java serialization cũ

V2 vẫn dùng fully-qualified name `org.example.lab.model.SavedCustomer` nhưng có thêm trường mới `segment`.

Tạo file `v2-reader/src/main/java/org/example/lab/model/SavedCustomer.java`:

~~~java
package org.example.lab.model;

import java.io.Serial;
import java.io.Serializable;
import java.math.BigDecimal;

public final class SavedCustomer implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String customerId;
    private String displayName;
    private BigDecimal credit;

    // Trường mới không tồn tại trong stream V1.
    private String segment;

    public String getCustomerId() {
        return customerId;
    }

    public String getDisplayName() {
        return displayName;
    }

    public BigDecimal getCredit() {
        return credit;
    }

    public String getSegment() {
        // Field mới được deserialize từ stream V1 sẽ là null.
        return segment == null ? "LEGACY" : segment;
    }
}
~~~

**Lưu ý:** `ObjectInputStream` khôi phục fields theo Java serialization protocol; nó **không gọi constructor thông thường của serializable class** khi khôi phục chính phần serializable state. Vì vậy, đặt default vào constructor mới không phải cách đáng tin để điền field chưa có trong stream V1.

Trong ví dụ, getter áp chính sách mặc định `LEGACY`. Hệ thống thật có thể cần migration adapter hoặc `readObject` tùy semantics; không nên âm thầm cho field mới default nếu nó ảnh hưởng quyền truy cập hoặc trạng thái giao dịch.

### 11.1. Điều kiện nào giúp V1 stream đọc được bằng V2?

- Class name/package vẫn tương ứng.
- `serialVersionUID` tương thích.
- Những thay đổi field không phá các quy tắc serialization compatibility.
- Các referenced classes trong object graph vẫn nạp được.
- Classloader/module/security policy cho phép đường đọc cần thiết.
- Ý nghĩa business fields cũ không bị đổi.
- New fields vắng trong stream cũ có policy xử lý.

Giữ `serialVersionUID` không bảo đảm mọi thay đổi class đều tương thích; nó chỉ là **một phần của cơ chế kiểm tra**.

## 12. Phần D — Test V2 đọc stream V1

Tạo test `v2-reader/src/test/java/org/example/lab/LegacyCompatibilityTest.java`:

~~~java
package org.example.lab;

import static org.junit.jupiter.api.Assertions.*;

import java.io.InputStream;
import java.io.ObjectInputStream;
import java.math.BigDecimal;
import org.example.lab.model.SavedCustomer;
import org.junit.jupiter.api.Test;

class LegacyCompatibilityTest {

    @Test
    void readsSerializedCustomerFromV1() throws Exception {
        try (InputStream raw = getClass().getResourceAsStream(
                "/legacy/customer-v1.ser")) {

            assertNotNull(raw, "Missing immutable V1 fixture");

            try (ObjectInputStream input =
                    new ObjectInputStream(raw)) {

                Object decoded = input.readObject();

                assertInstanceOf(SavedCustomer.class, decoded);
                SavedCustomer customer = (SavedCustomer) decoded;

                assertEquals(
                        "000042",
                        customer.getCustomerId()
                );
                assertEquals(
                        "Café",
                        customer.getDisplayName()
                );
                assertEquals(
                        0,
                        customer.getCredit().compareTo(
                                new BigDecimal("10.25"))
                );
                assertEquals(
                        "LEGACY",
                        customer.getSegment()
                );
            }
        }
    }
}
~~~

Test này chỉ đọc một **binary fixture tin cậy do chính V1 của bài thực hành tạo ra**. Native deserialization không được áp dụng tùy tiện cho bytes đến từ network/đối tác; xem phần bảo mật bên dưới.

### 12.1. Một bài negative test có chủ đích

Thử sửa **bản sao** của V2:

~~~java
@Serial
private static final long serialVersionUID = 2L;
~~~

Chạy lại reader trên `customer-v1.ser`. Thông thường sẽ gặp `InvalidClassException` vì UID class local khác stream. Đây là bằng chứng điều kiện compatibility bị phá, **không** phải lý do để tự đổi lại UID của tất cả classes một cách máy móc.

Sau khi quan sát, khôi phục `1L` và test lại. Không sửa fixture V1 để làm test pass.

### 12.2. Một bài negative test khác: đổi package

Nếu đổi model V2 thành `org.example.lab.v2.SavedCustomer` mà không có code migration, stream V1 vẫn tham chiếu `org.example.lab.model.SavedCustomer`. Khi class cũ không còn khả dụng, reader có thể báo `ClassNotFoundException`. Đổi tên package là thay đổi cấu trúc class, không phải một thay đổi field bình thường.

Trong hệ thật có thể dùng migration reader/class resolver được thiết kế rõ, nhưng không nên dùng class name alias tùy tiện cho bytes không tin cậy.

## 13. Bảo mật: Java deserialization chỉ với dữ liệu tin cậy

`ObjectInputStream` có lịch sử rủi ro khi đọc object graph không tin cậy: classpath có thể chứa loại đối tượng không mong đợi, và một số gadget chains từng dẫn đến khai thác. Vì vậy:

- Trong lab, chỉ đọc **synthetic fixture V1 đã kiểm checksum**.
- Không đặt native Java serialization ở biên nhận input public mới.
- Với hệ thống cần tiếp tục đọc stream cũ, xem threat model, nguồn dữ liệu, kích thước, types và filter policy.
- Java có `ObjectInputFilter` (JEP 290) và cơ chế filter context liên quan (JEP 415) cho các trường hợp hỗ trợ.
- Xây allowlist phù hợp với object graph, giới hạn depth/references/bytes khi có thể.
- Kiểm tra rằng các filters thật sự được áp dụng trong runtime/reader.
- Không coi filter là giải pháp duy nhất thay cho giảm bề mặt deserialization.
- Ưu tiên format có schema rõ và stable identity khi thiết kế lưu trữ lâu dài.

### 13.1. Test dữ liệu hỏng khác test dữ liệu không đáng tin

Một stream bị cắt byte có thể gây `EOFException` hoặc `StreamCorruptedException`. Test trường hợp này giúp kiểm error handling, nhưng **không chứng minh ứng dụng an toàn trước mọi payload độc hại**.

Với dữ liệu lưu trữ quan trọng:
- Khi parse fail, ghi record ID/format version dạng đã kiểm soát, không log toàn bộ payload.
- Quarantine để điều tra, không tự thay object thành mặc định thành công.
- Không làm side effects hoặc cập nhật state trước khi xác thực tính đúng đắn.
- Cung cấp metrics cho failure counts và migration progress.

## 14. Cách cấu hình Maven/JUnit cho V2

Nếu dùng Maven, một cấu hình `v2-reader/pom.xml` có thể như sau. Các số phiên bản là **ví dụ pin để có bài lab tái lập**, không ngụ ý phiên bản mới nhất.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.lab</groupId>
    <artifactId>legacy-reader-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <useModulePath>false</useModulePath>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Biểu thức Maven `${junit.version}` lấy phiên bản từ thuộc tính `junit.version` được khai báo phía trên, nên đoạn XML có thể được sao chép trực tiếp. Với dự án thực tế, nên ưu tiên phiên bản thư viện và plugin đã được pin theo dependency management của tổ chức.

Để tự chạy test theo môi trường, từ thư mục V2:

~~~bash
cd v2-reader
mvn test
~~~

**Trong quy trình Worker STEP 4, không thực thi lệnh này; đây là hướng dẫn cho người học ở bài thực hành.** Những test đã tạo cần nằm dưới `src/test/java` và fixture dưới `src/test/resources`. Nếu build tool không dùng Maven, giữ nguyên ý tưởng fixtures và assertions rồi dịch cấu hình test sang Gradle.

### 14.1. Kiểm test runner thực sự thực thi

Một báo cáo `BUILD SUCCESS` không đủ nếu test count là 0. Xác minh Surefire/JUnit reports có:
- Test classes được discover.
- Số test executed.
- Không có unexpectedly skipped tests.
- JDK của test fork.
- Failures được giữ, không tự động retry vô hạn đến khi xanh.

## 15. Ma trận chạy giữa JDK baseline và target

Một kế hoạch minh họa:

| Producer | Reader | File/source | Kỳ vọng |
|---|---|---|---|
| V1 / JDK 17 | V1 / JDK 17 | Fixtures được tạo | Baseline control |
| V1 / JDK 17 | V2 / JDK 17 | Latin-1, UTF-8, `.ser` | PASS nếu V2 vẫn hỗ trợ Java 17 |
| V1 / JDK 17 | V2 / JDK 21 | Cùng fixtures, **không regenerate** | **Bắt buộc PASS** |
| V2 / JDK 21 | V2 / JDK 21 | Dữ liệu V2 mới | Regression bình thường |
| V2 / JDK 21 | V1 / JDK 17 | Dữ liệu V2 | Chỉ bắt buộc nếu rollback/mixed version cần |

**Không ép test tổ hợp không được framework/library hỗ trợ**. Nếu V2 chỉ hỗ trợ JDK 21, bỏ ô V2 trên JDK 17 và ghi lý do. Nếu dự án vẫn cần rollback về V1 trong rolling deployment, kiểm thêm **old reader/new writer**; chỉ V2 đọc V1 chưa đủ chứng minh rollback an toàn.

### 15.1. Phải phân biệt ba loại kết quả

- **PASS:** chạy và assert đúng business contract.
- **FAIL:** xác nhận regression hoặc dữ liệu không còn tương thích.
- **BLOCKED:** không thể chạy do môi trường/test infrastructure chưa đáp ứng; chưa có bằng chứng tương thích.

Không báo PASS nếu fixture bị thiếu, test runner chạy 0 tests hoặc test bị skip.

## 16. Thực hành “fail first, fix, lock”

Để hiểu tại sao regression tests có giá trị, làm theo một chuỗi có chủ đích.

### Bài 1: Lỗi charset

1. Dùng V1 tạo `name-v1-latin1.txt` với bytes `43 61 66 E9`.
2. Trong V2, thử code sai `new String(bytes)`.
3. Quan sát dưới JDK default UTF-8: kết quả không còn là `Café` hoặc có replacement character.
4. Viết test phải trả về `Café`.
5. Sửa reader dùng `ISO_8859_1` cho format legacy đã biết.
6. Thêm negative test strict UTF-8 trên Latin-1 bytes.
7. Chạy lại trên JDK target và ghi checksum fixture.

**Tiêu chí:** code đúng không phụ thuộc default charset của máy chạy.

### Bài 2: Lỗi locale

1. Chọn identifier `id`.
2. Thử chuyển upper-case với English và Turkish locale.
3. Tạo case thất bại khi application dựa vào default locale.
4. Định nghĩa machine canonicalization dùng `Locale.ROOT`.
5. Test `ID` trên nhiều locale.
6. Tách bài test UI formatting khỏi machine protocol.

**Tiêu chí:** identifier lưu trữ/trao đổi có format ổn định; text hiển thị vẫn dùng locale theo yêu cầu người dùng.

### Bài 3: Lỗi serialization UID

1. Tạo `customer-v1.ser` từ V1 với UID 1.
2. V2 đọc và assert ID, name, credit và field mới default.
3. Trong một bản sao của V2, đổi UID thành 2.
4. Quan sát lỗi `InvalidClassException`.
5. Khôi phục UID 1.
6. Thử đổi package để thấy class identity quan trọng.
7. Ghi ra kết luận giới hạn compatibility.

**Tiêu chí:** V2 đọc stream V1 mà không regenerate; việc thêm field mới không làm sai business semantics.

### Bài 4: Thêm unknown/invalid inputs

1. Tạo fixture byte sequence lỗi hoặc file bị cắt riêng trong bộ test.
2. Assert reader trả lỗi có kiểm soát.
3. Không fallback sang một object “hợp lệ” giả.
4. Không log full raw serialized payload.
5. Nếu dùng filter, viết test chứng minh filter được áp dụng.

**Tiêu chí:** dữ liệu hỏng bị phát hiện và không tạo side effect nghiệp vụ.

## 17. Mở rộng: phát hiện hồi quy khi format là JSON

Không phải mọi ứng dụng dùng native `Serializable`; nhiều hệ dùng JSON/Jackson để lưu object. JSON không dùng Java `serialVersionUID`, nhưng vẫn có thể thay đổi giữa versions do:
- Naming strategy chuyển camelCase thành snake_case.
- Include/exclude null fields.
- Default values và missing fields.
- Enum representation.
- Numeric precision.
- Date/time formatting và timezone.
- Polymorphic type information.
- Jackson module registration và framework auto-configuration.

Một fixture V1:

~~~json
{
  "customerId": "000042",
  "displayName": "Café",
  "credit": "10.25",
  "status": "ACTIVE",
  "createdAt": "2024-10-26T21:30:00+07:00"
}
~~~

Khi V2 đọc, assert:
- ID `000042` vẫn là chuỗi, không mất zeros.
- Tên Unicode đúng.
- Credit dùng decimal semantics, không bị làm tròn do `double`.
- Status map đúng.
- Timestamp giữ đúng instant/offset contract.
- Field V1 thiếu ở schema V2 được xử lý theo policy.

Nếu V2 đọc JSON cũ rồi ghi lại, và V1 vẫn phải đọc được bản ghi đó trong rollback window, cần test **old reader/new writer** riêng.

### 17.1. Không regenerate “golden JSON” bằng V2

Một lỗi thường gặp: khi test snapshot fail, chạy “update snapshots” rồi commit giá trị mới. Cách đó có thể hợp thức hóa việc mất field hoặc đổi timezone.

Muốn đổi contract:
- Ghi version format mới.
- Giữ fixture V1 cho support window.
- Có expected semantics được review.
- Test adapter V1→V2.
- Chỉ loại contract cũ khi retention/rollback policy cho phép.

## 18. Phân biệt charset, locale và serialization khi điều tra

Ba nhóm có triệu chứng chồng nhau nhưng tầng nguyên nhân khác nhau.

| Triệu chứng | Charset | Locale | Serialization |
|---|---|---|---|
| `Café` thành `Caf�` | **Rất có thể** | Ít khả năng | Có thể nếu stream/string layer bị đổi |
| `id` thành `İD` | Không | **Case conversion theo tr-TR** | Chỉ khi code chuyển đổi sau đọc |
| `InvalidClassException` | Không phải nguyên nhân chính | Không | **UID/class compatibility** |
| JSON parse được nhưng amount sai | Có thể nếu bytes lỗi | Có thể do number parsing | Business mapper/codec có thể liên quan |
| Date hiển thị khác | Có thể nếu text encoding sai | Locale và timezone | Formatter sau deserialize |
| `ClassNotFoundException` khi đọc `.ser` | Không | Không | Class identity/classpath |
| Chỉ fail trên Linux CI | Default charset/bytes | Locale/timezone | Classpath/JDK/config cũng có thể |
| Trả về null ở field mới | Không điển hình | Không điển hình | Field absent khi deserialize hoặc JSON mapping |

**Không chữa mọi lỗi bằng thay default charset hoặc đổi locale toàn JVM.** Xác định dữ liệu gốc là bytes gì, reader nào diễn giải, business contract nào phải giữ.

## 19. Thu bằng chứng thực nghiệm để chẩn đoán

Một failure report nên gồm:
- Producer tag, commit, JDK vendor/build.
- Reader tag, JDK vendor/build.
- Fixture name, hash, format và declared charset.
- Test name, stack trace hoặc actual/expected values.
- Locale ID/timezone/charset của process test.
- Serializer provider/dependency versions.
- Class/package/`serialVersionUID` nếu là Java stream.
- Whether running local, CI or container.
- Có regeneration/normalization nào làm đổi bytes không?

Ví dụ một báo cáo ngắn:

~~~text
TEST: legacyLatin1MustDecode
PRODUCER: customer-v1, JDK baseline
READER: customer-v2, JDK target
FIXTURE: name-v1-latin1.txt
DECLARED CHARSET: ISO-8859-1
EXPECTED: "Café"
ACTUAL: "Caf�"
ROOT CAUSE: decoder dùng default UTF-8 thay vì ISO-8859-1
FIX: explicit charset per format
REGRESSION: strict decode + golden fixture SHA-256
~~~

Nếu lỗi xảy ra chỉ trong CI, xem thêm `java -version` của **test fork** và liệu fixtures bytes có bị Git/process encoding chuyển đổi không.

## 20. Test data integrity và semantic invariants

Kiểm thử không chỉ xác nhận parser đọc được:

| Invariant | Kiểm tra |
|---|---|
| ID | `000042` giữ leading zeros |
| Name | `Café` và `Đặng Ánh` không mất dấu |
| Money | `BigDecimal("10.25")` giữ giá trị chính xác |
| Segment | Dữ liệu V1 vắng field mới có default được định nghĩa |
| Status | Unknown enum không tự map thành success |
| Date/time | Giữ instant hoặc local semantics theo contract |
| Format version | Decoder chọn đúng format/charset |
| Class identity | Java stream nạp được class tương thích |
| Integrity | Invalid bytes không tạo object nghiệp vụ giả |
| Security | Không mở deserialization của arbitrary classes |
| Retention | Đọc được những generations còn trong support window |

Đặc biệt với dữ liệu tài chính và identity, **“không exception” không phải PASS** nếu decoded value sai.

## 21. Khi nào dùng migration adapter thay vì giữ format cũ?

Không phải lúc nào V2 cũng nên tiếp tục đọc trực tiếp native Java serialization V1 mãi mãi. Nếu cần hỗ trợ nhiều năm, định dạng gắn với Java class names/UID gây khó khăn khi đổi package, module và dependency.

Một hướng có kiểm soát:

~~~text
Legacy V1 stream
       |
       v
Dedicated trusted migration reader
       |
       v
Stable domain data transfer object
       |
       v
Versioned JSON/Avro/Protobuf/DB representation
       |
       v
New application readers
~~~

Để chuyển an toàn:
1. Xác định tất cả objects và versions cần đọc.
2. Đọc bằng runtime/classpath có hỗ trợ V1 với dữ liệu tin cậy.
3. Chuẩn hóa thành domain model trung lập.
4. Ghi format mới có schema/version rõ.
5. Assert business invariants trước/sau.
6. Ghi provenance, checksum và error counts.
7. Rehearse rollback/forward-only strategy.
8. Chỉ loại V1 reader khi hết retention hoặc migrate xong.

Nếu stream cũ có rủi ro deserialization, migration reader cần được cô lập/quản lý quyền phù hợp; **không** đưa một general-purpose deserializer ra biên nhận input công khai.

## 22. Khi chạy trên CI hoặc container

Một bài lab pass local có thể fail CI vì:
- Test đang chạy JDK khác.
- File fixture không được copy vào test resources.
- Default charset/locale khác.
- Filename case khác trên Linux.
- Git line endings làm đổi bytes.
- Maven/Gradle test JVM bị cấu hình khác.
- CI có cache generated fixtures cũ.
- Test đổi `Locale.setDefault` gây race với test khác.
- Docker image không chứa resources.
- Jackson/serializer versions khác do dependency resolution.

### 22.1. Ma trận kiểm soát môi trường

| Biến | Cách xác nhận |
|---|---|
| JDK | In vendor/runtime version của test JVM |
| Charset | `Charset.defaultCharset()` để chẩn đoán, không làm test phụ thuộc |
| Locale | `Locale.getDefault()` và locale sử dụng trong code |
| Timezone | `ZoneId.systemDefault()` và business ZoneId |
| Fixture bytes | SHA-256 so với manifest |
| Test resources | `getResourceAsStream` không null |
| Classpath | `SavedCustomer.class.getName()` và dependency versions |
| Test execution | JUnit reports có đúng số lượng test |
| Docker image | Digest, JDK, copied resources |
| Build tool | Maven/Gradle wrapper + resolved dependency graph |

### 22.2. Không sửa bug bằng cách ép default toàn JVM

Các flags như `-Dfile.encoding=UTF-8`, `-Duser.language=en` hoặc `-Duser.timezone=UTC` có thể hữu ích để chuẩn hóa môi trường, nhưng **không thay thế việc đọc legacy format bằng đúng charset/locale/timezone contract**. Nếu nguồn dữ liệu thật là ISO-8859-1, ép UTF-8 cho cả JVM không làm bytes gốc thành UTF-8.

Có thể dùng ma trận locale/timezone để **phơi bày bug**, rồi sửa code bằng explicit encoding/Locale/Clock khi phù hợp.

## 23. Bài thực hành nâng cao: tách kiểm thử theo ba tầng

Một bộ kiểm thử tốt có thể gồm:

**Tầng 1 – Byte-level:**
- Hash của fixture.
- Những bytes đặc trưng `E9`, UTF-8 `C3 A9`.
- Strict decoder malformed input.

**Tầng 2 – Type-level:**
- Java `SavedCustomer` deserialize đúng.
- UID/class identity giữ compatible.
- DTO JSON mapping đúng typed fields.
- BigDecimal/date/time không mất precision.

**Tầng 3 – Business-level:**
- Customer ID không đổi.
- Dữ liệu khách hàng có dấu không bị hỏng.
- Credit vẫn đúng.
- Field V1 thiếu không bị hiểu thành “được ưu đãi” hoặc trạng thái sai.
- Error inputs bị chặn hoặc quarantine theo policy.

Nếu chỉ có tầng 1, có thể bytes đúng nhưng business mapping sai. Nếu chỉ có tầng 3, khi fail có thể khó biết lỗi do codec hay logic. **Cả ba tầng giúp chẩn đoán có bằng chứng**.

## 24. Bài thực hành nâng cao: old reader/new writer

Giả sử V2 thêm `segment` nhưng vẫn cần rollback về V1. Câu hỏi mới: V1 có đọc được stream do V2 ghi?

Trong Java serialization, thêm field cùng `serialVersionUID` có thể cho phép old reader bỏ qua field mới theo quy tắc compatibility tương ứng, **nhưng không đủ để bảo đảm business semantics hoặc mọi thay đổi class đều an toàn**.

Cách kiểm:
1. Viết V2 writer tạo `customer-v2.ser` từ một object có trường mới.
2. Khởi động V1 reader bằng classpath/runtime V1 thật.
3. Đọc fixture V2.
4. Assert những fields V1 dùng.
5. Đánh giá có semantics V2 nào V1 không hiểu.
6. Nếu một chi phí/semantic field mới là bắt buộc cho correctness, không tuyên bố rollback safe chỉ vì `ObjectInputStream` không exception.

Cửa sổ rollback nên được định nghĩa theo rollout plan. Nếu dữ liệu V2 không thể được V1 đọc, cần **forward-only cutover hoặc migration plan** có phê duyệt thay vì hứa rollback toàn phần.

## 25. Troubleshooting cho những failure thường gặp

| Lỗi/triệu chứng | Chẩn đoán | Hướng khắc phục |
|---|---|---|
| Latin-1 xuất `�` | Đọc sai charset | Explicit legacy charset |
| `MalformedInputException` | Bytes không hợp encoding được chọn | Đọc theo format contract hoặc quarantine |
| `UnmappableCharacterException` | Decoder không map được byte sequence | Xác định charset/nguồn dữ liệu |
| Key khác trên CI Turkish | Default locale | Machine key dùng `Locale.ROOT` |
| Số `1.234,50` parse sai | Locale/decimal symbols | Explicit parser + full consumption |
| Tên tháng khác trên JDK | Locale data/CLDR đổi | Chốt UI policy hoặc canonical wire format |
| Ngày lệch một ngày | Timezone/default clock | Explicit ZoneId/Clock |
| `InvalidClassException` | UID/field/class incompatibility | Phân tích stream/class V1–V2 |
| `ClassNotFoundException` | Class/package cũ không còn | Versioned reader/adapter |
| Field mới trả null | Field vắng trong V1 stream | Default/migration semantics rõ |
| Serialized fixture thiếu | Test resource không được copy | Kiểm `src/test/resources` |
| Fixture hash đổi | Text conversion/regeneration | Khôi phục immutable fixture |
| Build pass nhưng 0 tests | Test runner/discovery lỗi | Kiểm Surefire/Gradle/JUnit |
| Parse pass nhưng số dư sai | Business mapping/precision | BigDecimal/invariant assertions |
| Native deserialize input lạ | Security risk | Trusted source, filters, isolation |
| V2 đọc V1, V1 không đọc V2 | Chưa bảo đảm rollback | Cross-version matrix/forward-only policy |

Đừng xử lý một lỗi đọc dữ liệu bằng cách xóa fixture bị lỗi. Thường đó chính là mẫu có giá trị phát hiện regression.

## 26. Những sai lầm thường gặp khi làm lab

- Tạo golden fixture bằng V2, rồi gọi đó là legacy fixture.
- Thay đổi fixture mỗi khi test fail mà không review contract.
- Chỉ dùng ASCII và kết luận charset tương thích.
- Dùng `new String(bytes)` với default charset cho file có format lâu dài.
- Dùng lossy decoder rồi chỉ assert “không exception”.
- Dùng `String.toUpperCase()` không locale cho identifier.
- Ép `Locale.ROOT` lên mọi text UI mà không xét ngôn ngữ người dùng.
- Dùng `double` cho amount và mất decimal precision.
- Test `LocalDate.now()` theo ngày cố định mà không inject Clock.
- Coi timezone và locale là một khái niệm.
- Giữ `serialVersionUID` giống nhau rồi cho rằng class tùy ý thay đổi vẫn đọc được.
- Đổi UID để “chữa” `InvalidClassException` mà không hiểu schema.
- Đổi package của class rồi mong object stream tự map.
- Đọc native Java serialization của bytes không tin cậy.
- Chỉ assert object không null, không kiểm business fields.
- Bỏ qua field mới null khi đọc V1 stream.
- Coi V2-read-V1 PASS là bằng chứng V1-read-V2 PASS.
- Không lưu hash/provenance của fixtures.
- Quên kiểm JDK thực sự chạy test fork.
- Bỏ qua tests bị skip hoặc pipeline chạy 0 tests.
- Sửa CI bằng cách đổi default charset toàn hệ thống mà không hiểu format cũ.
- Không xét retention/replay/rollback window khi bỏ legacy reader.

## 27. Checklist kết quả phải nộp

- [ ] Producer V1 được biên dịch/chạy bằng JDK baseline thực.
- [ ] Ba fixtures đã tạo và có checksum.
- [ ] Fixture text Latin-1 có bytes `43 61 66 E9`.
- [ ] Fixture UTF-8 bảo toàn tiếng Việt `Đặng Ánh`.
- [ ] V2 giải mã đúng Latin-1 bằng charset tường minh.
- [ ] Negative test báo lỗi khi strict UTF-8 đọc Latin-1 bytes.
- [ ] Không có code mới phụ thuộc default charset cho format đã biết.
- [ ] Identifier `id` được chuẩn hóa đúng bằng `Locale.ROOT`.
- [ ] Có thử khác biệt Turkish locale có chủ đích.
- [ ] Decimal/date formatting có contract và locale rõ.
- [ ] V2 `SavedCustomer` có UID/class identity compatible.
- [ ] V2 đọc được `customer-v1.ser` do V1 tạo.
- [ ] Assert ID giữ leading zeros và credit giữ decimal value.
- [ ] Field V2 mới có semantics rõ khi vắng trong stream V1.
- [ ] Đã quan sát failure khi UID sai trong bản sao thử nghiệm.
- [ ] Native deserialization chỉ dùng synthetic/trusted fixture.
- [ ] Có test lỗi/hỏng dữ liệu với error handling an toàn.
- [ ] Test resources được đưa vào artifact/test classpath.
- [ ] CI chạy đúng test count trên JDK mục tiêu.
- [ ] Có ma trận old-writer/new-reader và khi cần old-reader/new-writer.
- [ ] Không regenerate fixtures sau khi test fail.
- [ ] Có báo cáo PASS/FAIL/BLOCKED với environment metadata.

## 28. Mẫu báo cáo hoàn thành bài thực hành

~~~text
Lab: Charset / Locale / Serialization Regression
Baseline producer: V1, JDK 17 (vendor/build = ...)
Candidate reader: V2, JDK 21 (vendor/build = ...)
Fixture manifest: checksum + producer source revision

1. Latin-1 customer text:
   V2 decode = Café
   Strict UTF-8 rejects legacy Latin-1 bytes
   Status: PASS / FAIL / BLOCKED

2. UTF-8 Vietnamese:
   V2 decode = Đặng Ánh
   Status: PASS / FAIL / BLOCKED

3. Locale-independent identifier:
   ROOT: id -> ID
   Turkish: id -> İD
   Machine contract remains ID
   Status: PASS / FAIL / BLOCKED

4. V1 Java serialized object:
   customerId=000042, displayName=Café, credit=10.25
   new segment=LEGACY
   Status: PASS / FAIL / BLOCKED

5. Negative UID test:
   V2 temporary UID mismatch produces InvalidClassException
   Restored UID 1 reads V1 stream
   Status: PASS / FAIL / BLOCKED

Environment:
   JDK vendor/build, OS/arch, test runner, locale,
   timezone, charset, artifact hash, fixture hashes

Remaining risks:
   old-reader/new-writer compatibility?
   untrusted deserialization?
   extra historical producers or formats?
Decision:
   Accept / Fix / Block rollout, with owner and evidence
~~~

Điền giá trị bằng **kết quả chạy thực**, không coi bảng mẫu là kết quả đã xác minh. Nếu không có V1 binary/provenance, phải ghi rõ thiếu bằng chứng legacy compatibility.

## 29. Câu hỏi tự kiểm tra

1. Vì sao một file ASCII đơn giản không đủ để phát hiện regression charset?
2. Nếu `0xE9` được ghi theo ISO-8859-1, tại sao UTF-8 strict decoder phải reject?
3. Khi nào nên dùng `Locale.ROOT`, khi nào nên dùng locale của người dùng?
4. Vì sao `Locale.setDefault` trong một test chạy song song có thể gây flakiness?
5. Tại sao cần kiểm `ParsePosition` khi đọc số locale-specific?
6. Vì sao thay `serialVersionUID` thành một giá trị mới có thể làm stream cũ lỗi?
7. Khi thêm field V2, giá trị nào xuất hiện nếu V1 stream không chứa field đó?
8. Vì sao giữ UID không đủ nếu package/class name bị đổi?
9. Tại sao native Java deserialization không nên dùng cho input tùy ý từ network?
10. Vì sao V2 vừa ghi vừa đọc PASS không chứng minh old-data compatibility?
11. Kết quả nào cần thêm để chứng minh rollback được khi V1/V2 cùng chạy?
12. Nếu test pass local nhưng CI fail, những metadata nào giúp phân biệt lỗi JVM với fixture bị thay bytes?

Gợi ý trọng tâm: mọi câu trả lời nên liên hệ **bytes/schema gốc, reader semantics, phạm vi hợp đồng và bằng chứng thí nghiệm**, không chỉ nêu một API name.

## 30. Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset trong JDK hiện đại và tác động tới code thiếu encoding tường minh.
- [Java Charset API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html): charsets, encoders và decoders.
- [CharsetDecoder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed/unmappable handling và `CodingErrorAction`.
- [Locale API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): locale semantics và default locale.
- [DecimalFormat API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): localized decimal formats và parser.
- [Java Time API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html): `Instant`, `Clock`, `ZoneId`, `DateTimeFormatter`.
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html): class descriptors, UID, field compatibility.
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): hạn chế input deserialization.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter theo ngữ cảnh.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions, test discovery và lifecycle.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): chạy JUnit tests trong Maven.

Các tài liệu “current/latest” có thể khác release đang được pin. Với dự án thật, chọn tài liệu **theo JDK vendor/build, framework, serializer và test tool versions** đang dùng. Kết quả thử nghiệm cần ưu tiên evidence từ fixtures và runtime thực.

## 31. Kết luận

**Phát hiện hồi quy charset, locale và dữ liệu tuần tự hóa đòi hỏi kiểm đúng chiều: phiên bản cũ ghi, phiên bản mới đọc và giữ nguyên ý nghĩa nghiệp vụ.** Một vòng round-trip của V2 không đủ. Hãy tạo fixtures V1 bất biến có checksum, test với bytes ngoài ASCII, đặt charset/locale tường minh cho các machine formats và kiểm serialization class identity, `serialVersionUID`, fields cũ/mới và an toàn deserialization.

Quy trình thực hành là **tạo dữ liệu từ V1 → đóng băng fixtures → viết negative/positive tests → chạy reader V2 trên JDK đích → phân loại lỗi ở tầng bytes/locale/schema → sửa code và xác minh lại → ghi ma trận tương thích/rollback**. Khi những bài kiểm thử đó chạy thường xuyên trong CI, thay JDK, framework hay serializer sẽ ít có nguy cơ biến dữ liệu lịch sử thành giá trị sai mà hệ thống vẫn âm thầm chấp nhận.
