# Tránh tính toán nặng hoặc tác dụng phụ khi tạo biểu diễn `toString()`

`toString()` là phương thức của `java.lang.Object` trả về một chuỗi mô tả đối tượng. Lập trình viên thường override phương thức này để đọc log, debug, xem trạng thái trong IDE hoặc hiển thị nhanh một giá trị. Vì vậy, **`toString()` nên dễ gọi, nhanh, có giới hạn và không gây tác dụng phụ ngoài ý muốn**.

Một cách cài đặt có vấn đề là mỗi lần `toString()` lại truy vấn cơ sở dữ liệu, gọi HTTP, đọc tệp, tính toán trên hàng triệu phần tử, thay đổi bộ đếm, cập nhật cache hoặc sửa đối tượng. Một thao tác tưởng như vô hại — `System.out.println(obj)` hoặc ghi log — khi đó có thể làm chương trình chậm, tạo lỗi khó tìm hoặc thay đổi hành vi nghiệp vụ.

Mục tiêu thực tế là: **chuỗi biểu diễn chỉ mô tả trạng thái đã có hoặc một phần tóm tắt đủ rẻ để lấy**, còn nghiệp vụ tốn kém và các thao tác có tác dụng phụ cần được gọi qua phương thức có tên, mục đích và chi phí rõ ràng.

## 1. Vì sao phải quan tâm đến chi phí của `toString()`?

Java có thể gọi `toString()` trong nhiều ngữ cảnh:

- `System.out.println(object)` chuyển đối tượng thành chuỗi trước khi in.
- `"order = " + order`, `String.valueOf(order)` và `String.format("%s", order)` tạo biểu diễn dạng chuỗi.
- Khi một `List`, `Set`, `Map` được chuyển thành chuỗi, biểu diễn của các phần tử/key/value có thể được gọi tiếp.
- Công cụ debug, hệ thống log, trình kiểm tra lỗi hoặc mã thư viện có thể yêu cầu chuỗi biểu diễn để cung cấp ngữ cảnh.

Đó là lý do **không nên giả định chỉ có một nơi duy nhất gọi `toString()`**. Một đối tượng có thể được in nhiều lần trong một request, hay từ nhiều luồng vào thời điểm khó dự đoán. Những tác dụng phụ nằm trong `toString()` sẽ xảy ra chỉ vì có người yêu cầu xem thông tin.

Ví dụ một đoạn code tưởng đơn giản:

~~~java
System.out.println("Current order: " + order);
~~~

Đây là mã minh họa nằm trong một phương thức có biến `order`. Phép ghép chuỗi buộc Java chuyển `order` thành chuỗi. Nếu `Order.toString()` gọi dịch vụ bên ngoài, chính lệnh in này có thể gây I/O, timeout hoặc ném ngoại lệ.

**Bản chất của `toString()`:** nó là phương thức thông thường có thể chứa bất kỳ mã Java nào; JVM không tự ngăn việc đọc/ghi dữ liệu hay tính toán nặng. Quy tắc “nhẹ và không tác dụng phụ” là **nguyên tắc thiết kế**, giúp giảm rủi ro khi sử dụng phương thức thường xuyên.

## 2. Thế nào là “tính toán nặng” và “tác dụng phụ”?

**Tính toán nặng** là công việc có chi phí lớn hoặc khó dự đoán về thời gian, bộ nhớ, CPU hay I/O. **Tác dụng phụ** là việc lời gọi làm thay đổi trạng thái quan sát được bên ngoài kết quả trả về, hoặc kích hoạt hành động ngoài mục tiêu tạo chuỗi.

| Mẫu cài đặt trong `toString()` | Vấn đề tiềm ẩn | Cách tiếp cận phù hợp hơn |
| --- | --- | --- |
| Tính tổng/phân tích toàn bộ tập rất lớn ở mỗi lần gọi | CPU tăng theo số phần tử; lặp lại công việc | Dùng dữ liệu tổng hợp đã lưu sẵn nếu cần và luôn được cập nhật đúng; hoặc chỉ in kích thước/tóm tắt. |
| Gọi SQL/API/network, đọc tệp | Có I/O, timeout, lỗi hạ tầng, có thể tạo truy vấn bất ngờ | Tách sang `loadDetails()` hay phương thức nghiệp vụ tường minh. |
| Tự động truy cập quan hệ ORM tải chậm (lazy association) | Có thể tạo truy vấn, tải cả đồ thị, hoặc lỗi khi session đóng | In ID/trường scalar đã có; tránh duyệt quan hệ trong `toString()`. |
| `counter++`, thêm vào collection, thay trạng thái | Gọi để quan sát lại làm đổi dữ liệu | Dời thao tác cập nhật sang phương thức ghi có chủ đích. |
| Gọi `toString()` của mọi phần tử trong collection lớn | Chuỗi khổng lồ; phần tử có thể chứa tác dụng phụ/đệ quy | Giới hạn số phần tử; ưu tiên các mã định danh hay thuộc tính đơn giản. |
| Đi sâu vào quan hệ hai chiều hoặc đồ thị có vòng | Đệ quy vô hạn, `StackOverflowError` | Chỉ hiển thị ID/summary và giới hạn độ sâu. |
| Khóa lâu, chờ tương lai hoàn thành, sleep | Khó dự đoán độ trễ; nguy cơ chặn luồng log/debug | Đọc snapshot đã có, không chờ công việc bất đồng bộ. |
| In mật khẩu, token, dữ liệu cá nhân | Lộ thông tin qua log và công cụ quan sát | Chỉ in trường an toàn; che hoặc bỏ dữ liệu nhạy cảm. |

Không phải mọi phép tính trong `toString()` đều xấu. Ghép vài trường số/chuỗi, định dạng một mã ngắn hoặc đọc các trường đã có thường là hợp lý. **Vấn đề là chi phí mất kiểm soát, công việc bị lặp lại và hành vi ngoài việc mô tả đối tượng.**

## 3. Ví dụ chạy được: một `toString()` có tác dụng phụ

Tệp **`ToStringCostDemo.java`**, dùng Java 17+:

~~~java
import java.util.List;

public class ToStringCostDemo {
    static final class BadReport {
        private final List<Integer> amounts;
        private int renderCount;

        BadReport(List<Integer> amounts) {
            this.amounts = List.copyOf(amounts);
        }

        @Override
        public String toString() {
            renderCount++; // Tác dụng phụ chỉ vì tạo biểu diễn.
            int total = 0;
            for (int amount : amounts) {
                total += amount; // Quét toàn bộ danh sách mỗi lần.
            }
            return "Report(total=" + total + ", renderCount=" + renderCount + ")";
        }

        int renderCount() {
            return renderCount;
        }
    }

    static final class GoodReport {
        private final int id;
        private final int itemCount;
        private final int total;

        GoodReport(int id, List<Integer> amounts) {
            this.id = id;
            this.itemCount = amounts.size();
            int sum = 0;
            for (int amount : amounts) {
                sum = Math.addExact(sum, amount);
            }
            this.total = sum;
        }

        @Override
        public String toString() {
            return "Report(id=" + id
                + ", items=" + itemCount
                + ", total=" + total + ")";
        }
    }

    public static void main(String[] args) {
        List<Integer> amounts = List.of(4, 6, 10);
        BadReport bad = new BadReport(amounts);

        System.out.println(bad.toString());
        System.out.println(bad.toString());
        System.out.println("renderCount=" + bad.renderCount());

        GoodReport good = new GoodReport(12, amounts);
        System.out.println(good);
        System.out.println(String.valueOf(good));
        System.out.println(good.toString().equals(good.toString()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ToStringCostDemo.java
java ToStringCostDemo
~~~

Kết quả chuẩn:

~~~text
Report(total=20, renderCount=1)
Report(total=20, renderCount=2)
renderCount=2
Report(id=12, items=3, total=20)
Report(id=12, items=3, total=20)
true
~~~

Ở `BadReport`, **hai lần gọi** `toString()` làm `renderCount` tăng từ `0` lên `2`, dù người dùng chỉ muốn đọc chuỗi. Mỗi lần cũng quét toàn bộ `amounts`. Với danh sách lớn, việc ghi log lặp lại có thể tạo chi phí đáng kể.

Ở `GoodReport`, dữ liệu tổng hợp được **tính một lần khi tạo đối tượng** và lưu vào các trường `final`. `toString()` chỉ kết hợp vài giá trị đã có, không sửa trạng thái. Hai lời gọi cho cùng chuỗi khi trạng thái không thay đổi.

**Không nên hiểu ví dụ là luôn phải tính trước mọi phép tổng hợp.** Constructor của `GoodReport` vẫn cần thời gian tuyến tính theo kích thước danh sách và `Math.addExact` có thể ném `ArithmeticException` nếu tổng tràn `int`. Nếu tổng chưa cần thiết cho nghiệp vụ, thiết kế tốt hơn có thể **không tính tổng ở đâu cả khi tạo đối tượng**, và chỉ in `id` cùng `itemCount`. Việc tiền xử lý phải có lý do nghiệp vụ hoặc hiệu năng rõ ràng.

Ngoài ra, dữ liệu đầu vào của ví dụ là `List<Integer>` bất biến về các phần tử theo kiểu `Integer`. Với class mutable thực tế, dữ liệu tổng hợp lưu sẵn phải được cập nhật đúng mỗi khi trạng thái thay đổi; nếu không, biểu diễn có thể bị lỗi thời. Đối tượng bất biến thường giúp đơn giản hóa bảo đảm này.

## 4. Nguyên tắc: `toString()` nên quan sát, không điều khiển chương trình

Trong thực tế, hãy coi `toString()` là thao tác **quan sát trạng thái**, không phải điểm kích hoạt nghiệp vụ.

### Không thực hiện I/O hay tải dữ liệu

Tránh các ý tưởng như sau:

~~~java
@Override
public String toString() {
    // Phản ví dụ minh họa, KHÔNG phải class chạy độc lập.
    return "Customer(" + id + ", orders=" + orderRepository.findByCustomer(id) + ")";
}
~~~

Lệnh trên chỉ mang tính minh họa trong một class có các trường/biến phù hợp; `orderRepository` là phụ thuộc giả định. Nó tạo nguy cơ:

- Lời gọi log dẫn đến truy vấn dữ liệu.
- Thời gian tạo chuỗi phụ thuộc database/network.
- Một lần in danh sách khách hàng sinh nhiều truy vấn (vấn đề N+1).
- `toString()` thất bại do session đóng hoặc tài nguyên bên ngoài lỗi.
- Chuỗi có thể chứa một lượng lớn dữ liệu không cần thiết.

Thay bằng biểu diễn giới hạn trên các trường đã có, ví dụ `"Customer(id=" + id + ")"`. Khi cần chi tiết, hãy gọi phương thức `loadOrders()`, `fetchCustomerDetails()` hoặc một truy vấn rõ mục đích tại nơi chịu trách nhiệm nghiệp vụ.

### Không sửa dữ liệu, gửi sự kiện hay đo lường ẩn

Nếu `toString()` làm `updateStatus()`, `save()`, `publishEvent()`, `retry()`, `count++` hoặc cập nhật trạng thái toàn cục, chỉ riêng việc chuyển đối tượng thành chuỗi có thể làm thay đổi kết quả chương trình.

**Đừng biến việc debug thành một hành động nghiệp vụ.** Lời gọi `toString()` có thể xảy ra tự động khi framework ghi log hoặc môi trường phát triển hiển thị đối tượng. Khi phải ghi metrics hay audit, gọi thao tác tường minh ở đúng ranh giới nghiệp vụ; không gắn việc này với tạo biểu diễn.

### Giữ kết quả ổn định khi trạng thái ổn định

Không có quy định API bắt buộc `toString()` của mọi đối tượng phải trả một chuỗi duy nhất suốt vòng đời. Với đối tượng mutable, chuỗi có thể đổi khi dữ liệu đổi. Nhưng **hai lần gọi liên tiếp trên cùng trạng thái nên cho thông tin giống nhau**, trừ khi kiểu dữ liệu có yêu cầu khác được tài liệu hóa rõ.

Tránh đưa ngẫu nhiên, số đếm lần render, thời gian hiện tại hoặc chi phí ngoại vi vào chuỗi chỉ vì dễ thực hiện. Nếu cần thời điểm tạo bản ghi, hãy ghi thời điểm đó vào trường nghiệp vụ tại một hành động tường minh, sau đó `toString()` chỉ hiển thị trường đã lưu.

## 5. Giới hạn số phần tử và độ dài biểu diễn

Một `toString()` in hàng triệu phần tử không nhất thiết có tác dụng phụ, nhưng vẫn có thể quá chậm và chiếm nhiều bộ nhớ. `Collection.toString()` thường duyệt phần tử và tạo chuỗi biểu diễn tương ứng; mỗi phần tử còn có thể gọi `toString()` riêng.

Nên tóm tắt **số lượng và một mẫu nhỏ** thay vì in tất cả dữ liệu. Với giá trị dạng `String` đã được kiểm soát, ví dụ có thể làm như sau.

Tệp **`BoundedToStringDemo.java`**:

~~~java
import java.util.List;

public class BoundedToStringDemo {
    static final class TaskBatch {
        private final int id;
        private final List<String> taskIds;

        TaskBatch(int id, List<String> taskIds) {
            this.id = id;
            this.taskIds = List.copyOf(taskIds);
        }

        @Override
        public String toString() {
            int shown = Math.min(3, taskIds.size());
            return "TaskBatch(id=" + id
                + ", size=" + taskIds.size()
                + ", sample=" + taskIds.subList(0, shown)
                + (shown < taskIds.size() ? ", ..." : "")
                + ")";
        }
    }

    public static void main(String[] args) {
        TaskBatch shortBatch = new TaskBatch(1, List.of("T1", "T2"));
        TaskBatch longBatch = new TaskBatch(
            2, List.of("T1", "T2", "T3", "T4", "T5")
        );

        System.out.println(shortBatch);
        System.out.println(longBatch);
    }
}
~~~

Chạy:

~~~bash
javac BoundedToStringDemo.java
java BoundedToStringDemo
~~~

Kết quả:

~~~text
TaskBatch(id=1, size=2, sample=[T1, T2])
TaskBatch(id=2, size=5, sample=[T1, T2, T3], ...)
~~~

Ví dụ dùng danh sách ID dạng `String` để bảo đảm các phần tử được hiển thị ngắn và không có tác dụng phụ. Nếu `taskIds` chứa đối tượng có `toString()` phức tạp, việc lấy `subList` nhỏ **chưa tự bảo đảm an toàn**: vẫn cần chọn các trường ID an toàn hoặc chủ động kiểm soát cách định dạng từng phần tử.

`List.copyOf` trong constructor tạo một danh sách không cho phép sửa cấu trúc và không chấp nhận phần tử `null`; đây là lựa chọn thiết kế của ví dụ. Một dữ liệu rất lớn vẫn mất chi phí sao chép **khi tạo đối tượng**, nhưng mỗi lần `toString()` chỉ biểu diễn tối đa ba ID đầu tiên. Độ dài tổng thể vẫn phụ thuộc độ dài từng ID; nếu ID là văn bản dài không kiểm soát, phải bổ sung giới hạn độ dài chuỗi để có **trần output thực sự**.

## 6. Tránh đệ quy vô hạn với quan hệ đối tượng có vòng

Một kiểu đối tượng có tham chiếu ngược có thể gây lỗi khi `toString()` tự động đi sâu vào quan hệ:

~~~text
Parent -> Child -> Parent -> Child -> ...
~~~

Giả sử `Parent.toString()` in toàn bộ `children`, trong khi `Child.toString()` lại in toàn bộ `parent`. Chỉ một lần ghi log parent có thể dẫn tới chuỗi lời gọi lặp lại không kết thúc và gây `StackOverflowError`.

Đối với mô hình quan hệ hai chiều, đồ thị hoặc cây có thể có vòng, hãy chỉ mô tả các thuộc tính cục bộ, ID của đối tượng liên quan, số lượng phần tử hoặc một độ sâu có kiểm soát. Ví dụ:

~~~java
final class Node {
    private final int id;
    private Node next;

    Node(int id) {
        this.id = id;
    }

    void link(Node next) {
        this.next = next;
    }

    @Override
    public String toString() {
        return "Node(id=" + id
            + ", nextId=" + (next == null ? "null" : next.id)
            + ")";
    }
}
~~~

Đây là **một khai báo class minh họa**, có thể đặt cạnh các class khác trong cùng tệp Java. Nếu gọi `Node a = new Node(1)`, `Node b = new Node(2)`, rồi `a.link(b)` và `b.link(a)`, `a.toString()` sẽ trả `Node(id=1, nextId=2)`. Nó không gọi `next.toString()`, nên không lặp qua vòng liên kết.

Đừng suy luận rằng `StringBuilder` tự giải quyết được đệ quy: nếu nối trực tiếp một object khác vào builder, Java vẫn có thể gọi `toString()` của object đó.

## 7. Log và `toString()`: tránh chi phí ngay cả khi không cần log

Một ví dụ thường gặp với logging framework:

~~~java
// Minh họa trong phương thức có logger và order:
logger.debug("Order details: " + order);

// Một kiểu gọi logging theo tham số:
logger.debug("Order details: {}", order);
~~~

Dòng đầu **tạo chuỗi ngay khi thực thi phép ghép**, vì vậy `order.toString()` có thể bị gọi trước khi framework quyết định có ghi mức DEBUG hay không. Dòng thứ hai có thể **hoãn định dạng** tùy logging API và cấu hình, nên thường tránh được một phần công việc khi log bị tắt. Tuy nhiên, **không có bảo đảm chung rằng mọi framework, mọi mức log hay mọi cơ chế tham số hóa đều không gọi `toString()`**. Không được biến lời khuyên dùng placeholder thành lý do để đặt công việc nặng trong `toString()`.

Nếu việc tạo thông tin chi tiết tự nó rất tốn kém, hãy kiểm tra khả năng dùng logging API hỗ trợ lazy evaluation/supplier; hoặc điều kiện `logger.isDebugEnabled()` khi phù hợp, rồi mới xây dựng nội dung trong nhánh đó. Chọn giải pháp theo framework và nhu cầu thực tế; không phải lúc nào một lệnh kiểm tra mức log cũng cần thiết.

Ngoài chi phí, còn phải cân nhắc **tính an toàn của dữ liệu log**. Một `toString()` in token, mật khẩu, thông tin thanh toán hay dữ liệu định danh có thể làm lộ dữ liệu tới tập tin log hoặc công cụ quan sát. Các trường nhạy cảm nên bị bỏ qua hoặc che giá trị. Dùng chuỗi biểu diễn cho debug **không đồng nghĩa** với việc đã có quyền phát tán tất cả trạng thái của đối tượng.

## 8. Giữ biểu diễn ngắn, có ích và không phụ thuộc cơ sở dữ liệu

Một mẫu `toString()` thực dụng cho entity nghiệp vụ là in **loại đối tượng, ID và một số trạng thái cơ bản đã có**:

~~~java
@Override
public String toString() {
    return "Payment(id=" + id + ", status=" + status + ")";
}
~~~

Đây là đoạn mã trong một class có hai trường `id` và `status`. Nếu `status` là enum hoặc chuỗi ngắn, việc tạo biểu diễn thường đơn giản. Nếu `status` lại là một đối tượng phức tạp có `toString()` riêng, vẫn cần kiểm tra chi phí của phép gọi đó.

Tránh kiểu:

~~~java
@Override
public String toString() {
    // Phản ví dụ: phụ thuộc giả định trong class, KHÔNG chạy độc lập.
    return "Payment(" + paymentService.refresh(id) + ")";
}
~~~

Một phương thức tên `refresh` gợi ý rõ thao tác thay đổi hoặc tải lại trạng thái. Nó thuộc luồng nghiệp vụ hay đồng bộ dữ liệu riêng, không nên được kích hoạt mỗi khi cần in đối tượng.

Nếu một ứng dụng cần biểu diễn **chi tiết để xuất báo cáo, serialize JSON hoặc hiển thị UI**, hãy tạo hàm/DTO/serializer dành riêng cho mục tiêu đó. `toString()` chủ yếu là biểu diễn thuận tiện để hỗ trợ quan sát/debug; nó **không phải định dạng dữ liệu ổn định dành cho tích hợp giữa các hệ thống**.

### Có nên cache chuỗi `toString()`?

Không có đáp án chung cho mọi đối tượng.

- Với một value object **thực sự bất biến** và biểu diễn tốn một chút công sức, cache chuỗi sau lần tạo có thể là lựa chọn có ích nếu đã đo được lợi ích.
- Với đối tượng **mutable**, cache biểu diễn đòi hỏi cơ chế vô hiệu hóa chính xác khi trường liên quan thay đổi. Nếu không, `toString()` có thể trả dữ liệu lỗi thời.
- Cache cũng có chi phí bộ nhớ và các vấn đề đồng thời nếu tự cài đặt không phù hợp. Thường nên bắt đầu bằng **biểu diễn đơn giản và rẻ**, chỉ thêm cache sau khi có số liệu hiệu năng.

Một nguyên tắc an toàn: **đừng cài cache có tác dụng phụ lớn trong `toString()` chỉ vì mong kết quả nhanh hơn**. Việc thiết kế cache thuộc phần quản lý trạng thái, cần được quyết định rõ ràng.

## 9. `record`, code generator và phương thức được sinh sẵn

Java record sinh `toString()` từ các thành phần được khai báo. Điều này rất tiện với các record nhỏ chứa `int`, `String` hay enum đơn giản. Tuy nhiên, nếu thành phần là **đối tượng phức tạp, collection lớn hoặc giá trị nhạy cảm**, biểu diễn được sinh tự động có thể không phù hợp cho log.

~~~java
record AccountView(long id, String accessToken) {}

AccountView view = new AccountView(5L, "SECRET");
System.out.println(view); // Sẽ có trường accessToken trong biểu diễn.
~~~

Hai dòng cuối là mã minh họa trong một phương thức Java; nội dung `"SECRET"` chỉ là dữ liệu mẫu. **Không nên in token thật**. Nếu đối tượng chứa dữ liệu nhạy cảm, bạn có thể override `toString()` để chỉ hiển thị trường an toàn hoặc không log đối tượng đó.

Tương tự, nếu IDE hay thư viện sinh tự động `toString()` dựa trên **toàn bộ trường**, cần xem lại những trường nào là quan hệ ORM, dữ liệu lớn, tham chiếu ngược hoặc giá trị bí mật. Sinh tự động giúp giảm công viết mã nhưng **không thay thế quyết định về phạm vi và chi phí của biểu diễn**.

Cũng cần nhớ: `Object.toString()` mặc định thường cho biểu diễn dựa trên tên class và một giá trị hash dạng hex; không phải địa chỉ bộ nhớ hay khóa duy nhất đáng tin cậy. Nếu chưa cần thêm thông tin, không có nghĩa mọi class đều bắt buộc override `toString()`.

## 10. Kiểm thử hành vi `toString()`

Một bài test có giá trị cần kiểm tra cả **nội dung hiển thị**, **việc không thay đổi trạng thái**, và **giới hạn dữ liệu**. Ví dụ:

1. Gọi `toString()` hai lần liên tiếp trên cùng trạng thái; chuỗi có giống nhau không?
2. Ghi lại các trường có thể thay đổi trước lời gọi và đối chiếu sau; việc tạo chuỗi có làm thay đổi trạng thái nghiệp vụ không?
3. Với collection lớn, chuỗi có in ra số lượng giới hạn hay quét toàn bộ phần tử?
4. Với quan hệ hai chiều, lời gọi có đi vòng mãi giữa hai object không?
5. Với đối tượng có trường `null`, `toString()` có xử lý được mà không gây `NullPointerException` bất ngờ không?
6. Với entity có quan hệ tải chậm, việc chỉ in ID có tránh truy vấn dữ liệu ngoài dự kiến không?
7. Chuỗi có vô tình chứa token, mật khẩu, nội dung nhạy cảm hay thông tin quá chi tiết không?

Không nên viết test chỉ kiểm tra một lần `toString()` chứa đúng từ khóa rồi kết luận phương thức an toàn. Với các loại object dùng trong log, khả năng **không gây hành động ngoài ý muốn** thường quan trọng ngang với định dạng.

### Phân biệt điều có thể kiểm chứng và điều cần đo

Kiểm thử đơn vị có thể xác nhận bộ đếm không đổi, dịch vụ giả lập không bị gọi, hoặc chuỗi chỉ có tối đa một số phần tử nhất định. Nhưng độ trễ thực tế phụ thuộc dữ liệu, phần cứng, JVM và môi trường. Đừng khẳng định `toString()` “O(1)” nếu chuỗi chứa trường `String` dài không giới hạn; việc sao chép và xây dựng chuỗi vẫn cần thời gian theo số ký tự đầu ra. Có thể nói rõ ràng hơn rằng biểu diễn **không quét toàn bộ collection** và **không gọi I/O**.

## 11. Checklist triển khai

Trước khi chốt một `toString()`, kiểm tra:

- **Mục đích:** chuỗi mô tả giúp nhận biết object (loại, ID, trạng thái ngắn), không làm nhiệm vụ truy vấn hay serialize đầy đủ.
- **Chi phí:** chỉ đọc các trường sẵn có; tránh duyệt toàn bộ cấu trúc lớn hoặc tính toán lặp lại không cần thiết.
- **Tác dụng phụ:** không sửa field, không tăng bộ đếm, không gửi request, không ghi database, không tải dữ liệu hay kích hoạt lazy load.
- **Giới hạn:** tránh chuỗi khổng lồ, in toàn bộ đồ thị hoặc vòng tham chiếu; chọn giới hạn phần tử/độ sâu/độ dài phù hợp.
- **Bảo mật:** không đưa secret và thông tin riêng tư không cần thiết vào biểu diễn.
- **Tính ổn định:** cùng trạng thái thường tạo ra biểu diễn giống nhau; không phụ thuộc random hoặc đồng hồ nếu không có mục đích rõ.
- **Tương tác hệ thống:** xem xét nơi `toString()` bị gọi gián tiếp, đặc biệt khi logging, debug, ghép chuỗi và các collection.
- **Kiểm chứng:** kiểm tra output, trạng thái sau nhiều lần gọi và hành vi với dữ liệu lớn/quan hệ lồng.

## 12. Câu hỏi tự kiểm tra

1. Nếu `toString()` gọi database để lấy danh sách đơn hàng, vì sao chỉ một câu lệnh `println(customer)` lại có thể làm chương trình chậm hoặc lỗi?
2. Trong `BadReport`, sau hai lần gọi `toString()`, trường `renderCount` đổi thế nào? Điều đó thể hiện tác dụng phụ gì?
3. Một `toString()` chỉ đọc `id` và `status` đã có, so với một `toString()` duyệt hàng triệu phần tử, cách nào dễ kiểm soát chi phí hơn?
4. Với quan hệ `Parent ↔ Child`, vì sao gọi `toString()` của đối tượng liên quan ở cả hai phía có thể gây `StackOverflowError`?
5. `logger.debug("Order: " + order)` có thể gọi `order.toString()` ngay cả khi mức DEBUG bị tắt không? Vì sao?
6. Một record có trường `accessToken`: vì sao không nên mặc định log nguyên record? Bạn có thể thiết kế biểu diễn an toàn hơn như thế nào?
7. Nếu dùng cache cho chuỗi `toString()` của đối tượng mutable, cần điều kiện gì để không trả về dữ liệu cũ?
8. Vì sao ngay cả một `toString()` không có I/O cũng có thể tốn nhiều thời gian nếu chuỗi trả về quá dài?

**Ghi nhớ:** `toString()` là công cụ **mô tả**, không phải nơi **thực hiện nghiệp vụ**. Hãy giữ phương thức nhẹ, đọc trạng thái sẵn có, giới hạn kích thước và tránh tác dụng phụ, I/O, đệ quy vô hạn cũng như rò rỉ dữ liệu. Công việc tốn kém cần có API tường minh để người gọi hiểu lúc nào và vì sao nó được thực hiện.