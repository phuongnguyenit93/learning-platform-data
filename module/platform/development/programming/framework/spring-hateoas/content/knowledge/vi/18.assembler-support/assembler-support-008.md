# Tùy biến instantiateModel

**RepresentationModelAssemblerSupport<T, D>** là lớp cơ sở của Spring HATEOAS giúp triển khai assembler cho một loại tài nguyên. Lớp này hỗ trợ tạo representation model, thêm self link dựa trên mapping của controller và chuyển một tập hợp entity thành collection model. Mặc định, nó tạo instance của lớp model bằng reflection và yêu cầu model có constructor không tham số.

Khi model cần constructor có tham số, được tạo từ factory riêng hoặc cần cách khởi tạo khác, có thể override phương thức **instantiateModel(T entity)**. Đây là extension point dành riêng cho bước tạo object. **createModelWithId(...)** gọi phương thức này, sau đó bổ sung self link vào model. Vì vậy, assembler có thể kiểm soát cách khởi tạo model mà vẫn giữ cơ chế tạo link tự động.

Trong SPRING_HATEOAS, assembler chuyển domain object thành representation có dữ liệu và hypermedia links. Bài học này tập trung vào vòng đời tạo model, lý do override instantiateModel, cách dùng constructor tham số, cách phối hợp với createModelWithId và toModel, cũng như các lưu ý về hiệu năng, bất biến dữ liệu và kiểm thử.

Sau bài học, bạn có thể:

- Giải thích vai trò của RepresentationModelAssemblerSupport.
- Mô tả cách instantiateModel(T entity) được gọi trong quá trình tạo representation.
- Hiểu giới hạn của cơ chế khởi tạo mặc định bằng constructor không tham số.
- Override instantiateModel để dùng constructor tham số hoặc factory.
- Giữ self link tự động bằng createModelWithId(...).
- Phân biệt trách nhiệm của instantiateModel, toModel và toCollectionModel.
- Kiểm thử model được khởi tạo đúng và có các link cần thiết.

## RepresentationModelAssemblerSupport giải quyết vấn đề gì?

Một ứng dụng Spring HATEOAS thường phải chuyển domain object thành một representation model. Quá trình đó thường gồm hai việc:

1. Tạo instance của lớp model dành cho API.
2. Điền dữ liệu và thêm link hypermedia, đặc biệt là self link trỏ đến tài nguyên hiện tại.

Nếu mỗi assembler tự viết lại phần tạo self link, mã nguồn dễ lặp lại và có thể không nhất quán. RepresentationModelAssemblerSupport gom phần khởi tạo model và tạo self link vào một lớp cơ sở.

Ví dụ, domain object Order được chuyển thành OrderModel:

~~~java
public class OrderModel extends RepresentationModel<OrderModel> {

    private Long id;
    private String orderNumber;
    private String status;

    public OrderModel() {}

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Assembler có thể kế thừa RepresentationModelAssemblerSupport:

~~~java
import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    OrderModelAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.id(), order);
        model.setId(order.id());
        model.setOrderNumber(order.orderNumber());
        model.setStatus(order.status());
        return model;
    }
}
~~~

Constructor của lớp cơ sở nhận:

- controllerClass: controller dùng để suy ra URI của tài nguyên.
- resourceType: lớp representation model mà assembler sẽ tạo.

createModelWithId(order.id(), order) tạo OrderModel và thêm self link theo mapping của OrderController. Assembler chỉ cần điền các thuộc tính còn lại.

## instantiateModel làm nhiệm vụ gì?

instantiateModel(T entity) là phương thức protected trong RepresentationModelAssemblerSupport. Nó chịu trách nhiệm tạo instance của kiểu D, trong đó D là một kiểu con của RepresentationModel.

Chữ ký khái quát:

~~~java
protected D instantiateModel(T entity)
~~~

Tham số entity là domain object đang được chuyển đổi. Mặc định, phương thức dùng reflection để tạo instance từ resourceType đã truyền vào constructor của lớp cơ sở. Cách mặc định giả định lớp model có constructor không tham số.

Trong luồng thông thường, assembler gọi createModelWithId(...); phương thức này tạo model thông qua instantiateModel(entity) rồi gắn self link. Có thể hình dung luồng xử lý:

~~~text
toModel(entity)
    |
    v
createModelWithId(id, entity)
    |
    v
instantiateModel(entity)
    |
    v
tạo instance của D
    |
    v
gắn self link từ controller mapping + id
    |
    v
assembler điền các thuộc tính còn lại
    |
    v
trả RepresentationModel
~~~

Điểm quan trọng là instantiateModel chỉ chịu trách nhiệm khởi tạo object. Nó không phải nơi truy vấn repository, kiểm tra quyền, xử lý nghiệp vụ hoặc tự tạo self link.

### Hành vi mặc định

Nếu model có constructor không tham số, có thể không cần override:

~~~java
public class OrderModel extends RepresentationModel<OrderModel> {

    private Long id;
    private String status;

    public OrderModel() {
    }

    // Getters and setters
}
~~~

Lớp cơ sở có thể tạo instance bằng reflection. Sau đó assembler điền dữ liệu trong toModel.

Ưu điểm của cách mặc định là ít mã và dễ dùng với các model JavaBean. Nhược điểm là model phải đáp ứng yêu cầu constructor không tham số, đồng thời quá trình tạo instance dựa trên reflection.

### Khi nào cần override?

Override instantiateModel khi:

- Model chỉ cung cấp constructor có tham số để bảo đảm object được khởi tạo ở trạng thái hợp lệ.
- Model dùng các trường final và không có setter.
- Cần tạo model thông qua factory hoặc builder riêng.
- Muốn khởi tạo trước một số giá trị từ entity.
- Đã đo được chi phí reflection đáng kể trong đường xử lý có tần suất cao và muốn dùng cách tạo instance trực tiếp.

Không cần override chỉ để thêm dữ liệu vào model. Nếu model có constructor không tham số và dữ liệu có thể được gán trong toModel, hãy giữ cách triển khai đơn giản.

## Override instantiateModel với constructor tham số

Giả sử OrderModel là representation bất biến, chỉ có constructor nhận các giá trị bắt buộc:

~~~java
import org.springframework.hateoas.RepresentationModel;

public class OrderModel extends RepresentationModel<OrderModel> {

    private final Long id;
    private final String orderNumber;
    private String status;

    public OrderModel(Long id, String orderNumber) {
        this.id = id;
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Model này không có constructor không tham số. Vì vậy, cần override instantiateModel:

~~~java
import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    OrderModelAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    protected OrderModel instantiateModel(Order order) {
        return new OrderModel(order.id(), order.orderNumber());
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.id(), order);
        model.setStatus(order.status());
        return model;
    }
}
~~~

Khi toModel gọi createModelWithId, lớp cơ sở gọi instantiateModel(order). Phương thức override tạo model bằng constructor tham số, sau đó lớp cơ sở gắn self link. toModel tiếp tục điền status và trả model.

Luồng này giữ được cả hai lợi ích:

- Model được khởi tạo theo invariant mà constructor quy định.
- Self link vẫn được tạo tự động theo controller mapping.

Không nên tự tạo new OrderModel(...) trong toModel rồi bỏ qua createModelWithId nếu muốn tận dụng self link tự động của lớp cơ sở.

## Phân biệt instantiateModel và createModelWithId

Hai phương thức có liên quan nhưng trách nhiệm khác nhau:

| Phương thức | Trách nhiệm | Khi nào tùy biến |
| --- | --- | --- |
| instantiateModel(entity) | Tạo instance của kiểu representation model | Khi cần constructor tham số, factory hoặc cách khởi tạo riêng |
| createModelWithId(id, entity) | Tạo model và thêm self link theo ID | Dùng trong toModel để giữ cơ chế tạo self link |
| createModelWithId(id, entity, parameters...) | Tạo model và xây self link có thêm tham số URI | Khi mapping cần thêm path parameters |
| toModel(entity) | Điều phối chuyển entity thành representation hoàn chỉnh | Override để điền dữ liệu và thêm link |
| toCollectionModel(entities) | Chuyển một iterable entity thành collection model | Thường dùng mặc định; có thể override nếu collection cần xử lý riêng |

instantiateModel không nhận ID riêng vì nó chỉ cần entity nguồn để khởi tạo object. ID được truyền cho createModelWithId để xây self link.

### Vì sao không tự thêm self link trong instantiateModel?

instantiateModel có thể được gọi từ createModelWithId, nơi lớp cơ sở đã biết controller, resource type và ID. Nếu tự thêm self link trong instantiateModel, có nguy cơ:

- Lặp lại logic tạo URI đã có trong lớp cơ sở.
- Tạo link sai khi assembler hỗ trợ nhiều dạng ID hoặc path parameters.
- Khó giữ nhất quán nếu controller mapping thay đổi.

Hãy để instantiateModel tạo object. Dùng createModelWithId để gắn self link. Các link nghiệp vụ khác có thể được thêm trong toModel.

## Dùng factory để tạo model

Không nhất thiết phải gọi constructor trực tiếp. Nếu model cần khởi tạo qua một factory, assembler có thể nhận factory bằng constructor injection rồi gọi factory trong instantiateModel.

Ví dụ factory:

~~~java
@Component
class OrderModelFactory {

    OrderModel create(Order order) {
        return new OrderModel(order.id(), order.orderNumber());
    }
}
~~~

Assembler:

~~~java
@Component
class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    private final OrderModelFactory modelFactory;

    OrderModelAssembler(OrderModelFactory modelFactory) {
        super(OrderController.class, OrderModel.class);
        this.modelFactory = modelFactory;
    }

    @Override
    protected OrderModel instantiateModel(Order order) {
        return modelFactory.create(order);
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.id(), order);
        model.setStatus(order.status());
        return model;
    }
}
~~~

Factory hữu ích khi khởi tạo model có nhiều quy tắc hoặc cần tái sử dụng. Tuy nhiên, không nên đưa repository hoặc logic nghiệp vụ vào factory chỉ để tạo DTO. Việc lấy dữ liệu và quyết định nghiệp vụ nên nằm ở service; factory tập trung vào việc tạo representation model.

Nếu factory là Spring bean, hãy inject vào assembler. Không gọi new để tự tạo các dependency cần quản lý bởi Spring. Bản thân model thường chỉ là object dữ liệu, không nên chứa service hoặc repository.

## Kết hợp instantiateModel với assembler hoàn chỉnh

Ví dụ dưới đây thể hiện rõ vai trò của lớp cơ sở, phương thức override và việc thêm link bổ sung:

~~~java
import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    OrderModelAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    protected OrderModel instantiateModel(Order order) {
        return new OrderModel(order.id(), order.orderNumber());
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.id(), order);
        model.setStatus(order.status());

        model.add(linkTo(methodOn(OrderController.class).all())
            .withRel("orders"));

        if (order.isEditable()) {
            model.add(linkTo(methodOn(OrderController.class)
                .patch(order.id(), null))
                .withRel("edit"));
        }

        return model;
    }
}
~~~

Trong ví dụ:

1. instantiateModel tạo model với ID và mã đơn hàng qua constructor.
2. createModelWithId gọi phương thức override và tự thêm self link.
3. toModel điền trạng thái và thêm link đến collection.
4. Link edit chỉ xuất hiện khi domain object cho biết đơn hàng có thể chỉnh sửa.

Ví dụ giả định Order có id(), orderNumber(), status() và isEditable(), OrderController có các method all() và patch(id, request). Link edit chỉ công bố khả năng tương tác; server vẫn phải kiểm tra quyền và trạng thái khi nhận request.

## Tạo collection model

RepresentationModelAssemblerSupport cũng hỗ trợ chuyển một tập hợp entity thành CollectionModel<D> thông qua toCollectionModel(...). Phương thức này gọi toModel cho từng entity, vì vậy logic khởi tạo trong instantiateModel được áp dụng cho mỗi item.

Ví dụ controller:

~~~java
@GetMapping
CollectionModel<OrderModel> all() {
    return assembler.toCollectionModel(orderService.findAll());
}
~~~

Nếu service trả về List<Order>, mỗi phần tử được chuyển thành OrderModel thông qua toModel. Vì toModel gọi createModelWithId, mỗi item có self link.

Nếu collection cần link ở cấp ngoài như self, có thể bổ sung sau khi tạo:

~~~java
CollectionModel<OrderModel> collection =
    assembler.toCollectionModel(orderService.findAll())
        .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
~~~

instantiateModel chỉ tạo từng item; nó không tạo collection wrapper và không quyết định link cấp collection.

## Lưu ý về hiệu năng và thiết kế model

Mặc định reflection giúp giảm mã khởi tạo, nhưng có thể tạo chi phí nhỏ khi mỗi entity đều cần tạo representation model. Override bằng constructor trực tiếp có thể giảm chi phí reflection, song chỉ nên làm khi có lý do rõ ràng hoặc đã đo hiệu năng.

Một số nguyên tắc:

- Model nên nhẹ, không chứa logic nghiệp vụ nặng.
- Không truy vấn database trong instantiateModel; nếu cần dữ liệu, hãy tải ở service trước khi assembler chạy.
- Không inject service hoặc repository vào representation model.
- Ưu tiên constructor thể hiện các thuộc tính bắt buộc, nhưng không cần biến mọi model thành immutable nếu điều đó làm code phức tạp không cần thiết.
- Nếu cần tạo model bằng factory, giữ factory tập trung vào việc dựng representation.
- Không override instantiateModel chỉ để thêm link; dùng createModelWithId và toModel.

Với collection lớn, instantiateModel được gọi nhiều lần qua quá trình assemble. Hãy tránh xử lý tốn kém ở đây và cân nhắc phân trang để giới hạn số model phải tạo trong một response.

## Kiểm thử instantiateModel

Kiểm thử nên xác minh hai khía cạnh: model được tạo theo cách tùy biến và self link vẫn được gắn đúng. Có thể kiểm thử assembler trực tiếp để xác minh dữ liệu, sau đó dùng MVC test để xác minh serialization.

Ví dụ unit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class OrderModelAssemblerTest {

    private final OrderModelAssembler assembler = new OrderModelAssembler();

    @Test
    void instantiateModelUsesConstructorValues() {
        Order order = new Order(42L, "ORD-0042", "DRAFT");

        OrderModel model = assembler.instantiateModel(order);

        assertThat(model.getId()).isEqualTo(42L);
        assertThat(model.getOrderNumber()).isEqualTo("ORD-0042");
    }
}
~~~

Ví dụ giả định Order có constructor tương ứng, test nằm cùng package với assembler để truy cập phương thức protected và OrderModelAssembler không cần dependency bổ sung. Nếu assembler nhận factory qua constructor, hãy cung cấp factory giả hoặc cấu hình test phù hợp. Test này tập trung vào bước khởi tạo; status được gán sau đó trong toModel.

### Kiểm thử self link qua MVC

~~~java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerHypermediaTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void responseContainsSelfLink() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/orders/42")));
    }
}
~~~

Test giả định order ID 42 tồn tại, controller dùng mapping /orders/{id} và trả representation HAL. MVC test xác minh self link sau khi request context đã được thiết lập. Khi ứng dụng dùng context path hoặc proxy prefix, nên kiểm tra URI theo cấu hình thực tế.

Các trường hợp nên kiểm thử:

1. Model dùng constructor tham số được tạo đúng từ entity.
2. Các thuộc tính được điền trong toModel có giá trị chính xác.
3. createModelWithId vẫn tạo self link với ID đúng.
4. Link nghiệp vụ được thêm theo trạng thái phù hợp.
5. toCollectionModel áp dụng cùng quy tắc khởi tạo cho từng phần tử.
6. Entity đầu vào không hợp lệ được xử lý theo hợp đồng assembler.
7. Model không cần constructor không tham số khi instantiateModel đã được override.

## Những sai lầm thường gặp

**Nghĩ instantiateModel là nơi chuyển đổi toàn bộ entity.** Phương thức này chỉ khởi tạo instance. Hãy điền dữ liệu và thêm link trong toModel.

**Quên override khi model không có constructor không tham số.** Cơ chế mặc định dùng reflection và giả định constructor không tham số. Hãy override instantiateModel nếu model cần constructor khác.

**Tự tạo model trong toModel rồi bỏ qua createModelWithId.** Cách này có thể khiến self link tự động không được thêm. Dùng createModelWithId nếu muốn tận dụng mapping controller.

**Tự thêm self link trong instantiateModel.** Việc này trộn trách nhiệm khởi tạo object với tạo link. Để createModelWithId xử lý self link.

**Đặt truy vấn hoặc nghiệp vụ trong instantiateModel.** Assembler không nên trở thành tầng truy cập dữ liệu. Chuẩn bị dữ liệu ở service trước khi chuyển đổi.

**Dùng reflection hoặc factory phức tạp mà không có lý do.** Nếu model có constructor không tham số, mặc định thường đủ dùng. Chỉ tùy biến khi cấu trúc model hoặc yêu cầu đo được đòi hỏi.

**Đưa dependency nghiệp vụ vào model.** Representation model nên là dữ liệu được serialize, không phải Spring service. Giữ dependency ở assembler hoặc factory.

## Kết luận

instantiateModel(T entity) là extension point của RepresentationModelAssemblerSupport, dùng để tạo instance representation model. Mặc định, Spring HATEOAS tạo object bằng reflection và yêu cầu constructor không tham số. Khi model cần constructor tham số, factory hoặc cách khởi tạo khác, override phương thức này để kiểm soát việc tạo object.

Trong toModel, hãy gọi createModelWithId(id, entity) để lớp cơ sở dùng instantiateModel và thêm self link theo controller mapping. Sau đó điền các thuộc tính và link nghiệp vụ. Cách tách trách nhiệm này giữ model dễ kiểm soát, tránh lặp logic tạo URI và giúp cùng một quy tắc khởi tạo được tái sử dụng khi assemble collection.

Tài liệu tham khảo: [Spring HATEOAS Reference — Representation model assembler support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-relation-assembler).
