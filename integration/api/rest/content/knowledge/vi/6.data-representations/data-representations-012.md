# Đa ngôn ngữ, Accept-Language và Content-Language

Một resource có thể giữ nguyên định danh và dữ liệu nghiệp vụ nhưng có nhiều cách biểu diễn bằng ngôn ngữ khác nhau. Chẳng hạn, `GET /products/42` vẫn truy cập sản phẩm `42`, dù tên và mô tả được trình bày bằng tiếng Việt hay tiếng Anh.

Trong chương **Biểu diễn dữ liệu** của module **INTEGRATION_API_REST**, bài học này tập trung vào hợp đồng ngôn ngữ giữa client và server: client nêu ưu tiên, server chọn một biểu diễn đang có, rồi thông báo ngôn ngữ thực tế của kết quả. Thiết kế cần giữ dữ liệu dễ tích hợp, cache đúng biến thể và xử lý rõ trường hợp không có bản dịch phù hợp.

Sau bài học, người học có thể đọc các header ngôn ngữ, thiết kế chính sách lựa chọn và fallback, triển khai một ví dụ Java/Spring, đồng thời xác định các tình huống cần kiểm thử ở tầng HTTP.

## 1. Resource và bản dịch là hai khái niệm khác nhau

Xét API danh mục công khai có sản phẩm `42`. ID, trạng thái kinh doanh và giá của sản phẩm không phụ thuộc ngôn ngữ; tên và mô tả có thể được dịch.

| Thành phần | Bản tiếng Việt | Bản tiếng Anh |
| --- | --- | --- |
| URI | `/products/42` | `/products/42` |
| `id` | `"42"` | `"42"` |
| `name` | Cốc sứ | Ceramic mug |
| `status` | `ACTIVE` | `ACTIVE` |
| `statusLabel` | Đang bán | Available |
| `price` | `129000.00` | `129000.00` |
| `currency` | `VND` | `VND` |

Tên field JSON và mã trạng thái nghiệp vụ giữ ổn định để client xử lý bằng máy. Nhãn hiển thị có thể đổi theo ngôn ngữ. Không dịch `ACTIVE` thành một mã khác chỉ vì client yêu cầu tiếng Việt.

Ngôn ngữ cũng không tự quyết định tiền tệ, múi giờ hay thị trường. Một người đọc tiếng Anh vẫn có thể mua hàng bằng VND tại Việt Nam. Nếu API cần những chiều dữ liệu đó, hãy mô hình hóa và xác thực chúng riêng.

## 2. Phân biệt các header

| Header | Vai trò |
| --- | --- |
| `Accept` | Client muốn kiểu biểu diễn nào, chẳng hạn JSON |
| `Accept-Language` | Client ưu tiên ngôn ngữ tự nhiên nào cho response |
| `Content-Type` | Mô tả định dạng nội dung của message đang gửi |
| `Content-Language` | Mô tả ngôn ngữ của đối tượng đọc mà nội dung hướng tới |
| `Vary` | Cho biết những header request ảnh hưởng đến lựa chọn biểu diễn, phục vụ cache |

Ví dụ request:

```http
GET /products/42 HTTP/1.1
Host: api.example.com
Accept: application/json
Accept-Language: vi-VN, vi;q=0.9, en;q=0.6
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Language: vi
Vary: Accept-Language
Cache-Control: public, max-age=60

{
  "id": "42",
  "name": "Cốc sứ",
  "status": "ACTIVE",
  "statusLabel": "Đang bán",
  "price": 129000.00,
  "currency": "VND"
}
```

`Content-Language: vi` phản ánh kết quả tiếng Việt đang trả về. Server không sao chép nguyên danh sách `vi-VN, vi;q=0.9, en;q=0.6` vào header này. Tham khảo định nghĩa [Accept-Language](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.4) và [Content-Language trong RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.5).

### 2.1. Language tag và language range

Các dạng thường gặp:

| Giá trị | Ý nghĩa |
| --- | --- |
| `vi` | Tiếng Việt |
| `vi-VN` | Tiếng Việt với biến thể vùng Việt Nam |
| `en` | Tiếng Anh |
| `en-GB` | Tiếng Anh với biến thể vùng Vương quốc Anh |
| `zh-Hans` | Tiếng Trung dùng chữ giản thể |
| `zh-Hant` | Tiếng Trung dùng chữ phồn thể |

Language tag dùng dấu gạch nối. `vi_VN` là dạng có thể gặp trong cấu hình hoặc biểu diễn nội bộ của một số thư viện, không phải cách viết tag nên xuất ra HTTP. So khớp tag không phân biệt hoa thường; cách viết như `vi-VN`, `en-GB`, `zh-Hant` giúp người đọc dễ nhận diện thành phần. Cấu trúc tag được mô tả trong [RFC 5646](https://www.rfc-editor.org/rfc/rfc5646.html).

`Accept-Language` chứa **language range**, trong đó có thể có `*`. `Content-Language` chứa **language tag**; không đưa `*` hoặc trọng số `q` vào đây.

## 3. Đọc Accept-Language theo mức ưu tiên

```http
Accept-Language: vi-VN, vi;q=0.9, en;q=0.6, *;q=0.1
```

Cách diễn giải:

1. Ưu tiên `vi-VN`, với trọng số mặc định là `1`.
2. Tiếp theo là `vi`, trọng số `0.9`.
3. Tiếp theo là `en`, trọng số `0.6`.
4. Chấp nhận lựa chọn khác qua `*`, nhưng ở mức ưu tiên thấp.

Trọng số `q` nằm trong khoảng từ `0` đến `1`, có tối đa ba chữ số sau dấu thập phân. `q=0` biểu thị không chấp nhận lựa chọn tương ứng. Với các giá trị có cùng trọng số, client không nên mặc nhiên trông cậy rằng mọi server đều ưu tiên theo thứ tự xuất hiện. Xem [RFC 9110, Quality Values](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.4.2).

Ví dụ:

```http
Accept-Language: en;q=1, vi;q=0
```

Nếu API tuyên bố tôn trọng lựa chọn ngôn ngữ, server không nên trả tiếng Việt như một fallback tùy tiện. Việc loại bỏ các mục `q=0` rồi quên chúng là lỗi thiết kế: danh sách còn lại không thể hiện đầy đủ lựa chọn client đã từ chối.

Wildcard không phải lệnh dịch tự động. Nó chỉ tham gia lựa chọn giữa những bản ngôn ngữ server thực sự có.

## 4. Công bố chính sách lựa chọn và fallback

Header chỉ là đầu vào. API còn cần quyết định tập ngôn ngữ hỗ trợ, cách so khớp và hành vi khi không tìm thấy kết quả.

Ví dụ xuyên suốt bài dùng hợp đồng sau:

- Resource có hai bản dịch đầy đủ: `vi` và `en`.
- Không có ưu tiên ngôn ngữ thì chọn `vi`.
- Với ưu tiên hợp lệ có trọng số dương, dùng lookup để tìm một bản đang có; chẳng hạn `en-GB` có thể dẫn tới bản `en`.
- Mục ngôn ngữ có `q=0` được dùng để loại lựa chọn bị cấm. `*;q=0` không tự phủ nhận một mục cụ thể có trọng số dương như `en;q=1`.
- Wildcard có trọng số dương chọn một bản còn được phép; thứ tự lựa chọn của server là `vi`, rồi `en`.
- Nếu header hợp lệ nhưng không chọn được bản nào, trả `406 Not Acceptable`.
- Header sai cú pháp được xử lý bằng `400 Bad Request` theo quy ước của ví dụ.

Đây là **chính sách của API minh họa**, không phải yêu cầu mọi REST API phải trả `406` khi thiếu bản dịch. HTTP cho phép server bỏ qua một ưu tiên thương lượng để cung cấp biểu diễn mặc định; quyết định đó phải được nêu rõ cho người tích hợp. Tham khảo [RFC 9110, Content Negotiation](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.4.1).

### 4.1. Lookup khác filtering

Filtering tìm tập tag phù hợp với một range; lookup chọn một tag bằng cách tìm từ lựa chọn cụ thể về tổng quát. Vì vậy, không nên dùng phép so sánh chuỗi bằng tuyệt đối rồi kết luận `en-GB` hoàn toàn không liên quan đến `en`.

Ngược lại, không phải mọi ngôn ngữ cùng vùng đều thay thế được nhau. `zh-Hant` và `zh-Hans` còn khác hệ chữ; tự ý bỏ tất cả thành phần ngoài mã ngôn ngữ có thể làm mất ý nghĩa sản phẩm cần bảo toàn. Các cơ chế so khớp và hành vi mặc định được mô tả trong [RFC 4647](https://www.rfc-editor.org/rfc/rfc4647.html#section-3).

### 4.2. Bảng hành vi của API minh họa

| Accept-Language | Kết quả | Lý do |
| --- | --- | --- |
| Không gửi | `200`, `Content-Language: vi` | Mặc định được công bố |
| `en` | `200`, `Content-Language: en` | Có bản phù hợp |
| `en-GB, vi;q=0.5` | `200`, `Content-Language: en` | Lookup `en-GB` về `en` |
| `fr, en;q=0.8` | `200`, `Content-Language: en` | Xét tiếp ưu tiên sau `fr` |
| `fr` | `406` | Không có bản được yêu cầu và API chọn chính sách nghiêm |
| `vi;q=0, en;q=1` | `200`, `Content-Language: en` | Tiếng Việt bị loại |
| `vi;q=0, *;q=0.5` | `200`, `Content-Language: en` | Wildcard chọn bản còn được phép |
| `*;q=0, en;q=1` | `200`, `Content-Language: en` | Có yêu cầu cụ thể được chấp nhận |
| `vi;q=0, en;q=0` | `406` | Không còn bản hợp lệ |
| `*;q=0` | `406` | Không có ưu tiên dương nào để chọn |
| `en;q=1.5` | `400` | Trọng số ngoài phạm vi |
| `vi_VN` | `400` | Sai cú pháp range của ví dụ |

Mặc định chỉ được áp dụng ở đúng nhánh hợp đồng cho phép. Nó không phải lối thoát luôn trả tiếng Việt sau mọi thất bại.

### 4.3. Chọn từ các bản thực sự tồn tại

Danh sách ngôn ngữ của toàn hệ thống chưa đủ để chọn bản dịch cho từng resource. Nếu hệ thống hỗ trợ `vi`, `en` nhưng sản phẩm `99` chỉ có bản `en`, bộ chọn cần nhận tập khả dụng của sản phẩm đó.

Có hai thiết kế phổ biến:

- **Chọn trọn biểu diễn:** chỉ chọn một ngôn ngữ khi các trường bắt buộc đã có bản dịch đầy đủ. Cách này dễ giải thích và cache.
- **Fallback theo trường:** tên dùng tiếng Việt nhưng mô tả tạm dùng tiếng Anh. Cách này cần hợp đồng chỉ rõ trường nào có thể fallback và cách client nhận biết.

Bài học chọn trọn biểu diễn. Không gắn `Content-Language: vi` chỉ vì client yêu cầu tiếng Việt khi nội dung hướng tới họ thực tế vẫn là bản tiếng Anh.

## 5. Content-Language mô tả nội dung đã được chọn

### 5.1. Header không thực hiện việc dịch

Đặt `Content-Language: en` không làm body tiếng Việt trở thành tiếng Anh. Header phải được tạo sau khi biết nội dung thực tế.

Một quy trình dễ kiểm soát:

```text
Request
  -> đọc và kiểm tra ưu tiên ngôn ngữ
  -> tìm các bản dịch khả dụng của resource
  -> chọn ngôn ngữ theo hợp đồng
  -> dựng DTO từ bản dịch được chọn
  -> gắn Content-Language tương ứng
  -> trả response và metadata cache
```

DTO và header nên nhận cùng một kết quả lựa chọn. Nếu controller dùng một locale để lấy dữ liệu còn interceptor tự đọc lại header để gắn nhãn, hai phần dễ bất đồng khi có fallback.

### 5.2. Nội dung hướng tới nhiều nhóm ngôn ngữ

Một tài liệu chủ đích phục vụ đồng thời người đọc tiếng Việt và tiếng Anh có thể có:

```http
Content-Language: vi, en
```

Đây là mô tả đối tượng đọc của **một** nội dung đa ngôn ngữ. Việc có tên riêng hoặc một câu trích tiếng Anh trong tài liệu tiếng Việt không tự động đòi hỏi thêm `en`; hãy dựa vào đối tượng đọc mà nội dung hướng tới. Xem [RFC 9110, Content-Language](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.5).

Nếu API quản trị trả nhiều bản dịch riêng biệt, có thể ghi tag ngay trong từng mục:

```json
{
  "id": "42",
  "translations": [
    { "language": "vi", "name": "Cốc sứ" },
    { "language": "en", "name": "Ceramic mug" }
  ]
}
```

Đây là hợp đồng khác với endpoint danh mục chỉ trả một bản dịch được chọn.

## 6. Header ngôn ngữ trong request có body

`Accept-Language` nêu ưu tiên cho response, không mô tả ngôn ngữ của dữ liệu client đang gửi.

Ví dụ đăng một đánh giá tiếng Việt nhưng muốn đọc phản hồi tiếng Anh:

```http
POST /products/42/reviews HTTP/1.1
Host: api.example.com
Content-Type: application/json
Content-Language: vi
Accept-Language: en

{
  "rating": 5,
  "comment": "Cốc đẹp, đóng gói cẩn thận."
}
```

Hai giá trị khác nhau hoàn toàn hợp lý. API có thể lưu ngôn ngữ đánh giá là `vi`, rồi trả thông báo xác nhận bằng `en`. Client không thể thay nội dung bình luận đã lưu chỉ bằng cách gửi `Accept-Language` khác trong lần đọc sau.

Khi body chứa nhiều trường thuộc nhiều ngôn ngữ, cần metadata theo trường hoặc theo mục nếu nghiệp vụ cần biết chính xác. Header chung không thay thế được mô hình dữ liệu này.

## 7. Minh họa lựa chọn ngôn ngữ bằng Java 17

JDK có `Locale.LanguageRange.parse` để đọc danh sách ưu tiên và `Locale.lookupTag` để lookup tag. Cần bổ sung chính sách HTTP của ứng dụng thay vì mặc nhiên dùng kết quả `null` làm lý do trả ngôn ngữ mặc định. Xem tài liệu [LanguageRange](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.LanguageRange.html) và [Locale.lookupTag](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html#lookupTag(java.util.List,java.util.Collection)).

Lớp dưới đây minh họa đúng tập hỗ trợ **hai tag tổng quát `vi`, `en`**, với giả định cả hai bản dịch đều có. Các giới hạn kích thước và cách xử lý mục lặp là quy ước của ví dụ:

- Tối đa 1.024 ký tự và 20 phần tử phân tách bằng dấu phẩy.
- Bỏ qua phần tử rỗng; danh sách không còn phần tử nào được coi như không có ưu tiên.
- Không nhận range lặp sau khi chuẩn hóa hoa thường.
- Khi các range có cùng `q`, xếp theo chữ cái để kết quả ổn định trong ví dụ.

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Locale.LanguageRange;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class CatalogLanguages {
    private static final List<String> SUPPORTED = List.of("vi", "en");
    private static final Pattern ITEM = Pattern.compile(
        "(?i)([a-z]{1,8}(?:-[a-z0-9]{1,8})*|\\*)"
        + "(?:[ \\t]*;[ \\t]*q=(0(?:\\.[0-9]{0,3})?|1(?:\\.0{0,3})?))?"
    );

    private CatalogLanguages() {}

    public static Optional<String> select(String header) {
        if (header == null || header.isBlank()) {
            return Optional.of("vi");
        }
        if (header.length() > 1024) {
            throw new IllegalArgumentException("Accept-Language too long");
        }

        String[] items = header.split(",", -1);
        if (items.length > 20) {
            throw new IllegalArgumentException("Too many language ranges");
        }

        Set<String> seen = new HashSet<>();
        List<String> normalized = new ArrayList<>();
        for (String item : items) {
            if (item.isBlank()) {
                continue;
            }
            Matcher matcher = ITEM.matcher(item.strip());
            if (!matcher.matches()) {
                throw new IllegalArgumentException("Invalid language range");
            }
            String range = matcher.group(1).toLowerCase(Locale.ROOT);
            if (!seen.add(range)) {
                throw new IllegalArgumentException("Repeated language range");
            }
            String weight = matcher.group(2);
            normalized.add(range + (weight == null ? "" : ";q=" + weight));
        }
        if (normalized.isEmpty()) {
            return Optional.of("vi");
        }

        List<LanguageRange> ranges = LanguageRange.parse(
            String.join(",", normalized)
        ).stream().sorted(
            Comparator.comparingDouble(LanguageRange::getWeight)
                .reversed()
                .thenComparing(LanguageRange::getRange)
        ).toList();

        // Loại bản bị cấm trước khi lookup hoặc xét wildcard.
        List<String> candidates = SUPPORTED.stream().filter(tag ->
            ranges.stream().noneMatch(range ->
                range.getWeight() == 0
                && !range.getRange().equals("*")
                && basicMatches(range.getRange(), tag)
            )
        ).toList();

        for (LanguageRange range : ranges) {
            if (range.getWeight() == 0) {
                continue;
            }
            if (range.getRange().equals("*")) {
                return candidates.stream().findFirst();
            }
            String selected = Locale.lookupTag(List.of(range), candidates);
            if (selected != null) {
                return Optional.of(selected);
            }
        }
        return Optional.empty();
    }

    private static boolean basicMatches(String range, String tag) {
        String normalizedTag = tag.toLowerCase(Locale.ROOT);
        return normalizedTag.equals(range)
            || normalizedTag.startsWith(range + "-");
    }
}
```

Một số kết quả cần hiểu khi đọc mã:

```java
CatalogLanguages.select(null);                  // Optional[vi]
CatalogLanguages.select("en-GB, vi;q=0.5");      // Optional[en]
CatalogLanguages.select("vi;q=0, *;q=0.5");      // Optional[en]
CatalogLanguages.select("*;q=0, en;q=1");        // Optional[en]
CatalogLanguages.select("vi;q=0, en;q=0");       // Optional.empty
CatalogLanguages.select("fr");                 // Optional.empty
CatalogLanguages.select("en;q=1.5");            // IllegalArgumentException
```

`Optional.empty()` biểu thị không chọn được bản theo hợp đồng, để tầng HTTP quyết định response `406`. Lỗi cú pháp đi theo nhánh khác; không dùng chung một giá trị để diễn đạt cả hai tình huống.

Phạm vi của lớp được cố ý giới hạn. Nếu thêm các bản `en-US`, `en-GB` hoặc tag có hệ chữ, cần thiết kế và kiểm chứng quy tắc giữa range tổng quát, range cụ thể và các mục loại trừ. Không suy rằng chỉ thêm một tag vào `SUPPORTED` đã tạo ra bộ thương lượng phù hợp cho mọi hệ thống. Khi bản dịch thiếu theo sản phẩm, hãy truyền tập khả dụng vào bộ chọn thay cho danh sách cố định.

## 8. Trả body và header nhất quán trong Spring MVC

Controller dưới đây phục vụ duy nhất sản phẩm `42` để tập trung vào biểu diễn. Danh mục này công khai, có đủ hai bản dịch và không thay đổi theo tài khoản; đó là giả định cho phép dùng `Cache-Control: public`.

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    public record ProductView(
        String id,
        String name,
        String status,
        String statusLabel,
        BigDecimal price,
        String currency
    ) {}

    @GetMapping(value = "/products/42", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> getProduct(
        @RequestHeader(value = "Accept-Language", required = false) String header
    ) {
        final Optional<String> selected;
        try {
            selected = CatalogLanguages.select(header);
        } catch (IllegalArgumentException exception) {
            return languageError(HttpStatus.BAD_REQUEST, "INVALID_ACCEPT_LANGUAGE");
        }
        if (selected.isEmpty()) {
            return languageError(
                HttpStatus.NOT_ACCEPTABLE, "LANGUAGE_NOT_ACCEPTABLE"
            );
        }

        String language = selected.orElseThrow();
        ProductView body = language.equals("vi")
            ? new ProductView("42", "Cốc sứ", "ACTIVE", "Đang bán",
                new BigDecimal("129000.00"), "VND")
            : new ProductView("42", "Ceramic mug", "ACTIVE", "Available",
                new BigDecimal("129000.00"), "VND");

        return ResponseEntity.ok()
            .header("Content-Language", language)
            .header("Vary", "Accept-Language")
            .header("Cache-Control", "public, max-age=60")
            .body(body);
    }

    private ResponseEntity<?> languageError(HttpStatus status, String code) {
        return ResponseEntity.status(status)
            .header("Vary", "Accept-Language")
            .header("Cache-Control", "no-store")
            .body(Map.of(
                "code", code,
                "availableLanguages", List.of("vi", "en")
            ));
    }
}
```

`ResponseEntity` cho phép trả status, header và body trong cùng một kết quả; xem [tài liệu Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html).

Lỗi thương lượng ở ví dụ dùng mã ổn định và danh sách tag để client xử lý mà không cần hiểu câu thông báo đã dịch. Khi bổ sung thông điệp cho con người, hãy dùng chính sách ngôn ngữ lỗi có điểm dừng rõ ràng. Bộ xử lý lỗi không được gọi lại bộ thương lượng vừa thất bại theo cách tạo vòng lặp.

Ở ứng dụng nhiều endpoint, nên đặt việc lựa chọn ngôn ngữ ở thành phần dùng chung và truyền kết quả vào service. Nếu dùng `LocaleResolver`, interceptor hoặc message bundle của Spring, cần đối chiếu hành vi thực tế với hợp đồng, đặc biệt với `q=0`, wildcard và fallback. Locale do framework cung cấp không chứng minh rằng dữ liệu dịch tương ứng chắc chắn tồn tại.

Không gọi `Locale.setDefault(...)` theo mỗi request. Locale mặc định là trạng thái dùng chung trong JVM; thay đổi theo một người dùng có thể ảnh hưởng request khác. Với xử lý bất đồng bộ, cần truyền lựa chọn ngôn ngữ tường minh hoặc quản lý ngữ cảnh phù hợp với cách thực thi.

## 9. Cache phải nhận diện biến thể ngôn ngữ

Giả sử hai client gọi cùng URI:

```text
Client A: GET /products/42, Accept-Language: vi
Client B: GET /products/42, Accept-Language: en
```

Nếu cache chỉ phân biệt URI mà bỏ qua ngôn ngữ, B có thể nhận body tiếng Việt đã được lưu từ A. Trong thiết kế thương lượng qua header, response có thể được cache cần cho biết chiều lựa chọn:

```http
Vary: Accept-Language
```

Ý nghĩa của header trong việc tái sử dụng response được mô tả tại [RFC 9110, Vary](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.5).

Bốn điểm triển khai cần thống nhất:

1. **Đặt header cho cả bản mặc định.** Request không gửi `Accept-Language` vẫn là một tình huống đầu vào của cơ chế lựa chọn.
2. **Giữ các chiều Vary khác.** Nếu tầng nén đã thêm `Accept-Encoding`, cấu hình cuối cùng cần giữ cả hai, chẳng hạn `Vary: Accept-Language, Accept-Encoding`.
3. **Kiểm tra cache thực tế.** Origin gửi header chưa đủ nếu CDN được cấu hình bỏ qua header đó hoặc selector trên URI.
4. **Phân biệt dữ liệu công khai và cá nhân hóa.** Nếu ngôn ngữ lấy từ hồ sơ và body còn phụ thuộc danh tính, riêng `Vary: Accept-Language` không bảo vệ được sự khác nhau giữa tài khoản. Cần chính sách như `private` hoặc `no-store` phù hợp.

Các chuỗi header khác nhau có thể dẫn tới cùng bản dịch:

```http
Accept-Language: vi-VN, vi;q=0.9
```

```http
Accept-Language: vi
```

Cache theo giá trị header thô có thể tạo nhiều mục cho cùng nội dung. Nếu chuẩn hóa tại gateway hoặc CDN, phải dùng cùng chính sách với origin và bảo đảm khóa cache hình thành sau bước lựa chọn phù hợp. Không tự bỏ toàn bộ phần trọng số chỉ để tăng tỷ lệ cache hit.

### 9.1. ETag thuộc về biểu diễn đã chọn

Nếu bổ sung ETag, cần phân biệt những bản có body khác nhau. Ví dụ:

```http
Content-Language: vi
ETag: "product-42-vi-r7"
```

```http
Content-Language: en
ETag: "product-42-en-r4"
```

Các chuỗi trên minh họa cách định danh; hệ thống phải bảo đảm validator thay đổi phù hợp khi biểu diễn tương ứng thay đổi. Cùng phiên bản dữ liệu sản phẩm chưa đủ nếu bản dịch được cập nhật riêng.

Khi nhận `If-None-Match`, hãy chọn đúng biến thể trước rồi so với validator của nó. Không trả `304` chỉ vì client có validator của bản tiếng Anh trong khi request hiện tại cần bản tiếng Việt có nội dung khác. Response `304` cần giữ metadata cache bắt buộc của kết quả tương ứng, gồm `Vary` và ETag khi áp dụng.

Controller ở mục trước chưa triển khai ETag hay `304`; khi bổ sung, cần gắn chúng với cùng kết quả chọn ngôn ngữ.

## 10. Khi nào nên chọn ngôn ngữ qua URI?

Thương lượng bằng header giữ URI resource gọn:

```http
GET /products/42
Accept-Language: vi
```

Lựa chọn khác là selector tường minh:

```http
GET /products/42?lang=vi
```

Hoặc thiết kế một resource bản dịch có thể quản lý độc lập:

```http
GET /products/42/translations/vi
```

| Cách chọn | Tình huống phù hợp | Điều cần công bố |
| --- | --- | --- |
| Header | Tích hợp muốn giữ một URI sản phẩm | Thuật toán thương lượng, fallback, Vary |
| Query parameter | Cần chia sẻ đường dẫn với ngôn ngữ được chọn | Tập giá trị hợp lệ, cách tạo cache key |
| Resource bản dịch | Cần đọc, sửa, phân quyền từng bản dịch | Định danh và vòng đời của bản dịch |

Nếu nhận đồng thời `lang` và `Accept-Language`, phải nêu thứ tự ưu tiên hoặc cách xử lý xung đột. Chẳng hạn, có thể quy định selector trên URI quyết định ngôn ngữ, header chỉ dùng khi selector vắng mặt. Khi đó, không áp dụng máy móc `Vary: Accept-Language` cho mọi response nếu header không tham gia lựa chọn.

Header ngôn ngữ không cấp quyền xem bản dịch. Quyền đọc hoặc chỉnh sửa vẫn phải dựa trên danh tính và chính sách truy cập của resource. Không dùng `vi-VN` làm bằng chứng người gọi thuộc một quốc gia hoặc nhóm người dùng.

## 11. Hợp đồng OpenAPI và thông báo lỗi

Trong OpenAPI, có thể mô tả `Accept-Language` là header kiểu chuỗi, kèm ví dụ danh sách có trọng số và phần diễn giải thuật toán. Không giới hạn toàn bộ giá trị header bằng `enum: [vi, en]` nếu API thực sự chấp nhận danh sách range và trọng số: enum đó sẽ phủ nhận những request hợp lệ theo chính hợp đồng.

Cần mô tả `Content-Language` ở response thành công và ghi nhận response `400`, `406` nếu chọn chính sách trong bài. Ngôn ngữ tài liệu OpenAPI không bắt buộc trùng ngôn ngữ dữ liệu trả về.

Thông báo lỗi cho con người có thể dịch; mã lỗi cần ổn định:

```json
{
  "code": "PRODUCT_NOT_FOUND",
  "message": "Không tìm thấy sản phẩm.",
  "traceId": "request-7f2a"
}
```

Client dùng `code` để rẽ nhánh, `message` để hiển thị. Không so sánh câu tiếng Việt hoặc tiếng Anh để quyết định có cần thử lại request.

Nếu danh sách ngôn ngữ được đưa vào log hoặc số liệu vận hành, nên ưu tiên tag đã chọn và nguyên nhân fallback. Tránh dùng nguyên header không giới hạn làm nhãn thống kê vì nó tạo số lượng giá trị rất lớn. Chỉ ghi ưu tiên chi tiết khi có nhu cầu và chính sách dữ liệu phù hợp.

## 12. Các tình huống kiểm thử có giá trị

Bảng ở mục 4 là điểm khởi đầu cho kiểm thử hợp đồng. Cần xác minh cả **body, status và header**; chỉ thấy HTTP `200` chưa chứng minh chọn đúng ngôn ngữ.

Quan sát thủ công:

```bash
curl -i "http://localhost:8080/products/42" \
  -H "Accept: application/json" \
  -H "Accept-Language: en-GB, vi;q=0.5"
```

Mong đợi theo hợp đồng minh họa: `200`, `Content-Language: en`, `Vary` có `Accept-Language`, `name` là `Ceramic mug`, `status` vẫn là `ACTIVE`.

```bash
curl -i "http://localhost:8080/products/42" \
  -H "Accept-Language: vi;q=0, en;q=0"
```

Mong đợi: `406`, mã `LANGUAGE_NOT_ACCEPTABLE`, không có body sản phẩm bị gắn nhãn ngôn ngữ tùy tiện.

```bash
curl -i "http://localhost:8080/products/42" \
  -H "Accept-Language: en;q=1.5"
```

Mong đợi: `400`, mã `INVALID_ACCEPT_LANGUAGE`.

Các lệnh dùng cú pháp Bash; trên PowerShell có thể dùng `curl.exe` và đặt các tham số trên cùng một dòng.

Ngoài request đơn lẻ, cần chú ý:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Hai request `vi` và `en` liên tiếp qua cache | Không lẫn body hoặc header giữa hai bản |
| Request không có header sau request có header | Mặc định đúng, không bị request trước ảnh hưởng |
| Body giữa các ngôn ngữ | ID, mã trạng thái, kiểu giá và tiền tệ giữ nguyên |
| Một bản dịch bắt buộc bị thiếu | Đúng chính sách trọn biểu diễn hoặc fallback |
| Request song song bằng hai ngôn ngữ | Không chia sẻ locale có thể bị thay đổi giữa request |
| Lỗi nghiệp vụ sau khi chọn ngôn ngữ | Mã lỗi ổn định, câu hiển thị đúng chính sách |
| Validator `en` được gửi khi yêu cầu `vi` | Không trả `304` nhầm khi body được chọn khác |
| Header quá dài hoặc có quá nhiều mục | Từ chối có kiểm soát, không phản chiếu nguyên header vào lỗi |

Đây là mục tiêu kiểm thử cho người triển khai, không phải khẳng định các đoạn mã minh họa đã được chạy trong một dự án Spring hoàn chỉnh.

## 13. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Lấy mục đầu tiên bằng `split(",")[0]` | Bỏ qua trọng số và ưu tiên còn lại | Parse range, trọng số và quy tắc lựa chọn |
| Dùng locale mặc định của máy chủ | Hành vi thay đổi theo môi trường | Đặt mặc định trong hợp đồng |
| Luôn fallback sang `vi` | Có thể trả lựa chọn bị từ chối | Giữ các mục loại trừ và công bố fallback |
| Gắn header trước khi chọn bản dịch | Header khác với body | Dùng chung kết quả lựa chọn |
| Đổi tên field hoặc mã nghiệp vụ theo ngôn ngữ | Client tích hợp bị hỏng | Chỉ dịch nội dung và nhãn hiển thị |
| Thiếu `Vary` khi thương lượng qua header | Cache trả nhầm biến thể | Đồng bộ origin và cache |
| Dùng ngôn ngữ làm bằng chứng phân quyền | Quyết định truy cập không đáng tin | Xác thực và phân quyền theo resource |
| Thay locale toàn cục theo request | Request ảnh hưởng lẫn nhau | Truyền ngữ cảnh riêng cho mỗi lần xử lý |

Khi thiết kế endpoint mới, hãy xác định phần dữ liệu cần dịch, tập bản dịch thực có và ngôn ngữ thực tế của kết quả trước khi quyết định header. Một hợp đồng rõ ràng giúp client dự đoán được hành vi ngay cả khi yêu cầu không khớp hoàn toàn với các bản dịch đang có.
