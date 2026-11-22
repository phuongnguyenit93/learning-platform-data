# Encoding path segment và ký tự đặc biệt

## Mục tiêu bài học

Trong REST API, một path parameter thường được viết như **{assetKey}** trong URI template **/api/assets/{assetKey}**. Khi giá trị chỉ có chữ cái, chữ số và dấu gạch ngang, mọi thứ khá đơn giản. Nhưng nếu giá trị chứa **khoảng trắng, chữ có dấu, %, &, ?, #, / hoặc ;**, cách tạo URI và cách server diễn giải đường dẫn có thể thay đổi kết quả request.

Trong module **SPRING_REST_DOCS**, mục tiêu là tạo tài liệu REST API có thể kiểm chứng từ HTTP test với **MockMvc**, **WebTestClient** hoặc **REST Assured**. Bài này tập trung vào việc **mã hóa path segment** đúng cách, viết test cho các trường hợp đặc biệt và dùng **pathParameters(...)** để sinh snippet. Các snippet sau đó có thể đưa vào tài liệu **Asciidoctor/Markdown** và quy trình build, CI.

Sau bài học, bạn có thể:

- Phân biệt **URI template**, **giá trị path variable**, **URI đã percent-encode** và **giá trị đã decode** tại controller.
- Giải thích cách mã hóa UTF-8 bằng ký hiệu **%HH** và lý do khoảng trắng trong path thường thành **%20**.
- Phân biệt encoding cho **path segment** với cơ chế **application/x-www-form-urlencoded** thường dùng ở form và query.
- Dùng **UriComponentsBuilder** để mở rộng biến trong template và mã hóa giá trị đúng giai đoạn.
- Xác định rủi ro của **encoded slash (%2F)**, dấu phân đoạn **;**, **?**, **#**, dấu phần trăm và dot segments.
- Tạo bài test MockMvc sinh **path-parameters.adoc**, đồng thời kiểm tra URI encoding bằng test riêng.
- Thiết kế kiểm thử end-to-end qua HTTP server/proxy cho các đường dẫn nhạy cảm với encoding.

## 1. Path segment là gì?

Xét đường dẫn:

~~~text
/api/assets/guide-2026/versions/3
~~~

Các **path segments** được phân cách bằng dấu gạch chéo (**/**):

~~~text
api | assets | guide-2026 | versions | 3
~~~

URI template của endpoint có thể là:

~~~text
/api/assets/{assetKey}/versions/{version}
~~~

Trong trường hợp này, **guide-2026** là giá trị của **assetKey** và **3** là giá trị của **version**. Mỗi biến được thiết kế để chiếm **một đoạn** của đường dẫn.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| URI template | **/api/assets/{assetKey}** | Mẫu dùng để tạo request và tài liệu hóa tên biến |
| Giá trị thô | **Báo cáo Q4** | Dữ liệu nghiệp vụ trước khi mã hóa |
| Path đã mã hóa | **/api/assets/B%C3%A1o%20c%C3%A1o%20Q4** | Biểu diễn URI dùng percent-encoding cho các ký tự cần mã hóa |
| Giá trị controller mong đợi | **Báo cáo Q4** | Chuỗi được server/framework giải mã và bind vào **@PathVariable** |

**Tên biến** của Spring REST Docs vẫn là **assetKey** trong tất cả trường hợp. Không viết **parameterWithName("Báo cáo Q4")** hay **parameterWithName("B%C3%A1o...")** vì đây là các *giá trị*, không phải tên biến trong URI template.

## 2. Percent-encoding và UTF-8

URI có một tập ký tự mang ý nghĩa cấu trúc. Để biểu diễn các ký tự không được dùng trực tiếp tại một vị trí, HTTP client có thể mã hóa chúng thành chuỗi **%HH**, trong đó **HH** là hai chữ số thập lục phân mô tả **một byte**.

Khi một ký tự Unicode được mã hóa dưới dạng UTF-8, nó có thể chiếm nhiều byte; mỗi byte được biểu diễn bằng một ký hiệu phần trăm riêng. Ví dụ:

- Chữ **á** trong UTF-8 có hai byte **C3 A1**, nên thường được viết thành **%C3%A1** trong URI.
- Khoảng trắng ASCII có mã hex **20**, nên có thể được viết thành **%20**.
- Dấu **&** có byte hex **26**, nên khi cần mã hóa trở thành **%26**.

Do vậy, **Báo cáo Q4** có dạng path segment mã hóa:

~~~text
B%C3%A1o%20c%C3%A1o%20Q4
~~~

Đây là một ví dụ mã hóa theo UTF-8. Một số ký tự *không bắt buộc* phải mã hóa trong mọi thành phần URI; cách mã hóa cụ thể còn phụ thuộc vào vị trí ký tự và phương pháp xây dựng URI. Đối với **giá trị thay vào URI template**, nên dùng bộ mã hóa chặt chẽ của URI builder để tránh dữ liệu bị hiểu thành cú pháp đường dẫn.

### 2.1. Bảng ký tự đặc biệt trong path

Giả sử mỗi giá trị được đưa vào **một biến** trong template **/api/assets/{assetKey}**, rồi được mã hóa chặt chẽ khi mở rộng URI template:

| Giá trị gốc | Biểu diễn trong segment | Điều cần chú ý |
| --- | --- | --- |
| **guide-2026** | **guide-2026** | Chữ, số và dấu gạch ngang thường không cần escape |
| **Báo cáo Q4** | **B%C3%A1o%20c%C3%A1o%20Q4** | UTF-8 cho chữ có dấu; **%20** cho khoảng trắng |
| **A&B** | **A%26B** | Mã hóa dấu **&** trong giá trị |
| **question?draft** | **question%3Fdraft** | Dấu **?** nếu không escape có thể mở phần query |
| **release#2** | **release%232** | Dấu **#** nếu không escape có thể mở fragment phía client |
| **50%done** | **50%25done** | **%** phải được mã hóa để không bị nhầm với một escape sequence |
| **A+B** | **A%2BB** | Giữ dấu **+** là dữ liệu, tránh nhầm với quy ước form encoding |
| **part;draft** | **part%3Bdraft** | Dấu **;** có ý nghĩa đặc biệt trong một số cách xử lý path |
| **folder/file** | **folder%2Ffile** | Encoded slash vẫn là trường hợp nhạy cảm và có thể bị server/proxy từ chối |

Các giá trị trong bảng mô tả cách mã hóa của URI-template variable theo hướng **strict encoding**. Chúng không có nghĩa mọi reverse proxy và servlet container sẽ chấp nhận và trả về cùng giá trị khi nhận URL chứa các ký tự đặc biệt.

### 2.2. Không dùng quy tắc encoding của form cho path segment

**java.net.URLEncoder** chủ yếu tạo biểu diễn theo quy ước **application/x-www-form-urlencoded**, trong đó khoảng trắng thường trở thành dấu **+**:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String encoded = URLEncoder.encode(
    "Báo cáo Q4", StandardCharsets.UTF_8);
// Một phần kết quả: B%C3%A1o+c%C3%A1o+Q4
~~~

Trong **path**, dấu cộng có thể là một ký tự có nghĩa riêng, không phải lúc nào cũng được hiểu là khoảng trắng. Vì vậy **không nên dùng URLEncoder như công cụ chung để mã hóa path segment**. Hãy dùng URI builder nhận biết các thành phần của URI.

Trong phần query, dấu cộng cũng có thể được xử lý khác nhau tùy API/client và cơ chế form decoding. Khi cần biểu diễn chính xác một giá trị, hãy dùng phương thức tạo query parameter của HTTP client thay cho thao tác nối chuỗi URL thủ công.

## 3. Mã hóa giá trị trước hay sau khi mở rộng URI template?

Điểm dễ gây lỗi là nhầm **giá trị dữ liệu** với **cú pháp của URI template**. Giả sử một mã tài liệu thực sự có nội dung **folder/file** nhưng được mong đợi nằm trong *một* biến **{assetKey}**. Nếu thay thẳng mã này vào chuỗi đường dẫn:

~~~java
String key = "folder/file";
String url = "/api/assets/" + key;
// /api/assets/folder/file
~~~

URL kết quả có **hai đoạn** sau **/api/assets/**, không còn là một segment. Một route chỉ có **/api/assets/{assetKey}** thường không khớp request đó.

### 3.1. Sử dụng UriComponentsBuilder

Với Spring Framework:

~~~java
import org.springframework.web.util.UriComponentsBuilder;

String key = "Báo cáo Q4&Sales";

String encodedPath = UriComponentsBuilder
    .fromPath("/api/assets/{assetKey}")
    .encode()
    .buildAndExpand(key)
    .toUriString();

// /api/assets/B%C3%A1o%20c%C3%A1o%20Q4%26Sales
~~~

Ở ví dụ này, **encode()** được gọi trên **builder trước buildAndExpand(...)**. Đây là cách quan trọng để mã hóa các giá trị URI template chặt chẽ: ký tự dành riêng trong **giá trị** sẽ được escape để khó bị hiểu thành cấu trúc URI.

Khi cần một đối tượng URI để gửi request:

~~~java
import java.net.URI;

URI uri = UriComponentsBuilder
    .fromPath("/api/assets/{assetKey}")
    .encode()
    .buildAndExpand("Báo cáo Q4&Sales")
    .toUri();
~~~

Sử dụng **URI** trực tiếp khi API client hỗ trợ giúp giảm nguy cơ lớp khác tự mã hóa lại một chuỗi đã được escape.

### 3.2. Vì sao phải cẩn thận với thứ tự encode và expand?

Đây là hai ý niệm khác nhau:

- **Mã hóa URI template trước khi mở rộng:** URI builder nhận biết rõ chỗ nào là biến, do đó có thể escape chặt chẽ ký tự dành riêng nằm trong **giá trị**.
- **Mã hóa toàn bộ URI sau khi đã chèn giá trị:** lúc này một số ký tự dành riêng có thể được xem như cú pháp URI hợp lệ, ví dụ dấu **/** có thể được giữ là dấu phân tách path.

Đối với giá trị có **/**, **;** hoặc các ký tự dành riêng khác, hai cách này có thể tạo kết quả khác nhau. Hãy ưu tiên API mở rộng URI template và thử nghiệm đúng đường đi của request ở phiên bản Spring/client đang dùng.

### 3.3. Không encode hai lần

Giả sử giá trị gốc là **Báo cáo**. Sau khi mã hóa, nó có dạng:

~~~text
B%C3%A1o%20c%C3%A1o
~~~

Nếu đưa nguyên chuỗi **đã mã hóa** này như một **giá trị thô** vào URI builder có encoding, ký tự **%** có thể bị escape thành **%25**, dẫn đến:

~~~text
B%25C3%25A1o%2520c%25C3%25A1o
~~~

Đây là **double encoding**. Server giải mã một lần sẽ thấy dấu phần trăm và các ký hiệu escape còn nguyên, thay vì giá trị nghiệp vụ ban đầu.

Quy tắc thực hành: **quản lý giá trị ở dạng chưa encode**, rồi để **một lớp chịu trách nhiệm mã hóa URI**. Nếu đã có đối tượng **URI** hợp lệ, truyền nó bằng overload nhận **URI** khi phù hợp, tránh chuyển đổi vòng qua chuỗi rồi mở rộng/mã hóa thêm lần nữa.

## 4. Những ký tự đặc biệt cần xử lý theo ngữ cảnh

### 4.1. Dấu hỏi (?) và dấu thăng (#)

Trong URL:

~~~text
/api/assets/report?draft
/api/assets/report#v2
~~~

Dấu **?** đánh dấu phần bắt đầu của query string; dấu **#** đánh dấu fragment. Fragment thường được client xử lý và **không được gửi tới server** trong HTTP request target.

Nếu **report?draft** hay **report#v2** thực sự là giá trị *một path segment*, chúng cần được mã hóa khi tạo URI:

~~~text
/api/assets/report%3Fdraft
/api/assets/report%23v2
~~~

Không nối thủ công các giá trị chứa **?** và **#** vào URL, vì request khi đó có thể tới tài nguyên khác với tài nguyên mà người gọi dự định.

### 4.2. Dấu phần trăm (%) và escape không hợp lệ

Ký tự **%** mở đầu một escape sequence dạng **%HH**. Ví dụ, **%20** có nghĩa là byte khoảng trắng khi giải mã phù hợp. Chuỗi như **%G1** không phải một escape hợp lệ.

Nếu giá trị nghiệp vụ chứa dấu **%** thật, chẳng hạn **50%done**, biểu diễn URI có thể là **50%25done**. Không nên dùng cách xử lý chuỗi thủ công như tìm/thay dấu **%**, vì rất dễ tạo lỗi mã hóa kép hoặc cho phép giải mã nhiều lần ở các tầng khác nhau.

Request với percent-escape sai cú pháp có thể bị HTTP client, proxy hoặc server từ chối **trước khi vào controller**. Kiểm thử phản hồi của hệ thống triển khai thực tế thay vì mặc định lỗi luôn được controller xử lý.

### 4.3. Dấu gạch chéo (/) và encoded slash (%2F)

Trong một segment, dấu **/** là trường hợp khó nhất vì nó vốn phân tách các đoạn đường dẫn:

~~~text
/api/assets/folder/file       # Hai đoạn: folder, file
/api/assets/folder%2Ffile     # Mong muốn biểu diễn một giá trị chứa /
~~~

Dù URI builder có thể tạo **%2F**, không có bảo đảm mọi hạ tầng sẽ đối xử giống nhau:

1. Reverse proxy, firewall hoặc container có thể **từ chối encoded slash**.
2. Một lớp có thể decode **%2F** thành **/** trước khi Spring thực hiện route matching.
3. Cách xử lý có thể khác giữa môi trường test MockMvc và ứng dụng chạy qua HTTP server thật.
4. Việc decode sai tầng hoặc decode nhiều lần có thể tạo khác biệt về routing và kiểm soát truy cập.

**Khuyến nghị thiết kế:** nếu một ID có thể chứa dấu **/**, hãy cân nhắc chọn định dạng ID an toàn cho một segment, dùng mã định danh thay thế hoặc thiết kế API khác. Không mặc định rằng mã hóa dấu gạch chéo là giải pháp hoạt động trong mọi cấu hình.

Tránh vô tình cho phép đường dẫn như **../**, **%2E%2E%2F** hoặc các biến thể có thể trở thành path traversal sau khi decode. Nếu giá trị path dùng để truy cập file, luôn áp dụng kiểm soát đường dẫn đích ở tầng lưu trữ và kiểm tra quyền truy cập, không chỉ dựa vào encoding.

### 4.4. Dấu chấm phẩy (;) và dấu chấm (.)

Dấu **;** có thể liên quan đến các cơ chế như **matrix variables/path parameters** của một số framework hoặc cách xử lý route; điều đó khác với thuật ngữ **path parameter** của REST Docs đang dùng để chỉ biến **{...}**.

Nếu **;** là một phần của mã nghiệp vụ, hãy để URI builder mã hóa giá trị và kiểm thử trên server thực. Nếu không cần thiết, nên dùng slug/ID chỉ chứa ký tự an toàn.

Dấu **.** trong tên như **report.v2** thường không gây vấn đề. Tuy nhiên, các đoạn đường dẫn đúng bằng **.** hoặc **..** có ý nghĩa đặc biệt trong quá trình chuẩn hóa URI. Không dùng **.** hoặc **..** làm định danh path segment nếu hệ thống có thể xử lý chúng theo cơ chế điều hướng thư mục.

## 5. Controller mẫu và hợp đồng API

Ví dụ một API tìm tài liệu theo khóa:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AssetController {

    @GetMapping("/api/assets/{assetKey}")
    AssetResponse getAsset(@PathVariable("assetKey") String assetKey) {
        return new AssetResponse(assetKey);
    }
}

record AssetResponse(String assetKey) {}
~~~

Controller mẫu trả lại giá trị đã bind để minh họa. Khi triển khai thực tế, cần có service kiểm tra mã tồn tại, kiểm tra quyền truy cập và quy ước ký tự cho **assetKey**.

Một hợp đồng khả thi là yêu cầu mã tài liệu dạng **slug** chỉ gồm chữ, số và dấu gạch ngang. Nếu áp dụng giới hạn này, người gọi không cần gửi khoảng trắng hoặc dấu **/** trên path; còn tên hiển thị có dấu được lưu trong thuộc tính riêng, chẳng hạn **displayName**.

~~~text
GET /api/assets/quarterly-report-2026

{
  "assetKey": "quarterly-report-2026",
  "displayName": "Báo cáo quý 4 năm 2026"
}
~~~

Đây thường là lựa chọn đơn giản cho API dùng rộng rãi: **khóa định danh** ổn định trong path và **tên hiển thị** giàu ký tự Unicode trong JSON response.

Nếu hợp đồng yêu cầu ID Unicode có khoảng trắng, cần mô tả cách client tạo URI và viết test end-to-end xác nhận giá trị nhận được đúng với giá trị ban đầu.

## 6. Tạo snippet bằng MockMvc và kiểm thử encoding riêng

Ví dụ sử dụng **Java 17+**, **JUnit 5**, **Spring Boot 3.x** và **spring-restdocs-mockmvc**. Với Gradle và BOM quản lý phiên bản của Spring Boot:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

### 6.1. Test sinh tài liệu path parameter

Tạo **AssetDocumentationTest.java**, đặt cùng package với **AssetController**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AssetController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class AssetDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentAssetKey() throws Exception {
        mockMvc.perform(
                get("/api/assets/{assetKey}", "quarterly-report-2026")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.assetKey")
                .value("quarterly-report-2026"))
            .andDo(document("asset-get",
                pathParameters(
                    parameterWithName("assetKey")
                        .description("Khóa tài liệu trong một path segment; "
                            + "sử dụng slug, ví dụ quarterly-report-2026")
                )
            ));
    }
}
~~~

Ở đây **get(...)** được static import từ **RestDocumentationRequestBuilders** để giữ **URI template** và tên biến **assetKey** cho REST Docs. Việc này quan trọng vì **pathParameters(...)** cần tên biến để đối chiếu với **parameterWithName("assetKey")**.

**Không viết** descriptor bằng giá trị đã URL-encode: snippet mô tả ý nghĩa của **assetKey**, còn bảng request mẫu do REST Docs sinh từ request được thực thi.

Trong thư mục đầu ra dự kiến có:

~~~text
build/generated-snippets/asset-get/
├── path-parameters.adoc
├── http-request.adoc
├── http-response.adoc
└── curl-request.adoc
~~~

Danh sách trên chỉ minh họa một số snippet; cấu hình thực tế có thể sinh thêm các tệp khác.

### 6.2. Test thuần xác minh kết quả mã hóa URI

Nên có một test riêng kiểm tra **chuỗi URI được tạo ra** trước khi request đi qua network:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.web.util.UriComponentsBuilder;

import static org.assertj.core.api.Assertions.assertThat;

class AssetUriEncodingTest {

    @Test
    void encodeUnicodeSpaceAndAmpersandInTemplateVariable() {
        String path = UriComponentsBuilder
            .fromPath("/api/assets/{assetKey}")
            .encode()
            .buildAndExpand("Báo cáo Q4&Sales")
            .toUriString();

        assertThat(path).isEqualTo(
            "/api/assets/B%C3%A1o%20c%C3%A1o%20Q4%26Sales");
    }

    @Test
    void encodeLiteralPercentOnce() {
        String path = UriComponentsBuilder
            .fromPath("/api/assets/{assetKey}")
            .encode()
            .buildAndExpand("50%done")
            .toUriString();

        assertThat(path).isEqualTo("/api/assets/50%25done");
    }
}
~~~

Hai test này kiểm tra **bước tạo URI**; chúng không chứng minh một reverse proxy sẽ chấp nhận mọi request chứa percent-encoding. Nếu có endpoint cho phép giá trị Unicode hay ký tự dành riêng trong ID, hãy bổ sung integration test đi qua **cùng server/proxy** với môi trường triển khai.

### 6.3. Kiểm tra một giá trị sau khi server decode

Với hợp đồng chấp nhận **Báo cáo Q4** như một mã tài liệu, bài kiểm thử tích hợp cần xác nhận chuỗi nhận ở controller không còn là **B%C3%A1o%20...**. Kiểm thử HTTP end-to-end có thể làm theo quy trình:

1. Gọi URI builder bằng giá trị thô **Báo cáo Q4**.
2. Quan sát request target có đoạn **B%C3%A1o%20c%C3%A1o%20Q4**.
3. Xác nhận handler nhận đúng **Báo cáo Q4**.
4. Xác nhận JSON response hoặc dữ liệu nghiệp vụ chứa đúng chuỗi.
5. Kiểm tra route và response qua reverse proxy/ingress nếu API được công bố sau các tầng này.

Không suy ra rằng MockMvc mô phỏng đầy đủ mọi quy tắc URI decoding của servlet container hoặc reverse proxy. Hãy giữ test tạo URI riêng, test controller riêng và test triển khai thật cho các ký tự nhạy cảm.

## 7. WebTestClient và REST Assured

Cùng một descriptor **parameterWithName(...)** được dùng trong cả ba HTTP test client. Phần khác biệt là cách tạo URI và gắn **document(...)**.

### 7.1. WebTestClient

Khi **WebTestClient** đã có cấu hình Spring REST Docs (ví dụ qua **documentationConfiguration(...)**), đoạn test với slug an toàn có thể là:

~~~java
webTestClient.get()
    .uri("/api/assets/{assetKey}", "quarterly-report-2026")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("asset-webtestclient",
        pathParameters(
            parameterWithName("assetKey")
                .description("Slug nhận diện tài liệu")
        )
    ));
~~~

Trong ví dụ này, **document(...)** thuộc **WebTestClientRestDocumentation**. Nếu cần mã hóa giá trị phức tạp, nên tạo URI bằng API URI builder của client; kiểm tra URI thực sự được gửi qua HTTP để tránh phụ thuộc vào giả định rằng mọi overload của **uri(...)** thực hiện encoding giống nhau.

### 7.2. REST Assured

Với **RequestSpecification spec** đã gắn cấu hình REST Docs:

~~~java
given(spec)
    .filter(document("asset-rest-assured",
        pathParameters(
            parameterWithName("assetKey")
                .description("Slug nhận diện tài liệu")
        )
    ))
    .pathParam("assetKey", "quarterly-report-2026")
    .when()
    .get("/api/assets/{assetKey}")
    .then()
    .statusCode(200);
~~~

Ở đây **document(...)** thuộc **RestAssuredRestDocumentation**. **pathParam(...)** gán **giá trị request**, trong khi **parameterWithName(...)** mô tả **tên biến**. Với giá trị chứa **%**, **/** hoặc ký tự Unicode, hãy xem và kiểm thử cấu hình URL encoding của REST Assured thay vì tự nối URL đã mã hóa với URI template.

## 8. Đưa tài liệu encoding vào snippet và Asciidoctor

Người dùng API cần biết **định dạng ID được phép** và **cách truyền** giá trị chứa ký tự đặc biệt. Chỉ ghi “Mã tài liệu” có thể chưa đủ.

Một descriptor hữu ích:

~~~java
pathParameters(
    parameterWithName("assetKey")
        .description("Slug của tài liệu, gồm chữ cái ASCII, chữ số và "
            + "dấu gạch ngang; ví dụ quarterly-report-2026")
)
~~~

Nếu API **thực sự cho phép** tên Unicode và khoảng trắng, mô tả nên đổi cho đúng hợp đồng, ví dụ: “Khóa tài liệu; client phải percent-encode giá trị trong một path segment bằng UTF-8”. Đồng thời, phải có test HTTP chứng minh các trường hợp đã công bố hoạt động qua hệ thống triển khai.

Ví dụ file **src/docs/asciidoc/index.adoc**:

~~~asciidoc
= Asset API
:toc: left

== Lấy tài liệu theo khóa

GET /api/assets/{assetKey}

Khóa tài liệu phải tuân theo quy ước được ghi trong bảng bên dưới.

=== Path parameters

include::{snippets}/asset-get/path-parameters.adoc[]

=== HTTP request

include::{snippets}/asset-get/http-request.adoc[]

=== HTTP response

include::{snippets}/asset-get/http-response.adoc[]
~~~

Ví dụ Gradle Groovy DSL khi đã có plugin **org.asciidoctor.jvm.convert**:

~~~groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
~~~

Trong CI, chạy test để tạo snippet trước bước dựng tài liệu, rồi chỉ xuất bản nếu test và Asciidoctor đều thành công. Một bài kiểm thử cụ thể nên thất bại khi tên biến đổi từ **{assetKey}** thành **{fileKey}** mà descriptor không cập nhật. Kiểm thử encoding riêng giúp phát hiện việc URL builder bị thay đổi ngoài ý muốn.

REST Docs thông thường sinh snippet AsciiDoc. Nếu dự án xuất bản tài liệu Markdown, cần bộ chuyển đổi hoặc cơ chế nhúng tương thích với trình dựng Markdown, vì **include::...[]** không phải cú pháp Markdown tiêu chuẩn.

## 9. Lỗi thường gặp và cách khắc phục

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| URL chứa khoảng trắng hoặc ký tự tiếng Việt bị từ chối | Chèn chuỗi chưa encode vào URL | Dùng URI builder với UTF-8 và encoding cho template variable |
| Controller nhận **+** thay vì khoảng trắng | Dùng **URLEncoder** cho path | Dùng cách encode path segment tạo **%20** cho khoảng trắng |
| Giá trị nhận có chữ **%20** thay vì khoảng trắng | Double encoding hoặc tầng xử lý không decode như mong đợi | Theo dõi giá trị gốc, URI gửi đi và số lần encode/decode |
| **/api/assets/folder/file** không khớp một biến **{assetKey}** | Dấu **/** tạo thêm path segment | Tránh **/** trong ID hoặc thiết kế đường dẫn khác |
| Request chứa **%2F** bị chặn ở proxy | Tầng trung gian hạn chế encoded slash | Kiểm thử hạ tầng thực; cân nhắc ID an toàn thay vì nới lỏng không kiểm soát |
| Chuỗi **report#v2** tới server chỉ còn **report** | Phần sau **#** được xem là fragment | Encode dấu thăng thành **%23** trong giá trị |
| Chuỗi **report?draft** bị hiểu như query | **?** chưa được escape | Encode **?** trong giá trị thành **%3F** |
| Request có **%G1** bị từ chối trước controller | Percent-escape sai cú pháp | Dùng URI builder, không tự ghép **%HH** |
| Spring REST Docs báo path parameter thiếu hoặc không tồn tại | Descriptor dùng tên sai hoặc request mất URI template | Dùng **RestDocumentationRequestBuilders** và **parameterWithName("assetKey")** |
| Snippet đúng nhưng endpoint fail trên production | Khác biệt giữa MockMvc và proxy/container về decoding | Bổ sung integration test qua cùng đường đi HTTP như production |
| Mã chứa **..** dẫn tới đường dẫn ngoài phạm vi | Path normalization hoặc xử lý file path không an toàn | Kiểm tra/chuẩn hóa đường dẫn và giới hạn truy cập ở service/storage |

## 10. Bài thực hành

Bạn cần tài liệu hóa endpoint:

~~~text
GET /api/reports/{reportKey}
~~~

Giả sử hai nhóm mã báo cáo được phép:

- **Mã an toàn:** **report-Q4-2026**, chỉ gồm ký tự ASCII chữ, số và dấu gạch ngang.
- **Mã Unicode:** **Báo cáo Q4**, có khoảng trắng và tiếng Việt có dấu.

Hãy thực hiện:

1. Viết controller dùng **@PathVariable("reportKey") String reportKey** và trả JSON chứa mã đã nhận.
2. Viết test MockMvc dùng **RestDocumentationRequestBuilders.get("/api/reports/{reportKey}", "report-Q4-2026")**, kiểm tra HTTP 200 và sinh **report-get/path-parameters.adoc**.
3. Viết test riêng cho **UriComponentsBuilder**. Cho giá trị thô **Báo cáo Q4**, xác nhận path tạo được là **/api/reports/B%C3%A1o%20c%C3%A1o%20Q4**.
4. Viết thêm test với **report#2**, **50%done** và **A&B** để quan sát kết quả **%23**, **%25** và **%26**.
5. Kiểm thử thực tế qua HTTP server/proxy cho mã Unicode (nếu API công bố hỗ trợ mã này), xác nhận controller nhận đúng chuỗi **Báo cáo Q4**.
6. Giải thích vì sao **folder/report** là mã khó hỗ trợ trong một path segment, ngay cả khi URI builder tạo được **folder%2Freport**.
7. Nhúng snippet path parameters cùng HTTP request/response vào **index.adoc** và chạy quy trình test → Asciidoctor trong build/CI.

Gợi ý descriptor:

~~~java
pathParameters(
    parameterWithName("reportKey")
        .description("Khóa báo cáo; nếu có Unicode hoặc khoảng trắng, "
            + "client phải mã hóa an toàn trong path segment")
)
~~~

**Tiêu chí hoàn thành:** test tài liệu hóa sinh snippet có đúng biến **reportKey**; test URI encoding xác nhận được các giá trị đặc biệt; hợp đồng API chỉ tuyên bố hỗ trợ những định dạng đã được kiểm thử; tài liệu được dựng thành công từ snippet.

## Ghi nhớ

**Encoding path segment** giúp giữ dữ liệu URI không bị hiểu nhầm thành dấu phân tách hoặc thành phần điều khiển URL. Hãy giữ giá trị ở dạng thô, mở rộng URI template và mã hóa bằng URI builder ở đúng giai đoạn; chú ý UTF-8, **%20**, **%25**, và đặc biệt là **%2F**. **Spring REST Docs** dùng **pathParameters(...)** để kiểm chứng tên biến và sinh tài liệu từ HTTP test, còn tính đúng của encoding/decoding phải được kiểm thử ở client, controller và các tầng HTTP triển khai. Kết hợp hai loại kiểm thử trong build, CI để tài liệu phản ánh đúng hợp đồng của API.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring Framework: URI Links](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html), [RFC 3986: URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986).
