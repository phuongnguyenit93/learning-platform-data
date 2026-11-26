# Chi phí tạo link trong Spring HATEOAS

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích những công đoạn tiêu tốn tài nguyên khi một REST API tạo hypermedia link.
- Phân biệt chi phí tạo link với chi phí truy vấn dữ liệu và tuần tự hóa response.
- Nhận diện các điểm gây lãng phí khi tạo link cho danh sách tài nguyên.
- Tổ chức assembler và chiến lược tạo link để giữ response dễ bảo trì mà vẫn có hiệu năng tốt.
- Đo đạc trước khi tối ưu và đánh giá tác động của số lượng link lên response.

## 1. Vì sao cần quan tâm đến chi phí tạo link?

Spring HATEOAS giúp response REST mô tả tài nguyên hiện tại và những tài nguyên hoặc hành động mà client có thể tiếp tục truy cập. Chẳng hạn, một đơn hàng có thể chứa link `self`, link đến khách hàng sở hữu đơn hàng và link đến danh sách dòng hàng. Các link này giúp client điều hướng theo hợp đồng hypermedia thay vì tự ghép URL từ quy ước nội bộ của server.

Mỗi link đều cần được xây dựng và đưa vào representation. Với một response chỉ có một tài nguyên và vài link, phần chi phí này thường nhỏ. Nhưng khi API trả về hàng trăm hoặc hàng nghìn phần tử, mỗi phần tử lại có nhiều link, tổng số thao tác tạo link, đối tượng trung gian và dữ liệu JSON có thể tăng đáng kể.

Điều đó không có nghĩa là nên loại bỏ hypermedia. Mục tiêu là hiểu link được tạo ở đâu, chi phí phát sinh từ công đoạn nào và có cách nào tránh làm cùng một việc nhiều lần mà vẫn giữ được khả năng điều hướng của API.

## 2. Các thành phần tạo nên chi phí

Quá trình tạo một link trong ứng dụng Spring HATEOAS thường bao gồm một số công đoạn sau:

1. **Xác định đích đến:** ứng dụng chọn controller hoặc phương thức xử lý tương ứng với tài nguyên hay hành động.
2. **Phân giải mapping:** Spring HATEOAS sử dụng thông tin mapping để xác định đường dẫn, biến đường dẫn và các thành phần URL liên quan.
3. **Tạo URI:** các giá trị tham số được đưa vào URI; query parameter, context path và thông tin request có thể tham gia vào quá trình này.
4. **Tạo đối tượng link:** quan hệ như `self`, `next`, `customer` được gắn với URI để tạo `Link`.
5. **Đưa link vào representation:** link được thêm vào `EntityModel`, `CollectionModel`, `PagedModel` hoặc model tương ứng.
6. **Tuần tự hóa response:** Jackson và cấu hình media type chuyển representation thành JSON, ví dụ HAL JSON.

~~~mermaid
flowchart TD
    A[Entity hoặc DTO] --> B[Chọn đích đến và relation]
    B --> C[Phân giải controller mapping]
    C --> D[Tạo URI]
    D --> E[Tạo Link]
    E --> F[Thêm vào representation]
    F --> G[Tuần tự hóa HAL JSON]
    G --> H[HTTP response]
~~~

Không phải mọi link đều tốn chi phí như nhau. Link có đường dẫn đơn giản thường ít công việc hơn link có nhiều tham số hoặc cần thông tin request. Việc tạo affordance để mô tả thêm phương thức HTTP, input và metadata của hành động cũng có thể cần thêm bước phân tích endpoint và tạo metadata.

### 2.1. `methodOn` và phân giải phương thức

Một cách tạo link quen thuộc là dùng `methodOn` kết hợp với `linkTo`:

~~~java
Link selfLink = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();
~~~

`methodOn` tạo một proxy để ghi nhận lời gọi phương thức controller cùng các đối số. Spring HATEOAS dùng thông tin đó để tìm mapping và xây URI tương ứng. Trong cách sử dụng thông thường này, phương thức controller không được thực thi như một request thật; vì vậy không nên hiểu đoạn mã trên là một lần gọi lại endpoint.

Tuy vậy, việc tạo proxy, ghi nhận lời gọi, phân giải mapping và dựng URI vẫn có chi phí CPU và cấp phát đối tượng. Chi phí này thường không đáng kể ở quy mô nhỏ, nhưng có thể trở nên dễ thấy khi lặp lại trên một tập dữ liệu lớn.

### 2.2. Số lượng link và kích thước response

Giả sử một response có `n` tài nguyên và mỗi tài nguyên tạo `k` link. Số link ở cấp tài nguyên xấp xỉ:

\[
L = n \times k
\]

Nếu response còn có link điều hướng ở cấp collection hoặc page, cần cộng thêm số link đó. Khi `n = 500` và mỗi phần tử có 4 link, riêng các phần tử đã tạo ra khoảng 2.000 link.

Số link tăng kéo theo nhiều đối tượng cần tạo, nhiều trường cần tuần tự hóa và nhiều byte phải truyền qua mạng. Vì vậy, cần phân biệt hai tác động:

- **Chi phí trên server:** CPU và bộ nhớ dùng để tạo `Link`, representation và JSON.
- **Chi phí truyền tải:** kích thước response tăng, có thể làm tăng thời gian truyền và lượng dữ liệu client phải phân tích.

Phân trang giúp giới hạn số tài nguyên trong một response. Đây là một cách kiểm soát quy mô response hiệu quả, đồng thời vẫn giữ các link `first`, `prev`, `self`, `next` và `last` cần thiết cho điều hướng trang.

### 2.3. Chi phí phát sinh từ việc lấy dữ liệu

Bản thân `linkTo` không phải là thao tác truy vấn cơ sở dữ liệu. Tuy nhiên, biểu thức cung cấp đối số cho link có thể truy cập dữ liệu liên quan:

~~~java
Link customerLink = linkTo(
    methodOn(CustomerController.class).one(order.getCustomer().getId())
).withRel("customer");
~~~

Nếu `customer` là quan hệ lazy của ORM, việc gọi `getCustomer()` hoặc truy cập thuộc tính của nó có thể kích hoạt truy vấn. Trong vòng lặp qua nhiều đơn hàng, điều này có nguy cơ tạo ra mẫu truy vấn N+1.

Khi điều tra hiệu năng, hãy tách riêng thời gian lấy dữ liệu khỏi thời gian tạo link. Nếu mỗi link cần một truy vấn bổ sung, tối ưu `linkTo` sẽ không giải quyết được nguyên nhân chính.

## 3. Tạo link cho một tài nguyên

Giả sử API quản lý đơn hàng có endpoint đọc một đơn hàng theo ID. Controller có thể được khai báo như sau:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    EntityModel<Order> one(@PathVariable UUID id) {
        // Tìm đơn hàng và trả về representation.
        // Phần truy vấn được lược bỏ để tập trung vào cách tạo link.
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

Một assembler tạo representation và link `self`:

~~~java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        Link self = linkTo(
            methodOn(OrderController.class).one(order.getId())
        ).withSelfRel();

        return EntityModel.of(order, self);
    }
}
~~~

Assembler tập trung quy tắc chuyển một `Order` thành `EntityModel<Order>`. Controller có thể sử dụng cùng assembler cho endpoint chi tiết và endpoint danh sách. Khi cần thay đổi relation hoặc cách xây URI, nhóm phát triển có một vị trí rõ ràng để cập nhật.

Ví dụ trên dùng một link cho mỗi tài nguyên. Khi cần thêm link đến khách hàng, nên dùng một mã định danh đã có sẵn trong dữ liệu đơn hàng hoặc một projection phù hợp:

~~~java
@Override
public EntityModel<Order> toModel(Order order) {
    Link self = linkTo(
        methodOn(OrderController.class).one(order.getId())
    ).withSelfRel();

    Link customer = linkTo(
        methodOn(CustomerController.class).one(order.getCustomerId())
    ).withRel("customer");

    return EntityModel.of(order, self, customer);
}
~~~

Trong ví dụ này, `getCustomerId()` đại diện cho một thuộc tính ID có sẵn trên `Order`. Nếu mô hình thực tế chỉ có quan hệ ORM, hãy cân nhắc projection, truy vấn join phù hợp hoặc tải trước ID cần thiết. Không nên để assembler vô tình kích hoạt một truy vấn cho từng phần tử.

## 4. Tạo link cho collection mà không lặp công việc

Một endpoint danh sách thường chuyển nhiều entity thành model. Với `RepresentationModelAssembler`, có thể tái sử dụng logic tạo model cho từng phần tử:

~~~java
@GetMapping
CollectionModel<EntityModel<Order>> all() {
    List<Order> orders = orderService.findAll();

    return orderModelAssembler.toCollectionModel(orders);
}
~~~

Khi `toCollectionModel` được gọi, assembler chuyển từng phần tử và tạo các link tương ứng. Nếu mỗi phần tử cần một link `self` và một link `customer`, tổng số link cấp phần tử tăng tuyến tính theo số phần tử.

Một cách triển khai kém hiệu quả là tạo cùng một link nhiều lần trong cùng quá trình xây dựng model:

~~~java
// Ví dụ minh họa cách làm dư thừa.
model.add(linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel());

model.add(linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel());
~~~

Hai biểu thức trên cùng tạo link `self`. Ứng dụng vừa lặp lại công việc, vừa có nguy cơ đưa relation trùng vào model. Hãy tạo link một lần, giữ trong biến và tái sử dụng nếu nhiều bước trong cùng request cần đến nó:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();

model.add(self);
// Các bước tiếp theo có thể dùng lại biến self khi cần.
~~~

Việc tái sử dụng biến trong cùng một lần dựng representation giúp tránh tạo lại cùng một đối tượng link. Không nên biến điều này thành một cache toàn cục nếu URI có thể phụ thuộc vào request.

## 5. Những cách tối ưu có tác dụng thực tế

### 5.1. Giới hạn số tài nguyên trong mỗi response

Nếu endpoint trả về quá nhiều phần tử, hãy xem lại phân trang và kích thước page. Mỗi phần tử thường mang dữ liệu và các link riêng, vì thế giới hạn số phần tử cũng giới hạn số link cần tạo và tuần tự hóa.

Với API dùng Spring Data, có thể tích hợp `PagedResourcesAssembler` để tạo `PagedModel` từ `Page`. Cách này giúp biểu diễn thông tin trang và các link điều hướng theo mô hình phân trang của API. Hãy chọn page size dựa trên dữ liệu thực tế, kích thước response và nhu cầu của client.

### 5.2. Chỉ tạo link có ý nghĩa trong trạng thái hiện tại

Không phải tài nguyên nào cũng hỗ trợ mọi hành động. Một đơn hàng đã giao có thể không còn cho phép hủy; một đơn hàng đã hủy có thể không còn cho phép thanh toán. Chỉ thêm link hành động khi hành động đó thực sự khả dụng theo trạng thái và quyền của người dùng.

Điều này vừa làm response dễ hiểu hơn, vừa tránh tạo các link mà client không thể sử dụng. Quy tắc khả dụng nên được tính từ dữ liệu và chính sách nghiệp vụ đã có, tránh truy vấn riêng cho từng link.

### 5.3. Tránh truy vấn dữ liệu trong assembler

Assembler nên tập trung chuyển đổi dữ liệu đã được chuẩn bị thành representation. Nếu assembler gọi repository hoặc truy cập quan hệ lazy cho từng entity, thời gian xử lý danh sách có thể tăng mạnh.

Hãy đưa nhu cầu dữ liệu vào tầng truy vấn hoặc service: tải trước ID liên quan, dùng projection phù hợp hoặc gom truy vấn theo lô. Sau đó assembler chỉ đọc các giá trị cần thiết và tạo link.

### 5.4. Chọn cách xây link phù hợp với độ phức tạp của endpoint

`linkTo(methodOn(...))` giúp link gắn với mapping của controller, nhờ đó giảm việc lặp lại đường dẫn trong code. Đây thường là lựa chọn dễ bảo trì khi endpoint có path variable hoặc cấu trúc mapping thay đổi.

Với endpoint rất đơn giản, có thể xây từ mapping của controller rồi nối thêm phần đường dẫn:

~~~java
Link self = linkTo(OrderController.class)
    .slash(order.getId())
    .withSelfRel();
~~~

Cách này tránh bước ghi nhận lời gọi phương thức qua `methodOn` trong ví dụ đơn giản, nhưng cũng làm code phụ thuộc trực tiếp hơn vào cách ghép đường dẫn. Nó chỉ phù hợp khi cấu trúc URL thực sự tương ứng với mapping của controller và được kiểm thử khi mapping thay đổi.

Không nên thay toàn bộ `methodOn` chỉ vì giả định cách khác nhanh hơn. Hãy đo trong ứng dụng thực tế; lợi ích CPU nhỏ có thể không đáng để đổi lấy logic URL khó bảo trì.

### 5.5. Cân nhắc affordance

Affordance bổ sung thông tin về hành động có thể thực hiện, chẳng hạn phương thức HTTP và thông tin đầu vào. Chúng hữu ích khi client cần hiểu cách gửi yêu cầu tiếp theo từ hypermedia.

Metadata affordance có thể làm representation lớn hơn và tăng công việc xử lý khi tạo response. Chỉ mô tả những hành động thực sự có ích cho client. Nếu một response có hàng trăm phần tử và mỗi phần tử đều mang nhiều affordance, hãy đo riêng thời gian tạo metadata và kích thước JSON để xác định tác động.

### 5.6. Cẩn trọng với cache link và representation

URI tuyệt đối có thể phụ thuộc vào scheme, host, context path, cấu hình reverse proxy hoặc request hiện tại. Link cũng có thể phụ thuộc vào tenant, người dùng, quyền và trạng thái tài nguyên. Vì vậy, cache một `Link` đã tạo hoặc toàn bộ representation rồi dùng chung cho mọi request có thể trả về URI sai hoặc làm lộ hành động không phù hợp.

Chỉ cache representation khi có thể xác định rõ các yếu tố làm thay đổi nội dung và có chính sách cache tương ứng. Với dữ liệu công khai, ổn định, có thể cân nhắc HTTP cache và ETag. Với dữ liệu phụ thuộc người dùng hoặc request, cần phân vùng cache đúng hoặc không cache representation đó.

## 6. Đo lường trước khi tối ưu

Không nên kết luận rằng tạo link là nút thắt chỉ vì API đang dùng Spring HATEOAS. Trong nhiều hệ thống, truy vấn cơ sở dữ liệu, gọi dịch vụ bên ngoài hoặc tuần tự hóa dữ liệu lớn mới là phần chiếm nhiều thời gian.

Một quy trình đo lường có thể thực hiện như sau:

1. Chọn endpoint có response lớn hoặc có độ trễ cao và ghi nhận kích thước dữ liệu đầu vào, số phần tử, số link cùng kích thước response.
2. Đo thời gian truy vấn dữ liệu, chuyển đổi entity thành model, tạo link và tuần tự hóa nếu ứng dụng có thể tách các giai đoạn này.
3. Dùng Java Flight Recorder hoặc profiler phù hợp để quan sát CPU, allocation và các phương thức xuất hiện nhiều trong thời gian xử lý request.
4. Thử với các quy mô dữ liệu đại diện, chẳng hạn 1, 20, 100 và 500 phần tử, trong môi trường ổn định và có warm-up.
5. Thay đổi một yếu tố mỗi lần, chẳng hạn giảm số link lặp, tải trước ID liên quan hoặc điều chỉnh page size; sau đó so sánh lại.

Các chỉ số nên theo dõi gồm:

| Chỉ số | Điều cần tìm hiểu |
|---|---|
| Thời gian xử lý p50, p95, p99 | Độ trễ điển hình và các request chậm |
| CPU time | Tạo link có tiêu thụ đáng kể CPU không |
| Allocation và GC | Có nhiều đối tượng tạm hoặc áp lực bộ nhớ không |
| Số truy vấn SQL | Việc tạo model có vô tình kích hoạt truy vấn bổ sung không |
| Số link và kích thước JSON | Response có quá nhiều metadata không |
| Thời gian tuần tự hóa | Chi phí nằm ở tạo model hay ghi JSON |

Khi kiểm tra, nên dùng cùng loại dữ liệu, cùng cấu hình, cùng số request và cùng cách khởi động ứng dụng. Một phép đo đơn lẻ không đủ để kết luận; hãy chạy lặp lại và so sánh xu hướng. Nếu thời gian chủ yếu nằm ở truy vấn SQL, hãy xử lý truy vấn trước. Nếu CPU và allocation tập trung ở giai đoạn tạo representation, lúc đó mới xem xét tối ưu link.

## 7. Ví dụ phân tích một response danh sách

Giả sử endpoint trả về 100 đơn hàng. Mỗi đơn hàng có:

- Một link `self` đến chi tiết đơn hàng.
- Một link `customer` đến khách hàng.
- Một link `invoice` nếu hóa đơn đã được phát hành.
- Một link `cancel` nếu trạng thái hiện tại cho phép hủy.

Số link không cố định ở mức 400 vì hai link cuối phụ thuộc trạng thái. Nếu trung bình mỗi đơn hàng có 3 link, response tạo khoảng 300 link cấp phần tử, cộng với các link điều hướng collection hoặc page.

Khi API chậm, hãy lần lượt kiểm tra:

- `customerId` và các dữ liệu liên quan đã được tải theo lô chưa?
- Điều kiện hiển thị `invoice` và `cancel` có gọi repository riêng cho từng đơn hàng không?
- Có link nào đang được tạo lặp cho cùng tài nguyên và relation không?
- Page size có lớn hơn nhu cầu sử dụng thực tế không?
- JSON tăng kích thước do link hay do nội dung entity được embed?

Nếu phát hiện việc lấy trạng thái hóa đơn đang tạo một truy vấn cho mỗi đơn hàng, thay đổi truy vấn service để tải trạng thái theo lô thường có tác dụng lớn hơn việc thay cú pháp `methodOn`. Nếu dữ liệu đã được tải hiệu quả nhưng profiler cho thấy thời gian CPU tập trung ở việc tạo hàng nghìn link, hãy thử giảm link dư thừa hoặc giảm số phần tử mỗi response rồi đo lại.

## 8. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| `methodOn` gọi endpoint thật để lấy URL | `methodOn` ghi nhận lời gọi trên proxy; Spring HATEOAS dùng thông tin đó để phân giải mapping và tạo link. |
| Tạo link luôn là phần chậm nhất của response | Truy vấn dữ liệu, dịch vụ bên ngoài và tuần tự hóa có thể tốn nhiều thời gian hơn. Cần profiler để xác định. |
| Mỗi lần thêm một link chỉ ảnh hưởng một chút | Với collection lớn, số link và kích thước JSON tăng theo số phần tử. |
| Có thể cache mọi link để tăng tốc | URI và hành động có thể phụ thuộc request, người dùng, quyền hoặc trạng thái tài nguyên. |
| Bỏ link sẽ luôn làm API nhanh hơn | Bỏ link có thể làm giảm khả năng điều hướng và tăng việc client phải tự suy luận URL hoặc gọi thêm endpoint. |

## 9. Checklist khi thiết kế response có nhiều link

- [ ] Mỗi link thể hiện một quan hệ hoặc hành động có ích cho client.
- [ ] Link không bị tạo lặp trong cùng một representation.
- [ ] Assembler không phát sinh truy vấn dữ liệu ngoài dự kiến.
- [ ] Các ID cần cho URI đã được tải hiệu quả.
- [ ] Collection lớn có phân trang và page size hợp lý.
- [ ] Link hành động phản ánh đúng trạng thái và quyền hiện tại.
- [ ] Affordance được thêm khi client thực sự cần metadata hành động.
- [ ] Cache tôn trọng host, context path, tenant, người dùng và quyền.
- [ ] Hiệu năng được đo bằng dữ liệu đại diện trước và sau khi thay đổi.

## 10. Bài tập vận dụng

Một endpoint trả về 200 đơn hàng. Mỗi đơn hàng có link `self`, `customer`, `invoice` và `cancel`. API có độ trễ tăng mạnh khi số đơn hàng tăng từ 20 lên 200.

Hãy đề xuất cách điều tra và tối ưu theo thứ tự. Trong câu trả lời, cần phân biệt:

1. Chi phí tạo URI và đối tượng `Link`.
2. Truy vấn dữ liệu phát sinh khi assembler đọc quan hệ liên kết.
3. Chi phí tuần tự hóa và truyền response có nhiều link.
4. Tác động của phân trang và điều kiện hiển thị link theo trạng thái đơn hàng.

Một hướng giải quyết tốt cần chỉ ra phép đo nào sẽ xác nhận nguyên nhân trước khi thay đổi code. Không nên bỏ link `self` hoặc các link điều hướng cần thiết chỉ để làm response nhỏ hơn; hãy xác định link dư thừa, truy vấn lặp hoặc số phần tử vượt nhu cầu thực tế.

## Kết luận

Chi phí tạo link trong Spring HATEOAS đến từ việc phân giải mapping, dựng URI, tạo đối tượng link, xây representation và tuần tự hóa dữ liệu. Với response nhỏ, chi phí này thường không đáng kể; với collection lớn, số link và kích thước JSON có thể tăng nhanh.

Hãy dùng assembler để tập trung quy tắc tạo representation, tránh truy vấn dữ liệu trong vòng lặp, chỉ tạo link có ý nghĩa, phân trang collection và đo riêng từng giai đoạn. Khi có số liệu, bạn mới có thể chọn giữa tối ưu truy vấn, giảm số link dư thừa, điều chỉnh page size hoặc thay đổi cách xây URI mà vẫn giữ được hợp đồng hypermedia rõ ràng.

