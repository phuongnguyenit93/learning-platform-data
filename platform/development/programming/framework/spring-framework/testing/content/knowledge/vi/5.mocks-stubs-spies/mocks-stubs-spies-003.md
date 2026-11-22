# Tạo Mockito mock và khai báo dữ liệu trả về

Mockito giúp bài kiểm thử kiểm soát các phụ thuộc của lớp đang được kiểm tra. Ta có thể tạo một đối tượng mock từ interface hoặc class, quy định kết quả mà nó trả về khi nhận một lời gọi cụ thể, rồi đưa mock đó vào service qua constructor. Nhờ vậy, unit test có thể tập trung vào logic của service mà không cần gọi cơ sở dữ liệu, HTTP API, hệ thống thanh toán hoặc một dịch vụ bên ngoài.

Trong nhóm kỹ thuật Mock, Stub và Spy, việc tạo mock và khai báo dữ liệu trả về là bước thiết lập hành vi cho một collaborator. Mock là đối tượng giả do Mockito tạo ra; stub là hành vi trả lời đã được cấu hình cho mock; spy là đối tượng theo dõi một triển khai thật và mặc định vẫn gọi hành vi thật. Hiểu rõ ba khái niệm này giúp chọn đúng cách cô lập phụ thuộc và tránh viết test phụ thuộc quá nhiều vào chi tiết triển khai.

## 1. Mock, stub và spy khác nhau thế nào?

Các thuật ngữ này thường xuất hiện cùng nhau nhưng mô tả những khía cạnh khác nhau:

| Khái niệm | Ý nghĩa | Khi nên dùng |
|---|---|---|
| Mock | Đối tượng giả do Mockito tạo, có thể cấu hình hành vi và kiểm tra lời gọi | Khi cần thay thế một collaborator hoặc xác nhận một tương tác có ý nghĩa |
| Stub | Hành vi được cấu hình để trả về dữ liệu, ném exception hoặc tạo kết quả | Khi logic cần một đầu vào phụ thuộc do test kiểm soát |
| Spy | Đối tượng được tạo từ một triển khai thật; các phương thức thường gọi hành vi thật trừ khi được stub | Khi cần theo dõi hoặc thay thế có chọn lọc một phần hành vi của đối tượng thật |
| Fake | Một triển khai đơn giản do người viết test tạo ra, có thể thực hiện một phần hợp đồng thật | Khi cần một collaborator hoạt động được, chẳng hạn repository lưu dữ liệu trong bộ nhớ |

Một mock có thể được cấu hình bằng nhiều stub. Vì vậy, mock nói về đối tượng được tạo, còn stub nói về hành vi của đối tượng đó. Spy có thể được stub giống mock, nhưng khác biệt quan trọng là phương thức chưa được stub của spy vẫn có thể thực thi mã thật.

Ví dụ, khi kiểm tra một dịch vụ giữ chỗ, ta không muốn test phải đọc số lượng hàng tồn kho từ database. Ta tạo mock cho cổng truy vấn tồn kho và khai báo rằng mã hàng cụ thể còn tám đơn vị. Dịch vụ nhận dữ liệu đó và quyết định có thể giữ chỗ hay không.

## 2. Chuẩn bị một phụ thuộc để mock

Nên tạo ranh giới phụ thuộc bằng một interface có hợp đồng rõ ràng. Ví dụ sau mô tả cổng truy vấn số lượng tồn kho:

~~~java
import java.util.Optional;

public interface InventoryGateway {
    Optional<Integer> availableUnits(String sku);
}
~~~

Dịch vụ nghiệp vụ nhận cổng này qua constructor:

~~~java
import java.util.Objects;

public class ReservationPolicy {
    private final InventoryGateway inventoryGateway;

    public ReservationPolicy(InventoryGateway inventoryGateway) {
        this.inventoryGateway = Objects.requireNonNull(inventoryGateway);
    }

    public boolean canReserve(String sku, int requestedQuantity) {
        if (requestedQuantity <= 0) {
            throw new IllegalArgumentException(
                    "Requested quantity must be positive");
        }

        return inventoryGateway.availableUnits(sku)
                .map(available -> available >= requestedQuantity)
                .orElse(false);
    }
}
~~~

Trong ứng dụng thật, một bean có thể triển khai InventoryGateway bằng JDBC, JPA hoặc HTTP. Trong unit test, Mockito sẽ cung cấp một implementation giả. ReservationPolicy không cần biết dữ liệu đến từ đâu; nó chỉ làm việc với hợp đồng availableUnits.

Đây là một lợi ích quan trọng của Dependency Injection: test có thể tự tạo service và truyền vào đúng phụ thuộc cần kiểm soát. Không cần khởi động Spring ApplicationContext chỉ để kiểm tra điều kiện giữ chỗ.

## 3. Tạo mock bằng Mockito.mock()

Cách trực tiếp nhất là gọi Mockito.mock() với kiểu cần giả lập:

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.Optional;

class ManualMockExample {
    void createMock() {
        InventoryGateway inventoryGateway =
                mock(InventoryGateway.class);

        when(inventoryGateway.availableUnits("SKU-01"))
                .thenReturn(Optional.of(8));

        ReservationPolicy policy =
                new ReservationPolicy(inventoryGateway);

        boolean canReserve = policy.canReserve("SKU-01", 5);
    }
}
~~~

Lệnh mock(InventoryGateway.class) yêu cầu Mockito tạo một đối tượng có kiểu InventoryGateway. Khi phương thức availableUnits được gọi, Mockito chặn lời gọi và sử dụng hành vi đã cấu hình. Lệnh when(...).thenReturn(...) thiết lập kết quả cho lời gọi có đối số SKU-01.

Các bước có thể đọc theo thứ tự:

1. Tạo mock từ kiểu phụ thuộc.
2. Khai báo kết quả mong muốn cho lời gọi cụ thể.
3. Truyền mock vào constructor của đối tượng đang kiểm tra.
4. Gọi hành vi công khai của đối tượng đang kiểm tra.
5. Kiểm tra kết quả hoặc tương tác cần thiết.

Mockito.mock() phù hợp khi chỉ cần tạo mock tại một vị trí trong test. Nếu một lớp test có nhiều test method cùng sử dụng một mock, annotation @Mock thường giúp phần khai báo gọn và dễ đọc hơn.

## 4. Tạo mock bằng annotation @Mock

Mockito cung cấp annotation @Mock để khai báo các trường mock. Với JUnit Jupiter, cách thông dụng là bật MockitoExtension:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ReservationPolicyTest {
    @Mock
    private InventoryGateway inventoryGateway;

    private ReservationPolicy policy;

    @BeforeEach
    void setUp() {
        policy = new ReservationPolicy(inventoryGateway);
    }

    @Test
    void allowsReservationWhenEnoughUnitsAreAvailable() {
        when(inventoryGateway.availableUnits("SKU-01"))
                .thenReturn(Optional.of(8));

        assertTrue(policy.canReserve("SKU-01", 5));
    }

    @Test
    void rejectsReservationWhenAvailableUnitsAreInsufficient() {
        when(inventoryGateway.availableUnits("SKU-01"))
                .thenReturn(Optional.of(3));

        assertFalse(policy.canReserve("SKU-01", 5));
    }

    @Test
    void rejectsReservationWhenInventoryIsUnknown() {
        when(inventoryGateway.availableUnits("SKU-01"))
                .thenReturn(Optional.empty());

        assertFalse(policy.canReserve("SKU-01", 5));
    }
}
~~~

MockitoExtension khởi tạo các trường có annotation Mockito trước mỗi test và quản lý vòng đời của chúng. Vì vậy, không cần tự gọi MockitoAnnotations.openMocks(this) trong ví dụ này.

Mỗi test cấu hình dữ liệu phù hợp với tình huống của nó. Test số lượng đủ dùng Optional.of(8), test thiếu hàng dùng Optional.of(3), còn test không tìm thấy dữ liệu dùng Optional.empty(). Cùng một service được kiểm tra với nhiều trạng thái của phụ thuộc mà không cần thay đổi implementation thật.

Nếu không dùng MockitoExtension, annotation @Mock sẽ không tự khởi tạo chỉ vì JUnit nhìn thấy nó. Có thể dùng MockitoAnnotations.openMocks(this) trong setup, nhưng phải quản lý việc đóng tài nguyên trả về. Với JUnit Jupiter, MockitoExtension thường là lựa chọn đơn giản và nhất quán hơn.

### @Mock không phải bean Spring

@Mock tạo một đối tượng Mockito trong phạm vi test. Annotation này tự nó không đăng ký đối tượng vào Spring ApplicationContext và cũng không thay thế một bean đang được Spring quản lý.

Vì vậy, unit test thường tạo service trực tiếp bằng constructor và truyền mock vào. Nếu một bài integration test cần thay một bean trong Spring context, hãy dùng cơ chế mock bean phù hợp của bộ kiểm thử Spring Boot đang sử dụng. Hai nhu cầu này khác nhau: một bên là tạo đối tượng để kiểm tra logic cô lập, bên kia là thay một thành phần trong đồ thị bean của ứng dụng.

## 5. Khai báo dữ liệu trả về với when().thenReturn()

Mẫu stubbing phổ biến nhất của Mockito là:

~~~java
when(mock.someMethod(arguments))
        .thenReturn(value);
~~~

Phần when(...) xác định lời gọi cần cấu hình. Phần thenReturn(...) cung cấp kết quả mà mock sẽ trả về khi nhận lời gọi khớp với cấu hình đó.

Ví dụ:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(Optional.of(8));
~~~

Khi ReservationPolicy gọi availableUnits("SKU-01"), mock trả về Optional chứa số 8. Nếu test gọi với một mã hàng khác mà chưa có cấu hình tương ứng, Mockito sẽ sử dụng giá trị mặc định của kiểu trả về.

Một lời gọi có thể được cấu hình với nhiều kết quả khác nhau. Điều này hữu ích khi đang kiểm tra hành vi phụ thuộc vào nhiều lần đọc liên tiếp:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(
                Optional.of(8),
                Optional.of(5),
                Optional.empty());
~~~

Các lần gọi tiếp theo nhận lần lượt kết quả thứ nhất, thứ hai và thứ ba. Sau khi dùng hết các kết quả đã khai báo, Mockito tiếp tục trả về kết quả cuối cùng trong chuỗi. Có thể viết dạng nối nhiều thenReturn() nếu muốn làm rõ từng bước:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(Optional.of(8))
        .thenReturn(Optional.of(5))
        .thenReturn(Optional.empty());
~~~

Không nên dùng chuỗi kết quả chỉ để làm test phức tạp hơn. Hãy dùng nó khi số lần gọi và sự thay đổi kết quả theo thời gian là một phần của tình huống cần kiểm tra, chẳng hạn lần đọc đầu tiên thấy còn hàng nhưng lần đọc sau không còn.

## 6. Khai báo kết quả cho nhiều đối số

Mockito có thể stub một lời gọi dựa trên giá trị đối số chính xác:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(Optional.of(8));

when(inventoryGateway.availableUnits("SKU-02"))
        .thenReturn(Optional.of(2));
~~~

Hai lời gọi có đối số khác nhau nhận hai kết quả khác nhau. Đây thường là cách rõ ràng nhất khi test có một số ít dữ liệu đầu vào xác định.

Khi không muốn phụ thuộc vào một giá trị cụ thể, có thể dùng argument matcher:

~~~java
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

when(inventoryGateway.availableUnits(anyString()))
        .thenReturn(Optional.of(4));
~~~

anyString() khớp với chuỗi không null. Với matcher any() hoặc matcher theo kiểu, cần chú ý quy tắc kết hợp đối số:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

interface MessageGateway {
    boolean publish(String channel, Message message);
}

record Message(String body) {
}

class MessageGatewayStubbingExample {
    void configure() {
        MessageGateway messageGateway = mock(MessageGateway.class);

        when(messageGateway.publish(
                anyString(),
                any(Message.class)))
                .thenReturn(true);
    }
}
~~~

Nếu đã dùng matcher cho một đối số của lời gọi, tất cả đối số còn lại trong cùng lời gọi cũng phải được biểu diễn bằng matcher. Không trộn một giá trị thường với matcher:

Giả sử biến messageGateway đã được tạo trong phương thức configure() như ví dụ trên. Lời gọi sau không hợp lệ vì chỉ đối số thứ hai dùng matcher:

~~~java
// Không đúng: một đối số là giá trị thường, đối số còn lại là matcher.
when(messageGateway.publish(
        "orders",
        any(Message.class)))
        .thenReturn(true);
~~~

Nếu cần cố định một đối số và dùng matcher cho đối số khác, hãy dùng eq():

Trong cùng phương thức configure(), có thể viết lời gọi hợp lệ như sau:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

when(messageGateway.publish(
        eq("orders"),
        any(Message.class)))
        .thenReturn(true);
~~~

Matcher chỉ có ý nghĩa bên trong stubbing hoặc verification. Không gọi any(), eq() như dữ liệu thông thường trong mã nghiệp vụ. Nếu cần khớp giá trị null, hãy dùng isNull() thay vì giả định anyString() hoặc any(Class) sẽ khớp null.

## 7. Khai báo exception bằng thenThrow()

Không phải phụ thuộc nào cũng trả về dữ liệu thành công. Test thường cần mô phỏng timeout, lỗi kết nối hoặc lỗi nghiệp vụ để xác nhận service xử lý đúng.

Với phương thức có giá trị trả về, có thể dùng thenThrow():

~~~java
class InventoryUnavailableException extends RuntimeException {
    InventoryUnavailableException(String message) {
        super(message);
    }
}
~~~

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenThrow(new InventoryUnavailableException(
                "Inventory service is unavailable"));
~~~

Test có thể xác nhận lỗi được truyền lên hoặc được service chuyển thành kết quả nghiệp vụ phù hợp:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;

class ReservationPolicyFailureTest {
    @Test
    void propagatesInventoryFailure() {
        InventoryGateway gateway = mock(InventoryGateway.class);
        ReservationPolicy policy = new ReservationPolicy(gateway);

        when(gateway.availableUnits("SKU-01"))
                .thenThrow(new InventoryUnavailableException(
                        "Inventory service is unavailable"));

        assertThrows(
                InventoryUnavailableException.class,
                () -> policy.canReserve("SKU-01", 1));
    }
}
~~~

Nếu dùng checked exception, phương thức được stub phải khai báo hoặc cho phép exception đó theo quy tắc của Java. Với runtime exception, không cần khai báo throws trong chữ ký phương thức.

Khi muốn một lời gọi trả về bình thường rồi lần tiếp theo mới ném lỗi, có thể kết hợp các kết quả trong một chuỗi:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(Optional.of(8))
        .thenThrow(new InventoryUnavailableException(
                "Inventory service is unavailable"));
~~~

Điều này hữu ích khi cần mô phỏng lỗi phát sinh sau một lần đọc thành công, nhưng chỉ nên dùng nếu chuỗi lời gọi đó phản ánh một tình huống thực tế mà service cần xử lý.

## 8. Stub phương thức void

Phương thức void không có giá trị trả về nên không thể dùng when(...).thenReturn(...). Mockito cung cấp nhóm API do...when(...) để cấu hình hành vi:

~~~java
doThrow(new NotificationException("Gateway failed"))
        .when(notificationGateway)
        .send("orders", message);
~~~

Đoạn trên mô phỏng việc gửi thông báo thất bại bằng cách ném exception khi notificationGateway nhận lời gọi send với các đối số đã chỉ định.

Một test hoàn chỉnh có thể kiểm tra cách service phản ứng:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;

interface NotificationGateway {
    void send(String channel, Message message);
}

class NotificationException extends RuntimeException {
    NotificationException(String message) {
        super(message);
    }
}

class NotificationService {
    private final NotificationGateway gateway;

    NotificationService(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    void notifyOrderCreated(Message message) {
        gateway.send("orders", message);
    }
}

class NotificationServiceTest {
    @Test
    void propagatesFailureWhenSendingNotification() {
        NotificationGateway gateway =
                mock(NotificationGateway.class);
        NotificationService service =
                new NotificationService(gateway);
        Message message = new Message("Order created");

        doThrow(new NotificationException("Gateway failed"))
                .when(gateway)
                .send("orders", message);

        assertThrows(
                NotificationException.class,
                () -> service.notifyOrderCreated(message));
    }
}
~~~

Với mock thông thường, phương thức void mặc định không làm gì. Vì thế, doNothing() thường không cần thiết. API này có thể hữu ích khi cấu hình một spy để chặn hành vi thật của phương thức void, hoặc khi muốn thể hiện rõ một hành vi rỗng trong test.

## 9. Tạo dữ liệu trả về động bằng thenAnswer()

thenReturn() phù hợp khi kết quả đã biết trước. Khi kết quả phải được tính từ đối số đầu vào, dùng thenAnswer():

~~~java
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import java.util.Locale;
import org.mockito.Mockito;

interface CodeNormalizer {
    String normalize(String input);
}

class CodeNormalizerStubbingExample {
    void configure() {
        CodeNormalizer codeNormalizer =
                Mockito.mock(CodeNormalizer.class);

        when(codeNormalizer.normalize(anyString()))
                .thenAnswer(invocation -> {
                    String input = invocation.getArgument(0);
                    return input.trim().toUpperCase(Locale.ROOT);
                });
    }
}
~~~

Answer nhận thông tin về lời gọi thông qua invocation. Test lấy đối số bằng getArgument(index), tính kết quả rồi trả về. Cách này cho phép một cấu hình xử lý nhiều giá trị đầu vào.

Có thể dùng thenAnswer() khi cần:

- Kết quả phụ thuộc vào đối số của lời gọi.
- Một callback cần được thực thi trong lúc test.
- Một đối tượng trả về cần được tạo mới cho từng lời gọi.
- Cần mô phỏng một phản hồi có quy tắc thay vì một giá trị cố định.

Tuy nhiên, nếu kết quả chỉ là một giá trị đã biết, thenReturn() dễ đọc hơn. Không nên chuyển mọi stub thành Answer vì phần logic trong test có thể trở nên phức tạp và khó phân biệt với logic sản phẩm.

## 10. Dùng doReturn() khi làm việc với spy

Với mock thông thường, when(mock.method()).thenReturn(value) là cách khai báo ưu tiên. Với spy, lời gọi trong phần when(...) có thể thực thi phương thức thật ngay trong lúc cấu hình.

Ví dụ, một danh sách rỗng được tạo thành spy:

~~~java
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.when;

import java.util.ArrayList;
import java.util.List;

List<String> values = spy(new ArrayList<>());

when(values.get(0)).thenReturn("sample");
~~~

Khi đánh giá values.get(0) trong when(...), phương thức thật của ArrayList được gọi. Vì danh sách chưa có phần tử ở vị trí 0, lệnh cấu hình có thể ném IndexOutOfBoundsException trước khi thenReturn() được thực hiện.

Với tình huống đó, dùng doReturn(...).when(spy).method(...):

~~~java
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;

import java.util.ArrayList;
import java.util.List;

List<String> values = spy(new ArrayList<>());

doReturn("sample").when(values).get(0);
~~~

doReturn() thiết lập kết quả mà không cần gọi phương thức thật trong lúc cấu hình. Mockito còn có doThrow(), doAnswer() và doNothing() trong cùng nhóm API do...when(...).

Không nên chọn spy chỉ vì nó tiện hơn mock. Spy giữ lại hành vi thật của đối tượng, nên test có thể vô tình truy cập file, mạng, database hoặc trạng thái bên ngoài. Nếu cần cô lập một collaborator, mock hoặc fake thường rõ ràng hơn. Spy phù hợp khi chủ đích là giữ phần lớn hành vi thật và thay thế có chọn lọc một phương thức.

## 11. Giá trị mặc định khi chưa stub

Một mock không tự thực hiện logic của class hoặc interface gốc. Nếu lời gọi chưa được cấu hình, Mockito dùng default answer của nó. Tùy kiểu trả về, kết quả mặc định có thể là null, false, giá trị số 0 hoặc một giá trị rỗng dành cho một số kiểu phổ biến.

Ví dụ, nếu test quên cấu hình một phương thức trả về đối tượng, kết quả null có thể làm service ném NullPointerException ở một dòng sau đó. Lỗi này đôi khi khiến người đọc nghĩ logic service có vấn đề, trong khi nguyên nhân là test chưa khai báo dữ liệu phụ thuộc cần thiết.

Hãy stub các lời gọi có ảnh hưởng đến hành vi đang kiểm tra. Không cần stub mọi phương thức của mock nếu service không gọi chúng hoặc kết quả mặc định không ảnh hưởng đến tình huống. Việc cấu hình quá nhiều hành vi không liên quan khiến test dài và dễ lỗi khi mã thay đổi.

## 12. Kết hợp stubbing với verification

Stubbing quy định mock sẽ trả lời thế nào. Verification xác nhận một lời gọi có xảy ra hay không. Hai thao tác này có liên quan nhưng phục vụ hai mục đích khác nhau.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.Test;

class ReservationPolicyVerificationTest {
    @Test
    void queriesTheRequestedSku() {
        InventoryGateway gateway = mock(InventoryGateway.class);
        ReservationPolicy policy = new ReservationPolicy(gateway);

        when(gateway.availableUnits("SKU-01"))
                .thenReturn(Optional.of(8));

        assertTrue(policy.canReserve("SKU-01", 5));

        verify(gateway).availableUnits("SKU-01");
    }
}
~~~

Test vừa thiết lập dữ liệu trả về vừa xác nhận service đã hỏi đúng mã hàng. Verification có giá trị khi lời gọi là một phần của hợp đồng cần kiểm tra, ví dụ gửi thông báo, ghi audit hoặc gọi một dịch vụ đúng một lần.

Không cần verify mọi lời gọi chỉ vì Mockito hỗ trợ. Nếu kết quả đầu ra đã thể hiện đầy đủ hành vi cần kiểm tra, assertion thường bền vững hơn. Một test xác minh quá nhiều lời gọi nội bộ có thể thất bại sau một lần refactor dù hành vi quan sát được của ứng dụng vẫn đúng.

## 13. Những lỗi thường gặp khi tạo mock và stubbing

### Quên bật MockitoExtension

Khai báo @Mock nhưng không khởi tạo annotation sẽ khiến trường mock vẫn null. Với JUnit Jupiter, thêm @ExtendWith(MockitoExtension.class) ở lớp test hoặc dùng cách khởi tạo Mockito tương ứng.

### Dùng mock thay cho một đối tượng giá trị

Không cần mock String, BigDecimal, DTO hoặc value object đơn giản. Hãy tạo dữ liệu thật cho những kiểu này. Mock chủ yếu dành cho collaborator có hành vi hoặc ranh giới bên ngoài mà test cần kiểm soát.

### Stub một đối số nhưng gọi với đối số khác

Khi cấu hình availableUnits("SKU-01"), lời gọi availableUnits("SKU-02") không dùng cấu hình đó. Hãy xác định test cần khớp chính xác đối số hay cần matcher tổng quát. Chỉ dùng matcher rộng khi nhiều giá trị thực sự có cùng ý nghĩa đối với tình huống đang kiểm tra.

### Trộn matcher với giá trị thường

Khi một lời gọi đã sử dụng matcher, mọi đối số của lời gọi đó phải dùng matcher. Kết hợp eq() với any() để diễn đạt rõ đối số cố định và đối số linh hoạt.

### Dùng when() trên spy khiến mã thật chạy sớm

Khi stubbing spy, biểu thức trong when(...) có thể gọi phương thức thật và gây tác dụng phụ hoặc exception. Dùng doReturn(), doThrow() hoặc doAnswer() khi cần tránh thực thi thật trong lúc cấu hình.

### Stub quá nhiều hành vi

Chỉ cấu hình những lời gọi cần cho tình huống. Stub không được dùng có thể làm test khó đọc và che giấu việc service đã thay đổi cách cộng tác. Nếu một cấu hình dùng chung cho nhiều test nhưng chỉ một số test cần đến, hãy đặt stub trong test tương ứng hoặc tổ chức setup phù hợp.

### Dùng mock như một bản sao của hệ thống thật

Mockito không xác nhận rằng SQL, HTTP request hoặc cấu hình Spring thực tế hoạt động đúng. Mock chỉ trả về điều test đã cấu hình. Những hành vi phụ thuộc vào database, transaction, serialization hoặc Spring wiring vẫn cần slice test hay integration test phù hợp.

## 14. Cách chọn API stubbing

| Nhu cầu | API thường dùng | Ví dụ |
|---|---|---|
| Trả về một giá trị cố định | when(...).thenReturn(...) | Một mã hàng có tám đơn vị |
| Trả về nhiều giá trị theo thứ tự | thenReturn(value1, value2, ...) | Lần đọc đầu thành công, lần sau hết hàng |
| Ném exception từ phương thức có giá trị trả về | when(...).thenThrow(...) | Repository mất kết nối |
| Tạo kết quả dựa trên đối số | thenAnswer(...) | Chuẩn hóa chuỗi đầu vào |
| Ném exception từ phương thức void | doThrow(...).when(...) | Gửi thông báo thất bại |
| Tránh gọi phương thức thật khi stubbing spy | doReturn(...).when(...) | Stub vị trí chưa tồn tại trong danh sách |
| Khớp đối số linh hoạt | any(), anyString(), eq(), isNull() | Nhận mọi mã hàng không null |

Khi đọc một test Mockito, có thể nhận ra cấu trúc cơ bản: phần tạo mock xác định collaborator được thay thế; phần stubbing xác định dữ liệu hoặc lỗi mà collaborator cung cấp; phần thực thi gọi hành vi của lớp đang kiểm tra; phần assertion và verification xác nhận kết quả cần thiết.

## 15. Nguyên tắc sử dụng trong Spring Framework Testing

- Dùng Mockito.mock() khi cần tạo mock trực tiếp tại một vị trí; dùng @Mock cùng MockitoExtension khi mock là fixture của test class.
- Ưu tiên constructor injection để truyền mock vào service. Test có thể tự tạo đối tượng và không cần Spring context cho logic thuần túy.
- Dùng when(...).thenReturn(...) cho kết quả cố định của phương thức có giá trị trả về.
- Dùng thenThrow() để mô phỏng lỗi; dùng doThrow() cho phương thức void.
- Dùng argument matcher khi nhiều giá trị đầu vào có cùng ý nghĩa; kết hợp matcher bằng eq() khi cần giữ một đối số cố định.
- Dùng thenAnswer() cho kết quả thực sự phụ thuộc vào đối số hoặc thời điểm gọi.
- Với spy, cân nhắc doReturn() để không vô tình gọi phương thức thật trong lúc stubbing.
- Không dựa vào giá trị mặc định của mock nếu kết quả đó ảnh hưởng đến hành vi đang kiểm tra.
- Chỉ verification những tương tác thuộc hợp đồng cần kiểm tra; ưu tiên assertion trên kết quả quan sát được.
- Nhớ rằng mock chỉ mô phỏng hành vi đã cấu hình. Cần kiểm thử tích hợp để xác nhận việc kết nối với database, mạng và Spring container.

Tạo mock và khai báo dữ liệu trả về giúp kiểm thử một thành phần trong môi trường có thể kiểm soát. Khi lựa chọn đúng collaborator, cấu hình đúng phản hồi và truyền mock qua constructor, test có thể kiểm tra các nhánh thành công lẫn thất bại một cách ổn định. Mockito cung cấp nhiều API cho từng tình huống; chọn API đơn giản nhất thể hiện đúng hành vi cần kiểm tra sẽ giúp bài test dễ đọc và dễ duy trì.
