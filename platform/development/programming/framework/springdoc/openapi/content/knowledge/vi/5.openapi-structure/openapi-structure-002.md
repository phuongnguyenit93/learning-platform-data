# Info: title, summary khi được hỗ trợ, description và version

## 1. Vai trò của Info Object trong OpenAPI

Một tài liệu OpenAPI mô tả hợp đồng mà client sử dụng để gọi API. Bên cạnh danh sách endpoint, tham số, request body và response, tài liệu cần thông tin nhận diện API: tên API là gì, API phục vụ mục đích nào, mô tả tổng quan ra sao và hợp đồng đang ở phiên bản nào.

OpenAPI đặt các thông tin này trong **Info Object**, nằm ở trường gốc **info** của tài liệu. Với Spring Boot, Springdoc OpenAPI tạo phần này từ cấu hình Java, annotation hoặc bean OpenAPI mà ứng dụng cung cấp.

Info Object giúp:

- Người đọc nhận biết đúng API khi một hệ thống có nhiều dịch vụ.
- Swagger UI hiển thị tiêu đề và mô tả tổng quan ở đầu trang tài liệu.
- Client, cổng developer portal và công cụ tự động có thông tin để phân biệt các hợp đồng.
- Nhóm phát triển công bố phiên bản hợp đồng API và thông tin liên hệ có trách nhiệm.

Info là metadata mô tả toàn bộ API được tài liệu bao phủ. Nó không thay thế mô tả ở từng endpoint. Ví dụ, Info.description nói API quản lý sản phẩm và đơn hàng; còn Operation.summary mô tả cụ thể endpoint GET /products/{id} dùng để làm gì.

## 2. Vị trí và cấu trúc của Info Object

Một OpenAPI document thường có trường gốc **openapi**, **info**, **servers**, **paths** và có thể có **components**, **security** hoặc **tags**. Phần Info nằm ngay dưới trường gốc:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  summary: API phục vụ cửa hàng trực tuyến
  description: |
    API cho phép ứng dụng quản lý sản phẩm, danh mục và đơn hàng.
    Tài liệu này mô tả hợp đồng HTTP dành cho các hệ thống tích hợp.
  version: "1.4.0"
paths: {}
~~~

Trong ví dụ này:

- **openapi: 3.1.0** cho biết tài liệu sử dụng phiên bản đặc tả OpenAPI 3.1.0.
- **info.title** là tên API.
- **info.summary** là phần tóm tắt ngắn, nếu phiên bản OpenAPI hỗ trợ.
- **info.description** là phần mô tả chi tiết hơn về API.
- **info.version** là phiên bản của API được mô tả trong tài liệu.

Cần phân biệt **openapi** ở cấp gốc với **info.version**. Trường openapi cho biết tài liệu tuân theo phiên bản nào của đặc tả OpenAPI; info.version cho biết phiên bản hợp đồng API mà tổ chức đang công bố. Hai giá trị có mục đích khác nhau và có thể thay đổi độc lập.

## 3. title: tên API rõ ràng và ổn định

Trường **title** là tên chính thức của API và là trường bắt buộc trong Info Object. Tên này thường xuất hiện nổi bật trên Swagger UI và các công cụ đọc OpenAPI.

Ví dụ:

~~~yaml
info:
  title: Product Catalog API
  version: "1.0.0"
~~~

Một title tốt nên:

- Nêu rõ miền nghiệp vụ hoặc chức năng chính.
- Phân biệt được API với những dịch vụ khác trong cùng hệ thống.
- Dùng cách viết nhất quán giữa các môi trường và phiên bản tài liệu.
- Tránh đưa tên môi trường như local, staging hoặc production vào title nếu cùng một hợp đồng được triển khai ở nhiều môi trường.

Một số ví dụ:

| Tên chưa rõ | Tên rõ hơn |
|---|---|
| Backend API | Customer Management API |
| Service | Order API |
| API v1 | Inventory API |
| My Application | Payment Gateway API |

Tên API không cần nhồi toàn bộ chức năng vào một dòng. Những chi tiết như đối tượng sử dụng, phạm vi endpoint hoặc giới hạn nghiệp vụ nên được giải thích trong summary và description.

## 4. summary: tóm tắt ngắn khi được hỗ trợ

**summary** là câu tóm tắt ngắn về API ở cấp Info Object. Trường này được bổ sung trong OpenAPI Specification 3.1.0. Vì vậy, không phải mọi tài liệu OpenAPI 3.0 hoặc mọi phiên bản thư viện mô hình OpenAPI đều có thể biểu diễn trường này.

Ví dụ:

~~~yaml
info:
  title: Shop API
  summary: API quản lý danh mục và đơn hàng của cửa hàng
  version: "1.4.0"
~~~

Summary nên trả lời ngắn gọn API phục vụ mục đích gì. Một câu thường là đủ. Tránh lặp lại nguyên văn title hoặc biến summary thành một đoạn hướng dẫn dài.

Cần phân biệt hai loại summary:

- **Info.summary** tóm tắt toàn bộ API trong tài liệu.
- **Operation.summary** tóm tắt một thao tác HTTP cụ thể, được khai báo bằng annotation **@Operation** hoặc trường summary của Operation Object.

Ví dụ, Info.summary có thể là “API quản lý cửa hàng trực tuyến”, trong khi Operation.summary của endpoint tạo đơn hàng là “Tạo đơn hàng mới”.

### 4.1. Khi tài liệu dùng OpenAPI 3.0

OpenAPI 3.0 không định nghĩa trường **info.summary**. Nếu ứng dụng sinh tài liệu 3.0, hãy đặt câu giới thiệu ngắn ở đầu **info.description** và không giả định Swagger UI sẽ hiểu một trường summary tùy ý.

### 4.2. Khi tài liệu dùng OpenAPI 3.1

OpenAPI 3.1.0 trở lên định nghĩa Info.summary. Để sử dụng, cần bảo đảm phiên bản Springdoc cùng thư viện swagger-models hoặc openapi-annotations mà dự án sử dụng hỗ trợ thuộc tính này, đồng thời tài liệu sinh ra thực sự khai báo phiên bản OpenAPI tương ứng.

Không chỉ dựa vào việc mã Java biên dịch được. Hãy tải OpenAPI JSON/YAML và xác minh trường **info.summary** có xuất hiện đúng vị trí hay không. Nếu thư viện đang dùng chưa có API tương ứng, cần nâng cấp theo ma trận tương thích trước khi gọi thuộc tính summary trong mã nguồn.

## 5. description: mô tả phạm vi và cách sử dụng API

Trường **description** cung cấp phần giải thích chi tiết hơn về API. Đây là nơi mô tả:

- Mục tiêu và phạm vi nghiệp vụ của API.
- Những nhóm chức năng hoặc tài nguyên được cung cấp.
- Đối tượng client dự kiến sử dụng.
- Quy ước chung như múi giờ, định dạng dữ liệu hoặc cách xử lý lỗi.
- Liên kết đến hướng dẫn tích hợp, chính sách hoặc tài liệu bổ sung khi phù hợp.

Ví dụ:

~~~yaml
info:
  title: Shop API
  description: |
    API dành cho các ứng dụng bán hàng và hệ thống tích hợp.

    Các nhóm chức năng chính:
    - Quản lý sản phẩm và danh mục.
    - Tạo và theo dõi đơn hàng.
    - Tra cứu trạng thái thanh toán.

    Thời gian trong response sử dụng định dạng ISO 8601.
    Các endpoint yêu cầu xác thực được mô tả bằng security scheme.
  version: "1.4.0"
~~~

Theo OpenAPI Specification, nội dung description hỗ trợ CommonMark. Do đó, có thể dùng Markdown để tạo đoạn văn, danh sách, liên kết và nhấn mạnh nội dung. Khi viết YAML nhiều dòng, block scalar **|** giúp giữ cấu trúc dễ đọc.

Mô tả nên cung cấp ngữ cảnh đủ để người tích hợp bắt đầu sử dụng API. Những chi tiết riêng của endpoint vẫn nên đặt trong **@Operation.description**, parameter description hoặc schema description tương ứng.

Tránh ghi thông tin bí mật, token mẫu đang hoạt động, địa chỉ hệ thống nội bộ hoặc chi tiết hạ tầng không dành cho người đọc tài liệu. Nếu description chứa liên kết, hãy dùng URL ổn định và kiểm tra quyền truy cập của người nhận tài liệu.

## 6. version: phiên bản của API được mô tả

Trường **version** là trường bắt buộc trong Info Object và có kiểu chuỗi. Nó xác định phiên bản API mà tài liệu đang mô tả.

Ví dụ:

~~~yaml
info:
  title: Shop API
  version: "1.4.0"
~~~

Nên đặt version thành chuỗi có quy ước rõ ràng. Dự án có thể dùng Semantic Versioning hoặc một chính sách đánh số phiên bản riêng, miễn là nhóm phát triển và client hiểu cùng một ý nghĩa.

Nếu áp dụng quy ước tương tự Semantic Versioning:

- Tăng phiên bản major khi có thay đổi phá vỡ tương thích.
- Tăng minor khi bổ sung chức năng tương thích ngược theo chính sách của API.
- Tăng patch khi sửa lỗi hoặc cập nhật mô tả không làm thay đổi hợp đồng theo chính sách đã thống nhất.

Đây là chính sách quản lý phiên bản do nhóm API lựa chọn; OpenAPI không tự áp đặt cách tăng version. Một thay đổi tưởng như bổ sung cũng cần được đánh giá theo hành vi client thực tế, chẳng hạn thêm trường bắt buộc vào request có thể phá vỡ client cũ.

### 6.1. Phân biệt các loại phiên bản

| Giá trị | Ý nghĩa |
|---|---|
| Trường gốc openapi | Phiên bản đặc tả OpenAPI mà tài liệu tuân theo, ví dụ 3.0.3 hoặc 3.1.0 |
| info.version | Phiên bản API hoặc hợp đồng được mô tả |
| Phiên bản ứng dụng | Phiên bản bản build hoặc release của phần mềm triển khai API |
| Phiên bản trên URL | Phiên bản được thể hiện trong đường dẫn, ví dụ /api/v1 hoặc /api/v2 |

Các giá trị này không bắt buộc giống nhau. Ví dụ, một bản build ứng dụng 2.8.5 có thể tiếp tục cung cấp hợp đồng API v1.4.0; tài liệu đó có thể dùng OpenAPI 3.1.0.

**info.version không tự tạo endpoint versioning.** Đặt giá trị info.version thành 2.0.0 không tự chuyển đường dẫn /api/v1 sang /api/v2, không tạo controller mới và không duy trì song song hai phiên bản API. Việc định tuyến phiên bản cần được triển khai ở controller, path, header, media type hoặc cơ chế versioning mà ứng dụng lựa chọn.

## 7. Bổ sung metadata liên quan

Info Object còn có một số trường tùy chọn giúp người đọc biết nơi liên hệ và điều khoản sử dụng tài liệu:

- **termsOfService**: URL tới điều khoản dịch vụ.
- **contact**: tên, email hoặc URL của nhóm phụ trách API.
- **license**: tên giấy phép và thông tin URL hoặc identifier theo phiên bản đặc tả hỗ trợ.

Ví dụ:

~~~yaml
info:
  title: Shop API
  description: API quản lý sản phẩm và đơn hàng.
  version: "1.4.0"
  termsOfService: https://example.com/terms
  contact:
    name: API Support
    url: https://example.com/support
    email: api-support@example.com
  license:
    name: Apache 2.0
    url: https://www.apache.org/licenses/LICENSE-2.0.html
~~~

Các URL trong ví dụ là địa chỉ minh họa. Khi triển khai, hãy thay bằng trang thực tế và bảo đảm thông tin liên hệ thuộc đúng nhóm chịu trách nhiệm.

Không bắt buộc phải khai báo tất cả trường tùy chọn. Chỉ công bố thông tin đã được tổ chức phê duyệt và còn hiệu lực. Với API nội bộ, contact có thể là kênh hỗ trợ nội bộ; với API công khai, thông tin hỗ trợ và giấy phép nên phù hợp chính sách công bố.

## 8. Cấu hình Info bằng annotation trong Spring Boot

Springdoc có thể lấy metadata từ annotation **@OpenAPIDefinition** và **@Info** thuộc gói **io.swagger.v3.oas.annotations**.

Ví dụ:

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Shop API",
        version = "1.4.0",
        description = "API dành cho ứng dụng bán hàng và các hệ thống tích hợp. "
            + "Cung cấp chức năng quản lý sản phẩm, danh mục và đơn hàng. "
            + "Thời gian trong response sử dụng định dạng ISO 8601."
    )
)
public class OpenApiConfiguration {
}
~~~

Cách này phù hợp khi metadata có thể khai báo tĩnh bằng annotation. Các trường title, version và description giúp tài liệu có thông tin nhận diện và giới thiệu cơ bản.

Nếu phiên bản annotation **@Info** đang dùng có hỗ trợ thuộc tính summary và tài liệu được xuất theo OpenAPI 3.1.0 trở lên, có thể bổ sung summary ngay trong annotation. Nếu compiler báo không có thuộc tính hoặc tài liệu sinh ra không có trường đó, hãy kiểm tra phiên bản thư viện và phiên bản đặc tả đang dùng trước khi thay đổi dependency.

## 9. Cấu hình Info bằng bean OpenAPI

Một lựa chọn khác là khai báo bean **OpenAPI** và tạo đối tượng **Info** bằng Java:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI shopOpenAPI() {
        Info info = new Info()
            .title("Shop API")
            .version("1.4.0")
            .description("API dành cho ứng dụng bán hàng và các hệ thống tích hợp. "
                + "Cung cấp chức năng quản lý sản phẩm, danh mục và đơn hàng.");

        return new OpenAPI()
            .info(info);
    }
}
~~~

Cách này phù hợp khi cần xây dựng metadata bằng code, tái sử dụng giá trị cấu hình hoặc bổ sung thông tin có điều kiện.

Nếu phiên bản swagger-models đang dùng hỗ trợ Info.summary và ứng dụng xuất OpenAPI 3.1.0 trở lên, có thể thiết lập thêm:

~~~java
info.setSummary("API quản lý sản phẩm, danh mục và đơn hàng");
~~~

Phương thức trên chỉ dùng được khi phiên bản model có thuộc tính summary. Với OpenAPI 3.0 hoặc thư viện chưa hỗ trợ, bỏ phần cấu hình này và đưa câu tóm tắt vào description.

Nên chọn một nguồn cấu hình chính cho Info để tránh metadata bị khai báo lặp ở nhiều nơi. Nếu ứng dụng vừa dùng annotation vừa khai báo bean OpenAPI, hãy kiểm tra kết quả sinh ra để bảo đảm không có giá trị bị ghi đè ngoài ý muốn.

## 10. Kiểm tra Info trong OpenAPI JSON và YAML

Sau khi khởi động ứng dụng, truy cập endpoint tài liệu mặc định của Springdoc:

~~~http
GET /v3/api-docs
~~~

Nếu cấu hình hỗ trợ xuất YAML, có thể tải tài liệu tại:

~~~http
GET /v3/api-docs.yaml
~~~

Tìm phần **info** ở cấp gốc và xác minh:

- title có đúng tên API không.
- summary có xuất hiện khi dùng OpenAPI 3.1 và thư viện hỗ trợ không.
- description có giữ đúng nội dung nhiều dòng và liên kết không.
- version có đúng phiên bản hợp đồng được công bố không.
- contact, license và termsOfService có đúng nếu đã khai báo không.
- Trường openapi ở cấp gốc có đúng phiên bản đặc tả mà nhóm dự kiến không.

Ví dụ phần tài liệu mong đợi:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  summary: API quản lý sản phẩm, danh mục và đơn hàng
  description: |
    API dành cho ứng dụng bán hàng và các hệ thống tích hợp.
  version: "1.4.0"
~~~

Swagger UI thường hiển thị title và description trong phần đầu giao diện. Summary có thể được hiển thị tùy phiên bản Swagger UI và cấu hình; vì vậy cần kiểm tra cả nội dung OpenAPI document lẫn giao diện thực tế.

## 11. Lỗi thường gặp khi cấu hình Info

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI hiển thị tên API mặc định | Chưa khai báo Info hoặc cấu hình chưa được Spring scan/nạp |
| Title đúng nhưng version sai | Có nhiều nguồn cấu hình hoặc bean OpenAPI khác đang cung cấp Info |
| Summary không xuất hiện | Tài liệu đang dùng OpenAPI 3.0 hoặc thư viện model/annotation chưa hỗ trợ Info.summary |
| Description bị mất định dạng | YAML multiline hoặc chuỗi Java được ghép chưa đúng như mong đợi |
| Version bị hiểu là số | YAML không đặt version trong dấu nháy; nên khai báo thành chuỗi rõ ràng |
| Info.version thay đổi nhưng URL không đổi | Info.version chỉ là metadata, không thực hiện routing version |
| Swagger UI không phản ánh cập nhật | Ứng dụng chưa khởi động lại, cache hoặc đang đọc tài liệu từ endpoint/nhóm khác |

Khi điều tra, hãy đọc trực tiếp OpenAPI JSON/YAML trước. Nếu dữ liệu trong document đã đúng nhưng giao diện chưa hiển thị như mong đợi, kiểm tra phiên bản Swagger UI và cấu hình giao diện. Nếu document đã sai, kiểm tra nguồn cấu hình Info và bean hoặc annotation mà Springdoc thực sự nạp.

## 12. Quy tắc viết metadata dễ bảo trì

Một Info Object tốt cần ngắn gọn, đúng phạm vi và nhất quán:

1. Dùng title nhận diện rõ API và miền nghiệp vụ.
2. Dùng summary làm câu giới thiệu ngắn nếu OpenAPI 3.1 và thư viện hỗ trợ.
3. Dùng description để giải thích phạm vi, quy ước chung và liên kết cần thiết.
4. Dùng version để xác định phiên bản hợp đồng API, không nhầm với phiên bản OpenAPI hoặc bản build.
5. Chỉ khai báo contact, license và termsOfService khi thông tin đã được xác nhận.
6. Quản lý metadata ở một nguồn cấu hình chính.
7. Kiểm tra phần info trong tài liệu JSON/YAML sau mỗi thay đổi có liên quan.

Info Object là điểm bắt đầu để người dùng hiểu API trước khi đi sâu vào từng endpoint. Khi title, summary, description và version được định nghĩa rõ ràng, Springdoc có thể tạo ra tài liệu dễ nhận diện, dễ phân phối và thuận tiện cho việc quản lý hợp đồng API theo thời gian.

