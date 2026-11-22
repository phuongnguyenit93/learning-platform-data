# Tính nguyên tử khi thất bại và nguy cơ thay đổi dở dang trong Java

## 1. Vấn đề: một phương thức có thể ném exception sau khi đã thay đổi dữ liệu

Giả sử một thao tác thêm hàng vào giỏ phải đồng thời cập nhật danh sách sản phẩm và tổng số lượng. Nếu phương thức thêm vào danh sách trước, rồi mới kiểm tra số lượng có hợp lệ hay không, exception sẽ ngắt luồng thực thi giữa chừng. Người gọi nhận được thông báo “thêm thất bại” nhưng giỏ đã chứa một dòng không hợp lệ. Những thao tác sau đó có thể đọc một trạng thái mâu thuẫn, dù exception đã được bắt và chương trình vẫn tiếp tục chạy.

**Tính nguyên tử khi thất bại** (failure atomicity) là cam kết ở cấp độ thao tác: **hoặc thao tác thành công và để lại trạng thái hoàn chỉnh, hoặc thao tác thất bại và trạng thái quan sát được vẫn như trước khi thao tác bắt đầu**. Đây là một mục tiêu thiết kế API quan trọng khi phương thức có thể ném exception trong lúc cập nhật đối tượng.

Để đánh giá một thao tác, cần xác định rõ:

- **Trạng thái trước**: những giá trị và tài nguyên nào được phép thay đổi bởi thao tác?
- **Bất biến** (invariant): điều kiện nào luôn phải đúng, chẳng hạn mọi số lượng đều dương và tổng bằng tổng các dòng?
- **Điểm có thể thất bại**: kiểm tra đầu vào, phép toán tràn số, cấp phát bộ nhớ, callback, ghi tệp, truy vấn dữ liệu, hoặc gọi dịch vụ bên ngoài?
- **Trạng thái sau thất bại**: đối tượng còn hợp lệ hay phải giống hệt trạng thái trước? Hành động bên ngoài có thể quan sát một phần thay đổi hay không?

Một exception **không tự khôi phục** biến, collection, tệp hay dữ liệu đã ghi. Lệnh **catch** chỉ bắt luồng điều khiển; **finally** và try-with-resources xử lý dọn dẹp tài nguyên. Không cơ chế nào trong số đó mặc nhiên đảo ngược mọi thay đổi đã xảy ra.

## 2. Phân biệt những mức bảo đảm an toàn trước exception

Các mức bảo đảm thường dùng để mô tả thao tác thay đổi trạng thái:

| Mức bảo đảm | Khi thao tác ném exception | Ví dụ ý nghĩa |
| --- | --- | --- |
| Không có bảo đảm rõ ràng | Trạng thái có thể không hợp lệ hoặc không còn dùng an toàn | Danh sách đã thêm dòng mới nhưng biến tổng chưa cập nhật |
| **Basic guarantee** | Bất biến được giữ; đối tượng vẫn hợp lệ, nhưng có thể đã thay đổi một phần | Một số mục hợp lệ đã được thêm trước khi thao tác dừng |
| **Strong guarantee / failure atomicity** | Trạng thái thuộc phạm vi cam kết được giữ như trước thao tác | Phép thêm thất bại thì cả danh sách lẫn tổng không đổi |
| **No-throw guarantee** | Thao tác được thiết kế không phát sinh exception trong phạm vi bảo đảm | Một phép gán tham chiếu đã được chuẩn bị sẵn, xét trong điều kiện vận hành thông thường |

**Basic guarantee** đủ cho một số thao tác xử lý tuần tự: nếu thất bại ở bản ghi thứ ba, hai bản ghi đầu có thể đã được xử lý nhưng toàn bộ đối tượng vẫn nhất quán. **Strong guarantee** là yêu cầu mạnh hơn khi API mang nghĩa “thành công toàn bộ hoặc thất bại toàn bộ”.

Không được suy ra mức bảo đảm từ việc phương thức khai báo **throws**, từ loại checked/unchecked exception, hoặc từ việc mã có **try/catch**. Mức bảo đảm phụ thuộc vào thứ tự thay đổi dữ liệu, thiết kế trạng thái và những tác dụng phụ thực sự.

Khái niệm này cũng khác hai nghĩa thường gặp của “atomic”:

- **Atomicity trong concurrency**: các luồng khác có nhìn thấy trạng thái trung gian hay không. Một thao tác có thể được khóa đồng bộ nhưng vẫn để lại dữ liệu dở dang sau exception.
- **Atomicity trong giao dịch lưu trữ**: hệ quản trị cơ sở dữ liệu hoặc cơ chế ghi tệp cung cấp các quy tắc riêng. Một phép gán tham chiếu trong RAM không tự biến hai lần ghi tệp hoặc hai lời gọi HTTP thành một giao dịch.

## 3. Ví dụ Java 17+: thấy rõ trạng thái dở dang và cách khắc phục

Ví dụ sau dùng snapshot bất biến gồm danh sách số lượng và tổng số lượng. Hai phương thức nhận cùng đầu vào nhưng khác thứ tự cập nhật:

- **addBroken** công bố danh sách mới trước rồi mới kiểm tra điều kiện và tính tổng. Khi ném exception, người gọi vẫn nhìn thấy danh sách đã đổi.
- **addSafe** kiểm tra đầu vào, tính toán, xây dựng toàn bộ snapshot mới trước; chỉ khi không có exception mới thay một tham chiếu trạng thái.

Lưu chương trình sau vào tệp **FailureAtomicityDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class FailureAtomicityDemo {
    static final class Cart {
        record Snapshot(List<Integer> quantities, int total) {}

        private volatile Snapshot state =
                new Snapshot(List.of(), 0);

        Snapshot snapshot() {
            return state;
        }

        synchronized void addBroken(int quantity) {
            Snapshot before = state;
            List<Integer> updated = new ArrayList<>(before.quantities());
            updated.add(quantity);

            // Công bố một phần thay đổi quá sớm.
            state = new Snapshot(List.copyOf(updated), before.total());

            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }

            int newTotal = Math.addExact(before.total(), quantity);
            state = new Snapshot(List.copyOf(updated), newTotal);
        }

        synchronized void addSafe(int quantity) {
            // Những bước có thể thất bại đều diễn ra trước commit.
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }

            Snapshot before = state;
            int newTotal = Math.addExact(before.total(), quantity);
            List<Integer> updated = new ArrayList<>(before.quantities());
            updated.add(quantity);
            Snapshot candidate =
                    new Snapshot(List.copyOf(updated), newTotal);

            // Một bước công bố trạng thái hoàn chỉnh.
            state = candidate;
        }
    }

    public static void main(String[] args) {
        Cart broken = new Cart();
        broken.addBroken(2);

        try {
            broken.addBroken(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("Broken rejected: " + e.getMessage());
        }

        System.out.println("Broken: "
                + broken.snapshot().quantities()
                + ", total=" + broken.snapshot().total());

        Cart safe = new Cart();
        safe.addSafe(2);
        Cart.Snapshot beforeFailure = safe.snapshot();

        try {
            safe.addSafe(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("Safe rejected: " + e.getMessage());
        }

        System.out.println("Safe: "
                + safe.snapshot().quantities()
                + ", total=" + safe.snapshot().total());

        if (!beforeFailure.equals(safe.snapshot())) {
            throw new AssertionError("State changed after failure");
        }

        try {
            safe.addSafe(Integer.MAX_VALUE);
        } catch (ArithmeticException e) {
            System.out.println("Overflow rejected: " + e.getMessage());
        }

        System.out.println("After overflow: "
                + safe.snapshot().quantities()
                + ", total=" + safe.snapshot().total());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac FailureAtomicityDemo.java
java FailureAtomicityDemo
~~~

Kết quả chuẩn:

~~~text
Broken rejected: quantity must be positive
Broken: [2, -1], total=2
Safe rejected: quantity must be positive
Safe: [2], total=2
Overflow rejected: integer overflow
After overflow: [2], total=2
~~~

**Vì sao kết quả khác nhau?**

Ở phiên bản lỗi, **state** được thay bằng snapshot có danh sách **[2, -1]** nhưng tổng vẫn bằng **2**. Sau đó điều kiện **quantity <= 0** ném exception, bỏ qua cập nhật tổng cuối cùng. Dữ liệu còn lại vừa chứa số lượng không hợp lệ, vừa không còn thỏa bất biến “tổng bằng tổng các phần tử”.

Ở phiên bản an toàn, nhánh số lượng âm thất bại **trước khi** thay **state**. Nhánh tràn số dùng **Math.addExact**, vì vậy không silently wrap số nguyên và cũng không cập nhật trạng thái. Câu kiểm tra bằng **equals** xác minh snapshot sau exception bằng snapshot trước đó.

Có ba chi tiết thiết kế quan trọng:

1. **List.copyOf** tạo danh sách không thể thay đổi qua API của **List** và từ chối phần tử **null**. Chỉ nên gọi đây là snapshot bất biến sâu nếu chính các phần tử bên trong cũng bất biến; ở đây các phần tử là **Integer**.
2. **volatile** giúp luồng đọc nhìn thấy snapshot đã công bố; **synchronized** tuần tự hóa các lần ghi, tránh hai luồng cùng đọc trạng thái cũ rồi ghi đè mất cập nhật của nhau. Chỉ dùng **volatile** mà bỏ cơ chế phối hợp giữa nhiều writer thì chưa đủ.
3. Việc xây dựng snapshot mới có thể ném exception trước khi gán **state**. Trong phạm vi thao tác trên trạng thái bộ nhớ này, một phép gán tham chiếu cuối cùng là điểm công bố trạng thái hoàn chỉnh. Ví dụ **không** tuyên bố có thể phục hồi từ mọi lỗi nghiêm trọng của VM, như **OutOfMemoryError** xuất hiện ở vị trí bất kỳ.

Ví dụ cố ý giữ hai phương thức trong cùng một class để so sánh; trong API thực tế chỉ nên xuất bản biến thể đáp ứng hợp đồng đã chọn.

## 4. Mẫu thiết kế: chuẩn bị trước, công bố sau

Đối với một aggregate có thể biểu diễn bằng một giá trị trạng thái, cách làm đáng tin cậy là:

1. **Định nghĩa bất biến và phạm vi cam kết**: những trường, collection và quan hệ nào phải đồng thời nhất quán?
2. **Kiểm tra điều kiện tiên quyết** trước đột biến: đối số, quyền, quy tắc nghiệp vụ và khả năng thực hiện.
3. **Tính toán kết quả có thể thất bại**: chẳng hạn **Math.addExact**, parse, chuyển đổi, tạo bản sao, cấp phát collection, ánh xạ dữ liệu.
4. **Tạo bản trạng thái hoàn chỉnh** bằng giá trị cục bộ hoặc đối tượng mới, chưa công bố cho người dùng khác.
5. **Commit tại một điểm rõ ràng**: gán một snapshot đã xây xong, hoặc dùng cơ chế giao dịch phù hợp với dữ liệu.
6. **Quy định hệ quả sau commit**: các callback, thông báo, ghi log, phát sự kiện nếu thất bại thì phương thức sẽ phản ánh thế nào?

Sơ đồ luồng có thể hình dung như sau:

~~~text
Trạng thái S0
    |
    v
Kiểm tra và chuẩn bị ứng viên S1
    |               |
  Lỗi             Thành công
    |               |
    v               v
Giữ S0         Commit S1 một lần
                    |
                    v
                  Kết thúc
~~~

Đừng hiểu “validate trước” là giải pháp toàn năng. Nếu hai phép ghi thật sự độc lập đều có thể thất bại, việc kiểm tra đầu vào sớm vẫn không ngăn lỗi ở phép ghi thứ hai. Khi đó cần thay đổi biểu diễn trạng thái, staging, giao dịch, hoặc một hợp đồng rõ ràng chỉ bảo đảm mức cơ bản.

### Khi một đối tượng chứa nhiều trường phụ thuộc nhau

Với trạng thái như **balance**, **reserved** và **available**, cập nhật từng trường riêng lẻ sẽ tạo khoảng thời gian bất nhất nếu một bước ném exception. Đóng gói chúng vào một record bất biến, xây record mới rồi công bố một tham chiếu giúp tránh những trạng thái phối hợp dở dang trong RAM.

Đối với collection, trình tự **clear → addAll → sửa tổng** vẫn là nhiều bước đột biến. Việc tính xong một collection tạm chưa đủ nếu sau đó lại sao chép nó vào collection công khai bằng nhiều lời gọi có thể lỗi. Cần để trạng thái cũ tồn tại nguyên vẹn đến khi có thể thay bằng tham chiếu trỏ đến collection mới.

### Khi có nhiều writer và reader

Một bản sao được tính từ S0 có thể trở nên cũ trong lúc writer khác đã commit S1. Có thể đồng bộ toàn bộ chuỗi đọc–tính–ghi, hoặc dùng **AtomicReference** và compare-and-set theo vòng lặp khi phù hợp. Với compare-and-set, mọi lần thử phải tính lại từ snapshot đang còn hiệu lực; không chạy tác dụng phụ không thể lặp an toàn ở trong vòng lặp retry. Nếu mỗi lần tính mới gọi một dịch vụ thu phí hay gửi email, một vòng lặp CAS thất bại có thể tạo tác dụng phụ trùng lặp.

Ngược lại, **AtomicInteger**, **volatile** hay **synchronized** không tự bảo đảm rollback khi code bên trong đã sửa dữ liệu trước lúc exception. Chúng giải quyết một số vấn đề quan sát và cạnh tranh giữa luồng, còn failure atomicity đòi hỏi thiết kế đường đi khi lỗi.

## 5. Trường hợp chuyển tiền: hai thay đổi cần cùng cam kết

Giả sử hai số dư **source** và **destination** được quản lý trong cùng một đối tượng. Mã dạng sau có nguy cơ cập nhật dở dang:

~~~java
// Mã minh họa; source và destination là hai trường
// số dư mutable đã được khai báo ở nơi khác.
source -= amount;
destination = Math.addExact(destination, amount);
~~~

Nếu phép cộng tại đích gây **ArithmeticException**, tiền đã bị trừ ở nguồn. Đổi thứ tự hai dòng không giải quyết triệt để; dòng cập nhật thứ hai vẫn có thể thất bại.

Nếu toàn bộ số dư được sở hữu bởi một aggregate trong bộ nhớ, có thể chuẩn bị kết quả dưới dạng một snapshot chung:

~~~java
record Balances(long source, long destination) {}

// Minh họa bên trong phương thức có quyền ghi trạng thái.
// before là snapshot bất biến hiện tại.
if (amount <= 0 || amount > before.source()) {
    throw new IllegalArgumentException("invalid amount");
}

long nextSource = Math.subtractExact(before.source(), amount);
long nextDestination = Math.addExact(before.destination(), amount);
Balances next = new Balances(nextSource, nextDestination);

// Commit: thay một tham chiếu chung từ before sang next;
// cần đồng bộ writer hoặc dùng CAS phù hợp.
balances = next;
~~~

Hai đoạn trên là **mã minh họa theo ngữ cảnh**, không phải chương trình độc lập. Chúng nêu điểm khác biệt về thứ tự thay đổi, không thay thế ví dụ runnable ở mục 3.

Nếu nguồn và đích nằm trong **hai bản ghi cơ sở dữ liệu**, thao tác phải dùng transaction thực sự và có đường rollback thích hợp theo hệ lưu trữ. Nếu chúng nằm ở **hai dịch vụ hoặc hai cơ sở dữ liệu độc lập**, một transaction cục bộ không tạo ra tính nguyên tử toàn cục. Cần thiết kế quy trình phân tán, idempotency, trạng thái chuyển tiếp và xử lý thất bại; những kỹ thuật như saga/compensation có thể phục hồi nghiệp vụ nhưng không đồng nghĩa mọi bên ngoài chưa từng thấy thay đổi trung gian.

## 6. Vì sao rollback thủ công bằng catch có thể vẫn sai?

Mẫu dưới đây trông như đã xử lý lỗi nhưng chưa đủ để khẳng định tính nguyên tử:

~~~java
// Mã minh họa: undo() cũng có thể thất bại.
applyFirstChange();
try {
    applySecondChange();
} catch (RuntimeException failure) {
    undoFirstChange();
    throw failure;
}
~~~

Các tình huống cần xem xét:

- **applyFirstChange** hoàn tất một phần rồi tự ném exception trước khi vào khối **try**; không có nhánh hoàn tác nào chạy.
- **undoFirstChange** có thể ném exception khác, khiến trạng thái chưa được phục hồi và exception gốc bị che khuất.
- Một observer khác đã thấy thay đổi thứ nhất; hoàn tác sau đó không thể xóa trải nghiệm hoặc tác dụng phụ đã quan sát.
- Lời gọi bên ngoài đã gửi email, phát sự kiện hoặc chuyển tiền thật; gọi hàm nghịch đảo không chắc làm mọi thứ như chưa từng xảy ra.

Nếu phải rollback, hãy ghi rõ phạm vi, thứ tự đảo ngược, tình huống rollback thất bại, cách bảo tồn exception gốc và cơ chế phục hồi tiếp theo. Đối với tài nguyên có giao dịch thật, ưu tiên dùng giao dịch của hệ đó. Đối với trạng thái trong bộ nhớ, thường dễ kiểm chứng hơn khi tránh sửa trạng thái hiện hành cho đến khi hoàn tất chuẩn bị.

**finally** và try-with-resources rất cần để đóng stream, trả connection và giải phóng khóa theo hợp đồng. Chúng bảo đảm xử lý vòng đời tài nguyên ở đường thành công/lỗi, **không tự undo** nội dung đã ghi, request đã gửi hay object đã bị sửa.

## 7. Điểm khó thường bị bỏ qua trong API thực tế

### Callback và thông báo sau commit

Giả sử một phương thức cập nhật thành công rồi gọi listener:

~~~java
state = candidate;                 // Đã commit.
listener.onChanged(candidate);     // Có thể ném exception.
~~~

Nếu listener ném lỗi, người gọi nhận exception nhưng trạng thái đã đổi. Phương thức đó **không đáp ứng** lời hứa “bất kỳ exception nào cũng giữ trạng thái cũ”. Có thể chọn một hợp đồng khác: commit thành công, lỗi thông báo được báo/ghi nhận riêng, retry độc lập hoặc qua outbox. Điều cốt yếu là hợp đồng API và đường xử lý phải khớp với thực tế.

Gọi listener **trước commit** cũng chưa chắc an toàn: listener có thể phát sinh tác dụng phụ hoặc giữ tham chiếu đến dữ liệu ứng viên. Hãy phân biệt giai đoạn chuẩn bị thuần túy với các thao tác tạo ra tác dụng phụ bên ngoài.

### Ghi tệp và thay thế dữ liệu

Ghi đè tệp đích trực tiếp có thể để lại nội dung dở dang nếu quá trình ghi lỗi. Một hướng thiết kế là tạo **tệp tạm trong cùng hệ tệp**, ghi đủ dữ liệu, đóng tài nguyên và chỉ sau đó thay thế đường dẫn đích bằng thao tác move nguyên tử **khi hệ tệp hỗ trợ**. Trong Java, **Files.move** với **StandardCopyOption.ATOMIC_MOVE** có thể ném **AtomicMoveNotSupportedException**; phải quyết định có chấp nhận fallback kém bảo đảm hơn hay không. Tính nguyên tử khi đổi tên cũng khác độ bền sau mất điện; để có cam kết durability cần xem xét flush/fsync và hệ tệp cụ thể.

### Database, mạng và sự kiện

- Transaction của database chỉ bảo vệ những thao tác thực sự tham gia transaction theo đúng cơ chế của database. Một request HTTP hay email nằm ngoài transaction ấy.
- Timeout mạng không chứng minh tác vụ từ xa thất bại; máy chủ có thể đã commit nhưng phản hồi bị mất.
- Khi retry một thao tác có tác dụng phụ, hãy xét khóa idempotency, deduplication, trạng thái kết quả và quy tắc retry.
- Không phát thông điệp “thành công” từ trạng thái chưa commit; nếu cần bảo đảm phối hợp giữa dữ liệu và sự kiện, xem xét transactional outbox ở tầng kiến trúc thích hợp.

### Alias, mutable objects và phạm vi snapshot

Danh sách mới nhưng chứa cùng các phần tử mutable vẫn có thể bị thay đổi qua tham chiếu khác. **List.copyOf** chỉ bảo vệ cấu trúc danh sách, không biến mọi object con thành bất biến sâu. Nếu caller nhận trực tiếp mutable object nội bộ, họ có thể sửa dữ liệu mà không đi qua đường commit. Muốn cam kết snapshot đáng tin, cần kiểm soát quyền sở hữu, copy phù hợp hoặc dùng value object bất biến xuyên suốt.

### Loại lỗi nào nằm trong hợp đồng?

Tài liệu API nên xác định các lỗi được bảo đảm xử lý, chẳng hạn **IllegalArgumentException**, **ArithmeticException** hoặc lỗi I/O đã được xét trong thiết kế. Không nên hứa rollback tuyệt đối khi process bị kill, máy mất điện, VM gặp lỗi nghiêm trọng hoặc các hệ bên ngoài không có giao dịch. Có thể áp dụng failure atomicity mạnh trong một phạm vi rất cụ thể, như “snapshot RAM của Cart không đổi khi phương thức addSafe ném exception trước commit”, và một mức bảo đảm khác cho mạng hay storage.

## 8. Cách kiểm thử đường thất bại

Bài kiểm thử phải **chứng minh trạng thái sau lỗi**, thay vì chỉ kiểm tra rằng exception có xảy ra. Một quy trình hữu ích:

1. Thiết lập trạng thái hợp lệ S0 và chụp snapshot đầy đủ những phần thuộc cam kết.
2. Kích hoạt lỗi tại từng điểm có thể thất bại: tham số không hợp lệ, tràn số, bước tính toán, cấp phát, bộ lưu trữ giả lập, callback.
3. Bắt **đúng loại exception dự kiến**, sau đó kiểm tra trạng thái hiện hành so với S0 theo mức bảo đảm đã công bố.
4. Thực hiện thêm một thao tác hợp lệ sau lỗi để chứng minh đối tượng tiếp tục hoạt động đúng.
5. Kiểm thử đồng thời riêng nếu nhiều thread có thể đọc/ghi; kiểm thử failure atomicity tuần tự chưa chứng minh tính linearizable giữa các luồng.

Trong ví dụ runnable, câu **beforeFailure.equals(safe.snapshot())** kiểm tra strong guarantee cho đầu vào âm. Lần gọi với **Integer.MAX_VALUE** xác minh thêm một đường lỗi khác: tràn số số học. Trong dự án thật có thể bổ sung fault injection để ép lỗi ở các dependency; tránh viết mock chỉ để tái khẳng định logic của mock thay vì quan sát trạng thái ứng dụng.

Một bảng kiểm tình huống thường hữu ích hơn chỉ có happy path:

| Điểm thất bại | Kỳ vọng với strong guarantee của aggregate |
| --- | --- |
| Kiểm tra đối số không đạt | Không có thay đổi nào được công bố |
| Tính toán gây tràn số | Snapshot hiện tại giữ nguyên |
| Tạo collection/record mới thất bại trước commit | Snapshot cũ vẫn còn |
| Hai writer cùng cập nhật | Không mất cập nhật; mỗi commit dựa trên trạng thái hợp lệ |
| Callback sau commit thất bại | Phải có hợp đồng riêng; không thể mặc nhiên gọi đây là strong guarantee toàn phương thức |
| Tác vụ storage/network bên ngoài thất bại | Cần đánh giá cơ chế transaction, idempotency và phạm vi cam kết tương ứng |

## 9. Sai lầm phổ biến và cách nhận diện

**“Đã ném exception nghĩa là chưa có gì xảy ra.”** Sai: exception chỉ mô tả luồng thực thi đã rẽ sang đường lỗi. Hãy kiểm tra tất cả thay đổi được thực hiện trước điểm ném lỗi.

**“Bọc synchronized thì thao tác là atomic.”** Khóa có thể chặn các thread khác quan sát trạng thái trung gian khi cùng tuân thủ khóa, nhưng không khôi phục dữ liệu nếu lệnh cuối ném lỗi; sau khi khóa nhả, trạng thái sai có thể lộ ra.

**“Đặt validate ở đầu là đủ.”** Không đủ nếu sau validate còn gọi phép tính, allocator, callback hoặc I/O có thể thất bại sau đột biến.

**“Đã sao chép collection nên chắc chắn atomic.”** Nếu công bố bản sao quá sớm hoặc lại dùng **clear/addAll** để thay collection gốc, thao tác vẫn có nhiều điểm cập nhật.

**“Cứ catch rồi bỏ qua để ứng dụng chạy tiếp.”** Nuốt lỗi khiến trạng thái dở dang khó phát hiện. Chỉ recover khi có kế hoạch thực sự; nếu không, ném lại với ngữ cảnh phù hợp và để tầng chịu trách nhiệm xử lý.

**“Rollback thủ công luôn đưa thế giới về trạng thái cũ.”** Hoàn tác cũng có thể lỗi và không thu hồi những tác dụng phụ mà người khác đã nhìn thấy.

**“Tất cả exception phải bảo đảm không đổi trạng thái.”** Một API có thể cố ý cung cấp basic guarantee hoặc báo trạng thái partial progress. Điều cần thiết là hợp đồng nêu rõ và triển khai nhất quán.

## 10. Áp dụng trong thiết kế phương thức Java

Trước khi viết một phương thức thay đổi trạng thái có nhiều bước, tự trả lời:

- Nếu exception xuất hiện sau từng dòng có khả năng thất bại, dữ liệu đang ở trạng thái nào?
- Những trường nào tạo thành **một bất biến chung**? Có thể lưu chung vào một snapshot bất biến không?
- Các thao tác chuẩn bị có hoàn toàn nội bộ và chưa phát sinh side effect không?
- Có thể tạo một **điểm commit duy nhất** không? Nếu không, cơ chế giao dịch thực sự là gì?
- Khi retry, có nguy cơ chạy lặp một side effect hay mất cập nhật giữa các writer không?
- Khi người gọi nhận exception, tài liệu API hứa “không thay đổi”, “vẫn hợp lệ” hay “có thể hoàn thành một phần”?
- Kiểm thử nào so sánh trạng thái trước–sau, kể cả đường tràn số, I/O và cạnh tranh giữa luồng?

**Điểm cần ghi nhớ:** Failure atomicity là bảo đảm về **trạng thái có thể quan sát sau khi một thao tác thất bại**, không phải đặc tính tự động của exception handling. Với dữ liệu trong bộ nhớ, cách tiếp cận dễ kiểm chứng là **kiểm tra → tính toán và xây trạng thái ứng viên → commit một lần**. Khi thao tác đi qua database, file hoặc dịch vụ bên ngoài, phải xác định lại phạm vi cam kết và sử dụng cơ chế giao dịch/phục hồi tương ứng.