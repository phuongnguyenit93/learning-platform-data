# Kiểm tra đầu vào và ngăn injection trong function

Function serverless thường nhận dữ liệu từ HTTP request, message queue, event bus, webhook, object storage hoặc một function khác. Dù nguồn dữ liệu nằm trong cùng cloud account hay được gửi qua một gateway đã xác thực, nội dung vẫn có thể sai định dạng, lỗi thời, bị giả mạo hoặc được tạo có chủ đích để làm thay đổi câu lệnh mà function thực thi.

**Input validation** kiểm tra dữ liệu có đúng cấu trúc, giới hạn và quy tắc nghiệp vụ hay không. **Injection prevention** bảo đảm dữ liệu không tin cậy được xử lý như dữ liệu, không bị diễn giải thành câu lệnh SQL, biểu thức truy vấn, lệnh hệ điều hành, đường dẫn, template hoặc nội dung thực thi. Hai việc liên quan nhưng không thay thế nhau: một chuỗi có thể hợp lệ theo schema nhưng vẫn nguy hiểm nếu được ghép trực tiếp vào câu SQL hoặc lệnh shell.

Trong Java serverless, mỗi trigger là một ranh giới tiếp nhận dữ liệu. API Gateway có thể giới hạn kích thước request hoặc xác thực token, nhưng function vẫn cần kiểm tra hợp đồng đầu vào và quyền trên tài nguyên cụ thể. Message từ queue cũng cần được validate vì producer có thể có bug, event cũ có thể được replay và payload có thể đã thay đổi schema. Mục tiêu là làm cho mọi dữ liệu đi vào logic nghiệp vụ có kiểu rõ ràng, giới hạn rõ ràng và được dùng an toàn trong từng ngữ cảnh.

## 1. Xác định ranh giới tin cậy và nguồn dữ liệu

Bắt đầu bằng cách liệt kê mọi nguồn dữ liệu đi vào function. Không nên chỉ xem HTTP body là input không tin cậy; dữ liệu có thể đến từ path parameter, query string, header, cookie, file upload, event metadata, message body, object key hoặc kết quả của dịch vụ bên ngoài.

| Nguồn | Ví dụ | Rủi ro cần kiểm tra |
|---|---|---|
| HTTP path/query | orderId, limit, sort, filter | IDOR, injection, giá trị quá lớn, biểu thức filter tùy ý |
| HTTP body | JSON tạo đơn hàng | Sai schema, field thừa, kiểu dữ liệu bất thường, dữ liệu vượt giới hạn |
| HTTP header/cookie | Authorization, forwarded headers, custom header | Header giả mạo, CRLF injection, token sai audience |
| Message queue | OrderCreated event | Duplicate, schema cũ, tenant không khớp, payload độc hại |
| Event bus | ObjectCreated hoặc domain event | Event giả mạo, nguồn không mong đợi, replay |
| Webhook | Thanh toán hoặc hệ thống đối tác | Chữ ký sai, phát lại, payload không đúng schema |
| Object storage | File upload, object key | File độc hại, path traversal, ZIP Slip, nội dung không đúng loại |
| Dịch vụ bên ngoài | URL, tên file, dữ liệu API | SSRF, response quá lớn, dữ liệu không đáng tin |

Một ranh giới tin cậy xuất hiện khi dữ liệu đi từ người dùng, tenant, tài khoản, tổ chức hoặc hệ thống có chính sách bảo mật khác sang function. Đánh dấu rõ nơi xác thực danh tính, nơi kiểm tra quyền và nơi validate nội dung.

Đặc biệt, **xác thực nguồn gửi không chứng minh payload hợp lệ**. Một message được publish bởi IAM principal hợp lệ vẫn có thể chứa orderId không tồn tại, tenantId sai hoặc một giá trị được tạo từ input độc hại. Tương tự, JWT hợp lệ chỉ chứng minh danh tính và các claim được xác minh; function vẫn phải kiểm tra người dùng được phép thao tác trên resource nào.

## 2. Ba lớp kiểm tra: cú pháp, ngữ nghĩa và quyền

Một input an toàn cần vượt qua nhiều lớp kiểm tra:

1. **Cú pháp và cấu trúc:** JSON parse được, field đúng kiểu, enum hợp lệ, path parameter đúng định dạng.
2. **Giới hạn và ngữ nghĩa:** chuỗi không quá dài, số nằm trong miền hợp lệ, danh sách có kích thước cho phép, ngày tháng hợp lý, trạng thái nghiệp vụ cho phép thao tác.
3. **Quyền truy cập:** caller được phép đọc hoặc thay đổi resource, tenant và thuộc tính cụ thể.

Ví dụ, request có thể chứa quantity là số nguyên dương nhưng vẫn không được phép mua sản phẩm đó. Một orderId có thể đúng định dạng UUID nhưng thuộc tenant khác. Một filter có thể đúng cú pháp JSON nhưng yêu cầu truy vấn quá rộng gây cạn tài nguyên.

Validation ở gateway giúp từ chối sớm request sai và giảm tải. Validation trong function bảo vệ logic khi function được gọi từ nhiều trigger hoặc có thể được invoke trực tiếp. Domain layer cần bảo vệ các bất biến trước khi ghi database. Database constraint và conditional write giúp chống race condition khi nhiều invocation đồng thời.

Không dựa vào một lớp duy nhất. Nếu gateway kiểm tra schema nhưng một queue trigger cũng gọi cùng domain service, domain service vẫn phải bảo vệ các điều kiện nghiệp vụ.

## 3. Dùng allowlist và giới hạn rõ ràng

Ưu tiên allowlist: định nghĩa chính xác những giá trị được chấp nhận. Blocklist cố gắng liệt kê chuỗi nguy hiểm thường dễ bị vượt qua vì có nhiều cách mã hóa, cú pháp và cách biểu diễn khác nhau.

Ví dụ:

- Trạng thái đơn hàng chỉ nhận các giá trị enum đã công bố.
- Sort field chỉ nhận một trong các trường được hỗ trợ.
- Page size nằm trong khoảng từ 1 đến giới hạn tối đa.
- Currency lấy từ tập mã được hệ thống hỗ trợ.
- Tên file, extension và object prefix tuân theo quy tắc đã định.
- URL đích chỉ thuộc host được cho phép.
- Header custom chỉ nhận định dạng và độ dài đã công bố.

Không dùng một regex quá rộng để thay thế schema và quy tắc nghiệp vụ. Regex nên ngắn, có giới hạn chiều dài đầu vào và tránh pattern có thể gây catastrophic backtracking. Với identifier, dùng parser hoặc kiểu dữ liệu chuyên dụng nếu có.

Ví dụ validate page size:

~~~java
public int validatePageSize(Integer requested) {
    if (requested == null) {
        return 25;
    }

    if (requested < 1 || requested > 100) {
        throw new ValidationException(
                "pageSize must be between 1 and 100"
        );
    }

    return requested;
}
~~~

Không tự động clamp một giá trị sai về giới hạn nếu điều đó che giấu lỗi client hoặc thay đổi ý nghĩa nghiệp vụ. Chọn một contract nhất quán: dùng default khi field bị bỏ qua, nhưng trả lỗi khi caller gửi giá trị ngoài miền được hỗ trợ.

Với số tiền, dùng BigDecimal hoặc kiểu số nguyên theo đơn vị nhỏ nhất thay vì float/double. Kiểm tra scale, precision, dấu và giới hạn nghiệp vụ. Với phép tính có nguy cơ tràn số, dùng các phép toán exact như Math.addExact khi phù hợp hoặc kiểm tra miền trước khi tính.

## 4. Validate JSON và DTO trong Java

Đừng truyền raw JSON map xuyên suốt ứng dụng. Parse thành DTO có kiểu, validate field và chuyển thành command nội bộ trước khi gọi domain service. DTO nên chứa đúng field API cho phép; tránh bind trực tiếp request vào entity database vì client có thể gửi thêm field như role, ownerId, status hoặc tenantId.

Ví dụ dùng Jakarta Bean Validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 64)
        String customerReference,

        @NotEmpty
        @Size(max = 50)
        java.util.List<@Valid OrderLineRequest> items
) {}

public record OrderLineRequest(
        @NotBlank
        @Size(max = 40)
        String productId,

        @Positive
        int quantity
) {}
~~~

Function có thể dùng Validator để kiểm tra DTO:

~~~java
public <T> void validate(T input, Validator validator) {
    Set<ConstraintViolation<T>> violations =
            validator.validate(input);

    if (!violations.isEmpty()) {
        throw new ValidationException(
                "Request does not satisfy the input contract"
        );
    }
}
~~~

Đây là ví dụ minh họa; cần cấu hình implementation Jakarta Validation phù hợp với runtime hoặc framework. Khi trả lỗi, có thể trả mã lỗi và danh sách field không hợp lệ, nhưng không đưa stack trace, giá trị nhạy cảm hoặc toàn bộ payload vào response.

Cần đặt giới hạn trước và trong quá trình parse:

- Maximum HTTP body size ở gateway và adapter.
- Maximum nesting depth và số phần tử trong collection.
- Giới hạn độ dài chuỗi, số field và số phần tử mảng.
- Kiểu số rõ ràng; từ chối giá trị vượt miền hoặc định dạng không mong muốn.
- Giới hạn thời gian xử lý và tránh parse payload cực lớn trong bộ nhớ.
- Không bật polymorphic deserialization rộng cho dữ liệu không tin cậy.

Schema validation chỉ kiểm tra hình dạng. Sau khi parse vẫn cần kiểm tra quan hệ giữa các field, quyền truy cập và trạng thái nghiệp vụ.

## 5. Chuẩn hóa dữ liệu trước khi validate

Một số input có nhiều cách biểu diễn cùng một giá trị: URL encoding, Unicode normalization, dấu phân cách đường dẫn, ký tự percent-encoded hoặc chữ hoa/chữ thường. Nếu một lớp validate một dạng nhưng lớp sau decode hoặc normalize theo cách khác, attacker có thể vượt qua kiểm tra.

Các nguyên tắc:

- Xác định một quy trình canonicalization nhất quán cho từng loại input.
- Decode theo đúng contract và chỉ một lần ở ranh giới phù hợp.
- Validate trên representation thực sự được dùng ở bước tiếp theo.
- Tránh tự decode lần nữa trong repository hoặc service.
- Chuẩn hóa Unicode khi nghiệp vụ cần so sánh chuỗi tương đương.
- Với hostname, xử lý IDN và chữ hoa/chữ thường theo quy tắc URL.
- Với path, dùng API Path thay vì tự thay thế dấu slash hoặc nối chuỗi.

Không chuẩn hóa mọi chuỗi theo cùng một cách. Ví dụ, Unicode normalization có thể phù hợp với username nhưng không nên âm thầm thay đổi nội dung tự do hoặc dữ liệu đã ký. Nếu chữ ký webhook được tính trên raw body, phải xác minh chữ ký theo đúng byte representation mà đối tác ký trước khi parse hoặc biến đổi payload.

## 6. Ngăn SQL injection

SQL injection xảy ra khi input được ghép trực tiếp vào câu SQL và bị database diễn giải như một phần cú pháp. Ví dụ không an toàn:

~~~java
String sql = "SELECT * FROM orders WHERE customer_id = '"
        + customerId + "'";
Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(sql);
~~~

Nếu customerId chứa dấu nháy và phần cú pháp SQL, câu truy vấn có thể bị thay đổi. Không nên tìm cách loại bỏ một vài ký tự như dấu nháy hoặc dấu chấm phẩy; cách đó không bao quát mọi cú pháp và encoding.

Dùng parameterized query:

~~~java
String sql =
        "SELECT id, status, total_amount "
        + "FROM orders "
        + "WHERE customer_id = ? AND tenant_id = ?";

try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

    statement.setString(1, customerId);
    statement.setString(2, verifiedTenantId);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            // Map các cột được phép vào DTO.
        }
    }
}
~~~

PreparedStatement tách cấu trúc SQL khỏi giá trị dữ liệu. Giá trị không được diễn giải thành cú pháp SQL. Đồng thời, query phải có tenant predicate và authorization phù hợp; parameterization ngăn injection nhưng không tự ngăn truy cập trái phép vào dữ liệu tenant khác.

### Tên cột, bảng và ORDER BY

Parameter placeholder thường không dùng được cho tên bảng, tên cột hoặc từ khóa SQL. Không nối trực tiếp sort field từ query string vào SQL.

Thay vào đó, ánh xạ input sang danh sách identifier cố định:

~~~java
Map<String, String> allowedSortColumns = Map.of(
        "createdAt", "created_at",
        "total", "total_amount",
        "status", "status"
);

String sortColumn = allowedSortColumns.get(requestedSort);

if (sortColumn == null) {
    throw new ValidationException("Unsupported sort field");
}

String direction = switch (requestedDirection) {
    case "asc" -> "ASC";
    case "desc" -> "DESC";
    default -> throw new ValidationException(
            "Unsupported sort direction");
};

String sql = "SELECT id, status FROM orders ORDER BY "
        + sortColumn + " " + direction + " LIMIT ?";
~~~

Chỉ nối các token lấy từ allowlist do server định nghĩa; giá trị filter vẫn dùng bind parameter. ORM như JPA không tự động an toàn nếu dùng native query hoặc nối JPQL/SQL từ chuỗi input. Dùng Criteria API, query builder có parameter binding hoặc repository method có tham số.

## 7. Ngăn NoSQL và query-language injection

NoSQL không có nghĩa là không có injection. Một số database nhận document query, filter expression, aggregation pipeline hoặc operator như $ne, $gt và $where. Nếu ứng dụng nhận một object JSON tùy ý rồi truyền thẳng thành query, người dùng có thể chèn operator hoặc thay đổi cấu trúc truy vấn.

Không dùng raw request map làm filter database. Chuyển DTO thành query có cấu trúc do server tạo:

~~~java
public List<Order> findOrders(
        String verifiedTenantId,
        OrderSearchRequest request) {

    Criteria criteria = new Criteria()
            .and("tenantId").is(verifiedTenantId);

    if (request.status() != null) {
        criteria.and("status").is(request.status());
    }

    if (request.createdAfter() != null) {
        criteria.and("createdAt").gte(request.createdAfter());
    }

    Query query = new Query(criteria)
            .limit(validatePageSize(request.pageSize()));

    return mongoTemplate.find(query, Order.class);
}
~~~

Ví dụ dùng Spring Data MongoDB; kiểu request và repository cần được điều chỉnh theo dự án. Chỉ tạo operator mà server cho phép. Không cho client gửi trực tiếp aggregation pipeline, MongoDB operator, DynamoDB expression hoặc tên index tùy ý nếu không có một use case được kiểm soát.

Với DynamoDB, dùng ExpressionAttributeValues và expression name/value binding đúng API. Không nối input vào biểu thức condition hoặc projection. Với Elasticsearch hoặc search engine, dùng query builder typed và giới hạn field, operator, độ sâu, số kết quả và thời gian truy vấn.

## 8. Ngăn OS command injection

OS command injection xảy ra khi input được nối vào shell command. Một chuỗi tưởng như tên file hoặc tham số có thể chứa metacharacter khiến shell thực thi lệnh khác.

Không dùng:

~~~java
Runtime.getRuntime().exec(
        "convert " + inputFile + " " + outputFile
);
~~~

Cách an toàn hơn là tránh shell và gọi executable cố định bằng ProcessBuilder với từng argument riêng:

~~~java
ProcessBuilder processBuilder = new ProcessBuilder(
        "/usr/bin/convert",
        validatedInputPath.toString(),
        validatedOutputPath.toString()
);

processBuilder.redirectOutput(ProcessBuilder.Redirect.DISCARD);
processBuilder.redirectError(ProcessBuilder.Redirect.DISCARD);
Process process = processBuilder.start();

if (!process.waitFor(5, TimeUnit.SECONDS)) {
    process.destroyForcibly();
    throw new ProcessingTimeoutException();
}

if (process.exitValue() != 0) {
    throw new ProcessingException("Image conversion failed");
}
~~~

ProcessBuilder không tự gọi shell khi truyền executable và arguments theo cách này, nên shell metacharacter không được diễn giải như cú pháp shell. Tuy nhiên, argument vẫn có thể bị chương trình đích hiểu là option hoặc input đặc biệt. Cần validate path, dùng executable cố định, đặt option trước input, dùng delimiter -- nếu công cụ hỗ trợ và giới hạn quyền filesystem.

Nếu có thư viện Java thực hiện trực tiếp chức năng cần thiết, ưu tiên dùng thư viện thay vì gọi process bên ngoài. Trong serverless, process phụ còn tiêu thụ CPU, memory, file descriptor và thời gian invocation; cần timeout, giới hạn output và cleanup process khi lỗi.

## 9. Path traversal, file access và ZIP Slip

Path traversal xảy ra khi input điều khiển đường dẫn và làm ứng dụng truy cập file ngoài thư mục được phép. Ví dụ, tên file chứa chuỗi ../ có thể thoát khỏi thư mục gốc nếu ứng dụng chỉ nối chuỗi.

Dùng Path API và kiểm tra đường dẫn đã chuẩn hóa:

~~~java
Path root = Paths.get("/tmp/uploads").toAbsolutePath().normalize();
Path candidate = root.resolve(userSuppliedName).normalize();

if (!candidate.startsWith(root)) {
    throw new ValidationException("Invalid file path");
}
~~~

Đây là kiểm tra cơ bản cho đường dẫn không có symbolic link độc hại. Với file đã tồn tại hoặc môi trường có thể tạo symbolic link, cần resolve real path và xác minh nó vẫn nằm dưới root thực. Với file mới, kiểm tra parent directory đã resolve; hạn chế quyền ghi và tránh race giữa kiểm tra với thao tác mở file.

Khi giải nén ZIP, không ghi entry trực tiếp bằng cách nối entry name vào destination directory. Đây là lỗi ZIP Slip:

~~~java
Path destination = Paths.get("/tmp/extracted")
        .toAbsolutePath().normalize();

Path output = destination.resolve(zipEntry.getName())
        .normalize();

if (!output.startsWith(destination)) {
    throw new SecurityException("ZIP entry escapes destination");
}
~~~

Sau kiểm tra, cần tạo parent directory an toàn và xử lý symbolic link, duplicate entry, absolute path, tên file bất thường và giới hạn kích thước giải nén. Giới hạn tổng số entry, kích thước sau giải nén và tỷ lệ nén để chống archive bomb. Không tin extension hoặc tên file là bằng chứng nội dung an toàn.

## 10. Ngăn Server-Side Request Forgery (SSRF)

SSRF xảy ra khi function lấy URL do caller kiểm soát rồi gửi request tới địa chỉ mà server có thể truy cập. Attacker có thể cố truy cập metadata endpoint của cloud, địa chỉ loopback, mạng private, dịch vụ quản trị hoặc host nội bộ.

Thiết kế an toàn nhất là không nhận URL tùy ý. Nếu nghiệp vụ cần gọi đối tác, nhận một partner ID hoặc resource ID rồi ánh xạ sang endpoint cố định trong cấu hình server.

Nếu buộc phải nhận URL:

- Chỉ cho phép scheme cần thiết, thường là HTTPS.
- Dùng allowlist hostname hoặc domain đã đăng ký; không chỉ kiểm tra chuỗi suffix hời hợt.
- Phân giải DNS và kiểm tra mọi địa chỉ IP trả về; chặn loopback, private, link-local, multicast, reserved và địa chỉ metadata.
- Chống DNS rebinding bằng cách kiểm soát kết nối tới địa chỉ đã xác minh hoặc dùng egress proxy có policy.
- Tắt redirect tự động hoặc xác minh lại từng redirect target.
- Không cho phép userinfo hoặc port tùy ý nếu nghiệp vụ không cần.
- Đặt connect/read/overall timeout, giới hạn response body và số redirect.
- Giới hạn egress ở network layer để function chỉ gọi các đích cần thiết.

Chỉ kiểm tra URL bằng regex là không đủ. Hostname có thể phân giải thành IP nội bộ sau bước validate, redirect có thể chuyển sang host khác và nhiều dạng IPv6/encoding có thể làm bộ lọc chuỗi sai. Hãy kết hợp validation ở ứng dụng với network egress controls.

## 11. Template injection, XSS và output encoding

Template injection xuất hiện khi input không tin cậy được diễn giải như source template hoặc expression. Không ghép input vào template source rồi đưa cho template engine thực thi. Hãy dùng template cố định và truyền input như model data. Nếu sản phẩm cho phép người dùng tạo template, cần sandbox hạn chế quyền, giới hạn CPU/time và cấm truy cập class, file hoặc network không cần thiết.

Cross-site scripting (XSS) thường xuất hiện ở nơi response được render trong trình duyệt. JSON API không tự động gây XSS, nhưng dữ liệu do API trả về có thể được frontend chèn vào HTML không an toàn. Dùng output encoding theo đúng context:

- HTML text cần HTML escaping.
- HTML attribute cần attribute escaping và giới hạn attribute được phép.
- JavaScript string cần JavaScript-safe encoding; tốt hơn tránh nhúng dữ liệu trực tiếp vào inline script.
- URL cần parse, validate scheme và encode component đúng cách.
- SQL cần parameter binding, không dùng HTML escaping.
- Shell command cần tránh shell và truyền arguments an toàn.

Không dùng một hàm escape chung cho mọi ngữ cảnh. Encoding phải được áp dụng tại điểm dữ liệu đi vào sink, dựa trên ngữ cảnh diễn giải cuối cùng. Nếu dữ liệu được encode hai lần hoặc encode sai context, vẫn có thể tạo lỗ hổng hoặc làm hỏng nội dung.

### LDAP, XPath, GraphQL và expression language

Các ngôn ngữ truy vấn khác cũng có thể bị injection nếu ứng dụng ghép input vào filter hoặc expression. Với LDAP, dùng API tạo filter có escaping/parameter binding của thư viện; không nối username trực tiếp vào chuỗi filter. Với XPath, dùng variable resolver thay vì ghép giá trị vào biểu thức. Với GraphQL, dùng query cố định cùng variables và giới hạn depth, complexity, field và resolver cost. Với SpEL, EL hoặc expression engine khác, không evaluate expression do caller cung cấp; chỉ dùng expression do ứng dụng định nghĩa và truyền dữ liệu qua biến được kiểm soát.

Nguyên tắc chung là phân tách cú pháp truy vấn khỏi giá trị đầu vào và chỉ cho phép tập thao tác mà ứng dụng thực sự cần. Nếu người dùng được phép xây dựng bộ lọc nâng cao, hãy cung cấp một DSL có schema giới hạn rồi chuyển nó thành query an toàn; đừng chuyển nguyên văn filter thành source expression.

## 12. XML, YAML và deserialization không tin cậy

XML parser có thể bị khai thác qua external entity (XXE) nếu được phép đọc file hoặc gọi URL bên ngoài. Nếu function phải parse XML, tắt external general entities, parameter entities và external DTD; bật secure processing và giới hạn kích thước, độ sâu, số node.

Ví dụ cấu hình DocumentBuilderFactory theo hướng an toàn:

~~~java
DocumentBuilderFactory factory =
        DocumentBuilderFactory.newInstance();

factory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl",
        true
);
factory.setFeature(
        "http://xml.org/sax/features/external-general-entities",
        false
);
factory.setFeature(
        "http://xml.org/sax/features/external-parameter-entities",
        false
);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
~~~

Các feature được hỗ trợ tùy parser; nếu cấu hình bảo mật không được chấp nhận, không âm thầm bỏ qua rồi tiếp tục parse XML không tin cậy. Hãy dùng parser có cấu hình secure mặc định và kiểm thử thực tế.

Với JSON deserialization, tránh bật polymorphic default typing rộng để input có thể chỉ định class cần khởi tạo. Dùng DTO cụ thể, subtype allowlist, giới hạn nesting và kích thước. Tránh Java native serialization cho dữ liệu từ mạng hoặc queue không tin cậy. Với YAML, chọn safe constructor và không cho phép tag có thể khởi tạo object tùy ý.

## 13. Header, log và biểu thức regex

Input không chỉ có thể tấn công database hoặc shell. Chuỗi được phản chiếu vào HTTP header, log hoặc regex cũng có thể tạo lỗ hổng.

### HTTP response header injection

Không đưa trực tiếp dữ liệu caller vào header. Ký tự CR/LF có thể tạo header mới hoặc làm sai cấu trúc response nếu framework không chặn. Dùng header API của framework, kiểm tra độ dài và loại bỏ ký tự điều khiển theo contract. Không cho phép user tự đặt Location, Set-Cookie hoặc header bảo mật tùy ý.

### Log injection

Nếu ghi chuỗi chứa newline hoặc ký tự điều khiển vào log dạng text, attacker có thể tạo dòng log giả hoặc làm hỏng parsing. Dùng structured logging, encode/sanitize giá trị không tin cậy và giới hạn độ dài. Không log password, access token, session cookie, secret hoặc toàn bộ request body.

### Regular expression denial of service

Regex có backtracking phức tạp có thể tiêu thụ CPU lớn với input được tạo có chủ đích. Giới hạn độ dài trước khi match, dùng pattern đơn giản và tránh nested quantifier. Java java.util.regex không cung cấp timeout trực tiếp cho một lần match; nếu cần kiểm soát thời gian chặt, dùng engine có bảo đảm độ phức tạp phù hợp hoặc cô lập việc xử lý. Với identifier và định dạng phổ biến, ưu tiên parser chuyên dụng.

## 14. File upload và nội dung độc hại

Function nhận file upload phải kiểm tra cả metadata lẫn nội dung. Content-Type do client gửi có thể giả mạo; extension không chứng minh file thực sự thuộc định dạng đó.

Một pipeline an toàn có thể gồm:

1. Giới hạn request size tại API gateway và giới hạn kích thước object sau upload.
2. Ghi file vào bucket/prefix quarantine với quyền riêng.
3. Kiểm tra extension theo allowlist và MIME sniff bằng nội dung thực.
4. Kiểm tra magic bytes, parser và cấu trúc file.
5. Giới hạn số trang, số entry, kích thước giải nén và độ sâu archive.
6. Quét malware bằng dịch vụ phù hợp nếu loại dữ liệu yêu cầu.
7. Đổi tên object bằng ID do server tạo, không dùng trực tiếp tên path từ client.
8. Chuyển file hợp lệ sang vùng xử lý hoặc lưu trữ chính thức.
9. Ghi trạng thái kiểm tra và cleanup file thất bại theo TTL.

Với ảnh, PDF, Office document hoặc archive, parser cũng là bề mặt tấn công. Dùng thư viện được cập nhật, giới hạn tài nguyên và chạy với quyền tối thiểu. Không cho parser truy cập network hoặc filesystem ngoài vùng tạm nếu không cần.

Nếu dùng presigned URL để upload trực tiếp lên object storage, backend vẫn cần xác minh object sau khi upload. Chỉ vì upload được ký hợp lệ không có nghĩa nội dung an toàn hoặc thuộc đúng tenant.

## 15. Validate webhook và event payload

Webhook cần xác minh chữ ký trước khi tin nội dung. Thông thường, đối tác ký raw request body cùng timestamp hoặc metadata theo contract của họ. Hãy:

- Đọc raw body theo cách không làm thay đổi byte trước khi verify.
- Kiểm tra chữ ký bằng thuật toán và header đúng theo tài liệu đối tác.
- So sánh MAC bằng constant-time comparison khi tự triển khai.
- Kiểm tra timestamp và cửa sổ chống replay.
- Dùng event ID để deduplicate.
- Sau khi xác minh mới parse payload thành DTO và validate schema.
- Lưu kết quả tiếp nhận bền vững trước khi trả response thành công.
- Chuyển xử lý dài sang queue sau khi đã xác minh và ghi nhận event.

Với queue hoặc event bus nội bộ, kiểm tra event type, schema version, producer, tenant, event ID và thời điểm. Metadata như producer name hoặc tenant ID trong payload chỉ hỗ trợ định tuyến và audit; nó không tự chứng minh danh tính. Quyền publish cần được kiểm soát ở broker/IAM, còn consumer cần kiểm tra quyền và quy tắc nghiệp vụ của chính nó.

Event có thể cũ, đến sai thứ tự hoặc bị replay. Dùng version/sequence của aggregate và conditional update để tránh event cũ ghi đè trạng thái mới.

## 16. Kiểm tra quyền và chống mass assignment

Mass assignment xảy ra khi ứng dụng bind toàn bộ field caller gửi vào domain entity hoặc database record. Attacker có thể thêm field mà UI không hiển thị, ví dụ ownerId, tenantId, role, status, approved hoặc price.

Không dùng entity trực tiếp làm request DTO. Tạo DTO chỉ gồm field caller được phép cung cấp, sau đó mapping tường minh:

~~~java
public CreateOrderCommand toCommand(
        CreateOrderRequest request,
        VerifiedIdentity identity) {

    return new CreateOrderCommand(
            identity.tenantId(),
            identity.subject(),
            request.customerReference(),
            request.items()
    );
}
~~~

Tenant và subject lấy từ identity đã xác minh, không lấy từ body. Giá, trạng thái thanh toán, quyền sở hữu và approval thường do server hoặc domain workflow quyết định. Sau khi mapping, domain service kiểm tra quyền trên resource và bất biến nghiệp vụ trước khi ghi.

Với multi-tenant application, mọi query và update cần gắn tenant scope ở phía server. Không chỉ kiểm tra user có quyền gọi endpoint; phải kiểm tra user có quyền với đúng resource ID. Conditional update có thể yêu cầu tenantId, ownerId và expected version cùng khớp để chống TOCTOU/race condition.

## 17. Error handling không làm lộ thông tin

Khi validation thất bại, trả lỗi rõ ràng nhưng không tiết lộ implementation. Một response có thể gồm mã lỗi ổn định, field lỗi và correlation ID.

Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/invalid-input",
  "title": "Invalid request",
  "status": 422,
  "code": "INVALID_PAGE_SIZE",
  "detail": "pageSize must be between 1 and 100",
  "traceId": "req-91ac"
}
~~~

Không trả stack trace, SQL query, đường dẫn filesystem, tên class, secret, token hoặc thông tin network nội bộ. Với lỗi phân quyền, cân nhắc trả 404 thay vì 403 nếu tiết lộ resource tồn tại có thể gây rủi ro; giữ cách xử lý nhất quán.

Log nội bộ có thể ghi exception và context cần thiết, nhưng phải redact dữ liệu nhạy cảm. Đừng đưa nguyên văn attacker input vào log mà không giới hạn và sanitize. Ghi nhận loại lỗi, field, nguồn trigger và trace ID thay vì lưu toàn bộ payload.

## 18. Giới hạn tài nguyên và bảo vệ function khỏi input gây quá tải

Một input có thể không chứa cú pháp injection nhưng vẫn làm function cạn CPU, memory, connection hoặc thời gian invocation. Đây là nhóm rủi ro resource exhaustion và denial of service.

Đặt giới hạn cho:

- Request body và file upload.
- Số phần tử trong array, số field và độ sâu JSON.
- Page size, filter count, sort fields và query complexity.
- Regex input và thời gian parse.
- Archive entry count, uncompressed size và compression ratio.
- HTTP response body từ dependency.
- Số URL redirect và tổng thời gian gọi outbound.
- Batch size, số tác vụ song song và queue depth.
- Database query timeout và maximum result rows.

Dùng rate limit và quota ở gateway; giới hạn concurrency của function để bảo vệ database và dịch vụ đối tác. Với tác vụ nặng hoặc dài, chuyển sang queue hoặc workflow có backpressure. Không retry ngay lập tức khi dependency quá tải vì có thể tạo retry storm.

## 19. Quy trình xử lý input an toàn trong Java function

Một pipeline HTTP điển hình:

~~~mermaid
flowchart TD
    A["HTTP / message / event"] --> B["Giới hạn kích thước và tốc độ"]
    B --> C["Xác thực nguồn và danh tính"]
    C --> D["Parse theo schema cố định"]
    D --> E["Canonicalize theo contract"]
    E --> F["Validate kiểu, giới hạn và ngữ nghĩa"]
    F --> G["Authorize tenant và resource"]
    G --> H["Tạo command nội bộ có kiểu"]
    H --> I["Dùng parameter binding / safe API"]
    I --> J["Commit state và side effect có kiểm soát"]
    J --> K["Response / acknowledgment"]
~~~

Một HTTP handler có thể được tổ chức như sau:

~~~java
public final class CreateOrderHandler
        implements RequestHandler<ApiRequest, ApiResponse> {

    private final Validator validator;
    private final AuthorizationService authorization;
    private final OrderService orderService;

    @Override
    public ApiResponse handleRequest(
            ApiRequest request,
            Context context) {

        VerifiedIdentity identity =
                identityProvider.fromVerifiedContext(request);

        CreateOrderRequest dto =
                jsonMapper.readValue(
                        enforceBodyLimit(request.body()),
                        CreateOrderRequest.class
                );

        validate(dto, validator);

        authorization.requireCanCreateOrder(identity);

        CreateOrderCommand command =
                toCommand(dto, identity);

        OrderResult result = orderService.create(command);

        return ApiResponse.created(result);
    }
}
~~~

Ví dụ dùng các abstraction như ApiRequest, VerifiedIdentity, identityProvider, jsonMapper và OrderService; cần thay bằng adapter của API Gateway/runtime. Không đọc identity từ body hoặc header tùy ý. Body limit phải được áp dụng trước khi parse; nếu gateway đã giới hạn, function vẫn nên bảo vệ khi có đường invoke khác.

Với message trigger, thay bước lấy identity bằng kiểm tra producer/source context và quyền xử lý event; payload vẫn phải validate schema, tenant, version và trạng thái. Chỉ ack sau khi kết quả nghiệp vụ được ghi bền vững theo contract của broker.

## 20. Kiểm thử input validation và injection

Unit test chỉ kiểm tra một validator là chưa đủ. Cần test tại đúng sink nơi dữ liệu được dùng: query database, process invocation, file access, URL fetch, template render và log.

Ma trận kiểm thử:

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|
| Schema | Field thiếu, sai kiểu, field lạ | Từ chối theo contract; không gọi domain service |
| Giới hạn | Body quá lớn, array quá dài, số âm hoặc quá lớn | Từ chối sớm, không cạn tài nguyên |
| SQL | Giá trị chứa quote và cú pháp SQL | Query vẫn giữ cấu trúc; giá trị được bind |
| NoSQL | JSON chứa operator hoặc filter lạ | Không được biến thành query operator |
| Command | Input có shell metacharacter hoặc option prefix | Không chạy shell; executable/argument được kiểm soát |
| Path | ../, absolute path, encoded traversal, symlink | Không truy cập ngoài root |
| ZIP | Entry thoát thư mục hoặc archive bomb | Từ chối và không ghi file ngoài vùng |
| SSRF | Loopback, private IP, metadata IP, redirect tới host cấm | Request outbound bị chặn |
| XML | DOCTYPE và external entity | Parser từ chối hoặc không resolve external entity |
| XSS/template | HTML/script/template expression trong dữ liệu | Dữ liệu không được thực thi khi render |
| Header/log | CRLF, newline và chuỗi rất dài | Không tạo header/log giả hoặc log quá lớn |
| Authorization | ID hợp lệ thuộc tenant khác | Từ chối, không tiết lộ dữ liệu |
| Webhook/event | Chữ ký sai, event cũ, duplicate, schema cũ | Từ chối hoặc deduplicate theo policy |

Dùng test fixture chứa payload độc hại đã biết nhưng không thực thi chúng trong môi trường production. Kiểm thử integration cần xác minh query parameterization, filesystem boundary, egress policy và parser configuration thực tế. Fuzz testing có thể phát hiện input edge case; property-based testing hữu ích để kiểm tra invariant như mọi path sau normalize vẫn nằm dưới root.

## 21. Quan sát và phản ứng khi phát hiện input độc hại

Theo dõi số lần validation thất bại, auth failure, rate limit, parser error, outbound request bị chặn và query timeout. Phân loại theo trigger, route, error code và tenant reference đã được kiểm soát.

Metric hữu ích:

- Request bị từ chối theo lý do và route.
- Schema validation failure theo version.
- SQL/database error và query latency.
- SSRF/egress policy denial.
- File upload bị quarantine hoặc scan thất bại.
- Webhook signature failure và duplicate event count.
- Rate limit, throttling và invocation concurrency.
- Parser timeout, body size và archive expansion ratio.

Không dùng raw user input làm metric label vì cardinality có thể tăng không giới hạn và gây lộ dữ liệu. Không log toàn bộ payload độc hại; lưu hash, event ID, request ID hoặc một mẫu đã redact nếu chính sách cho phép. Cần cảnh báo khi tỷ lệ lỗi tăng đột biến, nhưng tránh biến mọi lỗi validation thông thường thành sự cố mức cao.

Khi phát hiện lạm dụng, có thể giảm quota, chặn principal hoặc route, disable trigger bị ảnh hưởng, quarantine message/file và điều tra trace liên quan. Nếu input đã đi tới side effect, dùng audit trail và idempotency record để xác định trạng thái; không phát lại message một cách mù quáng.

## 22. Checklist bảo vệ input cho production

Trước khi triển khai function, hãy xác nhận:

1. Đã liệt kê mọi nguồn input: HTTP, message, event, webhook, file và dependency?
2. Có giới hạn body, file, collection, nesting, query và thời gian parse?
3. DTO chỉ chứa field caller được phép gửi?
4. Có schema validation và semantic validation ở function/domain layer?
5. Canonicalization và decoding được thực hiện nhất quán, không decode lặp?
6. Danh tính và tenant được lấy từ context đã xác minh?
7. Authorization được kiểm tra trên từng resource, không chỉ endpoint?
8. SQL dùng PreparedStatement hoặc parameterized query?
9. Tên bảng/cột/sort/filter được ánh xạ qua allowlist?
10. NoSQL và search query được tạo từ typed query builder, không dùng raw client object?
11. Không ghép input vào shell command; nếu cần process, dùng executable cố định và argument riêng?
12. Path được normalize/resolve và giữ trong root cho phép?
13. SSRF được kiểm soát bằng host allowlist và egress policy?
14. XML/JSON/YAML deserialization có cấu hình an toàn?
15. Template và output được xử lý theo đúng context encoding?
16. File upload được giới hạn, kiểm tra nội dung và quarantine?
17. Webhook có signature verification và replay protection?
18. Log và error response không làm lộ secret hoặc tạo log injection?
19. Concurrency, timeout, retry và result size có giới hạn?
20. Có test ở đúng sink và có metric/cảnh báo cho hành vi bất thường?

## Kết luận

Input validation bảo đảm dữ liệu đúng cấu trúc, giới hạn và quy tắc nghiệp vụ; injection prevention bảo đảm dữ liệu không bị diễn giải thành lệnh hoặc biểu thức ngoài ý muốn. Một function serverless phải áp dụng cả hai cho mọi trigger, kể cả message nội bộ và event từ dịch vụ cloud.

Trong Java, hãy parse vào DTO có kiểu, dùng allowlist và giới hạn rõ ràng, lấy identity từ context đã xác minh, kiểm tra quyền theo resource và dùng API an toàn tại từng sink: PreparedStatement cho SQL, query builder cho NoSQL, ProcessBuilder không qua shell, Path API cho file và egress policy cho URL. Kết hợp kiểm thử ở sink, timeout, quota, log có cấu trúc và cleanup an toàn để bảo vệ function khi nhận dữ liệu lỗi hoặc có chủ đích tấn công.

