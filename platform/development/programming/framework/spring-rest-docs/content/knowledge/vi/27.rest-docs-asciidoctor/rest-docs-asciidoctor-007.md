# Đặt tiêu đề, anchor và liên kết tới operation

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Tổ chức tiêu đề AsciiDoc theo cấu trúc tài liệu API và đặt tên operation nhất quán.
- Tạo anchor ID tường minh để liên kết đến resource, operation, request, response hoặc tình huống lỗi.
- Dùng cross-reference trong cùng trang và xref giữa các file AsciiDoc.
- Phân biệt anchor/URL điều hướng với document identifier mà Spring REST Docs dùng để ghi snippet.
- Tạo mục lục và trang tổng quan có liên kết tới operation.
- Tránh anchor trùng, ID tự sinh không ổn định, đường dẫn xref sai và liên kết hỏng khi build.

## 1. Tiêu đề và điều hướng trong tài liệu API

Một tài liệu REST API thường có nhiều resource, mỗi resource có nhiều operation. Người đọc đi từ trang tổng quan đến resource, mở operation rồi xem request, response hoặc lỗi. Tiêu đề và liên kết cần phản ánh cấu trúc đó.

Ví dụ:

```text
API Guide
├── Authentication
├── Orders
│   ├── List orders
│   ├── Get an order
│   ├── Create an order
│   └── Cancel an order
└── Error responses
```

Trong Asciidoctor:

- Tiêu đề tài liệu dùng dấu bằng.
- Section cấp một dùng hai dấu bằng; các cấp tiếp theo tăng thêm một dấu bằng.
- Anchor xác định một vị trí để liên kết đến.
- Cross-reference đưa người đọc đến anchor khác.
- Xref giữa các file đưa người đọc sang tài liệu khác.
- External link mở tài nguyên ngoài như OAuth reference hoặc trang hỗ trợ.

Không dùng heading chỉ để tạo chữ lớn. Cấp heading cần biểu đạt đúng quan hệ nội dung để mục lục và outline có ý nghĩa.

## 2. Phân biệt ba loại định danh

Spring REST Docs và Asciidoctor đều sử dụng tên định danh, nhưng mỗi loại có mục đích khác nhau.

| Định danh | Ví dụ | Được dùng ở đâu |
| --- | --- | --- |
| Document identifier | orders-get | document("orders-get", ...); xác định thư mục snippet được sinh |
| Anchor ID | orders-get hoặc orders-get-request | Liên kết đến vị trí trong AsciiDoc/HTML |
| File/URL đích | orders/get.adoc hoặc orders.html | Xref giữa các trang hoặc URL tài liệu đã xuất bản |

Có thể đặt document identifier và anchor ID cùng chuỗi, nhưng chúng không tự liên kết với nhau. Thư mục generated-snippets/orders-get/ không tự tạo anchor ID orders-get trong HTML. Tác giả cần đặt anchor hoặc heading phù hợp trong AsciiDoc.

Ví dụ test:

```java
andDo(document("orders-get",
    responseFields(
        fieldWithPath("id").description("Mã đơn hàng")
    )
))
```

Trong AsciiDoc:

```asciidoc
[[orders-get]]
== Lấy thông tin đơn hàng

include::{snippets}/orders-get/http-request.adoc[]
```

Anchor orders-get là liên kết điều hướng; document identifier orders-get là tên thư mục snippet. Chúng chỉ có quan hệ vì người viết chủ động dùng cùng tên.

## 3. Cấu trúc tiêu đề AsciiDoc

Một file AsciiDoc thông thường có document title ở đầu:

```asciidoc
= Orders API
:toc:
:toclevels: 3

== Tổng quan

== Orders

=== Lấy thông tin đơn hàng

=== Tạo đơn hàng

=== Hủy đơn hàng
```

Ý nghĩa:

- = Orders API là tiêu đề tài liệu.
- == Tổng quan và == Orders là section cấp một.
- Các operation là section con.
- toc bật table of contents.
- toclevels giới hạn độ sâu heading hiển thị trong mục lục.

Với tài liệu lớn, nên thống nhất một quy ước: file tổng quan sở hữu tiêu đề chính và điều hướng resource; file operation được include hoặc render như trang con theo cấu trúc heading đã định trước.

Không nhảy cấp heading chỉ để đạt cỡ chữ mong muốn. Nếu operation là con của resource, dùng cấp heading phản ánh quan hệ đó.

## 4. Đặt anchor ID tường minh

Asciidoctor có thể tạo ID tự động từ heading, nhưng anchor tường minh giúp kiểm soát liên kết và giữ ID ổn định khi tiêu đề được biên tập.

### 4.1. Anchor trước section

Đặt anchor ngay trước heading:

```asciidoc
[[orders]]
== Orders

[[orders-get]]
=== Lấy thông tin đơn hàng

[[orders-create]]
=== Tạo đơn hàng
```

Từ bất kỳ vị trí nào trong cùng tài liệu, có thể tham chiếu:

```asciidoc
<<orders-get,Lấy thông tin đơn hàng>>
```

Anchor cần duy nhất trong phạm vi tài liệu được render. Không sao chép ID orders-get vào hai operation section khác nhau trong cùng trang.

### 4.2. Anchor cho một phần nhỏ bên trong operation

Có thể đặt anchor cho request, response hoặc error scenario:

```asciidoc
[[orders-get-request]]
==== Request

include::{snippets}/orders-get/http-request.adoc[]

[[orders-get-response]]
==== Response

include::{snippets}/orders-get/http-response.adoc[]

[[orders-get-not-found]]
==== Không tìm thấy đơn hàng

include::{snippets}/orders-get-not-found/http-response.adoc[]
```

Anchor chi tiết hữu ích khi một trang operation dài, trang khác cần liên kết trực tiếp đến response/lỗi, hoặc mục lục use case cần đưa người đọc đến đúng ví dụ.

Không cần đặt anchor cho mọi heading nhỏ. Chỉ đặt ID tường minh khi vị trí có khả năng được tham chiếu hoặc cần URL ổn định.

## 5. Quy ước đặt tên anchor

Nên đặt ID bằng chữ thường, dùng dấu gạch nối và diễn đạt resource/action:

| Anchor ID | Vị trí |
| --- | --- |
| authentication | Phần xác thực |
| orders | Nhóm endpoint Orders |
| orders-list | Operation liệt kê |
| orders-get | Operation đọc một đơn hàng |
| orders-get-request | Request của operation đọc đơn hàng |
| orders-get-response | Response thành công |
| orders-get-not-found | Response 404 |
| orders-create-validation-error | Lỗi validation khi tạo đơn |

Quy tắc:

1. Dùng một pattern nhất quán cho toàn module.
2. Gắn resource vào đầu ID để tránh trùng giữa các nhóm.
3. Dùng suffix mô tả phần nội dung như request, response, not-found, validation-error.
4. Không dùng khoảng trắng, dấu tiếng Việt hoặc ký tự tùy tiện trong ID.
5. Tránh đưa version build hoặc số thứ tự test vào anchor nếu chúng không phải contract điều hướng.

Anchor ID trở thành một phần URL khi xuất bản HTML. Khi đổi ID đã được chia sẻ cho consumer, bookmark hoặc trang khác có thể hỏng. Hãy coi ID công khai như một giao diện cần được quản lý.

## 6. Liên kết trong cùng trang

Dùng cross-reference để liên kết đến anchor trong cùng tài liệu:

```asciidoc
<<orders-get,Lấy thông tin đơn hàng>>
```

Có thể liên kết mà không viết label riêng:

```asciidoc
<<orders-get>>
```

Hoặc dùng cú pháp xref:

```asciidoc
xref:orders-get[]
```

Ưu tiên label có ý nghĩa thay vì chỉ hiển thị ID. Ví dụ:

```asciidoc
Sau khi tạo thành công, client nhận mã đơn hàng mới.
Để đọc lại tài nguyên, xem <<orders-get,Lấy thông tin đơn hàng>>.
```

Không dùng URL đầy đủ cho liên kết nội bộ cùng trang. Anchor reference ngắn hơn và phù hợp khi xuất bản ở nhiều base path.

## 7. Xref giữa các file AsciiDoc

Khi tài liệu được chia thành nhiều file, dùng xref với đường dẫn tương đối:

```asciidoc
xref:orders/get.adoc[Chi tiết operation lấy đơn hàng]
```

Liên kết đến anchor cụ thể trong file khác:

```asciidoc
xref:orders/get.adoc#orders-get-response[Response của operation lấy đơn hàng]
```

Ví dụ layout:

```text
docs/
├── index.adoc
├── authentication.adoc
└── orders/
    ├── index.adoc
    ├── list.adoc
    ├── get.adoc
    └── create.adoc
```

Từ index.adoc:

```asciidoc
== Resources

* xref:orders/index.adoc[Orders]
* xref:authentication.adoc[Authentication]
```

Từ orders/index.adoc:

```asciidoc
== Orders

* xref:list.adoc[Liệt kê đơn hàng]
* xref:get.adoc#orders-get[Lấy thông tin đơn hàng]
* xref:create.adoc[Tạo đơn hàng]
```

Xref giữa các file hoạt động trong ngữ cảnh Asciidoctor và site được build. Đừng trỏ đến file .adoc bằng URL web giả định nếu pipeline xuất bản dùng tên HTML khác; dùng xref để bộ xử lý chuyển đổi liên kết theo cấu hình.

## 8. Nhúng operation và snippet mà vẫn giữ anchor

Một operation có thể có nhiều snippet. Anchor nên đặt ở phần AsciiDoc do tác giả quản lý, còn snippet được include bên dưới.

```asciidoc
[[orders-get]]
=== Lấy thông tin đơn hàng

Trả về đơn hàng theo mã định danh.

[[orders-get-parameters]]
==== Parameters

include::{snippets}/orders-get/path-parameters.adoc[]
include::{snippets}/orders-get/query-parameters.adoc[]

[[orders-get-request]]
==== Request

include::{snippets}/orders-get/request-headers.adoc[]
include::{snippets}/orders-get/http-request.adoc[]

[[orders-get-response]]
==== Response

include::{snippets}/orders-get/response-headers.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
```

Trang tổng quan có thể trỏ thẳng đến operation:

```asciidoc
== Orders

* xref:orders/get.adoc#orders-get[Lấy thông tin đơn hàng]
```

Anchor không sinh snippet và snippet không tự tạo anchor. Asciidoctor tạo liên kết đến vị trí đã được đánh dấu trong tài liệu.

## 9. Liên kết từ operation đến security, error và resource khác

Tài liệu API thường có quan hệ giữa operation:

- Operation yêu cầu cơ chế xác thực được mô tả ở Authentication.
- POST tạo tài nguyên và trả Location trỏ đến tài nguyên mới.
- DELETE có thể trả 204 và không có response body.
- Các operation dùng chung error format.

Ví dụ:

```asciidoc
[[orders-create]]
=== Tạo đơn hàng

Endpoint yêu cầu quyền tạo đơn. Xem <<authentication,Bảo mật và xác thực>>.

Sau khi tạo thành công, API trả header Location trỏ đến tài nguyên mới.
Client có thể dùng <<orders-get,Lấy thông tin đơn hàng>> để đọc tài nguyên.

Khi payload không hợp lệ, xem <<errors-validation,Lỗi validation>>.
```

Với Location là URI runtime của resource, không nhầm header đó với anchor Asciidoctor. Header Location thuộc HTTP response; xref/anchor là điều hướng trong tài liệu. Chúng không phải cùng một địa chỉ.

## 10. Liên kết ngoài

Dùng link macro cho tài nguyên ngoài bộ tài liệu:

```asciidoc
link:https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/[Spring REST Docs Reference]
```

Ví dụ:

```asciidoc
Với mô hình Bearer token, xem thêm
link:https://www.rfc-editor.org/rfc/rfc6750[RFC 6750 - Bearer Token Usage].
```

Liên kết ngoài cần trỏ đến nguồn chính thức/tin cậy, có label mô tả đích đến, tránh URL chứa tracking/session parameter và được kiểm tra định kỳ.

Không sử dụng xref cho URL web ngoài. Dùng xref cho tài liệu trong bộ Asciidoctor; dùng link cho URL ngoài.

## 11. ID tự sinh từ heading và khi nào cần tránh phụ thuộc

Asciidoctor có thể sinh ID từ tiêu đề section. Các attribute như idprefix và idseparator ảnh hưởng cách tạo ID tự động:

```asciidoc
:idprefix:
:idseparator: -

== Orders

=== Lấy thông tin đơn hàng
```

ID tự sinh có thể thay đổi khi tiêu đề được dịch hoặc chỉnh sửa, attribute idprefix/idseparator thay đổi, hoặc heading trùng xuất hiện và processor phải xử lý ID trùng.

Nếu một section được liên kết từ nhiều trang hoặc đã được chia sẻ cho consumer, hãy đặt anchor tường minh. Dùng ID tự sinh cho heading nội bộ ít có khả năng được tham chiếu và không cần cam kết ổn định.

Attribute sectanchors và sectlinks có thể hỗ trợ hiển thị liên kết tới section heading tùy theme/output. Chúng không thay thế việc chọn ID có chủ đích cho operation quan trọng. Kiểm tra HTML output để biết theme trình bày anchor ra sao.

## 12. Mục lục và trang điều hướng operation

Đối với tài liệu dài, bật TOC và giới hạn độ sâu:

```asciidoc
= REST API Guide
:toc:
:toclevels: 3
:sectanchors:

[[overview]]
== Tổng quan

[[authentication]]
== Authentication

[[orders]]
== Orders

[[orders-list]]
=== Liệt kê đơn hàng

[[orders-get]]
=== Lấy thông tin đơn hàng

[[orders-create]]
=== Tạo đơn hàng
```

TOC giúp điều hướng theo heading. Anchor tường minh giúp trang khác và prose có thể trỏ tới operation. Hai cơ chế bổ trợ nhau.

Nếu trang có nhiều file con, một trang resource index có thể làm danh mục:

```asciidoc
= Orders

Các operation:

* xref:list.adoc[Liệt kê đơn hàng]
* xref:get.adoc#orders-get[Lấy thông tin đơn hàng]
* xref:create.adoc[Tạo đơn hàng]

Các lỗi dùng chung:

* xref:../errors.adoc#errors-validation[Lỗi validation]
```

Kiểm tra đường dẫn tương đối từ file đang chứa xref. Đường dẫn tính từ file AsciiDoc hiện tại, không phải luôn từ root project.

## 13. Quy tắc đặt anchor cho toàn bộ module

Một quy ước có thể áp dụng:

| Loại nội dung | Pattern gợi ý | Ví dụ |
| --- | --- | --- |
| Resource | resource-name | orders |
| Operation | resource-action | orders-get |
| Request section | resource-action-request | orders-get-request |
| Response section | resource-action-response | orders-get-response |
| Error scenario | resource-action-error-name | orders-get-not-found |
| Shared concept | concept-name | authentication, pagination |

Document identifier có thể theo pattern tương tự:

| Test exchange | Document identifier |
| --- | --- |
| GET order thành công | orders-get |
| GET order không tồn tại | orders-get-not-found |
| POST order thành công | orders-create |
| POST order validation lỗi | orders-create-validation-error |

Không dùng cùng ID cho nhiều anchor trong một trang. Nếu hai file được ghép vào một trang qua include, kiểm tra anchor của chúng vẫn duy nhất sau khi ghép.

## 14. Kiểm tra liên kết và anchor trong build

Một liên kết hỏng có thể không làm HTTP test thất bại. Nó thuộc bước biên soạn tài liệu và cần được phát hiện trong build.

Quy trình:

1. Chạy documentation tests để sinh snippet.
2. Chạy Asciidoctor trên toàn bộ entrypoint của tài liệu.
3. Cấu hình include/xref lỗi làm build thất bại.
4. Kiểm tra HTML: anchor ID có tồn tại, duy nhất và đúng vị trí.
5. Kiểm tra link nội bộ và link ngoài theo chính sách dự án.
6. Mở trang render, thử TOC và liên kết quan trọng.

Ví dụ Gradle:

```groovy
def snippetsDir = file("$buildDir/generated-snippets")

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
}
```

Phần trên bảo đảm task Asciidoctor chạy sau test và nhận output snippet. Nó không tự kiểm tra tất cả liên kết ngoài hoặc anchor duy nhất; có thể bổ sung link checker/HTML validation riêng trong pipeline nếu dự án yêu cầu.

### 14.1. Danh sách kiểm tra thủ công

- Anchor ID trong xref có đúng chính tả và đúng file?
- Có anchor trùng sau khi include các file con không?
- Section có đổi heading nhưng anchor cũ vẫn giữ không?
- Xref tương đối đã tính từ đúng file nguồn chưa?
- Link ngoài có label dễ hiểu và URL chính xác không?
- TOC có hiển thị đúng độ sâu?
- Link đến operation có đưa người đọc tới tiêu đề operation thay vì đầu trang không?

## 15. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Xref không nhảy đúng section | Anchor ID sai hoặc section không có anchor đó | Kiểm tra ID trong AsciiDoc/HTML output |
| Đổi tiêu đề làm bookmark cũ hỏng | Dùng ID tự sinh từ heading | Đặt anchor tường minh và giữ ID ổn định |
| Hai operation nhận cùng anchor | Copy/paste ID mà không đổi resource/action | Dùng quy ước resource-action và kiểm tra trùng |
| Link giữa file không tìm thấy | Đường dẫn tương đối tính từ sai vị trí | Tính path từ file chứa xref và chạy lại Asciidoctor |
| Xref trỏ đến file .adoc không đúng URL phát hành | Dùng URL cố định thay vì Asciidoctor cross-reference | Dùng xref để processor xử lý đích output |
| Include snippet đúng nhưng link operation không có | Nhầm document identifier với anchor | Tạo anchor trong AsciiDoc riêng biệt |
| TOC quá dài | toc levels lớn hơn cấu trúc cần thiết | Giảm toc levels và chỉnh hierarchy heading |
| Anchor bị trùng sau khi include partial | Nhiều partial dùng cùng ID | Đặt ID có namespace theo resource/operation |
| Link ngoài không còn hoạt động | Tài liệu nguồn đổi URL hoặc bị chuyển hướng | Dùng nguồn chính thức và kiểm tra định kỳ |

## 16. Checklist tiêu đề, anchor và liên kết

- [ ] Có một document title và hierarchy heading rõ ràng.
- [ ] Operation quan trọng có anchor ID tường minh.
- [ ] Anchor ID dùng chữ thường, dấu gạch nối và duy nhất trong trang.
- [ ] Document identifier của REST Docs không bị nhầm với anchor ID.
- [ ] Liên kết trong cùng trang dùng cross-reference tới anchor đúng.
- [ ] Liên kết giữa file dùng xref và path tương đối đúng.
- [ ] URL ngoài dùng link macro với label mô tả rõ.
- [ ] TOC có độ sâu phù hợp với cấu trúc.
- [ ] Anchor vẫn ổn định khi chỉnh sửa câu chữ heading.
- [ ] Kiểm tra anchor/link sau khi include các file con.
- [ ] Build tài liệu thất bại khi include bắt buộc không tồn tại.

## 17. Bài tập thực hành

Tài liệu Orders API có ba operation:

- GET /api/orders/{id}: đọc một đơn hàng.
- POST /api/orders: tạo đơn hàng.
- DELETE /api/orders/{id}: hủy đơn hàng.

Hãy thực hiện:

1. Tạo document title Orders API, bật TOC với độ sâu phù hợp.
2. Đặt anchor orders-get, orders-create và orders-delete cho từng operation.
3. Trong GET operation, đặt anchor riêng cho request, response và lỗi 404.
4. Viết trang index với xref tới ba operation.
5. Từ POST operation, liên kết đến GET operation để đọc tài nguyên vừa tạo.
6. Liên kết phần authentication dùng chung từ cả ba operation.
7. Dùng một external link tới tài liệu chính thức liên quan đến authorization.
8. Render Asciidoctor, kiểm tra HTML anchor và click thử liên kết trong trang index.

**Câu hỏi tự kiểm tra:** Nếu test dùng document("orders-get"), Asciidoctor có tự tạo liên kết #orders-get không? Không. Document identifier chỉ xác định nơi snippet được ghi. Anchor trong trang phải được tạo riêng, chẳng hạn [[orders-get]], rồi mới có thể tham chiếu bằng xref hoặc cross-reference.

## Kết luận

Tiêu đề, anchor và liên kết quyết định cách người đọc điều hướng tài liệu REST API. Dùng heading để thể hiện cấu trúc, anchor tường minh cho operation và phần quan trọng, cross-reference cho vị trí trong cùng trang, xref cho tài liệu AsciiDoc khác và link cho URL ngoài. Phân biệt anchor ID với document identifier của Spring REST Docs: một cái điều hướng trang, một cái nhóm snippet của HTTP exchange. Giữ quy ước ID ổn định, kiểm tra uniqueness sau khi include và xác minh liên kết trên HTML render. Khi build phát hiện include/xref hỏng và nhóm review các đường dẫn quan trọng, người tích hợp có thể đi từ tổng quan đến đúng operation, request, response hoặc lỗi mà không bị lạc trong tài liệu.
