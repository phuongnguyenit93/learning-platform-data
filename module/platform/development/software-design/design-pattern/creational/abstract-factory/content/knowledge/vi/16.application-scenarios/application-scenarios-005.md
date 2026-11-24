# Bộ adapter môi trường thật và môi trường mô phỏng phục vụ kiểm thử

## 1. Tình huống: một ứng dụng, hai môi trường thực thi

Xét ứng dụng **đặt phòng**: khi người dùng xác nhận đặt phòng, hệ thống cần thực hiện hai thao tác bên ngoài logic nghiệp vụ:

1. **Thu tiền** thông qua hệ thống thanh toán.
2. **Gửi thông báo** xác nhận sau khi thu tiền thành công.

Trong môi trường chạy thật (*production/live*), hai thao tác này có thể đi qua SDK hoặc API của nhà cung cấp. Trong môi trường mô phỏng (*simulation/test*), bài kiểm thử cần quan sát giao dịch và thông báo **mà không thật sự trừ tiền hay gửi email**.

Nếu lớp nghiệp vụ tự gọi SDK thật:

~~~java
class BookingService {
    void confirmBooking(String bookingId, long amountCents, String email) {
        // Mã minh họa sự phụ thuộc trực tiếp vào bên ngoài.
        String receiptId = paymentSdk.capture(bookingId, amountCents);
        mailSdk.dispatch(email, "Xác nhận " + bookingId, receiptId);
    }
}
~~~

thì kiểm thử `BookingService` có thể phải kết nối dịch vụ bên ngoài, cần tài khoản và dữ liệu cấu hình thật, chạy chậm hoặc gây tác dụng phụ ngoài ý muốn. Nếu thêm các nhánh `if (testing)` vào từng điểm gọi SDK, mã nghiệp vụ lại phải biết nó đang chạy trong môi trường nào.

**Abstract Factory** là một mẫu thuộc nhóm **Creational Design Patterns** giúp giải quyết phần lựa chọn **cả một họ đối tượng liên quan**. Ở tình huống này, ta có thể định nghĩa hai họ adapter:

- **Họ Live:** adapter thanh toán và adapter thông báo cùng kết nối các dịch vụ thật đã cấu hình.
- **Họ Simulation:** adapter thanh toán và adapter thông báo cùng lưu vết thao tác trong bộ nhớ để kiểm thử.

Client chỉ nhận **một factory** và sử dụng hai sản phẩm thông qua interface chung. Mục tiêu là chuyển đổi môi trường bằng việc cấp factory phù hợp, đồng thời bảo đảm bài kiểm thử không vô tình gọi một sản phẩm thật lẫn với sản phẩm mô phỏng.

> Trong bài này, «môi trường thật» có nghĩa là adapter được nối với **client của nhà cung cấp bên ngoài**. Ví dụ Java tự chạy chỉ dùng họ Simulation; các adapter Live được định nghĩa để minh họa điểm tích hợp và cần được cấp client SDK/API thực khi triển khai sản phẩm.

## 2. Xác định chính xác họ sản phẩm trong bài toán

Đây là trường hợp Abstract Factory vì client có **nhiều loại dependency bên ngoài** cùng cần chọn theo **một chế độ thực thi**.

| Vai trò sản phẩm | Họ Live | Họ Simulation |
| --- | --- | --- |
| Thu tiền | `LivePaymentAdapter` gọi client thanh toán | `FakePaymentAdapter` tạo mã biên nhận giả, ghi nhận lệnh |
| Gửi thông báo | `LiveMessageAdapter` gọi client thông báo | `FakeMessageAdapter` lưu nội dung thông báo vào bộ nhớ |
| Factory cung cấp họ | `LiveIntegrationFactory` | `SimulatedIntegrationFactory` |
| Client sử dụng | `BookingService` | **Cùng** `BookingService` |

**Loại sản phẩm** là `PaymentPort` và `MessagePort`. Chúng có trách nhiệm riêng nên không phải cùng triển khai một interface.

**Họ sản phẩm** là cặp các biến thể tương ứng với chế độ chạy. Với họ Simulation, cả thanh toán và thông báo đều được mô phỏng. Với họ Live, cả hai đều hướng tới những dịch vụ thực được cấp bởi cấu hình production.

Điều kiện phù hợp của Abstract Factory ở đây là **quy tắc phối hợp cấp môi trường**: đối với kiểm thử hoàn toàn cách ly, các adapter liên quan không được tạo tác dụng phụ thật; đối với môi trường thật, cả bộ adapter phải được cấu hình nhất quán theo hệ thống mà ứng dụng dự kiến sử dụng.

### 2.1. Phân biệt hai tầng trừu tượng

**Product interfaces** mô tả hành vi mà nghiệp vụ cần:

~~~java
interface PaymentPort {
    String capture(String bookingId, long amountCents);
}

interface MessagePort {
    void sendConfirmation(
        String email,
        String bookingId,
        String receiptId
    );
}
~~~

**Abstract Factory** mô tả cách yêu cầu tạo các sản phẩm đó:

~~~java
interface IntegrationFactory {
    PaymentPort createPaymentPort();
    MessagePort createMessagePort();
}
~~~

`BookingService` không cần biết lớp thực thi là `LivePaymentAdapter` hay `FakePaymentAdapter`. Nó chỉ cần các hợp đồng `PaymentPort` và `MessagePort`.

**Lưu ý:** interface `IntegrationFactory` không cần một phương thức `isTest()` để client tự phân nhánh. Nếu client dùng `if (factory.isTest())` để thay đổi nghiệp vụ, trách nhiệm lựa chọn môi trường đã bị đưa trở lại nơi cần tránh.

### 2.2. Adapter và Abstract Factory giải quyết hai vấn đề khác nhau

Tên các lớp có chữ *Adapter* vì chúng **thích ứng API của hệ thống ngoài** về interface mà nghiệp vụ sử dụng:

- SDK thanh toán có phương thức `provider.captureCharge(...)`; adapter trình bày nó dưới hợp đồng `PaymentPort.capture(...)`.
- SDK gửi thư có API `provider.dispatch(...)`; adapter trình bày nó dưới hợp đồng `MessagePort.sendConfirmation(...)`.

Đây là vai trò của **Adapter pattern** (mẫu cấu trúc).

**Abstract Factory** không tự chuyển đổi API của SDK. Nó chịu trách nhiệm **tạo và cấp đúng bộ adapter** theo môi trường. Hai mẫu có thể phối hợp: *Adapter giúp các dependency có cùng hợp đồng, Abstract Factory giúp lựa chọn họ triển khai của các hợp đồng đó.*

## 3. Cấu trúc và hướng phụ thuộc

~~~mermaid
flowchart TB
    Root["Composition root: chọn chế độ chạy"] --> Factory["IntegrationFactory"]
    Service["BookingService"] --> Factory
    Service --> Payment["PaymentPort"]
    Service --> Message["MessagePort"]
    Live["LiveIntegrationFactory"] -. "implements" .-> Factory
    Sim["SimulatedIntegrationFactory"] -. "implements" .-> Factory
    Live --> LP["LivePaymentAdapter"]
    Live --> LM["LiveMessageAdapter"]
    Sim --> FP["FakePaymentAdapter"]
    Sim --> FM["FakeMessageAdapter"]
    LP -. "implements" .-> Payment
    FP -. "implements" .-> Payment
    LM -. "implements" .-> Message
    FM -. "implements" .-> Message
    LP --> SDK1["Payment Provider Client"]
    LM --> SDK2["Message Provider Client"]
~~~

Trong cấu trúc này:

1. `BookingService` là **client** của Abstract Factory, hoặc có thể được khởi tạo bằng các sản phẩm do factory cấp.
2. `PaymentPort` và `MessagePort` là **Abstract Products**.
3. Các adapter `Live...` và `Fake...` là **Concrete Products**.
4. Hai lớp `...IntegrationFactory` là **Concrete Factories**.
5. **Composition root** quyết định dùng factory nào dựa trên cấu hình môi trường và chính sách cho phép.

Quan hệ phụ thuộc hướng về các interface ổn định. Những chi tiết về SDK, URL, tài khoản bên ngoài hoặc fake phục vụ kiểm thử ở phía cài đặt.

Một quy tắc thiết kế có ích là: **client không tự tạo adapter và không tự đọc tên môi trường**. Quyết định lựa chọn nên nằm ở nơi lắp ghép ứng dụng, trước khi logic nghiệp vụ bắt đầu thực thi.

## 4. Xác định hợp đồng chung trước khi hiện thực adapter

Để thay thế được họ Live bằng Simulation, hai họ phải thống nhất các hành vi mà nghiệp vụ trông đợi.

### 4.1. Hợp đồng PaymentPort

Trong ví dụ:

~~~java
String receiptId = payment.capture(bookingId, amountCents);
~~~

- `bookingId` định danh nghiệp vụ của lần đặt phòng.
- `amountCents` là số tiền nguyên theo đơn vị nhỏ nhất của một đồng tiền minh họa, tránh sai số của `double`.
- Khi thanh toán thành công, phương thức trả về **mã biên nhận không rỗng**.
- Khi thất bại, phương thức báo lỗi; không trả về biên nhận «thành công» giả.
- Hợp đồng của hệ thống thật còn cần làm rõ **idempotency**, timeout, xử lý mã lỗi, khả năng retry và đối soát.

Trong fake, mã biên nhận có thể có tiền tố `SIM-` để không nhầm với biên nhận thực, nhưng client **không được dựa vào tiền tố này để phân nhánh nghiệp vụ**. Client chỉ xem đây là một chuỗi biên nhận hợp lệ theo hợp đồng.

### 4.2. Hợp đồng MessagePort

~~~java
message.sendConfirmation(email, bookingId, receiptId);
~~~

Client gọi phương thức này **sau khi thu tiền thành công**. Trong môi trường thật, adapter chuyển yêu cầu thành thao tác gửi của nhà cung cấp; trong simulation, adapter chỉ **ghi nhận** yêu cầu gửi.

Cần thống nhất ý nghĩa «gửi thành công»: dịch vụ ngoài đã nhận yêu cầu, thư đã vào hàng đợi hay người nhận thực sự đã nhận? Ví dụ đơn giản chỉ mô hình hóa một lời gọi không ném lỗi. Ứng dụng production phải xác định trạng thái giao hàng và cơ chế retry riêng.

### 4.3. Tính tương thích giữa hai loại sản phẩm

Factory giúp nhóm hai adapter theo môi trường, nhưng điều đó **không tự bảo đảm một giao dịch phân tán hoàn tất nguyên tử**. Thu tiền có thể thành công trong khi gửi thông báo thất bại. Khi ấy, các chiến lược như retry có kiểm soát, outbox, bù trừ hoặc điều phối trạng thái cần được thiết kế ở tầng nghiệp vụ và hạ tầng.

Vì vậy, không nên nhầm **tính nhất quán của họ sản phẩm** với **tính nguyên tử của quy trình giao dịch**. Abstract Factory giải quyết cách tạo adapter phù hợp; nó không thay thế xử lý lỗi của các hệ thống bên ngoài.

## 5. Java tự chạy: factory Live và Simulation

Ví dụ sau đầy đủ để lưu trong một tệp `EnvironmentAdapterDemo.java`. Mã chạy với JDK thông thường, không cần thư viện ngoài. Chạy chương trình sẽ thực hiện **hai tình huống kiểm thử trên fake**, không gọi mạng, không trừ tiền và không gửi email.

Họ Live trong cùng tệp gồm những adapter **ủy quyền cho interface của client nhà cung cấp**. Khi tích hợp thật, ứng dụng cung cấp implementation của `PaymentProviderClient` và `MessageProviderClient` dựa trên SDK tương ứng. Ví dụ này không giả vờ có một SDK đã được kết nối.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

// ===== 1. Abstract Products: API mà nghiệp vụ cần =====

interface PaymentPort {
    String capture(String bookingId, long amountCents);
}

interface MessagePort {
    void sendConfirmation(
        String email,
        String bookingId,
        String receiptId
    );
}

// ===== 2. Abstract Factory =====

interface IntegrationFactory {
    PaymentPort createPaymentPort();
    MessagePort createMessagePort();
}

// ===== 3. Các client nhà cung cấp cần nối vào ở môi trường thật =====
// Hai interface này biểu diễn ranh giới SDK/API bên ngoài,
// không được BookingService sử dụng trực tiếp.

interface PaymentProviderClient {
    String captureCharge(String bookingId, long amountCents);
}

interface MessageProviderClient {
    void dispatch(
        String destination,
        String subject,
        String body
    );
}

// ===== 4. Họ Live: adapter ủy quyền cho client của nhà cung cấp =====

class LivePaymentAdapter implements PaymentPort {
    private final PaymentProviderClient provider;

    LivePaymentAdapter(PaymentProviderClient provider) {
        this.provider = Objects.requireNonNull(provider);
    }

    @Override
    public String capture(String bookingId, long amountCents) {
        return provider.captureCharge(bookingId, amountCents);
    }
}

class LiveMessageAdapter implements MessagePort {
    private final MessageProviderClient provider;

    LiveMessageAdapter(MessageProviderClient provider) {
        this.provider = Objects.requireNonNull(provider);
    }

    @Override
    public void sendConfirmation(
            String email,
            String bookingId,
            String receiptId) {
        provider.dispatch(
            email,
            "Xác nhận đặt phòng " + bookingId,
            "Biên nhận: " + receiptId
        );
    }
}

class LiveIntegrationFactory implements IntegrationFactory {
    private final PaymentProviderClient paymentClient;
    private final MessageProviderClient messageClient;

    LiveIntegrationFactory(
            PaymentProviderClient paymentClient,
            MessageProviderClient messageClient) {
        this.paymentClient = Objects.requireNonNull(paymentClient);
        this.messageClient = Objects.requireNonNull(messageClient);
    }

    @Override
    public PaymentPort createPaymentPort() {
        return new LivePaymentAdapter(paymentClient);
    }

    @Override
    public MessagePort createMessagePort() {
        return new LiveMessageAdapter(messageClient);
    }
}

// ===== 5. Họ Simulation: các fake lưu vết trong bộ nhớ =====

class FakePaymentAdapter implements PaymentPort {
    private final List<String> recordedCaptures = new ArrayList<>();
    private boolean rejectNext;

    @Override
    public String capture(String bookingId, long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException(
                "Số tiền phải lớn hơn 0"
            );
        }

        if (rejectNext) {
            rejectNext = false;
            throw new IllegalStateException(
                "Simulated payment rejection"
            );
        }

        recordedCaptures.add(bookingId + ":" + amountCents);
        return "SIM-" + bookingId;
    }

    void rejectNextCapture() {
        rejectNext = true;
    }

    List<String> captures() {
        return Collections.unmodifiableList(recordedCaptures);
    }
}

class FakeMessageAdapter implements MessagePort {
    private final List<String> recordedMessages = new ArrayList<>();

    @Override
    public void sendConfirmation(
            String email,
            String bookingId,
            String receiptId) {
        // Chỉ ghi nhận ý định gửi, không gọi dịch vụ ngoài.
        recordedMessages.add(
            email + "|" + bookingId + "|" + receiptId
        );
    }

    List<String> messages() {
        return Collections.unmodifiableList(recordedMessages);
    }
}

// Một factory Simulation duy trì cùng các fake để test đọc kết quả.
class SimulatedIntegrationFactory implements IntegrationFactory {
    private final FakePaymentAdapter payment =
            new FakePaymentAdapter();
    private final FakeMessageAdapter message =
            new FakeMessageAdapter();

    @Override
    public PaymentPort createPaymentPort() {
        return payment;
    }

    @Override
    public MessagePort createMessagePort() {
        return message;
    }

    // Những phương thức kiểm tra này nằm ở concrete factory
    // dành cho test, không nằm trong IntegrationFactory.
    FakePaymentAdapter recordedPayments() {
        return payment;
    }

    FakeMessageAdapter recordedMessages() {
        return message;
    }
}

// ===== 6. Business client: không biết SDK hay fake =====

class BookingService {
    private final PaymentPort payment;
    private final MessagePort message;

    BookingService(IntegrationFactory factory) {
        Objects.requireNonNull(factory);
        this.payment = factory.createPaymentPort();
        this.message = factory.createMessagePort();
    }

    String completeBooking(
            String bookingId,
            long amountCents,
            String email) {
        // Thất bại ở capture() sẽ làm lời gọi ném lỗi;
        // khi đó sendConfirmation() không được thực thi.
        String receiptId = payment.capture(bookingId, amountCents);
        message.sendConfirmation(email, bookingId, receiptId);
        return receiptId;
    }
}

// ===== 7. Chương trình mô phỏng và các kiểm tra thủ công =====

public class EnvironmentAdapterDemo {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        SimulatedIntegrationFactory simulation =
                new SimulatedIntegrationFactory();

        BookingService service = new BookingService(simulation);

        // Tình huống 1: thanh toán mô phỏng thành công.
        String receipt = service.completeBooking(
            "BK-101", 150_000L, "guest@example.test"
        );

        require("SIM-BK-101".equals(receipt),
            "Phải trả về biên nhận mô phỏng");
        require(simulation.recordedPayments().captures().size() == 1,
            "Phải ghi nhận đúng một lần thu tiền");
        require(
            "BK-101:150000".equals(
                simulation.recordedPayments().captures().get(0)
            ),
            "Phải ghi nhận đúng mã đặt phòng và số tiền"
        );
        require(simulation.recordedMessages().messages().size() == 1,
            "Phải ghi nhận đúng một thông báo");
        require(
            "guest@example.test|BK-101|SIM-BK-101".equals(
                simulation.recordedMessages().messages().get(0)
            ),
            "Thông báo phải chứa đúng biên nhận"
        );

        // Tình huống 2: fake mô phỏng thanh toán bị từ chối.
        simulation.recordedPayments().rejectNextCapture();

        boolean rejected = false;
        try {
            service.completeBooking(
                "BK-102", 100_000L, "guest@example.test"
            );
        } catch (IllegalStateException ex) {
            rejected = "Simulated payment rejection"
                    .equals(ex.getMessage());
        }

        require(rejected, "Phải phát hiện thanh toán bị từ chối");
        require(simulation.recordedMessages().messages().size() == 1,
            "Không được ghi nhận thông báo thứ hai");
        require(simulation.recordedPayments().captures().size() == 1,
            "Không được ghi nhận khoản thu thất bại");

        System.out.println("PASS: simulation success and rejection");
        System.out.println("Receipts recorded: "
            + simulation.recordedPayments().captures().size());
        System.out.println("Messages recorded: "
            + simulation.recordedMessages().messages().size());
    }
}
~~~

### 5.1. Chạy ví dụ

Lưu tệp bằng UTF-8 rồi chạy:

~~~bash
javac -encoding UTF-8 EnvironmentAdapterDemo.java
java EnvironmentAdapterDemo
~~~

Kết quả mong đợi:

~~~text
PASS: simulation success and rejection
Receipts recorded: 1
Messages recorded: 1
~~~

Dù chương trình có định nghĩa `LivePaymentAdapter` và `LiveMessageAdapter`, `main()` **chỉ chọn `SimulatedIntegrationFactory`**. Nó không khởi tạo `LiveIntegrationFactory`, không có client SDK thực, không mở kết nối mạng và không gửi thông báo bên ngoài.

### 5.2. Tại sao test có thể kiểm tra hành vi nghiệp vụ?

Khi gọi `service.completeBooking(...)`, `BookingService` sử dụng đúng **hai interface mà production cũng sử dụng**. Trong lần gọi thành công:

1. `FakePaymentAdapter.capture(...)` nhận mã đặt phòng và số tiền.
2. Fake ghi lại lệnh thu tiền rồi trả biên nhận `SIM-BK-101`.
3. `BookingService` truyền biên nhận đó sang `FakeMessageAdapter`.
4. Fake thông báo ghi nhận dữ liệu, không gửi ra bên ngoài.
5. Test đọc danh sách từ concrete factory **chỉ ở phía kiểm thử** và xác nhận chuỗi lệnh đúng.

Ở lần gọi bị từ chối, fake thanh toán ném `IllegalStateException`. Luồng thực thi rời khỏi `completeBooking()` trước khi gọi `sendConfirmation()`, vì vậy số thông báo được ghi nhận không tăng.

**Điểm quan trọng:** kiểm thử đối chiếu **hành vi nghiệp vụ qua các port**. Nó không chứng minh client thanh toán thật hoặc hệ thống gửi thư thật luôn có cùng kết quả. Những ranh giới bên ngoài cần một tầng kiểm thử tích hợp riêng.

### 5.3. Vì sao fake có phương thức quan sát riêng?

`SimulatedIntegrationFactory.recordedPayments()` và `recordedMessages()` trả về concrete fake để test quan sát. Đây là API dành cho phép kiểm thử, **không xuất hiện trong `IntegrationFactory`**.

Nếu thêm `getCapturedPayments()` vào Abstract Factory chung chỉ vì kiểm thử, factory Live sẽ phải hỗ trợ một phương thức không có ý nghĩa đối với production. Cách chia trên giữ interface chính nhỏ, còn tiện ích kiểm thử nằm ở đối tượng cụ thể do test tạo ra.

### 5.4. Vòng đời fake ảnh hưởng trực tiếp tới tính đúng của test

Trong ví dụ, `SimulatedIntegrationFactory` tạo một `FakePaymentAdapter` và một `FakeMessageAdapter` rồi **trả lại cùng các instance** mỗi lần được gọi. Nhờ vậy `BookingService` ghi dữ liệu vào đúng các fake mà test đang quan sát.

Nếu factory tạo fake mới ở mỗi lần gọi và test lại gọi thêm `factory.createPaymentPort()` để kiểm tra, test có thể nhìn nhầm vào một đối tượng trống. Vì vậy cần ghi rõ **phạm vi chia sẻ trạng thái** của các sản phẩm.

Để kiểm thử cách ly, nên tạo **factory mới cho từng test case** nếu chúng không được thiết kế để dùng chung trạng thái. Fake trong ví dụ dùng `ArrayList` và không an toàn cho truy cập đồng thời; khi hệ thống chạy đa luồng, fake cũng phải mô phỏng được yêu cầu đồng bộ cần thiết hoặc được bảo vệ bằng cơ chế phù hợp.

## 6. Lắp ghép môi trường thật và lựa chọn factory

Lớp `LiveIntegrationFactory` ở trên nhận hai client:

~~~java
LiveIntegrationFactory(
    PaymentProviderClient paymentClient,
    MessageProviderClient messageClient
)
~~~

Trong sản phẩm thật, **composition root** cần tạo hoặc nhận hai client SDK/API đã cấu hình, rồi cung cấp chúng cho factory. Ví dụ minh họa về ý tưởng (các lớp provider cụ thể phụ thuộc SDK thực của dự án):

~~~java
// Pseudocode tích hợp: các provider bên dưới cần được
// cài đặt/khởi tạo từ SDK và cấu hình của hệ thống thật.
PaymentProviderClient payClient = createRealPaymentClient(config);
MessageProviderClient mailClient = createRealMessageClient(config);

IntegrationFactory factory =
        new LiveIntegrationFactory(payClient, mailClient);

BookingService bookingService = new BookingService(factory);
~~~

Đoạn trên là **pseudocode**, không thuộc tệp Java tự chạy ở phần 5: `createRealPaymentClient` và `createRealMessageClient` chưa có implementation vì API nhà cung cấp thay đổi theo dự án.

Một cách phân chia phù hợp:

- **Adapter Live** chuyển API của SDK thành các phương thức domain port.
- **Factory Live** gom những adapter thích hợp vào một họ chạy thật.
- **Factory Simulation** gom các fake dùng để kiểm thử.
- **Composition root** giải quyết chế độ, cấu hình kết nối và việc cấp factory.
- **BookingService** luôn thực thi cùng một quy trình nghiệp vụ, bất kể môi trường.

### 6.1. Chọn môi trường phải có quy tắc rõ ràng

Không nên dùng điều kiện kiểu:

~~~java
// Nguy hiểm: mọi giá trị khác "live" đều mặc nhiên là fake.
IntegrationFactory factory = "live".equals(mode)
        ? createLiveFactory()
        : new SimulatedIntegrationFactory();
~~~

Nếu người vận hành nhập sai `APP_MODE=liv`, ứng dụng có thể **âm thầm chuyển sang simulation**, tạo biên nhận giả mà vẫn báo thành công. Đây là lỗi nặng trong nghiệp vụ thanh toán.

Chính sách lựa chọn nên có:

1. **Danh sách giá trị cho phép** như `LIVE`, `SIMULATION`.
2. **Kiểm tra đầu vào nghiêm ngặt**, không đoán tên môi trường khi nhập sai.
3. **Giới hạn quyền dùng simulation**: ví dụ chỉ cho phép trong test hoặc môi trường được cấu hình rõ.
4. **Cấu hình đầy đủ** trước khi tạo factory Live: endpoint, xác thực, timeout, phiên bản API, quyền truy cập.
5. **Không tự fallback từ lỗi Live sang Simulation** khi dependency bên ngoài gặp sự cố.

Đối với phần mềm xử lý tiền, cấu hình không rõ nghĩa nên **fail fast**. Một bộ adapter mô phỏng không phải phương án dự phòng tương đương cho hệ thống thanh toán thật.

### 6.2. Không để client tự chọn từng adapter

Đoạn mã sau làm mất lợi ích của một factory cho cả họ:

~~~java
PaymentPort payment =
        mode.equals("LIVE") ? livePayment : fakePayment;
MessagePort message =
        otherMode.equals("LIVE") ? liveMessage : fakeMessage;
~~~

Hai biến cấu hình có thể không nhất quán, dẫn tới tình trạng **thu tiền thật nhưng thông báo chỉ được ghi vào bộ nhớ**, hoặc **thu tiền giả nhưng gửi email thật**.

Chọn một `IntegrationFactory` ở ranh giới lắp ghép giúp biểu diễn yêu cầu rằng cả hai adapter phải thuộc cùng chế độ. Tuy vậy, concrete factory vẫn có thể được viết sai; cần kiểm tra cấu hình của từng factory để bảo đảm đúng họ và ngăn trộn lẫn bằng các kiểm tra tích hợp thích hợp.

## 7. Tổ chức các tầng kiểm thử

Một bộ fake tốt giúp chạy test nhanh, xác định và cách ly. Tuy nhiên **test với fake** và **test adapter thật** trả lời những câu hỏi khác nhau.

| Tầng kiểm thử | Factory/adapter sử dụng | Mục tiêu |
| --- | --- | --- |
| **Unit test BookingService** | `SimulatedIntegrationFactory` | Kiểm tra thứ tự xử lý, dữ liệu truyền qua port, cách phản ứng khi payment lỗi |
| **Contract test cho adapter** | Từng adapter với client thử nghiệm theo hợp đồng | Kiểm tra chuyển đổi yêu cầu, kiểu dữ liệu, lỗi và kết quả của cổng tích hợp |
| **Integration test** | Adapter Live trỏ đến sandbox/test endpoint có chủ đích | Kiểm tra giao tiếp thật với API/SDK, xác thực, timeout, cách trả lỗi |
| **End-to-end test** | Hệ thống thử nghiệm đã cấu hình an toàn | Kiểm tra nhiều thành phần phối hợp trong hành trình nghiệp vụ |
| **Production monitoring** | Factory Live thực tế | Phát hiện lỗi vận hành, độ trễ, tỷ lệ thành công và biến thể đã chọn |

### 7.1. Test fake không chứng minh API của nhà cung cấp hoạt động

Một test sử dụng `FakePaymentAdapter` có thể thành công dù `LivePaymentAdapter` đang:

- Gửi sai trường dữ liệu hoặc sai đơn vị tiền.
- Không truyền khóa chống trùng giao dịch (*idempotency key*).
- Chuyển mã lỗi trả về thành biên nhận thành công.
- Không xử lý timeout hoặc lỗi mạng.
- Tạo mã giao dịch đúng kiểu chuỗi nhưng không hợp lệ theo nhà cung cấp thật.

Những lỗi này cần **contract test** và **integration test** với adapter Live trong môi trường có kiểm soát. Fake nên tuân theo hợp đồng chung, nhưng không thể thay thế kiểm chứng thực tế của hệ thống ngoài.

### 7.2. Fake cần mô phỏng các nhánh lỗi quan trọng

Không nên để fake chỉ **luôn thành công**. Trong quy trình đặt phòng, các nhánh đáng kiểm tra gồm:

- Thu tiền thành công, thông báo được yêu cầu đúng một lần.
- Thu tiền bị từ chối, không yêu cầu gửi thông báo.
- Provider báo timeout: nghiệp vụ xử lý trạng thái chưa chắc chắn theo chính sách đã định.
- Gửi thông báo lỗi sau khi thu tiền thành công: cần xác định cách retry và tránh thu tiền lần nữa.
- Cùng yêu cầu được gửi lại: cần kiểm tra logic chống lặp nếu hệ thống hỗ trợ idempotency.

Fake có thể cho phép test cấu hình lỗi theo tình huống, như phương thức `rejectNextCapture()` trong mã ví dụ. Nhưng fake không nên tự phỏng đoán đầy đủ cơ chế mạng và hệ thống phân tán; cần chọn những nhánh có ý nghĩa với quyết định nghiệp vụ.

### 7.3. Kiểm tra tương thích hai họ

Một chiến lược hữu ích là mô tả tập **hợp đồng chung của mỗi product** rồi áp dụng cho các implementation thích hợp.

Ví dụ, với cả fake và adapter Live khi kiểm thử ở sandbox:

- `capture(...)` trả về mã biên nhận hợp lệ khi thành công.
- Từ chối thanh toán được biểu diễn bằng cơ chế lỗi nhất quán theo hợp đồng domain.
- `sendConfirmation(...)` chuyển đúng email, bookingId và receiptId tới ranh giới gửi.
- Các khóa tương quan (correlation ID) có thể đi xuyên suốt luồng nghiệp vụ khi ứng dụng yêu cầu.

Lưu ý: **không nhất thiết phải tạo cùng một test kiểm tra side effect cho cả hai họ**. Đối với fake, có thể đọc danh sách ghi nhận trong bộ nhớ; đối với Live, có thể kiểm tra request tới endpoint sandbox hoặc bản ghi của nhà cung cấp. Điều cần thống nhất là **ngữ nghĩa sản phẩm**, không phải cách triển khai.

## 8. Các rủi ro khi sử dụng bộ adapter mô phỏng

### 8.1. Simulation rò rỉ sang môi trường thật

Nguy cơ lớn nhất là một cấu hình production vô tình chọn fake. Kết quả có thể trông «thành công» với biên nhận `SIM-...`, trong khi người dùng chưa trả tiền.

Cách phòng tránh về thiết kế là **chọn chế độ có chủ đích**, kiểm tra cấu hình bắt buộc, giới hạn điều kiện bật simulation, theo dõi chế độ đã chọn và không tự động thay lỗi production bằng fake.

Có thể dùng môi trường triển khai hoặc quyền truy cập để kiểm soát việc bật simulation, nhưng việc đó phải được tích hợp với hệ thống cấu hình và kiểm soát thực tế của dự án.

### 8.2. Fake giữ trạng thái chung giữa các test

Nếu một `SimulatedIntegrationFactory` dùng chung cho toàn bộ bộ test, các bản ghi của test trước có thể còn lại, gây phụ thuộc vào thứ tự chạy.

Cách xử lý thường đơn giản là **tạo một factory mới cho từng test**, hoặc cung cấp cơ chế reset có kiểm soát. Dùng shared fake chỉ khi thật sự cần kiểm tra tương tác giữa các thao tác trong cùng một kịch bản.

### 8.3. Dùng giả lập để che giấu thiếu sót của API thật

Fake có thể trả một `receiptId` ngay lập tức, trong khi dịch vụ thật trả về trạng thái *pending* và chỉ hoàn tất qua webhook. Nếu product interface chỉ định nghĩa `String capture()` và mặc định mọi giao dịch thành công tức thời, abstraction này có thể **không phản ánh đúng nghiệp vụ**.

Lúc đó cần thiết kế lại hợp đồng domain để biểu diễn trạng thái phù hợp: `PENDING`, `SUCCEEDED`, `FAILED` hoặc một kết quả có ý nghĩa tương đương. Fake phải tuân theo hợp đồng thật sự, không buộc adapter Live che giấu tính chất bất đồng bộ của hệ thống ngoài.

### 8.4. Cố làm fake giống hệt toàn bộ môi trường thật

Fake quá phức tạp có thể biến thành một bản sao của SDK bên ngoài, khó bảo trì và vẫn không bảo đảm đúng từng tình huống. Chỉ mô phỏng những **hành vi cần cho kiểm thử nghiệp vụ**. Những phần phụ thuộc provider nên được kiểm tra bằng sandbox/contract test riêng.

### 8.5. Cho client phụ thuộc vào khả năng của fake

~~~java
// Không nên để mã nghiệp vụ làm việc này:
if (payment instanceof FakePaymentAdapter) {
    // Bỏ qua bước kiểm tra hoặc đổi quy trình xử lý.
}
~~~

Điều đó khiến chương trình thay đổi logic khi chạy simulation. Client nên chỉ dùng `PaymentPort` và `MessagePort`. Mọi quan sát đặc thù fake phải ở **mã kiểm thử**, không ở service nghiệp vụ.

### 8.6. Nhầm việc chọn cùng họ với giao dịch nguyên tử

Thu tiền và gửi email là hai hệ thống khác nhau. Abstract Factory giúp chọn đúng cặp adapter theo môi trường, **không bảo đảm** cả hai thao tác cùng thành công hoặc cùng thất bại.

Ở production, có thể cần transaction outbox, xử lý sự kiện, idempotency, retry và đối soát khi thao tác thứ hai thất bại. Đây là những quyết định kiến trúc bổ sung, độc lập với câu hỏi tạo factory nào.

## 9. Khi nào nên áp dụng cấu trúc này?

**Phù hợp khi:**

- Một nghiệp vụ dùng **nhiều loại dependency ngoài** và cần thay **cả bộ** giữa live, sandbox hoặc simulation.
- Các adapter có **hợp đồng domain đủ ổn định** để cùng một client sử dụng.
- Cần kiểm thử logic mà không gọi API thật, không cần tài khoản dịch vụ và không tạo side effect.
- Muốn tập trung lựa chọn môi trường, cấu hình và việc tạo adapter ở một nơi.
- Hệ thống có khả năng bổ sung **các họ mới** như `StagingIntegrationFactory` hoặc `OfflineIntegrationFactory` với cùng tập product interface.

**Chưa cần thiết khi:**

- Chỉ có một dependency đơn giản: truyền một `PaymentPort` giả vào service có thể đã đủ, không nhất thiết có Abstract Factory.
- Các dependency cần chọn **độc lập hoàn toàn**, không có quy tắc nào buộc chúng đi cùng một họ.
- Số loại port thay đổi liên tục khiến một `IntegrationFactory` lớn và buộc mọi concrete factory sửa liên tục.
- Mã ứng dụng nhỏ và cách lắp ghép trực tiếp đã đủ rõ ràng.

Không nên gom mọi adapter trong hệ thống vào một factory khổng lồ. Hãy nhóm những product có **cùng quyết định môi trường hoặc ràng buộc phối hợp**. Một bộ xử lý báo cáo và một bộ thanh toán không nhất thiết thuộc cùng một factory chỉ vì chúng đều có phiên bản fake.

## 10. Bài tập mở rộng và tự kiểm tra

### 10.1. Bài tập thực hành

Từ chương trình ở phần 5, hãy thử bổ sung **`FakeMessageAdapter` có khả năng mô phỏng gửi thất bại**. Quan sát những câu hỏi cần giải quyết:

- Sau khi thanh toán fake thành công nhưng gửi thông báo thất bại, `BookingService` cần trả trạng thái gì?
- Có nên gọi lại `payment.capture(...)` khi retry gửi thư không?
- Nếu cả hai thao tác được retry, làm sao tránh ghi nhận hai lần thu tiền cho cùng đặt phòng?
- Có cần tách một trạng thái `paymentSucceededButNotificationPending` trong domain?

Đây là bài tập về **ứng dụng thực tế và giới hạn của bộ adapter**, không phải yêu cầu phải đưa cơ chế giao dịch phân tán vào chính factory.

### 10.2. Câu hỏi nhận diện mẫu

**Câu 1.** `LivePaymentAdapter` và `LiveMessageAdapter` là hai lớp implement cùng một interface `Adapter` hay sao?

**Trả lời:** Không bắt buộc. Chúng là hai **loại sản phẩm khác nhau** (`PaymentPort` và `MessagePort`), nên có những hợp đồng riêng. Chúng thuộc cùng họ Live vì được chọn cùng chế độ chạy.

**Câu 2.** Vì sao `SimulatedIntegrationFactory` cần trả lại những fake mà test có thể quan sát?

**Trả lời:** `BookingService` phải dùng đúng các instance đã ghi lại thao tác; test cần đọc trạng thái của chính những instance đó. Factory trong ví dụ giữ fake theo vòng đời của một test.

**Câu 3.** Dùng một fake thanh toán nhưng adapter gửi email thật trong cùng một bài kiểm thử có phải luôn sai không?

**Trả lời:** Không phải mọi test phối hợp khác chế độ đều sai. Một **integration test có chủ đích** có thể dùng cấu hình hỗn hợp để kiểm tra riêng một cổng. Nhưng nếu yêu cầu của kịch bản là **mô phỏng hoàn toàn, không side effect thật**, cấu hình đó vi phạm mục tiêu; không nên xảy ra do lựa chọn môi trường vô tình.

**Câu 4.** Một unit test chạy thành công với `FakePaymentAdapter` có chứng minh cổng thanh toán production hoạt động không?

**Trả lời:** Không. Nó chứng minh logic client với hợp đồng của fake. Adapter Live phải được kiểm tra riêng về API, lỗi, trạng thái và giao tiếp thật ở môi trường thử nghiệm được kiểm soát.

**Câu 5.** Nếu production payment provider bị lỗi, có nên tự thay `LiveIntegrationFactory` bằng `SimulatedIntegrationFactory` để người dùng vẫn đặt phòng thành công?

**Trả lời:** Không. Simulation không xử lý thanh toán thật và không phải cơ chế dự phòng nghiệp vụ. Cần báo trạng thái lỗi/chờ phù hợp, retry hoặc chuyển nhà cung cấp thật theo quy tắc đã được thiết kế và kiểm chứng.

**Câu 6.** Nếu hệ thống có nhiều chế độ như Live, Staging và Simulation, cần sửa `BookingService` bao nhiêu chỗ khi thêm `StagingIntegrationFactory`?

**Trả lời:** Thông thường không cần sửa `BookingService` nếu các product interface giữ nguyên. Thêm concrete products/factory cho staging và cập nhật phần lắp ghép lựa chọn factory.

## 11. Ghi nhớ

**Abstract Factory phù hợp để cấp một bộ adapter theo môi trường** khi nhiều loại dependency phải được lựa chọn cùng nhau. Trong tình huống đặt phòng, `IntegrationFactory` tạo `PaymentPort` và `MessagePort`; họ Live nối với nhà cung cấp thật, họ Simulation ghi nhận các tương tác trong bộ nhớ. `BookingService` luôn dùng cùng các interface và không cần biết môi trường đang chạy.

Lợi ích trực tiếp là **kiểm thử logic nhanh, xác định và không có tác dụng phụ bên ngoài**, đồng thời cô lập cách kết nối SDK khỏi mã nghiệp vụ. Giới hạn quan trọng là fake không kiểm chứng được giao thức thực, chọn đúng factory không làm cho nhiều hệ thống có giao dịch nguyên tử, và **simulation không được âm thầm thay thế live** khi xảy ra lỗi. Thiết kế tốt kết hợp kiểm thử với fake, kiểm thử hợp đồng, kiểm thử tích hợp ở sandbox và chính sách lựa chọn môi trường tường minh.
