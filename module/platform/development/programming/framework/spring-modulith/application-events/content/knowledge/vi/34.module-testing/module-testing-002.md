# Giới hạn phạm vi test

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events kết nối các module qua hợp đồng sự kiện và giúp giữ ranh giới nghiệp vụ rõ ràng. Khi kiểm thử, phạm vi cần đủ rộng để chứng minh hợp đồng và luồng giao tiếp hoạt động, nhưng cũng đủ hẹp để lỗi có thể được định vị nhanh. Một bài test khởi động toàn bộ ứng dụng cho mọi trường hợp thường chậm và dễ phụ thuộc vào hạ tầng; một unit test chỉ mock mọi collaborator lại có thể bỏ sót lỗi wiring, transaction hoặc cấu hình listener.

**Giới hạn phạm vi test** là quyết định thành phần nào được chạy thật, thành phần nào được thay thế bằng test double và ranh giới nào được kiểm tra trong một test. Phạm vi nên xuất phát từ hành vi cần chứng minh và rủi ro cần kiểm soát. Với Spring Modulith, có thể kiểm thử một lớp hoặc use case, một adapter, một application module, quan hệ kiến trúc giữa các module hoặc toàn bộ luồng tích hợp. Không phải test nào cũng cần khởi động cả ứng dụng hay broker thật.

## 1. Bắt đầu từ hành vi và ranh giới cần bảo vệ

Trước khi chọn annotation hoặc test framework, hãy mô tả điều test cần chứng minh. Ví dụ:

- Khi Order được xác nhận, module Order công bố OrderConfirmed với các field theo contract.
- Listener trong Inventory nhận event và yêu cầu giữ hàng.
- Listener chỉ xử lý sau khi transaction phát event commit.
- Event Publication Registry ghi nhận publication và phản ánh trạng thái hoàn tất.
- Module Order không truy cập repository nội bộ của Inventory.
- Adapter RabbitMQ chuyển message đúng destination và xử lý lỗi theo chính sách.
- Một event giao lại không làm tác dụng nghiệp vụ bị thực hiện hai lần.

Mỗi hành vi có ranh giới tự nhiên khác nhau. Quy tắc tính toán có thể được kiểm thử bằng unit test; việc listener được Spring đăng ký cần test có Spring context; việc transaction commit trước listener cần test tích hợp; việc message được broker giao nhận cần test với broker hoặc môi trường mô phỏng có semantics tương đương.

Hãy chọn phạm vi nhỏ nhất có thể chứng minh đầy đủ hành vi. Nếu test cần kiểm tra một quy tắc domain, không cần khởi động RabbitMQ. Nếu test cần xác nhận broker acknowledgement, mock broker sẽ không chứng minh được điều đó.

## 2. Các tầng phạm vi test

Có thể chia test thành các tầng sau:

| Phạm vi | Thành phần chạy thật | Mục tiêu |
|---|---|---|
| Unit test | Một class hoặc nhóm class nhỏ | Quy tắc, nhánh logic và state transition |
| Component test | Một component cùng collaborator gần | Wiring cục bộ, converter, serializer hoặc adapter |
| Module test | Một application module và dependency được chọn | Hợp đồng public, service, repository, listener trong module |
| Integration test | Nhiều module hoặc hệ thống ngoài | Transaction, messaging và phối hợp qua boundary |
| Architecture test | Mô hình module và dependency | Ranh giới module, dependency direction và package access |
| End-to-end test | Toàn ứng dụng cùng hạ tầng cần thiết | Một số hành trình nghiệp vụ quan trọng từ đầu đến cuối |

Các tầng không thay thế nhau. Unit test nhiều không chứng minh Spring wiring đúng; module test không chứng minh cấu hình broker production đúng; end-to-end test thành công cũng không giúp định vị mọi lỗi nhỏ nhanh bằng test phạm vi hẹp.

Một bộ test cân bằng thường có nhiều test nhỏ, một lượng vừa phải module/integration test và rất ít end-to-end test. Tỷ lệ cụ thể tùy hệ thống; điều quan trọng là mỗi test có lý do rõ ràng cho phạm vi mà nó khởi động.

## 3. Unit test: kiểm tra logic thuần trong phạm vi nhỏ

Unit test phù hợp với logic có thể kiểm tra mà không cần Spring context, database hoặc broker. Ví dụ: quy tắc chọn event tiếp theo, xác thực event metadata, chuyển trạng thái saga, tính số lượng reservation hoặc quyết định retry.

~~~java
class OrderPolicyTests {

    private final OrderPolicy policy = new OrderPolicy();

    @Test
    void confirmedOrderCanPublishEvent() {
        Order order = Order.confirmed(
            new OrderId("ORD-100"),
            Money.of(250_000, "VND")
        );

        OrderConfirmed event = policy.toEvent(order);

        assertThat(event.orderId()).isEqualTo("ORD-100");
        assertThat(event.total()).isEqualTo(250_000);
        assertThat(event.currency()).isEqualTo("VND");
    }
}
~~~

Test này chỉ kiểm tra mapping nghiệp vụ. Nó không chứng minh event đã được Spring publish, listener được gọi hoặc publication được lưu trong registry. Những điều đó thuộc phạm vi khác.

Không mock mọi object chỉ để biến một unit test thành một bài kiểm tra tương tác giả tạo. Nếu logic có thể được kiểm tra bằng input/output thuần, hãy dùng object thật. Dùng mock khi cần kiểm tra một ranh giới collaborator hoặc mô phỏng lỗi mà test không thể tạo ra một cách đơn giản.

## 4. Component test: kiểm tra một thành phần có wiring giới hạn

Component test phù hợp khi cần kiểm tra một nhóm class phối hợp với nhau nhưng không cần toàn bộ module. Ví dụ serializer cùng converter, mapper, adapter hoặc một service cùng repository test double.

Với event payload, có thể kiểm tra serializer tạo JSON đúng schema, encoding UTF-8, xử lý field optional và từ chối payload vượt giới hạn. Test không cần mở broker vì mục tiêu là contract serialization.

Với adapter, có thể kiểm tra mapping từ application event sang message envelope, routing key, headers và exception translation. Broker thật chỉ cần khi hành vi phụ thuộc protocol, acknowledgement, redelivery hoặc queue topology.

Giữ component test gần với implementation cần bảo vệ. Nếu test khởi động quá nhiều bean không liên quan, lỗi cấu hình ở module khác có thể làm test thất bại dù component đang kiểm tra không thay đổi.

## 5. Module test với Spring Modulith

Spring Modulith cung cấp **@ApplicationModuleTest** để khởi động test context theo ranh giới application module. Đây là phạm vi hữu ích khi muốn kiểm tra public behavior của một module cùng các thành phần Spring thuộc phạm vi được chọn.

Ví dụ:

~~~java
@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.STANDALONE
)
class InventoryModuleTests {

    @Autowired
    InventoryApplicationService inventory;

    @Test
    void reservesAvailableQuantity() {
        ReservationResult result =
            inventory.reserve(new ReserveInventoryCommand(
                "ORD-100",
                "SKU-1",
                2
            ));

        assertThat(result.isReserved()).isTrue();
    }
}
~~~

Đặt test ở package giúp Spring Modulith nhận diện module cần kiểm thử. Trong test, ưu tiên gọi public API hoặc gửi event qua hợp đồng module. Không gọi trực tiếp private method hoặc repository nội bộ chỉ vì test có thể truy cập được chúng.

**@ApplicationModuleTest** có các bootstrap mode để kiểm soát module nào được đưa vào context:

| Mode | Phạm vi khởi tạo | Khi phù hợp |
|---|---|---|
| **STANDALONE** | Module đang kiểm thử | Module có thể chạy với dependency được thay thế hoặc không cần module khác |
| **DIRECT_DEPENDENCIES** | Module đang kiểm thử và các dependency trực tiếp | Kiểm tra module trong ngữ cảnh phụ thuộc gần nhất |
| **ALL_DEPENDENCIES** | Module đang kiểm thử cùng dependency bắc cầu | Khi hành vi cần các module phụ thuộc sâu hơn |

Chọn mode tường minh để người đọc hiểu phạm vi test. Nếu module cần một dependency ngoài phạm vi, có thể thay thế port hoặc collaborator bên ngoài bằng test double. Đừng mở rộng sang toàn bộ dependency chỉ để làm một test chạy qua mà không hiểu test đang kiểm tra điều gì.

## 6. Khi nào chọn STANDALONE, DIRECT_DEPENDENCIES hay ALL_DEPENDENCIES?

**STANDALONE** hữu ích khi muốn chứng minh module có thể được khởi tạo và kiểm tra độc lập. Những dependency ngoài module có thể được cung cấp qua mock hoặc test configuration. Nếu module không thể chạy vì phải truy cập implementation nội bộ của module khác, đó có thể là tín hiệu coupling cần xem xét.

**DIRECT_DEPENDENCIES** phù hợp khi module sử dụng API công khai của một hoặc vài module khác và cần kiểm tra sự phối hợp trực tiếp. Đây thường là phạm vi thực tế cho module test có dependency rõ ràng.

**ALL_DEPENDENCIES** cần thiết khi hành vi phụ thuộc vào một chuỗi module và việc thay thế dependency bắc cầu sẽ làm mất hành vi cần chứng minh. Tuy nhiên, context lớn hơn sẽ tăng thời gian khởi động và làm test nhạy với thay đổi ở nhiều module.

Không chọn mode rộng nhất theo thói quen. Nếu một test cần module C chỉ vì module B gọi C, hãy hỏi liệu test đang xác minh hợp đồng của module A hay đang vô tình kiểm tra toàn bộ implementation phía sau B. Khi hợp đồng A–B đã đủ để test, có thể thay thế dependency ngoài phạm vi bằng một test double.

## 7. Test public API thay vì chi tiết nội bộ

Module test nên quan sát hành vi qua public API, event contract hoặc port được công bố. Cách này giúp test sống lâu hơn khi implementation thay đổi.

Ví dụ, khi kiểm tra Order công bố OrderConfirmed, hãy gọi use case xác nhận đơn và quan sát event được phát. Không cần gọi trực tiếp method nội bộ publishConfirmedEvent hoặc kiểm tra tên class implementation của publisher.

Nếu một test phải truy cập package-private repository của module khác, điều đó có thể cho thấy module đang vượt qua ranh giới sở hữu. Hãy xem lại API hoặc event contract thay vì mở rộng visibility chỉ để test thuận tiện.

Test không nên biến cấu trúc nội bộ thành hợp đồng ngầm. Những assertion như “service A phải gọi repository B đúng hai lần” thường mong manh nếu hành vi bên ngoài không yêu cầu điều đó. Hãy ưu tiên kiểm tra kết quả, trạng thái và message contract có ý nghĩa nghiệp vụ.

## 8. Kiểm thử ranh giới kiến trúc riêng với kiểm thử hành vi

Spring Modulith có thể phân tích module structure và xác minh dependency giữa các module. Kiểm tra kiến trúc trả lời câu hỏi “các module có phụ thuộc đúng hướng và đúng API không?”, còn module test trả lời “module có thực hiện hành vi đúng không?”.

Ví dụ kiểm tra dependency:

~~~java
class ApplicationModulesTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules modules =
            ApplicationModules.of(Application.class);

        modules.verify();
    }
}
~~~

Đây là test kiến trúc; nó không cần khởi động toàn bộ Spring application context để thực hiện use case. Nó có thể phát hiện dependency cycle hoặc truy cập không phù hợp theo quy tắc module được khai báo.

Không dùng architecture test để thay thế test nghiệp vụ. Một module có dependency đúng vẫn có thể phát sai event hoặc xử lý sai transaction. Ngược lại, end-to-end test chạy thành công không chứng minh package dependency tuân thủ ranh giới kiến trúc.

## 9. Giới hạn phạm vi cho application event listener

Listener là điểm giao giữa event contract và hành vi module. Phạm vi test phụ thuộc điều cần xác minh:

- Mapping event sang command hoặc use case: unit/component test.
- Listener được Spring đăng ký và nhận đúng event: module test.
- Listener xử lý sau commit: transaction integration test.
- Listener bất đồng bộ và retry publication: module/integration test với cơ chế chờ có kiểm soát.
- Message qua broker và consumer acknowledgement: adapter/broker integration test.

Với listener nội bộ, test có thể publish application event qua Spring event publisher hoặc API phù hợp của Spring Modulith rồi quan sát kết quả tại public API của module nhận.

Không gọi method listener trực tiếp nếu mục tiêu là kiểm tra event routing hoặc transaction phase. Gọi trực tiếp chỉ kiểm tra logic method, không chứng minh Spring đã đăng ký listener hay listener chạy ở thời điểm mong muốn.

Nếu chỉ muốn kiểm tra logic xử lý, tách logic ra application service và unit test service đó. Giữ một số module test xác nhận listener kết nối event với service đúng cách.

## 10. Kiểm thử transaction và xử lý sau commit

Event listener có thể chạy sau khi transaction phát event commit. Khi test cần xác minh semantics này, phải kiểm soát transaction thật và thời điểm commit.

Một bẫy thường gặp là test method được đánh dấu **@Transactional** và framework tự rollback khi kết thúc. Nếu listener chỉ chạy sau commit, test có thể kết thúc mà transaction chưa commit, khiến listener không chạy. Test khi đó thất bại dù implementation đúng, hoặc test bỏ qua hành vi cần xác minh.

Cách tiếp cận:

- Tạo transaction rõ ràng và commit trước khi chờ kết quả listener.
- Nếu cần rollback, xác nhận listener không thực hiện tác dụng phụ theo semantics mong đợi.
- Kiểm tra trạng thái database sau commit thay vì chỉ verify một mock được gọi.
- Không dùng transaction test mặc định để suy luận rằng async listener đã hoàn tất.
- Đặt ranh giới transaction trong application service thực tế và tránh self-invocation làm mất proxy semantics.

Test transaction nên có ít kịch bản nhưng kiểm tra đúng ranh giới commit/rollback. Không cần lặp lại test transaction cho mọi event type nếu các listener dùng chung cơ chế đã được xác minh và logic riêng đã có unit/module test.

## 11. Phạm vi cho Event Publication Registry

Event Publication Registry theo dõi publication tới transactional listeners và hỗ trợ phát hiện publication chưa hoàn tất. Khi kiểm thử, hãy tách hai câu hỏi:

1. Listener thực hiện đúng hành vi khi nhận event?
2. Publication state được ghi nhận và hoàn tất đúng theo cơ chế registry?

Câu hỏi thứ nhất thường thuộc module test. Câu hỏi thứ hai cần test với persistence configuration của registry, transaction và listener thực tế. Một mock publisher hoặc gọi trực tiếp listener không thể chứng minh trạng thái registry được cập nhật đúng.

Các tình huống đáng kiểm tra gồm publication thành công, listener thất bại, publication còn incomplete và phục hồi/resubmit theo cấu hình. Không cần kiểm tra chi tiết bảng nội bộ của registry nếu contract được công bố là API quản lý hoặc trạng thái quan sát được. Ưu tiên API hỗ trợ của phiên bản Spring Modulith đang dùng.

Giới hạn test ở module sở hữu listener khi kiểm tra hành vi của listener. Chỉ mở rộng sang adapter hoặc application context rộng hơn khi cần chứng minh persistence và recovery đi qua đúng hạ tầng.

## 12. Phạm vi cho event đi qua broker

Broker integration test có mục tiêu khác module test. Nó cần xác minh serialization, routing, headers, acknowledgement, redelivery, retry topology và tương tác với broker.

Không cần chạy RabbitMQ hoặc Kafka thật cho mọi unit test. Thay vào đó:

- Unit test kiểm tra quyết định và mapping.
- Component test kiểm tra serializer, converter và adapter với client giả hoặc stub.
- Broker integration test kiểm tra protocol semantics quan trọng như confirm, ack, redelivery, DLQ và message size.
- Một số end-to-end test xác nhận luồng nghiệp vụ trọng yếu qua producer, broker và consumer.

Khi test broker, dùng broker/container cô lập hoặc môi trường test có thể tái lập. Tạo queue/topic riêng cho test và dọn dữ liệu sau khi chạy. Không để test phụ thuộc vào broker dùng chung có message từ môi trường khác.

Nếu adapter có interface rõ ràng, module test có thể thay thế adapter bằng fake để xác minh module tạo đúng command/event. Broker integration test riêng chịu trách nhiệm kiểm tra adapter với transport. Cách chia này giảm thời gian chạy mà vẫn giữ được test ở nơi có thể phát hiện lỗi thực.

## 13. Chọn mock, stub, fake hay hệ thống thật

Test double cần được chọn theo mục tiêu, không phải theo thói quen.

| Test double | Dùng khi | Giới hạn |
|---|---|---|
| Mock | Kiểm tra tương tác với collaborator hoặc mô phỏng lỗi | Dễ gắn chặt test với implementation |
| Stub | Cung cấp kết quả cố định cho một lời gọi | Không chứng minh hệ thống thật có hành vi tương tự |
| Fake | Cung cấp implementation đơn giản có hành vi gần thực tế | Có thể khác biệt với database/broker thật |
| Real dependency | Cần kiểm tra semantics của hệ thống thật | Tốn thời gian và cần môi trường cô lập |

Ví dụ, mock PaymentGateway phù hợp khi test process manager phát đúng command. Fake repository có thể phù hợp khi test state machine. Database thật cần thiết khi test unique constraint, transaction isolation hoặc locking. Broker thật cần thiết khi test redelivery hoặc routing semantics.

Tránh mock mọi class trong module đang kiểm thử. Nếu test module chỉ có các mock nối với nhau, nó không còn kiểm tra wiring hoặc hành vi module; nó chỉ kiểm tra một kịch bản được dựng sẵn trong test.

## 14. Kiểm soát dependency ngoài phạm vi

Module có thể phụ thuộc database, broker, HTTP service, clock, filesystem hoặc identity provider. Hãy xác định dependency nào là một phần của hành vi cần kiểm tra và dependency nào chỉ là hạ tầng ngoài phạm vi.

Ví dụ:

- Test logic tính retry deadline: dùng Clock cố định.
- Test adapter HTTP mapping: dùng HTTP stub server.
- Test repository query: dùng database test.
- Test broker acknowledgement: dùng broker test.
- Test module orchestration: thay thế external gateway bằng fake hoặc mock.
- Test security boundary: dùng identity context được dựng rõ ràng hoặc test identity provider theo mức cần thiết.

Đừng khởi động mọi dependency ngoài chỉ vì Spring context có thể tự kết nối. Test phải tự kiểm soát endpoint, credentials, queue/topic và dữ liệu. Không dùng môi trường production hoặc tài nguyên dùng chung cho test tự động.

Nếu một dependency không thể thay thế vì module trực tiếp phụ thuộc implementation cụ thể, xem lại port/adapter boundary. Một module có thể cần contract ổn định với dependency ngoài, nhưng không nên để toàn bộ test scope bị kéo rộng bởi chi tiết triển khai của dependency đó.

## 15. Test data, database và isolation

Phạm vi test còn bao gồm dữ liệu và trạng thái được chia sẻ. Một test có thể pass riêng nhưng fail khi chạy song song nếu dùng cùng orderId, queue, schema hoặc file.

Nguyên tắc:

- Dùng định danh test riêng và dữ liệu tối thiểu.
- Tạo database/schema hoặc namespace cô lập khi cần.
- Làm sạch dữ liệu theo owner của test.
- Không phụ thuộc thứ tự chạy giữa các test.
- Không giả định transaction rollback sẽ dọn dữ liệu do thread async hoặc connection khác ghi.
- Dọn message trong queue/topic và trạng thái registry/inbox/outbox sau test.
- Dùng clock cố định cho thời gian nghiệp vụ và timeout.
- Đặt timeout cho mọi chờ đợi bất đồng bộ.

Test có thể dùng transaction rollback để cô lập dữ liệu đồng bộ trong cùng transaction. Nhưng listener chạy ở thread khác hoặc sau commit có thể dùng transaction/connection riêng. Khi đó, rollback của test thread không dọn được tác dụng phụ của listener. Hãy cleanup rõ ràng hoặc dùng database/namespace riêng.

## 16. Kiểm thử bất đồng bộ mà không mở rộng scope quá mức

Listener bất đồng bộ cần được chờ tới khi đạt trạng thái mong muốn. Không dùng Thread.sleep() với thời gian cố định làm cơ chế đồng bộ vì test vừa chậm vừa không ổn định.

Dùng Awaitility hoặc API chờ phù hợp để chờ một điều kiện quan sát được:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(inventoryRepository.findByOrderId(orderId))
            .isPresent()
    );
~~~

Điều kiện nên phản ánh kết quả nghiệp vụ, không chỉ việc thread đã chạy hoặc method đã được gọi. Đặt timeout hợp lý để lỗi được báo nhanh và có thông tin chẩn đoán.

Nếu mục tiêu là test logic listener, có thể gọi application service đồng bộ trong unit test. Chỉ test async behavior trong số ít module/integration test cần xác minh executor, transaction phase hoặc publication lifecycle. Không cần biến mọi test nghiệp vụ thành test bất đồng bộ.

## 17. Tránh test scope quá rộng và test scope quá hẹp

Dấu hiệu test quá rộng:

- Khởi động toàn bộ ứng dụng chỉ để kiểm tra một hàm domain.
- Phụ thuộc broker, database và HTTP service dù hành vi không cần chúng.
- Thất bại do module không liên quan thay đổi.
- Thời gian chạy dài khiến developer ngại chạy test.
- Một test kiểm tra quá nhiều kết quả nên lỗi khó định vị.

Dấu hiệu test quá hẹp:

- Mock chính listener khi mục tiêu là kiểm tra listener registration.
- Mock repository khi cần xác minh unique constraint hoặc transaction.
- Gọi method trực tiếp khi cần kiểm tra event dispatch.
- Không kiểm tra commit/rollback dù hành vi phụ thuộc transaction phase.
- Chỉ kiểm tra publisher được gọi mà không xác nhận event contract.
- Dùng fake broker khi cần kiểm tra redelivery hoặc acknowledgement thật.

Khi test thất bại, phạm vi vừa đủ giúp chỉ ra lớp có lỗi. Nếu một unit test cần quá nhiều mock, logic có thể đang ôm quá nhiều trách nhiệm. Nếu một module test cần mọi module khác và nhiều hệ thống ngoài, ranh giới module hoặc port có thể chưa rõ.

## 18. Ma trận chọn phạm vi cho các hành vi Spring Modulith

| Hành vi cần chứng minh | Phạm vi ưu tiên | Hệ thống thật cần có |
|---|---|---|
| Quy tắc domain khi nhận event | Unit test | Không |
| Event DTO và schema mapping | Component/contract test | Serializer thực tế |
| Listener được đăng ký trong module | Module test | Spring context giới hạn |
| Module phát event qua public API | Module test | Spring context và event mechanism |
| Module dependency hợp lệ | Architecture test | Module model |
| Listener chỉ chạy sau commit | Module/integration test | Transaction manager và persistence |
| Publication registry cập nhật trạng thái | Integration test | Registry persistence |
| Consumer xử lý duplicate idempotent | Module/integration test | Store/constraint cần thiết |
| RabbitMQ routing và ACK/NACK | Broker integration test | RabbitMQ |
| Kafka serialization và offset semantics | Broker integration test | Kafka |
| Quy trình Order–Inventory–Payment | Một số end-to-end test | Các module và dependency liên quan |

Ma trận là điểm bắt đầu. Nếu test chỉ cần xác minh một hợp đồng, hãy dùng fake cho collaborator ngoài phạm vi. Nếu rủi ro nằm ở transaction hoặc transport, dùng hệ thống thật tại đúng boundary đó.

## 19. Tổ chức bộ test và CI

Một chiến lược CI có thể chia test theo chi phí và mục đích:

1. **Nhanh:** unit test, mapper/serializer test và architecture verification.
2. **Theo module:** @ApplicationModuleTest cho module thay đổi và các hợp đồng quan trọng.
3. **Tích hợp:** database, registry, broker hoặc HTTP stub/container cho các semantics cần thiết.
4. **End-to-end:** một số hành trình nghiệp vụ quan trọng, chạy ở stage phù hợp.

Test nhanh nên chạy thường xuyên ở local và mỗi pull request. Test tích hợp có thể chạy song song nếu mỗi test có namespace và dữ liệu cô lập. End-to-end test thường ít hơn và có thể chạy trên pipeline hoặc môi trường staging.

Không tách test thành nhiều nhóm chỉ theo annotation. Hãy đặt tên theo hành vi và boundary, ví dụ InventoryModuleTests, OrderEventContractTests, PublicationAfterCommitTests hoặc RabbitMqAdapterIntegrationTests. Người đọc phải hiểu test kiểm tra điều gì mà không cần xem toàn bộ implementation.

Khi một thay đổi module làm test của module khác thất bại, hãy kiểm tra xem test đó đang xác minh public contract hay phụ thuộc chi tiết nội bộ. Thay đổi contract có thể yêu cầu cập nhật consumer; thay đổi implementation nội bộ không nên làm test module khác thất bại nếu boundary được giữ đúng.

## 20. Quy trình quyết định phạm vi cho một test mới

Trước khi viết test, trả lời lần lượt:

1. Hành vi hoặc invariant nào cần được bảo vệ?
2. Module nào sở hữu hành vi và dữ liệu?
3. Ranh giới cần kiểm tra là class, adapter, module, kiến trúc hay toàn hệ thống?
4. Những dependency nào phải chạy thật để chứng minh hành vi?
5. Dependency ngoài phạm vi nào có thể thay bằng mock, stub hoặc fake?
6. Có cần kiểm tra Spring wiring, transaction, async listener hoặc broker semantics không?
7. Dữ liệu, queue/topic và trạng thái registry được cô lập ra sao?
8. Test có thể quan sát kết quả nghiệp vụ qua public API không?
9. Test có ổn định khi chạy song song và độc lập với thứ tự không?
10. Nếu test fail, thông tin có đủ để định vị boundary gây lỗi không?

Nếu không thể trả lời câu hỏi về boundary, hãy xem lại thiết kế module trước khi thêm nhiều mock hoặc mở rộng context. Một test scope tốt thường là dấu hiệu hợp đồng và trách nhiệm module đã rõ.

Giới hạn phạm vi test là cách đặt đúng mức kiểm chứng tại từng ranh giới. Unit test bảo vệ logic nhỏ, module test xác minh hành vi trong boundary của Spring Modulith, architecture test bảo vệ dependency direction, còn integration và end-to-end test tập trung vào transaction, registry, broker và các luồng quan trọng. Khi mỗi test chỉ khởi động những thành phần cần thiết, dùng dependency thật đúng nơi có rủi ro và quan sát kết quả qua hợp đồng công khai, bộ test sẽ nhanh hơn, ổn định hơn và giúp định vị lỗi rõ ràng hơn.

