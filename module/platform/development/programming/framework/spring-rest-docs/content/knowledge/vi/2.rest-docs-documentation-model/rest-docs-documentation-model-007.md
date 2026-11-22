# Định danh operation và tổ chức thư mục snippet

Trong Spring REST Docs, mỗi lần gọi §document(...)§ cần một **định danh operation** (operation identifier). Định danh này được dùng để phân nhóm những snippet sinh ra từ request/response và descriptor của lần kiểm thử đó. Khi trang Asciidoctor include §{snippets}/orders-get-success/http-response.adoc[]§, phần §orders-get-success§ phải khớp với identifier test đã sử dụng.

Đặt tên và tổ chức thư mục snippet có ảnh hưởng trực tiếp đến khả năng duy trì tài liệu. Nếu nhiều test ghi vào cùng một thư mục, ví dụ thành công và lỗi có thể ghi đè hoặc trộn lẫn. Nếu test đổi identifier nhưng tài liệu vẫn include đường dẫn cũ, build có thể thất bại hoặc vô tình dùng snippet còn sót lại từ lần chạy trước. Nếu tên operation khó hiểu, người phát triển khó truy ngược trang tài liệu về test tạo ra nó.

Bài này thuộc chương **Mô hình tài liệu** của module §SPRING_REST_DOCS§. Module thực hành tạo tài liệu REST API có thể kiểm chứng bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown trong build và CI. Bài học tập trung vào cách chọn identifier, cấu trúc thư mục, phân biệt các operation cùng route và kiểm soát vòng đời snippet.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích identifier của §document(...)§ được dùng để định vị snippet như thế nào.
2. Đặt tên operation ổn định, dễ hiểu và phân biệt được method, resource, trường hợp xử lý.
3. Tổ chức output snippet theo resource, operation và tình huống.
4. Phân biệt một operation có nhiều snippet với nhiều operation có cùng route.
5. Tránh trùng identifier, ghi đè output, dùng snippet cũ và lỗi include.
6. Kết nối đường dẫn snippet với cấu hình Gradle/Maven và quy trình CI.
7. Quản lý thay đổi tên operation mà không làm hỏng trang tài liệu.

## 2. Identifier gắn snippet với operation nguồn

Một test MockMvc thường kết thúc bằng một lời gọi có dạng:

```java
.andDo(document("orders-get-success",
    pathParameters(
        parameterWithName("orderId")
            .description("Mã đơn hàng")
    ),
    responseFields(
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("status").description("Trạng thái")
    )
));
```

Trong đó §orders-get-success§ là identifier do tác giả đặt. Spring REST Docs dùng identifier này để tạo thư mục operation bên dưới output directory của test. Với cấu hình phổ biến, cấu trúc thường là:

```text
build/generated-snippets/
└── orders-get-success/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
```

Đường dẫn thực tế phụ thuộc output directory được cấu hình cho test. Dự án Gradle thường đặt tại §build/generated-snippets§; dự án Maven thường dùng §target/generated-snippets§. Identifier vẫn là phần tên được nối vào output directory.

Khi viết:

```asciidoc
include::{snippets}/orders-get-success/http-response.adoc[]
```

các thành phần có ý nghĩa như sau:

| Thành phần | Ý nghĩa |
| --- | --- |
| §{snippets}§ | Attribute Asciidoctor trỏ tới output directory |
| §orders-get-success§ | Identifier truyền vào §document(...)§ |
| §http-response.adoc§ | Tên snippet cần include |

**Identifier là hợp đồng liên kết giữa test và tài liệu nguồn.** Đổi identifier trong test thường đòi hỏi đổi những đường dẫn include tương ứng.

### 2.1. Một identifier chứa nhiều snippet

Một operation có thể sinh đồng thời nhiều mảnh nội dung. Ví dụ, test đọc đơn hàng có thể tạo:

- §http-request.adoc§ và §http-response.adoc§ cho ví dụ HTTP.
- §path-parameters.adoc§ cho biến đường dẫn.
- §query-parameters.adoc§ cho tham số truy vấn.
- §request-headers.adoc§ hoặc §response-headers.adoc§ cho header được mô tả.
- §request-fields.adoc§ hoặc §response-fields.adoc§ cho payload.

Những file này cùng nằm trong thư mục có identifier của operation. Không cần tạo identifier riêng cho từng snippet. Tên file phân biệt **loại thông tin**, còn tên thư mục xác định **operation nguồn**.

### 2.2. Nhiều operation có thể dùng cùng route

Ví dụ §GET /api/orders/{orderId}§ có ít nhất hai kết quả:

| Operation | Request ví dụ | Response | Identifier |
| --- | --- | --- | --- |
| Đọc đơn hàng thành công | §GET /api/orders/42§ | §200 OK§, JSON đơn hàng | §orders-get-success§ |
| Không tìm thấy đơn hàng | §GET /api/orders/999§ | §404 Not Found§, JSON lỗi hoặc body rỗng theo hợp đồng | §orders-get-not-found§ |

Đây là hai operation tài liệu hóa riêng dù cùng method và route template. Nếu dùng chung identifier, snippet của lần chạy này có thể thay thế snippet lần chạy kia. Người đọc cũng không còn biết response nào thuộc tình huống nào.

## 3. Quy tắc đặt tên identifier

Tên tốt nên trả lời nhanh ba câu hỏi: **resource nào, thao tác nào, tình huống nào?**

Một mẫu dễ đọc:

```text
<resource>-<http-method>-<scenario>
```

Ví dụ:

| Identifier | Ý nghĩa |
| --- | --- |
| §orders-get-success§ | Đọc đơn hàng thành công |
| §orders-get-not-found§ | Không tìm thấy đơn hàng |
| §orders-create-success§ | Tạo đơn hàng thành công |
| §orders-create-invalid§ | Request tạo đơn không hợp lệ |
| §orders-update-conflict§ | Cập nhật bị xung đột trạng thái |
| §orders-delete-success§ | Xóa đơn hàng thành công |

Đây là quy ước dự án có thể chọn; Spring REST Docs không bắt buộc phải dùng đúng mẫu trên. Điều quan trọng là identifier ổn định và duy nhất trong phạm vi các test ghi vào cùng output directory.

### 3.1. Nguyên tắc cụ thể

**Dùng tên resource hoặc nhóm endpoint nhất quán.** Nếu phần còn lại của tài liệu gọi là §orders§ thì không nên lúc dùng §order§, lúc dùng §purchase§ cho cùng khái niệm mà không có lý do.

**Ghi method hoặc hành động rõ ràng.** §orders-get-success§ dễ nhận ra hơn §orders-success§ khi một resource có GET, POST và DELETE.

**Ghi tình huống khi có thể có nhiều response.** Dùng §success§, §not-found§, §invalid§, §forbidden§, §conflict§ hoặc một từ vựng thống nhất của dự án.

**Ưu tiên chữ thường và dấu gạch ngang.** Tên như §orders-get-not-found§ dễ đọc trong đường dẫn include và không phụ thuộc quy ước hoa/thường của hệ thống file.

**Giữ identifier độc lập với dữ liệu fixture.** Không đặt §orders-get-42§ chỉ vì test hiện gọi ID 42, trừ khi giá trị ID là một phần định danh thật sự cần phân biệt. Fixture có thể thay đổi nhưng tên operation nên giữ ổn định.

**Không nhúng phiên bản code hoặc ngày chạy tùy tiện.** Identifier như §orders-get-v17-20261117§ khiến các lần build tạo ra nhiều thư mục không cần thiết. Version API nên xuất hiện ở cấu trúc tài liệu/output được quản lý rõ ràng nếu dự án có nhu cầu.

### 3.2. Tránh tên mơ hồ hoặc quá dài

| Tên chưa tốt | Vấn đề | Tên rõ hơn |
| --- | --- | --- |
| §test1§ | Không nói resource hay hành động | §orders-get-success§ |
| §success§ | Có thể trùng giữa nhiều resource | §orders-create-success§ |
| §get-order§ | Không phân biệt thành công và lỗi | §orders-get-success§ |
| §orders-42§ | Gắn với dữ liệu fixture | §orders-get-success§ |
| §orders-get-success-with-user-role-admin-and-v2§ | Quá dài, lẫn nhiều chiều phân loại | §orders-get-admin-success§ nếu role thực sự tạo ra response riêng |
| §orders-final-new§ | Không mô tả hành vi; chữ final/new nhanh lỗi thời | §orders-create-success§ |

Nếu role, locale, version hay media type thực sự làm thay đổi hợp đồng response thì có thể đưa một chiều đó vào tên operation, ví dụ §orders-get-owner-success§ và §orders-get-support-success§. Chỉ thêm khi có khác biệt cần tài liệu hóa; không đưa mọi giá trị input vào identifier.

## 4. Tổ chức thư mục snippet theo nhiều resource

Với dịch vụ nhỏ, một output directory có thể chứa các operation ở cùng cấp:

```text
build/generated-snippets/
├── products-get-success/
├── products-get-not-found/
├── products-create-success/
├── orders-get-success/
├── orders-create-invalid/
└── orders-cancel-conflict/
```

Cấu trúc này dễ tìm kiếm và thuận tiện khi tài liệu nguồn include snippet. Khi số operation tăng, có thể duy trì danh sách identifier có quy ước rõ ràng, hoặc chia output directory theo source set/module/test suite.

### 4.1. Tách theo resource trong trang tài liệu

Không nhất thiết phải tổ chức thư mục output lồng sâu để có tài liệu nhiều phần. Cách thường đơn giản là giữ identifier phẳng và tổ chức trang Asciidoctor theo resource:

```text
src/docs/asciidoc/
├── index.adoc
├── introduction.adoc
├── products.adoc
├── orders.adoc
└── errors.adoc

build/generated-snippets/
├── products-get-success/
├── products-get-not-found/
├── orders-get-success/
└── orders-create-invalid/
```

Trang §orders.adoc§ tham chiếu các thư mục §orders-*§, còn trang §products.adoc§ tham chiếu §products-*§. Người biên tập có thể tìm nhanh operation liên quan qua tên file và identifier.

### 4.2. Khi nào cần chia output directory?

Trong hệ thống lớn, việc chia output directory có ích khi:

- Có nhiều module độc lập cùng sinh snippet.
- Nhiều source set hoặc test suite có lifecycle và nhiệm vụ build khác nhau.
- Các phiên bản API cần được build, review hoặc phát hành riêng.
- Nhiều loại tài liệu có cách tiền xử lý hoặc template snippet khác nhau.

Khi đó, có thể cấu hình các nhóm test sử dụng output directory riêng, ví dụ:

```text
build/
├── snippets-public-api/
│   ├── orders-get-success/
│   └── products-get-success/
├── snippets-admin-api/
│   ├── orders-get-admin/
│   └── users-get-admin/
└── docs/
    ├── public-api/
    └── admin-api/
```

Các tên thư mục ở đây là ví dụ về **cách tổ chức build**, không phải cấu trúc được Spring REST Docs tự tạo mặc định. Việc phân tách cần đi cùng cấu hình của từng test và attribute §snippets§ tương ứng trong tài liệu. Nếu mọi test vẫn ghi về một output directory duy nhất, việc tạo folder thủ công ở source tree sẽ không tự chia output của Spring REST Docs.

### 4.3. Tránh phân chia quá mức

Không nên tạo một output directory riêng cho từng test method nếu các test thuộc cùng một bộ tài liệu và có thể dùng chung cơ chế build. Chia quá nhiều nơi làm tăng số cấu hình, attribute include và bước dọn output.

Một lựa chọn thực tế:

| Quy mô | Cách tổ chức phù hợp |
| --- | --- |
| Vài endpoint trong một service | Một output directory; identifier theo resource/method/scenario |
| Nhiều resource cùng một API | Một output directory; cấu trúc trang chia theo resource |
| Nhiều API/module độc lập | Output directory riêng theo module hoặc test suite |
| Nhiều phiên bản public API | Tách tài liệu và output theo version khi cần phát hành độc lập |

## 5. Ví dụ tạo identifier và include nhất quán

Giả sử test MockMvc ghi nhận API đọc sản phẩm. Ta dùng identifier §products-get-success§.

```java
@Test
void getProduct_success() throws Exception {
    mockMvc.perform(
            get("/api/products/{productId}", 7L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(7))
        .andDo(document("products-get-success",
            pathParameters(
                parameterWithName("productId")
                    .description("Mã sản phẩm cần tra cứu")
            ),
            responseFields(
                fieldWithPath("id")
                    .description("Mã định danh sản phẩm"),
                fieldWithPath("name")
                    .description("Tên sản phẩm")
            )
        ));
}
```

Vì test sử dụng biến URI §{productId}§, cần builder của Spring REST Docs:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
```

Đối với §MockMvc§, test cần cấu hình REST Docs, ví dụ với §RestDocumentationExtension§ và §documentationConfiguration(...)§. Dependency và output directory phải được thiết lập theo build tool đang dùng.

Tài liệu AsciiDoc dùng chính identifier này:

```asciidoc
=== Tra cứu sản phẩm

.Request
include::{snippets}/products-get-success/http-request.adoc[]

.Path parameters
include::{snippets}/products-get-success/path-parameters.adoc[]

.Response
include::{snippets}/products-get-success/http-response.adoc[]

.Response fields
include::{snippets}/products-get-success/response-fields.adoc[]
```

Nếu đổi identifier trong test thành §product-get§, bốn include trên phải được xem lại. Đổi test mà quên đổi tài liệu sẽ tạo ra một đường dẫn không còn đúng; nếu build không dọn output cũ, include có thể vẫn tìm thấy file cũ và che giấu lỗi liên kết.

## 6. Identifier phải duy nhất trong phạm vi output chia sẻ

Hai test độc lập cùng ghi một identifier có thể cùng ghi các file như §http-request.adoc§ và §http-response.adoc§ vào một thư mục. Nếu nội dung khác nhau, kết quả cuối cùng phụ thuộc thứ tự hoặc cách chạy song song, dẫn đến tài liệu không xác định.

Ví dụ không tốt:

```java
@Test
void getOrder_success() {
    // ...
    document("orders-get");
}

@Test
void getOrder_notFound() {
    // ...
    document("orders-get");
}
```

Cả hai test cùng ghi vào §orders-get§. Tên đúng nên phản ánh trường hợp:

```java
document("orders-get-success", ...);
document("orders-get-not-found", ...);
```

Quy tắc cần nhớ:

- Identifier phải **duy nhất** với các operation độc lập trong cùng output directory.
- Nếu một test method thực hiện nhiều request được tài liệu hóa, mỗi operation cần được đặt identifier riêng phù hợp với mục đích.
- Không để hai task test chạy đồng thời ghi vào cùng thư mục/identifier khi tạo nội dung khác nhau.
- Nếu chia output directory, identifier có thể được tái sử dụng giữa các output độc lập, nhưng chỉ khi trang tài liệu trỏ đúng directory chứa snippet đó.

### 6.1. Trùng identifier không phải cách tái sử dụng snippet

Nếu nhiều trang cần cùng một snippet của **cùng operation**, hãy include cùng một file output ở nhiều nơi. Không chạy lại một test khác với identifier đó để “tạo lại” snippet cho trang mới. Nếu operation có response khác, hãy tạo identifier mới và test tương ứng.

### 6.2. Trường hợp test được chạy song song

Parallel test giúp rút ngắn thời gian nhưng phải quan tâm đến output chia sẻ. Các test tạo identifier riêng thường có thể ghi các thư mục riêng. Những test cùng identifier hoặc cùng custom snippet file có thể xung đột. Cách giải quyết là duy trì identifier duy nhất, không ghi cùng output từ nhiều task và đảm bảo mỗi test suite có nơi xuất riêng nếu cần chạy độc lập.

## 7. Quản lý output cũ và snippet lỗi thời

Snippet là output sinh tự động, nên có **vòng đời**:

```text
Test + document(identifier)
          │
          ▼
   Tạo thư mục snippet
          │
          ▼
  Tài liệu nguồn include file
          │
          ▼
   Thay đổi API/identifier
          │
          ▼
     Chạy build mới
          │
     ┌────┴─────┐
     ▼          ▼
  Cập nhật   Xóa/không còn
  snippet    tham chiếu cũ
```

Một vấn đề nguy hiểm: file snippet từ lần build trước vẫn tồn tại. Test hiện tại có thể không chạy hoặc identifier đã đổi, nhưng Asciidoctor vẫn đọc được file cũ. Trang render thành công trong khi không dùng bằng chứng mới.

### 7.1. Làm sạch đúng lúc

Trong CI, nên build từ checkout sạch hoặc làm sạch output generated trước khi tạo snippet. Với build cục bộ, có thể dùng task clean phù hợp rồi chạy test và task tài liệu. Không nên xóa thủ công source tài liệu hoặc thư mục không thuộc output sinh tự động.

Cần phân biệt:

- **Source tài liệu:** file §.adoc§/§.md§ do nhóm quản lý, phải được bảo toàn.
- **Generated snippets:** file output từ test, có thể tái tạo.
- **Rendered documentation:** HTML/PDF/site output từ bước biên soạn.

Làm sạch generated output không có nghĩa là xóa source. Build nên định nghĩa rõ output directory để việc clean an toàn và có thể lặp lại.

### 7.2. Kiểm tra include sau khi đổi identifier

Khi rename §orders-get-success§:

1. Tìm các include đang tham chiếu tới tên cũ trong những trang được quản lý.
2. Đổi identifier ở test và đường dẫn include cùng một thay đổi.
3. Tái tạo snippet trong output sạch.
4. Chạy Asciidoctor và xác nhận không còn include lỗi.
5. Xem nội dung hiển thị là đúng operation/thành công/lỗi mong muốn.

Không dựa vào việc “file cũ còn nên render được”. Một build sạch là cách xác nhận đường dẫn mới thực sự có nguồn.

## 8. Cấu hình thư mục output trong build

Identifier chỉ là một phần của đường dẫn. Phần gốc được xác định bởi cấu hình Spring REST Docs và build tool.

### 8.1. Với Gradle

Một cách cấu hình thường thấy là đặt output snippet thành thư mục build và cho task biên soạn tài liệu phụ thuộc test. Ví dụ Groovy DSL mang tính minh họa:

```groovy
plugins {
    id 'org.asciidoctor.jvm.convert' version '4.0.2'
}

configurations {
    asciidoctorExt
}

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

def snippetsDir = file("$buildDir/generated-snippets")

test {
    outputs.dir snippetsDir
}

asciidoctor {
    dependsOn test
    configurations 'asciidoctorExt'
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

Đây là cấu hình khung; phiên bản plugin, Spring Boot/REST Docs và DSL Gradle của dự án có thể yêu cầu điều chỉnh. Phần cốt lõi là task test tạo snippet vào một output directory đã biết và Asciidoctor đọc đúng directory đó qua attribute §snippets§.

Với test JUnit 5, có thể kết nối §RestDocumentationExtension§ với MockMvc qua §documentationConfiguration(provider)§. Dự án Spring Boot cũng có thể dùng §@AutoConfigureRestDocs§ theo cấu hình test phù hợp.

### 8.2. Với Maven

Trong Maven, output mặc định theo cấu hình thông dụng thường đặt tại §target/generated-snippets§. Plugin biên soạn tài liệu cần được nối với lifecycle sau khi test sinh snippet và nhận attribute §snippets§ trỏ tới thư mục đó.

Không nên sao chép cấu hình Gradle vào Maven. Hãy xác định rõ:

- Test nào tạo snippet và ở phase nào.
- Output directory thực tế là gì.
- Plugin Asciidoctor được chạy sau test hay không.
- File include dùng đúng attribute và identifier không.
- Build sạch có tái tạo được cùng cấu trúc output không.

### 8.3. Khi một module có nhiều test suite

Nếu integration test, contract test và smoke test cùng tạo snippet, hãy quyết định chúng có thuộc cùng một bộ tài liệu không. Nếu chúng có vòng đời độc lập, có thể dùng output directory riêng rồi biên soạn từng bộ tài liệu. Tránh để một suite bị skip nhưng trang vẫn lấy snippet từ suite khác có tên trùng.

Ví dụ:

```text
build/
├── generated-snippets/
│   ├── orders-get-success/       (unit/MVC docs)
│   └── products-get-success/
├── integration-snippets/
│   ├── orders-get-database/
│   └── products-get-indexed/
└── docs/
    ├── mvc-api/
    └── integration-api/
```

Tên và phân nhóm trên là chiến lược tổ chức của dự án; cần cấu hình test output và attribute riêng tương ứng. Spring REST Docs không tự phân biệt ý nghĩa “unit” hay “integration” từ tên folder.

## 9. Tổ chức identifier khi API có version, locale hoặc role

Một số hệ thống có nhiều biến thể của cùng resource. Không phải biến thể nào cũng cần identifier riêng; chỉ tách khi biến thể đó tạo ra response hoặc hợp đồng cần tài liệu hóa khác nhau.

| Chiều biến thể | Khi nên thể hiện trong identifier | Ví dụ |
| --- | --- | --- |
| Version API | Khi tài liệu và schema version độc lập | §v1-orders-get-success§, §v2-orders-get-success§ |
| Role/permission | Khi quyền làm thay đổi response hoặc hành vi cần mô tả | §orders-get-owner-success§, §orders-get-admin-success§ |
| Locale | Khi payload hoặc nội dung thực sự khác theo ngôn ngữ | §products-get-vi§, §products-get-en§ |
| Content type | Khi API hỗ trợ representation khác nhau cần tài liệu hóa | §products-get-json§, §products-get-xml§ |
| Scenario | Khi cùng operation có kết quả khác nhau | §orders-get-not-found§, §orders-get-forbidden§ |

Nếu locale chỉ làm thay đổi dữ liệu fixture nhưng schema/hợp đồng không khác, có thể dùng một operation chuẩn và nói rõ locale trong phần query parameter. Đừng tạo hàng trăm thư mục chỉ vì dữ liệu mẫu khác nhau. Ngược lại, nếu API version 1 và version 2 có field hoặc status khác nhau, phải tách chúng để tránh bảng mô tả của version này được chèn nhầm vào version kia.

## 10. Danh sách kiểm tra identifier và đường dẫn

Trước khi hoàn thành một thay đổi tài liệu, kiểm tra:

- Tên identifier mô tả resource/action/scenario đủ rõ chưa?
- Có test độc lập nào đang dùng cùng identifier trong một output directory không?
- Các snippet cần thiết có được test yêu cầu sinh ra không?
- Đường dẫn §{snippets}/<identifier>/<file>§ có khớp tên trong §document(...)§ không?
- Attribute §snippets§ có trỏ tới đúng output directory của test suite không?
- Build tài liệu có phụ thuộc test tạo snippet không?
- Output cũ có thể che giấu việc test không chạy hoặc rename không?
- Khi rename, tất cả include trong source tài liệu có được cập nhật không?
- Có đang chia output directory quá mức khiến cấu hình khó theo dõi không?
- Trang cuối cùng có hiển thị đúng tình huống và không đưa nhầm snippet success vào phần lỗi không?

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân phổ biến | Hướng khắc phục |
| --- | --- | --- |
| Include báo không tìm thấy file | Identifier hoặc attribute sai; test không sinh snippet | Đối chiếu §document(...)§ và §snippets§, chạy test |
| Trang render được nhưng ví dụ cũ | Output generated còn tồn dư | Làm sạch output, chạy test và render lại |
| Hai operation có response bị trộn | Dùng chung identifier | Tách identifier theo scenario |
| Test chạy song song ghi đè file | Nhiều test cùng output path | Identifier duy nhất hoặc output directory riêng |
| Snippet nằm ở folder khác mong đợi | Output directory của test khác với attribute Asciidoctor | Dùng một cấu hình nguồn chung hoặc cập nhật attribute |
| Rename test nhưng include vẫn tên cũ | Thiếu đồng bộ giữa test và tài liệu | Cập nhật cả hai và kiểm tra clean build |
| Tên identifier có ID fixture | Tên gắn với dữ liệu test biến động | Đặt tên theo resource/method/scenario |
| Version API dùng chung snippet | Schema các version bị trộn | Tách output hoặc identifier theo version rõ ràng |
| Chỉ một số snippet xuất hiện | Test không khai báo descriptor tương ứng | Bổ sung descriptor nếu thành phần thuộc hợp đồng |
| Build tài liệu không chạy test | Thiếu quan hệ task dependency | Nối task test trước task biên soạn |

## 12. Bài thực hành: quản lý tên và thư mục snippet

Giả sử API quản lý đơn hàng có các tình huống sau:

- §GET /api/orders/{id}§ trả §200§ khi đơn tồn tại.
- Cùng GET trả §404§ khi không tìm thấy.
- §POST /api/orders§ tạo đơn và trả §201§.
- §POST /api/orders§ trả §400§ nếu dữ liệu không hợp lệ.
- §PATCH /api/orders/{id}§ trả §409§ nếu trạng thái hiện tại không cho phép cập nhật.

**Nhiệm vụ:**

1. Đặt identifier cho cả năm operation theo một quy ước duy nhất.
2. Vẽ cấu trúc thư mục snippet dự kiến sau khi các test chạy.
3. Viết một đoạn §document(...)§ đại diện cho operation §POST§ thành công với §requestFields§, §responseHeaders§ và §responseFields§.
4. Tạo các đường dẫn include tương ứng cho trang §orders.adoc§.
5. Mô tả điều gì xảy ra nếu hai test GET success và GET 404 dùng cùng identifier.
6. Thay identifier §orders-create-success§ thành §orders-post-201§. Liệt kê những file phải sửa và các bước kiểm chứng trên clean build.
7. Đề xuất khi nào cần tách output directory riêng nếu dự án có thêm integration test và API v2.

**Tiêu chí đạt:** mọi operation có định danh duy nhất, thư mục phản ánh đúng tình huống, các include truy ngược được về test nguồn và clean build tạo đủ snippet mà không dùng output cũ.

## 13. Ghi nhớ

- Identifier trong §document("...")§ xác định thư mục nhóm các snippet của operation dưới output directory đã cấu hình.
- Tên tốt thường gồm **resource + method/action + scenario**, ổn định và duy nhất trong phạm vi output dùng chung.
- Một operation có nhiều snippet; **nhiều operation cùng route** cần identifier riêng nếu chúng minh họa các response hoặc tình huống khác nhau.
- Chia thư mục output theo module, suite hay version khi có nhu cầu lifecycle/tài liệu độc lập; tránh chia nhỏ quá mức.
- Đổi identifier cần cập nhật include và kiểm tra lại từ output sạch để không nhúng nhầm snippet tồn dư.
- Build/CI phải chạy test tạo snippet trước khi biên soạn Asciidoctor/Markdown và xác nhận đúng output directory được sử dụng.
