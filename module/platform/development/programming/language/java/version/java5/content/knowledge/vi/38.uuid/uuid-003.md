# Tạo UUID ngẫu nhiên bằng randomUUID

Khi tạo một đơn hàng, yêu cầu hỗ trợ hoặc sự kiện, ứng dụng thường cần cấp định danh ngay trước khi lưu dữ liệu. Nếu nhiều tiến trình cùng hoạt động, một biến đếm cục bộ như `1, 2, 3...` không đủ để tránh cấp trùng giữa các tiến trình.

`UUID.randomUUID()` cung cấp một cách tạo định danh ngẫu nhiên ngay trong thư viện chuẩn Java. Bài này tập trung vào cách gọi phương thức, hiểu kết quả, dùng định danh đúng vòng đời và kiểm tra mã có nguồn ngẫu nhiên.

## 1. randomUUID tạo ra điều gì?

`UUID` là giá trị định danh 128 bit. Phương thức `UUID.randomUUID()`:

- Là phương thức `static`, không nhận tham số.
- Trả về đối tượng `java.util.UUID` phiên bản 4.
- Dùng bộ sinh số giả ngẫu nhiên mạnh về mật mã.
- Có thể gọi trực tiếp mà không cần tạo một đối tượng `UUID` trước.

API này có từ Java 5 và vẫn được cung cấp trong Java hiện đại. Các ví dụ của bài dùng Java 17 trở lên. Xem hợp đồng của [UUID.randomUUID](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/UUID.html#randomUUID()).

Cách dùng trong một phương thức:

```java
// Đoạn mã, đặt bên trong một phương thức; cần import java.util.UUID.
UUID id = UUID.randomUUID();
String text = id.toString();
System.out.println(text);
```

Một chuỗi có thể trông như sau:

```text
3a81c720-4d56-4bd7-a821-513f6248a9c0
```

Đây là **giá trị minh họa**, không phải stdout cố định phải xuất hiện khi chạy. Một lần gọi khác có thể tạo giá trị khác; không viết kiểm tra kỳ vọng phương thức luôn trả đúng chuỗi trên.

### Dạng văn bản và giá trị bên trong

Chuỗi thông thường có 36 ký tự: 32 chữ số hệ 16 và 4 dấu gạch ngang, chia nhóm theo dạng `8-4-4-4-12`. Các dấu gạch ngang chỉ phục vụ trình bày; UUID vẫn chứa 128 bit dữ liệu.

Với UUID phiên bản 4 theo bố cục chuẩn:

```text
xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
```

`4` đánh dấu phiên bản; `y` thuộc `8, 9, a, b` do hai bit bố cục được cố định. Còn lại **122 bit** dành cho tính ngẫu nhiên. Đặc tả hiện đại của UUID là [RFC 9562, mục 5.4](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.4); nó tiếp tục định nghĩa UUIDv4.

Không cần tự ghép chuỗi theo mẫu này. Một chuỗi có ký tự `4` ở đúng vị trí chưa chứng minh các bit khác được tạo ngẫu nhiên tốt.

## 2. Khi nào nên tạo một UUID mới?

Hãy gắn việc tạo UUID với **sự ra đời của một đối tượng nghiệp vụ**, không gắn với mọi lần đọc định danh.

Ví dụ, một phiếu hỗ trợ được tạo một lần rồi có thể được đọc nhiều lần:

```text
Nhận yêu cầu tạo phiếu
        |
        v
Sinh UUID một lần
        |
        v
Lưu UUID cùng phiếu
        |
        v
Mọi lần đọc sau trả lại UUID đã lưu
```

Nếu phương thức lấy id gọi `randomUUID()` mỗi lần, cùng một phiếu sẽ có nhiều “định danh” khác nhau. Khi đó liên kết, nhật ký và dữ liệu tham chiếu không còn cùng trỏ tới một giá trị.

Một ví dụ sai về vòng đời:

```java
// Đoạn minh họa lỗi thiết kế, không phải chương trình độc lập.
public UUID getId() {
    return UUID.randomUUID();
}
```

Ở thiết kế đúng, phương thức đọc chỉ trả trường `id` đã được gán lúc tạo. Nếu dữ liệu đã được lưu, khi nạp lại phải phục hồi UUID đã lưu, không cấp UUID mới.

### Dùng UUID ở ranh giới nào?

| Ranh giới | Cách dùng |
| --- | --- |
| Bên trong mô hình Java | Giữ kiểu `UUID` để thể hiện ý nghĩa định danh |
| Trong URL hoặc thông điệp văn bản | Dùng `toString()` |
| Nhận lại UUID đã có | Phân tích chuỗi thành `UUID`, không sinh mới |
| So sánh hai định danh | Dùng `equals` hoặc `Objects.equals` |
| Tạo thực thể mới | Gọi `randomUUID()` đúng một lần theo vòng đời |

Việc UUID không mang ý nghĩa nghiệp vụ cũng hữu ích: không cần nhúng tên khách hàng, số điện thoại hoặc tên máy vào định danh.

## 3. Chương trình hoàn chỉnh: tạo, giữ và kiểm tra định danh

Lưu thành **RandomUuidDemo.java**:

```java
import java.util.Objects;
import java.util.UUID;
import java.util.function.Supplier;

public class RandomUuidDemo {
    record Ticket(UUID id, String subject) {
        Ticket {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(subject, "subject");
        }
    }

    static final class TicketService {
        private final Supplier<UUID> idSource;

        TicketService(Supplier<UUID> idSource) {
            this.idSource = Objects.requireNonNull(idSource, "idSource");
        }

        Ticket create(String subject) {
            UUID id = Objects.requireNonNull(idSource.get(), "generated id");
            return new Ticket(id, subject);
        }
    }

    public static void main(String[] args) {
        TicketService service = new TicketService(UUID::randomUUID);
        Ticket ticket = service.create("Cannot sign in");

        UUID id = ticket.id();
        String text = id.toString();
        UUID restored = UUID.fromString(text);

        System.out.println("version = " + id.version());
        System.out.println("variant = " + id.variant());
        System.out.println("text length = " + text.length());
        System.out.println("same value after parsing = " + id.equals(restored));
        System.out.println("id remains stable = " + id.equals(ticket.id()));

        UUID fixture = UUID.fromString(
                "3a81c720-4d56-4bd7-a821-513f6248a9c0");
        TicketService testService = new TicketService(() -> fixture);
        Ticket testTicket = testService.create("Example");
        System.out.println("test id = " + testTicket.id());
        System.out.println("test uses supplied id = "
                + fixture.equals(testTicket.id()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 RandomUuidDemo.java
java RandomUuidDemo
```

Stdout:

```text
version = 4
variant = 2
text length = 36
same value after parsing = true
id remains stable = true
test id = 3a81c720-4d56-4bd7-a821-513f6248a9c0
test uses supplied id = true
```

Chương trình thực sự tạo UUID ngẫu nhiên cho phiếu đầu tiên nhưng không in chính giá trị thay đổi đó, nên stdout trên ổn định. Phần cuối dùng một giá trị cố định được truyền vào để kiểm tra việc dịch vụ sử dụng đúng nguồn cấp id.

Giá trị `variant = 2` là mã Java dùng cho bố cục UUID chuẩn tương ứng. Không nhầm nó với phiên bản: kết quả của `randomUUID()` có `version() = 4`.

### Vì sao dùng Supplier trong ví dụ?

`Supplier<UUID>` là một nguồn có thể cấp UUID khi gọi `get()`. Trong ứng dụng, truyền `UUID::randomUUID`; khi kiểm tra, truyền `() -> fixture`.

Nhờ đó có thể kiểm tra riêng hai trách nhiệm:

1. Mã tạo phiếu có lấy id từ nguồn được cung cấp và lưu lại đúng không?
2. UUID được thư viện tạo có đúng phiên bản, bố cục và biểu diễn kỳ vọng không?

Không cần điều khiển hạt giống ngẫu nhiên của `randomUUID()`, cũng không cần thay đổi cấu hình toàn cục để kiểm tra dịch vụ. Đối với đoạn mã rất nhỏ chỉ cần tạo một id, có thể gọi trực tiếp; việc truyền nguồn cấp id hữu ích khi sự ngẫu nhiên làm kiểm tra nghiệp vụ khó lặp lại.

Giá trị cố định trong ví dụ chỉ phục vụ một tình huống kiểm tra. Nếu nguồn cấp luôn trả cùng một UUID trong ứng dụng thật, mọi phiếu sẽ trùng id.

## 4. “Duy nhất” có phải là bảo đảm toán học tuyệt đối?

Không. Tập giá trị hữu hạn vẫn có khả năng trùng. Với UUIDv4 được tạo độc lập và phân bố đều trên 122 bit ngẫu nhiên, số khả năng là:

```text
N = 2^122
```

Sau n lần tạo, khi xác suất va chạm còn nhỏ, có thể ước lượng theo bài toán ngày sinh:

```text
P(có ít nhất một cặp trùng) ≈ n(n - 1) / (2 × 2^122)
```

Chẳng hạn với một tỷ UUID, phép ước lượng cho khoảng `9,4 × 10^-20`. Con số này dựa trên giả định chất lượng nguồn ngẫu nhiên và tính độc lập, không thay thế tính đúng đắn của hệ thống.

Các lỗi ứng dụng thực tế có thể gây trùng dễ hơn rất nhiều: dùng nhầm một hằng số làm id, sao chép bản ghi cùng khóa, hoặc tái sử dụng dữ liệu kiểm tra.

Vì vậy, nếu UUID làm khóa của dữ liệu cần duy nhất:

- Vẫn đặt ràng buộc khóa chính hoặc duy nhất tại nơi lưu trữ.
- Để nơi lưu trữ quyết định xung đột một cách nguyên tử.
- Phân biệt trùng khóa kỹ thuật với trùng một giao dịch nghiệp vụ.

Không làm theo kiểu “kiểm tra chưa tồn tại rồi mới chèn” và coi thế là đủ: hai tiến trình vẫn có thể cùng kiểm tra trước khi một tiến trình chèn thành công.

Nếu hệ thống quyết định thử tạo lại id sau xung đột, cần giới hạn số lần và xử lý đúng lỗi trùng khóa. Không thử vô hạn và không đổi id tùy tiện nếu nó đã được gửi ra ngoài hoặc đã được tham chiếu.

## 5. UUID mới không giải quyết việc gửi lặp yêu cầu

Giả sử người dùng gửi yêu cầu tạo phiếu, mạng bị ngắt sau khi máy chủ đã lưu. Nếu gửi lại cùng thao tác và máy chủ sinh một UUID khác, hệ thống có thể tạo hai phiếu hợp lệ về khóa nhưng trùng ý nghĩa nghiệp vụ.

```text
Lần gửi 1 -> UUID A -> đã lưu
Lần gửi 2 -> UUID B -> cũng lưu
```

A khác B không chứng minh đây là hai yêu cầu nghiệp vụ khác nhau.

Khi cần chống xử lý lặp, phải có chính sách riêng, chẳng hạn một khóa chống xử lý lặp được giữ ổn định cho các lần thử lại của cùng thao tác. Khóa đó có thể mang dạng UUID, nhưng giá trị quan trọng là **được tái sử dụng đúng**, không phải gọi `randomUUID()` lại sau mỗi lần thử.

Định danh thực thể và khóa chống xử lý lặp có thể là hai trường khác nhau. Chọn theo hợp đồng của thao tác.

## 6. Những điều randomUUID không cung cấp

### Không chứa thời điểm tạo để suy ra thứ tự

UUIDv4 không phải số thứ tự tăng dần. Không dùng so sánh hai UUID ngẫu nhiên để kết luận đối tượng nào được tạo trước.

Nếu cần ngày giờ tạo, lưu một trường thời gian riêng. Nếu yêu cầu đặc biệt là định danh sắp theo thời gian, cần lựa chọn thiết kế phù hợp; thay vì đổi ý nghĩa của `randomUUID()`, hãy đánh giá loại định danh khác. Việc có các phiên bản UUID mới không khiến UUIDv4 tự trở thành API lỗi thời.

### Không thay thế phân quyền

Đường dẫn `/tickets/{uuid}` vẫn cần kiểm tra người gọi có quyền xem phiếu không. Một người biết UUID từ nhật ký, liên kết được chia sẻ hoặc thông điệp khác không vì thế được cấp quyền truy cập.

Nguồn ngẫu nhiên mạnh giúp hạn chế khả năng đoán id, nhưng định danh và quyền truy cập là hai trách nhiệm khác nhau. Với chức năng cấp quyền qua một mã bí mật, cần thiết kế vòng đời, hết hạn, thu hồi và bảo vệ riêng; không coi việc chuỗi trông ngẫu nhiên là đủ.

### Không cung cấp khả năng khôi phục dữ liệu nghiệp vụ

Không thể “giải mã” UUIDv4 để lấy tên người dùng, nội dung phiếu hoặc ngày tạo. Phải lưu và tra cứu các thông tin đó bằng chính dữ liệu ứng dụng.

### Không phải giá trị ngẫu nhiên có thể cắt tùy ý

Lấy một đoạn chuỗi UUID, chỉ giữ một nửa 64 bit hoặc lấy `hashCode()` đều thu hẹp không gian định danh và làm thay đổi nguy cơ trùng. `hashCode()` phục vụ cấu trúc băm, không phải UUID rút gọn duy nhất.

Nếu giao diện muốn hiển thị một phần id cho dễ đọc, giữ đầy đủ UUID ở dữ liệu nền và không giả định phần hiển thị đó đủ để nhận diện duy nhất.

## 7. Lỗi thường gặp

| Lỗi | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Viết `new UUID(0L, 0L)` rồi tưởng đã sinh ngẫu nhiên | Hai số truyền vào xác định toàn bộ giá trị | Dùng `UUID.randomUUID()` để tạo mới |
| Sinh UUID trong phương thức đọc id | Mỗi lần đọc có thể nhận giá trị khác | Gán một lần rồi lưu lại |
| Gọi `randomUUID()` để “phục hồi” một id nhận qua URL | Tạo định danh khác với định danh được gửi | Phân tích giá trị đã nhận |
| Dùng `==` để so hai đối tượng UUID | So tham chiếu thay vì giá trị | Dùng `equals` |
| Khẳng định hai lần gọi chắc chắn khác nhau | Bỏ qua khả năng va chạm | Kiểm tra hợp đồng và ràng buộc duy nhất |
| Kiểm tra một chuỗi UUID cố định từ nguồn ngẫu nhiên | Kết quả không được cố định | Truyền nguồn cấp id khi cần kiểm tra xác định |
| Sinh id mới cho mọi lần thử lại | Không chống xử lý lặp nghiệp vụ | Giữ khóa chống xử lý lặp của cùng thao tác |
| Dùng UUID như bằng chứng quyền truy cập | Biết định danh không đồng nghĩa được phép | Kiểm tra quyền theo tài nguyên |

Một đợt thử tạo hàng nghìn UUID mà không trùng chỉ là quan sát của đợt thử đó. Nó không chứng minh không thể trùng trong tương lai và không đánh giá đầy đủ chất lượng mật mã của nguồn ngẫu nhiên.

Khi cần tạo UUID với tần suất lớn, đo trong môi trường thực tế trước khi tối ưu. Không tự thay nguồn của thư viện bằng `Random`, thời gian hệ thống hoặc phép nối chuỗi chỉ vì muốn mã ngắn hơn.

## 8. Thực hành

1. Thêm một trường `createdAt` vào phiếu thay vì cố suy thời gian từ UUIDv4.
2. Viết kiểm tra cho `TicketService` bằng một `Supplier` trả UUID đã biết. Kiểm tra id được lưu, không kiểm tra một chuỗi kỳ vọng từ nguồn ngẫu nhiên.
3. Mô phỏng hai lần thử lại cùng một yêu cầu tạo phiếu. Chỉ ra vì sao hai UUID khác nhau chưa ngăn được tạo trùng nghiệp vụ.
4. Giải thích vì sao `UUID.fromString(id.toString())` có cùng giá trị với `id`, còn `UUID.randomUUID()` không phải cách chuyển chuỗi trở lại.
5. Xác định nơi cần ràng buộc duy nhất nếu nhiều tiến trình cùng lưu phiếu.

Điểm cần đạt: biết **khi nào tạo**, **lưu giá trị ở đâu**, **so sánh bằng gì**, **kiểm tra tính ngẫu nhiên thế nào**, và **trách nhiệm nào cần xử lý ngoài việc sinh id**.
