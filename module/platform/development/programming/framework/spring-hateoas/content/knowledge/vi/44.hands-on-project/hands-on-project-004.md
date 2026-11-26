# Thêm self link

## Mục tiêu dự án

Trong bài thực hành này, bạn sẽ xây một REST API nhỏ để đọc đơn hàng và thêm self link bằng Spring HATEOAS. Client nhận được một representation có dữ liệu đơn hàng cùng URI trỏ về chính tài nguyên đó. Với collection, API cũng công bố self link của collection và self link riêng cho từng item.

Bạn sẽ thực hiện một luồng hoàn chỉnh: tạo endpoint, viết representation assembler, tạo links từ controller mapping, gọi API bằng HTTP client và kiểm thử response HAL bằng MockMvc.

Sau khi hoàn thành, bạn có thể:

- Tạo self link cho một item bằng WebMvcLinkBuilder.
- Dùng RepresentationModelAssembler để tách việc tạo representation khỏi controller.
- Tạo self link cho collection.
- Hiểu vì sao không nên hard-code URI trong assembler.
- Kiểm thử self link ở cả item và collection.
- Theo href được server trả về để điều hướng tới tài nguyên.

## Bài toán

Một cửa hàng có API đọc đơn hàng. Client hiện phải tự ghép URI từ ID để biết địa chỉ của từng đơn. Nếu server đổi route hoặc thêm context path, client phải sửa cách tạo URI.

Hãy thay đổi API để mỗi response tự công bố địa chỉ của tài nguyên:

- GET /api/orders/{id} trả về một đơn hàng có relation self.
- GET /api/orders trả về collection có relation self.
- Mỗi đơn hàng được nhúng trong collection cũng có relation self riêng.
- Nếu ID không tồn tại, API trả về 404.

Client sẽ dùng href trong relation self làm nguồn URI để truy cập tài nguyên. Client không cần biết quy tắc ghép đường dẫn từ ID.

## Chuẩn bị dự án

Tạo một ứng dụng Spring Boot dùng Java 17 trở lên và Spring MVC. Thêm các dependency sau; để Spring Boot dependency management chọn phiên bản tương thích:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-hateoas")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Nếu dự án dùng Maven, thêm các starter tương đương vào pom.xml và dùng Spring Boot parent hoặc BOM để quản lý version. Không tự chọn version Spring HATEOAS tách rời khỏi Spring Boot release train.

Tạo package ví dụ:

~~~text
com.example.orders
  OrderApiApplication.java
  Order.java
  OrderStatus.java
  OrderResponse.java
  OrderService.java
  OrderModelAssembler.java
  OrderController.java
  OrderControllerTest.java
~~~

## Bước 1: Tạo domain model và dữ liệu mẫu

Dự án dùng dữ liệu trong bộ nhớ để tập trung vào hypermedia. Tạo enum trạng thái:

~~~java
package com.example.orders;

public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED
}
~~~

Tạo domain record:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record Order(
        Long id,
        String customerName,
        BigDecimal total,
        OrderStatus status) {
}
~~~

Tạo DTO dùng cho response:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record OrderResponse(
        Long id,
        String customerName,
        BigDecimal total,
        OrderStatus status) {
}
~~~

Service cung cấp hai thao tác đọc:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final List<Order> orders = List.of(
            new Order(
                    101L,
                    "Nguyen An",
                    new BigDecimal("125000.00"),
                    OrderStatus.PAID),
            new Order(
                    102L,
                    "Tran Binh",
                    new BigDecimal("89000.00"),
                    OrderStatus.PENDING),
            new Order(
                    103L,
                    "Le Chi",
                    new BigDecimal("245000.00"),
                    OrderStatus.SHIPPED));

    public List<Order> findAll() {
        return orders;
    }

    public Optional<Order> findById(Long id) {
        return orders.stream()
                .filter(order -> order.id().equals(id))
                .findFirst();
    }
}
~~~

Ở ứng dụng thật, service có thể gọi repository hoặc query service. Điểm quan trọng của bài thực hành là assembler nhận Order đã được tải; assembler không tự truy vấn dữ liệu.

## Bước 2: Tạo assembler có self link

Tạo OrderModelAssembler:

~~~java
package com.example.orders;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse response = new OrderResponse(
                order.id(),
                order.customerName(),
                order.total(),
                order.status());

        return EntityModel.of(
                response,
                linkTo(methodOn(OrderController.class)
                        .findById(order.id()))
                        .withSelfRel());
    }
}
~~~

Hãy đọc kỹ phần tạo link:

- methodOn(OrderController.class).findById(order.id()) mô tả method controller cần liên kết tới. Spring HATEOAS dùng proxy invocation để đọc mapping; controller method không được thực thi ở bước này.
- linkTo(...) chuyển mapping thành URI dựa trên cấu hình MVC và request context.
- withSelfRel() gắn relation chuẩn self cho link.
- EntityModel.of(...) bọc DTO cùng link trong một representation model.

Assembler chỉ chuyển Order thành OrderResponse và thêm link. URI không được ghép bằng chuỗi như "/api/orders/" + order.id(), vì cách đó buộc assembler biết route và dễ sai khi route hoặc context path đổi.

## Bước 3: Tạo controller cho item và collection

Controller gọi service để lấy dữ liệu rồi giao assembler tạo item representation:

~~~java
package com.example.orders;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orders;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orders,
            OrderModelAssembler assembler) {
        this.orders = orders;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderResponse> findById(@PathVariable Long id) {
        Order order = orders.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Order not found"));

        return assembler.toModel(order);
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderResponse>> findAll() {
        List<Order> result = orders.findAll();

        CollectionModel<EntityModel<OrderResponse>> collection =
                assembler.toCollectionModel(result);

        collection.add(linkTo(methodOn(OrderController.class)
                .findAll())
                .withSelfRel());

        return collection;
    }
}
~~~

Có hai cấp self link trong API:

1. Item self link được tạo trong OrderModelAssembler.toModel(...). Nó trỏ tới GET /api/orders/{id}.
2. Collection self link được thêm trong findAll(). Nó trỏ tới GET /api/orders.

toCollectionModel(...) gọi assembler cho từng Order, do đó mỗi item trong collection có self link riêng. Link collection được thêm sau khi collection model được tạo.

Tạo class khởi động ứng dụng:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }
}
~~~

## Bước 4: Chạy API và quan sát response

Khởi động ứng dụng rồi gọi endpoint item:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/orders/101
~~~

Response có dạng:

~~~http
HTTP/1.1 200
Content-Type: application/hal+json

{
  "id": 101,
  "customerName": "Nguyen An",
  "total": 125000.00,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/101"
    }
  }
}
~~~

Tiếp theo gọi collection:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/orders
~~~

Collection có self link của chính collection. Mỗi item được nhúng cũng có self link riêng. Tên relation embedded được Spring HATEOAS suy ra từ kiểu dữ liệu; không nên hard-code tên relation embedded trong client nếu API có công bố relation khác.

Kiểm tra ID không tồn tại:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/orders/999
~~~

Kết quả mong đợi là HTTP 404. Không trả một representation rỗng hoặc self link trỏ tới một đơn hàng không tồn tại.

## Bước 5: Kiểm thử self link bằng MockMvc

Tạo integration test dùng ứng dụng thật với dữ liệu trong bộ nhớ:

~~~java
package com.example.orders;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
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
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void itemResponseContainsSelfLink() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 101L)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$._links.self.href",
                        endsWith("/api/orders/101")));
    }

    @Test
    void collectionResponseContainsSelfLink() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href",
                        endsWith("/api/orders")));
    }

    @Test
    void unknownOrderReturnsNotFound() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 999L)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isNotFound());
    }
}
~~~

Test xác minh relation self có mặt và href kết thúc bằng đường dẫn mong đợi. Không so sánh toàn bộ absolute URL vì hostname, port và context path có thể khác giữa máy phát triển, test và production.

Nếu muốn kiểm tra self link của từng item trong collection, đọc body JSON và duyệt mảng embedded theo relation thực tế của response. Xác minh mỗi item có href riêng tương ứng với ID của nó.

## Bước 6: Thử điều hướng theo href

Một client HATEOAS nên lấy URI từ response. Ví dụ, sau khi nhận response item:

1. Đọc trường _links.self.href.
2. Dùng href đó cho request tiếp theo khi cần tải lại tài nguyên.
3. Không tự tạo lại URI từ ID và một route được viết cứng trong client.

Với collection, client bắt đầu từ URI collection, đọc embedded items và theo self link của item cần mở. Khi API thay đổi route nhưng vẫn giữ relation self, client có thể tiếp tục hoạt động mà không cần biết cách ghép path mới.

Hãy thử thay đổi mapping controller từ /api/orders sang /store/orders. Chạy lại test và quan sát href được tạo từ mapping mới. Client dùng link từ response vẫn có thể điều hướng theo URI mới.

## Tiêu chí hoàn thành

- [ ] Ứng dụng khởi động thành công với Spring MVC và Spring HATEOAS.
- [ ] GET /api/orders/101 trả HTTP 200 và media type HAL JSON.
- [ ] Item response có relation self.
- [ ] Href self trỏ đúng endpoint item.
- [ ] GET /api/orders trả collection có relation self.
- [ ] Các item trong collection có self link riêng.
- [ ] GET /api/orders/999 trả HTTP 404.
- [ ] MockMvc test cho item, collection và not-found đều pass.
- [ ] Assembler không hard-code URI và không truy vấn repository.
- [ ] Client có thể lấy href từ response để điều hướng.

## Thử thách mở rộng

Sau khi hoàn thành yêu cầu cơ bản, hãy tự mở rộng:

1. Thêm endpoint GET /api/orders/{id}/customer và relation customer cho item. Tạo URI bằng methodOn thay vì ghép chuỗi.
2. Thêm pagination cho collection và xác minh self link giữ lại page, size cùng filter hiện tại.
3. Đưa ứng dụng vào context path /shop rồi xác minh self link có context path đúng.
4. Tạo một client test chỉ dùng relation self để tải item, không biết route cụ thể.
5. Viết test xác minh khi mapping đổi, href trong response đổi theo mapping và các relation vẫn giữ nguyên.

## Lỗi thường gặp

- **Không thấy _links trong JSON:** kiểm tra request Accept là application/hal+json và ứng dụng đã thêm Spring HATEOAS starter.
- **Self link sai path:** kiểm tra class-level và method-level RequestMapping; tạo URI từ methodOn để tránh route viết cứng.
- **Collection có self link nhưng item không có:** bảo đảm assembler được dùng qua toCollectionModel(...) và toModel(...) thêm self link.
- **Href có host hoặc port lạ:** kiểm tra forwarded headers, reverse proxy và cấu hình base URL trong môi trường triển khai.
- **Endpoint item trả 200 cho ID không tồn tại:** service phải báo không tìm thấy và controller ánh xạ thành 404.
- **Test phụ thuộc hostname:** dùng endsWith hoặc kiểm tra URI path thay vì so sánh toàn bộ absolute URL.
- **Client tiếp tục ghép URI:** thay logic đó bằng cách đọc href từ relation self.

## Kết quả cần nộp

Hoàn thành source code cho model, service, assembler, controller và integration test. Ghi lại hai response HAL của item và collection, kèm kết quả test cho trường hợp ID không tồn tại. Trong phần mô tả ngắn, giải thích nơi tạo self link của item, nơi tạo self link của collection và cách client theo href mà server công bố.

Self link là điểm điều hướng cơ bản của một resource representation. Qua dự án nhỏ này, bạn đã để server công bố URI từ mapping thực tế, để assembler chịu trách nhiệm tạo item representation và để client sử dụng link thay vì tự đoán cấu trúc URL.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, Building links in Spring MVC: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder
- Spring HATEOAS Reference Documentation, Representation models: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models
- Spring HATEOAS API, RepresentationModelAssembler: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html
- Spring Boot Reference Documentation, Spring HATEOAS: https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html
