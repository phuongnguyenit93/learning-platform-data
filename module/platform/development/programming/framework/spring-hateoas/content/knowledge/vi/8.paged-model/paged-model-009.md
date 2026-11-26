# Trang rỗng

## Mục tiêu

Một API phân trang có thể trả về trang không có phần tử. Trường hợp này xuất hiện khi bộ lọc không tìm thấy bản ghi, collection chưa có dữ liệu hoặc client yêu cầu một số trang nằm ngoài phạm vi hiện tại. Với Spring HATEOAS, PagedModel có thể biểu diễn trang rỗng cùng metadata phân trang và các liên kết điều hướng phù hợp.

Sau bài học, bạn có thể:

- Phân biệt collection rỗng, trang rỗng và request tới tài nguyên không tồn tại.
- Tạo PagedModel rỗng nhưng vẫn giữ PageMetadata.
- Cung cấp fallback type để serializer xác định kiểu phần tử và relation HAL.
- Xử lý trang không có kết quả và trang vượt quá phạm vi dữ liệu.
- Kiểm thử metadata, links và cấu trúc HAL của response rỗng.

## Các tình huống tạo ra trang rỗng

Trang rỗng không nhất thiết có nghĩa là lỗi. Có hai trường hợp thường gặp:

| Trường hợp | Ví dụ | Metadata |
|---|---|---|
| Không có bản ghi phù hợp | Tìm đơn hàng theo trạng thái CANCELLED nhưng chưa có đơn nào bị hủy. | totalElements = 0, totalPages = 0; page number thường là trang client yêu cầu. |
| Trang được yêu cầu vượt quá phạm vi | Có 45 đơn hàng, mỗi trang 20 phần tử, client yêu cầu page=5. | totalElements = 45, totalPages = 3, number = 5; content rỗng. |

Hai trường hợp đều có content rỗng, nhưng ý nghĩa khác nhau. Trường hợp đầu tiên không có phần tử phù hợp trong toàn bộ kết quả. Trường hợp thứ hai có dữ liệu nhưng không có phần tử ở vị trí trang được yêu cầu. Giữ đúng metadata giúp client hiểu sự khác biệt và quyết định quay về trang đầu, điều chỉnh bộ lọc hoặc thông báo không có kết quả.

Một collection resource vẫn tồn tại ngay cả khi chưa có phần tử. Vì vậy, với endpoint trả danh sách, response 200 OK cùng PagedModel rỗng thường phù hợp hơn 404 Not Found. 404 thường dành cho URI của một tài nguyên không tồn tại. API có thể chọn chính sách riêng cho page index vượt giới hạn, nhưng cần nhất quán và ghi rõ trong hợp đồng.

Không nên dùng 204 No Content nếu client cần nhận page metadata hoặc links. Status 204 không có response body, trong khi trang rỗng thường cần body để mô tả page size, số trang, tổng số phần tử và đường dẫn điều hướng.

## PagedModel rỗng vẫn cần metadata

PagedModel<T> là collection representation có thêm metadata phân trang. Metadata được biểu diễn bằng PagedModel.PageMetadata với bốn giá trị:

| Thuộc tính | Ý nghĩa |
|---|---|
| size | Số phần tử tối đa trong một trang theo yêu cầu phân trang. |
| number | Số thứ tự trang hiện tại, bắt đầu từ 0 trong mô hình Pageable của Spring Data. |
| totalElements | Tổng số phần tử của toàn bộ kết quả sau khi áp dụng bộ lọc. |
| totalPages | Tổng số trang dựa trên kích thước trang và tổng số phần tử. |

Với kết quả không có bản ghi, totalElements và totalPages bằng 0. size vẫn giữ kích thước trang được yêu cầu. number vẫn phản ánh trang đang được xử lý, thường là 0 khi client yêu cầu trang đầu tiên.

Ví dụ metadata cho trang đầu không có kết quả:

~~~java
PagedModel.PageMetadata metadata =
        new PagedModel.PageMetadata(20, 0, 0, 0);
~~~

Đối với trang vượt phạm vi, metadata phải phản ánh kết quả truy vấn thực tế. Ví dụ client yêu cầu trang số 5, trong khi kết quả có 45 phần tử và page size là 20:

~~~java
PagedModel.PageMetadata metadata =
        new PagedModel.PageMetadata(20, 5, 45, 3);
~~~

Content của trang này có thể rỗng, nhưng không được thay totalElements và totalPages thành 0. Nếu làm vậy, client sẽ hiểu nhầm rằng toàn bộ collection không có dữ liệu.

## Tạo PagedModel rỗng

Khi tạo PagedModel thủ công, có thể dùng factory method empty cùng PageMetadata. Nếu serializer cần biết kiểu phần tử để xác định relation cho collection rỗng, cung cấp fallback type:

~~~java
import org.springframework.hateoas.PagedModel;

PagedModel.PageMetadata metadata =
        new PagedModel.PageMetadata(pageSize, pageNumber, 0, 0);

PagedModel<OrderModel> response =
        PagedModel.empty(metadata, OrderModel.class);
~~~

Trong ví dụ, OrderModel là kiểu phần tử dự kiến của trang. Nếu OrderModel có annotation @Relation, fallback type giúp relation resolver có đủ thông tin kiểu ngay cả khi content không có phần tử. Điều này hữu ích khi API cần relation nhất quán giữa trang có dữ liệu và trang rỗng.

Fallback type cung cấp thông tin kiểu cho quá trình serialization; nó không tạo ra phần tử giả và không thay đổi totalElements. Cũng không nên mặc định rằng serializer luôn phát ra một mảng _embedded rỗng. Hình dạng cụ thể phụ thuộc serializer và relation được xác định; hãy kiểm thử JSON thực tế mà API công bố.

Nếu cần tự tạo links cấp trang, có thể thêm chúng vào PagedModel:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

PagedModel<OrderModel> response =
        PagedModel.empty(metadata, OrderModel.class);

response.add(linkTo(methodOn(OrderController.class)
        .findAll(pageable)).withSelfRel());
~~~

Trong ví dụ, findAll là handler method nhận Pageable. Khi thêm link, cần giữ các tham số page, size, sort và filter có liên quan để client có thể tái tạo request tương ứng. Với collection phân trang thực tế, ưu tiên dùng PagedResourcesAssembler để tạo model và links theo Page, Pageable cùng mapping của controller thay vì tự dựng toàn bộ links.

## Dùng Spring Data PagedResourcesAssembler

Khi service hoặc repository trả về org.springframework.data.domain.Page<T>, PagedResourcesAssembler có thể chuyển Page thành PagedModel và tạo metadata, links phân trang:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;
    private final PagedResourcesAssembler<Order> pagedAssembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler orderAssembler,
            PagedResourcesAssembler<Order> pagedAssembler) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
        this.pagedAssembler = pagedAssembler;
    }

    @GetMapping("/api/orders")
    PagedModel<OrderModel> findAll(Pageable pageable) {
        Page<Order> page = orderService.findAll(pageable);
        return pagedAssembler.toModel(page, orderAssembler);
    }
}
~~~

Khi Page không có content, assembler vẫn có thể lấy page size, page number, totalElements và totalPages từ Page để xây metadata. Assembler cũng tạo các links điều hướng tương ứng với trang hiện tại. Đây thường là cách phù hợp khi ứng dụng đã dùng Spring Data và muốn giữ links đồng bộ với Pageable.

Nếu ứng dụng không dùng Spring Data, có thể tạo PagedModel thủ công từ kết quả truy vấn và PageMetadata. Khi đó, chính ứng dụng chịu trách nhiệm tính toán đúng totalElements, totalPages, page number và các links điều hướng. Không tính totalPages chỉ từ số phần tử trong trang hiện tại vì trang rỗng không cung cấp đủ thông tin về tổng tập kết quả.

## Links trên trang rỗng

Một trang rỗng vẫn có thể có link self. Các links first, prev, next và last chỉ nên xuất hiện khi chúng có ý nghĩa theo chính sách phân trang và vị trí trang:

- Trang đầu tiên của collection rỗng thường chỉ cần self; không có trang trước hoặc trang tiếp theo.
- Trang rỗng do bộ lọc không có kết quả vẫn có thể có link tới endpoint collection hoặc link xóa/bỏ bộ lọc nếu API cung cấp điều hướng đó.
- Trang vượt phạm vi có thể cung cấp self và link quay về trang hợp lệ gần nhất hoặc trang đầu tiên, nếu API chọn chính sách điều hướng như vậy.
- Trang cuối cùng có dữ liệu thường không có next; trang đầu tiên thường không có prev.

Không tạo next link cho một trang rỗng chỉ vì client yêu cầu page index lớn. Làm vậy có thể tạo chuỗi request vô hạn đến những trang tiếp theo cũng rỗng. Link phải phản ánh tập kết quả và chính sách phân trang hiện tại.

Ví dụ representation HAL minh họa cho kết quả rỗng:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders?page=0&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

Đây là hình dạng minh họa khi collection không có phần tử; phần _embedded có thể không xuất hiện. Với trang vượt phạm vi, page metadata sẽ giữ tổng số phần tử và tổng số trang thực tế, thay vì dùng metadata của collection rỗng hoàn toàn.

## Kiểm thử trang rỗng

Kiểm thử cần xác minh status, media type, metadata và links. Ví dụ với MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
                .param("page", "0")
                .param("size", "20")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$.page.size").value(20))
        .andExpect(jsonPath("$.page.totalElements").value(0))
        .andExpect(jsonPath("$.page.totalPages").value(0))
        .andExpect(jsonPath("$.page.number").value(0));
~~~

Nên có thêm test cho trang vượt phạm vi. Với 45 phần tử và page size 20, request page=5 có content rỗng nhưng metadata phải giữ totalElements=45 và totalPages=3. Nếu ứng dụng chọn trả 404 cho trang vượt phạm vi, hãy kiểm thử chính sách đó và bảo đảm client có thể phân biệt nó với collection không có kết quả.

Nếu dùng @Relation hoặc fallback type để kiểm soát relation HAL, kiểm thử serializer ở cả trang có phần tử và trang rỗng. Đừng chỉ kiểm tra status 200; thay đổi relation hoặc mất page metadata có thể phá client dù endpoint vẫn trả thành công.

## Những lỗi thường gặp

- **Coi trang rỗng là tài nguyên không tồn tại:** collection có thể tồn tại nhưng không có phần tử phù hợp. Dùng response rỗng với metadata phù hợp theo hợp đồng.
- **Đặt totalPages bằng 0 cho mọi trang không có content:** trang vượt phạm vi vẫn có thể thuộc collection có nhiều trang. Giữ metadata thật từ kết quả truy vấn.
- **Bỏ page metadata:** client không biết kích thước trang, tổng phần tử hoặc trang hiện tại để điều hướng.
- **Không cung cấp fallback type:** serializer có thể không xác định được relation mong muốn khi collection không có item.
- **Tạo phần tử giả để giữ relation:** dữ liệu giả làm sai totalElements và khiến client hiển thị bản ghi không tồn tại. Dùng fallback type.
- **Tạo next link vô hạn cho trang rỗng:** links phải dựa trên phạm vi trang thực tế và chính sách điều hướng.
- **Dùng 204 khi client cần metadata:** response 204 không có body nên không thể mang PageMetadata hoặc links.
- **Tính tổng trang từ content hiện tại:** trang rỗng không cho biết tổng số phần tử. Dùng tổng đếm từ truy vấn hoặc metadata Page.

## Quy trình xử lý trang rỗng

1. Xác định collection có tổng số phần tử bằng 0 hay chỉ trang được yêu cầu nằm ngoài phạm vi.
2. Giữ nguyên page size, page number, totalElements và totalPages từ kết quả truy vấn.
3. Tạo PagedModel rỗng với PageMetadata; cung cấp fallback type nếu cần xác định relation HAL.
4. Thêm self và chỉ thêm links phân trang có ý nghĩa theo vị trí trang.
5. Ưu tiên PagedResourcesAssembler khi chuyển Spring Data Page thành PagedModel.
6. Kiểm thử collection không có dữ liệu, trang vượt phạm vi và representation HAL được serialize.

Trang rỗng là một trạng thái bình thường của collection phân trang. Khi PagedModel giữ đúng metadata, fallback type và links điều hướng, client vẫn hiểu được kết quả truy vấn và có thể tiếp tục tương tác với API mà không cần suy đoán từ một response không có phần tử.
