# Weaving: quá trình kết hợp aspect với chương trình trong AOP

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**), ta muốn mô tả một số hành vi chung — ví dụ đo thời lượng, kiểm toán, truy vết hay kiểm tra chính sách — một lần và áp dụng chúng tại những điểm xác định của chương trình. **Weaving** là quá trình **kết hợp hành vi được mô tả trong aspect với mã chương trình đích**, tạo ra cách thực thi mà tại các điểm phù hợp, hành vi bổ sung và hành vi chính chạy theo quy tắc đã định.

Cách hiểu quan trọng: định nghĩa một aspect và chọn vị trí áp dụng mới là *ý định*. Weaving là khâu biến ý định ấy thành sự kết hợp **có hiệu lực khi chương trình thực thi**. Tùy cơ chế, quá trình đó diễn ra lúc biên dịch, sau biên dịch, khi tải lớp hoặc lúc chạy. Không có một thời điểm weaving, loại điểm can thiệp hay cách thay đổi mã duy nhất cho mọi công nghệ AOP.

## 1. Mục tiêu bài học

Sau khi học, bạn có thể:

- Mô tả chính xác weaving nhận thông tin gì, xác định điểm áp dụng ra sao và tạo ra hành vi gì.
- Phân biệt **aspect**, **advice**, **join point**, **pointcut**, **target** và **weaver**, đồng thời giải thích mối liên hệ giữa chúng.
- Phân biệt **compile-time weaving**, **binary/post-compile weaving**, **load-time weaving** và các hình thức kết hợp ở thời gian chạy.
- Hiểu sự khác nhau giữa **biến đổi bytecode** và **bao bọc lời gọi qua proxy/interceptor**.
- Phân tích thứ tự các advice, tác động lên kết quả/ngoại lệ, phạm vi có thể bị can thiệp và các tình huống dễ bị bỏ sót.
- Kiểm tra việc weaving thực sự xảy ra, chọn cơ chế phù hợp và nhận diện nguy cơ khi áp chính sách tại nhiều điểm.

## 2. Mô hình trực giác: aspect được kết hợp vào đâu?

Xét ứng dụng bán vé có phương thức `bookTicket()`. Trách nhiệm cốt lõi của phương thức là kiểm tra ghế và tạo đặt chỗ. Những trách nhiệm như theo dõi độ trễ hoặc ghi sự kiện kỹ thuật có thể cần áp dụng cho nhiều thao tác khác nhau.

Nếu chèn thủ công cùng một đoạn đo thời gian ở hàng chục phương thức, mã theo dõi dễ bị **rải rác (scattering)**. Nếu một phương thức vừa giữ ghế, vừa ghi log, vừa định dạng thông tin truy vết, các trách nhiệm dễ **đan xen (tangling)**.

AOP cho phép diễn đạt một chính sách theo kiểu:

> Với những điểm thực thi thỏa điều kiện chọn, hãy thực hiện hành vi bổ sung trước, sau hoặc bao quanh hành vi chính.

Weaving hiện thực sự kết hợp đó.

```text
Mã/chương trình đích                   Định nghĩa aspect
- bookTicket()                         - Quy tắc chọn điểm áp dụng
- cancelTicket()                       - Hành vi đo thời lượng
- calculatePrice()                     - Cách xử lý thành công/lỗi
           \                            /
            \                          /
             +----- Bộ kết hợp (weaver)
                         |
                         v
               Chương trình có hiệu lực
               ┌─────────────────────────┐
Lời gọi ------>│ đo thời điểm bắt đầu     │
               │   bookTicket()          │
               │ đo kết thúc / ghi kết quả│
               └─────────────────────────┘
                         |
                         v
                  Kết quả hoặc lỗi
```

Sơ đồ là **mô hình khái niệm**. Một bộ weaving có thể biến đổi bytecode để tạo mã đã tích hợp; một hệ thống khác có thể kết hợp các bộ chặn lời gọi ở thời gian chạy. Với một số công nghệ, khái niệm weaving được dùng chặt cho biến đổi mã; với một số cách trình bày AOP tổng quát, nó bao gồm cả việc ghép các lớp can thiệp tại thời gian chạy. Cần nói rõ cơ chế đang xét.

### 2.1. Weaving không đồng nghĩa với “gọi thêm một hàm”

Lời gọi trực tiếp `logger.log(...)` trong từng phương thức là mã được lập trình viên đặt vào thủ công. Trong AOP, **pointcut xác định ở đâu** và **advice xác định phải làm gì**; weaving làm chúng tác động đến những điểm thực thi phù hợp. Công việc này có thể tạo bytecode mới, trang bị logic can thiệp khi lớp được định nghĩa hoặc lắp chuỗi lớp bao quanh.

Tuy nhiên, không phải mọi hành vi dùng chung đều cần weaving. Nếu nghiệp vụ chủ động gọi một bộ phận tính giá dùng chung, đó là tái sử dụng chức năng trực tiếp, không tự nhiên trở thành một aspect.

## 3. Các thành phần tham gia weaving

| Thành phần | Vai trò | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Aspect** (khía cạnh) | Đóng gói quy tắc chọn điểm áp dụng và hành vi cắt ngang | Chính sách chung nào được mô tả? |
| **Join point** (điểm nối) | Một điểm trong luồng hoặc cấu trúc thực thi có thể được can thiệp theo cơ chế AOP | Có thể chèn hành vi ở những điểm nào? |
| **Pointcut** (điều kiện chọn điểm nối) | Chọn tập join point phù hợp, có thể kết hợp điều kiện tĩnh và động | Chính sách có hiệu lực ở đâu? |
| **Advice** (hành vi bổ sung) | Mã thực thi trước, sau hoặc bao quanh điểm được chọn | Tại điểm đó cần thực hiện gì? |
| **Target** (đích) | Thành phần cung cấp hành vi chính, ví dụ đối tượng có phương thức đặt vé | Hành vi nghiệp vụ nào được tác động? |
| **Weaver** (bộ kết hợp) | Cơ chế ghép pointcut/advice với điểm áp dụng của chương trình | Sự kết hợp được tạo ra như thế nào, khi nào? |
| **Woven artifact/runtime composition** (sản phẩm đã kết hợp hoặc cấu hình kết hợp khi chạy) | Kết quả sử dụng được sau weaving | Chương trình sẽ thực thi thêm những bước gì? |

Một cách nhớ: **join point là các địa điểm có thể ghé, pointcut là bộ lọc chọn địa điểm, advice là hành động tại địa điểm, aspect là nhóm chính sách, weaver là thành phần thực hiện kết hợp**.

Không nên tráo khái niệm:

- **Pointcut không phải advice.** Điều kiện chọn “mọi lần thực thi tác vụ xử lý đơn hàng” chưa mô tả hành vi cần chèn.
- **Join point không phải pointcut.** Join point là một điểm cụ thể trong mô hình thực thi; pointcut là quy tắc có thể khớp nhiều điểm.
- **Aspect không phải lúc nào cũng là một đối tượng được tạo một lần.** Chu kỳ sống/trạng thái của aspect tùy ngôn ngữ và cơ chế triển khai.
- **Weaver không phải phương thức nghiệp vụ.** Nó đóng vai trò kết hợp các mô tả riêng biệt; một số cơ chế tạo mã mới, một số dựng lớp trung gian.

### 3.1. Cơ chế phải xác định mô hình join point

Ví dụ các loại điểm can thiệp có thể được một ngôn ngữ hoặc công cụ AOP hỗ trợ gồm: thực thi phương thức, lời gọi phương thức, tạo đối tượng, truy cập trường, xử lý ngoại lệ hoặc các điểm điều khiển khác. **Không có cam kết tất cả cơ chế đều hỗ trợ tất cả loại này.**

Điểm **gọi phương thức** và điểm **thực thi thân phương thức** cũng không tương đương: một phương thức có thể được gọi từ nhiều nơi; lựa chọn phía người gọi hoặc phía thân thực thi tạo khả năng quan sát và phạm vi áp dụng khác nhau. Với cơ chế chỉ chặn lời gọi đi qua proxy, một số đường gọi nội bộ không đi qua proxy sẽ không được can thiệp.

## 4. Quá trình weaving hoạt động như thế nào?

Đây là một quy trình khái niệm, chi tiết thực tế có thể khác nhau giữa các công cụ.

1. **Thu thập đầu vào.** Bộ kết hợp nhận mã/lớp đích, định nghĩa aspect, pointcut, advice và thông tin cấu hình hay thứ tự ưu tiên cần thiết.
2. **Xác định join point được hỗ trợ.** Dựa trên mô hình của công nghệ, xác định các điểm có thể chèn hoặc bao bọc hành vi.
3. **Đánh giá điều kiện pointcut.** Các điều kiện tĩnh như tên, kiểu, chữ ký có thể được xác định sớm; điều kiện phụ thuộc dữ liệu thực thi có thể đòi hỏi kiểm tra thêm tại thời gian chạy.
4. **Lập kế hoạch kết hợp.** Quyết định advice nào áp ở điểm nào, cách truyền tham số, kết quả, ngoại lệ và thứ tự giữa nhiều advice.
5. **Thực hiện kết hợp.** Biến đổi mã/bytecode, thiết lập bộ biến đổi lúc tải lớp hoặc tạo chuỗi proxy/interceptor tùy phương án.
6. **Thực thi và quan sát.** Lời gọi thực tế đi qua logic được kết hợp; kiểm tra việc chạy đúng lúc, đúng thứ tự, đúng số lần và giữ hợp đồng của tác vụ chính.

```text
Aspect + Pointcut + Advice        Chương trình đích
            |                            |
            +------------+---------------+
                         |
                    Chọn join point
                         |
                    Ghép hành vi
                         |
        +----------------+----------------+
        |                                 |
  Tạo/sửa mã lớp                     Tạo chuỗi can thiệp
  hoặc bytecode                      tại thời gian chạy
        |                                 |
        +----------------+----------------+
                         |
                   Chạy chương trình
                         |
                Quan sát kết quả/lỗi
```

Điểm chọn **không nhất thiết được quyết định hoàn toàn trước khi chạy**: kiểu chữ ký có thể khớp ngay khi kết hợp mã, còn điều kiện dựa trên giá trị đối số hoặc trạng thái động có thể phải kiểm tra mỗi lần thực thi. Không nên suy luận từ việc “khớp pointcut khi cấu hình” rằng advice chắc chắn chạy trên mọi lời gọi.

## 5. Thời điểm weaving: bốn nhóm thường gặp

Việc phân nhóm giúp chọn giải pháp và dự đoán khả năng quan sát. Tên gọi cụ thể đôi khi khác nhau giữa công nghệ.

| Phương án | Thời điểm | Tác động điển hình | Điều cần đánh đổi |
| --- | --- | --- | --- |
| **Compile-time weaving (CTW)** | Khi biên dịch từ nguồn | Sinh mã hoặc bytecode đã tích hợp hành vi khía cạnh | Cần tích hợp công cụ vào quy trình build, phải quản lý nguồn và bản sinh |
| **Post-compile/binary weaving** | Sau khi đã có bytecode, trước khi chạy hoặc đóng gói | Biến đổi lớp đã biên dịch thành lớp mới | Cần kiểm soát phiên bản và tính tương thích của sản phẩm |
| **Load-time weaving (LTW)** | Khi JVM chuẩn bị định nghĩa một lớp | Chuyển đổi bytecode trong đường tải lớp | Cần cấu hình cơ chế tải/biến đổi và kiểm soát phạm vi lớp |
| **Kết hợp ở thời gian chạy** | Khi tạo đối tượng, dựng proxy/chuỗi bộ chặn hoặc một số dạng instrumentation | Hành vi đi qua lớp trung gian hoặc mã được can thiệp động | Phụ thuộc đường gọi, kiểu đối tượng, khả năng biến đổi và trạng thái đang chạy |

### 5.1. Compile-time weaving

Ở thời điểm biên dịch, bộ kết hợp có thể đọc mô tả aspect và mã nguồn để tạo ra sản phẩm đã mang hành vi bổ sung. Sản phẩm chạy sau đó **không nhất thiết cần một bước tìm điểm áp dụng tương tự tại mỗi lần gọi**; một số điều kiện động vẫn có thể được kiểm tra khi chạy.

Ưu điểm: kết quả có thể được kiểm tra như một sản phẩm build, dễ ghim phiên bản, và không phải thay đổi lớp tại thời điểm tải.

Giới hạn: quy trình build phức tạp hơn; có thể phải dùng bộ biên dịch hoặc bước xử lý đặc biệt. Sửa aspect hoặc pointcut có thể cần build lại. Nếu mã sinh khác với mã nguồn, debugger hoặc stack trace có thể chứa vị trí/khung lời gọi bổ sung.

**Không kết luận compile-time weaving luôn nhanh hơn mọi cách khác.** Chi phí còn phụ thuộc loại advice, độ rộng pointcut, tối ưu của JVM và công việc bên trong advice.

### 5.2. Binary/post-compile weaving

Bộ kết hợp nhận bytecode đã tạo trước đó, chèn hoặc sửa các phần cần thiết và xuất một bản bytecode được kết hợp. Cách này hữu ích nếu có lớp đã biên dịch mà không muốn hoặc không thể biên dịch từ nguồn trong cùng bước.

Cần chú ý: phải bảo toàn khả năng nạp lớp, cấu trúc bytecode hợp lệ, tương thích phiên bản class file, cơ chế xác minh bytecode, việc đóng gói và nguồn gốc artifact. Nếu lớp bị biến đổi nhiều lần ngoài ý muốn, advice có thể bị áp trùng hoặc bản sinh không còn nhất quán.

### 5.3. Load-time weaving

Ở Java, cơ chế gắn với quá trình tải lớp có thể nhận bytecode **trước khi lớp được định nghĩa** và biến đổi nội dung theo quy tắc. Ví dụ, một bộ biến đổi lớp có thể tham gia chuỗi nạp lớp, nhưng mỗi công cụ lại quyết định những lớp nào được phép sửa và bằng cách nào.

Các điểm cần hiểu:

- Thứ tự đăng ký nhiều bộ biến đổi có thể ảnh hưởng kết quả cuối; một biến đổi cần tương thích với biến đổi tiếp theo.
- Lớp đã nạp trước khi cấu hình có hiệu lực thường không tự nhiên được xử lý như lớp sắp nạp.
- Khả năng tác động vào lớp thư viện, lớp thuộc module khác hoặc lớp đặc biệt phụ thuộc quyền, cấu hình và giới hạn của môi trường.
- Công cụ kiểm thử hoặc môi trường đóng gói có thể có đường nạp lớp khác môi trường chạy thật; phải kiểm chứng trong cấu hình thực tế.

Load-time weaving là một cách **thực hiện kết hợp tại giai đoạn nạp lớp**. Nó không đồng nghĩa với mọi tình huống “AOP chạy động”.

### 5.4. Kết hợp ở thời gian chạy: proxy, interceptor và instrumentation

Một hệ thống có thể tạo **proxy** hoặc chuỗi **interceptor** bao quanh đối tượng đích. Người gọi truy cập qua đại diện; đại diện thực hiện advice rồi chuyển tiếp lời gọi. Cách này dễ hình dung và linh hoạt theo cấu hình đối tượng, nhưng nó chỉ can thiệp những lời gọi **thực sự đi qua đại diện**.

Một nhánh công nghệ khác có thể can thiệp mã lúc chạy bằng khả năng instrumentation/biến đổi lớp. Việc biến đổi lại một lớp đã định nghĩa chịu những ràng buộc của máy ảo và công cụ; không được giả định có thể thay đổi tùy ý cấu trúc lớp hoặc mọi điểm nối khi chương trình đang chạy.

Vì vậy:

- **Proxy không phải sửa trực tiếp bytecode của lớp đích**; nó chủ yếu thay đổi đường đi của lời gọi.
- **Instrumentation không tự động là một hệ AOP hoàn chỉnh**; vẫn phải có mô hình chọn join point, advice, thứ tự và ngữ nghĩa kết hợp.
- **Weaving không đồng nghĩa với chạy lại**; kết hợp một lần và gọi nhiều lần là hai hoạt động khác nhau.

### 5.5. Sơ đồ thời điểm

```text
Mã nguồn
   |
   |  [Compile-time weaving có thể diễn ra]
   v
Bytecode ban đầu
   |
   |  [Post-compile/binary weaving có thể diễn ra]
   v
Bytecode để đóng gói/chạy
   |
   |  [Load-time weaving có thể diễn ra trước khi định nghĩa lớp]
   v
Lớp được JVM nạp và định nghĩa
   |
   |  [Có thể dựng proxy/interceptor; một số cơ chế hỗ trợ can thiệp động]
   v
Lời gọi thực thi qua đường đã kết hợp
```

Đây là **các vị trí có thể lựa chọn**, không phải chuỗi bước bắt buộc phải sử dụng hết. Một hệ thống có thể dùng một phương án hoặc phối hợp một số phương án nếu chúng tương thích và thực sự cần thiết.

## 6. Weaving làm thay đổi đường thực thi ra sao?

Giả sử một điểm có `before`, `after returning`, `after throwing`, `finally` và `around` theo những ngữ nghĩa mà công cụ hỗ trợ.

### 6.1. Hành vi trước/sau

- **Before:** chạy trước tác vụ đích; nếu chặn bằng lỗi hoặc quyết định đặc biệt, đích có thể không được thực thi.
- **After returning:** chạy khi đích hoàn tất theo đường thành công; “return” không bao gồm ngoại lệ.
- **After throwing:** chạy theo đường lỗi; không mặc nhiên chạy khi thành công.
- **After/finally:** thường nhằm xử lý cuối cùng dù thành công hay thất bại; phải xem ngữ nghĩa của công cụ cụ thể.
- **Around:** bao quanh điểm được chọn và có thể điều phối việc chuyển tiếp vào thao tác đích; mạnh nhất và có nguy cơ thay đổi hành vi chính lớn nhất.

Khái niệm **proceed** thường biểu đạt bước “tiếp tục chuỗi thực thi bên trong” của around advice. Khi chính sách chỉ nhằm ghi log hoặc đo thời gian, lựa chọn an toàn thường là chuyển tiếp **đúng một lần** và bảo toàn kết quả/ngoại lệ. Một số cơ chế cho phép bỏ qua, thay đối số, gọi nhiều lần hoặc thay kết quả; đây là năng lực phải dùng có chủ đích, không phải mặc định vô hại.

### 6.2. Thứ tự các khía cạnh

Hai khía cạnh A và B cùng bao quanh công việc T có thể kết hợp như sau:

```text
A(
   B(
      T()
   )
)
```

Nếu cả A và B đều thực hiện một hành vi trước, một hành vi sau khi thành công và một hành vi cuối cùng, thứ tự trực giác là:

```text
A before
B before
T
B after returning
B finally
A after returning
A finally
```

Đây là thứ tự **theo cấu trúc lồng A(B(T))**, không phải một quy tắc ưu tiên mặc định cho mọi công nghệ. Nếu đổi thứ tự kết hợp thành B(A(T)), đường thực thi cũng đổi.

Trường hợp có ngoại lệ, thao tác “sau thành công” không chạy. Hành vi “sau lỗi” và “finally” chỉ đúng theo hợp đồng của từng advice; mã người dùng bên trong advice cũng có thể ném lỗi mới. Khi có nhiều aspect, cần xác định rõ thứ tự và chủ ý muốn điều khiển lỗi như thế nào.

### 6.3. Điểm cần giữ nguyên trong hợp đồng chương trình

Một chính sách theo dõi thuần túy không nên vô tình:

- Thay kết quả `return` của nghiệp vụ.
- Nuốt ngoại lệ, đổi lỗi thành kết quả thành công hoặc tạo lỗi mới chỉ do format log.
- Gọi công việc chính thêm lần nữa.
- Chỉnh sửa dữ liệu có thể quan sát được mà không được cho phép.
- Đưa thông tin bí mật trong tham số hoặc kết quả vào bản ghi.

Weaving tăng khả năng tái sử dụng nhưng **không bãi bỏ hợp đồng** giữa người gọi và thành phần nghiệp vụ.

## 7. Ví dụ Java 17: kết hợp hai hành vi quanh một phương thức

Ví dụ sử dụng **JDK dynamic proxy** để tạo hai lớp bao quanh cùng một đối tượng. Mục tiêu là thấy rõ **thứ tự ghép** và hiệu quả trên đường thành công/lỗi. Proxy là một hình thức kết hợp lời gọi **ở thời gian chạy**, không minh họa việc sửa bytecode; nó cũng không đại diện cho mọi join point mà các bộ weaving khác có thể hỗ trợ.

Lưu chương trình dưới tên `WeavingDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Locale;

public class WeavingDemo {
    interface Task {
        String run(String input);
    }

    static final class CoreTask implements Task {
        @Override
        public String run(String input) {
            if (input == null || input.isBlank()) {
                throw new IllegalArgumentException("Dữ liệu rỗng");
            }
            return input.trim().toUpperCase(Locale.ROOT);
        }
    }

    private static Object invokeTarget(
            Method method, Object target, Object[] arguments) throws Throwable {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static Task weave(String name, Task target) {
        return (Task) Proxy.newProxyInstance(
            Task.class.getClassLoader(),
            new Class<?>[] { Task.class },
            (proxy, method, arguments) -> {
                if (!method.getName().equals("run")) {
                    return invokeTarget(method, target, arguments);
                }

                System.out.println(name + " before");
                try {
                    Object result = invokeTarget(method, target, arguments);
                    System.out.println(name + " after returning");
                    return result;
                } catch (Throwable ex) {
                    System.out.println(name + " after throwing");
                    throw ex;
                } finally {
                    System.out.println(name + " finally");
                }
            }
        );
    }

    public static void main(String[] args) {
        Task task = weave("A", weave("B", new CoreTask()));

        System.out.println("Kết quả: " + task.run("  aop  "));

        try {
            task.run(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Bắt lỗi: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac WeavingDemo.java
java WeavingDemo
```

Kết quả dự kiến chính xác:

```text
A before
B before
B after returning
B finally
A after returning
A finally
Kết quả: AOP
A before
B before
B after throwing
B finally
A after throwing
A finally
Bắt lỗi: Dữ liệu rỗng
```

**Giải thích:**

1. `CoreTask` là phần nghiệp vụ cốt lõi: từ chối chuỗi trắng; với chuỗi hợp lệ, cắt khoảng trắng ở hai đầu và chuyển thành chữ hoa.
2. `weave("B", new CoreTask())` tạo đại diện B quanh đích. `weave("A", ...)` tiếp tục đặt A bên ngoài B. Vì vậy lời gọi chạy theo A → B → đích, và các hành vi sau đó quay từ B ra A.
3. `method.getName().equals("run")` là **bộ lọc minh họa** vị trí can thiệp. Nó đủ cho ví dụ một phương thức `run`; một bộ pointcut thực tế có thể xét chữ ký, kiểu đích, annotation, điều kiện động và nhiều tiêu chí khác.
4. `invokeTarget` bóc `InvocationTargetException` do reflection tạo ra để chuyển tiếp nguyên nhân thật. Vì vậy `IllegalArgumentException` gốc đi ra qua B rồi A và đến người gọi.
5. Mọi proxy chỉ can thiệp **lời gọi được thực hiện qua proxy**. Gọi thẳng `new CoreTask().run(...)` sẽ không chạy A/B. Một lời gọi nội bộ trên `this` của đối tượng đích cũng không tự động vòng qua chuỗi proxy.
6. Trong mã minh họa, `Throwable` được bắt để ghi nhánh lỗi rồi ném lại; điều này giúp quan sát lỗi nhưng **không có nghĩa mọi lỗi đều nên được xử lý, phục hồi hoặc ghi đầy đủ nội dung** trong chương trình thật.

Các điểm giới hạn của ví dụ:

- JDK proxy này dựa trên **giao diện** `Task`, chặn lời gọi phương thức qua proxy; nó không tự chặn mọi `private`, `static`, constructor hay truy cập trường của `CoreTask`.
- Ví dụ chỉ chọn tên `run`, chưa phải ngôn ngữ pointcut đầy đủ.
- Nối A/B bằng lời gọi `weave` là cấu hình tường minh; một hệ thống AOP có thể tính toán cấu hình và thứ tự từ quy tắc khác.
- Hàm `invokeTarget` chỉ bóc ngoại lệ bọc do reflection. Nếu một cơ chế proxy khác phải chuyển ngoại lệ được kiểm tra (checked exception) không nằm trong khai báo phương thức, hành vi chuyển tiếp có thể chịu giới hạn của hợp đồng giao diện.
- Log vào `System.out` nhằm minh họa thứ tự; một hệ thống quan sát thật cần cân nhắc độ trễ, độ tin cậy và dữ liệu nhạy cảm.

## 8. Sự khác biệt giữa biến đổi bytecode và proxy

Đây là phần đặc biệt quan trọng khi giải thích cơ chế weaving.

| Câu hỏi | Biến đổi mã/bytecode | Proxy/interceptor |
| --- | --- | --- |
| Đơn vị được thay đổi | Nội dung mã hoặc định nghĩa lớp trong phạm vi hỗ trợ | Đường lời gọi qua một đối tượng đại diện/chuỗi bộ chặn |
| Lời gọi trực tiếp lên đích | Có thể thấy hành vi đã ghép nếu điểm tương ứng thực sự được biến đổi | Bỏ qua proxy thì thường bỏ qua logic của proxy |
| Lời gọi nội bộ từ `this` | Có thể can thiệp nếu join point nằm trong mã đã biến đổi và được hỗ trợ | Thường không đi qua proxy ngoài |
| Constructor/trường | Phụ thuộc công cụ và loại join point hỗ trợ | JDK dynamic proxy thông thường không chặn các điểm này của lớp đích |
| Thời điểm thiết lập | Khi biên dịch, sau biên dịch, lúc tải hoặc đôi khi lúc chạy | Khi tạo proxy/chuỗi và đưa đại diện vào đường sử dụng |
| Chi phí, giới hạn | Biến đổi/kiểm chứng bytecode, tương thích JVM, ánh xạ debug | Chi phí lớp trung gian, định tuyến lời gọi, danh tính proxy, phạm vi giao diện/kiểu |
| Cách kiểm chứng | Kiểm tra artifact/lớp đã biến đổi và hành vi khi chạy | Đảm bảo người gọi nhận đúng proxy và quan sát lời gọi đi qua nó |

Vì vậy không thể dựa vào từ “weaving” rồi kết luận “mọi lời gọi phương thức đều có advice”. Khả năng thực tế phụ thuộc **loại join point, cơ chế kết hợp và đường thực thi**.

### 8.1. Proxy và danh tính đối tượng

Một proxy có thể khác đối tượng đích về `getClass()`, việc so sánh tham chiếu `==`, phương thức `equals`, `hashCode` hoặc `toString`, tùy thiết kế. Chương trình phụ thuộc cụ thể vào danh tính/kiểu của đối tượng phải cân nhắc trước khi đưa proxy vào. Không nên dùng tiêu chí tên phương thức đơn giản để áp chính sách lên các phương thức nền tảng đó một cách vô ý.

### 8.2. Class loading và module

Một bộ biến đổi bytecode trong JVM phải tuân thủ định dạng class file, kiểm chứng kiểu, quyền truy cập và giới hạn của cơ chế biến đổi. Kể cả khi aspect khớp pointcut, môi trường chạy vẫn có thể không cho truy cập hoặc sửa một lớp nhất định. Trong hệ thống module hóa, quyền truy cập/khả năng mở gói cũng có thể ảnh hưởng instrumentation và reflection.

Khả năng **retransform/redefine** một lớp đã được nạp, khi được cung cấp, cũng có giới hạn riêng; không thể suy ra rằng mọi thay đổi cấu trúc lớp đều hợp lệ. Mỗi cơ chế phải được kiểm tra bằng tài liệu và thực nghiệm của công cụ cụ thể.

## 9. Weaving nâng cao: nhiều khía cạnh, điều kiện động và tính đúng đắn

### 9.1. Xung đột và tính kết hợp

Giả sử cùng một thao tác được bao bởi kiểm soát quyền, mở giao dịch, kiểm toán và đo thời gian. Nếu kiểm tra quyền được đặt **bên trong** bước tạo giao dịch, có thể tạo giao dịch cho yêu cầu không hợp lệ; nếu đo thời gian **bên ngoài** một chuỗi thử lại, số đo bao gồm mọi lần thử; nếu đo thời gian **bên trong**, mỗi lần thử có số đo riêng.

Các chính sách không phải lúc nào giao hoán:

```text
Timing(Retry(Operation))   -> đo toàn bộ vòng thử lại
Retry(Timing(Operation))   -> đo riêng từng lần thử
```

Thứ tự tương tự ảnh hưởng tới việc ghi sự kiện kiểm toán trước hay sau khi giao dịch hoàn tất. Cần quy định **thứ tự precedence**, đơn vị công việc, những nhánh lỗi và thời điểm xem kết quả là thành công.

### 9.2. Pointcut động và phạm vi điều khiển

Một điều kiện dựa trên chữ ký có thể được xác định sớm; điều kiện phụ thuộc đối số, trạng thái đối tượng hoặc đường thực thi có thể được kiểm tra khi chạy. Các bộ lọc động mở rộng tính biểu đạt nhưng có thể thêm chi phí tại mỗi lời gọi và làm việc suy luận khó hơn.

Điều kiện điểm áp dụng nên rõ, có phạm vi hẹp và dùng dữ liệu tối thiểu. Tên phương thức phù hợp không đảm bảo chính sách đúng với toàn bộ phiên bản hoặc ngữ nghĩa nghiệp vụ của phương thức.

### 9.3. Aspect có trạng thái và đồng thời

Một bộ theo dõi có trạng thái dùng chung có thể bị nhiều luồng gọi cùng lúc. Nếu advice ghi biến đếm, tổng thời gian hoặc bối cảnh của “yêu cầu hiện tại”, phải hiểu aspect được tạo theo phạm vi nào và dùng cơ chế đồng bộ/phân tách trạng thái tương ứng.

Không lưu định danh yêu cầu vào một biến instance dùng chung rồi mặc định nó thuộc về đúng lời gọi. Với tác vụ bất đồng bộ, bối cảnh gắn luồng cũng có thể thất lạc khi công việc chuyển luồng. Weaving chỉ xác định hành vi được áp dụng ở những điểm phù hợp; **nó không tự giải quyết bài toán truyền bối cảnh và an toàn đồng thời**.

### 9.4. Idempotency và advice quanh thao tác có tác dụng phụ

Một around advice có thể được thiết kế để gọi lại thao tác khi gặp lỗi tạm thời. Nhưng nếu đích đã gửi một lệnh thanh toán rồi lỗi khi nhận phản hồi, gọi lại có thể tạo giao dịch trùng. Cơ chế retry là trách nhiệm chung; **quyết định thao tác có an toàn để retry hay không** là hợp đồng nghiệp vụ/kết nối bên ngoài.

Không thiết kế advice thử lại chỉ theo loại lỗi mà bỏ qua khả năng tác dụng phụ đã xảy ra. Khi cần, sử dụng mã idempotency, phát hiện trùng, xác định ranh giới giao dịch và các trạng thái không chắc chắn.

### 9.5. Vấn đề weave trùng hoặc không weave

Hai lỗi ngược nhau thường xảy ra:

- **Không áp dụng:** pointcut quá hẹp, lớp đã được nạp, đường gọi đi thẳng tới target hoặc cơ chế không hỗ trợ loại join point.
- **Áp dụng lặp:** hai cơ chế cùng chặn một điểm, chạy qua nhiều proxy, hoặc artifact đã được biến đổi rồi bị biến đổi thêm lần nữa ngoài dự kiến.

Kết quả có thể là thiếu kiểm toán, ghi log hai lần, đo sai thời gian hoặc lặp tác dụng phụ. Muốn kiểm chứng, cần xem **số lần advice chạy trên một lời gọi thực tế**, không chỉ kiểm tra một dòng cấu hình có tồn tại.

### 9.6. Bảo mật và hành vi ẩn

Một hệ thống không nên dựa duy nhất vào lớp can thiệp có thể bỏ qua để bảo vệ bất biến quan trọng. Nếu một đường gọi không qua proxy hoặc một lớp không được weaving, thao tác nhạy cảm vẫn có thể chạy. Cần đặt quy tắc bảo vệ ở ranh giới đáng tin cậy và kiểm thử mọi đường truy cập được hỗ trợ.

Ngoài ra, advice ghi log/kiểm toán không được tự ý ghi mật khẩu, khóa bí mật, token truy cập hoặc nội dung riêng tư. Một pointcut rộng áp khắp hệ thống có thể làm phạm vi thu thập dữ liệu trở nên rất lớn.

## 10. Kiểm thử và chẩn đoán khi weaving không chạy như mong đợi

Nên kiểm tra theo thứ tự sau:

1. **Điểm dự định có được hỗ trợ không?** Xác minh mô hình join point: thực thi phương thức, lời gọi, constructor, trường hay điểm khác.
2. **Pointcut có khớp điểm thực tế không?** Kiểm tra chữ ký, kiểu, cấu trúc kế thừa, điều kiện động và các quy tắc loại trừ.
3. **Weaver có tham gia đúng giai đoạn không?** Với compile-time/binary weaving, kiểm tra artifact được dùng; với load-time weaving, kiểm tra thời điểm nạp lớp; với proxy, kiểm tra đối tượng mà người gọi thực sự sử dụng.
4. **Các advice có chạy đúng thứ tự và số lần không?** Kiểm tra thành công, lỗi, gọi lồng, đa luồng và tác vụ bất đồng bộ.
5. **Kết quả có được bảo toàn không?** Đối chiếu giá trị trả về, ngoại lệ gốc, trạng thái và tác dụng phụ của tác vụ đích.
6. **Có ảnh hưởng vận hành không?** Đo thời lượng thực tế, lượng log sinh ra và ảnh hưởng của truy vết, đồng thời kiểm tra việc loại bỏ dữ liệu nhạy cảm.

Với các cơ chế biến đổi mã, debugger và stack trace có thể hiển thị khung lời gọi hoặc thông tin nguồn bổ sung. Với proxy, cần biết chuỗi đại diện thực sự nhận lời gọi. Việc đọc một phương thức nghiệp vụ **không đủ để biết toàn bộ hành vi**, vì advice có thể được định nghĩa ở nơi khác.

### 10.1. Một ma trận kiểm thử nhỏ nhưng có ý nghĩa

| Tình huống | Kỳ vọng cần kiểm tra |
| --- | --- |
| Lời gọi thuộc pointcut, thành công | Advice chạy đúng số lần, đúng thứ tự, kết quả không đổi |
| Lời gọi thuộc pointcut, đích ném lỗi | Nhánh lỗi/finally đúng, ngoại lệ không bị nuốt |
| Lời gọi ngoài pointcut | Không có advice ngoài phạm vi |
| Lời gọi nội bộ hoặc đường bypass | Ghi nhận đúng giới hạn của cơ chế đang dùng |
| Hai aspect cùng áp dụng | Thứ tự kết hợp khớp quy tắc định trước |
| Lời gọi đồng thời/bất đồng bộ | Bối cảnh, dữ liệu đo đạc không lẫn nhau |
| Khởi động/load lại/artifact mới | Phương thức ghép còn hiệu lực và không bị lặp |

Kiểm thử chỉ chạy trực tiếp lớp đích thường **không chứng minh** một cơ chế proxy đã được ghép đúng. Tương tự, kiểm thử chỉ nhìn vào cấu hình chưa chứng minh mã đã biến đổi chính xác. Hãy kiểm tra ở ranh giới sử dụng thực tế.

## 11. Khi nào lựa chọn mỗi phương án kết hợp?

Hãy ra quyết định dựa trên những câu hỏi cụ thể:

- **Phạm vi điểm can thiệp:** chỉ cần chặn những lời gọi qua giao diện, hay cần thao tác bên trong lớp như constructor/truy cập trường?
- **Quyền kiểm soát mã:** có thể biên dịch lại nguồn không, hay chỉ có artifact đã biên dịch?
- **Thời điểm thay đổi chính sách:** có thể đóng gói lại và triển khai lại, hay cần điều chỉnh động?
- **Môi trường chạy:** có thể cấu hình đường tải lớp hoặc instrumentation không? Các giới hạn module và quyền truy cập là gì?
- **Khả năng quan sát:** người bảo trì có tra được điều kiện áp dụng, thứ tự và nơi chèn hành vi không?
- **Bảo toàn hợp đồng:** thao tác có tác dụng phụ, ranh giới giao dịch, ngoại lệ, đồng thời và an toàn dữ liệu đã được xem xét chưa?

**Ví dụ định hướng:**

- Một công cụ phân tích tĩnh có thể dùng compile-time/binary weaving khi muốn sản phẩm build tự chứa cơ chế theo dõi.
- Một môi trường cần can thiệp khi lớp được nạp có thể cân nhắc load-time weaving, với điều kiện cấu hình và kiểm chứng lớp được kiểm soát.
- Một ứng dụng có giao diện rõ và chỉ cần chặn lời gọi thông qua đối tượng đại diện có thể dùng proxy/interceptor, khi mọi nơi sử dụng đều có thể được cung cấp đúng đối tượng đại diện.

Đó là **tiêu chí lựa chọn**, không phải bảo đảm mỗi phương án có sẵn trong mọi nền tảng.

## 12. Sai lầm thường gặp

| Hiểu sai | Sự thật cần nhớ |
| --- | --- |
| “Viết aspect là chương trình tự động chạy advice.” | Cần cơ chế kết hợp đang hoạt động và điểm được chọn thực sự khớp. |
| “Weaving chỉ xảy ra khi biên dịch.” | Có nhiều thời điểm kết hợp, gồm sau biên dịch, khi nạp lớp hoặc qua trung gian ở thời gian chạy. |
| “Proxy sẽ can thiệp mọi lời gọi tới một lớp.” | Chỉ các đường gọi đi qua proxy, trong phạm vi phương thức được hỗ trợ, mới bị chặn. |
| “Bất cứ join point nào cũng được mọi weaver hỗ trợ.” | Mỗi công cụ có mô hình điểm can thiệp riêng. |
| “Advice trước/sau không thể đổi hành vi chính.” | Advice có thể gây lỗi, thay đổi trạng thái; around còn có khả năng ảnh hưởng luồng tiếp tục/kết quả. |
| “Hai aspect cùng áp dụng thì thứ tự không quan trọng.” | Thứ tự quyết định giao dịch, quyền, đo thời gian, kiểm toán và retry. |
| “Khớp pointcut là đã kiểm chứng weaving.” | Cần xác nhận artifact/đường gọi và hành vi thực tế, gồm cả nhánh lỗi. |
| “Weaving càng rộng càng dễ bảo trì.” | Phạm vi quá rộng tăng hành vi ẩn, chi phí và rủi ro áp sai. |

## 13. Bài tập áp dụng

### Bài tập 1 — Xác định thành phần

Cho quy tắc: “Tại mọi lần thực thi chức năng xử lý đơn hàng, ghi thời điểm bắt đầu và kết thúc, kể cả khi có lỗi”.

Hãy xác định: đâu là điểm nối khả dĩ, đâu là pointcut, đâu là advice, đâu là đích và bộ weaving phải tạo ra điều gì?

**Gợi ý trả lời:** Join point khả dĩ là điểm thực thi các phương thức xử lý đơn hàng *nếu công nghệ hỗ trợ loại điểm này*; pointcut lọc đúng nhóm phương thức; advice thực hiện đo và ghi thời điểm; đích là các phương thức nghiệp vụ; weaving ghép hành vi đó vào những điểm khớp sao cho đường thành công/lỗi đều được theo dõi. Thời điểm và kỹ thuật kết hợp phụ thuộc cơ chế được chọn.

### Bài tập 2 — Kiểm tra thứ tự

Cho cấu trúc `Audit(Timeout(Operation))`, trong đó mỗi lớp bao quanh ghi “before” và “finally”. Hãy ghi thứ tự khi tác vụ kết thúc bình thường, rồi so với `Timeout(Audit(Operation))`.

**Gợi ý trả lời:** Với cấu trúc thứ nhất: `Audit before → Timeout before → Operation → Timeout finally → Audit finally`. Với cấu trúc thứ hai: `Timeout before → Audit before → Operation → Audit finally → Timeout finally`. Hành vi timeout cụ thể có thể khác nhau theo công cụ; thứ tự này chỉ mô tả cách lồng hai lớp.

### Bài tập 3 — Chẩn đoán thiếu advice

Một ứng dụng khởi tạo `Task original = new CoreTask()`, sau đó tạo `Task wrapped = weave("Trace", original)`. Gọi `wrapped.run(...)` có log, còn `original.run(...)` không có. Có lỗi trong pointcut không?

**Gợi ý trả lời:** Chưa chắc. Nếu dùng cơ chế bọc lời gọi qua proxy như ví dụ, đây là hành vi đúng với phạm vi can thiệp. Lời gọi đến `original` bỏ qua proxy. Cần chỉnh đường cung cấp phụ thuộc hoặc chọn cơ chế có phạm vi can thiệp phù hợp nếu yêu cầu bắt buộc mọi đường gọi đều được theo dõi.

### Bài tập 4 — So sánh thời điểm

Bạn chỉ sở hữu các tệp `.class` đã biên dịch, nhưng cần áp một chính sách mới trước khi đưa ứng dụng vào vận hành. Bạn có thể dùng compile-time weaving từ nguồn đang có không? Phương án nào đáng xem xét và cần kiểm chứng gì?

**Gợi ý trả lời:** Nếu không có nguồn thì không thể mặc định thực hiện quy trình biên dịch từ nguồn theo kiểu thông thường. Có thể xem xét binary weaving hoặc load-time weaving nếu công cụ, quyền truy cập và bytecode cho phép. Phải kiểm chứng tính tương thích class file, danh sách lớp được can thiệp, hành vi/ngoại lệ và artifact thật sự được chạy.

### Bài tập 5 — Nhận diện ảnh hưởng nghiệp vụ

Một advice tự động retry `chargeCard()` ba lần nếu xảy ra timeout. Cơ chế weaving có bảo đảm đúng nghiệp vụ không?

**Gợi ý trả lời:** Không. Cơ chế chỉ áp chính sách retry tại điểm đã chọn. Timeout không chứng minh lần thanh toán trước chưa thành công; cần điều kiện retry an toàn, idempotency, mã yêu cầu và quy tắc xử lý trạng thái không chắc chắn. Đây là lý do việc kết hợp kỹ thuật phải tôn trọng hợp đồng nghiệp vụ.

## 14. Ghi nhớ

- **Weaving là quá trình kết hợp aspect với chương trình** để advice được thực thi tại những join point phù hợp với pointcut.
- Aspect mô tả chính sách; pointcut chọn nơi áp dụng; advice mô tả hành vi; **weaver biến mô tả đó thành sự kết hợp có hiệu lực**.
- **Thời điểm kết hợp** có thể là lúc biên dịch, sau biên dịch, khi tải lớp hoặc ở thời gian chạy. Các phương án khác nhau về khả năng can thiệp, đường gọi và công cụ cần thiết.
- **Proxy là bao bọc lời gọi; biến đổi bytecode là can thiệp mã lớp.** Không được suy luận khả năng của phương án này sang phương án kia.
- **Thứ tự, điều kiện động, nhánh lỗi, đồng thời và tác dụng phụ** quyết định weaving có giữ đúng hợp đồng chương trình hay không.
- Luôn kiểm chứng **điểm áp dụng thật, đường gọi thật và kết quả thực**, thay vì chỉ nhìn vào tên aspect hay cấu hình.
