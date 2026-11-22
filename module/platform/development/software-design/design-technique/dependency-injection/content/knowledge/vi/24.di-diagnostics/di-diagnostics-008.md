# Kiểm thử vượt qua nhưng cấu hình lắp ghép ứng dụng bị thiếu

## 1. Hiện tượng: unit test xanh, ứng dụng vẫn không khởi động hoặc không phục vụ được

Trong **Dependency Injection (DI)**, lớp nghiệp vụ nhận các cộng tác viên qua constructor hoặc một cơ chế injection tường minh; **composition root** quyết định implementation nào được tạo, được kết nối và có vòng đời ra sao. Đây là một cách thực hiện **Inversion of Control (IoC)**: phần sử dụng dependency không tự quyết định việc tạo/lắp ghép dependency.

DI giúp kiểm thử dễ dàng hơn, nhưng cũng tạo ra một sự khác biệt cần hiểu: **đồ thị đối tượng trong bài test không nhất thiết là đồ thị ứng dụng chạy thật**.

Một nhóm phát triển có thể gặp tình huống:

- Hàng chục unit test của `CheckoutService` đều PASS vì test truyền `FakeOrderRepository` và `RecordingReceiptSender`.
- Ở một cấu hình triển khai, ứng dụng chọn gửi biên nhận qua email, nhưng composition root **chưa đăng ký** implementation `ReceiptSender` cho kênh `EMAIL`.
- Các unit test không dựng composition root nên không phát hiện cấu hình thiếu.
- Ứng dụng thật thất bại khi khởi động, hoặc tệ hơn, chỉ thất bại khi request đầu tiên đi qua nhánh thiếu dependency.

Đây là lỗi **thiếu kiểm chứng việc lắp ghép** (*composition/wiring gap*), không nhất thiết là lỗi thuật toán nghiệp vụ.

```text
UNIT TEST
  FakeOrderRepository -----+
                           +--> CheckoutService --> PASS
  RecordingReceiptSender --+

ỨNG DỤNG THẬT
  Application composition root
    +--> ConcreteOrderRepository ------+
    +--> ReceiptSender cho EMAIL: ???  +--> CheckoutService
                                         ^
                                         |
                               THIẾU BINDING / SAI CẤU HÌNH
```

**Các mục tiêu của bài:**

1. Phân biệt test logic một lớp với test **đồ thị dependency thực sự được lắp**.
2. Chẩn đoán thiếu binding, sai binding, thiếu cấu hình, nhánh chưa được khởi tạo và scope/lifecycle sai.
3. Hiểu vì sao constructor injection cải thiện phát hiện sớm nhưng **không tự kiểm chứng mọi configuration profile**.
4. Xây ví dụ Java thuần gồm unit test PASS và composition root thất bại do thiếu đăng ký.
5. Bổ sung **composition smoke test** và các kiểm tra startup/readiness phù hợp.
6. Biết giới hạn giữa việc dựng graph thành công, kết nối hạ tầng thật và kiểm thử toàn luồng trước khi chuyển sang DI container.

## 2. Cần kiểm chứng những lớp trách nhiệm khác nhau

Một bài test chỉ chứng minh những điều **thật sự được chạy** trong phạm vi của nó. Không nên suy từ `UNIT PASS` thành “ứng dụng production đã cấu hình đúng”.

| Loại kiểm chứng | Đồ thị được sử dụng | Phát hiện tốt | Chưa đủ để chứng minh |
| --- | --- | --- | --- |
| **Unit test** | Graph nhỏ tự dựng với fake/stub hoặc implementation thuần Java. | Quy tắc nghiệp vụ, validation, phối hợp các port, xử lý lỗi do fake đưa vào. | Production root có đăng ký đủ implementation hay không. |
| **Composition/root smoke test** | Đi qua **cách xây graph của executable** với cấu hình đại diện. | Thiếu binding, cấu hình không hợp lệ, trùng lựa chọn, không tạo được entry point. | Giao thức HTTP/database/email thực hoạt động đúng, nếu adapter chỉ tạo lazy. |
| **Component test** | Một nhóm thành phần thật phối hợp với các ranh giới ngoài được thay thế. | Wiring giữa các lớp trong component, mapping/điều phối và lifecycle nội bộ. | Toàn bộ đường triển khai hoặc hệ thống ngoài không nằm trong phạm vi. |
| **Contract test** | Chạy cùng tập hành vi trên nhiều implementation của một port. | Fake và adapter thật có nhất quán với một hợp đồng cụ thể không. | Cấu hình production có chọn đúng implementation không. |
| **Integration test** | Adapter thật với database, file, HTTP test server, queue hoặc dịch vụ thử. | Kết nối, câu lệnh, mapping, transaction, cấu hình client và cleanup. | Toàn bộ các route/profile chưa được test. |
| **End-to-end test** | Đường đi từ entry point qua các thành phần đã triển khai. | Một luồng người dùng/ca sử dụng hoàn chỉnh trong môi trường thử. | Mọi tổ hợp tính năng hoặc mọi trường hợp lỗi. |

Những cấp kiểm thử này **bổ sung cho nhau**. Một unit test rất tốt vẫn có thể bỏ qua lỗi cấu hình vì nó chủ động truyền đủ dependency. Ngược lại, một smoke test chỉ khởi tạo được graph chưa chứng minh logic xử lý đơn hàng đúng.

### 2.1. “Ứng dụng có thể tạo object” khác “ứng dụng có thể phục vụ”

Phân biệt ít nhất ba mốc:

1. **Constructed:** các object được tạo và reference bắt buộc đã nối theo quy tắc composition.
2. **Ready:** những điều kiện mà ứng dụng coi là cần để nhận việc đã được xác thực; ví dụ cấu hình bắt buộc, endpoint, kết nối thiết yếu hoặc đăng ký listener.
3. **Serving:** một request/job đi qua entry point có thể thực thi và tạo kết quả mong muốn.

Nếu adapter HTTP chỉ lưu URL trong constructor và kết nối khi gọi `send()`, việc root dựng adapter thành công **không chứng minh endpoint có thể truy cập**. Tương tự, một route chưa đăng ký có thể không phát lộ khi khởi động nếu chưa có phép kiểm tra route table.

## 3. Những nguyên nhân khiến test PASS nhưng wiring thiếu

### 3.1. Test không gọi composition root

```java
// Unit test dựng graph riêng:
CheckoutService service =
        new CheckoutService(new FakeOrderRepository(),
                            new RecordingReceiptSender());
```

Đây là điều **đúng đắn** cho unit test. Nhưng nó không chạm tới `ApplicationComposition.build(...)`, vì vậy không biết application graph có thiếu `ReceiptSender` hoặc dùng cấu hình khác không.

### 3.2. Một profile hoặc nhánh điều kiện thiếu binding

Ví dụ chỉ đăng ký `CONSOLE`, trong khi cấu hình `production` chọn `EMAIL`. Cấu hình `local` chạy được; nhánh production chưa được kiểm chứng.

Điểm này cũng áp dụng cho các chế độ `local`, `staging`, `production`, vùng địa lý, tenant, tính năng bật/tắt, hoặc các executable khác nhau như API server, CLI và worker.

### 3.3. Đăng ký đúng interface nhưng sai implementation

Không có binding thiếu về mặt kỹ thuật, nhưng ứng dụng vô tình nhận `NoOpReceiptSender` thay cho sender thật. Một smoke test chỉ kiểm tra `!= null` có thể PASS, dù yêu cầu gửi biên nhận đã bị bỏ qua.

**Thiếu binding**, **binding sai** và **binding không đầy đủ theo môi trường** là những lỗi có liên quan nhưng không giống nhau.

### 3.4. Nhánh lazy không được khởi tạo trong test

Một factory/provider có thể chỉ tạo client khi request gọi tính năng hiếm. Root khởi động được vì mới inject provider, nhưng factory chưa được gọi; lỗi thiếu cấu hình hoặc thiếu binding chỉ hiện ra ở lần truy cập đầu tiên.

Điều này là hệ quả của **lazy initialization** và cách kiểm tra startup, không phải dấu hiệu DI tự hỏng.

### 3.5. Test thay bean/adapter thật bằng fake mà không kiểm tra root thật

Một số framework hỗ trợ cấu hình hoặc annotation cho phép test **ghi đè** binding production bằng mock. Điều này hữu ích khi kiểm tra service, nhưng nếu mọi test đều ghi đè bean bị thiếu, toàn bộ suite có thể xanh dù cấu hình thật vẫn thiếu.

### 3.6. Root của executable khác chưa được kiểm tra

Web API khởi động tốt chưa đảm bảo batch worker có đủ listener, sender hoặc repository. Nếu có nhiều entry point hoặc executable, mỗi graph thực tế cần được kiểm tra theo phạm vi phù hợp.

## 4. Ví dụ Java thuần: chỗ thiếu binding nằm ở composition root

Ta mô phỏng hệ thống checkout:

- `CheckoutService` cần `OrderRepository` và `ReceiptSender`.
- `CheckoutController` là entry point.
- Cấu hình chọn `CONSOLE` hoặc `EMAIL`.
- Composition root giữ một **bảng đăng ký có kiểu nghiệp vụ rõ ràng** `Map<ReceiptChannel, ReceiptSender>`.
- Ta cố tình tạo một trường hợp **chọn `EMAIL` nhưng không đăng ký sender email** để quan sát lỗi.

Bảng `Map` chỉ thuộc **vùng composition**; `CheckoutService` không tra cứu một service locator tổng quát. Các adapter dùng bộ nhớ và in console nên không truy cập database hoặc gửi email thật.

Lưu đoạn sau trong `WiringDiagnosticsDemo.java`:

```java
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

enum ReceiptChannel {
    CONSOLE, EMAIL
}

interface OrderRepository {
    void save(String orderId);
}

interface ReceiptSender {
    void send(String orderId);
}

// Logic nghiệp vụ chỉ nhận những port cần thiết.
final class CheckoutService {
    private final OrderRepository repository;
    private final ReceiptSender sender;

    CheckoutService(OrderRepository repository, ReceiptSender sender) {
        this.repository = Objects.requireNonNull(
                repository, "repository");
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void confirm(String orderId) {
        if (orderId == null || orderId.trim().isEmpty()) {
            throw new IllegalArgumentException("INVALID_ORDER_ID");
        }

        repository.save(orderId);
        sender.send(orderId);
    }
}

final class InMemoryOrderRepository implements OrderRepository {
    private final List<String> saved = new ArrayList<>();

    @Override
    public void save(String orderId) {
        saved.add(orderId);
    }
}

final class ConsoleReceiptSender implements ReceiptSender {
    @Override
    public void send(String orderId) {
        System.out.println("CONSOLE_SENT:" + orderId);
    }
}

// Adapter demo, chỉ in ra stdout, KHÔNG gửi email thực tế.
final class DemoEmailReceiptSender implements ReceiptSender {
    @Override
    public void send(String orderId) {
        System.out.println("EMAIL_SENT:" + orderId);
    }
}

final class CheckoutController {
    private final CheckoutService service;

    CheckoutController(CheckoutService service) {
        this.service = Objects.requireNonNull(service, "service");
    }

    void handle(String orderId) {
        service.confirm(orderId);
        System.out.println("CONFIRMED:" + orderId);
    }
}

final class ApplicationGraph {
    private final CheckoutController controller;

    ApplicationGraph(CheckoutController controller) {
        this.controller = Objects.requireNonNull(
                controller, "controller");
    }

    void handle(String orderId) {
        controller.handle(orderId);
    }
}

// Hai cấu hình ở đây mô phỏng hai trạng thái đăng ký.
// registerEmailAdapter=false cố tình minh họa graph bị thiếu.
final class RuntimeOptions {
    final ReceiptChannel selectedChannel;
    final boolean registerEmailAdapter;

    RuntimeOptions(ReceiptChannel selectedChannel,
                   boolean registerEmailAdapter) {
        this.selectedChannel = Objects.requireNonNull(
                selectedChannel, "selectedChannel");
        this.registerEmailAdapter = registerEmailAdapter;
    }
}

final class ApplicationComposition {
    static ApplicationGraph build(RuntimeOptions options) {
        Objects.requireNonNull(options, "options");

        // Composition root: chọn và đăng ký các adapter cụ thể.
        Map<ReceiptChannel, ReceiptSender> senders =
                new EnumMap<>(ReceiptChannel.class);

        senders.put(ReceiptChannel.CONSOLE,
                new ConsoleReceiptSender());

        if (options.registerEmailAdapter) {
            senders.put(ReceiptChannel.EMAIL,
                    new DemoEmailReceiptSender());
        }

        ReceiptSender chosen = senders.get(options.selectedChannel);
        if (chosen == null) {
            // Fail-fast: báo tên vai trò thiếu, không dùng fallback ngầm.
            throw new IllegalStateException(
                    "WIRING_MISSING_SENDER:" + options.selectedChannel);
        }

        OrderRepository repository = new InMemoryOrderRepository();
        CheckoutService checkout = new CheckoutService(
                repository, chosen);
        CheckoutController controller =
                new CheckoutController(checkout);

        return new ApplicationGraph(controller);
    }
}

public class WiringDiagnosticsDemo {
    public static void main(String[] args) {
        System.out.println("Boot with missing EMAIL binding:");

        try {
            ApplicationComposition.build(
                    new RuntimeOptions(ReceiptChannel.EMAIL, false));
        } catch (IllegalStateException expected) {
            System.out.println(expected.getMessage());
        }

        System.out.println("Boot with fixed EMAIL binding:");

        ApplicationGraph app = ApplicationComposition.build(
                new RuntimeOptions(ReceiptChannel.EMAIL, true));

        app.handle("ORD-100");
    }
}
```

Chạy:

```bash
javac WiringDiagnosticsDemo.java
java WiringDiagnosticsDemo
```

Đầu ra dự kiến:

```text
Boot with missing EMAIL binding:
WIRING_MISSING_SENDER:EMAIL
Boot with fixed EMAIL binding:
EMAIL_SENT:ORD-100
CONFIRMED:ORD-100
```

### 4.1. Chỗ nào thật sự bị thiếu?

Trong lần bootstrap đầu tiên:

```text
RuntimeOptions(EMAIL, false)
           |
           v
Map các sender chỉ có khóa CONSOLE
           |
           v
senders.get(EMAIL) == null
           |
           v
WIRING_MISSING_SENDER:EMAIL
```

`CheckoutService` vẫn là một lớp có thiết kế DI hợp lý: hai dependency bắt buộc hiện ra trong constructor. **Vấn đề nằm ở composition root**: lựa chọn `EMAIL` nhưng không có implementation tương ứng.

Đoạn code cố ý có cờ `registerEmailAdapter` để tái hiện cấu hình thiếu theo cách xác định. Trong ứng dụng thật, nguyên nhân có thể là một module chưa được nạp, một binding bị tắt bởi profile, một factory không được gọi hoặc gói triển khai thiếu cấu hình.

### 4.2. Vì sao kiểm tra thiếu binding ở root tốt hơn bỏ qua?

Một lựa chọn nguy hiểm là:

```java
// Anti-pattern: fallback âm thầm khi phải có sender EMAIL.
ReceiptSender chosen = senders.get(selectedChannel);
if (chosen == null) {
    chosen = orderId -> { /* bỏ qua việc gửi */ };
}
```

Đoạn trên là minh họa ngắn, giả định `senders` và `selectedChannel` đã có. Hệ thống có thể khởi động thành công, đơn được lưu nhưng **không có biên nhận**. Nếu gửi biên nhận là yêu cầu bắt buộc, fallback im lặng có thể gây mất chức năng nghiêm trọng hơn một lỗi startup rõ ràng.

Nếu có chế độ demo hoặc tắt gửi biên nhận **hợp lệ theo nghiệp vụ**, root phải chọn chế độ đó **tường minh**, có tên và test riêng; không được dùng nó làm phương án che cấu hình thiếu.

### 4.3. Điều constructor injection phát hiện được và chưa phát hiện được

`Objects.requireNonNull` ở `CheckoutService` giúp fail-fast nếu có ai truyền `null`. Tuy nhiên:

- Nó không tự chọn được `EMAIL` hay `CONSOLE`.
- Nó không bảo đảm sender được đăng ký đúng với mọi cấu hình.
- Nó không bảo đảm sender gọi mạng/email thật được.
- Nó không bảo đảm lifecycle và thread safety của adapter.

**Constructor injection làm dependency rõ ràng; composition test kiểm tra việc cung cấp dependency có đúng không.** Đây là hai lớp bảo vệ bổ sung.

## 5. Unit test PASS dù production root đang thiếu

Bây giờ ta viết một unit test **đúng cho phạm vi của nó**. Nó không biết root, vì chỉ cần xác minh `CheckoutService` phối hợp đúng repository và sender được truyền vào.

Lưu file `CheckoutServiceUnitTest.java` cạnh file demo:

```java
final class RecordingOrderRepository implements OrderRepository {
    int calls;
    String lastOrderId;

    @Override
    public void save(String orderId) {
        calls++;
        lastOrderId = orderId;
    }
}

final class RecordingReceiptSender implements ReceiptSender {
    int calls;
    String lastOrderId;

    @Override
    public void send(String orderId) {
        calls++;
        lastOrderId = orderId;
    }
}

public class CheckoutServiceUnitTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        RecordingOrderRepository repository =
                new RecordingOrderRepository();
        RecordingReceiptSender sender =
                new RecordingReceiptSender();

        // Unit composition: cung cấp đủ fake bằng tay.
        CheckoutService service = new CheckoutService(
                repository, sender);

        service.confirm("UNIT-1");

        check(repository.calls == 1
                        && "UNIT-1".equals(repository.lastOrderId),
                "Không lưu đúng đơn");
        check(sender.calls == 1
                        && "UNIT-1".equals(sender.lastOrderId),
                "Không gửi thông báo đúng đơn");

        boolean invalidRejected = false;
        try {
            service.confirm(" ");
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }

        check(invalidRejected, "Không từ chối mã đơn rỗng");
        check(repository.calls == 1 && sender.calls == 1,
                "Dữ liệu sai vẫn phát sinh side effect");

        boolean missingRejected = false;
        try {
            new CheckoutService(repository, null);
        } catch (NullPointerException expected) {
            missingRejected = true;
        }

        check(missingRejected,
                "Constructor không từ chối dependency bắt buộc thiếu");
        System.out.println("UNIT PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac WiringDiagnosticsDemo.java CheckoutServiceUnitTest.java
java CheckoutServiceUnitTest
```

Kết quả:

```text
UNIT PASS
```

Đây **không phải unit test sai**. Nó chứng minh service sử dụng đúng các port đã được cung cấp và xử lý input không hợp lệ; nó **không có trách nhiệm** chứng minh `ApplicationComposition.build(...)` đăng ký đủ sender. Vấn đề của bộ kiểm thử là **thiếu một lớp kiểm chứng cấu hình**, không phải cần sửa mọi unit test thành integration test.

## 6. Bổ sung composition smoke test đi qua root thật

Ta cần một bài test gọi **chính phương thức lắp ghép mà ứng dụng dùng** (ở ví dụ là `ApplicationComposition.build`), với các cấu hình được hỗ trợ.

Lưu `ApplicationCompositionSmokeTest.java` cạnh hai file trên:

```java
public class ApplicationCompositionSmokeTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void missingBindingMustFailClearly() {
        boolean detected = false;

        try {
            ApplicationComposition.build(
                    new RuntimeOptions(ReceiptChannel.EMAIL, false));
        } catch (IllegalStateException expected) {
            detected = "WIRING_MISSING_SENDER:EMAIL"
                    .equals(expected.getMessage());
        }

        check(detected,
                "Root không phát hiện thiếu sender cho EMAIL");
        System.out.println("MISSING BINDING DETECTED");
    }

    static void supportedModesMustBoot() {
        // Chế độ console được hỗ trợ dù không đăng ký email.
        ApplicationGraph console = ApplicationComposition.build(
                new RuntimeOptions(ReceiptChannel.CONSOLE, false));
        console.handle("SMOKE-C");

        // Chế độ email phải có adapter email tương ứng.
        ApplicationGraph email = ApplicationComposition.build(
                new RuntimeOptions(ReceiptChannel.EMAIL, true));
        email.handle("SMOKE-E");
    }

    public static void main(String[] args) {
        missingBindingMustFailClearly();
        supportedModesMustBoot();
        System.out.println("GRAPH SMOKE PASS");
    }
}
```

Chạy:

```bash
javac WiringDiagnosticsDemo.java ApplicationCompositionSmokeTest.java
java ApplicationCompositionSmokeTest
```

Đầu ra dự kiến:

```text
MISSING BINDING DETECTED
CONSOLE_SENT:SMOKE-C
CONFIRMED:SMOKE-C
EMAIL_SENT:SMOKE-E
CONFIRMED:SMOKE-E
GRAPH SMOKE PASS
```

### 6.1. Hai nhóm assert phục vụ hai mục đích khác nhau

- **Negative test** `missingBindingMustFailClearly()`: đưa vào một cấu hình **cố ý sai** để chứng minh root phát hiện lỗi và báo mã dễ chẩn đoán. Test này PASS **không** có nghĩa cấu hình thiếu đó được phép triển khai.
- **Positive smoke test** `supportedModesMustBoot()`: dựng graph cho các chế độ **được tuyên bố hỗ trợ** và đi qua entry point. Nếu một cấu hình đáng lẽ hợp lệ mà root không dựng được, test phải FAIL.

Trong CI thực, các cấu hình production được hỗ trợ phải xuất hiện ở nhóm **positive** và dùng các binding chính xác theo môi trường thử. Không được gọi cấu hình đang thiếu là “được kiểm chứng” chỉ vì ta viết negative test mong nó thất bại.

### 6.2. Smoke test có thể cần một nơi kiểm tra riêng

Một số adapter có constructor tốn tài nguyên, cần mạng hoặc secret. Để không gọi production trong CI, có thể:

1. Tách phần **định nghĩa binding/selection** khỏi phần tạo kết nối có side effect.
2. Dùng một môi trường thử được cấp quyền hoặc test double **ở đúng ranh giới hệ thống ngoài**.
3. Giữ đủ cấu hình và đường wiring cần kiểm tra để tránh thay toàn bộ root bằng một root giả khác.
4. Bổ sung integration test riêng cho adapter thật với database/test server/sandbox.

Nếu smoke test tự tạo `new CheckoutService(fake, fake)` giống unit test, nó **không kiểm tra root**. Tên test là `ApplicationSmokeTest` không thay đổi điều đó.

## 7. Chẩn đoán lỗi thiếu wiring theo trình tự có thể lặp lại

Khi xuất hiện báo cáo “test đều xanh nhưng deploy lỗi”, không nên bắt đầu bằng sửa ngẫu nhiên annotation hoặc thêm `new` trong service. Có thể dùng quy trình sau.

### Bước 1: Xác định lỗi nằm ở pha nào

- **Compile:** chương trình không có constructor phù hợp, type mismatch hoặc module thiếu class tại build.
- **Startup/bootstrap:** root thiếu binding, cấu hình bắt buộc hoặc tạo adapter thất bại.
- **READY nhưng first request lỗi:** dependency được tạo lazy, route/handler chưa được tạo, hoặc một nhánh hiếm chưa được chạm đến.
- **Runtime sau một thời gian:** credential hết hạn, connection bị đóng, request scope bị capture, hoặc phụ thuộc ngoài mất kết nối.

Các pha dẫn đến **những loại test khác nhau**; không gom mọi thứ dưới nhãn “DI bị lỗi”.

### Bước 2: Ghi lại cấu hình có thể tái hiện

Tập trung vào các thông tin **không bí mật**:

- Executable và entry point nào đang chạy?
- Profile/mode nào đang được chọn?
- Tính năng/route nào gây lỗi?
- Loại binding nào thiếu hoặc sai?
- Root nào đã chạy; factory có lazy không?
- Lỗi phát sinh trước READY hay trong request/job?

Không dump toàn bộ biến môi trường, connection string, token hoặc exception cause chứa URL nhạy cảm chỉ để tìm lỗi DI. Có thể log **tên khóa bị thiếu** và mã lỗi chuẩn hóa thay vì giá trị bí mật.

### Bước 3: Vẽ graph dự kiến và graph thực tế

```text
Graph dự kiến:
  CheckoutController
      -> CheckoutService
           -> OrderRepository (SQL adapter)
           -> ReceiptSender (EMAIL adapter)

Graph thực tế theo chế độ EMAIL:
  CheckoutController
      -> CheckoutService
           -> OrderRepository (SQL adapter)
           -> ReceiptSender (MISSING)
```

Chỉ liệt kê class chưa đủ; cần biết **instance được chọn theo profile**, scope và nguồn cấu hình. Hai instance cùng interface có thể có lifetime và quyền truy cập khác nhau.

### Bước 4: So sánh cách lắp graph trong unit test và executable

Nếu unit test lắp `RecordingReceiptSender` còn application root cần `DemoEmailReceiptSender`, thử xác minh rằng production root thật sự tạo và truyền `DemoEmailReceiptSender`. Đừng sửa fake vì unit test không có lỗi trong phạm vi của nó.

### Bước 5: Dựng lại root với cấu hình đang gặp lỗi

Nếu lỗi thiếu binding, ưu tiên bổ sung **composition smoke test** cho profile/mode đó. Nếu lỗi lazy, thêm bước kích hoạt factory cần thiết hoặc readiness check theo contract. Nếu lỗi kết nối thật, bổ sung integration test với môi trường thử có kiểm soát.

### Bước 6: Sửa tại đúng ranh giới

- Thiếu đăng ký: thêm binding/adapter vào composition root hoặc module cấu hình đúng.
- Sai implementation: sửa selector/qualifier/tên binding và test hành vi cần thiết.
- Thiếu cấu hình: thêm xác thực fail-fast và xử lý secret an toàn.
- Scope sai: thay cách cấp dependency, không giữ request-scoped instance trong singleton.
- Resource sống không đúng: chỉnh ownership, start/stop, drain và cleanup.
- Route/handler thiếu: đăng ký entry point thực và kiểm tra routing, không chỉ dựng service.

### Bước 7: Chạy lại test ở phạm vi phù hợp

Chạy unit test để bảo vệ logic, composition smoke test cho graph, integration test cho adapter liên quan và regression test đi qua entry point phát sinh lỗi. Với cấu hình có nhiều chế độ, cần đảm bảo ca vừa bị lỗi có mặt trong **ma trận test**.

## 8. Ma trận cấu hình: không chỉ test “môi trường mặc định”

Một root có thể dựng thành công với `CONSOLE` nhưng thiếu `EMAIL`. Càng nhiều profile, tính năng và executable, rủi ro bỏ sót nhánh càng lớn.

| Executable | Cấu hình | Điều kiện phải kiểm tra | Phạm vi test |
| --- | --- | --- | --- |
| CLI demo | CONSOLE | Console sender tồn tại; command được lắp ghép. | Positive composition smoke. |
| HTTP server | EMAIL | Email sender được đăng ký; controller/route thực được tạo. | Composition smoke + integration/sandbox. |
| Worker | EMAIL | Consumer/handler/job graph đầy đủ; lifecycle được quản lý. | Worker bootstrap smoke + test xử lý message. |
| Profile thử | EMAIL thiếu binding *cố ý* | Root từ chối trước khi phục vụ, có mã lỗi rõ. | Negative configuration test. |
| Chế độ tính năng tùy chọn tắt | Không cần sender ở use case không gửi biên nhận | Không tạo nhầm dependency bắt buộc hoặc fallback không cho phép. | Test đường không sử dụng + cấu hình hợp lệ. |

Không cần test **tích Descartes của mọi cờ tính năng** nếu số tổ hợp quá lớn. Hãy chọn theo rủi ro: mỗi executable, mỗi profile có wiring khác, mỗi nhóm implementation, nhánh lazy trọng yếu và các tổ hợp từng gây lỗi.

**Nguyên tắc:** danh sách mode/profile được phép triển khai phải được nêu rõ; CI không nên mặc định chỉ kiểm tra cấu hình tiện nhất để chạy ở máy phát triển.

### 8.1. Khi feature flag quyết định có cần dependency hay không

Có hai mô hình khác nhau:

- **Tính năng bắt buộc:** nếu `EMAIL` được chọn, phải có `ReceiptSender` phù hợp và root phải báo lỗi nếu thiếu.
- **Tính năng thực sự tùy chọn:** nếu email bị tắt theo sản phẩm, có thể không tạo sender email; controller/use case phải thể hiện trạng thái không gửi theo hợp đồng, không giả vờ đã gửi.

Tránh dùng `null` mơ hồ trong constructor để ngầm đại diện cả “bị thiếu cấu hình” lẫn “tính năng chủ động tắt”. Nên biểu diễn bằng configuration/strategy rõ ràng và kiểm thử từng nhánh.

## 9. Phát hiện sớm: validation ở composition root

Một root tốt cần phân biệt:

```text
1. Parse configuration
2. Validate required settings và tổ hợp lựa chọn
3. Resolve/register adapter cho các vai trò bắt buộc
4. Construct object graph
5. Start adapter/lifecycle component cần thiết
6. Validate readiness khi hợp đồng yêu cầu
7. Expose entry point / accept work
```

Trong ví dụ, `WIRING_MISSING_SENDER:EMAIL` xuất hiện ở bước lựa chọn, trước khi root tạo `CheckoutService`. Việc báo lỗi **đúng vai trò** dễ chẩn đoán hơn một `NullPointerException` ở request đầu tiên.

### 9.1. Ba mức validation khác nhau

| Mức | Ví dụ | Điều được bảo đảm |
| --- | --- | --- |
| **Type/constructor validation** | `Objects.requireNonNull(sender)`. | Constructor không nhận `null` đối với dependency bắt buộc. |
| **Composition validation** | Chế độ EMAIL phải có đúng một `ReceiptSender` hợp lệ. | Root có thể lắp graph theo lựa chọn đó. |
| **Readiness/integration validation** | Client có thể kết nối tới test server hoặc dịch vụ yêu cầu. | Điều kiện kết nối đã kiểm tra tại thời điểm kiểm tra, không bảo đảm không lỗi trong tương lai. |

Không mức nào tự thay thế hoàn toàn mức khác. Đặc biệt, readiness thành công tại thời điểm khởi động vẫn không bảo đảm backend sẽ không timeout hoặc hết hạn token khi đang phục vụ.

### 9.2. Lỗi cấu hình cần rõ nhưng không lộ dữ liệu nhạy cảm

Thông báo tốt:

```text
WIRING_MISSING_SENDER:EMAIL
CONFIG_MISSING:RECEIPT_ENDPOINT
INVALID_RECEIPT_TIMEOUT
```

Thông báo không an toàn có thể là dump toàn bộ `RuntimeOptions`, URI chứa credential, `Authorization` header hoặc object chứa secret. Cần ghi **tên vai trò/khóa và mã lỗi**, không ghi giá trị bí mật. Khi thư viện ngoài ném exception có thể chứa input nhạy cảm, hãy kiểm duyệt cause/message trước khi đưa vào log tập trung.

### 9.3. Constructor injection không kiểm tra chính sách đăng ký

Ngay cả khi mọi constructor đều kiểm tra `null`, vẫn có lỗi khi:

- Hai implementation cạnh tranh một vai trò nhưng selector không rõ.
- Root chọn `NoOp` thay vì adapter thật.
- Một handler chưa được nối vào router hoặc queue consumer.
- Provider tạo dependency sai khi request đầu tiên gọi.
- Scope tạo theo request bị giữ trong singleton.
- Config được đọc nhưng không được truyền đến adapter cần nó.

Cần kiểm tra các **invariant của graph**, không chỉ `instanceof` hoặc `!= null`.

## 10. Các tình huống chẩn đoán khác ngoài “không có binding”

### 10.1. Nhiều ứng viên, không biết chọn ai

Nếu có hai `PaymentGateway` hoặc hai `ReceiptSender` cùng vai trò, container có thể báo cấu hình mơ hồ, hoặc root thủ công có thể chọn nhầm.

**Chẩn đoán:** kiểm tra điều kiện lựa chọn, tên/qualifier/khóa, và test với tất cả mode được hỗ trợ. Đừng dựa vào thứ tự duyệt `HashMap` hay thứ tự đăng ký không được quy định.

### 10.2. Cấu hình lắp ghép có dependency vòng

`ServiceA` bắt buộc có `ServiceB` qua constructor trong khi `ServiceB` cũng bắt buộc có `ServiceA`. Root thủ công không thể tạo một graph constructor thuần bằng cách đổi thứ tự `new`. Container cũng có thể phát hiện hoặc báo lỗi tùy cơ chế.

**Chẩn đoán:** xem lại ranh giới trách nhiệm, tách hợp đồng hoặc chuyển sang cơ chế điều phối hợp lý. Không giấu vòng bằng Service Locator hay provider tùy tiện chỉ để test khởi động PASS.

### 10.3. Service được tạo nhưng entry point không sử dụng

Một smoke test gọi `new CheckoutService(...)` có thể PASS, trong khi router chưa đăng ký `/checkout`, command chưa được đưa vào CLI hoặc worker không đăng ký message handler.

**Chẩn đoán:** có ít nhất một test ở **ranh giới entry point** phù hợp với executable. Nếu framework tạo handler tự động, cần xác nhận handler thực sự hiện diện và có dependency đã nối.

### 10.4. Startup không lỗi nhưng lazy provider lỗi ở first use

```java
// Pseudocode: root inject factory, chưa gọi factory tại startup.
CheckoutService service = new CheckoutService(
        repository,
        new LazyReceiptSender(() -> createEmailSender(config)));
```

Đoạn trên dùng một decorator/factory giả định chưa được định nghĩa trong ví dụ chạy. Nếu `createEmailSender` đọc cấu hình hoặc mở kết nối lúc đầu tiên gửi, root có thể báo READY trước khi phát hiện thiếu secret.

**Chẩn đoán:** phân loại dependency nào cần **fail-fast trước READY**, dependency nào có thể lazy theo chính sách. Nếu bắt buộc, dùng warm-up/readiness có ý nghĩa và test đường tạo thật; nếu tùy chọn, thiết kế lỗi first-use và fallback tường minh.

### 10.5. Đối tượng đúng nhưng vòng đời sai

Một root có thể inject đúng interface nhưng giữ `RequestContext` từ request đầu trong singleton, hoặc đóng connection pool trước khi các request đang xử lý kết thúc.

**Chẩn đoán:** test identity theo scope, ownership, cleanup khi exception và shutdown. “Wiring đủ” chỉ là điều kiện cần; **lifetime của các tham chiếu phải tương thích**.

## 11. Không nên sửa lỗi wiring bằng những cách che giấu lỗi

| Cách sửa vội | Vì sao nguy hiểm | Hướng tốt hơn |
| --- | --- | --- |
| `new` adapter trong service khi locator trả `null`. | Tạo phụ thuộc ngầm, lẫn cấu hình và logic nghiệp vụ. | Sửa đăng ký/selection tại root; inject qua constructor. |
| Gắn `NoOpReceiptSender` làm default không có chủ đích. | Test/health xanh nhưng chức năng bắt buộc biến mất. | Chế độ demo/tắt tính năng phải tường minh và được test. |
| Test chỉ dùng fake rồi bỏ qua bootstrap. | Không phát hiện graph production thiếu. | Giữ unit test, bổ sung composition smoke test thật. |
| Chạy toàn bộ framework/context cho từng unit test. | Test chậm, khó xác định nguyên nhân và vẫn có thể override binding. | Phân tầng test: unit nhanh, một số root/integration test chọn lọc. |
| Catch mọi lỗi startup rồi tiếp tục báo READY. | Chuyển lỗi cấu hình thành lỗi request khó phát hiện. | Fail-fast cho dependency bắt buộc và log mã lỗi an toàn. |
| Bật mọi profile/binding trong CI để “chắc chắn đủ”. | Có thể tạo tổ hợp khác production, che thiếu binding ở profile thực. | Dựng từng cấu hình hợp lệ theo cùng cơ chế lựa chọn. |
| Ghi log toàn bộ configuration/exception. | Có thể lộ password, token, endpoint chứa credential. | Log các trường đã được phép và mã lỗi có thể đối chiếu. |

## 12. Khi sử dụng DI container, cần kiểm tra điều gì?

Sau khi hiểu wiring bằng Java thuần, DI container có thể tự động hóa việc chọn, tạo và inject. Nhưng **container không bảo đảm rằng mọi profile và entry point đã được kiểm chứng**.

Những lỗi thường xuất hiện ở cấu hình container:

- Bean/implementation không được đăng ký hoặc nằm ngoài phạm vi module scan.
- Binding bị loại bởi profile, điều kiện, feature flag hoặc cấu hình environment.
- Có nhiều bean cùng kiểu, nhưng qualifier/selection không rõ hoặc sai.
- Một bean bị thay bằng mock/test override, khiến test pass khác production.
- Scope singleton/request/task bị phối hợp sai.
- Circular dependency hoặc vòng đời khởi tạo không phù hợp.
- Lazy bean chỉ nổ khi được truy xuất lần đầu.
- Controller/listener chưa được đăng ký dù service đã có trong container.
- Hook startup/shutdown không quản lý đúng resource do ứng dụng tự tạo.

### 12.1. Kiểm thử container với cấu hình gần production

Một container smoke test nên:

1. Nạp **module cấu hình thực của executable** cần kiểm tra.
2. Chọn profile/feature flag đại diện cho trạng thái triển khai thật.
3. Tránh ghi đè những binding **đang muốn kiểm chứng** bằng mock.
4. Xác nhận graph tạo được và những entry point/handler quan trọng hiện diện.
5. Nếu cần readiness, kích hoạt đường khởi tạo lazy hoặc kiểm tra tích hợp phù hợp.
6. Dọn container và tài nguyên đúng lifecycle của framework.

Tên annotation, chính sách scan, qualifier, lazy và destroy callback **phụ thuộc framework**. Không nên kết luận từ một cú pháp DI container bất kỳ rằng mọi implementation đã được load đúng; hãy đọc contract của framework và test bằng chính cách bootstrap đó.

### 12.2. Root không nhất thiết nằm trong một file duy nhất

Một ứng dụng có thể tổ chức wiring thành nhiều factory/module, rồi composition root điều phối chúng. Test không cần assert mọi lời gọi `new` nằm trong `main`; cần xác nhận **đường bootstrap thực** đã tạo và nối graph đúng.

Ngược lại, nếu test gọi một factory phụ nhưng executable không bao giờ gọi factory đó, test vẫn có thể xanh. Chẩn đoán phải lần theo **đường từ entry point khởi động**, không chỉ kiểm tra một module wiring đứng riêng.

## 13. CI/CD nên có những chốt kiểm tra gì?

Một pipeline hợp lý cho bài toán wiring có thể chia thành các nhóm:

```text
Compile / static checks
          |
          v
Fast unit tests (fake, Clock.fixed, no network)
          |
          v
Composition smoke tests
  - executable A / profile X
  - executable A / profile Y
  - worker B / profile Z
          |
          v
Selected integration tests
  - database/test server/queue/sandbox
          |
          v
Deployment smoke/readiness checks
  - route/handler được đăng ký
  - cấu hình bắt buộc hợp lệ
  - tài nguyên thiết yếu sẵn sàng
```

Các chốt kiểm tra có thể chạy ở thời điểm khác nhau; không nhất thiết mọi test dùng cùng một máy hay cùng một môi trường. Quan trọng là **mỗi chốt có một phạm vi và điều kiện PASS rõ ràng**.

### 13.1. Không mở kết nối production chỉ để kiểm tra wiring

Root smoke test ở CI không nên làm side effect như gửi tiền, gửi email tới khách hàng hoặc ghi dữ liệu production. Đối với adapter thật, dùng cấu hình sandbox/test server hoặc chế độ chỉ xác thực cấu trúc khi phù hợp. Những kiểm tra có I/O phải có quyền truy cập, cleanup và giới hạn tác động rõ ràng.

Một phương án thiết kế là tách **cấu hình/binding validation** khỏi **connection warm-up**, nhưng phải có test bổ sung kiểm tra quá trình warm-up thật. Tách pha giúp kiểm tra nhanh, không phải lý do bỏ qua lỗi kết nối.

### 13.2. Không biến health check thành một bài test giả

Một endpoint `/health` trả HTTP 200 vì tiến trình còn chạy không chứng minh các dependency bắt buộc đang được nối đúng. `Liveness` và `readiness` có mục tiêu khác nhau.

Nếu readiness yêu cầu email sender hoặc database phải dùng được, cần xác định cách kiểm tra theo hợp đồng vận hành. Đồng thời phải tránh health check tạo side effect nguy hiểm hoặc gửi request tốn phí không kiểm soát.

### 13.3. Ghi nhận nguyên nhân có thể hành động

Một lỗi như `WIRING_MISSING_SENDER:EMAIL` cho biết **vai trò** và **lựa chọn cấu hình** đang thiếu, hỗ trợ sửa ở composition root. Kèm correlation ID hoặc tên module đã được cho phép có thể hữu ích. Tránh đưa secret, raw request body, token hoặc toàn bộ cause của thư viện chưa rà soát vào telemetry.

## 14. Bài tập thực hành: một worker dùng cấu hình khác API

**Bối cảnh:** hệ thống đặt hàng có hai executable:

- **API server:** tạo đơn và ghi vào repository.
- **Worker:** đọc sự kiện `ORDER_CREATED`, chọn `NotificationSender` theo kênh `EMAIL` hoặc `SMS`, rồi gửi thông báo.

Unit test của `NotificationService` dùng `FakeMessageRepository` và `RecordingNotificationSender`; tất cả PASS. API cũng khởi động được. Tuy nhiên, worker ở production chọn `SMS` mà module wiring chỉ đăng ký sender `EMAIL`.

Hãy thực hiện:

1. **Vẽ hai object graph** cho API và worker. Phân biệt binding dùng chung và binding chỉ thuộc worker.
2. **Giải thích unit PASS:** fake trong unit test đã chứng minh điều gì, và vì sao không chạm tới lỗi thiếu `SMS`?
3. **Thiết kế mã lỗi:** nếu worker chọn `SMS` nhưng không có sender, composition root nên báo lỗi gì và ở pha nào?
4. **Viết root smoke test:** tạo worker graph bằng mode `EMAIL` và `SMS`, xác minh cả hai mode hỗ trợ tạo entry point và gọi handler thử trong môi trường an toàn.
5. **Viết negative test:** cố ý bỏ sender `SMS` và assert root fail-fast, không fallback sang `EMAIL` hoặc `NoOp`.
6. **Phân biệt kiểm tra cấu hình và I/O:** root tạo được `SmsSender` có chứng minh API SMS thật sẽ chấp nhận token và request không? Cần integration test nào?
7. **Xử lý lazy:** nếu SMS client được tạo khi message đầu tiên đến, phải bổ sung kiểm tra readiness hoặc chính sách first-use failure nào?
8. **Xử lý lifecycle:** ai sở hữu SMS client và message consumer? Khi worker shutdown, phải ngừng nhận message, xử lý in-flight và đóng resource theo thứ tự nào?
9. **Cấu hình nhiều môi trường:** lập ma trận local/staging/production. Trong profile nào sender SMS được đăng ký, trong profile nào được phép tắt? Viết rõ nguyên tắc chọn binding.
10. **Bảo vệ dữ liệu:** lỗi thiếu token có thể log tên khóa nhưng không log giá trị. Hãy đề xuất hai mã lỗi an toàn và hai trường metadata được phép ghi.

**Gợi ý đối chiếu:** unit test dùng fake là đúng để kiểm chứng logic của `NotificationService`; lỗi nằm ở **worker composition root** và cấu hình `SMS`. Tách graph theo executable, có smoke test cho các mode được hỗ trợ và integration test cho SMS sandbox. Nếu `SMS` là bắt buộc, phải từ chối startup thiếu binding; nếu tính năng tùy chọn thì biểu diễn chế độ tắt tường minh. Với client lazy, cần kiểm tra đúng thời điểm yêu cầu readiness. Không giả định API server khởi động tốt đồng nghĩa worker đã có đủ dependency.

## 15. Checklist chẩn đoán nhanh

| Câu hỏi | Dấu hiệu cần có |
| --- | --- |
| Unit test có sử dụng root của ứng dụng không? | Biết rõ unit dùng graph riêng và có lớp test khác kiểm tra root. |
| Có liệt kê mode/profile được hỗ trợ không? | Có ma trận cấu hình tối thiểu cho từng executable. |
| Root có từ chối thiếu dependency bắt buộc không? | Có mã lỗi fail-fast, không dùng `null` hoặc No-Op fallback ngầm. |
| Binding có đúng implementation, không chỉ đúng interface? | Test lựa chọn theo khóa/profile và kiểm chứng hành vi entry point. |
| Có kiểm tra các nhánh lazy trọng yếu? | Readiness/warm-up hoặc test first-use theo hợp đồng. |
| Entry point có được đăng ký và gọi thật trong test? | Không chỉ assert service constructor thành công. |
| Scope và ownership có được kiểm tra? | Không giữ request context trong singleton; close đúng sau stop/drain. |
| Test có che cấu hình production bằng mock override không? | Root smoke test không thay những binding đang muốn chứng minh. |
| Adapter thật có integration test trong môi trường an toàn? | Có kiểm tra I/O, giao thức và lỗi của boundary quan trọng. |
| Log chẩn đoán có để lộ secret không? | Chỉ dùng mã lỗi và trường metadata đã được phép. |
| Khi thêm implementation/route mới, test nào phải đổi? | Có quy trình cập nhật ma trận và smoke test của graph liên quan. |

**Điểm cần nhớ:** **Unit test PASS không có nghĩa application composition root đã được kiểm chứng.** Constructor injection giúp dependency của từng lớp rõ ràng, nhưng chỉ những bài test **thực sự dựng graph của executable với cấu hình tương ứng** mới có thể phát hiện thiếu/sai binding ở ranh giới lắp ghép. Hãy kết hợp unit test với composition smoke test, readiness và integration test theo mục tiêu; báo lỗi cấu hình bắt buộc sớm, tránh fallback ngầm và luôn kiểm soát scope, lifecycle trước khi giao wiring cho DI container.
