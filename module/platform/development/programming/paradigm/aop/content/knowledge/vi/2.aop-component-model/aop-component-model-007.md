# Phân biệt chọn vị trí, truyền ngữ cảnh và thực hiện hành vi trong AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), muốn đưa ghi nhật ký, đo thời gian hoặc kiểm soát quyền ra khỏi mã nghiệp vụ, ta cần giải quyết ba câu hỏi khác nhau:

1. **Chọn vị trí:** những điểm nào trong quá trình chương trình chạy phải chịu tác động?
2. **Truyền ngữ cảnh:** tại điểm đã chọn, hành vi bổ sung cần những thông tin gì của lần thực thi hiện tại?
3. **Thực hiện hành vi:** sau khi có điểm và ngữ cảnh, mã bổ sung làm gì trước, sau hoặc bao quanh nghiệp vụ?

Trong thuật ngữ AOP, việc chọn vị trí liên quan đến **join point** và **pointcut**; việc cung cấp dữ liệu cho mã bổ sung là **context exposure/binding**; còn mã thực hiện tác động là **advice**. Một **aspect** nhóm các quy tắc và hành vi cho cùng mối quan tâm cắt ngang. Đây là ba trách nhiệm có thể phối hợp, nhưng phải phân biệt rõ để thiết kế, kiểm thử và sửa lỗi.

## 1. Ví dụ dẫn nhập: cùng một lời gọi, ba câu hỏi

Một hệ thống đặt chỗ có `reserve(user, seats)` và `status(id)`. Ta muốn ghi log cho mỗi lần đặt chỗ, nhưng không ghi cùng loại log cho thao tác xem trạng thái.

| Trách nhiệm | Câu hỏi cụ thể | Cách trả lời trong ví dụ |
| --- | --- | --- |
| Chọn vị trí | Lời gọi nào kích hoạt chính sách? | Chỉ thao tác `reserve` |
| Truyền ngữ cảnh | Mã log cần dữ liệu nào? | Tên thao tác, `user`, `seats`, kết quả hoặc ngoại lệ |
| Thực hiện hành vi | Khi kích hoạt cần làm gì? | In `BEFORE`, gọi nghiệp vụ, in `AFTER` khi thành công hoặc `ERROR` khi lỗi |

Điểm mấu chốt là: **bộ chọn không tự ghi log**, **context không tự quyết định quyền**, và **advice không tự biết mình nên áp dụng ở đâu** nếu không được kết hợp với cơ chế chọn điểm.

~~~text
Một lời gọi phát sinh
        |
        v
 [Các join point mà cơ chế hỗ trợ]
        |
        v
 [POINTCUT: có khớp điểm này?]
        |                         \
      Có                          Không
        |                           |
        v                           v
 [BINDING: tạo/lấy context]      Không chạy advice này
        |
        v
 [ADVICE: hành vi phụ trợ]
        |
        +--> Before
        +--> Gọi hoặc chặn nghiệp vụ
        +--> After success / After error / Finally
~~~

Đây là sơ đồ khái niệm. Danh sách join point, dữ liệu có thể ràng buộc và hình thức triển khai tùy thuộc kỹ thuật AOP đang dùng.

## 2. Chọn vị trí: phân biệt join point và pointcut

### 2.1 Join point là vị trí có thể can thiệp

**Join point (điểm nối)** là một điểm xác định trong quá trình chương trình thực thi, nơi một cơ chế AOP *có khả năng* gắn xử lý bổ sung. Chẳng hạn: lúc gọi một phương thức, lúc bắt đầu thực thi thân phương thức, hoặc một số sự kiện khác mà cơ chế có hỗ trợ.

Cần phân biệt hai trường hợp thường gặp:

- **Method call:** điểm bên gọi phát sinh lời gọi đến một phương thức.
- **Method execution:** điểm thực thi thân phương thức đích.

Nếu phương thức A gọi B ba lần, ta có ba lần gọi và tương ứng ba lần B được thực thi. Tuy nhiên, một lớp bọc chặn lời gọi từ bên ngoài có thể nhìn thấy điểm gọi qua lớp bọc mà không nhìn thấy các lời gọi nội bộ bên trong B. Một cơ chế biến đổi mã có thể quan sát những điểm khác. Vì vậy, không được suy rằng hỗ trợ một loại join point đồng nghĩa hỗ trợ mọi loại khác.

**Join point là ứng viên của một điểm tác động**, chưa đồng nghĩa advice nào đó đã chạy ở đây.

### 2.2 Pointcut là quy tắc chọn

**Pointcut** mô tả một tập các join point thỏa điều kiện. Điều kiện có thể dựa trên chữ ký phương thức, lớp, phạm vi mã hoặc dữ liệu runtime nếu cơ chế hỗ trợ.

Mô tả bằng giả mã, không phụ thuộc cú pháp thư viện:

~~~text
pointcut: các lần thực thi reserve(user, seats)
advice:   ghi thông tin trước và sau nghiệp vụ
~~~

Dòng thứ nhất là **vị trí chọn**; dòng thứ hai mới nói **hành vi cần thực hiện**. Có thể giữ cùng pointcut nhưng thay advice ghi log bằng advice đo thời gian. Ngược lại, có thể áp dụng cùng advice ở một tập điểm khác, miễn là dữ liệu và hợp đồng thực thi phù hợp.

Một số quy tắc chọn có thể được xác định nhờ cấu trúc tĩnh như tên phương thức và chữ ký. Một số khác phải đánh giá lúc chạy, ví dụ dựa vào kiểu thực của đối tượng hoặc giá trị tham số. Vì vậy, không phải mọi pointcut chỉ là một phép tìm kiếm tên phương thức.

**Chọn quá rộng** dễ làm log nhiễu, tốn tài nguyên hoặc can thiệp vào mã không liên quan. **Chọn quá hẹp** khiến một số đường gọi quan trọng không được quan sát hoặc bảo vệ. Bộ kiểm thử phải xác nhận cả vị trí *phải được chọn* và vị trí *không được chọn*.

### 2.3 Đừng lẫn điểm chọn với quyết định an ninh

Giả sử mọi lần xóa dữ liệu phải được kiểm tra quyền. Nếu pointcut chỉ chọn các lời gọi “đã đủ quyền”, những lần gọi không đủ quyền có thể **không vào advice kiểm tra**, rồi vẫn đến nghiệp vụ nếu không có rào chắn khác. Cách tổ chức rõ ràng hơn là chọn **tất cả các điểm cần bảo vệ** và thực hiện đánh giá quyền trong một hành vi được áp dụng nhất quán.

Kết luận: pointcut trả lời **“xét điểm nào?”**. Việc cho phép hay từ chối một tác động là trách nhiệm của chính sách thực thi tại ranh giới thích hợp.

## 3. Truyền ngữ cảnh: context binding giải quyết điều gì?

Sau khi xác định một điểm, advice thường cần dữ liệu cụ thể của **lần gọi này**, chứ không chỉ biết tên phương thức. **Context exposure/binding** đưa các dữ liệu khả dụng vào phạm vi xử lý của advice.

Ví dụ:

~~~text
reserve("Lan", 2)
~~~

Ngữ cảnh có thể bao gồm:

| Nhóm ngữ cảnh | Ví dụ | Mục đích |
| --- | --- | --- |
| Thông tin join point | Tên, chữ ký `reserve` | Đặt tên thao tác, phân loại log/metrics |
| Đối tượng liên quan | Đối tượng đích nhận thao tác | Hiểu thành phần đang bị tác động |
| Tham số lúc chạy | `"Lan"`, `2` | Quan sát dữ liệu của lần gọi cụ thể |
| Kết quả | Mã đặt chỗ trả về | Xác nhận thành công, ghi kết quả được phép |
| Ngoại lệ | `IllegalArgumentException` | Phân loại và ghi nhận lỗi |
| Ngữ cảnh nghiệp vụ/hạ tầng được cấp hợp lệ | Mã tương quan, danh tính đã xác thực | Liên kết sự kiện và kiểm tra chính sách |

Cần hiểu **thời điểm khả dụng** của dữ liệu. Trước khi nghiệp vụ chạy, ta có thể có chữ ký và tham số, nhưng chưa thể có kết quả của nghiệp vụ. Khi thực thi thành công mới có giá trị trả về; khi lỗi thì có ngoại lệ. Một số advice chỉ chạy trên nhánh thành công, một số chỉ trên nhánh lỗi. Việc ràng buộc dữ liệu phải phù hợp loại điểm và nhánh thực thi đó.

Có hai khái niệm dễ nhầm:

- **Thông tin mô tả điểm** tương đối ổn định, ví dụ chữ ký phương thức.
- **Thông tin động** thay đổi theo từng lần chạy, ví dụ `seats=2` ở lần đầu và `seats=0` ở lần sau.

Cùng một pointcut có thể chọn cả hai lần gọi; context binding làm cho advice phân biệt được dữ liệu của từng lần.

Trong một số mô hình AOP, biểu thức chọn vừa kiểm tra điều kiện vừa đặt tên tham số để truyền sang advice. Điều này không làm ba trách nhiệm trở thành một: **selection quyết định điểm nào**, **binding quyết định dữ liệu nào được cấp**, và **advice quyết định hành động nào xảy ra**.

### 3.1 Truyền ngữ cảnh không phải tự động lan truyền dữ liệu

Không nên suy rằng mọi thông tin của một luồng chạy đều có mặt trong tác vụ nền hay một luồng khác. Với thao tác bất đồng bộ, context có thể cần được truyền một cách tường minh qua ranh giới thread hoặc tác vụ. Nếu cơ chế dùng trạng thái gắn với luồng, phải cân nhắc vòng đời, tính cô lập giữa các lời gọi và dọn dẹp dữ liệu sau khi dùng.

Context cũng không mặc nhiên là nguồn đáng tin. Chuỗi tên vai trò lấy từ tham số người dùng không đủ chứng minh quyền truy cập. Dữ liệu quan sát trong log phải được lọc, đặc biệt với mật khẩu, token, thông tin cá nhân và dữ liệu nhạy cảm.

## 4. Thực hiện hành vi: các dạng advice

**Advice** là đoạn mã bổ sung được kích hoạt tại những join point phù hợp. Nó có thể ghi log, đo thời gian, kiểm tra quyền, theo dõi lỗi hoặc thực hiện xử lý khác.

| Loại hành vi | Thời điểm | Ứng dụng |
| --- | --- | --- |
| Before | Trước phần nghiệp vụ | Ghi START, kiểm tra tiền điều kiện |
| After returning / success | Sau khi nghiệp vụ kết thúc bình thường | Ghi kết quả, thống kê thành công |
| After throwing / error | Khi nghiệp vụ ném lỗi | Ghi hoặc phân loại ngoại lệ |
| After / finally | Khi rời phạm vi được bao quanh | Dừng đồng hồ, giải phóng tài nguyên |
| Around | Bao quanh nghiệp vụ | Kiểm soát trước/sau, gọi tiếp, kết quả và ngoại lệ |

Tên và khả năng chính xác phụ thuộc cơ chế triển khai. Không nên mặc định mọi loại advice có quyền ngăn lời gọi hoặc thay giá trị trả về.

### 4.1 Around advice và cơ chế tiếp tục

Một dạng around advice thường có khả năng gọi `proceed` hoặc continuation tương đương để thực hiện phần được bao quanh.

~~~text
around(context, proceed):
    started = monotonicTime()
    logStart(context.operation)
    try:
        result = proceed()
        logSuccess(context.operation)
        return result
    catch error:
        logFailure(context.operation, error)
        throw error
    finally:
        recordDuration(monotonicTime() - started)
~~~

Đoạn trên là **giả mã khái niệm**: `context.operation` do binding cung cấp, còn việc ghi log, gọi tiếp và đo thời gian là hành vi của advice. Nếu không gọi `proceed`, nghiệp vụ có thể bị chặn; nếu gọi hai lần, nó có thể chạy hai lần trong những cơ chế cho phép. Việc nuốt lỗi, thay kết quả hay gọi lại phải tuân thủ hợp đồng và tính an toàn của tác dụng phụ nghiệp vụ.

## 5. Ví dụ Java 17: mô hình hóa từng trách nhiệm

Ví dụ sau dùng **Java dynamic proxy** để minh họa việc bọc các lời gọi qua giao diện. Đây là một cách diễn giải tư duy AOP, không phải cơ chế AOP bao quát mọi loại join point.

Lưu file `AopRolesDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AopRolesDemo {
    interface Booking {
        String reserve(String actor, int seats);
        String status(int requestId);
    }

    static final class BookingImpl implements Booking {
        @Override
        public String reserve(String actor, int seats) {
            System.out.println("BUSINESS reserve");
            if (seats <= 0) {
                throw new IllegalArgumentException("seats must be positive");
            }
            return "R-" + seats;
        }

        @Override
        public String status(int requestId) {
            System.out.println("BUSINESS status");
            return "OPEN";
        }
    }

    // Context của đúng một lần gọi.
    record JoinContext(Booking target, Method method, Object[] arguments) {
    }

    @FunctionalInterface
    interface Proceed {
        Object call() throws Throwable;
    }

    // 1. CHỌN VỊ TRÍ.
    static boolean pointcut(Method method) {
        return method.getDeclaringClass() == Booking.class
                && method.getName().equals("reserve")
                && method.getParameterCount() == 2;
    }

    static Object invokeTarget(JoinContext context) throws Throwable {
        try {
            return context.method().invoke(
                    context.target(), context.arguments());
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    // 3. THỰC HIỆN HÀNH VI.
    static Object advice(JoinContext context, Proceed proceed)
            throws Throwable {
        System.out.println("BEFORE " + context.method().getName()
                + " actor=" + context.arguments()[0]
                + " seats=" + context.arguments()[1]);
        try {
            Object result = proceed.call();
            System.out.println("AFTER result=" + result);
            return result;
        } catch (Throwable error) {
            System.out.println(
                    "ERROR " + error.getClass().getSimpleName());
            throw error;
        }
    }

    static Booking weave(Booking target) {
        return (Booking) Proxy.newProxyInstance(
                Booking.class.getClassLoader(),
                new Class<?>[] { Booking.class },
                (proxy, method, args) -> {
                    // 2. TRUYỀN NGỮ CẢNH.
                    Object[] callArgs =
                            args == null ? new Object[0] : args.clone();
                    JoinContext context =
                            new JoinContext(target, method, callArgs);

                    if (!pointcut(method)) {
                        return invokeTarget(context);
                    }
                    return advice(context, () -> invokeTarget(context));
                });
    }

    public static void main(String[] args) {
        Booking booking = weave(new BookingImpl());
        System.out.println("RESULT " + booking.reserve("Lan", 2));
        System.out.println("RESULT " + booking.status(7));
        try {
            booking.reserve("Lan", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER " + ex.getMessage());
        }
    }
}
~~~

Chạy bằng Java 17+:

~~~bash
javac AopRolesDemo.java
java AopRolesDemo
~~~

Stdout:

~~~text
BEFORE reserve actor=Lan seats=2
BUSINESS reserve
AFTER result=R-2
RESULT R-2
BUSINESS status
RESULT OPEN
BEFORE reserve actor=Lan seats=0
BUSINESS reserve
ERROR IllegalArgumentException
CALLER seats must be positive
~~~

**Đối chiếu với ba trách nhiệm:**

1. `pointcut(Method)` chỉ chọn lời gọi `reserve` qua giao diện `Booking`, có hai tham số. `status` không khớp nên không có dòng `BEFORE` hay `AFTER`.
2. `JoinContext` lưu đối tượng đích, `Method` và tham số của *lần gọi hiện tại*. Cả hai lần `reserve` cùng khớp pointcut, nhưng lần thứ nhất có `seats=2`, lần thứ hai có `seats=0`.
3. `advice(...)` in `BEFORE`, gọi `proceed.call()`, rồi in `AFTER` hoặc `ERROR`. Nhánh lỗi được truyền tiếp; `invokeTarget` tháo `InvocationTargetException` của reflection để giữ ngoại lệ gốc cho bên gọi.

Tên `weave` trong ví dụ chỉ biểu thị thao tác **gắn lớp bọc khi tạo proxy**. Các hệ thống AOP khác có thể kết hợp mã bằng những kỹ thuật khác nhau; việc tạo proxy không phải là định nghĩa duy nhất của weaving.

**Giới hạn quan trọng:** proxy chỉ can thiệp các lời gọi đi **qua proxy**. Lời gọi trực tiếp `new BookingImpl().reserve(...)` không đi qua bộ chọn và advice này. Lời gọi nội bộ trên đối tượng gốc cũng không tự đi qua proxy. Ví dụ sử dụng tham số `actor` để trình bày binding, không đại diện cho cơ chế xác thực danh tính.

## 6. So sánh ba trách nhiệm qua các tình huống thực tế

### 6.1 Ghi nhật ký

- **Chọn vị trí:** thao tác cần được ghi nhận; bao gồm cả các lần có thể thất bại nếu muốn quan sát lỗi.
- **Truyền ngữ cảnh:** tên thao tác, mã tương quan, trạng thái và những trường đã được phép ghi.
- **Thực hiện hành vi:** ghi sự kiện bắt đầu, thành công hoặc thất bại, che dữ liệu nhạy cảm.

Nếu advice chỉ chạy trên nhánh thành công, dù context xử lý lỗi được thiết kế tốt đến đâu, log lỗi vẫn không có cơ hội chạy. Đây là lỗi phối hợp **điểm chọn/kiểu advice** với mục tiêu ghi nhận.

### 6.2 Đo thời gian

- **Chọn vị trí:** các thao tác cần theo dõi độ trễ.
- **Truyền ngữ cảnh:** tên phép đo, loại thao tác, trạng thái; tránh nhãn có số lượng giá trị quá lớn.
- **Thực hiện hành vi:** lấy mốc thời gian bằng đồng hồ đo khoảng thời gian, gọi nghiệp vụ, ghi chênh lệch ở nhánh kết thúc.

Phạm vi đo phụ thuộc vị trí advice được gắn: có tính kiểm tra quyền, thao tác mạng hay thời gian chờ không? Nếu lời gọi chỉ phát động một tác vụ bất đồng bộ và trả về ngay, đo quanh lời gọi chỉ phản ánh thời gian *khởi phát*, không phản ánh thời gian *hoàn tất*.

### 6.3 Kiểm soát truy cập

- **Chọn vị trí:** các điểm vào của những hành động cần bảo vệ.
- **Truyền ngữ cảnh:** danh tính được xác thực, hành động, tài nguyên và thuộc tính chính sách.
- **Thực hiện hành vi:** đánh giá quyền và chặn trước khi xảy ra tác dụng phụ cần bảo vệ.

Một tham số `role` được truyền vào context không mặc nhiên đáng tin. Dữ liệu đầu vào chỉ là **dữ liệu**, còn việc xác minh nguồn và đánh giá quyền thuộc về chính sách an ninh. Cũng phải kiểm tra các đường gọi không đi qua proxy, lời gọi từ tác vụ nền và những ranh giới khác mà cơ chế can thiệp không bao phủ.

## 7. Các nhầm lẫn hay gặp

**Nhầm join point với pointcut.** Join point là một điểm có thể tác động; pointcut là quy tắc chọn một tập các điểm như vậy. Phương thức tồn tại trong chương trình không có nghĩa mọi lần thực thi của nó chịu một advice.

**Nhầm chọn điểm với thực thi.** Quy tắc `reserve` khớp không tự in log, không tự chặn người gọi hoặc tính thời gian. Advice và thứ tự áp dụng mới tạo ra hành vi thực tế.

**Nhầm binding với điều kiện chọn.** Binding `seats=0` cung cấp dữ liệu cho advice; bản thân giá trị 0 không làm lời gọi bị chặn nếu không có quy tắc hoặc hành vi kiểm tra nó.

**Cho rằng mọi context có sẵn ở mọi thời điểm.** Kết quả chỉ có sau khi hoàn thành thành công; ngoại lệ xuất hiện ở nhánh lỗi. Context của thread không tự động lan truyền đến mọi tác vụ bất đồng bộ.

**Quên continuation trong around advice.** Nếu không gọi tiếp, nghiệp vụ có thể không chạy. Nếu gọi hai lần, nó có thể bị thực hiện hai lần. Nếu nuốt lỗi, bên gọi sẽ nhìn thấy hợp đồng khác.

**Tin rằng chọn đúng tên phương thức là đủ cho bảo mật.** Phải kiểm tra mọi đường vào thực tế, nguồn danh tính được xác thực, tài nguyên chịu tác động và thời điểm kiểm tra. Các bất biến nghiệp vụ quan trọng có thể vẫn cần bảo vệ ở tầng dữ liệu hoặc miền thích hợp.

## 8. Khi nhiều advice cùng áp dụng

Giả sử một thao tác đặt chỗ cần kiểm tra quyền, ghi log và đo độ trễ:

~~~text
Bên gọi
  |
  +-- Bắt đầu đo thời gian
       |
       +-- Kiểm tra quyền
            |-- Từ chối --> Lỗi (có thể chưa ghi START)
            |
            +-- Ghi log START
                 |
                 +-- Thực hiện nghiệp vụ
                 |
            +-- Ghi SUCCESS hoặc ERROR
       |
  +-- Dừng đồng hồ trong nhánh kết thúc
~~~

Nếu đưa log ra ngoài kiểm tra quyền, các lần từ chối cũng có thể được ghi. Nếu đặt đồng hồ bên trong kiểm tra quyền, thời gian từ chối không được tính vào phép đo đó. Như vậy, cùng một **tập điểm được chọn**, cùng một **nguồn context**, nhưng thay đổi **thứ tự advice** đã thay đổi kết quả quan sát.

Với nhiều aspect, cần có quy tắc thứ tự rõ ràng, kiểm thử cả thành công, thất bại và từ chối. Việc sắp xếp tác động trong advice cũng phải tránh vô tình ghi thành công cho một lần ném lỗi.

## 9. Bảng kiểm để thiết kế và kiểm thử

| Tình huống | Chọn vị trí | Truyền ngữ cảnh | Thực hiện hành vi |
| --- | --- | --- | --- |
| `reserve("Lan", 2)` | Khớp | `actor=Lan`, `seats=2` | BEFORE → nghiệp vụ → AFTER |
| `status(7)` | Không khớp | Không cần cấp context cho advice đó | Không chạy advice |
| `reserve("Lan", 0)` | Vẫn khớp | `seats=0` | BEFORE → nghiệp vụ ném lỗi → ERROR; bên gọi nhận lỗi gốc |
| Gọi trực tiếp `BookingImpl` | Không đi qua proxy minh họa | Không cấp qua proxy | Không có advice proxy |
| Nhiều advice cùng khớp | Xác định được tập điểm từng chính sách | Mỗi advice nhận đúng dữ liệu được phép | Thứ tự và nhánh kết thúc đúng |

Khi kiểm thử ngoài ví dụ, cần xét overload, các đường gọi nội bộ, phương thức kế thừa, tham số `null`, kết quả `void`, lỗi ngoài dự kiến, tác vụ bất đồng bộ và những trường hợp một điểm bị chọn nhiều lần. Mỗi nhóm kiểm thử phục vụ một trách nhiệm khác nhau; kiểm thử chỉ thấy dòng log xuất hiện chưa chứng minh mọi lời gọi cần bảo vệ đều được bao phủ.

## 10. Tự luyện phân tích

Giả sử mọi thao tác **cập nhật** hồ sơ đều phải kiểm tra quyền và ghi log, còn thao tác **đọc** hồ sơ chỉ cần đo độ trễ. Có người đề xuất “chọn mọi phương thức và ghi toàn bộ tham số”.

Hãy phân tích:

- **Chọn vị trí:** chia đúng phạm vi cập nhật và đọc; tránh tự động gắn chính sách cập nhật cho các phương thức đọc.
- **Truyền ngữ cảnh:** kiểm soát quyền cần danh tính đã xác thực và tài nguyên; log chỉ nhận thông tin được phép công bố; phép đo độ trễ cần tên phép đo và trạng thái, thường không cần toàn bộ hồ sơ.
- **Thực hiện hành vi:** kiểm tra quyền trước khi cập nhật; ghi sự kiện phù hợp ở nhánh thành công/lỗi; đo thời gian ở nhánh kết thúc của thao tác đọc.
- **Kiểm chứng:** thử người không có quyền, đường gọi trực tiếp, thất bại nghiệp vụ, dữ liệu nhạy cảm, kết quả và ngoại lệ trước/sau khi thêm aspect.

**Ghi nhớ:** **pointcut chọn “ở đâu/khi nào”**, **binding cấp “thông tin nào của lần thực thi”**, và **advice quyết định “làm gì với thông tin và luồng thực thi đó”**. Tách rạch ròi ba trách nhiệm giúp một aspect đúng phạm vi, truyền đúng dữ liệu và tạo đúng hành vi.
