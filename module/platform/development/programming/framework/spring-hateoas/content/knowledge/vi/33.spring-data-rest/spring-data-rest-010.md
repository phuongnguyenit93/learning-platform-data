# Giới hạn tự động sinh link

Spring Data REST tự động công bố tài nguyên dựa trên **Spring Data repository** và metadata mà ứng dụng khai báo. Từ repository, exporter có thể tạo collection resource, item resource, link tới association, search resource cho query method được export và các link phân trang. Cơ chế này giúp dựng nhanh một REST API có khả năng khám phá.

Tuy nhiên, repository metadata chỉ mô tả cấu trúc truy cập dữ liệu. Nó không mô tả đầy đủ quy trình nghiệp vụ, quyền của người dùng, trạng thái workflow hoặc dịch vụ bên ngoài. Vì vậy, Spring Data REST không thể tự suy ra mọi link mà client cần. Những hành động như duyệt đơn hàng, hoàn tiền, phát hành hóa đơn, khóa tài khoản hoặc lấy dữ liệu từ hệ thống khác cần được thiết kế và công bố có chủ đích.

Hiểu giới hạn này giúp quyết định khi nào nên dùng link mặc định, khi nào bổ sung link bằng Spring HATEOAS và khi nào cần custom controller hoặc endpoint riêng.

## Spring Data REST tự động sinh link từ đâu?

Spring Data REST tập trung export các tài nguyên dựa trên repository. Ví dụ:

~~~java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders",
    itemResourceRel = "order"
)
public interface OrderRepository extends JpaRepository<Order, UUID> {
}
~~~

Repository trên cho phép Spring Data REST công bố collection resource tại /orders và item resource cho từng đơn hàng tại /orders/{id}. Các HTTP method mặc định được ánh xạ dựa trên những method repository mà exporter hỗ trợ, chẳng hạn findAll, findById, save và delete.

Ở mức ứng dụng, client có thể bắt đầu khám phá từ root URL. HAL response thường có link tới các collection resource đã export và link profile mô tả metadata của API:

~~~json
{
  "_links": {
    "orders": {
      "href": "https://api.example.com/orders"
    },
    "profile": {
      "href": "https://api.example.com/api/alps"
    }
  }
}
~~~

Đây là link điều hướng được sinh từ repository discovery. Trong ví dụ, /api là base path minh họa; URI profile thực tế phụ thuộc cấu hình Spring Data REST. Nếu một repository không được export, collection resource của nó không xuất hiện ở root.

## Những link được tạo tự động

Spring Data REST có thể tạo một số nhóm link dựa trên cấu trúc repository và domain model:

| Nguồn metadata | Resource/link thường được tạo | Giới hạn |
| --- | --- | --- |
| Repository được export | Link collection ở root và item resource theo ID | Chỉ có với repository được phát hiện và cho phép export |
| Các method CRUD được hỗ trợ | GET, POST, PUT, PATCH hoặc DELETE tương ứng | Phụ thuộc method repository và exposure configuration |
| Query method của repository | Search resource và link tới từng query | Chỉ query method được export mới được công bố |
| Association tới resource được quản lý | Link association trên item resource | Phản ánh quan hệ persistence, không phải mọi quan hệ nghiệp vụ |
| Paging repository | Link first, prev, self, next, last khi phù hợp và page metadata | Phụ thuộc kiểu repository và cấu hình phân trang |
| Annotation path/rel | URI và tên relation theo metadata | Chỉ đổi cách công bố resource đã có, không tự tạo nghiệp vụ mới |

Ví dụ collection resource có thể chứa link search nếu repository khai báo query method:

~~~java
import java.util.UUID;
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders",
    itemResourceRel = "order"
)
public interface OrderRepository extends JpaRepository<Order, UUID> {

    @RestResource(path = "by-status", rel = "by-status")
    Page<Order> findByStatus(OrderStatus status, Pageable pageable);
}
~~~

Query method được công bố dưới search resource, ví dụ /orders/search/by-status. Link search được exporter tạo vì repository khai báo một query có thể gọi qua HTTP. Search resource và query method resource là tài nguyên chỉ đọc, thường chỉ hỗ trợ GET. Spring Data REST không tự phát hiện mọi câu hỏi nghiệp vụ mà người dùng có thể đặt; nếu không có query method hoặc custom search endpoint, không có link tìm kiếm tương ứng.

## Association link chỉ phản ánh quan hệ được quản lý

Với item resource, Spring Data REST có thể tạo link cho association trong domain type. Ví dụ:

~~~java
import java.util.UUID;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;

@Entity
class Order {

    @Id
    private UUID id;

    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
~~~

Nếu Customer có repository được export, representation đơn hàng có thể có link relation customer. Spring Data REST cũng cung cấp association resource để đọc hoặc thay đổi quan hệ theo các method được hỗ trợ.

Exporter tạo link cho association được quản lý bởi repository. Với property đơn giản hoặc dữ liệu nhúng, nó có thể copy dữ liệu vào representation. Nó không tự tạo link tới mọi giá trị tính toán, đối tượng ngoài persistence context, API bên thứ ba hoặc dịch vụ không có repository tương ứng.

Ví dụ, Order có thể có thuộc tính computedRiskScore hoặc một service trả về trạng thái vận chuyển từ hệ thống logistics. Hai dữ liệu này không tự biến thành resource link chỉ vì chúng xuất hiện trong domain model. Nếu client cần điều hướng tới lịch sử vận chuyển, ứng dụng phải tạo resource và link tương ứng.

## Giới hạn quan trọng: repository không phải workflow engine

Các link mặc định thường mô tả thao tác dữ liệu tổng quát:

- Đọc collection hoặc một item.
- Tạo item bằng POST.
- Cập nhật item bằng PUT/PATCH nếu được export.
- Xóa item bằng DELETE nếu được export.
- Tìm kiếm bằng query method đã khai báo.
- Đọc hoặc cập nhật association resource.
- Điều hướng giữa các trang của collection.

Các thao tác nghiệp vụ thường có ngữ nghĩa riêng:

- Duyệt đơn hàng chỉ khi trạng thái là PENDING.
- Hủy đơn nếu chưa giao hàng.
- Hoàn tiền nếu thanh toán đã capture và chưa hoàn.
- Phát hành hóa đơn sau khi đơn hoàn tất.
- Khóa tài khoản theo chính sách bảo mật.

Spring Data REST không thể suy luận các điều kiện này chỉ từ tên method save hoặc delete. Nó cũng không tự tạo relation nghiệp vụ như approve-order hoặc refund-payment dựa trên tên trạng thái trong entity.

Một item resource có link DELETE không có nghĩa người dùng hiện tại được phép xóa item. Sự hiện diện của link không thay thế authorization tại endpoint. Server luôn phải kiểm tra quyền, trạng thái và quy tắc nghiệp vụ khi request thực sự đến.

## Path và rel chỉ tùy chỉnh resource đã được export

Annotation @RepositoryRestResource và @RestResource cho phép đổi path hoặc relation của resource đã có:

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people",
    itemResourceRel = "person"
)
interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "names", rel = "names")
    List<Person> findByName(String name);
}
~~~

Trong ví dụ, collection resource đổi sang /people và query method được công bố dưới /people/search/names. Các thuộc tính path và rel có nhiệm vụ đổi URI hoặc tên relation trong link.

Chúng không thêm hành động mới. Nếu cần link approve-order, chỉ đặt rel = "approve-order" trên một query method không khiến nó trở thành thao tác phê duyệt đúng nghĩa. Query method vẫn là query; thao tác thay đổi trạng thái cần endpoint và service nghiệp vụ tương ứng.

## Hạn chế repository và method được export

Không phải repository hoặc method nào cũng nên xuất hiện trên HTTP API. Có thể tắt export bằng exported = false.

Ẩn toàn bộ repository:

~~~java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(exported = false)
interface InternalAuditRepository extends JpaRepository<AuditEntry, UUID> {
}
~~~

Ẩn query method hoặc association:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RestResource;

interface OrderRepository extends JpaRepository<Order, UUID> {

    @RestResource(exported = false)
    List<Order> findByInternalReviewFlag(boolean flagged);
}
~~~

~~~java
import jakarta.persistence.FetchType;
import jakarta.persistence.ManyToOne;
import org.springframework.data.rest.core.annotation.RestResource;

@ManyToOne(fetch = FetchType.LAZY)
@RestResource(exported = false)
private Customer customer;
~~~

Annotation exported = false ngăn exporter công bố resource tương ứng. Với association, điều này giúp ẩn association resource khỏi hợp đồng HTTP. Association resource thường có GET để đọc quan hệ, PUT để gán quan hệ to-one hoặc thay tập quan hệ, POST để thêm phần tử cho quan hệ collection và DELETE để gỡ liên kết theo quy tắc của exporter. Đây là các thao tác quản lý quan hệ persistence, không tự trở thành hành động nghiệp vụ như mời khách hàng vào đơn hoặc chuyển giao trách nhiệm. Cần kiểm tra cả projection đang được export: projection có thể đưa property trở lại representation và làm thay đổi hiệu quả của cấu hình ẩn. Với dữ liệu nhạy cảm, hãy kiểm tra JSON thực tế và dùng projection/DTO cùng authorization để kiểm soát trường được trả về; việc ẩn một association link không phải là chính sách bảo mật dữ liệu đầy đủ.

Nếu không muốn công bố method CRUD, có thể override method repository và gắn @RestResource(exported = false) lên method tương ứng. Một số method CRUD dùng chung để phục vụ nhiều HTTP method. Ví dụ save có thể được dùng cho POST, PUT và PATCH; nếu cần tắt một HTTP method nhưng vẫn giữ method khác, cấu hình exposure ở mức HTTP method sẽ phù hợp hơn.

## Giới hạn HTTP method bằng ExposureConfiguration

Spring Data REST cho phép cấu hình method exposure theo domain type hoặc toàn cục bằng RepositoryRestConfiguration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.HttpMethod;

@Configuration
class OrderRestConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config -> {
            config.getExposureConfiguration()
                .forDomainType(Order.class)
                .withItemExposure((metadata, methods) ->
                    methods.disable(HttpMethod.DELETE));
        });
    }
}
~~~

Ví dụ trên tắt DELETE trên item resource của Order. Các method khác vẫn theo cấu hình hiện hành. Có thể dùng exposure configuration để kiểm soát method ở collection hoặc item và áp dụng quy tắc cho một domain type cụ thể.

Đây là cách giới hạn HTTP method được exporter hỗ trợ. Nó vẫn không thay thế Spring Security hoặc kiểm tra nghiệp vụ. Nếu một người dùng không được xóa đơn hàng, hãy bảo vệ endpoint bằng authorization và policy phù hợp, ngay cả khi link DELETE không được công bố.

## Repository detection cũng giới hạn link được sinh

Spring Data REST dùng RepositoryDetectionStrategy để quyết định repository nào được export. Các lựa chọn thường dùng:

| Strategy | Hành vi |
| --- | --- |
| DEFAULT | Export repository public hoặc được annotation phù hợp, đồng thời tôn trọng exported = false |
| ANNOTATED | Chỉ export repository được đánh dấu bằng RepositoryRestResource, trừ repository bị tắt |
| VISIBILITY | Dựa vào visibility của repository public |
| ALL | Export mọi repository được phát hiện, không phụ thuộc visibility/annotation theo cách của DEFAULT |

Chọn strategy phù hợp giúp tránh tự động công bố repository nội bộ chỉ vì nó nằm trong component scan. Nếu muốn chỉ những repository được duyệt mới trở thành REST resource, ANNOTATED thường là lựa chọn dễ kiểm soát.

## Bổ sung link nghiệp vụ bằng RepresentationModelProcessor

Khi muốn thêm link vào representation mặc định của entity, Spring Data REST tích hợp với Spring HATEOAS qua **RepresentationModelProcessor**. Các bean có kiểu RepresentationModelProcessor<EntityModel<T>> được exporter phát hiện và gọi khi serialize entity kiểu T.

Ví dụ, chỉ công bố link phê duyệt khi đơn hàng đang chờ duyệt:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
class OrderApprovalLinkProcessor
        implements RepresentationModelProcessor<EntityModel<Order>> {

    private static final LinkRelation APPROVE_ORDER =
        LinkRelation.of("https://api.example.com/rels/approve-order");

    private final OrderApprovalPolicy approvalPolicy;

    OrderApprovalLinkProcessor(OrderApprovalPolicy approvalPolicy) {
        this.approvalPolicy = approvalPolicy;
    }

    @Override
    public EntityModel<Order> process(EntityModel<Order> model) {
        Order order = model.getContent();

        if (order != null && approvalPolicy.canApprove(order)) {
            model.add(linkTo(
                methodOn(OrderWorkflowController.class)
                    .approve(order.getId())
            ).withRel(APPROVE_ORDER));
        }

        return model;
    }
}
~~~

Processor được gọi khi exporter tạo representation cho Order. Policy có thể xét trạng thái đơn hàng, người dùng hiện tại và quy tắc nghiệp vụ để quyết định có thêm link hay không. Khi đơn hàng không thể duyệt, link approve-order không xuất hiện.

Processor bổ sung link vào representation; nó không tự tạo endpoint. Controller và service thực hiện hành động vẫn phải được xây dựng riêng. Cũng cần tránh để processor phát sinh nhiều truy vấn phụ khi xử lý một collection lớn. Nếu cần biết khả năng thực hiện hành động, hãy thiết kế policy/query phù hợp và kiểm soát số lần truy cập dữ liệu.

## Tạo custom controller cho hành động nghiệp vụ

Để link approve-order có đích hợp lệ, tạo custom controller và service xử lý chuyển trạng thái:

~~~java
import java.util.UUID;

import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;

@RepositoryRestController
public class OrderWorkflowController {

    private final OrderApprovalService approvalService;

    OrderWorkflowController(OrderApprovalService approvalService) {
        this.approvalService = approvalService;
    }

    @PostMapping("/orders/{id}/approval")
    public ResponseEntity<Void> approve(@PathVariable UUID id) {
        approvalService.approve(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

@RepositoryRestController đặt handler trong base path của Spring Data REST và cho phép dùng cơ chế handler mapping, message converter, exception handling và CORS tương ứng. Annotation này phù hợp khi custom operation gắn với không gian URI của repository. Với resource tùy chỉnh không gắn với một repository cụ thể nhưng vẫn cần nằm dưới base path, có thể dùng @BasePathAwareController.

Trong ví dụ, processor tạo link bằng methodOn(OrderWorkflowController.class).approve(...), nên href được suy ra từ mapping controller. Không hard-code URL nếu có thể dùng link builder để tránh sai base path khi cấu hình API.

Service approvalService phải tự kiểm tra trạng thái, quyền người dùng và điều kiện chuyển trạng thái. Việc processor đã ẩn link không ngăn client gọi trực tiếp endpoint bằng URL cũ hoặc tự dựng request.

## Khi nào nên dùng processor, khi nào nên dùng controller riêng?

| Nhu cầu | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Thêm link liên quan vào representation entity mặc định | RepresentationModelProcessor<EntityModel<T>> | Mở rộng output exporter mà không thay toàn bộ representation |
| Thêm query link cho repository search | RepresentationModelProcessor trên search representation phù hợp | Bổ sung khả năng khám phá ở search resource |
| Tạo hành động nghiệp vụ có POST/PATCH và validation riêng | Custom controller + application service | Có endpoint và luồng nghiệp vụ rõ ràng |
| Tùy chỉnh collection/item URI hoặc rel | RepositoryRestResource/RestResource | Thay đổi metadata export sẵn có |
| Ẩn repository, method hoặc association | exported = false hoặc detection/exposure configuration | Giới hạn bề mặt API |
| Tạo resource không dựa trên repository | Custom controller hoặc controller HATEOAS riêng | Exporter không có repository metadata để suy ra resource |

Không dùng processor để thực hiện nghiệp vụ khi serialize response. Processor nên tập trung bổ sung metadata và link. Thay đổi dữ liệu thuộc về controller/service command path.

## Kiểm thử giới hạn link tự động và link tùy chỉnh

Kiểm thử cần xác nhận cả những gì exporter tự tạo lẫn những link do ứng dụng bổ sung. Ví dụ MockMvc kiểm tra link association mặc định và link approve-order theo trạng thái:

~~~java
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
class OrderRepositoryLinksTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesApprovalLinkWhenOrderCanBeApproved() throws Exception {
        mockMvc.perform(get("/orders/{id}", PENDING_ORDER_ID)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.customer.href").exists())
            .andExpect(jsonPath(
                "$._links['https://api.example.com/rels/approve-order'].href")
                .exists());
    }

    @Test
    void omitsApprovalLinkWhenOrderCannotBeApproved() throws Exception {
        mockMvc.perform(get("/orders/{id}", COMPLETED_ORDER_ID)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$._links['https://api.example.com/rels/approve-order']")
                .doesNotExist());
    }
}
~~~

PENDING_ORDER_ID và COMPLETED_ORDER_ID là fixture được chuẩn bị với trạng thái tương ứng. Test cũng giả định Order có association customer được export. Nếu ứng dụng dùng CURIE, JSONPath cần kiểm tra relation đã compact và khai báo curies tương ứng.

Với resource đã tắt export, kiểm tra link không xuất hiện ở root/search hoặc endpoint trả 404/405 tùy resource và mapping. Với method đã tắt bằng exposure configuration, kiểm tra HTTP method bị từ chối. Không chỉ test annotation; cần xác nhận response HTTP thực tế sau khi exporter xử lý.

## Những lỗi thường gặp

- **Cho rằng repository tự sinh mọi link:** exporter chỉ dựa trên repository, method, association và metadata được hỗ trợ.
- **Nhầm association với workflow:** association customer không đồng nghĩa với hành động approve-order hoặc refund-payment.
- **Dùng path/rel để tạo nghiệp vụ:** đổi tên link không tạo ra endpoint hay quy tắc nghiệp vụ.
- **Đưa query method thành command:** search resource được thiết kế để đọc; command cần endpoint có ngữ nghĩa riêng.
- **Dùng link như authorization:** client có thể gọi trực tiếp endpoint; server vẫn phải kiểm tra quyền.
- **Ẩn method chưa đủ:** một method repository có thể phục vụ nhiều HTTP method; dùng ExposureConfiguration khi cần giới hạn chính xác.
- **Quên projection:** projection có thể đưa property trở lại representation dù cấu hình exported=false đã được đặt.
- **Processor truy vấn quá nhiều:** xử lý mỗi entity trong collection có thể tạo N+1 nếu policy truy cập database riêng.
- **Processor làm thay đổi dữ liệu:** side effect khi serialize làm response không ổn định và khiến GET khó dự đoán.
- **Link không có endpoint đích:** processor thêm relation nhưng custom controller chưa được triển khai hoặc mapping sai base path.

Spring Data REST tự động sinh link rất hữu ích cho resource có cấu trúc repository rõ ràng: collection, item, association, search và pagination. Giới hạn của nó xuất hiện khi API cần diễn đạt workflow, quyền truy cập, trạng thái hoặc dịch vụ ngoài repository. Hãy dùng annotation và exposure configuration để kiểm soát bề mặt export, dùng RepresentationModelProcessor để bổ sung link vào representation, và dùng custom controller cùng service cho hành động nghiệp vụ thực sự.

## Tài liệu tham khảo

- [Spring Data REST – Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST – Configuring the REST URL path and hiding exported resources](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST – Customizing the JSON output with RepresentationModelProcessor](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html)
- [Spring Data REST – Customizing repository exposure and HTTP methods](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-sdr.html)
- [Spring Data REST – @RepositoryRestController and @BasePathAwareController](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
