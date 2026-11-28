# Fuzz query parser — kiểm thử độ bền và tính nhất quán của query trong xác thực HMAC

## 1. Vì sao query parser là một bề mặt tấn công?

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client và server dùng **shared secret** để tạo và xác minh chữ ký HMAC cho HTTP request. Một hợp đồng ký thường chứa HTTP method, URI (path và query), các header được chọn, timestamp/nonce và digest của body. Phần query đặc biệt nhạy cảm: nhiều chuỗi ký tự khác nhau có thể cùng biểu thị một tập tham số, hoặc **bị các tầng xử lý hiểu thành những tập tham số khác nhau**.

Ví dụ, các request sau có thể đi qua gateway, framework và business code theo những cách khác nhau:

~~~http
GET /v1/orders?user=alice&role=viewer HTTP/1.1
GET /v1/orders?role=viewer&user=alice HTTP/1.1
GET /v1/orders?role=viewer&role=admin HTTP/1.1
GET /v1/orders?redirect=%252Fadmin HTTP/1.1
GET /v1/orders?search=hello+world HTTP/1.1
~~~

Nếu lớp xác minh HMAC ký theo một phiên bản của query, còn controller sử dụng phiên bản khác, attacker có thể tìm được request **được xác thực nhưng có ý nghĩa nghiệp vụ khác với dữ liệu đã ký**. Các lớp có thể vô tình giải mã `%xx` hai lần, đổi `+` thành dấu cách, bỏ tham số trùng lặp, chọn giá trị đầu/cuối hoặc diễn giải dấu `;` thành dấu phân tách.

**Fuzz query parser** là kỹ thuật tự động đưa vào query parser nhiều đầu vào hợp lệ, bất thường và sai định dạng để phát hiện crash, xử lý không nhất quán, vượt giới hạn tài nguyên và sai lệch giữa những cách diễn giải. Trong bối cảnh HMAC, trọng tâm an ninh là: **request được chấp nhận phải có một ý nghĩa tham số duy nhất, nhất quán với canonical request mà HMAC bảo vệ**.

Bài này thuộc chương **Security testing**. Sau khi học, người học có thể:

- Định nghĩa rõ một hợp đồng parse/canonicalize query, bao gồm điều kiện từ chối.
- Tạo corpus và fuzz harness có thể chạy lại nhờ seed cố định.
- Viết property/invariant test cho tính ổn định của canonicalization, giới hạn tài nguyên và duplicate keys.
- Kiểm thử sự nhất quán giữa HTTP gateway, Spring/Spring Security, HMAC verifier và handler nghiệp vụ.
- Phân biệt xác thực bằng HMAC, chống replay bằng timestamp/nonce và phân quyền sau xác thực.

## 2. Threat model: attacker điều khiển những gì?

Giả sử attacker có thể tự gửi HTTP request với request-target tùy ý đến endpoint công khai. Attacker **không biết shared secret** của client khác, nhưng có thể thử query được encode bất thường hoặc phát lại một request từng được ký hợp lệ. Ở một hệ thống có client hợp lệ nhưng bị lạm dụng, attacker thậm chí có thể tạo request có chữ ký đúng cho query do mình chọn. Vì vậy lỗi parser vẫn quan trọng kể cả khi phần HMAC dùng thuật toán mật mã chính xác.

| Nhóm đầu vào | Ví dụ | Lỗi cần tìm |
|---|---|---|
| Thứ tự tham số | `b=2&a=1` / `a=1&b=2` | Canonicalization không nhất quán |
| Khóa trùng lặp | `role=user&role=admin` | HTTP parameter pollution; first-wins/last-wins |
| Trùng sau decode | `role=user&%72ole=admin` | Bypass kiểm tra duplicate trước khi decode |
| Percent-encoding | `x=%2F`, `x=%2f`, `x=%252F` | Decode sai số lần; chữ ký không khớp |
| Dấu cộng và khoảng trắng | `q=a+b`, `q=a%20b`, `q=a%2Bb` | Nhầm URI query với form encoding |
| Phân tách | `a=1;b=2`, `x=%26y%3D2` | Một tầng xem `;`/`&`/`=` là delimiter khác tầng kia |
| Chuỗi sai | `x=%`, `x=%G0`, `x=%C0%AF` | Exception không kiểm soát, UTF-8 không hợp lệ |
| Ký tự điều khiển | `x=%00`, `x=%0D%0Aadmin` | Header/log injection, khác cách xử lý |
| Empty/missing | `x=`, `x`, `&x=1` | Hợp đồng mơ hồ về tham số rỗng |
| Đầu vào lớn | 5.000 ký tự, hàng nghìn cặp `a=b` | CPU/memory amplification, DoS |
| Unicode | `q=%C3%A9`, `q=e%CC%81` | Chuẩn hóa Unicode không thống nhất |
| Gateway rewrite | thay thứ tự query, decode trước khi forward | Verifier và handler thấy dữ liệu khác nhau |

Mục tiêu fuzz không chỉ là "không bị lỗi 500". Một parser trả 200 cho mọi input nhưng làm mất tham số hoặc tự sửa query theo nhiều cách cũng có thể tạo lỗ hổng liên quan đến HMAC và phân quyền.

## 3. Cố định hợp đồng query trước khi fuzz

**Không có một thuật toán canonical query chung đúng cho mọi API.** Mỗi hệ thống phải thống nhất phiên bản hợp đồng giữa client, verifier, gateway và handler. Ví dụ phía dưới chọn chính sách **strict, fail-closed** để minh họa; hãy điều chỉnh cho API thực tế trước khi áp dụng.

| Quy tắc của ví dụ | Chính sách |
|---|---|
| Đầu vào parser | `rawQuery`, không chứa ký tự `?` đầu chuỗi; `null`/chuỗi rỗng biểu thị không có tham số |
| Mã hóa trên wire | Chỉ nhận ký tự ASCII thô thuộc nhóm unreserved, dấu `+` trong value hoặc chuỗi escape `%HH` |
| Phân tách | `&` giữa các cặp; bắt buộc `=` giữa khóa và giá trị; `k=` hợp lệ, `k` không hợp lệ |
| Khóa | Sau giải mã phải thuộc `[A-Za-z0-9_.~-]+`, dài không quá 128 byte |
| Giá trị | Có thể rỗng, UTF-8 hợp lệ, dài không quá 1.024 byte sau giải mã |
| Dấu `+` | **Dấu cộng thật**, không phải dấu cách; canonical thành `%2B` |
| Percent-encoding | Decode **đúng một lần**; `%2f` và `%2F` cùng thành `%2F` |
| Ký tự điều khiển | Từ chối byte 0x00–0x1F và 0x7F sau giải mã |
| Khóa trùng | Từ chối sau decode, kể cả `a` và `%61` |
| Chuẩn hóa Unicode | Giữ nguyên code point; **không** áp dụng NFC/NFD ngầm |
| Sắp xếp | Sort khóa sau khi canonical encode; vì khóa duy nhất nên không có thứ tự trùng |
| Giới hạn | Raw query tối đa 4.096 ký tự ASCII, tối đa 64 cặp, canonical output tối đa 4.096 ký tự |

Ở ví dụ này, parser giữ nguyên giá trị có ý nghĩa nhưng sắp xếp các **khóa duy nhất**. Với ứng dụng mà thứ tự tham số có ý nghĩa, hợp đồng phải giữ thứ tự hoặc từ chối dạng không hỗ trợ; không được tự ý sắp xếp.

Các trường hợp điển hình:

| Query đầu vào | Canonical query hoặc kết quả |
|---|---|
| `b=2&a=1` | `a=1&b=2` |
| `x=%7e` | `x=~` |
| `q=hello+world` | `q=hello%2Bworld` |
| `q=hello%20world` | `q=hello%20world` |
| `x=%2f` | `x=%2F` |
| `x=%252F` | `x=%252F` (không decode lần hai) |
| `q=%C3%A9` | `q=%C3%A9` (UTF-8 hợp lệ) |
| `x=` | `x=` (giá trị rỗng hợp lệ) |
| `x` | **REJECT**: thiếu dấu bằng |
| `a=1&%61=2` | **REJECT**: khóa `a` trùng sau decode |
| `role=user&role=admin` | **REJECT**: tham số trùng |
| `x=%C0%AF` | **REJECT**: UTF-8 không hợp lệ |
| `x=%0D%0A` | **REJECT**: ký tự điều khiển |
| `x=é` | **REJECT**: ký tự non-ASCII phải được percent-encode |

Một số hệ thống cố ý dùng repeated keys để biểu diễn array. Khi đó phải định nghĩa cụ thể cách ký **và cách handler tiêu thụ tất cả giá trị**. Chính sách từ chối duplicate trong ví dụ giúp loại bỏ rủi ro verifier xem hai giá trị, nhưng controller chỉ lấy giá trị đầu hoặc cuối.

### Ranh giới với path, body và những header khác

`rawQuery` chỉ là **một phần** của canonical request. HTTP method, path, host/header đã ký, body digest, timestamp và nonce có quy tắc riêng. Không được để query parser tự xử lý `..` trong path, xóa slash hoặc làm thay đổi body bytes. Ví dụ về chuỗi ký đã thống nhất có thể là:

~~~text
<UPPERCASE_HTTP_METHOD>
<CANONICAL_PATH>
<CANONICAL_QUERY>
<TIMESTAMP_SECONDS>
<NONCE>
<LOWERCASE_HEX_SHA256_OF_BODY>
~~~

Các dòng nối bằng byte LF, encode UTF-8; HMAC-SHA256 được tính trên **đúng byte chuỗi ký**. Ví dụ này minh họa ranh giới; format thực tế cần được version hóa, có test vector độc lập giữa client và server.

## 4. Parser Java 17 dùng để xây fuzz oracle

Code tham chiếu sau giới hạn kích thước trước khi tạo cấu trúc tạm, decode percent bằng byte, kiểm tra UTF-8 nghiêm ngặt, kiểm tra duplicate **sau** decode rồi mới sinh canonical query. Mọi input vi phạm hợp đồng trả về `BadQueryException`, để HTTP adapter chuyển thành lỗi client phù hợp thay vì phát sinh 500.

**`QueryCanonicalizer.java`**

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.StringJoiner;

public final class QueryCanonicalizer {
    public static final int MAX_QUERY_CHARS = 4096;
    public static final int MAX_PAIRS = 64;
    private static final String HEX = "0123456789ABCDEF";

    private QueryCanonicalizer() {}

    public static final class BadQueryException extends IllegalArgumentException {
        public BadQueryException(String reason) {
            super(reason);
        }
    }

    private record Pair(String key, String value) {}

    public static String canonicalize(String rawQuery) {
        if (rawQuery == null || rawQuery.isEmpty()) {
            return "";
        }
        if (rawQuery.length() > MAX_QUERY_CHARS) {
            throw new BadQueryException("query_too_long");
        }

        String[] items = rawQuery.split("&", -1);
        if (items.length > MAX_PAIRS) {
            throw new BadQueryException("too_many_parameters");
        }

        Set<String> seenKeys = new HashSet<>();
        List<Pair> pairs = new ArrayList<>(items.length);

        for (String item : items) {
            int separator = item.indexOf('=');
            if (separator <= 0) {
                // Cấm key-only, empty key và empty segment (&&, & cuối).
                throw new BadQueryException("expected_key_equals_value");
            }

            String decodedKey = decode(item.substring(0, separator), 128);
            String decodedValue = decode(item.substring(separator + 1), 1024);

            // Policy: key chỉ dùng unreserved ASCII, value có thể là UTF-8.
            if (!decodedKey.matches("[A-Za-z0-9_.~-]+")) {
                throw new BadQueryException("invalid_parameter_key");
            }
            if (!seenKeys.add(decodedKey)) {
                throw new BadQueryException("duplicate_parameter_key");
            }

            pairs.add(new Pair(encode(decodedKey), encode(decodedValue)));
        }

        // Khóa duy nhất: đảo thứ tự cặp không đổi canonical query.
        pairs.sort(Comparator.comparing(Pair::key));
        StringJoiner result = new StringJoiner("&");
        for (Pair pair : pairs) {
            result.add(pair.key() + "=" + pair.value());
        }

        String canonical = result.toString();
        if (canonical.length() > MAX_QUERY_CHARS) {
            throw new BadQueryException("canonical_query_too_long");
        }
        return canonical;
    }

    private static String decode(String part, int maxBytes) {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        for (int i = 0; i < part.length();) {
            char c = part.charAt(i);
            if (c == '%') {
                if (i + 2 >= part.length()) {
                    throw new BadQueryException("invalid_percent_escape");
                }
                int hi = hexValue(part.charAt(i + 1));
                int lo = hexValue(part.charAt(i + 2));
                if (hi < 0 || lo < 0) {
                    throw new BadQueryException("invalid_percent_escape");
                }
                bytes.write((hi << 4) | lo);
                i += 3;
            } else if (c < 128 && (isUnreserved(c) || c == '+')) {
                // '+' giữ nguyên là plus; không dùng form-url-decoder.
                bytes.write(c);
                i++;
            } else {
                // Bao gồm raw non-ASCII, dấu ;, #, ?, space, raw '='.
                throw new BadQueryException("disallowed_raw_character");
            }

            if (bytes.size() > maxBytes) {
                throw new BadQueryException("component_too_long");
            }
        }

        byte[] decoded = bytes.toByteArray();
        for (byte b : decoded) {
            int unsigned = b & 0xFF;
            if (unsigned < 0x20 || unsigned == 0x7F) {
                throw new BadQueryException("disallowed_control_character");
            }
        }

        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(decoded))
                    .toString();
        } catch (CharacterCodingException ex) {
            throw new BadQueryException("invalid_utf8");
        }
    }

    private static int hexValue(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        return -1;
    }

    private static boolean isUnreserved(int c) {
        return (c >= 'a' && c <= 'z')
                || (c >= 'A' && c <= 'Z')
                || (c >= '0' && c <= '9')
                || c == '-' || c == '.' || c == '_' || c == '~';
    }

    private static String encode(String value) {
        StringBuilder result = new StringBuilder();
        for (byte b : value.getBytes(StandardCharsets.UTF_8)) {
            int unsigned = b & 0xFF;
            if (isUnreserved(unsigned)) {
                result.append((char) unsigned);
            } else {
                result.append('%')
                        .append(HEX.charAt(unsigned >>> 4))
                        .append(HEX.charAt(unsigned & 0x0F));
            }
        }
        return result.toString();
    }
}
~~~

Với query `b=2&a=1`, parser tạo canonical `a=1&b=2`. Với `a=1&%61=2`, cả `a` và `%61` đều decode thành `a`, vì thế bị từ chối. Với `x=%252F`, decode một lần tạo chuỗi ký tự `%2F`, sau đó encode lại thành `%252F`: dữ liệu không bị âm thầm đổi thành dấu slash.

**Giới hạn của mẫu:** Đây là policy minh họa cho một API chấp nhận unique keys; chỉ dùng parser này khi lớp framework, route và business code có cùng cách diễn giải. `String` Java ở đây biểu diễn raw ASCII query đã trích xuất đúng cách từ request target. Hệ thống có thể cần xử lý cấp byte trực tiếp nếu HTTP stack biến đổi request-target trước khi ứng dụng nhìn thấy.

## 5. Các bất biến cần fuzz

Fuzz hiệu quả cần oracle rõ ràng: test phải biết điều kiện nào là **luôn đúng**, thay vì chỉ kiểm tra không crash.

**Bất biến A — tổng quát và an toàn:** mọi input đều đi đến một trong hai kết quả: canonical query hợp lệ hoặc `BadQueryException` đã kiểm soát. Không có `NullPointerException`, `ArrayIndexOutOfBoundsException`, lỗi giải mã lọt lên thành HTTP 500 hoặc tiêu thụ tài nguyên không giới hạn.

**Bất biến B — idempotence:** với query được chấp nhận, canonical hóa kết quả thêm lần nữa không làm thay đổi dữ liệu:

\[
C(C(q)) = C(q)
\]

**Bất biến C — thứ tự cặp:** nếu tập các khóa **duy nhất** không đổi, mọi hoán vị cặp tham số tạo cùng canonical query, theo chính sách ví dụ:

\[
C(a=1\ \&\ b=2) = C(b=2\ \&\ a=1)
\]

**Bất biến D — không nhập nhằng:** tham số trùng sau percent decode đều bị từ chối, bao gồm `a=1&a=2` và `a=1&%61=2`. Đổi `+` thành `%20` phải tạo canonical khác; đổi `%2f` thành `%2F` phải tạo cùng canonical.

**Bất biến E — giới hạn:** parser từ chối kích thước vượt ngưỡng đã công bố và không trả kết quả lớn hơn giới hạn canonical. Kiểm tra cả raw length, decoded component length và số cặp.

**Bất biến F — gắn với HMAC:** mọi thay đổi có ý nghĩa nghiệp vụ **khác** phải đổi canonical bytes hoặc bị từ chối. Chỉ những biến thể được hợp đồng coi là tương đương (ví dụ đảo thứ tự cặp có khóa duy nhất, chữ hoa/thường của hex escape) mới được dùng chung chữ ký. Trong phép thử này, verify chữ ký bằng HMAC thực tế; đừng kết luận an toàn chỉ vì hai chuỗi có độ dài khác nhau.

**Bất biến G — chống replay và phân quyền:** parser không được tự gia hạn timestamp, đổi nonce hay bỏ kiểm tra chữ ký. Sau khi HMAC hợp lệ, endpoint vẫn phải kiểm tra principal có quyền với tài nguyên đã yêu cầu.

## 6. JUnit 5: corpus cố định và fuzz lặp lại được

Để bắt đầu mà không cần thêm thư viện fuzzing, có thể dùng JUnit 5 với corpus và vòng lặp random theo **seed cố định**. Các ca cụ thể giữ vai trò regression test, còn random tạo biến thể tự động. Những test này chạy bằng framework test Java hiện có; bài không yêu cầu tự chạy Gradle trong STEP 4.

**`QueryCanonicalizerTest.java`**

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

import org.junit.jupiter.api.Test;

class QueryCanonicalizerTest {
    @Test
    void sortsUniqueKeysAndNormalizesPercentEncoding() {
        assertEquals("a=~&b=%2B",
                QueryCanonicalizer.canonicalize("b=+&a=%7e"));
        assertEquals("path=%2F",
                QueryCanonicalizer.canonicalize("path=%2f"));
        assertEquals("path=%252F",
                QueryCanonicalizer.canonicalize("path=%252F"));
        assertEquals("q=%C3%A9",
                QueryCanonicalizer.canonicalize("q=%c3%a9"));
        assertEquals("x=", QueryCanonicalizer.canonicalize("x="));
        assertEquals("", QueryCanonicalizer.canonicalize(""));
    }

    @Test
    void plusAndSpaceHaveDifferentMeanings() {
        assertEquals("q=a%2Bb", QueryCanonicalizer.canonicalize("q=a+b"));
        assertEquals("q=a%20b", QueryCanonicalizer.canonicalize("q=a%20b"));
    }

    @Test
    void rejectsDuplicateKeysBeforeTheyReachBusinessCode() {
        for (String invalid : List.of(
                "role=user&role=admin",
                "a=1&%61=2",
                "x=1&x=1")) {
            assertThrows(QueryCanonicalizer.BadQueryException.class,
                    () -> QueryCanonicalizer.canonicalize(invalid), invalid);
        }
    }

    @Test
    void rejectsMalformedAndAmbiguousInputs() {
        for (String invalid : List.of(
                "a", "=x", "a=1&", "a=1&&b=2",
                "a=%", "a=%G0", "a=%C0%AF", "a=%FF",
                "a=%00", "a=%0D%0Aadmin", "a=bad value",
                "a=1;b=2", "a=1#fragment", "a=1=2",
                "a=é")) {
            assertThrows(QueryCanonicalizer.BadQueryException.class,
                    () -> QueryCanonicalizer.canonicalize(invalid), invalid);
        }
    }

    @Test
    void rejectsOversizedRequests() {
        assertThrows(QueryCanonicalizer.BadQueryException.class,
                () -> QueryCanonicalizer.canonicalize(
                        "x=" + "a".repeat(4096)));

        List<String> tooManyPairs = new ArrayList<>();
        for (int i = 0; i < 65; i++) {
            tooManyPairs.add("k" + i + "=x");
        }
        assertThrows(QueryCanonicalizer.BadQueryException.class,
                () -> QueryCanonicalizer.canonicalize(
                        String.join("&", tooManyPairs)));
    }

    @Test
    void fuzzValidUniquePairsAcrossPermutations() {
        Random random = new Random(0x5EEDL);
        String[] values = {"", "1", "%7e", "hello+world", "%E2%82%AC", "%252F"};

        for (int iteration = 0; iteration < 2_000; iteration++) {
            List<String> pairs = new ArrayList<>();
            int count = 1 + random.nextInt(12);
            for (int i = 0; i < count; i++) {
                pairs.add("k" + i + "="
                        + values[random.nextInt(values.length)]);
            }

            String expected = QueryCanonicalizer.canonicalize(
                    String.join("&", pairs));
            Collections.shuffle(pairs, random);
            String permuted = String.join("&", pairs);

            assertEquals(expected, QueryCanonicalizer.canonicalize(permuted),
                    "iteration=" + iteration + ", raw=" + permuted);
            assertEquals(expected, QueryCanonicalizer.canonicalize(expected),
                    "canonical must be idempotent");
        }
    }

    @Test
    void fuzzArbitraryAsciiWithoutUnexpectedCrashes() {
        Random random = new Random(0xBADC0DEL);
        String alphabet = "abAB09-_.~+%=&;#?[] \r\n";

        for (int iteration = 0; iteration < 20_000; iteration++) {
            int length = random.nextInt(128);
            StringBuilder raw = new StringBuilder(length);
            for (int i = 0; i < length; i++) {
                raw.append(alphabet.charAt(random.nextInt(alphabet.length())));
            }

            try {
                String canonical = QueryCanonicalizer.canonicalize(raw.toString());
                assertTrue(canonical.length()
                        <= QueryCanonicalizer.MAX_QUERY_CHARS);
                assertEquals(canonical, QueryCanonicalizer.canonicalize(canonical),
                        "iteration=" + iteration);
            } catch (QueryCanonicalizer.BadQueryException expected) {
                // Đầu vào bị từ chối đúng hợp đồng.
                // Exception ngoài loại này phải làm bài test thất bại.
            }
        }
    }
}
~~~

**Vì sao cần hai vòng fuzz?** Bộ phát sinh ngẫu nhiên ký tự thô thường tạo rất nhiều input không hợp lệ. Nếu chỉ bắt exception rồi bỏ qua, test có thể cho kết quả xanh dù hầu hết nhánh xử lý dữ liệu hợp lệ chưa được thực thi. Vòng `fuzzValidUniquePairsAcrossPermutations` chủ động tạo dữ liệu hợp lệ để kiểm tra biến đổi có ý nghĩa; vòng `fuzzArbitraryAsciiWithoutUnexpectedCrashes` tìm lỗi parser ở dữ liệu hỗn loạn.

Trong CI, lưu seed, số iteration và input tối giản gây lỗi. Khi một input gây lỗi, đưa nó vào bộ test hồi quy cố định, sau đó mới mở rộng thời lượng fuzz. Không ghi token, shared secret hoặc body nhạy cảm vào artifact fuzz.

## 7. Dùng fuzzing engine để đào sâu parser

Với hệ thống cần fuzz liên tục, có thể dùng một Java coverage-guided fuzzing engine như **Jazzer**. Đặt target minh họa sau vào cấu hình target của engine theo hướng dẫn phiên bản đang dùng. Engine có thể biến đổi byte input để khám phá các nhánh `%HH`, UTF-8 lỗi, duplicate key và giới hạn độ dài.

**`QueryParserFuzzTarget.java`**

~~~java
import java.nio.charset.StandardCharsets;

public final class QueryParserFuzzTarget {
    private QueryParserFuzzTarget() {}

    // Entry point nhận byte[] theo convention của Jazzer.
    public static void fuzzerTestOneInput(byte[] input) {
        String raw = new String(input, StandardCharsets.ISO_8859_1);
        try {
            String canonical = QueryCanonicalizer.canonicalize(raw);
            String secondPass = QueryCanonicalizer.canonicalize(canonical);
            if (!canonical.equals(secondPass)) {
                throw new AssertionError("Non-idempotent canonical query: " + raw);
            }
        } catch (QueryCanonicalizer.BadQueryException expected) {
            // Rejection là kết quả bình thường của parser strict.
        }
    }
}
~~~

Có thể cung cấp corpus hạt giống với các chuỗi `a=1`, `b=2&a=1`, `a=%2f`, `a=%252f`, `a=%C3%A9`, `a=+`, `a=1&%61=2`, `a=%`, `a=%FF`, `a=%00`, `a=1&&b=2`. Nên bổ sung từ điển token `%`, `&`, `=`, `+`, `;`, `#`, `%25`, `%2F`, `%20`, `%00` và ranh giới 4.096/4.097 ký tự.

Engine báo crash khi target ném exception không dự kiến hoặc assertion thất bại. Tập hợp coverage và lỗi cần được triage: lỗi parser có thể là lỗi an ninh nếu request HMAC được chấp nhận sai, nhưng cũng có thể chỉ là vấn đề ổn định hoặc hiệu năng. Các giới hạn CPU/memory và timeout nên được giám sát riêng; một property test ngắn không chứng minh parser chống được mọi kiểu DoS.

## 8. Kiểm thử end-to-end: parser ↔ HMAC ↔ gateway ↔ controller

Fuzz unit riêng chỉ xác minh parser nội bộ. Với HMAC request authentication, còn phải kiểm tra rằng **dữ liệu được ký, dữ liệu được xác minh và dữ liệu được handler dùng để quyết định** có cùng ngữ nghĩa. Một hệ thống có thể dùng parser hoàn hảo ở verifier nhưng mất an toàn khi Spring MVC hoặc gateway parse theo quy tắc khác.

~~~mermaid
flowchart LR
    A["HTTP client<br/>raw request-target"] --> B["Proxy / gateway"]
    B --> C["HMAC verifier<br/>canonical request"]
    C --> D["Timestamp + nonce<br/>replay protection"]
    D --> E["Controller<br/>query parameter binding"]
    E --> F["Authorization<br/>business action"]
~~~

Với mỗi input fuzz, ghi kết quả có kiểm soát từ hai phía: canonical bytes hoặc hash của canonical bytes ở verifier, danh sách tham số mà handler nhìn thấy (chỉ trong test environment), principal sau xác thực và HTTP status. Đối chiếu với hợp đồng đã chọn. Trường hợp verifier từ chối phải dừng trước controller.

Các kịch bản cốt lõi:

1. **Giống ngữ nghĩa, khác cách viết.** Ký `b=2&a=1` và gửi `a=1&b=2`. Nếu chính sách sắp xếp unique keys, cả hai có chung canonical bytes. Gateway/handler phải hiểu cùng tập tham số. Nếu framework bảo toàn thứ tự để quyết định nghiệp vụ, chính sách canonical cần đổi.
2. **Khác ngữ nghĩa, cố giữ chữ ký.** Ký `role=user`, sau đó gửi `role=admin` với chữ ký cũ. Phải từ chối `signature_invalid`. Nếu ký `role=user&role=admin`, phải từ chối duplicate trước khi thực hiện nghiệp vụ.
3. **Trùng sau decode.** Gửi `role=user&%72ole=admin`. Parser ở verifier phải từ chối ngay; không để controller chọn `role=admin` trong khi verifier từng chỉ nhìn `role=user`.
4. **Plus/space differential.** Ký `q=a+b`. Nếu gateway đổi `+` thành space trước verifier hoặc controller, kết quả có thể lệch. Tùy hợp đồng, từ chối request hoặc cấu hình gateway bảo toàn ngữ nghĩa, rồi kiểm chứng bằng test.
5. **Double decode.** `file=%252Fadmin` phải khác `file=%2Fadmin`. Nếu service decode lần hai, business value có thể biến thành `/admin` dù HMAC ký một giá trị khác.
6. **Percent encoding chữ hoa/thường.** `x=%2f` và `x=%2F` phải canonical như nhau, nhưng chỉ khi tất cả các tầng nhất trí.
7. **Request hết hạn hoặc nonce lặp.** Dù query hợp lệ và HMAC đúng, request có timestamp ngoài cửa sổ hoặc nonce đã dùng phải bị từ chối; fuzz không bỏ qua replay protection.
8. **Key rotation.** Ký bằng key cũ còn được phép xác minh trong giai đoạn rotation, rồi fuzz query. Không key nào được cho phép bỏ qua lỗi parser hoặc chính sách timestamp.
9. **Authorization.** Một request HMAC hợp lệ có thể vẫn không có quyền gọi endpoint, truy cập `tenantId` hoặc cập nhật đơn hàng. Test đảm bảo kết quả phân quyền không bị bypass qua tham số trùng, encode bất thường hoặc rewrite.

### Các điểm kiểm tra cụ thể trong Spring

- Bảo đảm verifier và controller dùng cùng nguồn dữ liệu query có ngữ nghĩa thống nhất. Đừng xác minh trên raw query một cách rồi để `@RequestParam` hoặc `MultiValueMap` được phân tích theo một cách khác mà chưa kiểm thử.
- Kiểm tra hành vi HTTP server và proxy đối với dấu `;`, percent-encoded delimiters, multi-value query, ký tự không hợp lệ và những request-target bị từ chối trước khi vào filter. Những trường hợp đó vẫn phải được ghi nhận như kết quả security test có chủ đích.
- Định nghĩa rõ verifier chạy trước endpoint authorization, xử lý timestamp/nonce sau parse hợp đồng và xác minh chữ ký, đồng thời không gửi request bị reject xuống business handler.
- Nếu gateway có chức năng rewrite query hoặc normalize URL, so sánh input thật **trước gateway**, payload gửi đến verifier và giá trị handler bind được. Không giả định các tầng tự bảo toàn byte hoặc thứ tự tham số.
- Tránh log toàn bộ query chứa PII, token hoặc signature; dùng mã lỗi, correlation ID và hash an toàn trong test diagnostics.

## 9. Bộ tiêu chí hoàn thành và cách phân loại lỗi

| Phát hiện | Phân loại thực tế | Hướng xử lý |
|---|---|---|
| Query sai làm ném exception không kiểm soát | Robustness / availability | Bắt lỗi parse, trả mã 4xx theo API |
| Duplicate key khiến HMAC và controller hiểu khác | **Security correctness** | Thống nhất parser hoặc từ chối duplicate |
| Chuỗi ký thay đổi theo gateway rewrite | Compatibility / security boundary | Chốt lại canonical target và proxy contract |
| Input quá dài gây CPU/memory tăng mạnh | Availability / DoS | Giới hạn chiều dài, số cặp, kích thước decoded |
| Query thay đổi ngữ nghĩa nhưng chữ ký cũ vẫn được chấp nhận | **Authentication bypass candidate** | Kiểm tra canonicalization, phân tích chuỗi xử lý và sửa ngay |
| HMAC hợp lệ nhưng principal truy cập trái quyền | **Authorization issue** | Kiểm soát quyền theo principal, resource, tenant |
| Timestamp/nonce bị bỏ qua khi parser throw/fallback | Replay protection failure | Fail closed; không đi tiếp sau lỗi |
| Fuzz corpus gây lỗi đã được thu gọn | Regression finding | Thêm test tối giản có seed, đầu vào và expected result |

Checklist áp dụng khi làm bài thực hành:

- [ ] Có hợp đồng query chính thức và bộ vector positive/negative theo hợp đồng đó.
- [ ] Fuzz cả đầu vào hợp lệ và không hợp lệ; seed tái hiện được; lưu input tối giản.
- [ ] Kiểm tra duplicate sau decode, Unicode/UTF-8, percent-encoding, `+`, `&`, `=`, `;` và giới hạn độ dài.
- [ ] Test được tính ổn định `C(C(q)) = C(q)` và tính nhất quán canonical hóa.
- [ ] Bất kỳ query thay đổi ngữ nghĩa đều bị từ chối hoặc dẫn đến canonical bytes/HMAC khác.
- [ ] Các tầng gateway, security filter và controller xử lý query nhất quán.
- [ ] Timestamp, nonce, key rotation, canonical body/header và authorization không bị ảnh hưởng bởi lỗi parser.

**Bài thực hành mở rộng:** Thêm một property test dùng generator chỉ tạo query có khóa duy nhất và giá trị UTF-8 đa dạng; sau đó chủ động đưa `a=1&%61=2` vào harness end-to-end qua gateway. Xác minh request bị từ chối **trước handler**, bất kể giá trị chữ ký và thứ tự query. Tiếp theo ký hai request `x=%2F` và `x=%252F`, chứng minh chúng biểu thị hai giá trị khác nhau trong hợp đồng và không được dùng chung chữ ký HMAC.
