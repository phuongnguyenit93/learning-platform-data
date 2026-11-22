# Không biến định dạng chẩn đoán hoặc thuật toán băm thành giao thức ngoài ý muốn

Trong Java, `toString()` và `hashCode()` thuộc hợp đồng cơ bản của `Object`, nhưng mục tiêu của chúng **khác hẳn hợp đồng dữ liệu trao đổi với hệ thống bên ngoài**. `toString()` chủ yếu phục vụ biểu diễn văn bản dễ đọc hoặc chẩn đoán; `hashCode()` hỗ trợ những cấu trúc dựa trên băm như `HashMap`, `HashSet`. Nếu một chuỗi log hoặc giá trị hash tình cờ bị dùng làm mã định danh, khóa lưu trữ, dữ liệu API, cache key phân tán hay nội dung chữ ký, ứng dụng đã tạo ra một **giao thức ngầm** rất dễ vỡ khi refactor.

Bài học này thuộc nhóm **Thiết kế hợp đồng**: biết lựa chọn điểm nào cần ràng buộc ổn định, điểm nào nên được quyền thay đổi khi cài đặt tiến hóa, và cách tách chúng ở ranh giới hệ thống.

## 1. Phân biệt ba loại hợp đồng

| Thành phần | Mục tiêu chính | Có nên dùng trực tiếp làm hợp đồng bên ngoài? |
| --- | --- | --- |
| `toString()` | Biểu diễn đối tượng thành chuỗi; thường hữu ích cho debug/log | **Không mặc định.** Cú pháp, thứ tự trường, cách ẩn dữ liệu, ngôn ngữ trình bày có thể thay đổi. |
| `equals()` / `hashCode()` | Xác định bằng nhau và hỗ trợ các collection dựa trên băm trong chương trình | **Không mặc định.** Giá trị hash không phải định danh nghiệp vụ hay dấu vân tay ổn định cho kho dữ liệu. |
| DTO/schema/định danh công khai được thiết kế tường minh | Trao đổi dữ liệu và tương thích giữa các phiên bản, tiến trình, dịch vụ | **Có, khi đã quy định** trường, ý nghĩa, kiểu dữ liệu, quy tắc mã hóa, phiên bản và chính sách tương thích. |

**Ví dụ lỗi ranh giới:**

~~~java
// Đây là ví dụ PHẢN DIỆN; không nên dùng làm giao thức.
String externalKey = customer.hashCode() + "";
String requestBody = order.toString();
~~~

Chương trình có thể chạy và gửi dữ liệu, nhưng phía nhận không có hợp đồng đủ rõ về tính duy nhất, định dạng, độ bền qua các lần chạy hay thay đổi code.

Nguyên tắc thiết kế: **giá trị dùng để debug được tự do thay đổi theo nhu cầu chẩn đoán; dữ liệu công khai phải thay đổi theo một quy trình quản lý hợp đồng**.

## 2. Vì sao `toString()` không phải serializer hay định dạng API?

Phương thức `Object.toString()` mặc định tạo biểu diễn dạng tên lớp, dấu `@` và chuỗi thập lục phân bắt nguồn từ `hashCode()` của đối tượng. Đây là **chuỗi biểu diễn**, không phải ID toàn cục hay biểu diễn lưu trữ. Khi một lớp override `toString()`, tác giả có thể in tên trường, bỏ bớt thông tin, thêm tiền tố, che dữ liệu nhạy cảm, hoặc đổi thứ tự thuộc tính. Những thay đổi đó có thể hoàn toàn hợp lệ cho mục tiêu chẩn đoán.

Ngay cả chuỗi `toString()` do IDE, Lombok hoặc `record` sinh ra cũng không nên mặc nhiên trở thành một API. Chẳng hạn, thêm một component vào record có thể làm thay đổi `toString()` được sinh ra, và đổi cách triển khai có thể làm thay đổi toàn bộ biểu diễn dù dữ liệu nghiệp vụ không đổi.

Nếu dùng `toString()` để tạo request body, file cấu hình, dấu vết kiểm toán hoặc khóa cache, sẽ nảy sinh một số lỗi:

- **Breaking change âm thầm:** thêm trường phục vụ debug cũng làm thay đổi định dạng mà client/parser đang đọc.
- **Lỗi phân tích cú pháp:** dấu phẩy, dấu bằng, khoảng trắng, escape, `null`, xuống dòng và các giá trị lồng nhau không có bộ quy tắc wire-format đáng tin cậy.
- **Rò rỉ thông tin:** có thể xuất hiện token, mật khẩu, email, dữ liệu cá nhân hoặc thuộc tính nội bộ trong log hay response.
- **Không ổn định về môi trường:** định dạng số/ngày, locale hoặc thư viện định dạng có thể khác nhau giữa các nơi.
- **Khó phân biệt diagnostic với dữ liệu máy đọc:** log có thể thay đổi để hỗ trợ vận hành trong khi parser phía khác vẫn phụ thuộc chuỗi cũ.

**Đúng hướng:** xác định một DTO hoặc kiểu dữ liệu cho API, rồi dùng serializer có quy tắc công khai (ví dụ JSON qua Jackson khi ứng dụng đã có thư viện đó). Việc JSON hợp lệ không tự động bảo đảm tương thích: vẫn cần xác định tên trường, kiểu, optional/null, ý nghĩa, các enum hợp lệ, versioning và chiến lược nâng cấp.

Một ví dụ response có chủ đích:

~~~json
{
  "schemaVersion": 1,
  "invoiceId": "INV-104",
  "amountCents": 1500,
  "currency": "VND"
}
~~~

Hợp đồng phải nói rõ `invoiceId` là mã hóa đơn được hệ thống cấp, `amountCents` là đơn vị nhỏ nhất theo quy ước API, `currency` dùng mã tiền tệ nào, và trường `schemaVersion` được xử lý ra sao. Không nên để client tự đoán các điều ấy từ một chuỗi debug như `Invoice[id=INV-104, amount=1500]`.

## 3. Ví dụ Java 17: cùng một đối tượng, hai mục đích biểu diễn

Ví dụ sau cố ý giữ `toString()` ngắn để phục vụ log, nhưng định danh bên ngoài và DTO được lấy từ các trường được đặt tên rõ ràng.

**Tệp `ContractBoundaryDemo.java` (chạy độc lập với Java 17+):**

~~~java
public class ContractBoundaryDemo {
    record Invoice(String id, long amountCents) {
        @Override
        public String toString() {
            // Format chẩn đoán; không phải schema truyền dữ liệu.
            return "Invoice[id=" + id + "]";
        }
    }

    record InvoiceResponse(int schemaVersion, String invoiceId, long amountCents) {
    }

    public static void main(String[] args) {
        Invoice first = new Invoice("INV-104", 1500);
        Invoice same = new Invoice("INV-104", 1500);

        InvoiceResponse api = new InvoiceResponse(
                1, first.id(), first.amountCents());

        System.out.println("Diagnostic: " + first);
        System.out.println("Public ID: " + api.invoiceId());
        System.out.println("Schema version: " + api.schemaVersion());
        System.out.println("Equal invoices: " + first.equals(same));
        System.out.println("Equal hash codes: "
                + (first.hashCode() == same.hashCode()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ContractBoundaryDemo.java
java ContractBoundaryDemo
~~~

Kết quả:

~~~text
Diagnostic: Invoice[id=INV-104]
Public ID: INV-104
Schema version: 1
Equal invoices: true
Equal hash codes: true
~~~

Điều cần thấy:

1. `Invoice.toString()` được dùng trong thông điệp `Diagnostic` và có thể đổi thành `Invoice{number=...}` theo yêu cầu debug.
2. `InvoiceResponse` biểu diễn **hình dạng dữ liệu công khai ở mức Java**. Trong API thực tế, một serializer sẽ chuyển DTO thành payload theo schema đã công bố. `record.toString()` của DTO cũng không phải serializer.
3. `first.equals(same)` là `true`, do record mặc định so sánh component theo hợp đồng record; do đó hai đối tượng cũng phải có `hashCode()` bằng nhau. Điều này **không nói** rằng mã hash là ID duy nhất.
4. `INV-104` chỉ là định danh bên ngoài **nếu hệ thống thực sự cấp và bảo đảm tính duy nhất/phạm vi/độ bền** cho nó. Chỉ đặt một trường tên `id` không tự tạo ra các bảo đảm đó.

Cách tách giúp thay đổi nội dung log theo nhu cầu vận hành mà không tự ý sửa schema bên ngoài.

## 4. Vì sao `hashCode()` không phải mã định danh ổn định?

Theo hợp đồng Java:

- Nếu `a.equals(b)` trả về `true` thì `a.hashCode() == b.hashCode()` **phải đúng**.
- Hai đối tượng không bằng nhau **vẫn có thể** có cùng mã hash. Collisions là khả năng bình thường khi ánh xạ miền giá trị lớn vào một `int` 32-bit.
- `hashCode()` của đối tượng cần nhất quán trong một lần chạy khi thông tin tham gia so sánh bằng nhau không bị sửa; hợp đồng **không yêu cầu** giữ nguyên cùng con số qua hai lần thực thi chương trình.
- Override `hashCode()` có thể thay đổi công thức khi thuật toán nội bộ được chỉnh sửa miễn vẫn tôn trọng hợp đồng với `equals()`. Việc đó có thể làm hỏng dữ liệu ở hệ khác nếu trước đó xuất con số hash ra ngoài.

Một `HashMap` dùng `hashCode()` để tìm vùng lưu trữ và `equals()` để phân biệt những khóa có mã băm trùng nhau. Điều kiện nó cần khác với điều kiện của một **khóa CSDL, mã thanh toán, ID tài nguyên REST hoặc idempotency key**.

Lưu ý sắc thái: thuật toán của `String.hashCode()` được Java định nghĩa rõ và cùng nội dung string cho kết quả nhất quán theo đặc tả. Tuy vậy, nó vẫn chỉ là `int` có thể va chạm và không phải một giao thức ID an toàn, có namespace, cơ chế cấp phát và versioning. Không được suy luận rằng “mọi `hashCode()` đều thay đổi ở mỗi lần chạy”; vấn đề nằm ở **bảo đảm được công bố có phù hợp mục đích không**.

`System.identityHashCode(obj)` cũng không giải quyết bài toán định danh ngoài tiến trình: đây là mã băm theo danh tính tham chiếu trong một JVM, **không** là số thứ tự độc nhất toàn cục, không bảo đảm không va chạm và không phải khóa bền vững sau restart.

**Mẫu phản diện:**

~~~java
// Đừng lưu hay gửi mã định danh nghiệp vụ kiểu này:
int customerId = customer.hashCode();

// Đừng dùng chuỗi này làm khóa bền vững qua các phiên bản:
String storageKey = Integer.toHexString(order.hashCode());
~~~

Nếu dữ liệu của `order` dùng trong `equals()`/`hashCode()` thay đổi khi đang làm khóa `HashMap`/`HashSet`, tra cứu trong collection còn có thể hỏng ngay trong **cùng** chương trình. Với khóa của collection dựa trên hash, nên dùng value object bất biến hoặc tránh sửa trạng thái tham gia hợp đồng equality/hash khi đối tượng đang là khóa.

## 5. Bảng quyết định cho từng nhu cầu

| Nhu cầu | Nên thiết kế |
| --- | --- |
| In thông tin giúp lập trình viên debug | `toString()` an toàn, súc tích; che bí mật; log có cấu trúc khi cần truy vấn |
| Tra cứu trong `HashMap` / chống trùng trong `HashSet` | `equals()` và `hashCode()` tuân thủ hợp đồng, đặc biệt với khóa bất biến |
| ID bản ghi CSDL, URL tài nguyên, khóa đối chiếu giữa dịch vụ | ID nghiệp vụ hoặc ID được cấp phát (ví dụ UUID) với chính sách uniqueness và lifecycle |
| Payload HTTP/event/file để hệ thống khác giải mã | DTO + schema/serializer có version, các quy tắc encoding và compatibility |
| Cache key chia sẻ giữa nhiều tiến trình/phiên bản | Các trường xác định, quy tắc chuẩn hóa và mã hóa ổn định, namespace, phiên bản |
| Phát hiện dữ liệu bị đổi | Digest mật mã trên **byte encoding chuẩn hóa, đã xác định**; xét nguy cơ va chạm |
| Chứng minh thông điệp có nguồn tin cậy/chưa bị sửa bởi kẻ tấn công | HMAC hoặc chữ ký số theo mô hình tin cậy; digest đơn thuần chưa phải xác thực |

Không dùng `hashCode()` làm mã kiểm tra tính toàn vẹn hay biện pháp bảo mật: mã 32-bit không chống va chạm chủ đích, không có khóa bí mật và không mang thuộc tính xác thực.

## 6. Khi thực sự cần khóa tính toán ổn định từ nhiều trường

Đôi khi mã định danh không do một cơ quan cấp; ứng dụng cần một khóa xác định từ cặp giá trị như `tenantId` và `externalInvoiceId`. Khi đó phải quy định chính xác:

1. **Danh sách và thứ tự trường:** ví dụ `namespace, tenantId, externalInvoiceId`.
2. **Kiểu dữ liệu và quy tắc cho null:** không tùy tiện biến `null` thành chuỗi `"null"`; ví dụ dưới **cấm null**.
3. **Mã hóa byte:** ví dụ UTF-8; không phụ thuộc default charset của hệ điều hành.
4. **Ranh giới giữa trường:** tránh nối `"ab"+"c"` và `"a"+"bc"` đều thành `"abc"`. Có thể dùng tiền tố độ dài cố định để giữ cấu trúc.
5. **Chuẩn hóa:** có phân biệt hoa/thường, khoảng trắng đầu-cuối, Unicode normalization hay không? Quyết định theo nghiệp vụ rồi công bố; không tự ý `trim()`/lowercase.
6. **Namespace và phiên bản:** ví dụ `invoice-key-v1` trong input; đổi quy tắc phải có phương án migration.
7. **Thuật toán và cách hiển thị:** chọn SHA-256 cho digest, biểu diễn hex chữ thường; xác định rõ trường hợp các dịch vụ cần tái tạo cùng khóa.

**Tệp `StableKeyDemo.java` (Java 17+):**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;

public class StableKeyDemo {
    private static void writeField(DataOutputStream out, String value)
            throws IOException {
        Objects.requireNonNull(value, "A key field must not be null");
        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(utf8.length);       // 4 byte big-endian.
        out.write(utf8);
    }

    public static String deriveKey(String tenantId, String externalInvoiceId)
            throws NoSuchAlgorithmException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (DataOutputStream data = new DataOutputStream(bytes)) {
            writeField(data, "invoice-key-v1");
            writeField(data, tenantId);
            writeField(data, externalInvoiceId);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(bytes.toByteArray());
        return HexFormat.of().formatHex(digest);
    }

    public static void main(String[] args) throws NoSuchAlgorithmException {
        String first = deriveKey("tenant-A", "INV-104");
        String same = deriveKey("tenant-A", "INV-104");
        String other = deriveKey("tenant-A", "INV-105");

        System.out.println("Hex length: " + first.length());
        System.out.println("Same input: " + first.equals(same));
        System.out.println("Different input: " + !first.equals(other));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StableKeyDemo.java
java StableKeyDemo
~~~

Kết quả với các giá trị cố định trên:

~~~text
Hex length: 64
Same input: true
Different input: true
~~~

**Tại sao ổn định hơn `hashCode()` cho mục đích này?** Chuỗi `invoice-key-v1`, thứ tự các trường, UTF-8, mã hóa độ dài kiểu số nguyên 4 byte big-endian, SHA-256 và hex được mô tả tường minh. Các tiến trình triển khai cùng quy tắc có thể tạo cùng khóa. Không nên tùy tiện thay một thành phần sau khi đã ghi dữ liệu bền vững.

**Giới hạn của ví dụ:** SHA-256 không bảo đảm tuyệt đối không va chạm theo toán học; nếu cần danh tính nghiệp vụ chắc chắn, nên dùng ID được cấp phát và ràng buộc uniqueness trong nguồn dữ liệu có thẩm quyền. Digest không phải chữ ký số hoặc HMAC; ai biết input đều có thể tự tính. Ví dụ cũng chưa xử lý version migration, xác thực đầu vào, Unicode normalization hay nguy cơ suy đoán dữ liệu nhạy cảm có không gian giá trị nhỏ; ứng dụng phải quyết định theo yêu cầu thật. Với dữ liệu Unicode đa nguồn, cần quy định rõ các quy tắc chuẩn hóa và xử lý surrogate không hợp lệ trước khi mã hóa UTF-8.

## 7. Khi dùng serialization, đừng tự tin quá mức vào “mặc định”

Tách DTO mới chỉ là bước đầu. Hợp đồng wire cần được mô tả và thử bằng dữ liệu thực tế:

- **Tên, kiểu và đơn vị trường:** `amountCents` phải phân biệt với `amount` tính theo đơn vị tiền; số nguyên và chuỗi số không tự tương đương.
- **Thiếu trường và giá trị null:** quy định default có hợp lệ không, khác biệt với field hiện diện nhưng `null`.
- **Thứ tự và tính chuẩn hóa:** đối với JSON, client thông thường nên đọc field theo tên; nếu dùng JSON làm đầu vào để tạo chữ ký hoặc hash, phải áp dụng canonicalization đã thống nhất ở **byte level**, gồm thứ tự key và xử lý số/escape.
- **Giá trị mới:** enum mới, trạng thái mới hay trường mới có thể phá client có parser đóng; chiến lược thêm trường “tương thích ngược” còn tùy consumer.
- **Ngày giờ và locale:** chọn ISO-8601 với múi giờ/offset rõ ràng khi thích hợp; không dựa vào chuỗi mà `Date.toString()` hay formatter dùng locale mặc định tạo ra.
- **Versioning:** xác định phiên bản schema/API, quy tắc nhận phiên bản cũ, quá trình loại bỏ field và contract tests.
- **An toàn thông tin:** chỉ xuất trường cần thiết; log dạng có cấu trúc cũng phải masking dữ liệu nhạy cảm và kiểm soát retention/permissions.

Ví dụ danh sách trường ổn định trong JSON không nên được tạo bằng cách cắt, parse regex hoặc `split(",")` trên `toString()`. Cách ấy sẽ hỏng khi giá trị chứa dấu phẩy, xuống dòng hoặc cấu trúc lồng nhau.

## 8. Khi giao thức ngầm đã tồn tại ngoài đời

Một ứng dụng cũ có thể đang dùng `toString()` trong bản ghi audit hoặc `hashCode()` làm cache key. Thay cách triển khai ngay lập tức đôi khi làm client khác không đọc được, mất khóa tra cứu hoặc làm trùng lặp lệnh. Khi phát hiện, nên xử lý như thay đổi giao thức:

1. **Liệt kê người tiêu thụ**: API clients, job, event consumers, dashboard, DB, cache, log pipeline. Tìm nơi có parser hoặc khóa xây từ giá trị cũ.
2. **Đóng băng và mô tả định dạng đang tồn tại** để có thể nhận diện và di trú; thêm kiểm thử tương thích thực tế (golden samples) cho đường cũ nếu cần.
3. **Đề xuất trường và schema mới tường minh**, ví dụ `invoiceId` và `schemaVersion`; hoặc khóa `invoice-key-v1` với quy tắc tạo khóa công bố.
4. **Chuyển đổi có kiểm soát**: dual-read, dual-write, backfill hoặc alias ID theo nhu cầu, đồng thời kiểm soát uniqueness và thời hạn dữ liệu.
5. **Theo dõi consumer đã chuyển hết**, sau đó mới loại bỏ định dạng cũ theo chính sách tương thích và thông báo phiên bản. Giữ log phục vụ debug tách biệt.

Sửa `toString()` cho đẹp hơn hoặc thay `Objects.hash(...)` bằng thuật toán hash khác có thể là refactor tốt **trong phạm vi Object contract**; nhưng nếu kết quả đã thoát ra ngoài, cần quản lý như thay đổi giao thức ngoài chứ không coi là refactor vô hại.

## 9. Các dấu hiệu cảnh báo khi review code

| Dấu hiệu trong code | Câu hỏi cần đặt ra |
| --- | --- |
| `response.setBody(entity.toString())` | Đây là mô tả để xem hay payload mà client cần parse? Schema ở đâu? |
| `cacheKey = obj.hashCode()` | Va chạm, restart, sửa dữ liệu và khác phiên bản được xử lý thế nào? |
| `databaseId = identityHashCode(obj)` | Điều gì bảo đảm duy nhất và bền vững qua tiến trình? |
| `digest.update(obj.toString().getBytes())` | Charset, format, escaping và thứ tự trường đã là byte contract chưa? |
| `logger.info("{}", wholeEntity)` | `toString()` có lộ bí mật, chứa vòng tham chiếu hay tạo log quá lớn không? |
| `map.put(mutableKey, value)` rồi sửa key | `equals/hashCode` có thay đổi, làm việc tìm key trở nên sai không? |
| Client dùng regex trên log line | Log vốn là tín hiệu quan sát hay đã thành định dạng tích hợp không có phiên bản? |

Đối với log, ưu tiên các trường có cấu trúc rõ nghĩa như `eventType`, `correlationId`, `invoiceId` và `status`; định dạng thân thông báo có thể phục vụ người đọc. Không nên tuyên bố rằng một log là “không quan trọng” nếu thực tế hệ thống khác đang phụ thuộc nó: khi đó phải thừa nhận hợp đồng thực tế, nâng cấp người tiêu thụ rồi mới giải phóng định dạng chẩn đoán.

## 10. Tự kiểm tra

1. **Hai đối tượng khác nhau có cùng `hashCode()` được không?** Có. Hai mã hash trùng không chứng minh `equals()` trả về `true`.
2. **`String.hashCode()` có thuật toán được quy định, vậy có dùng làm ID trong DB không?** Không nên: là giá trị `int` có va chạm, thiếu ràng buộc uniqueness và chính sách định danh; sự ổn định của một thuật toán riêng không biến nó thành giao thức ID phù hợp.
3. **Thêm trường `phone` vào `toString()` có thể phá API không?** Có, nếu API đang lấy output `toString()` làm payload; còn có nguy cơ lộ thông tin không nên phát ra.
4. **Hai dịch vụ đều dùng SHA-256 trên JSON có nhất thiết tạo cùng digest không?** Không. Khác thứ tự key, whitespace, dạng số hoặc escape có thể tạo byte khác. Cần cùng encoding/canonicalization.
5. **Đổi `toString()` nhưng giữ `invoiceId` và schema DTO ổn định có đáng xem là API breaking change?** Thông thường không, miễn API thật sự chỉ trao đổi DTO theo hợp đồng đã công bố và không có consumer khác lệ thuộc chuỗi debug.
6. **Một ID hash SHA-256 có đảm bảo chống giả mạo dữ liệu không?** Không. Muốn xác thực nguồn hoặc tính toàn vẹn có đối thủ chủ động, cần chọn cơ chế khóa bí mật hoặc chữ ký phù hợp.

## Kết luận

Hợp đồng `Object` cho phép viết Java đúng đắn ở mức **biểu diễn chẩn đoán, so sánh bằng nhau và cấu trúc băm trong bộ nhớ**. Khi dữ liệu vượt ra ngoài ranh giới tiến trình hoặc trở thành dữ liệu lưu trữ lâu dài, hãy thiết kế **ID, DTO, schema, byte encoding, versioning và compatibility** một cách tường minh. Một chuỗi đẹp để đọc log hay con số thuận tiện cho `HashMap` không tự nhiên trở thành giao thức đáng tin cậy.
