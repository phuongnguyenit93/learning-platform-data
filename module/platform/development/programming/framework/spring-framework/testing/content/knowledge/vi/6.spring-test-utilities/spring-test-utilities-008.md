# Các tiện ích so sánh JSON, XML và tài nguyên

Khi kiểm thử ứng dụng Spring, kết quả thường được biểu diễn dưới dạng JSON, XML hoặc nội dung tài nguyên như file ảnh, PDF, CSV và file cấu hình. So sánh trực tiếp chuỗi hoặc byte là cách đơn giản, nhưng không phải lúc nào cũng diễn đạt đúng điều cần bảo vệ. JSON có thể thay đổi thứ tự thuộc tính hoặc khoảng trắng mà không đổi ý nghĩa; XML có thể có namespace và cấu trúc node cần kiểm tra; tài nguyên nhị phân cần được so sánh theo nội dung byte và metadata.

Spring Test cung cấp các matcher cho MockMvc và phối hợp với những thư viện chuyên dụng để kiểm tra nội dung. Các công cụ thường gặp gồm:

- **ContentResultMatchers:** kiểm tra content type, encoding, chuỗi, byte, JSON và XML của HTTP response.
- **JsonPathResultMatchers:** truy vấn một phần JSON bằng biểu thức JSONPath.
- **XPathResultMatchers:** truy vấn node và giá trị XML bằng XPath.
- **Spring Resource abstraction:** đọc tài nguyên từ classpath, filesystem, servlet context hoặc nguồn dữ liệu khác theo cùng một interface.
- **Resource và byte assertions:** xác nhận file fixture, nội dung tải xuống hoặc dữ liệu nhị phân.

Mục tiêu của bài học là chọn cách so sánh phù hợp với hợp đồng của thành phần đang kiểm thử, để assertion dễ hiểu và ít phụ thuộc vào cách định dạng dữ liệu.

## 1. Chọn cách so sánh theo ý nghĩa dữ liệu

Trước khi viết assertion, cần xác định điều gì thực sự quan trọng:

| Dữ liệu | Điều cần xác nhận | Cách tiếp cận phù hợp |
|---|---|---|
| JSON response | Cấu trúc, giá trị field, phần tử mảng | JSON comparison hoặc JSONPath |
| XML response | Cấu trúc node, thuộc tính, namespace, giá trị | XML comparison hoặc XPath |
| Text resource | Nội dung văn bản | Đọc Resource thành chuỗi và so sánh |
| Binary resource | Byte, content type, content length | So sánh byte và response metadata |
| File fixture | File tồn tại, đọc được, nội dung mong đợi | Resource abstraction và assertion |

Có ba mức so sánh thường dùng:

1. **So sánh nguyên văn:** phù hợp khi định dạng và từng ký tự là một phần của hợp đồng, ví dụ nội dung plain text hoặc định dạng file cần chính xác.
2. **So sánh cấu trúc:** phù hợp với JSON và XML khi thứ tự thuộc tính, khoảng trắng hoặc cách trình bày không phải điều đang kiểm tra.
3. **So sánh một phần:** phù hợp khi chỉ một số field, node hoặc metadata quan trọng; dùng JSONPath, XPath hoặc assertion riêng.

Không nên dùng phép so sánh toàn bộ chuỗi cho mọi loại dữ liệu. Một assertion nên phản ánh điều mà client hoặc thành phần phụ thuộc có quyền kỳ vọng.

## 2. Kiểm tra JSON với MockMvc

Spring MVC Test cung cấp ContentResultMatchers để xác nhận response body. Với JSON, có thể dùng phương thức json của content matcher:

~~~java
mockMvc.perform(get("/api/products/42"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ))
    .andExpect(content().json("""
        {
          "id": 42,
          "name": "Keyboard",
          "active": true
        }
        """));
~~~

Ví dụ giả định endpoint trả một product dưới dạng JSON. Assertion content type xác nhận response có media type tương thích với JSON; assertion json so sánh nội dung theo cấu trúc JSON thay vì yêu cầu chuỗi response có cùng khoảng trắng hoặc thứ tự trình bày.

### 2.1. So sánh JSON theo chế độ strict và lenient

Khi dùng JSONAssert thông qua Spring Test, chế độ so sánh quyết định mức độ chặt chẽ:

- **STRICT:** cấu trúc phải khớp, không cho phép field thừa và thứ tự phần tử mảng phải khớp.
- **LENIENT:** cho phép field thừa và không yêu cầu thứ tự phần tử mảng cố định; những field và giá trị được khai báo trong expected vẫn phải có và khớp.

Có thể chọn chế độ rõ ràng bằng JsonCompareMode:

~~~java
import org.skyscreamer.jsonassert.JSONCompareMode;

mockMvc.perform(get("/api/products/42"))
    .andExpect(status().isOk())
    .andExpect(content().json(
        """
        {
          "id": 42,
          "name": "Keyboard"
        }
        """,
        JSONCompareMode.STRICT
    ));
~~~

Chọn STRICT khi response là một contract ổn định và field thừa cũng cần được phát hiện. Chọn LENIENT khi API được phép bổ sung field hoặc thứ tự mảng không mang ý nghĩa. Nếu thứ tự mảng là quy tắc nghiệp vụ, hãy dùng chế độ chặt chẽ hoặc assertion riêng cho thứ tự.

Không nên chọn LENIENT chỉ để làm test hết đỏ. Trước khi đổi chế độ, hãy xác định API có thực sự cho phép field thừa hoặc thứ tự mảng thay đổi hay không.

### 2.2. So sánh JSON bằng JSONPath

JSONPath phù hợp khi chỉ cần xác nhận một vài field. Spring MVC Test cung cấp jsonPath matcher thông qua MockMvcResultMatchers:

~~~java
mockMvc.perform(get("/api/products/42"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$.name").value("Keyboard"))
    .andExpect(jsonPath("$.active").value(true));
~~~

Biểu thức JSONPath bắt đầu từ ký hiệu gốc $. Dấu chấm truy cập thuộc tính, còn dấu ngoặc vuông có thể chọn phần tử mảng hoặc tên thuộc tính đặc biệt.

Ví dụ response:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "id": "CUS-20",
    "name": "An"
  },
  "items": [
    {"sku": "BOOK-01", "quantity": 2},
    {"sku": "PEN-02", "quantity": 3}
  ]
}
~~~

Các assertion có thể tập trung vào field cần thiết:

~~~java
mockMvc.perform(get("/api/orders/ORD-100"))
    .andExpect(jsonPath("$.customer.id").value("CUS-20"))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items.length()").value(2))
    .andExpect(jsonPath("$.items[0].sku").value("BOOK-01"))
    .andExpect(jsonPath("$.items[1].quantity").value(3));
~~~

JSONPath matcher hỗ trợ nhiều dạng kiểm tra:

- value: giá trị của field hoặc kết quả truy vấn.
- exists và doesNotExist: sự tồn tại của giá trị được truy vấn.
- isEmpty và isNotEmpty: collection hoặc giá trị rỗng.
- isArray và isMap: kiểu cấu trúc được truy vấn.
- value với Hamcrest matcher: kiểm tra điều kiện linh hoạt hơn.

Ví dụ:

~~~java
mockMvc.perform(get("/api/orders/ORD-100"))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items").isNotEmpty())
    .andExpect(jsonPath("$.discountCode").doesNotExist());
~~~

Khi kiểm tra giá trị số, cần chú ý kiểu dữ liệu. JSON chỉ có khái niệm number; thư viện truy vấn có thể chuyển đổi giá trị sang kiểu Java cụ thể. Nếu matcher cần một kiểu cụ thể, có thể chỉ định target type theo overload mà phiên bản Spring đang dùng, hoặc kiểm tra qua kiểu số phù hợp. Không nên ép kiểu chuỗi nếu hợp đồng JSON quy định đây là số.

### 2.3. Kiểm tra phần tử mảng và tập hợp

Nếu response chứa danh sách, hãy xác định thứ tự có ý nghĩa hay không:

~~~java
mockMvc.perform(get("/api/products"))
    .andExpect(jsonPath("$.products").isArray())
    .andExpect(jsonPath("$.products.length()").value(2))
    .andExpect(jsonPath("$.products[0].id").value(10))
    .andExpect(jsonPath("$.products[1].id").value(20));
~~~

Ví dụ này bảo vệ cả số phần tử và thứ tự. Nếu API không cam kết thứ tự, có thể xác nhận từng phần tử theo thuộc tính ổn định, hoặc dùng JSON comparison ở chế độ cho phép thứ tự thay đổi. Tránh viết test phụ thuộc thứ tự tình cờ của database.

Với mảng lồng nhau, JSONPath giúp đi sâu đến đúng vị trí:

~~~java
mockMvc.perform(get("/api/orders/ORD-100"))
    .andExpect(jsonPath("$.items[?(@.quantity > 1)].length()").value(1));
~~~

Biểu thức filter như trên hữu ích cho điều kiện truy vấn, nhưng nên giữ biểu thức đơn giản để người đọc hiểu được điều đang kiểm tra. Với logic phức tạp, có thể lấy response thành JSON tree bằng ObjectMapper rồi dùng assertion Java rõ ràng.

### 2.4. Kiểm tra JSON null, field thiếu và field rỗng

Ba trạng thái này khác nhau:

- Field không xuất hiện trong JSON.
- Field xuất hiện với giá trị null.
- Field xuất hiện với chuỗi rỗng hoặc collection rỗng.

Ví dụ:

~~~json
{
  "middleName": null,
  "tags": [],
  "displayName": ""
}
~~~

Không nên coi các trạng thái trên là tương đương. API có thể dùng null để biểu thị chưa có dữ liệu, mảng rỗng để biểu thị danh sách hiện không có phần tử và field bị lược bỏ để biểu thị thuộc tính không được cung cấp.

Khi cần phân biệt field thiếu với field null, hãy dùng JSONPath phù hợp và kiểm tra sự tồn tại của node. Nếu thư viện JSONPath hoặc cấu hình provider làm kết quả thiếu/null khó phân biệt, có thể parse JSON thành JsonNode và kiểm tra trực tiếp:

~~~java
JsonNode root = objectMapper.readTree(responseBody);

assertTrue(root.has("middleName"));
assertTrue(root.get("middleName").isNull());
assertTrue(root.get("tags").isArray());
assertEquals(0, root.get("tags").size());
~~~

### 2.5. Khi nào nên dùng so sánh toàn bộ và khi nào nên dùng JSONPath?

| Nhu cầu | Nên dùng |
|---|---|
| Response có schema nhỏ và toàn bộ field là contract | content().json với STRICT |
| API cho phép thêm field hoặc mảng không có thứ tự cố định | content().json với LENIENT |
| Chỉ một vài field quan trọng | jsonPath |
| Cần kiểm tra một phần tử theo điều kiện | JSONPath filter hoặc parse JSON tree |
| Cần phân biệt field thiếu, null và rỗng | JSONPath kết hợp kiểm tra tồn tại hoặc JsonNode |
| Body là văn bản có định dạng chính xác | content().string |

So sánh toàn bộ giúp phát hiện thay đổi ngoài dự kiến trong contract. JSONPath giúp test tập trung vào hành vi cụ thể và giảm phụ thuộc vào field không liên quan. Có thể kết hợp cả hai nếu test có một số điều kiện quan trọng cần diễn đạt riêng.

## 3. Kiểm tra XML với MockMvc

XML có cấu trúc cây gồm element, attribute, text node và namespace. So sánh nguyên văn XML thường quá nhạy với khoảng trắng, xuống dòng và cách trình bày. Spring Test hỗ trợ so sánh XML và truy vấn XPath.

### 3.1. So sánh XML response

Có thể dùng content().xml để xác nhận XML response:

~~~java
mockMvc.perform(get("/api/catalog/42")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_XML
    ))
    .andExpect(content().xml("""
        <product>
            <id>42</id>
            <name>Keyboard</name>
        </product>
        """));
~~~

So sánh XML theo cấu trúc giúp test ít phụ thuộc cách xuống dòng và khoảng trắng. Spring Test sử dụng tiện ích so sánh XML phù hợp với thư viện XMLUnit khi kiểm tra nội dung XML; vì vậy cần có dependency XMLUnit tương ứng trên test classpath khi dùng matcher này.

Khi chọn cách so sánh, cần xác định thứ tự child element có thuộc contract hay không, và có cần phân biệt attribute với element hay không. Một XML document có thể biểu diễn dữ liệu tương tự nhưng cấu trúc khác nhau; test nên xác nhận đúng cấu trúc mà client phụ thuộc.

### 3.2. Truy vấn XML bằng XPath

XPath cho phép chọn node hoặc giá trị theo đường dẫn. Spring MVC Test cung cấp xpath matcher:

~~~java
mockMvc.perform(get("/api/catalog/42")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isOk())
    .andExpect(xpath("/product/id").string("42"))
    .andExpect(xpath("/product/name").string("Keyboard"));
~~~

Một số matcher thường dùng:

- node: kiểm tra node được chọn.
- nodeCount: kiểm tra số node.
- exists và doesNotExist: kiểm tra node có tồn tại hay không.
- string: kiểm tra giá trị dạng chuỗi.
- number: kiểm tra giá trị số.
- booleanValue: kiểm tra kết quả boolean của biểu thức XPath.

Ví dụ kiểm tra danh sách:

~~~java
mockMvc.perform(get("/api/catalog")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(xpath("/catalog/product").nodeCount(2))
    .andExpect(xpath("/catalog/product[1]/id").string("10"))
    .andExpect(xpath("/catalog/product[2]/id").string("20"));
~~~

XPath mặc định đếm vị trí node bắt đầu từ 1. Điều này khác với chỉ số mảng Java bắt đầu từ 0. Khi kiểm tra nhiều node, cần viết chỉ số đúng theo XPath.

### 3.3. XPath với namespace

XML có namespace cần khai báo prefix trong biểu thức XPath và ánh xạ prefix đó đến namespace URI. Prefix trong XPath không bắt buộc phải giống prefix được dùng trong document; điều quan trọng là URI phải khớp.

Ví dụ XML:

~~~xml
<p:product xmlns:p="urn:example:catalog">
    <p:id>42</p:id>
    <p:name>Keyboard</p:name>
</p:product>
~~~

Test có thể khai báo namespace map:

~~~java
Map<String, String> namespaces = Map.of(
    "p", "urn:example:catalog"
);

mockMvc.perform(get("/api/catalog/42")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(xpath("/p:product/p:id", namespaces).string("42"))
    .andExpect(xpath("/p:product/p:name", namespaces).string("Keyboard"));
~~~

Nếu bỏ qua namespace, biểu thức XPath có thể không tìm thấy node dù XML response chứa đúng element. Đây là nguyên nhân thường gặp khi test XML từ SOAP service hoặc API dùng namespace.

### 3.4. Kiểm tra attribute, node và số lượng

XPath có thể chọn attribute bằng ký hiệu @:

~~~xml
<product id="42" active="true">
    <name>Keyboard</name>
</product>
~~~

Các assertion tương ứng:

~~~java
mockMvc.perform(get("/api/catalog/42")
        .accept(MediaType.APPLICATION_XML))
    .andExpect(xpath("/product/@id").string("42"))
    .andExpect(xpath("/product/@active").string("true"))
    .andExpect(xpath("/product/name").exists())
    .andExpect(xpath("/product/description").doesNotExist());
~~~

Nếu chỉ cần xác nhận sự hiện diện của node, dùng exists hoặc node. Nếu cần kiểm tra nhiều node, dùng nodeCount. Nếu cần xác nhận giá trị, dùng string, number hoặc booleanValue để ý định được thể hiện rõ.

### 3.5. XML và khoảng trắng

XML parser có thể xử lý khoảng trắng giữa các element khác với khoảng trắng trong text node. Ví dụ, khoảng trắng thụt lề giữa các thẻ thường không phải dữ liệu nghiệp vụ; nhưng khoảng trắng bên trong một element text có thể là nội dung cần giữ.

Không nên chuẩn hóa chuỗi XML bằng cách xóa mọi khoảng trắng trước khi so sánh, vì thao tác đó có thể làm thay đổi nội dung text hợp lệ. Hãy dùng XML structural comparison hoặc XPath cho phần tử cần kiểm tra. Nếu khoảng trắng là một phần của contract, hãy viết assertion riêng cho text node đó.

## 4. Đọc và so sánh tài nguyên bằng Spring Resource

Spring định nghĩa interface Resource để truy cập tài nguyên theo một cách thống nhất. Thay vì buộc code phụ thuộc trực tiếp vào File, Resource cho phép làm việc với classpath, filesystem, URL hoặc servlet context.

Một số implementation thường gặp:

| Resource implementation | Nguồn tài nguyên | Trường hợp sử dụng |
|---|---|---|
| ClassPathResource | Classpath | File fixture trong src/test/resources |
| FileSystemResource | Filesystem | File ở một đường dẫn xác định |
| UrlResource | URL | Tài nguyên qua URL hoặc URI |
| ByteArrayResource | Mảng byte trong bộ nhớ | Nội dung nhị phân tạo trực tiếp trong test |
| InputStreamResource | InputStream có sẵn | Nguồn stream được cung cấp từ bên ngoài |
| ServletContextResource | Web application resource | Tài nguyên nằm trong ServletContext |

Resource cung cấp các thao tác như exists, isReadable, getInputStream, contentLength, getFilename và getURL. Không phải implementation nào cũng hỗ trợ mọi thao tác theo cùng cách.

### 4.1. Đọc fixture từ classpath

Đặt dữ liệu mẫu trong src/test/resources:

~~~text
src
└── test
    └── resources
        └── fixtures
            ├── product-response.json
            ├── catalog-response.xml
            └── sample-image.png
~~~

Đọc JSON fixture:

~~~java
Resource expectedJson = new ClassPathResource(
    "fixtures/product-response.json"
);

assertTrue(expectedJson.exists());
assertTrue(expectedJson.isReadable());

String expected = StreamUtils.copyToString(
    expectedJson.getInputStream(),
    StandardCharsets.UTF_8
);
~~~

Sau đó có thể dùng expected làm đầu vào cho content().json hoặc parse bằng ObjectMapper để xác nhận dữ liệu. Đóng stream sau khi đọc; có thể dùng try-with-resources:

~~~java
String expected;
try (InputStream input = expectedJson.getInputStream()) {
    expected = StreamUtils.copyToString(
        input,
        StandardCharsets.UTF_8
    );
}
~~~

ClassPathResource giúp test không phụ thuộc thư mục chạy hiện tại của Gradle hoặc IDE. Tài nguyên được tìm trên classpath nên phù hợp với fixture được đóng gói cùng test.

### 4.2. Đọc binary resource và so sánh byte

Với file nhị phân, đọc thành byte array:

~~~java
Resource expectedFile = new ClassPathResource(
    "fixtures/sample-image.png"
);

byte[] expectedBytes;
try (InputStream input = expectedFile.getInputStream()) {
    expectedBytes = StreamUtils.copyToByteArray(input);
}
~~~

Khi endpoint trả file, có thể so sánh response body:

~~~java
mockMvc.perform(get("/api/files/sample-image"))
    .andExpect(status().isOk())
    .andExpect(content().contentType(MediaType.IMAGE_PNG))
    .andExpect(content().bytes(expectedBytes));
~~~

So sánh byte xác nhận nội dung chính xác. Nếu file có metadata biến đổi theo lần tạo, ví dụ timestamp hoặc header động bên trong archive, so sánh toàn bộ byte có thể quá chặt. Khi đó, hãy đọc cấu trúc file bằng thư viện phù hợp và kiểm tra những phần thuộc contract.

### 4.3. Không phụ thuộc vào getFile()

Một lỗi thường gặp là gọi Resource.getFile() cho mọi loại tài nguyên. Method này chỉ hoạt động khi resource có thể được biểu diễn thành file hệ thống. Classpath resource nằm trong JAR hoặc resource đến từ URL/stream có thể không có file path thực.

Ưu tiên getInputStream() để đọc nội dung. Dùng getFile() khi test thực sự yêu cầu một file hệ thống và biết chắc resource có backing file phù hợp. Cách này giúp test chạy ổn định cả trong IDE, Gradle và môi trường đóng gói.

### 4.4. Dùng ResourceLoader

ResourceLoader cung cấp API để lấy Resource từ location string:

~~~java
ResourceLoader resourceLoader = new DefaultResourceLoader();

Resource jsonFixture =
    resourceLoader.getResource("classpath:fixtures/product-response.json");

Resource localFile =
    resourceLoader.getResource("file:build/test-output/report.json");
~~~

Một số prefix phổ biến:

- classpath: tìm trên classpath.
- file: truy cập file system.
- https: hoặc URL scheme phù hợp để truy cập tài nguyên từ xa.

Không có prefix thường được xử lý theo quy tắc mặc định của ResourceLoader. Khi viết test, nên dùng prefix rõ ràng để người đọc biết tài nguyên đến từ đâu. Với URL bên ngoài, tránh để test phụ thuộc internet hoặc dịch vụ không kiểm soát; hãy dùng fixture cục bộ hoặc server thử nghiệm.

## 5. So sánh JSON và XML lấy từ file fixture

Fixture giúp expected content dễ đọc, có thể tái sử dụng và không làm test method quá dài. Tuy nhiên, fixture phải phản ánh đúng contract của test và được lưu ở vị trí dễ tìm.

### 5.1. JSON fixture với content matcher

~~~java
@Test
void returnsProductDocument() throws Exception {
    // Arrange
    Resource fixture = new ClassPathResource(
        "fixtures/product-response.json"
    );
    String expected;
    try (InputStream input = fixture.getInputStream()) {
        expected = StreamUtils.copyToString(
            input,
            StandardCharsets.UTF_8
        );
    }

    // Act + Assert
    mockMvc.perform(get("/api/products/42"))
        .andExpect(status().isOk())
        .andExpect(content().json(expected, JSONCompareMode.STRICT));
}
~~~

Ví dụ sử dụng fixture JSON để so sánh toàn bộ contract. Nếu fixture lớn và chỉ vài field cần được bảo vệ, JSONPath có thể làm test ngắn và tập trung hơn.

### 5.2. XML fixture với structural matcher

~~~java
@Test
void returnsCatalogXml() throws Exception {
    // Arrange
    Resource fixture = new ClassPathResource(
        "fixtures/catalog-response.xml"
    );
    String expected;
    try (InputStream input = fixture.getInputStream()) {
        expected = StreamUtils.copyToString(
            input,
            StandardCharsets.UTF_8
        );
    }

    // Act + Assert
    mockMvc.perform(get("/api/catalog")
            .accept(MediaType.APPLICATION_XML))
        .andExpect(status().isOk())
        .andExpect(content().xml(expected));
}
~~~

Nếu chỉ cần xác nhận một node trong fixture lớn, có thể dùng XPath thay cho việc so sánh toàn bộ XML.

### 5.3. Tổ chức fixture theo mục đích

Nên đặt tên file phản ánh tình huống:

~~~text
fixtures/
├── product/
│   ├── product-active.json
│   └── product-not-found.json
├── catalog/
│   ├── catalog-with-items.xml
│   └── empty-catalog.xml
└── files/
    ├── sample-image.png
    └── report.csv
~~~

Không nên đặt tên chung như expected1.json hoặc data.xml vì khó biết fixture thuộc kịch bản nào. Nếu fixture chỉ dùng cho một test và rất ngắn, có thể khai báo trực tiếp trong test method. Khi nội dung dài hoặc được nhiều test dùng, file fixture giúp việc xem xét và cập nhật thuận tiện hơn.

## 6. Kiểm tra file upload và multipart resource

Spring Test cung cấp MockMultipartFile để mô phỏng một phần upload multipart trong các test MVC. Có thể chuẩn bị tên field, tên file, content type và byte content:

~~~java
MockMultipartFile file = new MockMultipartFile(
    "document",
    "report.csv",
    "text/csv",
    "id,name\n1,Ada\n".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/documents")
        .file(file))
    .andExpect(status().isCreated());
~~~

Ví dụ kiểm tra endpoint nhận file có field name là document. Khi cần xác nhận nội dung file đã được lưu hoặc xử lý đúng, hãy kiểm tra kết quả qua service, repository hoặc response theo hợp đồng của endpoint. Status CREATED một mình không chứng minh byte được lưu chính xác.

Với file lớn hoặc nhiều loại file, nên chuẩn bị fixture riêng và đọc bằng Resource:

~~~java
Resource csvFixture =
    new ClassPathResource("fixtures/files/report.csv");

byte[] content;
try (InputStream input = csvFixture.getInputStream()) {
    content = StreamUtils.copyToByteArray(input);
}

MockMultipartFile upload = new MockMultipartFile(
    "document",
    csvFixture.getFilename(),
    "text/csv",
    content
);
~~~

Khi test upload, nên kiểm tra các trường hợp có ý nghĩa như file rỗng, content type không được hỗ trợ, tên file không hợp lệ, kích thước vượt giới hạn và nội dung sai định dạng. MockMultipartFile mô phỏng dữ liệu multipart để test; nó không chứng minh browser hoặc mạng đã gửi multipart đúng trong môi trường thật.

## 7. Kiểm tra content type, encoding và header của tài nguyên

Nội dung đúng nhưng metadata sai vẫn có thể làm client xử lý sai. Khi kiểm tra endpoint trả file hoặc JSON/XML, hãy xác nhận cả metadata thuộc contract:

~~~java
mockMvc.perform(get("/api/reports/monthly"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_PDF
    ))
    .andExpect(header().exists(HttpHeaders.CONTENT_DISPOSITION))
    .andExpect(header().string(
        HttpHeaders.CONTENT_DISPOSITION,
        containsString("attachment")
    ));
~~~

Với text response, có thể xác nhận encoding và nội dung:

~~~java
mockMvc.perform(get("/api/reports/export.csv"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.parseMediaType("text/csv")
    ))
    .andExpect(content().encoding("UTF-8"))
    .andExpect(content().string(containsString("id,name")));
~~~

Content type có thể bao gồm parameter charset. Dùng contentTypeCompatibleWith khi chỉ cần tương thích với media type; dùng contentType khi cần khớp chính xác cả giá trị theo contract. Hãy tránh so sánh header đầy đủ nếu một phần của nó được phép thay đổi theo môi trường.

## 8. Dependency cần thiết cho các matcher

Các matcher JSON/XML trong Spring Test có thể cần thư viện hỗ trợ tương ứng trên test classpath. Spring Test tích hợp với các thư viện chuyên biệt thay vì tự định nghĩa lại toàn bộ parser và comparator.

| Khả năng | Thư viện thường dùng | Vai trò |
|---|---|---|
| So sánh JSON qua content().json | JSONassert | So sánh cấu trúc JSON và chế độ strict/lenient |
| JSONPath matcher | Jayway JsonPath | Truy vấn field và node JSON |
| So sánh XML qua content().xml | XMLUnit | So sánh XML theo cấu trúc |
| XPath matcher | API XPath và hỗ trợ của Spring Test | Truy vấn node/giá trị XML |
| Đọc fixture Resource | Spring Core | Truy cập classpath, filesystem và resource abstraction |

Trong dự án Spring Boot, starter test thường đưa vào nhiều thư viện test phổ biến, nhưng không nên giả định mọi thư viện tùy chọn đều có mặt trong mọi cấu hình. Nếu một matcher báo thiếu class hoặc không thể tạo parser, hãy kiểm tra dependency test runtime và phiên bản tương thích trong dependency management của dự án.

Ví dụ khai báo Gradle ở mức khái niệm:

~~~groovy
dependencies {
    testImplementation "org.springframework.boot:spring-boot-starter-test"

    // Chỉ thêm thư viện riêng nếu dependency graph của dự án chưa cung cấp.
    testImplementation "org.skyscreamer:jsonassert"
    testImplementation "com.jayway.jsonpath:json-path"
    testImplementation "org.xmlunit:xmlunit-core"
}
~~~

Các phiên bản nên được quản lý bởi Spring Boot dependency management hoặc version catalog hiện có. Tránh tự ghim phiên bản khác với bộ dependency của dự án khi chưa kiểm tra tương thích.

## 9. Viết assertion dễ chẩn đoán

Một assertion tốt cần cho biết test đang bảo vệ điều gì và giúp xác định nhanh sai khác. Có thể áp dụng một số nguyên tắc:

- Dùng JSONPath cho field quan trọng thay vì so sánh một chuỗi JSON dài nếu chỉ một phần response thuộc contract.
- Dùng JSON structural comparison khi cần bảo vệ toàn bộ response schema.
- Dùng XPath để chọn đúng node, nhất là XML có namespace.
- Dùng Resource để nạp fixture từ classpath, không ghép đường dẫn tương đối phụ thuộc working directory.
- Với file nhị phân, kiểm tra byte và metadata cần thiết.
- Khi response có giá trị động, kiểm tra field ổn định bằng JSONPath/XPath hoặc tách phần động trước khi so sánh.
- Khi assertion thất bại, giữ expected fixture và actual response đủ rõ để xác định sai khác.

Nếu JSON/XML chứa timestamp, id sinh tự động hoặc URL theo host hiện tại, không nên sửa expected bằng cách đoán giá trị. Có thể kiểm tra định dạng, kiểu dữ liệu, quan hệ hoặc phần ổn định của giá trị đó. Nếu giá trị phải cố định theo contract, hãy điều khiển clock hoặc dữ liệu sinh trong test.

### 9.1. Tránh kiểm tra quá nhiều chi tiết không thuộc contract

Một response có thể chứa metadata nội bộ được bổ sung theo thời gian. Nếu API cho phép mở rộng, kiểm tra toàn bộ response bằng STRICT có thể tạo chi phí bảo trì cao. Ngược lại, nếu API là schema đóng hoặc response phải được client tiêu thụ theo cấu trúc chính xác, strict comparison là bảo vệ có ích.

Hãy chọn assertion từ góc nhìn của consumer:

- Consumer cần biết field nào?
- Field có thể vắng mặt hoặc null không?
- Mảng có thứ tự ổn định không?
- XML namespace có phải một phần của contract không?
- File tải xuống phải giống byte tuyệt đối hay chỉ cùng nội dung logic?

### 9.2. Tránh dùng một fixture cho nhiều ý nghĩa

Nếu cùng một fixture được dùng cho nhiều test có mục tiêu khác nhau, một thay đổi nhỏ có thể làm nhiều test thất bại và khó xác định test nào đang bảo vệ contract nào. Tách fixture theo tình huống hoặc dùng builder tạo dữ liệu có tên rõ ràng.

## 10. Các lỗi thường gặp

### 10.1. So sánh JSON bằng chuỗi nguyên văn

JSON có thể hợp lệ dù khoảng trắng hoặc thứ tự key khác nhau. Dùng content().string khi định dạng chính xác là yêu cầu; dùng content().json hoặc JSONPath khi cần kiểm tra cấu trúc.

### 10.2. Dùng LENIENT mà không hiểu ý nghĩa

LENIENT cho phép field thừa và không yêu cầu thứ tự mảng. Điều này có thể bỏ qua một thay đổi không mong muốn nếu contract yêu cầu cấu trúc đóng hoặc thứ tự cụ thể. Chọn chế độ theo yêu cầu API.

### 10.3. Quên namespace trong XPath

XPath không tự tìm được element có namespace chỉ bằng local name trong mọi trường hợp. Khai báo namespace map và dùng prefix trong biểu thức.

### 10.4. Nhầm vị trí mảng JSON và node XML

JSONPath thường dùng chỉ số mảng bắt đầu từ 0, còn XPath dùng vị trí node bắt đầu từ 1. Hãy kiểm tra chỉ số khi chuyển assertion giữa hai định dạng.

### 10.5. Dùng getFile() cho classpath resource trong JAR

Resource có thể không có file hệ thống. Dùng getInputStream() để đọc nội dung theo cách tổng quát.

### 10.6. Đọc InputStreamResource nhiều lần

InputStreamResource thường đại diện cho stream có thể chỉ đọc một lần. Nếu cần đọc nhiều lần, hãy dùng resource có thể mở stream mới hoặc lưu byte vào ByteArrayResource.

### 10.7. Chỉ kiểm tra status khi tải file

Status 200 không chứng minh body đúng. Hãy kiểm tra content type, header tải xuống và byte hoặc cấu trúc nội dung phù hợp.

### 10.8. Bỏ qua encoding

Đọc file bằng charset mặc định của máy có thể làm test khác nhau giữa môi trường. Chỉ định UTF-8 hoặc charset thuộc contract khi chuyển byte thành chuỗi.

### 10.9. Fixture phụ thuộc đường dẫn local

Đường dẫn tuyệt đối trên máy cá nhân không ổn định trong CI. Đặt fixture trong src/test/resources và dùng ClassPathResource.

## 11. Mẫu kết hợp JSONPath, XPath và Resource

Một MVC test có thể dùng nhiều tiện ích theo mục tiêu của từng endpoint. Ví dụ với JSON:

~~~java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ProductService productService;

    @Test
    void returnsProductFields() throws Exception {
        given(productService.findById(42L))
            .willReturn(new ProductDto(42L, "Keyboard", true));

        mockMvc.perform(get("/api/products/42"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.name").value("Keyboard"))
            .andExpect(jsonPath("$.active").value(true));
    }
}
~~~

Ví dụ giả định controller và DTO có các method tương ứng. JSONPath làm rõ các field mà endpoint cần trả về. Nếu cần bảo vệ toàn bộ JSON contract, có thể thay hoặc bổ sung bằng content().json với expected fixture.

Với XML:

~~~java
@WebMvcTest(CatalogController.class)
class CatalogControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsCatalogElements() throws Exception {
        mockMvc.perform(get("/api/catalog")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isOk())
            .andExpect(xpath("/catalog/product").nodeCount(2))
            .andExpect(xpath("/catalog/product[1]/id").string("10"));
    }
}
~~~

Với tài nguyên nhị phân:

~~~java
@Test
void downloadsExpectedFile() throws Exception {
    Resource fixture =
        new ClassPathResource("fixtures/sample-image.png");

    byte[] expected;
    try (InputStream input = fixture.getInputStream()) {
        expected = StreamUtils.copyToByteArray(input);
    }

    mockMvc.perform(get("/api/files/sample-image"))
        .andExpect(status().isOk())
        .andExpect(content().contentType(MediaType.IMAGE_PNG))
        .andExpect(content().bytes(expected));
}
~~~

Ba ví dụ có cùng cấu trúc: chuẩn bị dữ liệu mong đợi, gửi request qua MockMvc và xác nhận response. Phần matcher thay đổi theo bản chất nội dung.

## 12. Quy trình chọn tiện ích

Khi viết test cho một endpoint hoặc component trả dữ liệu, có thể tiến hành theo thứ tự:

1. Xác định media type và dạng nội dung: JSON, XML, text hay binary.
2. Xác định contract cần bảo vệ: toàn bộ cấu trúc, một vài field/node hay byte chính xác.
3. Chọn matcher: JSON comparison, JSONPath, XML comparison, XPath, string hoặc bytes.
4. Nếu expected content dài, đặt fixture trong src/test/resources và nạp bằng Resource.
5. Xác nhận content type, encoding và header tải xuống khi chúng thuộc contract.
6. Chạy test trong cấu hình build của dự án để phát hiện dependency test còn thiếu.

Với JSON, dùng structural comparison khi toàn bộ schema quan trọng và JSONPath khi chỉ một số field cần kiểm tra. Với XML, dùng XML comparison cho toàn document và XPath cho node hoặc giá trị cụ thể, đồng thời xử lý namespace rõ ràng. Với tài nguyên, dùng Resource để đọc nguồn dữ liệu và chọn so sánh chuỗi hoặc byte theo đúng loại nội dung.

## Kết luận

Spring Test kết hợp các matcher JSON/XML của MockMvc với JSONPath, XPath và Resource abstraction để kiểm tra response ở đúng mức cấu trúc. JSON nên được so sánh theo contract hoặc truy vấn field; XML nên được so sánh theo cấu trúc hoặc chọn node bằng XPath; file fixture và tài nguyên tải xuống nên được đọc qua Resource rồi kiểm tra nội dung cùng metadata cần thiết. Chọn đúng cách so sánh giúp test diễn đạt rõ kỳ vọng của client và giảm lỗi do khác biệt định dạng không có ý nghĩa.
