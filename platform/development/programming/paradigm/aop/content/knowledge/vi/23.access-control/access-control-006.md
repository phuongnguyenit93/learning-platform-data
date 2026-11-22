# Nguy cơ đường gọi không đi qua cơ chế can thiệp trong AOP

## 1. Vấn đề: có advice bảo vệ không có nghĩa mọi đường gọi đều được bảo vệ

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), ta có thể đặt advice kiểm soát truy cập tại các **join point** do **pointcut** chọn. Ví dụ, trước khi thực thi thao tác rút tiền, sửa dữ liệu hoặc xóa tài nguyên, advice có thể xác minh danh tính, quyền và phạm vi đối tượng.

Tuy nhiên, **chính sách chỉ có tác dụng khi đường thực thi thực sự đi qua cơ chế can thiệp được cấu hình**. Nếu đối tượng nghiệp vụ được gọi trực tiếp, phương thức không nằm trong tập join point hỗ trợ, đường gọi đi qua một đối tượng khác hoặc một lối vào chưa được instrument, advice có thể không chạy. Khi đó lời gọi vẫn có khả năng thực hiện tác dụng phụ, mặc dù người phát triển tin rằng đã có một lớp kiểm tra quyền bao quanh.

Rủi ro đặc biệt nghiêm trọng nếu kiểm soát truy cập tồn tại **duy nhất** trong một advice. Một đường gọi bypass có thể thực thi cùng hành vi nghiệp vụ mà không kiểm tra quyền dự kiến.

Cần trả lời bốn câu hỏi khác nhau:

1. **Hành vi nào cần được bảo vệ?** Ví dụ: thay đổi số dư, đọc hồ sơ riêng tư, tạo yêu cầu thanh toán.
2. **Điều kiện nào cho phép thực hiện?** Danh tính được xác thực, vai trò, quyền trên đối tượng, trạng thái nghiệp vụ hoặc ranh giới tenant.
3. **Cơ chế AOP thực tế can thiệp tại đâu?** Lời gọi phương thức qua proxy, thực thi phương thức đã weaving, hay một tập join point khác?
4. **Có đường gọi nào dẫn đến tác dụng phụ mà không đi qua những điểm ấy không?** Đây là câu hỏi trung tâm của bài.

Một hệ thống chỉ an toàn nếu **mọi đường có thể tới hành vi nhạy cảm đều được kiểm soát bởi một ranh giới tin cậy tương ứng**. Advice là một cơ chế áp dụng chính sách; nó không tự chứng minh độ bao phủ của tất cả đường gọi.

## 2. Hiểu đúng các thuật ngữ trước khi đánh giá bypass

| Khái niệm | Ý nghĩa liên quan đến an toàn truy cập |
| --- | --- |
| Join point | Điểm trong thực thi chương trình mà mô hình AOP cho phép áp dụng advice |
| Pointcut | Quy tắc chọn tập join point cần can thiệp |
| Advice | Logic được chạy trước/sau/quanh join point được chọn |
| Target | Đối tượng hoặc hành vi thực tế thực hiện nghiệp vụ |
| Proxy | Đối tượng đại diện có thể chặn lời gọi trước khi chuyển tiếp tới target |
| Weaving | Ghép logic aspect vào cấu trúc hoặc luồng thực thi theo cơ chế hỗ trợ |
| Call site | Vị trí thực hiện lời gọi; có thể là nơi can thiệp khác với điểm thực thi của phương thức |
| Access-control boundary | Nơi hệ thống bắt buộc xác minh quyền trước khi cho phép một tác dụng phụ nhạy cảm |

**Method-call join point** và **method-execution join point** không nhất thiết đồng nhất. Một cơ chế có thể can thiệp vào lời gọi tại các call site đã chọn; cơ chế khác can thiệp vào phần thực thi của phương thức. Cách lựa chọn này ảnh hưởng đến trường hợp tự gọi, dispatch động và các đường được biên dịch hoặc tải sau.

Tương tự, AOP dựa trên proxy và AOP dựa trên biến đổi bytecode có phạm vi can thiệp khác nhau. Không nên lấy giới hạn của một cơ chế để tuyên bố rằng **mọi** hình thức AOP đều có cùng lỗ hổng. Việc đánh giá phải căn cứ vào **cơ chế và cấu hình thực tế**.

## 3. Mô hình đơn giản: đường đi qua proxy và đường đi thẳng tới target

Giả sử một giao diện cung cấp thao tác nhạy cảm:

~~~text
                 +----------------+
Caller --------> | Guarded proxy  | ---check---> Target.sensitive()
                 +----------------+

Caller -------------------------------> Target.sensitive()
                   đường trực tiếp
~~~

Ở đường thứ nhất, caller giữ tham chiếu đến **proxy**; advice gắn với proxy có thể kiểm tra quyền. Ở đường thứ hai, caller giữ **target gốc** và gọi thẳng, nên một interceptor chỉ nằm ở proxy không được kích hoạt.

Nếu tất cả điều kiện bảo vệ được thực hiện tại proxy, đường thứ hai có thể bỏ qua chúng. Trường hợp này thường xuất hiện khi:

- Một phần mã lấy đối tượng từ cơ chế tạo proxy, phần khác tự khởi tạo target.
- Target gốc được lưu hoặc chia sẻ cùng với proxy.
- Một phương thức của target gọi phương thức khác trên chính đối tượng target.
- Một callback, lambda hoặc method reference giữ tham chiếu đến target thay vì proxy.
- Có một entry point bổ sung không qua đường cấp phát/interception dự kiến.

Không nhất thiết kẻ tấn công có quyền gọi bất kỳ phương thức Java nào trực tiếp. Để thành vấn đề bảo mật khai thác được, phải tồn tại **đường vào hoặc thành phần có thể bị điều khiển đủ để đi tới nhánh không được bảo vệ**. Tuy vậy, ngay cả khi chỉ xảy ra do lập trình sai ở nội bộ, đây vẫn là lỗi kiến trúc nghiêm trọng cần được kiểm tra.

## 4. Tự gọi phương thức: lời gọi con có thể không đi qua advice

Ví dụ khái niệm:

~~~java
class OrderService {
    void updatePrice() {
        // thao tác nhạy cảm, được kỳ vọng có advice kiểm tra quyền
    }

    void refreshOrder() {
        updatePrice(); // lời gọi nội bộ trên chính đối tượng này
    }
}
~~~

Ở một cơ chế can thiệp dựa vào proxy bên ngoài, lời gọi tới refreshOrder() đi qua proxy, nhưng lời gọi updatePrice() bên trong có thể tương đương **this.updatePrice()** trên target. Lời gọi nội bộ ấy không quay lại proxy; nếu advice chỉ chặn updatePrice() tại proxy, advice không được kích hoạt.

Nhìn từ người gọi:

~~~text
caller -> proxy.refreshOrder()
             -> target.refreshOrder()
                  -> this.updatePrice()
                       (không qua proxy.updatePrice())
~~~

Nếu refreshOrder() không có cùng chính sách kiểm tra quyền, thao tác updatePrice() có thể diễn ra mà không qua kiểm tra dự kiến.

**Giới hạn của kết luận:** đây là rủi ro điển hình với một số mô hình **proxy interception**. Một cơ chế weaving can thiệp tại method-execution join point có thể áp dụng advice khi thân updatePrice() chạy, kể cả khi được gọi nội bộ. Cơ chế weaving kiểu call-site cũng phải xét call site đó có nằm trong phạm vi được dệt hay không. Không được khẳng định tự gọi luôn vượt qua advice trong mọi AOP.

Vấn đề thực sự là **điểm can thiệp nào bảo vệ hành vi** và **đường gọi nội bộ có đi qua điểm đó hay không**.

## 5. Ví dụ Java 17+: minh họa đường gọi không qua proxy

Ví dụ dùng **Java Dynamic Proxy** của thư viện chuẩn. Một proxy kiểm tra quyền khi ai đó gọi withdraw(...) **qua proxy**. Target có phương thức batch(...) gọi withdraw(...) trên chính target, nên lời gọi bên trong không đi qua InvocationHandler của proxy.

Mã minh họa này cố ý tạo một thiết kế thiếu kiểm soát ở target để thấy sự khác biệt. Nó là chương trình học thuật cục bộ, không phải mẫu bảo mật nên triển khai.

Tạo tệp **InterceptionGapDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public final class InterceptionGapDemo {
    interface Ledger {
        void withdraw(int amount);
        void batch(int amount);
    }

    static final class UnsafeLedger implements Ledger {
        int balance = 100;

        @Override
        public void withdraw(int amount) {
            balance -= amount;
            System.out.println("TARGET withdraw " + amount);
        }

        @Override
        public void batch(int amount) {
            System.out.println("TARGET batch");
            withdraw(amount); // self-invocation trên target
        }
    }

    static final class SafeLedger implements Ledger {
        int balance = 100;

        @Override
        public void withdraw(int amount) {
            // Minh họa ranh giới kiểm tra bên trong dịch vụ tin cậy.
            // Trong hệ thống thật phải kiểm tra quyền từ nguồn danh tính tin cậy.
            throw new SecurityException("denied in service");
        }

        @Override
        public void batch(int amount) {
            withdraw(amount);
        }
    }

    public static void main(String[] args) {
        UnsafeLedger target = new UnsafeLedger();

        Ledger guarded = (Ledger) Proxy.newProxyInstance(
                Ledger.class.getClassLoader(),
                new Class<?>[]{Ledger.class},
                (proxy, method, values) -> {
                    if (method.getName().equals("withdraw")) {
                        System.out.println("PROXY check withdraw");
                        throw new SecurityException("denied at proxy");
                    }
                    try {
                        return method.invoke(target, values);
                    } catch (InvocationTargetException error) {
                        throw error.getCause();
                    }
                });

        try {
            guarded.withdraw(10);
        } catch (SecurityException error) {
            System.out.println("caller: " + error.getMessage());
        }

        guarded.batch(20);
        System.out.println("unsafe balance=" + target.balance);

        SafeLedger safe = new SafeLedger();
        try {
            safe.batch(20);
        } catch (SecurityException error) {
            System.out.println("safe caller: " + error.getMessage());
        }
        System.out.println("safe balance=" + safe.balance);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac InterceptionGapDemo.java
java InterceptionGapDemo
~~~

Stdout:

~~~text
PROXY check withdraw
caller: denied at proxy
TARGET batch
TARGET withdraw 20
unsafe balance=80
safe caller: denied in service
safe balance=100
~~~

**Giải thích kết quả:**

1. guarded.withdraw(10) đi qua proxy. InvocationHandler chặn và báo lỗi; target.withdraw() không chạy ở lượt này.
2. guarded.batch(20) đi qua proxy, nhưng proxy chỉ kiểm tra tên phương thức withdraw. Nó chuyển batch() sang target bằng reflection.
3. Bên trong target.batch(), lời gọi withdraw(20) thực thi trực tiếp trên target, không quay lại InvocationHandler của proxy. Số dư giảm từ 100 xuống 80.
4. SafeLedger đặt một kiểm tra tối thiểu **trong chính phương thức thay đổi trạng thái**. Lời gọi nội bộ tới withdraw() vẫn bị từ chối; số dư không đổi.

Trong chương trình thật, điều kiện kiểm tra cần lấy danh tính đã xác thực, quyền thao tác, đối tượng đích và trạng thái liên quan từ nguồn đáng tin cậy. Dòng throw trong SafeLedger chỉ giúp chứng minh **vị trí cưỡng chế** có thể bảo vệ cả đường gọi trực tiếp lẫn lời gọi nội bộ.

**Phạm vi ví dụ:** Java Dynamic Proxy chỉ đại diện cho một kiểu interception dựa trên interface; nó không chứng minh các giới hạn của mọi cơ chế bytecode weaving. InvocationHandler nhận lời gọi qua proxy và chuyển cho target; lời gọi trong thân target không tự chuyển qua proxy.

## 6. Những nguyên nhân gây thiếu bao phủ join point

### 6.1. Đường khởi tạo đối tượng khác nhau

Một nhóm đối tượng nhận proxy từ một factory/registry, nhưng nơi khác gọi new Target() trực tiếp. Khi đó hai nơi có thể nhìn thấy cùng một kiểu nghiệp vụ nhưng khác đường thực thi:

~~~text
caller A -> factory -> proxy -> target -> guard có thể chạy
caller B -> new Target() ---------> target -> không có proxy guard
~~~

Cần quản lý nguồn tạo đối tượng và loại bỏ việc cấp phát target thô tới các caller không được phép. Nếu code có thể tạo đối tượng mới ngoài container/interception boundary, cơ chế AOP dựa vào proxy không tự kiểm soát được nó.

Không nên chữa bằng cách “nhớ gọi proxy” trong từng phương thức; đó là một kỷ luật dễ bị phá vỡ. Tốt hơn là hạn chế quyền tạo/truy cập target và cưỡng chế quyền ở nơi thực hiện effect nhạy cảm.

### 6.2. Lời gọi nội bộ, đệ quy và phương thức ủy quyền

Các tình huống như this.sensitive(), helper.sensitive() hoặc đệ quy đều phải được xem xét:

- Nếu this.sensitive() ở trên target thô, một proxy đứng ngoài không nhận cuộc gọi.
- Nếu helper là proxy riêng, cuộc gọi có thể được instrument.
- Nếu helper là target thô, advice ở proxy của helper bị bỏ qua.
- Nếu code đã được weaving ở điểm thực thi tương ứng, lời gọi nội bộ có thể vẫn kích hoạt advice.
- Nếu advice được áp dụng chỉ cho một phần kiểu/method, một nhánh đệ quy hoặc overload khác có thể không match.

Chỉ dùng tên “internal call” chưa đủ kết luận. Phải truy theo **đối tượng thực nhận lời gọi**, **join point được chọn** và **phạm vi instrumentation**.

### 6.3. Method không được cơ chế can thiệp hỗ trợ

Khả năng can thiệp khác nhau tùy cơ chế:

- Java Dynamic Proxy chuẩn hoạt động trên các interface được proxy khai báo; một phương thức chỉ có trên lớp triển khai mà không lộ trong interface không thể được gọi qua kiểu proxy ấy như một phương thức interface bình thường.
- Cơ chế subclass proxy phụ thuộc khả năng override, nên phương thức final hoặc không thể override không thể được can thiệp bằng cách override tương ứng; một số phương thức private cũng không là điểm override.
- Bytecode weaving/instrumentation có thể can thiệp vào những điểm mà proxy subclass không thể, nhưng vẫn phụ thuộc phạm vi weave, loại join point được hỗ trợ và các giới hạn runtime.
- Các lời gọi tới static method, constructor, code native, default interface method hoặc method handle có hành vi interception phụ thuộc rất cụ thể vào mô hình AOP; không được suy luận chung là đều được bảo vệ hay đều bị bỏ qua.

Khi thiết kế pointcut, phải kiểm tra riêng từng kiểu phương thức sử dụng trong ứng dụng. Đặc biệt, không nên chọn AOP interceptor làm **điểm bảo vệ duy nhất** nếu không kiểm chứng được khả năng intercept đối với mọi biến thể cần bảo vệ.

### 6.4. Sai phạm vi pointcut hoặc điều kiện match

Một pointcut có thể bỏ sót phương thức do:

- Tên kiểu, package, chữ ký hoặc modifier không đúng biểu thức chọn.
- Chỉ chọn public methods trong khi effect thực nằm ở một helper khác.
- Chỉ chọn một overload, bỏ sót overload có khả năng ghi dữ liệu.
- Kiểu runtime khác kiểu mong đợi do kế thừa, implement interface hoặc dynamic dispatch.
- Aspect chỉ được áp dụng cho một module/classloader/namespace cụ thể.
- Điểm cắt chọn nơi gọi chứ không phải nơi thực thi, nên một call site khác nằm ngoài phạm vi đã dệt.

**Pointcut không phải bản khai chính sách truy cập.** Biểu thức chọn là công cụ định tuyến advice. Chính sách quyền nên được định nghĩa độc lập bằng operation, resource, principal và action để khi đổi cách instrument, yêu cầu bảo vệ vẫn nhất quán.

### 6.5. Bỏ qua một đường vào khác

Cùng thao tác có thể được kích hoạt từ:

- Yêu cầu tương tác từ người dùng.
- Job theo lịch.
- Handler nhận message hoặc event.
- Callback và background worker.
- Công cụ quản trị, tác vụ dữ liệu hoặc batch import.
- Một API nội bộ, entry point mới hoặc đường gọi được thêm sau này.

Nếu chỉ instrument đường qua một lớp xử lý request, các đường từ job hoặc worker có thể không có advice tương tự. Điều cần kiểm tra là **mọi entry point dẫn đến cùng effect nhạy cảm**, không chỉ endpoint chính.

Một request có kiểm soát quyền trước khi gọi service không tạo đảm bảo cho job đang gọi trực tiếp service. Ngược lại, job có danh tính hệ thống được cấp quyền đặc biệt phải được kiểm soát theo một principal và scope được xác định rõ, thay vì mặc định “nội bộ thì toàn quyền”.

### 6.6. Callback và thực thi bất đồng bộ

Một phương thức bị intercept có thể chỉ lập lịch công việc rồi trả về:

~~~text
caller -> proxy.submit()
             -> target.submit() tạo Runnable
             -> trả về
                               Runnable.run() trên worker
                                  -> sensitive effect
~~~

Nếu policy chỉ can thiệp vào submit(), chưa chắc nó can thiệp vào Runnable.run() hoặc lời gọi thực sự làm thay đổi tài nguyên. Điều này đặc biệt quan trọng khi quyền có thể đổi giữa lúc submit và lúc chạy.

Có hai câu hỏi phải tách:

1. Người gọi có quyền **đăng ký/khởi tạo** công việc không?
2. Tác vụ thực thi sau đó có quyền **thực hiện effect** trên tài nguyên tại thời điểm cần thiết không?

Cơ chế context propagation có thể chuyển identity/correlation tới worker, nhưng **mang theo identity không tương đương tự xác minh authorization**. Nếu quyền phải được kiểm tra lại ở thời điểm thực thi, worker cần thực hiện kiểm tra tại ranh giới đó.

### 6.7. Lời gọi qua reflection, method handle và code sinh động

Một lời gọi phản chiếu tới target vẫn có thể đi vào thân phương thức mà không qua proxy nếu nó dùng tham chiếu target thô. Ngược lại, reflection được gọi trên proxy có thể vẫn đi qua cơ chế dispatch của proxy. Vì vậy phát biểu “reflection luôn bỏ qua AOP” là sai.

Cần xác định **đối tượng đích của lời gọi reflection** và cách cơ chế interception tích hợp với reflection/method handle. Với runtime bytecode weaving, câu trả lời còn phụ thuộc vị trí và thời điểm mã được dệt.

Các lớp được tải muộn, sinh động hoặc tải qua classloader khác cũng có thể nằm ngoài scope weave nếu cấu hình không bao phủ chúng. Mỗi thay đổi về cách tải/mở rộng mã cần có kiểm tra độ bao phủ.

## 7. Phân biệt sự cố độ bao phủ và sự cố chính sách

Không phải mọi lỗi truy cập đều do bypass. Có hai loại nguyên nhân:

**Loại A — advice không chạy:** đường gọi không đi qua điểm can thiệp. Log cho thấy không có sự kiện “guard evaluated” ở operation nhạy cảm; dù chính sách đúng trên giấy, nó không được thực thi.

**Loại B — advice chạy nhưng quyết định sai:** principal bị giả mạo, thiếu tenant check, cache quyết định quyền lỗi thời, giá trị role được lấy từ nguồn không tin cậy, hoặc kiểm tra quyền chỉ dựa trên chức danh mà bỏ đối tượng cụ thể.

Cả hai có thể cùng tồn tại. Một kiểm thử chỉ xác nhận “advice đã chạy” không chứng minh quyết định quyền chính xác. Một kiểm thử chỉ xác nhận “người không có quyền bị từ chối ở endpoint A” không chứng minh endpoint B hay background handler an toàn.

Nên quan sát riêng:

~~~text
entrypoint -> sensitive operation
        |
        +-- instrumentation applied?  YES/NO
        |
        +-- authorization evaluated?  YES/NO
        |
        +-- resource/action checked?  YES/NO
        |
        +-- decision                ALLOW/DENY/ERROR
        |
        +-- effect occurred?         YES/NO
~~~

Điều kiện cần quan trọng: **không được có một trường hợp principal không được phép mà effect nhạy cảm vẫn xảy ra**, bất kể lời gọi đến qua đường nào.

## 8. Đường gọi nào thực sự cần được bảo vệ?

Đánh giá bắt đầu từ **tác dụng phụ nhạy cảm** và **dữ liệu cần bảo vệ**, rồi truy ngược các đường gọi dẫn đến chúng:

~~~text
External entry points             Internal pathways               Sensitive effect
----------------------            ------------------              ----------------
UI request ---------------------> controller ----------------\
Scheduled job ------------------> scheduler handler ---------+--> accountService.debit()
Message consumer ---------------> event handler -------------/
Admin tool ---------------------> import service -------------/
Internal call ------------------> helper ---------------------/
~~~

Nếu kiểm tra quyền chỉ xuất hiện ở controller, các nhánh khác chưa chắc được bảo vệ. Nếu đặt guard ở accountService.debit() nhưng dùng proxy và một caller lấy target trực tiếp, vẫn chưa có bảo đảm. Hãy đặt **ranh giới cưỡng chế quyền có độ tin cậy cao** gần thao tác nhạy cảm, đồng thời áp dụng guard ở các biên vào để từ chối sớm và nâng cao khả năng quan sát.

Đây không nhất thiết là yêu cầu kiểm tra trùng lặp mọi nơi. Mục tiêu là có một **điểm thực thi chính sách không thể bị bỏ qua bởi các đường hợp lệ trong kiến trúc**, với kiểm tra bổ sung ở các biên phù hợp. Ví dụ, dịch vụ bảo vệ tài nguyên có thể không cấp thao tác thay đổi trạng thái nếu thiếu dữ liệu authorization đã xác minh, bất kể ai là caller.

Cần thận trọng với các hàm “trusted”, “system”, “internal” chỉ dựa trên tên. Nếu chúng dẫn đến cùng effect mà bỏ qua xác thực/authorization, phải có một mô hình trust rõ ràng: ai được gọi, principal nào được sử dụng và cấp quyền theo cơ chế nào.

## 9. Các chiến lược thiết kế giảm rủi ro bypass

### 9.1. Đặt kiểm tra bất biến ở lớp có quyền thực hiện effect

Một chiến lược mạnh là biến quyền truy cập thành điều kiện bắt buộc của API thực hiện effect. Ví dụ, phương thức thực sự ghi một bản ghi phải đòi hỏi chính sách cho phép thao tác trên bản ghi đó; một proxy chỉ hỗ trợ áp dụng policy nhất quán và giảm lặp.

Phân biệt:

- **Advice tiền kiểm:** từ chối nhanh, ghi dấu truy cập, chuẩn hóa log, áp chính sách chung ở đường gọi được instrument.
- **Guard ở ranh giới tài nguyên/dịch vụ tin cậy:** đảm bảo effect không thể được kích hoạt bởi một đường đi không kiểm tra quyền.

Nếu hai tầng cùng kiểm tra, nên dùng cùng nguồn chính sách hoặc quy tắc được kiểm chứng để tránh lệch quyết định. Bảo vệ ở tầng dữ liệu như quyền truy cập của tài khoản database hay phân tách tenant có thể bổ sung rào chắn khi lỗi application xảy ra.

### 9.2. Kiểm soát vòng đời và tham chiếu đối tượng

Với mô hình proxy, bảo đảm caller bên ngoài chỉ nắm được tham chiếu tới proxy khi cần intercept; tránh trả target thô từ registry/factory hoặc public API. Hạn chế trực tiếp việc khởi tạo và chia sẻ các object cung cấp nghiệp vụ nhạy cảm.

Đừng cố sửa bằng cách ép mọi phương thức tự gọi một proxy toàn cục nếu điều đó sinh ra vòng phụ thuộc và khó kiểm soát. Nếu cần đường can thiệp nhất quán, có thể tái cấu trúc các thao tác nhạy cảm sang một thành phần riêng có ranh giới API rõ ràng, hoặc dùng cơ chế weaving phù hợp và kiểm thử độ bao phủ.

### 9.3. Dùng cơ chế can thiệp phù hợp với join point cần bảo vệ

Khi cần intercept method-execution bên trong target, một cơ chế weaving có khả năng bao phủ đúng join point có thể phù hợp hơn proxy interception. Tuy nhiên, weaving cũng không thay thế phân tích bảo mật:

- Phải biết tập class/method được weave.
- Phải kiểm tra thứ tự các advice.
- Phải kiểm tra lỗi tải/biến đổi bytecode có bị bỏ qua âm thầm không.
- Phải xem xét những thành phần nạp khác classloader hoặc chạy ở môi trường build/deployment khác.

Lựa chọn cơ chế là quyết định kỹ thuật; **chứng cứ bao phủ** mới là cơ sở khẳng định một đường đi được bảo vệ.

### 9.4. Ưu tiên fail closed ở các điểm quyết định truy cập

Nếu việc lấy principal hoặc dịch vụ kiểm tra quyền thất bại, một policy cho phép truy cập theo mặc định có thể biến sự cố hạ tầng thành bypass. Với thao tác nhạy cảm, cần quy định trạng thái thiếu thông tin là từ chối hoặc một outcome không thực thi effect theo chính sách.

Cẩn thận với fallback advice:

~~~text
Fallback(Authorization(operation))
~~~

Nếu fallback bắt lỗi authorization rồi trả hoặc thực hiện một nhánh thay thế không kiểm tra quyền, nó có thể che dấu từ chối. Một đường fallback trả dữ liệu công khai có kiểm soát khác với đường fallback tiếp tục thực hiện effect đặc quyền. Thứ tự các advice phải được xem xét theo loại lỗi được phép fallback.

### 9.5. Tách authentication, authorization và context

**Authentication:** người gọi là ai? **Authorization:** principal đó được làm gì trên resource nào? **Context propagation:** làm sao thông tin đã xác minh được mang tới điểm thực thi?

Một ThreadLocal lưu principal không tự bảo đảm độ tin cậy của principal. Trong tác vụ bất đồng bộ, context có thể bị mất hoặc giữ sót từ request khác nếu không capture/restore đúng scope. Ngược lại, chuyển context đầy đủ tới worker không có nghĩa guard đã chạy.

Một mô hình tốt:

~~~text
trusted ingress:
    verify identity
    construct trusted principal context
    invoke operation

sensitive boundary:
    resolve principal from trusted context
    evaluate permission for action + resource
    deny before side effect if unauthorized

async handoff:
    capture trusted context according to contract
    bind for worker scope
    re-evaluate permission if required at execution time
    restore worker's previous context
~~~

Khi quyền có thể đổi giữa lúc xếp hàng và lúc xử lý, cần quyết định rõ kiểm tra tại thời điểm **enqueue**, tại thời điểm **execute** hay cả hai. Điều này phụ thuộc hợp đồng nghiệp vụ, không tự giải quyết nhờ AOP.

## 10. Thứ tự advice có thể tạo một đường vòng logic

Không chỉ bypass theo cơ chế proxy, thứ tự nhiều advice cũng có thể làm một guard bị **bỏ qua trên một số nhánh**.

### 10.1. Cache ở ngoài authorization

~~~text
Cache(
  Authorization(
    readResource
  )
)
~~~

Nếu Cache trả dữ liệu ngay khi cache hit, nó không gọi Authorization bên trong. Với tài nguyên theo quyền cá nhân hoặc tenant, đây có thể là lỗi nghiêm trọng: người chưa được quyền có thể nhận một giá trị cache đã lưu từ người khác nếu cache key và chính sách không an toàn.

Cần đặt chính sách truy cập ở ranh giới nhìn thấy **cả hit và miss**, hoặc thiết kế cache có phân vùng theo principal/resource, kết hợp với kiểm tra quyền luôn đúng. Đổi thứ tự đơn thuần chưa đủ nếu bản thân resource access vẫn thiếu guard ở tầng tin cậy.

### 10.2. Retry ở ngoài guard

~~~text
Retry(
  Authorization(
    operation
  )
)
~~~

Nếu mỗi attempt đều đi qua Authorization, policy có thể được đánh giá lại mỗi lần. Nhưng nếu Retry chỉ bọc một thunk giữ sẵn target thô, hoặc guard chỉ chạy ở bước submit mà hành vi thực chạy ở callback khác, retry có thể không lặp việc kiểm tra. Phải xác định **cái gì thực sự được proceed() gọi**.

### 10.3. Fallback thay đổi outcome của lỗi truy cập

~~~text
Fallback(
  Authorization(
    operation
  )
)
~~~

Nếu fallback bắt SecurityException và chuyển thành đường xử lý “thành công” có effect mà không đánh giá quyền, chính sách truy cập bị vô hiệu trên nhánh lỗi. Không nên đưa lỗi từ chối quyền vào nhóm lỗi có thể retry/fallback theo kiểu hạ tầng tạm thời.

### 10.4. Recorder không chứng minh guard đã chạy

Một log “operation success” từ outer advice không thể là bằng chứng rằng guard trong inner advice đã chạy: cache hoặc fallback có thể trả kết quả mà không gọi inner advice. Nếu cần audit về quyền, phải ghi sự kiện tại **điểm ra quyết định quyền** với định danh resource, action và outcome phù hợp, đồng thời bảo đảm việc audit không tiết lộ dữ liệu nhạy cảm.

### 10.5. Advice khác gây lỗi hoặc có tác dụng phụ trước guard

~~~text
LoggingWithExternalSideEffect(
  Authorization(
    operation
  )
)
~~~

Nếu logging thực sự gửi dữ liệu nhạy cảm ra ngoài trước khi Authorization quyết định, dù operation bị từ chối, effect ghi log đã xảy ra. Trật tự phải dựa trên **những gì advice bên ngoài thực hiện**, không chỉ tên gọi “logging”.

## 11. Kiểm thử độ bao phủ như một thuộc tính bảo mật

Một test đơn giản “gọi proxy.sensitive() với người không có quyền và thấy exception” chỉ chứng minh **đường proxy đó** được bảo vệ. Cần bổ sung kiểm thử các đường dẫn khác có khả năng tới effect nhạy cảm.

### 11.1. Tạo danh mục các đường gọi

Bắt đầu từ thao tác nhạy cảm, lập bảng:

| Đường gọi | Đối tượng thực được gọi | Kiểm tra quyền đặt ở đâu? | Kỳ vọng |
| --- | --- | --- | --- |
| Entry point chính | Proxy hoặc đối tượng được weave | Guard được xác định | Người không có quyền bị chặn |
| Một phương thức gọi phương thức khác trên this | Target nội bộ | Kiểm tra ở ranh giới effect hoặc weaving thật | Không bỏ qua quyền |
| Thành phần khác giữ target gốc | Raw target | Guard độc lập với proxy | Không có đường thực thi effect trái quyền |
| Callback trên worker | Task/worker object | Guard và context tại lúc thực thi | Không dùng quyền sai hoặc đã hết hiệu lực |
| Job/consumer | Service hoặc handler riêng | Chính sách cho principal hệ thống | Chỉ quyền được cấp |
| Reflection/method handle | Proxy hay target cụ thể | Cơ chế instrument và guard tương ứng | Không có đường bỏ qua do thay kiểu gọi |
| Cache hit/fallback | Outer advice | Guard tại đường có thể trả kết quả | Không trả dữ liệu trái quyền |
| Đường gọi từ module/classloader khác | Object được dispatch thật | Weaving/interception có bằng chứng | Phạm vi bảo vệ vẫn đúng |

Bảng này chỉ là mẫu tư duy; phải điền bằng các đường gọi thực tế của ứng dụng, không suy đoán dựa trên tên lớp.

### 11.2. Kiểm thử âm tính ở cấp effect

Với một principal **không** được quyền:

1. Gọi từng entry point có thể kích hoạt hành vi nhạy cảm.
2. Xác nhận kết quả là từ chối đúng hợp đồng.
3. Quan trọng hơn: xác nhận **không có effect nhạy cảm nào xảy ra** — không đổi số dư, không tạo bản ghi, không gửi thông điệp, không lộ dữ liệu.
4. Nếu có transaction, xác nhận trạng thái dữ liệu sau rollback và effect ngoài transaction.
5. Nếu đường gọi bất đồng bộ, chờ hoặc theo dõi đến ranh giới hoàn tất thích hợp; không dừng kiểm tra ở thời điểm future vừa được trả về.

Một test chỉ assert exception nhưng không kiểm tra side effect có thể bỏ sót trường hợp thao tác được thực thi rồi mới bị chặn.

### 11.3. Kiểm thử dương tính

Với principal hợp lệ, xác nhận thao tác thành công và advice không vô tình chặn đường được cấp phép. Điều này giúp phân biệt “không có đường bypass” với một hệ thống vô tình từ chối mọi thứ.

### 11.4. Bằng chứng advice thật sự kích hoạt

Trong test, có thể dùng một probe để đếm số lượt advice tương ứng với join point nhạy cảm, rồi đối chiếu với số lượt hiệu ứng nghiệp vụ. Tuy nhiên:

- Đếm advice không đủ chứng minh policy quyết định đúng.
- Một method được advice chạy nhiều lần có thể chỉ tạo effect một lần.
- Một effect có thể xảy ra ngoài method đã được instrument.
- Một phần số liệu có thể bị thiếu do sampling hoặc telemetry lỗi.

Do đó, hãy kết hợp **dấu vết interception**, **quyết định authorization** và **trạng thái effect thực tế**.

## 12. Rà soát tĩnh và kiểm tra cấu hình build/deploy

Kiểm thử động không thể duyệt hết mọi đường gọi. Có thể bổ sung phân tích:

- Tìm những nơi tự khởi tạo lớp có hành vi nhạy cảm thay vì dùng thành phần đã được kiểm soát.
- Tìm chỗ cấp phát, lưu hoặc expose target gốc từ proxy factory/registry.
- Kiểm tra lời gọi this.method(), method references và callback được tạo từ target.
- Đối chiếu pointcut với các overload, modifiers, classloader và module thực tế.
- Kiểm tra những method không thể override nếu cơ chế đang dùng là subclass proxy.
- Với weaving, xác nhận instrumentation được áp dụng cho build artifact thực sự triển khai và không bỏ qua lỗi weave.
- Kiểm tra các cấu hình khác nhau giữa chạy test, chạy local và production, kể cả các thành phần tải động.
- Khi refactor hoặc thêm entry point mới, cập nhật danh mục đường tới effect nhạy cảm.

Một báo cáo “đã có aspect được khai báo” không phải bằng chứng rằng toàn bộ class đã được can thiệp. Cần quan sát cấu trúc runtime, test và cấu hình weaving/proxy thực tế.

## 13. Mối quan hệ với principle of least privilege

**Least privilege** yêu cầu mỗi caller, service account hoặc tác vụ chỉ có quyền tối thiểu cần thiết. Nếu một tầng nghiệp vụ được gọi qua đường bỏ advice mà vẫn giữ quyền database quá rộng, lỗi bypass có thể dẫn đến thay đổi tài nguyên vượt phạm vi dự kiến.

Các biện pháp bổ trợ:

1. Chia trách nhiệm thành các API có hành động và resource rõ ràng.
2. Dùng danh tính và quyền được xác minh tại biên đáng tin cậy.
3. Kiểm tra authorization gần tài nguyên cần bảo vệ, kể cả quan hệ sở hữu/tenant nếu có.
4. Hạn chế quyền của tài khoản dịch vụ/DB, tránh cho một đường gọi bypass có toàn quyền với mọi bản ghi.
5. Không cho caller tự xác nhận “isAdmin=true” hoặc tạo một context tự khai rồi vượt qua chính sách.
6. Giới hạn việc expose đối tượng thô có thể thực hiện hành vi nhạy cảm.
7. Tách read-only API khỏi mutating API khi điều đó giúp giảm bề mặt truy cập.

AOP có ích để áp chính sách nhất quán và giảm code lặp, nhưng không thay thế cấu trúc quyền thực tế của resource manager, hệ thống xác thực và ranh giới dữ liệu.

## 14. Những nhầm lẫn phổ biến cần tránh

**Nhầm lẫn 1: “Có annotation/aspect ở phương thức nên bất kỳ lời gọi nào cũng được kiểm tra.”** Điều này chỉ đúng khi cơ chế runtime thật sự intercept join point đó trên mọi đường cần thiết. Kiểm tra cơ chế proxy/weaving và điểm vào.

**Nhầm lẫn 2: “Tự gọi phương thức luôn bỏ qua AOP.”** Sai nếu khẳng định cho tất cả công cụ. Proxy interception có rủi ro self-invocation; method-execution weaving có thể xử lý khác. Phải xác định mô hình.

**Nhầm lẫn 3: “Đổi sang reflection là sẽ bỏ qua guard.”** Không có quy tắc chung: reflection trên proxy có thể vẫn đi qua handler; reflection trên target thô có thể không. Điều quan trọng là receiver và vị trí interception.

**Nhầm lẫn 4: “Chặn API đầu vào là đủ; không cần bảo vệ service.”** Khi có job, worker, event consumer hoặc API khác tới cùng effect, một ranh giới đầu vào có thể không bao phủ mọi đường.

**Nhầm lẫn 5: “ThreadLocal đã có principal nên worker tự được bảo vệ.”** Context có thể không được propagate; có context cũng không có nghĩa authorization đã được đánh giá. Phải xác thực nguồn và kiểm tra đúng thời điểm.

**Nhầm lẫn 6: “Cache hit không có effect nên không gây rủi ro.”** Trả dữ liệu mật cho principal sai là một effect bảo mật quan trọng, dù không có ghi database.

**Nhầm lẫn 7: “Chỉ cần đếm advice đã chạy.”** Một số effect vẫn có thể xuất hiện trên nhánh không instrument; ngoài ra guard có thể đưa ra quyết định sai dù được gọi. Phải xác minh dữ liệu và effect.

**Nhầm lẫn 8: “Hủy future hoặc timeout chứng minh không có effect.”** Tác vụ có thể vẫn chạy và ghi dữ liệu sau khi caller nhận timeout. Cần theo dõi completion và thiết kế cancellation/idempotency rõ ràng.

**Nhầm lẫn 9: “Chính sách nội bộ có thể luôn fail open.”** Nếu thiếu danh tính hoặc service xác minh quyền, thao tác nhạy cảm phải có chính sách thất bại an toàn theo hợp đồng.

**Nhầm lẫn 10: “Test một endpoint thành công là xác nhận toàn bộ bảo vệ.”** Cần test mọi nhóm đường vào có thể đến cùng thao tác, kết hợp static review và kiểm tra runtime thực tế.

## 15. Quy trình review từng hành vi nhạy cảm

Để giảm nguy cơ đường gọi không đi qua cơ chế can thiệp, áp dụng quy trình sau:

**Bước 1 — Chọn effect nhạy cảm.** Xác định thao tác thực sự thay đổi hoặc làm lộ tài nguyên, chẳng hạn debitAccount, exportPrivateData hoặc deleteDocument.

**Bước 2 — Định nghĩa quyền cần kiểm tra.** Nêu action, resource, principal, tenant, trạng thái và nguồn tin cậy của dữ liệu quyền.

**Bước 3 — Vẽ đồ thị đường gọi.** Từ entry point tương tác, job, message và callback, lần theo mọi con đường chính tới effect. Ghi rõ đối tượng thực được dispatch.

**Bước 4 — Gắn vị trí join point/pointcut.** Đánh dấu advice được kỳ vọng chạy ở method-call hay method-execution, trên proxy hay code được weave.

**Bước 5 — Kiểm tra khe hở.** Self-invocation, target thô, không match pointcut, method không intercept được, classloader khác, asynchronous handoff, cache/fallback và đường vào mới.

**Bước 6 — Chọn ranh giới cưỡng chế tin cậy.** Bảo đảm mọi đường hợp lệ cuối cùng phải qua điểm quyết định quyền trước effect, dù điểm interception phụ trợ bị bỏ qua.

**Bước 7 — Kiểm tra thứ tự advice.** Cache, fallback, retry, logging và authorization có thể bỏ qua proceed() hoặc biến đổi outcome. Đừng để một advice ngoài cùng vô tình trả kết quả nhạy cảm trước guard.

**Bước 8 — Kiểm thử mọi kiểu đường.** Dùng principal có quyền và không có quyền; kiểm tra cả kết quả, log kiểm tra quyền và trạng thái effect sau cùng.

**Bước 9 — Xác nhận build/deploy.** Verify cấu hình proxy/weaving, classloader và điểm cắt đang hoạt động trên artifact triển khai, không chỉ trong một unit test.

**Bước 10 — Duy trì khi hệ thống thay đổi.** Mỗi entry point mới, đường gọi mới, thay đổi interface hoặc thay đổi chính sách cache/async đều cần kiểm tra lại độ bao phủ.

## 16. Ma trận quyết định: cơ chế nào đang bảo vệ?

| Tình huống | Nếu chỉ can thiệp tại proxy bên ngoài | Nếu weaving được cấu hình đúng tại method execution | Ranh giới tin cậy vẫn cần |
| --- | --- | --- | --- |
| Gọi method qua proxy | Handler/advice có cơ hội chạy | Advice ở method có thể chạy | Quyết định quyền chính xác |
| Gọi trực tiếp target gốc | Có thể bypass proxy | Có thể vẫn chạy nếu target đã được weave | Không expose effect trái quyền |
| Target gọi this.sensitive() | Thường không quay qua proxy | Có thể được instrument tại execution join point | Cưỡng chế trước effect |
| Method final/private | Phụ thuộc loại proxy; subclass override có giới hạn | Phụ thuộc công cụ và phạm vi weave | Không dựa vào giả định chung |
| Worker chạy callback sau return | Proxy ở hàm submit không tự bảo vệ callback | Chỉ bảo vệ nếu callback/effect cũng nằm trong tập được weave | Kiểm tra quyền tại execution khi cần |
| Reflection trên target | Có thể bỏ qua proxy | Phụ thuộc điểm weave được hỗ trợ | Kiểm tra effect độc lập đường gọi |
| Cache hit trước guard | Advice bên trong cache không chạy | Thứ tự policy vẫn có thể bỏ qua guard ở nhánh cache | Quyền truy cập dữ liệu cache |
| Class không nằm trong scope instrumentation | Proxy không tồn tại hoặc không được dùng | Advice không xuất hiện tại class ấy | Quyền ở service/resource |

Không nên đọc bảng thành lời khẳng định về mọi implementation. Nó nhấn mạnh rằng độ an toàn phụ thuộc vào cả **cơ chế interception**, **cấu hình** và **thiết kế policy**.

## 17. Bài tập tự kiểm tra

**Tình huống A.** Một phương thức sensitive() bị chặn khi caller dùng proxy. Nhưng cùng target có hàm batch() gọi this.sensitive(). Tại sao bài test gọi proxy.sensitive() chưa đủ?

**Trả lời:** bài test chỉ kiểm tra đường qua proxy. Lời gọi this.sensitive() có thể không quay qua proxy, nên cần test batch() và kiểm tra effect. Nếu dùng method-execution weaving, phải xác nhận thật sự có advice tại execution join point.

**Tình huống B.** Có một job theo lịch gọi trực tiếp một service nhạy cảm, trong khi kiểm tra quyền chỉ ở request handler. Điều gì cần làm?

**Trả lời:** xác định principal và quyền của job, đưa kiểm tra quyền tới ranh giới mà cả request handler và job đều phải đi qua, hoặc xây một đường kiểm soát tương đương có thể chứng minh; test job với quyền hợp lệ và không hợp lệ.

**Tình huống C.** Reflection gọi method trên chính object proxy. Có thể khẳng định chắc chắn bypass advice không?

**Trả lời:** không. Nếu receiver là proxy và method thuộc cơ chế proxy, lời gọi có thể vẫn qua interceptor. Phải kiểm tra receiver thật, dispatch và điểm weave.

**Tình huống D.** Cache bao ngoài Authorization; người dùng không có quyền nhận dữ liệu từ cache hit. Điều gì sai?

**Trả lời:** cache trả dữ liệu trước khi Authorization chạy. Cần bảo đảm guard bao phủ cả cache hit/miss, cache key và phân vùng dữ liệu đúng principal/resource, đồng thời kiểm tra ở ranh giới dữ liệu tin cậy.

**Tình huống E.** Advice ghi “đã kiểm tra quyền” khi submit một tác vụ; worker xử lý sau nhiều phút với quyền đã bị thu hồi. Có tự coi tác vụ đã được phép thực thi không?

**Trả lời:** không tự động. Hợp đồng phải định nghĩa quyền được cố định tại lúc submit hay phải đánh giá lại khi execute; nếu phải đánh giá tại execution, worker cần dùng danh tính đáng tin cậy và guard đúng thời điểm.

**Tình huống F.** Một test assert rằng lời gọi trái quyền ném exception, nhưng database đã bị cập nhật trước khi exception được ném. Có đạt mục tiêu không?

**Trả lời:** không. Quy tắc truy cập cần ngăn effect trái quyền; phải kiểm tra trạng thái sau lời gọi và điểm quyết định quyền **trước** side effect, không chỉ loại exception.

**Tình huống G.** Một final method không thể bị subclass proxy override. Có nên kết luận mọi AOP đều không can thiệp được vào final method?

**Trả lời:** không. Giới hạn này liên quan cơ chế subclass/override. Một số cơ chế weaving có khả năng khác; cần xác minh phương thức và mô hình join point thực tế.

**Tình huống H.** Unit test cho thấy aspect được đăng ký, nhưng một đường tạo new Target() vẫn chạy. Kết luận?

**Trả lời:** sự tồn tại của aspect không chứng minh mọi instance được bảo vệ. Cần kiểm soát cách tạo và phân phối tham chiếu, thêm test cho direct target và bảo vệ tại ranh giới effect.

## 18. Kết luận kỹ thuật

Nguy cơ đường gọi không qua cơ chế can thiệp xuất hiện khi **điểm AOP được bảo vệ** không nằm trên **mọi đường thực thi tới một hiệu ứng nhạy cảm**. Nguyên nhân có thể là self-invocation qua target, tham chiếu đối tượng thô, giới hạn loại method, sai pointcut, class không được weave, các entry point khác, callback bất đồng bộ, hoặc advice ngoài cùng bỏ qua nhánh authorization.

Để kiểm soát rủi ro, cần làm rõ **đường gọi nào kích hoạt join point**, **receiver nào được sử dụng**, **authorization được cưỡng chế tại ranh giới nào**, và **effect nào có thể xảy ra nếu advice không chạy**. AOP nên giúp áp dụng kiểm soát một cách nhất quán và quan sát được; còn tính an toàn phải được xác minh trên mọi đường hợp lệ tới tài nguyên bằng thiết kế quyền tin cậy, kiểm thử âm tính ở cấp effect và kiểm tra cấu hình thực thi thực tế.