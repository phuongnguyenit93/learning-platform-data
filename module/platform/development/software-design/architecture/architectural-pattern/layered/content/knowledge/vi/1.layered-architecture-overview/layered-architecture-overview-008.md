# Chi phí lớp trung gian, ánh xạ dữ liệu và phối hợp thay đổi; điều kiện áp dụng

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Tổng quan kiến trúc phân tầng**. Module hướng tới việc tổ chức phần mềm theo kiến trúc phân tầng: mỗi phần có trách nhiệm rõ ràng, các phần cộng tác qua những ranh giới có chủ đích. Bài này tập trung vào ba hệ quả thực tế khi tạo các ranh giới đó: chi phí của lớp trung gian, công sức ánh xạ dữ liệu và việc phối hợp khi yêu cầu thay đổi.

Một lớp mới có thể làm mã dễ hiểu và dễ thay đổi hơn, nhưng cũng có thể thêm bước chuyển tiếp, thêm mô hình dữ liệu và thêm nơi phải cập nhật. Giá trị của kiến trúc phân tầng phụ thuộc vào việc lợi ích tách biệt trách nhiệm có lớn hơn chi phí ấy hay không.

## 1. Lớp trung gian mang lại giá trị gì?

Trong một ứng dụng Java/Spring điển hình, một yêu cầu có thể đi qua controller, lớp điều phối ca sử dụng, mô hình nghiệp vụ và repository trước khi đọc hoặc ghi dữ liệu. Các phần này có mục đích khác nhau:

- **Presentation** tiếp nhận giao thức bên ngoài, kiểm tra dữ liệu đầu vào ở mức phù hợp với giao thức và định dạng phản hồi.
- **Application** điều phối một ca sử dụng: gọi các thành phần cần thiết, xác định ranh giới giao dịch và phối hợp các bước.
- **Business/domain** biểu diễn quy tắc và trạng thái nghiệp vụ.
- **Data access/infrastructure** chuyển yêu cầu lưu trữ thành thao tác với cơ sở dữ liệu hoặc hệ thống bên ngoài.

Đây là những trách nhiệm logic. Chúng có thể nằm trong cùng một tiến trình và được triển khai thành các package hoặc module khác nhau. Không có yêu cầu rằng mỗi trách nhiệm phải là một ứng dụng hay một dịch vụ chạy riêng.

Một lớp trung gian đáng có khi nó tạo ra một ranh giới hữu ích. Chẳng hạn, application service có thể điều phối việc tạo đơn hàng: kiểm tra quyền thực hiện, tải dữ liệu cần thiết, gọi nghiệp vụ tạo đơn, lưu kết quả và phát sự kiện. Controller không cần biết thứ tự các bước đó; repository không cần quyết định quy trình nghiệp vụ.

Ngược lại, một lớp chỉ chuyển tiếp lời gọi mà không bổ sung chính sách, điều phối, chuyển đổi có ý nghĩa hoặc ranh giới phụ thuộc có thể làm đường đi của chương trình dài hơn mà không tăng khả năng bảo trì. Vì vậy, không nên đánh giá kiến trúc bằng số lượng lớp hay package. Hãy xem mỗi ranh giới có bảo vệ một trách nhiệm hoặc một quyết định có khả năng thay đổi độc lập hay không.

## 2. Các loại chi phí của lớp trung gian

### 2.1. Chi phí khi chương trình chạy

Trong cùng một tiến trình JVM, một lời gọi phương thức qua thêm một lớp thường có chi phí rất nhỏ so với truy vấn cơ sở dữ liệu, gọi mạng hoặc xử lý tệp. Tuy vậy, nhiều tầng có thể tạo ra chi phí cộng dồn:

- Tạo thêm đối tượng trung gian và tăng áp lực lên bộ nhớ, garbage collection.
- Chuyển đổi cùng một dữ liệu nhiều lần giữa các cấu trúc gần như giống nhau.
- Thực hiện truy vấn lặp lại vì trách nhiệm tải dữ liệu bị phân tán hoặc bị che khuất.
- Thêm bước xác thực, chuẩn hóa hoặc tính toán trùng lặp.
- Khó nhận ra thao tác nào thực sự tốn thời gian khi một yêu cầu đi qua quá nhiều điểm chuyển tiếp.

Ví dụ, một yêu cầu xem chi tiết đơn hàng có thể lần lượt gọi controller, facade, manager, service, helper và repository. Nếu các lớp ở giữa chỉ gọi tiếp lớp kế tiếp, chúng không làm giảm truy vấn hay đơn giản hóa quy tắc; chúng chỉ kéo dài luồng điều khiển.

Chi phí thay đổi rõ rệt nếu một ranh giới logic trở thành ranh giới mạng. Gọi một service khác qua HTTP hoặc messaging có thể thêm độ trễ mạng, timeout, lỗi kết nối, retry, xác thực giữa dịch vụ và yêu cầu quan sát phân tán. Đây là hệ quả của việc triển khai thành các tiến trình hoặc dịch vụ riêng, không phải chi phí mặc định của việc chia package trong một ứng dụng phân tầng.

### 2.2. Chi phí trong phát triển và vận hành

Mỗi lớp mới đều có thể làm tăng số nơi cần đọc, sửa và kiểm thử. Một luồng xử lý quá nhiều tầng khiến người bảo trì phải lần theo nhiều tệp để hiểu một hành vi đơn giản. Nếu mỗi tầng còn có interface, implementation, factory và mapper riêng nhưng không có nhu cầu thay thế thực tế, cấu trúc trở nên nặng nề.

Ranh giới giao dịch và xử lý lỗi cũng cần được đặt có chủ đích. Nếu nhiều tầng tự mở giao dịch hoặc tự bắt rồi bọc ngoại lệ, hành vi commit, rollback và thông tin lỗi có thể khó dự đoán. Thông thường, application service là nơi phù hợp để xác định phạm vi giao dịch của một ca sử dụng; repository tập trung vào thao tác lưu trữ và có thể chuyển ngoại lệ kỹ thuật thành kiểu lỗi phù hợp với hợp đồng của tầng gọi.

Một số dấu hiệu lớp trung gian đang tạo chi phí lớn hơn giá trị:

- Một lớp có tên như `Manager` hoặc `Helper` nhưng không có trách nhiệm cụ thể.
- Nhiều phương thức chỉ gọi tiếp một phương thức cùng tham số và cùng kết quả.
- Cùng một quy tắc nghiệp vụ được lặp lại ở controller, service và repository.
- Một thay đổi nhỏ buộc phải sửa hàng loạt lớp có cấu trúc giống nhau.
- Log và trace không cho biết rõ bước nào quyết định kết quả hoặc phát sinh truy vấn.

Cách khắc phục không phải là gộp tất cả vào một lớp. Hãy giữ ranh giới có trách nhiệm rõ ràng, rồi loại bỏ những bước chuyển tiếp không bảo vệ được một quyết định hay hợp đồng nào.

## 3. Ánh xạ dữ liệu giữa các tầng

### 3.1. Vì sao cần nhiều mô hình dữ liệu?

Mỗi ranh giới có thể cần một hình dạng dữ liệu khác nhau:

| Mô hình | Mục đích | Ví dụ |
|---|---|---|
| Request/response DTO | Hợp đồng HTTP, giới hạn dữ liệu được gửi hoặc trả về | `CreateOrderRequest`, `OrderResponse` |
| Command/query của application | Mô tả yêu cầu mà ca sử dụng cần xử lý | `CreateOrderCommand` |
| Domain model | Biểu diễn trạng thái và quy tắc nghiệp vụ | `Order`, `OrderLine` |
| Persistence model/entity | Phù hợp với cách lưu trữ và ánh xạ ORM | `OrderJpaEntity` |

Các mô hình này không bắt buộc phải khác nhau trong mọi ứng dụng. Chúng nên tách ra khi mỗi bên có yêu cầu hoặc vòng đời thay đổi khác nhau.

Ví dụ, API có thể nhận `productId` và `quantity`, trong khi domain model cần một đối tượng dòng đơn hàng đã được kiểm tra số lượng hợp lệ. Entity JPA có thể cần khóa ngoại, cột phiên bản và quan hệ phục vụ lưu trữ. Dùng một đối tượng duy nhất cho cả ba mục đích có thể khiến thay đổi schema làm lộ ra API, hoặc khiến API vô tình cho phép client gán những trường nội bộ như `status`, `totalAmount` hay `createdAt`.

Tách mô hình giúp:

- Giữ hợp đồng API ổn định khi cấu trúc lưu trữ thay đổi.
- Chỉ nhận những trường mà người gọi được phép cung cấp.
- Tránh để annotation hoặc quan hệ ORM chi phối mô hình nghiệp vụ.
- Chuẩn hóa dữ liệu tại ranh giới, chẳng hạn định dạng ngày giờ hoặc mã định danh.
- Biểu diễn rõ dữ liệu đầu vào, dữ liệu đã được kiểm tra và dữ liệu trả về.

### 3.2. Ánh xạ cũng có chi phí

Mỗi lần chuyển đổi có thể cần tạo đối tượng, duyệt collection, xử lý giá trị null, chuyển enum, định dạng thời gian hoặc nạp quan hệ. Khi các mô hình gần như giống hệt nhau, việc duy trì nhiều bản sao có thể tạo ra mã lặp và rủi ro không đồng bộ.

Một lỗi thường gặp là thêm trường vào một mô hình nhưng quên cập nhật mapper ở một ranh giới khác. Kết quả có thể là trường bị mất âm thầm, nhận giá trị mặc định sai hoặc không xuất hiện trong phản hồi. Các trường có ngữ nghĩa đặc biệt cần được chú ý:

- **Null và trường bị bỏ qua:** trong API cập nhật một phần, không gửi trường có thể mang nghĩa “giữ nguyên”, còn gửi `null` có thể mang nghĩa “xóa giá trị”. Một phép ánh xạ đơn giản có thể làm mất khác biệt này.
- **Tiền và số lượng:** cần giữ đúng độ chính xác, đơn vị và quy tắc làm tròn; không tùy tiện chuyển tiền sang `double`.
- **Thời gian:** cần thống nhất múi giờ và ý nghĩa của thời điểm so với ngày lịch.
- **Enum và trạng thái:** tên hoặc giá trị lưu trữ không nhất thiết trùng với mã công khai của API.
- **Quan hệ ORM:** việc đọc thuộc tính lazy khi ánh xạ có thể kích hoạt truy vấn bổ sung, thậm chí tạo ra vấn đề N+1 nếu lặp qua nhiều entity.

Ánh xạ vì thế không chỉ là thao tác sao chép thuộc tính. Nó là nơi chuyển đổi giữa hai hợp đồng và cần được thiết kế, kiểm thử theo ngữ nghĩa của dữ liệu.

### 3.3. Ví dụ ánh xạ ở ranh giới

Giả sử API nhận yêu cầu tạo đơn hàng. Controller chuyển request DTO thành command mà ca sử dụng hiểu được. Application service gọi nghiệp vụ và trả kết quả dưới dạng response DTO:

```java
public record CreateOrderLineRequest(
        String productId,
        int quantity
) {}

public record CreateOrderRequest(
        List<CreateOrderLineRequest> lines
) {}

public record CreateOrderLine(
        ProductId productId,
        int quantity
) {}

public record CreateOrderCommand(
        List<CreateOrderLine> lines
) {}

@RestController
@RequestMapping("/orders")
class OrderController {
    private final CreateOrderUseCase createOrder;
    private final OrderHttpMapper mapper;

    OrderController(CreateOrderUseCase createOrder, OrderHttpMapper mapper) {
        this.createOrder = createOrder;
        this.mapper = mapper;
    }

    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        Order order = createOrder.handle(mapper.toCommand(request));
        return mapper.toResponse(order);
    }
}
```

Mapper có thể được viết thủ công hoặc sinh mã bằng một thư viện như MapStruct. Dù dùng cách nào, quy tắc chuyển đổi vẫn cần được xem xét: số lượng phải dương, mã sản phẩm phải được chuyển thành kiểu định danh phù hợp, và phản hồi chỉ nên chứa các trường được phép công khai. Kiểm tra cú pháp và cấu trúc đầu vào có thể đặt ở biên HTTP; quy tắc như “đơn hàng phải có ít nhất một dòng” hoặc “số lượng phải hợp lệ theo nghiệp vụ” cần được bảo vệ ở application/domain để không phụ thuộc vào một giao thức cụ thể.

Ở biên lưu trữ, adapter có thể chuyển domain model thành entity JPA và chuyển kết quả đã lưu trở lại mô hình mà tầng nghiệp vụ sử dụng:

```java
@Repository
class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderRepository jpaRepository;
    private final OrderPersistenceMapper mapper;

    JpaOrderRepository(
            SpringDataOrderRepository jpaRepository,
            OrderPersistenceMapper mapper
    ) {
        this.jpaRepository = jpaRepository;
        this.mapper = mapper;
    }

    @Override
    public Order save(Order order) {
        OrderJpaEntity entity = mapper.toEntity(order);
        OrderJpaEntity saved = jpaRepository.save(entity);
        return mapper.toDomain(saved);
    }
}
```

Ví dụ này minh họa một lựa chọn kiến trúc, không phải quy tắc bắt buộc cho mọi dự án. Với ứng dụng CRUD nhỏ, ít quy tắc và ít khả năng thay đổi độc lập, dùng entity làm mô hình nội bộ có thể hợp lý. Khi domain có hành vi riêng, nhiều nguồn dữ liệu hoặc API cần ổn định qua các lần đổi schema, việc tách mô hình thường đem lại lợi ích rõ hơn.

### 3.4. Chọn chiến lược ánh xạ

Có ba cách thường gặp:

1. **Ánh xạ thủ công:** dễ thấy quy tắc và thuận tiện khi chuyển đổi có điều kiện hoặc xử lý ngữ nghĩa phức tạp. Nhược điểm là có thể lặp mã khi số trường lớn.
2. **Thư viện sinh mapper:** giảm mã sao chép và phát hiện một số sai lệch lúc biên dịch. Cần cấu hình rõ các trường đặc biệt, tránh để mapper tự động che giấu chuyển đổi quan trọng.
3. **Dùng chung một mô hình:** giảm số lần chuyển đổi và số kiểu dữ liệu. Cách này phù hợp khi các ranh giới thực sự có cùng ngữ nghĩa và cùng vòng đời; nó làm tăng liên kết nếu các bên cần thay đổi độc lập.

Hãy đặt mapper tại ranh giới mà nó chuyển đổi. Mapper HTTP không nên quyết định cách entity được lưu; mapper persistence không nên chứa quy tắc giá bán hay quyền đặt hàng. Cách đặt này giúp mỗi chuyển đổi có một chủ sở hữu rõ ràng.

## 4. Phối hợp thay đổi qua nhiều tầng

Một yêu cầu mới thường chạm đến nhiều phần, nhưng không phải yêu cầu nào cũng cần sửa tất cả các tầng. Phạm vi thay đổi phụ thuộc vào nơi có quyết định bị ảnh hưởng.

### 4.1. Xác định loại thay đổi

Giả sử sản phẩm cần bổ sung hướng dẫn giao hàng cho đơn hàng. Có thể có các tình huống khác nhau:

- Nếu chỉ cần hiển thị thêm trường trong response, thay đổi có thể chủ yếu nằm ở hợp đồng API và mapper phản hồi.
- Nếu người dùng được nhập hướng dẫn khi tạo đơn, request DTO, command và quy trình application có thể cần cập nhật.
- Nếu hướng dẫn phải được lưu lâu dài, persistence model và schema cơ sở dữ liệu cũng cần thay đổi.
- Nếu hướng dẫn có giới hạn hoặc quy tắc nghiệp vụ, domain model cần bảo vệ các bất biến đó.

Không nên tự động thêm cùng một trường vào mọi lớp chỉ vì các lớp có tên tương ứng. Hãy lần theo dữ liệu và xác định nơi cần biết thông tin đó. Một tầng chỉ nên nhận thay đổi khi trách nhiệm hoặc hợp đồng của nó thực sự bị tác động.

### 4.2. Giữ hợp đồng ổn định và quản lý phụ thuộc

Phối hợp thay đổi dễ hơn khi mỗi tầng phụ thuộc vào hợp đồng phù hợp với trách nhiệm của nó. Presentation có thể phụ thuộc vào use case hoặc application contract; application gọi các abstraction cần thiết; adapter lưu trữ triển khai hợp đồng repository. Khi schema thay đổi nhưng hợp đồng repository và domain không đổi, thay đổi có thể được giới hạn trong adapter và migration.

Ngược lại, nếu controller trực tiếp phụ thuộc entity JPA, một thay đổi quan hệ hoặc tên cột có thể lan ra API. Nếu domain phụ thuộc repository cụ thể của Spring Data, việc đổi công nghệ lưu trữ sẽ tác động tới nghiệp vụ. Mục tiêu của ranh giới là hạn chế phạm vi lan truyền như vậy.

Với API được nhiều client sử dụng, cần cân nhắc tương thích ngược. Thêm trường tùy chọn thường ít rủi ro hơn đổi tên hoặc đổi ý nghĩa trường hiện có. Thay đổi phá vỡ hợp đồng có thể cần phiên bản API, giai đoạn chuyển tiếp hoặc kế hoạch cập nhật client. Với schema, migration cần được sắp xếp theo thứ tự triển khai an toàn, đặc biệt khi ứng dụng cũ và mới có thể cùng chạy trong một khoảng thời gian.

### 4.3. Phối hợp giữa người và nhóm

Khi nhiều người làm việc trên các tầng khác nhau, hợp đồng rõ ràng giúp giảm xung đột. Nhóm phụ trách API cần thống nhất cấu trúc request/response; nhóm nghiệp vụ cần thống nhất ý nghĩa của command và quy tắc; nhóm dữ liệu cần thống nhất migration và cách lưu. Những quyết định này nên được thể hiện bằng kiểu dữ liệu, tài liệu hợp đồng, ví dụ và kiểm thử, thay vì chỉ trao đổi miệng.

Không cần tạo quy trình phê duyệt nặng cho mọi thay đổi nhỏ. Mức phối hợp nên tương xứng với phạm vi ảnh hưởng: một mapper nội bộ có thể do một người cập nhật; thay đổi API công khai hoặc schema dùng chung cần thông báo và phối hợp triển khai.

## 5. Kiểm thử để kiểm soát chi phí thay đổi

Kiến trúc phân tầng chỉ có ích khi ranh giới giúp kiểm tra hành vi dễ hơn. Nên đặt kiểm thử ở nơi có thể phát hiện sai lệch với chi phí hợp lý:

- **Unit test cho domain:** kiểm tra bất biến và quy tắc nghiệp vụ mà không cần khởi động Spring hoặc kết nối cơ sở dữ liệu.
- **Unit test cho application service:** kiểm tra thứ tự điều phối, kết quả và cách xử lý các tình huống như không tìm thấy dữ liệu hoặc không đủ điều kiện thực hiện.
- **Test cho mapper:** cần thiết khi có logic chuyển đổi, trường tùy chọn, enum, tiền, thời gian hoặc cấu trúc lồng nhau. Mapper chỉ sao chép trường đơn giản có thể được kiểm tra cùng với test hợp đồng thay vì tạo một bộ test trùng lặp.
- **Integration test cho adapter/repository:** xác minh truy vấn, ánh xạ ORM, transaction và migration trên cơ sở dữ liệu phù hợp.
- **Contract hoặc web-layer test:** xác minh request/response, mã trạng thái, validation và tính tương thích của API.

Ví dụ, unit test cho mapper nên kiểm tra trường hợp có ý nghĩa chứ không chỉ xác nhận rằng phương thức trả về một đối tượng:

```java
@Test
void mapsEachRequestedLineToApplicationCommand() {
    var request = new CreateOrderRequest(List.of(
            new CreateOrderLineRequest("P-100", 2),
            new CreateOrderLineRequest("P-200", 1)
    ));

    var command = mapper.toCommand(request);

    assertEquals(2, command.lines().size());
    assertEquals(new ProductId("P-100"), command.lines().get(0).productId());
    assertEquals(2, command.lines().get(0).quantity());
}
```

Test này hữu ích nếu mapper có thể làm mất dòng, đổi nhầm mã hoặc sai số lượng. Nếu việc ánh xạ chỉ là phép gán hiển nhiên, giá trị của một test riêng có thể thấp; hãy ưu tiên kiểm tra hành vi ở ranh giới công khai và các quy tắc có rủi ro cao.

Khi một thay đổi phải đi qua nhiều tầng, test ở các ranh giới giúp xác định lỗi nằm ở chuyển đổi, điều phối, nghiệp vụ hay lưu trữ. Tránh chỉ viết test kiểm tra từng lời gọi getter/setter; những test đó thường khóa chặt cách cài đặt mà không bảo vệ hành vi quan trọng.

## 6. Khi nào nên chấp nhận thêm lớp và mô hình?

Việc tách lớp và ánh xạ thường đáng giá khi có một hoặc nhiều điều kiện sau:

- Các phần có lý do thay đổi khác nhau, ví dụ API thay đổi thường xuyên trong khi quy tắc nghiệp vụ cần ổn định.
- Nhiều giao diện cùng sử dụng một ca sử dụng, chẳng hạn REST API, tác vụ nền và giao diện quản trị.
- Nghiệp vụ có quy tắc hoặc trạng thái đủ phức tạp để cần mô hình riêng.
- Cấu trúc lưu trữ có khả năng thay đổi hoặc cần được cô lập khỏi phần còn lại.
- Nhiều nhóm cùng phát triển và cần hợp đồng rõ để làm việc độc lập.
- Có yêu cầu bảo mật khiến dữ liệu công khai phải được kiểm soát khác với dữ liệu nội bộ.

Giữ cấu trúc đơn giản có thể phù hợp hơn khi ứng dụng nhỏ, chủ yếu CRUD, ít quy tắc, chỉ có một giao diện và các mô hình dữ liệu có cùng vòng đời. Trong trường hợp đó, controller, service và repository có thể đã đủ; không cần tạo thêm interface, command, domain object và mapper cho mọi thao tác nếu chúng chỉ lặp lại cùng một cấu trúc.

Có thể dùng các câu hỏi sau khi quyết định thêm một lớp hoặc mô hình:

1. Lớp này sở hữu quyết định, quy tắc hoặc hợp đồng nào?
2. Nếu bỏ lớp này, trách nhiệm nào sẽ bị trộn lẫn hoặc phụ thuộc sai hướng?
3. Mô hình dữ liệu mới có ngữ nghĩa hoặc vòng đời khác mô hình hiện có không?
4. Chi phí ánh xạ và kiểm thử có được bù lại bằng khả năng cô lập thay đổi không?
5. Có bằng chứng về nhu cầu thay thế, tái sử dụng hoặc phối hợp độc lập hay chỉ đang tạo cấu trúc dự phòng?

Nếu chưa có lợi ích cụ thể, hãy bắt đầu với cấu trúc nhỏ và tách thêm khi trách nhiệm hoặc áp lực thay đổi xuất hiện. Nếu đã có ranh giới rõ, đừng gộp chúng chỉ để giảm số tệp.

## 7. Ghi nhớ

- Mỗi lớp trung gian cần có trách nhiệm hoặc hợp đồng đủ rõ để biện minh cho chi phí đọc, gọi và bảo trì.
- Lời gọi giữa các lớp trong cùng JVM thường rẻ; truy vấn lặp, tạo đối tượng không cần thiết và ranh giới mạng mới là những nguồn chi phí cần đo lường kỹ.
- DTO, command, domain model và entity có thể khác nhau vì phục vụ các hợp đồng khác nhau. Không bắt buộc phải tạo đủ tất cả cho mọi ứng dụng.
- Ánh xạ là chuyển đổi ngữ nghĩa, cần chú ý null, tiền, thời gian, enum và quan hệ ORM.
- Khi yêu cầu thay đổi, chỉ cập nhật những tầng có trách nhiệm hoặc hợp đồng bị ảnh hưởng; giữ phụ thuộc qua các hợp đồng ổn định để giới hạn phạm vi lan truyền.
- Chọn mức phân tầng theo độ phức tạp nghiệp vụ, số giao diện, vòng đời dữ liệu, quy mô phối hợp và chi phí vận hành thực tế.

