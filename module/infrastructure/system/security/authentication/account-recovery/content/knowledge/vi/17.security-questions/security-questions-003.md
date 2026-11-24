# Rủi ro khi chuẩn hóa câu trả lời bảo mật

## Mục tiêu và bối cảnh

Trong chương **Security Questions** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, chuẩn hóa câu trả lời liên quan trực tiếp đến việc hệ thống chấp nhận ai trong luồng khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực. Một thao tác tưởng như chỉ để “dễ nhập hơn”, như bỏ dấu hoặc xóa khoảng trắng, có thể thay đổi tập câu trả lời được chấp nhận.

Bài học tập trung vào bốn câu hỏi:

- Những phép biến đổi nào chỉ thống nhất cách biểu diễn, và những phép nào làm mất thông tin?
- Vì sao hai câu trả lời khác nhau có thể vượt qua cùng một bộ kiểm tra mà không cần phá hàm băm?
- Làm thế nào để quy tắc nhất quán giữa đăng ký, xác minh, các dịch vụ và các phiên bản?
- Làm gì với hash cũ khi thay đổi chính sách chuẩn hóa?

Các ví dụ dữ liệu, xác suất và giới hạn đầu vào trong bài chỉ phục vụ minh họa thiết kế. Không có quy tắc chuẩn hóa nào biến dữ kiện tiểu sử thành bằng chứng đủ mạnh để tự cho phép thay MFA hoặc đăng ký passkey mới.

OWASP cảnh báo không dùng câu hỏi bảo mật trong phần mềm an toàn mới; hướng dẫn xử lý của tài liệu dành cho hệ thống cũ. Vì vậy, kỹ thuật trong bài giúp hiểu và kiểm soát rủi ro khi duy trì hoặc loại bỏ cơ chế cũ, không phải khuyến nghị bổ sung câu hỏi bảo mật vào sản phẩm mới. Xem [OWASP Choosing and Using Security Questions](https://cheatsheetseries.owasp.org/cheatsheets/Choosing_and_Using_Security_Questions_Cheat_Sheet.html).

## 1. Chuẩn hóa thay đổi điều kiện “câu trả lời đúng”

Giả sử người dùng đăng ký câu trả lời s. Dịch vụ áp dụng hàm chuẩn hóa f, mã hóa kết quả thành byte, rồi lưu bộ kiểm tra bằng một hàm dẫn xuất khóa dành cho mật khẩu, gọi tắt là KDF.

~~~text
Khi đăng ký:
    canonical = f(s)
    verifier  = KDF(UTF8(canonical), salt, parameters)

Khi xác minh câu trả lời x:
    candidate = f(x)
    kiểm tra UTF8(candidate) với verifier đã lưu
~~~

Sau bước này, hệ thống không còn kiểm tra “x giống nguyên văn s”. Nó kiểm tra theo quan hệ tương đương do f tạo ra.

~~~text
x được chấp nhận khi:
    f(x) = f(s)

Tập câu trả lời tương đương với s:
    E_f(s) = { x | f(x) = f(s) }
~~~

Nếu f chỉ đổi chữ thường, “LAN”, “Lan” và “lan” có thể nằm trong cùng một tập. Nếu f còn bỏ dấu, “Hoa”, “Hòa”, “Hóa” và “Họa” có thể bị gộp tiếp.

Đây là **va chạm do chuẩn hóa**, không phải va chạm mật mã. Hai đầu vào đã trở thành cùng một chuỗi byte trước khi đi vào KDF. Tăng chi phí băm hoặc đổi salt không thể phân biệt lại thông tin đã bị xóa.

Vì vậy, hàm chuẩn hóa là một phần của chính sách xác thực. Sửa hàm đó có thể thay đổi người được hệ thống chấp nhận dù không sửa thuật toán băm.

## 2. Phân biệt các thao tác thường bị gọi chung là chuẩn hóa

| Nhóm thao tác | Ví dụ | Tác động cần nhận diện |
| --- | --- | --- |
| Chuẩn hóa Unicode | NFC, NFD, NFKC, NFKD | Thống nhất các quan hệ tương đương do Unicode định nghĩa |
| Chuyển hoa thường | Chuyển toàn bộ sang chữ thường | Gộp các giá trị khác nhau về chữ hoa và chữ thường |
| Xử lý khoảng trắng | Cắt đầu cuối, gộp nhiều dấu cách | Thay đổi các vị trí hoặc loại khoảng trắng được phân biệt |
| Phiên âm, chuyển tự | Đổi “đ” thành “d” | Áp dụng quy tắc ngôn ngữ có thể làm mất thông tin |
| Bỏ dấu hoặc ký hiệu | Xóa dấu thanh, gạch nối, dấu nháy | Gộp các tên hoặc chuỗi mà người dùng có thể muốn phân biệt |
| So khớp gần đúng | Chấp nhận sai một ký tự | Mở rộng điều kiện chấp nhận theo khoảng cách hoặc điểm số |
| Cắt ngắn | Chỉ giữ n ký tự hoặc n byte đầu | Bỏ toàn bộ phần đuôi của bí mật |

Các thao tác này không có cùng mục đích và không nên được gom vào một hàm dùng chung tên “cleanString”.

Cũng cần tách chuẩn hóa khỏi bảo vệ đầu ra. Chuẩn hóa câu trả lời không thay thế truy vấn có tham số để chống SQL injection hoặc mã hóa đầu ra để chống XSS. Ngược lại, lưu chuỗi đã HTML escape làm đầu vào cho KDF có thể khiến cùng một câu trả lời bị xử lý khác giữa các giao diện.

## 3. Unicode: giống ký tự không đồng nghĩa giống chuỗi mã

### 3.1. Tương đương chuẩn tắc

Một số ký tự có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng ký tự cơ sở cùng dấu kết hợp.

~~~text
Cách 1: H + ò + a
        U+0048 U+00F2 U+0061

Cách 2: H + o + dấu huyền kết hợp + a
        U+0048 U+006F U+0300 U+0061
~~~

Hai cách trên biểu diễn cùng chữ “Hòa”. Nếu so sánh chuỗi hoặc băm trực tiếp mà không có quy tắc phù hợp, khác biệt cách nhập có thể làm người dùng thật bị từ chối.

Unicode định nghĩa NFC/NFD theo tương đương chuẩn tắc; NFKC/NFKD còn xử lý tương đương tương thích. NFC thiên về dạng tổ hợp, NFD thiên về dạng phân rã. Xem [Unicode UAX #15](https://www.unicode.org/reports/tr15/).

### 3.2. Tương đương tương thích rộng hơn

| Đầu vào minh họa | NFC | NFKC |
| --- | --- | --- |
| Chữ ò dựng sẵn và o kèm dấu huyền kết hợp | Cho cùng dạng chuẩn | Cho cùng dạng chuẩn |
| Chữ A dạng toàn chiều rộng U+FF21 | Giữ khác A thông thường | Đưa về A |
| Số một trong vòng tròn U+2460 | Giữ khác số 1 | Đưa về số 1 |

Việc gộp các biến thể tương thích có thể có ích trong một số loại dữ liệu, nhưng với bí mật xác thực phải xác định rõ các phân biệt nào được phép mất.

### 3.3. Những điều chuẩn hóa Unicode không tự làm

- NFC không tự chuyển “Hòa” thành “Hoa”.
- NFC không tự chuyển “Đào” thành “Dao”.
- NFC không tự xóa khoảng trắng hoặc chuyển chữ thường.
- Dùng NFD rồi xóa dấu kết hợp là một phép biến đổi mất thông tin bổ sung.

Chính sách của bài sẽ dùng NFC làm ví dụ về cách thống nhất biểu diễn có giới hạn. Đây không phải tuyên bố rằng NFC là đủ để bảo đảm an toàn cho toàn bộ cơ chế câu hỏi bảo mật.

Trong Java, API tương ứng là java.text.Normalizer và các giá trị Normalizer.Form. Xem [Java Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html).

## 4. Bỏ dấu và chuyển tự có thể gộp nhiều bí mật

Xét một chính sách giả định: chuyển chữ thường, phân rã Unicode và xóa dấu kết hợp.

| Câu trả lời ban đầu | Kết quả của chính sách giả định |
| --- | --- |
| Hoa | hoa |
| Hòa | hoa |
| Hóa | hoa |
| Họa | hoa |

Nếu người dùng đăng ký “Họa”, người chỉ biết hoặc đoán “Hoa” cũng có thể vượt qua bộ kiểm tra đó.

Đây không chỉ là chuyện chữ viết. Nó làm thay đổi xác suất đoán. Trong phân bố minh họa sau:

~~~text
P(Hoa) = 10%
P(Hòa) = 15%
P(Hóa) =  5%
P(Họa) = 20%
Các câu trả lời khác = 50%
~~~

Trước khi gộp, một ứng viên trong bốn giá trị trên có xác suất cao nhất là 20%. Sau khi gộp, lớp “hoa” chiếm 50%. Một lần đoán có thể bao phủ cả bốn trường hợp.

Với một phép biến đổi xác định f và cùng phân bố đầu vào:

~~~text
P(f(A) = z) = tổng P(A = a) trên mọi a thỏa f(a) = z
~~~

Gộp lớp không tạo thêm độ bất định cho bí mật. Mức giảm thực tế phụ thuộc dữ liệu; không thể suy ra số bit còn lại chỉ từ chiều dài câu trả lời sau chuẩn hóa.

Một lỗi triển khai khác là cho rằng xóa dấu kết hợp đã chuyển toàn bộ tiếng Việt thành ASCII. Ký tự “đ” không tự trở thành “d” bằng phép đó. Nếu bổ sung ánh xạ riêng, cần đánh giá thêm những lớp giá trị vừa bị gộp.

Quy tắc hỗ trợ tìm kiếm tên người và quy tắc kiểm tra một bí mật có mục đích khác nhau. Không nên tái sử dụng bộ chuyển tự của chức năng tìm kiếm cho câu trả lời khôi phục.

## 5. Chữ hoa, chữ thường và locale

### 5.1. Locale mặc định có thể làm kết quả phụ thuộc máy chủ

Trong Java, toLowerCase() dùng locale mặc định. Với locale tiếng Thổ Nhĩ Kỳ, chữ I có thể thành chữ ı không có chấm; một locale khác có thể cho kết quả i.

Nếu nút đăng ký và nút xác minh có locale mặc định khác nhau, cùng đầu vào có thể đi đến hai chuỗi khác nhau. Cần chỉ định locale khi chính sách đã chủ ý chuyển chữ thường; Locale.ROOT giúp tránh phụ thuộc locale mặc định, nhưng không loại bỏ việc mất phân biệt hoa thường. Xem [Java String: toLowerCase](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#toLowerCase()).

### 5.2. Chuyển chữ thường không phải toàn bộ bài toán so khớp không phân biệt hoa thường

Không nên giả định các cách sau luôn định nghĩa cùng một tập giá trị:

~~~text
Chuyển chữ thường rồi so sánh
Chuyển chữ hoa rồi so sánh
Dùng equalsIgnoreCase
Dùng Unicode case folding
Dùng Collator dành cho ngôn ngữ
~~~

Ví dụ, quy tắc chuyển chữ hoa của chuỗi có thể đổi ß thành hai chữ SS. Việc đổi biểu diễn cũng có thể thay đổi chiều dài. Vì vậy, tên chính sách “không phân biệt hoa thường” chưa đủ để triển khai nhất quán; phải chỉ rõ phép biến đổi và phiên bản tương ứng.

Nếu hệ thống cũ đã cam kết không phân biệt hoa thường, cần giữ đúng hợp đồng của bản ghi đó trong giai đoạn chuyển đổi. Không được âm thầm đổi sang một cách so khớp khác vì API có tên gần giống.

## 6. Khoảng trắng, ký tự vô hình và thứ tự biến đổi

### 6.1. “Xóa khoảng trắng” là mô tả chưa đủ

Cần xác định ít nhất:

- Xóa ở đầu cuối hay cả bên trong?
- Chỉ xử lý dấu cách U+0020 hay nhiều loại khoảng trắng?
- Giữ một dấu cách giữa các từ hay xóa hết?
- Xử lý tab, xuống dòng, non-breaking space và ký tự độ rộng bằng không thế nào?
- Chuỗi chỉ gồm khoảng trắng được từ chối trước hay sau biến đổi?

Trong Java, trim() xử lý các ký tự ở biên có giá trị không vượt U+0020. strip() dựa trên quy tắc whitespace của Java. Hai hàm không tương đương. Xem [Java String: trim và strip](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#strip()).

Đặc biệt, Character.isWhitespace không coi U+00A0 là whitespace, dù nó là non-breaking space. Xem [Java Character.isWhitespace](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html#isWhitespace(int)).

### 6.2. Cùng phép biến đổi nhưng khác thứ tự vẫn có thể khác kết quả

Xét chuỗi gồm U+00A0, “Lan”, rồi U+00A0. Trong ví dụ dùng Java strip():

~~~text
NFKC rồi strip:
    U+00A0 Lan U+00A0
    -> U+0020 Lan U+0020
    -> Lan

strip rồi NFKC:
    U+00A0 Lan U+00A0
    -> U+00A0 Lan U+00A0
    -> U+0020 Lan U+0020
~~~

Kết quả cuối khác nhau. Nói “cả hai dịch vụ đều dùng NFKC và strip” chưa chứng minh chúng có cùng chính sách.

Tương tự, thêm chuyển hoa thường, bỏ dấu hoặc cắt ngắn vào pipeline đòi hỏi xác định lại thứ tự. Không được coi các phép biến đổi là tự do hoán đổi.

### 6.3. Không tự động xóa mọi ký tự vô hình

Một số ký tự định dạng có thể ảnh hưởng cách hiển thị hoặc cách nối chữ. Xóa tất cả mà không mô tả chính sách vừa có thể gộp các đầu vào, vừa có thể làm hỏng văn bản hợp lệ của một số ngôn ngữ.

Nếu một loại ký tự không được hỗ trợ, một phương án rõ ràng hơn là từ chối đầu vào đó theo chính sách có phiên bản và hướng dẫn người dùng phù hợp. Việc từ chối cũng cần xem xét khả năng tiếp cận và ngôn ngữ; không thể coi danh sách cấm trong một ví dụ là phù hợp cho mọi hệ thống.

## 7. Ký tự nhìn giống nhau không nhất thiết tương đương Unicode

Chữ a Latin U+0061 và chữ а Cyrillic U+0430 có thể trông gần giống nhau nhưng là hai ký tự khác. NFC không làm chúng trở thành cùng một ký tự.

Unicode có cơ chế phân tích ký tự dễ gây nhầm lẫn trong UTS #39. Cơ chế đó giúp nhận diện rủi ro; không nên lấy biểu diễn phục vụ phát hiện nhầm lẫn rồi mặc nhiên dùng làm giá trị bí mật để xác minh. Xem [Unicode UTS #39](https://www.unicode.org/reports/tr39/).

Rủi ro phát sinh nếu một lớp giao diện thay ký tự “trông giống nhau”, trong khi máy chủ giữ nguyên; hoặc công cụ hỗ trợ chỉ hiển thị chuỗi mà không nhận ra khác biệt.

Cách xử lý cần nhất quán với chính sách đã đăng ký. Với đầu vào không được hỗ trợ, cung cấp thông báo phù hợp; không âm thầm ánh xạ sang một chữ cái khác để cố làm cho câu trả lời khớp.

## 8. Byte, độ dài và lỗi mã hóa cũng là một phần của chính sách

### 8.1. Độ dài chuỗi có nhiều đơn vị

Một giới hạn “256 ký tự” cần nói rõ là:

- 256 code unit UTF-16 của Java.
- 256 Unicode code point.
- 256 cụm ký tự hiển thị.
- Hay 256 byte sau mã hóa UTF-8.

Các đơn vị này không thay thế cho nhau. Một ký tự bổ sung có thể dùng hai code unit UTF-16; một ký tự hiển thị có thể chứa nhiều code point. Việc cắt bằng substring còn có thể chia đôi một cặp surrogate.

Cần giới hạn tài nguyên ngay tại lớp nhận request và kiểm tra lại sau chuẩn hóa, vì pipeline có thể thay đổi chiều dài. Nếu quá giới hạn thì từ chối theo hợp đồng; không tự cắt phần đuôi để làm đầu vào vừa với KDF.

Một số KDF hoặc thư viện có giới hạn đầu vào tính bằng byte. Chẳng hạn, OWASP lưu ý giới hạn 72 byte của phần lớn triển khai bcrypt. Phải kiểm tra hành vi của thư viện thực tế, đặc biệt với UTF-8; không để phần đuôi câu trả lời bị bỏ qua âm thầm. Xem [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#input-limits-of-bcrypt).

### 8.2. Thay thế dữ liệu lỗi có thể làm mất phân biệt

Nếu bộ giải mã thay các byte UTF-8 lỗi bằng ký tự thay thế thay vì báo lỗi, nhiều chuỗi byte khác nhau có thể đi tới cùng một chuỗi ký tự.

Java CharsetDecoder cho phép chọn báo lỗi, bỏ qua hoặc thay thế. Với dữ liệu xác thực, hợp đồng giải mã cần được xác định rõ từ đầu luồng nhận dữ liệu. Xem [Java CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html).

Ở chiều ngược lại, việc mã hóa chuỗi chứa surrogate đơn lẻ cũng phải được xử lý. Không nên để đầu vào không hợp lệ tự trở thành chuỗi byte thay thế trước KDF.

Một encoder UTF-8 được cấu hình REPORT có thể từ chối dữ liệu như vậy. Encoder không thể khôi phục byte gốc nếu một lớp trước đã thay thế chúng. Xem [Java CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html).

### 8.3. Chỉ giải mã theo hợp đồng giao thức

Không gọi URL decode lặp lại hoặc HTML decode câu trả lời “cho chắc”. Ví dụ, chuỗi ký tự phần trăm có thể là dữ liệu người dùng nhập, không phải một yêu cầu giải mã thêm.

Quá trình giải mã request, chuẩn hóa văn bản và mã hóa UTF-8 cho KDF phải là những bước được mô tả riêng. Mỗi lớp tự sửa chuỗi sẽ khiến hành vi tổng thể khó dự đoán.

## 9. Ví dụ Java: một chính sách NFC có phạm vi hẹp

Ví dụ dưới đây minh họa một **phiên bản chính sách giả định cho thành phần cũ**:

- Giữ nguyên dấu, hoa thường và khoảng trắng đầu cuối.
- Chỉ thống nhất tương đương chuẩn tắc bằng NFC.
- Từ chối chuỗi rỗng, chỉ có khoảng trắng, UTF-16 lỗi và một số nhóm ký tự không được hỗ trợ.
- Mã hóa UTF-8 ở chế độ báo lỗi, không cắt ngắn đầu vào.

Các giới hạn dùng để minh họa kiểm soát tài nguyên, không phải yêu cầu độ mạnh của bí mật. Chính sách này cố ý từ chối ký tự thuộc nhóm FORMAT; lựa chọn đó có thể loại bỏ đầu vào hợp lệ của một số ngôn ngữ. Cần thiết kế phạm vi hỗ trợ trước khi áp dụng thực tế và không áp ngược cho hash cũ.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public final class AnswerCanonicalizerV2 {
    public static final String VERSION = "ANSWER_NFC_V2";

    private static final int MAX_RAW_CODE_UNITS = 1024;
    private static final int MAX_CANONICAL_CODE_POINTS = 256;
    private static final int MAX_UTF8_BYTES = 1024;

    private AnswerCanonicalizerV2() {
    }

    public static byte[] canonicalBytes(String raw) {
        if (raw == null || raw.isEmpty()) {
            throw new IllegalArgumentException("ANSWER_REQUIRED");
        }
        if (raw.length() > MAX_RAW_CODE_UNITS) {
            throw new IllegalArgumentException("ANSWER_TOO_LONG");
        }

        requireWellFormedUtf16(raw);
        String canonical = Normalizer.normalize(
                raw, Normalizer.Form.NFC);

        int codePoints = canonical.codePointCount(
                0, canonical.length());
        if (codePoints == 0
                || codePoints > MAX_CANONICAL_CODE_POINTS) {
            throw new IllegalArgumentException("ANSWER_LENGTH");
        }

        boolean unsupported = canonical.codePoints().anyMatch(cp ->
                Character.isISOControl(cp)
                || Character.getType(cp) == Character.FORMAT
                || cp == 0xFFFD);
        if (unsupported) {
            throw new IllegalArgumentException("ANSWER_UNSUPPORTED");
        }

        boolean onlySpaces = canonical.codePoints().allMatch(cp ->
                Character.isWhitespace(cp)
                || Character.isSpaceChar(cp));
        if (onlySpaces) {
            throw new IllegalArgumentException("ANSWER_REQUIRED");
        }

        try {
            ByteBuffer encoded = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(canonical));

            if (encoded.remaining() > MAX_UTF8_BYTES) {
                throw new IllegalArgumentException("ANSWER_BYTES");
            }

            byte[] bytes = new byte[encoded.remaining()];
            encoded.get(bytes);
            return bytes;
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException("ANSWER_ENCODING");
        }
    }

    private static void requireWellFormedUtf16(String value) {
        for (int i = 0; i < value.length(); i++) {
            char current = value.charAt(i);

            if (Character.isHighSurrogate(current)) {
                if (i + 1 >= value.length()
                        || !Character.isLowSurrogate(
                                value.charAt(i + 1))) {
                    throw new IllegalArgumentException("ANSWER_ENCODING");
                }
                i++;
            } else if (Character.isLowSurrogate(current)) {
                throw new IllegalArgumentException("ANSWER_ENCODING");
            }
        }
    }
}
~~~

Hàm trả về byte để lớp KDF dùng đúng mã hóa đã quy định. Nó không băm, không so khớp hash và không quyết định người yêu cầu có được khôi phục hay không.

Các mã lỗi trong ví dụ là tín hiệu nội bộ. API công khai phải ánh xạ chúng theo ngữ cảnh để tránh tiết lộ sự tồn tại của tài khoản hoặc chi tiết bộ kiểm tra. Không đưa raw, canonical hoặc mảng byte vào thông báo lỗi, log hay tracing.

Đối với bản ghi có phiên bản khác, máy chủ phải chọn đúng bộ xử lý phiên bản đó. Tên V2 không có nghĩa được phép tự thay thế mọi quy tắc cũ bằng hàm trên.

## 10. Đăng ký và xác minh phải cùng một hợp đồng

Một pipeline đầy đủ cần xác định cả bước nào xảy ra và bước nào không được tự thêm.

~~~mermaid
flowchart TD
    A["Request có giới hạn kích thước"] --> B["Giải mã và parse đúng giao thức"]
    B --> C["Chọn bản ghi trong đúng tài khoản và tenant"]
    C --> D["Đọc phiên bản chuẩn hóa từ dữ liệu máy chủ"]
    D --> E{"Phiên bản được hỗ trợ?"}
    E -- "Không" --> F["Không xác minh bằng chính sách đoán"]
    E -- "Có" --> G["Kiểm tra đầu vào và chuẩn hóa đúng phiên bản"]
    G --> H["Mã hóa byte theo hợp đồng"]
    H --> I["Dùng API kiểm tra KDF"]
    I --> J["Kết quả khớp của thành phần cũ"]
    J --> K["Chính sách khôi phục đánh giá bằng chứng độc lập"]
~~~

Bản ghi bộ kiểm tra cần mang hoặc liên kết được với các thông tin sau:

| Thông tin | Vai trò |
| --- | --- |
| Tenant, tài khoản, mã câu hỏi | Không dùng nhầm bộ kiểm tra của người hoặc phạm vi khác |
| Phiên bản chính sách chuẩn hóa | Xác định chính xác pipeline đã tạo đầu vào cho KDF |
| Quy tắc mã hóa | Thống nhất chuỗi byte đầu vào |
| Thuật toán KDF, tham số, salt và hash | Phục vụ kiểm tra bằng thư viện phù hợp |
| Trạng thái hoạt động hoặc ngừng sử dụng | Không tiếp tục chấp nhận bộ kiểm tra đã bị thay thế |

Đây là mô hình dữ liệu của dịch vụ minh họa, không phải cấu trúc metadata của bài học.

Phiên bản phải do máy chủ kiểm soát. Không cho request tự gửi “dùng phiên bản dễ hơn”, và không mặc định phiên bản mới nhất khi bản ghi thiếu thông tin. Trường hợp không xác định cần đi tới quy trình xử lý đã thiết kế, không suy đoán bằng cách thử hàng loạt quy tắc.

Frontend có thể hỗ trợ nhập liệu, nhưng backend là nơi áp dụng hợp đồng có thẩm quyền. Nếu frontend âm thầm bỏ dấu trước khi gửi, backend nhận đầu vào đã mất thông tin và không thể kiểm tra lại ý định ban đầu.

Trong hệ thống nhiều dịch vụ, cần dùng chung đặc tả và bộ dữ liệu minh họa theo phiên bản. “Cùng gọi là lowercase” không bảo đảm Java, JavaScript và một collation của cơ sở dữ liệu có cùng điều kiện so khớp.

## 11. Thay đổi chính sách và xử lý hash cũ

### 11.1. Không thể di chuyển bằng cách chỉ sửa nhãn phiên bản

Giả sử bộ kiểm tra hiện tại được tạo từ:

~~~text
V1:
    lowercase + bỏ dấu + xóa khoảng trắng
~~~

Sau đó nhóm phát triển quyết định dùng NFC và giữ nguyên mọi phân biệt còn lại.

Nếu chỉ đổi metadata từ V1 sang V2, đầu vào đưa vào KDF khi xác minh không còn giống quy trình tạo hash. Người dùng thật có thể bị từ chối.

Quan trọng hơn, hash của giá trị đã mất dấu không cho biết nguyên bản là “Hoa”, “Hòa” hay “Họa”. Không thể khôi phục thông tin đó từ hash để tạo một bộ kiểm tra mới có phân biệt dấu.

### 11.2. Không thử mọi cách đến khi khớp

Một bản sửa nhanh thường có dạng:

~~~text
Thử raw
Nếu sai, thử trim
Nếu sai, thử lowercase
Nếu sai, thử bỏ dấu
Nếu sai, thử quy tắc cũ
Chấp nhận nếu bất kỳ cách nào khớp
~~~

Cách này làm điều kiện chấp nhận thành hợp của nhiều tập đầu vào. Nó cũng có thể biến một request thành nhiều lần kiểm tra ứng viên và nhiều lần gọi KDF tốn tài nguyên.

Việc một bộ kiểm tra chỉ khớp sau nhánh fallback không chứng minh nhánh đó an toàn. Mỗi bản ghi cần một chính sách xác định, thay vì một danh sách thử mang tính suy đoán.

### 11.3. Nâng chi phí KDF và đổi chuẩn hóa là hai việc khác nhau

Sau khi xác minh theo đúng quy tắc cũ, hệ thống có thể có đủ đầu vào để nâng chi phí KDF mà vẫn giữ nguyên quan hệ tương đương cũ. Việc đó không phục hồi những phân biệt đã bị xóa.

Nếu muốn đổi quan hệ tương đương hoặc đăng ký phương án khôi phục mới, cần một quy trình có bằng chứng độc lập đủ tin cậy. Không dựa riêng vào câu trả lời cũ để cho người yêu cầu định nghĩa lại bí mật, tắt MFA hoặc thay kênh khôi phục.

Hướng chuyển đổi phù hợp thường là:

1. Xác định các phiên bản thực sự đang tồn tại.
2. Ngừng thêm người dùng mới vào cơ chế câu hỏi bảo mật.
3. Giữ bộ xác minh cũ có kiểm soát trong giai đoạn chuyển tiếp.
4. Khi người dùng có thể xác thực bằng phương thức thích hợp, hướng dẫn thiết lập phương án khôi phục thay thế.
5. Thu hồi bộ kiểm tra cũ sau khi chuyển đổi, xử lý dữ liệu theo chính sách lưu giữ.

### 11.4. Nâng runtime cũng cần xem xét

Không nên khẳng định mỗi lần nâng Unicode đều làm thay đổi kết quả NFC của mọi chuỗi; Unicode có các cam kết ổn định. Tuy vậy, pipeline tổng thể còn phụ thuộc ánh xạ hoa thường, phân loại ký tự, thư viện, dữ liệu mới được hỗ trợ và mã ứng dụng.

Cần ghi lại môi trường thực thi phù hợp với đặc tả và chạy các trường hợp tương thích khi nâng JDK hoặc thay thư viện. Không xử lý sai khác bằng cách tự động thêm nhánh chuẩn hóa khoan dung hơn.

## 12. Các trường hợp minh họa cho chính sách V2

Bảng dưới mô tả kết quả theo đúng hàm ví dụ, không phải khuyến nghị áp dụng hồi tố cho dữ liệu đang có. Các chuỗi có ký hiệu \u được viết theo cách biểu diễn Unicode escape để nhìn rõ code point.

| Đầu vào A | Đầu vào B hoặc điều kiện | Kết quả theo V2 |
| --- | --- | --- |
| H\u00F2a | Ho\u0300a | Cùng dạng NFC, cùng byte UTF-8 |
| Hoa | Hòa | Khác nhau |
| LAN | Lan | Khác nhau |
| “ Lan ” | “Lan” | Khác nhau vì giữ khoảng trắng đầu cuối |
| Lan\u00A0 | Lan\u0020 | Khác nhau vì NFC không gộp hai dấu cách đó |
| \uFF21 | A | Khác nhau |
| \u2460 | 1 | Khác nhau |
| a Latin U+0061 | а Cyrillic U+0430 | Khác nhau |
| Lan\u200B | Có ký tự ZERO WIDTH SPACE thuộc nhóm FORMAT | Bị từ chối theo lựa chọn của ví dụ |
| Surrogate cao \uD800 đứng một mình | UTF-16 không hợp lệ | Bị từ chối |
| Chuỗi chỉ có U+0020 và U+00A0 | Không có nội dung ngoài khoảng trắng | Bị từ chối |
| Chuỗi vượt giới hạn raw | Dù một phép chuẩn hóa có thể rút ngắn | Bị từ chối trước xử lý sâu |

Ngoài các giá trị cụ thể, cần kiểm chứng những bất biến sau trong thiết kế:

- Cùng phiên bản và cùng đầu vào hợp lệ cho cùng đầu ra trên các nút xử lý.
- Đăng ký và xác minh dùng cùng thứ tự bước, mã hóa và giới hạn.
- Chuẩn hóa NFC lặp lại không thay đổi kết quả đã chuẩn hóa; tính chất này không chứng minh các bước mất thông tin khác là an toàn.
- Phiên bản không được hỗ trợ không tự rơi về một chính sách khác.
- Nguồn gửi không thể né ngân sách thử bằng cách thay hoa thường, dấu hoặc session.
- Quá giới hạn dẫn đến từ chối, không dẫn đến cắt ngắn.
- Không log câu trả lời thô, câu trả lời chuẩn hóa hoặc hash dùng để dò lại câu trả lời.
- Kết quả khớp không tự cấp session hoặc quyền thay phương thức xác thực.

Đây là tập yêu cầu để xây dựng kiểm tra cho một triển khai; bài học không báo cáo đã chạy kiểm thử chương trình.

## 13. So khớp khoan dung làm khó kiểm soát lạm dụng

Bỏ dấu, tự sửa lỗi chính tả hoặc chấp nhận khoảng cách chỉnh sửa có thể giúp một số người dùng nhớ gần đúng câu trả lời. Đồng thời, những cách đó mở rộng vùng được chấp nhận quanh mỗi giá trị.

Nếu còn thử nhiều dạng cho một request, giới hạn “năm request” không còn có nghĩa là năm ứng viên được kiểm tra. Ngân sách cần xét công việc thực tế và các đường xử lý, đồng thời tránh mở rộng điều kiện so khớp ngay từ đầu.

Khóa giới hạn thử nên gắn với tài khoản hoặc hồ sơ ở phía máy chủ, kết hợp kiểm soát theo nguồn và toàn dịch vụ. Không lấy nguyên văn câu trả lời làm khóa duy nhất: thay một dấu cách có thể tạo khóa mới. Cũng không ghi câu trả lời hoặc một hash nhanh của nó vào hệ thống đo lường để phân biệt các lần thử; không gian đáp án thấp có thể cho phép dò ngược.

Phản hồi như “đúng sau khi bỏ dấu”, “chỉ sai một ký tự” hoặc “câu thứ hai đã khớp” còn giúp người yêu cầu điều chỉnh từng bước. API khôi phục chưa xác minh không nên trở thành công cụ kiểm tra gần đúng dữ kiện cá nhân.

Ngược lại, từ chối đầu vào chưa hỗ trợ không được tự dẫn đến khóa toàn bộ tài khoản. Người dùng vẫn cần có thể đăng nhập bằng phương thức hợp lệ khác và tiếp cận quy trình hỗ trợ phù hợp.

## 14. Ví dụ thiết kế: hỗ trợ tiếng Việt nhưng giữ ranh giới khôi phục

Giả sử hệ thống cũ lưu câu trả lời tên người thân. Người dùng đã nhập “Hòa”, nhưng một bàn phím khác gửi dạng có dấu kết hợp. Cùng lúc, người tấn công chỉ đoán được “Hoa”.

Có hai cách sửa giả định:

| Cách xử lý | Người dùng thật với dạng dấu kết hợp | Người chỉ đoán “Hoa” | Hệ quả |
| --- | --- | --- | --- |
| Bỏ toàn bộ dấu trước khi kiểm tra | Có thể được chấp nhận | Có thể được chấp nhận | Mở rộng lớp đáp án sang tên không dấu |
| Chuẩn hóa NFC theo hợp đồng đã thiết lập | Có thể thống nhất biểu diễn “Hòa” | Vẫn khác “Hòa” | Giải quyết khác biệt biểu diễn có phạm vi hẹp |

Tuy nhiên, cách thứ hai chỉ hoạt động đúng với bộ kiểm tra được tạo theo cùng hợp đồng. Nếu hash cũ được tạo trực tiếp từ chuỗi chưa chuẩn hóa, không thể tùy ý đổi verifier sang NFC mà cho rằng dữ liệu đã tự chuyển đổi.

Ngay cả khi câu trả lời khớp, hệ thống vẫn chưa có bằng chứng độc lập đủ để tắt MFA hoặc thêm passkey. Việc khôi phục cần dựa vào phương thức còn kiểm soát, mã khôi phục hợp lệ hoặc quy trình xác minh khác đã được thiết kế.

Khi bằng chứng đạt chính sách, quyền khôi phục cấp ra cần gắn với tài khoản, hồ sơ, hành động và thời hạn; được tiêu thụ một lần khi thay đổi hoàn tất. Sau sự cố nghi chiếm đoạt, hệ thống còn phải xử lý session, refresh token, grant cũ và thông báo theo phạm vi rủi ro. Một lỗi chuẩn hóa không được trở thành lý do bỏ qua các bước đó.

## 15. Ranh giới áp dụng trong module khôi phục tài khoản

Không dùng cùng bộ chuẩn hóa câu trả lời cho mọi loại đầu vào:

| Đầu vào | Ranh giới xử lý |
| --- | --- |
| Câu trả lời bảo mật cũ | Theo chính sách có phiên bản đã gắn với bộ kiểm tra |
| Mật khẩu | Theo hợp đồng mật khẩu riêng; không tự kế thừa quy tắc bỏ dấu của câu hỏi |
| Token hoặc recovery code | Theo định dạng và quy tắc so khớp đã được thiết kế cho loại mã đó |
| Định danh tài khoản | Theo chính sách định danh, tách khỏi xử lý bí mật |
| Dữ liệu passkey và chữ ký | Theo giao thức và thư viện mật mã; không đưa qua bộ sửa văn bản của câu trả lời |
| Dữ liệu hiển thị, tìm kiếm | Theo mục đích hiển thị hoặc tìm kiếm, không quyết định bí mật nào khớp |

Một thay đổi có vẻ tiện lợi ở thư viện xử lý chuỗi có thể ảnh hưởng nhiều nhánh khôi phục nếu ranh giới này không rõ. Đặc biệt, không chuyển chữ thường hoặc xóa ký tự trong token chỉ vì quy tắc đó từng được dùng cho câu trả lời.

Khi xem xét thiết kế, cần xác định chính xác **tập đầu vào nào được coi là cùng một câu trả lời, tập đó được tạo theo phiên bản nào, và kết quả khớp được phép ảnh hưởng đến quyền gì**. Làm rõ ba điều này giúp tránh cả việc từ chối người dùng thật lẫn việc mở rộng quyền khôi phục cho người chỉ biết một biến thể dễ đoán.
