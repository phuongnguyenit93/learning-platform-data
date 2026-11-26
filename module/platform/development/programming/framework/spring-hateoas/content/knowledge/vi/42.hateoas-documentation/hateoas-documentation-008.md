# Tài liệu migration

## Mục tiêu

Nâng cấp Spring HATEOAS không chỉ là đổi version của một dependency. Mỗi major release có thể thay đổi API Java, package, cách đăng ký hypermedia media type, tích hợp Spring Boot, Jackson và cả định dạng representation được gửi tới client. Nếu chỉ sửa code cho biên dịch, ứng dụng vẫn có thể gặp lỗi runtime hoặc làm thay đổi hợp đồng HAL mà client đang sử dụng.

Tài liệu migration giúp xác định những thay đổi giữa phiên bản nguồn và phiên bản đích, phân loại phần cần sửa và chọn thứ tự nâng cấp an toàn. Với Spring HATEOAS, cần đọc tài liệu của chính thư viện cùng migration guide của Spring Boot, Spring Framework, Jackson và các release notes liên quan.

Sau bài học, bạn có thể:

- Chọn đúng tài liệu cho phiên bản nguồn và phiên bản đích.
- Phân biệt migration guide, release notes, Javadocs và security advisories.
- Áp dụng các thay đổi API lớn từ Spring HATEOAS 0.x sang 1.0.
- Nhận diện các thay đổi nền tảng khi chuyển sang Spring HATEOAS 3.x.
- Lập kế hoạch nâng cấp theo từng lớp dependency và API.
- Kiểm thử lại representation, links, affordances và client traversal sau migration.

## Migration documentation gồm những gì?

Không có một tài liệu duy nhất mô tả mọi thay đổi của toàn bộ hệ Spring. Hãy dùng từng loại tài liệu cho một câu hỏi cụ thể:

| Tài liệu | Câu hỏi cần trả lời | Khi nào cần đọc |
|---|---|---|
| Migration guide | Phải đổi gì khi chuyển từ phiên bản cũ sang phiên bản mới? | Trước khi bắt đầu major upgrade. |
| Release notes/changelog | Phiên bản cụ thể đã thêm, sửa hoặc loại bỏ điều gì? | Với từng minor và patch release. |
| Javadocs | API hiện tại có method, constructor, package và contract nào? | Khi sửa code hoặc thay API deprecated. |
| Spring Boot migration guide | Platform, starter, auto-configuration và properties thay đổi ra sao? | Khi nâng cấp Spring Boot cùng HATEOAS. |
| Spring Framework migration guide | MVC, WebFlux, HTTP converters và các integration API thay đổi gì? | Khi đổi major của Spring Framework. |
| Jackson migration guide | Mapper, package, module và serialization defaults thay đổi thế nào? | Khi nâng cấp Jackson 2 lên Jackson 3. |
| Security advisories | Phiên bản nào bị ảnh hưởng và bản vá bắt đầu từ đâu? | Trước khi chọn version đích và trước khi phát hành. |

Tài liệu cần khớp với phiên bản đang dùng. Javadocs của phiên bản mới nhất có thể chứa API chưa tồn tại ở phiên bản đích của dự án. Tương tự, một release note của patch mới không thay thế migration guide cho major release.

## Xác định phiên bản nguồn và phiên bản đích

Trước khi đọc migration guide, ghi lại các thông tin sau:

- Spring Boot đang dùng và phiên bản maintenance hiện tại của nhánh đó.
- Spring HATEOAS đang dùng.
- Spring Framework và Spring Security được quản lý bởi BOM nào.
- Java, Servlet container hoặc reactive runtime.
- Jackson và các module serialization tùy chỉnh.
- Các media type đang được công bố, chẳng hạn HAL, HAL-FORMS hoặc Problem Details.
- Các API deprecated đang được sử dụng trong code.

Nếu dùng Spring Boot, ưu tiên để Spring Boot dependency management chọn các phiên bản tương thích. Tránh tự nâng riêng Spring HATEOAS hoặc Spring Framework vượt khỏi release train mà Boot đang quản lý. Nếu quản lý dependency trực tiếp, cần xác minh compatibility matrix của từng thành phần trước khi đổi version.

Một lộ trình migration phải có cặp phiên bản rõ ràng, ví dụ:

~~~text
Nguồn: Spring Boot 3.x + Spring HATEOAS 2.x
Đích: Spring Boot 4.x + Spring HATEOAS 3.x
~~~

Không suy ra rằng mọi ứng dụng dùng HATEOAS 2.x đều có cùng thay đổi. Một dự án có custom media type, Jackson module hoặc code dùng API deprecated sẽ cần nhiều bước hơn dự án chỉ dùng EntityModel và HAL mặc định.

## Thay đổi lớn từ Spring HATEOAS 0.x sang 1.0

Spring HATEOAS 1.0 là một lần tái cấu trúc API lớn. Mục tiêu là dùng tên gọi phản ánh đúng representation model và tách rõ API phía server, phía client cùng phần triển khai media type.

### Đổi tên representation models

Các kiểu cũ và kiểu thay thế:

| API 0.x | API từ 1.0 |
|---|---|
| ResourceSupport | RepresentationModel |
| Resource | EntityModel |
| Resources | CollectionModel |
| PagedResources | PagedModel |
| ResourceAssembler | RepresentationModelAssembler |
| toResource(...) | toModel(...) |
| toResources(...) | toCollectionModel(...) |

Ví dụ, code cũ có thể khai báo:

~~~java
class OrderResource extends ResourceSupport {
    private String status;
}
~~~

Sau khi migration:

~~~java
import org.springframework.hateoas.RepresentationModel;

class OrderModel extends RepresentationModel<OrderModel> {
    private String status;
}
~~~

Với assembler, tên interface và method cũng thay đổi:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;

class OrderAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderModel>> {

    @Override
    public EntityModel<OrderModel> toModel(Order order) {
        return EntityModel.of(new OrderModel());
    }
}
~~~

Không chỉ thay tên class. Hãy tìm các generic type, return type, import và lời gọi method cũ trong toàn bộ source code, bao gồm test, custom serializer và client.

### Thay đổi package và tên API

| API cũ | API mới hoặc vị trí mới |
|---|---|
| LinkDiscoverer | Package client |
| LinkBuilder | Package server |
| EntityLinks | Package server |
| ControllerLinkBuilder | Được chuyển vào server.mvc và deprecated; dùng WebMvcLinkBuilder |
| RelProvider | LinkRelationProvider |
| String relation | LinkRelation |
| VndError | Package mediatype.vnderror |

Ví dụ tạo link trong Spring MVC:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class)
        .findById(order.id()))
        .withSelfRel();
~~~

Khi đổi từ RelProvider sang LinkRelationProvider, kiểm tra các interface tự triển khai. API mới trả LinkRelation thay cho String; các implementation và nơi tiêu thụ relation cần được điều chỉnh theo kiểu mới.

### RepresentationModel.getLinks() trả về Links

Trong API mới, getLinks() trả về đối tượng Links thay vì List<Link>. Links cung cấp API để kết hợp, lọc và thao tác trên tập links. Nếu code cũ khai báo trực tiếp:

~~~java
List<Link> links = model.getLinks();
~~~

hãy chuyển sang dùng kiểu Links hoặc chuyển sang collection Java tại ranh giới cần thiết:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Links;

Links links = model.getLinks();
boolean hasSelf = links.hasLink(IanaLinkRelations.SELF);
~~~

Không nên ép mọi nơi quay lại List<Link> nếu logic có thể dùng trực tiếp các phép toán của Links.

## Migration script cho bước 1.0

Tài liệu Spring HATEOAS 1.0 có cung cấp migration script để thay các import và static method references đã được di chuyển. Script được thiết kế để chạy từ application root và mặc định kiểm tra các file Java.

Script có thể giúp:

- Thay một số tên class cũ bằng tên mới.
- Cập nhật import cho các API chuyển package.
- Điều chỉnh một số static method references.

Script không bảo đảm sửa toàn bộ source code. Nó không thể tự hiểu mọi generic type, custom media type, logic nghiệp vụ hoặc hợp đồng JSON của ứng dụng.

Quy trình sử dụng an toàn:

1. Tạo branch migration và bảo đảm working tree sạch.
2. Đọc hướng dẫn chính thức để lấy đúng script dành cho bước 0.x sang 1.0.
3. Chạy script trong branch migration theo hướng dẫn của dự án.
4. Xem toàn bộ diff, đặc biệt các import, generic type và method references.
5. Sửa phần script không thể nhận diện.
6. Biên dịch và chạy test trước khi tiếp tục nâng cấp các dependency khác.

Không dùng script migrate-to-1.0.sh như một công cụ nâng cấp chung cho Spring HATEOAS 2.x hoặc 3.x. Nó chỉ giải quyết nhóm thay đổi được tài liệu 1.0 mô tả.

## Một số thay đổi trong giai đoạn phát triển 1.0

Nếu dự án từng dùng milestone hoặc release candidate, hãy đọc phần migration tương ứng giữa các bản pre-release. Ví dụ, tài liệu 1.0 RC1 ghi nhận:

- Các API Link.andAffordance(...) nhận affordance details được chuyển sang Affordances. Cách xây dựng thủ công dùng Affordances.of(link).afford(...).
- AffordanceModelFactory.getAffordanceModel(...) chuyển từ ResolvableType sang InputPayloadMetadata và PayloadMetadata. Custom media type implementation cần thích ứng.
- HAL-FORMS điều chỉnh cách render các thuộc tính có giá trị mặc định theo specification, ví dụ có thể bỏ thuộc tính required=false thay vì render tường minh.

Các thay đổi milestone/RC chỉ áp dụng khi phiên bản nguồn của bạn thực sự là milestone hoặc release candidate tương ứng. Không áp dụng chúng như một breaking change mới cho mọi ứng dụng đang chạy bản GA hiện tại.

## Nâng cấp từ Spring HATEOAS 2.x lên 3.x

Tài liệu reference hiện hành vẫn giữ chương migration chi tiết cho 1.0; không có một chương migration tương tự bao quát mọi thay đổi từ 2.x lên 3.x. Với bước nâng cấp này, cần kết hợp release notes của Spring HATEOAS với migration guide của Spring Boot, Spring Framework và Jackson.

Spring HATEOAS 3.x thuộc thế hệ nền tảng Spring Framework 7 và Jackson 3. Khi ứng dụng đi cùng Spring Boot 4, migration cần được xem là một lần nâng cấp platform đồng bộ:

| Thành phần | Điều cần rà soát |
|---|---|
| Spring Boot | Nâng theo hướng dẫn Boot 4; xem dependency management, module và starter mới. |
| Spring Framework | Boot 4 yêu cầu Spring Framework 7.x nếu quản lý dependency trực tiếp. |
| Java | Spring Boot 4 yêu cầu Java 17 trở lên. |
| Servlet | Ứng dụng MVC cần container tương thích Servlet 6.1. |
| Jackson | Spring Boot 4 dùng Jackson 3 làm mặc định; kiểm tra package và mapper customization. |
| Spring HATEOAS | Chọn nhánh tương thích với Boot/Framework và dùng maintenance release đã vá. |

Không nâng riêng thư viện HATEOAS lên 3.x trong một ứng dụng vẫn đang cố định toàn bộ platform ở Spring Framework 6.x. Hãy kiểm tra dependency graph và release train trước khi thay version.

### Jackson 2 sang Jackson 3

Đây là một trong những thay đổi dễ ảnh hưởng đến code tùy chỉnh nhất. Jackson 3 chuyển phần lớn package và Maven group từ com.fasterxml.jackson sang tools.jackson. Ngoại lệ quan trọng là jackson-annotations vẫn giữ package com.fasterxml.jackson.annotation để tương thích.

Một số điểm cần rà soát:

- Import ObjectMapper, JsonNode, serializers, deserializers và module classes.
- Custom Jackson modules được đăng ký thủ công.
- Các bean và customizer từng dựa trên Jackson2ObjectMapperBuilder.
- Code tích hợp với message converters.
- Test so sánh JSON bằng raw string.
- Các default serialization thay đổi.

Trong hệ Spring Boot 4, JSON mapper được auto-configure theo Jackson 3. JsonMapper là kiểu mapper dành riêng cho JSON; cấu hình tùy chỉnh nên dùng JsonMapper.Builder và các customizer tương ứng của Spring Framework 7.

Ví dụ customizer theo cách mới:

~~~java
import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
import tools.jackson.databind.SerializationFeature;

@Bean
JsonMapperBuilderCustomizer jsonMapperCustomizer() {
    return builder -> builder.enable(SerializationFeature.INDENT_OUTPUT);
}
~~~

Đoạn code minh họa cho ứng dụng dùng Spring Boot 4. Nếu ứng dụng không dùng Boot, cách cấu hình mapper phụ thuộc vào Jackson 3 và message converter mà Spring Framework 7 cung cấp.

Jackson 3 cũng thay đổi một số serialization defaults. Ví dụ, thứ tự property có thể được sắp xếp alphabetically và ngày giờ được serialize theo ISO-8601 thay vì dạng timestamp mặc định cũ. Các thay đổi này có thể làm snapshot test của HAL JSON khác đi dù logic tạo link không đổi.

Nếu cần một giai đoạn chuyển tiếp, Spring Boot 4 có property spring.jackson.use-jackson2-defaults để đưa một số default của JsonMapper gần với Jackson 2 hơn. Đây là bước đệm, không nên xem là giải pháp thay thế cho việc kiểm tra và hoàn tất migration Jackson 3.

### Module và starter của Spring Boot 4

Spring Boot 4 có thiết kế module nhỏ và tập trung hơn. Khi nâng cấp, rà soát dependency và starter thay vì giả định mọi module cũ vẫn được kéo vào theo cùng cách. Boot 4 cung cấp starter riêng cho Spring HATEOAS; kiểm tra starter đang dùng và các dependency transitively cần thiết.

Với ứng dụng Spring MVC dùng Spring Boot 4, starter là:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-hateoas")
}
~~~

Starter này dành cho Spring MVC và không nên kết hợp với Spring WebFlux. Nếu ứng dụng dùng WebFlux, dùng dependency trực tiếp org.springframework.hateoas:spring-hateoas cùng spring-boot-starter-webflux. Không thêm cả hai web stacks chỉ để lấy hypermedia support.

Spring Boot auto-configuration đã đăng ký các thành phần HATEOAS thường cần, nên đa số ứng dụng không cần tự thêm @EnableHypermediaSupport. Nếu thêm annotation để kiểm soát cấu hình hypermedia thủ công, lưu ý rằng nó thay quyền cấu hình của Boot và có thể tắt JsonMapper customization được mô tả ở phần Jackson.

Nếu ứng dụng tự quản lý dependency thay vì dùng Boot starter/BOM, cần xác minh phiên bản Spring Framework, Spring HATEOAS, Jackson, Reactor và các thư viện liên quan tương thích với nhau. Không thêm các version override chỉ để ép build qua nếu chưa hiểu dependency conflict.

## Đọc release notes theo từng mốc

Migration guide giúp lập kế hoạch cho thay đổi lớn. Release notes giúp phát hiện các thay đổi và bản vá ở từng maintenance release.

Tại thời điểm biên soạn 26/11/2026, trang release chính thức liệt kê Spring HATEOAS 3.1.3 là bản stable mới nhất và 3.2.0-RC1 là pre-release. Reference documentation hiện được publish ở phiên bản 3.1.2. Điều này cho thấy version của Javadocs/reference guide có thể chậm hơn một patch so với release mới nhất.

Khi chọn version đích:

1. Xác định nhánh tương thích với Spring Boot và Spring Framework của dự án.
2. Chọn maintenance release mới nhất trong nhánh đó.
3. Đọc release notes từ version nguồn tới version đích.
4. Kiểm tra versioned reference documentation và Javadocs đúng phiên bản.
5. Đọc security advisories của thư viện và dependency transitive.
6. Chỉ dùng milestone/RC nếu có chủ đích thử nghiệm.

Không chọn bản pre-release cho production chỉ vì số version lớn hơn. Cũng không coi patch release chỉ là cập nhật dependency vô hại: patch có thể sửa serializer, parser, cache hoặc bảo mật.

### Ví dụ vì sao phải đọc security advisories

Trong năm 2026, Spring HATEOAS công bố các bản vá cho những vấn đề ảnh hưởng đến một số maintenance releases, gồm lỗi xử lý deserialization của Collection+JSON/UBER và khả năng heap exhaustion do cache nội bộ không giới hạn. Các bản vá được công bố trong release line 3.0.4 và 2.5.3.

Ví dụ này nhấn mạnh rằng migration review cần kiểm tra cả security advisory, không chỉ compile errors hoặc API deprecation. Hãy mở advisory tương ứng để xác định chính xác các phiên bản bị ảnh hưởng và phiên bản đã vá; không suy rộng phạm vi từ một release line sang mọi nhánh.

## Lập kế hoạch migration theo từng lớp

Một migration dễ kiểm soát khi chia thành các lớp độc lập:

| Lớp | Công việc | Kết quả cần có |
|---|---|---|
| Dependency | Chọn BOM và phiên bản tương thích. | Dependency tree không có xung đột ngoài dự kiến. |
| Source API | Thay API deprecated/removed, package và generic type. | Main source và test source biên dịch. |
| Serialization | Kiểm tra Jackson, message converter và custom media type. | Representation được serialize đúng. |
| Hypermedia contract | Kiểm tra relation, href, templates, embedded resources và affordances. | Client vẫn điều hướng được theo hợp đồng đã công bố. |
| Runtime | Kiểm tra MVC/WebFlux, security, proxy và auto-configuration. | Application context khởi động và endpoint hoạt động. |
| Security | Đọc advisories và nâng patch có bản vá. | Không còn dùng phiên bản nằm trong phạm vi ảnh hưởng. |
| Operations | Kiểm tra log, metrics, startup diagnostics và deployment runtime. | Có thể vận hành và rollback nếu cần. |

Nâng cấp theo một thay đổi có thể kiểm chứng tại mỗi bước. Nếu đồng thời đổi Spring Boot, Spring Framework, Jackson, Spring Security và cấu trúc representation trong một commit lớn, rất khó xác định nguyên nhân khi test thất bại.

## Checklist trước khi sửa code

- [ ] Ghi lại version nguồn và version đích của từng dependency.
- [ ] Xác định ai quản lý version: Spring Boot BOM hay dependency management riêng.
- [ ] Nâng ứng dụng lên maintenance release cuối của nhánh hiện tại trước khi đổi major.
- [ ] Xử lý các deprecation warnings còn tồn tại.
- [ ] Đọc migration guide của Spring HATEOAS và các framework nền.
- [ ] Đọc release notes cho tất cả version nằm giữa nguồn và đích.
- [ ] Kiểm tra security advisories và bản vá.
- [ ] Lập danh sách custom media types, Jackson modules và custom link discoverers.
- [ ] Lưu lại sample response hiện tại để so sánh hợp đồng.

## Checklist sau khi nâng cấp

- [ ] Main source và test source biên dịch.
- [ ] Application context khởi động với cấu hình production tương đương.
- [ ] Controller tạo đúng self link và relation.
- [ ] Collection, pagination và search links giữ đúng URI template.
- [ ] HAL single-link rendering và embedded relation đúng chính sách.
- [ ] HAL-FORMS affordances và template properties không đổi ngoài dự kiến.
- [ ] Problem Details giữ đúng media type và extension members.
- [ ] Traverson hoặc client thực tế vẫn tìm link và đi theo relation.
- [ ] Custom Jackson serializers/deserializers và media type modules hoạt động.
- [ ] Security filters, forwarded headers và context path tạo đúng links.
- [ ] Integration tests xác minh Content-Type, status và response body.
- [ ] Security advisory không còn đánh dấu version đích là bị ảnh hưởng.
- [ ] Theo dõi log startup để loại bỏ cảnh báo migration tạm thời.

## Kiểm thử hợp đồng hypermedia sau migration

Không chỉ kiểm tra JSON có parse được. Client có thể phụ thuộc vào relation và semantics của link ngay cả khi URI cụ thể thay đổi.

Ví dụ một test hợp đồng HAL có thể xác minh:

~~~java
mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$.id").value(orderId.toString()))
        .andExpect(jsonPath("$._links.self.href").exists());
~~~

Với mỗi media type được hỗ trợ, hãy lưu sample response trước migration và so sánh có chủ đích sau migration. Không nên snapshot mọi byte nếu thứ tự JSON property không phải semantics của API. Thay vào đó, parse JSON rồi kiểm tra:

- Media type và HTTP status.
- Tên relation và số lượng link.
- Href, URI template và các biến được công bố.
- Embedded relation và cấu trúc collection.
- Affordance metadata và form properties.
- Pagination metadata và filter được giữ trong self link.

Các assertion cho relation ngoài self cần khớp hợp đồng của API cụ thể. Ví dụ, chỉ kiểm tra cancel nếu relation đó được công bố cho trạng thái và principal đang dùng trong fixture; không giả định mọi representation đều có cùng action links.

Thêm test traversal bắt đầu từ entry point rồi theo relation tới collection và item. Test này kiểm tra client thực sự dùng được hypermedia contract sau khi serializer hoặc link builder thay đổi.

## Các lỗi migration thường gặp

- **Chỉ đổi version dependency:** compile có thể thành công nhưng JSON hoặc links đã thay đổi; cần contract test.
- **Dùng script 1.0 cho mọi lần nâng cấp:** script chỉ hỗ trợ các thay đổi được mô tả cho bước 0.x sang 1.0.
- **Sửa import nhưng quên generic type:** các assembler và collection response có thể vẫn dùng kiểu cũ.
- **Nâng Spring HATEOAS riêng lẻ:** dependency có thể không tương thích với Boot, Framework hoặc Jackson.
- **Bỏ qua Jackson customizations:** custom serializer và message converter có thể không còn hoạt động sau khi đổi mapper.
- **So sánh JSON raw string:** khác thứ tự property không nhất thiết là thay đổi semantics; parse JSON và kiểm tra cấu trúc.
- **Chỉ chạy unit test assembler:** chưa xác minh MVC serialization, content negotiation và request context.
- **Chỉ kiểm tra self link:** client còn phụ thuộc search, pagination, action links, embedded resources và affordances.
- **Dùng bản RC trong production:** pre-release có thể còn thay đổi; chọn stable maintenance release phù hợp.
- **Bỏ qua security advisory:** một version biên dịch và test qua vẫn có thể nằm trong phạm vi bị ảnh hưởng.
- **Không chuẩn bị rollback:** luôn giữ dependency lock, artifact và cách triển khai có thể quay về phiên bản nguồn.

## Quy trình migration đề xuất

1. Chốt phiên bản nguồn, phiên bản đích và ma trận tương thích.
2. Nâng phiên bản nguồn lên maintenance release mới nhất của nhánh hiện tại.
3. Đọc migration guide, release notes, Javadocs và security advisories tương ứng.
4. Chia thay đổi thành dependency, source API, serialization, hypermedia contract và runtime.
5. Thay API deprecated/removed và package cũ theo đúng hướng dẫn.
6. Nâng Spring Boot, Spring Framework, Jackson và Spring HATEOAS theo một release train tương thích.
7. Chạy compile và unit tests sau mỗi nhóm thay đổi.
8. Chạy integration tests và so sánh sample representations.
9. Chạy client traversal tests và kiểm tra links trong môi trường gần production.
10. Theo dõi startup diagnostics, log và security advisories trước khi phát hành.

Tài liệu migration là bản đồ để xác định thay đổi, không phải script tự động nâng cấp toàn bộ ứng dụng. Với Spring HATEOAS, hãy đặc biệt kiểm tra cả API Java và hợp đồng hypermedia mà client nhận được. Một migration hoàn tất khi ứng dụng chạy trên dependency set tương thích, response giữ đúng semantics và client vẫn khám phá được API qua links.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, Migrating to Spring HATEOAS 1.0: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#preface.migrating-to-1.0
- Spring HATEOAS Release Notes: https://github.com/spring-projects/spring-hateoas/releases
- Spring HATEOAS 3.0 Reference Documentation: https://docs.spring.io/spring-hateoas/docs/3.0.x/reference/html/
- Spring HATEOAS 2.5 Reference Documentation: https://docs.spring.io/spring-hateoas/docs/2.5.x/reference/html/
- Spring Boot 4.0 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- Spring Blog, Introducing Jackson 3 support in Spring: https://spring.io/blog/2025/10/07/introducing-jackson-3-support-in-spring/
- Spring HATEOAS security advisory CVE-2026-41006: https://github.com/advisories/GHSA-7fxc-486f-32q9
- Spring HATEOAS security advisory CVE-2026-41007: https://github.com/advisories/GHSA-439x-6767-44cv
