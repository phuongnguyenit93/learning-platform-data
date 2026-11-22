# Kết hợp điều kiện ngữ cảnh với phạm vi cấu trúc trong AOP

Một **pointcut theo ngữ cảnh** có thể trả lời câu hỏi “lời gọi này xảy ra với đối tượng, tham số hoặc hoàn cảnh thực thi nào?”. Trong khi đó, điều kiện **phạm vi cấu trúc** thường trả lời “đây là loại join point nào, nằm ở lớp/gói/thành phần nào và mang chữ ký phương thức gì?”. Kết hợp hai nhóm điều kiện giúp AOP chọn **đúng nơi, đúng lần thực thi**, thay vì áp dụng hành vi cắt ngang cho mọi phương thức cùng tên hoặc mọi lời gọi thỏa một giá trị dữ liệu.

Ví dụ, giả sử muốn đo riêng những lần xử lý đơn hàng **ưu tiên cao**, có số lượng lớn, tại một phương thức nghiệp vụ cụ thể:

- Điều kiện cấu trúc: đây là lần thực thi thao tác xử lý đơn hàng, thuộc phạm vi thành phần đã chọn.
- Điều kiện ngữ cảnh: đối tượng thực tế thuộc loại nghiệp vụ cần đo, tham số mức ưu tiên là “critical” và số lượng lớn hơn hoặc bằng một ngưỡng.
- Advice: chỉ ghi số liệu cho những lần **đồng thời thỏa hai nhóm điều kiện**.

Mục tiêu của bài là hiểu cách thiết kế, kết hợp, đánh giá và kiểm thử các điều kiện này trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP) nói chung**. Cú pháp biểu thức và tập join point được hỗ trợ có thể khác nhau giữa các cơ chế; những đoạn giả mã dưới đây minh họa **ngữ nghĩa**, không khẳng định là cú pháp dùng chung cho mọi công cụ.

## 1. Nhắc lại các thành phần tham gia

- **Join point (điểm nối):** điểm trong quá trình chạy chương trình mà cơ chế AOP có thể gắn hành vi, chẳng hạn lời gọi hoặc lần thực thi phương thức nếu được hỗ trợ.
- **Pointcut (bộ chọn điểm):** một quy tắc xác định tập join point cần áp dụng hành vi.
- **Advice:** hành vi bổ sung chạy tại điểm được chọn, như ghi log, đo thời gian hoặc kiểm tra chính sách.
- **Context binding / exposure:** cách cung cấp cho pointcut/advice thông tin của lần thực thi, ví dụ đối tượng đích, tham số, đối tượng bên gọi hoặc ngữ cảnh luồng gọi.
- **Weaving:** cách kết hợp advice với điểm được chọn, có thể bằng biến đổi mã/bytecode, proxy hoặc kỹ thuật khác.

Một pointcut có thể chứa điều kiện dựa trên **cấu trúc tĩnh**, **ngữ cảnh runtime**, hoặc **kết hợp cả hai**. “Tĩnh” ở đây nói về dữ liệu có thể suy ra từ cấu trúc/chữ ký, không có nghĩa mọi hệ thống AOP buộc phải tính chúng tại compile time. Tương tự, một điều kiện “ngữ cảnh” không nhất thiết chỉ xét tham số: nó có thể xét kiểu của target, caller, control flow hoặc dữ liệu khác mà mô hình join point công bố.

## 2. Hai nhóm điều kiện khác nhau ở đâu?

| Tiêu chí | Điều kiện phạm vi cấu trúc | Điều kiện ngữ cảnh |
| --- | --- | --- |
| Câu hỏi chính | Join point *nằm ở đâu, thuộc loại nào?* | Lần thực thi *diễn ra với dữ liệu và hoàn cảnh nào?* |
| Dữ liệu thường dùng | Loại call/execution, gói, lớp, chữ ký, tên/kiểu tham số khai báo, phạm vi mã | Target/caller runtime, đối số thực tế, quan hệ kiểu động, ngữ cảnh lời gọi, điều kiện đánh giá lúc chạy |
| Tần suất thay đổi | Thường ổn định theo vị trí mã/chữ ký | Có thể khác ở từng lần gọi |
| Ví dụ | “Các lần thực thi phương thức execute trong nhóm xử lý giao dịch” | “Target là OrderTask và đối số level là critical” |
| Lỗi điển hình | Chọn phạm vi quá rộng, sai call/execution, bỏ sót overload | Sai đối tượng, null, dữ liệu thiếu/tin nhầm đầu vào, điều kiện thay đổi theo thời gian |
| Tác dụng khi phối hợp | Giới hạn tập điểm ứng viên | Chọn những sự kiện cần xử lý *trong* tập ứng viên |

Ví dụ một phương thức `process(String category, int count)` có thể chạy hàng nghìn lần. Về cấu trúc, những lần thực thi này đều thuộc cùng một vị trí. Nhưng ngữ cảnh mỗi lần khác nhau: có lần `category="critical"`, có lần `category="normal"`, có lần đối tượng đích là triển khai khác. Một pointcut kết hợp có thể khớp chỉ vài lần thực thi trong số đó.

### 2.1 “Kiểu” có thể là cấu trúc hoặc ngữ cảnh

Đừng suy rằng mọi kiểm tra kiểu là tĩnh. **Kiểu khai báo ở chữ ký** là thông tin cấu trúc; **kiểu runtime của target hoặc đối số** là thông tin động.

Giả sử lời gọi được biên dịch qua một biến kiểu giao diện nhưng đối tượng thật thuộc lớp `OrderTask`. Điều kiện chữ ký theo giao diện có thể khớp nhiều triển khai; điều kiện `target instanceof OrderTask` chỉ khớp một nhóm đối tượng runtime. Chúng bổ sung cho nhau, không có ý nghĩa tương đương.

## 3. Mô hình toán học: giao của hai tập điểm

Gọi:

- `J`: tập join point mà cơ chế AOP hỗ trợ xem xét.
- `S(j)`: điều kiện cấu trúc đúng cho điểm `j`.
- `C(j, ctx)`: điều kiện ngữ cảnh đúng cho điểm `j` ở ngữ cảnh `ctx` của **lần chạy hiện tại**.

Điểm được chọn khi:

~~~text
selected(j, ctx) = S(j) AND C(j, ctx)
~~~

Tập điểm **có khả năng** được chọn trước hết bị giới hạn bởi `S`; trong số đó, `C` xác định từng lần thực thi có thực sự khớp hay không.

~~~text
Tất cả join point được hỗ trợ (J)
                  |
                  v
     [Kiểm tra phạm vi cấu trúc S]
          |                  |
        false               true
          |                  |
     Không áp dụng           v
                  [Lấy/ràng buộc context]
                            |
                            v
                  [Kiểm tra điều kiện C]
                     |              |
                   false           true
                     |              |
                 Không chạy         v
                    advice      Chạy advice
~~~

Sơ đồ diễn giải logic; nó không áp đặt thứ tự máy thực hiện mọi phép kiểm tra. Một trình biên dịch/weaver có thể tối ưu biểu thức mà vẫn giữ ngữ nghĩa quan sát được. Cần phân biệt **mô tả tập điểm** với **thứ tự hoạt động vật lý** của mã instrument.

### 3.1 Vì sao nên lấy giao S AND C?

Nếu chỉ dùng `S`, chính sách có thể tác động cả các yêu cầu bình thường không cần đo. Nếu chỉ dùng `C`, điều kiện “level=critical” có thể khớp cả phương thức thuộc thành phần khác, nơi cùng tham số mang ý nghĩa khác. **Giao của hai điều kiện** vừa giới hạn vị trí vừa giới hạn tình huống.

Ví dụ:

~~~text
S = execution(các phương thức xử lý đơn hàng)
C = target thuộc OrderTask AND level == "critical"

P = S AND C
~~~

Các tên biểu thức trên là **giả mã**, không phải cú pháp AOP phổ quát.

## 4. Khi nào dùng AND, OR và NOT?

Các biểu thức pointcut phong phú có thể cho phép **hội (AND)**, **tuyển (OR)** và **phủ định (NOT)**, cũng như nhóm điều kiện bằng dấu ngoặc.

### 4.1 AND: cả hai cùng đúng

~~~text
P = StructureScope AND RuntimeCondition
~~~

Dùng khi cần chính sách ở một phạm vi cụ thể *và* một hoàn cảnh cụ thể. Ví dụ đo thời gian các thao tác thanh toán khi chúng thuộc nhóm xử lý giao dịch và đang dùng phương thức thanh toán chậm cần theo dõi.

### 4.2 OR: chọn hợp của các nhánh

~~~text
P = (OrderStructure AND OrderContext)
    OR
    (ReportStructure AND ReportContext)
~~~

Hai nhóm nghiệp vụ có thể cần chung một advice nhưng tiêu chí riêng. **Nhóm ngoặc là bắt buộc về mặt diễn giải**, nhất là khi phối hợp nhiều toán tử.

### 4.3 NOT: loại trừ có chủ đích

~~~text
P = BusinessStructure
    AND RuntimeCondition
    AND NOT InfrastructureHelperStructure
~~~

Dùng để tránh pointcut rộng vô tình chạm vào logging helper, adapter hoặc mã phụ trợ. Tuy nhiên, phủ định cần được thử kỹ: loại trừ một nhóm phương thức chỉ vì tên lớp có thể bỏ sót trường hợp nghiệp vụ hợp lệ.

### 4.4 Hai biểu thức gần giống nhưng chọn khác

~~~text
P1 = (S1 OR S2) AND C

P2 = S1 OR (S2 AND C)
~~~

Với `P1`, **mọi điểm** thuộc `S1` hoặc `S2` đều phải thỏa `C`. Với `P2`, toàn bộ `S1` được chọn **ngay cả khi `C` sai**.

Giả sử `S1` là giao dịch thanh toán, `S2` là hoàn tiền và `C` là mức ưu tiên “critical”. Nếu yêu cầu chỉ tác động các giao dịch critical thì `P2` quá rộng: nó chọn cả thanh toán bình thường. Đây là lý do phải viết **ngoặc theo ý định**, dù một ngôn ngữ pointcut có quy tắc ưu tiên toán tử được công bố.

Bảng chân trị rút gọn:

| S1 | S2 | C | (S1 OR S2) AND C | S1 OR (S2 AND C) |
| --- | --- | --- | --- | --- |
| true | false | false | false | **true** |
| true | false | true | true | true |
| false | true | false | false | false |
| false | true | true | true | true |
| false | false | true | false | false |

Khi xây pointcut cho nhiều chức năng, một bảng chân trị nhỏ thường phát hiện lỗi phạm vi tốt hơn việc đọc lướt biểu thức dài.

## 5. Chọn ngữ cảnh nào? Không phải mọi dữ liệu đều giống nhau

Điều kiện ngữ cảnh có thể dựa vào những thành phần khác nhau:

| Thành phần | Ý nghĩa thường gặp | Lưu ý |
| --- | --- | --- |
| **Target** | Đối tượng nhận hoặc thực hiện thao tác đang quan sát | Khác proxy/caller; runtime class phụ thuộc đối tượng được xét |
| **This / caller context** | Đối tượng đang thực thi mã tại một điểm thích hợp | Ở call join point có thể khác target; static context có thể không có instance |
| **Arguments** | Đối số thực tế của lần gọi | Xử lý null, boxing, kiểu khai báo so với runtime và chính sách bảo mật |
| **Control-flow context** | Điểm này có nằm trong luồng điều khiển của thao tác được chọn không? | Phụ thuộc mô hình hỗ trợ; có thể phát sinh overhead |
| **Annotation/metadata** | Dấu hiệu khai báo trên phương thức/lớp hoặc metadata của đối tượng | Annotation tĩnh không tự đồng nghĩa điều kiện runtime |
| **Custom state/context** | Correlation ID, danh tính, cờ vận hành đã được cung cấp đúng cách | Phải xét tính tin cậy, vòng đời và truyền qua luồng bất đồng bộ |

Một **kiểu tham số trong chữ ký** là thông tin cấu trúc; giá trị của tham số ở một lời gọi là ngữ cảnh. Một **annotation khai báo** có thể là bộ chọn cấu trúc; đọc đối tượng annotation của một lần thực thi, nếu cơ chế có hỗ trợ, lại có cách biểu diễn/đánh giá khác. Vì vậy cần gọi tên đúng **dữ liệu** và **thời điểm** được dùng trong từng điều kiện.

### 5.1 Control flow là ngữ cảnh thực thi

Một số mô hình AOP cho phép điều kiện “chỉ khớp khi điểm này xảy ra trong luồng điều khiển của thao tác X”. Chẳng hạn cùng `repository.save()` nhưng chỉ muốn ghi một loại trace khi được gọi trong quá trình nhập dữ liệu.

Khác với giới hạn lớp/gói, điều kiện này phụ thuộc **chuỗi lời gọi đang hoạt động**. Tuy nhiên, không mặc định rằng control flow được truyền qua tác vụ bất đồng bộ, thread mới hoặc luồng xử lý rời rạc: khái niệm “đang nằm trong cflow” phải được xác định theo mô hình và ranh giới thực thi thật sự.

### 5.2 Context được dùng để *lọc* hay *truyền cho advice*?

Hai việc khác nhau:

- **Context condition** quyết định `true/false` để chọn điểm.
- **Context binding** đặt dữ liệu như `target`, `args` hoặc id vào phạm vi mà advice có thể sử dụng.

Một pointcut có thể chọn tất cả thao tác đặt hàng theo cấu trúc rồi binding tham số `amount` để advice đo hoặc ghi log; không nhất thiết phải lọc theo `amount`. Ngược lại, nếu chỉ muốn chọn các thao tác vượt ngưỡng, một điều kiện ngữ cảnh có thể kiểm tra `amount >= threshold`.

Hãy tránh nhầm **“advice nhận được tham số”** với **“tham số đó đã được kiểm tra trong pointcut”**.

## 6. Tính tĩnh, tính động và ngữ nghĩa đánh giá

Giả sử có 100 lớp nhưng chỉ 4 lớp nằm trong cấu trúc được chọn. Cơ chế AOP có thể loại trừ nhiều vị trí không phù hợp ngay khi phân tích mã, rồi chỉ cần đánh giá điều kiện ngữ cảnh cho những điểm còn lại. Đây là một hướng tối ưu hợp lý, nhưng khả năng thực thi cụ thể phụ thuộc công cụ.

Ba mức quyết định có thể gặp:

1. **Xác định từ cấu trúc:** thông tin loại join point, chữ ký, phạm vi kiểu và một số metadata.
2. **Xác định từ đối tượng lúc chạy:** instance nào đang nhận lời gọi, kiểu runtime nào, tham số thực tế là gì.
3. **Xác định từ trạng thái động khác:** quan hệ luồng điều khiển, ngữ cảnh giao dịch hoặc trạng thái được cung cấp riêng.

Không nên tự cho phép những biểu thức điều kiện tùy ý tạo **tác dụng phụ**. Nếu một pointcut phải gọi hàm có khả năng ghi dữ liệu, lấy khóa hoặc thay trạng thái, việc tối ưu hóa/thay đổi thứ tự đánh giá có thể làm hệ thống khó dự đoán. Nên ưu tiên các điều kiện thuần túy, ngắn, có nghĩa rõ ràng.

Khi kết hợp AND, ngôn ngữ có thể công bố **short-circuit** hoặc cho phép trình triển khai bố trí lại những phép thử phù hợp để tối ưu. Không dựa vào thứ tự của các phép thử pointcut để thực hiện hành vi nghiệp vụ. Nếu một hành vi phải xảy ra theo thứ tự, hãy tổ chức nó trong advice hoặc trong cơ chế có hợp đồng thứ tự rõ ràng.

## 7. Ví dụ Java 17 chạy độc lập: ghép S AND C tại một điểm bọc

Ví dụ dưới đây dùng **dynamic proxy của Java** để minh họa nguyên tắc chọn bằng hai lớp điều kiện. Đây là chương trình chạy độc lập, **không phải cú pháp pointcut chuẩn của một bộ AOP** và chỉ can thiệp lời gọi đi qua proxy.

Ta có giao diện `Task`, hai triển khai `OrderTask` và `ReportTask`. Điều kiện cấu trúc `S` chọn phương thức `execute(String,int)` của giao diện. Điều kiện ngữ cảnh `C` yêu cầu **đích là OrderTask**, `level="critical"` và `items >= 3`. Chỉ khi **S AND C** đúng, advice mới in sự kiện trước/sau/lỗi.

Lưu thành file `ContextAndStructureDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class ContextAndStructureDemo {
    public interface Task {
        String execute(String level, int items);
        String status();
    }

    public static final class OrderTask implements Task {
        @Override
        public String execute(String level, int items) {
            System.out.println("BUSINESS order level=" + level
                    + " items=" + items);
            if (items == 9) {
                throw new IllegalArgumentException("demo rejection");
            }
            return "order:" + items;
        }

        @Override
        public String status() {
            System.out.println("BUSINESS status");
            return "OK";
        }
    }

    public static final class ReportTask implements Task {
        @Override
        public String execute(String level, int items) {
            System.out.println("BUSINESS report level=" + level
                    + " items=" + items);
            return "report:" + items;
        }

        @Override
        public String status() {
            return "OK";
        }
    }

    // S: chọn phạm vi/chữ ký cấu trúc.
    static boolean matchesStructure(Method method) {
        return method.getDeclaringClass() == Task.class
                && method.getName().equals("execute")
                && Arrays.equals(method.getParameterTypes(),
                        new Class<?>[] { String.class, int.class });
    }

    // C: kiểm tra ngữ cảnh của lời gọi hiện tại.
    static boolean matchesContext(Task target, Object[] args) {
        return target instanceof OrderTask
                && args.length == 2
                && "critical".equals(args[0])
                && args[1] instanceof Integer count
                && count >= 3;
    }

    static Object invokeOriginal(Method method, Task target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static Task wrap(Task target) {
        return (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[] { Task.class },
                (proxy, method, args) -> {
                    Object[] actualArgs =
                            args == null ? new Object[0] : args.clone();

                    // Chỉ kích hoạt advice khi S AND C đúng.
                    if (!matchesStructure(method)
                            || !matchesContext(target, actualArgs)) {
                        return invokeOriginal(method, target, actualArgs);
                    }

                    System.out.println("ADVICE before execute");
                    try {
                        Object result =
                                invokeOriginal(method, target, actualArgs);
                        System.out.println("ADVICE after " + result);
                        return result;
                    } catch (Throwable error) {
                        System.out.println("ADVICE error "
                                + error.getClass().getSimpleName());
                        throw error;
                    }
                });
    }

    public static void main(String[] args) {
        Task order = wrap(new OrderTask());
        Task report = wrap(new ReportTask());

        System.out.println("RETURN " + order.execute("critical", 3));
        System.out.println("RETURN " + order.execute("normal", 5));
        System.out.println("RETURN " + order.execute("critical", 2));
        System.out.println("RETURN " + report.execute("critical", 4));
        System.out.println("RETURN " + order.status());

        try {
            order.execute("critical", 9);
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac ContextAndStructureDemo.java
java ContextAndStructureDemo
~~~

Stdout:

~~~text
ADVICE before execute
BUSINESS order level=critical items=3
ADVICE after order:3
RETURN order:3
BUSINESS order level=normal items=5
RETURN order:5
BUSINESS order level=critical items=2
RETURN order:2
BUSINESS report level=critical items=4
RETURN report:4
BUSINESS status
RETURN OK
ADVICE before execute
BUSINESS order level=critical items=9
ADVICE error IllegalArgumentException
CALLER demo rejection
~~~

### 7.1 Vì sao từng lần gọi có kết quả khác nhau?

| Lời gọi | S: `execute(String,int)` | C: OrderTask, critical, items ≥ 3 | Advice chạy? |
| --- | --- | --- | --- |
| `order.execute("critical", 3)` | true | true | Có, trước và sau thành công |
| `order.execute("normal", 5)` | true | false (level) | Không |
| `order.execute("critical", 2)` | true | false (items) | Không |
| `report.execute("critical", 4)` | true | false (target) | Không |
| `order.status()` | false | Không cần xét | Không |
| `order.execute("critical", 9)` | true | true | Có, trước và khi lỗi |

Trong ví dụ, `matchesStructure` nhìn vào `Method` được proxy cung cấp: một chữ ký của giao diện `Task`. `matchesContext` nhận **target thực**, `args` của từng lần gọi. Điều kiện và advice nằm ở các hàm Java minh họa để nhìn thấy ranh giới trách nhiệm.

Khi không khớp, chương trình **vẫn gọi nghiệp vụ** qua `invokeOriginal`, chỉ bỏ qua advice quan sát. Khi nghiệp vụ ném `IllegalArgumentException`, reflection bọc trong `InvocationTargetException`; hàm chuyển tiếp tháo lớp bọc bằng `getCause()` và advice ghi nhánh `error` rồi ném tiếp lỗi gốc.

### 7.2 Giới hạn của ví dụ

- Dynamic proxy chỉ chặn các lời gọi **đi qua proxy** và giao diện được cung cấp. Gọi trực tiếp `new OrderTask().execute(...)` không kích hoạt advice tại proxy này.
- Bộ chọn trong ví dụ là các hàm Java thông thường, **không phải** một ngôn ngữ pointcut phổ quát.
- Hàm `matchesStructure` quan sát chữ ký `Method` tại proxy, **không chứng minh** mọi mô hình method-call hay method-execution AOP đều có cùng declaring class.
- `args.clone()` tạo một bản sao nông của mảng đối số; bản sao không biến đối số thành dữ liệu bất biến hoặc đáng tin.
- Ví dụ quan sát đơn giản theo `level` và `items`, không dùng chúng để đưa ra quyết định an ninh. Nếu thay bằng phân quyền thật, phải lấy chủ thể từ nguồn xác thực đáng tin, kiểm tra quyền trên tài nguyên cụ thể và bao phủ mọi đường vào cần bảo vệ.

## 8. Thiết kế biểu thức kết hợp ở mức nâng cao

### 8.1 Phân nhóm theo mục đích, đặt tên rõ

Giả sử có ba phạm vi:

~~~text
paymentOperations = cấu trúc các thao tác thanh toán
refundOperations  = cấu trúc các thao tác hoàn tiền
sensitiveContext  = ngữ cảnh có mức rủi ro cao

highRiskOperations =
    (paymentOperations OR refundOperations)
    AND sensitiveContext
~~~

Đặt tên cho các thành phần tạo ra quy tắc dễ kiểm tra hơn một biểu thức dài chứa nhiều điều kiện lặp. Nếu các điều kiện cấu trúc có phần chung, tái sử dụng phần ấy để tránh thay đổi không nhất quán.

Tuy nhiên, **tên một pointcut không thay thế hợp đồng của nó**. Khi thay phạm vi từ “thanh toán” thành “giao dịch” rộng hơn, phải kiểm tra những điểm mới được đưa vào có thực sự cần chịu advice đó hay không.

### 8.2 Cùng cấu trúc, nhiều hoàn cảnh

~~~text
P1 = ServiceExecution AND CriticalRequest
P2 = ServiceExecution AND SlowTenantContext
~~~

Một join point cấu trúc có thể được dùng cho nhiều chính sách ngữ cảnh. Nhưng `CriticalRequest` và `SlowTenantContext` có ý nghĩa khác nhau: một điều kiện liên quan yêu cầu nghiệp vụ, một điều kiện liên quan cấu hình/đặc tính vận hành. Tránh gom cả hai thành một “context quan trọng” mơ hồ nếu hành vi thay đổi độc lập.

### 8.3 Nhiều cấu trúc, chung một hoàn cảnh

~~~text
P = (CreateOrderExecution OR CancelOrderExecution)
    AND ObservedEnvironment
~~~

Khi điều kiện `ObservedEnvironment` chỉ được phép áp dụng cho **cả hai nhóm**, hãy đặt nó ngoài ngoặc bao hai điều kiện cấu trúc. Nếu đặt thành `CreateOrderExecution OR (CancelOrderExecution AND ObservedEnvironment)`, mọi lần tạo đơn đều bị áp dụng advice bất kể môi trường. Đây là lỗi rất thường gặp khi thêm `OR` vào một pointcut đang có `AND`.

### 8.4 Loại trừ lời gọi hạ tầng hoặc mã sinh

Đôi khi điểm chọn theo tên/kiểu bắt cả wrapper, helper, adapter hoặc phương thức do compiler/runtime tạo. Cần hiểu mô hình join point và đặt điều kiện loại trừ phù hợp:

~~~text
P = BusinessScope
    AND RelevantRuntimeContext
    AND NOT InternalInstrumentationScope
~~~

Mục đích là tránh việc advice gọi helper, helper lại khớp pointcut và kích hoạt advice lần nữa. Nhưng loại trừ theo tên lớp chung chung có thể bỏ sót nghiệp vụ thật. Hãy kiểm tra *điểm cụ thể* thay vì chỉ xét tên trông giống hạ tầng.

## 9. Bẫy lớn: nhầm pointcut quan sát với rào chắn bảo mật

Kết hợp `S AND C` phù hợp khi một advice **chỉ cần chạy trong một số hoàn cảnh**, như log bổ sung cho yêu cầu ưu tiên cao hoặc phép đo được lấy mẫu. Nhưng phải cẩn thận nếu advice giữ vai trò **kiểm tra bắt buộc**.

**Thiết kế nguy hiểm:** đặt `C = user has permission` trong pointcut rồi chỉ chạy advice kiểm tra quyền khi `C` đúng. Các lời gọi không đủ quyền có thể không khớp pointcut và **bỏ qua advice**, khiến nghiệp vụ chạy nếu không có rào chắn khác.

**Ý định cần thể hiện:** chọn **toàn bộ điểm cần bảo vệ** bằng phạm vi tin cậy; trong advice (hoặc ranh giới bảo vệ thích hợp) kiểm tra quyền của chủ thể đã được xác thực rồi **cho phép hoặc chặn** trước tác dụng phụ. Chỉ dùng điều kiện ngữ cảnh để thu hẹp phạm vi kiểm soát khi đã chứng minh các trường hợp bị loại trừ không cần bảo vệ.

Cũng không nên nhầm một tham số tên `role` hay `userId` với danh tính đã được xác thực. **Binding cung cấp dữ liệu; nguồn và ý nghĩa tin cậy của dữ liệu phải được bảo đảm riêng.**

## 10. Null, kiểu runtime, overload và các trường hợp biên

### 10.1 Null và kiểm tra tham số

Một giá trị `null` không có runtime class: gọi `getClass()` trên nó ném `NullPointerException`. Nếu điều kiện chỉ cần so sánh chuỗi, đặt hằng bên trái như `"critical".equals(level)` giúp xử lý null an toàn.

Nếu một pointcut muốn chọn theo **kiểu tham số được khai báo**, thông tin chữ ký có thể vẫn đầy đủ khi đối số thực tế là null. Nhưng nếu muốn chọn theo **kiểu runtime của đối số**, phải xác định quy tắc đối với null và xem mô hình AOP hỗ trợ loại kiểm tra nào.

### 10.2 Overload và kiểu khai báo

Các phương thức `process(String)` và `process(Object)` là hai overload khác nhau. Chọn theo tên đơn thuần có thể áp dụng cả hai; chọn đúng chữ ký cần xét danh sách kiểu tham số. Trình biên dịch chọn overload theo kiểu tĩnh của biểu thức đối số và quy tắc ngôn ngữ, không đơn giản dựa trên runtime class của giá trị.

### 10.3 Call, execution và đường gọi thực tế

Phạm vi cấu trúc có thể chọn **điểm gọi phương thức (call)** hoặc **lần thực thi phần thân (execution)** nếu nền tảng hỗ trợ. Hai loại điểm có thể có chữ ký/đối tượng ngữ cảnh và phạm vi quan sát khác nhau.

Khi gọi qua interface, một pointcut theo chữ ký tại call site có thể mang kiểu tĩnh khác với phần thân thực thi trong lớp con. Với cơ chế proxy, gọi nội bộ qua `this` hoặc gọi trực tiếp đối tượng gốc có thể bỏ qua lớp bọc. Do đó “điều kiện S và C đều đúng” **chưa đủ** nếu điểm đó không nằm trong tập join point có thể can thiệp.

### 10.4 Generic, bridge và synthetic

Type erasure của Java có thể tạo chữ ký bytecode khác với khai báo generic trong nguồn. Compiler đôi khi sinh bridge/synthetic method để giữ đa hình. Một bộ quét Reflection thấy hai phương thức không đồng nghĩa hệ thống AOP có hai execution join point hoặc advice chắc chắn chạy hai lần.

Khi xây điều kiện cấu trúc theo chữ ký, cần biết công cụ match mã nguồn, descriptor sau erasure, hay một tập join point đã chuẩn hóa. Đừng tạo một điều kiện AND sai chỉ vì hiểu nhầm chữ ký của bridge là chữ ký nghiệp vụ.

### 10.5 Ngữ cảnh bất đồng bộ

Ngữ cảnh nằm trong lời gọi đồng bộ có thể không tồn tại nguyên trạng khi công việc chuyển sang thread, executor, queue hoặc một bước callback khác. Nếu điều kiện yêu cầu correlation ID hay danh tính, phải có cách truyền và khôi phục phù hợp, đồng thời tránh rò dữ liệu giữa các tác vụ tái sử dụng luồng.

Nếu đo thời gian một hàm chỉ **khởi phát** tác vụ bất đồng bộ rồi trả về, advice quanh hàm đó đo thời gian khởi phát; nó không mặc nhiên đo thời gian đến khi tác vụ thực sự hoàn thành.

## 11. Hiệu năng và sự ổn định của điều kiện

Điểm chạy thường xuyên có thể làm overhead của pointcut/advice tăng đáng kể. Những nguyên tắc thực tế:

- Giữ phạm vi cấu trúc rõ ràng để giảm số điểm phải xem xét.
- Ưu tiên điều kiện ngữ cảnh thuần túy, nhanh, không có tác dụng phụ và tránh thao tác I/O hay lấy thêm khóa.
- Cẩn thận với các phép kiểm tra đòi tra cứu mạng/cơ sở dữ liệu mỗi lần gọi: chúng có thể thay đổi cả hiệu năng lẫn hành vi nghiệp vụ.
- Tránh đọc dữ liệu nhạy cảm trong điều kiện hoặc log nếu không cần.
- Không dùng trạng thái global dễ thay đổi mà không có chính sách đồng bộ; kết quả match giữa các lần gọi có thể thay đổi khó dự đoán.
- Nếu áp dụng sampling, thiết kế rõ điều kiện chọn mẫu và kiểm chứng số liệu không bị thiên lệch ngoài mong muốn.

Không nên mô tả một pointcut động là “luôn được tối ưu sau khi lọc cấu trúc”. Điều này phụ thuộc implementation. Có những phép kiểm tra tĩnh có thể được tối ưu, nhưng thứ tự và mức độ tiết kiệm thực tế cần được xác minh ở công cụ đang dùng.

## 12. Kiểm thử theo ma trận cấu trúc và ngữ cảnh

Một bộ kiểm thử tốt nên tách ít nhất bốn nhóm kết quả:

| Nhóm | S | C | Kết quả cần có |
| --- | --- | --- | --- |
| Khớp cả hai | true | true | Advice chạy đúng một lần theo chính sách |
| Chỉ khớp cấu trúc | true | false | Nghiệp vụ chạy, advice có điều kiện không chạy |
| Không khớp cấu trúc | false | Không cần xét | Advice không chạy |
| Điểm không được nền tảng quan sát | Có thể đúng về ý tưởng | Có thể đúng về dữ liệu | Không được suy rằng advice chắc chắn chạy |

Với ví dụ Java ở trên, các lời gọi `order.execute("normal",5)` và `report.execute("critical",4)` giúp tách hai nguyên nhân khiến `C` sai. `order.status()` kiểm chứng `S` sai. `order.execute("critical",9)` kiểm chứng lời gọi vừa khớp vừa ném ngoại lệ; advice phải ghi lỗi, không được ghi thành công và không được nuốt lỗi.

Những kiểm tra bổ sung cần làm với chương trình thực:

1. **Mỗi nhánh AND/OR/NOT:** lập bảng chân trị, thử cả điều kiện giao nhau và loại trừ.
2. **Kiểu và chữ ký:** interface, lớp con, override, overload, generic, giá trị null, dữ liệu không đúng kiểu.
3. **Ngữ cảnh:** target, caller, args, control flow, metadata, và thời điểm dữ liệu được binding.
4. **Phạm vi weaving:** lời gọi qua proxy, lời gọi trực tiếp, lời gọi nội bộ, tác vụ nền và các lối vào khác.
5. **Ngoại lệ:** after-success không chạy trên lỗi; after-error và finally theo đúng hợp đồng, kết quả/lỗi nghiệp vụ được giữ.
6. **Nhiều advice cùng khớp:** thứ tự can thiệp, khả năng tái nhập và tác dụng phụ phải được xác minh.
7. **An ninh:** những thao tác cần bảo vệ vẫn phải được kiểm tra trên mọi đường vào, kể cả khi điều kiện ngữ cảnh của một advice quan sát là false.

## 13. Bài tập phân tích

Một dự án muốn ghi trace cho **mọi thao tác tạo hoặc hủy đơn hàng có mức ưu tiên cao**, nhưng bỏ qua getter và phương thức hạ tầng.

Có người đề xuất:

~~~text
P = CreateOrder OR (CancelOrder AND HighPriority)
~~~

**Vấn đề:** biểu thức chọn toàn bộ `CreateOrder`, kể cả các lần không có ưu tiên cao. Nó chỉ yêu cầu `HighPriority` đối với `CancelOrder`.

Biểu thức đúng với yêu cầu là:

~~~text
P = (CreateOrder OR CancelOrder)
    AND HighPriority
    AND NOT InfrastructureHelper
~~~

Ở đây, `CreateOrder`, `CancelOrder`, `InfrastructureHelper` là các điều kiện cấu trúc; `HighPriority` là điều kiện dựa trên ngữ cảnh của lần chạy. Nếu điều kiện “ưu tiên cao” phụ thuộc vào tham số, cần ràng buộc đúng tham số và kiểm tra null/giá trị không hợp lệ. Nếu nó đến từ một trạng thái nghiệp vụ được tính trong lời gọi, cần bảo đảm điểm can thiệp có thể quan sát dữ liệu tại thời điểm điều kiện được đánh giá.

**Câu hỏi:** Nếu thao tác tạo đơn được gọi trực tiếp qua đối tượng gốc nhưng hệ thống chỉ đặt advice tại proxy, biểu thức pointcut đúng có bảo đảm ghi trace không?

**Đáp:** không. Điều kiện khớp về mặt logic không thay thế khả năng can thiệp thực tế. Cần kiểm chứng mọi đường gọi mà chính sách phải bao phủ.

**Câu hỏi:** Nếu trace chỉ được yêu cầu cho ưu tiên cao, có được dùng cùng điều kiện để bỏ qua kiểm tra quyền của ưu tiên bình thường không?

**Đáp:** không thể tự suy như vậy. Trace có thể là quan sát có điều kiện; kiểm soát quyền là chính sách bắt buộc theo phạm vi hành động và phải được thiết kế độc lập.

## 14. Ghi nhớ

Có thể tự rà soát một pointcut kết hợp bằng bốn câu hỏi:

1. **Cấu trúc:** join point nào được chọn theo loại điểm, chữ ký, lớp/gói hoặc phạm vi mã?
2. **Ngữ cảnh:** dữ liệu runtime nào phải đúng trong chính lần chạy đó? Có cần phân biệt target/caller/arguments/control flow không?
3. **Logic:** điều kiện phải là `S AND C`, `(S1 OR S2) AND C`, hay có loại trừ `NOT`? Dấu ngoặc có bảo toàn yêu cầu?
4. **Thực thi:** cơ chế AOP có quan sát được điểm này không, binding có đúng và advice có giữ nguyên kết quả/ngoại lệ không?

**Kết luận:** phạm vi cấu trúc giúp trả lời **“ở đâu có thể áp dụng?”**, điều kiện ngữ cảnh giúp trả lời **“trong lần thực thi nào thật sự áp dụng?”**. Một pointcut tốt phải diễn tả chính xác **giao hoặc hợp các tập điểm**, được kiểm thử với các trường hợp không khớp và vẫn tôn trọng phạm vi join point của nền tảng. Advice mới quyết định hành vi sau khi điểm được chọn.
