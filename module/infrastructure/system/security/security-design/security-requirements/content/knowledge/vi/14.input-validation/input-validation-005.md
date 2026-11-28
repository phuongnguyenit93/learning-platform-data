# Length validation — Đặc tả giới hạn độ dài đầu vào

## 1. Vì sao “tối đa 100 ký tự” chưa phải một yêu cầu đầy đủ?

Một API ghi rằng tên hiển thị được dài tối đa 100 ký tự. Giao diện đếm ký tự nhìn thấy, dịch vụ Java dùng `String.length()`, còn hệ thống lưu trữ giới hạn số byte. Cùng một chuỗi có thể được giao diện chấp nhận, bị API từ chối hoặc chỉ thất bại khi ghi xuống đích lưu.

Sự khác biệt này không chỉ gây lỗi trải nghiệm. Đầu vào rất dài có thể làm tốn bộ nhớ, kéo dài thời gian phân tích cú pháp, tăng chi phí biểu thức chính quy, phình hàng đợi hoặc làm phát sinh dữ liệu bị cắt ngầm. Nếu giá trị được dùng làm định danh, việc cắt ngầm còn có thể khiến hai đầu vào khác nhau trở thành cùng một giá trị.

Trong chương Input validation, **length validation** là việc kiểm tra kích thước đầu vào theo một đơn vị và một giai đoạn xử lý đã xác định. Mục tiêu là chuyển rủi ro thành yêu cầu có thể đo và kiểm chứng: chấp nhận đúng dữ liệu nghiệp vụ, giới hạn chi phí xử lý, từ chối đầu vào vượt ngưỡng trước khi gây tác động không mong muốn.

Một đặc tả độ dài cần có:

- Đối tượng được đo: toàn request, một field, từng phần tử hay tổng một danh sách.
- Đơn vị đo: byte, UTF-16 code unit, Unicode code point hoặc grapheme cluster.
- Thời điểm đo: trước giải mã, sau giải mã, sau chuẩn hóa hay trước khi ghi vào đích.
- Biên dưới và biên trên, có bao gồm giá trị bằng biên hay không.
- Quy tắc cho field thiếu, `null`, chuỗi rỗng và khoảng trắng.
- Hành vi khi vượt giới hạn và bằng chứng cho thấy không có tác động nghiệp vụ.

Các ngưỡng trong bài là ví dụ thiết kế, không phải giá trị chuẩn bắt buộc cho mọi ứng dụng.

## 2. Độ dài phải gắn với một đơn vị cụ thể

### 2.1. Byte

Byte phù hợp khi giới hạn dữ liệu trên đường truyền, kích thước buffer, file, message hoặc một đích lưu có ràng buộc theo byte. Với văn bản, phải chỉ rõ encoding.

Ví dụ, độ dài UTF-8 của chuỗi không thể suy ra bằng cách lấy số ký tự nhân với một hằng số rồi coi đó là số byte thực tế. Hệ thống phải đo hoặc tính đúng theo encoding đã thống nhất.

Cũng cần phân biệt:

- Byte của HTTP body còn nén.
- Byte sau giải nén.
- Byte của JSON, gồm dấu ngoặc, dấu nháy và escape.
- Byte của giá trị chuỗi sau parse và encode lại thành UTF-8.

Bốn đại lượng này không giống nhau. Một giới hạn ở đại lượng thứ nhất không thay thế giới hạn ở ba đại lượng còn lại.

### 2.2. UTF-16 code unit

Java `String.length()` trả về số UTF-16 code unit. Một ký tự bổ sung ngoài Basic Multilingual Plane được biểu diễn bằng một cặp surrogate nên chiếm hai code unit. Đây không nhất thiết là số ký tự mà người dùng nhìn thấy. Hành vi này được mô tả trong [Java String API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html).

Giới hạn theo code unit vẫn hợp lệ nếu được chọn có chủ ý, chẳng hạn để chặn sớm công việc trên một chuỗi Java. Vấn đề là gọi nó là “ký tự” rồi để các bên thực hiện theo những cách đếm khác nhau.

### 2.3. Unicode code point

Code point là một đơn vị của biểu diễn Unicode. Một ký tự có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ cái kết hợp với dấu. Vì vậy, số code point cũng không luôn bằng số ký tự mà người dùng cảm nhận.

Một chuỗi chứa surrogate không ghép cặp cần được xử lý theo hợp đồng đầu vào. Đếm code point không tự chứng minh chuỗi là Unicode hợp lệ: Java vẫn có thể đếm surrogate không ghép cặp như một code point. Nếu yêu cầu chỉ chấp nhận Unicode hợp lệ, phải xác minh điều đó riêng.

### 2.4. Grapheme cluster

Extended grapheme cluster là một cách phân đoạn gần với ký tự mà người dùng cảm nhận. Một chữ cái đi cùng dấu hoặc một chuỗi emoji có thể gồm nhiều code point nhưng nằm trong cùng một cluster.

Nếu chọn đơn vị này, đặc tả cần chỉ ra thuật toán hoặc thư viện, phiên bản Unicode và các tùy biến nếu có. “Đếm ký tự nhìn thấy” là cách diễn đạt quá mơ hồ để hai hệ thống triển khai độc lập. Tham khảo định nghĩa trong [Unicode UAX #29](https://www.unicode.org/reports/tr29/).

Một cluster có thể chứa nhiều code point. Vì thế giới hạn cluster phục vụ trải nghiệm cần đi kèm giới hạn kích thước dữ liệu để bảo vệ tài nguyên; không nên dùng riêng số cluster làm trần bộ nhớ.

### 2.5. Ví dụ đối chiếu

Bảng sau đo các chuỗi đúng như biểu diễn, trước khi áp dụng một chính sách chuẩn hóa riêng:

| Chuỗi | Biểu diễn code point | UTF-16 code unit | Code point | UTF-8 byte | Grapheme cluster theo phân đoạn mặc định |
|---|---|---:|---:|---:|---:|
| `A` | U+0041 | 1 | 1 | 1 | 1 |
| `é` dựng sẵn | U+00E9 | 1 | 1 | 2 | 1 |
| `e` + dấu sắc kết hợp | U+0065 U+0301 | 2 | 2 | 3 | 1 |
| `😀` | U+1F600 | 2 | 1 | 4 | 1 |
| `🇻🇳` | U+1F1FB U+1F1F3 | 4 | 2 | 8 | 1 |

Khi đặc tả nói “độ dài tối đa 1”, cả đơn vị đo lẫn bước chuẩn hóa quyết định kết quả chấp nhận. Đây là lý do bộ kiểm thử chỉ có ASCII thường không phát hiện được bất nhất.

## 3. Tách giới hạn nghiệp vụ khỏi giới hạn tài nguyên

Hai loại giới hạn giải quyết hai vấn đề khác nhau.

**Giới hạn nghiệp vụ** xác định dữ liệu nào có ý nghĩa đối với sản phẩm. Ví dụ một mô tả công khai có tối đa 2.000 code point sau chuẩn hóa, hoặc tên hiển thị có tối đa 40 grapheme cluster.

**Giới hạn tài nguyên** xác định mức công việc mà hệ thống cho phép thực hiện. Ví dụ request body sau giải nén không quá 16 KiB, mỗi danh sách không quá 50 phần tử, và mỗi chuỗi phải có trần kích thước trước khi chạy xử lý phức tạp.

Một đầu vào có thể hợp lệ về trải nghiệm nhưng vượt ngân sách tài nguyên. Trường hợp nhiều dấu kết hợp trên một chữ là ví dụ: số cluster nhỏ nhưng số code point và byte có thể lớn.

Ngược lại, một request nhỏ vẫn có thể vi phạm nghiệp vụ. Một mô tả rỗng chỉ chiếm rất ít byte nhưng không đáp ứng yêu cầu tối thiểu một code point.

Có thể mô tả chính sách của một field văn bản bằng các điều kiện đồng thời:

```text
required(value)
AND well_formed_unicode(value)
AND min_points <= code_point_count(canonical_value) <= max_points
AND utf8_bytes(canonical_value) <= max_field_bytes
AND request_budgets_are_satisfied
```

Các điều kiện này không thay thế kiểm tra nội dung, phân quyền, truy vấn có tham số hay encoding đầu ra. Chuỗi tấn công ngắn vẫn có thể nằm hoàn toàn trong giới hạn độ dài.

## 4. Đặt kiểm tra đúng giai đoạn xử lý

Một pipeline minh họa:

```text
Đọc dữ liệu với trần byte thực tế
          |
          v
Giải nén có giới hạn, nếu giao thức hỗ trợ
          |
          v
Giải mã và parse với ngân sách kích thước / độ sâu
          |
          v
Kiểm tra kiểu, field bắt buộc và Unicode hợp lệ
          |
          v
Chuẩn hóa đã được hợp đồng cho phép
          |
          v
Kiểm tra min / max theo đơn vị nghiệp vụ và byte đích
          |
          v
Dùng chính giá trị đã kiểm tra để thực hiện nghiệp vụ
```

### 4.1. Chặn trước khi cấp phát lớn

Nếu ứng dụng đọc toàn bộ body vào bộ nhớ rồi mới kiểm tra độ dài, giới hạn đó không bảo vệ giai đoạn đọc. Cần giới hạn ngay tại lớp nhận dữ liệu hoặc bằng cơ chế đọc có ngân sách thực tế.

Không chỉ tin `Content-Length`. Giới hạn phải áp dụng cho số byte thực sự nhận hoặc xử lý, kể cả trường hợp cơ chế truyền không cung cấp sẵn một độ dài đáng tin cậy. Khi hỗ trợ dữ liệu nén, cần một trần riêng cho dữ liệu giải nén, cùng các giới hạn thời gian và tài nguyên phù hợp.

Trần request, số field, độ sâu cấu trúc và số phần tử bổ sung cho nhau. Một đối tượng chứa rất nhiều field ngắn vẫn có thể tạo ra chi phí lớn dù mỗi field riêng lẻ đều hợp lệ.

### 4.2. Kiểm tra ngữ nghĩa trên biểu diễn sẽ sử dụng

Giả sử hệ thống quy định lưu mô tả ở dạng NFC. Kiểm tra giới hạn nghiệp vụ phải áp dụng trên giá trị NFC sẽ được lưu, không kiểm tra một biến rồi ghi một biến khác.

Chuẩn hóa có thể thay đổi biểu diễn và số đơn vị cần đo. Không được giả định mọi phép chuẩn hóa luôn làm chuỗi ngắn đi. Đồng thời, đầu vào trước chuẩn hóa vẫn cần một trần kỹ thuật để không phải xử lý một chuỗi cực lớn chỉ nhằm biết kết quả cuối có đủ ngắn hay không.

Java cung cấp các dạng chuẩn hóa qua [Normalizer API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html). Việc chọn NFC, NFKC hoặc giữ nguyên là quyết định của hợp đồng dữ liệu, không phải một thao tác vệ sinh áp dụng cho mọi field.

### 4.3. Không chuẩn hóa tùy tiện credential và định danh opaque

Password, token, chữ ký, mã định danh opaque và dữ liệu đã ký cần tuân theo giao thức của chúng. Tự trim, đổi hoa thường hoặc chuẩn hóa trước kiểm tra có thể thay đổi giá trị mà bên gửi muốn xác thực.

Nếu một giao thức quy định credential có độ dài theo byte hoặc định dạng ASCII cụ thể, phải dùng đúng quy tắc đó. Không tái sử dụng validator cho mô tả tự do để xử lý credential.

### 4.4. Kiểm tra tương thích với đích sau biến đổi

Dữ liệu có thể được serialize sang message, encode cho một giao thức khác hoặc đưa vào một đích lưu có giới hạn khác. Những bước này có thể thêm overhead hoặc thay đổi kích thước.

Một field đạt giới hạn UTF-8 trong API chưa đủ chứng minh toàn message sau serialize đạt giới hạn của broker. Hợp đồng cần có ngân sách cho toàn bộ biểu diễn đích, hoặc chứng minh giới hạn đầu vào bảo đảm điều đó.

Không giải mã lặp cho tới khi chuỗi “không còn thay đổi”. Mỗi lớp giải mã phải có trách nhiệm theo giao thức, tránh để validator và thành phần sử dụng dữ liệu nhìn thấy hai giá trị khác nhau.

## 5. Đặc tả field dưới dạng hợp đồng

Một bảng hợp đồng hữu ích hơn một câu “text tối đa 2.000 ký tự”:

| Thuộc tính | Chính sách minh họa cho `description` |
|---|---|
| Kiểu | JSON string |
| Field thiếu | Từ chối khi tạo mới; quy tắc PATCH được định nghĩa riêng |
| `null` | Từ chối |
| Chuỗi rỗng | Từ chối |
| Khoảng trắng | Không tự trim; điều kiện “không toàn khoảng trắng” nếu cần là quy tắc riêng |
| Unicode lỗi | Từ chối; không âm thầm thay dữ liệu lỗi rồi tiếp tục |
| Chuẩn hóa nghiệp vụ | NFC |
| Đơn vị độ dài nghiệp vụ | Unicode code point sau NFC |
| Biên nghiệp vụ | 1 đến 2.000, bao gồm hai biên |
| Trần kích thước field | 6.000 byte UTF-8 sau NFC |
| Trần kỹ thuật trước chuẩn hóa | 8.192 UTF-16 code unit đối với đầu vào Java đã parse |
| Trần request minh họa | 16 KiB sau giải nén; các trần trước parse khác do endpoint quy định |
| Khi vi phạm | Trả mã lỗi ổn định, không cắt ngầm và không ghi thay đổi nghiệp vụ |
| Giá trị đưa vào nghiệp vụ | Chính giá trị NFC đã vượt qua các kiểm tra |

Trần 8.192 code unit là giới hạn kỹ thuật bổ sung, không phải một cách diễn đạt khác của giới hạn 2.000 code point. Một request có thể bị từ chối vì vượt trần kỹ thuật ngay cả khi một phép biến đổi sau đó có thể tạo ra giá trị ngắn hơn. Hành vi này phải được nêu rõ cho client.

Với trường hợp PATCH, cần phân biệt “không gửi field” với “gửi chuỗi rỗng” và “gửi null để xóa”. Không để validator tự quyết định ngữ nghĩa cập nhật bằng cách biến cả ba thành cùng một giá trị.

Đối với tên hiển thị dùng grapheme cluster, một hợp đồng khác có thể quy định tối đa 40 cluster, đồng thời có trần code point và byte riêng. Không áp dụng mặc định bảng `description` cho mọi field.

## 6. Bộ yêu cầu bảo mật có thể kiểm chứng

Các mã dưới đây minh họa cách chuyển chính sách thành yêu cầu và bằng chứng. Chúng cần được gắn với endpoint, field và chủ sở hữu cụ thể.

### LEN-01 — Công bố đơn vị và biểu diễn đo

Mọi field có giới hạn độ dài phải có đơn vị đo, giai đoạn xử lý, biên bao gồm hay loại trừ và quy tắc cho missing/null/empty. Nếu dùng grapheme cluster, phải xác định cách phân đoạn.

**Bằng chứng:** hợp đồng API, đặc tả field và test vector dùng chung giữa client với server.

### LEN-02 — Server thực thi độc lập với giao diện

Server phải kiểm tra các giới hạn ở mọi đường nhận dữ liệu không tin cậy. Client-side validation chỉ hỗ trợ phản hồi sớm; yêu cầu vẫn có hiệu lực khi gọi API trực tiếp hoặc sửa request.

**Bằng chứng:** thử nghiệm bỏ qua giao diện, cùng kịch bản qua API, import và consumer liên quan.

### LEN-03 — Giới hạn trước xử lý tốn tài nguyên

Hệ thống phải áp dụng giới hạn kích thước thực tế trước khi đọc hoặc parse không giới hạn, và trước các phép xử lý tốn tài nguyên. Các parser, giải nén, cấu trúc lồng nhau và danh sách phải có ngân sách phù hợp.

**Bằng chứng:** cấu hình ingress/parser và kiểm thử quá giới hạn chứng minh yêu cầu bị chặn tại lớp dự kiến.

### LEN-04 — Dùng cùng giá trị chuẩn hóa để kiểm tra và thực thi

Nếu hợp đồng cho phép chuẩn hóa, hệ thống phải thực hiện đúng phép biến đổi đã định nghĩa, kiểm tra giá trị sau biến đổi và dùng chính giá trị đó cho nghiệp vụ hoặc lưu trữ.

**Bằng chứng:** test vector tương đương Unicode; kiểm tra giá trị thực sự được ghi và giá trị được chuyển sang thành phần tiếp theo.

### LEN-05 — Từ chối vượt giới hạn, không cắt ngầm

Đầu vào vượt giới hạn phải bị từ chối theo hợp đồng. Không dùng substring, cắt byte, cấu hình database hoặc serializer để âm thầm biến nó thành giá trị được chấp nhận.

**Bằng chứng:** kiểm thử vượt biên; không có dữ liệu bị cắt, va chạm định danh hoặc ghi nghiệp vụ một phần.

Nếu nghiệp vụ có tính năng rút gọn nội dung, đó phải là một phép biến đổi công khai với quy tắc riêng, không phải cách sửa lỗi validation mà caller không biết.

### LEN-06 — Bao phủ tổng kích thước và phần tử

Với collection hoặc batch, phải có giới hạn số phần tử, giới hạn từng phần tử và ngân sách tổng phù hợp. Phải tính cả cấu trúc lồng nhau thuộc phạm vi đầu vào.

**Bằng chứng:** thử nhiều field ngắn, nhiều phần tử gần biên và nested object; không chỉ một chuỗi dài đơn lẻ.

### LEN-07 — Lỗi ổn định, không phản chiếu payload

Lỗi validation phải chỉ ra field, loại giới hạn và đơn vị khi phù hợp, nhưng không phản chiếu toàn bộ dữ liệu người dùng vào response hoặc log. Các lớp hạ tầng có thể trả lỗi riêng, nhưng phải giữ nguyên tính chất từ chối và không tạo tác động nghiệp vụ.

**Bằng chứng:** response và sự kiện quan sát với input dài hoặc nhạy cảm; kích thước lỗi được giới hạn.

### LEN-08 — Đích lưu không nới hoặc thay đổi hợp đồng âm thầm

Ràng buộc database, message broker và hệ thống nhận phải tương thích với biểu diễn đã kiểm tra. Thay đổi cấu hình, encoding hoặc phiên bản thư viện có ảnh hưởng đến việc đếm phải có đánh giá và test tương thích.

**Bằng chứng:** kiểm thử tích hợp biên với cấu hình thật; kiểm tra không có truncation hoặc chuyển mã không mong muốn.

OWASP khuyến nghị đặt giới hạn theo field và giới hạn request trước buffering hoặc parsing. Bộ mã yêu cầu trong bài là một cách triển khai đặc tả cho hệ thống giả định, không phải tên yêu cầu do OWASP định nghĩa. Xem [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).

## 7. Ví dụ Java: kiểm tra code point và byte sau NFC

Ví dụ dưới đây thực hiện phần kiểm tra field `description` sau khi request đã được parse với giới hạn phù hợp. Nó không thay thế giới hạn body, giới hạn giải nén hoặc cấu hình parser ở phía trước.

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public final class DescriptionLengthValidator {
    private static final int RAW_MAX_UTF16_UNITS = 8_192;
    private static final int MIN_CODE_POINTS = 1;
    private static final int MAX_CODE_POINTS = 2_000;
    private static final int MAX_UTF8_BYTES = 6_000;

    public static final class ValidatedDescription {
        private final String value;

        private ValidatedDescription(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public static final class ValidationFailure
            extends IllegalArgumentException {
        private final String code;

        private ValidationFailure(String code) {
            super(code);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    public static ValidatedDescription validate(String raw) {
        if (raw == null) {
            throw failure("DESCRIPTION_REQUIRED");
        }

        // Trần công việc trên String đã parse, không phải trần request.
        if (raw.length() > RAW_MAX_UTF16_UNITS) {
            throw failure("DESCRIPTION_RAW_TOO_LARGE");
        }

        requireWellFormedUtf16(raw);

        String canonical = Normalizer.normalize(
                raw, Normalizer.Form.NFC);

        int points = canonical.codePointCount(
                0, canonical.length());

        if (points < MIN_CODE_POINTS) {
            throw failure("DESCRIPTION_TOO_SHORT");
        }

        if (points > MAX_CODE_POINTS) {
            throw failure("DESCRIPTION_TOO_LONG_CODE_POINTS");
        }

        int bytes = canonical.getBytes(
                StandardCharsets.UTF_8).length;

        if (bytes > MAX_UTF8_BYTES) {
            throw failure("DESCRIPTION_TOO_LARGE_UTF8");
        }

        return new ValidatedDescription(canonical);
    }

    private static void requireWellFormedUtf16(String value) {
        for (int i = 0; i < value.length(); i++) {
            char current = value.charAt(i);

            if (Character.isHighSurrogate(current)) {
                if (i + 1 >= value.length()
                        || !Character.isLowSurrogate(
                                value.charAt(i + 1))) {
                    throw failure("DESCRIPTION_INVALID_UNICODE");
                }
                i++;
            } else if (Character.isLowSurrogate(current)) {
                throw failure("DESCRIPTION_INVALID_UNICODE");
            }
        }
    }

    private static ValidationFailure failure(String code) {
        return new ValidationFailure(code);
    }
}
```

Một caller sử dụng kết quả như sau:

```java
DescriptionLengthValidator.ValidatedDescription checked =
        DescriptionLengthValidator.validate(requestDescription);

// Chỉ chuyển tiếp giá trị đã kiểm tra, không dùng lại requestDescription.
profileService.updateDescription(profileId, checked.value());
```

Các điểm thiết kế cần hiểu:

- `raw.length()` là trần công việc theo code unit, không bị gọi nhầm là số ký tự nghiệp vụ.
- Surrogate không hợp lệ được từ chối trước khi chuẩn hóa và encode.
- Độ dài nghiệp vụ được đo bằng code point trên giá trị NFC.
- Byte UTF-8 được kiểm tra riêng vì 2.000 code point có thể vượt 6.000 byte.
- Exception chỉ chứa mã lỗi cố định, không chứa dữ liệu đầu vào.
- Kết quả trả về là chính giá trị đã kiểm tra; caller không cần tự lặp phép biến đổi.

Đo byte bằng `getBytes` tạo thêm một mảng byte. Trong ví dụ, công việc đã được chặn bởi các trần trước đó. Với dữ liệu lớn hoặc luồng nhị phân, nên dùng cách xử lý có ngân sách và không cấp phát nguyên dữ liệu chỉ để kiểm tra độ dài.

Đây không phải bộ kiểm tra mọi nội dung của mô tả. Một chuỗi toàn khoảng trắng hoặc một chuỗi ngắn có nội dung nguy hiểm có thể vượt qua phần length validation. Các quy tắc nội dung và bảo vệ tại nơi sử dụng vẫn phải được thiết kế riêng.

## 8. Không dùng cắt ngầm thay cho kiểm tra

Cách xử lý sau làm thay đổi dữ liệu thay vì từ chối:

```java
// Anti-pattern: caller không biết giá trị đã bị thay đổi.
String shortened = input.substring(0, Math.min(input.length(), 100));
repository.save(shortened);
```

Ngoài việc không thực hiện đúng hợp đồng từ chối, cắt theo code unit còn có thể tách một cặp surrogate. Cắt mảng byte UTF-8 ở vị trí tùy ý có thể làm hỏng biểu diễn ký tự. Ngay cả cắt đúng ranh giới code point vẫn có thể tách một grapheme cluster.

Với định danh, truncation đặc biệt nguy hiểm. Hai tên dài có cùng tiền tố có thể bị lưu thành cùng một tên. Nếu một thành phần kiểm tra uniqueness trên dữ liệu gốc còn đích lưu cắt dữ liệu, kết quả kiểm tra và kết quả lưu không còn cùng nghĩa.

Khi sản phẩm thực sự muốn tạo bản xem trước, cần coi đó là chức năng khác: xác định đơn vị rút gọn, dấu báo bị rút gọn, dữ liệu gốc giữ ở đâu và đầu ra nào được phép rút gọn. Không dùng bản xem trước làm giá trị định danh hay credential.

Tương tự, không bắt lỗi “dữ liệu quá dài” từ database rồi tự cắt và retry. Làm vậy biến một ràng buộc an toàn ở đích thành cơ chế sửa dữ liệu âm thầm.

## 9. Thiết kế ma trận biên và Unicode

Với biên dưới `m` và biên trên `M`, kiểm tra các giá trị quanh biên:

```text
m - 1, m, m + 1, M - 1, M, M + 1
```

Mỗi trường hợp phải dùng đúng đơn vị hợp đồng. Nếu `M` là code point, tạo chuỗi gồm `M` code point; không tạo `M` code unit rồi giả định hai cách đếm tương đương.

Đối với hợp đồng `description` trong bài:

| Dữ liệu | Điều cần chứng minh |
|---|---|
| Field thiếu hoặc null | Bị từ chối theo quy tắc required |
| Chuỗi rỗng | Không đạt tối thiểu một code point |
| ASCII dài 1, 2.000 và 2.001 | Bao gồm biên; từ chối vượt biên code point |
| 1.500 emoji `😀` | 1.500 code point, 6.000 byte: đạt hai biên liên quan |
| 1.501 emoji `😀` | Chưa vượt 2.000 code point nhưng vượt 6.000 byte |
| 2.000 emoji `😀` | Minh họa giới hạn code point không thay thế giới hạn byte |
| `e` kết hợp U+0301 và `é` dựng sẵn | Cùng giá trị NFC được kiểm tra và chuyển tiếp |
| Chuỗi nhiều dấu kết hợp | Không nhầm số cluster với kích thước dữ liệu |
| Surrogate đứng riêng | Bị từ chối theo chính sách Unicode hợp lệ |
| Input vượt 8.192 code unit trước chuẩn hóa | Bị chặn tại trần kỹ thuật |
| Payload JSON quá giới hạn toàn request | Bị chặn trước giai đoạn xử lý field |

Các trường hợp trên kiểm tra những ràng buộc khác nhau. Một test vượt code point nhưng cũng vượt byte không đủ để chứng minh nhánh giới hạn byte đã hoạt động độc lập.

Khi kiểm tra riêng trần byte 6.000, cần có mẫu 5.999, 6.000 và 6.001 byte mà vẫn đạt giới hạn code point. Có thể kết hợp ký tự ASCII với emoji để tạo đúng số byte, thay vì chỉ lặp một loại ký tự có bước nhảy bốn byte.

Với chính sách theo grapheme cluster, bổ sung test gồm dấu kết hợp, cờ, emoji nối bằng zero-width joiner và các chuỗi liên quan tới ngôn ngữ được hỗ trợ. Ghi lại phiên bản bộ phân đoạn để việc nâng cấp không âm thầm thay đổi kết quả ở biên.

## 10. Kiểm thử đường xử lý, không chỉ hàm đếm

Một hàm validator đúng chưa chứng minh endpoint được bảo vệ. Cần kiểm tra nó thực sự nằm trên mọi đường tạo hoặc thay đổi dữ liệu.

### 10.1. Bỏ qua client

Gửi request trực tiếp với field vượt giới hạn, thay vì chỉ nhập qua ô giao diện. Xác minh server từ chối dù client không chạy bất kỳ kiểm tra nào.

Nếu giao diện có bộ đếm khác đơn vị với server, cần sửa hợp đồng hoặc thông báo rõ giới hạn tương ứng. Không dùng frontend làm nguồn chuẩn của quyết định bảo mật.

### 10.2. Đường import, batch và message

CSV import, công cụ quản trị, job đồng bộ và consumer hàng đợi cũng có thể đưa dữ liệu vào cùng nghiệp vụ. Chúng cần giới hạn phù hợp tại ranh giới của chúng và kiểm tra ngữ nghĩa trước khi ghi.

Một queue nội bộ không tự biến nội dung message thành dữ liệu đáng tin. Nguồn có thể là dịch vụ khác, bản phát lại hoặc dữ liệu được tạo từ đầu vào bên ngoài.

### 10.3. Đích lưu và downstream

Với giá trị ở đúng biên, xác minh dữ liệu lưu và dữ liệu đọc lại không bị cắt hoặc thay đổi ngoài phép chuẩn hóa đã quy định. Gửi sang downstream trong biểu diễn thực tế để kiểm tra overhead và ràng buộc encoding.

Không suy từ tên kiểu cột rằng giới hạn luôn được tính theo cùng đơn vị. Ngữ nghĩa của kiểu dữ liệu, charset, collation và cấu hình lỗi phải được đối chiếu với hệ quản trị thực tế.

### 10.4. Tác động nghiệp vụ

Khi đầu vào không hợp lệ, không tạo một phần bản ghi, không gửi email nghiệp vụ và không phát message thành công trước khi phát hiện lỗi. Với batch, cần định nghĩa rõ từ chối toàn bộ hay trả kết quả từng phần tử.

Một response báo lỗi không đủ làm bằng chứng nếu hệ thống đã thực hiện tác động trước đó. Kiểm thử phải quan sát trạng thái sau request và các tác động được phát ra.

## 11. Giới hạn danh sách và tổng dữ liệu

Giả sử endpoint cho phép tối đa 50 nhãn, mỗi nhãn tối đa 40 code point. Chỉ kiểm tra từng nhãn không ngăn caller gửi một triệu nhãn. Chỉ kiểm tra số nhãn cũng không ngăn một nhãn dài hàng triệu code point.

Cần mô tả đồng thời:

```text
số phần tử <= 50
độ dài từng nhãn <= 40 code point
byte UTF-8 của từng nhãn <= ngưỡng field
tổng dữ liệu đã giải mã <= ngân sách request
độ sâu và số node của cấu trúc <= ngân sách parser
```

Nếu cộng kích thước nhiều phần tử trong một kiểu số hữu hạn, phép cộng không được tràn rồi tạo ra tổng nhỏ giả. Có thể kiểm tra bằng cách trừ ngân sách còn lại trước khi cộng, hoặc dùng phép cộng có phát hiện tràn.

Không chờ thu thập toàn bộ collection mới kiểm tra số phần tử nếu parser hoặc giao thức cho phép chặn sớm. Với luồng dữ liệu, giới hạn phải được thực thi trong quá trình đọc.

Các trần cần nhất quán với nhu cầu sản phẩm. Nếu mỗi phần tử được phép ở biên tối đa nhưng toàn batch không được chứa mọi phần tử ở biên đó, hợp đồng phải nói rõ ngân sách tổng; client không nên phải đoán từ các lỗi ngẫu nhiên.

## 12. Phản hồi lỗi và quan sát vận hành

Một lỗi minh họa:

```json
{
  "code": "FIELD_LENGTH_EXCEEDED",
  "field": "description",
  "unit": "unicode_code_points_after_nfc",
  "max": 2000,
  "requestId": "req-demo-731"
}
```

Response không cần chép lại field bị từ chối. Với dữ liệu bí mật, ngay cả việc phản chiếu một đoạn đầu hoặc độ dài chi tiết cũng cần được đánh giá theo mục đích; thông tin trả cho client nên là mức cần thiết.

Endpoint cần xác định mã HTTP hoặc cơ chế lỗi tương ứng của giao thức. Lỗi toàn body ở gateway có thể khác lỗi độ dài một field sau parse. Không bắt buộc mọi lớp tạo cùng payload, nhưng caller cần phân biệt được đầu vào sai với lỗi nội bộ.

Log hoặc metric nên dùng mã quy tắc, endpoint chuẩn hóa và kết quả. Không dùng giá trị đầu vào làm metric label; điều đó vừa có thể rò dữ liệu vừa làm tăng số lượng chuỗi thời gian.

Cũng cần giới hạn số lỗi trả về trong một request. Một đối tượng có hàng nghìn field lỗi không nên tạo response lỗi lớn hơn chính ngân sách đã đặt cho request.

Nếu cần theo dõi thời gian xử lý, độ dùng bộ nhớ hoặc số byte đọc trước khi từ chối, hãy định nghĩa ngưỡng dựa trên ngân sách thực tế. Không đặt một con số mili giây phổ quát rồi coi nó là tiêu chuẩn bảo mật cho mọi hệ thống.

## 13. Những nhầm lẫn cần tránh

| Nhầm lẫn | Hệ quả | Cách đặc tả rõ hơn |
|---|---|---|
| “Ký tự” không có định nghĩa | Client và server từ chối khác nhau | Ghi đơn vị, encoding và biểu diễn |
| Chỉ giới hạn trên giao diện | API trực tiếp bỏ qua hoàn toàn | Server kiểm tra mọi đường vào |
| Kiểm tra sau khi đọc toàn body | Bộ nhớ đã bị tiêu thụ trước khi từ chối | Giới hạn trong quá trình nhận và parse |
| Đo trước chuẩn hóa, lưu sau chuẩn hóa | Giá trị kiểm tra khác giá trị sử dụng | Kiểm tra và dùng cùng canonical value |
| Giới hạn cluster thay cho mọi trần | Chuỗi ít cluster vẫn có thể rất lớn | Bổ sung trần byte/code point và request |
| Cắt ngầm cho vừa cột | Mất dữ liệu hoặc va chạm định danh | Từ chối rõ ràng và kiểm tra tích hợp |
| Chỉ kiểm tra từng phần tử | Tổng collection vẫn không bị chặn | Giới hạn item count và ngân sách tổng |
| Độ dài hợp lệ nghĩa là nội dung an toàn | Chuỗi ngắn vẫn có thể gây injection | Giữ các kiểm soát theo ngữ cảnh sử dụng |
| Log nguyên input khi validation fail | Biến đường lỗi thành đường rò rỉ | Log mã lỗi và metadata tối thiểu |
| Dùng validator văn bản cho token | Làm thay đổi credential opaque | Áp dụng hợp đồng riêng của giao thức |

## 14. Bài tập xây dựng yêu cầu

Một dịch vụ hồ sơ nhận `displayName`, `description` và danh sách `tags`. Giao diện đang dùng một bộ đếm ký tự, backend Java dùng `String.length()`, còn hệ thống search có giới hạn message theo byte.

Hãy tạo một đặc tả có thể nghiệm thu:

1. Chọn đơn vị nghiệp vụ cho từng field và giải thích theo nhu cầu người dùng.
2. Xác định các trần kỹ thuật trước parse, trước chuẩn hóa và tại đích message.
3. Quy định missing, null, empty và whitespace cho tạo mới và cập nhật.
4. Nêu phép chuẩn hóa nào được phép và cách bảo đảm dùng chính giá trị đã kiểm tra.
5. Viết test tại biên bằng ASCII, tiếng Việt có dấu, emoji và dấu kết hợp.
6. Kiểm tra số lượng tag, độ dài từng tag và tổng request bằng các ca riêng.
7. Chỉ ra bằng chứng rằng request bị từ chối không tạo tác động nghiệp vụ.
8. Thiết kế lỗi đủ rõ để client sửa dữ liệu mà không phản chiếu payload nhạy cảm.

Đầu ra cần là hợp đồng có đơn vị, giai đoạn, ngưỡng và bằng chứng. Việc chọn một annotation có chữ “Size” hoặc một thuộc tính giao diện có chữ “max” chỉ là bước triển khai sau khi hợp đồng đó đã rõ.

## 15. Tài liệu tham khảo

- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): giới hạn theo field và kiểm soát đầu vào trước xử lý.
- [Java String API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): ý nghĩa UTF-16 code unit và các API code point.
- [Java Normalizer API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): các dạng chuẩn hóa Unicode.
- [Unicode UAX #29 — Text Segmentation](https://www.unicode.org/reports/tr29/): grapheme cluster và quy tắc phân đoạn.

Khi đưa length validation vào yêu cầu bảo mật, điều quan trọng là xác định hệ thống đo cái gì, đo ở đâu và làm gì khi vượt giới hạn. Một hợp đồng rõ ràng cho phép đội phát triển, kiểm thử và vận hành kiểm chứng cùng một hành vi trên toàn bộ đường đi của dữ liệu.
