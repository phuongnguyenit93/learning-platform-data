# CollectionModel rỗng

Trong API REST, một truy vấn hợp lệ có thể không tìm thấy phần tử nào. Ví dụ, client lọc đơn hàng theo trạng thái đã hủy nhưng hiện tại không có đơn hàng phù hợp. Endpoint vẫn có thể trả về một tài nguyên tập hợp hợp lệ, với nội dung rỗng và các liên kết điều hướng cần thiết. Spring HATEOAS cung cấp CollectionModel để biểu diễn tập hợp đó.

CollectionModel rỗng không đồng nghĩa với endpoint không tồn tại hoặc request thất bại. Nó biểu diễn một tập hợp hiện có nhưng hiện không chứa phần tử. Khi dùng CollectionModel.empty(), cần hiểu thêm một vấn đề của Java: do type erasure, runtime không thể suy ra kiểu phần tử từ một collection không có phần tử. Spring HATEOAS cho phép khai báo fallback type để hạ tầng có thể nhận biết kiểu payload ngay cả khi collection rỗng.

Bài học này tập trung vào cách tạo CollectionModel rỗng, thêm link ở cấp tập hợp, khai báo kiểu phần tử dự phòng, xử lý kết quả truy vấn rỗng trong controller, ảnh hưởng đến RepresentationModelProcessor và cách kiểm thử response HAL.

## 1. CollectionModel biểu diễn một tập hợp tài nguyên

CollectionModel<T> là lớp wrapper của Spring HATEOAS dành cho một tập hợp phần tử. Nó kế thừa RepresentationModel nên ngoài nội dung collection còn có thể chứa các Link ở cấp tập hợp.

Ví dụ tập hợp đơn hàng:

~~~java
List<OrderRepresentation> orders = List.of(
    new OrderRepresentation(orderId, "PROCESSING", total)
);

CollectionModel<OrderRepresentation> model =
    CollectionModel.of(orders);
~~~

Tập hợp có thể được tạo cùng link:

~~~java
CollectionModel<OrderRepresentation> model =
    CollectionModel.of(orders, selfLink, searchLink);
~~~

Khi truy vấn không có kết quả, ứng dụng vẫn có thể trả một CollectionModel với nội dung rỗng:

~~~java
CollectionModel<OrderRepresentation> model =
    CollectionModel.empty();
~~~

Các thành phần quan trọng:

- Nội dung được truy cập bằng getContent(). CollectionModel bảo đảm nội dung không null; khi không có phần tử, đây là một collection rỗng.
- Các link được quản lý qua API kế thừa từ RepresentationModel, chẳng hạn add(), getLinks() và hasLink(...).
- Kiểu phần tử được thể hiện qua tham số generic T ở compile time. Với collection rỗng, cần khai báo fallback type nếu runtime cần biết kiểu đó.

CollectionModel.empty() tạo một wrapper không có phần tử. Nó không tự thêm link self, link tìm kiếm hoặc link phân trang. Những liên kết đó phải được tạo và thêm theo hợp đồng API.

## 2. Khi nào nên trả CollectionModel rỗng?

Một collection rỗng phù hợp khi endpoint biểu diễn một tập hợp tài nguyên hợp lệ nhưng truy vấn hiện tại không có phần tử.

Ví dụ:

- Danh sách đơn hàng của khách hàng chưa có đơn nào.
- Kết quả tìm kiếm không có tài nguyên phù hợp.
- Một bộ lọc hợp lệ trả về tập hợp rỗng.
- Một trang truy vấn hợp lệ không chứa phần tử do tập dữ liệu đã thay đổi hoặc trang nằm ngoài phạm vi hiện có.

Hãy phân biệt các trường hợp:

| Tình huống | Ý nghĩa | Phản hồi thường dùng |
|---|---|---|
| Truy vấn hợp lệ, không có phần tử | Tập hợp tồn tại nhưng rỗng | 200 với CollectionModel rỗng |
| Không tìm thấy một tài nguyên đơn | Tài nguyên được yêu cầu không tồn tại | 404 Not Found |
| Request sai cú pháp hoặc tham số không hợp lệ | Client gửi yêu cầu không hợp lệ | 400 Bad Request |
| Người gọi không được phép truy cập | Quyền truy cập bị từ chối | 403 Forbidden hoặc chính sách bảo mật phù hợp |
| Endpoint không có nội dung để trả theo thiết kế | Server chủ động không trả representation | Có thể dùng 204 No Content |

Với API hypermedia, 200 cùng CollectionModel rỗng thường hữu ích hơn 204 khi client vẫn cần nhận link self, link tạo mới, link tìm kiếm hoặc thông tin điều hướng. 204 không có response body nên không thể mang CollectionModel và các link trong body.

Không nên trả 404 chỉ vì một truy vấn danh sách không có kết quả. 404 thường phù hợp với một URI tài nguyên đơn không được tìm thấy. Ý nghĩa HTTP cuối cùng vẫn phải nhất quán với hợp đồng API của ứng dụng.

## 3. Tạo CollectionModel rỗng bằng empty()

Cách cơ bản:

~~~java
CollectionModel<OrderRepresentation> model =
    CollectionModel.empty();
~~~

Java có thể suy luận kiểu T từ kiểu đích của phép gán. Tuy nhiên, thông tin generic này chủ yếu phục vụ compiler. Do type erasure, khi chạy chương trình, collection không có phần tử để runtime suy ra kiểu thực tế.

Nếu chỉ cần trả về một collection rỗng đơn giản và không có thành phần hạ tầng nào cần nhận biết kiểu phần tử, empty() có thể đủ. Nhưng nếu ứng dụng dùng RepresentationModelProcessor hoặc các cơ chế dò kiểu representation, nên khai báo fallback type rõ ràng.

### 3.1. Tạo collection rỗng kèm link

CollectionModel.empty() có overload nhận các link. Ví dụ:

~~~java
CollectionModel<OrderRepresentation> model =
    CollectionModel.empty(selfLink, searchLink);
~~~

Cũng có thể truyền Iterable<Link>:

~~~java
CollectionModel<OrderRepresentation> model =
    CollectionModel.empty(links);
~~~

Trong đó links là tập hợp Link đã được tạo trước. Nếu cần thêm link sau khi tạo:

~~~java
CollectionModel<OrderRepresentation> model =
    CollectionModel.<OrderRepresentation>empty();

model.add(selfLink);
model.add(searchLink);
~~~

Link self nên trỏ đến URI của chính tập hợp, bao gồm query parameter nếu query đó là một phần của trạng thái truy vấn cần duy trì. Link search có thể dẫn đến endpoint tìm kiếm hoặc một biểu diễn affordance phù hợp với hợp đồng API.

### 3.2. Khai báo fallback type ngay khi tạo

Spring HATEOAS cung cấp overload empty(Class<T> elementType, Class<?>... generics) để tạo collection rỗng cùng kiểu phần tử dự phòng:

~~~java
CollectionModel<OrderRepresentation> model =
    CollectionModel.empty(OrderRepresentation.class);
~~~

Ở đây, OrderRepresentation là kiểu của mỗi phần tử trong collection. Fallback type giúp các thành phần xử lý representation nhận diện được loại payload khi không có phần tử thực tế.

Nếu phần tử là một kiểu generic lồng nhau, có thể dùng ParameterizedTypeReference hoặc ResolvableType để giữ đầy đủ thông tin kiểu. Ví dụ collection chứa EntityModel<OrderRepresentation>:

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

CollectionModel<EntityModel<OrderRepresentation>> model =
    CollectionModel.empty(
        new ParameterizedTypeReference<EntityModel<OrderRepresentation>>() {}
    );
~~~

Cách khai báo này bảo toàn cả kiểu wrapper EntityModel lẫn kiểu nội dung OrderRepresentation trong fallback type.

## 4. Type erasure và lý do cần fallback type

Java thực hiện type erasure: phần lớn tham số generic bị loại khỏi kiểu runtime sau khi biên dịch. Ví dụ:

~~~java
CollectionModel<OrderRepresentation> orders =
    CollectionModel.empty();

CollectionModel<CustomerRepresentation> customers =
    CollectionModel.empty();
~~~

Hai biến có kiểu generic khác nhau trong mã nguồn, nhưng cả hai đều là instance của cùng lớp CollectionModel tại runtime. Vì collection rỗng, runtime không thể đọc phần tử đầu tiên để xác định đó là OrderRepresentation hay CustomerRepresentation.

Với collection không rỗng, hạ tầng có thể xem phần tử thực tế để suy ra kiểu. Với collection rỗng, không có phần tử để phân tích. Fallback type cung cấp thông tin thay thế cho trường hợp đó.

Có thể hình dung:

~~~text
CollectionModel.of(nonEmptyItems)
        |
        +-- Có phần tử
        |     |
        |     +-- Runtime có thể xem kiểu phần tử
        |
CollectionModel.empty()
        |
        +-- Không có phần tử
              |
              +-- Không suy ra được payload type từ content
              |
              +-- Fallback type cung cấp kiểu dự phòng
~~~

Fallback type không tạo ra phần tử giả và cũng không thay đổi nội dung collection. Nó chỉ khai báo kiểu phần tử mà collection được thiết kế để chứa.

### 4.1. Dùng withFallbackType() khi collection có thể rỗng

Không phải lúc nào ứng dụng cũng biết trước collection có rỗng hay không. Có thể tạo model từ kết quả repository rồi khai báo kiểu dự phòng:

~~~java
Iterable<OrderRepresentation> result =
    orderQuery.findByStatus(status);

CollectionModel<OrderRepresentation> model =
    CollectionModel.of(result)
        .withFallbackType(OrderRepresentation.class);
~~~

Nếu result có phần tử, Spring HATEOAS có thể xem kiểu phần tử thực tế. Nếu result rỗng, fallback type vẫn cung cấp kiểu OrderRepresentation.

Có các overload với Class, ParameterizedTypeReference và ResolvableType. Chọn overload phù hợp với độ phức tạp của kiểu phần tử:

| API | Khi sử dụng |
|---|---|
| empty() | Tạo collection rỗng cơ bản |
| empty(Class<T>) | Tạo collection rỗng với kiểu phần tử đơn giản |
| empty(Link...) | Tạo collection rỗng cùng các link |
| empty(ParameterizedTypeReference<T>) | Khai báo kiểu phần tử generic đầy đủ |
| empty(ResolvableType) | Khai báo kiểu phần tử bằng mô hình kiểu của Spring |
| withFallbackType(Class, ...) | Bổ sung kiểu dự phòng cho collection đã tạo |
| withFallbackType(ParameterizedTypeReference) | Bổ sung kiểu dự phòng generic |
| withFallbackType(ResolvableType) | Bổ sung kiểu dự phòng bằng ResolvableType |

Ví dụ dùng ResolvableType cho phần tử EntityModel<OrderRepresentation>:

~~~java
import org.springframework.core.ResolvableType;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

ResolvableType elementType = ResolvableType.forClassWithGenerics(
    EntityModel.class,
    OrderRepresentation.class
);

CollectionModel<EntityModel<OrderRepresentation>> model =
    CollectionModel.<EntityModel<OrderRepresentation>>empty(elementType);
~~~

Đối với kiểu lồng nhau phức tạp, hãy khai báo đúng kiểu phần tử của CollectionModel. Nếu collection chứa EntityModel<OrderRepresentation>, fallback type phải mô tả EntityModel<OrderRepresentation>, không chỉ mô tả OrderRepresentation.

## 5. Ảnh hưởng của collection rỗng đến RepresentationModelProcessor

RepresentationModelProcessor là cơ chế cho phép bổ sung hoặc điều chỉnh representation model sau khi model được tạo. Processor có thể được khai báo cho một kiểu model cụ thể, chẳng hạn collection đơn hàng:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
public class OrderCollectionProcessor implements
        RepresentationModelProcessor<
            CollectionModel<EntityModel<OrderRepresentation>>> {

    @Override
    public CollectionModel<EntityModel<OrderRepresentation>> process(
            CollectionModel<EntityModel<OrderRepresentation>> model) {

        // Có thể bổ sung link cấp collection tại đây.
        return model;
    }
}
~~~

Hạ tầng Spring HATEOAS cần xác định processor nào phù hợp với model đang xử lý. Với CollectionModel không rỗng, nó có thể phân tích các phần tử để suy ra kiểu payload. Với collection rỗng, không có phần tử để dò kiểu.

Vì vậy, theo cơ chế mặc định, RepresentationModelProcessor có thể không được gọi cho CollectionModel rỗng nếu hạ tầng không xác định được kiểu payload. Đây là lý do thực tế quan trọng để khai báo fallback type.

Ví dụ tạo collection rỗng có kiểu rõ ràng:

~~~java
CollectionModel<EntityModel<OrderRepresentation>> model =
    CollectionModel.empty(
        new ParameterizedTypeReference<EntityModel<OrderRepresentation>>() {}
    );

return model.add(selfLink);
~~~

Khi có fallback type, hạ tầng có thêm thông tin để đối chiếu kiểu model với processor đã đăng ký. Nếu ứng dụng dựa vào processor để gắn link hoặc áp dụng chính sách chung cho mọi collection đơn hàng, hãy kiểm thử riêng trường hợp collection rỗng.

Không nên xem fallback type là một mẹo chỉ phục vụ serializer. Nó còn có ý nghĩa với cơ chế chọn RepresentationModelProcessor theo generic type.

## 6. Tạo CollectionModel rỗng trong controller

Ví dụ endpoint tìm kiếm đơn hàng theo trạng thái. Repository/service trả về danh sách có thể rỗng:

~~~java
@GetMapping
public CollectionModel<EntityModel<OrderRepresentation>> all(
        @RequestParam(required = false) String status) {

    List<Order> orders = service.findByStatus(status);

    if (orders.isEmpty()) {
        return CollectionModel
            .<EntityModel<OrderRepresentation>>empty(
                new ParameterizedTypeReference<EntityModel<OrderRepresentation>>() {}
            )
            .add(linkTo(methodOn(OrderController.class).all(status))
                .withSelfRel());
    }

    return assembler.toCollectionModel(orders)
        .add(linkTo(methodOn(OrderController.class).all(status))
            .withSelfRel());
}
~~~

Đoạn code minh họa việc xử lý hai trường hợp: có phần tử thì dùng assembler chuyển từng Order thành EntityModel; không có phần tử thì tạo CollectionModel rỗng với fallback type. Cả hai nhánh đều trả link self cho cùng endpoint và cùng tham số truy vấn.

Trong mã nguồn đầy đủ, cần import ParameterizedTypeReference, CollectionModel, EntityModel và các lớp WebMvcLinkBuilder tương ứng. Kiểu OrderRepresentation là DTO của API, còn Order và service là thành phần nghiệp vụ.

Có thể tách logic tạo link self để tránh lặp:

~~~java
private Link selfLink(String status) {
    return linkTo(methodOn(OrderController.class).all(status))
        .withSelfRel();
}
~~~

Sau đó dùng selfLink(status) cho cả collection rỗng và không rỗng. Cách này giúp relation và cách tạo URI nhất quán.

### 6.1. Một phương thức dùng fallback cho cả hai trường hợp

Nếu muốn tránh nhánh if/else, có thể tạo CollectionModel từ kết quả rồi đặt fallback type:

~~~java
List<EntityModel<OrderRepresentation>> items =
    service.findByStatus(status).stream()
        .map(assembler::toModel)
        .toList();

return CollectionModel.of(items)
    .withFallbackType(
        new ParameterizedTypeReference<EntityModel<OrderRepresentation>>() {}
    )
    .add(selfLink(status));
~~~

Cách này đơn giản khi service đã trả về một danh sách hữu hạn. Với dữ liệu lớn hoặc truy vấn phân trang, không nên tải tất cả phần tử vào bộ nhớ chỉ để tạo CollectionModel. Hãy dùng truy vấn giới hạn và mô hình phân trang phù hợp.

## 7. Link ở cấp collection khi không có phần tử

CollectionModel rỗng vẫn có thể mang nhiều link có ý nghĩa. Ví dụ:

~~~java
CollectionModel<OrderRepresentation> emptyOrders =
    CollectionModel.empty(OrderRepresentation.class)
        .add(selfLink)
        .add(searchLink)
        .add(createLink);
~~~

Các link có thể gồm:

- self: URI của collection hiện tại, có thể bao gồm bộ lọc đang áp dụng.
- search: đường dẫn hoặc affordance để thực hiện truy vấn khác.
- create: đường dẫn tạo tài nguyên mới nếu người dùng hiện tại được phép.
- profile: mô tả profile hoặc ngữ nghĩa của tài nguyên theo hợp đồng API nếu ứng dụng sử dụng relation này.

Không phải collection rỗng nào cũng cần tất cả các link trên. Chỉ công bố các link có ý nghĩa trong ngữ cảnh và phù hợp với quyền truy cập. Ví dụ, nếu người dùng không được tạo đơn hàng, không nên thêm link create chỉ vì collection đang rỗng.

Một response HAL minh họa:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders?status=CANCELLED"
    },
    "search": {
      "href": "/orders{?status}",
      "templated": true
    },
    "create": {
      "href": "/orders"
    }
  }
}
~~~

Đây là biểu diễn minh họa cho collection rỗng có link điều hướng. Phần _embedded có thể không xuất hiện khi không có phần tử; hình dạng chính xác cần được xác nhận theo cấu hình serializer và relation provider của ứng dụng. Hợp đồng quan trọng là client vẫn nhận được tài nguyên tập hợp và các link đã công bố.

## 8. CollectionModel rỗng và phân trang

Một collection rỗng có thể xảy ra trong API phân trang. Ví dụ client yêu cầu trang thứ 5 nhưng tập dữ liệu hiện chỉ có 2 trang, hoặc dữ liệu bị xóa sau khi client đọc trang trước.

Cần phân biệt CollectionModel rỗng với PagedModel rỗng:

| Kiểu | Mục đích |
|---|---|
| CollectionModel<T> | Biểu diễn tập hợp và các link của tập hợp |
| PagedModel<T> | Biểu diễn tập hợp có metadata phân trang |
| PagedModel.PageMetadata | Chứa thông tin kích thước, trang hiện tại, tổng phần tử và tổng số trang |

Nếu API công bố metadata phân trang, hãy dùng PagedModel thay vì cố nhét thông tin trang vào các trường tùy ý của CollectionModel.

Một trang không có phần tử vẫn có thể có metadata và link self. Link next, prev, first hoặc last chỉ nên xuất hiện khi trạng thái phân trang thực tế cho phép. Không tạo link next chỉ vì collection rỗng; điều đó có thể dẫn client đến một chuỗi điều hướng vô nghĩa.

Với repository Spring Data, các assembler hoặc phương thức hỗ trợ phân trang của Spring HATEOAS có thể chuyển Page thành PagedModel. Khi kết quả rỗng, cần giữ được kiểu phần tử và metadata phân trang phù hợp để serializer và processor hiểu đúng representation.

## 9. Kiểm thử CollectionModel rỗng

Kiểm thử cần xác nhận collection không có phần tử, nhưng vẫn có link cấp tập hợp và đúng media type. Với Spring MVC, có thể dùng MockMvc:

~~~java
mockMvc.perform(get("/orders")
        .param("status", "CANCELLED")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Nếu cấu hình relation và serializer tạo _embedded.orders với mảng rỗng, có thể kiểm tra thêm đường dẫn đó. Tuy nhiên, không nên mặc định mọi cấu hình HAL luôn tạo cùng một cấu trúc _embedded cho collection không có phần tử. Hãy kiểm tra JSON thực tế của ứng dụng và xác định cấu trúc mà client được cam kết sử dụng.

Có thể kiểm thử nội dung model trực tiếp:

~~~java
CollectionModel<OrderRepresentation> model =
    CollectionModel.empty(OrderRepresentation.class)
        .add(selfLink);

assertThat(model.getContent()).isEmpty();
assertThat(model.hasLink("self")).isTrue();
~~~

Nếu dùng RepresentationModelProcessor, cần có test riêng cho collection rỗng:

~~~java
CollectionModel<EntityModel<OrderRepresentation>> model =
    CollectionModel.empty(
        new ParameterizedTypeReference<EntityModel<OrderRepresentation>>() {}
    );

CollectionModel<EntityModel<OrderRepresentation>> processed =
    processor.process(model);

assertThat(processed.hasLink("self")).isTrue();
~~~

Test processor trực tiếp chỉ xác nhận logic process. Để kiểm tra cơ chế tự chọn processor của Spring HATEOAS, cần kiểm thử qua luồng tích hợp nơi RepresentationModelProcessorInvoker thực sự xử lý model.

Các trường hợp nên có trong bộ test:

1. Kết quả truy vấn có phần tử.
2. Kết quả truy vấn rỗng.
3. Collection rỗng có fallback type.
4. Collection rỗng vẫn có self link.
5. Processor có được áp dụng cho collection rỗng khi đã khai báo fallback type.
6. Link create hoặc search chỉ xuất hiện khi phù hợp quyền và hợp đồng.
7. Response có media type HAL JSON như endpoint công bố.

## 10. Lỗi thường gặp khi tạo CollectionModel rỗng

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả null khi truy vấn không có kết quả | Client không nhận được biểu diễn collection nhất quán | Trả CollectionModel rỗng |
| Trả 404 cho danh sách rỗng | Nhầm lẫn giữa collection không có phần tử và tài nguyên đơn không tồn tại | Dùng 200 với collection rỗng khi truy vấn hợp lệ |
| Gọi empty() nhưng không khai báo fallback type | Runtime không suy ra kiểu phần tử; processor có thể không được gọi | Dùng empty(Class), empty(ParameterizedTypeReference) hoặc withFallbackType |
| Nghĩ fallback type tạo phần tử | Hiểu sai vai trò của metadata kiểu | Nhớ rằng fallback type chỉ cung cấp thông tin kiểu, content vẫn rỗng |
| Quên thêm self link | Client khó nhận biết URI của collection hiện tại | Thêm self link theo request và bộ lọc |
| Luôn thêm link create | Công bố hành động không khả dụng với người dùng hiện tại | Kiểm tra quyền và chính sách nghiệp vụ |
| Dùng CollectionModel khi cần metadata trang | Client không biết vị trí và tổng số trang | Dùng PagedModel cho response phân trang |
| Kiểm thử giả định _embedded luôn có mảng rỗng | Test phụ thuộc chi tiết serializer không được bảo đảm | Kiểm tra response thực tế và hợp đồng media type |

## 11. Quy trình áp dụng

Khi endpoint có thể trả collection rỗng, hãy thực hiện theo các bước:

1. Xác định truy vấn có hợp lệ khi không có phần tử hay không.
2. Trả CollectionModel rỗng thay vì null đối với kết quả danh sách hợp lệ.
3. Thêm self link và các link cấp collection cần thiết.
4. Khai báo fallback type khi cần processor hoặc thành phần runtime nhận diện kiểu payload.
5. Dùng ParameterizedTypeReference hoặc ResolvableType cho kiểu phần tử generic lồng nhau.
6. Dùng PagedModel khi response cần metadata phân trang.
7. Kiểm thử cả collection có dữ liệu và collection rỗng, bao gồm link và processor.

CollectionModel.empty() giúp API biểu diễn rõ một tập hợp hiện chưa có phần tử. Fallback type giải quyết khoảng trống thông tin kiểu do Java type erasure, để các thành phần Spring HATEOAS có thể tiếp tục xử lý representation ngay cả khi collection không có phần tử. Kết hợp collection rỗng với các link có ý nghĩa giúp client tiếp tục khám phá API và thực hiện bước tiếp theo theo hợp đồng hypermedia.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Collection resource representation model](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [CollectionModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [RepresentationModelProcessor API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelProcessor.html)
- [PagedModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)

