# Tái cấu trúc từng phần, ghi rõ ngoại lệ kiến trúc và đường chuyển tiếp

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Cải tiến hệ thống hiện có**. Module hướng tới cách tổ chức phần mềm theo kiến trúc phân tầng, với presentation tiếp nhận giao tiếp bên ngoài, application điều phối ca sử dụng, business/domain bảo vệ quy tắc và data access/infrastructure làm việc với cơ sở dữ liệu hoặc hệ thống khác. Trong một hệ thống đã vận hành lâu năm, các trách nhiệm này thường chưa được tách rõ hoặc đã bị trộn lẫn qua nhiều lần bổ sung tính năng.

Tái cấu trúc hệ thống hiện có cần một đường chuyển tiếp có thể kiểm soát. Không phải lúc nào cũng có thể dừng phát triển để viết lại toàn bộ ứng dụng. Thay vào đó, nhóm có thể cải tiến từng phần, duy trì khả năng phát hành và ghi nhận rõ các ngoại lệ kiến trúc còn tồn tại. Mỗi bước cần có mục tiêu, bằng chứng kiểm tra và điều kiện để tiếp tục hoặc quay lui.

## 1. Vì sao cần tái cấu trúc từng phần?

Một ứng dụng lâu năm có thể chứa controller truy vấn database trực tiếp, service vừa điều phối vừa tính quy tắc, entity JPA được trả thẳng ra API, hoặc nhiều module cùng phụ thuộc vào một package dùng chung. Những cấu trúc này có thể đã hoạt động và đang phục vụ người dùng; thay đổi lớn cùng lúc dễ tạo ra rủi ro mới.

Tái cấu trúc từng phần phù hợp khi:

- Hệ thống vẫn cần phát hành tính năng trong lúc cải tiến.
- Có những khu vực rủi ro cao cần được bảo vệ trước.
- Chưa hiểu đầy đủ mọi hành vi của hệ thống cũ.
- Dữ liệu và tích hợp bên ngoài không thể chuyển đổi trong một lần.
- Nhiều nhóm cùng sở hữu các phần khác nhau.
- Cần giữ tương thích với API, message hoặc quy trình đang được sử dụng.

Mục tiêu của mỗi bước không nhất thiết là đạt kiến trúc đích ngay lập tức. Có thể bắt đầu bằng việc tạo một ranh giới cho một ca sử dụng, cô lập truy cập dữ liệu hoặc bảo vệ một quy tắc đang bị lặp. Sau đó, nhóm tiếp tục chuyển các luồng liên quan khi có đủ hiểu biết và kiểm thử.

Tái cấu trúc (refactoring) theo nghĩa chặt chẽ là thay đổi cấu trúc bên trong mà giữ nguyên hành vi quan sát được. Một thay đổi đồng thời đổi quy tắc nghiệp vụ hoặc hợp đồng API là một thay đổi chức năng/thiết kế rộng hơn; nó vẫn có thể cần thiết, nhưng phải được đánh giá và phát hành như một thay đổi có tác động tới người dùng.

## 2. Đánh giá hiện trạng trước khi chọn điểm bắt đầu

Không nên chọn điểm refactor chỉ vì package có tên chưa đẹp. Hãy hiểu luồng thực tế, người sử dụng và hậu quả nếu thay đổi sai.

### 2.1. Lập bản đồ một luồng nghiệp vụ

Ví dụ luồng xem đơn hàng có thể đang đi theo đường:

```text
HTTP Controller
   |
   +--> JPA Repository
   |
   +--> Tự tính tổng và kiểm tra trạng thái
   |
   +--> Trả trực tiếp OrderEntity thành JSON
   |
   v
Database
```

Luồng này có thể đang trộn nhiều trách nhiệm:

- Controller biết cấu trúc lưu trữ và truy vấn.
- Quy tắc tính tổng nằm ngoài mô hình nghiệp vụ.
- API phụ thuộc vào entity và quan hệ ORM.
- Khó gọi cùng hành vi từ tác vụ nền hoặc message consumer.
- Kiểm thử controller có thể cần database thật chỉ để xác minh một quy tắc đơn giản.

Trước khi sửa, ghi nhận luồng gọi, dữ liệu đầu vào/đầu ra, các side effect, transaction và hệ thống phụ thuộc. Có thể dùng trace, log, test hiện có và trao đổi với người vận hành để xác định những hành vi mà mã nguồn chưa thể hiện đầy đủ.

### 2.2. Xác định rủi ro và giá trị

Có thể đánh giá từng khu vực theo các tiêu chí:

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Tác động nghiệp vụ | Nếu lỗi, có ảnh hưởng tiền, dữ liệu, quyền hoặc hoạt động cốt lõi không? |
| Tần suất thay đổi | Khu vực này có thường xuyên nhận yêu cầu mới không? |
| Mức độ phụ thuộc | Có bao nhiêu module, API hoặc nhóm đang sử dụng nó? |
| Khả năng kiểm thử | Có test đủ để nhận ra hành vi bị thay đổi không? |
| Khả năng cô lập | Có thể tạo adapter hoặc facade để chuyển đổi từng bước không? |
| Chi phí chuyển đổi | Cần migration dữ liệu, thay API hoặc phối hợp nhiều nhóm không? |

Một khu vực thay đổi thường xuyên, có nhiều lỗi và có thể cô lập tốt thường là ứng viên phù hợp. Một module ít thay đổi nhưng có dữ liệu quan trọng và thiếu kiểm thử có thể cần được bảo vệ bằng characterization test trước khi refactor.

Không cần chấm điểm chính xác cho mọi tiêu chí. Mục đích là làm rõ lý do chọn điểm bắt đầu và tránh thay đổi một khu vực chỉ vì nó dễ đổi tên.

## 3. Tạo đường chuyển tiếp bằng ranh giới nhỏ

Một cách cải tiến thường dùng là đặt một ranh giới mới trước phần cũ, rồi chuyển dần trách nhiệm qua ranh giới đó. Ranh giới có thể là application service, interface, facade, adapter hoặc module API tùy vấn đề cần giải quyết.

Ví dụ ban đầu, controller gọi trực tiếp repository và tự tính tổng:

```java
@RestController
@RequestMapping("/orders")
class LegacyOrderController {
    private final SpringDataOrderRepository repository;

    LegacyOrderController(SpringDataOrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    OrderResponse get(@PathVariable UUID id) {
        OrderJpaEntity entity = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));

        BigDecimal total = entity.getLines().stream()
                .map(line -> line.getUnitPrice()
                        .multiply(BigDecimal.valueOf(line.getQuantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new OrderResponse(entity.getId(), total);
    }
}
```

Một bước chuyển tiếp có thể đưa việc đọc và tính toán vào một application service, đồng thời giữ nguyên endpoint và response:

```java
@Service
class GetOrderService {
    private final OrderRepository orders;

    GetOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderSummary get(OrderId id) {
        Order order = orders.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        return new OrderSummary(order.id(), order.total());
    }
}
```

Controller sau chuyển đổi chỉ còn chuyển đổi HTTP và gọi ca sử dụng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final GetOrderService getOrder;

    OrderController(GetOrderService getOrder) {
        this.getOrder = getOrder;
    }

    @GetMapping("/{id}")
    OrderResponse get(@PathVariable UUID id) {
        OrderSummary summary = getOrder.get(new OrderId(id));
        return new OrderResponse(summary.id().value(), summary.total());
    }
}
```

Ví dụ minh họa cấu trúc chuyển tiếp; kiểu `OrderRepository` và `Order` có thể được đưa vào dần. Ở bước đầu, repository adapter vẫn có thể dùng entity cũ bên trong. Sau khi có test và ranh giới ổn định, nhóm mới cân nhắc tách persistence entity khỏi domain model nếu lợi ích đủ lớn.

Điểm quan trọng là hợp đồng HTTP không cần thay đổi trong cùng lần refactor. Có thể thay đổi cách tổ chức nội bộ trước, giữ đường dẫn, status code và response để giảm số bên bị ảnh hưởng.

## 4. Chọn kỹ thuật chuyển đổi phù hợp

Không có một kỹ thuật duy nhất cho mọi hệ thống. Hãy chọn cách tạo đường chuyển tiếp phù hợp với kiểu phụ thuộc đang tồn tại.

### 4.1. Facade hoặc application service

Facade cung cấp một điểm vào ổn định cho một nhóm thao tác cũ. Application service diễn đạt một ca sử dụng và điều phối các bước cần thiết. Có thể đặt một lớp mới trước subsystem cũ để caller mới không phải biết cấu trúc nội bộ.

Kỹ thuật này hữu ích khi nhiều controller hoặc module đang gọi trực tiếp nhiều thành phần cũ. Thay vì sửa tất cả caller cùng lúc, có thể chuyển từng caller sang facade rồi dần thu hẹp API cũ.

Không nên để facade trở thành một lớp chuyển tiếp vĩnh viễn chứa mọi logic. Khi trách nhiệm được chuyển xong, facade nên được giữ như hợp đồng có ý nghĩa hoặc được loại bỏ nếu không còn giá trị.

### 4.2. Adapter

Adapter chuyển đổi giữa hợp đồng mới và API cũ. Ví dụ, application service cần `OrderRepository`, còn hệ thống hiện có chỉ cung cấp `LegacyOrderDao`. Một adapter có thể triển khai hợp đồng mới bằng cách gọi DAO cũ và chuyển đổi dữ liệu.

```java
class LegacyOrderRepositoryAdapter implements OrderRepository {
    private final LegacyOrderDao legacyDao;
    private final LegacyOrderMapper mapper;

    LegacyOrderRepositoryAdapter(
            LegacyOrderDao legacyDao,
            LegacyOrderMapper mapper) {
        this.legacyDao = legacyDao;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return legacyDao.find(id.value())
                .map(mapper::toDomain);
    }
}
```

Adapter cho phép phía mới phụ thuộc vào hợp đồng mà nó cần, trong khi chi tiết cũ được cô lập. Khi thay DAO cũ bằng implementation mới, application không nhất thiết phải thay đổi.

### 4.3. Strangler pattern

Strangler pattern chuyển dần chức năng từ hệ thống cũ sang hệ thống mới. Một routing layer, gateway hoặc facade quyết định yêu cầu nào đi vào luồng cũ và yêu cầu nào đi vào luồng mới.

Ví dụ:

```text
Client
  |
  v
API Gateway / Routing Facade
  |
  +----> Luồng cũ: các chức năng chưa chuyển
  |
  +----> Luồng mới: ca sử dụng đã được thay thế
                  |
                  v
             Application
                  |
             Domain / Ports
                  |
             Adapters
```

Cách này phù hợp khi có thể tách chức năng theo endpoint, use case, tenant hoặc nhóm người dùng. Cần có tiêu chí rõ để chọn tuyến, theo dõi lưu lượng và biết khi nào luồng cũ có thể ngừng hoạt động.

Không nên định tuyến ngẫu nhiên hai phiên bản cho thao tác ghi nếu chúng cùng cập nhật một dữ liệu mà không có cơ chế nhất quán. Việc chạy song song để so sánh kết quả cần được giới hạn ở luồng đọc hoặc môi trường có thể kiểm soát side effect.

### 4.4. Branch by abstraction

Khi nhiều caller đang phụ thuộc trực tiếp vào một implementation, có thể tạo abstraction ở giữa trước, rồi chuyển caller sang abstraction từng bước. Sau đó thay implementation cũ bằng implementation mới phía sau abstraction.

Ví dụ, nhiều lớp đang gọi trực tiếp `LegacyPricingClient`. Nhóm tạo interface `PricingGateway`, viết adapter dùng client cũ, chuyển caller sang interface, rồi thay adapter bằng client mới khi đã kiểm chứng.

Kỹ thuật này giảm số thay đổi đồng thời và giúp có thể chuyển implementation mà không phải sửa toàn bộ caller một lần. Tuy nhiên, abstraction cần thể hiện hợp đồng thực sự ổn định; không nên tạo interface chỉ để có thêm một tầng tên gọi.

## 5. Ghi rõ ngoại lệ kiến trúc

Trong giai đoạn chuyển tiếp, có thể tồn tại những trường hợp chưa tuân theo kiến trúc mục tiêu. Ví dụ:

- Một controller cũ vẫn truy vấn repository trực tiếp.
- Một module mới tạm thời gọi adapter cũ vì chưa chuyển xong dữ liệu.
- Một module dùng chung vẫn được nhiều khu vực phụ thuộc trong khi nhóm đang tách API.
- Một luồng legacy cần giữ entity JPA để tương thích với schema hoặc batch job hiện tại.

Ngoại lệ không nhất thiết là lỗi cần sửa ngay. Vấn đề xuất hiện khi ngoại lệ không được nhìn thấy, không có người chịu trách nhiệm hoặc không có điều kiện kết thúc. Khi đó, “tạm thời” dễ trở thành cấu trúc mặc định.

### 5.1. Nội dung cần có trong một ngoại lệ

Một mục ghi nhận ngoại lệ nên có các thông tin:

| Trường | Nội dung |
|---|---|
| ID | Mã tham chiếu duy nhất hoặc liên kết tới issue/ADR |
| Phạm vi | Module, package, class hoặc dependency cụ thể |
| Quy tắc bị ngoại lệ | Quy tắc kiến trúc nào đang chưa được tuân thủ |
| Lý do | Ràng buộc kỹ thuật, tương thích hoặc ưu tiên nghiệp vụ |
| Rủi ro | Tác động có thể xảy ra và phạm vi ảnh hưởng |
| Biện pháp kiểm soát | Test, adapter, logging, quyền truy cập hoặc giới hạn sử dụng |
| Người/nhóm sở hữu | Ai chịu trách nhiệm theo dõi |
| Điều kiện kết thúc | Việc gì phải hoàn tất để bỏ ngoại lệ |
| Thời điểm xem xét | Ngày hoặc mốc phát hành cần đánh giá lại |

Ví dụ:

```text
ID: ARCH-EX-014
Phạm vi: legacy-order.web.OrderController
Quy tắc: Presentation không truy cập Spring Data repository trực tiếp
Lý do: Endpoint đang phục vụ client cũ; chưa có contract test đủ tin cậy
Rủi ro: Controller phụ thuộc schema và có thể kích hoạt truy vấn ngoài ý muốn
Kiểm soát: Giữ response hiện tại; thêm characterization test cho endpoint
Sở hữu: Nhóm Order
Điều kiện kết thúc: Endpoint gọi GetOrderUseCase và repository chỉ được truy cập qua adapter
Xem xét lại: Khi hoàn thành migration luồng đọc Order
```

Đây là ví dụ minh họa. Mốc xem xét nên gắn với một sự kiện có thể xác minh, không chỉ ghi “sẽ xử lý sau”.

### 5.2. Ngoại lệ cần hẹp và có giới hạn

Một ngoại lệ tốt chỉ mở ra phạm vi cần thiết. Ví dụ cho phép một controller cụ thể truy cập một repository trong giai đoạn chuyển đổi rõ ràng sẽ dễ quản lý hơn việc cho phép toàn bộ package web truy cập mọi persistence package.

Không nên dùng ngoại lệ để bỏ qua toàn bộ quy tắc kiến trúc. Nếu có nhiều trường hợp giống nhau, hãy xem xét cập nhật kiến trúc mục tiêu hoặc tạo một adapter/hợp đồng chính thức. Có thể kiến trúc ban đầu không phù hợp với thực tế và cần được điều chỉnh có chủ đích.

### 5.3. Ngoại lệ có thời hạn và điều kiện loại bỏ

Mỗi ngoại lệ nên có người sở hữu và mốc xem xét. Mốc có thể là ngày cụ thể, release hoặc điều kiện như “sau khi tất cả caller chuyển sang interface mới”. Khi tới mốc, nhóm phải quyết định một trong ba việc:

- Loại bỏ ngoại lệ vì phần chuyển đổi đã hoàn tất.
- Gia hạn với lý do và biện pháp kiểm soát được cập nhật.
- Chấp nhận ngoại lệ như một quyết định kiến trúc dài hạn và sửa lại quy tắc tương ứng.

Không nên để ngoại lệ hết hạn tự động làm build hỏng nếu nhóm chưa có quy trình xử lý phù hợp; nhưng cũng không nên bỏ qua cảnh báo hết hạn mãi mãi. Công cụ kiểm tra có thể báo cáo các ngoại lệ quá hạn để đưa vào review.

## 6. Biến ngoại lệ thành quy tắc kiểm tra được

Tài liệu ngoại lệ giúp con người hiểu lý do; architecture test giúp ngăn phạm vi ngoại lệ lan rộng.

Ví dụ với ArchUnit, có thể cấm package web truy cập persistence, nhưng tạm cho phép một class cụ thể:

```java
@AnalyzeClasses(packages = "com.example")
class LayerRulesTest {
    @ArchTest
    static final ArchRule webMustNotDependOnPersistence =
            noClasses()
                .that().resideInAPackage("..web..")
                .and().doNotHaveFullyQualifiedName(
                        "com.example.legacy.web.LegacyOrderController")
                .should().dependOnClassesThat()
                .resideInAPackage("..persistence..");
}
```

Ví dụ chỉ minh họa cách thu hẹp một ngoại lệ trong test. Tên package phải điều chỉnh theo dự án. Cần liên kết ngoại lệ trong code review hoặc ADR để người đọc hiểu vì sao class được miễn trừ và điều kiện loại bỏ là gì.

Khi chuyển đổi hoàn tất, xóa ngoại lệ khỏi test cùng với việc loại bỏ dependency cũ. Nếu chỉ xóa annotation hoặc sửa test mà chưa loại bỏ đường phụ thuộc, nhóm có thể mất cơ chế bảo vệ mà không đạt được kiến trúc mục tiêu.

Một lựa chọn khác là giữ allowlist ngoại lệ trong một test hoặc cấu hình tập trung. Cách này giúp báo cáo phạm vi và thời điểm xem xét, nhưng không nên biến allowlist thành một danh sách dài không có người sở hữu. Mỗi entry cần có liên kết tới quyết định và trạng thái hiện tại.

## 7. Lập đường chuyển tiếp theo các bước nhỏ

Một kế hoạch refactor hữu ích mô tả trạng thái hiện tại, trạng thái đích và các trạng thái trung gian có thể triển khai an toàn.

Ví dụ chuyển một luồng đọc đơn hàng:

| Giai đoạn | Trạng thái | Bằng chứng cần có |
|---|---|---|
| 0. Hiện trạng | Controller truy vấn JPA và tự ánh xạ response | Ghi nhận hành vi, response mẫu, query và test hiện có |
| 1. Bảo vệ hành vi | Thêm characterization test cho endpoint | Test xác nhận status, body và trường hợp lỗi |
| 2. Tạo ranh giới | Controller gọi application use case; use case dùng adapter cũ | Web test và application test chạy ổn định |
| 3. Cô lập lưu trữ | Adapter chuyển entity thành read model/domain view | Repository integration test và mapper test |
| 4. Thu hẹp ngoại lệ | Xóa quyền truy cập persistence trực tiếp từ controller | Architecture test không còn allowlist cho class đó |
| 5. Dọn cấu trúc | Xóa DAO hoặc đường gọi cũ không còn dùng | Build, test và quan sát runtime xác nhận không còn caller |

Mỗi giai đoạn nên có thể review và phát hành độc lập khi phù hợp. Nếu một bước quá lớn, hãy chia tiếp theo endpoint, use case hoặc nhóm dữ liệu. Không cần di chuyển mọi class trong một pull request chỉ để đạt sơ đồ package cuối cùng.

### 7.1. Characterization test trước khi đổi cấu trúc

Hệ thống cũ có thể có hành vi chưa được ghi trong tài liệu, kể cả hành vi kỳ lạ mà client đang phụ thuộc. Characterization test ghi lại những gì hệ thống thực sự làm trước khi thay đổi.

Test này có thể lưu response mẫu, status code, thứ tự side effect hoặc kết quả truy vấn ở những tình huống quan trọng. Không phải mọi hành vi hiện tại đều là hành vi mong muốn; nhưng cần phân biệt lỗi đã biết với hợp đồng đang được sử dụng.

Khi nhóm muốn sửa một hành vi sai, hãy tạo test mới cho hành vi đích và ghi rõ đó là thay đổi chức năng. Đừng âm thầm thay đổi kết quả trong một commit được mô tả chỉ là refactor.

### 7.2. Chuyển từng caller

Khi abstraction mới đã có, chuyển caller theo từng nhóm và theo dõi việc sử dụng API cũ. Trong thời gian chuyển tiếp, có thể giữ adapter cũ và mới cùng tồn tại.

Cần tránh hai implementation cùng sở hữu dữ liệu mà không có quy tắc rõ. Nếu cả hai cùng ghi, cần xác định nguồn dữ liệu chính, thứ tự cập nhật, cách xử lý lỗi và cơ chế đối soát. Nếu không thể bảo đảm nhất quán, hãy chuyển một nhóm caller hoặc một phạm vi dữ liệu tại một thời điểm.

### 7.3. Dọn đường cũ sau khi chuyển xong

Sau khi caller đã chuyển, cần tìm và loại bỏ API, adapter, package hoặc dependency cũ không còn sử dụng. Nếu chỉ thêm đường mới nhưng giữ nguyên mọi đường cũ, hệ thống sẽ ngày càng có nhiều cách làm cùng một việc.

Việc dọn dẹp nên có bằng chứng: không còn caller, metric cho thấy lưu lượng cũ bằng không trong khoảng thời gian phù hợp, contract test của client đã chuyển và không có job nền phụ thuộc đường cũ.

## 8. Chuyển đổi dữ liệu và hợp đồng an toàn

Refactor thường chạm đến schema hoặc cấu trúc dữ liệu. Thay đổi code và migration database cần được phối hợp để phiên bản ứng dụng cũ và mới có thể cùng tồn tại trong thời gian triển khai.

Một chiến lược phổ biến là expand-and-contract:

1. **Expand:** thêm cột, bảng hoặc API mới theo cách tương thích với phiên bản đang chạy.
2. **Migrate:** chuyển hoặc backfill dữ liệu theo lô, có kiểm tra và khả năng tiếp tục.
3. **Switch:** chuyển ứng dụng đọc/ghi sang cấu trúc mới sau khi đã xác minh dữ liệu.
4. **Contract:** chỉ xóa cột hoặc API cũ khi không còn phiên bản hoặc caller nào cần chúng.

Ví dụ, đổi `customer_name` thành `display_name` trong database có thể được triển khai theo nhiều release. Đầu tiên thêm cột mới, sau đó đồng bộ/backfill dữ liệu, chuyển code đọc sang cột mới, chuyển ghi và kiểm tra chênh lệch, cuối cùng mới xóa cột cũ khi mọi ứng dụng liên quan đã chuyển.

Không nên duy trì dual write lâu hơn cần thiết. Hai lần ghi vào hai cấu trúc có thể lệch nhau nếu một thao tác thành công còn thao tác kia thất bại. Nếu buộc phải dual write trong giai đoạn chuyển tiếp, cần transaction phù hợp nếu cùng resource, hoặc outbox/đối soát nếu khác resource; cần metric để phát hiện sai lệch và kế hoạch kết thúc cụ thể.

Với API hoặc message contract, có thể thêm trường tùy chọn trước, cập nhật consumer, rồi mới ngừng phát trường cũ. Thay đổi phá vỡ tương thích cần phiên bản hoặc giai đoạn chuyển tiếp được thông báo rõ.

## 9. Kiểm soát phát hành và khả năng quay lui

Tái cấu trúc có thể được phát hành dần bằng feature flag, routing theo nhóm người dùng hoặc chuyển tuyến ở gateway. Những cơ chế này hữu ích khi cần giới hạn phạm vi ảnh hưởng và quan sát hành vi thực tế.

Một kế hoạch phát hành nên xác định:

- Phiên bản hoặc luồng nào được bật trước.
- Điều kiện thành công: lỗi, latency, tỷ lệ kết quả sai hoặc số lượng bản ghi chênh lệch.
- Điều kiện dừng hoặc quay lại luồng cũ.
- Ai có quyền thay đổi flag/routing.
- Cách xử lý dữ liệu đã được ghi theo cấu trúc mới.
- Thời điểm loại bỏ flag và đường cũ.

Quay lại code cũ không luôn đồng nghĩa quay lại dữ liệu cũ. Nếu migration đã thay đổi schema hoặc ghi dữ liệu mới, phiên bản cũ có thể không đọc được. Vì vậy, cần thiết kế tương thích ngược trước khi phát hành và xác định cách xử lý dữ liệu nếu phải rollback.

Feature flag không nên tồn tại mãi. Khi luồng mới ổn định và đã chuyển hết caller, hãy xóa flag, code cũ và cấu hình routing để giảm số trạng thái phải duy trì.

## 10. Ghi quyết định kiến trúc và theo dõi tiến độ

Khi một bước chuyển tiếp ảnh hưởng nhiều nhóm hoặc tạo ngoại lệ, nên ghi lại quyết định kiến trúc (Architecture Decision Record - ADR) ngắn gọn. ADR có thể nêu:

- Bối cảnh và vấn đề đang gặp.
- Các lựa chọn đã cân nhắc.
- Quyết định được chọn và lý do.
- Hệ quả, rủi ro và đánh đổi.
- Ngoại lệ được cho phép, phạm vi và điều kiện kết thúc.
- Trạng thái quyết định: đề xuất, đã chấp nhận, bị thay thế hoặc đã hoàn tất.

ADR không cần trở thành tài liệu dài cho mọi thay đổi nhỏ. Mục đích là giúp người sau hiểu vì sao hệ thống đang có hai cách triển khai hoặc vì sao một dependency tạm thời được phép.

Có thể theo dõi tiến độ chuyển đổi bằng một bảng nhỏ:

| Khu vực | Trạng thái hiện tại | Đích tiếp theo | Người sở hữu | Điều kiện hoàn tất |
|---|---|---|---|---|
| Order read API | Controller gọi JPA trực tiếp | Gọi application use case | Nhóm Order | Web test và architecture rule pass |
| Pricing client | Caller phụ thuộc client cũ | Dùng PricingGateway | Nhóm Pricing | Caller chuyển xong, client cũ không còn được gọi |
| Customer schema | Hai cột cùng tồn tại | Chỉ dùng display_name | Nhóm Data | Backfill và kiểm tra dữ liệu hoàn tất |

Trạng thái nên phản ánh bằng chứng thực tế, chẳng hạn test đã chạy, metric đã đạt hoặc caller đã chuyển. Không đánh dấu hoàn tất chỉ vì code mới đã được merge.

## 11. Những sai lầm thường gặp khi refactor hệ thống cũ

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Viết lại toàn bộ trước khi hiểu hành vi | Phạm vi lớn, khó so sánh và khó quay lui | Chọn một luồng có ranh giới rõ và chuyển từng bước |
| Tạo package mới nhưng giữ nguyên phụ thuộc cũ | Cấu trúc nhìn khác nhưng coupling không đổi | Kiểm tra dependency thực tế bằng test và review |
| Cho phép ngoại lệ không có owner hoặc điều kiện kết thúc | Ngoại lệ trở thành kiến trúc mặc định | Ghi phạm vi, rủi ro, người sở hữu và mốc xem xét |
| Giữ cả đường cũ và mới vô thời hạn | Tăng số cách xử lý và chi phí bảo trì | Theo dõi caller rồi xóa đường cũ khi đủ điều kiện |
| Dual write không có đối soát | Dữ liệu hai nơi lệch nhau | Xác định nguồn chính, transaction hoặc outbox và kiểm tra sai lệch |
| Thay hợp đồng trong cùng một bước refactor | Khó xác định lỗi do cấu trúc hay do hành vi mới | Tách thay đổi cấu trúc và thay đổi chức năng khi có thể |
| Dựa vào unit test để kết luận migration an toàn | Không phát hiện lỗi SQL, transaction hoặc dữ liệu cũ | Thêm integration test và kiểm tra migration |
| Không có kế hoạch quay lui dữ liệu | Code cũ có thể không tương thích schema mới | Dùng expand-and-contract và xác định rollback path |

Một ngoại lệ có thể được chấp nhận nếu nó giúp chuyển đổi an toàn. Nhưng mỗi ngoại lệ cần có chi phí được nhìn thấy và quyết định tiếp tục hoặc loại bỏ. Nếu nhiều ngoại lệ lặp lại vì cùng một lý do, có thể kiến trúc mục tiêu cần được điều chỉnh.

## 12. Checklist review một thay đổi refactor

Trước khi hợp nhất một bước chuyển đổi, hãy kiểm tra:

1. Phạm vi và mục tiêu của thay đổi có đủ nhỏ để review không?
2. Hành vi hiện tại và hợp đồng cần giữ có được ghi nhận bằng test hoặc tài liệu không?
3. Trách nhiệm được chuyển tới đúng tầng chưa: presentation, application, domain hay data access?
4. Dependency mới có tạo hướng phụ thuộc rõ ràng không?
5. Có ngoại lệ kiến trúc nào được thêm, sửa hoặc loại bỏ không? Mỗi ngoại lệ có owner và điều kiện kết thúc chưa?
6. API, message và schema có tương thích với phiên bản đang chạy không?
7. Migration có thể chạy an toàn, tiếp tục sau lỗi và được kiểm tra không?
8. Transaction, dual write và side effect có được xử lý rõ không?
9. Có metric hoặc log để nhận biết luồng mới đang hoạt động đúng không?
10. Có điều kiện dừng, quay lui và kế hoạch xử lý dữ liệu đã ghi không?
11. Sau khi chuyển xong, đường cũ và feature flag nào cần xóa?
12. Test unit, integration, contract và architecture nào chứng minh bước này an toàn?

## 13. Ghi nhớ

- Tái cấu trúc hệ thống đang vận hành nên bắt đầu từ một luồng và một ranh giới có thể kiểm soát, với hiểu biết về hành vi hiện tại.
- Giữ hợp đồng bên ngoài ổn định khi có thể; tách refactor cấu trúc khỏi thay đổi chức năng để dễ đánh giá.
- Facade, adapter, branch by abstraction và strangler pattern tạo đường chuyển tiếp khi caller hoặc implementation cũ chưa thể thay ngay.
- Ngoại lệ kiến trúc cần phạm vi hẹp, lý do, rủi ro, biện pháp kiểm soát, người sở hữu và điều kiện kết thúc.
- Architecture test có thể cho phép ngoại lệ cụ thể trong thời gian chuyển đổi và giúp ngăn dependency lan rộng.
- Chuyển từng caller, kiểm thử từng bước và loại bỏ đường cũ khi đã có bằng chứng không còn sử dụng.
- Dùng expand-and-contract cho schema và contract để phiên bản cũ/mới có thể cùng tồn tại trong thời gian triển khai.
- Dual write cần cơ chế nhất quán, đối soát và thời điểm kết thúc rõ ràng.
- Kế hoạch phát hành phải có điều kiện thành công, dừng và quay lui; rollback code không tự động khôi phục dữ liệu.
- ADR và bảng theo dõi giúp nhóm hiểu lý do chuyển tiếp, ngoại lệ còn lại và bằng chứng hoàn tất.

