# Kiểm thử dữ liệu dùng để tạo SimpleMailMessage

Trong Spring Framework Mail, **SimpleMailMessage** là đối tượng dùng để mô tả một email **văn bản thuần**: người gửi, người nhận, Reply-To, CC, BCC, ngày gửi, tiêu đề và nội dung. Ứng dụng thường lấy những giá trị này từ dữ liệu nghiệp vụ rồi gọi **MailSender.send(SimpleMailMessage)** để thực hiện gửi thư.

Một lỗi dữ liệu có thể xuất hiện trước cả khi ứng dụng kết nối tới SMTP server. Ví dụ: email gửi tới nhầm người, tiêu đề chứa sai mã đơn hàng, body lấy nhầm số tiền, Reply-To trỏ tới hộp thư không được quản lý, hoặc thông tin người nhận bị rỗng. Nếu chỉ kiểm thử bằng cách “gửi được thư”, các lỗi này có thể khó được phát hiện và gây hậu quả thực tế.

**Kiểm thử đơn vị dữ liệu dùng để tạo SimpleMailMessage** nhằm xác minh rằng, với một đầu vào nghiệp vụ xác định, ứng dụng tạo ra đúng các trường và đúng nội dung email. Trong phần lớn trường hợp, **không cần chạy SMTP server, không cần tài khoản mail thật và không cần gửi email ra ngoài**.

Mô hình thường gặp:

~~~text
Business data / DTO
        |
        v
Validate and normalize
        |
        v
SimpleMailMessage factory / mapper
        |
        v
SimpleMailMessage
        |
        v
MailSender.send(...)
~~~

Có hai điểm kiểm thử bổ sung cho nhau:

1. **Kiểm thử factory/mapper:** đưa dữ liệu mẫu vào, nhận SimpleMailMessage và assert trực tiếp các thuộc tính của message.
2. **Kiểm thử service gửi thư:** mock MailSender, gọi service, dùng ArgumentCaptor bắt SimpleMailMessage được truyền vào send và kiểm tra nó.

Hai kiểu test này cho biết dữ liệu được dựng đúng và service thực sự chuyển đúng message cho sender, **không khẳng định SMTP đã chấp nhận hay người nhận đã nhận email**.

## 1. SimpleMailMessage chứa những dữ liệu gì?

SimpleMailMessage hỗ trợ các trường phổ biến:

| Trường | API thiết lập | API đọc để assert | Ý nghĩa |
| --- | --- | --- | --- |
| Người gửi | **setFrom(...)** | **getFrom()** | Địa chỉ From |
| Reply-To | **setReplyTo(...)** | **getReplyTo()** | Địa chỉ nhận phản hồi |
| Người nhận chính | **setTo(...)** | **getTo()** | Mảng địa chỉ To |
| CC | **setCc(...)** | **getCc()** | Mảng người nhận bản sao |
| BCC | **setBcc(...)** | **getBcc()** | Mảng người nhận ẩn |
| Ngày gửi | **setSentDate(...)** | **getSentDate()** | Giá trị java.util.Date |
| Tiêu đề | **setSubject(...)** | **getSubject()** | Chủ đề email |
| Nội dung text | **setText(...)** | **getText()** | Body plain text |

Ví dụ:

~~~java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage message = new SimpleMailMessage();

message.setFrom("orders@example.org");
message.setTo("an@example.net");
message.setReplyTo("support@example.org");
message.setSubject("Xác nhận đơn hàng ORDER-2026-001");
message.setText(
        "Xin chào Nguyễn An,\n\n"
      + "Đơn hàng ORDER-2026-001 đã được xác nhận."
);
~~~

Đây là thao tác tạo đối tượng Java. **Chưa có kết nối SMTP** cho tới khi một MailSender thực sự gửi message.

### 1.1. SimpleMailMessage là plain text

SimpleMailMessage không phải lựa chọn để dựng HTML, inline image hoặc attachment. Nếu cần các phần MIME đó, dùng **MimeMessage**, **MimeMessageHelper** và **JavaMailSender**.

Kiểm thử SimpleMailMessage nên tập trung vào:

- Giá trị From/To/Reply-To/CC/BCC.
- Subject.
- Nội dung văn bản và xuống dòng.
- SentDate nếu ứng dụng thiết lập.
- Quy tắc dựng message từ model.
- Hành vi với đầu vào hợp lệ và không hợp lệ.

Không nên kỳ vọng thuộc tính HTML hoặc attachment xuất hiện trong đối tượng này.

### 1.2. setTo(...) nhận một hoặc nhiều địa chỉ

Dù thiết lập một địa chỉ:

~~~java
message.setTo("an@example.net");
~~~

**getTo()** trả về một mảng **String[]**. Vì vậy, test nên dùng:

~~~java
assertArrayEquals(
        new String[] {"an@example.net"},
        message.getTo()
);
~~~

Không dùng assertEquals với một String để so sánh trực tiếp với String[].

### 1.3. CC và BCC không cần xuất hiện ở mọi email

Nếu nghiệp vụ không yêu cầu CC/BCC, có thể kiểm tra các trường này **không được đặt**. Với một SimpleMailMessage mới được tạo và chưa set CC/BCC, getter thường trả null.

Đó là một trường hợp test có giá trị: không vô tình gửi thêm thông tin cho địa chỉ quản trị hoặc người nhận ngoài ý muốn.

## 2. Định nghĩa hợp đồng dữ liệu trước khi viết test

Một bài unit test chỉ có ích nếu biết **message đúng** có nghĩa là gì.

Ví dụ yêu cầu nghiệp vụ cho email xác nhận đơn hàng:

| Dữ liệu nguồn | Trường trong mail | Quy tắc |
| --- | --- | --- |
| Địa chỉ khách hàng | To | Một địa chỉ đã được chuẩn hóa và kiểm tra cú pháp |
| Địa chỉ hệ thống | From | Cấu hình cố định, không lấy từ input của khách |
| Hộp thư hỗ trợ | Reply-To | Địa chỉ hỗ trợ được kiểm soát |
| Mã đơn hàng | Subject và text | Cùng một mã đơn hàng |
| Tên khách hàng | Text | Có tên được chuẩn bị trong DTO |
| Tổng tiền | Text | Số tiền của đúng đơn hàng, định dạng nhất quán |
| Thời điểm xác nhận | SentDate | Giá trị xác định, không phụ thuộc thời gian ngẫu nhiên khi test |
| CC/BCC | Không có | Không gửi thêm bản sao ngoài yêu cầu |

Đầu vào hợp lệ mẫu:

~~~text
recipientEmail = an@example.net
customerName   = Nguyễn An
orderNumber    = ORDER-2026-001
totalAmount    = 500000
confirmedAt    = 2026-11-12T08:30:00Z
~~~

Đầu ra mong đợi:

~~~text
From: orders@example.org
To: an@example.net
Reply-To: support@example.org
Subject: Xác nhận đơn hàng ORDER-2026-001
SentDate: 2026-11-12T08:30:00Z

Xin chào Nguyễn An,

Đơn hàng ORDER-2026-001 đã được xác nhận.
Tổng tiền: 500000 VND.

Trân trọng,
Đội ngũ bán hàng
~~~

Chọn format này để test ví dụ **độc lập với quy ước dấu phân cách số và locale của máy chạy**. Trong sản phẩm thật, định dạng tiền theo locale có thể khác và cần hợp đồng kiểm thử tương ứng.

## 3. Tách dữ liệu nghiệp vụ khỏi quá trình gửi

Một service vừa truy vấn database, kiểm tra đơn hàng, dựng message vừa gọi SMTP sẽ khó kiểm thử đơn vị hơn:

~~~java
public void sendConfirmation(Long id) {
    Order order = orderRepository.findById(id).orElseThrow();
    SimpleMailMessage message = new SimpleMailMessage();

    // Truy vấn thêm dữ liệu, dựng text, lấy ngày hiện tại...
    mailSender.send(message);
}
~~~

Test dễ bị phụ thuộc repository, thời gian hiện tại, cấu hình mail và những dữ liệu ngoài phạm vi muốn kiểm tra.

Thay vào đó, tách thành:

~~~text
OrderRepository / business service
                 |
                 v
         OrderMailData snapshot
                 |
                 v
      OrderMailMessageFactory
                 |
                 v
         SimpleMailMessage
                 |
                 v
         OrderMailService
                 |
                 v
          MailSender
~~~

Lợi ích:

- Factory/mapper có thể test bằng Java object thuần.
- MailSender có thể được mock mà không mở mạng.
- Dữ liệu được snapshot trước khi gửi, tránh JPA lazy loading ngoài transaction.
- Khi template plain text thay đổi, test của factory cho thấy giá trị được dựng khác trước.
- Lỗi nghiệp vụ và lỗi SMTP không bị trộn trong một unit test.

## 4. Tạo DTO đầu vào có kiểu rõ ràng

Ví dụ Java record:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderMailData(
        String recipientEmail,
        String customerName,
        String orderNumber,
        BigDecimal totalAmount,
        Instant confirmedAt
) {}
~~~

Các trường này đại diện cho dữ liệu cần thiết để dựng một thông báo xác nhận. Không cần đưa toàn bộ entity Order hoặc Customer vào mail factory.

### 4.1. Vì sao nên dùng DTO?

Nếu test lấy trực tiếp từ entity JPA, nó có thể phụ thuộc:

- Persistence context và lazy associations.
- Constructor hoặc cấu hình ORM.
- Repository state.
- Logic tính toán nằm ở service khác.
- Thời điểm dữ liệu được tải.

DTO giúp định nghĩa đầu vào rõ ràng và kiểm tra message theo một **snapshot** có thể dự đoán.

### 4.2. DTO không tự bảo đảm dữ liệu hợp lệ

Java record không mặc định kiểm tra email trống, số tiền âm hoặc ngày null. Do đó, quy tắc validation có thể nằm trong constructor của DTO, factory hoặc tầng nghiệp vụ.

Quan trọng hơn vị trí cụ thể là **hợp đồng phải rõ và có thể kiểm thử**: input nào được chấp nhận, input nào bị từ chối và có được chuẩn hóa hay không.

## 5. Viết một factory tạo SimpleMailMessage

Ví dụ factory có trách nhiệm tạo message, **không gửi SMTP**:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import java.math.BigDecimal;
import java.util.Date;
import java.util.Objects;
import org.springframework.mail.SimpleMailMessage;

public final class OrderMailMessageFactory {

    private static final String FROM =
            "orders@example.org";

    private static final String REPLY_TO =
            "support@example.org";

    public SimpleMailMessage create(OrderMailData data) {
        Objects.requireNonNull(data, "data");

        String recipient = validateRecipient(data.recipientEmail());

        String customerName =
                requiredSingleLine(data.customerName(), "customerName");

        String orderNumber =
                requiredSingleLine(data.orderNumber(), "orderNumber");

        BigDecimal total =
                Objects.requireNonNull(
                        data.totalAmount(),
                        "totalAmount"
                );

        if (total.signum() < 0) {
            throw new IllegalArgumentException(
                    "totalAmount must not be negative"
            );
        }

        Date sentDate = Date.from(
                Objects.requireNonNull(
                        data.confirmedAt(),
                        "confirmedAt"
                )
        );

        String text =
                "Xin chào " + customerName + ",\n\n"
              + "Đơn hàng " + orderNumber
              + " đã được xác nhận.\n"
              + "Tổng tiền: " + total.toPlainString()
              + " VND.\n\n"
              + "Trân trọng,\n"
              + "Đội ngũ bán hàng";

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(FROM);
        message.setReplyTo(REPLY_TO);
        message.setTo(recipient);
        message.setSubject("Xác nhận đơn hàng " + orderNumber);
        message.setText(text);
        message.setSentDate(sentDate);

        return message;
    }

    private static String requiredSingleLine(
            String input,
            String field
    ) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank"
            );
        }

        String value = input.trim();

        if (value.indexOf('\r') >= 0 ||
                value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    field + " must be single-line"
            );
        }

        return value;
    }

    private static String validateRecipient(String input) {
        String value = requiredSingleLine(
                input,
                "recipientEmail"
        );

        try {
            InternetAddress address =
                    new InternetAddress(value, true);

            address.validate();

            if (!value.equals(address.getAddress())
                    || address.isGroup()) {
                throw new IllegalArgumentException(
                        "Expected a single mailbox address"
                );
            }

            return value;
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Invalid recipientEmail syntax",
                    ex
            );
        }
    }
}
~~~

Đây là một factory ví dụ. Các địa chỉ From/Reply-To được đặt cố định để dễ theo dõi; trong ứng dụng thật, có thể inject một cấu hình đã được kiểm soát và kiểm thử riêng.

### 5.1. Điều factory bảo đảm

- Data không được null.
- Các trường cần thiết phải có giá trị.
- Tên khách và mã đơn hàng là một dòng.
- Recipient có cú pháp mailbox theo khả năng kiểm tra của Jakarta Mail.
- Số tiền không âm theo quy tắc đơn hàng ví dụ.
- Ngày gửi không null.
- From và Reply-To do hệ thống kiểm soát.
- To, Subject và Text lấy từ cùng DTO.
- Không đặt CC/BCC.

### 5.2. Điều factory không bảo đảm

- Mailbox chắc chắn tồn tại.
- Người nhận sở hữu địa chỉ.
- SMTP server chấp nhận message.
- Email đã được chuyển phát hoặc đọc.
- Kiểm tra cú pháp bằng InternetAddress bao phủ toàn bộ chính sách email quốc tế hóa/SMTPUTF8.
- Số tiền không âm phù hợp mọi nghiệp vụ (ví dụ hoàn tiền có thể có quy tắc riêng).

Không biến một unit test thành tuyên bố rằng gửi thư ngoài đời sẽ thành công.

## 6. Kiểm thử factory không cần mock MailSender

Vì factory chỉ tạo object, test có thể gọi trực tiếp rồi assert bằng JUnit 5.

Ví dụ bộ test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;

class OrderMailMessageFactoryTest {

    private final OrderMailMessageFactory factory =
            new OrderMailMessageFactory();

    private static OrderMailData sample() {
        return new OrderMailData(
                "an@example.net",
                "Nguyễn An",
                "ORDER-2026-001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );
    }

    @Test
    void createsExpectedSimpleMailMessage() {
        SimpleMailMessage message = factory.create(sample());

        assertEquals("orders@example.org", message.getFrom());

        assertArrayEquals(
                new String[] {"an@example.net"},
                message.getTo()
        );

        assertEquals(
                "support@example.org",
                message.getReplyTo()
        );

        assertEquals(
                "Xác nhận đơn hàng ORDER-2026-001",
                message.getSubject()
        );

        assertEquals(
                "Xin chào Nguyễn An,\n\n"
              + "Đơn hàng ORDER-2026-001 đã được xác nhận.\n"
              + "Tổng tiền: 500000 VND.\n\n"
              + "Trân trọng,\n"
              + "Đội ngũ bán hàng",
                message.getText()
        );

        assertEquals(
                Date.from(Instant.parse("2026-11-12T08:30:00Z")),
                message.getSentDate()
        );

        assertNull(message.getCc());
        assertNull(message.getBcc());
    }
}
~~~

Unit test này không khởi động Spring context và không gọi SMTP.

### 6.1. Vì sao assert đủ các trường?

Nếu test chỉ kiểm tra:

~~~java
assertNotNull(message);
~~~

thì một message có From sai, To sai, Subject rỗng vẫn có thể vượt qua. Mục tiêu là **hợp đồng dữ liệu**, nên cần assert những trường có ý nghĩa nghiệp vụ.

### 6.2. Test nội dung hoàn chỉnh hay từng đoạn?

Hai phương pháp có giá trị khác nhau:

- **assertEquals toàn text:** bảo vệ chính xác câu chữ, khoảng trắng và xuống dòng, phù hợp email giao dịch có nội dung ổn định.
- **assertTrue contains:** kiểm tra những dữ kiện cụ thể khi bố cục/câu chữ được phép thay đổi.

Nếu hợp đồng yêu cầu một câu thông báo cố định, so sánh toàn bộ text giúp bắt cả lỗi dấu cách và xuống dòng. Nếu copywriting thay đổi thường xuyên, có thể kiểm tra những thông tin bắt buộc và để việc kiểm tra nội dung biên tập cho tầng khác.

## 7. Test từng trường From, To, Reply-To, CC và BCC

Địa chỉ email là dữ liệu ảnh hưởng trực tiếp đến việc **ai nhận được thông tin**. Vì vậy, các assertion này quan trọng không kém body.

### 7.1. From phải từ cấu hình được kiểm soát

~~~java
assertEquals(
        "orders@example.org",
        message.getFrom()
);
~~~

Nếu ứng dụng cho người dùng nhập dữ liệu, không lấy From trực tiếp từ một trường profile tùy ý. From có thể cần khớp account gửi hoặc domain được provider ủy quyền.

### 7.2. To phải đúng recipient của nghiệp vụ

~~~java
assertArrayEquals(
        new String[] {"an@example.net"},
        message.getTo()
);
~~~

Nếu service vô tình lấy email của admin thay vì khách hàng, test có thể phát hiện trước khi sự cố xảy ra.

### 7.3. Reply-To khác From

~~~java
assertEquals(
        "support@example.org",
        message.getReplyTo()
);
~~~

Reply-To quyết định nơi nhận phản hồi trong nhiều email client; nó có thể khác From. Không gán nhầm Reply-To là email người nhận hoặc một địa chỉ không ai theo dõi.

### 7.4. CC/BCC không xuất hiện nếu không yêu cầu

~~~java
assertNull(message.getCc());
assertNull(message.getBcc());
~~~

Đây là một kiểm thử **không làm lộ thông tin**: một email đơn hàng của khách không được âm thầm gửi thêm bản sao tới địa chỉ ngoài hợp đồng.

### 7.5. Nếu nghiệp vụ thật sự cần nhiều người nhận

Ví dụ:

~~~java
message.setTo(
        "an@example.net",
        "binh@example.net"
);
message.setCc("accounting@example.org");
~~~

Test:

~~~java
assertArrayEquals(
        new String[] {"an@example.net", "binh@example.net"},
        message.getTo()
);

assertArrayEquals(
        new String[] {"accounting@example.org"},
        message.getCc()
);
~~~

Nếu thứ tự người nhận không quan trọng theo hợp đồng, có thể kiểm tra tập hợp và độ dài; nếu thứ tự có ý nghĩa trong kết quả được tạo ra, assertArrayEquals giúp phát hiện thay đổi thứ tự.

Lưu ý: gửi một message tới nhiều người có thể khiến địa chỉ trong To/CC hiển thị cho những người nhận khác. Nếu cần bảo vệ riêng tư hoặc retry từng recipient độc lập, nên cân nhắc một mail message cho mỗi người.

## 8. Test Subject và dữ liệu động

Subject thường ghép một phần cố định với mã nghiệp vụ.

~~~java
message.setSubject(
        "Xác nhận đơn hàng " + data.orderNumber()
);
~~~

Test cần kiểm tra:

- Prefix đúng.
- Mã đơn hàng đúng.
- Không lấy mã của đơn hàng khác.
- Không có newline điều khiển bất thường.
- Unicode tiếng Việt được giữ nguyên.
- Subject không rỗng.

Ví dụ:

~~~java
@Test
void subjectContainsCorrectOrderNumber() {
    SimpleMailMessage message = factory.create(sample());

    assertEquals(
            "Xác nhận đơn hàng ORDER-2026-001",
            message.getSubject()
    );
}
~~~

### 8.1. Test một input khác để bắt lỗi hard-code

Nếu mọi test chỉ dùng mã ORDER-2026-001, một developer vô tình hard-code giá trị đó trong factory có thể không bị phát hiện.

Nên có thêm trường hợp:

~~~java
@Test
void subjectChangesWithOrderData() {
    OrderMailData another = new OrderMailData(
            "binh@example.net",
            "Trần Bình",
            "ORDER-2026-999",
            new BigDecimal("120000"),
            Instant.parse("2026-11-13T09:00:00Z")
    );

    SimpleMailMessage message = factory.create(another);

    assertEquals(
            "Xác nhận đơn hàng ORDER-2026-999",
            message.getSubject()
    );
}
~~~

### 8.2. Test Subject không chứa thông tin không cần thiết

Không nên ghép password, OTP, token hoặc dữ liệu nhạy cảm vào subject chỉ vì dễ đọc. Một unit test có thể xác nhận subject chỉ chứa những thành phần được hợp đồng cho phép.

## 9. Test body plain text, Unicode và xuống dòng

Với SimpleMailMessage, body là một chuỗi text. Những lỗi phổ biến:

- Thiếu một đoạn quan trọng.
- Sai tên khách.
- Sai số tiền hoặc đơn vị.
- Nội dung lấy nhầm dữ liệu.
- Có chuỗi null thay thế giá trị thiếu.
- Dòng mới hoặc dấu cách sai khiến email khó đọc.
- Ký tự tiếng Việt bị thay thế do chuyển đổi byte ở tầng trước.

### 9.1. Kiểm tra text hoàn chỉnh

~~~java
assertEquals(
        "Xin chào Nguyễn An,\n\n"
      + "Đơn hàng ORDER-2026-001 đã được xác nhận.\n"
      + "Tổng tiền: 500000 VND.\n\n"
      + "Trân trọng,\n"
      + "Đội ngũ bán hàng",
        message.getText()
);
~~~

Test này bảo vệ đúng cả dấu tiếng Việt và vị trí newline.

### 9.2. Unicode là dữ liệu test có chủ đích

Không nên chỉ test:

~~~text
Hello John
~~~

Email thực tế có thể chứa:

~~~text
Xin chào Nguyễn Ánh,
Đơn hàng đã được xác nhận.
~~~

Các ký tự **ă, â, đ, ê, ô, ơ, ư** và dấu thanh giúp nhận diện vấn đề khi dữ liệu bị biến đổi trước khi gọi setText.

Tuy nhiên, kiểm thử String trong SimpleMailMessage **chưa phải kiểm thử MIME charset hay SMTP encoding trên wire**. Đó là trách nhiệm kiểm thử tích hợp với transport, ví dụ JavaMailSender/MimeMessage trong bước riêng.

### 9.3. Nội dung text không phải HTML

Nếu body chứa:

~~~text
<strong>Đơn hàng đã xác nhận</strong>
~~~

SimpleMailMessage sẽ gửi đoạn đó như văn bản thuần, không yêu cầu email client render thành chữ đậm.

Nếu test mong muốn HTML được hiển thị, cần dùng MimeMessageHelper với text/html thay vì SimpleMailMessage.

### 9.4. Newline theo hợp đồng

Nếu text dùng \n, có thể so sánh trực tiếp trong unit test. Không cần ép mọi test dùng System.lineSeparator(), vì kết quả có thể khác giữa Linux và Windows trong khi hợp đồng nội dung cần ổn định.

Trong quá trình serialize MIME, thư viện gửi mail có thể xử lý line endings theo chuẩn giao thức. Đừng dùng unit test của SimpleMailMessage để suy luận về byte CRLF cuối cùng trên SMTP wire.

## 10. Test SentDate có tính xác định

Một anti-pattern là gọi:

~~~java
message.setSentDate(new Date());
~~~

rồi test so sánh với thời điểm hiện tại trong một cửa sổ rất hẹp. Những test này dễ bị flaky vì thời gian chạy, scheduling và clock khác nhau.

### 10.1. Truyền thời điểm vào DTO

Factory mẫu dùng:

~~~java
message.setSentDate(Date.from(data.confirmedAt()));
~~~

Test:

~~~java
Instant confirmedAt =
        Instant.parse("2026-11-12T08:30:00Z");

OrderMailData data = new OrderMailData(
        "an@example.net",
        "Nguyễn An",
        "ORDER-2026-001",
        new BigDecimal("500000"),
        confirmedAt
);

SimpleMailMessage message = factory.create(data);

assertEquals(
        Date.from(confirmedAt),
        message.getSentDate()
);
~~~

Giá trị được lấy từ đầu vào đã biết, nên test không phụ thuộc timezone hoặc giờ hiện tại của CI.

### 10.2. Dùng Clock khi phải lấy thời gian hiện tại

Nếu nghiệp vụ cần **thời điểm tạo message** thay vì thời điểm xác nhận đơn hàng, có thể inject java.time.Clock:

~~~java
public final class TimestampedMailFactory {

    private final Clock clock;

    public TimestampedMailFactory(Clock clock) {
        this.clock = clock;
    }

    public SimpleMailMessage create() {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("system@example.org");
        message.setTo("user@example.net");
        message.setSubject("Thông báo");
        message.setText("Nội dung");
        message.setSentDate(Date.from(clock.instant()));
        return message;
    }
}
~~~

Test:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-12T08:30:00Z"),
        ZoneOffset.UTC
);

TimestampedMailFactory factory =
        new TimestampedMailFactory(fixed);

assertEquals(
        Date.from(Instant.parse("2026-11-12T08:30:00Z")),
        factory.create().getSentDate()
);
~~~

### 10.3. Không nhất thiết mọi email phải setSentDate

SimpleMailMessage cho phép ứng dụng thiết lập trường này, nhưng tùy kiến trúc, thời gian gửi có thể được xử lý ở tầng transport. Nếu hệ thống không yêu cầu setSentDate, test nên xác nhận trạng thái đúng theo hợp đồng, không ép tạo dữ liệu không cần thiết.

## 11. Test validation: input rỗng hoặc null

Một factory cần xác định rõ cách xử lý dữ liệu thiếu. Không nên để message chứa:

~~~text
To: null
Subject: Xác nhận đơn hàng null
Body: Xin chào null
~~~

Ví dụ test:

~~~java
@Test
void rejectsNullData() {
    assertThrows(
            NullPointerException.class,
            () -> factory.create(null)
    );
}

@Test
void rejectsBlankRecipient() {
    OrderMailData data = new OrderMailData(
            "   ",
            "Nguyễn An",
            "ORDER-2026-001",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    assertThrows(
            IllegalArgumentException.class,
            () -> factory.create(data)
    );
}
~~~

Cần thống nhất loại exception được hứa trong hợp đồng. Nếu dùng validation framework như Bean Validation, test có thể kiểm tra constraint violations tại tầng phù hợp thay vì bắt đúng các exception minh họa.

### 11.1. Test từng trường bắt buộc

Các trường hợp nên có:

- data null.
- recipientEmail null, empty, blank.
- customerName null hoặc blank.
- orderNumber null hoặc blank.
- totalAmount null.
- confirmedAt null.
- totalAmount âm nếu domain không cho phép.
- recipientEmail sai cú pháp.
- subject input chứa CR hoặc LF.

Điều quan trọng là **không được gửi mail khi factory không tạo được dữ liệu hợp lệ**.

## 12. Parameterized tests cho dữ liệu không hợp lệ

JUnit 5 hỗ trợ ParameterizedTest để tránh lặp lại nhiều test giống nhau.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class OrderMailValidationTest {

    private final OrderMailMessageFactory factory =
            new OrderMailMessageFactory();

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   ", "not-an-email", "@example.net"})
    void rejectsInvalidRecipient(String recipient) {
        OrderMailData data = new OrderMailData(
                recipient,
                "Nguyễn An",
                "ORDER-2026-001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> factory.create(data)
        );
    }
}
~~~

Đây là test cho rule của factory minh họa. Không có nghĩa mọi hệ thống email phải từ chối cùng một tập input nếu hợp đồng sản phẩm khác nhau.

### 12.1. NullAndEmptySource khác blank

**@NullAndEmptySource** kiểm tra null và chuỗi rỗng. Các chuỗi như một hoặc ba dấu cách cần thêm vào **@ValueSource** nếu muốn kiểm tra blank.

### 12.2. Kiểm tra địa chỉ quốc tế hóa riêng

Nếu sản phẩm hỗ trợ địa chỉ quốc tế hóa, cần một test matrix tương ứng với SMTPUTF8 và provider. Không dùng một regex ASCII tự phát để khẳng định mọi địa chỉ hợp lệ trên thế giới đều được hỗ trợ.

### 12.3. Syntax validation không chứng minh mailbox tồn tại

Ví dụ **InternetAddress.validate()** kiểm tra cú pháp theo API. Nó không thực hiện xác minh mailbox thực tế.

Đừng viết một unit test kiểm tra một địa chỉ có tồn tại trên provider thật. Điều đó vượt khỏi phạm vi SimpleMailMessage factory và tạo phụ thuộc mạng.

## 13. Kiểm thử chuẩn hóa khoảng trắng

Dữ liệu đầu vào thường có khoảng trắng thừa do nhập liệu hoặc tích hợp.

Factory ví dụ chủ động gọi **trim()**:

~~~java
OrderMailData data = new OrderMailData(
        "  an@example.net  ",
        "  Nguyễn An  ",
        "  ORDER-2026-001  ",
        new BigDecimal("500000"),
        Instant.parse("2026-11-12T08:30:00Z")
);

SimpleMailMessage message = factory.create(data);

assertArrayEquals(
        new String[] {"an@example.net"},
        message.getTo()
);

assertEquals(
        "Xác nhận đơn hàng ORDER-2026-001",
        message.getSubject()
);

assertTrue(
        message.getText().startsWith("Xin chào Nguyễn An,")
);
~~~

Nhưng không phải mọi trường đều nên trim. Mật khẩu, mã xác thực hoặc dữ liệu ký số có thể cần giữ nguyên. Trong factory mail giao dịch, chỉ chuẩn hóa những trường có hợp đồng rõ ràng.

### 13.1. Tránh sửa dữ liệu nguồn ngầm

Factory nên dựng message từ DTO mà không mutate DTO hoặc entity nguồn. Java record giúp giới hạn thay đổi ở object record, nhưng các trường tham chiếu tới mutable object vẫn cần được quản lý cẩn thận.

## 14. Chống chèn ký tự xuống dòng trong header

Khi ghép dữ liệu không tin cậy vào Subject hoặc địa chỉ, ký tự CR/LF có thể làm hỏng định dạng header hoặc tạo rủi ro header injection nếu tầng downstream xử lý không an toàn.

Ví dụ input nguy hiểm:

~~~text
ORDER-123
Bcc: attacker@example.net
~~~

Factory mẫu yêu cầu mã đơn hàng một dòng:

~~~java
if (value.indexOf('\r') >= 0 ||
        value.indexOf('\n') >= 0) {
    throw new IllegalArgumentException(
            "Header field must be single-line"
    );
}
~~~

Test:

~~~java
@Test
void rejectsNewlineInOrderNumber() {
    OrderMailData data = new OrderMailData(
            "an@example.net",
            "Nguyễn An",
            "ORDER-123\r\nBcc: someone@example.net",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    assertThrows(
            IllegalArgumentException.class,
            () -> factory.create(data)
    );
}
~~~

### 14.1. Vì sao nên reject thay vì cắt tùy ý?

Nếu tự xóa newline mà không kiểm soát, giá trị mã đơn hàng có thể bị biến thành một mã khác hoặc khiến audit không thể đối soát. Với identifier, **từ chối input sai hợp đồng** thường rõ ràng hơn.

### 14.2. Không tự dựng raw SMTP header

SimpleMailMessage giúp ứng dụng sử dụng API setter thay vì tự nối raw MIME header. Tuy vậy, dữ liệu nghiệp vụ vẫn cần validation và không nên dựa hoàn toàn vào thư viện để loại bỏ mọi giá trị không hợp lệ.

## 15. Test số tiền và locale

Số tiền phải đến từ đúng dữ liệu nguồn, không được thay đổi bất ngờ khi chuyển thành String.

Factory mẫu dùng:

~~~java
data.totalAmount().toPlainString()
~~~

cho format đơn giản như **500000 VND**.

### 15.1. Vì sao dùng BigDecimal?

BigDecimal phù hợp cho nhiều nghiệp vụ tính tiền vì tránh một số vấn đề làm tròn của floating point. Trong test, tạo dữ liệu:

~~~java
new BigDecimal("500000")
~~~

thay vì dùng double khi cần giữ chính xác giá trị thập phân.

### 15.2. Nếu format theo locale

Ví dụ code minh họa:

~~~java
NumberFormat format =
        NumberFormat.getCurrencyInstance(
                Locale.forLanguageTag("vi-VN")
        );

String formatted = format.format(amount);
~~~

Kết quả có thể phụ thuộc dữ liệu locale/CLDR và phiên bản JDK. Nếu hợp đồng đòi format cụ thể, hãy kiểm soát formatter, locale, currency và chính sách rounding, hoặc kiểm thử một abstraction formatter đã chuẩn hóa.

### 15.3. Không hard-code chuỗi tiền sai hệ thống

Test nên có dữ liệu số tiền khác nhau để phát hiện builder luôn dùng một giá trị cố định. Ví dụ 500000 và 120000 không được tạo cùng một tổng tiền trong body.

## 16. Test không làm rò rỉ dữ liệu khách khác

Một lỗi nghiêm trọng là dùng sai DTO hoặc cache message giữa các request, khiến tên/người nhận của người A đi với mã đơn hàng của người B.

Test với hai DTO độc lập:

~~~java
@Test
void createsIndependentMessagesForDifferentOrders() {
    OrderMailData first = new OrderMailData(
            "an@example.net",
            "Nguyễn An",
            "ORDER-101",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    OrderMailData second = new OrderMailData(
            "binh@example.net",
            "Trần Bình",
            "ORDER-202",
            new BigDecimal("120000"),
            Instant.parse("2026-11-13T09:30:00Z")
    );

    SimpleMailMessage firstMessage = factory.create(first);
    SimpleMailMessage secondMessage = factory.create(second);

    assertNotSame(firstMessage, secondMessage);

    assertArrayEquals(
            new String[] {"an@example.net"},
            firstMessage.getTo()
    );

    assertArrayEquals(
            new String[] {"binh@example.net"},
            secondMessage.getTo()
    );

    assertTrue(
            firstMessage.getText().contains("ORDER-101")
    );

    assertTrue(
            secondMessage.getText().contains("ORDER-202")
    );

    assertFalse(
            secondMessage.getText().contains("Nguyễn An")
    );
}
~~~

### 16.1. Không tái sử dụng một mutable SimpleMailMessage singleton

Không nên giữ một SimpleMailMessage được sửa đi sửa lại cho các request đồng thời. Nếu nhiều thread chia sẻ object mutable này, dữ liệu recipient hoặc body có thể bị trộn.

Factory tạo **message mới cho mỗi lần gọi** là thiết kế dễ kiểm thử và an toàn hơn.

### 16.2. Kiểm tra không giữ trạng thái giữa lần gửi

Đây không chỉ là chuyện thread safety; một message được tái sử dụng tuần tự cũng có thể giữ CC/BCC/Reply-To cũ nếu code quên xóa chúng.

## 17. Service gửi thư chỉ nhận message đã được dựng

Tầng service có thể rất mỏng:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final MailSender mailSender;
    private final OrderMailMessageFactory factory;

    public OrderMailService(
            MailSender mailSender,
            OrderMailMessageFactory factory
    ) {
        this.mailSender = mailSender;
        this.factory = factory;
    }

    public void sendConfirmation(OrderMailData data) {
        SimpleMailMessage message = factory.create(data);
        mailSender.send(message);
    }
}
~~~

Ở đây **MailSender** là abstraction đủ cho SimpleMailMessage. Không cần dùng JavaMailSender nếu service chỉ gửi plain-text message, dù JavaMailSender cũng kế thừa MailSender và có thể được inject ở môi trường thật.

### 17.1. Dependency injection giúp test dễ hơn

Test có thể đưa vào:

- Factory thật để kiểm tra nội dung.
- MailSender mock để không kết nối mạng.

Không cần cấu hình SMTP host, port, username hoặc password trong unit test.

## 18. Dùng Mockito ArgumentCaptor để kiểm tra message được gửi

Đây là cách kiểm thử đặc biệt hữu ích khi đối tượng SimpleMailMessage chỉ được tạo **bên trong service** rồi truyền thẳng vào MailSender.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

class OrderMailServiceTest {

    @Test
    void sendsMessageBuiltFromBusinessData() {
        MailSender sender = mock(MailSender.class);
        OrderMailMessageFactory factory =
                new OrderMailMessageFactory();

        OrderMailService service =
                new OrderMailService(sender, factory);

        OrderMailData data = new OrderMailData(
                "an@example.net",
                "Nguyễn An",
                "ORDER-2026-001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );

        service.sendConfirmation(data);

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender, times(1)).send(captor.capture());
        verifyNoMoreInteractions(sender);

        SimpleMailMessage sentMessage = captor.getValue();

        assertEquals(
                "orders@example.org",
                sentMessage.getFrom()
        );

        assertArrayEquals(
                new String[] {"an@example.net"},
                sentMessage.getTo()
        );

        assertEquals(
                "support@example.org",
                sentMessage.getReplyTo()
        );

        assertEquals(
                "Xác nhận đơn hàng ORDER-2026-001",
                sentMessage.getSubject()
        );

        assertTrue(
                sentMessage.getText().contains("Nguyễn An")
        );

        assertTrue(
                sentMessage.getText().contains("500000 VND")
        );

        assertNull(sentMessage.getCc());
        assertNull(sentMessage.getBcc());
    }
}
~~~

Mockito capture đối tượng được truyền vào **MailSender.send(...)**. Vì sender là mock, **không có email nào được gửi ra ngoài**.

### 18.1. ArgumentCaptor kiểm tra điều gì?

Nó kiểm tra **tương tác ở ranh giới**:

~~~text
OrderMailService.sendConfirmation(data)
                  |
                  v
         MailSender.send(message)
                  |
                  v
         Mockito captures message
                  |
                  v
           Assertions on fields
~~~

Nếu service không gọi send, hoặc gọi hai lần ngoài dự kiến, verify sẽ phát hiện.

### 18.2. Captor không thay thế test của factory

Captor hữu ích để biết service chuyển đúng object cho MailSender. Test factory riêng lại hữu ích vì lỗi mapping được cô lập, dễ đọc và không cần Mockito.

Một test suite tốt có thể gồm **unit test factory** và **một số test service với captor**, không cần lặp mọi assertion ở cả hai nơi.

## 19. Test số lần gọi send

Một lỗi có thể làm service gửi trùng khi retry hoặc lặp sai số lần.

~~~java
verify(sender, times(1))
        .send(any(SimpleMailMessage.class));
~~~

Nếu logic yêu cầu không gửi khi dữ liệu không hợp lệ:

~~~java
verifyNoInteractions(sender);
~~~

Nếu quy trình cố ý gửi N thông báo cho N người, test cần assert số lần gọi theo hợp đồng. Đừng chỉ test rằng ít nhất một email đã được gửi.

### 19.1. Test fail-fast trước khi gọi MailSender

~~~java
@Test
void invalidDataDoesNotInvokeSender() {
    MailSender sender = mock(MailSender.class);

    OrderMailService service = new OrderMailService(
            sender,
            new OrderMailMessageFactory()
    );

    OrderMailData invalid = new OrderMailData(
            "not-an-email",
            "Nguyễn An",
            "ORDER-2026-001",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    assertThrows(
            IllegalArgumentException.class,
            () -> service.sendConfirmation(invalid)
    );

    verifyNoInteractions(sender);
}
~~~

Điều này kiểm tra một ràng buộc rất quan trọng: **dữ liệu bị từ chối trước khi tạo side effect gửi email**.

### 19.2. Không nhầm lỗi validation với lỗi transport

Nếu factory từ chối một địa chỉ không hợp lệ, test nên assert validation exception. Không cần mock một SMTP 550 để test chính logic validation.

## 20. Mock factory khi chỉ kiểm tra service orchestration

Có những test chỉ cần xác minh service gọi factory rồi chuyển đúng object cho sender, không quan tâm cấu trúc nội dung.

~~~java
@Test
void servicePassesFactoryResultToSender() {
    MailSender sender = mock(MailSender.class);
    OrderMailMessageFactory factory =
            mock(OrderMailMessageFactory.class);

    SimpleMailMessage prepared = new SimpleMailMessage();
    prepared.setTo("an@example.net");
    prepared.setText("Nội dung test");

    OrderMailData data = new OrderMailData(
            "an@example.net",
            "Nguyễn An",
            "ORDER-2026-001",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    when(factory.create(data)).thenReturn(prepared);

    OrderMailService service =
            new OrderMailService(sender, factory);

    service.sendConfirmation(data);

    verify(factory).create(data);
    verify(sender).send(prepared);
}
~~~

**Lưu ý thiết kế ví dụ:** để Mockito mock một class, project cần cấu hình Mockito phù hợp với phiên bản đang dùng; nếu không muốn mock class concrete, hãy dùng interface factory hoặc truyền factory thật. Nếu class được khai báo **final** như ví dụ factory phía trên, hỗ trợ mock final class phụ thuộc Mockito mock maker/version.

### 20.1. Khi nào không nên mock factory?

Nếu mục tiêu bài test là kiểm tra To/Subject/Text, mock factory sẽ bỏ qua logic cần kiểm tra. Khi đó hãy dùng factory thật hoặc test trực tiếp factory.

### 20.2. Khi nào nên mock factory?

Nếu muốn kiểm tra workflow riêng của service, chẳng hạn “factory tạo message rồi service gửi đúng một lần”, mock factory có thể giúp giới hạn phạm vi test.

## 21. Test xử lý exception từ MailSender

Một unit test có thể mock sender ném **MailException** để xác nhận cách service phản ứng. Ví dụ:

~~~java
import org.springframework.mail.MailSendException;

@Test
void propagatesMailSendFailure() {
    MailSender sender = mock(MailSender.class);

    OrderMailService service = new OrderMailService(
            sender,
            new OrderMailMessageFactory()
    );

    OrderMailData data = new OrderMailData(
            "an@example.net",
            "Nguyễn An",
            "ORDER-2026-001",
            new BigDecimal("500000"),
            Instant.parse("2026-11-12T08:30:00Z")
    );

    doThrow(new MailSendException("Simulated SMTP failure"))
            .when(sender)
            .send(any(SimpleMailMessage.class));

    assertThrows(
            MailSendException.class,
            () -> service.sendConfirmation(data)
    );

    verify(sender, times(1))
            .send(any(SimpleMailMessage.class));
}
~~~

Test này chỉ chứng minh service không nuốt lỗi trong ví dụ hiện tại. Nó không kiểm tra kết nối SMTP hoặc phản hồi server thật.

### 21.1. Nếu service có retry

Nếu ứng dụng bổ sung retry, cần kiểm thử:

- Lỗi nào được retry.
- Số attempts.
- Thời gian/backoff bằng clock/scheduler giả.
- Không retry lỗi dữ liệu vĩnh viễn.
- Không chạy lại nghiệp vụ ngoài ý muốn.
- Xử lý kết quả không xác định có nguy cơ gửi trùng.

Không bật retry toàn bộ MailException chỉ để làm test “send eventually succeeds”.

## 22. Kiểm thử nội dung nhạy cảm và quyền riêng tư

Không chỉ test dữ liệu phải có. Còn phải test dữ liệu **không được xuất hiện**.

Ví dụ một DTO có thể đi kèm thông tin khác trong request, nhưng SimpleMailMessage chỉ nên chứa những trường cần cho email.

Các assertion có thể gồm:

~~~java
assertFalse(message.getText().contains("internal-secret"));
assertFalse(message.getSubject().contains("password"));
assertNull(message.getBcc());
~~~

Những chuỗi này chỉ mang tính minh họa; tốt hơn là test bằng fixture có secret giả được cố ý đưa vào đầu vào và xác nhận factory không dùng nó.

### 22.1. Không cho dữ liệu khách hàng A xuất hiện trong mail khách B

Test hai snapshot độc lập là cách đơn giản để bảo vệ khỏi lỗi dùng chung mutable object hoặc mapping sai.

### 22.2. Không gửi bí mật trong Subject

Subject có thể được hiển thị trong notification preview và nhiều hệ thống xử lý mail. Tránh đưa OTP, token truy cập hoặc thông tin bí mật vào đó nếu không có yêu cầu đặc biệt được đánh giá rủi ro.

### 22.3. Kiểm tra BCC có đúng chính sách

BCC là dữ liệu gửi thực sự ở envelope, dù địa chỉ có thể không xuất hiện trong header mà người nhận nhìn thấy. Một BCC ngoài ý muốn vẫn là sự cố riêng tư; unit test nên xác minh rule của ứng dụng.

## 23. Kiểm thử dữ liệu với bảng trường hợp

Một bảng test giúp thấy phạm vi dữ liệu cần phủ:

| Trường hợp | Input | Kết quả mong đợi |
| --- | --- | --- |
| Hợp lệ cơ bản | Một recipient và DTO đầy đủ | Message đúng From/To/Subject/Text |
| Unicode | Tên Nguyễn Ánh | Text giữ nguyên tiếng Việt |
| Recipient có khoảng trắng hai đầu | Dữ liệu trim được | To được chuẩn hóa |
| Recipient rỗng | Chuỗi blank | Exception, không send |
| Recipient sai cú pháp | Không có @ | Exception, không send |
| Subject input chứa CR/LF | Mã đơn hàng có newline | Exception, không send |
| Mã đơn hàng khác | ORDER-999 | Subject/text đổi theo dữ liệu |
| Tổng tiền khác | 120000 thay 500000 | Body có giá trị mới |
| Tổng tiền âm | -100 theo rule ví dụ | Exception |
| Ngày khác | Instant khác | SentDate khớp |
| Nhiều lần tạo message | Hai DTO khác nhau | Hai message độc lập |
| Không có CC/BCC theo hợp đồng | DTO hợp lệ | CC/BCC không được set |
| MailSender lỗi | Mock ném MailSendException | Service xử lý theo hợp đồng |
| Không gửi trùng | Gọi service một lần | verify sender send đúng một lần |

Bảng là kế hoạch test data, không phải định nghĩa mặc định của Spring. Những rule như “số tiền không âm” phải theo hợp đồng nghiệp vụ cụ thể.

## 24. Fixture và test data builder

Khi test nhiều case, việc lặp lại constructor DTO có thể làm test dài. Có thể dùng một fixture helper:

~~~java
public final class MailTestData {

    private MailTestData() {
    }

    public static OrderMailData validOrder() {
        return new OrderMailData(
                "an@example.net",
                "Nguyễn An",
                "ORDER-2026-001",
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );
    }

    public static OrderMailData withRecipient(String recipient) {
        OrderMailData base = validOrder();

        return new OrderMailData(
                recipient,
                base.customerName(),
                base.orderNumber(),
                base.totalAmount(),
                base.confirmedAt()
        );
    }
}
~~~

Test trở nên rõ hơn:

~~~java
@Test
void rejectsBlankEmail() {
    assertThrows(
            IllegalArgumentException.class,
            () -> factory.create(
                    MailTestData.withRecipient(" ")
            )
    );
}
~~~

### 24.1. Không tạo fixture quá thông minh

Một builder test tự chuẩn hóa dữ liệu hoặc tự sửa recipient sai có thể che lỗi factory. Fixture nên tạo đúng input mà test yêu cầu, không tự thay logic sản phẩm.

### 24.2. Giữ dữ liệu giả nhưng có ý nghĩa

Dùng domain ví dụ như example.org hoặc example.net giúp tránh gửi nhầm và thể hiện đây là dữ liệu test. Không dùng email hoặc mật khẩu người dùng thật trong unit test.

## 25. Tách unit test khỏi integration test

Hai cấp độ test trả lời hai câu hỏi khác nhau.

### 25.1. Unit test

Mục tiêu:

- Dữ liệu nghiệp vụ được map đúng vào SimpleMailMessage.
- Validation hoạt động.
- MailSender nhận đúng message.
- Lời gọi send đúng số lần.
- Không có side effect mạng.

Công cụ:

- JUnit 5.
- Mockito.
- DTO và factory thật hoặc fake.
- Clock cố định nếu cần.

### 25.2. Integration test

Mục tiêu khác:

- Mail transport có tạo/serialize message và gửi tới SMTP server test thành công?
- Cấu hình host/port/AUTH/STARTTLS có hoạt động?
- Địa chỉ và nội dung đi qua provider có đúng không?
- Encoding trên wire và MIME behavior có phù hợp không?

Công cụ:

- SMTP capture server hoặc test server được kiểm soát.
- Spring integration test khi cần.
- Không dùng mailbox người nhận thật nếu không cần.

### 25.3. Vì sao không dùng SMTP thật cho unit test?

Test sẽ:

- Chậm và khó chạy song song.
- Phụ thuộc DNS, mạng và credentials.
- Có thể gửi email ngoài ý muốn.
- Bị ảnh hưởng bởi rate limit/provider outage.
- Khó tái hiện lỗi.
- Tạo nguy cơ rò rỉ dữ liệu test ra môi trường ngoài.

Factory unit test và Mockito captor đã kiểm tra được phần lớn hợp đồng dữ liệu mà không cần SMTP.

## 26. Một số anti-pattern thường gặp

### 26.1. Chỉ verify send(any())

~~~java
verify(sender).send(any(SimpleMailMessage.class));
~~~

Nó chứng minh có gọi gửi nhưng không cho biết **người nhận, tiêu đề và body có đúng không**. Thêm captor/assert hoặc unit test factory.

### 26.2. So sánh mảng bằng assertEquals

~~~java
assertEquals(
        new String[] {"an@example.net"},
        message.getTo()
);
~~~

Cách này không thích hợp để so sánh nội dung String[]; hãy dùng **assertArrayEquals**.

### 26.3. Test phụ thuộc System.currentTimeMillis()

Nếu assert ngày gửi gần bằng giờ hiện tại với ngưỡng rất nhỏ, test có thể flaky. Hãy dùng fixed Clock hoặc Instant cố định.

### 26.4. Dùng dữ liệu production

Test không cần địa chỉ email thật, số điện thoại thật, OTP hoặc token thật. Dùng dữ liệu giả có giá trị kiểm chứng.

### 26.5. Mock chính đối tượng cần kiểm tra

Nếu mục tiêu là xem SimpleMailMessage có Subject/Text gì mà lại mock toàn bộ message, test chỉ chứng minh hành vi của mock. Nên tạo SimpleMailMessage thật và assert getter.

### 26.6. Kiểm thử SMTP trong unit test

Không để unit test phải chờ SMTP provider. Tách MailSender qua interface và mock/fake tại ranh giới.

### 26.7. Assert nội dung quá ít

Kiểm tra rằng text không null không phát hiện sai số tiền hoặc sai tên khách. Assert những giá trị nghiệp vụ quan trọng.

### 26.8. Assert mọi chi tiết biên tập không cần thiết

Ngược lại, nếu hợp đồng chỉ yêu cầu mã đơn hàng và trạng thái, khóa toàn bộ dấu cách và câu chữ có thể gây test thay đổi liên tục khi chỉnh copywriting. Chọn mức assertion theo yêu cầu thực tế.

### 26.9. Xóa lỗi bằng cách bắt Exception và bỏ qua

Nếu dữ liệu không hợp lệ, code không nên âm thầm gửi một email rỗng hoặc thay recipient bằng địa chỉ mặc định nguy hiểm. Test nên kiểm tra fail-fast hoặc một fallback đã được quy định rõ.

## 27. Ví dụ một bộ unit test hoàn chỉnh rút gọn

Bộ test sau minh họa các yêu cầu cốt lõi:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

class OrderMailContractTest {

    private final OrderMailMessageFactory factory =
            new OrderMailMessageFactory();

    private OrderMailData data(
            String recipient,
            String customer,
            String orderNumber
    ) {
        return new OrderMailData(
                recipient,
                customer,
                orderNumber,
                new BigDecimal("500000"),
                Instant.parse("2026-11-12T08:30:00Z")
        );
    }

    @Test
    void mapsAllRequiredFields() {
        SimpleMailMessage message = factory.create(
                data(
                        "an@example.net",
                        "Nguyễn An",
                        "ORDER-001"
                )
        );

        assertAll(
                () -> assertEquals(
                        "orders@example.org",
                        message.getFrom()
                ),
                () -> assertEquals(
                        "support@example.org",
                        message.getReplyTo()
                ),
                () -> assertArrayEquals(
                        new String[] {"an@example.net"},
                        message.getTo()
                ),
                () -> assertEquals(
                        "Xác nhận đơn hàng ORDER-001",
                        message.getSubject()
                ),
                () -> assertTrue(
                        message.getText().contains("Nguyễn An")
                ),
                () -> assertTrue(
                        message.getText().contains("500000 VND")
                ),
                () -> assertEquals(
                        Date.from(Instant.parse(
                                "2026-11-12T08:30:00Z"
                        )),
                        message.getSentDate()
                ),
                () -> assertNull(message.getCc()),
                () -> assertNull(message.getBcc())
        );
    }

    @Test
    void doesNotSendInvalidRecipient() {
        MailSender sender = mock(MailSender.class);
        OrderMailService service =
                new OrderMailService(sender, factory);

        assertThrows(
                IllegalArgumentException.class,
                () -> service.sendConfirmation(
                        data(
                                "invalid-address",
                                "Nguyễn An",
                                "ORDER-001"
                        )
                )
        );

        verifyNoInteractions(sender);
    }

    @Test
    void sendsCorrectPreparedMessageOnce() {
        MailSender sender = mock(MailSender.class);
        OrderMailService service =
                new OrderMailService(sender, factory);

        service.sendConfirmation(
                data("an@example.net", "Nguyễn An", "ORDER-001")
        );

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender, times(1)).send(captor.capture());

        SimpleMailMessage captured = captor.getValue();

        assertArrayEquals(
                new String[] {"an@example.net"},
                captured.getTo()
        );
        assertEquals(
                "Xác nhận đơn hàng ORDER-001",
                captured.getSubject()
        );
        assertTrue(
                captured.getText().contains("ORDER-001")
        );

        verifyNoMoreInteractions(sender);
    }
}
~~~

Bộ test dùng object thật để kiểm tra dữ liệu, mock chỉ ở ranh giới gửi mail. Không cần Spring context hoặc SMTP thật.

## 28. Cách tổ chức mã kiểm thử trong dự án

Một cấu trúc minh họa:

~~~text
src/
├── main/java/
│   └── example/mail/
│       ├── OrderMailData.java
│       ├── OrderMailMessageFactory.java
│       └── OrderMailService.java
└── test/java/
    └── example/mail/
        ├── OrderMailMessageFactoryTest.java
        ├── OrderMailServiceTest.java
        └── MailTestData.java
~~~

Các dependency thường gặp trong ứng dụng Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là ví dụ khai báo Gradle cho dự án dùng Spring Boot; phiên bản được quản lý tùy cấu hình build hiện tại. Chỉ dùng JUnit/Mockito API phù hợp với phiên bản dependency đã cài.

### 28.1. Không cần @SpringBootTest cho mọi test

Factory không phụ thuộc Spring context. Dựng trực tiếp:

~~~java
new OrderMailMessageFactory()
~~~

và gọi create là đủ. Khởi động cả Spring context cho mỗi kiểm thử mapping làm chậm test và có thể kéo theo cấu hình không cần thiết.

### 28.2. Khi nào cần @SpringBootTest?

Khi muốn kiểm tra wiring, auto-configuration hoặc tích hợp với một SMTP capture server, SpringBootTest có thể phù hợp. Nhưng đây là cấp độ khác với unit test dữ liệu của SimpleMailMessage.

## 29. Kiểm tra các trường hợp thay đổi hợp đồng trong tương lai

Khi ứng dụng phát triển, factory có thể được bổ sung:

- CC cho bộ phận kế toán.
- Reply-To theo thương hiệu.
- Locale theo người dùng.
- Nhiều mẫu Subject.
- Nội dung nhắc lại hoặc cảnh báo.
- Chữ ký cuối thư theo tenant.

Mỗi thay đổi có thể ảnh hưởng dữ liệu được gửi. Khi bổ sung một trường:

1. Ghi rõ rule dữ liệu.
2. Bổ sung input mẫu.
3. Assert trường mới và trường không được thay đổi.
4. Thêm trường hợp thiếu hoặc dữ liệu sai.
5. Nếu số lượng recipient thay đổi, kiểm tra quyền riêng tư.
6. Giữ sender mock để không gửi email thật.
7. Kiểm tra các trường hợp input của hai tenant không bị trộn.

Không cần biến unit test thành bản sao đầy đủ của logic nghiệp vụ; mục tiêu là bảo vệ ranh giới dữ liệu có rủi ro.

## 30. Câu hỏi thường gặp

**1. Có cần SMTP server để test SimpleMailMessage không?**

Không. SimpleMailMessage là object Java. Có thể tạo bằng factory rồi assert các getter. Để kiểm tra service gọi send, mock MailSender.

**2. Có nên dùng JavaMailSender hay MailSender trong unit test?**

Nếu service chỉ gửi SimpleMailMessage, interface MailSender là đủ. JavaMailSender hữu ích khi phải xử lý MimeMessage/HTML/attachment.

**3. Làm sao biết To được set đúng?**

Dùng **message.getTo()** và **assertArrayEquals(...)** vì kết quả là String[].

**4. Làm sao kiểm tra service đã truyền đúng message vào send?**

Dùng Mockito **ArgumentCaptor<SimpleMailMessage>**, verify sender.send(captor.capture()), rồi assert các trường của message được bắt.

**5. Vì sao test assertNull CC và BCC?**

Để phát hiện người nhận bản sao ngoài yêu cầu. Với email giao dịch có dữ liệu riêng tư, đây là ràng buộc quan trọng.

**6. Có cần kiểm thử Subject chứa tiếng Việt không?**

Có nếu sản phẩm gửi tiếng Việt. Unit test xác minh String đúng; encoding MIME trên wire nên được kiểm tra ở integration test riêng.

**7. Có nên gọi System.currentTimeMillis() trong test không?**

Không nên nếu cần kết quả xác định. Dùng Instant cố định hoặc Clock.fixed.

**8. SimpleMailMessage có thể gửi HTML không?**

Nó dùng plain text. Nếu cần HTML, dùng MimeMessage với MimeMessageHelper và kiểm thử MIME theo API tương ứng.

**9. InternetAddress.validate() có biết mailbox tồn tại không?**

Không. Nó kiểm tra cú pháp, không xác minh người sở hữu hoặc khả năng chuyển phát thực tế.

**10. Test một message đúng có đủ không?**

Nên thêm một input khác, input sai, Unicode, các trường tùy chọn và kiểm tra hai message độc lập để phát hiện hard-code hoặc state bị dùng chung.

**11. Có nên dùng assertEquals cho toàn bộ text không?**

Có nếu nội dung được cố định theo hợp đồng. Nếu copywriting thường xuyên thay đổi, có thể assert những dữ kiện bắt buộc và dành phần review câu chữ cho quy trình khác.

**12. Vì sao dùng DTO thay vì JPA entity?**

DTO giúp test không phụ thuộc database/persistence context và tránh lỗi lazy loading khi tạo mail ngoài transaction.

**13. Nếu MailSender ném MailSendException thì test gì?**

Kiểm tra service xử lý theo hợp đồng: propagate, lưu lỗi hoặc retry. Unit test không chứng minh SMTP provider thật có phản hồi tương tự.

**14. Có nên kiểm tra số lần send?**

Có, nhất là khi tránh gửi trùng. Mockito verify times(1) giúp kiểm tra một lần gọi service không tạo hai lệnh gửi ngoài dự kiến.

**15. Có nên gửi email thật trong CI để đảm bảo dữ liệu đúng?**

Không cần cho unit test. Sử dụng test SMTP server/capture cho integration test khi muốn kiểm tra transport.

**16. Kiểm tra nội dung nào không được đưa vào email?**

Có thể kiểm tra CC/BCC ngoài yêu cầu, secret/token, thông tin khách khác và các giá trị nhạy cảm không thuộc hợp đồng email.

## 31. Ghi nhớ về kiểm thử dữ liệu tạo SimpleMailMessage

**Kiểm thử dữ liệu SimpleMailMessage là kiểm thử hợp đồng biến đổi dữ liệu nghiệp vụ thành một email plain text.** Thay vì chờ SMTP gửi thư, hãy truyền DTO xác định vào một factory, nhận SimpleMailMessage và assert rõ ràng **From, To, Reply-To, CC, BCC, Subject, Text và SentDate** theo yêu cầu.

**Tách factory khỏi MailSender** giúp kiểm thử không cần mạng. Trong test của service, dùng **Mockito ArgumentCaptor** để bắt message được truyền vào send và kiểm tra các trường; dùng **verify(times(1))** để kiểm tra số lần gọi và **verifyNoInteractions** khi dữ liệu bị từ chối. Đối với mảng địa chỉ To/CC/BCC, dùng **assertArrayEquals**, không so sánh mảng bằng assertEquals.

Dữ liệu test cần có **tiếng Việt, trường thiếu hoặc rỗng, địa chỉ sai cú pháp, khoảng trắng, CR/LF trong header, số tiền/locale, thời điểm cố định và nhiều DTO độc lập**. Các test này bảo vệ khả năng gửi đúng người, đúng nội dung và không rò rỉ dữ liệu ngoài ý muốn. Dù mọi unit test đều thành công, vẫn phải phân biệt chúng với integration test SMTP/MIME: **message được dựng đúng chưa có nghĩa provider đã chấp nhận, chuyển phát hoặc người nhận đã đọc email**.
