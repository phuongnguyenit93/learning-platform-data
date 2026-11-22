# Thiết lập ngoại lệ từ thành phần được giả lập

Trong kiểm thử đơn vị, một service thường phụ thuộc vào repository, HTTP client, payment gateway hoặc một thành phần bên ngoài. Để kiểm tra nhánh lỗi mà không tạo sự cố thật, ta có thể cấu hình mock ném một ngoại lệ tại đúng lời gọi cần kiểm tra. Test từ đó xác nhận service xử lý, chuyển đổi hoặc truyền tiếp lỗi theo hợp đồng của nó.

Mockito cung cấp hai cách stubbing chính: `when(...).thenThrow(...)` cho phương thức trả về giá trị và `doThrow(...).when(...)` cho phương thức `void`. Kết hợp chúng với `assertThrows` của JUnit để kiểm tra ngoại lệ, nguyên nhân gốc và các tương tác liên quan.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Cấu hình mock ném checked exception và unchecked exception.
- Dùng `thenThrow` cho phương thức trả về giá trị.
- Dùng `doThrow` cho phương thức `void`.
- Thiết lập nhiều hành vi liên tiếp hoặc ném exception theo tham số.
- Kiểm tra service chuyển đổi, giữ nguyên hoặc xử lý exception từ collaborator.
- Hiểu giới hạn của checked exception và cách Mockito xác thực kiểu exception.
- Tránh lỗi khi cấu hình exception trên mock và spy.
- Mô phỏng đúng lỗi của API bất đồng bộ trả về `CompletableFuture`.

## 1. Vì sao cần thiết lập ngoại lệ trên mock?

Giả sử `CheckoutService` gọi `PaymentGateway` để thu tiền. Khi gateway timeout, service cần chuyển lỗi kỹ thuật thành lỗi phù hợp với nghiệp vụ. Nếu chỉ kiểm thử trường hợp thành công, ta chưa biết service có xử lý đúng khi collaborator thất bại hay không.

Có thể mô phỏng các tình huống như:

- HTTP client nhận timeout hoặc lỗi kết nối.
- Repository ném lỗi truy cập dữ liệu.
- Payment gateway từ chối giao dịch hoặc không phản hồi.
- Message publisher không thể gửi message.
- File storage không đọc hoặc ghi được tài nguyên.
- Một collaborator ném exception theo dữ liệu đầu vào cụ thể.

Mock giúp test điều khiển thời điểm và loại ngoại lệ. Test không cần tắt mạng, làm database ngừng hoạt động hoặc tạo sự cố không ổn định trong môi trường kiểm thử.

Một test dùng mock chỉ xác nhận cách class đang kiểm tra phản ứng với ngoại lệ được mô phỏng. Nó không chứng minh HTTP client, database driver hoặc dịch vụ bên ngoài thực sự phát sinh ngoại lệ đó trong production. Hành vi tích hợp của các thành phần ấy cần được kiểm tra ở mức phù hợp khác.

## 2. Ví dụ: service chuyển ngoại lệ của gateway thành lỗi nghiệp vụ

Ta bắt đầu bằng một gateway có thể ném checked exception:

~~~java
public interface PaymentGateway {

    PaymentResult charge(PaymentCommand command)
            throws PaymentGatewayException;
}
~~~

Các kiểu dữ liệu minh họa:

~~~java
public record PaymentCommand(String orderId, long amount) {}

public record PaymentResult(String transactionId) {}

public class PaymentGatewayException extends Exception {

    public PaymentGatewayException() {
        super();
    }

    public PaymentGatewayException(String message) {
        super(message);
    }
}
~~~

Service xử lý lỗi từ gateway:

~~~java
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public Receipt checkout(PaymentCommand command) {
        try {
            PaymentResult result = paymentGateway.charge(command);
            return new Receipt(command.orderId(), result.transactionId());
        } catch (PaymentGatewayException exception) {
            throw new CheckoutFailedException(
                "Payment could not be completed",
                exception
            );
        }
    }
}
~~~

Ngoại lệ nghiệp vụ giữ ngoại lệ gốc làm cause:

~~~java
public class CheckoutFailedException extends RuntimeException {

    public CheckoutFailedException(String message, Throwable cause) {
        super(message, cause);
    }
}

public record Receipt(String orderId, String transactionId) {}
~~~

Trong test, ta cấu hình mock gateway ném `PaymentGatewayException`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    PaymentGateway paymentGateway;

    @InjectMocks
    CheckoutService checkoutService;

    @Test
    void convertsGatewayFailureToCheckoutFailure() throws Exception {
        PaymentCommand command =
            new PaymentCommand("ORDER-100", 250_000);

        PaymentGatewayException gatewayFailure =
            new PaymentGatewayException("Gateway timed out");

        when(paymentGateway.charge(command))
            .thenThrow(gatewayFailure);

        CheckoutFailedException thrown = assertThrows(
            CheckoutFailedException.class,
            () -> checkoutService.checkout(command)
        );

        assertEquals(
            "Payment could not be completed",
            thrown.getMessage()
        );
        assertSame(gatewayFailure, thrown.getCause());

        verify(paymentGateway).charge(command);
    }
}
~~~

Có ba việc diễn ra:

1. `when(paymentGateway.charge(command))` chỉ định lời gọi mà mock cần xử lý.
2. `thenThrow(gatewayFailure)` quy định ngoại lệ được ném khi lời gọi đó xảy ra.
3. `assertThrows` gọi service và xác nhận ngoại lệ mà service công bố ra ngoài.

`assertSame` kiểm tra cause chính là instance ngoại lệ ban đầu. Điều này hữu ích khi service cần giữ lại thông tin nguyên nhân để log, chẩn đoán hoặc xử lý ở tầng cao hơn.

## 3. Dùng thenThrow cho phương thức trả về giá trị

Cú pháp cơ bản:

~~~java
when(mock.someMethod(arguments))
    .thenThrow(exception);
~~~

Ví dụ:

~~~java
when(paymentGateway.charge(command))
    .thenThrow(new PaymentGatewayException("Connection refused"));
~~~

Khi code gọi đúng phương thức với các đối số khớp, mock ném ngoại lệ thay vì trả về giá trị mặc định.

### Truyền instance ngoại lệ

~~~java
PaymentGatewayException failure =
    new PaymentGatewayException("Payment provider unavailable");

when(paymentGateway.charge(command))
    .thenThrow(failure);
~~~

Dùng instance khi test cần kiểm tra message, cause hoặc một trạng thái cụ thể của exception. Mockito ném instance đã cung cấp.

Nếu cùng một stub được gọi nhiều lần, việc dùng lại một instance có thể làm stack trace khó đọc. Với test cần mỗi lần gọi có một exception instance mới, cân nhắc dạng truyền class.

### Truyền class ngoại lệ

~~~java
when(paymentGateway.charge(command))
    .thenThrow(PaymentGatewayException.class);
~~~

Mockito tạo instance của kiểu exception khi stub được gọi. Kiểu này phù hợp khi test chỉ cần loại ngoại lệ, không cần cấu hình message hoặc cause riêng. Exception class phải có constructor mà Mockito có thể sử dụng để khởi tạo.

Nếu cần message tùy chỉnh hoặc kiểm tra đúng cause, truyền instance thường rõ ràng hơn.

### Ném unchecked exception

Unchecked exception không cần khai báo trong chữ ký phương thức:

~~~java
when(paymentGateway.charge(command))
    .thenThrow(new IllegalStateException("Gateway is not initialized"));
~~~

Cách thiết lập giống checked exception. Điểm khác biệt nằm ở quy tắc Java: unchecked exception thuộc nhóm `RuntimeException` hoặc `Error`, nên phương thức không cần khai báo `throws`.

## 4. Checked exception phải phù hợp với chữ ký phương thức

Java quy định checked exception phải được khai báo hoặc xử lý. Mockito cũng kiểm tra tính hợp lệ của checked exception khi cấu hình stub.

Nếu phương thức khai báo:

~~~java
PaymentResult charge(PaymentCommand command)
        throws PaymentGatewayException;
~~~

thì có thể cấu hình:

~~~java
when(paymentGateway.charge(command))
    .thenThrow(new PaymentGatewayException("Provider unavailable"));
~~~

Nhưng nếu phương thức không khai báo checked exception:

~~~java
public interface ProductCache {
    Product find(String productId);
}
~~~

thì cấu hình checked exception không tương thích:

~~~java
when(productCache.find("P-100"))
    .thenThrow(new IOException("Disk error"));
~~~

Mockito sẽ báo lỗi cấu hình vì `IOException` là checked exception mà phương thức `find` không khai báo. Trong trường hợp này, có thể dùng một unchecked exception phù hợp với hợp đồng:

~~~java
when(productCache.find("P-100"))
    .thenThrow(new IllegalStateException("Cache is unavailable"));
~~~

Đừng biến checked exception thành unchecked chỉ để làm test chạy. Hãy chọn exception đúng với API mà collaborator công bố. Nếu API thực sự có thể ném checked exception, chữ ký phương thức cần phản ánh điều đó.

## 5. Dùng doThrow cho phương thức void

Với phương thức có giá trị trả về, Mockito có thể ghi nhận lời gọi trong biểu thức `when(...)`. Phương thức `void` không có giá trị để truyền vào `when`, vì vậy cần cú pháp `doThrow(...).when(...)`.

Giả sử một notifier có phương thức gửi thông báo:

~~~java
public interface NotificationClient {

    void send(Notification notification)
            throws NotificationDeliveryException;
}

public record Notification(String recipient, String message) {}

public class NotificationDeliveryException extends Exception {

    public NotificationDeliveryException(String message) {
        super(message);
    }
}
~~~

Cấu hình mock ném exception:

~~~java
doThrow(new NotificationDeliveryException("SMTP unavailable"))
    .when(notificationClient)
    .send(any(Notification.class));
~~~

Một service chuyển lỗi thành exception nghiệp vụ:

~~~java
public class NotificationService {

    private final NotificationClient client;

    public NotificationService(NotificationClient client) {
        this.client = client;
    }

    public void notifyUser(Notification notification) {
        try {
            client.send(notification);
        } catch (NotificationDeliveryException exception) {
            throw new NotificationFailedException(
                "Could not notify recipient",
                exception
            );
        }
    }
}
~~~

~~~java
public class NotificationFailedException extends RuntimeException {

    public NotificationFailedException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Test:

~~~java
@Test
void convertsDeliveryFailureToNotificationFailure() throws Exception {
    NotificationClient client = mock(NotificationClient.class);
    NotificationService service = new NotificationService(client);

    Notification notification =
        new Notification("ada@example.com", "Your order is ready");

    NotificationDeliveryException cause =
        new NotificationDeliveryException("SMTP unavailable");

    doThrow(cause)
        .when(client)
        .send(notification);

    NotificationFailedException thrown = assertThrows(
        NotificationFailedException.class,
        () -> service.notifyUser(notification)
    );

    assertSame(cause, thrown.getCause());
    verify(client).send(notification);
}
~~~

Cú pháp này cũng dùng được với unchecked exception:

~~~java
doThrow(new IllegalStateException("Client is closed"))
    .when(notificationClient)
    .send(any(Notification.class));
~~~

Khi dùng argument matcher, hãy tuân thủ quy tắc Mockito: nếu một lời gọi có nhiều tham số và đã dùng matcher cho một tham số, hãy dùng matcher cho tất cả tham số của lời gọi đó.

## 6. Thiết lập nhiều lần gọi liên tiếp

Một số tình huống cần mô phỏng lần gọi đầu thất bại nhưng lần sau thành công. Mockito cho phép nối các hành vi trong cùng một stub.

Ví dụ lần đầu client timeout, lần tiếp theo trả về sản phẩm:

~~~java
when(catalogClient.find("BOOK-1"))
    .thenThrow(new CatalogTimeoutException("Temporary timeout"))
    .thenReturn(new Product("BOOK-1", "Spring Testing"));
~~~

Test xác nhận thứ tự hành vi:

~~~java
@Test
void receivesFailureFirstAndProductOnRetry() {
    when(catalogClient.find("BOOK-1"))
        .thenThrow(new CatalogTimeoutException("Temporary timeout"))
        .thenReturn(new Product("BOOK-1", "Spring Testing"));

    assertThrows(
        CatalogTimeoutException.class,
        () -> catalogClient.find("BOOK-1")
    );

    Product product = catalogClient.find("BOOK-1");

    assertEquals("Spring Testing", product.name());
}
~~~

Nếu stub có nhiều hành vi nối tiếp và số lần gọi vượt quá số hành vi đã khai báo, Mockito tiếp tục lặp lại hành vi cuối cùng. Ví dụ, sau một lần ném exception rồi một lần trả về product, các lần gọi tiếp theo tiếp tục trả về product.

Có thể thiết lập nhiều ngoại lệ liên tiếp:

~~~java
when(catalogClient.find("BOOK-1"))
    .thenThrow(
        new CatalogTimeoutException("First timeout"),
        new CatalogTimeoutException("Second timeout")
    )
    .thenReturn(new Product("BOOK-1", "Spring Testing"));
~~~

Kiểu thiết lập này hữu ích để kiểm tra retry, nhưng hãy đặt nó ở ranh giới mà logic retry thực sự sử dụng. Nếu service có vòng lặp retry, hãy gọi service và xác nhận kết quả cũng như số lần gọi, thay vì chỉ gọi mock thủ công rồi kết luận retry hoạt động.

Ví dụ kiểm tra số lần thử:

~~~java
verify(catalogClient, times(3)).find("BOOK-1");
~~~

Số lần mong đợi phải khớp chính sách retry của service, gồm cả lần gọi đầu và các lần thử lại.

## 7. Ném exception có điều kiện bằng thenAnswer

Đôi khi exception phụ thuộc vào đối số hoặc trạng thái của lời gọi. Khi đó, có thể dùng `thenAnswer` để quyết định hành vi trong callback.

Ví dụ client chỉ timeout với một mã sản phẩm:

~~~java
when(catalogClient.find(anyString()))
    .thenAnswer(invocation -> {
        String productId = invocation.getArgument(0);

        if ("SLOW-ITEM".equals(productId)) {
            throw new CatalogTimeoutException("Lookup timed out");
        }

        return new Product(productId, "Available product");
    });
~~~

Test:

~~~java
@Test
void throwsOnlyForTheSlowProduct() {
    when(catalogClient.find(anyString()))
        .thenAnswer(invocation -> {
            String productId = invocation.getArgument(0);

            if ("SLOW-ITEM".equals(productId)) {
                throw new CatalogTimeoutException("Lookup timed out");
            }

            return new Product(productId, "Available product");
        });

    assertThrows(
        CatalogTimeoutException.class,
        () -> catalogClient.find("SLOW-ITEM")
    );

    Product product = catalogClient.find("BOOK-1");

    assertEquals("BOOK-1", product.id());
}
~~~

`thenAnswer` linh hoạt nhưng có thể khiến test khó đọc nếu callback chứa nhiều logic. Nếu chỉ cần ném một exception cố định, hãy dùng `thenThrow`. Chỉ dùng `thenAnswer` khi quyết định thực sự phụ thuộc vào tham số, số lần gọi hoặc dữ liệu trong invocation.

## 8. Thiết lập ngoại lệ trên spy

Mock không gọi implementation thật theo mặc định. Spy thì khác: nó bao quanh một đối tượng thật và thường gọi phương thức thật nếu chưa được stub.

Ví dụ:

~~~java
CatalogRepository repository = spy(new CatalogRepository());
~~~

Nếu viết:

~~~java
when(repository.load("BOOK-1"))
    .thenThrow(new CatalogAccessException("Unavailable"));
~~~

thì biểu thức `repository.load("BOOK-1")` được gọi ngay khi Mockito đánh giá đối số của `when`. Với spy, lời gọi thật có thể chạy ngay tại bước cấu hình. Nếu phương thức thật truy cập file, database hoặc ném exception, test có thể thất bại trước khi stub được cài đặt.

Để tránh gọi implementation thật trong lúc stubbing, dùng dạng `doThrow`:

~~~java
doThrow(new CatalogAccessException("Unavailable"))
    .when(repository)
    .load("BOOK-1");
~~~

Dạng này đặc biệt hữu ích cho spy khi phương thức thật có side effect hoặc không thể chạy trong lúc chuẩn bị test.

Với phương thức `void` trên spy, `doThrow` cũng là cách cấu hình phù hợp:

~~~java
doThrow(new IllegalStateException("Cannot refresh"))
    .when(repository)
    .refresh();
~~~

| Đối tượng | Cú pháp thường dùng | Lưu ý |
|---|---|---|
| Mock, phương thức trả về giá trị | `when(mock.call()).thenThrow(...)` | Mock không chạy implementation thật |
| Mock, phương thức void | `doThrow(...).when(mock).call()` | Không có giá trị trả về để dùng trong when |
| Spy, phương thức trả về giá trị | `doThrow(...).when(spy).call()` | Tránh gọi implementation thật trong lúc stubbing |
| Spy, phương thức void | `doThrow(...).when(spy).call()` | Cấu hình exception mà không chạy phương thức thật |

Không nên dùng spy chỉ vì muốn một phần dependency thật. Với unit test, mock hoặc fake thường làm ranh giới rõ ràng hơn. Chỉ dùng spy khi cần giữ lại phần lớn hành vi thật và chỉ thay thế có chủ đích một số lời gọi.

## 9. Kiểm tra điều gì sau khi ngoại lệ được ném?

Một test tốt không dừng ở việc xác nhận có exception. Hãy kiểm tra hợp đồng lỗi mà class đang kiểm tra phải cung cấp.

### Kiểm tra loại ngoại lệ

~~~java
CheckoutFailedException thrown = assertThrows(
    CheckoutFailedException.class,
    () -> checkoutService.checkout(command)
);
~~~

`assertThrows` trả về chính exception được ném, vì vậy có thể kiểm tra thêm message, cause hoặc thuộc tính riêng.

### Kiểm tra message và cause

~~~java
assertEquals(
    "Payment could not be completed",
    thrown.getMessage()
);
assertInstanceOf(
    PaymentGatewayException.class,
    thrown.getCause()
);
~~~

Nếu cần xác nhận đúng instance cause:

~~~java
assertSame(gatewayFailure, thrown.getCause());
~~~

### Xác nhận collaborator đã được gọi

~~~java
verify(paymentGateway).charge(command);
~~~

Điều này chứng minh service đã đi qua lời gọi gây lỗi dự kiến.

### Xác nhận các bước tiếp theo không xảy ra

Giả sử service chỉ lưu receipt sau khi thanh toán thành công. Khi gateway ném exception, test nên xác nhận repository không được gọi:

~~~java
verifyNoInteractions(receiptRepository);
~~~

Nếu repository đã có tương tác khác trước đó, dùng kiểm tra cụ thể hơn:

~~~java
verify(receiptRepository, never()).save(any(Receipt.class));
~~~

Chọn assertion phản ánh hợp đồng nghiệp vụ. Không cần xác minh mọi lời gọi nội bộ nếu chúng không ảnh hưởng đến kết quả hoặc side effect mà người dùng quan tâm.

## 10. Ngoại lệ đồng bộ và phương thức bất đồng bộ

Một điểm dễ nhầm là phương thức trả về `CompletableFuture`. Khi dependency hoạt động bất đồng bộ, lỗi của tác vụ thường được biểu diễn bằng một future thất bại, thay vì ném trực tiếp ngay lúc gọi phương thức.

Ví dụ interface:

~~~java
public interface RemoteCatalogClient {
    CompletableFuture<Product> findAsync(String productId);
}
~~~

Để mô phỏng future thất bại:

~~~java
when(remoteCatalogClient.findAsync("BOOK-1"))
    .thenReturn(
        CompletableFuture.failedFuture(
            new CatalogTimeoutException("Remote lookup timed out")
        )
    );
~~~

Service có thể xử lý lỗi trong pipeline:

~~~java
public CompletableFuture<Product> findProduct(String productId) {
    return remoteCatalogClient.findAsync(productId)
        .exceptionally(exception -> {
            throw new CompletionException(
                new CatalogUnavailableException(
                    "Catalog is unavailable",
                    exception
                )
            );
        });
}
~~~

Trong test, hãy chờ hoặc join future rồi kiểm tra exception theo cách mà API bất đồng bộ công bố. Ví dụ:

~~~java
CompletionException thrown = assertThrows(
    CompletionException.class,
    () -> service.findProduct("BOOK-1").join()
);
~~~

Nếu dùng `thenThrow` cho phương thức trả về future:

~~~java
when(remoteCatalogClient.findAsync("BOOK-1"))
    .thenThrow(new IllegalStateException("Client not initialized"));
~~~

thì exception xảy ra đồng bộ ngay trong lúc gọi `findAsync`. Điều đó khác với một future được trả về ở trạng thái failed. Hãy chọn cách mô phỏng khớp với hợp đồng thực tế của collaborator.

## 11. Các lỗi thường gặp khi cấu hình exception

- **Dùng `when(...).thenThrow(...)` cho phương thức void:** Java không có giá trị trả về để đặt trong when; hãy dùng `doThrow(...).when(mock).method(...)`.
- **Ném checked exception không được khai báo:** Mockito sẽ báo lỗi stubbing không hợp lệ. Kiểm tra chữ ký phương thức và dùng kiểu exception phù hợp.
- **Cấu hình sai đối số:** stub chỉ áp dụng cho lời gọi khớp với đối số hoặc matcher. Lời gọi không khớp có thể nhận giá trị mặc định của mock thay vì exception.
- **Dùng matcher không nhất quán:** nếu một tham số dùng matcher, các tham số còn lại trong cùng lời gọi cũng cần matcher.
- **Chỉ kiểm tra exception mà bỏ qua hành vi sau lỗi:** service có thể ném đúng loại exception nhưng vẫn ghi dữ liệu hoặc gọi một collaborator không nên được gọi.
- **Dùng spy như mock:** spy gọi implementation thật khi chưa được stub. Hãy cân nhắc side effect và dùng cú pháp `doThrow` khi cần.
- **Dùng một exception instance cho nhiều test:** mỗi test nên tự cấu hình mock và exception của mình, tránh chia sẻ trạng thái.
- **Mô phỏng lỗi đồng bộ cho API bất đồng bộ:** nếu API trả future thất bại, hãy trả `CompletableFuture.failedFuture(...)` để kiểm tra đúng đường xử lý.
- **Dùng exception quá chung chung:** ưu tiên loại exception có ý nghĩa với hợp đồng của collaborator, để test diễn đạt đúng tình huống cần mô phỏng.
- **Coi mock là bằng chứng tích hợp:** test mock xác nhận phản ứng của class đang kiểm tra; nó không kiểm chứng giao thức hoặc lỗi thật của dịch vụ bên ngoài.

## 12. Quy trình thiết lập và kiểm tra ngoại lệ

Khi cần kiểm tra nhánh lỗi của một collaborator, hãy làm theo trình tự:

1. Xác định lời gọi nào có thể thất bại và loại exception mà API khai báo hoặc quy ước.
2. Tạo mock bằng Mockito hoặc dùng mock đã được inject vào class đang kiểm tra.
3. Chọn đúng cú pháp: `when(...).thenThrow(...)` cho phương thức trả về giá trị, `doThrow(...).when(...)` cho phương thức void hoặc khi cần tránh gọi implementation thật trên spy.
4. Cấu hình exception instance nếu cần kiểm tra message/cause; dùng class khi chỉ cần loại exception.
5. Gọi class đang kiểm tra để đi qua nhánh lỗi.
6. Dùng `assertThrows` hoặc cách kiểm tra tương ứng với API bất đồng bộ.
7. Kiểm tra message, cause và trạng thái nghiệp vụ được công bố.
8. Xác minh collaborator đã được gọi đúng và side effect không mong muốn không xảy ra.
9. Chạy test độc lập và bảo đảm mỗi test tự tạo, cấu hình dependency của nó.

## Kết luận

Mockito cho phép mô phỏng lỗi của collaborator một cách có kiểm soát. Dùng `thenThrow` cho phương thức trả về giá trị, `doThrow` cho phương thức void và cho các tình huống spy cần tránh gọi implementation thật trong lúc cấu hình. Kết hợp stubbing với `assertThrows`, kiểm tra cause và xác minh side effect để chứng minh class đang kiểm tra xử lý lỗi đúng theo hợp đồng.

Một mock có thể tạo ra đúng tình huống lỗi mà test cần, nhưng ý nghĩa của test nằm ở phản ứng của service hoặc class đang kiểm tra. Giữ test tập trung vào phản ứng đó sẽ làm nhánh lỗi rõ ràng, ổn định và dễ bảo trì.

