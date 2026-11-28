# Chuẩn hóa báo cáo gồm môi trường, cấu hình, đầu vào, kỳ vọng, kết quả và bằng chứng byte hoặc ngoại lệ

## 1. Vì sao bài kiểm chứng cần một báo cáo có thể tái hiện?

Một dòng log `PASS` hoặc ảnh chụp màn hình “chạy thành công” không đủ để người khác xác nhận **điều gì đã được kiểm thử**, chạy trên JDK nào, với byte đầu vào nào, và liệu kết quả có phù hợp với **hợp đồng API** hay chỉ phù hợp với một tình huống tình cờ.

Trong Java 18 và các JDK hiện đại, cùng một ứng dụng có thể liên quan đến nhiều ranh giới:

- **Mã hóa văn bản:** JEP 400 đưa UTF-8 thành default charset thông thường của các API Java SE phụ thuộc charset mặc định, nhưng không tự chuyển đổi file đã lưu.
- **Simple Web Server:** JEP 408 cung cấp công cụ phục vụ file tĩnh để phát triển/kiểm tra; HTTP status, header và byte phản hồi phải được kiểm chứng độc lập.
- **Javadoc:** JEP 413 cho phép đưa code snippet vào tài liệu; mã được trích dẫn và thao tác tạo tài liệu cần được kiểm tra.
- **Reflection và MethodHandle:** JEP 416 thay đổi cách triển khai core reflection; hợp đồng quyền truy cập, lookup mode và exception vẫn cần được kiểm chứng trên JDK đang dùng.
- **Phân giải tên:** `InetAddress` và resolver có thể chịu ảnh hưởng từ network, cache và môi trường; không nên ghi một địa chỉ IP quan sát được như đáp án phổ quát.

Những chủ đề này khác nhau, nhưng báo cáo kiểm chứng đều cần cùng một cấu trúc:

> **Môi trường → Cấu hình → Đầu vào → Kỳ vọng → Thao tác → Kết quả thực tế → Bằng chứng → Kết luận.**

Bài thuộc chương **Thực hành tổng hợp**, mô-đun `JAVA_VERSION_JAVA18`. Trọng tâm là xây quy trình báo cáo **đáng tin cậy, có thể chạy lại và đủ thông tin chẩn đoán**, chỉ dùng kiến thức vẫn có giá trị trên JDK hiện đại.

## 2. Phân biệt kiểm thử, quan sát và bằng chứng

Ba khái niệm thường bị gộp làm một:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Kỳ vọng (expected)** | Kết quả cần đúng theo API/tiêu chuẩn hoặc yêu cầu đã định trước khi chạy | Chuỗi `Cà` mã hóa UTF-8 phải là `43 C3 A0` |
| **Quan sát (actual)** | Dữ liệu chương trình thực sự trả ra trong một lần chạy | `HexFormat` in `43C3A0` |
| **Bằng chứng (evidence)** | Dữ liệu độc lập hoặc log có thể kiểm tra lại để chứng minh quan sát | Byte hex, kích thước, SHA-256, status/header HTTP, loại exception và input |
| **Kết luận (verdict)** | So sánh actual với expected theo tiêu chí rõ | `PASS`, `FAIL`, `SKIP`, `BLOCKED` |

Một vài nguyên tắc:

1. **Không viết expected bằng cách sao chép actual** vừa thu được; như vậy phép kiểm tra trở thành tự xác nhận.
2. Nếu byte cần chính xác, hãy định nghĩa byte mẫu từ **đặc tả độc lập** trước khi gọi API.
3. Nếu kỳ vọng là exception, ghi **API gây lỗi, cấu hình tạo lỗi và class exception**; không chỉ ghi “có lỗi”.
4. Nếu một phép thử không chạy do thiếu môi trường, ghi `BLOCKED`, không ghi `PASS`.
5. Nếu phản hồi khác kỳ vọng nhưng code vẫn chạy, đó là `FAIL` — không phải “thành công vì không có exception”.

### 2.1. Bộ sáu trường tối thiểu

Một test case hoàn chỉnh tối thiểu có:

| Trường | Câu hỏi cần trả lời |
| --- | --- |
| `environment` | Đang chạy trên JDK/JVM/OS/kiến trúc nào? |
| `configuration` | JVM flags, module path, charset, HTTP/locale/clock có gì ảnh hưởng? |
| `input` | Dữ liệu nguồn, byte/chuỗi/URL/cấu trúc class nào đã được đưa vào? |
| `expected` | Hợp đồng yêu cầu gì, căn cứ vào tài liệu nào? |
| `actual` | Thực tế trả ra giá trị, status, byte hoặc exception gì? |
| `evidence` | Có bản ghi nào giúp người khác xác minh actual và nguyên nhân? |

Nên bổ sung `verdict`, `caseId`, `timestamp`, `steps`, `artifactVersion` và `limitations` để phục vụ chạy lại, so sánh giữa các JDK và CI.

## 3. Môi trường: ghi thông tin ảnh hưởng hành vi, không phải mọi property

Báo cáo cần đủ thông tin để so sánh hai lần chạy, đặc biệt khi có khác biệt giữa JDK 17, JDK 18 và JDK hiện đại.

### 3.1. Ghi đúng JDK và runtime

Thông tin hữu ích:

- JDK feature release và patch version; Java 18 là **mốc giới thiệu** tính năng, không nhất thiết là JDK hiện đang chạy.
- Vendor, JVM implementation và `Runtime.version()`.
- `java` và `javac` thuộc cùng bộ công cụ hay không.
- OS name/version, architecture; có chạy trong container hay trên máy trực tiếp không.
- Classpath/module path và phiên bản dependencies tác động tới bài test.
- Source revision hoặc hash của chính chương trình/fixture.

Lệnh kiểm tra trước khi chạy:

```shell
java -version
javac -version
```

`java -version` và `javac -version` giúp nhận diện trường hợp trình biên dịch dùng một JDK nhưng chương trình thực thi dùng JDK khác.

Có thể ghi một số thông tin ngay trong Java:

```java
import java.nio.charset.Charset;

System.out.println("java.version = "
        + System.getProperty("java.version"));
System.out.println("java.vendor = "
        + System.getProperty("java.vendor"));
System.out.println("java.vm.name = "
        + System.getProperty("java.vm.name"));
System.out.println("runtime.version = "
        + Runtime.version());
System.out.println("os.name = "
        + System.getProperty("os.name"));
System.out.println("os.arch = "
        + System.getProperty("os.arch"));
System.out.println("defaultCharset = "
        + Charset.defaultCharset().name());
```

Dùng giá trị được chương trình in ra trong **lần chạy thực tế**, không điền phiên bản từ máy khác hoặc từ tài liệu tham khảo.

### 3.2. Môi trường ngoài JVM cũng quan trọng

Một phép thử HTTP có thể bị ảnh hưởng bởi proxy, DNS, server đang nghe cổng nào hoặc content coding. Một phép thử encoding có thể bị ảnh hưởng bởi charset của file nguồn và terminal. Một phép thử Reflection/MethodHandle có thể bị ảnh hưởng bởi module graph.

Ghi các chi tiết thực sự có liên quan:

| Loại phép thử | Chi tiết môi trường cần lưu |
| --- | --- |
| UTF-8/file I/O | Byte nguồn, charset theo hợp đồng, `Charset.defaultCharset()`, newline/BOM khi liên quan |
| Console/stdout | Terminal, redirect, charset của stream nếu được kiểm tra; không suy từ default charset |
| HTTP | URL hoặc loopback port, server build, phương thức request, response headers |
| Javadoc | Phiên bản `javadoc`, source encoding, lệnh build tài liệu, tài nguyên snippet |
| Reflection/JPMS | Module names, module path, `exports`/`opens`, caller module, class loader khi liên quan |
| MethodHandle | `MethodType`, `Lookup.lookupClass()`, lookup modes, quyền read/open của module |
| DNS | Host/query, network/resolver context, cache policy, thời điểm; tránh hardcode IP ngoài hợp đồng |

Không ghi tất cả biến môi trường một cách bừa bãi; chúng có thể chứa token, mật khẩu hoặc định danh cá nhân.

## 4. Cấu hình: phải ghi chính xác thứ làm thay đổi phép thử

### 4.1. JVM flags và charset

Đối với mã hóa từ JDK 18, ghi rõ JVM startup flags nếu có, đặc biệt:

```shell
java -Dfile.encoding=UTF-8 EvidenceProbe.java
```

Hoặc khi cần điều tra sự tương thích của dữ liệu cũ:

```shell
java -Dfile.encoding=COMPAT EvidenceProbe.java
```

`UTF-8` và `COMPAT` là các giá trị được hỗ trợ cho `file.encoding` theo JEP 400. Chúng điều khiển lựa chọn default charset khi **khởi động**; không chuyển đổi byte file đã lưu. `System.setProperty("file.encoding", "...")` sau khi JVM đã chạy không phải cơ chế đổi default charset đáng tin cậy.

Nên ghi cả:

- `Charset.defaultCharset().name()` — charset thực tế được API trả về.
- `System.getProperty("file.encoding")` — system property để đối chiếu.
- `System.getProperty("native.encoding")` — thông tin encoding của môi trường nếu có, không phải công tắc tự thay đổi default charset.

**Không suy rằng `System.out` và `System.err` nhất định dùng `Charset.defaultCharset()`.** Charset standard streams/terminal có hợp đồng riêng, nên khi kiểm tra byte đầu ra cần thu **byte thực tế** hoặc cấu hình stream được nêu rõ.

### 4.2. Cấu hình HTTP và module

Ví dụ báo cáo cấu hình:

```yaml
configuration:
  runtime:
    charsetContract: UTF-8
    fileEncodingStartup: UTF-8
  http:
    method: GET
    url: http://127.0.0.1:8000/hello.txt
    accept: text/plain
    expectedContentType: text/plain
    contentEncoding: none
  modules:
    caller: demo.probe
    target: demo.vault
    targetPackageOpenToCaller: false
```

Đây là **ví dụ về cấu trúc báo cáo**, không phải trạng thái quan sát của workspace người học. Trong test thật, phải điền theo command line, module descriptors và response headers được ghi lại.

`Content-Type`, `Content-Encoding` và charset là ba khái niệm khác nhau. Nếu body bị nén, cần phân biệt byte truyền qua transport với byte representation sau khi giải nén trước khi so sánh nội dung.

## 5. Đầu vào: mô tả được cả biểu diễn người đọc và byte máy đọc

### 5.1. Vì sao chỉ ghi “đầu vào là Cà” chưa đủ?

Ký tự `Cà` nhìn thấy trên màn hình không cho biết file hoặc request đã chứa byte nào. Trong UTF-8:

```text
Text:      Cà
UTF-8 hex: 43 C3 A0
Byte count: 3
```

Nếu file cũ dùng charset khác, cùng nội dung hiển thị có thể có byte khác. Nếu phần mềm đọc sai, thông tin bị thay bằng `U+FFFD` có thể khiến ta không khôi phục được byte ban đầu.

Một input record tốt có cả:

- Giá trị văn bản mong đợi và charset nguồn được quy định.
- Byte hex **nếu test liên quan byte**.
- Độ dài byte, BOM/newline nếu quan trọng.
- SHA-256 của fixture khi file dài hoặc nhị phân.
- Nguồn gốc fixture: file tạo từ công cụ nào và được xác nhận bằng gì.
- Giới hạn dữ liệu: có được rút gọn, giả lập hay đã được ẩn thông tin nhạy cảm không.

### 5.2. Dùng oracle độc lập với API đang kiểm tra

Ví dụ đúng:

```java
byte[] expected = {
        0x43, (byte) 0xC3, (byte) 0xA0
};

byte[] actual = "Cà".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

boolean passed = java.util.Arrays.equals(expected, actual);
```

`expected` chứa byte lấy từ quy tắc UTF-8, không được tạo bằng chính lời gọi `getBytes` đang cần kiểm tra.

Ví dụ **yếu**:

```java
byte[] expected = text.getBytes(StandardCharsets.UTF_8);
byte[] actual = text.getBytes(StandardCharsets.UTF_8);

// Hai mảng luôn khớp, chưa chứng minh implementation đúng
// với oracle byte độc lập của đặc tả UTF-8.
```

Việc so sánh hai phép mã hóa giống hệt có thể kiểm tra tính nhất quán, nhưng không đủ để kết luận byte đúng theo một nguồn chuẩn độc lập.

## 6. Kỳ vọng: dựa trên hợp đồng, không “đoán điều sẽ xảy ra”

Khi ghi `expected`, phân biệt:

| Loại kỳ vọng | Ví dụ | Căn cứ phù hợp |
| --- | --- | --- |
| Byte chính xác | `Cà` → `43 C3 A0` | Unicode/UTF-8 |
| Chuỗi đúng | Strict UTF-8 decode `43 C3 A0` → `Cà` | CharsetDecoder/UTF-8 |
| Exception | Strict decode `C3 28` → `MalformedInputException` | `CharsetDecoder` + `CodingErrorAction.REPORT` |
| HTTP status | GET fixture tồn tại → `200` | Hợp đồng server/endpoint |
| HTTP body | Body GET trùng byte fixture nguồn | Hợp đồng file server |
| Reflection | Private access bị module đóng từ chối | `AccessibleObject`/JPMS với module graph cụ thể |
| MethodHandle | `invokeExact` sai descriptor → `WrongMethodTypeException` | MethodHandle method type contract |
| Javadoc | Kết quả snippet hiện đúng mã và markups | Tài liệu `javadoc`/snippet và output build |

**Không ghi chung một status cố định cho mọi điều kiện.** Ví dụ một server có thể trả status khác nếu request method không được hỗ trợ; phải định nghĩa kỳ vọng theo đúng implementation và phiên bản đang kiểm tra.

### 6.1. Kỳ vọng exception phải đủ cụ thể

Thay vì:

```text
Expected: lỗi Java
```

Hãy ghi:

```text
Expected: java.nio.charset.MalformedInputException
Operation: UTF-8 CharsetDecoder.decode(ByteBuffer)
Config: onMalformedInput(REPORT)
Input hex: C3 28
```

Nếu API có thể báo các lớp exception khác nhau theo những điều kiện khác nhau, hãy ghi rõ case nào cần loại nào. Trong test production, tránh `catch (Exception)` rồi coi mọi exception là PASS.

## 7. Kết quả thực tế và bằng chứng: lưu cái cần để tái kiểm chứng

### 7.1. Ghi observed riêng biệt với verdict

Ví dụ:

```text
Case ID: UTF8-ENCODE-001
Expected bytes: 43 C3 A0
Actual bytes:   43 C3 A0
Expected size:  3
Actual size:    3
Verdict: PASS
```

Với trường hợp không hợp lệ:

```text
Case ID: UTF8-STRICT-002
Input bytes:    C3 28
Expected:       java.nio.charset.MalformedInputException
Actual:         java.nio.charset.MalformedInputException
Verdict:        PASS (vì lỗi này là kỳ vọng)
```

Hai đoạn trên là **ví dụ minh họa dạng báo cáo**; phải chạy code để có quan sát thực tế trên máy người học.

### 7.2. Khi nào lưu hex, khi nào lưu SHA-256?

| Tình huống | Bằng chứng phù hợp |
| --- | --- |
| Byte ngắn, có thể công khai | Hex đầy đủ, độ dài và charset |
| File vừa/nhỏ dùng làm fixture | Độ dài + hex vùng liên quan + SHA-256 + fixture version |
| File lớn/nhị phân | Độ dài + SHA-256 + vị trí khác biệt; giữ file fixture chuẩn |
| Payload có dữ liệu nhạy cảm | Hash và số liệu đã được phép công bố; hạn chế lưu raw payload |
| HTTP | Status + header cần thiết + byte body/hash + URL/route đã ẩn thông tin nhạy cảm |
| Exception | Fully qualified class name, operation, input/config, stack trace được lọc thông tin bí mật |

SHA-256 có thể giúp xác định hai bản nội dung có cùng byte hay không với độ tin cậy rất cao. **Chỉ có hash mà không có fixture chuẩn để so** chưa đủ kết luận body đúng hợp đồng; ít nhất cần hash kỳ vọng từ nguồn độc lập, độ dài và quy tắc tạo fixture.

Không đưa mật khẩu, token trong query string, cookie, `Authorization` header hoặc dữ liệu khách hàng thật vào report không được bảo vệ. Hash của dữ liệu có entropy thấp cũng có thể làm lộ thông tin qua đoán giá trị, nên không coi hash là biện pháp ẩn danh tuyệt đối.

### 7.3. Exception message không phải hợp đồng ổn định

Nên ưu tiên kiểm tra:

1. Fully qualified class name.
2. API gây exception.
3. Dữ liệu và cấu hình dẫn tới lỗi.
4. Cause chain và stack trace **khi cần** chẩn đoán.

Không cố định test bằng cách so sánh nguyên văn `getMessage()` giữa các bản JDK. Nội dung message, stack frames và đường dẫn trong thông báo có thể thay đổi theo JDK, provider hoặc môi trường.

Với `MalformedInputException`, có thể ghi thêm `getInputLength()`. Chỉ số này là **độ dài input malformed**, **không phải vị trí byte lỗi**. Khi cần offset, có thể dùng API incremental `CharsetDecoder.decode(ByteBuffer, CharBuffer, boolean)` và vị trí buffer khi nhận `CoderResult.isError()`.

## 8. Chương trình Java hoàn chỉnh: tạo bằng chứng UTF-8 có thể kiểm tra lại

Chương trình sau tạo hai case độc lập. Nó dùng các API đã có từ JDK 18 trở về sau, không phụ thuộc terminal charset để kiểm chứng byte: hex ASCII được ghi ra stdout, còn oracle byte được khai báo độc lập.

Tạo file `EvidenceProbe.java` với nội dung:

```java
import java.nio.ByteBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Arrays;
import java.util.HexFormat;

public final class EvidenceProbe {
    private static final HexFormat HEX =
            HexFormat.of().withUpperCase();

    private static final byte[] EXPECTED_UTF8 = {
            0x43, (byte) 0xC3, (byte) 0xA0
    };

    private static String decodeStrict(byte[] bytes)
            throws java.nio.charset.CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("timestampUtc=" + Instant.now());
        System.out.println("runtimeVersion=" + Runtime.version());
        System.out.println("javaVendor="
                + System.getProperty("java.vendor"));
        System.out.println("osName="
                + System.getProperty("os.name"));
        System.out.println("osArch="
                + System.getProperty("os.arch"));
        System.out.println("defaultCharset="
                + Charset.defaultCharset().name());
        System.out.println("file.encoding="
                + System.getProperty("file.encoding"));
        System.out.println("native.encoding="
                + System.getProperty("native.encoding"));

        // Case 1: oracle byte độc lập với API getBytes().
        byte[] actual = "Cà".getBytes(StandardCharsets.UTF_8);
        String expectedHex = HEX.formatHex(EXPECTED_UTF8);
        String actualHex = HEX.formatHex(actual);

        System.out.println("CASE UTF8-ENCODE-001");
        System.out.println("expectedHex=" + expectedHex);
        System.out.println("actualHex=" + actualHex);
        System.out.println("expectedSize=" + EXPECTED_UTF8.length);
        System.out.println("actualSize=" + actual.length);

        boolean bytesMatch =
                Arrays.equals(EXPECTED_UTF8, actual);
        System.out.println("verdict="
                + (bytesMatch ? "PASS" : "FAIL"));
        require(bytesMatch, "UTF-8 byte mismatch");

        // Case 2: byte malformed phải bị từ chối.
        byte[] malformed = {
                (byte) 0xC3, (byte) 0x28
        };

        System.out.println("CASE UTF8-STRICT-002");
        System.out.println("inputHex=" + HEX.formatHex(malformed));
        System.out.println("expectedException="
                + MalformedInputException.class.getName());

        try {
            decodeStrict(malformed);
            System.out.println("actualException=NONE");
            System.out.println("verdict=FAIL");
            throw new AssertionError(
                    "Malformed UTF-8 was accepted");
        } catch (MalformedInputException expected) {
            System.out.println("actualException="
                    + expected.getClass().getName());
            System.out.println("malformedInputLength="
                    + expected.getInputLength());
            System.out.println("verdict=PASS");
        }

        System.out.println("OVERALL=PASS");
    }
}
```

Chạy từ thư mục chứa file:

```shell
java EvidenceProbe.java
```

Hoặc biên dịch trước nếu quy trình CI cần tách compile và run:

```shell
javac -encoding UTF-8 EvidenceProbe.java
java EvidenceProbe
```

Lưu ý:

- Java source-file mode có từ trước JDK 18 và vẫn được hỗ trợ.
- File nguồn được lưu **UTF-8**; dùng `javac -encoding UTF-8` giúp việc biên dịch nguồn có dấu không phụ thuộc lựa chọn môi trường.
- `HexFormat` có từ Java 17, nên dùng được với Java 18 và các JDK mới.
- `C3 28` là byte không hợp lệ theo UTF-8; strict decoder với `REPORT` sẽ ném `MalformedInputException`.
- `malformedInputLength` không được hiểu là vị trí offset của lỗi.
- Lệnh chạy xuất nhiều trường môi trường; chỉ chia sẻ các trường không nhạy cảm.
- Chương trình không cần Internet, database hoặc Simple Web Server để có thể tái hiện.

Nếu có lỗi trước khi in `OVERALL=PASS`, đó là phép thử thất bại và cần giữ nguyên log. Đừng sửa expected thành actual chỉ để làm build xanh.

### 8.1. Dạng log mong đợi

Các dòng không phụ thuộc bản JDK hoặc hệ điều hành:

```text
CASE UTF8-ENCODE-001
expectedHex=43C3A0
actualHex=43C3A0
expectedSize=3
actualSize=3
verdict=PASS
CASE UTF8-STRICT-002
inputHex=C328
expectedException=java.nio.charset.MalformedInputException
actualException=java.nio.charset.MalformedInputException
verdict=PASS
OVERALL=PASS
```

Các dòng `runtimeVersion`, `javaVendor`, `osName`, `file.encoding` và `native.encoding` phải ghi theo giá trị thực tế. Ví dụ trên là **kỳ vọng để người học đối chiếu sau khi chạy**, không phải log đã được thu trên một máy cụ thể.

### 8.2. Tại sao test thứ hai là PASS khi có exception?

Đối với đầu vào malformed, ứng dụng được yêu cầu **từ chối byte sai**. `MalformedInputException` là hành vi đúng theo hợp đồng strict decoding. Vì vậy:

- Có đúng exception → PASS.
- Không có exception → FAIL.
- Có exception không liên quan → FAIL hoặc BLOCKED tùy nguyên nhân, **không mặc nhiên PASS**.

Cách đánh giá này hữu ích cả với Reflection/MethodHandle: exception có thể là kết quả mong đợi của một case quyền truy cập bị từ chối.

## 9. Khi cần bằng chứng offset byte lỗi

`CharsetDecoder.decode(ByteBuffer)` tiện dụng để biết có lỗi nhưng `MalformedInputException.getInputLength()` không cung cấp byte offset. Khi cần chẩn đoán chính xác vị trí trong input, dùng incremental decoding.

Ví dụ với dữ liệu `41 42 C3 28`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

byte[] inputBytes = {
        0x41, 0x42, (byte) 0xC3, 0x28
};

ByteBuffer input = ByteBuffer.wrap(inputBytes);
CharBuffer output = CharBuffer.allocate(inputBytes.length);

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CoderResult result = decoder.decode(input, output, true);

if (result.isError()) {
    System.out.println("errorByteOffset=" + input.position());
    System.out.println("malformedByteCount=" + result.length());
}
```

Với byte trên, offset tính từ 0 bắt đầu tại `2`. Đây là thông tin hữu ích để đối chiếu với hexdump của file.

Với dữ liệu stream chia nhiều buffer, cần giữ đúng byte chưa tiêu thụ giữa các lần decode và tính **offset tuyệt đối** dựa trên tổng số byte đã đọc/tiêu thụ trước đó. Không dùng trực tiếp `input.position()` của một chunk rồi coi đó là offset tính từ đầu file.

## 10. Mẫu báo cáo Markdown thống nhất cho nhóm hoặc CI

Mẫu dưới đây có thể sao chép cho từng lần kiểm chứng. Dấu ngoặc vuông là chỗ người kiểm thử **phải điền bằng dữ liệu thật**; không nên giữ nguyên trong báo cáo đã nộp.

```markdown
# Báo cáo kiểm chứng: [chủ đề / case ID]

## A. Thông tin lần chạy
- Run ID: [định danh duy nhất]
- Timestamp UTC: [ISO-8601]
- Người/CI job thực hiện: [ID phù hợp, không chứa bí mật]
- Source revision: [commit hoặc artifact version]
- Mục tiêu: [hợp đồng API cần xác nhận]

## B. Môi trường
- JDK/JVM: [java -version thực tế]
- Java vendor: [...]
- OS/architecture: [...]
- Build tools/dependencies: [...]
- Runtime location: [local/container/CI; không lộ đường dẫn nhạy cảm]

## C. Cấu hình
- JVM startup flags: [...]
- Default charset: [...]
- File/protocol charset: [...]
- Module path / opens / reads: [...]
- HTTP/terminal settings nếu có: [...]

## D. Đầu vào và thao tác
- Input source: [...]
- Input string/shape: [...]
- Input byte count: [...]
- Input hex hoặc fixture hash: [...]
- Steps/commands: [...]

## E. Kỳ vọng
- Expected result: [...]
- Expected byte hex hoặc exception class: [...]
- Căn cứ: [URL/spec/API version]
- Acceptance criterion: [...]

## F. Kết quả thực tế
- Actual value/status: [...]
- Actual byte count / hex / hash: [...]
- Actual exception và cause chain nếu có: [...]
- Exit code: [...]

## G. Bằng chứng
- Log/artifact tham chiếu: [...]
- Byte offset hoặc HTTP headers nếu liên quan: [...]
- Redaction đã áp dụng: [...]
- Hạn chế/chưa kiểm chứng: [...]

## H. Kết luận
- Verdict: [PASS / FAIL / SKIP / BLOCKED]
- Expected vs actual: [...]
- Cách tái hiện: [...]
- Hướng xử lý nếu FAIL: [...]
```

Báo cáo cuối cùng nên gắn artifact kiểm thử hoặc log thực tế trong kho nội bộ theo chính sách dự án. Không cần chép toàn bộ stack trace dài vào phần tóm tắt nếu có file log chứa bằng chứng đầy đủ.

### 10.1. Bản ghi dạng bảng cho nhiều test case

| Case ID | Đầu vào | Kỳ vọng | Quan sát | Bằng chứng | Verdict |
| --- | --- | --- | --- | --- | --- |
| `UTF8-ENCODE-001` | `Cà` | `43C3A0` | Từ run thực | Hex/size | Chưa chạy |
| `UTF8-STRICT-002` | `C328` | `MalformedInputException` | Từ run thực | Exception class/input | Chưa chạy |
| `HTTP-FILE-003` | GET fixture | Status/body khớp fixture | Từ run thực | Status/header/body hash | Chưa chạy |
| `REFLECT-ACCESS-004` | Private member qua module đóng | Truy cập bị từ chối | Từ run thực | Module graph/exception | Chưa chạy |
| `MH-LOOKUP-005` | Lookup thiếu quyền | `IllegalAccessException` | Từ run thực | Lookup modes/opens/reads | Chưa chạy |

Trong bảng trên, `Chưa chạy` là trạng thái ban đầu của template, **không phải kết quả kiểm chứng đã hoàn tất**. Khi chạy xong, thay bằng `PASS`/`FAIL` hoặc ghi `SKIP`/`BLOCKED` có lý do.

## 11. Mở rộng báo cáo cho HTTP: status, header và byte phải cùng xuất hiện

Nếu bài thực hành dùng `jwebserver` hoặc `SimpleFileServer`, mở trang trong browser chưa đủ. Hãy dùng Java `HttpClient` để nhận response byte:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.HexFormat;

HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("http://127.0.0.1:8000/hello.txt"))
        .GET()
        .build();

HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

byte[] bytes = response.body();

System.out.println("status=" + response.statusCode());
System.out.println("contentType=" + response.headers()
        .firstValue("Content-Type").orElse("<absent>"));
System.out.println("contentEncoding=" + response.headers()
        .firstValue("Content-Encoding").orElse("<absent>"));
System.out.println("bodyBytes=" + bytes.length);
System.out.println("bodyHex=" + HexFormat.of()
        .withUpperCase()
        .formatHex(bytes, 0, Math.min(bytes.length, 32)));
```

Ví dụ trên là **đoạn code dùng trong một chương trình Java có import/entrypoint phù hợp**, không tự khởi chạy server. Người học phải chuẩn bị file fixture, khởi chạy server và ghi cấu hình thực tế.

### 11.1. Mẫu expected cho HTTP

Nếu server phục vụ file tĩnh ở loopback, có thể xác định:

- GET tới file fixture tồn tại → kỳ vọng `200` theo hợp đồng server.
- `Content-Type` → media type kỳ vọng; không mặc định có `charset=UTF-8`.
- Byte body → so trực tiếp với `Files.readAllBytes(fixture)` hoặc hash độc lập.
- `Content-Length` → nếu có, đối chiếu với độ dài byte theo ngữ nghĩa HTTP phù hợp.
- HTTP HEAD → không có response body; có thể dùng để kiểm tra metadata.
- File không tồn tại → kỳ vọng status theo hợp đồng server/route; ghi rõ.

Nếu response có `Content-Encoding: gzip`, đừng so byte nén với text UTF-8 trực tiếp. Trước tiên xác định bài test đang cần xác minh **byte wire** hay **representation đã giải nén**, rồi xử lý content coding đúng trước khi so.

`BodyHandlers.ofByteArray()` giúp giữ body dưới dạng byte để so sánh. `BodyHandlers.ofString()` trên Java HTTP Client có hợp đồng xử lý charset từ `Content-Type` và có fallback; vì vậy không dùng chuỗi sau giải mã thay cho bằng chứng raw bytes trong bài test byte.

## 12. Mở rộng cho Reflection và MethodHandle: báo cáo đúng loại ngoại lệ

Với kiểm chứng quyền truy cập, phải mô tả **đầy đủ module graph và member**. Một exception trống ngữ cảnh rất khó tái hiện.

### 12.1. Reflection `setAccessible(true)`

Báo cáo nên ghi:

```text
Case ID: REFLECT-ACCESS-004
JDK: [phiên bản thực tế]
Caller module: demo.inspector
Target module: demo.domain
Target package: demo.domain.internal
Target member: private field id
Caller reads target: true / false (quan sát)
Target package opens to caller: true / false (quan sát)
Operation: Field.setAccessible(true)
Expected: java.lang.reflect.InaccessibleObjectException
Actual: [exception class từ run]
Verdict: [PASS/FAIL/BLOCKED]
```

Không dùng `getDeclaredField` thành công để chứng minh được phép đọc `private`. Nếu module đích không open package cho caller, `setAccessible(true)` có thể ném `InaccessibleObjectException`.

`trySetAccessible()` là một phép thử khác: khi không thể bật quyền, nó trả `false`; không thay expected của `trySetAccessible` bằng class exception của `setAccessible(true)`.

### 12.2. MethodHandle `privateLookupIn`

Báo cáo nên ghi cả quyền của lookup gốc:

```text
Case ID: MH-LOOKUP-005
Caller Lookup.lookupClass: [...]
Caller Lookup.hasFullPrivilegeAccess: [...]
Caller Lookup.lookupModes: [...]
Caller module reads target: [...]
Target module opens package to caller: [...]
Operation: MethodHandles.privateLookupIn(target, caller)
Expected: java.lang.IllegalAccessException
Actual: [exception class từ run]
Verdict: [PASS/FAIL/BLOCKED]
```

Với `privateLookupIn` xuyên module, lookup gốc phải có `PRIVATE` và `MODULE`; module caller phải đọc module đích và module đích phải open package tới caller. Khi thiếu quyền, `IllegalAccessException` là exception được API khai báo.

**Đừng gộp hai phép kiểm tra quyền thành cùng một expected exception.** `setAccessible(true)` và `privateLookupIn` có hợp đồng lỗi khác nhau.

### 12.3. Exception trong MethodHandle invocation

Nếu phép thử liên quan `invokeExact`, ghi rõ `MethodType` của handle và **method type mà call site yêu cầu**. `WrongMethodTypeException` có thể xuất hiện khi hai kiểu này không khớp.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.WrongMethodTypeException;

MethodHandle identity = MethodHandles.identity(int.class);

try {
    // Handle thực: (int)int; call site yêu cầu (int)long.
    long value = (long) identity.invokeExact(7);
    throw new AssertionError("Expected WrongMethodTypeException");
} catch (WrongMethodTypeException expected) {
    System.out.println(expected.getClass().getName());
}
```

Đoạn trên cho thấy exception **được kỳ vọng** là một kết quả đúng. Không cần kiểm tra nguyên văn message của `WrongMethodTypeException`; ghi class, method type và line gọi.

## 13. Mở rộng cho Javadoc và Resolver: khi byte không phải bằng chứng chính

Không phải bài nào cũng có byte hoặc exception. Cấu trúc báo cáo vẫn giữ nguyên, nhưng loại evidence phải tương ứng với hợp đồng.

### 13.1. Javadoc `@snippet`

Khi kiểm chứng JEP 413 trên JDK hiện đại:

- **Môi trường:** `javadoc -version`, JDK đang dùng và build settings.
- **Cấu hình:** source encoding, source path, snippet-files root, doclint nếu áp dụng.
- **Đầu vào:** Javadoc comment và mã snippet được chỉ định.
- **Kỳ vọng:** tài liệu được tạo thành công; code và vùng/highlight đúng markup.
- **Actual:** exit code của `javadoc` và HTML output.
- **Evidence:** log build, đoạn HTML kết quả, ảnh/ảnh chụp render khi cần kiểm tra thị giác.

Đừng lấy screenshot đẹp làm bằng chứng duy nhất: nếu build không thành công hoặc code block thiếu dòng, cần log lệnh và output để tìm nguyên nhân.

### 13.2. `InetAddress` và Resolver

Khi kiểm chứng phân giải tên:

- Không cố định một IP của domain Internet công cộng làm expected vĩnh viễn.
- Ghi hostname/query, API gọi, cache/resolver context, IPv4/IPv6 và thời điểm.
- Nếu muốn test deterministic, dùng resolver giả lập hoặc fixture nội bộ có hợp đồng rõ.
- Nếu môi trường không có DNS/network như yêu cầu, đánh dấu `BLOCKED` hoặc `SKIP` có lý do, không chấp nhận một lỗi mạng ngẫu nhiên làm PASS.
- Nếu kiểm tra `UnknownHostException`, phải kiểm soát tình huống hostname không thể phân giải theo fixture/hợp đồng của test; không suy từ một DNS public thay đổi liên tục.

Trong báo cáo tổng hợp, không ép mọi case dùng `byteHex`. Dùng **dạng bằng chứng mạnh nhất có thể tái hiện**: byte, exception, status/header, API output, build log hoặc kết quả có assertion.

## 14. Tiêu chí PASS/FAIL và chính sách với dữ liệu không ổn định

### 14.1. Bảng trạng thái đề nghị

| Trạng thái | Khi dùng | Điều bắt buộc phải ghi |
| --- | --- | --- |
| `PASS` | Actual thỏa acceptance criteria đã định trước | Bằng chứng và môi trường |
| `FAIL` | Chạy được nhưng actual không thỏa kỳ vọng | Expected, actual, log, bước tái hiện |
| `SKIP` | Chủ động không chạy theo điều kiện đã xác định | Quy tắc skip và lý do |
| `BLOCKED` | Không thể chạy do dependency hoặc môi trường thiếu | Blocker, tác động, cách mở khóa |

Không cho `SKIP` và `BLOCKED` được tính là PASS trong tổng hợp. Nếu hệ thống CI có chính sách khác, phải công bố chính sách đó trong báo cáo.

### 14.2. Không che mất non-determinism

Khi test liên quan scheduler, DNS cache, HTTP server, thời gian hoặc tải máy, kết quả có thể biến động. Một báo cáo tốt ghi:

- Số lần chạy và phân bố kết quả.
- Bối cảnh môi trường giữa các lần chạy.
- Những tham số không được kiểm soát.
- Phép kiểm tra nào cần chạy lại.
- Có timeout/retry hay không và retry có làm thay đổi tiêu chí pass hay không.

Không chọn một lần PASS rồi xóa các lần FAIL khác. Nếu có sự không ổn định, gọi đúng tên là **flaky** và bảo lưu bằng chứng.

### 14.3. Kết quả đẹp không chứng minh đã kiểm tra đủ

Ví dụ một báo cáo có 100% PASS nhưng chỉ chạy trên một OS, một JDK và một charset nguồn không chứng minh tương thích cho mọi môi trường. Kết luận phải giới hạn trong **ma trận điều kiện đã kiểm tra**.

## 15. Checklist kiểm soát chất lượng báo cáo

Trước khi gửi report cho người review hoặc dùng làm bằng chứng CI:

- [ ] Có `caseId` và timestamp cụ thể không?
- [ ] JDK/JVM vendor, version, OS/architecture là kết quả từ chính run này?
- [ ] Có ghi launcher flags, module settings, charset và giao thức ảnh hưởng test?
- [ ] Đầu vào có nguồn gốc rõ và có byte/hash khi cần?
- [ ] Expected được định nghĩa **trước khi chạy** và có nguồn chính thức?
- [ ] Actual được lưu riêng, không tự sao chép từ expected?
- [ ] Byte oracle độc lập với API đang được thử?
- [ ] Với malformed input, đã kiểm tra exception class đúng thay vì catch mọi exception?
- [ ] Nếu cần offset, có phân biệt offset với malformed input length?
- [ ] Với HTTP, có status, headers và body bytes theo đúng mục tiêu?
- [ ] Với Reflection/MethodHandle, có caller/target module, `opens`/`reads`, member/method type?
- [ ] Với Javadoc, có log build và artifact output?
- [ ] Dữ liệu bí mật trong command, URL, log hoặc stack trace đã được loại bỏ?
- [ ] `SKIP`/`BLOCKED` có lý do và không được đếm như PASS?
- [ ] Báo cáo có lệnh tái hiện, artifact revision và giới hạn kết luận?
- [ ] Có thể phân biệt lỗi môi trường với lỗi hợp đồng API?

## 16. Bài tập tự kiểm tra

**Bài 1.** Vì sao một dòng `PASS` không đủ để xác minh hành vi mặc định UTF-8 trên một JVM?

*Đáp án:* Thiếu JDK/version, startup flags, input byte và acceptance criteria. PASS không cho biết điều kiện nào đã được thử và có thể tái hiện hay không.

**Bài 2.** Kiểm thử mã hóa `Cà` bằng UTF-8: expected nên lấy từ đâu?

*Đáp án:* Byte oracle độc lập theo UTF-8 là `43 C3 A0`. Sau đó mới gọi `getBytes(StandardCharsets.UTF_8)` để thu actual và so sánh.

**Bài 3.** Giải mã `C3 28` bằng decoder `REPORT` ném `MalformedInputException`. Verdict là gì?

*Đáp án:* PASS nếu acceptance criteria đã yêu cầu từ chối malformed UTF-8 và exception class đúng, có log input/config đầy đủ.

**Bài 4.** `MalformedInputException.getInputLength() == 1` có nghĩa byte lỗi ở offset 1 không?

*Đáp án:* Không. Đây là độ dài chuỗi byte malformed, không phải offset từ đầu input. Dùng `CoderResult`/`ByteBuffer.position()` khi cần offset.

**Bài 5.** GET file HTTP trả `200` nhưng byte body khác fixture gốc. Có được ghi PASS không?

*Đáp án:* Không. Khi hợp đồng yêu cầu byte trùng fixture, phải ghi FAIL cùng hex/hash và các header liên quan; 200 chỉ xác nhận status.

**Bài 6.** `setAccessible(true)` thất bại và ném `InaccessibleObjectException`, trong khi `privateLookupIn` thất bại và ném `IllegalAccessException`. Có thể dùng chung expected exception cho hai case không?

*Đáp án:* Không. Phải kiểm tra đúng class exception theo từng API và module/lookup conditions.

**Bài 7.** Vì sao không nên lưu `Authorization` header và raw user data vào báo cáo lỗi HTTP?

*Đáp án:* Chúng có thể chứa token, cookie hoặc dữ liệu cá nhân; chỉ giữ bằng chứng cần thiết, áp dụng redaction và cơ chế lưu trữ an toàn.

**Bài 8.** Một test resolver DNS ghi expected là IP duy nhất của domain công cộng và bắt đầu fail sau nhiều tháng. Vấn đề nằm ở đâu?

*Đáp án:* Kỳ vọng không ổn định theo hệ thống bên ngoài. Cần fixture/resolver kiểm soát hoặc tiêu chí không phụ thuộc một IP công cộng thay đổi.

**Bài 9.** Vì sao báo cáo phải phân biệt `SKIP` với `BLOCKED`?

*Đáp án:* SKIP là chủ động bỏ qua theo điều kiện, còn BLOCKED là không thể chạy do thiếu dependency/môi trường. Cả hai khác PASS và cần lý do riêng.

**Bài 10.** Một phép thử có log kết quả nhưng không biết phiên bản mã nguồn đang chạy. Thiếu trường nào?

*Đáp án:* Thiếu source revision/build artifact ID. Nếu không biết code/fixture nào đã chạy, người khác khó tái hiện và so sánh kết quả.

## 17. Ghi nhớ

Một báo cáo kiểm chứng đáng tin cậy không chỉ có kết quả đúng/sai mà cần **môi trường, cấu hình, đầu vào, kỳ vọng, kết quả thực tế và bằng chứng**. Đặt `caseId`, timestamp, source revision, thao tác tái hiện, verdict và giới hạn kết luận giúp review và CI dễ hiểu, dễ chạy lại.

- Với **encoding**, dùng byte hex/hash và decoder `REPORT`, kiểm tra exception class khi byte sai.
- Với **HTTP**, ghi status/header và so byte thật; tránh dựa vào trình duyệt.
- Với **Reflection/MethodHandle**, ghi module graph, quyền lookup và đúng loại exception.
- Với **Javadoc** hoặc **resolver**, dùng build log hay fixture kiểm soát thay vì ép một loại bằng chứng không phù hợp.

Thực hành tổng hợp có giá trị lâu dài trên JDK hiện đại là **lấy kỳ vọng từ hợp đồng, thu bằng chứng từ lần chạy thực, và báo cáo đủ thông tin để người khác bác bỏ hoặc tái hiện kết luận**.

### Tài liệu tham khảo chính thức

- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [OpenJDK — JEP 408: Simple Web Server](https://openjdk.org/jeps/408).
- [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [OpenJDK — JEP 416: Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
- [Oracle Java SE 26 — CharsetDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [Oracle Java SE 26 — MalformedInputException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/MalformedInputException.html).
- [Oracle Java SE 26 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
- [Oracle Java SE 26 — AccessibleObject](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [Oracle Java SE 26 — MethodHandles](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Oracle Java SE 26 — HexFormat](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/HexFormat.html).
