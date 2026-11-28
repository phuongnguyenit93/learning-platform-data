# Xây dựng công cụ chỉ đọc với đầu vào và kết quả đơn giản

Một cách dễ tiếp cận tool calling là bắt đầu bằng một công cụ chỉ đọc: nhận một mã định danh, tra cứu dữ liệu nghiệp vụ và trả về một kết quả ngắn. Ví dụ trong bài này là công cụ tra cứu sản phẩm theo mã SKU. Người dùng hỏi giá hoặc tình trạng còn hàng; mô hình có thể chọn công cụ, gửi mã SKU, nhận thông tin sản phẩm rồi diễn đạt câu trả lời.

Trong Spring AI, ta có thể đánh dấu một phương thức Java bằng **@Tool**, mô tả tham số bằng **@ToolParam** và cung cấp đối tượng chứa phương thức đó cho **ChatClient**. Spring AI công bố định nghĩa công cụ cho mô hình, nhận yêu cầu gọi và điều phối việc thực thi phương thức. Phần mã Java vẫn gọi dịch vụ nghiệp vụ hiện có để đọc dữ liệu.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

- Xác định một thao tác nghiệp vụ phù hợp để làm tool chỉ đọc.
- Viết phương thức Java nhận một tham số đơn giản và trả về kết quả dễ hiểu.
- Dùng **@Tool** để đặt tên, mô tả mục đích và công bố phương thức.
- Dùng **@ToolParam** để mô tả dữ liệu mô hình cần cung cấp.
- Đưa đối tượng tool vào yêu cầu **ChatClient** và hiểu đường đi của kết quả.
- Kiểm tra đầu vào, quyền truy cập và dữ liệu trả về ở phía ứng dụng.

Ví dụ dùng một dịch vụ danh mục sản phẩm đã có sẵn. Công cụ chỉ tra cứu sản phẩm theo SKU; nó không tạo đơn hàng, cập nhật giá hay thay đổi số lượng tồn kho.

## 2. Chọn một thao tác đọc rõ ràng

Một tool đầu tiên nên có phạm vi nhỏ và kết quả có thể kiểm tra bằng mắt. Ta chọn thao tác:

| Thành phần | Giá trị của ví dụ |
| --- | --- |
| Tên tool | **lookup_product** |
| Mục đích | Tra cứu một sản phẩm theo SKU |
| Đầu vào | Một chuỗi **sku** |
| Kết quả | Mã, tên, giá và tình trạng còn hàng |
| Tác động dữ liệu | Chỉ đọc |

Mô hình không cần biết cách ứng dụng truy vấn cơ sở dữ liệu, gọi repository hay dùng cache. Mô hình chỉ cần hiểu rằng có thể yêu cầu tra cứu một sản phẩm bằng SKU. Phương thức Java chịu trách nhiệm gọi dịch vụ nghiệp vụ và trả lại dữ liệu cần thiết.

Không nên bắt đầu bằng một tool có nhiều tham số tùy chọn, nhiều nhánh nghiệp vụ hoặc thao tác ghi dữ liệu. Một công cụ đọc nhỏ giúp kiểm tra riêng từng mắt xích: mô hình có chọn đúng công cụ không, đối số có đúng không, mã Java có đọc đúng dữ liệu không và kết quả có đủ rõ để mô hình trả lời không.

## 3. Chuẩn bị dữ liệu nghiệp vụ

Giả sử ứng dụng đã có dịch vụ tra cứu sản phẩm. Hợp đồng tối thiểu có thể là:

~~~java
import java.math.BigDecimal;
import java.util.Optional;

public record Product(
    String sku,
    String name,
    BigDecimal priceVnd,
    boolean inStock
) {}

public interface ProductCatalogService {
    Optional<Product> findBySku(String sku);
}
~~~

Trong dự án Java, đặt **Product** và **ProductCatalogService** ở hai file riêng tương ứng với tên kiểu. Đoạn mã trên trình bày hai hợp đồng liên quan trong cùng một ví dụ để dễ theo dõi.

Trong ứng dụng thực tế, phương thức **findBySku** có thể gọi repository hoặc một dịch vụ danh mục khác. Bài học này tập trung vào lớp tool nên không phụ thuộc vào cách lưu trữ cụ thể.

Điểm quan trọng là tool gọi dịch vụ nghiệp vụ thay vì tự nhúng truy vấn dữ liệu vào lớp tích hợp AI. Cách tách này giúp cùng một quy tắc tra cứu được dùng từ REST API, giao diện người dùng, tác vụ nền và tool của mô hình. Dịch vụ nghiệp vụ cũng là nơi thích hợp để áp dụng phạm vi dữ liệu, kiểm tra quyền và các quy tắc của hệ thống.

## 4. Viết phương thức tool đầu tiên

Tạo một lớp Spring bean chứa phương thức cần công bố cho mô hình. Ví dụ sau dùng một tham số chuỗi và trả về chuỗi mô tả ngắn:

~~~java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

@Component
public class ProductLookupTools {

    private final ProductCatalogService productCatalogService;

    public ProductLookupTools(ProductCatalogService productCatalogService) {
        this.productCatalogService = productCatalogService;
    }

    @Tool(
        name = "lookup_product",
        description = """
            Tra cứu thông tin cơ bản của một sản phẩm theo mã SKU.
            Dùng khi người dùng hỏi tên, giá hoặc tình trạng còn hàng
            của sản phẩm. Công cụ chỉ đọc dữ liệu, không tạo đơn hàng
            và không cập nhật thông tin sản phẩm.
            """
    )
    public String lookupProduct(
            @ToolParam(
                description = "Mã SKU của sản phẩm, ví dụ SKU-100"
            ) String sku) {

        return productCatalogService.findBySku(sku)
            .map(product ->
                "SKU: " + product.sku()
                    + "\nTên: " + product.name()
                    + "\nGiá: " + product.priceVnd().toPlainString() + " VND"
                    + "\nCòn hàng: " + (product.inStock() ? "Có" : "Không")
            )
            .orElse("Không tìm thấy sản phẩm có SKU " + sku + ".");
    }
}
~~~

Có ba phần cần chú ý:

1. **@Tool** đánh dấu phương thức là một công cụ có thể được mô hình yêu cầu gọi. Thuộc tính **name** là định danh ổn định; **description** giải thích khi nào công cụ phù hợp và nó có tác động gì.
2. **@ToolParam** mô tả tham số đầu vào. Trong ví dụ, mô hình cần cung cấp một chuỗi SKU. Spring AI dùng chữ ký phương thức và annotation để tạo schema đầu vào cho tool.
3. Thân phương thức gọi **ProductCatalogService** và chuyển kết quả thành thông tin ngắn. Nó không tự quyết định câu trả lời cuối cùng cho người dùng; mô hình sẽ nhận kết quả tool rồi tạo câu trả lời.

Tên tham số và mô tả nên nói đúng dữ liệu cần gửi. Nếu tham số là mã SKU, đừng mô tả chung chung là “thông tin sản phẩm”. Ví dụ định dạng như **SKU-100** giúp mô hình hiểu hình dạng của giá trị cần tạo.

### Vì sao chọn kết quả dạng String?

Một chuỗi là kiểu trả về dễ quan sát trong bài đầu tiên. Nó cho phép ta kiểm tra trực tiếp thông tin mà công cụ gửi lại cho mô hình. Với dữ liệu có cấu trúc lớn hơn, có thể trả về một DTO hoặc record để Spring AI chuyển đổi kết quả theo cấu hình converter của ứng dụng. Dù dùng kiểu nào, chỉ nên trả các trường cần thiết cho yêu cầu hiện tại.

Ví dụ trên định dạng giá bằng **toPlainString()** để giữ biểu diễn số thập phân và ghi rõ đơn vị VND. Nó cũng trả về thông báo rõ ràng khi không tìm thấy SKU. Trong hệ thống thật, cần thống nhất định dạng tiền tệ, ngôn ngữ và cách biểu diễn lỗi với các tool khác.

## 5. Đưa tool vào yêu cầu ChatClient

Có phương thức được đánh dấu **@Tool** chưa có nghĩa là mọi yêu cầu chat đều tự động nhìn thấy nó. Ứng dụng cần cung cấp đối tượng chứa tool cho yêu cầu hiện tại. Với **ChatClient**, có thể dùng phương thức **tools(...)**:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;

@Service
public class ProductAssistant {

    private final ChatClient chatClient;
    private final ProductLookupTools productLookupTools;

    public ProductAssistant(
            ChatClient.Builder chatClientBuilder,
            ProductLookupTools productLookupTools) {
        this.chatClient = chatClientBuilder.build();
        this.productLookupTools = productLookupTools;
    }

    public String answer(String question) {
        return chatClient.prompt()
            .user(question)
            .tools(productLookupTools)
            .call()
            .content();
    }
}
~~~

Khi người dùng hỏi “Sản phẩm SKU-100 giá bao nhiêu và còn hàng không?”, ứng dụng gọi **answer(...)**. Đối tượng **productLookupTools** được đính kèm vào prompt nên Spring AI có thể công bố tool definition tương ứng trong yêu cầu gửi đến mô hình.

Nếu mô hình thấy câu hỏi phù hợp với mô tả của **lookup_product**, nó có thể tạo tool call với đối số tương tự:

~~~json
{
  "sku": "SKU-100"
}
~~~

Đây là dữ liệu minh họa cho lời gọi. Trong ứng dụng, Spring AI xử lý việc chuyển đối số sang tham số phương thức. Mô hình không gửi một đoạn Java để chạy; nó gửi tên tool và dữ liệu đầu vào theo schema đã công bố.

## 6. Theo dõi một lượt gọi từ đầu đến cuối

Luồng cơ bản của ví dụ có thể mô tả như sau:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant App as Ứng dụng / ChatClient
    participant Model as Mô hình
    participant Tool as ProductLookupTools
    participant Service as ProductCatalogService

    User->>App: Hỏi giá và tình trạng SKU-100
    App->>Model: Prompt kèm tool definition
    Model-->>App: Tool call lookup_product(sku)
    App->>Tool: Thực thi phương thức với SKU
    Tool->>Service: findBySku(sku)
    Service-->>Tool: Product hoặc không tìm thấy
    Tool-->>App: Kết quả dạng String
    App->>Model: Gửi kết quả tool trở lại
    Model-->>App: Câu trả lời cho người dùng
    App-->>User: Hiển thị nội dung trả lời
~~~

Hãy phân biệt hai phản hồi:

- **Tool result** là dữ liệu do phương thức Java trả về, ví dụ tên sản phẩm, giá và tình trạng còn hàng.
- **Final answer** là nội dung mô hình tạo ra sau khi nhận tool result, ví dụ “Sản phẩm SKU-100 đang có hàng và có giá 125000 VND.”

Một yêu cầu chat có thể kết thúc mà không gọi tool nếu mô hình đánh giá công cụ không phù hợp hoặc không cần thiết. Việc mô hình có gọi tool hay không phụ thuộc vào nội dung câu hỏi, mô tả tool, cấu hình lựa chọn tool và khả năng tool calling của model đang dùng. Nếu cần bắt buộc một tool trong tình huống cụ thể, hãy tìm hiểu cơ chế tool choice của model và API Spring AI tương ứng với phiên bản dự án.

Trong luồng do **ChatClient** điều phối, ứng dụng nhận nội dung cuối cùng qua **.call().content()**. Ở mức tích hợp thấp hơn, nếu tự xử lý message và tool call, ứng dụng cần tự thực hiện chu trình nhận yêu cầu, gọi callback, đưa tool result trở lại hội thoại và tiếp tục yêu cầu mô hình.

## 7. Kiểm tra đầu vào và giới hạn quyền đọc

JSON Schema giúp mô hình tạo đối số theo cấu trúc mong đợi. Nó không bảo đảm dữ liệu đúng với nghiệp vụ. Phương thức và dịch vụ vẫn phải kiểm tra đầu vào trước khi truy vấn.

Với SKU, ứng dụng có thể xác minh:

- Giá trị không rỗng và không chỉ chứa khoảng trắng.
- Độ dài và định dạng đúng quy ước SKU của hệ thống.
- Sản phẩm thuộc phạm vi dữ liệu mà người dùng hiện tại được phép xem.
- Dịch vụ xử lý trường hợp SKU không tồn tại một cách nhất quán.

Ví dụ, nếu SKU có định dạng cố định, có thể kiểm tra bằng Bean Validation ở lớp biên hoặc bằng quy tắc trong dịch vụ nghiệp vụ. Không nên dựa vào **@ToolParam** như một bộ xác thực dữ liệu hoàn chỉnh. Annotation chủ yếu giúp mô tả schema cho mô hình; kiểm tra ở server vẫn là bắt buộc.

Đối với dữ liệu nhiều tenant hoặc dữ liệu riêng tư, dịch vụ cần xác định người dùng hiện tại và phạm vi được phép truy cập. Nếu cần truyền thông tin ngữ cảnh như tenant ID, user ID hoặc vai trò đã xác thực, hãy lấy từ security context hoặc cơ chế ngữ cảnh do ứng dụng kiểm soát, chẳng hạn **ToolContext**. Không yêu cầu mô hình tự chọn một tenant hay user ID để quyết định quyền truy cập.

Tool chỉ đọc vẫn có thể làm lộ dữ liệu. Vì vậy:

1. Chỉ cung cấp tool cho những yêu cầu mà người dùng có quyền thực hiện.
2. Kiểm tra quyền trên tài nguyên ở tầng dịch vụ hoặc tầng bảo mật.
3. Trả về các trường cần thiết, không trả toàn bộ entity hoặc thông tin nhạy cảm.
4. Không đưa thông tin xác thực, token, stack trace hay truy vấn nội bộ vào tool result.
5. Ghi log đủ để truy vết việc tra cứu, nhưng không ghi dữ liệu nhạy cảm không cần thiết.

## 8. Xử lý các trường hợp thường gặp

| Tình huống | Cách xử lý |
| --- | --- |
| Không tìm thấy SKU | Trả kết quả rõ ràng rằng không có sản phẩm phù hợp; không tự tạo dữ liệu thay thế |
| SKU rỗng hoặc sai định dạng | Từ chối đầu vào tại lớp ứng dụng và trả lỗi có thể hiểu được |
| Người dùng không có quyền xem sản phẩm | Từ chối theo chính sách truy cập; không tiết lộ dữ liệu ngoài phạm vi |
| Dịch vụ danh mục tạm thời lỗi | Dùng cơ chế xử lý lỗi của ứng dụng; không giả vờ rằng sản phẩm không tồn tại |
| Mô hình không gọi tool | Kiểm tra tool có được đính kèm vào prompt, mô tả có rõ và model có hỗ trợ tool calling không |
| Mô hình gửi đối số không đúng | Cải thiện mô tả tham số và schema, đồng thời giữ bước kiểm tra đầu vào ở server |

Không nên biến mọi lỗi hệ thống thành chuỗi “không tìm thấy”. Hai tình huống đó có ý nghĩa khác nhau: SKU không tồn tại là kết quả nghiệp vụ hợp lệ; database không truy cập được là lỗi vận hành cần được ghi nhận và xử lý theo chính sách của ứng dụng.

## 9. Kiểm tra tool trước khi kết nối mô hình

Có thể kiểm tra phương thức tool trực tiếp như một phương thức Java bình thường. Điều này giúp xác nhận phần nghiệp vụ hoạt động trước khi thêm yếu tố lựa chọn công cụ của mô hình.

Một bộ kiểm tra tối thiểu nên bao gồm:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| SKU hợp lệ và tồn tại | Trả đúng SKU, tên, giá và tình trạng còn hàng |
| SKU hợp lệ nhưng không tồn tại | Trả thông báo không tìm thấy |
| SKU rỗng | Bị từ chối theo quy tắc kiểm tra đầu vào |
| Người dùng ngoài phạm vi | Không trả dữ liệu sản phẩm |
| Dịch vụ danh mục phát sinh lỗi | Lỗi được xử lý theo chính sách của ứng dụng, không bị giả thành kết quả tra cứu |

Sau đó kiểm tra tích hợp với một model hỗ trợ tool calling:

- Đặt câu hỏi có SKU rõ ràng và nội dung phù hợp với mô tả tool.
- Quan sát log hoặc trace để xác nhận model yêu cầu **lookup_product**.
- Kiểm tra đối số được gửi xuống có đúng SKU không.
- Xác nhận phương thức chỉ gọi thao tác đọc.
- Xác nhận model dùng dữ liệu tool result trong câu trả lời cuối.

Không nên chỉ kiểm tra câu trả lời cuối cùng bằng một chuỗi cố định, vì cách diễn đạt của mô hình có thể thay đổi. Hãy kiểm tra các dữ kiện quan trọng và quan sát việc thực thi tool ở phía ứng dụng.

## 10. Các lỗi thiết kế dễ gặp

**Mô tả quá chung chung.** Nếu description chỉ ghi “Tìm sản phẩm”, mô hình khó phân biệt tool này với công cụ tìm kiếm theo tên, danh mục hoặc từ khóa. Hãy nói rõ tool tra cứu theo SKU và trả về những trường nào.

**Đưa quá nhiều tham số vào tool đầu tiên.** Một tool tra cứu SKU không cần nhận cả tên khách hàng, địa chỉ giao hàng, mã đơn và tùy chọn thanh toán. Mỗi tham số nên phục vụ trực tiếp mục đích tra cứu.

**Để tool trả toàn bộ entity.** Entity có thể chứa dữ liệu nội bộ hoặc quan hệ không cần thiết. Hãy chuyển thành kết quả gọn chỉ gồm trường cần dùng.

**Đặt quy tắc nghiệp vụ trong prompt.** Prompt và description giúp mô hình chọn tool; chúng không thay thế validation, phân quyền và quy tắc ở backend.

**Nhầm lẫn tool call với câu trả lời.** Khi mô hình gửi tool call, ứng dụng phải thực thi callback và trả kết quả về đúng luồng hội thoại. Tool call chưa phải là câu trả lời cuối cùng cho người dùng.

## 11. Mở rộng sau công cụ đầu tiên

Sau khi công cụ tra cứu SKU hoạt động ổn định, có thể mở rộng theo từng bước:

1. Thêm tham số tùy chọn như **includeDescription**, đồng thời mô tả rõ mặc định.
2. Trả về một DTO nhỏ thay cho chuỗi khi ứng dụng cần kết quả có cấu trúc.
3. Bổ sung phân trang hoặc bộ lọc nếu nghiệp vụ thực sự cần.
4. Truyền ngữ cảnh tenant và người dùng đã xác thực bằng cơ chế do ứng dụng kiểm soát.
5. Tạo tool thứ hai có mục đích khác và kiểm tra mô hình chọn đúng công cụ.

Chỉ thêm độ phức tạp khi có yêu cầu cụ thể. Mỗi tool nên có một mục đích dễ giải thích, đầu vào tối thiểu và kết quả rõ ràng.

## 12. Bài thực hành

Hãy tạo một tool chỉ đọc khác có tên **lookup_book**, nhận một mã ISBN và trả về tên sách, tác giả cùng tình trạng còn trong kho.

Yêu cầu:

- Khai báo phương thức bằng **@Tool** với tên và mô tả cụ thể.
- Dùng **@ToolParam** mô tả ISBN và ví dụ định dạng hợp lệ.
- Gọi một dịch vụ tra cứu sách có sẵn.
- Trả kết quả rõ ràng khi tìm thấy và khi không tìm thấy.
- Đưa đối tượng tool vào prompt bằng **ChatClient.tools(...)**.
- Kiểm tra đầu vào sai, sách không tồn tại và quyền đọc dữ liệu.

Khi hoàn thành, hãy tự trả lời: mô hình cần biết điều gì để chọn tool; ứng dụng chịu trách nhiệm điều gì khi thực thi; dữ liệu nào được phép đưa trở lại mô hình?

## Ghi nhớ

Một tool chỉ đọc đầu tiên có thể chỉ cần một phương thức Java, một tham số chuỗi và một kết quả ngắn. **@Tool** công bố mục đích công cụ; **@ToolParam** mô tả đầu vào; **ChatClient.tools(...)** đưa đối tượng tool vào yêu cầu hiện tại. Spring AI điều phối yêu cầu gọi đến phương thức, còn ứng dụng vẫn chịu trách nhiệm đọc dữ liệu, xác thực quyền, kiểm tra đầu vào và giới hạn kết quả trả về.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI Reference — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
