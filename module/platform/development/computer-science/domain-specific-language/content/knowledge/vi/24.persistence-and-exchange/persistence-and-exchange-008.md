# Nhập và xuất

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL) thường được dùng để mô tả cấu hình, quy trình, quy tắc hoặc mô hình nghiệp vụ. Dữ liệu trong DSL có thể được nạp từ tệp, chuyển đổi từ hệ thống khác, lưu vào kho dữ liệu, xuất thành JSON/YAML hoặc sinh thành cấu hình cho một nền tảng đích. **Nhập và xuất (import and export)** là hai nhóm thao tác đưa dữ liệu vào mô hình DSL và đưa mô hình đó ra các định dạng hoặc hệ thống khác.

Nhập dữ liệu cần chuyển đổi nội dung bên ngoài thành mô hình miền có cấu trúc, kiểm tra kiểu và quy tắc nghiệp vụ, xử lý tham chiếu và báo lỗi có thể khắc phục. Xuất dữ liệu cần chuyển mô hình thành định dạng đích, bảo toàn thông tin theo hợp đồng, tạo đầu ra ổn định và ghi dữ liệu an toàn. Hai chiều có liên quan nhưng không phải lúc nào cũng đảo ngược hoàn toàn: định dạng đích có thể không biểu diễn được mọi khả năng của DSL, hoặc import phải áp dụng giá trị mặc định và chuẩn hóa dữ liệu.

Một thiết kế nhập/xuất tốt cần trả lời rõ dữ liệu đến từ đâu, định dạng nào được hỗ trợ, schema phiên bản nào được áp dụng, dữ liệu không hợp lệ được xử lý ra sao, trường chưa biết có được giữ lại không và kết quả được lưu hoặc gửi đi như thế nào. Những quy tắc đó giúp DSL trao đổi dữ liệu với công cụ khác mà không làm mất ý nghĩa miền hoặc tạo trạng thái không nhất quán.

## 1. Nhập và xuất trong vòng đời DSL

Trong pipeline điển hình, nhập dữ liệu bắt đầu từ nguồn bên ngoài, đi qua bước giải mã và phân tích, rồi trở thành mô hình đã kiểm chứng. Xuất dữ liệu đi theo hướng ngược lại: lấy mô hình đã được xác nhận, chuyển thành cấu trúc định dạng đích và ghi ra đích lưu trữ.

~~~mermaid
flowchart TD
    A[External file or system] --> B[Decode and parse]
    B --> C[Import representation]
    C --> D[Map to domain model]
    D --> E[Validate and resolve references]
    E --> F[Accepted model]
    F --> G[Export mapping]
    G --> H[Encode target format]
    H --> I[File or external system]
~~~

Các bước nhập thường gồm:

1. Xác định nguồn và định dạng.
2. Đọc byte hoặc luồng dữ liệu.
3. Giải mã ký tự theo encoding được hỗ trợ.
4. Parse dữ liệu thành cấu trúc trung gian.
5. Ánh xạ trường và giá trị sang mô hình miền.
6. Áp dụng default hoặc migration nếu được phép.
7. Phân giải tham chiếu và kiểm chứng ràng buộc.
8. Trả mô hình cùng diagnostics hoặc lưu vào kho đích.

Các bước xuất thường gồm:

1. Lấy mô hình đã kiểm chứng.
2. Chọn schema và định dạng đích.
3. Chuyển mô hình thành cấu trúc tuần tự hóa.
4. Chuẩn hóa thứ tự, literal và cách biểu diễn giá trị.
5. Mã hóa thành byte hoặc ghi qua writer.
6. Hoàn tất tệp hoặc giao dịch tại hệ thống đích.
7. Trả kết quả, metadata và lỗi nếu có.

Không phải mọi ứng dụng cần tất cả các bước. Một DSL nhỏ có thể đọc trực tiếp JSON và tạo model; một nền tảng lớn có thể có adapter riêng cho từng nguồn và đích. Dù kiến trúc đơn giản hay phức tạp, ranh giới giữa đọc dữ liệu, chuyển đổi và kiểm chứng nên được xác định rõ.

## 2. Phân biệt import/export với parse/serialize

Các thuật ngữ có liên quan nhưng mang ý nghĩa khác nhau:

- **Parsing:** chuyển văn bản theo grammar thành CST hoặc AST.
- **Serialization:** chuyển một đối tượng hoặc mô hình thành biểu diễn có thể lưu hoặc truyền đi.
- **Import:** đưa dữ liệu từ một nguồn vào mô hình hoặc hệ thống hiện tại; thường bao gồm parse, mapping, migration và validation.
- **Export:** lấy dữ liệu từ mô hình hiện tại và tạo biểu diễn cho một định dạng hoặc hệ thống đích; thường bao gồm chọn schema, mapping và encoding.

Ví dụ, parser có thể đọc cú pháp DSL thành AST nhưng chưa biết customerId có tồn tại trong hệ thống hay không. Import đầy đủ cần ánh xạ tham chiếu và kiểm tra quy tắc miền. Tương tự, serializer có thể tạo JSON từ một object, nhưng export nghiệp vụ còn cần quyết định trường nào được phép công khai, phiên bản schema nào dùng và có cần loại bỏ dữ liệu nội bộ hay không.

## 3. Các nguồn dữ liệu có thể nhập

Một DSL có thể nhận dữ liệu từ nhiều nguồn:

- Tệp DSL do người dùng viết.
- JSON, YAML, XML, TOML hoặc CSV.
- Cơ sở dữ liệu hoặc kho cấu hình.
- REST API, message queue hoặc event stream.
- Công cụ mô hình hóa trực quan.
- Tệp được sinh từ template hoặc hệ thống khác.
- Phiên bản cũ của chính DSL.

Mỗi nguồn có đặc điểm khác nhau. Tệp DSL có grammar và vị trí lỗi rõ ràng; JSON/YAML có cấu trúc dữ liệu tổng quát; CSV thường là bảng phẳng và thiếu kiểu miền; API có thể phân trang hoặc trả dữ liệu theo từng đợt; cơ sở dữ liệu có thể chứa khóa ngoại và transaction riêng.

Không nên giả định mọi nguồn có cùng ngữ nghĩa. Ví dụ, một ô CSV rỗng có thể có nghĩa là chuỗi rỗng, giá trị bị thiếu hoặc không áp dụng. Một trường JSON không xuất hiện cũng khác với trường có giá trị null. Import adapter cần quy định cách ánh xạ từng trường hợp.

## 4. Các định dạng xuất phổ biến

Định dạng đích nên được chọn theo mục đích trao đổi và đặc tính dữ liệu.

| Định dạng | Phù hợp với | Điểm cần chú ý |
|---|---|---|
| DSL text | Con người chỉnh sửa và quản lý bằng Git | Cần grammar và quy tắc phiên bản |
| JSON | API, ứng dụng và cấu trúc lồng nhau | Không có comment trong chuẩn JSON cơ bản; kiểu ngày giờ cần quy ước |
| YAML | Cấu hình có thể đọc bằng mắt | Có nhiều tính năng cú pháp; cần giới hạn schema và parser an toàn |
| XML | Hệ thống tích hợp và schema phong phú | Namespace, schema validation và bảo mật parser |
| TOML | Cấu hình ứng dụng tương đối đơn giản | Mô hình dữ liệu có giới hạn hơn JSON/YAML |
| CSV | Trao đổi bảng và phân tích dữ liệu | Không biểu diễn tự nhiên quan hệ lồng nhau hoặc kiểu phức tạp |
| Binary format | Truyền dữ liệu gọn và hiệu quả | Khó đọc trực tiếp; cần schema và quản lý tương thích |

Một dự án có thể hỗ trợ nhiều định dạng nhưng nên có mô hình miền chuẩn làm điểm hội tụ. Nếu mỗi định dạng có logic nghiệp vụ riêng, quy tắc sẽ bị lặp và dễ không nhất quán.

## 5. Tách adapter định dạng khỏi mô hình miền

Một kiến trúc dễ bảo trì thường có adapter riêng cho mỗi định dạng. Adapter chịu trách nhiệm đọc hoặc ghi cú pháp của định dạng, còn mapping layer chuyển cấu trúc dữ liệu sang mô hình miền.

~~~mermaid
flowchart TD
    A[DSL text] --> P[DSL adapter]
    B[JSON] --> J[JSON adapter]
    C[YAML] --> Y[YAML adapter]
    D[CSV] --> C2[CSV adapter]
    P --> M[Canonical import model]
    J --> M
    Y --> M
    C2 --> M
    M --> V[Domain validation]
    V --> Dm[Domain model]
    Dm --> X[Export mapping]
    X --> O1[DSL]
    X --> O2[JSON]
    X --> O3[YAML]
    X --> O4[CSV]
~~~

Lợi ích của cách tách này:

- Mỗi adapter có thể được kiểm thử độc lập.
- Quy tắc miền được dùng chung cho mọi nguồn.
- Có thể thêm định dạng mới mà không sửa toàn bộ domain model.
- Lỗi cú pháp được tách khỏi lỗi ánh xạ và lỗi nghiệp vụ.
- Các định dạng có thể dùng cùng một schema nội bộ.

Một interface khái niệm trong Java:

~~~java
interface ImportAdapter<S> {
    ImportResult importData(S source, ImportContext context);
}

interface ExportAdapter<T> {
    ExportResult<T> exportData(DomainModel model, ExportContext context);
}
~~~

S có thể là InputStream, Path, một cây JSON hoặc response API. T có thể là byte[], String, OutputStream hoặc một cấu trúc request. Trong hệ thống thực tế, nên định nghĩa rõ quyền sở hữu và đóng stream, encoding, lỗi I/O và giới hạn kích thước.

## 6. Mô hình trung gian khi nhập dữ liệu

Dữ liệu bên ngoài thường không khớp trực tiếp với domain model. Có thể dùng một import DTO hoặc canonical import model làm cấu trúc trung gian.

Ví dụ JSON từ hệ thống bán hàng:

~~~json
{
  "order_code": "O-1042",
  "buyer": "C-22",
  "items": [
    { "sku": "BOOK-1", "qty": 2, "unit_price": "12.50" }
  ],
  "state": "paid"
}
~~~

Mô hình nội bộ có thể dùng các kiểu miền:

~~~java
record OrderImportDto(
    String orderCode,
    String buyerCode,
    List<ItemImportDto> items,
    String state
) {}

record ItemImportDto(
    String sku,
    int quantity,
    String unitPrice
) {}
~~~

Sau khi parse JSON, mapping layer có thể chuyển DTO thành Order, CustomerId, Quantity, Money và OrderStatus. Bước này có thể cần phân giải buyerCode thành khách hàng thực sự và kiểm tra SKU có tồn tại hay không.

DTO giúp tránh để tên trường và cấu trúc của một hệ thống ngoài lan vào domain model. Nếu API ngoài đổi buyer thành customer_ref, chỉ adapter hoặc mapping cần cập nhật nếu mô hình nghiệp vụ không đổi.

## 7. Ánh xạ trường và quy tắc dữ liệu

Mapping định nghĩa cách trường nguồn tương ứng với thuộc tính đích. Một bảng mapping nên mô tả:

- Tên trường nguồn và tên trường đích.
- Kiểu dữ liệu nguồn và kiểu đích.
- Trường bắt buộc hay tùy chọn.
- Giá trị mặc định nếu thiếu.
- Quy tắc chuyển đổi hoặc chuẩn hóa.
- Cách xử lý giá trị không hợp lệ.
- Có giữ trường chưa biết hay không.

Ví dụ:

| Trường nguồn | Trường mô hình | Quy tắc |
|---|---|---|
| order_code | OrderId | Chuẩn hóa và kiểm tra định dạng ID |
| buyer | CustomerId | Phân giải khách hàng |
| qty | Quantity | Số nguyên dương |
| unit_price | Money.amount | Đọc decimal chính xác |
| state | OrderStatus | Ánh xạ tên trạng thái theo bảng quy đổi |

Không nên dùng ép kiểu ngầm tùy tiện. Ví dụ, nếu nguồn gửi chuỗi 12.50, mapping cần parse decimal theo locale và quy tắc rõ. Không nên dùng double rồi làm tròn tùy tiện nếu dữ liệu là tiền tệ.

## 8. Giá trị thiếu, null và giá trị mặc định

Một trong những vấn đề khó nhất khi import là phân biệt các trạng thái dữ liệu:

- Trường không xuất hiện.
- Trường xuất hiện với null.
- Trường xuất hiện với chuỗi rỗng.
- Trường có giá trị mặc định.
- Trường không áp dụng.
- Trường không biết vì nguồn không cung cấp.

Ví dụ JSON rỗng khác với trường enabled có giá trị null và khác với enabled bằng false.

Nếu importer ánh xạ cả ba trường hợp thành false, nó có thể làm mất ý định của nguồn. Một import DTO có thể dùng trạng thái riêng như Missing, NullValue và Present(value) nếu nghiệp vụ cần phân biệt.

Giá trị mặc định cần được áp dụng ở một bước có chủ đích. Có thể áp dụng default khi tạo mô hình mới từ nguồn thiếu trường, migration tài liệu cũ sang schema mới hoặc chuẩn hóa cấu hình trước validation.

Nên ghi nhận trường nào được suy ra để diagnostics hoặc export có thể giải thích. Nếu default thay đổi giữa các phiên bản, dữ liệu thiếu trường có thể được hiểu khác, vì vậy versioning rất quan trọng.

## 9. Kiểu dữ liệu và chuyển đổi an toàn

Importer cần chuyển đổi dữ liệu theo hợp đồng kiểu của DSL.

| Dữ liệu nguồn | Kiểu miền đích | Điều cần kiểm tra |
|---|---|---|
| Số nguyên JSON | Integer hoặc Quantity | Giới hạn và miền giá trị |
| Chuỗi decimal | BigDecimal hoặc Money | Locale, scale và độ chính xác |
| Chuỗi ngày | LocalDate | Format và ngày hợp lệ |
| Chuỗi timestamp | Instant hoặc OffsetDateTime | Offset, timezone và độ chính xác |
| Chuỗi mã | CustomerId | Định dạng và tham chiếu tồn tại |
| Chuỗi trạng thái | Enum | Có giá trị được hỗ trợ hay không |
| Mảng | List hoặc Set | Kiểu phần tử, thứ tự và phần tử trùng |

Các chuyển đổi nên được phân loại:

- **Chuyển đổi an toàn:** không mất thông tin theo hợp đồng, ví dụ số nguyên nhỏ sang kiểu số rộng hơn.
- **Chuyển đổi có điều kiện:** cần kiểm tra range hoặc định dạng.
- **Chuyển đổi có mất mát:** có thể làm tròn, cắt bớt hoặc bỏ thông tin; cần cảnh báo hoặc từ chối.
- **Không hỗ trợ:** không có cách biểu diễn tương ứng trong mô hình đích.

Với tiền tệ, nên dùng BigDecimal hoặc kiểu decimal chính xác, đồng thời giữ mã tiền tệ. Với thời gian, cần quyết định giữ instant, offset hay timezone vùng. Với số đo, cần lưu đơn vị hoặc chuẩn hóa theo một quy ước rõ ràng.

## 10. Import từ CSV

CSV phù hợp với dữ liệu dạng bảng như danh sách người dùng, sản phẩm hoặc bản ghi đơn giản. Tuy nhiên, CSV không có kiểu dữ liệu và cấu trúc quan hệ chuẩn như JSON. Mỗi trường thường được đọc ban đầu dưới dạng chuỗi.

Ví dụ:

~~~csv
sku,name,quantity,unit_price
BOOK-1,Domain Modeling,2,12.50
PEN-3,Blue Pen,10,1.20
~~~

Importer cần xác định:

- Header có bắt buộc không.
- Tên cột có phân biệt chữ hoa/chữ thường không.
- Dấu phân cách là comma, semicolon hay tab.
- Quy tắc quote và escape.
- Encoding và BOM.
- Cách xử lý dòng thiếu hoặc thừa cột.
- Cách xử lý dấu phân cách trong giá trị được quote.
- Quy tắc locale cho decimal và ngày.

CSV có thể chứa newline trong trường được quote. Không nên tách file bằng split newline và tách cột bằng split comma nếu muốn hỗ trợ CSV đúng chuẩn. Nên dùng thư viện CSV đã được kiểm chứng hoặc parser tuân theo dialect được công bố.

### 10.1. Xử lý dòng lỗi

Một import lớn có thể có một số dòng sai. Hệ thống cần chọn một trong các chính sách:

- Từ chối toàn bộ file nếu có bất kỳ dòng lỗi nào.
- Bỏ qua dòng lỗi và nhập các dòng hợp lệ.
- Nhập vào vùng staging, cho người dùng review rồi commit.
- Cho phép một số lỗi ở mức warning nhưng từ chối lỗi ảnh hưởng toàn vẹn.

Kết quả cần ghi rõ số dòng đọc, số dòng hợp lệ, số dòng bị từ chối và diagnostics theo số dòng/cột.

## 11. Import từ JSON và YAML

JSON và YAML thường phù hợp với cấu trúc lồng nhau và API. JSON có cú pháp tương đối hạn chế; YAML hỗ trợ alias, anchor, tag và nhiều cách viết rút gọn tùy phiên bản. Vì vậy, importer cần xác định profile hoặc subset được hỗ trợ.

Ví dụ YAML:

~~~yaml
application: shop
services:
  - name: catalog
    replicas: 3
  - name: checkout
    replicas: 2
    depends_on:
      - catalog
~~~

Sau khi parse, cấu trúc có thể được ánh xạ thành Application và danh sách Service. Các tham chiếu depends_on cần được phân giải sau khi đã thu thập các service.

Nên giới hạn tính năng YAML nếu DSL không cần chúng. Ví dụ, alias đệ quy hoặc custom tags có thể làm việc kiểm tra và bảo mật phức tạp hơn. Không nên coi mọi cấu trúc YAML đều tự động tương thích với domain model.

### 11.1. Trường chưa biết

Khi schema mới có trường mà importer cũ không biết, có thể:

- Từ chối để tránh hiểu sai.
- Bỏ qua và cảnh báo.
- Giữ lại dưới dạng extension/unknown fields để export lại.

Chính sách cần phụ thuộc vào mục đích. Với API command, strict mode thường an toàn hơn. Với công cụ chỉnh sửa tài liệu có thể cần bảo toàn trường chưa biết để không làm mất dữ liệu khi lưu lại.

## 12. Import từ XML

XML có thể biểu diễn cấu trúc lồng nhau, namespace, attribute và nội dung văn bản. Khi import XML, cần xác định schema, namespace và cách ánh xạ element/attribute sang model.

Ví dụ:

~~~xml
<service name="catalog">
    <replicas>3</replicas>
    <dependsOn>database</dependsOn>
</service>
~~~

Một adapter có thể ánh xạ service/@name thành tên service, replicas thành số nguyên và dependsOn thành tham chiếu. Nếu dùng XSD, có thể thực hiện schema validation trước hoặc trong khi mapping.

XML parser cần được cấu hình an toàn. Không bật external entities hoặc DTD resolution nếu không cần thiết, vì cấu hình không an toàn có thể tạo lỗ hổng XXE, đọc file cục bộ hoặc truy vấn tài nguyên mạng. Cần giới hạn kích thước, độ sâu và số node khi xử lý tài liệu không tin cậy.

## 13. Xuất mô hình thành DSL

Export sang DSL thường dùng pretty printer hoặc serializer theo grammar. Cần quyết định:

- Thứ tự khai báo và thuộc tính.
- Cách biểu diễn literal và escape chuỗi.
- Cách ghi giá trị mặc định.
- Cách biểu diễn enum, đơn vị và thời gian.
- Cách biểu diễn tham chiếu: tên, qualified name hay ID.
- Cách định dạng danh sách và khối lồng nhau.
- Cách giữ hoặc tạo comment/metadata.

Ví dụ mô hình:

~~~text
Application(name = "shop")
  Service(name = "catalog", replicas = 3)
  Service(name = "checkout", replicas = 2, dependsOn = [catalog])
~~~

Có thể export thành:

~~~text
application "shop" {
    service "catalog" {
        replicas = 3
    }

    service "checkout" {
        replicas = 2
        depends_on = ["catalog"]
    }
}
~~~

Serializer phải bảo đảm kết quả tuân theo grammar và giữ ý nghĩa mô hình. Nếu mô hình chứa trạng thái không thể biểu diễn bằng DSL, export cần báo lỗi hoặc yêu cầu một extension format đã được định nghĩa.

## 14. Xuất JSON/YAML và lựa chọn schema

Khi export sang JSON hoặc YAML, cần có schema đích rõ ràng. Không nên serialize trực tiếp mọi trường nội bộ của domain object vì có thể làm lộ cache, ID nội bộ, tham chiếu vòng hoặc dữ liệu nhạy cảm.

Một DTO xuất riêng có thể giúp kiểm soát:

~~~java
record ServiceExportDto(
    String name,
    int replicas,
    List<String> dependsOn
) {}
~~~

Mapping từ model sang DTO quyết định trường nào được công khai. Sau đó serializer JSON/YAML chỉ xử lý cấu trúc DTO.

Các quyết định quan trọng:

- Tên trường dùng camelCase, snake_case hay quy ước khác.
- Trường mặc định có được ghi không.
- Giá trị null có được ghi hay bị bỏ qua.
- Enum xuất bằng tên, mã ổn định hay giá trị số.
- Ngày giờ dùng ISO 8601 hay định dạng riêng.
- Số decimal giữ scale hay chuẩn hóa.
- Collection có thứ tự ổn định không.
- Trường extension được ghi ở đâu.

Schema xuất nên được version hóa nếu có consumer bên ngoài. Thay đổi tên trường hoặc kiểu dữ liệu có thể phá vỡ consumer ngay cả khi domain model nội bộ vẫn tương thích.

## 15. Xuất CSV và giới hạn cấu trúc

Khi xuất mô hình lồng nhau thành CSV, cần quyết định cách làm phẳng (flatten) dữ liệu. Ví dụ application có nhiều service và mỗi service có nhiều dependency. Có thể xuất một dòng cho mỗi service, lặp tên application; hoặc tạo một tệp riêng cho service và một tệp cho dependency.

Một cách biểu diễn:

~~~csv
application,service,replicas,dependency
shop,catalog,3,
shop,checkout,2,catalog
~~~

Cần quy định header và thứ tự cột, escape dấu phẩy, dấu quote và newline, cách biểu diễn danh sách trong một ô, giá trị null và chuỗi rỗng, encoding và newline, cùng việc có xuất ID nội bộ hay chỉ tên hiển thị.

CSV không thể biểu diễn mọi quan hệ một cách tự nhiên. Nếu cần giữ cấu trúc phong phú, JSON, YAML hoặc DSL text có thể phù hợp hơn. Không nên làm phẳng dữ liệu mà không tài liệu hóa cách khôi phục.

## 16. Phiên bản schema và migration khi nhập

Định dạng dữ liệu trao đổi thường tồn tại lâu hơn một phiên bản ứng dụng. Schema có thể thay đổi:

- Thêm trường mới.
- Đổi tên hoặc tách trường.
- Thay đổi kiểu dữ liệu.
- Thay đổi giá trị enum.
- Thay đổi quan hệ hoặc cardinality.
- Bỏ một tính năng cũ.

Một tài liệu có thể chứa metadata phiên bản:

~~~json
{
  "schemaVersion": 2,
  "application": "shop",
  "services": []
}
~~~

Khi import, hệ thống đọc schemaVersion rồi chọn parser, mapping hoặc migration tương ứng. Không nên đoán phiên bản chỉ từ việc một trường có tồn tại hay không nếu các phiên bản có thể chồng lấn.

Một pipeline migration:

~~~mermaid
flowchart LR
    A[Input schema v1] --> B[Parse v1]
    B --> C[Migration v1 to v2]
    C --> D[Canonical model v2]
    D --> E[Validate]
~~~

Migration nên là bước tường minh, có thể kiểm thử và ghi nhận. Nếu thay đổi mất thông tin, importer cần cảnh báo hoặc từ chối tùy chính sách. Với dữ liệu quan trọng, giữ bản nguồn hoặc backup trước khi migration.

## 17. Tương thích ngược và tương thích tiến

Hai khái niệm thường gặp:

- **Backward compatibility:** phiên bản mới có thể đọc dữ liệu được tạo bởi phiên bản cũ.
- **Forward compatibility:** phiên bản cũ có thể xử lý dữ liệu được tạo bởi phiên bản mới ở mức đã cam kết, chẳng hạn giữ trường chưa biết hoặc bỏ qua extension an toàn.

Không phải định dạng nào cũng có thể đạt cả hai. Nếu phiên bản mới thêm một trường bắt buộc mà phiên bản cũ không hiểu, forward compatibility có thể không thực hiện được.

Một số chiến lược:

- Đặt giá trị mặc định cho trường mới.
- Giữ unknown fields khi cần bảo toàn.
- Dùng namespace extension cho tính năng mới.
- Tách schema API công khai khỏi domain model nội bộ.
- Cung cấp migration có phiên bản.
- Dùng capability negotiation khi hai hệ thống trao đổi trực tiếp.
- Từ chối rõ ràng khi phiên bản không được hỗ trợ.

Không nên âm thầm bỏ trường mới nếu trường đó ảnh hưởng đến hành vi nghiệp vụ. Bỏ qua chỉ an toàn khi hợp đồng xác nhận trường đó không ảnh hưởng consumer cũ.

## 18. Import dữ liệu lớn và streaming

Đọc toàn bộ tệp vào bộ nhớ đơn giản nhưng có thể không phù hợp với dữ liệu lớn. Một tệp CSV hàng triệu dòng hoặc JSON rất lớn có thể gây áp lực bộ nhớ nếu parser tạo toàn bộ cây rồi mới xử lý.

Streaming import xử lý dữ liệu từng phần:

~~~mermaid
flowchart LR
    A[Input stream] --> B[Streaming parser]
    B --> C[Record mapper]
    C --> D[Validate record]
    D --> E[Batch or transaction]
    E --> F[Destination]
~~~

Các lợi ích:

- Giảm bộ nhớ đỉnh.
- Có thể bắt đầu xử lý trước khi đọc hết nguồn.
- Phù hợp với CSV hoặc định dạng record-oriented.
- Có thể áp dụng batch và backpressure khi nguồn là stream.

Đổi lại, streaming làm việc kiểm tra quan hệ toàn cục phức tạp hơn. Ví dụ, một record có thể tham chiếu đến đối tượng xuất hiện ở cuối tệp. Có thể dùng staging table, index tạm, hai lượt đọc hoặc trì hoãn reference validation đến khi tất cả record đã được nạp.

Không phải mọi định dạng đều hỗ trợ streaming dễ dàng. JSON lồng sâu có thể dùng streaming parser, nhưng mapping vẫn cần giữ trạng thái cha-con. Với XML, SAX hoặc StAX có thể xử lý theo sự kiện; DOM thường giữ toàn bộ cây trong bộ nhớ.

## 19. Import theo batch và transaction

Khi nhập nhiều bản ghi vào cơ sở dữ liệu hoặc dịch vụ, cần quyết định ranh giới transaction.

Các chính sách phổ biến:

- **All-or-nothing:** nếu một bản ghi lỗi, rollback toàn bộ lô.
- **Per-record:** mỗi bản ghi là một transaction riêng.
- **Batch transaction:** chia dữ liệu thành các lô nhỏ; mỗi lô commit độc lập.
- **Staging then promote:** nhập vào vùng tạm, kiểm chứng toàn bộ, rồi chuyển sang dữ liệu chính thức.

All-or-nothing giữ tính nhất quán mạnh nhưng có thể tốn tài nguyên cho lô lớn. Per-record dễ tiếp tục khi một dòng lỗi nhưng có thể tạo tập dữ liệu chỉ nhập được một phần. Staging phù hợp khi cần review trước khi công bố.

Kết quả import nên báo số bản ghi đọc, hợp lệ, đã commit, bị từ chối và còn chờ xử lý. Nếu quá trình bị gián đoạn, cần biết có thể chạy lại an toàn hay không.

## 20. Import lặp lại và xử lý bản ghi trùng

Một nguồn có thể được nhập nhiều lần do retry, đồng bộ định kỳ hoặc người dùng chạy lại lệnh. Nếu mỗi lần import đều tạo bản ghi mới, dữ liệu sẽ bị trùng.

Cần xác định khóa nhận diện (identity key) cho từng loại đối tượng, ví dụ OrderId, mã khách hàng hoặc tổ hợp tenant và externalId. Chính sách khi gặp bản ghi đã tồn tại có thể là:

- **Insert-only:** bỏ qua hoặc báo lỗi nếu ID đã tồn tại.
- **Upsert:** tạo mới nếu chưa có, cập nhật nếu đã có.
- **Replace:** thay thế toàn bộ bản ghi theo nguồn mới.
- **Merge:** chỉ cập nhật các trường nguồn sở hữu, giữ trường nội bộ khác.
- **Reject conflict:** từ chối nếu dữ liệu hiện tại và dữ liệu import khác nhau.

Upsert không tự động an toàn. Cần xác định trường nào được phép cập nhật, cách xử lý version và xung đột với chỉnh sửa của người dùng. Nếu có thể, dùng external ID ổn định và revision/version của nguồn để phát hiện dữ liệu cũ.

## 21. Xuất dữ liệu nhất quán

Export trong khi mô hình đang được sửa có thể tạo ra một tệp chứa dữ liệu từ nhiều revision khác nhau. Để tránh snapshot không nhất quán, nên xuất từ một snapshot hoặc transaction nhất quán.

Các lựa chọn:

- Đọc mô hình trong một database transaction với isolation phù hợp.
- Tạo immutable snapshot trước khi serialize.
- Gắn revision ID hoặc timestamp logic vào export.
- Nếu dữ liệu phân trang từ API, dùng cursor/snapshot token để các trang thuộc cùng một phiên bản dữ liệu.

Một export lớn có thể được stream ra tệp tạm, sau đó đổi tên khi hoàn tất. Nếu lỗi xảy ra giữa chừng, không nên để tệp đích có vẻ như một bản export hoàn chỉnh nhưng chỉ chứa một phần dữ liệu.

## 22. Ghi tệp xuất an toàn

Khi export ra tệp, nên ghi vào tệp tạm rồi thay thế đích sau khi hoàn tất. Cách này giảm nguy cơ tệp cũ bị ghi đè một phần khi tiến trình thất bại.

Ví dụ Java giản lược:

~~~java
static void exportAtomically(Path target, byte[] bytes) throws IOException {
    Path parent = target.toAbsolutePath().getParent();
    Files.createDirectories(parent);
    Path temp = Files.createTempFile(parent, ".export-", ".tmp");
    boolean moved = false;
    try {
        Files.write(temp, bytes);
        Files.move(
            temp,
            target,
            StandardCopyOption.REPLACE_EXISTING,
            StandardCopyOption.ATOMIC_MOVE
        );
        moved = true;
    } finally {
        if (!moved) {
            Files.deleteIfExists(temp);
        }
    }
}
~~~

Đây là ví dụ cho một tệp và filesystem hỗ trợ atomic move. Nếu môi trường không hỗ trợ, cần quyết định fallback hoặc báo lỗi. Với export nhiều tệp, có thể ghi vào thư mục staging và công bố manifest hoặc thư mục phiên bản sau khi tất cả tệp đã hoàn tất.

## 23. Encoding, BOM và newline

Nhập/xuất văn bản cần quy định encoding. UTF-8 thường là lựa chọn phù hợp cho DSL đa ngôn ngữ, nhưng importer cần xử lý rõ:

- Tệp có BOM hoặc không có BOM.
- Encoding được khai báo hay phải cấu hình.
- Byte sequence không hợp lệ.
- Newline LF, CRLF hoặc CR.
- Chuẩn hóa Unicode nếu định danh cần quy tắc so sánh thống nhất.

Không nên tự đoán encoding một cách âm thầm nếu dữ liệu quan trọng. Nếu encoding không được hỗ trợ, báo lỗi rõ và chỉ ra nguồn. Với export, dùng encoding cố định hoặc ghi metadata phù hợp để consumer biết cách giải mã.

Newline cũng có thể ảnh hưởng đến diff và source location. Nếu export phục vụ Git, nên chuẩn hóa newline theo quy ước dự án. Nếu cần bảo toàn văn bản gốc, giữ newline trong metadata hoặc dùng chế độ không chuẩn hóa.

## 24. Bảo mật khi nhập dữ liệu

Import xử lý dữ liệu có thể không đáng tin cậy. Cần kiểm soát kích thước, cấu trúc và hành vi của parser.

Các rủi ro thường gặp:

- Tệp quá lớn làm cạn bộ nhớ.
- Cấu trúc lồng quá sâu gây tràn stack.
- JSON/YAML/XML chứa cấu trúc bất thường làm tăng chi phí xử lý.
- XML external entity hoặc DTD truy cập tài nguyên ngoài ý muốn.
- Tên tệp hoặc đường dẫn chứa dấu chấm chấm gây path traversal khi giải nén hoặc lưu attachment.
- Chuỗi được import chứa script hoặc biểu thức được thực thi không an toàn.
- CSV formula injection khi xuất dữ liệu được mở bằng spreadsheet.
- Secret hoặc dữ liệu cá nhân bị đưa vào log và diagnostics.
- Import tham chiếu tài nguyên ngoài phạm vi tenant/project.

Biện pháp kiểm soát:

- Giới hạn kích thước tệp, số record, độ sâu và số trường.
- Dùng parser an toàn, tắt tính năng ngoài nhu cầu.
- Không thực thi nội dung DSL trong giai đoạn import.
- Kiểm tra đường dẫn sau chuẩn hóa và xử lý symlink.
- Phân quyền nguồn và đích theo danh tính thực thi.
- Redact dữ liệu nhạy cảm khỏi log.
- Với CSV, xử lý các giá trị bắt đầu bằng dấu bằng, cộng, trừ hoặc @ theo chính sách chống formula injection khi export cho spreadsheet.
- Kiểm tra quyền và giới hạn tài nguyên ở runtime, không chỉ dựa vào validation tĩnh.

## 25. Lỗi import/export và diagnostics

Lỗi cần được phân loại để người dùng biết nên sửa dữ liệu, cấu hình hay hệ thống.

| Nhóm lỗi | Ví dụ | Thông tin nên trả |
|---|---|---|
| I/O | Không đọc được tệp | Đường dẫn, thao tác và nguyên nhân hệ thống |
| Encoding | Byte không hợp lệ | Encoding mong đợi và offset |
| Syntax | JSON/YAML/DSL sai cú pháp | Dòng, cột và token/construct liên quan |
| Mapping | Không tìm thấy trường bắt buộc | Tên trường nguồn và trường đích |
| Conversion | Chuỗi không phải số hợp lệ | Giá trị, kiểu đích và vị trí record |
| Reference | ID khách hàng không tồn tại | Khóa tham chiếu và nguồn khai báo |
| Validation | Số lượng âm | Quy tắc miền và đối tượng liên quan |
| Compatibility | Schema version không hỗ trợ | Phiên bản hiện tại và phiên bản được hỗ trợ |
| Conflict | Bản ghi đã thay đổi từ revision khác | ID, revision và lựa chọn xử lý |
| Export | Mô hình không biểu diễn được trong format đích | Trường hoặc tính năng không hỗ trợ |

Một kết quả import có thể có cấu trúc:

~~~java
record ImportResult<T>(
    T value,
    List<Diagnostic> diagnostics,
    int recordsRead,
    int recordsAccepted,
    int recordsRejected
) {}
~~~

value có thể là mô hình hoàn chỉnh, mô hình staging hoặc vắng mặt tùy policy. Không nên trả mô hình một phần mà không đánh dấu rõ trạng thái, vì caller có thể vô tình sử dụng nó như dữ liệu hợp lệ.

## 26. Chế độ strict, lenient và preview

Importer có thể hỗ trợ nhiều chế độ:

- **Strict:** từ chối ngay khi có trường không biết, kiểu sai hoặc vi phạm ràng buộc quan trọng.
- **Lenient:** bỏ qua hoặc chuyển đổi một số trường không quan trọng, đồng thời phát warning.
- **Preview/dry-run:** đọc, mapping và validation để hiển thị kết quả dự kiến nhưng không commit dữ liệu.
- **Partial:** chấp nhận bản ghi hợp lệ và báo riêng bản ghi bị từ chối nếu nghiệp vụ cho phép.

Không nên để lenient có nghĩa là “bỏ qua mọi lỗi”. Mỗi loại lỗi cần có chính sách cụ thể. Ví dụ, trường mô tả không biết có thể được giữ như extension; tham chiếu khách hàng không tồn tại có thể phải từ chối vì làm sai quan hệ miền.

Preview hữu ích cho dữ liệu lớn hoặc migration. Người dùng có thể xem số lượng record, cảnh báo, xung đột và thay đổi trước khi commit. Preview cần gắn với revision nguồn để khi dữ liệu thay đổi, kết quả cũ không được áp dụng nhầm.

## 27. API nhập/xuất có kiểu và có thể kiểm soát

Một API tốt nên thể hiện định dạng, context và kết quả lỗi một cách tường minh.

~~~java
record ImportOptions(
    boolean strict,
    boolean preserveUnknownFields,
    String targetSchemaVersion
) {}

record ExportOptions(
    String format,
    String schemaVersion,
    boolean includeDefaults
) {}

interface ModelExchangeService {
    ImportResult<DomainModel> importFrom(
        InputStream input,
        ImportOptions options
    );

    ExportResult<byte[]> exportTo(
        DomainModel model,
        ExportOptions options
    );
}
~~~

Đây là API khái niệm. Một implementation thực tế cần xác định ai đóng InputStream hoặc OutputStream, charset và media type, giới hạn kích thước và timeout, cancellation và backpressure, cách trả diagnostics và partial result, cách ghi transaction hoặc commit, cùng version và format được hỗ trợ.

Tránh API chỉ nhận Object hoặc Map<String, Object> cho mọi dữ liệu nếu có thể định nghĩa DTO/schema rõ. Kiểu rõ ràng giúp phát hiện lỗi sớm và giảm ép kiểu không an toàn.

## 28. CLI cho thao tác nhập và xuất

Một công cụ DSL có thể cung cấp lệnh CLI tường minh:

~~~text
dsl import orders.json --format json --schema v2 --dry-run

dsl import products.csv --format csv --mapping product-import.yml

dsl export application.dsl --format yaml --output application.yaml

dsl export application.dsl --format json --schema v3 --check
~~~

CLI nên trả exit code có ý nghĩa:

- 0: thao tác hoàn tất theo policy.
- Mã khác 0: lỗi cú pháp, mapping, validation, I/O hoặc conflict.
- Có thể dùng mã riêng cho partial import nếu pipeline cần phân biệt.

Thông báo cần nêu số record và đường dẫn đầu ra, nhưng không in dữ liệu nhạy cảm. dry-run không được commit thay đổi. check nên xác nhận đầu ra hiện tại có khớp với kết quả dự kiến mà không ghi lại dữ liệu.

## 29. Kiểm thử import và export

Kiểm thử nên bao gồm adapter, mapping, validation và thao tác I/O.

### 29.1. Kiểm thử định dạng

Dùng fixture cho JSON, YAML, XML, CSV và DSL; xác nhận parser đọc đúng cấu trúc, encoding và trường hợp newline/escape.

### 29.2. Kiểm thử mapping

Xác nhận tên trường, kiểu, default, enum, đơn vị, tham chiếu và unknown fields được ánh xạ theo hợp đồng.

### 29.3. Kiểm thử dữ liệu không hợp lệ

Bao gồm trường thiếu, null, giá trị sai kiểu, decimal ngoài range, tham chiếu không tồn tại, schema version không hỗ trợ và cấu trúc quá sâu.

### 29.4. Kiểm thử export

Xác nhận định dạng đầu ra hợp lệ, thứ tự ổn định, encoding đúng, trường nhạy cảm bị loại bỏ và các trường bắt buộc được ghi.

### 29.5. Kiểm thử tích hợp

Import dữ liệu vào mô hình, kiểm chứng, export sang định dạng đích rồi đọc lại nếu hợp đồng yêu cầu. So sánh theo semantic equality hoặc tiêu chí bảo toàn đã công bố.

### 29.6. Kiểm thử streaming và lỗi giữa chừng

Mô phỏng stream bị ngắt, đích ghi đầy, transaction thất bại hoặc process bị hủy. Xác nhận không công bố một tệp export dở dang như kết quả hoàn chỉnh.

### 29.7. Kiểm thử bảo mật

Dùng tệp quá lớn, cấu trúc lồng sâu, XML có external entity, đường dẫn traversal, symlink và CSV formula. Xác nhận giới hạn và chính sách được thực thi.

## 30. Quy trình thiết kế một luồng nhập/xuất

Có thể triển khai theo các bước:

1. **Xác định use case:** nhập để tạo mới, cập nhật, đồng bộ hay migration; xuất để đọc, triển khai hay trao đổi.
2. **Chọn format và schema:** công bố định dạng, version, encoding và giới hạn.
3. **Xác định mapping:** tên trường, kiểu, default, enum, reference và unknown fields.
4. **Tạo DTO hoặc canonical model:** tách cấu trúc ngoài khỏi domain model.
5. **Parse và chuyển đổi:** xử lý cú pháp, encoding và kiểu dữ liệu.
6. **Phân giải tham chiếu:** liên kết ID và quan hệ giữa đối tượng.
7. **Validation:** kiểm tra bất biến, uniqueness và chính sách miền.
8. **Chọn transaction policy:** all-or-nothing, batch, per-record hoặc staging.
9. **Xuất từ snapshot:** tránh tạo output từ nhiều revision khác nhau.
10. **Ghi an toàn:** dùng staging/atomic replace khi phù hợp.
11. **Báo cáo diagnostics:** nêu lỗi theo tệp, dòng, cột hoặc record.
12. **Kiểm thử tương thích:** giữ fixture theo từng phiên bản schema và consumer.

## 31. Nguyên tắc thiết kế

- **Có schema và version rõ ràng:** consumer cần biết dữ liệu được biểu diễn theo hợp đồng nào.
- **Tách adapter khỏi domain model:** tránh để định dạng ngoài chi phối logic nghiệp vụ.
- **Không ép kiểu tùy tiện:** chuyển đổi phải có quy tắc, range và xử lý mất mát.
- **Phân biệt missing, null và default:** tránh làm thay đổi ý nghĩa dữ liệu.
- **Quản lý unknown fields có chủ đích:** strict, preserve hoặc drop theo policy.
- **Phân giải tham chiếu sau khi thu thập dữ liệu cần thiết:** tránh phụ thuộc thứ tự record nếu không có yêu cầu.
- **Kiểm chứng trước khi commit:** dữ liệu không hợp lệ không nên trở thành mô hình chính thức.
- **Chọn transaction theo use case:** báo rõ partial import và khả năng retry.
- **Xuất từ snapshot nhất quán:** tránh trộn nhiều revision.
- **Ghi tệp an toàn:** không công bố output một phần như bản hoàn chỉnh.
- **Bảo vệ parser và hệ thống tệp:** giới hạn tài nguyên, kiểm tra đường dẫn và cấu hình parser an toàn.
- **Giữ diagnostics hữu ích:** phân biệt I/O, syntax, mapping, conversion, reference và validation errors.
- **Kiểm thử phiên bản và trường hợp biên:** bảo đảm consumer cũ/mới được hỗ trợ theo hợp đồng.

Nhập và xuất là cầu nối giữa mô hình DSL với tệp, API và hệ thống lưu trữ bên ngoài. Khi định dạng và schema được công bố rõ; adapter được tách khỏi domain model; mapping, kiểu dữ liệu, giá trị thiếu và tham chiếu được xử lý tường minh; cùng với transaction, streaming, bảo mật và diagnostics phù hợp, dữ liệu có thể đi qua các hệ thống mà vẫn giữ được ý nghĩa và tính nhất quán cần thiết.
