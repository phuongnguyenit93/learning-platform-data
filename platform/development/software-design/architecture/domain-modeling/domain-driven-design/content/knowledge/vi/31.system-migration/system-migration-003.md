# Bảo vệ hành vi cũ bằng kiểm thử trước khi tái cấu trúc

Khi chuyển một hệ thống đang chạy sang mô hình rõ ràng hơn, rủi ro lớn nhất thường không nằm ở việc viết lại một lớp hay đổi một framework. Rủi ro là vô tình thay đổi hành vi mà người dùng, dữ liệu hoặc hệ thống khác đang phụ thuộc vào.

Trong một hệ thống cũ, nhiều quy tắc nghiệp vụ có thể nằm rải rác trong service, SQL, mapper, batch job, controller hoặc những điều kiện mà không tài liệu nào mô tả đầy đủ. Trước khi tái cấu trúc, đội phát triển cần tạo một lớp bằng chứng về hành vi đang tồn tại. Kiểm thử ở giai đoạn này có mục đích chính là ghi nhận và bảo vệ hành vi quan sát được, để sau đó có thể thay đổi cấu trúc bên trong với độ tin cậy cao hơn.

Trong Domain-Driven Design, công việc này đặc biệt hữu ích khi hệ thống cũ đang che khuất mô hình miền. Kiểm thử giúp phát hiện các quy tắc đang thực sự có hiệu lực, các bất biến ngầm, các thuật ngữ được dùng trong code và những điểm mà các bounded context đang trao đổi với nhau. Khi mô hình mới dần xuất hiện, các kiểm thử ban đầu trở thành bằng chứng rằng quá trình thay đổi vẫn giữ được những hành vi cần bảo toàn.

## Mục tiêu học tập

Sau bài này, có thể:

- phân biệt hành vi cần bảo vệ với chi tiết triển khai cần được tự do thay đổi;
- tạo characterization test cho một hệ thống chưa có test đáng tin cậy;
- dùng Golden Master hoặc Approval Test khi đầu ra có cấu trúc lớn;
- kiểm soát thời gian, dữ liệu ngẫu nhiên và các phụ thuộc bên ngoài để test ổn định;
- xác định seam để đưa kiểm thử vào hệ thống cũ mà không cần viết lại toàn bộ;
- dùng test để phát hiện bất biến và quy tắc miền trước khi tái cấu trúc;
- chia quá trình migration thành các bước nhỏ có thể kiểm chứng;
- nhận biết khi một test đang khóa implementation thay vì bảo vệ behavior.

## Vì sao phải kiểm thử trước khi tái cấu trúc?

Tái cấu trúc thay đổi cấu trúc của chương trình trong khi mong muốn giữ nguyên hành vi. Nếu chưa có bằng chứng về hành vi hiện tại, câu "giữ nguyên behavior" chỉ là một giả định.

Ví dụ, một hệ thống tính giá đơn hàng có thể đang áp dụng:

1. giảm giá theo hạng khách hàng;
2. miễn phí vận chuyển khi tổng tiền sau giảm vượt ngưỡng;
3. làm tròn tiền ở từng dòng trước khi cộng;
4. bỏ qua sản phẩm đã ngừng bán;
5. ghi nhận thời điểm tính giá theo múi giờ của cửa hàng.

Một tài liệu nghiệp vụ có thể chỉ nói "tính giá và giảm giá". Code cũ mới chứa các chi tiết thực sự quyết định kết quả. Nếu chuyển logic sang Order, Money, DiscountPolicy và ShippingPolicy mà không đo được đầu ra cũ, một thay đổi nhỏ về thứ tự làm tròn cũng có thể làm sai hàng nghìn giao dịch.

Kiểm thử trước migration tạo ra một đường cơ sở:

~~~text
Hành vi quan sát được hôm nay
            |
            v
     Characterization tests
            |
            v
      Refactor từng bước
            |
            v
  Kiểm thử vẫn giữ nguyên hành vi
~~~

Đường cơ sở này không khẳng định hệ thống cũ là đúng về mặt nghiệp vụ. Nó ghi lại những gì hệ thống đang làm. Quyết định rằng một hành vi là đúng, sai hoặc cần thay đổi là một quyết định nghiệp vụ riêng.

## Hành vi và implementation là hai thứ khác nhau

Một test tốt cho migration thường mô tả điều mà người gọi có thể quan sát được:

| Thành phần | Nên bảo vệ | Không nên khóa |
|---|---|---|
| Kết quả | giá trị trả về, trạng thái, lỗi nghiệp vụ | tên biến cục bộ |
| Quy tắc | điều kiện, giới hạn, bất biến | cấu trúc if cụ thể |
| Side effect | bản ghi được tạo, event được phát | private method |
| Giao tiếp | hợp đồng HTTP/message | framework nội bộ |
| Dữ liệu | field có ý nghĩa với caller | thứ tự field không có ý nghĩa |
| Thời gian | thời điểm nghiệp vụ quan sát được | cách lấy system clock |
| Persistence | dữ liệu cần tồn tại | câu SQL cụ thể nếu SQL không phải contract |

Ví dụ, nếu hệ thống trả về total = 900000, test nên kiểm tra tổng tiền và các quy tắc liên quan. Test dựa vào việc LegacyOrderService gọi calculateDiscount trước calculateShipping có thể trở thành vật cản khi cấu trúc được thay đổi.

Một nguyên tắc hữu ích là hỏi:

> Nếu thay implementation bằng một implementation hoàn toàn khác nhưng caller vẫn nhận cùng kết quả và side effect, test này có còn cần thay đổi không?

Nếu câu trả lời là có, test có thể đang gắn quá chặt vào implementation.

## Characterization Test là gì?

Characterization Test là kiểm thử được viết để mô tả hành vi thực tế của hệ thống hiện tại. Nó thường được dùng khi chưa biết đầy đủ hệ thống đang làm gì hoặc khi tài liệu không đủ tin cậy.

Quy trình cơ bản:

1. chọn một entry point có thể gọi được;
2. cung cấp input thực tế hoặc đại diện;
3. chạy code hiện tại;
4. quan sát output và side effect;
5. ghi kết quả thành assertion;
6. chạy lại để xác nhận kết quả ổn định;
7. chỉ sau đó mới bắt đầu tái cấu trúc.

Tên test có thể phản ánh hành vi quan sát được:

~~~java
@Test
void customerWithGoldTierReceivesTheExistingDiscount() {
    var order = orderOf(
        line("BOOK", 2, money("100000")),
        line("PEN", 1, money("20000"))
    );

    var result = legacyService.calculate(order, goldCustomer());

    assertThat(result.total()).isEqualByComparingTo(money("192000"));
}
~~~

Ở đây, điều quan trọng là 192000 đã được quan sát từ hệ thống hiện tại và được xác nhận là hành vi cần giữ. Không nên bịa expected value dựa trên implementation mới rồi gọi đó là characterization test.

## Đầu tiên phải xác định phạm vi hành vi

Một hệ thống lớn không nên được khóa toàn bộ trong một lần. Hãy chọn một luồng có giá trị và giới hạn phạm vi:

~~~text
HTTP / Message
      |
      v
Application entry point
      |
      +----> Domain logic
      |
      +----> Repository
      |
      +----> External service
      |
      v
Observable result
~~~

Phạm vi đầu tiên nên có:

- một nghiệp vụ quan trọng;
- input có thể tạo lại;
- output có thể quan sát;
- side effect có thể kiểm tra;
- thời gian thực thi chấp nhận được;
- ít phụ thuộc ngoài nhất có thể.

Ví dụ, với hệ thống hóa đơn, có thể bắt đầu bằng "đánh dấu hóa đơn quá hạn" thay vì cố gắng test toàn bộ module billing.

## Preflight trước khi tạo baseline

Trước khi viết test, cần trả lời một số câu hỏi:

| Câu hỏi | Mục đích |
|---|---|
| Entry point là gì? | xác định seam |
| Input đến từ đâu? | tạo fixture |
| Output nào có ý nghĩa? | chọn assertion |
| Có side effect nào? | ghi nhận contract |
| Thời gian có ảnh hưởng không? | cố định clock |
| Randomness có ảnh hưởng không? | inject source |
| Có database không? | quyết định test level |
| Có HTTP/broker/file không? | cô lập hoặc dùng adapter thật |
| Có lỗi nghiệp vụ đặc biệt không? | tạo case riêng |
| Hành vi nào đã được business xác nhận? | phân biệt behavior cần giữ |

Không cần biết toàn bộ codebase trước khi bắt đầu. Nhưng cần hiểu đường đi của một use case đủ để biết assertion đang đo điều gì.

## Chọn seam để đưa test vào hệ thống cũ

Seam là một điểm mà tại đó có thể thay đổi input, dependency hoặc cách gọi mà không phải sửa quá nhiều code.

Các seam thường gặp:

- public method của application service;
- HTTP endpoint;
- command handler;
- message consumer;
- repository interface đã tồn tại;
- gateway tới dịch vụ ngoài;
- factory;
- clock hoặc provider thời gian;
- file hoặc database adapter.

Ví dụ, nếu code cũ nhận Clock, việc cố định thời gian dễ dàng:

~~~java
var clock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);

var service = new LegacyInvoiceService(repository, clock);
~~~

Nếu code chưa có seam, không nên vội viết lại toàn bộ. Có thể tạo một seam nhỏ, có mục đích rõ ràng, rồi ghi nhận behavior qua seam đó.

## Ví dụ: bảo vệ hành vi tính hóa đơn

Giả sử hệ thống cũ có service:

~~~java
public final class LegacyInvoiceService {
    private final InvoiceRepository repository;
    private final Clock clock;

    public LegacyInvoiceService(
        InvoiceRepository repository,
        Clock clock
    ) {
        this.repository = repository;
        this.clock = clock;
    }

    public InvoiceResult close(String invoiceId) {
        var invoice = repository.find(invoiceId);

        if (invoice == null) {
            throw new InvoiceNotFound(invoiceId);
        }

        if (invoice.isClosed()) {
            return InvoiceResult.alreadyClosed(invoiceId);
        }

        var closedAt = LocalDateTime.now(clock);
        repository.markClosed(invoiceId, closedAt);

        return InvoiceResult.closed(invoiceId, closedAt);
    }
}
~~~

Trước khi chuyển logic sang aggregate Invoice, cần khóa những hành vi có ý nghĩa:

- invoice không tồn tại thì báo lỗi;
- invoice đã đóng thì không đóng lần nữa;
- invoice đang mở được đóng đúng một lần;
- thời điểm đóng đến từ clock của application;
- repository nhận đúng identifier và timestamp.

Một characterization test có thể bắt đầu như sau:

~~~java
@Test
void openInvoiceIsClosedAtTheCurrentBusinessTime() {
    var repository = new InMemoryInvoiceRepository(
        openInvoice("INV-001")
    );
    var clock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
    );
    var service = new LegacyInvoiceService(repository, clock);

    var result = service.close("INV-001");

    assertThat(result.status()).isEqualTo(CLOSED);
    assertThat(result.closedAt())
        .isEqualTo(LocalDateTime.of(2026, 1, 15, 10, 0));
    assertThat(repository.find("INV-001").isClosed()).isTrue();
}
~~~

Test này bảo vệ contract quan sát được. Sau đó có thể chuyển invariant "invoice chỉ được đóng một lần" vào aggregate mà không phải giữ nguyên cấu trúc của service.

## Test các nhánh biên trước khi refactor

Một baseline tốt không chỉ chứa happy path. Những nhánh biên thường chứa nhiều quy tắc ngầm nhất.

Ví dụ:

~~~java
@Test
void missingInvoiceIsRejected() {
    var repository = new InMemoryInvoiceRepository();
    var service = new LegacyInvoiceService(repository, fixedClock());

    assertThatThrownBy(() -> service.close("MISSING"))
        .isInstanceOf(InvoiceNotFound.class);
}

@Test
void alreadyClosedInvoiceRemainsClosed() {
    var repository = new InMemoryInvoiceRepository(
        closedInvoice("INV-002", at("2026-01-10T09:00:00"))
    );
    var service = new LegacyInvoiceService(repository, fixedClock());

    var result = service.close("INV-002");

    assertThat(result.status()).isEqualTo(ALREADY_CLOSED);
    assertThat(repository.find("INV-002").closedAt())
        .isEqualTo(LocalDateTime.of(2026, 1, 10, 9, 0));
}
~~~

Những test như vậy giúp phát hiện một invariant trước khi nó được đưa vào domain model:

~~~text
Invoice
  |
  +-- trạng thái OPEN
  |      |
  |      +-- close() --> CLOSED
  |
  +-- trạng thái CLOSED
         |
         +-- close() --> giữ nguyên / báo ALREADY_CLOSED
~~~

## Khi output quá lớn: Golden Master

Một số hệ thống có output rất lớn, ví dụ:

- báo cáo hàng nghìn dòng;
- JSON phức tạp;
- kết quả tính toán có nhiều field;
- file export;
- HTML;
- response của một engine cũ.

Viết assertion riêng cho từng field có thể tốn công và bỏ sót thay đổi. Golden Master là cách lưu output đã được chấp nhận làm baseline rồi so sánh output mới với baseline.

Ví dụ:

~~~java
@Test
void pricingOutputMatchesGoldenMaster() {
    var input = loadFixture("pricing-order.json");

    var actual = legacyPricingService.calculate(input);
    var expected = loadGoldenMaster("pricing-order.result.json");

    assertThat(normalize(actual))
        .isEqualTo(normalize(expected));
}
~~~

Golden Master hữu ích khi mục tiêu đầu tiên là biết "hệ thống mới có khác hệ thống cũ không?". Tuy nhiên, việc output giống nhau không tự chứng minh output là đúng nghiệp vụ.

Nên có bước review:

~~~text
Output hiện tại
      |
      v
Business review
      |
      +----> behavior cần giữ
      |
      +----> behavior cần thay đổi
~~~

Nếu business xác nhận một behavior cũ là lỗi và migration có chủ đích sửa lỗi đó, baseline không nên trở thành rào cản. Test phải được cập nhật cùng với quyết định nghiệp vụ.

## Approval Test và snapshot

Approval Test phù hợp khi cần review một output lớn dưới dạng file hoặc snapshot. Ví dụ một kết quả tính giá có thể được lưu thành:

~~~text
test-fixtures/
  pricing/
    order-001.input.json
    order-001.approved.json
~~~

Khi code thay đổi:

1. test tạo output mới;
2. tool so sánh output mới với approved file;
3. diff cho biết chính xác phần thay đổi;
4. team quyết định thay đổi có được chấp nhận không;
5. chỉ sau khi review mới cập nhật approved file.

Không nên tự động cập nhật snapshot trong CI rồi coi test đã pass. Nếu snapshot luôn được ghi đè, nó không còn bảo vệ behavior.

## Bảo vệ side effect

Kết quả trả về không phải là behavior duy nhất. Một use case có thể:

- lưu aggregate;
- phát domain event;
- gửi command;
- tạo invoice;
- cập nhật trạng thái;
- gọi payment gateway;
- ghi audit log.

Một test migration nên xác định side effect nào là contract.

Ví dụ:

~~~java
@Test
void closingInvoicePersistsTheNewStateAndPublishesEvent() {
    var repository = new RecordingInvoiceRepository(openInvoice("INV-003"));
    var events = new RecordingEventPublisher();
    var service = new LegacyCloseInvoiceService(
        repository,
        events,
        fixedClock()
    );

    service.close("INV-003");

    assertThat(repository.savedIds()).containsExactly("INV-003");
    assertThat(events.events())
        .extracting(DomainEvent::type)
        .containsExactly("InvoiceClosed");
}
~~~

Nếu thứ tự event không phải contract, không nên assertion thứ tự. Nếu hệ thống downstream phụ thuộc thứ tự, thứ tự lại trở thành một behavior cần ghi nhận.

## Thời gian là một dependency

Code gọi trực tiếp now thường tạo test không ổn định:

~~~java
var due = LocalDate.now().plusDays(30);
~~~

Nếu logic migration phụ thuộc vào ngày hiện tại, nên đưa clock thành dependency:

~~~java
public final class DueDatePolicy {
    private final Clock clock;

    public DueDatePolicy(Clock clock) {
        this.clock = clock;
    }

    public LocalDate dueDate() {
        return LocalDate.now(clock).plusDays(30);
    }
}
~~~

Test:

~~~java
var clock = Clock.fixed(
    Instant.parse("2026-02-01T00:00:00Z"),
    ZoneOffset.UTC
);

assertThat(new DueDatePolicy(clock).dueDate())
    .isEqualTo(LocalDate.of(2026, 3, 3));
~~~

Trong migration, việc đưa clock thành dependency là một thay đổi cấu trúc nhỏ nhưng có giá trị lớn: nó tạo seam để ghi nhận behavior về thời gian.

## Múi giờ cũng là behavior

Không nên coi timezone là chi tiết kỹ thuật nếu nghiệp vụ dùng ngày địa phương.

Ví dụ:

~~~java
var zone = ZoneId.of("Asia/Ho_Chi_Minh");
var localDate = instant.atZone(zone).toLocalDate();
~~~

Nếu hệ thống cũ xác định "ngày làm việc" theo timezone của chi nhánh, test cần khóa timezone đó. Chuyển sang UTC chỉ vì thuận tiện có thể làm thay đổi ngày nghiệp vụ.

Một test tốt làm rõ cả instant và zone:

~~~java
@Test
void businessDateUsesBranchTimezone() {
    var instant = Instant.parse("2026-01-31T17:30:00Z");
    var zone = ZoneId.of("Asia/Ho_Chi_Minh");

    assertThat(instant.atZone(zone).toLocalDate())
        .isEqualTo(LocalDate.of(2026, 2, 1));
}
~~~

## Dữ liệu ngẫu nhiên

Randomness cũng cần một seam khi output của hệ thống phụ thuộc vào nó.

Thay vì:

~~~java
var token = UUID.randomUUID().toString();
~~~

có thể bọc dependency:

~~~java
public interface IdGenerator {
    UUID nextId();
}
~~~

Trong characterization test:

~~~java
var ids = new FixedIdGenerator(
    UUID.fromString("00000000-0000-0000-0000-000000000001")
);
~~~

Điều này không có nghĩa mọi random value phải bị cố định trong production. Chỉ input tạo ra sự khác biệt trong behavior của test mới cần được kiểm soát.

## Database: chọn đúng mức kiểm thử

Nếu test application service luôn gọi database thật, baseline có thể chậm và khó tái tạo. Nhưng nếu thay database bằng fake trong mọi trường hợp, có thể bỏ sót behavior của SQL, transaction hoặc mapping.

Nên chia:

~~~text
Application characterization
        |
        +--> fake/in-memory dependency
        |
        +--> adapter integration test
                    |
                    +--> real DB
                    +--> real schema
                    +--> real transaction
~~~

Characterization test bảo vệ hành vi của use case. Integration test bảo vệ adapter và hợp đồng với database.

Một migration có thể bắt đầu bằng in-memory repository để hiểu behavior của service, sau đó thêm integration test cho các truy vấn quan trọng.

## HTTP và external service

Nếu hệ thống cũ gọi payment gateway, shipping provider hoặc identity service, cần phân biệt hai loại behavior:

1. behavior của application khi gateway trả về một kết quả;
2. contract thật giữa adapter và gateway.

Ví dụ application test có thể dùng fake:

~~~java
var payment = new FakePaymentGateway(
    PaymentResult.approved("PAY-001")
);
~~~

Sau đó adapter có integration hoặc contract test riêng để xác minh request/response với hệ thống thật hoặc môi trường hợp đồng.

Không nên biến toàn bộ application characterization thành một test phụ thuộc mạng Internet. Test sẽ khó ổn định và khó xác định nguyên nhân khi thất bại.

## Message và event

Với hệ thống event-driven, behavior có thể là message được phát ra.

Ví dụ:

~~~java
@Test
void approvingPaymentPublishesTheExistingEventContract() {
    var publisher = new RecordingPublisher();
    var service = new LegacyPaymentService(repository, publisher);

    service.approve("PAY-001");

    assertThat(publisher.messages())
        .singleElement()
        .satisfies(message -> {
            assertThat(message.type()).isEqualTo("PaymentApproved");
            assertThat(message.paymentId()).isEqualTo("PAY-001");
        });
}
~~~

Nếu consumer bên ngoài đã phụ thuộc vào schema, field và semantics của event, đó là contract cần bảo vệ trong migration.

Trong DDD, domain event thường là một phần của model. Nhưng hệ thống cũ có thể đang phát integration event trực tiếp từ application service. Đừng giả định hai loại event có cùng contract chỉ vì tên giống nhau.

## Từ characterization test đến domain model

Khi nhiều test đã ổn định, hãy đọc chúng như một nguồn thông tin domain.

Ví dụ:

~~~text
Test: closeOpenInvoice
Test: closeAlreadyClosedInvoice
Test: closeMissingInvoice
Test: closeInvoiceAtBranchLocalTime
~~~

Từ đây có thể nhận ra:

- Invoice có lifecycle;
- OPEN và CLOSED là trạng thái có ý nghĩa;
- close là một domain operation;
- thời điểm đóng thuộc behavior;
- invoice không tồn tại và invoice đã đóng là hai trường hợp khác nhau.

Đây là lúc DDD bắt đầu có dữ liệu thực tế để hình thành model. Aggregate không nên được thiết kế chỉ từ tên bảng. Các invariant đã được quan sát trong behavior giúp xác định điều gì nên nằm trong aggregate boundary.

## Một ví dụ chuyển từ service thủ tục sang aggregate

Giả sử service cũ:

~~~java
public void closeInvoice(String id) {
    var row = invoiceTable.find(id);

    if (row.status().equals("OPEN")) {
        invoiceTable.updateStatus(id, "CLOSED");
        eventBus.publish(new InvoiceClosedEvent(id));
    }
}
~~~

Sau characterization test, có thể refactor dần thành:

~~~java
public final class Invoice {
    private InvoiceStatus status;

    public void close() {
        if (status == InvoiceStatus.CLOSED) {
            throw new InvoiceAlreadyClosed();
        }
        status = InvoiceStatus.CLOSED;
    }
}
~~~

Application service mới:

~~~java
public void closeInvoice(InvoiceId id) {
    var invoice = repository.get(id);
    invoice.close();
    repository.save(invoice);
    publisher.publish(new InvoiceClosed(id));
}
~~~

Characterization tests cũ trở thành hàng rào an toàn trong khi logic được chuyển sang domain model.

Điểm quan trọng là không phải test nào cũng phải giữ nguyên vị trí. Khi behavior đã được chuyển vào domain model, test có thể được tái cấu trúc để kiểm tra aggregate trực tiếp, miễn là behavior được bảo vệ đầy đủ.

## Refactor từng bước

Một chuỗi thay đổi an toàn có thể là:

~~~text
1. Characterize behavior
        |
2. Cố định dependency
        |
3. Tạo seam
        |
4. Tách pure logic
        |
5. Đưa invariant vào domain object
        |
6. Đổi persistence adapter
        |
7. Kiểm tra integration contract
        |
8. Xóa code cũ
~~~

Sau mỗi bước, chạy baseline test. Nếu test thất bại, trước tiên xác định:

- behavior đã thay đổi có chủ đích không;
- test đang sai hay implementation mới sai;
- dependency bên ngoài có thay đổi không;
- test có phụ thuộc thời gian hoặc dữ liệu không ổn định không.

Không nên sửa expected value chỉ để làm test xanh nếu chưa có quyết định rằng behavior mới là behavior mong muốn.

## Khi baseline test thất bại

Một failure trong migration là tín hiệu cần điều tra.

~~~text
Test failed
   |
   +--> Input khác?
   |
   +--> Environment khác?
   |
   +--> External dependency khác?
   |
   +--> Implementation mới sai?
   |
   +--> Behavior cũ được xác định lại?
~~~

Nếu behavior mới được business chấp thuận, hãy cập nhật test và ghi rõ lý do trong thay đổi. Nếu chưa có quyết định, giữ baseline cũ để tránh mất thông tin.

## Đừng biến bug thành contract một cách mù quáng

Characterization test ghi lại behavior hiện tại. Điều đó không có nghĩa mọi behavior hiện tại đều phải giữ.

Ví dụ:

~~~text
Hệ thống cũ:
  nếu số tiền âm -> vẫn lưu giao dịch

Business:
  đây là lỗi và phải chặn

Migration:
  test hiện tại ghi nhận behavior cũ
  |
  +--> quyết định nghiệp vụ xác nhận cần sửa
  |
  +--> test được thay đổi thành expected behavior mới
~~~

Sự khác biệt phải được chủ động quyết định. Điều nguy hiểm là một behavior bị thay đổi ngoài ý muốn nhưng không ai phát hiện.

## Test các bất biến quan trọng

Trong DDD, invariant là điều phải luôn đúng trong một phạm vi model.

Ví dụ với đơn hàng:

- tổng tiền không âm;
- dòng hàng phải có số lượng dương;
- đơn đã thanh toán không thể quay lại trạng thái chưa thanh toán;
- một payment không được capture hai lần;
- currency của các dòng phải phù hợp với order.

Characterization test giúp tìm invariant đang tồn tại:

~~~java
@Test
void paidOrderCannotBePaidAgain() {
    var order = paidOrder("ORD-001");

    var result = legacyPaymentService.pay(order);

    assertThat(result.status()).isEqualTo(ALREADY_PAID);
}
~~~

Sau đó invariant có thể được chuyển vào aggregate:

~~~java
public void pay(Payment payment) {
    if (status == OrderStatus.PAID) {
        throw new OrderAlreadyPaid();
    }
    status = OrderStatus.PAID;
}
~~~

Test sau refactor có thể nằm gần domain model hơn, nhưng ý nghĩa nghiệp vụ phải được giữ.

## Test và bounded context

Một hệ thống cũ thường có cùng một từ nhưng khác nghĩa ở các vùng khác nhau.

Ví dụ Customer có thể xuất hiện trong:

~~~text
Sales Context
  Customer = người mua và hạn mức thương mại

Billing Context
  Customer = chủ thể nhận hóa đơn và thông tin thuế

Support Context
  Customer = người liên hệ và lịch sử hỗ trợ
~~~

Characterization test cho từng use case giúp tránh tạo một model Customer khổng lồ để phục vụ mọi context.

Nếu test của Sales chỉ cần customerId, creditLimit và tier, đó là bằng chứng cho một contract cụ thể. Billing có thể có contract khác.

## Context map và migration

Khi thay thế một context cũ, test integration có thể đóng vai trò bằng chứng cho quan hệ giữa context cũ và context mới.

~~~mermaid
flowchart LR
    SalesOld[Sales cũ] -->|CustomerId + OrderPlaced| Billing[Billing]
    SalesNew[Sales mới] -->|CustomerId + OrderPlaced| Billing
    SalesNew -. kiểm thử contract .-> SalesOld
~~~

Mục tiêu không phải giữ implementation cũ mãi mãi. Mục tiêu là biết contract nào cần giữ trong thời gian chuyển đổi.

## Anti-Corruption Layer và kiểm thử

Khi hệ thống mới có model khác hệ thống cũ, Anti-Corruption Layer có thể chuyển đổi giữa hai model.

~~~text
Legacy Model
    |
    v
Legacy Adapter
    |
    v
Anti-Corruption Layer
    |
    v
New Domain Model
~~~

Test của ACL nên tập trung vào mapping:

~~~java
@Test
void legacyCustomerIsMappedToNewCustomerContract() {
    var legacy = new LegacyCustomer(
        "C-001",
        "GOLD",
        "ACTIVE"
    );

    var customer = mapper.map(legacy);

    assertThat(customer.id()).isEqualTo(new CustomerId("C-001"));
    assertThat(customer.tier()).isEqualTo(CustomerTier.GOLD);
    assertThat(customer.status()).isEqualTo(CustomerStatus.ACTIVE);
}
~~~

Nếu mapping thay đổi ngoài ý muốn, test sẽ phát hiện trước khi dữ liệu sai lan sang context mới.

## Contract test cho adapter

Một adapter cần có contract riêng khi nó giao tiếp với hệ thống khác.

Ví dụ:

~~~java
@Test
void paymentGatewaySendsTheRequiredContract() {
    var request = paymentAdapter.toRequest(
        new PaymentCommand("PAY-001", money("100000"))
    );

    assertThat(request.paymentId()).isEqualTo("PAY-001");
    assertThat(request.amount()).isEqualTo(100000);
    assertThat(request.currency()).isEqualTo("VND");
}
~~~

Nếu provider có môi trường contract test, có thể kiểm tra request/response thật ở tầng adapter. Application characterization test không cần biết JSON cụ thể của provider.

## Những test dễ gây hại trong migration

Một số test tạo cảm giác an toàn nhưng thực ra làm refactor khó hơn.

### Test private method

~~~java
assertThat(service.calculateInternalDiscount(...))
    .isEqualTo(...);
~~~

Nếu calculateInternalDiscount chỉ là implementation detail, test này khóa cấu trúc. Hãy kiểm tra behavior của public use case.

### Test thứ tự gọi nội bộ

~~~java
inOrder.verify(service).stepA();
inOrder.verify(service).stepB();
~~~

Thứ tự chỉ nên được kiểm tra khi caller thực sự quan tâm đến thứ tự đó.

### Mock mọi dependency

Một test với quá nhiều mock có thể xác nhận implementation thay vì behavior:

~~~text
mock A
mock B
mock C
mock D
    |
    v
verify 17 calls
~~~

Nếu một refactor đổi cấu trúc nhưng không đổi kết quả nghiệp vụ, test loại này thường vỡ hàng loạt.

### Snapshot tự cập nhật

Nếu test thất bại rồi tool tự động ghi output mới thành snapshot, baseline mất ý nghĩa.

### Test phụ thuộc thời gian thật

Test có thể pass lúc chạy nhưng fail ở ranh giới ngày, tháng hoặc timezone.

## Giảm flakiness

Baseline phải ổn định đủ để failure có ý nghĩa.

Các nguồn gây flakiness thường là:

- current time;
- timezone của máy;
- random UUID;
- thứ tự của HashMap;
- database dùng dữ liệu chung;
- network;
- retry;
- thread scheduling;
- file tạm;
- environment variable.

Chiến lược:

| Nguồn | Cách kiểm soát |
|---|---|
| Clock | inject Clock |
| Random | inject generator |
| Timezone | truyền ZoneId |
| UUID | fixed generator trong test |
| Database | fixture và transaction cô lập |
| HTTP | fake hoặc contract test |
| Message broker | test adapter riêng |
| Concurrency | kiểm tra invariant ở boundary phù hợp |
| File | thư mục tạm được cô lập |

Một test migration thất bại ngẫu nhiên không phải là baseline đáng tin cậy.

## Dữ liệu fixture

Fixture nên mô tả trường hợp nghiệp vụ:

~~~text
fixtures/
  invoice/
    open-invoice.json
    closed-invoice.json
    overdue-invoice.json
    missing-customer.json
~~~

Tên fixture nên giúp người đọc hiểu scenario. Tránh fixture khổng lồ không rõ field nào có ý nghĩa.

Một fixture tốt có thể được tái sử dụng cho characterization test và integration test nếu hai test cần cùng một business scenario.

## Golden Master cho batch

Với batch xử lý nhiều bản ghi, có thể ghi nhận:

~~~text
Input dataset
      |
      v
Legacy batch
      |
      v
Golden output
~~~

Sau khi có implementation mới:

~~~text
Input dataset
      |
      +----> Legacy batch ----> old output
      |
      +----> New batch -------> new output
                                   |
                                   v
                              diff report
~~~

Diff nên được chuẩn hóa nếu có field không mang ý nghĩa nghiệp vụ như generated timestamp hoặc execution id.

Ví dụ:

~~~java
String normalize(BatchResult result) {
    return result.items().stream()
        .map(this::removeExecutionMetadata)
        .sorted(comparing(Item::businessId))
        .map(this::serialize)
        .collect(joining("\n"));
}
~~~

Việc sort là hợp lý nếu thứ tự output không phải contract. Nếu thứ tự có ý nghĩa, không được normalize bằng cách sort.

## So sánh output có ý nghĩa

Không phải mọi khác biệt đều có cùng mức độ.

~~~text
Difference
   |
   +--> business field changed
   |       -> investigate
   |
   +--> timestamp changed
   |       -> normalize if non-contract
   |
   +--> generated id changed
   |       -> deterministic generator
   |
   +--> field order changed
           -> ignore only if order is non-semantic
~~~

Một lớp normalize tốt cần có quy tắc rõ ràng. Không nên normalize quá rộng đến mức che mất thay đổi nghiệp vụ.

## Quy trình migration có kiểm thử

Một quy trình thực tế:

### Bước 1: chọn một use case

Chọn một luồng có giá trị và giới hạn phạm vi.

### Bước 2: ghi nhận behavior

Chạy hệ thống hiện tại với các scenario đại diện.

### Bước 3: xác nhận baseline

Review expected result với người hiểu nghiệp vụ khi cần.

### Bước 4: tạo characterization tests

Biến kết quả đã xác nhận thành test tự động.

### Bước 5: ổn định dependency

Cố định clock, random, fixture và external boundary cần thiết.

### Bước 6: tạo seam

Đưa dependency ra interface hoặc adapter khi cần để test được.

### Bước 7: refactor nhỏ

Mỗi thay đổi nên có phạm vi đủ nhỏ để failure dễ truy nguyên.

### Bước 8: chạy baseline

Xác nhận behavior vẫn giữ nguyên.

### Bước 9: chuyển domain behavior

Đưa invariant và business rule vào entity, value object hoặc aggregate phù hợp.

### Bước 10: kiểm tra integration

Xác minh database, HTTP, broker và persistence contract ở tầng adapter.

### Bước 11: loại bỏ code cũ

Chỉ xóa implementation cũ sau khi đường đi mới có đủ bằng chứng.

## Ví dụ migration theo từng commit

Một chuỗi commit dễ review:

~~~text
commit 1: add characterization tests for closing invoices
commit 2: introduce Clock seam
commit 3: extract Invoice state transition
commit 4: introduce Invoice aggregate
commit 5: move repository mapping to adapter
commit 6: add integration test for persistence
commit 7: switch application service to new aggregate
commit 8: remove legacy close implementation
~~~

Mỗi commit có thể trả lời một câu hỏi cụ thể. Khi failure xảy ra, phạm vi điều tra nhỏ hơn.

## Test pyramid trong system migration

Không nên dùng một loại test cho mọi mục tiêu.

~~~text
              /\
             /  \
            / E2E \
           /------\
          / Adapter\
         / Contract \
        /-------------\
       / Use Case Tests \
      /-------------------\
     / Domain Unit Tests   \
    /_______________________\
~~~

Tùy hệ thống, tỷ lệ có thể khác nhau. Ý chính là:

- domain logic nên có test nhanh;
- application behavior nên có test qua use case boundary;
- adapter cần integration/contract test;
- E2E chỉ bao phủ các luồng quan trọng.

Characterization test có thể nằm ở nhiều tầng. Hãy đặt nó ở tầng cho phép quan sát behavior quan trọng với chi phí hợp lý.

## Khi nào nên dùng E2E?

E2E hữu ích để xác nhận luồng từ entry point đến output thật:

~~~text
HTTP
  |
Application
  |
Domain
  |
DB
~~~

Nhưng dùng E2E cho toàn bộ characterization sẽ làm baseline chậm và khó chẩn đoán. Nếu một test E2E thất bại, có thể không biết lỗi nằm ở controller, application service, domain logic, mapping hay database.

Nên dùng E2E cho một số behavior quan trọng, còn phần lớn baseline nên nằm ở boundary có tín hiệu rõ hơn.

## Khi nào test thật với database là cần thiết?

Nếu behavior phụ thuộc vào:

- unique constraint;
- transaction isolation;
- trigger;
- SQL aggregation;
- locking;
- database function;
- ORM mapping;
- index-dependent query;

thì fake repository không đủ bằng chứng. Cần integration test với database phù hợp.

Ví dụ invariant "hai invoice không được có cùng external reference" có thể được enforce bằng unique constraint. Test domain có thể bảo vệ business rule, nhưng test persistence phải chứng minh database thật cũng bảo vệ constraint.

## Transaction và migration

Một use case có thể yêu cầu:

~~~text
save aggregate
   +
publish outbox event
~~~

Nếu hai hành động phải nguyên tử, characterization test nên kiểm tra behavior quan sát được ở mức phù hợp. Sau đó integration test xác minh transaction boundary.

Nếu hệ thống dùng Transactional Outbox:

~~~text
Application
    |
    v
Transaction
  +------------------+
  | aggregate update |
  | outbox insert    |
  +------------------+
            |
            v
      Outbox publisher
~~~

Test không nên chỉ verify publisher.publish được gọi. Cần test persistence contract cho việc event được lưu trong cùng transaction nếu đó là invariant của hệ thống.

## Kiểm thử concurrency khi migration

Một số behavior chỉ xuất hiện khi có đồng thời:

- hai request cùng thanh toán;
- hai worker cùng lấy job;
- hai transaction cùng cập nhật aggregate.

Ví dụ:

~~~text
Request A ----\
               +--> same Invoice --> only one capture succeeds
Request B ----/
~~~

Nếu invariant phụ thuộc database locking hoặc optimistic version, unit test đơn luồng không đủ. Cần integration test hoặc concurrency test ở boundary thích hợp.

Characterization ở đây có thể bắt đầu từ một incident hoặc một scenario đã quan sát được, sau đó được biến thành test tái tạo được.

## Từ test sang ubiquitous language

Tên test có thể giúp phát hiện ngôn ngữ miền:

~~~text
closeInvoice
markOverdue
capturePayment
reserveStock
releaseReservation
approveCredit
~~~

Nếu trong code có nhiều tên gần nhau nhưng khác semantics, test giúp làm rõ chúng.

Ví dụ:

~~~text
cancelOrder != rejectOrder
expireReservation != releaseReservation
authorizePayment != capturePayment
~~~

Không nên gộp chúng chỉ vì đều thay đổi một field status.

DDD cần ngôn ngữ phản ánh hành vi nghiệp vụ. Characterization tests là một nguồn thực tế để tìm ra những động từ và trạng thái có ý nghĩa.

## Test trạng thái thay vì field

Một hệ thống cũ có thể biểu diễn state bằng string:

~~~java
status = "PAID";
~~~

Test tốt nên nói:

~~~java
assertThat(order.isPaid()).isTrue();
~~~

hoặc kiểm tra behavior:

~~~java
assertThatThrownBy(order::pay)
    .isInstanceOf(OrderAlreadyPaid.class);
~~~

Khi refactor sang enum hoặc state object, test ít bị ảnh hưởng nếu contract vẫn giữ nguyên.

## Một bảng decision table cho baseline

Decision table giúp tránh bỏ sót nhánh:

| Invoice tồn tại | Trạng thái | Hành động | Kết quả |
|---|---|---|---|
| Không | - | close | InvoiceNotFound |
| Có | OPEN | close | CLOSED |
| Có | CLOSED | close | ALREADY_CLOSED |
| Có | CANCELLED | close | theo behavior đã xác nhận |

Nếu hàng cuối chưa được xác định, đó là câu hỏi nghiệp vụ cần làm rõ trước khi khóa expected behavior.

## Test theo scenario

Một scenario có thể mô tả:

~~~text
Given invoice INV-001 is OPEN
And current business time is 2026-01-15 10:00
When the application closes INV-001
Then INV-001 becomes CLOSED
And closedAt is 2026-01-15 10:00
And InvoiceClosed is emitted
~~~

Trong code:

~~~java
@Test
void closingAnOpenInvoiceRecordsTimeAndPublishesEvent() {
    givenOpenInvoice("INV-001");
    givenBusinessTime("2026-01-15T10:00:00");

    closeInvoice("INV-001");

    thenInvoiceIsClosed("INV-001");
    thenClosedAtIs("2026-01-15T10:00:00");
    thenEventWasPublished("InvoiceClosed");
}
~~~

Style Given–When–Then đặc biệt hữu ích trong migration vì test vừa là executable specification vừa là bằng chứng về behavior.

## Khi refactor làm test vỡ vì cấu trúc

Có hai loại failure:

~~~text
Failure A:
expected total = 100
actual total   = 120
~~~

Đây có thể là behavior change.

~~~text
Failure B:
verify legacyHelper.calculateDiscount()
~~~

Đây có thể chỉ là implementation change.

Failure B thường là tín hiệu test nên được viết lại để kiểm tra output hoặc business side effect.

Không phải mọi test failure đều có nghĩa implementation mới sai.

## Dấu hiệu baseline chưa đủ tốt

Baseline cần được cải thiện nếu:

- test chỉ kiểm tra HTTP 200;
- expected value được tạo bằng cùng implementation đang test;
- snapshot bị cập nhật tự động;
- test chạy không ổn định;
- mọi dependency đều mock;
- không có case lỗi;
- không có case biên;
- không kiểm tra side effect quan trọng;
- test biết quá nhiều private method;
- không có người hiểu nghiệp vụ review behavior quan trọng.

Một test có thể pass 100% nhưng vẫn không bảo vệ behavior hữu ích.

## Dấu hiệu baseline quá chặt

Baseline quá chặt khi:

- đổi tên private method làm hàng chục test vỡ;
- đổi implementation collection làm test vỡ dù output giống nhau;
- thay framework persistence làm toàn bộ unit test vỡ;
- mock interaction phải cập nhật sau mọi refactor;
- test phụ thuộc thứ tự gọi không có ý nghĩa nghiệp vụ.

Mục tiêu là bảo vệ behavior, không đóng băng code.

## Checklist trước khi bắt đầu refactor

- [ ] Đã xác định entry point của use case.
- [ ] Đã xác định input và output quan sát được.
- [ ] Đã xác định side effect quan trọng.
- [ ] Đã kiểm soát clock nếu thời gian ảnh hưởng behavior.
- [ ] Đã kiểm soát random nếu random ảnh hưởng output.
- [ ] Đã có fixture tái tạo được.
- [ ] Đã có happy path.
- [ ] Đã có nhánh lỗi quan trọng.
- [ ] Đã có case biên.
- [ ] Đã xác định behavior cần giữ.
- [ ] Đã xác định behavior đang chờ quyết định nghiệp vụ.
- [ ] Baseline chạy ổn định.

## Checklist trong khi refactor

- [ ] Mỗi thay đổi có phạm vi nhỏ.
- [ ] Baseline được chạy sau thay đổi quan trọng.
- [ ] Failure được phân loại trước khi sửa test.
- [ ] Không cập nhật expected value chỉ để làm test xanh.
- [ ] Invariant được chuyển dần vào domain model.
- [ ] Adapter contract được kiểm tra ở boundary phù hợp.
- [ ] Persistence behavior có integration test khi cần.
- [ ] Event/message contract được bảo vệ nếu downstream phụ thuộc.

## Checklist trước khi loại bỏ legacy code

- [ ] Use case mới đạt cùng behavior đã xác nhận.
- [ ] Domain invariant có test phù hợp.
- [ ] Persistence adapter có test phù hợp.
- [ ] External contract có test phù hợp.
- [ ] Các behavior thay đổi có quyết định nghiệp vụ rõ ràng.
- [ ] Không còn caller cần implementation cũ.
- [ ] Monitoring hoặc logging cần thiết đã được xem xét.

## Ví dụ hoàn chỉnh: từ baseline đến aggregate

Giả sử behavior cũ:

~~~text
Given order ORD-001 is NEW
And it contains one item worth 100000 VND
When the order is paid
Then the status becomes PAID
And PaymentCaptured is emitted
And paying again is rejected
~~~

Baseline:

~~~java
@Test
void newOrderCanBePaid() {
    var repository = new InMemoryOrderRepository(newOrder("ORD-001"));
    var publisher = new RecordingPublisher();
    var service = new LegacyPaymentService(repository, publisher);

    service.pay("ORD-001");

    assertThat(repository.get("ORD-001").status())
        .isEqualTo(OrderStatus.PAID);
    assertThat(publisher.types())
        .containsExactly("PaymentCaptured");
}

@Test
void paidOrderCannotBePaidAgain() {
    var repository = new InMemoryOrderRepository(paidOrder("ORD-001"));
    var publisher = new RecordingPublisher();
    var service = new LegacyPaymentService(repository, publisher);

    assertThatThrownBy(() -> service.pay("ORD-001"))
        .isInstanceOf(OrderAlreadyPaid.class);

    assertThat(publisher.types()).isEmpty();
}
~~~

Sau đó model:

~~~java
public final class Order {
    private OrderStatus status;

    public void pay() {
        if (status == OrderStatus.PAID) {
            throw new OrderAlreadyPaid();
        }
        status = OrderStatus.PAID;
    }
}
~~~

Application service:

~~~java
public final class PayOrderHandler {
    private final OrderRepository repository;
    private final DomainEventPublisher publisher;

    public void handle(OrderId id) {
        var order = repository.get(id);
        order.pay();
        repository.save(order);
        publisher.publish(new PaymentCaptured(id));
    }
}
~~~

Baseline test có thể được di chuyển dần từ LegacyPaymentService sang PayOrderHandler rồi Order. Điều cần bảo vệ là scenario và invariant, không phải tên lớp cũ.

## Một mô hình migration tổng thể

~~~mermaid
flowchart TD
    A[Legacy behavior] --> B[Characterization tests]
    B --> C[Ổn định clock / random / fixtures]
    C --> D[Định nghĩa seams]
    D --> E[Refactor nhỏ]
    E --> F{Behavior còn giống?}
    F -->|Có| E
    F -->|Không| G[Điều tra difference]
    G --> H{Thay đổi có chủ đích?}
    H -->|Không| E
    H -->|Có| I[Cập nhật model và test]
    I --> E
    E --> J[New domain model]
    J --> K[Integration / contract tests]
    K --> L[Loại bỏ legacy path]
~~~

Điểm quan trọng trong vòng lặp này là bước Điều tra difference. Một diff không nên tự động được coi là regression hoặc tự động được chấp nhận. Nó là tín hiệu để xác định ý nghĩa nghiệp vụ.

## Kết nối với các tactical pattern của DDD

Kiểm thử trước migration có thể hỗ trợ từng pattern:

| Pattern | Điều test giúp làm rõ |
|---|---|
| Entity | identity và lifecycle |
| Value Object | equality và invariant |
| Aggregate | boundary và consistency rules |
| Repository | contract lưu/đọc aggregate |
| Domain Service | business rule không thuộc một entity |
| Domain Event | fact đã xảy ra và payload cần thiết |
| Application Service | orchestration và transaction boundary |
| Factory | điều kiện tạo object hợp lệ |

Ví dụ một Money mới có thể được thiết kế từ behavior đã quan sát:

~~~java
var total = money("100000");
var discount = money("10000");

assertThat(total.subtract(discount))
    .isEqualTo(money("90000"));
~~~

Nếu hệ thống cũ có rule currency phải giống nhau, characterization test có thể chỉ ra invariant để đưa vào value object:

~~~java
assertThatThrownBy(() ->
    money("100000", "VND")
        .add(money("10", "USD"))
).isInstanceOf(CurrencyMismatch.class);
~~~

## Không dùng test để thay thế domain discovery

Test là bằng chứng kỹ thuật về behavior. Nó không tự trả lời mọi câu hỏi:

- tại sao business muốn rule này;
- rule còn đúng trong tương lai không;
- hai context có cùng nghĩa của một thuật ngữ không;
- behavior cũ là chủ đích hay bug;
- aggregate boundary nào là phù hợp nhất.

Những câu hỏi đó cần được thảo luận với người hiểu nghiệp vụ. Test ghi nhận kết quả của quyết định và giúp bảo vệ quyết định đó trong quá trình thay đổi code.

## Một nguyên tắc thực hành

Trước khi refactor, hãy cố gắng biến câu:

> "Chúng ta nghĩ hệ thống đang làm như vậy."

thành:

> "Chúng ta có test tái hiện được hành vi này."

Sau khi refactor, mục tiêu tiếp theo là:

> "Model mới biểu diễn được quy tắc này bằng ngôn ngữ miền rõ ràng."

Khi hai điều này cùng tồn tại, migration có một đường đi rõ hơn: behavior cũ được quan sát và bảo vệ, trong khi cấu trúc mới có thể tiến dần về domain model mà không phải đoán xem mỗi thay đổi đã làm mất điều gì.

## Tóm tắt

Bảo vệ hành vi cũ bằng kiểm thử là một bước kỹ thuật quan trọng trước khi tái cấu trúc hệ thống. Characterization test tạo baseline từ behavior thực tế; Golden Master và Approval Test hữu ích với output lớn; fake, seam và fixed clock giúp kiểm soát dependency; integration và contract test bảo vệ những behavior phụ thuộc database hoặc hệ thống ngoài.

Trong quá trình DDD migration, các test này còn giúp phát hiện invariant, lifecycle, domain event và ranh giới context đang tồn tại trong hệ thống cũ. Sau khi behavior đã được xác nhận, có thể đưa từng quy tắc vào entity, value object, aggregate, repository hoặc application service phù hợp.

Điều cần giữ xuyên suốt quá trình là ý nghĩa của behavior đã được xác nhận. Khi một behavior có chủ đích thay đổi, quyết định đó cần được thể hiện rõ trong test và model mới. Khi một behavior không có chủ đích thay đổi, baseline phải phát hiện ra nó.
