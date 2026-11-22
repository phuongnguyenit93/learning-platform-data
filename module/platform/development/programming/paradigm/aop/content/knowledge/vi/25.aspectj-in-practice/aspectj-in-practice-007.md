# Khai báo ưu tiên, Aspect trừu tượng và mô hình tạo Aspect trong AspectJ

## 1. Vì sao ba khái niệm này phải được học cùng nhau?

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), một chương trình có thể áp dụng nhiều **aspect** lên cùng một **join point**. Chẳng hạn, một operation đồng thời phải được kiểm tra quyền, ghi log, đo thời gian và quản lý giao dịch. Khi ấy, ba câu hỏi kiến trúc xuất hiện:

1. **Aspect nào chạy trước, aspect nào chạy sau?** Đây là vấn đề **advice precedence**, có thể điều khiển bằng khai báo ưu tiên.
2. **Làm sao tái sử dụng phần cơ chế chung mà vẫn cho từng module xác định điểm cắt?** Đây là vai trò của **abstract aspect**, kế thừa aspect và abstract pointcut.
3. **Có bao nhiêu đối tượng aspect tồn tại, chúng gắn với đâu và giữ trạng thái bao lâu?** Đây là vấn đề **aspect instantiation model**.

Ba vấn đề có liên quan chặt chẽ: thứ tự quyết định phạm vi quan sát/kiểm soát, kế thừa quyết định cách chia sẻ chính sách, còn mô hình tạo aspect quyết định ai sở hữu state của advice. Nếu thiết kế sai, cùng một chương trình có thể ghi log trùng, bỏ qua kiểm tra quyền, giữ dữ liệu người gọi trong singleton hoặc coi tác vụ bất đồng bộ đã kết thúc ngay sau khi phương thức trả về.

Bài này minh họa bằng **cú pháp AspectJ độc lập** cùng những nguyên tắc AOP áp dụng rộng hơn. AspectJ là ngôn ngữ và công cụ weaving có cú pháp riêng; các đoạn mã dùng từ khóa aspect, pointcut, before, around, declare và per-clause cần được biên dịch bằng **ajc**, không thể biên dịch trực tiếp bằng javac thuần.

## 2. Ôn nhanh: join point, pointcut, advice, aspect

- **Join point:** vị trí có thể can thiệp vào hoạt động chương trình, chẳng hạn method call, method execution hoặc constructor execution; loại join point tùy cơ chế AOP.
- **Pointcut:** biểu thức chọn các join point, ví dụ chọn execution của một method nghiệp vụ.
- **Advice:** hành vi được chạy trước, sau, khi có lỗi hoặc thay thế/bọc join point. Với around advice, proceed() là cách tiếp tục tới advice có ưu tiên thấp hơn hoặc phép tính gốc.
- **Aspect:** đơn vị đóng gói pointcut, advice, field và method liên quan đến concern.
- **Weaving:** quá trình liên kết logic aspect vào chương trình. Cấu hình biên dịch hoặc nạp lớp quyết định các join point thực tế được áp dụng.
- **Concrete aspect:** aspect có thể được hệ thống AspectJ tạo instance và chạy advice.
- **Abstract aspect:** aspect dùng làm nền tảng kế thừa; có thể chứa pointcut trừu tượng và advice dùng chung, nhưng không tự trực tiếp tạo một instance nghiệp vụ theo kiểu concrete aspect.
- **Per-clause:** phần khai báo kiểu gắn các instance của aspect với singleton, object, dynamic control flow hoặc type.

Một lời gọi có nhiều advice không phải mặc nhiên một danh sách callback tuần tự. Advice có thể bao quanh nhau như các lớp lồng nhau; khi một tầng kết thúc, các lệnh sau proceed() hoặc after advice chạy trong quá trình quay ra ngoài.

## 3. Khai báo ưu tiên là gì?

**Precedence** xác định thứ bậc giữa các advice cùng áp dụng tại **một join point**. Trong AspectJ, cú pháp tổng quát là:

~~~aspectj
declare precedence: FirstAspect, SecondAspect, ThirdAspect;
~~~

Danh sách sắp xếp **từ ưu tiên cao sang ưu tiên thấp**. Nếu advice của FirstAspect và SecondAspect cùng khớp một join point, advice ở FirstAspect có ưu tiên cao hơn.

Có thể đặt khai báo trong một aspect chuyên điều phối thứ tự:

~~~aspectj
public aspect AdviceOrdering {
    declare precedence: AuthenticationAspect,
                        AuthorizationAspect,
                        TransactionAspect,
                        ObservationAspect;
}
~~~

Đây là **đoạn cú pháp minh họa**, các aspect trong danh sách chưa được định nghĩa ở đây nên không phải chương trình độc lập. Trong thiết kế thực tế, thứ tự cần dựa trên contract của từng concern, không được suy luận rằng danh sách này đúng cho mọi hệ thống.

Các điểm cần nhớ:

- Precedence chỉ có ý nghĩa khi nhiều advice **cùng khớp join point**. Nó không buộc những join point không liên quan phải chạy theo một thứ tự toàn cục.
- Thứ tự khai báo có thể ảnh hưởng đến việc một advice quan sát được kết quả, exception hoặc side effect do advice khác tạo ra.
- Nếu không có quan hệ precedence và không có quan hệ kế thừa xác định thứ tự giữa hai aspect khác nhau, **không nên dựa vào một thứ tự ngẫu nhiên**.
- Một khai báo không thay thế việc chọn pointcut phù hợp; aspect không khớp vẫn không chạy.
- Khi các yêu cầu thứ tự mâu thuẫn, trình biên dịch có thể báo lỗi về precedence/circularity. Không cố xử lý bằng cách đoán thứ tự của bản build hiện tại.

## 4. Before, after và around dưới tác động của precedence

Giả sử có Aspect A ưu tiên cao hơn Aspect B, cùng bao quanh một method:

~~~text
A quanh B quanh method:
A: trước proceed
    B: trước proceed
        METHOD chạy
    B: sau proceed
A: sau proceed
~~~

Với hai around advice đều gọi proceed() đúng một lần, A là vòng **ngoài** và B là vòng **trong**. Vì vậy:

- Phần trước proceed() của A chạy trước B.
- Phần sau proceed() của B chạy trước phần sau proceed() của A.
- Nếu A không gọi proceed(), B và method gốc có thể không chạy.
- Nếu B ném exception, A có thể thấy exception nếu đường điều khiển đi qua A.
- Với before advice, advice có ưu tiên cao hơn thường chạy trước các before advice thấp hơn cùng join point.
- Với after advice, logic thường chạy khi luồng điều khiển quay ra, vì vậy **không được suy luận đơn giản “ưu tiên cao sẽ in trước trong mọi loại advice”**.

Xét ví dụ:

~~~aspectj
aspect Outer {
    void around(): execution(void Work.run()) {
        System.out.println("OUTER enter");
        proceed();
        System.out.println("OUTER leave");
    }
}

aspect Inner {
    void around(): execution(void Work.run()) {
        System.out.println("INNER enter");
        proceed();
        System.out.println("INNER leave");
    }
}

aspect Ordering {
    declare precedence: Outer, Inner;
}
~~~

Nếu lớp Work có method run() in WORK và chỉ một invocation được thực thi, thứ tự là OUTER enter, INNER enter, WORK, INNER leave, OUTER leave. Đoạn trên minh họa **các aspect**, chưa cung cấp lớp Work nên không phải project độc lập; project chạy đầy đủ nằm ở phần ví dụ sau.

**Với advice bao quanh có thể ném lỗi**, hãy dùng try/finally nếu logic kết thúc/cleanup phải chạy cả khi proceed() ném exception. Chỉ đặt System.out.println sau proceed() sẽ không bảo đảm nó được gọi trong đường lỗi.

## 5. Cú pháp declare precedence và type pattern

AspectJ cho phép danh sách **type pattern**, không chỉ tên aspect đơn lẻ:

~~~aspectj
aspect PolicyOrder {
    declare precedence: *..*Security*, *..*Audit*, *;
}
~~~

Trong ngữ cảnh cú pháp này:

- Pattern đầu chọn các aspect phù hợp mẫu tên có chứa Security theo quy tắc type pattern.
- Pattern kế tiếp chọn nhóm Audit.
- Dấu * cuối biểu diễn các kiểu không được khớp bởi pattern trước trong danh sách, giúp có quy tắc cho phần còn lại.
- Trong danh sách declare precedence, wildcard đại diện phần còn lại này được dùng tối đa một lần.
- Dấu + sau tên kiểu có thể diễn đạt một type pattern gồm kiểu và các kiểu con, hữu ích khi khai báo thứ tự cho **các concrete subaspect** kế thừa abstract aspect.

Ví dụ:

~~~aspectj
aspect FamilyOrdering {
    declare precedence: SecurityPolicy+, AuditTemplate+, *;
}
~~~

Đây là snippet minh họa về type pattern; để biên dịch cần các type tương ứng. Với abstract parent và concrete child, một khai báo chỉ trỏ vào **abstract aspect cha** mà không bao gồm các concrete child có thể không tạo hiệu lực như mong muốn. Đọc chính xác type patterns và kiểm tra concrete aspects được match.

Đừng dùng pattern quá rộng chỉ vì dễ cấu hình. Một khai báo ảnh hưởng tới mọi aspect trong nhiều module có thể làm thay đổi phạm vi transaction, audit và retry ngoài dự kiến.

## 6. Thứ tự khi không khai báo rõ

Các quy tắc cơ bản của AspectJ:

1. **Giữa hai aspect khác nhau:** nếu có declare precedence, dùng thứ tự đã công bố.
2. **Quan hệ kế thừa:** một concrete subaspect có precedence cao hơn superaspect theo quy tắc kế thừa, trừ khi thứ tự được thiết lập khác bằng khai báo phù hợp.
3. **Hai aspect độc lập, không có precedence:** thứ tự giữa các advice của chúng không được xác định đáng tin để xây business logic.
4. **Nhiều advice trong cùng một aspect:** quy tắc thứ tự nội bộ khác với thứ tự giữa các aspect; với trường hợp có after advice, định nghĩa thứ tự có điều kiện theo vị trí khai báo.
5. **Chồng lấn nhiều quy tắc:** phải tránh quan hệ tạo chu trình hoặc mâu thuẫn dẫn đến lỗi biên dịch.

Một hệ thống phụ thuộc vào “lần chạy thử này LoggingAspect luôn thấy exception trước TransactionAspect” nhưng không có contract thứ tự tương ứng là hệ thống khó bảo trì.

## 7. Chọn precedence theo ý nghĩa nghiệp vụ

Xem ba concern:

- **Authorization:** có thể từ chối trước side effect.
- **Transaction:** quản lý điểm bắt đầu, commit/rollback.
- **Observability:** cần đo một operation ngay cả khi bị từ chối.

Hai lựa chọn có thể có:

~~~text
Observation -> Authorization -> Transaction -> Business
~~~

Nếu Observation nằm ngoài Authorization, nó có thể ghi kết quả DENY và duration của cả operation. Nếu chỉ muốn đo riêng phần nghiệp vụ đã được phép, điểm quan sát có thể nằm trong Authorization; khi đó denial có thể không được đo ở cùng timer.

Không có một thứ tự tốt nhất cho mọi ứng dụng. Hãy viết rõ bảng kỳ vọng:

| Tình huống | Thứ tự cần quan tâm | Câu hỏi cần trả lời |
| --- | --- | --- |
| Caller thiếu quyền | Authorization so với transaction | Có phát sinh side effect/transaction không? |
| Một attempt lỗi rồi retry | Retry so với timer | Timer đo toàn operation hay từng attempt? |
| Method ném lỗi | Audit/log so với transaction | Log ghi lỗi trước hay sau rollback? |
| Task trả CompletionStage | Advice so với completion | Method return hay task done là mốc kết thúc? |
| Operation kết thúc bị deny | Observability so với authorization | Denial có thuộc số operation được thống kê? |

Thứ tự advice là một phần của **hợp đồng quan sát và điều khiển**. Không nên thay một dòng precedence mà không kiểm thử lại behavior.

## 8. Abstract Aspect: mẫu chung và điểm cắt tùy biến

Khi nhiều module cần cùng cơ chế logging hoặc auditing nhưng có **tập join point khác nhau**, abstract aspect cho phép định nghĩa một template:

~~~aspectj
public abstract aspect OperationTemplate {
    protected abstract pointcut selectedOperation();

    before(): selectedOperation() {
        System.out.println("COMMON before");
    }
}
~~~

Ở đây:

- **abstract aspect** cho phép chứa **abstract pointcut** chưa có biểu thức.
- Advice trước join point dùng pointcut trừu tượng, nên chính sách log có thể được viết một lần.
- Một concrete subaspect phải triển khai pointcut để quyết định những join point được áp dụng.
- Abstract aspect không tự được dùng như một concrete aspect phát advice độc lập.
- Nên đặt tên pointcut theo **ý nghĩa** như businessOperation, protectedOperation hoặc dependencyCall; tránh tên helper mơ hồ.

Một concrete aspect:

~~~aspectj
public aspect OrderTemplate extends OperationTemplate {
    protected pointcut selectedOperation():
        execution(void OrderService.submit());
}
~~~

Những đoạn trên là **phần của một project có lớp OrderService**, được hoàn thiện ở ví dụ runnable. Ý nghĩa là concrete aspect chọn một operation còn parent sở hữu hành vi chung.

## 9. Hạn chế kế thừa của AspectJ cần nhớ

Khả năng kế thừa aspect giống mô hình hướng đối tượng nhưng có quy tắc riêng:

- Một **aspect có thể extends một class** phù hợp hoặc **implements interface**; điều đó không biến aspect thành đối tượng phải tạo bằng new.
- Một **aspect chỉ được extends aspect trừu tượng**; không định nghĩa một concrete aspect extends một concrete aspect khác.
- **Class thông thường không được extends một aspect.**
- **Abstract pointcut chỉ có thể được khai báo trong abstract aspect**; concrete child có thể định nghĩa pointcut đó.
- Pointcut có quy tắc thành viên và kế thừa; không thể overload hai pointcut chỉ bằng cách đổi danh sách tham số dưới cùng một tên theo cách method Java thông thường.
- Concrete subaspect có thể kế thừa field, method, pointcut và advice của abstract parent.
- Cơ chế tạo instance của concrete aspect **kế thừa từ parent aspect** khi có parent. Cần kiểm tra quan hệ giữa per-clause của parent và class con thay vì xem mỗi child là một cấu hình vòng đời độc lập.
- Advice được áp dụng theo concrete aspect thực sự được tạo; vì vậy khai báo precedence phải suy xét **concrete aspects** chứ không chỉ dựa vào tên abstract template.

Không tạo aspect instance bằng **new SomeAspect()**. Với những model hỗ trợ truy cập instance, AspectJ cung cấp những hình thức **aspectOf(...)** và **hasAspect(...)** tương ứng; cách dùng phụ thuộc loại per-clause.

## 10. Ví dụ hoàn chỉnh: ưu tiên + abstract aspect + advice lồng nhau

Đây là project AspectJ nhỏ gồm một lớp Java và bốn tệp .aj. Mục tiêu là thấy rõ:

1. Abstract aspect định nghĩa lời khuyên chung.
2. Concrete aspect chọn một method thực sự.
3. Trace aspect cùng chặn join point đó.
4. declare precedence đặt Trace ở vòng ngoài.
5. Mã nghiệp vụ không cần biết hai aspect đang tồn tại.

**Tệp Demo.java**

~~~java
public class Demo {
    public static void main(String[] args) {
        new OrderService().submit();
    }
}

class OrderService {
    void submit() {
        System.out.println("BUSINESS submit");
    }
}
~~~

**Tệp OperationTemplate.aj**

~~~aspectj
public abstract aspect OperationTemplate {
    protected abstract pointcut operation();

    before(): operation() {
        System.out.println("AUDIT before");
    }
}
~~~

**Tệp OrderAudit.aj**

~~~aspectj
public aspect OrderAudit extends OperationTemplate {
    protected pointcut operation():
        execution(void OrderService.submit());
}
~~~

**Tệp TraceAspect.aj**

~~~aspectj
public aspect TraceAspect {
    void around(): execution(void OrderService.submit()) {
        System.out.println("TRACE enter");
        try {
            proceed();
        } finally {
            System.out.println("TRACE leave");
        }
    }
}
~~~

**Tệp Ordering.aj**

~~~aspectj
public aspect Ordering {
    declare precedence: TraceAspect, OrderAudit;
}
~~~

### Biên dịch và chạy

Yêu cầu JDK 17, phiên bản AspectJ/ajc hỗ trợ Java 17, trình biên dịch ajc nằm trong PATH và thư viện runtime **aspectjrt.jar** tương thích. Đặt biến môi trường ASPECTJRT trỏ tới tệp aspectjrt.jar thực tế trên máy; đường dẫn đó không được đoán.

Lệnh biên dịch chung:

~~~bash
ajc -17 -classpath "$ASPECTJRT" -d out Demo.java OperationTemplate.aj OrderAudit.aj TraceAspect.aj Ordering.aj
~~~

Dòng trên dùng cách nội suy biến của shell kiểu Unix. Với PowerShell, dùng lệnh tương đương:

~~~powershell
ajc -17 -classpath "$env:ASPECTJRT" -d out Demo.java OperationTemplate.aj OrderAudit.aj TraceAspect.aj Ordering.aj
java -cp "out;$env:ASPECTJRT" Demo
~~~

Với bash hoặc shell có dấu hai chấm phân tách classpath:

~~~bash
java -cp "out:$ASPECTJRT" Demo
~~~

Không chạy javac cho các tệp .aj vì chúng chứa cú pháp AspectJ. ajc phải nhận **cả mã Java lẫn các tệp aspect** để thực hiện biên dịch và weaving cho join point được chọn.

**Stdout của lần chạy này**:

~~~text
TRACE enter
AUDIT before
BUSINESS submit
TRACE leave
~~~

### Giải thích thứ tự chính xác

- Method execution của OrderService.submit khớp cả pointcut operation của OrderAudit lẫn around advice của TraceAspect.
- TraceAspect có precedence cao hơn OrderAudit nên around advice của TraceAspect bắt đầu trước.
- Lời gọi proceed() của TraceAspect cho phép những advice có precedence thấp hơn tiếp tục; advice before kế thừa từ OperationTemplate qua OrderAudit chạy và in AUDIT before.
- Method gốc chạy và in BUSINESS submit.
- Luồng quay lại around advice; finally in TRACE leave dù method gốc ném exception.
- OperationTemplate là abstract template; **không có một lượt AUDIT thứ hai** do parent tự tồn tại như một concrete aspect tách biệt.
- Ordering không có advice nhưng vẫn có ý nghĩa: khai báo thứ tự tại join point.

Khi đổi declare precedence thành OrderAudit, TraceAspect, điều có thể quan sát là **AUDIT before chạy trước TRACE enter**. Nếu chính sách yêu cầu audit mọi lần thử trước khi cho phép trace/body chạy, vị trí này có ý nghĩa. Với những advice after/around khác, cần xem cả đường unwind, không chỉ so dòng log đầu.

**Giới hạn của demo:** không mô phỏng dependency ngoài, transaction hay nhiều thread. Số dòng là cố định vì chỉ một method và hai advice khớp, không có ngoại lệ. Khi mở rộng, cần tránh pointcut bắt chính phương thức trong aspect, gây đo trùng hoặc recursion.

## 11. Aspect instance: điểm khác biệt lớn so với object thông thường

Một **aspect instance** là đối tượng giữ field và thực thi advice. AspectJ có quy tắc tạo nó riêng; lập trình viên không tự gọi new như đối với service thông thường.

Vấn đề thiết kế quan trọng nhất là:

> State trong aspect có phạm vi **cùng với mô hình instantiation**, không tự động có phạm vi theo request, thread hoặc transaction mà ta mong muốn.

Ví dụ một counter trong singleton aspect sẽ được chia sẻ bởi nhiều lời gọi và nhiều thread trong phạm vi classloader tương ứng. Một counter trong pertarget aspect có thể gắn với từng target object. Một counter trong percflow aspect có thể gắn với một dynamic control flow.

Chọn sai phạm vi gây hai nhóm lỗi trái ngược:

- **Quá rộng:** dữ liệu người dùng/request bị chia sẻ nhầm, race condition, rò state.
- **Quá hẹp hoặc sai vòng đời:** mất dữ liệu cần chia sẻ, tạo quá nhiều đối tượng, metric bị phân mảnh hoặc context biến mất khi task chuyển thread.

## 12. Bản đồ mô hình tạo Aspect và phạm vi trạng thái

**Precedence trả lời advice nào bọc advice nào; instantiation trả lời instance nào sở hữu state.** Đây là hai quyết định khác nhau. Sau khi xác định thứ tự và thiết kế một abstract template, cần chọn phạm vi instance dựa trên ai sở hữu dữ liệu:

| Mô hình AspectJ | Instance thuộc về | Rủi ro cần nhớ |
| --- | --- | --- |
| `issingleton()` (mặc định) | Một instance aspect trong phạm vi bản aspect được nạp | Field mutable có thể bị nhiều thread cùng truy cập |
| `perthis(P)` | Mỗi object là `this` tại join point kích hoạt `P` | `this` ở method call không nhất thiết là receiver |
| `pertarget(P)` | Mỗi object là `target` tại join point kích hoạt `P` | Một target có thể phục vụ rất nhiều request |
| `percflow(P)` | Mỗi lần đi vào dynamic control flow từ `P` | Không tự truyền ngữ cảnh sang executor/thread khác |
| `percflowbelow(P)` | Phần flow nằm dưới join point kích hoạt `P` | Không áp dụng chính điểm mở flow theo ngữ nghĩa below |
| `pertypewithin(TypePattern)` | Một instance cho mỗi type phù hợp | Không phải mỗi object hoặc mỗi request |

Các per-clause trên là **cú pháp và mô hình của AspectJ**, không phải năng lực mặc định của mọi hệ AOP. `pertypewithin` nhận type pattern, các mô hình `perthis`/`pertarget`/`percflow` nhận pointcut expression. Điều kiện tạo instance có thể khác với pointcut của advice chạy sau đó.

## 13. Singleton: giữ state chung khi thực sự cần

Với singleton aspect không trạng thái, advice thường đơn giản và dễ dự đoán. Nhưng một field `currentUser`, `lastRequest` hoặc `startTime` trên singleton sẽ bị chia sẻ giữa nhiều invocation, có thể gây race và lộ ngữ cảnh. Singleton ở đây **không đồng nghĩa** một object duy nhất trên toàn bộ nhiều class loader hoặc tiến trình.

Nếu cần trạng thái riêng cho mỗi lời gọi, sử dụng dữ liệu cục bộ của advice hoặc context có lifecycle xác định; không đổi sang `perthis` chỉ vì muốn có per-request isolation.

## 14. `perthis` và `pertarget`: phân biệt đối tượng sở hữu

Ở **call join point**, `this` thường thuộc bên phát lời gọi và `target` là receiver; ở **execution join point** của instance method, hai vai trò thường cùng chỉ đối tượng đang chạy phương thức. Do đó per-object scope phụ thuộc cả **P chọn loại join point nào**.

Ví dụ rút gọn về target được gọi:

~~~java
// Chỉ định nghĩa type minh họa; chương trình chạy đầy đủ
// cho per-object lifecycle được trình bày ở bài chuyên sâu.
class Account {
    void charge() {}
}
~~~

~~~aspectj
// Snippet ý niệm độc lập: chọn một target Account cho mỗi instance.
aspect PerAccountObserver
        pertarget(execution(void Account.charge())) {
    private int hits = 0;
    before(): execution(void Account.charge()) { hits++; }
}
~~~

Hai lần gọi trên **cùng Account** sẽ dùng cùng pertarget instance sau khi pointcut kích hoạt; object Account khác có instance khác. `hits++` không tự trở thành thread-safe nếu nhiều thread dùng cùng Account. Đoạn mã chỉ minh họa mối quan hệ giữa P, target và state, không phải chương trình Java thuần chạy bằng `javac`.

## 15. `percflow` và `percflowbelow`: state theo call stack động

`percflow(P)` gắn một aspect instance với **mỗi lần bắt đầu dynamic flow** từ điểm khớp P. Với `percflowbelow(P)`, tác dụng nhắm phần ở dưới điểm mở flow. Đệ quy hoặc các flow lồng nhau có thể tạo nhiều scope; cần kiểm thử trước khi sử dụng để đếm attempt hoặc giữ trạng thái tác vụ.

Một `submit()` trả về Future **không bảo đảm** worker chạy ở thread khác còn nằm trong flow của caller. Phải truyền context theo ranh giới task nếu chính sách yêu cầu, thay vì giả định `percflow` là một context propagation API.

## 16. `pertypewithin`: scope theo type

Mẫu `pertypewithin(com.example.domain..*)` gắn aspect instance theo **mỗi type phù hợp**, không theo từng object. Nó hữu ích với thống kê/metadata per-class nhưng không thích hợp để lưu `currentUser` hoặc đếm riêng từng instance. Cần xét class loader và kiểu nào thực sự nằm trong vùng weaving trước khi diễn giải số lượng instance.

## 17. Accessor và thời điểm instance được gắn

Các dạng `aspectOf()`/`hasAspect()` phụ thuộc per-clause: singleton hoặc flow thường dùng accessor không tham số; per-object có dạng lấy object; per-type dùng `Class`. Không mặc định gọi `aspectOf` là hành động tạo aspect instance. Với per-object, instance có thể chưa được gắn nếu chưa có join point kích hoạt; với flow, accessor ngoài scope có thể không có instance phù hợp.

Giữ API cụ thể và kiểm thử theo **version AspectJ** đang dùng; không dùng truy cập instance từ ngoài thay thế một hợp đồng lifecycle rõ ràng.

## 18. Chọn mô hình từ quyền sở hữu state, không từ tên gọi

Trả lời tuần tự: **(1)** có thực sự cần state? **(2)** State gắn với caller, target, type hay một flow đồng bộ? **(3)** Có thread khác, recursion hoặc retry không? **(4)** Khi nào reset/cleanup và số instance tăng ra sao? **(5)** Advice chạy ở đâu so với điểm kích hoạt per-clause?

Ví dụ, một policy quan sát không state thường dùng singleton; counter theo target có thể dùng `pertarget`; một scope chẩn đoán chỉ tồn tại trên call stack đồng bộ có thể dùng `percflow`. Một logical request qua queue/thread pool nên dùng task context có propagation/lifetime minh bạch, không coi per-clause của AspectJ là per-request tự động.

**Ranh giới chương:** bảng trên đủ để hiểu vì sao precedence và abstract aspect có thể kết hợp với nhiều kiểu instance; phần vòng đời chuyên sâu cần đo bằng phép thử hai object, nhiều flow lồng nhau, lỗi và concurrent calls, chứ không suy từ tên mô hình.

## 19. Abstract Aspect và per-clause inheritance

Một abstract aspect có thể xác định cả policy mẫu lẫn mô hình instantiation; concrete child tiếp nhận quy tắc tạo instance theo kế thừa aspect.

Hình dung:

~~~aspectj
abstract aspect PerTargetTemplate
        pertarget(execution(void Account.charge())) {
    protected int visits = 0;

    protected abstract pointcut observedOperation();

    before(): observedOperation() {
        visits++;
    }
}

aspect AccountMonitor extends PerTargetTemplate {
    protected pointcut observedOperation():
        execution(void Account.charge());
}
~~~

Đây là snippet riêng minh họa inheritance và per-clause, không yêu cầu ghép cùng ví dụ có PerTargetCounter đã định nghĩa. Parent xác định mô hình pertarget và giữ cơ chế; child định nghĩa join point dùng advice.

Một số điều phải kiểm tra:

- Không mở rộng concrete aspect để “thừa kế” advice: parent aspect cần trừu tượng.
- Kiểu instantiation được định nghĩa/kế thừa qua quan hệ aspect; không coi child có thể tự chọn mô hình mâu thuẫn với parent mà không kiểm tra quy tắc ngôn ngữ.
- Nếu nhiều concrete children có cùng pointcut, chúng có thể tạo nhiều advice application độc lập dù dùng chung template. Tái sử dụng code **không tự deduplicate instrumentation**.
- Khi khai báo precedence giữa các gia đình aspect, chú ý concrete children và type patterns.
- Field visits thuộc instance của **concrete child**, với scope xác định bởi pertarget; không xem nó là bộ đếm toàn cục của abstract template.

## 20. Composition: ba trục độc lập nhưng tương tác

Hãy nhớ ba trục:

~~~text
Trục 1: WHERE  = pointcut / selected join points
Trục 2: ORDER  = advice precedence / nesting
Trục 3: SCOPE  = aspect instantiation / state ownership
~~~

Một aspect có pointcut đúng nhưng precedence sai có thể ghi nhận sai outcome. Một aspect có precedence đúng nhưng scope sai có thể rò state. Một aspect có scope và order đúng nhưng pointcut quá rộng có thể gây overhead hoặc chặn helper ngoài ý muốn.

Ví dụ một metric aspect singleton có thể thread-safe và chạy đúng ở operation boundary. Nếu pointcut chồng lấn với một metric aspect khác, counter vẫn bị đếm đôi. Đổi sang pertarget không giải quyết duplicate semantics; cần xác định một chủ sở hữu signal.

Ngược lại, pertarget giúp state tách theo object nhưng không tách theo request nếu một object được tái sử dụng cho hàng nghìn request. Đặt currentUser trong field pertarget của singleton service vẫn có thể làm rò identity.

## 21. Priority và error semantics

Một before advice có thể ném exception để chặn những advice có precedence thấp hơn và target execution. Một around advice có thể không gọi proceed(). Điều này hợp lý với authorization deny hoặc circuit breaker được thiết kế, nhưng phải ghi rõ contract:

- Aspect nào được phép chặn?
- Audit/log nên ghi cả denied attempts hay chỉ operation thật sự thực thi?
- Transaction có bắt đầu trước khi authorization có thể từ chối không?
- Timeout/retry có xảy ra ở ngoài hay trong transaction?
- Nếu advice cao hơn ném lỗi, advice thấp hơn có còn cơ hội quan sát không?
- Có cleanup trong finally ở advice ngoài khi một advice trong lỗi không?

Các quyết định này phải được kiểm thử với method success, failure, denied, timeout và retry. Không nên xử lý bằng cách đổi thứ tự type pattern cho đến khi stdout “trông đúng” mà thiếu hợp đồng rõ.

## 22. Priority với retry, transaction và đo thời gian

Hai thứ tự điển hình:

~~~text
OperationTimer -> RetryAspect -> AttemptTimer -> Business
~~~

Khi OperationTimer bao ngoài retry, nó đo toàn bộ operation và mọi lần thử (cùng thời gian chờ nếu retry có backoff). AttemptTimer bên trong được kích hoạt mỗi attempt. Đây không phải trùng nếu metric đặt tên **operation.duration** và **attempt.duration** khác nhau.

Nếu thứ tự đổi, duration có thể mất thời gian queue/backoff hoặc tạo nhiều mẫu không còn biểu diễn cùng đơn vị. Precedence là một cấu phần của contract metric, không chỉ chi phối thứ tự dòng log.

Tương tự, transaction quanh toàn bộ retry và transaction per-attempt có mức atomicity khác nhau. Việc “transaction ngoài retry” có thể giữ lock hoặc context lâu hơn; “transaction trong retry” có thể yêu cầu idempotency và rollback đúng mỗi attempt. Không mặc định đảo precedence vô hại.

Một concrete abstract-template subclass có advice kế thừa vẫn tham gia composition như một aspect cụ thể. Nếu dùng annotation hoặc type pattern để chọn các lớp, phải xác minh nhóm concrete aspects thực tế.

## 23. Lỗi thiết kế state hay gặp

### Singleton nhưng chứa currentUser

Sai vì service có thể được gọi đồng thời; principal của người A có thể bị dùng cho lời gọi người B. Hãy dùng context theo invocation/task đã xác thực hoặc truyền tham số.

### pertarget nhưng tưởng là per-request

Một target service object thường sống dài và phục vụ nhiều request. pertarget gắn state với object, không tạo mới theo mỗi yêu cầu. Chọn lại model hoặc dùng request/workflow-scoped context thực sự.

### percflow nhưng dùng qua async

Một method tạo Future rồi trả về; flow ở thread caller kết thúc trước worker. percflow không tự truyền state giữa thread và không thay việc truyền correlation/security context tường minh.

### pertypewithin nhưng tưởng mỗi object

Một class có hàng nghìn instances vẫn có aspect state theo type chứ không theo từng instance. Nếu cần số lượt riêng từng object, xem pertarget hoặc một registry có hợp đồng phù hợp.

### State mutable không đồng bộ

Aspect instance per-object hoặc singleton có thể được gọi từ nhiều thread. Chỉ vì AspectJ tạo instance theo mô hình đã chọn không đồng nghĩa counter++ tự thread-safe.

### Aspect không cleanup tài nguyên

Nếu advice giữ ThreadLocal, lock, permit hoặc transaction, phải khôi phục/đóng đúng mốc và đúng thread. Việc method return trước công việc dài hoàn tất không cho phép tự giữ tài nguyên của lời gọi ngắn qua một task ngoài scope.

## 24. Những sai lầm về abstract aspect

1. **Đặt một abstract pointcut trong concrete aspect.** Điều này vi phạm quy tắc ngôn ngữ; khai báo abstract pointcut thuộc abstract aspect.
2. **Cho concrete aspect extends concrete aspect.** AspectJ chỉ cho kế thừa từ abstract aspect.
3. **Tưởng parent abstract tự tạo advice event độc lập.** Advice của parent có hiệu lực thông qua concrete subtype; không đếm thêm một lần do parent tự active.
4. **Quên override abstract pointcut.** Concrete child phải cung cấp định nghĩa, nếu không không thể hoàn chỉnh theo contract.
5. **Chỉ declare precedence giữa tên abstract parent.** Khi cần áp dụng tới concrete child, phải xác minh type patterns có bao phủ child (ví dụ dấu +).
6. **Mỗi child trùng pointcut và cùng emit business outcome.** Có thể tạo semantic duplicates dù mỗi child kế thừa đúng một template.
7. **Dùng abstract aspect để gom những quy tắc nghiệp vụ không liên quan.** Tái sử dụng AOP phù hợp hơn khi phần chung thực sự là một cross-cutting mechanism ổn định; business policy nên được đặt tên/kiểm thử riêng.

## 25. Kiểm thử ba nhóm hành vi

### Thứ tự advice

Kiểm thử một join point được match bởi nhiều aspect, xác nhận thứ tự before và unwind theo precedence. Cần có cả đường success và exception. Nếu một advice có quyền deny, kiểm tra method gốc có được gọi hay không.

### Abstract aspect

Kiểm tra concrete child áp dụng đúng pointcut, nhận advice kế thừa, và các method không thuộc target không bị áp dụng. Khi có hai concrete children, kiểm tra có trùng join point/metric ngoài ý muốn hay không.

### Model instantiation

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Singleton với 10 lời gọi | State chung theo instance được tạo và thread-safe khi cần |
| Hai object target khác nhau | pertarget state tách biệt |
| this khác target tại call join point | perthis/pertarget gắn đúng object |
| Một flow lồng nhau | percflow tạo scope theo dynamic entry |
| Chỉ các join point bên dưới entry | percflowbelow không bao chính entry |
| Hai class cùng khớp type pattern | pertypewithin có instance riêng cho type |
| Gọi aspectOf khi instance chưa bound | hasAspect/exception handling phù hợp |
| Hai task executor cùng chạy | Không chia sẻ context do hiểu sai scope |
| Method trả CompletionStage | Invocation return không bị coi là task completion |
| Mở rộng concrete child mới | Precedence và pointcut coverage được kiểm tra |

Có thể dùng event recorder trong bộ nhớ thay vì so stdout cho toàn hệ thống; stdout trong ví dụ giúp học thứ tự, nhưng test sản phẩm nên assert semantic events và state.

## 26. Các câu hỏi tự đánh giá

**Câu 1.** A có precedence cao hơn B, cả hai dùng around và đều gọi proceed đúng một lần. Thứ tự enter/leave?

**Đáp án:** A enter → B enter → target → B leave → A leave.

**Câu 2.** Một method chỉ được match bởi B, không được match bởi A. Khai báo A trước B có ép A chạy không?

**Đáp án:** Không. Precedence không làm pointcut tự khớp.

**Câu 3.** Một abstract aspect chứa before advice và một abstract pointcut, concrete child triển khai pointcut. Có hai instance abstract và concrete độc lập cùng ghi log không?

**Đáp án:** Không. Parent abstract cung cấp phần cơ chế cho concrete child; không có một event riêng chỉ vì parent tồn tại.

**Câu 4.** Hai concrete children cùng kế thừa một logging template và pointcut của chúng cùng chọn một operation. Có thể bị log hai lần không?

**Đáp án:** Có. Kế thừa chung code không tự loại trùng join point.

**Câu 5.** Vì sao pertarget không phải per-request?

**Đáp án:** Vì state gắn với target object; target thường được tái sử dụng bởi nhiều request.

**Câu 6.** Khi method thực thi bên trong object A được gọi từ object B, perthis và pertarget có nhất thiết khác nhau không?

**Đáp án:** Không ở execution join point thông thường; this/target liên quan đến object đang thực thi. Tại call join point, this thường là phía caller còn target là callee, nên có thể khác.

**Câu 7.** Có nên dùng percflow để tự chuyển security context sang thread pool?

**Đáp án:** Không. Dynamic control flow không tự tạo propagation qua asynchronous execution.

**Câu 8.** pertypewithin dùng type pattern hay pointcut?

**Đáp án:** Type pattern.

## 27. Quy trình áp dụng vào kiến trúc

1. **Liệt kê các concern** cần AOP và xác định operation boundary rõ.
2. **Viết contract cho từng advice:** sẽ log/deny/retry/commit gì, khi nào và cho những join point nào.
3. **Phân loại order dependencies:** cái gì phải bao ngoài để quan sát/kiểm soát kết quả; cái gì nằm bên trong.
4. **Khai báo precedence tường minh** khi nhiều advice cùng join point và thứ tự có ảnh hưởng.
5. **Tách template trừu tượng** nếu nhiều module cùng cơ chế nhưng khác điểm cắt; bắt buộc concrete child khai báo phạm vi.
6. **Chọn per-clause theo chủ sở hữu state**, không chọn theo tên cho dễ nhớ.
7. **Kiểm tra call vs execution semantics** cho perthis/pertarget và pointcut matching.
8. **Kiểm tra lifecycle async, nested flow và thread safety.**
9. **Viết tests cho ba trục WHERE/ORDER/SCOPE** và những exception paths.
10. **Review khi thêm aspect mới:** tránh chồng pointcut, precedence conflict và double counting.
11. **Giữ logic nghiệp vụ cốt lõi tường minh**, không giấu quyết định giá, hạn mức hoặc chuyển trạng thái trong một template AOP chung.

## 28. Tài liệu tham khảo và lưu ý phiên bản

Các quy tắc cú pháp trong bài đối chiếu theo tài liệu chính thức của AspectJ:

- [AspectJ Programming Guide – Language Semantics](https://eclipse.dev/aspectj/doc/latest/progguide/semantics.html): advice precedence, abstract aspect, inheritance và aspect instantiation.
- [AspectJ Quick Reference](https://eclipse.dev/aspectj/doc/latest/progguide/quickreference.html): cú pháp declare, pointcut, advice và per-clause.
- [AspectJ Developer's Notebook – pertypewithin](https://eclipse.dev/aspectj/doc/released/adk15notebook/pertypewithin.html): một instance mỗi type, accessor và điều kiện ngầm.
- [AspectJ ajc compiler guide](https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html): lệnh biên dịch, tùy chọn Java compliance và yêu cầu cung cấp đầy đủ nguồn khi compile/weave.

Với môi trường thực tế, kiểm tra phiên bản ajc, runtime aspectjrt và phiên bản Java tương thích. Nếu dùng incremental build hoặc weaving ở thời điểm khác, cần xác minh rằng các class chứa join point đã được instrument thực sự; việc viết một tệp aspect hợp lệ chưa chứng minh nó sẽ chạy trên mọi bytecode.

## 29. Tổng kết

- **Declare precedence** trả lời advice nào có thứ tự cao hơn ở join point chồng lấn; với around advice, thứ tự này thường tương ứng với các vòng bọc lồng nhau và thứ tự quay ra ngược lại.
- **Abstract aspect** cho phép tái sử dụng cơ chế AOP và để concrete subaspect định nghĩa pointcut cụ thể. Chỉ concrete aspect mới thực thi advice theo instance thực của nó.
- **Aspect instantiation model** xác định phạm vi state: singleton, per-object theo this/target, per-dynamic-control-flow hoặc per-type.
- **WHERE / ORDER / SCOPE** là ba quyết định độc lập cần kiểm thử cùng nhau. Đúng pointcut nhưng sai order hoặc sai scope vẫn có thể làm chương trình quan sát nhầm, đếm trùng hoặc rò state.
- **AOP giúp tách cơ chế chung**, nhưng cần giữ bất biến nghiệp vụ, identity context, async lifecycle và trách nhiệm tài nguyên trong những hợp đồng rõ ràng.

Khi nắm chắc cả thứ tự, kế thừa và vòng đời instance, ta có thể xây dựng những aspect dùng lại được, dự đoán được hành vi và an toàn hơn khi nhiều concern cùng áp dụng trên một chương trình.