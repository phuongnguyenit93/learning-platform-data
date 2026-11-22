# Giới hạn kích thước tài liệu và độ sâu lồng

JSON là dữ liệu có cấu trúc, nhưng một tài liệu JSON hợp lệ vẫn có thể tiêu tốn quá nhiều bộ nhớ hoặc CPU. Một request có thể chứa object lồng hàng nghìn cấp, chuỗi rất dài, số có hàng triệu chữ số, hoặc array với số lượng phần tử khổng lồ. Nếu ứng dụng parse toàn bộ thành JsonNode hoặc DTO mà không giới hạn đầu vào, một client có thể làm tăng bộ nhớ, thời gian xử lý và số lượng object được tạo ra.

Jackson Core cung cấp **StreamReadConstraints** để giới hạn một số đặc điểm của input trong lúc parser đọc. Các giới hạn quan trọng gồm độ sâu lồng, độ dài chuỗi, độ dài số và, ở các phiên bản hỗ trợ, độ dài toàn tài liệu hoặc tên property. Đây là một lớp bảo vệ ở tầng parser. Ứng dụng vẫn cần giới hạn kích thước body ở transport, số phần tử ở tầng nghiệp vụ và lượng bộ nhớ mà mô hình dữ liệu có thể tiêu thụ.

Mục tiêu là đặt giới hạn dựa trên hợp đồng thật của API: đủ rộng cho payload hợp lệ lớn nhất, nhưng đủ thấp để một input bất thường không chiếm tài nguyên vô hạn.

## 1. Vì sao cần giới hạn JSON đầu vào?

Một JSON nhỏ về mặt ý nghĩa có thể tạo ra chi phí xử lý lớn. Ví dụ:

- Một object lồng sâu khiến parser phải theo dõi nhiều cấp cấu trúc.
- Một string rất dài tạo ra buffer và chuỗi Java lớn.
- Một number có hàng triệu chữ số khiến việc parse số và tạo BigInteger/BigDecimal tốn CPU, bộ nhớ.
- Một array chứa hàng triệu object tạo ra lượng lớn node hoặc DTO.
- Một object có hàng trăm nghìn property làm tăng số lần lookup, allocation và validation.
- Một body nén rất nhỏ có thể bung ra thành dữ liệu lớn nếu không giới hạn sau giải nén.

Một số payload minh họa:

**Độ sâu lồng bất thường**

~~~json
{"a":{"a":{"a":{"a":{"a":{"a":1}}}}}}
~~~

**Chuỗi rất dài**

~~~json
{
  "comment": "một chuỗi có thể dài hàng chục hoặc hàng trăm megabyte..."
}
~~~

**Số có token quá dài**

~~~json
{
  "value": 999999999999999999999999999999999999999999999999999999999999
}
~~~

**Array quá lớn**

~~~json
{
  "events": [
    {"id": 1},
    {"id": 2},
    {"id": 3}
  ]
}
~~~

Các ví dụ có thể hoàn toàn hợp lệ về cú pháp. Parser không thể tự biết một API chỉ cho phép tối đa 100 event hoặc comment không quá 10.000 ký tự nếu ứng dụng không đặt chính sách đó.

## 2. Các lớp giới hạn nên được kết hợp

Không có một giới hạn duy nhất bảo vệ mọi tài nguyên. Nên phân chia theo tầng:

~~~text
HTTP / message transport
  |
  +-- giới hạn body theo byte
  +-- giới hạn kích thước sau giải nén
  +-- timeout và giới hạn tốc độ
  |
  v
Jackson JsonFactory
  |
  +-- maxNestingDepth
  +-- maxStringLength
  +-- maxNumberLength
  +-- maxNameLength / maxDocumentLength (tùy phiên bản)
  |
  v
Databinding / custom deserializer
  |
  +-- số phần tử array
  +-- số property nếu hợp đồng cần
  +-- giới hạn collection / Map
  +-- kiểm tra kiểu và giá trị
  |
  v
Bean Validation / business layer
  |
  +-- độ dài field theo nghiệp vụ
  +-- số lượng item tối đa
  +-- kích thước metadata
  +-- giới hạn tổng hợp của request
~~~

Mỗi tầng có nhiệm vụ riêng:

- Transport giới hạn lượng byte được nhận trước khi parse.
- Parser giới hạn các token và cấu trúc cú pháp có nguy cơ gây chi phí cao.
- Databinding hoặc custom code giới hạn số phần tử và các quy tắc cấu trúc cụ thể.
- Validation kiểm tra dữ liệu theo nghiệp vụ sau khi đã ánh xạ.

Nếu chỉ đặt maxStringLength, một array có hàng triệu phần tử string ngắn vẫn có thể tiêu tốn rất nhiều bộ nhớ. Nếu chỉ giới hạn body theo byte, một payload nhỏ nhưng lồng sâu vẫn có thể gây vấn đề cho parser hoặc code xử lý phía sau.

## 3. StreamReadConstraints là gì?

StreamReadConstraints là cấu hình của Jackson Core áp dụng trong quá trình đọc token. Nó được gắn vào JsonFactory, là thành phần tạo JsonParser.

Các giới hạn thường được dùng:

| Giới hạn | Ý nghĩa |
|---|---|
| maxNestingDepth | Độ sâu lồng tối đa của object và array |
| maxStringLength | Độ dài tối đa của một JSON string |
| maxNumberLength | Độ dài tối đa của một token number |
| maxNameLength | Độ dài tối đa của tên property, nếu phiên bản hỗ trợ |
| maxDocumentLength | Độ dài tối đa của toàn bộ tài liệu, nếu phiên bản hỗ trợ |

StreamReadConstraints không phải giới hạn số byte HTTP trong mọi tình huống. Một string JSON có thể có số ký tự khác số byte UTF-8; một InputStream, Reader và parser từ nguồn khác có thể có đơn vị đo khác nhau. Muốn giới hạn byte request, hãy kiểm soát ở transport hoặc lớp đọc byte.

StreamReadConstraints được đưa vào Jackson Core từ dòng 2.15. Các thuộc tính và overload builder được bổ sung theo từng phiên bản. Đặc biệt, hãy kiểm tra API của đúng jackson-core đang dùng trước khi sử dụng maxNameLength hoặc maxDocumentLength; không phải mọi phiên bản 2.x đều có cùng tập phương thức.

## 4. Cấu hình độ sâu lồng bằng maxNestingDepth

maxNestingDepth giới hạn số cấp object/array được lồng nhau. Đây là bảo vệ quan trọng với payload có cấu trúc quá sâu.

Ví dụ cấu hình:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(100)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = JsonMapper.builder(factory).build();
~~~

Với cấu hình này, parser từ factory sẽ từ chối tài liệu có độ sâu lồng vượt quá giới hạn. Một JSON object hoặc array lồng quá sâu sẽ làm phát sinh StreamConstraintsException trong quá trình đọc.

Ví dụ:

~~~json
{
  "level1": {
    "level2": {
      "level3": {
        "level4": {
          "value": 1
        }
      }
    }
  }
}
~~~

Nếu giới hạn được đặt thấp hơn độ sâu thực tế, parser từ chối payload. Điều này xảy ra trước khi ứng dụng phải xây dựng toàn bộ cây hoặc DTO.

Không nên chọn 100 chỉ vì ví dụ dùng con số đó. Hãy đo độ sâu hợp lệ của payload thực tế, thêm biên an toàn và test cả trường hợp ở ngay giới hạn lẫn vượt giới hạn.

## 5. Hiểu độ sâu của object và array

Cả object và array đều góp phần tạo độ sâu lồng.

Ví dụ:

~~~json
{
  "orders": [
    {
      "items": [
        {
          "metadata": {
            "source": "web"
          }
        }
      ]
    }
  ]
}
~~~

Một chuỗi object xen kẽ array cũng làm tăng nesting depth. Không nên chỉ đếm số object trong DTO; hãy xem toàn bộ cấu trúc JSON mà parser đi qua.

Độ sâu không giống số lượng property. Một object có 10.000 property ở cùng cấp có thể có depth thấp nhưng vẫn lớn. Ngược lại, một nhánh có hàng trăm cấp có thể có ít property nhưng depth cao.

maxNestingDepth bảo vệ loại cấu trúc thứ hai. Để giới hạn object quá rộng, cần body limit, giới hạn token/property hoặc custom processing ở tầng ứng dụng.

## 6. Giới hạn độ dài chuỗi bằng maxStringLength

maxStringLength giới hạn số ký tự của một JSON string token mà parser chấp nhận.

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxStringLength(1_000_000)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();
~~~

Nếu API chỉ cần comment tối đa 20.000 ký tự, có thể đặt giới hạn parser lớn hơn mức nghiệp vụ một chút để bảo vệ parser, sau đó dùng Bean Validation kiểm tra chính xác từng field.

Ví dụ DTO:

~~~java
public record FeedbackRequest(
    @Size(max = 20_000)
    String comment
) {}
~~~

Hai giới hạn có mục đích khác nhau:

- maxStringLength bảo vệ parser khỏi một token string quá lớn ở bất kỳ vị trí nào.
- @Size(max = 20_000) thể hiện giới hạn nghiệp vụ cho property comment.

Không nên đặt maxStringLength bằng đúng giới hạn của một field nếu các field khác hợp lệ cần chuỗi dài hơn. Parser không phân biệt ý nghĩa của token string; nó áp dụng giới hạn cho mọi string token.

Nếu một string cần lớn hơn giới hạn parser vì lý do nghiệp vụ, hãy đánh giá lại thiết kế payload, dùng streaming hoặc truyền nội dung lớn qua một kênh/file riêng thay vì nới giới hạn toàn cục thiếu kiểm soát.

## 7. Giới hạn độ dài số bằng maxNumberLength

Một token number có thể có rất nhiều chữ số hoặc exponent dài. Việc parse token đó thành BigInteger, BigDecimal hoặc kiểu số khác có thể tiêu tốn CPU và bộ nhớ.

Có thể giới hạn độ dài number:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNumberLength(1_000)
    .build();
~~~

Ví dụ một số hợp lệ nhưng quá dài:

~~~json
{
  "accountingValue": 12345678901234567890123456789012345678901234567890
}
~~~

maxNumberLength kiểm soát độ dài token, không kiểm tra miền giá trị nghiệp vụ. Nếu amount chỉ được phép từ 0 đến 1.000.000, vẫn cần kiểm tra range sau khi parse.

Ví dụ:

~~~java
if (amount.signum() < 0
        || amount.compareTo(new BigDecimal("1000000")) > 0) {
    throw new IllegalArgumentException("amount is outside allowed range");
}
~~~

Nếu một field phải là số nguyên, hãy kiểm tra cả token type và range. Giới hạn độ dài token không thay thế kiểm tra VALUE_NUMBER_INT/VALUE_NUMBER_FLOAT hoặc kiểm tra số có thể chuyển sang int/long hay không.

## 8. Giới hạn tên property và toàn bộ document

Một JSON object có thể chứa tên property rất dài. Một tài liệu cũng có thể có tổng kích thước lớn dù từng string và number đều nằm dưới giới hạn riêng.

Các phiên bản Jackson Core mới có thêm cấu hình cho độ dài tên property và độ dài document:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(100)
    .maxStringLength(1_000_000)
    .maxNumberLength(1_000)
    .maxNameLength(256)
    .maxDocumentLength(10_000_000L)
    .build();
~~~

Ví dụ trên yêu cầu phiên bản jackson-core có các phương thức maxNameLength() và maxDocumentLength(). Nếu dự án dùng phiên bản cũ hơn, bỏ các lời gọi chưa được hỗ trợ và nâng cấp theo dependency management khi cần.

maxNameLength giới hạn một tên property. Nó không giới hạn số lượng property. maxDocumentLength giới hạn tổng độ dài parser nhìn thấy theo đơn vị mà API phiên bản đó quy định; không nên xem nó là thay thế hoàn toàn cho giới hạn byte của HTTP body.

Hãy kiểm tra Javadoc/release notes của đúng phiên bản Jackson để xác nhận:
- Phương thức builder có tồn tại không.
- Đơn vị đo document length áp dụng cho nguồn byte hay character.
- Loại parser nào áp dụng giới hạn đó.
- Exception nào được ném khi vượt giới hạn.

Nếu chưa có maxDocumentLength trong phiên bản đang dùng, giới hạn tổng body ở transport hoặc qua bounded stream.

## 9. Cấu hình đầy đủ cho JsonFactory và ObjectMapper

Có thể gom các giới hạn vào một factory dùng cho một nhóm endpoint:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(80)
    .maxStringLength(500_000)
    .maxNumberLength(500)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper apiMapper = JsonMapper.builder(factory)
    .build();
~~~

Mọi parser được tạo từ factory này sẽ áp dụng cùng chính sách đọc. ObjectMapper sử dụng factory nên các API như readValue(), readTree() và parser được tạo qua mapper cũng nhận giới hạn tương ứng.

Nếu cần các profile khác nhau, hãy tạo các factory/mapper riêng khi khởi tạo ứng dụng:

- Mapper cho request công khai với giới hạn chặt.
- Mapper cho import nội bộ có payload lớn hơn nhưng vẫn có giới hạn.
- Mapper cho message nhỏ có giới hạn thấp.
- Mapper cho fixture/test với cấu hình rõ ràng.

Không nên đổi constraints trên một factory/mapper đang được nhiều request sử dụng. Hãy hoàn tất cấu hình trước khi chia sẻ mapper giữa các thread.

## 10. Không nên nới giới hạn mặc định toàn cục tùy tiện

Jackson có các giới hạn mặc định và chúng có thể thay đổi theo phiên bản. Một số phiên bản cho phép override default StreamReadConstraints ở phạm vi static.

Cấu hình global có thể ảnh hưởng đến nhiều JsonFactory được tạo trong cùng process, kể cả những thư viện khác dùng Jackson. Điều đó khiến một thay đổi nhỏ ở một service làm thay đổi hành vi của parser ở nơi khác.

Ưu tiên cấu hình trên JsonFactory riêng:

~~~java
JsonFactory apiFactory = JsonFactory.builder()
    .streamReadConstraints(apiConstraints)
    .build();
~~~

Chỉ dùng global override khi ứng dụng thực sự cần một chính sách process-wide, hiểu rõ thứ tự khởi tạo và đã kiểm thử các mapper/thư viện cùng chạy trong process.

Không nên tắt hoặc đặt giới hạn rất cao chỉ để một payload bất thường vượt qua. Nếu có request hợp lệ vượt giới hạn, hãy xác định endpoint và loại dữ liệu cần hỗ trợ, rồi đặt policy riêng phù hợp.

## 11. Giới hạn byte của request ở tầng transport

StreamReadConstraints không thay thế giới hạn body theo byte. HTTP server, reverse proxy hoặc API gateway nên có giới hạn request body.

Các điểm cần nhớ:

- Content-Length có thể không có khi dùng chunked transfer.
- Không nên tin Content-Length từ client như bằng chứng duy nhất.
- Server/container phải đếm byte thực nhận.
- Với gzip hoặc content encoding khác, cần giới hạn cả kích thước nén và kích thước sau giải nén.
- Giới hạn upload cần được áp dụng trước khi buffer toàn bộ body vào bộ nhớ.

Ví dụ với body vừa phải, có thể đọc tối đa MAX_BYTES + 1 byte để phát hiện vượt giới hạn:

~~~java
private static final int MAX_BYTES = 2 * 1024 * 1024;

byte[] body = inputStream.readNBytes(MAX_BYTES + 1);

if (body.length > MAX_BYTES) {
    throw new PayloadTooLargeException("Request body exceeds 2 MiB");
}

JsonNode root = mapper.readTree(body);
~~~

Cách này phù hợp với payload nhỏ/vừa và có chủ đích giữ body trong bộ nhớ. Không dùng nó cho file lớn hoặc request streaming vì toàn bộ byte vẫn được giữ trong một mảng.

Với request lớn hoặc streaming, hãy cấu hình giới hạn ở server/container/gateway và dùng một InputStream có đếm byte hoặc bounded stream. Đảm bảo parser được đọc đến hết message hoặc transport đã xác nhận body hoàn tất; nếu parser dừng sau root đầu tiên, nó có thể chưa tiêu thụ hết byte của body.

## 12. Giới hạn sau giải nén để tránh decompression bomb

Một payload gzip có thể nhỏ khi truyền nhưng rất lớn sau giải nén. Nếu chỉ giới hạn số byte compressed, ứng dụng vẫn có thể nhận hàng trăm megabyte dữ liệu sau khi giải nén.

Cần áp dụng ít nhất hai giới hạn:

1. Kích thước byte trước giải nén để kiểm soát lưu lượng và tài nguyên mạng.
2. Kích thước byte sau giải nén để kiểm soát dữ liệu thực sự đưa vào parser.

Ngoài ra, cần timeout và giới hạn tốc độ giải nén phù hợp. Tầng nhận request nên cung cấp stream đã giải nén qua một bounded wrapper hoặc thư viện có hỗ trợ giới hạn số byte output.

Sau đó mới đưa stream vào JsonFactory/JsonParser. StreamReadConstraints tiếp tục bảo vệ nesting, string, number và các token khác.

Không nên chỉ kiểm tra kích thước file .gz hoặc Content-Length của request rồi tin rằng nội dung sau giải nén cũng nhỏ.

## 13. Giới hạn số phần tử array và số property

StreamReadConstraints cung cấp các giới hạn token/độ dài quan trọng, nhưng không nên giả định nó tự đặt giới hạn nghiệp vụ cho mọi array hoặc object.

Ví dụ:

~~~json
{
  "items": [
    {"id": 1},
    {"id": 2},
    {"id": 3}
  ]
}
~~~

Nếu API chỉ cho phép tối đa 500 item, hãy kiểm tra số phần tử ở tầng ứng dụng:

~~~java
JsonNode items = root.path("items");

if (!items.isArray()) {
    throw new IllegalArgumentException("items must be an array");
}

if (items.size() > 500) {
    throw new IllegalArgumentException("items cannot exceed 500 entries");
}
~~~

Với databinding vào List, có thể dùng Bean Validation:

~~~java
public record BatchRequest(
    @NotNull
    @Size(max = 500)
    List<@Valid ItemRequest> items
) {}
~~~

Tuy nhiên, Bean Validation chạy sau khi collection đã được tạo. Nếu cần ngăn allocation từ một array quá lớn, hãy dùng custom deserializer hoặc Streaming API để đếm và từ chối ngay khi vượt ngưỡng.

Tương tự, nếu object không được có quá 100 property, hãy đếm field trong custom deserializer hoặc streaming loop. Body size limit chỉ là giới hạn tổng quát, không thay thế quy tắc số lượng property.

## 14. Dùng Streaming API để kiểm soát collection lớn

Nếu payload chứa hàng triệu record và ứng dụng chỉ cần xử lý từng record, không nên đọc toàn bộ thành JsonNode hoặc List trước khi làm việc.

Ví dụ dùng JsonParser để đếm và xử lý từng item:

~~~java
try (JsonParser parser = factory.createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IOException("Expected an array");
    }

    int count = 0;

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (count >= MAX_ITEMS) {
            throw new IOException("Too many items");
        }

        ItemRequest item = mapper.readValue(parser, ItemRequest.class);
        process(item);
        count++;
    }
}
~~~

Ví dụ này giả định root là array và parser đang ở START_ARRAY. readValue(parser, ItemRequest.class) đọc một phần tử JSON hiện tại. Sau khi deserialize, parser được đặt ở cuối phần tử đó; vòng lặp gọi nextToken() để đến phần tử tiếp theo hoặc END_ARRAY.

Streaming giảm nhu cầu giữ toàn bộ array trong bộ nhớ, nhưng không tự giới hạn thời gian xử lý hoặc side effect. Nếu phần tử thứ 501 làm request thất bại, 500 phần tử trước có thể đã được process. Nếu yêu cầu all-or-nothing, hãy dùng transaction, staging hoặc xác nhận toàn bộ trước khi commit.

## 15. Độ sâu lồng và nguy cơ trong code ứng dụng

Giới hạn parser giúp từ chối cấu trúc quá sâu trước khi tạo toàn bộ object graph. Nhưng code ứng dụng cũng có thể tự đệ quy qua DTO hoặc JsonNode.

Ví dụ một hàm duyệt cây:

~~~java
void visit(JsonNode node) {
    if (node.isContainerNode()) {
        node.elements().forEachRemaining(this::visit);
    }
}
~~~

Nếu không có giới hạn depth, một cây rất sâu có thể gây stack overflow trong hàm đệ quy ngay cả khi parser đã hoàn tất.

Có thể dùng thuật toán iterative với stack tường minh hoặc giới hạn depth trong code duyệt:

~~~java
void visit(JsonNode root, int maxDepth) {
    Deque<NodeAtDepth> stack = new ArrayDeque<>();
    stack.push(new NodeAtDepth(root, 1));

    while (!stack.isEmpty()) {
        NodeAtDepth current = stack.pop();

        if (current.depth() > maxDepth) {
            throw new IllegalArgumentException("Tree is too deep");
        }

        JsonNode node = current.node();

        if (node.isContainerNode()) {
            node.elements().forEachRemaining(child ->
                stack.push(new NodeAtDepth(child, current.depth() + 1))
            );
        }
    }
}

record NodeAtDepth(JsonNode node, int depth) {}
~~~

Đây là lớp bảo vệ bổ sung cho các tree đã có sẵn, hoặc khi ứng dụng tạo node bằng code thay vì parse trực tiếp. Nếu parser đã có maxNestingDepth, vẫn nên tránh các hàm đệ quy không cần thiết ở những bước xử lý khác.

## 16. Tree Model có thể khuếch đại chi phí bộ nhớ

Một giới hạn body 2 MB không đồng nghĩa cây JsonNode chỉ chiếm 2 MB. Mỗi object, array, field name, node wrapper, collection entry và String Java đều có overhead.

Vì vậy, một JSON có nhiều field nhỏ có thể tạo ra lượng object trong heap lớn hơn đáng kể so với số byte đầu vào. Nếu nhiều request được parse đồng thời, tổng memory pressure tăng theo số request đang hoạt động.

Các biện pháp:

- Giới hạn body theo byte.
- Giới hạn depth và token length.
- Giới hạn số phần tử và số property.
- Dùng streaming khi không cần giữ toàn bộ tree.
- Giới hạn số request parse đồng thời.
- Dùng timeout và backpressure.
- Tránh tạo nhiều bản deepCopy() của payload lớn.
- Giải phóng tham chiếu đến JsonNode sau khi xử lý xong.

Nếu cần xử lý một phần dữ liệu, parse tree rồi chuyển từng subtree vẫn có thể giữ toàn bộ root trong bộ nhớ. Streaming trực tiếp thường phù hợp hơn khi payload rất lớn và không cần truy cập ngẫu nhiên.

## 17. Giới hạn trong custom deserializer

Custom deserializer có thể thực thi quota cụ thể mà annotation hoặc parser constraint không biểu diễn đủ.

Ví dụ một array chỉ được chứa tối đa 100 tag:

~~~java
List<String> readTags(JsonParser parser) throws IOException {
    if (parser.currentToken() != JsonToken.START_ARRAY) {
        throw JsonMappingException.from(parser, "tags must be an array");
    }

    List<String> tags = new ArrayList<>();

    JsonToken token;
    while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
        if (token == null) {
            throw JsonMappingException.from(parser, "Unexpected end of tags");
        }

        if (tags.size() >= 100) {
            throw JsonMappingException.from(
                parser,
                "tags cannot contain more than 100 entries"
            );
        }

        if (token != JsonToken.VALUE_STRING) {
            throw JsonMappingException.from(parser, "Every tag must be a string");
        }

        tags.add(parser.getText());
    }

    return tags;
}
~~~

Giới hạn được kiểm tra trước khi thêm phần tử tiếp theo vào List. Parser đã đọc token đầu tiên của phần tử vượt giới hạn, nhưng chưa cần tạo object Java cho phần tử đó.

Có thể áp dụng tương tự cho:
- Số entry của Map.
- Số field trong một object.
- Số phần tử trong nested array.
- Tổng số record trong một batch.
- Tổng số ký tự của một nhóm field nếu có quota riêng.

Nếu cần đếm toàn bộ token của document, có thể dùng parser wrapper hoặc streaming layer để đếm. Hãy tránh giới hạn chỉ theo số field ở root nếu payload có thể giấu hàng triệu field trong các object lồng nhau.

## 18. Giới hạn kích thước khi đọc file

Với file JSON, có thể kiểm tra kích thước trước khi parse:

~~~java
Path path = Path.of("input.json");
long maxBytes = 10L * 1024 * 1024;

long fileSize = Files.size(path);

if (fileSize > maxBytes) {
    throw new IOException("JSON file exceeds 10 MiB");
}

try (InputStream input = Files.newInputStream(path)) {
    JsonNode root = mapper.readTree(input);
}
~~~

Kiểm tra Files.size() hữu ích nhưng file có thể thay đổi giữa lúc kiểm tra và lúc đọc nếu một process khác đang ghi. Nếu file không được kiểm soát quyền sở hữu, hãy dùng cơ chế staging/atomic publish hoặc bounded stream khi đọc để giới hạn byte thực nhận.

Nếu file được upload, giới hạn cần được áp dụng ngay từ lúc nhận upload, không chờ đến khi file đã được lưu đầy đủ rồi mới kiểm tra.

Đối với import batch, có thể thêm manifest chứa kích thước, checksum và số record dự kiến. Những metadata này giúp xác nhận file hoàn chỉnh và phát hiện sai lệch ngoài cú pháp JSON.

## 19. Giới hạn theo endpoint thay vì một con số cho toàn ứng dụng

Các endpoint có profile payload khác nhau:

| Loại endpoint | Giới hạn thường cần quan tâm |
|---|---|
| Login hoặc command nhỏ | Body nhỏ, depth thấp, string ngắn |
| API CRUD thông thường | Body vừa, depth vừa, collection có giới hạn |
| Import batch | Body lớn hơn nhưng số record và thời gian xử lý phải được kiểm soát |
| Webhook | Body theo hợp đồng đối tác, depth/string có giới hạn |
| Metadata động | Giới hạn body, depth, string, số property |
| Upload file | Giới hạn file ở tầng upload; không nhất thiết parse file thành tree |
| Internal analytics | Có thể cần profile riêng nhưng vẫn có quota và backpressure |

Nếu một endpoint import cần payload 20 MB, không nên nới mọi endpoint public lên 20 MB. Tạo mapper/factory hoặc request pipeline riêng cho endpoint đó.

Trong Spring Boot hoặc framework tương tự, cần xác định mapper thực tế mà HTTP message converter dùng. Tạo một JsonFactory giới hạn nhưng không gắn nó vào converter không bảo vệ request.

## 20. Xử lý lỗi khi vượt giới hạn

Khi StreamReadConstraints bị vượt, Jackson thường ném StreamConstraintsException. Đây là lỗi đọc do parser từ chối cấu trúc hoặc token vượt policy.

Có thể bắt tại adapter:

~~~java
try {
    RequestDto request = mapper.readValue(inputStream, RequestDto.class);
    handle(request);
} catch (StreamConstraintsException exception) {
    throw new PayloadTooLargeOrComplexException(
        "JSON request exceeds allowed limits",
        exception
    );
}
~~~

Tên exception ứng dụng chỉ là ví dụ. Có thể phân loại theo giới hạn cụ thể nếu cần trả thông báo khác nhau, nhưng không nên lộ thông số nội bộ nhạy cảm hoặc stack trace cho client.

Ở HTTP API, body vượt giới hạn thường được ánh xạ thành 413 Payload Too Large nếu lỗi là kích thước body. Một cấu trúc quá sâu hoặc token quá dài có thể được trả 400 hoặc 413 tùy contract và framework. Hãy thống nhất error code giữa gateway, server và ứng dụng.

Nếu lỗi là IOException từ bounded stream, cần phân biệt nó với StreamConstraintsException. Một lỗi có thể đến từ giới hạn byte ở transport; lỗi còn lại đến từ parser constraints.

Không retry vô hạn một payload vượt giới hạn với cùng nội dung. Producer cần chia nhỏ request, giảm dữ liệu hoặc dùng endpoint import/stream phù hợp.

## 21. Kiểm thử các giới hạn ở ranh giới

Test nên kiểm tra cả trường hợp hợp lệ ở ngưỡng và trường hợp vượt ngưỡng. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.core.exc.StreamConstraintsException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class JsonReadLimitsTest {

    @Test
    void rejectsExcessiveNestingDepth() {
        StreamReadConstraints constraints =
            StreamReadConstraints.builder()
                .maxNestingDepth(3)
                .build();

        JsonFactory factory = JsonFactory.builder()
            .streamReadConstraints(constraints)
            .build();

        ObjectMapper mapper = new ObjectMapper(factory);

        String json = "[[[[0]]]]";

        assertThrows(
            StreamConstraintsException.class,
            () -> mapper.readTree(json)
        );
    }

    @Test
    void rejectsStringLongerThanConfiguredLimit() {
        StreamReadConstraints constraints =
            StreamReadConstraints.builder()
                .maxStringLength(5)
                .build();

        JsonFactory factory = JsonFactory.builder()
            .streamReadConstraints(constraints)
            .build();

        ObjectMapper mapper = new ObjectMapper(factory);

        assertThrows(
            StreamConstraintsException.class,
            () -> mapper.readTree("{\"value\":\"123456\"}")
        );
    }

    @Test
    void acceptsStringAtConfiguredLimit() {
        StreamReadConstraints constraints =
            StreamReadConstraints.builder()
                .maxStringLength(5)
                .build();

        JsonFactory factory = JsonFactory.builder()
            .streamReadConstraints(constraints)
            .build();

        ObjectMapper mapper = new ObjectMapper(factory);

        assertDoesNotThrow(
            () -> mapper.readTree("{\"value\":\"12345\"}")
        );
    }
}
~~~

Test này giả định phiên bản Jackson có StreamReadConstraints và StreamConstraintsException tương ứng. Nếu dùng phiên bản cũ hơn, cần nâng cấp hoặc kiểm tra giới hạn bằng wrapper/logic ứng dụng phù hợp.

Bổ sung test cho:
- Number dài hơn maxNumberLength.
- Tên property dài hơn maxNameLength nếu phiên bản hỗ trợ.
- Document dài hơn maxDocumentLength nếu phiên bản hỗ trợ.
- Body byte vượt giới hạn transport.
- Array vượt số phần tử nghiệp vụ.
- Payload nén bung ra vượt giới hạn sau giải nén.
- Input đúng ngay tại ranh giới được cho phép.

Đừng chỉ test một JSON rất lớn; hãy xác nhận từng loại constraint đang được áp dụng bởi đúng JsonFactory mà production sử dụng.

## 22. Chọn giới hạn dựa trên dữ liệu thật

Không có một bộ số tối ưu cho mọi hệ thống. Hãy dựa trên:

- Payload hợp lệ lớn nhất hiện tại.
- Dự kiến tăng trưởng schema.
- Số request đồng thời.
- Heap và CPU của service.
- Thời gian parse/validation cho payload lớn.
- Kích thước sau giải nén.
- Số phần tử và độ sâu thực tế.
- Khả năng chia batch hoặc streaming.

Một profile minh họa cho API CRUD có thể là:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(64)
    .maxStringLength(256_000)
    .maxNumberLength(256)
    .build();
~~~

Đây chỉ là điểm khởi đầu minh họa, không phải giá trị khuyến nghị chung. Nếu ứng dụng cần document lớn, hãy đo hiệu năng và chọn profile riêng.

Có thể thu thập histogram về body size, số phần tử, độ sâu hoặc string length trong môi trường test/staging. Khi thu thập ở production, tránh lưu nội dung nhạy cảm; chỉ ghi các số liệu tổng hợp cần thiết.

Đặt cảnh báo khi payload tiến gần ngưỡng để có thể điều chỉnh hợp đồng trước khi client bị từ chối đột ngột.

## 23. Những giới hạn không nên nhầm lẫn

| Cơ chế | Giới hạn gì | Không thay thế |
|---|---|---|
| Content-Length/body-size limit | Byte của request body | Nesting, field length, business count |
| StreamReadConstraints.maxNestingDepth | Độ sâu object/array | Số property hoặc array element |
| maxStringLength | Một string token | Độ dài nghiệp vụ riêng của từng field |
| maxNumberLength | Một number token | Range/precision nghiệp vụ |
| maxNameLength | Một field name | Tổng số field |
| maxDocumentLength | Độ dài tài liệu theo API/phiên bản | Mọi giới hạn byte sau giải nén |
| @Size trên collection | Số phần tử sau khi binding | Ngăn allocation trước khi binding |
| Custom streaming count | Số record/phần tử trong khi đọc | Body limit và timeout |
| Timeout/rate limit | Thời gian và tốc độ xử lý | Cấu trúc JSON quá sâu hoặc quá lớn |

Bảo vệ tốt cần nhiều lớp. Một request có thể không vượt bất kỳ giới hạn nào riêng lẻ nhưng vẫn gây áp lực khi hàng trăm request như vậy đến đồng thời. Vì vậy, cần kết hợp quota theo request với concurrency, rate limit và backpressure.

## 24. Quy trình triển khai an toàn

Khi đưa giới hạn vào một API hoặc pipeline import:

1. Xác định kích thước body tối đa ở tầng gateway/server.
2. Nếu có nén, giới hạn cả compressed và decompressed bytes.
3. Tạo JsonFactory với StreamReadConstraints phù hợp phiên bản.
4. Đặt maxNestingDepth, maxStringLength và maxNumberLength theo schema.
5. Dùng maxNameLength/maxDocumentLength nếu phiên bản hỗ trợ và nhu cầu rõ ràng.
6. Giới hạn số phần tử, số property và số record ở tầng streaming/deserializer.
7. Chỉ dùng tree model khi cần giữ toàn bộ payload trong bộ nhớ.
8. Dùng timeout, concurrency limit và backpressure.
9. Ánh xạ lỗi vượt giới hạn thành response/message error phù hợp.
10. Test ngay tại ngưỡng và vượt ngưỡng bằng mapper production.
11. Theo dõi số lần bị từ chối và điều chỉnh dựa trên payload hợp lệ thực tế.

## Kết luận

Giới hạn kích thước và độ sâu JSON là một phần của bảo mật đầu vào. StreamReadConstraints giúp Jackson từ chối cấu trúc lồng quá sâu, string hoặc number quá dài và một số giới hạn tên/document ở các phiên bản hỗ trợ. Tuy nhiên, parser constraints không thay thế giới hạn byte của transport, giới hạn số phần tử của ứng dụng hay timeout và concurrency control.

Hãy cấu hình JsonFactory riêng cho từng profile, đặt giới hạn theo payload hợp lệ lớn nhất, kiểm tra số phần tử trong khi streaming nếu cần và tránh parse toàn bộ tài liệu lớn thành tree khi không cần thiết. Kết hợp body limit, parser constraints, validation, backpressure và test tại ranh giới để giảm nguy cơ request JSON hợp lệ về cú pháp nhưng tiêu tốn tài nguyên quá mức.

