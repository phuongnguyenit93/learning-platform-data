# Vì sao ghi nhật ký, đo thời gian hoặc kiểm soát truy cập dễ lặp lại?

Một ứng dụng có các chức năng khác nhau như tạo đơn hàng, xuất báo cáo, chuyển tiền, cập nhật hồ sơ. Mỗi chức năng giải quyết một nghiệp vụ riêng, nhưng trước, trong hoặc sau khi thực hiện, ta thường phải làm các việc giống nhau: **kiểm tra ai có quyền gọi, ghi nhận chuyện gì xảy ra và đo thời gian thực thi**. Khi số chức năng tăng, những đoạn mã này xuất hiện lặp lại trên nhiều lớp, nhiều phương thức.

Đây là một động lực hình thành **lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP)**: tách các mối quan tâm dùng chung, cắt ngang nhiều luồng nghiệp vụ khỏi phần thực hiện nghiệp vụ. Bài này giải thích nguyên nhân sự lặp lại, hậu quả thiết kế, tư duy AOP và giới hạn của cách tiếp cận đó.

## 1. Tại sao cùng một chính sách xuất hiện ở nhiều nơi?

Giả sử hệ thống có ba yêu cầu:

- **Nghiệp vụ:** tạo đơn hàng, xuất báo cáo và duyệt thanh toán phải thực hiện đúng quy tắc riêng.
- **Vận hành:** các thao tác quan trọng cần ghi nhận lúc bắt đầu, kết thúc và thất bại; quản trị viên muốn biết thời gian chạy.
- **Truy cập:** chỉ chủ thể đáp ứng chính sách phân quyền được thực hiện một số thao tác nhạy cảm.

Thuật toán tạo đơn hàng không giống xuất báo cáo. Tuy nhiên, cả hai đều có **ranh giới thực thi**: nhận lời gọi → quyết định có cho phép hay không → bắt đầu công việc → trả kết quả hoặc phát sinh lỗi → kết thúc. Đây là những vị trí tự nhiên để đặt log, đồng hồ đo và kiểm tra quyền.

Sự lặp lại thường bắt nguồn từ bốn yếu tố:

1. **Chính sách áp dụng rộng.** Quy tắc “ghi log khi thất bại”, “đo độ trễ thao tác quan trọng” và “kiểm tra quyền trước hành động nhạy cảm” không thuộc riêng một chức năng.
2. **Điểm triển khai thuận tiện nằm ngay trong phương thức.** Người viết phương thức biết rõ nơi bắt đầu, kết thúc, tham số và kết quả, nên dễ chèn các lệnh phụ trợ trực tiếp tại đó.
3. **Các chức năng được tạo độc lập.** Nhiều lập trình viên làm nhiều chức năng; nếu thiếu điểm áp dụng chung, mỗi người phải nhớ triển khai chính sách giống nhau.
4. **Ngoại lệ và đường gọi đa dạng.** Một thao tác có thể thành công, ném ngoại lệ, bị từ chối hoặc được gọi từ nhiều điểm vào. Mỗi phương thức viết thủ công phải xử lý lại các trường hợp này.

Lặp lại ở đây là **lặp chính sách và cách phối hợp hành vi**. Những câu log mang tên phương thức khác nhau vẫn có thể là bản sao của cùng quy tắc “ghi START trước và END sau”.

## 2. Nhìn thấy sự lặp lại trong Java

File `Before.java` dưới đây là chương trình Java 17+ chạy độc lập. Hai nghiệp vụ khác nhau nhưng cùng lặp kiểm tra quyền, log và đo thời gian.

~~~java
public class Before {
    static void createOrder(String role) {
        if (!"ADMIN".equals(role)) {
            throw new SecurityException("Access denied");
        }
        long started = System.nanoTime();
        System.out.println("START createOrder");
        try {
            System.out.println("BUSINESS create order");
        } finally {
            System.out.println("END createOrder; elapsedNs="
                    + (System.nanoTime() - started));
        }
    }

    static void exportReport(String role) {
        if (!"ADMIN".equals(role)) {
            throw new SecurityException("Access denied");
        }
        long started = System.nanoTime();
        System.out.println("START exportReport");
        try {
            System.out.println("BUSINESS export report");
        } finally {
            System.out.println("END exportReport; elapsedNs="
                    + (System.nanoTime() - started));
        }
    }

    public static void main(String[] args) {
        createOrder("ADMIN");
        exportReport("ADMIN");
    }
}
~~~

Chạy:

~~~bash
javac Before.java
java Before
~~~

Mỗi thao tác in dòng `START`, tiếp theo là `BUSINESS`, cuối cùng là `END`. Số nanosecond thay đổi ở mỗi lần chạy. Đo chênh lệch bằng `System.nanoTime()` phù hợp hơn việc lấy hiệu hai thời điểm lịch. Khối `finally` bảo đảm ghi dòng kết thúc khi phần nghiệp vụ ném lỗi.

Có một quyết định quan trọng: kiểm tra quyền diễn ra **trước** khi bắt đầu đo và log. Do đó, lời gọi bị từ chối sẽ không có log `START` hoặc số đo. Nếu yêu cầu của hệ thống là thống kê cả lần bị từ chối, thứ tự trên cần thay đổi. Điều này cho thấy **thứ tự thực thi hành vi dùng chung cũng là chính sách**.

Với hai phương thức, sự lặp trông nhỏ. Với hàng trăm phương thức, muốn bổ sung correlation ID, đổi định dạng log, đo thêm thời gian lỗi hoặc thay quy tắc quyền thì phải sửa nhiều nơi. Một phương thức quên `finally` hoặc quên kiểm tra quyền có thể khiến dữ liệu vận hành thiếu nhất quán, thậm chí tạo lỗ hổng.

## 3. Scattering và tangling: hai mặt của cùng bài toán

AOP dùng hai khái niệm quan trọng:

**Scattering (phân tán):** *một* mối quan tâm xuất hiện ở *nhiều* vị trí. Ví dụ logic đo thời gian bị rải trong 80 phương thức. Muốn sửa một chính sách, ta phải tìm và sửa nhiều bản sao; việc bỏ sót rất dễ xảy ra.

**Tangling (đan xen):** *một* phương thức trộn *nhiều* mối quan tâm. Ví dụ phương thức chuyển tiền vừa kiểm tra số dư và ghi dữ liệu, vừa log, đo thời gian, kiểm tra quyền, thống kê. Người đọc khó thấy phần nào tạo nên hành vi nghiệp vụ thật sự.

| Góc nhìn | Dấu hiệu | Hệ quả |
| --- | --- | --- |
| Scattering | Cùng một quy tắc log/đo thời gian/phân quyền nằm trong nhiều phương thức | Khó đổi đồng loạt, dễ thiếu hoặc lệch chính sách |
| Tangling | Một phương thức trộn logic nghiệp vụ với nhiều lệnh hạ tầng | Khó hiểu, khó kiểm thử, khó truy vết nguyên nhân lỗi |
| Cả hai | Nhiều phương thức đều trộn những chính sách giống nhau | Chi phí bảo trì tăng theo quy mô và số lần thay đổi |

Có thể tự phân biệt bằng hai câu hỏi: **“mối quan tâm này đang nằm ở bao nhiêu nơi?”** là scattering; **“phương thức này phải gánh bao nhiêu mối quan tâm?”** là tangling.

## 4. Vì sao đây là các mối quan tâm cắt ngang?

**Concern (mối quan tâm)** là một trách nhiệm hoặc yêu cầu của phần mềm. Quy tắc tính thuế đơn hàng là một concern nghiệp vụ cụ thể. Trái lại, chính sách “ghi log thất bại” áp dụng được cho cả đơn hàng, báo cáo và nhiều thao tác khác: nó **cắt ngang (cross-cutting)** các chức năng.

Ba mối quan tâm đang xét có mục tiêu khác nhau:

| Mối quan tâm | Câu hỏi | Điểm can thiệp thường gặp | Rủi ro nếu chèn thủ công |
| --- | --- | --- | --- |
| Ghi nhật ký | Ai làm gì, khi nào, kết quả hay lỗi gì? | Trước/sau lời gọi, khi xảy ra ngoại lệ | Thiếu bối cảnh, log trùng, lộ dữ liệu nhạy cảm |
| Đo thời gian | Từ điểm A đến điểm B mất bao lâu? | Ngay trước và sau đoạn cần đo, kể cả lúc lỗi | Sai phạm vi đo, bỏ sót đường lỗi, nhầm elapsed với CPU |
| Kiểm soát truy cập | Chủ thể này có được phép tác động lên tài nguyên này không? | Trước hành động cần bảo vệ | Bỏ sót một đường gọi, tin quyền tự khai, quyết định sai đối tượng |

Ba mối quan tâm cùng **xuất hiện nhiều nơi**, nhưng không có nghĩa chúng áp dụng *giống hệt nhau ở mọi nơi*. Một getter đơn giản có thể không cần log hay đo thời gian; thao tác xóa dữ liệu nhạy cảm có thể đòi hỏi chính sách quyền chặt hơn thao tác xem danh mục công khai.

Một chính sách cắt ngang vì thế có hai phần cần trả lời rõ:

- **Làm gì?** Ví dụ ghi trạng thái lỗi với mã tương quan, đo elapsed time hoặc kiểm tra quyền.
- **Ở đâu và lúc nào?** Ví dụ các thao tác ghi dữ liệu, trước một hành động nhạy cảm, sau khi lời gọi thất bại.

Tách biệt hai câu hỏi này là bước chuyển từ **lặp lệnh ở từng phương thức** sang **quản lý chính sách ở một nơi**.

## 5. Trích xuất helper giúp được gì, còn thiếu gì?

Có thể bắt đầu bằng việc trích xuất hàm tiện ích:

~~~java
long started = Metrics.begin("exportReport");
try {
    // Nghiệp vụ xuất báo cáo
} finally {
    Metrics.end("exportReport", started);
}
~~~

Đây là **mã minh họa, không phải chương trình chạy độc lập**: `Metrics` đại diện một helper giả định. Helper giúp tập trung công thức và định dạng thống kê, nhưng mỗi phương thức vẫn phải **tự gọi đúng helper**, đặt `try/finally` đúng vị trí và nhớ xử lý đường lỗi. Phần gắn chính sách vào điểm thực thi vẫn phân tán.

Những cách tổ chức phổ biến có phạm vi khác nhau:

- **Helper:** tái sử dụng thuật toán, nhưng lời gọi vẫn do từng phương thức đặt.
- **Wrapper/decorator:** đặt hành vi dùng chung quanh đối tượng hoặc giao diện; các lời gọi phải đi qua đối tượng được bọc.
- **Kiểm soát tại ranh giới hệ thống:** xử lý một số chính sách tại một điểm vào hoặc tầng tài nguyên; chỉ bao quát các luồng đi qua ranh giới đó.
- **AOP:** xác định riêng *điểm áp dụng* và *hành vi cắt ngang*, rồi kết hợp chúng theo một cơ chế cụ thể.

Điểm cần giải quyết không chỉ là “xóa đoạn code giống nhau” mà còn là **“bảo đảm chính sách được áp dụng nhất quán ở đúng nơi”**.

## 6. Các khái niệm AOP giải quyết nhu cầu đó thế nào?

Ở mức tư duy AOP nói chung:

- **Join point (điểm nối):** điểm trong quá trình thực thi mà cơ chế AOP có thể tác động, ví dụ lời gọi hoặc thực thi một phương thức. Loại join point hỗ trợ tùy cơ chế.
- **Pointcut (quy tắc chọn điểm):** mô tả *join point nào* cần áp dụng chính sách. Chẳng hạn chọn các thao tác nghiệp vụ nhạy cảm, thay vì mọi phương thức.
- **Advice (hành vi bổ sung):** đoạn xử lý ở trước, sau, khi lỗi hoặc bao quanh một join point. Advice bao quanh có thể tiếp tục lời gọi, quan sát kết quả hoặc ngăn lời gọi.
- **Aspect (khía cạnh):** mô-đun tổ chức một mối quan tâm cắt ngang cùng các quy tắc chọn điểm và hành vi liên quan.
- **Weaving (kết hợp):** kết nối hành vi khía cạnh với chương trình tại những điểm đã chọn. Tùy cơ chế, việc này có thể diễn ra qua biến đổi mã/bytecode hoặc qua đối tượng đại diện lúc chạy.

Một luồng thực thi khả dĩ:

~~~text
Bên gọi
   |
   v
[Điểm thực thi được chọn]
   |
   +--> Kiểm tra quyền
   |      +--> Không đủ quyền: từ chối, không chạy nghiệp vụ
   |
   +--> Log bắt đầu + khởi động đồng hồ
   |
   +--> Chạy nghiệp vụ
   |      +--> Thành công: ghi trạng thái thành công
   |      +--> Lỗi: ghi trạng thái thất bại; truyền lỗi
   |
   +--> Dừng đồng hồ và log kết thúc (kể cả khi lỗi)
   |
   v
Bên gọi nhận kết quả hoặc lỗi
~~~

Sơ đồ chỉ mô tả **một thứ tự chính sách**. Nếu muốn ghi nhận cả yêu cầu bị từ chối, phép ghi log phải bao ngoài kiểm tra quyền. Nếu muốn đo toàn bộ thời gian đi qua lớp bảo vệ, điểm khởi động đồng hồ cũng phải thay đổi.

Nhờ định nghĩa hành vi và vị trí áp dụng riêng, AOP có thể giảm cả scattering và tangling: logic nghiệp vụ vẫn mô tả nghiệp vụ, còn quy tắc dùng chung được quản lý tập trung. Dù vậy, AOP không tự động bảo đảm mọi đường gọi đều được bao phủ hoặc chính sách bảo mật luôn đúng.

## 7. Minh họa Java 17: tập trung logic tại một proxy

Ví dụ dùng **dynamic proxy chuẩn của Java** để diễn giải tư duy AOP ở mức lời gọi qua giao diện. Đây là một kỹ thuật bọc lời gọi, **không phải một hệ thống AOP đầy đủ** với mọi kiểu join point.

Lưu thành `AopConceptDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class AopConceptDemo {
    public interface Task {
        void run();
    }

    public static class OrderTask implements Task {
        @Override
        public void run() {
            System.out.println("BUSINESS create order");
        }
    }

    public static class ReportTask implements Task {
        @Override
        public void run() {
            System.out.println("BUSINESS export report");
        }
    }

    static Task wrap(Task target, String role) {
        return (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[] {Task.class},
                (proxy, method, args) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return method.invoke(target,
                                args == null ? new Object[0] : args);
                    }

                    String name = target.getClass().getSimpleName()
                            + "." + method.getName();

                    if (!"ADMIN".equals(role)) {
                        System.out.println("DENIED " + name);
                        throw new SecurityException("Access denied");
                    }

                    long started = System.nanoTime();
                    System.out.println("START " + name);
                    try {
                        Object result = method.invoke(target,
                                args == null ? new Object[0] : args);
                        System.out.println("SUCCESS " + name);
                        return result;
                    } catch (InvocationTargetException e) {
                        System.out.println("ERROR " + name);
                        throw e.getCause();
                    } finally {
                        System.out.println("END " + name + "; elapsedNs="
                                + (System.nanoTime() - started));
                    }
                });
    }

    public static void main(String[] args) {
        Task order = wrap(new OrderTask(), "ADMIN");
        Task report = wrap(new ReportTask(), "ADMIN");
        order.run();
        report.run();
    }
}
~~~

Chạy:

~~~bash
javac AopConceptDemo.java
java AopConceptDemo
~~~

Dạng đầu ra (hai số `elapsedNs` không cố định):

~~~text
START OrderTask.run
BUSINESS create order
SUCCESS OrderTask.run
END OrderTask.run; elapsedNs=<số nanosecond>
START ReportTask.run
BUSINESS export report
SUCCESS ReportTask.run
END ReportTask.run; elapsedNs=<số nanosecond>
~~~

Hai cụm `<số nanosecond>` là **ký hiệu minh họa**, không phải stdout nguyên văn; chương trình thực tế in số nguyên sau dấu `=`.

Ở đây, cả hai lời gọi `run()` đi qua proxy. Đoạn xử lý chung kiểm tra quyền, ghi log, đo thời gian và chuyển lời gọi đến đối tượng thật. Trong `OrderTask` và `ReportTask`, chỉ còn phần nghiệp vụ; các chính sách phụ trợ không cần sao chép vào mỗi lớp nữa.

**Giới hạn cần hiểu của ví dụ:**

1. Proxy chỉ can thiệp khi bên gọi **thực sự gọi qua proxy** và giao diện `Task`. Gọi trực tiếp `new OrderTask().run()` bỏ qua đoạn xử lý chung.
2. Lời gọi nội bộ từ một phương thức đến phương thức khác của chính đối tượng qua `this` thường không đi qua proxy. Không thể mặc định mọi lời gọi trong hệ thống đã được bảo vệ.
3. Chuỗi `role` chỉ là dữ liệu đơn giản để minh họa. Hệ thống thật phải lấy danh tính từ nguồn **đã xác thực**, đánh giá quyền với hành động và tài nguyên cụ thể; không tin vai trò do người gọi tự khai.
4. Phương thức gọi bằng reflection có thể ném `InvocationTargetException`, chứa lỗi thực của nghiệp vụ. `throw e.getCause()` bảo toàn lỗi gốc thay vì trả một lỗi bọc khác.
5. Đồng hồ chỉ đo **thời gian lời gọi đồng bộ bên trong proxy**. Nếu phương thức khởi phát một tác vụ bất đồng bộ rồi trả về, đây không phải thời gian tác vụ hoàn tất.

## 8. Ba mối quan tâm trông giống nhau nhưng cần chính sách riêng

### 8.1 Ghi nhật ký

Log nên có cấu trúc, tên thao tác, mã tương quan, trạng thái và loại lỗi phù hợp. Log quá chi tiết ở mọi getter/setter sẽ gây nhiễu; log toàn bộ tham số có thể lộ mật khẩu, token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Chính sách ghi log cần giới hạn loại dữ liệu, mức độ và tần suất.

Nhật ký kỹ thuật kiểu “phương thức bắt đầu/kết thúc” **không thay thế sự kiện nghiệp vụ** như “đơn hàng đã thanh toán” hoặc “hợp đồng được phê duyệt”: ý nghĩa sự kiện cần được xác định ở nơi biết nghiệp vụ.

### 8.2 Đo thời gian

Đầu tiên phải định nghĩa **đo cái gì**: chỉ thân phương thức hay cả bước xác thực, có tính thời gian gọi mạng/cơ sở dữ liệu, có tính thời gian chờ hàng đợi không? Elapsed time là khoảng thời gian trôi qua, không đồng nghĩa CPU time. `System.nanoTime()` thích hợp đo chênh lệch trong một tiến trình.

Muốn đo cả đường lỗi thì dừng đồng hồ trong `finally` hoặc cơ chế tương đương. Với công việc bất đồng bộ, muốn biết thời gian hoàn tất phải quan sát đúng sự kiện hoàn tất của tác vụ, không chỉ lúc hàm trả về.

### 8.3 Kiểm soát truy cập

Kiểm tra quyền phải xảy ra **trước tác dụng phụ cần bảo vệ**. Một cơ chế chung giúp thống nhất kiểm tra ở nhiều điểm vào, nhưng nếu có đường gọi không qua điểm đó thì vẫn có khả năng bỏ sót. Cần kiểm thử cả đường được phép, đường bị từ chối, lời gọi trực tiếp/nội bộ và các điểm vào khác.

Bất biến nghiệp vụ cốt lõi (ví dụ không cho phép chi vượt hạn mức, hoặc chỉ chủ sở hữu được thay đổi một tài nguyên) có thể cần được bảo đảm sâu hơn ở ranh giới miền hoặc dữ liệu. **Tách chính sách dùng chung không có nghĩa giao toàn bộ an toàn cho lớp proxy.**

### 8.4 Thứ tự, ngoại lệ và chi phí

Thứ tự **kiểm tra quyền → đo thời gian → log** khác với **đo thời gian → log → kiểm tra quyền** về phạm vi quan sát, sự kiện ghi nhận và mức tiết lộ thông tin. Advice bao quanh phải quy định rõ các nhánh: trước lời gọi, sau thành công, khi lỗi và cuối cùng. Không được vô tình nuốt ngoại lệ, gọi nghiệp vụ hai lần hoặc ghi “SUCCESS” khi nghiệp vụ thất bại.

Một chuỗi nhiều aspect cũng có chi phí: thứ tự phối hợp phức tạp, điểm thực thi thực tế khó quan sát hơn từ nguồn mã và phép đo có thêm overhead. Việc chọn pointcut quá rộng tạo nhiễu; quá hẹp thì bỏ sót.

## 9. Khi nào nên nghĩ đến AOP?

Tư duy AOP phù hợp khi một chính sách có **cùng ý nghĩa ở nhiều ranh giới**, có quy tắc chọn điểm áp dụng rõ ràng, có thể kiểm thử được phạm vi và thứ tự can thiệp, đồng thời việc tách ra vẫn giữ hợp đồng nghiệp vụ (kết quả, ngoại lệ, tác dụng phụ) đúng như trước.

Không nên đưa vào aspect mọi đoạn mã trùng nhau. Quyết định giá bán, chuyển trạng thái đơn hàng, điều kiện của một giao dịch và các quy tắc miền có thể giống ở hình thức nhưng thay đổi độc lập theo nghiệp vụ. Gom chúng thành một chính sách cắt ngang có thể khiến thiết kế khó hiểu và phụ thuộc sai.

Khi thiết kế, hãy hỏi:

- Đây có thật sự là **một chính sách dùng chung**, hay chỉ là các đoạn code giống nhau tình cờ?
- Các điểm nào cần được áp dụng, điểm nào phải loại trừ? Có đường gọi nào có thể bỏ qua không?
- Thứ tự can thiệp, nhánh ngoại lệ và thời gian đo có được định nghĩa rõ không?
- Có giữ nguyên hành vi nghiệp vụ và bao quát đúng các hành động nhạy cảm không?
- Có cách kiểm thử và quan sát chính sách đang hoạt động trong runtime không?

## 10. Tự kiểm tra

Một hệ thống có 40 phương thức, mỗi phương thức đều tự đặt log `START/END`, đồng hồ đo và kiểm tra quyền.

**Hỏi:** Scattering nằm ở đâu? **Đáp:** cùng một chính sách được lặp trong 40 phương thức.

**Hỏi:** Tangling nằm ở đâu? **Đáp:** từng phương thức chứa cả mã nghiệp vụ lẫn log, đo thời gian, kiểm tra quyền.

**Hỏi:** Trích xuất helper đã giải quyết hết chưa? **Đáp:** chưa; 40 phương thức vẫn phải gọi helper và đặt đúng điểm bắt đầu/kết thúc.

**Hỏi:** AOP hỗ trợ phần nào? **Đáp:** tổ chức hành vi phụ trợ và quy tắc chọn điểm thực thi riêng, để áp dụng nhất quán mà giảm mã gắn thủ công ở từng nghiệp vụ.

**Hỏi:** Điều gì phải kiểm chứng sau khi tách? **Đáp:** tất cả điểm cần bảo vệ được bao phủ; kết quả, lỗi, thời gian đo và thứ tự log/quyền đúng; đường bỏ qua proxy hoặc đường bất đồng bộ được xử lý theo yêu cầu thực tế.

**Ghi nhớ:** những thao tác này dễ lặp lại vì chúng phục vụ **chính sách xuyên qua nhiều chức năng** trong khi cách viết thủ công đặt chúng ngay trong từng phương thức. AOP giúp nhìn ra và quản lý **scattering** và **tangling**. Lợi ích chỉ trọn vẹn khi việc chọn điểm áp dụng, thứ tự thực thi, ngoại lệ và ranh giới bảo mật đều được thiết kế và kiểm tra cẩn thận.
