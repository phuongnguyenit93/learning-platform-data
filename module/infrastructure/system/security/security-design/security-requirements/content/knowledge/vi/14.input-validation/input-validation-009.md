# Encoding validation

## 1. Vì sao encoding là một phần của yêu cầu bảo mật?

Encoding validation là việc xác minh dữ liệu đầu vào tuân theo các quy tắc biểu diễn đã được giao thức và ứng dụng chấp nhận. Nó trả lời những câu hỏi cụ thể: byte được hiểu bằng bộ mã nào, chuỗi có được giải mã nguyên vẹn không, escape thuộc lớp nào, biểu diễn Unicode có hợp lệ không và giá trị nào thực sự được đưa vào kiểm tra nghiệp vụ.

Nếu các thành phần diễn giải cùng một đầu vào theo cách khác nhau, kiểm soát bảo mật có thể kiểm tra một giá trị nhưng nghiệp vụ lại dùng một giá trị khác. Ngay cả khi không có tấn công, việc đoán charset hoặc âm thầm thay thế byte lỗi cũng có thể làm hỏng tên người, mã định danh và nội dung được ký hoặc đối chiếu.

Ví dụ, một HTTP endpoint công bố nhận JSON bằng UTF-8. Yêu cầu “đọc body thành String” chưa xác định cách xử lý một chuỗi byte UTF-8 sai. Nếu decoder tự thay byte lỗi bằng ký tự thay thế, hệ thống có thể tiếp tục xử lý dữ liệu mà người gửi không thực sự biểu diễn hợp lệ.

Một yêu cầu rõ hơn là:

> Endpoint chỉ chấp nhận body JSON được mã hóa UTF-8. Byte sequence không hợp lệ phải làm request bị từ chối trước khi parse nghiệp vụ. Không đoán charset khác và không sửa byte lỗi bằng ký tự thay thế để tiếp tục xử lý.

Trong thiết kế security requirements, yêu cầu này cần gắn với chủ thể thực thi, giới hạn tài nguyên, thứ tự xử lý, hành vi khi lỗi và bằng chứng kiểm thử. “Có dùng UTF-8” không tự chứng minh tất cả những điều đó đã được đáp ứng.

## 2. Phân biệt các lớp biểu diễn

### 2.1. Byte encoding, escape và normalization

| Cơ chế | Vai trò | Ví dụ | Câu hỏi cần đặc tả |
| --- | --- | --- | --- |
| Character encoding | Ánh xạ byte và ký tự | UTF-8 | Chấp nhận charset nào, xử lý byte lỗi ra sao? |
| Percent-encoding | Biểu diễn byte trong thành phần URL | `%20` | Thành phần nào decode, theo giao thức nào? |
| JSON escape | Biểu diễn ký tự trong JSON string | `\u00E9` | Parser xử lý escape và surrogate như thế nào? |
| Base64 | Biểu diễn dữ liệu nhị phân bằng một bảng ký tự | Một field chứa dữ liệu đính kèm | Chọn alphabet, padding và giới hạn dữ liệu sau decode nào? |
| Unicode normalization | Đưa một số biểu diễn Unicode tương đương về dạng đã chọn | NFC | Field nào chuẩn hóa, trước hay sau kiểm tra nào? |
| Output encoding | Giữ dữ liệu ở vai trò dữ liệu trong ngữ cảnh đầu ra | Encode khi hiển thị HTML | Encode ở điểm xuất nào và theo ngữ cảnh nào? |

Các cơ chế này không thay thế cho nhau. Chuỗi UTF-8 hợp lệ chưa chắc là JSON hợp lệ. JSON hợp lệ chưa chắc thỏa schema. Dữ liệu đã chuẩn hóa NFC chưa chắc được phép trong một mã tài khoản. Kiểm tra encoding đầu vào cũng không thay thế output encoding khi dữ liệu được hiển thị.

`Content-Encoding`, chẳng hạn một cơ chế nén HTTP được hỗ trợ, còn là một lớp khác với charset. Nếu hệ thống giải nén body thì cần kiểm soát cả kích thước và chi phí sau giải nén, trước khi tiếp tục giải mã ký tự và parse.

### 2.2. Các dạng tương đương không phải lúc nào cũng có cùng chính sách

Trong một JSON string, ký tự `é` có thể xuất hiện trực tiếp trong văn bản UTF-8 hoặc qua escape `\u00E9`. Nếu parser xử lý đúng, hai cách viết tạo cùng giá trị ký tự ở lớp ứng dụng.

Ngược lại, chuỗi gồm `e` rồi một combining acute accent là một biểu diễn Unicode khác với code point `é`. Chúng có thể được đưa về cùng dạng khi ứng dụng chọn NFC, nhưng không phải cứ decode UTF-8 là đã tự có normalization.

Với một số dữ liệu như chữ ký trên byte, hash của file hoặc token có giao thức riêng, thay đổi byte hay ký tự có thể làm thay đổi ý nghĩa. Chính sách normalization phải được chọn theo từng loại dữ liệu; không áp dụng một hàm “decode và làm sạch” chung cho mọi field.

## 3. Rủi ro do diễn giải không thống nhất

### 3.1. Chấp nhận byte lỗi bằng cách thay thế

Một decoder có thể được cấu hình báo lỗi, bỏ qua dữ liệu lỗi hoặc thay thế bằng ký tự khác. Đối với đầu vào cần bảo toàn, các lựa chọn đó dẫn đến hành vi khác nhau.

Nếu nhiều chuỗi byte khác nhau cùng bị sửa thành một chuỗi ký tự, ứng dụng có thể mất khả năng phân biệt dữ liệu ban đầu. Điều này đặc biệt đáng chú ý với định danh, đối chiếu, kiểm tra trùng và dữ liệu được dùng để đưa ra quyết định bảo mật.

Không nên phát hiện lỗi decode bằng cách tìm ký tự `U+FFFD` sau khi đã decode. Ký tự thay thế này cũng có thể được người gửi biểu diễn hợp lệ trong UTF-8. Nếu cần biết byte có hợp lệ không, phải dùng kết quả và chế độ lỗi của decoder tại biên byte.

### 3.2. Đoán charset hoặc dùng mặc định của môi trường

Nếu một thành phần đọc UTF-8 còn thành phần khác đọc theo bộ mã mặc định của hệ điều hành, cùng byte có thể thành các chuỗi khác nhau. Việc thử lần lượt nhiều charset cho đến khi “đọc được” cũng không chứng minh đã tìm đúng ý định của người gửi.

Yêu cầu nên chỉ rõ charset từ hợp đồng giao thức. Nếu một kênh nhập thật sự hỗ trợ nhiều charset, cần có cơ chế khai báo và lựa chọn rõ ràng, giới hạn charset được chấp nhận và hành vi khi khai báo mâu thuẫn. Không tự mở rộng phạm vi cho một endpoint vốn chỉ hỗ trợ UTF-8.

### 3.3. Decode lặp hoặc decode sai thành phần

Percent-encoding thuộc về các thành phần và quy tắc URL cụ thể. Nếu framework đã decode một giá trị, ứng dụng không nên decode lần nữa chỉ vì chuỗi còn chứa dấu `%`.

Ví dụ, `%25` biểu diễn ký tự `%`. Sau một lần decode, chuỗi kết quả có thể trông giống một escape khác. Tự decode tiếp làm giá trị thay đổi so với giá trị đã được kiểm tra hoặc so với hợp đồng của người gọi.

Tương tự, ký tự `+` được xử lý như dấu cách trong dữ liệu form theo quy tắc form tương ứng, nhưng không có cùng ý nghĩa đó trong mọi thành phần URL. Không dùng một hàm dành cho form để tùy tiện giải mã toàn bộ URL hay path.

### 3.4. Kiểm tra trước một phép biến đổi làm thay đổi giá trị

Một bộ lọc có thể chấp nhận chuỗi trước decode, trong khi truy vấn hoặc định tuyến lại dùng chuỗi sau decode. Một bước normalization diễn ra sau kiểm tra allowlist cũng có thể tạo ra giá trị khác với biểu diễn đã được kiểm tra.

Nguyên tắc cần bảo vệ là: các kiểm tra liên quan phải áp dụng cho biểu diễn mà nghiệp vụ sẽ sử dụng. Đồng thời, các giới hạn tài nguyên phải được thực thi từ những bước trước đó; không chờ đến biểu diễn cuối mới bắt đầu chặn kích thước.

## 4. Viết hợp đồng encoding ở từng biên tin cậy

Một yêu cầu encoding có thể bắt đầu bằng các thuộc tính sau:

1. Kênh đầu vào và thành phần dữ liệu: HTTP body, path, query, file import hay message.
2. Dạng byte hoặc văn bản được hỗ trợ và nguồn xác định charset.
3. Giới hạn kích thước trước và sau các bước decode hoặc giải nén.
4. Chế độ lỗi khi gặp byte, escape hoặc cấu trúc không hợp lệ.
5. Thành phần duy nhất chịu trách nhiệm cho từng lớp decode.
6. Biểu diễn nội bộ dùng cho kiểm tra schema và nghiệp vụ.
7. Chính sách Unicode và normalization theo từng field.
8. Hành vi phản hồi, quan sát và tác động được phép khi từ chối.

Ví dụ đặc tả cho một endpoint JSON:

```text
ID: SEC-ENC-JSON-01
Nguồn: HTTP body của endpoint tạo hồ sơ hiển thị.
Media type: application/json; charset chỉ được phép là UTF-8 nếu có khai báo.
Charset khi không khai báo: UTF-8 theo hợp đồng của endpoint.
Body limit: 16.384 byte thực nhận; không chỉ dựa vào Content-Length.
HTTP content coding: endpoint này chỉ hỗ trợ dữ liệu không nén.
UTF-8 error policy: từ chối byte sequence không hợp lệ; không replace hoặc ignore.
BOM policy: endpoint này từ chối UTF-8 BOM ở đầu body.
JSON escape: xử lý đúng một lần bởi JSON parser.
String policy: từ chối surrogate không ghép cặp sau khi parse.
Normalization: chỉ áp dụng cho field được nêu trong schema nghiệp vụ.
Failure effect: không tạo hoặc sửa hồ sơ khi bất kỳ bước bắt buộc nào thất bại.
```

Giới hạn 16.384 byte và quyết định từ chối BOM là lựa chọn minh họa của endpoint này, không phải chính sách bắt buộc cho mọi ứng dụng. Một hệ thống chọn hành vi khác cần mô tả và triển khai nhất quán.

Yêu cầu media type phải được kiểm tra bằng parser header phù hợp. Tên tham số, giá trị charset và cú pháp header có quy tắc của giao thức; không thay toàn bộ việc parse bằng so sánh nguyên chuỗi header với một literal duy nhất.

## 5. UTF-8 hợp lệ và Unicode hợp lệ

### 5.1. Ví dụ byte sequence

| Dữ liệu | Byte UTF-8 hoặc byte đang xét | Kết quả cần hiểu |
| --- | --- | --- |
| `A` | `41` | UTF-8 hợp lệ cho một ký tự ASCII |
| `é` dạng một code point | `C3 A9` | UTF-8 hợp lệ |
| `e` và combining acute accent | `65 CC 81` | UTF-8 hợp lệ, biểu diễn khác trước normalization |
| Một emoji `U+1F600` | `F0 9F 98 80` | UTF-8 hợp lệ cho code point ngoài BMP |
| Sequence có continuation byte sai | `C3 28` | UTF-8 không hợp lệ |
| Sequence bị cắt | `F0 9F 98` | UTF-8 không hợp lệ khi kết thúc dữ liệu |
| Dạng mã hóa dài hơn cần thiết | `C0 AF` | Không phải UTF-8 hợp lệ |
| Byte biểu diễn vùng surrogate | `ED A0 80` | Không phải UTF-8 hợp lệ |
| Giá trị vượt miền Unicode | `F4 90 80 80` | Không phải UTF-8 hợp lệ |

Không cần tự viết một decoder bằng các điều kiện byte này. Chúng là ví dụ để xây tiêu chí kiểm thử và hiểu chính sách. Khi triển khai, nên dùng decoder có chế độ báo lỗi rõ ràng và bảo đảm lớp trước không âm thầm sửa dữ liệu trước khi decoder đó được gọi.

### 5.2. JSON escape có thể tạo một vấn đề sau bước UTF-8

Một body chứa các ký tự ASCII của escape `\uD800` có thể hoàn toàn hợp lệ ở lớp UTF-8. Vấn đề xuất hiện khi JSON parser chuyển escape thành nội dung chuỗi: đó là một high surrogate không có low surrogate ghép cặp.

Một số môi trường có thể giữ chuỗi như vậy trong biểu diễn UTF-16. Vì thế, nếu hợp đồng yêu cầu chuỗi chỉ chứa Unicode scalar value hợp lệ, phải kiểm tra kết quả chuỗi sau parse hoặc cấu hình parser thực thi yêu cầu tương đương. Chỉ kiểm tra byte UTF-8 không bao phủ được lớp này.

Một cặp surrogate đúng trong UTF-16 biểu diễn một code point ngoài BMP; bản thân cặp đúng đó không phải lỗi. Không từ chối toàn bộ surrogate code unit mà bỏ qua cấu trúc ghép cặp, vì cách làm đó sẽ loại cả các ký tự hợp lệ ngoài BMP.

### 5.3. Hợp lệ về biểu diễn chưa phải hợp lệ theo chính sách field

NUL, nhiều ký tự điều khiển và các ký tự có tác động hiển thị có thể được biểu diễn hợp lệ về mặt encoding. Việc một field cho phép chúng hay không là chính sách ứng dụng cần được đặc tả riêng.

Một field tên hiển thị một dòng có thể cấm các nhóm điều khiển xác định. Một field nội dung nhiều dòng lại có thể cần newline. Một mã máy có thể chỉ chấp nhận ASCII. Không nên gọi mọi ký tự bị chính sách nghiệp vụ cấm là “UTF-8 sai”.

Tương tự, không được suy ra mọi code point có hình dạng lạ đều không hợp lệ về Unicode. Chính sách về chữ viết, dấu kết hợp hoặc khả năng hiển thị phải được đánh giá theo loại dữ liệu và người dùng mà sản phẩm hỗ trợ.

## 6. Giới hạn độ dài phải gắn với đơn vị

“Tên tối đa 80 ký tự” có thể được hiểu thành byte UTF-8, UTF-16 code unit, Unicode code point hoặc cụm ký tự hiển thị. Các cách đếm này không luôn bằng nhau.

| Nội dung | Byte UTF-8 | UTF-16 code unit | Unicode code point |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| `é` một code point | 2 | 1 | 1 |
| `e` và dấu kết hợp | 3 | 2 | 2 |
| Emoji `U+1F600` | 4 | 2 | 1 |

Bảng chỉ xét nội dung chuỗi, chưa gồm dấu ngoặc kép, escape hoặc phần còn lại của JSON. Số code point cũng không luôn bằng số ký tự mà người dùng cảm nhận, vì một cụm hiển thị có thể gồm nhiều code point.

Một thiết kế có thể dùng nhiều giới hạn đồng thời: giới hạn body bằng byte để kiểm soát tài nguyên, giới hạn field trước normalization để chặn chi phí và giới hạn sau normalization theo đơn vị sản phẩm đã chọn. Tầng lưu trữ và đầu ra phải hỗ trợ miền đã chấp nhận.

Không đợi đến khi đã đọc toàn bộ một stream không giới hạn mới đo độ dài String. Với xử lý streaming, cần giữ trạng thái decoder giữa các chunk; một sequence UTF-8 hợp lệ có thể bị chia ở ranh giới hai chunk. Chỉ đến khi hết stream mà sequence vẫn thiếu thì mới kết luận bị cắt.

## 7. Normalization theo từng field

Normalization không phải bước bắt buộc cho mọi dữ liệu. Nếu một field chọn NFC, yêu cầu cần ghi rõ normalization diễn ra trước kiểm tra nghiệp vụ nào, giá trị nào được lưu và dùng để tìm kiếm hoặc kiểm tra trùng.

Ví dụ, tên hiển thị có thể được chuẩn hóa NFC để tránh lưu nhiều biểu diễn tương đương theo chính sách sản phẩm. Một mã định danh ASCII không cần normalization để mở rộng đầu vào ngoài ASCII. Token hoặc nội dung được xác minh chữ ký phải được xử lý theo giao thức của nó, không tự normalize trước khi xác minh.

Các dạng normalization khác nhau có mục đích khác nhau. Không đổi NFC thành một dạng compatibility normalization chỉ vì muốn “làm sạch mạnh hơn”: việc đó có thể gộp các ký tự mà hợp đồng trước đó còn phân biệt.

Normalization cũng không giải quyết toàn bộ ký tự nhìn giống nhau giữa các hệ chữ, không cấp quyền sử dụng một định danh và không thay thế chính sách tên duy nhất. Nếu định danh ảnh hưởng bảo mật hoặc gây nhầm lẫn danh tính, đó là các yêu cầu riêng cần được thiết kế rõ.

## 8. Minh họa Java: decode nghiêm ngặt và kiểm tra chuỗi sau parse

Ví dụ sau minh họa hai trách nhiệm khác nhau:

- Giải mã một body UTF-8 đã được thu nhận trong giới hạn.
- Kiểm tra `displayName` sau khi JSON parser đã tạo String.

Hợp đồng minh họa cho `displayName` là: tối đa 256 code point trước normalization, chuẩn hóa NFC, sau đó có từ 1 đến 80 code point, không chỉ gồm khoảng trắng theo `String.isBlank()`, không có điều khiển C0 hoặc C1. Không tự trim và không tự đổi hoa thường.

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public final class Utf8InputPolicy {
    private static final int MAX_BODY_BYTES = 16_384;
    private static final int MAX_RAW_NAME_CODE_POINTS = 256;
    private static final int MAX_RAW_NAME_UTF16_UNITS = 512;
    private static final int MAX_NORMALIZED_NAME_CODE_POINTS = 80;

    private Utf8InputPolicy() {
    }

    public static String decodeBody(byte[] body) {
        if (body == null || body.length == 0) {
            throw new InvalidInput("EMPTY_BODY");
        }
        if (body.length > MAX_BODY_BYTES) {
            throw new InvalidInput("BODY_TOO_LARGE");
        }
        if (hasUtf8Bom(body)) {
            throw new InvalidInput("UTF8_BOM_NOT_ALLOWED");
        }

        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(body))
                    .toString();
        } catch (CharacterCodingException ex) {
            throw new InvalidInput("INVALID_UTF8");
        }
    }

    public static String validateDisplayName(String value) {
        if (value == null) {
            throw new InvalidInput("DISPLAY_NAME_REQUIRED");
        }
        if (value.length() > MAX_RAW_NAME_UTF16_UNITS) {
            throw new InvalidInput("DISPLAY_NAME_TOO_LARGE");
        }

        requireUnicodeScalars(value);

        int rawCount = value.codePointCount(0, value.length());
        if (rawCount > MAX_RAW_NAME_CODE_POINTS) {
            throw new InvalidInput("DISPLAY_NAME_TOO_LARGE");
        }

        String normalized = Normalizer.normalize(
                value, Normalizer.Form.NFC);

        int count = normalized.codePointCount(0, normalized.length());
        if (count < 1
                || count > MAX_NORMALIZED_NAME_CODE_POINTS
                || normalized.isBlank()) {
            throw new InvalidInput("DISPLAY_NAME_INVALID");
        }

        boolean hasControl = normalized.codePoints()
                .anyMatch(cp -> (cp >= 0x0000 && cp <= 0x001F)
                        || (cp >= 0x007F && cp <= 0x009F));
        if (hasControl) {
            throw new InvalidInput("DISPLAY_NAME_CONTROL_NOT_ALLOWED");
        }

        return normalized;
    }

    private static void requireUnicodeScalars(String value) {
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);

            if (Character.isHighSurrogate(current)) {
                if (index + 1 >= value.length()
                        || !Character.isLowSurrogate(value.charAt(index + 1))) {
                    throw new InvalidInput("INVALID_UNICODE_STRING");
                }
                index++;
            } else if (Character.isLowSurrogate(current)) {
                throw new InvalidInput("INVALID_UNICODE_STRING");
            }
        }
    }

    private static boolean hasUtf8Bom(byte[] body) {
        return body.length >= 3
                && (body[0] & 0xFF) == 0xEF
                && (body[1] & 0xFF) == 0xBB
                && (body[2] & 0xFF) == 0xBF;
    }

    public static final class InvalidInput extends RuntimeException {
        public InvalidInput(String code) {
            super(code);
        }
    }
}
```

Các điểm cần hiểu khi dùng minh họa:

1. `decodeBody()` được gọi trên byte gốc của lớp body mà endpoint đã quyết định hỗ trợ. Nếu framework đã chuyển body thành String bằng chế độ thay thế, gọi hàm này trên byte được encode lại từ String không khôi phục được bằng chứng về byte ban đầu.
2. Việc kiểm tra `byte[].length` không tự giới hạn chi phí thu nhận body. HTTP adapter vẫn phải chặn số byte thực đọc trước khi cấp phát quá nhiều bộ nhớ.
3. JSON parser nằm giữa hai hàm. Nó phải xử lý cấu trúc, escape, kiểu field và các quy tắc schema đã công bố; không truyền cả văn bản JSON vào hàm kiểm tra tên.
4. Kiểm tra surrogate diễn ra sau parse để bao phủ cả chuỗi do escape tạo ra.
5. Giới hạn 512 UTF-16 code unit là trần sớm cho field thô. Với tối đa 256 code point hợp lệ, mỗi code point dùng không quá hai code unit; giới hạn nghiệp vụ cuối vẫn được tính riêng sau NFC.
6. Hệ thống sử dụng String được trả về từ `validateDisplayName()` cho các kiểm tra và lưu trữ tiếp theo. Không validate kết quả normalized rồi quay lại lưu giá trị raw trong cùng vai trò nghiệp vụ.

Chính sách minh họa không tuyên bố tên đã an toàn cho mọi ngữ cảnh hiển thị, không giải quyết toàn bộ ký tự gây nhầm lẫn và không xác định quyền sửa hồ sơ. Những trách nhiệm đó cần kiểm soát riêng.

## 9. Encoding validation cho các kênh khác

### 9.1. Query parameter và path

Cần xác định gateway, HTTP server và framework parse, decode và chuyển tiếp những thành phần nào. Khi ứng dụng nhận một giá trị đã decode, nó kiểm tra giá trị đó theo schema, không tự thực hiện thêm một vòng URL decode.

Chính sách với escape sai, encoding sai và tham số lặp phải nhất quán giữa các lớp. Nếu proxy chấp nhận một dạng mà backend hiểu khác, việc chặn ở một lớp riêng lẻ có thể không bảo vệ đúng tài nguyên được truy cập cuối cùng.

Với path, cần phân biệt cấu trúc đường dẫn với dữ liệu trong một segment. Không decode toàn bộ URI theo cách làm thay đổi ranh giới thành phần rồi mới giả định kết quả vẫn trỏ tới cùng tài nguyên. Đối với định danh tài nguyên, ánh xạ một ID có hợp đồng rõ thường dễ kiểm soát hơn cho phép người dùng cung cấp đường dẫn tùy ý.

### 9.2. File import

Một file CSV hoặc văn bản cần hợp đồng charset, BOM, dấu phân cách và lỗi parse riêng. Không coi mọi file tải lên là UTF-8 hoặc dựa duy nhất vào phần mở rộng để quyết định cách đọc.

Nếu sản phẩm hỗ trợ một tập charset cho import, nguồn khai báo, cách lựa chọn và giới hạn fallback phải rõ. Kết quả import phải cho biết lỗi ở đâu theo cách không tiết lộ dữ liệu vượt phạm vi, đồng thời có chính sách về ghi một phần hay rollback toàn bộ.

File nhị phân không nên bị đưa qua decoder ký tự như một bước “làm sạch”. Nó cần validation định dạng, kích thước và cách xử lý phù hợp với loại file.

### 9.3. Field Base64

Field chứa Base64 cần quy định biến thể alphabet, padding, khoảng trắng có được chấp nhận không và giới hạn byte sau decode. Chấp nhận mọi biến thể mà một thư viện có thể đọc được có thể rộng hơn hợp đồng API.

Decode Base64 thành công chỉ chứng minh dữ liệu đạt quy tắc biểu diễn tương ứng. Nếu payload được công bố là ảnh hoặc tài liệu, nó vẫn cần kiểm tra định dạng và chính sách của loại dữ liệu đó.

### 9.4. Message và dữ liệu nội bộ

Consumer cần biết schema và encoding của message; không nên dùng charset mặc định của tiến trình. Dữ liệu đi qua hệ thống cũ hoặc một đường nhập khác vẫn có thể không thỏa hợp đồng hiện tại.

Tuy nhiên, không cần decode lại một String nội bộ chỉ vì muốn “kiểm tra UTF-8”. Byte gốc và lớp ký tự là hai biên khác nhau. Nếu ứng dụng cần bảo đảm String không có surrogate lẻ hoặc cần một chính sách field, hãy kiểm tra trực tiếp bất biến đó ở biên phù hợp.

## 10. Thiết kế tiêu chí kiểm thử

Phần này mô tả bằng chứng mà yêu cầu cần có, chưa phải một vòng chạy QA nội dung hoặc thực thi bộ kiểm thử của dự án.

### 10.1. Ma trận biểu diễn

| Tình huống | Kết quả theo hợp đồng endpoint minh họa |
| --- | --- |
| JSON UTF-8 có tên tiếng Việt hợp lệ | Parse và kiểm tra field thành công nếu các điều kiện khác đạt |
| Cùng giá trị qua ký tự trực tiếp và JSON escape hợp lệ | Cùng giá trị ứng dụng sau parse |
| Byte UTF-8 lỗi hoặc sequence bị cắt khi hết body | Từ chối với `INVALID_UTF8`; không tạo hồ sơ |
| Body có UTF-8 BOM | Từ chối theo chính sách BOM của endpoint |
| Charset khai báo ngoài UTF-8 | Từ chối ở adapter theo hợp đồng media type |
| Body UTF-8 hợp lệ nhưng JSON sai cú pháp | Từ chối do lỗi JSON, không gắn nhãn sai thành lỗi UTF-8 |
| JSON escape tạo surrogate lẻ | Từ chối ở parser hoặc bước kiểm tra String tương ứng |
| Cặp surrogate đúng biểu diễn code point ngoài BMP | Được xét như ký tự hợp lệ về biểu diễn, rồi kiểm tra chính sách field |
| Hai tên tương đương canonical trước NFC | Đưa về cùng dạng NFC theo chính sách tên hiển thị |
| `U+FFFD` được gửi bằng UTF-8 hợp lệ | Không kết luận là lỗi decode chỉ dựa vào code point này |
| NUL hoặc điều khiển C0/C1 trong tên | Từ chối theo chính sách tên, dù encoding có thể hợp lệ |

Kết quả “đạt encoding” không có nghĩa là toàn bộ request được chấp nhận. Một tên đúng UTF-8 vẫn có thể vượt độ dài hoặc người gọi có thể không có quyền sửa hồ sơ.

### 10.2. Kiểm thử kích thước và ranh giới stream

Cần có trường hợp body đúng giới hạn và vượt giới hạn byte, field đúng giới hạn và vượt giới hạn trước hoặc sau normalization. Các trường hợp ASCII, ký tự nhiều byte và code point ngoài BMP giúp phát hiện việc dùng nhầm đơn vị đếm.

Với đọc theo chunk, chia một sequence nhiều byte ở từng vị trí ranh giới để chứng minh decoder giữ trạng thái. Một chunk kết thúc giữa sequence chưa phải lỗi cuối cùng; kết thúc toàn bộ stream giữa sequence mới phải bị từ chối theo hợp đồng.

Nếu có kênh hỗ trợ giải nén, kiểm thử riêng giới hạn sau giải nén. Với endpoint minh họa không hỗ trợ nén, kiểm tra adapter từ chối content coding ngoài phạm vi trước khi xử lý như body JSON thông thường.

### 10.3. Kiểm thử tính nhất quán xuyên thành phần

Kiểm tra luồng đi qua gateway và backend thực tế để xác định không có bước trung gian thay byte lỗi, decode thêm hoặc tự chuyển charset. Chỉ kiểm thử một hàm Java với byte đầu vào chưa chứng minh đường HTTP sản xuất đã sử dụng cùng chính sách.

Các kiểm thử tích hợp cần chứng minh request bị từ chối không tạo bản ghi, không phát message nghiệp vụ và không bị xử lý lại bằng một bộ mã fallback. Mã lỗi và điểm từ chối phải phản ánh đúng lớp gây lỗi.

Đối với dữ liệu lưu trữ, cần kiểm tra round trip theo miền được hỗ trợ: giá trị chuẩn hóa được lưu, đọc lại và hiển thị qua cơ chế đầu ra phù hợp mà không bị đổi thành chuỗi lỗi. Round trip phục vụ tính toàn vẹn; nó không thay thế kiểm thử quyền hay an toàn đầu ra.

## 11. Lỗi, logging và quản trị hợp đồng

Một lỗi encoding có thể xuất hiện trước khi có String hợp lệ. Hệ thống không nên cố decode bằng một charset khác chỉ để phản chiếu toàn bộ dữ liệu đó trong phản hồi lỗi hoặc log.

Thông tin quan sát có thể gồm mã lỗi, route, số byte đã đọc trong giới hạn, correlation ID và lớp từ chối. Không ghi nguyên credential, body nhạy cảm hoặc dữ liệu nhị phân không giới hạn. Nếu cần mẫu byte phục vụ điều tra, phải có chính sách riêng về quyền truy cập, giới hạn và thời hạn lưu giữ.

Phản hồi cho client nên dùng mã lỗi ổn định. HTTP adapter quyết định mapping trạng thái phù hợp cho lỗi media type, body quá lớn, encoding sai và dữ liệu field sai. Không để exception decoder hoặc stack trace trở thành phản hồi công khai mặc định.

Hợp đồng encoding cần được quản lý cùng schema của từng đường vào. Thay đổi từ “tự sửa byte lỗi” sang “từ chối” có thể phát hiện client cũ đang gửi sai dữ liệu; đó là lý do cần kế hoạch triển khai và quan sát, không phải lý do để tiếp tục coi dữ liệu bị sửa là nguyên vẹn.

Nếu cùng dữ liệu được dùng để kiểm tra trùng, ký, hash hoặc liên kết định danh, phải xác định chính xác thao tác nào dùng byte gốc và thao tác nào dùng giá trị sau parse hoặc normalization. Các quyết định đó thuộc giao thức và mô hình dữ liệu, không nên được suy từ một tiện ích String dùng chung.

## 12. Những yêu cầu cần tránh

| Yêu cầu mơ hồ | Cách diễn đạt có thể kiểm chứng |
| --- | --- |
| “Hệ thống dùng UTF-8” | Chỉ rõ từng biên byte, charset chấp nhận, decoder và chính sách lỗi |
| “Decode đến khi chuỗi sạch” | Mỗi lớp biểu diễn có chủ sở hữu và số lần xử lý theo giao thức |
| “Thấy ký tự thay thế thì coi là byte lỗi” | Decoder báo lỗi trên byte gốc; chính sách `U+FFFD` của field được xét riêng |
| “Mọi tên tối đa 80 ký tự” | Ghi rõ đơn vị và thời điểm đếm trước hoặc sau normalization |
| “UTF-8 đúng thì dữ liệu an toàn” | Tách encoding, parse, schema, nghiệp vụ, quyền và kiểm soát tại điểm sử dụng |
| “Normalize mọi dữ liệu trước khi dùng” | Chọn chính sách cho từng field; tôn trọng giao thức chữ ký và token |
| “Framework tự lo hết” | Xác minh cấu hình và luồng thực tế không thay byte lỗi hoặc decode lặp |

Encoding validation bảo vệ sự nhất quán giữa dữ liệu được nhận, dữ liệu được kiểm tra và dữ liệu được dùng. Một đặc tả tốt chỉ ra rõ từng lớp biểu diễn, chính sách lỗi và nơi thực thi; nhờ đó các kiểm soát bảo mật phía sau có thể dựa trên một giá trị đã được hiểu thống nhất.
