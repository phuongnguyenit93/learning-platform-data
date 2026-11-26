# name của link

## Mục tiêu

Trong Spring HATEOAS, một Link không chỉ chứa URI đích và quan hệ (relation). Link còn có thể mang các thuộc tính mô tả như name, title, type, hreflang, deprecation và profile. Thuộc tính name là một nhãn tùy chọn gắn với chính link; nó hữu ích khi cần phân biệt hoặc nhận diện một link trong nhóm link cùng quan hệ.

Sau bài học, bạn có thể:

- Phân biệt link relation (rel) với thuộc tính name của link.
- Tạo named link bằng API của Spring HATEOAS.
- Kết hợp name với title, type và các metadata khác.
- Dùng tên để phân biệt nhiều link cùng relation trong representation HAL.
- Kiểm thử tên link trong JSON và giữ hợp đồng hypermedia ổn định.

## Relation và name có vai trò khác nhau

Một link có thể được hiểu qua hai câu hỏi:

- rel: link này có quan hệ gì với tài nguyên hiện tại?
- name: link cụ thể này được đặt tên hoặc nhận diện như thế nào trong nhóm quan hệ đó?

Ví dụ, một tài nguyên hóa đơn có thể công bố các link để tải bản PDF và XML. Cả hai đều có quan hệ download, vì chúng cùng là các cách tải nội dung hóa đơn. Thuộc tính name phân biệt biến thể cụ thể:

~~~json
{
  "_links": {
    "download": [
      {
        "href": "/api/invoices/42/pdf",
        "name": "pdf",
        "title": "Tải hóa đơn PDF",
        "type": "application/pdf"
      },
      {
        "href": "/api/invoices/42/xml",
        "name": "xml",
        "title": "Tải hóa đơn XML",
        "type": "application/xml"
      }
    ]
  }
}
~~~

Trong ví dụ:

- download là relation, mô tả ý nghĩa chung của các link.
- pdf và xml là name, giúp nhận diện từng link trong nhóm download.
- title là nhãn mô tả dành cho người dùng hoặc công cụ hiển thị.
- type cho biết media type của nội dung mà link dẫn tới.

name không thay thế rel. Nếu đặt relation thành pdf và xml, client sẽ phải biết các loại file để hiểu quan hệ. Dùng relation chung download cùng name cụ thể giúp tách ngữ nghĩa hành động khỏi định dạng nội dung.

Không phải link nào cũng cần name. Với link self duy nhất, relation thường đã đủ để client tìm tài nguyên hiện tại. Hãy thêm name khi nó mang lại khả năng phân biệt hoặc ý nghĩa thực tế cho client.

## Tạo named link trong Spring HATEOAS

Spring HATEOAS biểu diễn link bằng org.springframework.hateoas.Link. Có thể tạo link từ mapping của controller rồi gắn name bằng withName:

~~~java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link pdfLink = linkTo(methodOn(InvoiceController.class)
        .downloadPdf(invoiceId))
        .withRel("download")
        .withName("pdf");
~~~

linkTo(methodOn(...)) tạo URI dựa trên mapping của handler method. withRel("download") gán relation; withName("pdf") gán tên cho link. Các phương thức with... tạo Link mới với metadata tương ứng, nên có thể nối chuỗi để mô tả link:

~~~java
Link pdfLink = linkTo(methodOn(InvoiceController.class)
        .downloadPdf(invoiceId))
        .withRel("download")
        .withName("pdf")
        .withTitle("Tải hóa đơn PDF")
        .withType("application/pdf");
~~~

Để thêm link vào representation:

~~~java
EntityModel<InvoiceResponse> model = EntityModel.of(response)
        .add(linkTo(methodOn(InvoiceController.class)
                .findById(invoiceId)).withSelfRel())
        .add(pdfLink);
~~~

Nếu cần thêm nhiều biến thể, tạo một Link cho mỗi endpoint rồi gắn cùng relation và name khác nhau:

~~~java
Link pdf = linkTo(methodOn(InvoiceController.class)
        .downloadPdf(invoiceId))
        .withRel("download")
        .withName("pdf")
        .withType("application/pdf");

Link xml = linkTo(methodOn(InvoiceController.class)
        .downloadXml(invoiceId))
        .withRel("download")
        .withName("xml")
        .withType("application/xml");

model.add(pdf, xml);
~~~

Khi serialize sang HAL, nhiều link cùng relation có thể được biểu diễn thành một mảng link object. Mỗi object giữ href và metadata của chính link đó. Client có thể lọc các link có relation download, sau đó dùng name hoặc type để chọn biến thể phù hợp.

## Dùng LinkRelation và quan hệ chuẩn IANA

Spring HATEOAS cung cấp LinkRelation để biểu diễn relation như một kiểu riêng thay vì truyền chuỗi tùy ý. Với các relation chuẩn đã được IANA đăng ký, nên ưu tiên hằng số trong IanaLinkRelations:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/api/invoices/42", IanaLinkRelations.SELF);
Link item = Link.of("/api/invoices/42", IanaLinkRelations.ITEM);
Link collection = Link.of("/api/invoices", IanaLinkRelations.COLLECTION);
~~~

Các quan hệ phổ biến gồm:

| Relation | Ý nghĩa |
|---|---|
| self | Tài nguyên được biểu diễn bởi response hiện tại. |
| item | Một phần tử thuộc collection. |
| collection | Collection liên quan đến tài nguyên hoặc item. |
| next, prev | Điều hướng tới trang kế tiếp hoặc trước đó. |
| first, last | Điều hướng tới trang đầu hoặc cuối. |
| edit | Liên kết tới thao tác chỉnh sửa theo hợp đồng API. |
| related | Tài nguyên có liên quan. |

Với relation nghiệp vụ riêng như download, approve hoặc cancel, hãy thống nhất tên và ghi tài liệu ngữ nghĩa cho client. Trong API công khai cần khả năng liên thông rộng, có thể dùng URI relation mở rộng theo quy ước Web Linking hoặc CURIE khi định dạng hypermedia hỗ trợ. Tên relation phải mô tả quan hệ; thuộc tính name chỉ bổ sung cách nhận diện link cụ thể.

Ví dụ dùng LinkRelation cho relation tùy chỉnh:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link cancel = Link.of(
        "/api/orders/42/cancellation",
        LinkRelation.of("cancel"))
        .withName("customer-request");
~~~

## Phân biệt name, title và type

Spring HATEOAS hỗ trợ một số metadata tùy chọn cho link. Chọn đúng thuộc tính giúp client và công cụ hiển thị hiểu được link:

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| rel | Quan hệ của link với tài nguyên hiện tại. | download |
| name | Tên nhận diện link trong quan hệ đó. | pdf |
| title | Tiêu đề mô tả link, thường dùng để hiển thị. | Tải hóa đơn PDF |
| type | Gợi ý media type của đích link. | application/pdf |
| hreflang | Ngôn ngữ của tài nguyên đích. | vi |
| deprecation | URI mô tả thông tin về việc link hoặc quan hệ bị deprecated. | https://api.example.com/docs/deprecations/old-download |
| profile | URI mô tả profile của tài nguyên đích. | https://api.example.com/profiles/invoice-pdf |

Ví dụ:

~~~java
Link vietnameseGuide = Link.of(
        "https://api.example.com/docs/invoices",
        LinkRelation.of("help"))
        .withName("invoice-guide")
        .withTitle("Hướng dẫn hóa đơn")
        .withType("text/html")
        .withHreflang("vi");
~~~

name nên ngắn, ổn định và phù hợp cho máy đọc. title có thể là văn bản thân thiện với người dùng và có thể được bản địa hóa. type là gợi ý định dạng, không bảo đảm server luôn trả đúng nội dung; client vẫn cần xử lý response thực tế và status HTTP.

Các thuộc tính metadata là tùy chọn. Không nên điền name, title hoặc type chỉ để làm response dài hơn. Chỉ công bố thông tin có ý nghĩa cho client, công cụ hoặc giao diện sử dụng API.

## Name trong HAL và hợp đồng API

HAL JSON biểu diễn link dưới _links. Khi một relation chỉ có một link, giá trị thường là một link object. Khi có nhiều link cùng relation, giá trị có thể là mảng các link object. name là thuộc tính nằm trong từng link object, không phải một relation mới và cũng không phải trường dữ liệu của tài nguyên.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/invoices/42"
    },
    "download": [
      {
        "href": "/api/invoices/42/pdf",
        "name": "pdf",
        "type": "application/pdf"
      },
      {
        "href": "/api/invoices/42/xml",
        "name": "xml",
        "type": "application/xml"
      }
    ]
  }
}
~~~

Client có thể tìm relation download, sau đó chọn link có name là pdf hoặc xml. Nếu client dựa vào name, tên đó trở thành một phần hợp đồng API và cần được giữ ổn định. Đổi pdf thành portable-document có thể làm client cũ không tìm được biến thể mong đợi dù relation và URI vẫn còn.

Khi một media type khác được thương lượng, cách biểu diễn metadata link có thể khác. Không nên giả định mọi serializer hypermedia đều giữ nguyên toàn bộ thuộc tính như HAL. Hãy kiểm thử với media type thực tế mà client sử dụng.

## Kiểm thử named link

MockMvc có thể xác minh relation, name và type trong response HAL. Ví dụ:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/invoices/{id}", invoiceId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.download[0].name").value("pdf"))
        .andExpect(jsonPath("$._links.download[0].type")
                .value("application/pdf"))
        .andExpect(jsonPath("$._links.download[1].name").value("xml"))
        .andExpect(jsonPath("$._links.download[1].type")
                .value("application/xml"));
~~~

Đoạn test trên minh họa trường hợp assembler có quy ước thứ tự ổn định. Thứ tự phần tử trong mảng link không nên là cơ chế lựa chọn duy nhất của client. Nếu API không cam kết thứ tự, test cũng không nên buộc PDF luôn ở vị trí 0 và XML ở vị trí 1; hãy tìm phần tử theo thuộc tính name bằng JSONPath phù hợp hoặc đọc JSON rồi kiểm tra tập giá trị.

Ngoài serialization, nên kiểm thử rằng mỗi named link trỏ tới endpoint đúng và endpoint trả media type phù hợp. name và type là metadata mô tả link; chúng không thay thế kiểm thử hành vi của endpoint đích.

## Những lỗi thường gặp

- **Nhầm name với rel:** rel mô tả quan hệ ngữ nghĩa; name nhận diện link cụ thể. Không đổi relation thành tên định dạng chỉ để phân biệt các biến thể.
- **Dùng name thay cho title:** name phù hợp cho định danh ổn định; title là nội dung mô tả để hiển thị.
- **Dùng tên không ổn định:** client có thể phụ thuộc vào name. Đặt tên có chủ đích và quản lý thay đổi như một phần của hợp đồng.
- **Gắn cùng name cho các link không liên quan:** client sẽ khó phân biệt. Name nên duy nhất trong phạm vi nhóm link cùng relation khi cần phân biệt.
- **Giả định mọi serializer đều xuất name:** thuộc tính có thể được biểu diễn khác nhau theo media type. Kiểm thử đúng định dạng API thương lượng.
- **Dựa vào thứ tự link trong mảng:** thứ tự không nên là khóa nhận diện. Dùng name, type hoặc metadata phù hợp.
- **Công bố type như một bảo đảm tuyệt đối:** type chỉ là metadata gợi ý; endpoint vẫn cần trả nội dung và header chính xác.

## Quy trình đặt tên link

1. Xác định quan hệ ngữ nghĩa của link và chọn relation chuẩn IANA hoặc relation tùy chỉnh phù hợp.
2. Xác định có nhiều link cùng relation hay client cần nhận diện một biến thể cụ thể không.
3. Nếu cần, đặt name ngắn, ổn định và duy nhất trong nhóm relation đó.
4. Dùng title cho mô tả thân thiện, type cho media type và hreflang cho ngôn ngữ khi có ích.
5. Tạo Link bằng API Spring HATEOAS và gắn vào RepresentationModel hoặc EntityModel.
6. Kiểm thử HAL JSON để xác nhận rel, name và metadata; kiểm thử riêng endpoint đích.

Đặt tên link đúng cách giúp client nhận diện các biến thể liên kết mà vẫn giữ được ngữ nghĩa quan hệ nhất quán. Trong Spring HATEOAS, hãy dùng rel để diễn đạt mối quan hệ với tài nguyên và dùng name như metadata bổ sung cho từng link khi hợp đồng API thực sự cần nó.
