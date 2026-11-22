# Duy trì trạng thái hợp lệ trong lớp trừu tượng (Java)

Một đối tượng có **trạng thái hợp lệ** khi các giá trị của nó đáp ứng quy tắc thiết kế. **Bất biến (invariant)** là những điều kiện phải đúng sau khi constructor khởi tạo thành công và sau mỗi thao tác công khai hoàn tất bình thường.

Ví dụ, một đặt chỗ có thể yêu cầu mã tham chiếu không rỗng, số chỗ còn lại không âm, và mỗi yêu cầu đặt phải có số lượng dương không vượt quá sức chứa còn lại. Nếu trạng thái trở nên sai, những phương thức sau đó có thể tiếp tục tính toán dựa trên dữ liệu không đáng tin cậy.

Abstract class có constructor, trường và phương thức bình thường; nó chỉ không cho phép tạo thể hiện trực tiếp bằng new. Khi tạo lớp con cụ thể, phần trạng thái của superclass vẫn nằm trong đối tượng. Vì vậy, **abstract class nên tự bảo vệ các invariant chung mà nó sở hữu**.

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| Precondition | Caller được phép truyền giá trị nào? |
| Invariant | Trạng thái nào phải luôn đúng? |
| Postcondition | Sau thao tác thành công, kết quả phải ra sao? |
| Encapsulation | Ai được đọc hoặc sửa trạng thái và qua API nào? |

## 1. Kiểm tra ở constructor và mọi điểm cập nhật

Constructor là nơi phù hợp để xác thực dữ liệu bắt buộc và khởi tạo trường do lớp quản lý. Nếu tham số vi phạm hợp đồng, hãy ném exception rõ ràng thay vì tạo một đối tượng đã sai ngay từ đầu.

Tuy nhiên, **constructor chỉ bảo vệ điểm bắt đầu**. Mọi phương thức thay đổi trạng thái cũng phải duy trì invariant. Nếu chỉ kiểm tra lúc tạo nhưng sau đó cho phép gán số chỗ âm, đối tượng vẫn có thể trở nên sai.

- Dùng IllegalArgumentException cho giá trị không thỏa điều kiện nghiệp vụ.
- Dùng Objects.requireNonNull khi một tham chiếu bắt buộc khác null và thông báo NullPointerException là phù hợp.
- Constructor protected thường phù hợp cho abstract superclass chỉ được khởi tạo thông qua lớp con.
- Tránh công bố this qua callback hoặc registry trước khi đối tượng hoàn tất khởi tạo.

## 2. Ví dụ chạy được: đặt chỗ với invariant

Lưu vào **ReservationDemo.java**:

~~~java
abstract class Reservation {
    private final String reference;
    private int available;

    protected Reservation(String reference, int available) {
        if (reference == null || reference.isBlank()) {
            throw new IllegalArgumentException(
                    "reference must not be blank");
        }
        if (available < 0) {
            throw new IllegalArgumentException(
                    "available must be non-negative");
        }
        this.reference = reference;
        this.available = available;
    }

    public final String reference() {
        return reference;
    }

    public final int available() {
        return available;
    }

    public final void reserve(int count) {
        if (count <= 0) {
            throw new IllegalArgumentException(
                    "count must be positive");
        }
        if (count > available) {
            throw new IllegalStateException("not enough seats");
        }
        available -= count;
    }

    protected abstract String type();

    public final String description() {
        return type() + " " + reference + ": "
                + available + " seats";
    }
}

final class ConferenceReservation extends Reservation {
    ConferenceReservation(String reference, int available) {
        super(reference, available);
    }

    @Override
    protected String type() {
        return "Conference";
    }
}

public class ReservationDemo {
    public static void main(String[] args) {
        Reservation reservation =
                new ConferenceReservation("EV-24", 5);

        System.out.println(reservation.description());
        reservation.reserve(2);
        System.out.println(reservation.description());

        try {
            reservation.reserve(4);
        } catch (IllegalStateException error) {
            System.out.println("Rejected: " + error.getMessage());
        }
        System.out.println("Remaining: " + reservation.available());

        try {
            new ConferenceReservation(" ", 3);
        } catch (IllegalArgumentException error) {
            System.out.println("Invalid: " + error.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac ReservationDemo.java
java ReservationDemo
~~~

Stdout:

~~~text
Conference EV-24: 5 seats
Conference EV-24: 3 seats
Rejected: not enough seats
Remaining: 3
Invalid: reference must not be blank
~~~

Constructor Reservation xác thực mã và số chỗ trước khi lưu. reserve kiểm tra count và sức chứa **trước khi trừ**, nên yêu cầu thất bại không để lại số chỗ âm. Biến tham chiếu có kiểu Reservation nhưng đối tượng thực tế là ConferenceReservation; abstract class vẫn có thể làm kiểu tham chiếu.

## 3. Đóng gói để bảo vệ trạng thái

Nếu available là protected, lớp con có thể gán available = -99 và phá invariant mà không đi qua reserve. Hãy giữ trường mutable là private và cung cấp hành vi có ý nghĩa nghiệp vụ thay vì setter tùy ý.

- **Sở hữu dữ liệu rõ ràng:** không trả trực tiếp tham chiếu đến cấu trúc mutable nội bộ nếu caller có thể sửa nó.
- **Kiểm tra trước khi sửa:** xác thực đầu vào và trạng thái hiện tại, rồi mới cập nhật.
- **Hạn chế điểm mở rộng:** dùng final cho phương thức bảo vệ invariant khi lớp con không được phép thay đổi quy tắc đó.
- **Đừng nhầm final với thread-safe:** final ngăn override hoặc gán lại theo quy tắc Java, nhưng không tự làm thao tác nhiều bước trở thành nguyên tử.

Với trường tham chiếu mutable, có thể cần defensive copy. Ví dụ dưới đây minh họa danh sách nhãn:

~~~java
import java.util.List;

abstract class TaggedResource {
    private final List<String> tags;

    protected TaggedResource(List<String> tags) {
        this.tags = List.copyOf(tags);
    }

    public final List<String> tags() {
        return tags;
    }
}
~~~

List.copyOf từ chối danh sách null hoặc phần tử null và cung cấp danh sách không thể sửa qua API List. Vì String bất biến, đây là cách bảo vệ phù hợp cho các nhãn. Với phần tử mutable, đây vẫn là bản sao nông; cần xem có phải sao chép từng phần tử hay dùng kiểu bất biến không.

## 4. Phối hợp invariant giữa superclass và subclass

Invariant của toàn đối tượng là tổng hợp quy tắc cho cả trạng thái cha và trạng thái con. Constructor cha xác thực dữ liệu cha sở hữu; constructor con xác thực dữ liệu riêng sau khi gọi super(...). Lớp con phải giữ hợp đồng quan sát được từ lớp cha và không mở đường cập nhật trái với quy tắc chung.

Ví dụ, nếu lớp con yêu cầu số chỗ luôn lớn hơn 0, kiểm tra điều kiện đó chỉ trong constructor con là chưa đủ: một lần gọi reserve tiếp theo có thể đưa số chỗ về 0. Mọi API thay đổi trạng thái liên quan phải bảo vệ cùng invariant. Đây là khác biệt giữa **hợp lệ khi mới tạo** và **hợp lệ suốt vòng đời**.

Cũng cần cẩn thận khi superclass gọi phương thức overridable trong constructor: phương thức con có thể chạy trước khi trường con được khởi tạo. Hãy giữ constructor tập trung vào tham số và trạng thái mà chính nó kiểm soát; bài về rủi ro gọi phương thức override trong constructor phân tích trường hợp này chi tiết hơn.

## 5. Giới hạn khi có nhiều luồng

Ví dụ Reservation bảo vệ invariant trong luồng gọi tuần tự. Nếu hai luồng cùng gọi reserve, bước kiểm tra available và bước trừ không tự động trở thành một thao tác nguyên tử. Muốn hỗ trợ nhiều luồng, cần đồng bộ hóa phù hợp như khóa hoặc thiết kế concurrency khác, kèm kiểm thử đúng. Một phương thức final không tự đồng nghĩa với thread-safe.

## 6. Kiểm thử và lỗi thường gặp

| Ca kiểm tra | Kết quả mong đợi |
| --- | --- |
| Mã null, rỗng hoặc chỉ khoảng trắng | Từ chối |
| available âm | Từ chối |
| available bằng 0 với mã hợp lệ | Chấp nhận theo hợp đồng ví dụ |
| reserve(0) hoặc reserve(-1) | Từ chối, giữ trạng thái cũ |
| Đặt nhiều hơn số chỗ còn lại | Từ chối, giữ trạng thái cũ |
| Đặt số lượng hợp lệ | Giảm đúng lượng, không âm |
| Lớp con truy cập trực tiếp available | Lỗi biên dịch vì trường private |
| Nhiều luồng đặt chỗ đồng thời | Chỉ tuyên bố an toàn khi cơ chế đồng bộ đã được kiểm chứng |

Lỗi thường gặp là chỉ xác thực setter mà quên constructor; chỉ xác thực constructor mà quên phương thức cập nhật; dùng assert cho dữ liệu nghiệp vụ; để trường mutable protected; hoặc thay đổi nhiều trường trước khi kiểm tra xong khiến đối tượng ở trạng thái nửa chừng khi có exception.

**Ghi nhớ:** abstract class là nơi thích hợp để thiết lập invariant chung của một họ lớp. Constructor xác nhận điểm bắt đầu; đóng gói, API cập nhật có kiểm tra và kiểm soát điểm mở rộng giữ cho trạng thái hợp lệ về sau.