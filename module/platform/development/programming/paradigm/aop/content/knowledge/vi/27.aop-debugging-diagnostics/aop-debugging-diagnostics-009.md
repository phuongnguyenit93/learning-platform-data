# Tạo tình huống tái hiện tối thiểu cho lỗi tương tác aspect

## 1. Mục tiêu và vấn đề cần giải quyết

Khi nhiều aspect cùng tác động lên một join point, lỗi có thể chỉ xuất hiện **khi các aspect hoạt động đồng thời**, dù từng aspect chạy đúng khi đứng riêng. Ví dụ: một aspect ghi dấu vết bao quanh một aspect thử lại thao tác; kết quả nghiệp vụ thành công nhưng hệ thống vẫn ghi nhận lỗi, tạo hai bản ghi theo dõi hoặc thực hiện tác dụng phụ nhiều lần.

**Tình huống tái hiện tối thiểu** (minimal reproducible example, MRE) là chương trình nhỏ nhất vẫn tái hiện **đúng triệu chứng cần điều tra**, có bước chạy, đầu vào, điều kiện môi trường, kết quả thực tế và kết quả mong đợi rõ ràng. “Tối thiểu” không có nghĩa là xóa hết mọi chi tiết: phải giữ các điều kiện làm phát sinh tương tác aspect.

Sau bài này, bạn có thể:
- Xác định join point, pointcut, advice, thứ tự bao quanh và cơ chế áp dụng aspect liên quan trực tiếp đến lỗi.
- Rút một ca lỗi lớn thành ví dụ nhỏ, độc lập, có hành vi quan sát được và kết quả xác định.
- Tách tác động của từng aspect, thay đổi **một biến mỗi lần**, rồi chứng minh điều kiện cần để lỗi xảy ra.
- Phân biệt lỗi logic advice với sai lệch do proxy, weaving, pointcut, lớp tải động hoặc dữ liệu chia sẻ.
- Chuyển MRE thành kiểm thử hồi quy sau khi sửa.

**Phạm vi:** kiến thức AOP nói chung. Ví dụ chạy bằng JDK dynamic proxy để minh họa rõ chuỗi around-interceptor; những hệ AOP dùng compile-time weaving hoặc load-time weaving có cách bắt join point và cấu hình thứ tự riêng. Không mặc định một cơ chế đại diện cho mọi hệ AOP.

## 2. Bản đồ các thành phần gây tương tác

| Thành phần | Câu hỏi chẩn đoán | Triệu chứng thường gặp |
| --- | --- | --- |
| **Join point** | Chính xác lời gọi, thực thi, truy cập hay sự kiện nào được can thiệp? | Đặt log ở sai điểm; sự kiện bị ghi hai lần. |
| **Pointcut** | Hai mẫu chọn điểm cắt có giao nhau ngoài dự kiến không? | Advice chạy cả ở hàm phụ, logger hoặc hàm được gọi lồng nhau. |
| **Advice** | Before, after, after-returning, after-throwing hay around? | Nuốt/đổi ngoại lệ; thay giá trị trả về; bỏ qua thao tác đích. |
| **Thứ tự/precedence** | Aspect nào nằm ngoài, aspect nào nằm trong chuỗi gọi? | Một lần thử lại tạo hai trace; hành vi sau lỗi khác nhau. |
| **Proceed/continuation** | Advice around gọi tiếp mấy lần, trong nhánh nào? | Target chạy 0, 1 hoặc nhiều lần; lặp vô hạn; mất ngoại lệ gốc. |
| **State và vòng đời** | Dữ liệu lưu ở aspect instance, theo đối tượng, thread hay lời gọi? | Rò trạng thái giữa các yêu cầu; lỗi phụ thuộc thứ tự chạy test. |
| **Cơ chế áp dụng** | Proxy, compile-time weaving, load-time weaving hay mô hình khác? | Một lời gọi không được chặn; cùng mã nhưng khác hành vi khi chạy. |

Trong around advice, **lồng nhau khác với chạy lần lượt**:

~~~text
TRACE ngoài RETRY:                 RETRY ngoài TRACE:
TRACE.before                      RETRY.begin
  RETRY.begin                       TRACE.before
    target()                          target()
    retry nếu lỗi                   TRACE.error nếu lỗi
    target() lần nữa                RETRY.repeat
TRACE.after                          TRACE.before
                                       target() lần nữa
                                     TRACE.after
~~~

Đây là hai cấu trúc có thể quan sát khác nhau ngay cả khi kết quả trả về giống nhau. Quy tắc precedence thực tế phụ thuộc công cụ AOP; cần ghi cấu hình và bằng chứng, không suy luận từ thứ tự các tệp, tên class hay vị trí khai báo.

## 3. Quy trình thu nhỏ lỗi có thể kiểm chứng

### Bước 1 — Đóng băng triệu chứng và hợp đồng mong đợi

Viết một câu mô tả có thể đo được, chẳng hạn:

> Với **một lời gọi nghiệp vụ**, nếu lần đầu ném lỗi tạm thời rồi lần thử lại thành công, kết quả phải là “OK”, target thực thi đúng hai lần và trace cấp yêu cầu chỉ bắt đầu **một lần**, không phát sinh cảnh báo lỗi cuối cùng.

Ghi đồng thời **kết quả thực tế**, không chỉ mô tả “aspect lỗi”. Chọn ít nhất một tín hiệu cho mỗi loại: thứ tự sự kiện, số lần gọi target, giá trị trả về, ngoại lệ, tác dụng phụ và thời điểm xuất hiện. Phân biệt *một yêu cầu logic* với *một lần thực thi vật lý*.

### Bước 2 — Chụp điều kiện tái hiện

Ghi phiên bản JDK, hệ AOP/phiên bản và cách kích hoạt, đường biên đối tượng được chặn, cấu hình pointcut, precedence, loại weaving/proxy, các tùy chọn chạy và đầu vào. Với lỗi phụ thuộc chạy song song, ghi rõ số luồng, cách phối hợp, có hay không trạng thái tĩnh và vòng đời đối tượng. Không đưa dịch vụ ngoài, mạng hay thời gian thực vào MRE nếu chúng không phải điều kiện gây lỗi.

### Bước 3 — Giữ lại lát cắt nhỏ nhất

Bắt đầu với **một target**, **một phương thức**, **hai aspect thật sự va chạm** và **một ca gọi**. Tách phụ thuộc bên ngoài thành giả lập xác định, dùng sự kiện lưu trong bộ nhớ thay cho log phân tán. Xóa từng phần và chạy lại sau mỗi lần xóa; thành phần nào xóa khiến lỗi biến mất là manh mối quan trọng. Giữ lại các phần bắt buộc cho cơ chế interception, ví dụ interface nếu đang dùng JDK proxy.

### Bước 4 — Xây ma trận cô lập

Chạy theo cùng một đầu vào và điều kiện đặt lại trạng thái:

1. Không aspect: xác nhận target và phép thử lỗi tạm thời hoạt động theo thiết kế.
2. Chỉ aspect A: xác nhận hành vi riêng của A.
3. Chỉ aspect B: xác nhận hành vi riêng của B.
4. A ngoài B: ghi chuỗi sự kiện và kết quả.
5. B ngoài A (nếu cấu hình cho phép): chỉ đổi thứ tự, ghi lại cùng các quan sát.

Nếu lỗi chỉ xảy ra ở một tổ hợp, bạn đã thu hẹp được nguyên nhân. Nếu lỗi xuất hiện cả khi chỉ có A, xem lại chính A và giả định ban đầu. Nếu không tái hiện, kiểm tra sự khác nhau giữa bản tối thiểu và chương trình gốc: điểm cắt, kiểu join point, cơ chế áp dụng, lớp tải động, đối tượng bị chặn và vòng đời.

### Bước 5 — Biến mô tả thành bằng chứng

MRE phải có mã đầy đủ, lệnh chạy, stdout/ngoại lệ mong đợi, biểu đồ thứ tự hoặc danh sách sự kiện và tiêu chí PASS/FAIL. Chốt **một giả thuyết mỗi lượt**: ví dụ “đặt TRACE vào trong RETRY khiến TRACE quan sát hai attempt, nên ghi một lỗi tạm thời đã được khôi phục”.

## 4. MRE Java 17+: hai hành vi quanh một lời gọi

Tình huống giả định có hai aspect theo ngữ nghĩa: **TRACE** theo dõi một yêu cầu và **RETRY** thử lại một lần khi gặp IllegalStateException. Target thất bại xác định ở lần thực thi đầu tiên và thành công ở lần thứ hai. Chuỗi around được tạo bằng JDK dynamic proxy và danh sách interceptor để ta **kiểm soát chính xác thứ tự**, không phụ thuộc trình biên dịch AOP bên ngoài.

Lưu mã sau thành **AspectInteractionRepro.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class AspectInteractionRepro {
    private static final List<String> EVENTS = new ArrayList<>();

    public interface Service {
        String execute();
    }

    public static final class ServiceImpl implements Service {
        private int attempts = 0;

        @Override
        public String execute() {
            int n = ++attempts;
            EVENTS.add("target:" + n);
            if (n == 1) {
                throw new IllegalStateException("temporary");
            }
            return "OK";
        }
    }

    @FunctionalInterface
    interface Proceed {
        Object call() throws Throwable;
    }

    @FunctionalInterface
    interface Around {
        Object invoke(Proceed next) throws Throwable;
    }

    private static final Around TRACE = next -> {
        EVENTS.add("trace.before");
        try {
            Object result = next.call();
            EVENTS.add("trace.after");
            return result;
        } catch (Throwable failure) {
            EVENTS.add("trace.error");
            throw failure;
        }
    };

    private static final Around RETRY = next -> {
        EVENTS.add("retry.begin");
        try {
            return next.call();
        } catch (IllegalStateException transientFailure) {
            EVENTS.add("retry.repeat");
            return next.call();
        }
    };

    private static Object chain(List<Around> interceptors, int index, Proceed target)
            throws Throwable {
        if (index == interceptors.size()) {
            return target.call();
        }
        return interceptors.get(index)
                .invoke(() -> chain(interceptors, index + 1, target));
    }

    private static Service proxied(Service target, List<Around> interceptors) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] {Service.class},
                (proxy, method, args) -> chain(interceptors, 0, () -> {
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                })
        );
    }

    private static void scenario(String label, List<Around> interceptors) {
        EVENTS.clear();
        Service service = proxied(new ServiceImpl(), interceptors);
        String result = service.execute();

        System.out.println(label + " => " + result);
        System.out.println(String.join(" | ", EVENTS));
        long traceCount = EVENTS.stream()
                .filter("trace.before"::equals)
                .count();
        System.out.println("trace.before count=" + traceCount);
    }

    public static void main(String[] args) {
        scenario("TRACE then RETRY", List.of(TRACE, RETRY));
        scenario("RETRY then TRACE", List.of(RETRY, TRACE));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**, trong thư mục chứa tệp:

~~~bash
javac AspectInteractionRepro.java
java AspectInteractionRepro
~~~

Stdout đã được kiểm tra với JDK 21 (mã chỉ dùng tính năng có ở Java 17):

~~~text
TRACE then RETRY => OK
trace.before | retry.begin | target:1 | retry.repeat | target:2 | trace.after
trace.before count=1
RETRY then TRACE => OK
retry.begin | trace.before | target:1 | trace.error | retry.repeat | trace.before | target:2 | trace.after
trace.before count=2
~~~

**Giải thích theo từng tầng:**

- **ServiceImpl.execute()** tăng bộ đếm và phát lỗi ở attempt 1; attempt 2 trả “OK”. Mỗi scenario tạo ServiceImpl mới nên kết quả không phụ thuộc lần chạy trước.
- **Proceed** biểu diễn continuation: gọi nó sẽ đi tới interceptor tiếp theo hoặc target. Một advice around có thể gọi continuation nhiều lần; trong ví dụ, RETRY gọi lại đúng một lần khi nhận lỗi quy định.
- **TRACE** bao quanh toàn bộ continuation của nó. Nếu TRACE nằm ngoài RETRY, lỗi tạm thời được RETRY xử lý bên trong và TRACE chỉ thấy kết quả cuối cùng.
- Nếu **RETRY nằm ngoài TRACE**, mỗi attempt tạo một lượt đi qua TRACE. TRACE ghi trace.error cho attempt đầu dù yêu cầu cuối cùng thành công; trace.before xuất hiện hai lần.
- **Proxy.newProxyInstance** là một cách hiện thực interception qua interface, phù hợp để cô lập logic tương tác. Nó không tự thực hiện pointcut weaving lên mọi join point và không chứng minh những giới hạn của một hệ weaving khác.

Trong hợp đồng “TRACE đếm một lần cho mỗi yêu cầu logic”, tình huống thứ hai là **triệu chứng lỗi có thể tái hiện**: cùng kết quả “OK” nhưng thừa một trace và một bản ghi lỗi đã được phục hồi. Nếu yêu cầu thực tế là “một trace cho mỗi attempt”, tình huống thứ hai lại hợp lệ. Vì thế trước khi sửa cần xác nhận **ngữ nghĩa mong đợi**, không gọi mọi kết quả khác nhau là bug.

**Giới hạn chủ ý của ví dụ:** Đây là môi trường một luồng, interface proxy, exception đã định trước và thứ tự chain do mã đặt trực tiếp. Không kiểm tra recursion, gọi nội bộ trên cùng đối tượng, phương thức không qua proxy, weaving bytecode hay race condition; nếu đó là phần gây lỗi thật thì MRE kế tiếp phải giữ lại cơ chế tương ứng.

## 5. Đọc bằng chứng và khoanh vùng nguyên nhân

Đầu tiên đối chiếu **trạng thái kết thúc** và **đường đi**. Chỉ kiểm tra giá trị “OK” sẽ bỏ sót lỗi tương tác, bởi hai nhánh đều thành công. Đếm số lần target và advice chạy; ghi số lần continuation được gọi. Nếu hệ thống có metric hoặc thông báo lỗi, phân biệt lỗi attempt đã được phục hồi với lỗi cuối cùng của lời gọi logic.

Một bảng quan sát tối thiểu cho ví dụ:

| Biến thể | Giá trị trả về | Target thực thi | TRACE bắt đầu | TRACE ghi lỗi | Đạt hợp đồng trace/yêu cầu? |
| --- | --- | ---: | ---: | ---: | --- |
| TRACE ngoài RETRY | OK | 2 | 1 | 0 | Có |
| RETRY ngoài TRACE | OK | 2 | 2 | 1 | Không |

**Giả thuyết được chứng minh ở cấp MRE:** Thứ tự lồng around thay đổi phạm vi mà TRACE quan sát. TRACE ngoài RETRY thấy một yêu cầu đã phục hồi; TRACE trong RETRY nhìn từng attempt, bao gồm exception trung gian. Đây là lời giải thích cho kết quả thử nghiệm, **chưa tự động chứng minh** một ứng dụng thực tế dùng cùng precedence hay cùng cơ chế proxy.

Để đi từ MRE về ứng dụng, so sánh bằng chứng tại từng ranh giới: lời gọi đi qua proxy hay mã đã woven, điểm cắt thực sự khớp bao nhiêu lần, thứ tự before/around/after, số lần proceed, xử lý ngoại lệ trước/sau advice, và đối tượng/thread nào giữ state.

## 6. Mở rộng MRE theo nhóm lỗi tương tác

### 6.1. Hai pointcut chồng lên nhau

Triệu chứng: một phương thức nhận hai advice cùng nhiệm vụ; hoặc advice A ghi log bằng một phương thức cũng bị pointcut B chặn. Thu nhỏ bằng cách khai báo **một join point mong đợi** và **một join point không mong đợi**, rồi in mỗi lần match với tên phương thức và loại join point. Chứng minh lỗi mất đi khi siết điều kiện pointcut, không chỉ khi tắt cả aspect.

Không đánh đồng **call** (vị trí thực hiện lời gọi) với **execution** (thân phương thức bắt đầu chạy): các mô hình AOP hỗ trợ những kiểu join point khác nhau. Nếu hệ chỉ chặn thông qua proxy, một lời gọi không đi qua proxy có thể không được can thiệp; kết luận phải gắn với cơ chế cụ thể.

### 6.2. Around không chuyển tiếp, chuyển tiếp nhiều lần hoặc chuyển sai ngữ cảnh

Ghi sự kiện ở trước/sau mỗi lần gọi continuation và ở điểm vào target. Dùng counter xác định, không dựa vào thời gian chờ. Trường hợp “target không chạy” có thể do advice trả sớm; “target chạy hai lần” có thể là retry có chủ ý hoặc bug. Chỉ sửa sau khi đối chiếu hợp đồng nghiệp vụ và khả năng chạy lặp an toàn (*idempotency*).

Các lỗi dễ bỏ sót: gọi tiếp hai lần rồi trả kết quả lần đầu; bắt Throwable nhưng đổi thành lỗi khác; return ở nhánh cuối mà bỏ cleanup; advice gọi chính phương thức thuộc pointcut của nó gây tái nhập/reentrancy. Với recursion, đặt giới hạn sâu trong bản chẩn đoán và ghi dấu vết theo depth để tránh tràn stack.

### 6.3. Thứ tự và xử lý ngoại lệ

Tạo target ném chính xác một loại ngoại lệ. Đặt A ngoài B rồi B ngoài A, ghi **loại lỗi, thông điệp, cause và nơi bắt lỗi**. Phân biệt before/after-returning/after-throwing với around: một advice “sau khi ném lỗi” chỉ thấy lỗi thực sự đi qua ranh giới của nó; lỗi đã được advice bên trong xử lý có thể không xuất hiện ở tầng ngoài.

Nếu một aspect chuyển đổi exception và aspect khác quyết định retry theo type, thay thứ tự có thể thay kết quả nghiệp vụ, không riêng việc ghi log. MRE nên giữ đúng exception type và quy tắc chuyển đổi tối thiểu.

### 6.4. Trạng thái, thread và lifecycle

Kiểm tra ba trường hợp riêng: lời gọi tuần tự cùng instance, lời gọi tuần tự trên instance mới và nhiều lời gọi song song. Mỗi test reset state hoặc tạo đối tượng mới có chủ ý. Nếu chuyển sang song song mới lỗi, dùng công cụ đồng bộ có điểm chờ kiểm soát (ví dụ CountDownLatch), ghi thread và request id; không dựng race bằng sleep ngẫu nhiên rồi coi lúc PASS lúc FAIL là đủ bằng chứng.

Tránh suy diễn rằng context theo thread tự động được truyền qua mọi kiểu tác vụ bất đồng bộ. Nếu aspect dùng ThreadLocal hoặc dữ liệu per-request, MRE phải thể hiện **ranh giới chuyển thread** và quy tắc dọn dẹp.

### 6.5. Cơ chế chặn không khớp kỳ vọng

Phân biệt cụ thể:
- **Proxy interception:** một lời gọi phải đi qua đối tượng proxy để được áp dụng; kiểu proxy quyết định những phương thức nào được hỗ trợ. Gọi trực tiếp đối tượng gốc hoặc gọi nội bộ bỏ qua proxy có thể không kích hoạt advice.
- **Compile-time weaving:** mã được biến đổi khi biên dịch; cần giữ lệnh biên dịch, đường classpath và chứng cứ aspect đã được weave.
- **Load-time weaving:** mã được biến đổi khi class load; cần giữ cấu hình/agent tương ứng và thông tin classloader. Class đã được tải trước thời điểm áp dụng hoặc tải qua loader khác có thể cho kết quả khác, tùy công cụ.
- **Những hệ AOP khác:** xác nhận tập join point và cơ chế precedence thực tế từ chính công cụ đang dùng; không áp đặt quy tắc của một hệ lên hệ khác.

Nếu nghi ngờ vấn đề weaving hoặc classloader, ví dụ proxy ở mục 4 chỉ giúp kiểm chứng **logic thứ tự**, không thay thế được bài tái hiện chạy bằng engine thật. Giữ riêng hai MRE: một bản minh họa logic, một bản sát công nghệ để xác nhận nguyên nhân trong môi trường đích.

## 7. Chuẩn hóa phép thử hồi quy

Từ mã chạy bằng tay, viết assertion dựa trên **chuỗi sự kiện chính xác** và các thuộc tính của hợp đồng. Với tình huống ở mục 4, biến thể đáp ứng “một trace cho mỗi yêu cầu” có chuỗi sự kiện kỳ vọng:

~~~text
trace.before
retry.begin
target:1
retry.repeat
target:2
trace.after
~~~

Đừng chỉ assert kết quả trả về, vì cả hai thứ tự đều trả “OK”. Có thể thêm assertion: số sự kiện “target:” là 2, số “trace.before” là 1, không có “trace.error”, và toàn bộ chuỗi bằng danh sách kỳ vọng. Một khi sửa cấu hình hoặc mã aspect, chạy kiểm thử này cùng bản dùng cơ chế AOP thực tế để phát hiện thứ tự thay đổi trở lại.

Với ứng dụng nhiều thread, kiểm thử cần đồng bộ được các thời điểm thiết yếu, có timeout **để phát hiện treo**, ghi bất biến về số lượt xử lý và trạng thái cuối; một lần chạy ngẫu nhiên thành công chưa chứng minh không có race.

## 8. Hồ sơ MRE có thể chuyển giao

Một ca tái hiện tốt cho người khác phải tự đủ thông tin. Có thể dùng khung điền sau trong báo cáo lỗi thực tế (đây là khung báo cáo, không phải phần cần điền khi đọc bài):

| Trường | Nội dung cần ghi |
| --- | --- |
| **Tuyên bố lỗi** | Điều kiện đầu vào, kết quả mong đợi và một khác biệt quan sát được. |
| **Môi trường** | JDK, engine AOP + phiên bản, loại weaving/proxy, config cần thiết. |
| **Tệp tối thiểu** | Target, các aspect, mã kích hoạt và test/assertion. |
| **Cách chạy** | Lệnh build/chạy sao chép được; biến môi trường hay tham số bắt buộc. |
| **Kết quả mong đợi** | stdout, số lần target/advice, kiểu ngoại lệ/tác dụng phụ. |
| **Kết quả thực tế** | Chuỗi sự kiện đầy đủ, dấu hiệu lỗi; không bỏ attempt trung gian. |
| **Ma trận cô lập** | Không aspect; chỉ A; chỉ B; A+B; đổi thứ tự nếu có thể. |
| **Giới hạn tái hiện** | Cơ chế đã thay bằng mô phỏng, điều kiện đã loại bỏ, độ ổn định. |

Khi chia sẻ, loại bỏ thông tin nhạy cảm, phụ thuộc hạ tầng không cần thiết và dữ liệu ngẫu nhiên. Mỗi tệp/thiết lập còn lại phải có lý do rõ ràng: bỏ nó thì lỗi biến mất, môi trường không chạy, hoặc bằng chứng không còn phân biệt được các giả thuyết.

## 9. Sai lầm thường gặp và cách sửa

1. **Giữ cả ứng dụng lớn:** lỗi có thể do hàng chục thành phần; thu nhỏ từng phụ thuộc và chạy lại sau mỗi bước.
2. **Xóa đúng điều kiện gây lỗi:** loại bỏ một aspect, kiểu join point, state, precedence hay classloader khiến MRE hết lỗi nhưng cũng hết ý nghĩa. Ghi lý do cần giữ từng phần.
3. **Chỉ nhìn kết quả cuối:** hai chain cùng trả “OK”, song một chain sinh cảnh báo và trace thừa. Quan sát cả event trace, exception và số lần gọi.
4. **Cho rằng thứ tự khai báo là thứ tự chạy:** thứ tự thực tế phải được chứng minh bằng trace và cấu hình precedence của engine.
5. **Trộn retry với logic nghiệp vụ không idempotent:** chạy lại có thể tạo thanh toán, ghi dữ liệu hoặc gửi thông báo hai lần; chọn tác dụng phụ giả trong MRE để không gây hậu quả thực.
6. **Dùng sleep để giả lập race:** kết quả không ổn định và khó quy trách nhiệm; đồng bộ bằng tín hiệu có kiểm soát.
7. **Thử qua proxy rồi kết luận về weaving:** hai cơ chế có tập join point khác nhau. Đưa điều kiện công nghệ gốc trở lại trước khi chốt nguyên nhân.
8. **Không reset state giữa các ca:** bộ đếm, cache, static field hoặc context còn sót làm sai ma trận so sánh.
9. **Không có tiêu chí fail rõ:** một MRE hữu ích phải phân biệt được chạy đúng/sai chỉ từ lệnh và output/assertion.
10. **Sửa và đo nhiều biến cùng lúc:** chỉ thay một điều kiện (thứ tự, pointcut, quy tắc ngoại lệ, state), ghi kết quả rồi mới thử biến tiếp theo.

## 10. Checklist hoàn tất bài tái hiện

- [ ] Một câu mô tả triệu chứng, hợp đồng mong đợi và tín hiệu sai có thể kiểm tra.
- [ ] Đủ target, các aspect đang tương tác, join point và cơ chế áp dụng để lỗi vẫn tái hiện.
- [ ] Tất cả đầu vào và trạng thái khởi đầu xác định; lệnh chạy và phiên bản phụ thuộc được ghi.
- [ ] Có baseline, từng aspect riêng, hai aspect cùng chạy và phép đổi thứ tự khi phù hợp.
- [ ] Thu được chuỗi sự kiện, số lần proceed/target và ngoại lệ hoặc giá trị trả về tương ứng.
- [ ] Chỉ ra rõ thành phần tối thiểu khiến kết quả đổi, không suy diễn vượt cơ chế đã thử.
- [ ] Có assertion hồi quy về **hành vi cần bảo vệ**, bao gồm tác dụng phụ quan trọng.

**Kết luận kỹ thuật:** MRE hiệu quả giữ nguyên *quan hệ tương tác* giữa aspect nhưng loại bỏ biến số không cần thiết. Trong ví dụ, bằng chứng không nằm ở kết quả “OK” mà ở phạm vi trace quan sát từng attempt hay cả yêu cầu logic. Khi gắn lại engine AOP và loại join point thật, chuỗi sự kiện xác định giúp tìm đúng pointcut, precedence hoặc advice cần sửa và bảo vệ bản sửa bằng kiểm thử hồi quy.
