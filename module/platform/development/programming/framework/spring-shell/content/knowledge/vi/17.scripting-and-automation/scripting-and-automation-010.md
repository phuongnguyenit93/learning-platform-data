# Đầu ra JSON hoặc CSV do ứng dụng thiết kế cho máy đọc

Một command thường hiển thị bảng hoặc câu mô tả để người vận hành đọc. Khi kết quả được chuyển vào script, pipeline hoặc một chương trình khác, đầu ra cần có cấu trúc ổn định để máy có thể phân tích mà không phải đoán nội dung.

Spring Shell không tự biến mọi object trả về thành JSON hoặc CSV. Result handler mặc định xử lý object bằng cách gọi **toString()**. Vì vậy, ứng dụng phải chủ động chọn định dạng, định nghĩa schema, serialize dữ liệu và ghi đúng nội dung ra output. Spring Shell cung cấp **CommandContext.outputWriter()** để command ghi vào luồng output do shell quản lý.

Bài này dùng Spring Shell 4.x kết hợp Spring Boot 4 và Jackson 3 cho JSON. CSV được minh họa theo các quy tắc phổ biến của RFC 4180. Hai định dạng là hợp đồng dữ liệu do ứng dụng công bố; consumer phải dựa vào hợp đồng đó để đọc kết quả.

## 1. Đầu ra cho người đọc và đầu ra cho máy đọc

Đầu ra cho người đọc ưu tiên dễ quan sát: bảng căn cột, màu sắc, lời giải thích và thông báo tiến độ. Đầu ra cho máy đọc ưu tiên cú pháp có thể phân tích, tên trường ổn định, kiểu dữ liệu nhất quán và không có nội dung trang trí xen vào.

| Đầu ra | Ví dụ | Đặc điểm |
|---|---|---|
| Văn bản cho người đọc | Đã xuất 12 đơn hàng thành công. | Dễ hiểu nhưng không phải schema dữ liệu |
| Bảng terminal | Bảng có đường viền và căn cột | Phù hợp quan sát; định dạng có thể đổi theo độ rộng terminal |
| JSON | Mảng object có key và value | Biểu diễn dữ liệu lồng nhau, kiểu boolean, số, null và danh sách |
| CSV | Header và các dòng có cùng số cột | Phù hợp dữ liệu dạng bảng, dễ đưa vào spreadsheet và công cụ xử lý dữ liệu |

Không nên để một command vừa in lời chào, vừa in bảng, rồi mới in JSON. Một consumer có thể nhận cả phần văn bản không thuộc định dạng và thất bại khi parse. Hãy dành một chế độ riêng cho dữ liệu máy đọc và giữ stdout chỉ chứa payload của định dạng đã chọn.

## 2. Định nghĩa hợp đồng đầu ra trước khi serialize

JSON và CSV chỉ là cách mã hóa dữ liệu. Để hai hệ thống trao đổi ổn định, ứng dụng cần công bố những quyết định sau:

| Thành phần hợp đồng | Câu hỏi cần trả lời |
|---|---|
| Root structure | JSON là một object, một array hay envelope chứa metadata và data? |
| Field name | Tên thuộc tính dùng camelCase, snake_case hay quy ước khác? |
| Field order | Thứ tự có ý nghĩa không? Với CSV, thứ tự cột phải được cố định |
| Data type | Số tiền là JSON number hay string? ID là string hay number? |
| Date/time | Dùng ISO-8601, UTC hay offset cụ thể? |
| Null | Field null được giữ, bỏ đi hay đổi thành giá trị mặc định? |
| Empty result | Trả về [], object rỗng hay chỉ header CSV? |
| Ordering | Các record được sắp xếp theo trường nào? |
| Version | Thay đổi tên field hoặc kiểu dữ liệu có làm thay đổi schema version không? |
| Encoding | Consumer đọc UTF-8 hay một charset khác? |

Hợp đồng tốt giúp consumer không phải dựa vào thứ tự tình cờ của database, locale của máy chạy hoặc cách Java in object.

Ví dụ, một lệnh xuất đơn hàng có thể định nghĩa:

- JSON root là một array; mỗi phần tử là một đơn hàng.
- Field gồm **orderId**, **customerName**, **total** và **createdAt**.
- **orderId** và **customerName** là chuỗi; **total** là số thập phân; **createdAt** là chuỗi ISO-8601 UTC.
- Kết quả không có bản ghi là array rỗng **[]**.
- Record được sắp xếp theo thời gian tạo tăng dần, sau đó theo mã đơn hàng.
- CSV dùng cùng tập field và cùng thứ tự cột; hàng đầu là header.

Nếu cần metadata như thời điểm xuất, tổng số bản ghi hoặc schema version, JSON có thể dùng envelope:

~~~json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-26T08:30:00Z",
  "data": [
    {
      "orderId": "OD-1001",
      "customerName": "An Bình",
      "total": 125000.50,
      "createdAt": "2026-11-26T08:15:00Z"
    }
  ]
}
~~~

Không thay đổi root từ array sang object chỉ vì muốn thêm một field mà không version hóa hợp đồng. Consumer đang mong đợi array sẽ không còn đọc được payload mới.

## 3. Dùng Jackson 3 để tạo JSON

Spring Boot 4 ưu tiên Jackson 3. Khi Jackson 3 có trên classpath, auto-configuration cung cấp bean **JsonMapper** để serialize và deserialize dữ liệu. Trong ứng dụng Spring Boot 4, package của Jackson 3 bắt đầu bằng **tools.jackson**.

Ví dụ trong bài dùng Spring Boot 4 và Jackson 3. Ứng dụng Spring Boot 3 dùng Jackson 2 có package khác; không trộn **JsonMapper** của Jackson 3 với **ObjectMapper** của Jackson 2 trong cùng một đoạn code.

Nếu dự án chưa có JSON starter, thêm dependency được Spring Boot quản lý phiên bản:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

Tạo DTO chỉ chứa những field được công bố cho consumer:

~~~java
import java.math.BigDecimal;

public record OrderExportRow(
        String orderId,
        String customerName,
        BigDecimal total,
        String createdAt
) {
}
~~~

DTO xuất dữ liệu giúp tách schema công khai khỏi entity persistence. Nếu entity có thêm password hash, thông tin nội bộ hoặc quan hệ lazy-loaded, các field đó sẽ không tự động lọt vào payload.

Ví dụ command serialize danh sách DTO:

~~~java
import java.io.PrintWriter;
import java.time.LocalDate;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class OrderExportCommands {

    private static final Set<String> FORMATS = Set.of("json", "csv");

    private final OrderExportService orderExportService;
    private final JsonMapper jsonMapper;

    OrderExportCommands(
            OrderExportService orderExportService,
            JsonMapper jsonMapper) {
        this.orderExportService = orderExportService;
        this.jsonMapper = jsonMapper;
    }

    @Command(
            name = "orders-export",
            description = "Xuất đơn hàng dưới dạng JSON hoặc CSV."
    )
    public void export(
            @Option(longName = "from", required = true) LocalDate from,
            @Option(longName = "format", defaultValue = "json") String format,
            CommandContext context) throws JacksonException {

        String normalizedFormat = format.toLowerCase(Locale.ROOT);
        if (!FORMATS.contains(normalizedFormat)) {
            throw new IllegalArgumentException(
                    "Format chỉ nhận json hoặc csv."
            );
        }

        List<OrderExportRow> rows = orderExportService.exportFrom(from);
        PrintWriter out = context.outputWriter();

        if ("json".equals(normalizedFormat)) {
            out.println(jsonMapper.writeValueAsString(rows));
        }
        else {
            out.print(OrderCsvWriter.write(rows));
        }

        out.flush();
    }
}
~~~

Bean **JsonMapper** được inject từ Spring Boot. Command chỉ serialize DTO và ghi kết quả qua **outputWriter()**. Nó không ghi thêm lời giải thích hoặc bảng terminal vào cùng luồng.

Với dữ liệu mẫu, JSON có dạng:

~~~json
[
  {
    "orderId": "OD-1001",
    "customerName": "An, Bình",
    "total": 125000.50,
    "createdAt": "2026-11-26T08:15:00Z"
  },
  {
    "orderId": "OD-1002",
    "customerName": "Trần Minh",
    "total": 99000.00,
    "createdAt": "2026-11-26T08:20:00Z"
  }
]
~~~

JSON serializer tự xử lý dấu nháy, ký tự xuống dòng, Unicode và các ký tự đặc biệt trong string. Không ghép JSON bằng nối chuỗi thủ công; một dấu nháy hoặc dấu gạch chéo chưa escape có thể làm payload không hợp lệ.

### 3.1. Những quyết định cần giữ ổn định trong JSON

- **Tên field:** giữ nguyên tên qua các lần phát hành; nếu cần đổi tên, cân nhắc version schema hoặc cung cấp giai đoạn tương thích.
- **Kiểu dữ liệu:** không lúc trả **total** là number, lúc lại trả string. Với số tiền lớn, consumer JavaScript có thể mất độ chính xác khi dùng kiểu Number; cân nhắc biểu diễn dưới dạng chuỗi thập phân hoặc số nguyên theo đơn vị nhỏ nhất và ghi rõ hợp đồng.
- **Ngày giờ:** dùng ISO-8601 có offset hoặc UTC. Không phát ra ngày giờ local mà thiếu thông tin múi giờ nếu consumer cần xác định một thời điểm tuyệt đối.
- **Null và field vắng mặt:** **null** và không có key là hai trạng thái khác nhau. Chọn một quy tắc và kiểm thử cấu hình Jackson để không vô tình bỏ field.
- **Danh sách rỗng:** trả **[]** để giữ root structure nhất quán; không trả **null** chỉ vì không có record.
- **Thứ tự:** JSON object không nên được dùng như một giao kèo dựa vào thứ tự key. Nếu thứ tự record quan trọng, sắp xếp rõ ràng trong service.

Nếu cần thêm số lượng record hoặc schema version, dùng envelope có cấu trúc cố định thay vì thêm dòng chú thích trước/sau JSON.

## 4. Tạo CSV theo quy tắc rõ ràng

CSV là định dạng bảng, mỗi record có cùng số field. Theo RFC 4180, dấu phẩy phân tách field; record được ngăn bằng CRLF; field chứa dấu phẩy, dấu nháy kép hoặc xuống dòng cần được đặt trong dấu nháy kép; một dấu nháy kép bên trong field được biểu diễn bằng hai dấu nháy kép.

Một ví dụ CSV:

~~~csv
order_id,customer_name,total,created_at
OD-1001,"An, Bình",125000.50,2026-11-26T08:15:00Z
OD-1002,"Trần Minh",99000.00,2026-11-26T08:20:00Z
~~~

Ví dụ writer đơn giản cho schema đơn hàng:

~~~java
import java.util.List;

final class OrderCsvWriter {

    private OrderCsvWriter() {
    }

    static String write(List<OrderExportRow> rows) {
        StringBuilder csv = new StringBuilder();
        csv.append("order_id,customer_name,total,created_at\r\n");

        for (OrderExportRow row : rows) {
            csv.append(textCell(row.orderId())).append(',');
            csv.append(textCell(row.customerName())).append(',');
            csv.append(row.total() == null
                    ? ""
                    : row.total().toPlainString());
            csv.append(',');
            csv.append(textCell(row.createdAt()));
            csv.append("\r\n");
        }

        return csv.toString();
    }

    private static String textCell(String value) {
        if (value == null) {
            return "";
        }
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }
}
~~~

Writer đặt mọi field văn bản trong dấu nháy kép và nhân đôi dấu nháy kép bên trong. Cột số tiền được ghi bằng **BigDecimal.toPlainString()** để tránh ký hiệu khoa học và không phụ thuộc locale. Dòng kết thúc dùng CRLF theo quy ước RFC 4180.

Với dữ liệu:

~~~text
orderId = OD-1003
customerName = Công ty "Sao Mai", chi nhánh 2
total = 125000.50
createdAt = 2026-11-26T08:25:00Z
~~~

Field tên khách hàng được ghi:

~~~csv
"Công ty ""Sao Mai"", chi nhánh 2"
~~~

Các dấu phẩy và dấu nháy được giữ trong cùng một field. Không dùng **split(",")** để đọc CSV vì dấu phẩy có thể xuất hiện bên trong field đã được trích dẫn.

### 4.1. Null và chuỗi rỗng trong CSV

CSV không có một biểu diễn null thống nhất được mọi consumer hiểu giống nhau. Ví dụ writer ở trên ghi giá trị null thành field rỗng. Consumer sẽ không phân biệt chắc chắn null với chuỗi rỗng sau khi parse.

Nếu cần giữ hai trạng thái khác nhau, hãy định nghĩa null token riêng trong hợp đồng và quy định cách escape token đó, hoặc thêm field chỉ báo trạng thái. Khi cần biểu diễn null tự nhiên và dữ liệu lồng nhau, JSON thường phù hợp hơn CSV.

### 4.2. Header và thứ tự cột là một phần của hợp đồng

CSV không mang tên field trong từng record. Nếu header là:

~~~csv
order_id,customer_name,total,created_at
~~~

thì mọi dòng dữ liệu phải giữ đúng thứ tự bốn cột này. Không thay thứ tự dựa trên reflection của entity hoặc thứ tự cột tình cờ từ câu truy vấn. Consumer thường ánh xạ theo vị trí cột hoặc tên header.

Khi không có dữ liệu, vẫn nên xuất header:

~~~csv
order_id,customer_name,total,created_at
~~~

Điều này cho phép consumer nhận biết schema ngay cả khi kết quả rỗng.

## 5. Chọn JSON hay CSV

| Nhu cầu | JSON | CSV |
|---|---|---|
| Dữ liệu lồng nhau | Phù hợp | Không tự nhiên |
| Danh sách record cùng schema | Phù hợp | Rất phù hợp |
| Giữ kiểu boolean, number, null | Có cấu trúc rõ | Consumer cần biết schema ngoài |
| Mở bằng spreadsheet | Có thể cần bước nhập/chuyển đổi | Phù hợp hơn |
| Truyền qua API hoặc công cụ JSON | Phù hợp | Cần parser CSV riêng |
| Dữ liệu có nhiều field tùy chọn | Linh hoạt | Cần quy tắc cột cố định |

Không chọn CSV chỉ vì file nhỏ hơn hoặc nhìn dễ hơn. Nếu record có danh sách con, object lồng nhau hoặc nhiều kiểu dữ liệu phức tạp, JSON thường dễ giữ nguyên cấu trúc. CSV phù hợp khi dữ liệu có dạng bảng phẳng và người nhận cần các cột ổn định.

## 6. Gọi command từ script và pipeline

Sau khi command hỗ trợ format rõ ràng, script có thể chọn định dạng:

~~~text
./my-shell orders-export --from=2026-01-01 --format=json
./my-shell orders-export --from=2026-01-01 --format=csv
~~~

Có thể chuyển stdout vào file:

~~~text
./my-shell orders-export --from=2026-01-01 --format=json > orders.json
./my-shell orders-export --from=2026-01-01 --format=csv > orders.csv
~~~

Hoặc đưa JSON cho công cụ tiếp theo:

~~~text
./my-shell orders-export --from=2026-01-01 --format=json | jq '.[].orderId'
~~~

Đầu ra phải giữ stdout sạch. Không in banner khởi động, progress bar, màu ANSI, lời nhắc xác nhận hoặc thông báo "Đã xuất thành công" vào cùng luồng. Những thông tin chẩn đoán cần thiết nên được gửi qua logger hoặc stderr theo cấu hình triển khai.

Spring Shell khuyến nghị dùng **CommandContext.outputWriter()** thay cho **System.out** để ghi output của command. Hãy kiểm tra cả output thực tế của tiến trình khi chạy non-interactive và khi redirect; mục tiêu là file nhận được chỉ chứa JSON hoặc CSV hợp lệ.

Lỗi không nên được nối vào cuối JSON/CSV. Khi command thất bại, hãy để exception handling và exit status báo lỗi. Nếu pipeline cần stdout chỉ chứa payload, cấu hình launcher/result handling để diagnostic đi qua stderr riêng; không giả định mọi terminal hoặc runner tự tách hai luồng. Luôn kiểm tra stdout và stderr thực tế khi chạy non-interactive.

Encoding của stdout phụ thuộc cấu hình runtime và môi trường terminal. Nếu consumer yêu cầu UTF-8, hãy cấu hình launcher/môi trường chạy nhất quán và kiểm tra file sau khi redirect. Khi command tự ghi file, chỉ định charset rõ ràng bằng **StandardCharsets.UTF_8** thay vì dựa vào charset mặc định của máy.

## 7. CSV dùng cho spreadsheet có rủi ro riêng

Một CSV có thể được mở bằng Excel hoặc LibreOffice. Nếu field bắt đầu bằng ký tự như **=**, **+**, **-** hoặc **@**, một số spreadsheet có thể diễn giải nó như công thức thay vì văn bản. Đây là rủi ro thường được gọi là **CSV injection** hoặc **formula injection**.

Quy tắc quote của RFC 4180 chỉ bảo vệ cấu trúc field. Việc đặt giá trị trong dấu nháy kép không đảm bảo spreadsheet sẽ coi nó là text; spreadsheet có thể bỏ dấu nháy khi đọc field.

Vì vậy, hãy phân biệt:

- **CSV cho máy đọc:** ưu tiên bảo toàn nguyên giá trị và tuân thủ schema. Không tự thêm dấu nháy đơn hoặc tab vào dữ liệu vì điều đó làm thay đổi giá trị mà consumer nhận được.
- **CSV dành cho spreadsheet:** cần một chính sách riêng để trung hòa công thức, được kiểm thử với spreadsheet và quy trình thực tế. Một số biện pháp làm thay đổi dữ liệu hoặc không còn an toàn sau khi người dùng lưu rồi mở lại file.

Nếu cùng dữ liệu phục vụ cả pipeline và spreadsheet, hãy tạo hai chế độ export có hợp đồng riêng hoặc cân nhắc định dạng XLSX với kiểu cell được đặt tường minh. Không áp dụng một phép sửa chuỗi cho tất cả consumer.

## 8. Output lớn và hiệu năng

Ví dụ trước dùng List và StringBuilder nên giữ toàn bộ dữ liệu trong bộ nhớ. Cách này dễ hiểu và phù hợp với tập dữ liệu nhỏ hoặc vừa. Khi export hàng triệu record, bộ nhớ có thể tăng mạnh vì ứng dụng giữ đồng thời danh sách DTO và chuỗi output.

Với tập dữ liệu lớn:

1. Truy vấn theo page hoặc cursor có thứ tự xác định.
2. Ghi header CSV một lần, sau đó ghi từng record và flush theo lô phù hợp.
3. Với JSON, dùng Jackson streaming generator để mở array, ghi từng object, rồi đóng array.
4. Không gọi **toString()** trên toàn bộ entity hoặc serialize một graph lớn ngoài ý muốn.
5. Đóng resource của database đúng vòng đời; không giữ cursor sau khi command kết thúc.
6. Nếu ghi file trực tiếp, chọn charset UTF-8 và quản lý file bằng try-with-resources.

Khi streaming JSON, cần đảm bảo mọi nhánh lỗi vẫn đóng generator và output có cấu trúc rõ. Nếu tác vụ thất bại giữa chừng, consumer không được nhầm file JSON bị cắt cụt là kết quả hoàn chỉnh. Với export quan trọng, có thể ghi vào file tạm, hoàn tất và xác minh trước khi đổi tên thành file cuối.

## 9. Kiểm thử hợp đồng JSON và CSV

Kiểm thử command cần xác nhận nội dung, không chỉ xác nhận command chạy thành công.

| Ca kiểm thử | JSON | CSV |
|---|---|---|
| Có nhiều record | Mỗi object có đủ key và đúng kiểu | Mỗi record có đúng số cột |
| Không có record | Root là [] hoặc envelope rỗng theo hợp đồng | Chỉ có header |
| Field null | Kiểm tra quy tắc giữ null hoặc bỏ key | Kiểm tra null token hoặc field rỗng đã công bố |
| Unicode | Chuỗi được serialize và parse lại chính xác | UTF-8 và Unicode được giữ |
| Dấu phẩy trong text | String vẫn là một value | Field vẫn là một cột |
| Dấu nháy kép | JSON escape đúng | Dấu nháy được nhân đôi |
| CR/LF trong text | Được escape trong JSON string | Field được quote và parser đọc thành một field |
| Số thập phân | Không đổi kiểu hoặc mất độ chính xác ngoài hợp đồng | Dùng dấu chấm và không có phân cách hàng nghìn |
| Ngày giờ | ISO-8601 và timezone rõ ràng | Cùng định dạng đã công bố |
| Format không hỗ trợ | Báo lỗi và exit status khác thành công | Không ghi payload sai định dạng |

Với JSON, có thể parse output bằng cùng thư viện hoặc một parser độc lập để xác minh cấu trúc:

~~~java
import tools.jackson.databind.JsonNode;

JsonNode root = jsonMapper.readTree(jsonOutput);
assertThat(root.isArray()).isTrue();
assertThat(root.get(0).get("orderId").stringValue())
        .isEqualTo("OD-1001");
~~~

Với CSV, dùng một CSV parser trong test thay vì chỉ so sánh số dấu phẩy. Test cần có field chứa comma, quote và line break để phát hiện lỗi escaping.

Ngoài unit test cho serializer, hãy chạy command qua **ShellTestClient** hoặc tiến trình non-interactive để kiểm tra output writer, result handler và exit status. Kiểm tra stdout riêng với stderr; xác nhận stdout không có banner, log, prompt hoặc ANSI escape sequence.

Nếu CSV được mở trong spreadsheet, thêm kiểm thử formula injection với các giá trị do người dùng kiểm soát. Xác minh file sau khi export trong chính spreadsheet mà người dùng sẽ sử dụng; không suy luận an toàn chỉ từ việc field đã được quote.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JSON bắt đầu bằng tên class hoặc nội dung khó parse | Result handler mặc định gọi **toString()** trên object | Serialize bằng JsonMapper hoặc cung cấp ResultHandler có chủ đích |
| JSON không parse được | Ghép chuỗi thủ công hoặc có lời nhắn trước payload | Dùng JSON mapper và giữ stdout chỉ có payload |
| CSV lệch cột | Không quote field có comma hoặc quote | Dùng CSV writer tuân thủ quy tắc escaping |
| Dòng CSV bị tách sai | Field chứa CR/LF nhưng không được quote | Quote field chứa line break |
| Consumer đọc sai cột | Thứ tự header hoặc field thay đổi | Cố định schema và thứ tự cột |
| Số tiền đổi giá trị | Dùng NumberFormat theo locale hoặc double cho tiền | Dùng BigDecimal và định dạng thập phân theo hợp đồng |
| Ngày giờ lệch múi giờ | Xuất local time không có offset | Dùng ISO-8601 có timezone/UTC |
| Không phân biệt null với chuỗi rỗng trong CSV | CSV không có null marker chung | Công bố null token hoặc dùng JSON |
| Pipeline parse thất bại dù command thành công | Banner, log hoặc progress bị ghi vào stdout | Tách dữ liệu khỏi diagnostic |
| CSV chạy công thức khi mở spreadsheet | Field không tin cậy bắt đầu bằng ký tự công thức | Thiết kế chế độ spreadsheet-safe riêng và kiểm thử |
| Export lớn làm đầy heap | Giữ toàn bộ dữ liệu và output trong String/List | Dùng page/cursor và streaming writer |

## 11. Checklist thiết kế đầu ra máy đọc

Trước khi công bố command export, hãy xác nhận:

1. Có option format rõ ràng và chỉ chấp nhận các giá trị đã hỗ trợ.
2. DTO export chỉ chứa field công khai cần thiết.
3. JSON root, key, kiểu dữ liệu, null và date/time được định nghĩa.
4. CSV có header, thứ tự cột, quoting, delimiter, line ending và null policy cố định.
5. Decimal không phụ thuộc locale; ngày giờ có định dạng và timezone rõ.
6. Record có thứ tự xác định; kết quả rỗng có cấu trúc ổn định.
7. stdout chỉ chứa payload; diagnostic không trộn vào dữ liệu.
8. Encoding được thống nhất, ưu tiên UTF-8.
9. Consumer có thể parse output bằng parser chuẩn, không phải regex hoặc split đơn giản.
10. CSV cho spreadsheet có chính sách formula injection riêng.
11. Tập dữ liệu lớn có chiến lược paging hoặc streaming.
12. Schema được version hóa khi có thay đổi không tương thích.

Một đầu ra máy đọc tốt là một giao kèo dữ liệu có thể kiểm thử và duy trì. Khi command giữ schema ổn định, serialize đúng chuẩn và tách payload khỏi thông báo vận hành, cùng một chức năng có thể phục vụ terminal, script và pipeline mà consumer không cần phụ thuộc vào cách trình bày của con người.

## Tài liệu tham khảo

- [Spring Shell — Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html) — ghi output qua PrintWriter lấy từ CommandContext.
- [Spring Shell API — DefaultResultHandler](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/result/DefaultResultHandler.html) — result handler mặc định gọi toString() cho object không có handler chuyên biệt.
- [Spring Shell API — ResultHandlerService](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/ResultHandlerService.html) — cơ chế xử lý kết quả command và đăng ký handler.
- [Spring Boot — JSON](https://docs.spring.io/spring-boot/reference/features/json.html) — Jackson 3 là thư viện mặc định được ưu tiên; Spring Boot cấu hình JsonMapper khi Jackson có trên classpath.
- [Jackson 3 — ObjectMapper API](https://javadoc.io/doc/tools.jackson.core/jackson-databind/latest/tools.jackson.databind/tools/jackson/databind/ObjectMapper.html) — serialize object thành JSON string, byte array hoặc output stream.
- [RFC 4180 — Common Format and MIME Type for CSV Files](https://www.rfc-editor.org/rfc/rfc4180.html) — header, record, CRLF, quoting và escaping trong CSV.
- [OWASP — CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection) — rủi ro formula injection khi CSV được mở bằng spreadsheet.
- [OWASP Web Security Testing Guide — CSV Injection](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/21-Testing_for_CSV_Injection) — kiểm thử field, dấu phân cách và giá trị công thức trong CSV export.
