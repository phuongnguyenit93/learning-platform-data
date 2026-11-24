# Kiểm chứng request multipart và response không phải JSON

## Mục tiêu học tập

Trong **Spring Cloud Contract**, hợp đồng HTTP bằng **Groovy DSL** hoặc **YAML DSL** giúp thống nhất hành vi giữa **producer** (dịch vụ cung cấp API) và **consumer** (dịch vụ gọi API). Từ hợp đồng, công cụ sinh **producer contract test** để kiểm tra implementation và sinh **stub** cho consumer dùng với **Stub Runner**. Khi đưa vào CI, nhóm có thể phát hiện các thay đổi giao diện không tương thích trước lúc triển khai.

Trong chương **Kiểm thử HTTP**, chủ đề này tập trung vào hai tình huống thường khó hơn `application/json`:

1. **Request `multipart/form-data`:** body gồm nhiều phần, có thể chứa trường văn bản, tên tệp và dữ liệu tệp.
2. **Response không phải JSON:** producer trả `text/plain`, XML hoặc byte của tệp thay vì một JSON object.

Sau bài học, bạn có thể:

- Phân biệt **part name**, **filename**, **Content-Type của từng part** và **boundary** trong multipart.
- Viết một contract Groovy cho multipart request và response văn bản, rồi hiểu generated producer test và stub mapping cần kiểm chứng điều gì.
- Mô tả response `text/plain`, `application/xml` và `application/octet-stream`/`application/pdf` bằng Groovy hoặc YAML DSL phù hợp.
- Chọn **so khớp nguyên văn**, **XPath matcher** hay **so khớp byte** theo giao diện đã cam kết.
- Kiểm tra các tình huống lỗi như thiếu part, MIME không được hỗ trợ và response rỗng.
- Tách bạch **giới hạn của contract testing** với test về streaming, dung lượng, bảo mật, mạng và lưu trữ tệp thật.
- Xây dựng quy trình producer tests → stub artifact → Stub Runner consumer tests → CI đáng tin cậy.

## 1. Bài toán xuyên suốt: gửi chứng từ và tải biên nhận

Giả sử **Document Service** là producer, **Checkout Service** là consumer. Checkout cần đính kèm chứng từ giao hàng, sau đó đọc kết quả lưu trữ hoặc tải bản biên nhận.

Một thiết kế API minh họa:

| Tương tác | HTTP request | Request body | Response thành công |
|---|---|---|---|
| Đăng chứng từ | `POST /api/attachments` | `multipart/form-data` gồm `category` và `file` | `201 Created` với ID dạng `text/plain` |
| Đọc biên nhận | `GET /api/attachments/ATT-101/receipt` | Không có body | `200 OK` với XML |
| Tải nội dung tệp | `GET /api/attachments/ATT-101/content` | Không có body | `200 OK` với byte `application/octet-stream` |
| Kiểm tra lỗi upload | `POST /api/attachments` thiếu `file` | Multipart không hợp lệ theo nghiệp vụ | `400 Bad Request` với mã lỗi văn bản nếu API công bố |

Đây là **quy ước minh họa**, không phải endpoint mặc định của Spring Cloud Contract. Trong dự án thật, status, MIME, giới hạn tệp và cấu trúc phản hồi phải được producer và consumer thống nhất.

### Luồng kiểm chứng tổng thể

~~~mermaid
flowchart LR
    C["Groovy/YAML contract"] --> G["Sinh producer test"]
    C --> M["Sinh stub mapping"]
    F["Dữ liệu test + controller/app thật"] --> G
    G --> P["Producer contract test"]
    M --> A["Stub artifact"]
    A --> R["Stub Runner"]
    R --> U["Consumer test với HTTP client thật"]
    P --> CI["CI: kiểm tra đúng revision"]
    U --> CI
~~~

Điểm cần nhớ: **producer contract test** kiểm chứng producer thực sự trả kết quả theo contract; **consumer test** với Stub Runner kiểm chứng consumer gửi request và xử lý response giả lập theo contract. Hai kết quả bổ sung cho nhau, không thay thế nhau.

## 2. Multipart là tập hợp các part, không phải một JSON body

Với `multipart/form-data`, body được chia thành nhiều phần nhờ **boundary**. Mỗi phần có header và nội dung riêng.

Request minh họa:

~~~http
POST /api/attachments HTTP/1.1
Content-Type: multipart/form-data; boundary=AaB03x
Accept: text/plain

--AaB03x
Content-Disposition: form-data; name="category"

receipt
--AaB03x
Content-Disposition: form-data; name="file"; filename="proof.txt"
Content-Type: text/plain

signed by recipient
--AaB03x--
~~~

Ở đây:

- Header tổng `Content-Type` xác định request là multipart và công bố `boundary=AaB03x`.
- Part `category` là một field văn bản có giá trị `receipt`.
- Part `file` có **tên field** là `file`; `filename` là `proof.txt`.
- Content-Type của **file part** là `text/plain`, không đồng nghĩa với Content-Type của **toàn request**.
- Nội dung part file là byte của chuỗi `signed by recipient`.

Ví dụ chỉ dùng tệp văn bản để dễ đọc. Với PDF hoặc ảnh, phần nội dung tệp có thể chứa byte không hiển thị được trong Markdown.

### Bốn thứ rất dễ nhầm

| Khái niệm | Ví dụ | Nếu sai, điều gì xảy ra? |
|---|---|---|
| **Tên part** | `file` | Controller đọc `@RequestPart("file")` có thể báo thiếu part |
| **Filename** | `proof.txt` | Metadata tệp sai, quy tắc đặt tên hoặc loại tệp có thể thất bại |
| **MIME của part** | `text/plain` | Producer có thể từ chối hoặc giải mã sai dữ liệu của part |
| **Boundary** | `AaB03x` | Parser không thể chia body đúng nếu header và body lệch nhau |

**Boundary không phải mã nghiệp vụ.** HTTP client thường tự tạo một boundary mới khi gửi multipart. Không nên lấy chuỗi boundary ngẫu nhiên làm cam kết cố định của API. Nếu test/stub vô tình khóa cứng boundary, request multipart hợp lệ do một HTTP client khác tạo ra có thể không match.

### Multipart khác raw binary upload

Hai request sau không tương đương:

~~~http
PUT /api/attachments/ATT-101/content HTTP/1.1
Content-Type: application/octet-stream

<raw file bytes>
~~~

~~~http
POST /api/attachments HTTP/1.1
Content-Type: multipart/form-data; boundary=...

<one or more multipart parts>
~~~

Dòng `<raw file bytes>` chỉ biểu diễn ý tưởng, không phải ký tự được gửi thật. **Raw binary** đặt trực tiếp byte của file trong HTTP body; **multipart** bao một hoặc nhiều part có metadata. Đổi từ định dạng này sang định dạng kia là **thay đổi request contract**, dù cả hai đều được gọi là “upload file”.

## 3. Viết contract multipart bằng Groovy DSL

Giả sử producer trả một chuỗi ID sau khi chấp nhận upload:

~~~http
HTTP/1.1 201 Created
Content-Type: text/plain;charset=UTF-8
Location: /api/attachments/ATT-101

ATT-101
~~~

Một contract Groovy minh họa tại `src/test/resources/contracts/attachments/uploadTextFile.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Upload chung tu multipart va tra ID dang text'

    request {
        method 'POST'
        url '/api/attachments'

        headers {
            contentType('multipart/form-data;boundary=AaB03x')
            accept('text/plain')
        }

        multipart(
            category: 'receipt',
            file: named(
                name: 'proof.txt',
                content: 'signed by recipient',
                contentType: 'text/plain'
            )
        )
    }

    response {
        status 201
        headers {
            contentType('text/plain;charset=UTF-8')
            header('Location', '/api/attachments/ATT-101')
        }
        body('ATT-101')
    }
}
~~~

Trong Groovy DSL, `multipart(...)` mô tả form parts; `named(...)` mô tả một file part với tên tệp, nội dung và MIME. Đây là **fixture nhỏ** để kiểm tra giao tiếp, không phải một file PDF thực tế. Ví dụ dùng boundary rõ ràng để giải thích wire format và kiểm tra khả năng sinh request; khi áp dụng, cần đọc **generated test/mapping thực tế** để xác nhận phần match header không khóa cứng boundary khi client có quyền thay đổi nó.

### Đọc đúng các thành phần

| DSL | Dữ liệu được mô tả | Điều cần xác minh |
|---|---|---|
| `method 'POST'` | HTTP method | Test gửi `POST`; stub không nhận nhầm `GET` |
| `url '/api/attachments'` | Request path | Không bị đổi path hoặc context path ngoài ý muốn |
| `contentType('multipart/form-data;boundary=...')` | MIME tổng của request | Boundary đúng cho request sinh; stub match được request hợp lệ |
| `category: 'receipt'` | Form field | Part được gửi và được controller nhận đúng tên |
| `file: named(...)` | File part | Field `file`, filename, part MIME và content |
| `response.status 201` | HTTP status | Producer không âm thầm chuyển thành `200` |
| `Location` | URI tệp vừa tạo | Producer/consumer hiểu đúng URI theo giao diện |
| `body('ATT-101')` | Raw response string | Consumer nhận **văn bản**, không phải JSON string |

Có thể giữ filename cố định vì mục tiêu của fixture là một trường hợp cụ thể. Nếu consumer cần gửi nhiều filename khác nhau, hãy thiết kế matcher hợp lý và bổ sung test consumer cho biến thể đó. Đừng mặc định một fixture duy nhất có thể chứng minh mọi filename hoặc mọi loại tệp đều được hỗ trợ.

### Lưu ý về YAML DSL cho multipart

Spring Cloud Contract còn có YAML DSL; tuy nhiên, cấu trúc **multipart matcher/file part** trong YAML không được viết bằng cách bê nguyên hàm `multipart(...)` và `named(...)` của Groovy vào YAML. Hãy dùng schema YAML **đúng với phiên bản Spring Cloud Contract** của dự án khi khai báo multipart. Trong bài này, Groovy được chọn để trình bày multipart rõ nhất; các ví dụ YAML bên dưới tập trung vào **response không phải JSON**, nơi body có thể được biểu diễn trực tiếp bằng string hoặc file.

Không tạo đồng thời hai contract cùng request chỉ để “có cả Groovy và YAML” nếu điều đó tạo ra các stub mapping chồng lấn.

## 4. Producer cần khởi tạo gì để kiểm thử multipart?

Một contract chính xác chưa đủ nếu **generated test không gọi đúng controller**. Ví dụ producer Spring MVC có controller thật nhận form field và file part:

~~~java
package com.example.document;

import java.io.IOException;
import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class AttachmentController {

    private final AttachmentService service;

    public AttachmentController(AttachmentService service) {
        this.service = service;
    }

    @PostMapping(
        path = "/api/attachments",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<String> upload(
            @RequestParam("category") String category,
            @RequestPart("file") MultipartFile file) throws IOException {

        String id = service.save(
            category,
            file.getOriginalFilename(),
            file.getContentType(),
            file.getBytes()
        );

        return ResponseEntity
            .created(URI.create("/api/attachments/" + id))
            .contentType(MediaType.parseMediaType("text/plain;charset=UTF-8"))
            .body(id);
    }
}
~~~

`AttachmentService` là interface do dự án định nghĩa, ví dụ:

~~~java
package com.example.document;

public interface AttachmentService {
    String save(
        String category,
        String filename,
        String contentType,
        byte[] content
    );
}
~~~

Code trên minh họa **controller thực** mà generated test cần kiểm chứng; nó chưa phải ứng dụng hoàn chỉnh. Trong production, service cần xác thực, giới hạn kích thước, kiểm tra MIME/nội dung và lưu tệp an toàn. Trong test, ta có thể dùng một fake service xác định để tạo ID `ATT-101`.

### Base test class với MockMvc

Giả sử Maven/Gradle plugin được cấu hình tạo tests theo `MOCKMVC` mode và kế thừa `com.example.document.contract.DocumentContractBase`:

~~~java
package com.example.document.contract;

import com.example.document.AttachmentController;
import com.example.document.AttachmentService;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;

import java.nio.charset.StandardCharsets;

public abstract class DocumentContractBase {

    @BeforeEach
    protected void setUp() {
        AttachmentService fake = (category, filename, type, bytes) -> {
            if (!"receipt".equals(category)
                    || !"proof.txt".equals(filename)
                    || !"text/plain".equals(type)
                    || !"signed by recipient".equals(
                            new String(bytes, StandardCharsets.UTF_8))) {
                throw new IllegalArgumentException("Unexpected fixture");
            }

            return "ATT-101";
        };

        RestAssuredMockMvc.standaloneSetup(
            new AttachmentController(fake)
        );
    }
}
~~~

Lớp này tạo **controller thật** với fake `AttachmentService`, rồi gắn nó vào RestAssuredMockMvc. Nếu generated test gửi sai form field, sai tên file hoặc sai nội dung, logic fake hoặc controller có thể không đáp ứng hợp đồng. Vì thế dữ liệu fixture phải **khớp chính xác** với dữ liệu sinh từ contract.

**Nhưng có giới hạn:** fake service không chứng minh mã lưu trữ tệp thật hoạt động, không kiểm tra streaming hay virus scanning. Nếu ứng dụng sử dụng validator, filter, security, `@ControllerAdvice` hoặc converter tùy chỉnh, `standaloneSetup` có thể chưa dựng các thành phần đó. Khi cần kiểm tra chúng, cân nhắc `WebApplicationContext`, test Spring Boot đầy đủ hoặc integration test có server thật.

### Có cần một unit/integration test multipart riêng không?

Có khi consumer cần bảo đảm chi tiết **byte, metadata, dung lượng hoặc lỗi parsing**. Ngoài generated contract test, một controller test có thể dùng Spring MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class AttachmentControllerTest {

    private MockMvc mockMvc; // Được tạo trong setup của project.

    @Test
    void acceptsExpectedMultipartParts() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
            "file", "proof.txt", "text/plain",
            "signed by recipient".getBytes(java.nio.charset.StandardCharsets.UTF_8)
        );

        mockMvc.perform(multipart("/api/attachments")
                .file(file)
                .param("category", "receipt")
                .accept(MediaType.TEXT_PLAIN))
            .andExpect(status().isCreated())
            .andExpect(content().string("ATT-101"))
            .andExpect(header().string("Location", "/api/attachments/ATT-101"));
    }
}
~~~

Đây là **mẫu minh họa cần bổ sung setup `mockMvc`, controller và fake service trước khi chạy**; không phải một class test hoàn chỉnh. Test như vậy có ích để debug khi generated producer test fail vì form field hoặc serialization, nhưng không được dùng thay cho generated contract test trong pipeline.

## 5. Response `text/plain`: đừng biến chuỗi thành JSON

Một trong những lỗi dễ mắc là nghĩ mọi response body có dạng text đều là JSON. Hai response sau **khác về wire format**:

~~~http
HTTP/1.1 201 Created
Content-Type: text/plain;charset=UTF-8

ATT-101
~~~

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

"ATT-101"
~~~

Trường hợp đầu body là các byte UTF-8 của `ATT-101`. Trường hợp sau body là **JSON string**, bao gồm dấu ngoặc kép của JSON. Một consumer đọc raw text có thể không tương thích với việc đổi sang JSON string.

### Groovy DSL

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tra ma chung tu dang text'

    request {
        method 'GET'
        url '/api/attachments/ATT-101/id'
    }

    response {
        status 200
        headers {
            contentType('text/plain;charset=UTF-8')
        }
        body('ATT-101')
    }
}
~~~

### YAML DSL tương đương

~~~yaml
description: 'Tra ma chung tu dang text'
request:
  method: GET
  url: '/api/attachments/ATT-101/id'
response:
  status: 200
  headers:
    Content-Type: 'text/plain;charset=UTF-8'
  body: 'ATT-101'
~~~

Cả hai cách biểu diễn đều nhắm tới **raw text response**. Chọn một trong hai contract cho cùng tình huống khi đưa vào build.

### Kiểm chứng những gì?

- Status đúng, ví dụ `200` hoặc `201` theo giao diện.
- `Content-Type` đúng định dạng văn bản, kèm charset nếu đã cam kết.
- Body là chuỗi phù hợp; không tự thêm JSON quotes.
- Không có newline/whitespace cuối nếu giao diện công bố chuỗi nguyên văn.
- Consumer decode UTF-8 đúng, đặc biệt với nội dung tiếng Việt hoặc ký tự phi ASCII.

Với giá trị động (ví dụ ID được tạo mỗi lần), có thể dùng **matcher response** để generated producer test kiểm tra một định dạng (`ATT-[0-9]+`), trong khi stub trả `ATT-101` cố định. Matcher phải được cấu hình theo định dạng phù hợp; nếu consumer phụ thuộc vào body text nguyên văn, đừng dùng regex quá rộng như `.*`.

### Response nhiều dòng

Với thông báo văn bản hoặc CSV, YAML block scalar có thể biểu diễn newline:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'text/plain;charset=UTF-8'
  body: |-
    Order: ORD-101
    Status: ACCEPTED
~~~

`|-` giữ newline giữa hai dòng nhưng bỏ newline cuối. `|` sẽ xử lý newline cuối khác. Với response text, khác biệt một byte newline cũng có thể khiến assertion strict-equality thất bại; hãy chọn theo giao diện thật, không theo thói quen format YAML.

## 6. Response XML: kiểm tra nội dung theo XML, không phải JSONPath

Giả sử Checkout lấy biên nhận:

~~~http
GET /api/attachments/ATT-101/receipt HTTP/1.1
Accept: application/xml
~~~

Producer trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/xml;charset=UTF-8

<receipt>
  <attachmentId>ATT-101</attachmentId>
  <status>STORED</status>
  <createdAt>2026-01-15T08:30:00Z</createdAt>
</receipt>
~~~

Trong XML:

- Nội dung `<attachmentId>` là text node.
- `<status>` có ý nghĩa nghiệp vụ; consumer có thể phân nhánh theo `STORED`.
- `createdAt` là giá trị có thể thay đổi, nhưng định dạng cần ổn định.
- Nếu có XML namespace, XPath cần xử lý namespace tương ứng.

### Groovy DSL với XPath matcher

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tra bien nhan XML da luu'

    request {
        method 'GET'
        url '/api/attachments/ATT-101/receipt'
        headers {
            accept('application/xml')
        }
    }

    response {
        status 200
        headers {
            contentType('application/xml;charset=UTF-8')
        }
        body('''<receipt>
  <attachmentId>ATT-101</attachmentId>
  <status>STORED</status>
  <createdAt>2026-01-15T08:30:00Z</createdAt>
</receipt>''')

        bodyMatchers {
            xPath('/receipt/attachmentId/text()', byRegex('ATT-[0-9]+'))
            xPath('/receipt/status/text()', byRegex('STORED'))
            xPath('/receipt/createdAt/text()',
                byRegex('[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'))
        }
    }
}
~~~

`body` là **string XML**; `xPath(...)` nêu các node cần kiểm chứng. So khớp XPath phù hợp khi producer có thể đổi indentation hoặc cách format mà **không đổi ý nghĩa XML**. Tuy nhiên, matcher regex timestamp chỉ kiểm tra **hình dạng**, không tự chứng minh mọi ngày-giờ đều hợp lệ theo lịch.

Trong contract này, XML mẫu ổn định vẫn có thể được dùng để tạo stub cho consumer. Generated producer test nên kiểm tra các quy tắc XPath đã khai báo, chứ không nhất thiết buộc producer trả đúng từng dấu cách và timestamp mẫu. Hãy đọc generated test thực tế của phiên bản plugin để xác nhận.

### YAML DSL: XML body với block scalar và matcher

~~~yaml
description: 'Tra bien nhan XML da luu'
request:
  method: GET
  url: '/api/attachments/ATT-101/receipt'
  headers:
    Accept: 'application/xml'
response:
  status: 200
  headers:
    Content-Type: 'application/xml;charset=UTF-8'
  body: |-
    <receipt>
      <attachmentId>ATT-101</attachmentId>
      <status>STORED</status>
      <createdAt>2026-01-15T08:30:00Z</createdAt>
    </receipt>
  matchers:
    body:
      - path: '/receipt/attachmentId/text()'
        type: by_regex
        value: 'ATT-[0-9]+'
      - path: '/receipt/status/text()'
        type: by_regex
        value: 'STORED'
~~~

YAML `body: |-` tạo một string XML; phần `matchers.body` diễn đạt những XPath mà generated test cần kiểm chứng. Ở đây chỉ đặt hai matcher để minh họa; nếu consumer phụ thuộc chặt vào định dạng `createdAt` thì phải bổ sung matcher hoặc test tương ứng.

### XML namespace, encoding và lỗi thường gặp

Một response có thể dùng namespace:

~~~xml
<r:receipt xmlns:r="urn:example:receipt">
  <r:attachmentId>ATT-101</r:attachmentId>
</r:receipt>
~~~

XPath `/receipt/attachmentId/text()` trong ví dụ trước **không tự match** tài liệu có namespace này. Khi thiết kế contract, dùng XPath có xử lý prefix/namespace hoặc kỹ thuật `local-name()` và `namespace-uri()` phù hợp; đừng xóa namespace khỏi XML fixture chỉ để test xanh.

Những điểm khác cũng cần kiểm chứng:

1. XML có đúng cấu trúc element và attribute theo API không?
2. `Content-Type` là `application/xml` hay định dạng cụ thể đã thống nhất?
3. Byte thực tế có dùng charset phù hợp với header và khai báo XML không?
4. Nếu response có một phần dữ liệu động, matcher có quá rộng không?
5. Nếu consumer xác thực chữ ký số XML, việc đổi whitespace/canonicalization có ảnh hưởng không?

**Không dùng JSONPath cho XML.** Nếu cần kiểm tra XSD, chữ ký, schema hoặc quy tắc nghiệp vụ xuyên nhiều node, nên có test tích hợp/kiểm tra schema bổ sung; một vài XPath matcher không tự chứng minh toàn bộ tài liệu hợp lệ.

## 7. Response nhị phân: so khớp byte thay vì văn bản

Giả sử consumer tải nội dung tệp:

~~~http
GET /api/attachments/ATT-101/content HTTP/1.1
Accept: application/octet-stream
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="proof.bin"

<dãy byte nguyên gốc của tệp>
~~~

Phần nội dung trong dấu `<...>` chỉ để minh họa: body thật là **byte**, không phải chuỗi ký tự được gửi đi. Nếu producer trả PDF, có thể dùng `application/pdf`; nếu trả ảnh PNG, dùng `image/png`. Chọn MIME đúng theo giao diện đã cam kết.

### Groovy DSL: `fileAsBytes(...)`

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tai noi dung chung tu dang byte'

    request {
        method 'GET'
        url '/api/attachments/ATT-101/content'
    }

    response {
        status 200
        headers {
            contentType(applicationOctetStream())
            header('Content-Disposition',
                'attachment; filename="proof.bin"')
        }
        body(fileAsBytes('proof.bin'))
    }
}
~~~

`fileAsBytes('proof.bin')` yêu cầu Spring Cloud Contract đọc **byte từ file fixture** thay vì đọc như text. File phải có thật trong vùng tài nguyên mà contract tham chiếu, ví dụ:

~~~text
src/test/resources/contracts/attachments/
├── downloadContent.groovy
└── proof.bin
~~~

Trong tác vụ học này, các đường dẫn là ví dụ cho người đọc **tạo trong dự án thực hành**; bản thân bài Markdown không sinh file nhị phân.

### YAML DSL: `bodyFromFileAsBytes`

~~~yaml
description: 'Tai noi dung chung tu dang byte'
request:
  method: GET
  url: '/api/attachments/ATT-101/content'
response:
  status: 200
  headers:
    Content-Type: 'application/octet-stream'
    Content-Disposition: 'attachment; filename="proof.bin"'
  bodyFromFileAsBytes: 'proof.bin'
~~~

Tương ứng với YAML này, đặt `proof.bin` theo đường dẫn tương đối mà công cụ đọc được. Khác biệt quan trọng:

| Mục đích | Groovy | YAML | Phạm vi |
|---|---|---|---|
| Nội dung file **text** | `body(file('receipt.xml'))` | `bodyFromFile: 'receipt.xml'` | XML, text, JSON |
| Nội dung file **binary** | `body(fileAsBytes('proof.bin'))` | `bodyFromFileAsBytes: 'proof.bin'` | Byte không được ép thành String |

Không dùng `bodyFromFile` cho file nhị phân rồi mặc định mọi byte còn nguyên; quá trình xử lý text có thể thay encoding hoặc làm mất dữ liệu. Đối với dữ liệu byte, phải kiểm tra generated test, stub mapping/response và byte thực tế mà consumer nhận.

### Những assertion nên có với binary

Nếu giao diện cần bảo đảm nội dung **đúng từng byte**, có thể kiểm chứng bằng cách so sánh byte array với fixture hoặc checksum được tính trên byte. Nếu giao diện chỉ cam kết **đúng loại định dạng** và không cam kết một file cụ thể, test nên kiểm tra các đặc điểm có ý nghĩa như:

- `Content-Type` hợp lệ.
- `Content-Disposition` và filename nếu consumer phụ thuộc chúng.
- Body có byte và định dạng hợp lệ (ví dụ PDF magic bytes).
- Nội dung file đọc/giải mã được bằng công cụ phù hợp.
- Hash/checksum hoặc metadata được công bố khớp dữ liệu nhận được.

Không nên buộc producer trả đúng một bản PDF có timestamp/metadata nội bộ luôn thay đổi nếu giao diện không cam kết byte-for-byte. Với file lớn, cần test streaming và bộ nhớ riêng thay vì nhồi hàng chục MB vào mỗi fixture contract.

## 8. Response rỗng và lỗi: không được đánh đồng các tình huống

Response không phải JSON không có nghĩa là có thể bỏ qua **status** và **shape**.

| Tình huống | Response ví dụ | Ý nghĩa |
|---|---|---|
| Tạo chứng từ, trả ID text | `201` + `text/plain` body `ATT-101` | Có response body là chuỗi |
| Tạo chứng từ, không trả body | `201` với header `Location`, không body | Client lấy URI từ header |
| Xóa thành công | `204 No Content` | Không có response body |
| ID không tồn tại | `404` + error body theo chính sách API | Lỗi tài nguyên |
| MIME upload không hỗ trợ | `415 Unsupported Media Type` | Consumer cần đổi định dạng gửi |
| Multipart thiếu part | `400 Bad Request` hoặc mã phù hợp theo API | Request không thỏa quy tắc đã công bố |
| Upload vượt giới hạn | `413 Content Too Large` | Giới hạn kích thước, không tự retry nguyên dữ liệu |
| Đọc tệp lỗi hạ tầng | `503` hoặc lựa chọn khác theo API | Lỗi tạm thời, khác với không tìm thấy |

Đây là **các lựa chọn thiết kế tham khảo**; status chính xác và error body phải được thống nhất. Không tự suy rằng Spring Cloud Contract chọn `400` hay `415` thay cho ứng dụng.

### Contract lỗi multipart: thiếu part file

Một tình huống cần được kiểm tra nếu consumer dựa vào nó:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Multipart thieu file bi tu choi'

    request {
        method 'POST'
        url '/api/attachments'
        headers {
            contentType('multipart/form-data;boundary=AaB03x')
        }
        multipart(
            category: 'receipt'
        )
    }

    response {
        status 400
        headers {
            contentType('text/plain;charset=UTF-8')
        }
        body('FILE_PART_REQUIRED')
    }
}
~~~

Tình huống này giả định producer có cách trả lỗi ổn định khi thiếu `file`. Trong Spring MVC, lỗi binding có thể được framework chuyển thành status mặc định; để trả chính xác body `FILE_PART_REQUIRED`, ứng dụng có thể cần `@ControllerAdvice`. Base test phải dựng đúng exception handler; nếu không, generated test sẽ thấy một error body khác.

### `204` không có body

~~~yaml
description: 'Xoa chung tu thanh cong'
request:
  method: DELETE
  url: '/api/attachments/ATT-101'
response:
  status: 204
~~~

Không thêm `body: ''` hoặc JSON `null` chỉ để “điền cho đầy”. `204 No Content` và `200 OK` kèm body rỗng là hai giao diện khác nhau. Consumer test phải phân biệt khi ứng dụng cần hành vi cụ thể.

## 9. Xác minh generated producer test thật sự kiểm tra gì

Sau khi cài Spring Cloud Contract Verifier và plugin phù hợp, generated tests có thể được sinh trong các thư mục thường gặp:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

Tên class, framework test, cú pháp assertion và output path phụ thuộc phiên bản plugin/cấu hình; đọc **build log** nếu đường dẫn khác.

Với contract multipart → `201 text/plain`, reviewer cần đọc file generated test và xác nhận:

1. Request thực sự dùng `POST /api/attachments`.
2. Header `Content-Type` và **multipart parts** được tạo đúng, bao gồm `category`, tên field `file`, filename và byte nội dung.
3. Request được gửi vào **controller/application producer thật trong môi trường test**, không chỉ vào một stub.
4. Response assertion kiểm tra `201`.
5. Header `Content-Type` là text/plain đúng quy ước và `Location` phù hợp.
6. Body assertion xử lý **raw string** `ATT-101` chứ không parse như JSON object.
7. Test **đã chạy**, không bị skip hoặc không được test runner phát hiện.

Một mô tả rút gọn của generated test mong đợi (đây là **pseudocode**, không phải code do generator chắc chắn tạo từng dòng):

~~~text
GIVEN producer base test has registered AttachmentController

WHEN
  POST /api/attachments with multipart/form-data
  part category = "receipt"
  part file:
    filename = "proof.txt"
    content-type = "text/plain"
    content = bytes("signed by recipient")

THEN
  HTTP status == 201
  header Content-Type is text/plain;charset=UTF-8
  header Location == "/api/attachments/ATT-101"
  raw response body == "ATT-101"
~~~

Nếu generated test chỉ xác nhận status mà bỏ qua một field mà consumer phụ thuộc, hãy xem DSL, matcher, test mode và plugin configuration. **Không sửa file generated test thủ công** rồi cho rằng hợp đồng đã được cải thiện; generator sẽ ghi đè ở build sau.

### Với XML

Kiểm tra generated producer test có dùng **XPath/điều kiện XML** đúng vị trí thay vì chỉ tìm chuỗi `"STORED"` ở bất kỳ đâu trong response. Regex trên ID không nên chấp nhận ID rỗng, sai prefix hoặc chứa ký tự bất hợp lệ.

### Với binary

Kiểm tra response byte được đọc/tạo đúng từ fixture, MIME/header đúng. Nếu test chỉ kiểm tra status 200 mà không đọc byte, nó chưa chứng minh consumer sẽ tải được file hợp lệ. Tuy nhiên nếu byte vốn thay đổi có chủ đích, có thể cần assertion đặc điểm định dạng thay vì strict byte equality; đừng ép một matcher vượt quá cam kết API.

## 10. Đọc stub mapping và chạy consumer test

Stub Runner dùng artifact stub sinh từ hợp đồng, thường chứa **WireMock mappings** cho HTTP. Với multipart, mapping có thể có những điều kiện về method, URL, header và parts. Cách generator thể hiện điều kiện thay đổi theo phiên bản; cần đọc JSON mapping trong artifact thực tế.

Một **ví dụ WireMock mapping rút gọn để minh họa ý tưởng**:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/attachments",
    "multipartPatterns": [
      {
        "matchingType": "ALL",
        "headers": {
          "Content-Disposition": {
            "contains": "name=\"file\""
          }
        },
        "bodyPatterns": [
          {
            "equalTo": "signed by recipient"
          }
        ]
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "text/plain;charset=UTF-8",
      "Location": "/api/attachments/ATT-101"
    },
    "body": "ATT-101"
  }
}
~~~

**Lưu ý:** mapping trên chỉ minh họa các trường cần quan tâm; không khẳng định đây là JSON nguyên văn sinh ra từ contract ở mục 3. Mapping thực tế có thể chứa nhiều `multipartPatterns`, điều kiện về filename, `Content-Type`, field `category` và cách biểu diễn body khác. Hãy kiểm tra **đúng mapping được đóng gói** thay vì sao chép mapping minh họa làm bằng chứng.

### Những câu hỏi consumer test phải trả lời

- Client thật của Checkout có tạo request multipart đúng tên field `category` và `file` không?
- `filename` được gửi theo cách mà Document Service chấp nhận không?
- HTTP client có tự sinh boundary hợp lệ, và stub có match request đó không?
- Consumer có đọc được raw text `ATT-101` mà không cố deserialize JSON không?
- Consumer có xử lý XML bằng XML parser hoặc binary bằng byte stream không?
- Khi nhận `400`/`415`, consumer có hiển thị lỗi đúng thay vì coi là timeout?
- Test có thực sự gọi **Stub Runner đúng phiên bản artifact** hay nhầm sang producer đang chạy?

**Đừng hardcode cổng và version stub trong ứng dụng production.** Cấu hình client của consumer phải chuyển được sang URL stub trong test, đồng thời sử dụng URL producer thật trong môi trường triển khai.

### Với XML hoặc binary stub

- XML stub cần trả đúng `Content-Type` và XML body mà consumer parse được.
- Binary stub cần trả **byte**, không phải string base64 nếu API không công bố base64.
- Nếu consumer tải file theo stream, test cần đọc đến cuối stream và xác nhận tài nguyên được đóng/dọn dẹp khi cần.
- Nếu dùng header `Content-Disposition`, consumer không nên tin filename tùy ý để ghi file vào đường dẫn thiếu kiểm soát. Đây là vấn đề an toàn ứng dụng bên cạnh contract.

## 11. Multipart và non-JSON: những thay đổi dễ phá vỡ tương thích

| Thay đổi producer | Rủi ro với consumer | Kiểm tra phù hợp |
|---|---|---|
| Đổi tên part `file` thành `attachment` | Client vẫn gửi `file`, producer báo thiếu part | Contract request matcher, generated test và consumer Stub Runner test |
| Đổi API từ multipart sang raw binary | Cách đóng gói body hoàn toàn khác | Test gửi request thật và review thay đổi contract |
| Bỏ field `category` hoặc chuyển từ optional sang required | Consumer cũ không gửi field cần thiết | Contract cho trường hợp thiếu field và compatibility review |
| Đổi `text/plain` thành JSON string | Client đọc ID bị thêm dấu quote hoặc parse lỗi | Kiểm tra MIME và byte/string response |
| Đổi `application/xml` thành JSON | Consumer XML parser không đọc được | Contract content type + XPath/consumer parsing |
| XML thêm namespace hoặc đổi tên element | XPath/serialization của client có thể hỏng | XPath với namespace đúng, consumer test |
| Đổi `application/octet-stream` thành Base64 text | Byte nhận được khác định dạng công bố | Byte-level assertion + consumer decode test |
| Bỏ `Content-Disposition` hoặc đổi filename policy | Logic tải file có thể hỏng | Header assertion và consumer download test |
| Đổi `201` sang `200` hoặc `204` | Consumer phân nhánh sai hoặc mất body | Status, header, body contract tests |
| Bỏ giới hạn upload nhưng thay parser | File rất lớn có thể gây lỗi hệ thống | Integration, memory, security và performance tests |

**Producer test xanh với contract mới không đồng nghĩa consumer cũ tương thích.** Nếu nhóm thay cùng lúc implementation và Groovy/YAML DSL, generated test mới có thể vẫn xanh. Cần chạy consumer tests với **candidate stub cùng revision**, và với thay đổi phá vỡ cần có kế hoạch nâng cấp.

## 12. Những gì contract test không tự chứng minh

Trong trường hợp multipart và file, những bài test bổ sung thường quan trọng:

| Thuộc tính | Contract test cơ bản bảo vệ được gì? | Khi nào cần bổ sung? |
|---|---|---|
| Part name / filename / MIME | Tình huống được mô tả trong DSL | Parser đặc biệt, filename đa ngôn ngữ, chính sách file |
| File content | Một fixture nhỏ cụ thể | File lớn, streaming, checksum, hỏng dữ liệu |
| Dung lượng và timeout | Trường hợp cụ thể nếu có mô tả | Stress/performance/network test |
| Virus/malware, path traversal | Không tự bảo đảm | Security validation test |
| Lưu file lâu dài | Mock service có thể không kiểm tra | Persistence/integration test |
| Content-Disposition | Header mẫu có thể được kiểm tra | Kiểm soát filename trước khi ghi file ở consumer |
| XML tính hợp lệ | Một số XPath/regex | XSD, namespace phức tạp, chữ ký số, parser security |
| Retry khi upload thất bại | Một lần gọi contract chưa đủ | Idempotency và resilience test |
| Khả năng tương thích liên dịch vụ | Bảo vệ các case đã khai báo | Consumer cũ, versioning và deployment contract |

Ví dụ, nếu producer nhận và lưu file qua `MultipartFile.getBytes()`, test với một tệp rất nhỏ có thể qua, nhưng bộ nhớ tăng mạnh khi file thực có kích thước hàng trăm MB. Đây là vấn đề kiến trúc upload/streaming, không thể được kết luận chỉ bằng contract stub.

Tương tự, XML parser phải được cấu hình an toàn với external entities/XXE và file upload phải được kiểm tra loại nội dung, độ dài, nơi lưu; một contract test về status/body không tự thay thế các kiểm thử an toàn này.

## 13. Thiết kế ma trận kiểm chứng trước khi viết nhiều fixture

Thay vì tạo hàng chục file không rõ mục đích, hãy bắt đầu từ **nhánh hành vi mà consumer sử dụng**:

| ID | Request/response | Ý nghĩa đối với Checkout | Loại test chính |
|---|---|---|---|
| `UPLOAD_TEXT_OK` | Multipart `category` + file text → `201 text/plain` | Đọc được ID và Location | Producer contract + consumer Stub Runner |
| `UPLOAD_FILE_MISSING` | Multipart thiếu `file` → `400` | Hiển thị lỗi người dùng có thể sửa | Producer contract + consumer Stub Runner |
| `UPLOAD_BAD_MIME` | File part MIME không hỗ trợ → `415` | Không tự retry cùng file | Contract nếu đã công bố + validation test |
| `DOWNLOAD_RECEIPT_XML` | `GET` → `200 application/xml` | Parse được ID, status | Producer contract với XPath + consumer test |
| `DOWNLOAD_CONTENT_BIN` | `GET` → `200 application/octet-stream` | Đọc được byte file | Producer contract binary + consumer download test |
| `DELETE_NO_CONTENT` | `DELETE` → `204` không body | Không cố parse JSON/XML | Producer contract + consumer test |
| `LARGE_UPLOAD` | File lớn hơn giới hạn | Từ chối an toàn, không hết bộ nhớ | Integration/performance/security test |
| `CORRUPT_XML` | XML không hợp lệ hoặc sai namespace | Báo lỗi phù hợp | Parser/integration + contract lỗi nếu có cam kết |

Tập tình huống này là **đề xuất**, không phải yêu cầu tất cả API phải có `415` hoặc `400` giống nhau. Mỗi mục cần xuất phát từ quyết định thực tế của producer và consumer.

### Chọn fixture đủ nhỏ, đủ đại diện

- Text part: `receipt`, file `proof.txt`, nội dung `signed by recipient` đủ dễ đọc.
- XML: một biên nhận có ID, status, timestamp; thêm namespace nếu API sử dụng thật.
- Binary: một tệp nhỏ ổn định và được commit cùng contract, không lấy tệp ngẫu nhiên từ máy phát triển.
- Error: mã lỗi và status ổn định; không phụ thuộc stack trace hoặc đường dẫn nội bộ.
- Với dữ liệu động, dùng matcher đúng vị trí và giữ **giá trị mẫu cụ thể phía stub** để consumer test tái lập được.

## 14. CI: từ DSL đến stub cùng phiên bản

Một quy trình đáng tin cậy có thể tổ chức như sau:

~~~mermaid
sequenceDiagram
    participant Dev as Developer / PR
    participant Gen as Contract generator
    participant Prod as Producer test
    participant Art as Candidate stub artifact
    participant Cons as Consumer test
    Dev->>Gen: Cập nhật DSL và fixture
    Gen->>Prod: Sinh test HTTP multipart/non-JSON
    Prod->>Prod: Gọi controller/app, assert response
    alt Producer test đạt
        Gen->>Art: Sinh và đóng gói stub cùng revision
        Art->>Cons: Stub Runner tải đúng artifact
        Cons->>Cons: Gọi qua HTTP client thật
    else Producer test thất bại
        Prod-->>Dev: Chặn merge/phát hành
    end
    Cons-->>Dev: Kết quả tương thích
~~~

Kiểm tra tối thiểu trong pipeline:

1. **DSL được phát hiện:** tệp Groovy/YAML đúng vị trí và plugin sinh generated tests thực sự.
2. **Fixture tồn tại:** XML/text/binary file reference có đường dẫn hợp lệ và nằm trong nguồn build.
3. **Generated tests chạy:** không coi build xanh với `0 tests` là thành công.
4. **Request multipart đúng:** method, URL, các part, Content-Type và khả năng parse tại producer.
5. **Response đúng dạng:** text không bị JSON hóa, XML có cấu trúc đúng, binary được giữ nguyên byte khi giao diện cần.
6. **Stub artifact được ghim:** group/artifact/version/classifier hoặc build ID rõ ràng, không chạy nhầm bản cache cũ.
7. **Consumer test dùng client thật:** xác nhận ứng dụng gửi multipart và xử lý response non-JSON.
8. **Compatibility review:** mọi đổi MIME, part name, XML schema, binary encoding, status/header phải được đánh giá với consumer đang triển khai.

Một pipeline CI thực tế có thể gồm bước Maven `./mvnw verify` ở producer khi plugin được cấu hình đúng, tiếp theo bước publish stub và test consumer dùng Stub Runner. Với Gradle, dùng các task tương ứng của phiên bản plugin dự án. **Bài này mô tả quy trình**, không chạy build của một project mẫu.

## 15. Bài tập thực hành: phát hiện lỗi contract và consumer

### Tình huống

Nhóm Checkout có client gửi:

~~~text
POST /api/attachments
Content-Type: multipart/form-data; boundary=<client-generated>
parts:
  category = receipt
  file (filename=proof.txt, Content-Type=text/plain)
    = signed by recipient
~~~

Producer đã công bố kết quả:

~~~text
201 Created
Content-Type: text/plain;charset=UTF-8
Location: /api/attachments/ATT-101
body: ATT-101
~~~

Nhưng một PR đề xuất:

- Đổi tên part `file` thành `document`.
- Bỏ `Location`.
- Trả JSON `{"id":"ATT-101"}` với `Content-Type: application/json`.
- Cập nhật DSL và code producer cùng lúc; generated tests mới đều xanh.
- Không chạy consumer tests.

**Câu hỏi:**

1. Những thay đổi nào có thể phá vỡ Checkout?
2. Tại sao generated producer tests mới vẫn có thể xanh?
3. Cần đọc những artifact nào để xác nhận stub của PR mô tả điều gì?
4. Nếu Checkout vẫn dùng HTTP client gửi part `file`, yêu cầu gì cần được kiểm tra?
5. Nếu response được chuyển từ text sang JSON, kế hoạch chuyển đổi an toàn hơn là gì?

### Gợi ý đáp án

1. **Cả ba thay đổi giao diện đều đáng kiểm tra.** Tên part, header `Location` và MIME/shape response là những chi tiết consumer có thể đang phụ thuộc.
2. Generated tests mới chỉ chứng minh implementation producer phù hợp với **hợp đồng mới** trong những tình huống được mô tả; không tự chứng minh consumer cũ đã nâng cấp.
3. Đọc **Groovy/YAML DSL**, **generated producer tests**, **WireMock mapping** trong candidate stub và báo cáo producer test.
4. Chạy consumer test với **Stub Runner đang dùng đúng candidate stub**, để xem request multipart của client thật có match không, và cách consumer xử lý response.
5. Có thể duy trì giao diện cũ trong giai đoạn chuyển đổi, bổ sung endpoint/version mới, hoặc triển khai phối hợp có kiểm soát; lựa chọn phụ thuộc chính sách versioning và danh sách consumer.

### Bài tập mở rộng về XML và binary

**XML:** một response thêm default namespace `xmlns="urn:example:receipt"`, trong khi XPath cũ dùng `/receipt/attachmentId/text()`. Hãy giải thích vì sao XPath không còn match và đề xuất cách sửa theo namespace đã công bố.

**Binary:** producer trả Base64 text của file với `Content-Type: text/plain` thay vì raw byte `application/octet-stream`. Nếu consumer đang đọc `InputStream` và lưu byte nguyên bản, thay đổi này có tương thích không? Hãy thiết kế một test kiểm tra byte nhận được, MIME và checksum.

### Câu hỏi tự kiểm tra

- Vì sao boundary là chi tiết transport chứ không phải một field nghiệp vụ nên khóa cứng?
- Part name khác filename ở điểm nào?
- `text/plain` body `ATT-101` khác `application/json` body `"ATT-101"` như thế nào?
- Khi nào nên dùng XPath matcher thay vì so khớp nguyên văn XML?
- `fileAsBytes` khác `file` ở đâu?
- Vì sao `204 No Content` không nên có body JSON giả?
- Một generated producer test với fake storage có chứng minh việc lưu file thật không?
- Làm sao biết consumer test dùng đúng stub artifact của contract vừa thay đổi?

## 16. Ghi nhớ

**Multipart request và response không phải JSON cần được kiểm chứng ở đúng tầng dữ liệu.** Với multipart, hợp đồng phải nêu đúng **part name, filename, MIME part, nội dung** và tránh vô tình phụ thuộc boundary ngẫu nhiên. Với `text/plain`, phải bảo vệ **string/charset**; với XML, bảo vệ **cấu trúc, namespace, XPath**; với binary, bảo vệ **byte, Content-Type và metadata** theo cam kết giao diện.

Spring Cloud Contract giúp sinh **producer tests** và **stub** cho các hành vi đã mô tả; Stub Runner giúp consumer kiểm thử cách gọi và giải mã dữ liệu. Khi CI dùng cùng revision contract/stub và kết hợp thêm test tích hợp cho streaming, lưu trữ, bảo mật và file lớn, nhóm có bằng chứng đáng tin hơn để phát hiện thay đổi HTTP API không tương thích.
