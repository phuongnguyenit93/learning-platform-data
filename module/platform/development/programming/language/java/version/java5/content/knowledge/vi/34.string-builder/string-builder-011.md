# StringBuilder: phạm vi sử dụng trong một luồng và rủi ro chia sẻ

`StringBuilder` là vùng làm việc có thể thay đổi để ghép văn bản. Cách dùng dễ kiểm soát nhất là để một lần xử lý sở hữu builder, hoàn tất việc ghép rồi trả về `String`. Khi nhiều luồng cùng truy cập một builder và có luồng đang sửa, bạn cần một cơ chế phối hợp rõ ràng.

`StringBuilder` không tự bảo đảm đồng bộ hóa khi dùng từ nhiều luồng. Đây vẫn là đặc điểm của API Java hiện hành. [Tài liệu StringBuilder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html)

## 1. “Dùng trong một luồng” nói về đối tượng

Điều quan trọng là **có những ai truy cập cùng một đối tượng builder**, không phải ứng dụng có tổng cộng bao nhiêu luồng.

Ví dụ, máy chủ có thể xử lý nhiều yêu cầu đồng thời mà vẫn dùng `StringBuilder` an toàn nếu mỗi lần gọi phương thức tạo builder riêng và không đưa nó ra ngoài:

```java
static String describe(int id) {
    StringBuilder text = new StringBuilder();
    text.append("item=").append(id);
    return text.toString();
}
```

Đây là đoạn phương thức minh họa, đặt trong một lớp khi sử dụng.

Hai lần gọi `describe(1)` và `describe(2)` tạo hai builder khác nhau. Chúng không tranh chấp cùng nội dung.

Cần phân biệt:

| Tình huống | Đánh giá |
| --- | --- |
| Builder cục bộ, chỉ được dùng trong lần gọi hiện tại | Dễ kiểm soát quyền sở hữu |
| Nhiều luồng, mỗi luồng hoặc tác vụ có builder riêng | Không chia sẻ trạng thái builder |
| Builder cục bộ nhưng bị lambda giữ lại và chuyển cho nhiều tác vụ | Đã có thể trở thành đối tượng dùng chung |
| Builder nằm trong trường của một đối tượng dùng chung | Cần kiểm tra mọi đường truy cập |
| Một luồng sửa builder, luồng khác gọi `toString()` | Vẫn là truy cập đồng thời, cần phối hợp |
| Chuyển quyền sở hữu sang luồng khác, bên cũ ngừng sử dụng | Cần cơ chế chuyển giao bảo đảm khả năng nhìn thấy dữ liệu |

Biến cục bộ không tự làm đối tượng an toàn nếu tham chiếu tới nó đã thoát ra ngoài phạm vi.

## 2. Vì sao dùng chung có rủi ro?

Một thao tác ghép phải phối hợp vị trí ghi, độ dài và vùng chứa dữ liệu. Nếu hai luồng cùng thay đổi một builder mà không phối hợp, chương trình không được bảo đảm rằng mỗi thao tác sẽ diễn ra như một bước độc lập.

Một cách hình dung khả năng mất cập nhật:

```text
Builder đang có độ dài n.
Luồng A chuẩn bị thêm dữ liệu dựa trên trạng thái cũ.
Luồng B cũng chuẩn bị thêm dữ liệu dựa trên trạng thái cũ.
Các bước thực hiện xen kẽ, kết quả không còn tuân theo ý định ghép.
```

Đây là mô hình giải thích tranh chấp, không phải mô tả cố định mã nội bộ của mọi JDK.

Hậu quả có thể là thiếu dữ liệu, nội dung không đúng, thứ tự ngoài dự kiến hoặc lỗi khi thực thi. Không có một stdout hay ngoại lệ duy nhất bắt buộc xuất hiện. Chạy thử nhiều lần mà “vẫn đúng” không chứng minh thiết kế an toàn.

Java gọi trường hợp các truy cập xung đột giữa luồng không được sắp thứ tự phù hợp bằng quan hệ `happens-before` là tranh chấp dữ liệu (data race). Quan hệ này còn quyết định khả năng một luồng nhìn thấy kết quả ghi của luồng khác. [JLS: Happens-before Order](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

## 3. Ví dụ sai: trường dùng chung trong bộ định dạng

Đoạn sau chỉ minh họa thiết kế có lỗi; không có kết quả chạy cố định:

```java
class UnsafeFormatter {
    private final StringBuilder text = new StringBuilder();

    String format(int id) {
        text.setLength(0);
        text.append("item=").append(id);
        return text.toString();
    }
}
```

Nếu một `UnsafeFormatter` được nhiều luồng gọi, có thể xảy ra:

1. A bắt đầu ghép dữ liệu cho id 1.
2. B xóa nội dung bằng `setLength(0)`.
3. A tiếp tục ghép hoặc đọc kết quả từ trạng thái mà B đã sửa.

Trường `final` chỉ ngăn gán lại tham chiếu `text` sau khởi tạo; nó không cấm sửa nội dung builder. Đổi trường này sang `static final` còn khiến nhiều đối tượng dùng chung một builder.

Tương tự, khai báo tham chiếu `volatile StringBuilder` không làm các thao tác trên nội dung trở nên nguyên tử. `volatile` có ý nghĩa đối với việc công bố và đọc/ghi tham chiếu, nhưng không tự bao bọc toàn bộ quá trình `setLength → append → toString`. [JLS: mô hình bộ nhớ và đồng bộ hóa](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4)

Với bộ định dạng này, cách sửa đơn giản là bỏ trường builder và dùng biến cục bộ trong `format`.

## 4. Cách ưu tiên: mỗi tác vụ tạo builder riêng, trả về String

Chương trình dưới đây có hai tác vụ chạy trên nhóm luồng. Mỗi tác vụ ghép chuỗi của mình rồi trả về `String`. Luồng chính nhận kết quả qua `Future.get()`.

Lưu thành **BuilderConfinementDemo.java**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BuilderConfinementDemo {
    private static String render(int id) {
        StringBuilder text = new StringBuilder();
        text.append("item=").append(id);
        text.append(", square=").append(id * id);
        return text.toString();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> first = pool.submit(() -> render(3));
            Future<String> second = pool.submit(() -> render(4));

            StringBuilder report = new StringBuilder();
            report.append(first.get()).append(System.lineSeparator());
            report.append(second.get());
            System.out.println(report);
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 BuilderConfinementDemo.java
java BuilderConfinementDemo
```

Stdout:

```text
item=3, square=9
item=4, square=16
```

Ba điểm cần đọc đúng:

- `render` tạo builder mới cho mỗi lần gọi; hai tác vụ không sửa cùng builder.
- `report` chỉ được luồng chính sử dụng, dù nó nhận dữ liệu do tác vụ khác tạo.
- Thứ tự hiển thị do luồng chính ghép `first` rồi `second`. Tác vụ nào hoàn thành trước không quyết định thứ tự này.

`Future.get()` vừa đợi lấy kết quả vừa có bảo đảm bộ nhớ: các hành động của tác vụ xảy ra trước những hành động sau lần `get()` tương ứng ở luồng nhận. [Tài liệu Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)

Builder trong tác vụ không còn bị bên khác đọc khi đang sửa. Kết quả được chuyển đi là `String` bất biến. Bản thân việc gọi `toString()` trên một builder đang bị luồng khác sửa không thay thế cơ chế đồng bộ hóa.

## 5. Khi thật sự cần một builder dùng chung

Có tình huống nhiều luồng cần góp dữ liệu vào cùng vùng chứa. Khi dùng builder trong trường hợp này, hãy che giấu nó sau một giao diện nhỏ và bảo vệ **mọi đường đọc lẫn ghi** bằng cùng một khóa.

Lớp dưới đây biên dịch độc lập nhưng không có `main`:

```java
public final class SharedText {
    private final Object lock = new Object();
    private final StringBuilder text = new StringBuilder();

    public void appendRecord(String name, int value) {
        synchronized (lock) {
            text.append(name).append('=').append(value).append(';');
        }
    }

    public String snapshot() {
        synchronized (lock) {
            return text.toString();
        }
    }
}
```

Các ranh giới trong thiết kế này có mục đích cụ thể:

- Khóa bao phủ **cả bản ghi** như `A=1;`, nên các bước ghép của bản ghi không xen lẫn với bản ghi khác.
- `snapshot()` lấy cùng khóa để không đọc giữa lúc một bản ghi đang được sửa.
- Builder và khóa là `private`; bên gọi không nhận tham chiếu builder để sửa ngoài quy ước.
- Đầu vào `name` là `String` nên không có một nguồn văn bản có thể thay đổi cần được bảo vệ thêm.

Việc nhả khóa trên một monitor xảy ra trước lần lấy khóa tiếp theo trên cùng monitor. Vì vậy cùng một khóa cung cấp cả loại trừ truy cập và bảo đảm nhìn thấy dữ liệu. [JLS: quy tắc monitor](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

Thiết kế này bảo vệ tính toàn vẹn của từng bản ghi, **không ấn định thứ tự bản ghi giữa các luồng**. Thứ tự phụ thuộc luồng nào lấy khóa trước. Nếu cần thứ tự nghiệp vụ, hãy thiết kế cách sắp xếp hoặc ghép kết quả riêng, như chương trình ở phần trước.

Không trả `text` ra ngoài. Một phương thức `getBuilder()` có thể phá toàn bộ quy tắc vì bên gọi không bị buộc phải dùng `lock`.

## 6. StringBuffer có giải quyết mọi thứ không?

`StringBuffer` cung cấp đồng bộ hóa cho các phương thức cần thiết và hỗ trợ truy cập từ nhiều luồng. Tuy nhiên, một chuỗi nhiều lần gọi vẫn cần xem xét như một thao tác nghiệp vụ. [Tài liệu StringBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuffer.html)

Ví dụ, với bộ đệm dùng chung:

```java
buffer.append(name).append('=').append(value).append(';');
```

Đây là bốn lần gọi. Dù mỗi lần gọi an toàn, bản ghi hoàn chỉnh vẫn có thể bị xen kẽ với các lần gọi từ luồng khác. Nếu chọn `StringBuffer` mà yêu cầu cả bản ghi liền mạch, vẫn cần một vùng khóa bao phủ toàn bộ nhóm thao tác.

`StringBuffer` cũng không tự khóa một nguồn `CharSequence` có thể thay đổi được truyền vào từ bên ngoài. Do đó đổi tên lớp không thay thế việc xác định quyền sở hữu, nguồn dữ liệu và ranh giới thao tác.

## 7. Quy tắc lựa chọn khi viết mã

| Nhu cầu | Hướng xử lý |
| --- | --- |
| Ghép chuỗi trong một lần tính toán | Builder cục bộ, trả về `String` |
| Nhiều tác vụ tính toán độc lập | Mỗi tác vụ có builder riêng; ghép kết quả ở nơi điều phối |
| Dùng chung một bộ tích lũy | Đóng gói builder và bảo vệ mọi truy cập bằng cùng khóa |
| Chuyển builder giữa các luồng | Chuyển giao có đồng bộ và chấm dứt quyền sử dụng ở bên cũ |
| Chỉ cần đưa kết quả văn bản sang luồng khác | Ưu tiên `String` qua một cơ chế chuyển kết quả phù hợp |
| Muốn tái sử dụng builder trong trường để “tối ưu” | Đánh giá chi phí và rủi ro trước; không bỏ quyền sở hữu rõ ràng chỉ để giảm khởi tạo |

Các nhãn như “mỗi yêu cầu có một builder” chỉ đúng khi builder không bị giữ lại và dùng đồng thời bởi những tác vụ con. Tương tự, `ThreadLocal` không đồng nghĩa với “mỗi yêu cầu”: luồng trong nhóm luồng có thể được tái sử dụng cho yêu cầu sau. Nếu dùng bộ đệm theo luồng, phải quản lý dữ liệu cũ và vòng đời của nó.

Để rà soát một đoạn mã, hãy tự trả lời: ai giữ tham chiếu builder, ai được sửa, ai được đọc, khi nào quyền sử dụng kết thúc và kết quả được chuyển đi bằng cơ chế nào.

## 8. Tự kiểm tra

1. Vì sao ứng dụng có nhiều luồng vẫn có thể dùng `StringBuilder` mà không khóa?
2. Một builder là biến cục bộ nhưng được hai lambda cùng giữ lại có còn bị giới hạn trong một luồng không?
3. Vì sao chỉ khóa `appendRecord` mà để `snapshot` không khóa là thiếu?
4. Dùng cùng khóa có bảo đảm bản ghi A luôn xuất hiện trước bản ghi B không?

Đối chiếu:

1. Mỗi luồng hoặc tác vụ có thể thao tác trên đối tượng builder riêng.
2. Không; cần xem ai truy cập cùng đối tượng, không chỉ nơi khai báo biến.
3. Luồng đọc vẫn có thể truy cập builder khi luồng khác sửa và không có quy ước nhìn thấy dữ liệu tương ứng.
4. Không; khóa bảo vệ ranh giới thao tác, còn thứ tự giữa các luồng cần quy tắc bổ sung.
