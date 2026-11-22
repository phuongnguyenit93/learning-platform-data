# Mối quan tâm cốt lõi và mối quan tâm cắt ngang trong AOP

Một chương trình vừa phải **làm đúng nghiệp vụ**, vừa phải đáp ứng những yêu cầu vận hành như theo dõi, kiểm soát truy cập, kiểm toán và xử lý lỗi. Lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP) giúp ta suy nghĩ rõ hơn về hai nhóm mối quan tâm đó, nhất là khi cùng một quy tắc xuất hiện ở nhiều nơi.

Bài này tập trung vào cách **nhận diện, phân biệt và tổ chức** mối quan tâm cốt lõi với mối quan tâm cắt ngang. Các thuật ngữ AOP và một ví dụ Java sẽ minh họa cách tách trách nhiệm; chúng không biến mọi quy tắc dùng chung thành một khía cạnh.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích “mối quan tâm” (concern) là gì và vì sao nó khác một hàm hay một lớp.
- Nhận diện mối quan tâm cốt lõi (core concern) và mối quan tâm cắt ngang (cross-cutting concern) theo **trách nhiệm và bối cảnh**, thay vì theo tên gọi.
- Chỉ ra hai vấn đề khi mã xử lý một mối quan tâm nằm rải rác hoặc lẫn vào mã của mối quan tâm khác.
- Mô tả AOP có thể gom chính sách dùng chung quanh những điểm thực thi được chọn như thế nào.
- Phân biệt phần nghiệp vụ cần giữ trong miền nghiệp vụ với phần hạ tầng có thể tách ra; đánh giá những giới hạn và rủi ro khi tách.

## 2. “Mối quan tâm” là gì?

Trong thiết kế phần mềm, **mối quan tâm** là một yêu cầu, quy tắc, trách nhiệm hoặc góc nhìn mà hệ thống phải xử lý. Nó trả lời câu hỏi: “Điều gì cần được bảo đảm hoặc thực hiện?”. Một mối quan tâm có thể trải qua nhiều lớp, nhiều hàm, thậm chí nhiều tiến trình.

Ví dụ ở ứng dụng đặt vé:

- **Giữ chỗ:** kiểm tra ghế còn trống và chuyển ghế sang trạng thái đã giữ.
- **Tính tiền:** áp dụng giá vé, ưu đãi và thuế theo quy tắc kinh doanh.
- **Kiểm toán:** ghi nhận ai đã thực hiện thao tác nhạy cảm và kết quả.
- **Theo dõi:** ghi nhận thời điểm, thời lượng và nguyên nhân thất bại của yêu cầu.
- **Kiểm soát truy cập:** chỉ cho phép người dùng thích hợp thực hiện một thao tác.

Một phương thức có thể phục vụ nhiều mối quan tâm. Ngược lại, một mối quan tâm có thể cần phối hợp nhiều phương thức. Vì thế, **concern là cách chia trách nhiệm**, không đồng nghĩa với “mỗi concern phải có đúng một class”.

### 2.1. Mối quan tâm cốt lõi (core concern)

Đây là trách nhiệm trực tiếp hiện thực **mục đích chính của một chức năng hoặc hệ thống**. Nếu bỏ nó, chức năng không còn làm đúng việc mà người dùng cần.

Với đặt vé: tìm suất chiếu, xác nhận ghế còn chỗ, áp dụng quy tắc giá, giữ ghế và phát hành vé là các công việc cốt lõi. Chúng thể hiện nghiệp vụ cụ thể; không thể thay bằng một thao tác ghi log dùng chung.

Một hệ thống có thể có nhiều mối quan tâm cốt lõi. “Cốt lõi” thường được xác định theo **ranh giới đang xét**: tính giá là cốt lõi của dịch vụ tính giá, nhưng với một công cụ chỉ đo hiệu năng thì chính việc đo đạc có thể là mục đích cốt lõi của công cụ đó.

### 2.2. Mối quan tâm cắt ngang (cross-cutting concern)

Đây là trách nhiệm có **cùng một bản chất hoặc chính sách áp dụng qua nhiều phần chức năng**, nên mã thực hiện nó dễ xuất hiện lặp lại giữa các thành phần vốn có nhiệm vụ chính khác nhau.

Các ví dụ thường gặp:

| Mối quan tâm | Biểu hiện cắt ngang | Điều cần phân biệt |
| --- | --- | --- |
| Ghi log vận hành | Ghi bắt đầu, kết thúc, lỗi của nhiều thao tác | Nội dung sự kiện nghiệp vụ quan trọng có thể thuộc miền nghiệp vụ |
| Theo dõi, đo thời gian, truy vết | Đo nhiều lời gọi, liên kết yêu cầu qua các lớp | Không được làm sai lệch kết quả hay rò rỉ dữ liệu nhạy cảm |
| Kiểm toán | Ghi ai thực hiện hành động được kiểm soát | Quy tắc **sự kiện nào bắt buộc ghi** thường gắn với nghiệp vụ và pháp lý |
| Xác thực/kiểm soát truy cập | Áp chính sách chung tại nhiều điểm vào | Quy tắc quyền sở hữu, hạn mức hoặc trạng thái cụ thể có thể là quy tắc cốt lõi |
| Quản lý ranh giới giao dịch | Bắt đầu, hoàn tất hoặc hoàn tác quanh một đơn vị công việc | Ranh giới nhất quán và bất biến nghiệp vụ cần được xác định đúng |
| Chính sách chịu lỗi | Timeout, giới hạn thử lại ở nhiều lời gọi ngoài hệ thống | Không được thử lại vô điều kiện thao tác có tác dụng phụ |

**Cắt ngang không có nghĩa là phụ, tùy chọn hoặc ít quan trọng.** Kiểm soát truy cập và kiểm toán có thể mang tính sống còn. Tính “cắt ngang” nói về phạm vi tác động và xu hướng phân tán mã, không phải thứ hạng ưu tiên.

### 2.3. Hai chiều của một chức năng

Hãy tưởng tượng chức năng “Đặt vé” và “Hoàn vé” là hai dòng công việc theo chiều dọc. Cả hai đều cần một số chính sách theo chiều ngang:

| Chính sách / chức năng | Đặt vé | Hoàn vé |
| --- | --- | --- |
| Quy tắc nghiệp vụ riêng | Kiểm tra ghế, tính giá, phát hành | Kiểm tra điều kiện hoàn, tính tiền hoàn |
| Ghi log kỹ thuật | Có thể dùng chung | Có thể dùng chung |
| Đo thời lượng | Có thể dùng chung | Có thể dùng chung |
| Ghi nhận thao tác nhạy cảm | Cần xác định sự kiện cần ghi | Cần xác định sự kiện cần ghi |
| Kiểm tra quyền | Điều kiện của hành động đặt vé | Điều kiện của hành động hoàn vé |

Những ô “dùng chung” là ứng viên để gom thành một chính sách; những ô chứa quy tắc riêng của từng hành động vẫn cần quyết định của nghiệp vụ. Bảng chỉ giúp hình dung hai chiều trách nhiệm, **không tự chứng minh mọi dòng ngang đều nên viết bằng AOP**.

## 3. Vì sao việc phân biệt này quan trọng?

Không tách được hai loại trách nhiệm dễ dẫn đến hai vấn đề kinh điển.

### 3.1. Mã bị rải rác (scattering)

Giả sử 20 thao tác đều cần ghi thời điểm bắt đầu, kết quả và thời gian chạy. Nếu mỗi thao tác tự cài bộ ghi giống nhau, chính sách theo dõi bị rải ở 20 nơi. Muốn thay định dạng log hoặc bổ sung mã tương quan yêu cầu, người bảo trì phải tìm và sửa nhiều đoạn.

Hệ quả: dễ bỏ sót một luồng, sai lệch chính sách giữa các nơi và phát sinh lỗi khi thay đổi hàng loạt.

### 3.2. Trách nhiệm bị đan xen (tangling)

Trong một hàm đặt vé, các dòng mã có thể xen kẽ kiểm tra ghế, ghi log, kiểm tra quyền chung, đo thời gian, mở giao dịch, tính tiền và xử lý lỗi kỹ thuật.

Hệ quả: đọc mã khó thấy trình tự nghiệp vụ; kiểm thử nghiệp vụ phải đối diện nhiều phụ thuộc không cần thiết; một thay đổi hạ tầng có nguy cơ tác động mã miền nghiệp vụ.

Hai vấn đề khác nhau: **scattering** là *một trách nhiệm nằm ở nhiều chỗ*; **tangling** là *nhiều trách nhiệm đan vào một chỗ*. Chúng thường xảy ra cùng nhau nhưng không luôn luôn.

### 3.3. Mục tiêu thiết kế

Mục tiêu là **tách những lý do thay đổi**: thay quy tắc tính vé nên chủ yếu sửa miền nghiệp vụ; thay cách theo dõi thao tác nên chủ yếu sửa chính sách theo dõi. Đây là biểu hiện của nguyên tắc phân tách mối quan tâm (separation of concerns, SoC).

Tách mã không có nghĩa tách mọi tương tác: nghiệp vụ vẫn cần thông tin định danh, quyết định phân quyền hoặc kết quả giao dịch khi chúng là dữ kiện cốt yếu. Mối liên hệ phải được biểu đạt qua hợp đồng rõ ràng.

## 4. AOP giúp thực thi chính sách cắt ngang như thế nào?

AOP bổ sung một cơ chế **chọn điểm áp dụng và thực hiện hành vi** mà không buộc mỗi phương thức nghiệp vụ chép cùng chính sách. Để đọc được cơ chế này, cần phân biệt:

- **Join point:** sự kiện có thể can thiệp (chẳng hạn thực thi phương thức), trong phạm vi mà công cụ hỗ trợ.
- **Pointcut:** điều kiện chọn *những join point nào* cần áp dụng; chọn quá rộng thì chạy thừa, quá hẹp thì bỏ sót.
- **Advice:** hành vi áp dụng *trước, sau, khi lỗi hoặc bao quanh* sự kiện đã chọn.
- **Aspect:** đơn vị tập trung chính sách cùng cách chọn và thực hiện hành vi ấy.
- **Weaving/interception:** kỹ thuật kết hợp hành vi với đường chạy, qua mã được biến đổi hoặc ranh giới trung gian tùy công cụ.

Ví dụ, hệ thống đặt vé có thể áp dụng bộ ghi thời gian chung cho các thao tác đã đánh dấu, trong khi nghiệp vụ giữ việc kiểm tra ghế và phát hành vé. Ý nghĩa của “đã áp dụng” phải được **kiểm chứng trên đúng đường gọi**, không chỉ bằng sự tồn tại của pointcut.

```text
Người gọi
  → [Điểm được cơ chế AOP quan sát]
      → [Chính sách trước, nếu áp dụng]
          → [Nghiệp vụ giữ chỗ / hoàn vé]
      ← [Chính sách theo kết quả hoặc ngoại lệ]
  ← Kết quả hoặc lỗi theo hợp đồng
```

Mô hình trên không ấn định một thứ tự cho mọi advice. **Trước, sau thành công, sau lỗi và dọn dẹp bất kể kết quả** có ý nghĩa khác nhau; advice bao quanh còn có thể thay đổi việc có thực hiện nghiệp vụ hay không. Khi kiểm toán, kiểm tra quyền và ranh giới giao dịch cùng áp dụng, thứ tự phải được quy định: ghi thành công *trước* khi kết quả thực sự bền vững không đồng nghĩa đã hoàn tất nghiệp vụ.

Cũng không nên tách “mọi thứ có thể dùng chung” vào aspect: **miền nghiệp vụ vẫn quyết định quy tắc hoàn vé, trạng thái ghế, quyền sở hữu tài nguyên và những sự kiện bắt buộc**. Aspect có thể hỗ trợ cơ chế quan sát hay thực thi một kiểm tra chung, nhưng ranh giới tin cậy và đường gọi ngoại lệ phải được kiểm thử đầy đủ.

## 5. Ví dụ Java 17: giữ nghiệp vụ riêng, bọc chính sách kiểm toán

Ví dụ dùng **dynamic proxy có sẵn trong JDK** để minh họa một cách thực hiện hành vi cắt ngang ở thời gian chạy. Đây là một kỹ thuật bọc lời gọi giao diện, **không phải toàn bộ khả năng của AOP**.

Tạo tệp `ConcernDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ConcernDemo {
    public interface OrderPort {
        String place(String itemCode);
    }

    public static final class OrderService implements OrderPort {
        @Override
        public String place(String itemCode) {
            if (itemCode == null || itemCode.isBlank()) {
                throw new IllegalArgumentException("Mã hàng không hợp lệ");
            }
            return "Đã đặt " + itemCode;
        }
    }

    public static OrderPort withAudit(OrderPort target) {
        return (OrderPort) Proxy.newProxyInstance(
            OrderPort.class.getClassLoader(),
            new Class<?>[] { OrderPort.class },
            (proxy, method, args) -> {
                System.out.println("[AUDIT] bắt đầu " + method.getName());
                try {
                    Object result = method.invoke(target, args);
                    System.out.println("[AUDIT] thành công " + method.getName());
                    return result;
                } catch (InvocationTargetException ex) {
                    System.out.println("[AUDIT] thất bại " + method.getName());
                    throw ex.getCause();
                } finally {
                    System.out.println("[AUDIT] kết thúc " + method.getName());
                }
            }
        );
    }

    public static void main(String[] args) {
        OrderPort orders = withAudit(new OrderService());

        System.out.println(orders.place("A17"));
        try {
            orders.place(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ConcernDemo.java
java ConcernDemo
```

Đầu ra:

```text
[AUDIT] bắt đầu place
[AUDIT] thành công place
[AUDIT] kết thúc place
Đã đặt A17
[AUDIT] bắt đầu place
[AUDIT] thất bại place
[AUDIT] kết thúc place
Lỗi: Mã hàng không hợp lệ
```

**Đọc ví dụ theo trách nhiệm:**

1. `OrderService.place` nắm quy tắc cốt lõi: mã hàng hợp lệ thì nhận đặt, nếu không thì báo lỗi. Đây là ví dụ đơn giản hóa; hệ thống thực còn cần kiểm tra tồn kho, trạng thái, tính nhất quán và nhiều quy tắc khác.
2. `withAudit` áp chính sách ghi nhận cho lời gọi qua `OrderPort`. Mọi lần `orders.place(...)` đều đi qua lớp bọc, kể cả khi phương thức đích ném lỗi.
3. `InvocationTargetException` là lớp bọc do reflection tạo ra; ném lại `ex.getCause()` để người gọi nhận lỗi `IllegalArgumentException` gốc. Khối `finally` vẫn in dòng kết thúc.
4. Dùng `new OrderService().place(...)` trực tiếp sẽ **không** đi qua proxy. Tương tự, một lời gọi từ phương thức đích sang phương thức khác trên chính `this` không tự đi vòng qua proxy. Cơ chế sử dụng và ranh giới can thiệp phải được hiểu rõ.

Đây là log minh họa với `System.out`, chưa phải hệ thống kiểm toán bền vững. Sự kiện kiểm toán thật thường đòi hỏi danh tính có thể tin cậy, dấu thời gian, chính sách lưu trữ, tránh lộ dữ liệu nhạy cảm và cơ chế ghi phù hợp độ tin cậy cần thiết. **Việc quyết định một sự kiện kinh doanh nào bắt buộc được kiểm toán vẫn cần dựa trên quy tắc nghiệp vụ.**

### 5.1. Nếu không dùng một cơ chế AOP thì sao?

Bạn vẫn có thể áp dụng SoC qua **Decorator**, hàm bậc cao, interceptor, middleware hoặc cấu trúc dịch vụ chuyên trách. Một lớp `AuditedOrderPort` tự triển khai `OrderPort`, ủy quyền cho `OrderService` và ghi sự kiện trước/sau cũng tách trách nhiệm hợp lệ.

AOP đặc biệt hữu ích khi cần **khai báo một chính sách và áp nhất quán tại nhiều điểm chọn**. Nhưng không phải việc tách mã nào cũng cần AOP: nếu chỉ có một chỗ rõ ràng, một lời gọi trực tiếp hoặc Decorator dễ đọc có thể phù hợp hơn.

## 6. Quy tắc phân loại: nhìn vào vai trò thay vì tên gọi

Một yêu cầu không có nhãn “cốt lõi” hay “cắt ngang” cố định cho mọi hệ thống. Hãy xét lần lượt:

1. **Mục đích:** Nếu bỏ trách nhiệm này, tác vụ chính có còn đúng theo yêu cầu của người dùng hay nghiệp vụ không?
2. **Phạm vi:** Cùng một chính sách có áp dụng cho nhiều tác vụ thuộc những chức năng khác nhau không?
3. **Lý do thay đổi:** Chính sách có thay đổi tương đối độc lập với quy tắc từng chức năng không?
4. **Dữ kiện cần thiết:** Có thể xác định thời điểm và dữ liệu cần dùng tại ranh giới áp dụng mà không phải ẩn logic nghiệp vụ vào chính sách chung không?
5. **Tính quan sát được:** Người đọc có thể dễ dàng tìm ra nơi chính sách được áp dụng, thứ tự thực thi và kết quả của nó không?

**Ví dụ về vùng ranh giới dễ nhầm:**

| Yêu cầu | Phần có thể cắt ngang | Phần thường thuộc cốt lõi |
| --- | --- | --- |
| Chỉ người dùng hợp lệ được thao tác | Kiểm tra danh tính, chính sách phân quyền chung tại điểm vào | Quy tắc “chỉ chủ vé chưa sử dụng được hoàn vé” |
| Bảo đảm dữ liệu nhất quán | Cơ chế tạo/đóng ranh giới giao dịch | Quyết định những bước nào phải thành công cùng nhau và bất biến cần giữ |
| Ghi nhận thay đổi | Thu thập, truyền, lưu sự kiện theo chính sách chung | Định nghĩa sự kiện “Vé đã được xuất” và dữ kiện nghiệp vụ của nó |
| Kiểm tra dữ liệu | Quy tắc kỹ thuật lặp lại như dữ liệu bắt buộc hoặc giới hạn kích thước | Quy tắc “không hoàn vé sau giờ chiếu” |
| Xử lý lỗi | Chuẩn hóa định dạng lỗi và theo dõi lỗi kỹ thuật | Quyết định lỗi nào cho phép khôi phục, hoàn tiền, hủy giữ chỗ |
| Thử lại | Cơ chế timeout, backoff và số lần thử | Quyết định thao tác có an toàn khi thực thi lặp hay không |

Ví dụ: “mọi yêu cầu đều phải có mã tương quan” là một chính sách kỹ thuật dùng chung. “Một giao dịch chuyển tiền không được làm mất tổng số dư” là bất biến nghiệp vụ; không nên giấu bất biến đó trong một khía cạnh áp dụng theo tên phương thức.

### 6.1. Cắt ngang không đồng nghĩa với lặp mã

Hai hàm cùng gọi `calculatePrice()` chưa đủ để kết luận việc tính giá là cross-cutting. Đó có thể là **miền nghiệp vụ dùng chung**. Lặp mã đơn thuần có thể được xử lý bằng hàm, lớp hoặc mô-đun dùng chung, không cần cơ chế chèn hành vi theo điểm nối.

Ngược lại, một chính sách kỹ thuật mới chỉ áp dụng tại vài điểm vẫn có thể là mối quan tâm cắt ngang nếu nó đi qua nhiều ranh giới chức năng và có lý do thay đổi riêng.

### 6.2. Ranh giới quan trọng hơn vị trí tệp

Đặt log vào một tệp `AuditAspect` không tự bảo đảm SoC nếu tệp đó chứa quy tắc giá vé, điều kiện hoàn vé hoặc quyết định nghiệp vụ ẩn. Ngược lại, một lớp nghiệp vụ gọi rõ ràng đến thành phần kiểm toán qua giao diện có thể là thiết kế sạch dù không sử dụng aspect.

Hãy đánh giá **ai sở hữu quy tắc**, ai chỉ thực hiện cơ chế và hợp đồng nào nối hai bên; tên lớp hay annotation không chứng minh chất lượng thiết kế.

## 7. Các điểm nâng cao khi tổ chức mối quan tâm cắt ngang

### 7.1. Điểm can thiệp và khả năng nhìn thấy hành vi

Hành vi cắt ngang chạy ngoài thân phương thức đích nên người chỉ đọc một hàm có thể không thấy nó. Nếu chọn điểm quá rộng, chính sách có thể ảnh hưởng thao tác ngoài dự kiến; nếu chọn quá hẹp, một đường gọi bị bỏ sót.

Cần có quy ước đặt tên rõ, cấu hình truy xuất được, tài liệu về điểm áp dụng và kiểm thử ở **ranh giới thực sự**. Không nên coi việc đính nhãn hay khai báo quy tắc chọn điểm là bằng chứng hành vi đã chạy.

### 7.2. Thứ tự và kết quả lỗi

Giả sử có kiểm tra quyền, giao dịch, kiểm toán và đo thời gian quanh cùng một thao tác. Việc kiểm tra quyền trước hay sau tác vụ sẽ quyết định có kịp ngăn tác vụ hay không. Việc ghi kiểm toán trước hay sau khi giao dịch xác nhận ảnh hưởng ý nghĩa của “thành công”.

Nếu một hành vi bao quanh bỏ qua lời gọi tiếp, gọi nhiều lần hoặc sửa kết quả, nó có thể thay đổi nghiệp vụ. Cần định nghĩa rõ hành vi nào được phép, đặc biệt khi có lỗi. **Giữ nguyên ngoại lệ và ngữ nghĩa trả về** là mặc định tốt đối với khía cạnh chỉ dùng để quan sát.

### 7.3. Tính nguyên tử, tác dụng phụ và thử lại

Timeout hoặc retry là chính sách thường dùng chung, nhưng thử lại một lời gọi đã gây tác dụng phụ có thể tạo hai đơn hàng hoặc hai lần trừ tiền. Trước khi đặt chính sách thử lại quanh một thao tác, phải biết thao tác có **tính lặp an toàn (idempotency)** hay không, có khóa chống trùng hoặc mã yêu cầu duy nhất hay không, và phạm vi giao dịch được xác định như thế nào.

Cơ chế chung thực hiện retry; **nghiệp vụ xác định điều kiện được retry**. Hai trách nhiệm phối hợp, không thay thế nhau.

### 7.4. Bối cảnh thực thi và bất đồng bộ

Theo dõi yêu cầu có thể cần mã tương quan, danh tính hoặc thông tin truy vết. Khi công việc chuyển sang luồng khác, hàng đợi hoặc tác vụ bất đồng bộ, bối cảnh có thể không tự truyền theo. Một khía cạnh đọc dữ liệu gắn với luồng hiện tại nhưng không có cơ chế truyền bối cảnh sẽ ghi thiếu hoặc sai thông tin.

Chính sách theo dõi phải xác định lúc nào bối cảnh được tạo, truyền, khôi phục và xóa; tránh nhầm bối cảnh giữa các yêu cầu chạy đồng thời. Đây là vấn đề của ranh giới thực thi, không chỉ của cú pháp aspect.

### 7.5. Kiểm soát truy cập và độ tin cậy

Kiểm tra quyền chỉ ở lớp bọc có thể thiếu nếu tồn tại đường gọi khác không đi qua điểm can thiệp. Quy tắc quan trọng còn cần bảo vệ tại ranh giới đáng tin cậy và kiểm thử các đường truy cập khác nhau. Các bất biến sở hữu tài nguyên hoặc trạng thái nghiệp vụ phải có nơi thực thi chắc chắn.

Việc ghi log/kiểm toán cũng cần hạn chế mật khẩu, mã truy cập, dữ liệu cá nhân hoặc toàn bộ tham số nhạy cảm. Tái sử dụng một chính sách rộng làm tăng phạm vi tác động nếu nó thu thập dữ liệu không phù hợp.

### 7.6. Chi phí vận hành và kiểm thử

Mỗi lớp can thiệp có thể thêm lời gọi, cấp phát, đo đạc, truyền bối cảnh hoặc tương tác bên ngoài. Quan trọng hơn, nó thêm **hành vi ẩn đối với mã nghiệp vụ**. Khi kiểm thử, ngoài thử hàm cốt lõi, phải thử điểm áp dụng, thứ tự, nhánh thành công/lỗi và tình huống bỏ qua proxy hoặc weaving.

Một khía cạnh gián tiếp quá phức tạp có thể gây khó khăn lớn hơn phần lặp mã mà nó giải quyết. Vì vậy cần đánh giá chi phí này theo số điểm áp dụng và yêu cầu chất lượng thực tế.

## 8. Khi nào nên, khi nào không nên tách bằng AOP?

**AOP là ứng viên phù hợp** khi cùng một chính sách tương đối đồng nhất phải áp dụng tại nhiều điểm, có điều kiện chọn điểm rõ ràng, thực hiện quanh ranh giới hỗ trợ được và có thể kiểm thử độc lập. Ví dụ: ghi thời lượng của một nhóm lời gọi hoặc gắn mã tương quan cho các điểm vào được quy định.

**Ưu tiên cách thể hiện tường minh** khi hành vi là quy tắc nghiệp vụ cần người đọc nhìn thấy trong luồng chính, khi các điểm áp dụng quá khác nhau, khi thứ tự tác dụng phụ cần kiểm soát từng bước hoặc khi một hàm gọi thành phần dùng chung đã đủ rõ.

Một số lỗi thiết kế thường gặp:

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Xem mọi logic dùng chung là “aspect” | Che khuất quy tắc nghiệp vụ | Phân biệt tái sử dụng chức năng với chính sách cắt ngang |
| Chọn điểm áp dụng quá rộng | Hành vi chạy ở nơi không cần thiết | Thu hẹp quy tắc và kiểm thử từng đường gọi |
| Ẩn quyết định nghiệp vụ trong advice | Khó tìm nguyên nhân và khó bảo vệ bất biến | Giữ quyết định ở miền nghiệp vụ, dùng khía cạnh cho cơ chế chung |
| Nuốt lỗi hoặc sửa giá trị trả về khi chỉ theo dõi | Kết quả khác kỳ vọng của người gọi | Bảo toàn kết quả và chuyển tiếp lỗi gốc |
| Quên lời gọi nội bộ/bỏ qua lớp bọc | Chính sách không chạy trên một số đường | Xác minh thực tế cơ chế proxy hoặc weaving |
| Không xét thứ tự các khía cạnh | Log, giao dịch và quyền sai ngữ nghĩa | Quy định thứ tự và kiểm thử lỗi/thành công |
| Áp retry chung lên thao tác ghi | Tác dụng phụ bị nhân đôi | Phân loại thao tác, thiết lập idempotency và ranh giới an toàn |

## 9. Bài tập phân loại theo bối cảnh

Trong hệ thống đặt vé, hãy xác định **phần cốt lõi**, **phần có thể cắt ngang** và lý do:

1. Tính giá vé theo loại ghế và khuyến mãi.
2. Ghi thời lượng xử lý cho mọi yêu cầu qua cổng API.
3. Chỉ cho hoàn vé khi còn ít nhất 60 phút trước giờ chiếu.
4. Gắn mã truy vết xuyên suốt thao tác đặt vé và hoàn vé.
5. Thử lại việc gọi nhà cung cấp thanh toán sau một lỗi mạng.
6. Mọi thao tác đổi trạng thái vé phải phát sinh sự kiện `TicketStatusChanged`.

**Gợi ý đáp án:**

1. **Cốt lõi.** Công thức giá là quy tắc sản phẩm; có thể tái sử dụng trong mô-đun riêng nhưng không mặc nhiên là khía cạnh.
2. **Có thể cắt ngang.** Cùng một chính sách đo thời gian qua nhiều điểm vào.
3. **Cốt lõi.** Quy tắc hoàn vé quyết định quyền lợi và trạng thái nghiệp vụ; không nên chỉ ẩn trong điểm can thiệp kỹ thuật.
4. **Có thể cắt ngang.** Thu thập và truyền mã truy vết là chính sách quan sát nhiều chức năng, với điều kiện bối cảnh được truyền đúng.
5. **Pha trộn.** Cơ chế thử lại có thể dùng chung, nhưng thao tác thanh toán có được phép thử lại hay không phụ thuộc idempotency, trạng thái giao dịch và hợp đồng nhà cung cấp.
6. **Pha trộn.** “Khi nào và với dữ liệu gì phải có sự kiện” là yêu cầu nghiệp vụ; cơ chế phát hoặc vận chuyển sự kiện có thể là hạ tầng dùng chung. Cần thiết kế để không đánh mất sự kiện khi thay đổi trạng thái.

**Tự kiểm tra:** Với mỗi ví dụ, hãy trả lời thêm “Ai sở hữu quy tắc?”, “Nó phải chạy tại ranh giới nào?”, “Nếu đi đường gọi khác thì sao?” và “Lỗi của nó có được phép làm thất bại nghiệp vụ không?”. Những câu hỏi này thường quan trọng hơn việc đặt tên một lớp là “aspect”.

## 10. Ghi nhớ

- **Cốt lõi** nói hệ thống phải làm gì đúng với nghiệp vụ; **cắt ngang** nói một chính sách cần được áp dụng xuyên qua nhiều phần của hệ thống.
- **Scattering** làm một trách nhiệm rải ở nhiều nơi; **tangling** khiến các trách nhiệm đan xen trong cùng một nơi.
- AOP hỗ trợ diễn đạt **điểm áp dụng + hành vi chung** để tách một số mối quan tâm cắt ngang; khả năng thực tế tùy cơ chế kết hợp khía cạnh.
- **Phân loại phụ thuộc bối cảnh và quyền sở hữu quy tắc.** Dùng chung không tự động là cắt ngang; cắt ngang cũng không có nghĩa kém quan trọng.
- Trước khi chọn AOP, phải xét điểm can thiệp, thứ tự, lỗi, bất đồng bộ, bảo mật, idempotency và khả năng kiểm thử. Một thiết kế tách mối quan tâm tốt vẫn phải giữ luồng nghiệp vụ rõ ràng và đúng đắn.
