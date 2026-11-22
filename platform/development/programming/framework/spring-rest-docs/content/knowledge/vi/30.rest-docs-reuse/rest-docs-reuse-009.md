# Tránh tái sử dụng descriptor làm sai ngữ nghĩa

## 1. Tái sử dụng descriptor có thể làm sai hợp đồng API như thế nào?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, kiểm tra response và dùng descriptor để mô tả payload fields, parameters, headers, cookies và links. Các descriptor tạo snippet; snippet được biên soạn thành Asciidoctor/Markdown và đưa vào build, CI.

Tái sử dụng descriptor giúp giảm lặp, nhưng descriptor không chỉ là một dòng mô tả để in ra bảng. Nó còn thể hiện hợp đồng của operation: field có bắt buộc không, parameter có được phép vắng mặt không, header nào phải xuất hiện, link nào được công bố và phần payload nào đang được mô tả.

Nếu dùng một descriptor chung cho các endpoint có hợp đồng khác nhau, tài liệu có thể sai dù test vẫn chạy:

- Field bắt buộc ở endpoint A bị đánh dấu optional vì endpoint B cho phép bỏ qua.
- Header chỉ có ở response bị dùng nhầm trong request.
- ignored() che đi field quan trọng mà endpoint khác phải công bố.
- Mô tả chung không còn đúng ngữ cảnh của từng resource.
- Descriptor cho path con được dùng ở root, khiến đường dẫn hoặc ý nghĩa bị sai.

Nguyên tắc là tái sử dụng phần cấu trúc và thuật ngữ thực sự giống nhau, còn trạng thái và ý nghĩa thuộc từng operation phải được khai báo riêng.

## 2. Descriptor mô tả hợp đồng, không chỉ định dạng bảng

Một descriptor thường chứa một số khía cạnh:

| Khía cạnh | Ví dụ | Ảnh hưởng |
| --- | --- | --- |
| Định danh | fieldWithPath("email") | Chọn field trong payload |
| Ý nghĩa | description("Địa chỉ email") | Nội dung người đọc thấy |
| Trạng thái | optional(), ignored() | Quy định field có thể thiếu hoặc được bỏ qua |
| Metadata | attributes(key("format").value("email")) | Thông tin bổ sung cho template |
| Ngữ cảnh trích xuất | beneathPath(...) | Chọn subsection của payload hoặc links |

Khi hai endpoint cùng có field id, chưa chắc hai field có cùng ý nghĩa. id trong response người dùng có thể là mã người dùng; id trong request tạo đơn hàng có thể là idempotency key. Không nên dùng chung mô tả chỉ vì tên path giống nhau.

Trước khi chia sẻ descriptor, hãy so sánh:

1. Path hoặc tên header/parameter có giống nhau không?
2. Ý nghĩa với client có giống nhau không?
3. Field/parameter có cùng required/optional behavior không?
4. Có cùng kiểu, format, constraint và lifecycle không?
5. Descriptor có được trích xuất từ cùng cấp payload hay cùng loại HTTP message không?

Chỉ khi những điều này phù hợp mới nên dùng một factory chung.

## 3. Phân biệt cấu trúc dùng chung và hợp đồng riêng

| Nhóm | Có thể chia sẻ? | Ví dụ |
| --- | --- | --- |
| Quy ước cấu trúc | Thường có | Cách mô tả correlation header, timestamp format |
| Ngữ nghĩa endpoint | Cần xem xét từng operation | Field required, status transition, filter bắt buộc |

Ví dụ hai endpoint đều dùng X-Correlation-ID với cùng ý nghĩa:

~~~java
static HeaderDescriptor correlationIdHeader() {
    return headerWithName("X-Correlation-ID")
            .description("Mã tương quan để theo dõi request");
}
~~~

Factory này có thể dùng chung nếu cả hai endpoint thực sự nhận cùng header và có cùng yêu cầu. Ngược lại, không nên tạo một bộ request fields chung cho tất cả endpoint chỉ vì nhiều payload có field name.

## 4. Không chia sẻ trạng thái optional/ignored một cách vô điều kiện

optional() và ignored() thay đổi cách descriptor tham gia vào kiểm tra và snippet:

- optional() cho biết field/parameter/header có thể vắng mặt trong operation hợp lệ.
- ignored() loại descriptor khỏi phần tài liệu và kiểm tra tương ứng.
- Relaxed mode cho phép dữ liệu chưa mô tả xuất hiện theo phạm vi snippet được cấu hình.

Các trạng thái này không phải tùy chọn trình bày. Chúng phản ánh hợp đồng. Ví dụ:

~~~java
// API tạo hồ sơ yêu cầu email
fieldWithPath("email")
        .description("Địa chỉ email")

// API cập nhật hồ sơ cho phép bỏ qua email
fieldWithPath("email")
        .optional()
        .description("Địa chỉ email mới nếu cần thay đổi")
~~~

Hai field cùng path nhưng hợp đồng khác nhau. Không dùng một descriptor đã cấu hình optional cho cả hai operation.

Tương tự, ignored() không phải cách xử lý nhanh cho mọi field chưa muốn viết mô tả. Nếu field là một phần hợp đồng mà client cần biết, phải mô tả nó. Chỉ ignore khi chủ ý loại field khỏi tài liệu và đã hiểu tác động đến kiểm tra.

## 5. Dùng factory tạo descriptor mới theo ngữ cảnh

Một cách an toàn là tạo descriptor mới mỗi lần gọi factory. Chia sẻ hàm tạo và nội dung mô tả chuẩn, không chia sẻ một descriptor đã được điều chỉnh trạng thái cho nhiều operation:

~~~java
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.snippet.Attributes.key;

final class CommonFieldDescriptors {

    private CommonFieldDescriptors() {
    }

    static FieldDescriptor requiredEmail() {
        return fieldWithPath("email")
                .description("Địa chỉ email")
                .attributes(key("format").value("email"));
    }

    static FieldDescriptor optionalEmail() {
        return fieldWithPath("email")
                .optional()
                .description("Địa chỉ email mới nếu cần thay đổi")
                .attributes(key("format").value("email"));
    }
}
~~~

Sử dụng đúng ngữ cảnh:

~~~java
requestFields(CommonFieldDescriptors.requiredEmail());
requestFields(CommonFieldDescriptors.optionalEmail());
~~~

Factory riêng làm trạng thái hiện rõ ở nơi gọi. Khi cần mô tả khác nhau theo nghiệp vụ, đặt tên factory theo ý nghĩa như requiredBillingEmail() hoặc optionalContactEmail() thay vì tạo helper tổng quát có nhiều boolean khó đọc.

## 6. Tránh giữ descriptor dùng chung trong mảng mutable

Không nên khai báo một mảng descriptor toàn cục rồi chỉnh sửa phần tử theo từng test. Điều đó làm ý nghĩa phụ thuộc thứ tự gọi và có thể gây lỗi khi test chạy song song.

Không an toàn:

~~~java
static final FieldDescriptor EMAIL =
        fieldWithPath("email").description("Địa chỉ email");

// Nhiều test cùng thay đổi hoặc cấu hình lại descriptor này.
~~~

Nên tạo mới qua factory:

~~~java
static FieldDescriptor emailField(boolean optional) {
    FieldDescriptor descriptor = fieldWithPath("email")
            .description("Địa chỉ email");
    return optional ? descriptor.optional() : descriptor;
}
~~~

Tuy nhiên, không nên lạm dụng boolean nếu tên tham số không diễn đạt đầy đủ hợp đồng. Hai factory requiredEmail() và optionalEmail() thường dễ đọc và review hơn.

Mảng truyền vào requestFields(...), responseFields(...) hoặc requestHeaders(...) cũng nên được tạo riêng theo operation. Tránh sửa mảng sau khi đã truyền vào snippet.

## 7. Không trộn request và response descriptors

Một số tên header xuất hiện ở cả request lẫn response nhưng ý nghĩa khác nhau. Ví dụ Content-Type:

~~~java
static HeaderDescriptor requestContentType() {
    return headerWithName("Content-Type")
            .description("Media type của request body");
}

static HeaderDescriptor responseContentType() {
    return headerWithName("Content-Type")
            .description("Media type của response body");
}
~~~

Hai helper cùng dùng một tên header nhưng có mô tả theo hướng truyền. Tương tự, không dùng chung cookie request và response chỉ vì tên cookie giống nhau. Dùng requestCookies(...) cho cookie client gửi và responseCookies(...) cho cookie server trả.

~~~java
document("login",
        requestHeaders(requestContentType()),
        responseHeaders(responseContentType()));
~~~

Tách helper theo request/response giúp tránh mô tả sai chiều truyền và giúp reviewer hiểu endpoint đang công bố điều gì.

## 8. Không tái sử dụng descriptor khi path context khác nhau

Payload subsection extractor có thể làm thay đổi ngữ cảnh mà descriptor được hiểu. Ví dụ cùng field id có thể xuất hiện ở root và trong embedded resource:

~~~json
{
  "id": "collection-1",
  "_embedded": {
    "orders": [
      {"id": "order-42", "status": "PAID"}
    ]
  }
}
~~~

Field root và field trong orders[] không nhất thiết có cùng ý nghĩa. Mô tả riêng:

~~~java
responseFields(
        fieldWithPath("id").description("Mã collection"),
        subsectionWithPath("_embedded.orders")
                .description("Các đơn hàng được nhúng"));

responseFields(
        beneathPath("_embedded.orders[]"),
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("status").description("Trạng thái đơn hàng"));
~~~

Hai snippet có ngữ cảnh khác nhau. Không lấy descriptor id ở root rồi dùng nguyên nó trong subsection nếu mô tả nghiệp vụ khác nhau.

## 9. Tái sử dụng một phần descriptor thay vì cả bộ

Khi hai operation chỉ có một vài field chung, hãy ghép phần chung với field riêng:

~~~java
static FieldDescriptor[] auditFields() {
    return new FieldDescriptor[] {
            fieldWithPath("createdAt")
                    .description("Thời điểm tạo")
                    .attributes(key("format").value("ISO-8601")),
            fieldWithPath("updatedAt")
                    .description("Thời điểm cập nhật")
                    .attributes(key("format").value("ISO-8601"))
    };
}

static FieldDescriptor[] orderFields() {
    return Stream.concat(
            Arrays.stream(auditFields()),
            Stream.of(
                    fieldWithPath("orderNumber").description("Mã đơn hàng"),
                    fieldWithPath("status").description("Trạng thái đơn hàng")))
            .toArray(FieldDescriptor[]::new);
}
~~~

Ví dụ chia sẻ nhóm audit fields và giữ order fields riêng. Khi ghép descriptor, kiểm tra không có path trùng nhau và không có mô tả mâu thuẫn. Nếu các endpoint dùng chung field nhưng có format hoặc quyền hiển thị khác, tạo factory nhận ngữ cảnh cụ thể thay vì sửa descriptor đã chia sẻ.

## 10. Khi nào nên dùng relaxed mode?

Relaxed mode hữu ích khi một operation cố ý chỉ tài liệu hóa một phần payload hoặc parameter. Nhưng relaxed không thay thế việc xác định hợp đồng:

- Nếu field chưa mô tả là field nội bộ, cân nhắc ignored() có chủ ý hoặc preprocessing phù hợp.
- Nếu field là public API, nên mô tả thay vì dựa vào relaxed để test luôn qua.
- Nếu chỉ một endpoint có extra field, dùng descriptor/relaxed policy riêng cho endpoint đó.
- Không cấu hình relaxed toàn cục chỉ để tránh cập nhật descriptor khi API thay đổi.

Ví dụ endpoint trả object mở rộng nhưng trang tài liệu chỉ muốn mô tả field cơ bản:

~~~java
relaxedResponseFields(
        fieldWithPath("id").description("Mã tài nguyên"),
        fieldWithPath("name").description("Tên tài nguyên"))
~~~

Người viết phải ghi rõ phạm vi tài liệu đang cố ý bỏ qua field khác. Nếu mục tiêu là tài liệu đầy đủ và phát hiện thay đổi hợp đồng, dùng strict descriptors để test phát hiện field mới.

## 11. Ví dụ hai operation có hợp đồng khác nhau

Giả sử API tạo hồ sơ yêu cầu email, còn API cập nhật cho phép gửi một phần dữ liệu:

~~~java
@Test
void createProfileDocumentsRequiredEmail() throws Exception {
    mockMvc.perform(post("/api/profiles")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"email":"an@example.test","displayName":"An"}
                            """))
            .andExpect(status().isCreated())
            .andDo(document("profiles-create",
                    requestFields(
                            CommonFieldDescriptors.requiredEmail(),
                            fieldWithPath("displayName")
                                    .description("Tên hiển thị"))));
}

@Test
void updateProfileDocumentsOptionalEmail() throws Exception {
    mockMvc.perform(patch("/api/profiles/{id}", "profile-7")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"displayName":"An Nguyen"}
                            """))
            .andExpect(status().isOk())
            .andDo(document("profiles-update",
                    requestFields(
                            CommonFieldDescriptors.optionalEmail(),
                            fieldWithPath("displayName")
                                    .optional()
                                    .description("Tên hiển thị mới nếu cần thay đổi"))));
}
~~~

Ví dụ cần điều chỉnh theo controller và DTO thực tế. Cùng khái niệm email nhưng required/optional khác nhau theo operation. Descriptor riêng giữ đúng ngữ nghĩa và giúp test phát hiện khi hợp đồng thay đổi.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field bắt buộc bị ghi thành optional | Dùng lại descriptor optional từ endpoint khác | Tạo factory required/optional riêng |
| Field bị mất khỏi snippet | Dùng ignored() ở descriptor dùng chung | Chỉ ignore trong operation thật sự cần |
| Mô tả không đúng ngữ cảnh | Chia sẻ descriptor chỉ dựa vào tên path | So sánh ý nghĩa nghiệp vụ và loại payload |
| Request header mang mô tả response | Dùng chung helper không phân biệt chiều truyền | Tạo request/response descriptor factories |
| Field lồng nhau mô tả sai | Dùng descriptor ở sai subsection context | Tạo descriptor theo path/subsection cụ thể |
| Test chạy không ổn định | Chia sẻ mutable descriptor/mảng giữa test | Tạo descriptor mới từ factory cho mỗi operation |
| Field mới không làm test thất bại | Dùng relaxed mode quá rộng | Trở về strict cho phần hợp đồng public |
| Mô tả lặp hoặc path trùng | Ghép descriptor chung và riêng không kiểm tra | Rà soát path sau khi composition |

## 13. Bài thực hành

1. Tạo hai endpoint có cùng field email nhưng một endpoint required, một endpoint optional.
2. Viết hai factory tạo descriptor riêng và dùng đúng factory trong từng test.
3. Tạo helper cho request Content-Type và response Content-Type với mô tả khác nhau.
4. Tái sử dụng nhóm audit fields cho order và customer, giữ field riêng của từng resource.
5. Tạo response có root id và embedded orders[].id; mô tả hai ngữ nghĩa khác nhau.
6. Thử ignored() và relaxed response fields, ghi rõ trường hợp nào có thể dùng trong hợp đồng public.
7. Chạy documentation tests để xác nhận descriptor strict phát hiện field/parameter không được mô tả.

**Tiêu chí hoàn thành:** xác định được khi nào descriptor thật sự dùng chung; không chia sẻ trạng thái optional/ignored sai ngữ nghĩa; phân biệt request/response và path context; dùng factory tạo descriptor mới; giữ strictness phù hợp với hợp đồng API.

## 14. Checklist trước khi commit

- [ ] Descriptor dùng chung có cùng ý nghĩa nghiệp vụ ở mọi operation.
- [ ] Required/optional/ignored phản ánh đúng hợp đồng từng endpoint.
- [ ] Factory tạo descriptor mới cho từng operation hoặc ngữ cảnh.
- [ ] Request và response descriptors được phân tách khi ý nghĩa khác nhau.
- [ ] Field cùng tên ở root và subsection được mô tả theo đúng ngữ cảnh.
- [ ] Descriptor chung và riêng không tạo path trùng hoặc mô tả mâu thuẫn.
- [ ] Relaxed mode chỉ dùng khi chủ ý tài liệu hóa một phần hợp đồng.
- [ ] Strict descriptors vẫn bảo vệ các phần public API quan trọng.
- [ ] Documentation tests đã chạy lại và snippet phản ánh đúng hợp đồng.

**Ghi nhớ:** Chỉ tái sử dụng descriptor khi path, ý nghĩa và trạng thái hợp đồng thực sự giống nhau. Chia sẻ factory và quy ước mô tả, nhưng tạo descriptor riêng cho operation có required/optional, request/response hoặc subsection context khác nhau để tài liệu Spring REST Docs không làm sai ngữ nghĩa API.
