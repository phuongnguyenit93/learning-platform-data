# Đảm bảo message không bị sửa sau khi đưa vào hàng đợi

Trong **Spring Framework Mail**, việc gửi một email văn bản có thể bắt đầu rất đơn giản: tạo `SimpleMailMessage`, đặt `From`, `To`, `Subject`, `Text` rồi gọi `mailSender.send(message)`. Khi số lượng email tăng hoặc nghiệp vụ không nên phải đợi SMTP phản hồi, ứng dụng thường chuyển sang mô hình **đưa yêu cầu gửi vào hàng đợi (queue)** để một worker xử lý sau.

Điểm quan trọng là **`SimpleMailMessage` là đối tượng có thể thay đổi (mutable)**. Gọi `setTo(...)`, `setSubject(...)` hay `setText(...)` sẽ thay đổi dữ liệu của chính đối tượng ấy. Nếu một luồng đưa tham chiếu đến đối tượng vào hàng đợi, rồi tiếp tục sửa nó, worker có thể nhận **nội dung khác với nội dung được dự định tại thời điểm enqueue**.

Ví dụ: yêu cầu A được đưa vào queue để gửi cho Alice, nhưng sau đó một phương thức tái sử dụng đối tượng, đổi `To` thành Bob. Khi worker lấy message, thư có thể được gửi cho Bob với tiêu đề hoặc nội dung của Alice. Đây là lỗi vừa khó tái hiện do chạy song song, vừa có thể làm lộ dữ liệu cá nhân.

Mục tiêu bài học là xác định **ranh giới đóng băng dữ liệu**, thiết kế một yêu cầu gửi mail ổn định sau khi enqueue, và hiểu vì sao một queue thread-safe hay một copy constructor đơn thuần chưa phải là toàn bộ giải pháp.

## 1. Phân biệt message, yêu cầu gửi và hàng đợi

Trước tiên, nên tách ba khái niệm:

| Khái niệm | Đại diện trong Java | Vai trò | Có thể thay đổi? |
| --- | --- | --- | --- |
| **Đối tượng mail đang soạn** | `SimpleMailMessage` | Chứa người gửi, người nhận, tiêu đề và text để gửi qua Spring Mail | **Có** qua các setter |
| **Yêu cầu gửi đã được chấp nhận** | `MailJob` hoặc `EmailCommand` do ứng dụng định nghĩa | Chụp dữ liệu mà worker phải dùng, cùng ID và metadata công việc | **Nên bất biến** |
| **Queue** | `BlockingQueue`, broker hoặc bảng outbox | Chuyển giao yêu cầu từ producer sang worker | Có cơ chế đồng bộ/lưu trữ riêng; không tự làm object bất biến |

Một kiến trúc rõ ràng thường có dạng:

~~~mermaid
flowchart LR
    A["Nghiệp vụ phát sinh email"] --> B["Tạo MailJob bất biến"]
    B --> C["Queue / Outbox"]
    C --> D["Worker nhận MailJob"]
    D --> E["Tạo SimpleMailMessage mới"]
    E --> F["MailSender.send"]
    F --> G["SMTP provider"]
~~~

**Mốc quan trọng là lúc enqueue thành công:** toàn bộ dữ liệu mà hệ thống đã chấp nhận để gửi phải có một biểu diễn ổn định. Worker có thể chạy ngay lập tức, sau vài giây, hoặc sau khi ứng dụng restart. Việc nội dung email thay đổi trong khoảng đó phải là **quyết định nghiệp vụ có chủ đích**, không phải hậu quả của việc một tham chiếu Java bị sửa.

## 2. Vì sao đưa thẳng `SimpleMailMessage` vào queue có thể sai?

Giả sử ứng dụng có một queue trong bộ nhớ:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.springframework.mail.SimpleMailMessage;

BlockingQueue<SimpleMailMessage> queue = new LinkedBlockingQueue<>();

SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("no-reply@example.com");
message.setTo("alice@example.net");
message.setSubject("Thông báo tài khoản Alice");
message.setText("Nội dung dành riêng cho Alice.");

queue.add(message);

// Producer tiếp tục thay đổi chính object đã enqueue.
message.setTo("bob@example.net");
message.setSubject("Thông báo tài khoản Bob");
~~~

`queue.add(message)` **đưa một tham chiếu** đến `message` vào queue trong bộ nhớ; nó không tạo bản sao sâu của đối tượng. Vì vậy, một worker lấy tham chiếu đó sau dòng `setTo` có thể thấy người nhận là `bob@example.net`.

~~~text
T0  Producer: message.to = Alice
T1  Producer: queue.add(message)      # Queue giữ tham chiếu M
T2  Producer: message.to = Bob        # Vẫn là đối tượng M
T3  Worker:   queue.take() -> M
T4  Worker:   sender.send(M)          # Có thể gửi tới Bob
~~~

Nếu worker lấy và sử dụng message trước khi producer sửa, kết quả lại có thể là Alice. Do lịch chạy các thread thay đổi, lỗi trở nên **không xác định theo thời điểm (race condition)**.

### 2.1. Thread-safe queue không đồng nghĩa message thread-safe

`LinkedBlockingQueue` cung cấp các thao tác thêm/lấy có cơ chế đồng bộ và bảo đảm *happens-before* phù hợp: các thay đổi thực hiện **trước khi** đưa phần tử vào queue sẽ được worker nhìn thấy khi lấy phần tử đó.

Nhưng điều này **không cấm producer sửa phần tử sau enqueue**, cũng không làm những setter trên `SimpleMailMessage` trở thành an toàn với truy cập đồng thời. Khi hai thread đọc/ghi cùng một object mutable mà không có giao ước đồng bộ riêng, việc hiển thị giá trị và tổ hợp các trường có thể trở nên khó dự đoán.

Đặc biệt, một thư có thể bị “trộn” dữ liệu: `To` của yêu cầu B, `Subject` của yêu cầu A và `Text` của một lần cập nhật khác. Chỉ cần đảm bảo queue là thread-safe là chưa đủ.

### 2.2. `@Async` có thể gặp cùng vấn đề

Ví dụ không nên:

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("alice@example.net");
mail.setSubject("Thông báo cho Alice");
mail.setText("Nội dung của Alice");

asyncMailService.sendLater(mail); // Lịch thực thi có thể chưa bắt đầu.
mail.setTo("bob@example.net");   // Vẫn sửa cùng object.
~~~

Một lời gọi bất đồng bộ chỉ hoãn công việc sang executor/thread khác; nó không tự biến đối tượng truyền vào thành snapshot. Ngay cả khi không có message broker, **bất kỳ ranh giới bất đồng bộ nào** cũng cần xem xét quyền sở hữu dữ liệu.

## 3. Ba nguyên tắc để tránh message thay đổi sau enqueue

1. **Chụp dữ liệu trước khi enqueue.** Xác định rõ người nhận, tiêu đề, body và những giá trị cần giữ nguyên trong lần gửi này.
2. **Chỉ enqueue một payload bất biến hoặc dạng dữ liệu đã được serialize độc lập.** Không đưa tham chiếu tới `SimpleMailMessage` hoặc một DTO mutable còn được producer giữ lại để chỉnh sửa.
3. **Worker dựng message mới từ payload.** Chỉ worker sở hữu `SimpleMailMessage` được tạo để gửi; không chia sẻ đối tượng đó qua nhiều job hoặc thread.

Trong Java, có thể sử dụng một **`record` với các trường bất biến thực sự**. `String` và `UUID` là các giá trị bất biến phù hợp; với danh sách người nhận, phải sao chép `List` thay vì giữ nguyên danh sách mutable bên ngoài.

### 3.1. Record không tự làm các trường bên trong bất biến

Ví dụ thiếu an toàn:

~~~java
record UnsafeMailJob(String[] recipients, String subject, String body) {}

String[] recipients = {"alice@example.net"};
UnsafeMailJob job = new UnsafeMailJob(recipients, "Xin chào", "Nội dung");

recipients[0] = "bob@example.net";
// job.recipients()[0] cũng đã bị thay đổi!
~~~

`record` ngăn việc gán lại thành phần của đối tượng sau khởi tạo, nhưng **không tự sao chép mảng, danh sách mutable hay những object con**. Nếu record giữ tham chiếu `String[]`, người khác vẫn có thể sửa mảng đó.

Tương tự, một record chứa `Date`, `StringBuilder`, `Map` mutable hoặc một `MimeMessage` vẫn có thể bị thay đổi từ bên ngoài. Vì vậy, tính bất biến phải được xét **đệ quy với từng trường mà worker sẽ sử dụng**.

## 4. Thiết kế payload bất biến cho email văn bản

Một cách rõ ràng là khai báo `TextMailJob` làm **dữ liệu công việc**, tách khỏi API gửi thư của Spring:

~~~java
package com.example.mail.queue;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record TextMailJob(
        UUID jobId,
        String from,
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String replyTo,
        String subject,
        String body) {

    public TextMailJob {
        Objects.requireNonNull(jobId, "jobId");
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(subject, "subject");
        Objects.requireNonNull(body, "body");

        to = List.copyOf(Objects.requireNonNull(to, "to"));
        cc = List.copyOf(Objects.requireNonNull(cc, "cc"));
        bcc = List.copyOf(Objects.requireNonNull(bcc, "bcc"));

        if (to.isEmpty()) {
            throw new IllegalArgumentException(
                    "Mail job phải có ít nhất một người nhận To");
        }
    }
}
~~~

Các lựa chọn thiết kế:

- `jobId` là danh tính của yêu cầu gửi, phục vụ lưu trạng thái, log và cơ chế tránh tạo nhiều job cho cùng sự kiện.
- `from`, `replyTo`, `subject` và `body` là các chuỗi đã được xác định khi enqueue. `replyTo` có thể là `null` nếu không cần header này.
- `to`, `cc` và `bcc` là danh sách; `List.copyOf(...)` tạo một danh sách không cho phép sửa qua các thao tác thông thường và **không giữ các thay đổi sau này của list nguồn**.
- Các phần tử danh sách là `String` bất biến, nên việc sao chép container đủ cho ví dụ này. Nếu phần tử là object mutable, cần sao chép hoặc chuyển sang kiểu dữ liệu bất biến khác.
- Constructor thực hiện kiểm tra cơ bản để tránh enqueue job thiếu dữ liệu. Kiểm tra quyền gửi, policy người nhận, độ dài nội dung và thông tin nhạy cảm vẫn do ứng dụng phụ trách.

**Vì sao không dùng `String[]`?** Khi trả về một mảng từ accessor, bên gọi có thể thay đổi trực tiếp phần tử. Với danh sách được tạo bằng `List.copyOf`, accessor trả về một giá trị không cho phép `add`, `set` hoặc `remove`. Điều này giúp record trở thành một snapshot ổn định với tập trường đang dùng.

### 4.1. Chụp dữ liệu rồi enqueue

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

BlockingQueue<TextMailJob> queue = new LinkedBlockingQueue<>();
List<String> recipients = new ArrayList<>(
        List.of("alice@example.net"));

TextMailJob job = new TextMailJob(
        UUID.randomUUID(),
        "no-reply@example.com",
        recipients,
        List.of(),
        List.of(),
        "support@example.com",
        "Xác nhận cho Alice",
        "Xin chào Alice, tài khoản của bạn đã được tạo."
);

queue.add(job);

// Đổi danh sách nguồn sau enqueue:
recipients.set(0, "bob@example.net");

// Payload trong queue vẫn giữ người nhận Alice.
System.out.println(job.to()); // [alice@example.net]
~~~

Producer có thể thay đổi `recipients` mà không ảnh hưởng dữ liệu trong `job`. Từ sau `queue.add(job)`, không có setter nào để đổi các trường của job; worker sẽ nhận một yêu cầu nhất quán.

Ví dụ trên dùng **queue trong bộ nhớ để giải thích tính bất biến**. `LinkedBlockingQueue` không lưu công việc qua restart, không có cơ chế retry bền vững, không tự khởi tạo worker và không đủ làm hạ tầng gửi mail đáng tin cậy cho mọi ứng dụng production.

### 4.2. Dựng `SimpleMailMessage` bên trong worker

Worker chỉ nhận `TextMailJob`, tạo một message mới rồi giao cho `JavaMailSender`:

~~~java
package com.example.mail.queue;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class TextMailWorker {
    private final JavaMailSender sender;

    public TextMailWorker(JavaMailSender sender) {
        this.sender = sender;
    }

    public void deliver(TextMailJob job) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(job.from());
        mail.setTo(job.to().toArray(String[]::new));

        if (!job.cc().isEmpty()) {
            mail.setCc(job.cc().toArray(String[]::new));
        }
        if (!job.bcc().isEmpty()) {
            mail.setBcc(job.bcc().toArray(String[]::new));
        }
        if (job.replyTo() != null && !job.replyTo().isBlank()) {
            mail.setReplyTo(job.replyTo());
        }

        mail.setSubject(job.subject());
        mail.setText(job.body());
        sender.send(mail);
    }
}
~~~

Như vậy, đối tượng mutable `SimpleMailMessage` chỉ tồn tại trong phạm vi **một lần xử lý của worker**. Producer không nắm tham chiếu đến nó. Worker không giữ lại và tái sử dụng đối tượng cho job tiếp theo. Điều này đơn giản hóa việc kiểm soát ai có quyền thay đổi nội dung ngay trước khi gửi.

Trong một hệ thống dùng queue thật, callback hoặc consumer sẽ gọi `deliver(job)`. Đoạn code không tự nhận job từ broker và không hàm ý rằng Spring tự chạy worker chỉ vì lớp có `@Component`.

## 5. Copy constructor của `SimpleMailMessage` giúp được gì?

Spring cung cấp cách tạo message từ một message khác:

~~~java
SimpleMailMessage template = new SimpleMailMessage();
template.setFrom("no-reply@example.com");
template.setReplyTo("support@example.com");
template.setSubject("Thông báo");

SimpleMailMessage message = new SimpleMailMessage(template);
message.setTo("alice@example.net");
message.setText("Nội dung cho Alice");
~~~

Đây là cách hữu ích để **tránh sửa trực tiếp một template dùng chung**, nhất là trong ứng dụng tạo nhiều thư plain text có chung `From` và `Reply-To`.

Tuy nhiên, cần phân biệt:

- **Copy constructor** tạo **một `SimpleMailMessage` mới** với dữ liệu từ message nguồn tại thời điểm sao chép.
- Bản sao **vẫn là một `SimpleMailMessage` mutable**; code có tham chiếu tới nó vẫn có thể gọi setter.
- Nếu bản sao cũng bị đưa vào queue và producer còn sửa bản sao đó, rủi ro tương tự xuất hiện.

Do đó, cách viết sau vẫn không bảo đảm snapshot:

~~~java
SimpleMailMessage queuedMessage = new SimpleMailMessage(template);
queuedMessage.setTo("alice@example.net");
queue.add(queuedMessage);

queuedMessage.setTo("bob@example.net"); // Vẫn sửa object trong queue.
~~~

Nếu dự án nhỏ buộc phải enqueue `SimpleMailMessage`, tối thiểu phải quy định **chuyển quyền sở hữu**: producer không được sửa hay đọc/ghi đối tượng sau enqueue, worker là nơi duy nhất sử dụng nó, và không có thread nào khác giữ tham chiếu để sửa. Tuy nhiên, quy ước này khó được bảo đảm bằng kiểu Java vì class vẫn có setter. **Payload bất biến hoặc dữ liệu đã serialize** cung cấp ranh giới rõ ràng và dễ duy trì hơn.

## 6. Giá trị nào cần “đóng băng” vào thời điểm enqueue?

Không phải mọi thông tin trong quá trình gửi đều thuộc nội dung email. Để xác định snapshot đúng, hãy phân loại:

| Dữ liệu | Ví dụ | Có nên chụp khi enqueue? |
| --- | --- | --- |
| Người nhận | `To`, `Cc`, `Bcc` | **Có**, trừ khi nghiệp vụ chủ đích giải quyết người nhận lúc gửi |
| Tiêu đề | `Subject` | **Có** nếu yêu cầu đã được chấp nhận với tiêu đề cụ thể |
| Nội dung text | `Body`, ngôn ngữ, liên kết | **Có** nếu phải giữ nguyên thư được yêu cầu tại thời điểm đó |
| Địa chỉ đứng tên gửi | `From`, `Reply-To` | Chọn chính sách rõ: chụp ngay hoặc tra từ cấu hình khi gửi |
| ID nghiệp vụ | `orderId`, `userId`, `eventId` | **Có** để truy vết và tránh tạo job trùng |
| Phiên bản template | `welcome-v3` | **Có** nếu worker sẽ render template ở thời điểm khác |
| Thời gian tạo yêu cầu | `createdAt` bằng `Instant` | Nên có để audit và tính thời gian chờ |
| SMTP host/port/credentials | `spring.mail.*` | **Không đưa secret vào payload**; để tầng sender lấy từ cấu hình runtime |
| Số lần retry và trạng thái | `attempts`, `PENDING`, `FAILED` | Quản lý bằng metadata/job state riêng, có thể cập nhật theo thời gian |

Tùy yêu cầu, có hai mô hình:

**Mô hình A — chụp nội dung hoàn chỉnh:** producer tạo `subject` và `body` cuối cùng rồi enqueue. Worker chỉ dựng và gửi. Phù hợp với yêu cầu “message phải giữ đúng nội dung khi được đưa vào hàng đợi”.

**Mô hình B — chụp dữ liệu đầu vào + template version:** producer lưu `templateId`, `templateVersion` và các biến bất biến, worker render sau. Phù hợp khi việc render phải diễn ra ở worker, nhưng cần bảo đảm template version, tài nguyên tham chiếu và dữ liệu biến không bị thay đổi ngoài dự kiến.

Ví dụ nếu chỉ lưu:

~~~json
{
  "userId": "U42",
  "templateName": "welcome"
}
~~~

rồi worker **đọc tên hiển thị mới nhất** từ database và dùng **template hiện hành** tại thời điểm gửi, nội dung mail có thể khác so với thời điểm enqueue. Đây có thể là yêu cầu hợp lệ trong một số nghiệp vụ, nhưng không đáp ứng điều kiện **giữ nguyên message** nếu nội dung đã được phê duyệt trước đó.

### 6.1. Với mã xác nhận, liên kết hết hạn và dữ liệu thời gian

Snapshot nội dung không đồng nghĩa nội dung luôn còn hiệu lực lúc được gửi. Ví dụ một email reset mật khẩu chứa đường dẫn có hạn 10 phút, nhưng queue bị kẹt 30 phút. Worker có thể gửi đúng nội dung đã chụp nhưng đường dẫn đã hết hạn.

Thiết kế nên lưu thêm hạn sử dụng hoặc quy tắc kiểm tra trước gửi:

~~~text
jobId: ...
createdAt: 2026-11-12T08:00:00Z
expiresAt: 2026-11-12T08:10:00Z
subject: "Đặt lại mật khẩu"
body: "..."
~~~

Khi quá hạn, worker có thể đánh dấu job không còn hợp lệ theo nghiệp vụ thay vì sửa ngầm đường dẫn hoặc tự thay token. Nếu yêu cầu gửi lại với token mới, nên tạo **yêu cầu mới** có danh tính và nội dung mới.

### 6.2. Cấu hình runtime vẫn có thể thay đổi hợp lệ

Một thư đã enqueue có thể được gửi qua SMTP provider A hoặc B tùy cấu hình tại thời điểm worker chạy. Việc đổi mật khẩu hoặc host SMTP **không phải sửa nội dung mail**, mà là thay đổi kênh vận chuyển.

Với `From`, cần quyết định rõ: nếu địa chỉ này là một phần của nội dung đã được phê duyệt, hãy lưu trong job. Nếu địa chỉ luôn phải theo chính sách sender mới nhất, worker có thể lấy từ cấu hình nhưng cần tài liệu hóa quy tắc đó. Không âm thầm thay đổi chính sách sau khi hệ thống đã hứa giữ nguyên message.

## 7. Queue trong bộ nhớ và queue bền vững khác nhau thế nào?

### 7.1. Queue trong cùng JVM

~~~text
Producer thread          Shared JVM heap        Worker thread
     |                         |                      |
     |--- enqueue(job) ------->|                      |
     |                         |---- take(job) ------>|
~~~

`BlockingQueue<TextMailJob>` giúp chuyển dữ liệu giữa các thread trong cùng tiến trình. Khi dùng job bất biến, dữ liệu không thể bị sửa bằng việc thay đổi danh sách nguồn sau enqueue. Tuy nhiên:

- Job chưa được xử lý có thể **mất khi tiến trình dừng**.
- Không có cơ chế retry/ack bền vững nếu bạn không tự xây dựng.
- Một job có thể bị lấy ra rồi gửi thất bại; nếu không lưu trạng thái, khó biết phải chạy lại.

Vì vậy, queue trong bộ nhớ phù hợp để minh họa nguyên tắc đồng thời hoặc cho công việc mà tổ chức chấp nhận mất khi restart; không nên mặc định dùng nó cho những email giao dịch bắt buộc.

### 7.2. Message broker hoặc queue có cơ chế serialize

Khi gửi dữ liệu qua broker, ứng dụng thường chuyển payload thành **JSON, Avro, Protobuf hoặc byte stream**. Quá trình serialize thông thường tạo một bản dữ liệu độc lập với object nguồn:

~~~text
Producer TextMailJob
       |
       v
Serialize thành bytes
       |
       v
Broker lưu/thông chuyển bytes
       |
       v
Worker deserialize thành TextMailJob
       |
       v
Tạo SimpleMailMessage và gửi
~~~

Nếu producer sửa một `ArrayList` sau khi **serialize xong và broker đã chấp nhận bytes**, các bytes đã gửi không đổi. Tuy nhiên, nếu ứng dụng vẫn giữ một object mutable và việc serialize thực sự được thực hiện **sau** thời điểm gọi API bất đồng bộ, thay đổi trước lúc serialize có thể ảnh hưởng tới payload. Cần hiểu ranh giới của thư viện queue đang dùng, đặc biệt khi producer sử dụng buffer, callback, batch hoặc gửi bất đồng bộ.

Do vậy, cứ dùng **payload bất biến từ trước lúc gọi publish** vẫn là lựa chọn an toàn và dễ suy luận. Đối tượng được deserialize ở worker cũng nên được coi là dữ liệu không được sửa; metadata retry/trạng thái nên nằm ở lớp quản lý công việc.

### 7.3. Outbox và giao dịch nghiệp vụ

Ví dụ nghiệp vụ tạo đơn hàng và gửi xác nhận:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT order ...
  INSERT email_outbox(
      job_id, order_id, payload_snapshot, status='PENDING'
  )
COMMIT
~~~

Thay vì cập nhật đơn hàng rồi publish queue ngay trong một thao tác không có bảo đảm giao dịch chung, **transactional outbox** lưu yêu cầu gửi cùng transaction với dữ liệu nghiệp vụ. Sau đó một worker/relay đọc outbox, publish job hoặc gửi email.

`payload_snapshot` nên chứa dữ liệu đã xác định ở thời điểm commit (hoặc tham chiếu đến một phiên bản nội dung bất biến). Khi retry, worker đọc **cùng snapshot** thay vì tra lại dữ liệu mutable hiện tại của đơn hàng và vô tình gửi nội dung khác.

Outbox giúp giảm khả năng “đơn hàng lưu thành công nhưng yêu cầu mail bị mất”. Nó **không tự bảo đảm email được gửi đúng một lần**, vì bước chuyển qua SMTP là một hệ thống bên ngoài transaction database.

## 8. Đảm bảo không sửa message khác với chống gửi trùng

Hai vấn đề độc lập:

| Vấn đề | Ví dụ | Biện pháp chính |
| --- | --- | --- |
| **Message bị sửa sau enqueue** | Job của Alice bị thay To thành Bob | Payload bất biến, snapshot, sở hữu dữ liệu rõ ràng |
| **Cùng một message bị gửi nhiều lần** | Worker gửi xong nhưng crash trước khi ack | ID job, quy tắc retry, trạng thái xử lý và chống gửi trùng |

Một queue bền vững thường triển khai **at-least-once delivery**: nếu chưa nhận được xác nhận xử lý, cùng job có thể được giao lại. Ví dụ:

~~~text
T1 Worker nhận job-123
T2 SMTP trả 250: thư được chấp nhận
T3 Worker crash trước khi đánh dấu job-123 đã hoàn tất
T4 Broker giao lại job-123
T5 Worker có thể gửi thư lần thứ hai
~~~

Payload bất biến giúp hai lần gửi có cùng dữ liệu, nhưng **không ngăn việc phát sinh hai email**. Để giảm gửi trùng:

- Gắn **`jobId`** hoặc business event ID ổn định ngay từ lúc tạo yêu cầu.
- Ngăn tạo hai job cho cùng sự kiện nếu nghiệp vụ yêu cầu (unique constraint/idempotency key).
- Quản lý trạng thái `PENDING`, `PROCESSING`, `SUBMITTED`, `FAILED` theo từng job, kèm số lần thử và thời điểm xử lý.
- Nếu provider hỗ trợ idempotency key hoặc truy vấn message status, tận dụng đúng theo contract của provider.
- Với SMTP thuần, hiểu rằng một lần timeout sau khi gửi dữ liệu có thể gây **kết quả chưa rõ**; không được khẳng định có thể đạt exactly-once tuyệt đối chỉ bằng lock hoặc database.

Đối với mail giao dịch quan trọng, nên ưu tiên **độ tin cậy, khả năng tra cứu và kiểm soát gửi trùng** cùng với tính bất biến của payload.

## 9. Mối quan hệ giữa dữ liệu bất biến và quyền sở hữu object

Trong một hệ thống có nhiều luồng, có thể áp dụng quy ước:

~~~text
Producer owns MutableBuilder
    |
    | validate + snapshot
    v
Producer/Queue owns immutable MailJob
    |
    | handoff
    v
Worker owns newly constructed SimpleMailMessage
    |
    | send
    v
Sender / SMTP provider
~~~

Ở mỗi ranh giới:

1. **Mutable builder của producer** có thể được chỉnh khi yêu cầu chưa chấp nhận.
2. **MailJob** trở thành thông tin cố định khi enqueue; không có setter hay reference mutable cho phép sửa.
3. **Worker** tạo một `SimpleMailMessage` riêng, có thể bổ sung những field theo chính sách đã chốt rồi gọi `send`.
4. Sau khi gọi `send`, worker không sửa hoặc chia sẻ `SimpleMailMessage` với job khác.

Quy tắc này tránh “sở hữu chung” một message giữa producer, queue và worker. Trong Java, nó dễ thực thi hơn việc phải đặt nhiều `synchronized` quanh các setter, nhất là khi các tác vụ nằm trên nhiều máy khác nhau.

## 10. Trường hợp có attachment hoặc HTML thì sao?

Trong phần **Simple mail**, ta chủ yếu dùng `SimpleMailMessage` với `String`. Nếu sau này chuyển sang `MimeMessage` để gửi HTML, file đính kèm hoặc hình ảnh inline, rủi ro dữ liệu mutable còn rộng hơn:

- `MimeMessage` và `MimeBodyPart` có thể được chỉnh sau khi tạo.
- Một `byte[]` đính kèm có thể bị sửa nếu job giữ nguyên tham chiếu.
- `InputStream` có thể bị tiêu thụ hoặc đóng trước khi worker đọc.
- `File` hoặc đường dẫn trỏ tới một file có thể thay đổi nội dung trước khi worker gửi.
- Template HTML có thể được cập nhật giữa hai thời điểm enqueue và dequeue.

Với file đính kèm cần giữ nguyên, hãy chọn một trong những cách kiểm soát sau:

- Chụp **bytes** của tệp và sao chép mảng phòng vệ, có giới hạn kích thước phù hợp.
- Lưu vào **object storage với key/phiên bản bất biến**, worker lấy đúng phiên bản đó.
- Lưu **content hash** để phát hiện dữ liệu đính kèm bị thay đổi ngoài ý muốn.
- Không chỉ giữ đường dẫn đến một file tạm mà process khác có thể ghi đè hoặc xóa.

Ví dụ record chỉ có `byte[]` như:

~~~java
record AttachmentJob(byte[] pdfBytes) {}
~~~

**Chưa bất biến**, vì bên ngoài có thể sửa `pdfBytes`. Nếu bắt buộc dùng mảng, phải sao chép trong constructor và khi trả về cho bên gọi, hoặc dùng kiểu biểu diễn bất biến phù hợp:

~~~java
public final class PdfSnapshot {
    private final byte[] bytes;

    public PdfSnapshot(byte[] source) {
        this.bytes = source.clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Đối với thư text, chọn `String` và `List<String>` bất biến giúp bài toán đơn giản hơn đáng kể.

## 11. Dữ liệu đã enqueue vẫn cần bảo vệ thông tin nhạy cảm

Một payload bất biến có thể chứa thông tin cá nhân. Nếu queue hoặc outbox lưu toàn bộ body, dữ liệu đó có thể tồn tại lâu hơn vòng đời request HTTP ban đầu.

Cần cân nhắc:

- **Phân quyền** producer, consumer và người quản trị queue.
- **Mã hóa đường truyền và lưu trữ** theo khả năng của broker/database và yêu cầu dữ liệu.
- **Retention** của queue, dead-letter queue, outbox và bản sao lưu.
- **Log** chỉ ghi ID job, loại thư, trạng thái hoặc mã lỗi khi có thể; tránh in nguyên `body`, token hoặc toàn bộ recipient list.
- **Không đưa SMTP password/API key vào job payload**; worker nhận credentials từ cấu hình runtime/secret manager.
- **Truy cập dữ liệu người dùng** theo mục đích gửi thư hợp lệ, hạn chế endpoint cho phép gửi email tùy ý.

Việc lưu snapshot giúp giữ nguyên thông điệp, nhưng không có nghĩa nên lưu mã OTP hoặc token reset mật khẩu mãi mãi. Với dữ liệu có thời hạn, kết hợp hạn sử dụng và xóa/ẩn nội dung sau khi không còn cần thiết.

## 12. Kiểm thử ý tưởng “không sửa sau enqueue”

Một unit test nhỏ có thể xác minh constructor của payload **không giữ lại danh sách mutable từ bên ngoài**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class TextMailJobTest {
    @Test
    void recipientsRemainStableWhenInputListChanges() {
        List<String> mutableRecipients =
                new ArrayList<>(List.of("alice@example.net"));

        TextMailJob job = new TextMailJob(
                UUID.randomUUID(),
                "no-reply@example.com",
                mutableRecipients,
                List.of(),
                List.of(),
                null,
                "Thông báo cho Alice",
                "Nội dung cho Alice"
        );

        // Thay đổi dữ liệu đã dùng để tạo job.
        mutableRecipients.set(0, "bob@example.net");

        assertEquals("alice@example.net", job.to().get(0));
        assertThrows(
                UnsupportedOperationException.class,
                () -> job.to().set(0, "eve@example.net"));
    }
}
~~~

Test trên nhắm vào **khả năng duy trì snapshot**, không thử gửi email thực. Nó minh họa điều cần kiểm chứng trong thiết kế: job đã tạo không đổi khi producer chỉnh danh sách nguồn và người khác không thể sửa danh sách qua accessor.

### 12.1. Kiểm chứng tại ranh giới worker

Với mail service, có thể dùng mock `JavaMailSender` để bắt đối tượng `SimpleMailMessage` mà worker đưa vào `send`, rồi đối chiếu `To`, `Subject`, `Text` với dữ liệu job. Các trường cần đối chiếu là những trường đã đóng băng khi enqueue.

Một bài kiểm thử tích hợp có thể chạy worker cùng SMTP giả lập như Mailpit hoặc GreenMail và kiểm tra thông điệp nhận được. Nếu có message broker/outbox, cần quan sát **serialized payload trước và sau khi producer sửa dữ liệu nguồn**. Đây là kiểm thử ranh giới, không cần SMTP production hay người nhận thật.

### 12.2. Những trường hợp biên cần cân nhắc

| Tình huống | Điều nên xảy ra |
| --- | --- |
| Producer sửa `ArrayList` sau enqueue | Job trong queue vẫn giữ đúng recipient cũ |
| Producer đổi giá trị người dùng trong database | Worker dùng snapshot đã chốt nếu nghiệp vụ yêu cầu giữ nguyên |
| Hai worker xử lý hai job cùng lúc | Mỗi worker tạo `SimpleMailMessage` riêng |
| Retry job sau thất bại tạm thời | Dùng lại nội dung payload đã chốt, trừ khi nghiệp vụ tạo job mới |
| Job quá hạn | Worker bỏ hoặc đánh dấu thất bại theo chính sách, không âm thầm sửa token |
| Template được deploy phiên bản mới | Job cũ dùng bản nội dung đã render hoặc template version đã cố định |
| SMTP credential được rotate | Worker lấy secret cấu hình mới; không cập nhật nội dung job |
| Service restart khi queue ở RAM | Job chưa xử lý có thể mất; dùng hàng đợi bền vững nếu cần |

## 13. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách thiết kế phù hợp |
| --- | --- | --- |
| Enqueue trực tiếp `SimpleMailMessage` rồi tiếp tục gọi setter | Message trong queue có thể đổi nội dung | Snapshot thành job bất biến trước enqueue |
| Cho rằng `BlockingQueue` đã copy object | Queue trong RAM chỉ giữ tham chiếu | Sao chép dữ liệu hoặc tạo immutable payload |
| Dùng `record` chứa `String[]` mutable | Có thể sửa mảng qua tham chiếu | Dùng `List.copyOf` với `String` hoặc defensive copy |
| Chỉ tạo `new SimpleMailMessage(old)` và coi bản sao vĩnh viễn bất biến | Bản sao vẫn có setter | Không chia sẻ bản sao sau enqueue; tốt hơn là enqueue job bất biến |
| Dùng chung một `SimpleMailMessage` cho mọi job | Dữ liệu các request có thể đè lên nhau | Worker tạo message mới mỗi lần gửi |
| Chỉ lưu ID user rồi đọc mọi trường lúc gửi | Tên, email, nội dung có thể đổi theo database | Chọn và ghi rõ snapshot policy |
| Lưu template ID nhưng không lưu version | Sau deploy, mail chờ có thể đổi nội dung | Render sớm hoặc ghim template version |
| Lưu đường dẫn file tạm rồi gửi sau | Attachment có thể bị ghi đè/xóa | Snapshot file hoặc dùng versioned storage |
| Coi queue bất biến là bảo đảm exactly-once | Job vẫn có thể gửi trùng sau crash/retry | Job ID, trạng thái và cơ chế idempotency |
| Đưa password SMTP vào payload | Secret bị nhân bản trong broker, log và backup | Secret chỉ nằm ở runtime configuration |

## 14. Tình huống tổng hợp: gửi thông báo đơn hàng qua hàng đợi

Giả sử người dùng đặt một đơn hàng, hệ thống cần gửi email xác nhận. Dữ liệu lúc đơn hàng hoàn thành:

~~~text
Order ID:  A-2048
Email:     alice@example.net
Subject:   Đơn hàng A-2048 đã được xác nhận
Text:      Xin chào Alice, đơn hàng A-2048 đã được ghi nhận.
~~~

Một thiết kế theo nguyên tắc snapshot:

1. **Order service** xác nhận nghiệp vụ và lấy người nhận, subject, body cuối cùng tại thời điểm sự kiện.
2. **Mail producer** kiểm tra đầu vào, tạo `TextMailJob` với `jobId`, danh sách người nhận sao chép và nội dung `String`.
3. **Queue/outbox** nhận payload bất biến hoặc dạng serialize của payload, tách khỏi các đối tượng mutable phía producer.
4. Nếu ứng dụng cập nhật tên hiển thị của Alice thành một giá trị khác, **job đã enqueue không đổi**.
5. **Worker** nhận job, dựng một `SimpleMailMessage` mới từ snapshot rồi gọi `JavaMailSender.send(...)`.
6. **Job processor** ghi trạng thái và xử lý retry khi cần. Nếu kết quả SMTP chưa rõ do mất kết nối, hệ thống đánh giá nguy cơ gửi trùng trước khi thử lại.

Đây là sự khác nhau giữa hai cách biểu diễn:

~~~text
Không an toàn:
  Queue<SimpleMailMessage> --> object mutable dùng chung --> send

Ổn định hơn:
  Queue<TextMailJob bất biến> --> worker dựng message mới --> send
~~~

Nguyên tắc này không chỉ áp dụng cho email. Bất cứ hệ thống bất đồng bộ nào nhận một object mutable từ producer đều cần xác định **thời điểm snapshot**, **ai sở hữu dữ liệu** và **những thay đổi nào được phép xảy ra sau khi công việc đã được chấp nhận**.

Với Spring Framework Mail, lựa chọn rõ ràng nhất cho **Simple mail** là: **đưa nội dung thư vào một job bất biến, giữ job đó trong queue, và chỉ tạo `SimpleMailMessage` ở worker ngay trước khi gửi**. Thiết kế này ngăn một nguyên nhân quan trọng của việc gửi sai người nhận hoặc sai nội dung, đồng thời giúp hệ thống dễ bổ sung retry, outbox và theo dõi trạng thái mà không phụ thuộc vào một đối tượng Java mutable được chia sẻ.

### Tài liệu tham khảo

- **Spring Framework API — `SimpleMailMessage`:** các setter, copy constructor và vai trò của đối tượng mail dạng text.
- **Spring Framework API — `MailSender` / `JavaMailSender`:** giao diện gửi thông điệp bằng Spring Mail.
- **Java Platform API — `BlockingQueue` và `LinkedBlockingQueue`:** cơ chế đưa/lấy phần tử và bảo đảm đồng bộ giữa thread.
- **Java Platform API — Records, `List.copyOf` và `String`:** xây dựng dữ liệu snapshot với trường bất biến.
- **Spring Framework — Task Execution and Scheduling:** các ranh giới bất đồng bộ qua executor/`@Async`.
- **Mẫu kiến trúc Transactional Outbox:** lưu sự kiện/yêu cầu gửi cùng giao dịch nghiệp vụ để xử lý bền vững.
