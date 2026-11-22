# XPath và nội dung XML

## 1. Xác nhận response XML trong kiểm thử MVC

Khi kiểm thử một endpoint Spring MVC trả về XML, cần xác nhận cả cấu trúc dữ liệu lẫn giá trị mà client thực sự nhận được. `MockMvc` cung cấp hai nhóm matcher phù hợp:

- `content().xml(...)` so sánh toàn bộ response body với một tài liệu XML mong đợi.
- `xpath(...)` đánh giá một biểu thức XPath trên response body và kiểm tra kết quả như chuỗi, số, boolean hoặc số lượng node.

Hai cách kiểm tra bổ trợ cho nhau. So sánh XML giúp phát hiện phần tử hoặc thuộc tính bị thiếu, thừa hay sai giá trị trên toàn tài liệu. XPath tập trung vào một điều kiện cụ thể, chẳng hạn một mã định danh, tổng số phần tử hoặc nội dung của một node quan trọng.

Các matcher này thường được dùng sau `status()` và matcher content type trong một chuỗi `mockMvc.perform(...).andExpect(...)`. Chúng kiểm tra response được tạo ra qua luồng xử lý MVC, thay vì chỉ gọi trực tiếp phương thức controller.

## 2. Chuẩn bị endpoint trả về XML

Ví dụ dưới đây dùng controller trả về một chuỗi XML. Khai báo `produces` giúp Spring MVC công bố media type của response là `application/xml`.

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {

    @GetMapping(value = "/catalog", produces = MediaType.APPLICATION_XML_VALUE)
    String catalog() {
        return """
                <?xml version="1.0" encoding="UTF-8"?>
                <catalog>
                    <book id="bk-1">
                        <title>Spring MVC Testing</title>
                        <price>29.5</price>
                    </book>
                    <book id="bk-2">
                        <title>XML in Practice</title>
                        <price>35.0</price>
                    </book>
                </catalog>
                """;
    }
}
```

Ở ví dụ này controller trả về `String`, nên body là nội dung XML đã được tạo sẵn. Trong ứng dụng thực tế, controller cũng có thể trả về object được một XML message converter tuần tự hóa. Dù dùng cách nào, kiểm thử MVC vẫn nên xác nhận media type và nội dung cuối cùng trên response.

## 3. So sánh toàn bộ XML bằng `content().xml()`

`content().xml(expectedXml)` nhận một chuỗi XML mong đợi và so sánh nó với body của response. Spring sử dụng XMLUnit để thực hiện phép so sánh XML. Việc so sánh dựa trên cấu trúc XML, vì vậy khác biệt về cách thụt lề hoặc khoảng trắng định dạng thường không làm test thất bại. Đây không phải phép so sánh byte hoặc so sánh chuỗi nguyên văn.

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(CatalogController.class)
class CatalogControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsExpectedCatalogXml() throws Exception {
        String expectedXml = """
                <catalog>
                    <book id="bk-1">
                        <title>Spring MVC Testing</title>
                        <price>29.5</price>
                    </book>
                    <book id="bk-2">
                        <title>XML in Practice</title>
                        <price>35.0</price>
                    </book>
                </catalog>
                """;

        mockMvc.perform(get("/catalog").accept(MediaType.APPLICATION_XML))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_XML))
                .andExpect(content().xml(expectedXml));
    }
}
```

`contentTypeCompatibleWith(...)` xác nhận response có media type tương thích với `application/xml`, kể cả khi header có thêm tham số như charset. `content().xml(...)` tiếp tục xác nhận body có cấu trúc và dữ liệu như mong đợi.

Vì phép so sánh XML của Spring Test dựa vào XMLUnit, dự án cần có `xmlunit-core` trên test runtime classpath. Nếu dependency này chưa được cung cấp bởi cấu hình test hoặc dependency management hiện tại, có thể khai báo trong Gradle:

```groovy
dependencies {
    testImplementation("org.xmlunit:xmlunit-core")
}
```

Khi dùng Spring Boot dependency management, để BOM quản lý phiên bản nếu artifact đó đã được quản lý; nếu không, khai báo phiên bản tương thích với dependency set của dự án.

## 4. Chọn dữ liệu bằng XPath

XPath biểu diễn đường dẫn hoặc phép tính trên tài liệu XML. Trong MockMvc, static method `xpath(...)` của `MockMvcResultMatchers` tạo một `XpathResultMatchers` để kiểm tra kết quả của biểu thức trên response body.

Một số matcher thường dùng:

| Matcher | Kết quả XPath được kiểm tra | Ví dụ |
|---|---|---|
| `string(expected)` | Giá trị chuỗi của biểu thức | `xpath("/catalog/book[1]/title").string("Spring MVC Testing")` |
| `number(expected)` | Giá trị số | `xpath("count(/catalog/book)").number(2.0)` |
| `booleanValue(expected)` | Giá trị boolean | `xpath("boolean(/catalog/book[@id='bk-1'])").booleanValue(true)` |
| `nodeCount(expected)` | Số node được biểu thức chọn | `xpath("/catalog/book").nodeCount(2)` |

Ví dụ kết hợp nhiều điều kiện trên cùng một response:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.xpath;

@Test
void exposesExpectedBookFields() throws Exception {
    mockMvc.perform(get("/catalog").accept(MediaType.APPLICATION_XML))
            .andExpect(status().isOk())
            .andExpect(xpath("/catalog/book").nodeCount(2))
            .andExpect(xpath("/catalog/book[@id='bk-1']/title")
                    .string("Spring MVC Testing"))
            .andExpect(xpath("/catalog/book[@id='bk-2']/price")
                    .string("35.0"))
            .andExpect(xpath("count(/catalog/book)").number(2.0))
            .andExpect(xpath("boolean(/catalog/book[@id='bk-1'])")
                    .booleanValue(true));
}
```

Biểu thức `/catalog/book[@id='bk-1']/title` chọn phần tử `title` thuộc `book` có thuộc tính `id` bằng `bk-1`. `string(...)` kiểm tra giá trị văn bản của node được chọn. Biểu thức `count(...)` trả về số node phù hợp, còn `boolean(...)` chuyển kết quả thành giá trị logic.

`nodeCount(...)` hữu ích khi cần xác nhận tập node được chọn có đúng số lượng. Nếu muốn xác nhận không có phần tử phù hợp, có thể dùng `nodeCount(0)` trên biểu thức tương ứng.

## 5. Làm việc với XML namespace

XML namespace ảnh hưởng trực tiếp đến cách XPath chọn node. Xét tài liệu dùng namespace mặc định:

```xml
<catalog xmlns="urn:example:catalog">
    <book id="bk-1">
        <title>Spring MVC Testing</title>
    </book>
</catalog>
```

Mặc dù tài liệu không viết prefix trước `catalog` và `book`, các phần tử này vẫn thuộc namespace URI `urn:example:catalog`. Biểu thức `/catalog/book` không tự động khớp với chúng vì XPath không tự kế thừa namespace mặc định của tài liệu.

Hãy cung cấp ánh xạ prefix sang namespace URI khi tạo matcher:

```java
import java.util.Map;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.xpath;

@Test
void selectsElementsInDefaultNamespace() throws Exception {
    Map<String, String> namespaces = Map.of(
            "c", "urn:example:catalog");

    mockMvc.perform(get("/catalog").accept(MediaType.APPLICATION_XML))
            .andExpect(xpath("/c:catalog/c:book", namespaces).nodeCount(1))
            .andExpect(xpath("/c:catalog/c:book/c:title", namespaces)
                    .string("Spring MVC Testing"));
}
```

Prefix `c` là tên do bài kiểm thử chọn. Nó chỉ cần được ánh xạ đến đúng namespace URI; không bắt buộc phải trùng prefix được dùng trong XML response. Quy tắc này cũng áp dụng khi XML dùng prefix khác nhau cho cùng một namespace URI.

Khi XPath không tìm thấy node trong một tài liệu có namespace, hãy kiểm tra namespace URI và map prefix trước khi kết luận controller trả về sai cấu trúc. Đây là nguyên nhân phổ biến khiến `nodeCount(0)` hoặc matcher chuỗi cho kết quả bất ngờ.

## 6. Chọn giữa XML matcher và XPath matcher

| Nhu cầu kiểm thử | Matcher phù hợp | Lý do |
|---|---|---|
| Xác nhận toàn bộ cấu trúc và dữ liệu XML | `content().xml(expectedXml)` | Một assertion kiểm tra tài liệu XML tổng thể. |
| Kiểm tra một trường quan trọng | `xpath(...).string(...)` | Chỉ rõ node và giá trị cần xác nhận. |
| Kiểm tra số lượng phần tử | `xpath(...).nodeCount(...)` | Kiểm tra trực tiếp tập node được chọn. |
| Kiểm tra điều kiện hoặc phép tính | `xpath(...).booleanValue(...)` hoặc `number(...)` | Diễn đạt điều kiện bằng biểu thức XPath. |
| Kiểm tra body đúng từng ký tự hoặc byte | `content().string(...)` hoặc `content().bytes(...)` | Dùng khi khoảng trắng, thứ tự ký tự hoặc encoding là một phần của hợp đồng cần kiểm tra. |

Không cần lặp lại mọi dữ liệu bằng cả XML matcher và nhiều XPath matcher nếu một phép so sánh toàn tài liệu đã thể hiện đầy đủ yêu cầu. Ngược lại, XPath rất hữu ích khi test cần nêu rõ một quy tắc nghiệp vụ hoặc khi chỉ một phần của tài liệu là quan trọng đối với trường hợp kiểm thử.

Có thể kết hợp hai nhóm matcher trong cùng test khi chúng trả lời hai câu hỏi khác nhau: `content().xml(...)` xác nhận response XML tổng thể, còn XPath xác nhận một điều kiện nổi bật mà người đọc test cần nhìn thấy rõ.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `content().xml(...)` báo thiếu XMLUnit hoặc không tạo được XML diff | `xmlunit-core` không có trên test runtime classpath. | Kiểm tra dependency test và thêm `org.xmlunit:xmlunit-core` nếu cần. |
| Matcher XPath không phân tích được response | Body rỗng, XML sai cú pháp hoặc response chứa nội dung không phải XML. | Kiểm tra status, body thực tế, ký tự escape và cấu trúc đóng/mở tag. |
| XPath chọn được 0 node dù XML có phần tử | Biểu thức sai đường dẫn hoặc thiếu namespace mapping. | Kiểm tra tên node, phân biệt hoa thường và namespace URI; cung cấp map prefix cho XPath. |
| `string(...)` trả về chuỗi rỗng | Biểu thức chọn sai node hoặc node không có text value như dự kiến. | Kiểm tra lại đường dẫn, predicate và cấu trúc lồng nhau; dùng `nodeCount(...)` để xác nhận node có được chọn hay không. |
| XML matcher thất bại dù hai tài liệu nhìn gần giống nhau | Có khác biệt thực về text, thuộc tính, phần tử hoặc namespace; cũng có thể expected XML chưa phản ánh response. | Đọc chi tiết diff do XMLUnit cung cấp và so sánh node/attribute tương ứng. |
| Test mong đợi `application/xml` nhưng media type khác | Controller hoặc message converter tạo response với media type khác. | Kiểm tra `produces`, `Accept` header và cấu hình converter; xác nhận hợp đồng API mong muốn. |

Một số lưu ý khi viết XPath:

- Tên phần tử và thuộc tính trong XML phân biệt chữ hoa, chữ thường.
- Thuộc tính được chọn bằng cú pháp `@id`; predicate đặt trong dấu ngoặc vuông, ví dụ `book[@id='bk-1']`.
- XPath `string(...)` trả về giá trị chuỗi của biểu thức. Với node element, đó là string-value của node, gồm text node bên trong theo quy tắc XPath.
- XPath làm việc với cây XML đã phân tích cú pháp, nên thứ tự thuộc tính và cách thụt lề không phải cách phù hợp để xác nhận nội dung byte-for-byte.
- Nếu khoảng trắng trong text có ý nghĩa nghiệp vụ, hãy xác nhận giá trị cụ thể bằng XPath hoặc matcher chuỗi phù hợp; đừng dựa vào việc XML comparison có thể bỏ qua whitespace định dạng.

## 8. Quy trình viết một kiểm thử XML dễ đọc

Khi viết test cho endpoint XML, có thể đi theo trình tự sau:

1. Gửi request với `Accept: application/xml` nếu client yêu cầu XML.
2. Xác nhận HTTP status để biết request được xử lý đúng trạng thái mong đợi.
3. Xác nhận response content type tương thích với `application/xml`.
4. Dùng `content().xml(...)` nếu cần xác nhận tài liệu tổng thể.
5. Thêm XPath matcher cho các quy tắc quan trọng như node bắt buộc, số lượng bản ghi, giá trị field hoặc namespace.
6. Khi test thất bại, đọc response body và thông tin diff/XPath để xác định lỗi nằm ở status, media type, cú pháp XML, namespace hay dữ liệu.

Ví dụ hoàn chỉnh ở trên sử dụng `@WebMvcTest` để nạp lớp controller cùng hạ tầng MVC cần thiết. Nếu ứng dụng có cấu hình converter, filter hoặc thành phần bảo mật ảnh hưởng đến response và cần được kiểm thử cùng nhau, có thể chọn một Spring test context rộng hơn. Các matcher `content()` và `xpath()` vẫn được dùng trên kết quả `MockMvc`.

## 9. Kết luận

Trong Spring MVC Test, `content().xml(...)` xác nhận response body tương đương với XML mong đợi ở mức cấu trúc, còn `xpath(...)` kiểm tra chính xác node hoặc điều kiện cần quan tâm. Hãy xác nhận status và content type trước, sau đó chọn matcher theo phạm vi hợp đồng cần bảo vệ. Với tài liệu có namespace, luôn ánh xạ prefix trong XPath đến namespace URI tương ứng để biểu thức chọn đúng node.
