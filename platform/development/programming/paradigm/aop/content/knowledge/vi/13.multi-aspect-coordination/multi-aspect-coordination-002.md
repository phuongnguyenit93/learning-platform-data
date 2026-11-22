# Thứ tự ưu tiên và quy tắc phân xử khi có xung đột giữa nhiều aspect

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), một **join point** có thể được chọn bởi nhiều **pointcut** và chịu tác động của nhiều **advice** thuộc các **aspect** khác nhau. Chẳng hạn một lần gọi nghiệp vụ có thể đồng thời được bảo vệ bởi aspect kiểm tra quyền, cache, transaction, retry, audit và tracing. Các aspect ấy đều có lý do tồn tại, nhưng **thứ tự phối hợp quyết định những hành vi nào chạy trước, hành vi nào có thể bị bỏ qua và kết quả/ngoại lệ cuối cùng bên gọi nhận được**.

Nếu không xác định thứ tự ưu tiên (**precedence**) và quy tắc phân xử xung đột, chương trình có thể vẫn biên dịch thành công nhưng:
- Trả dữ liệu cache trước khi kiểm tra quyền.
- Ghi audit thiếu sự kiện do một lớp bên ngoài short-circuit.
- Đo thời gian với phạm vi không khớp tên metric.
- Nuốt ngoại lệ khiến transaction không thấy lỗi để rollback.
- Retry toàn bộ thao tác có tác dụng phụ mà không bảo đảm idempotency.
- Gọi validation sau khi dữ liệu đã bị ghi hoặc đã phát sự kiện.
- Có kết quả khác nhau khi đổi cách lắp ghép aspect hoặc cấu hình build.

Bài này trình bày cách suy luận **thứ tự ưu tiên, thứ tự vào/ra, xung đột selection và behavior, ràng buộc bắt buộc, tie/cycle, fallback và kiểm thử** trong AOP nói chung. **Không tồn tại một cú pháp khai báo precedence hay quy ước số priority phổ quát**. Ví dụ Java 17 sử dụng các wrapper thuần Java để biểu diễn cơ chế kết hợp một cách minh bạch; đó là mô hình minh họa, không phải khẳng định mọi bộ weaver đều triển khai như vậy.

## 1. Khái niệm nền: nhiều aspect cùng tác động một join point

Các thuật ngữ cần tách riêng:

- **Join point:** điểm trong hoạt động của chương trình mà một mô hình AOP có thể can thiệp, chẳng hạn method call hoặc method execution nếu được hỗ trợ.
- **Pointcut:** biểu thức chọn những điểm cần được can thiệp; các pointcut khác nhau có thể chọn cùng một điểm.
- **Advice:** hành vi thực thi tại join point đã chọn, ví dụ before, after returning, after throwing, after/finally hoặc around.
- **Aspect:** đơn vị tập hợp pointcut/advice và có thể có state/lifecycle riêng.
- **Weaving:** cách đưa các advice vào chương trình thông qua compiler, biến đổi binary, lúc nạp lớp hoặc proxy/wrapper.
- **Precedence / order:** quan hệ ưu tiên xác định các advice được kết hợp, sắp xếp hoặc vào chuỗi thực thi theo hợp đồng của nền tảng.
- **Conflict resolution:** chính sách xác định phải làm gì khi nhiều aspect cùng match, có ràng buộc trái ngược, priority bằng nhau, chặn continuation hoặc thay đổi kết quả/ngoại lệ.

Ví dụ một nghiệp vụ `AccountService.transfer(...)` có thể match các concern:

~~~text
Authorization: kiểm tra chủ thể và quyền trên tài khoản
Validation:    kiểm tra yêu cầu hợp lệ
Transaction:   xác lập ranh giới ghi dữ liệu
Audit:         ghi dấu vết được phép thu thập
Tracing:       tạo một span cho lời gọi
Retry:         thử lại một số lỗi tạm thời
~~~

**Cùng match không có nghĩa tất cả đều luôn chạy**. Nếu một around advice ngoài cùng không gọi tiếp, những advice bên trong có thể không được vào; nếu một advice bắt ngoại lệ rồi trả fallback, các lớp ngoài có thể thấy nhánh thành công thay vì lỗi.

## 2. Phân biệt bốn loại thứ tự

| Khái niệm | Câu hỏi | Có đồng nhất với thứ tự chạy không? |
| --- | --- | --- |
| **Thứ tự xử lý khi build** | Weaver đọc aspect A hay B trước? | Không mặc định; bộ dệt có thể dùng precedence riêng |
| **Thứ tự ghép advice** | Aspect nào bao ngoài/được xét trước? | Quyết định cấu trúc, nhưng phải biết loại advice |
| **Thứ tự chạy ở đường vào** | Before/đầu around nào thấy invocation trước? | Thường ngoài → trong ở mô hình wrapper |
| **Thứ tự chạy ở đường ra** | After/finally nào hoàn tất trước? | Thường trong → ngoài ở wrapper lồng nhau |

Lấy chuỗi around:

~~~text
A(B(C(Business)))
~~~

Nếu cả A, B, C đều gọi continuation đúng một lần và không chặn:

~~~text
A.before
B.before
C.before
Business
C.after
B.after
A.after
~~~

Kết quả là **thứ tự vào và thứ tự ra đảo nhau**. Nếu C ném lỗi, after-success của C và các lớp ngoài không tự chạy; code xử lý error/finally mới có cơ hội được gọi theo cách đã viết.

**Cẩn thận với advice không phải around:** một ngôn ngữ AOP có thể quy định cách xếp before và after độc lập, ví dụ dựa trên precedence hoặc thứ tự khai báo trong cùng aspect. Không tự lấy sơ đồ wrapper làm tiêu chuẩn cho mọi công cụ. Muốn xác định chính xác, phải đọc hợp đồng precedence của mô hình đang dùng và kiểm tra hành vi thực.

## 3. Priority là quy tắc kết hợp, không tự là quy tắc số

Một hệ thống có thể mô tả:

~~~text
AUTH > TX > AUDIT > METRICS
~~~

Dấu `>` ở đây được **quy ước cục bộ** là “bao ngoài/được ưu tiên cao hơn trong chuỗi đang xét”. Không có nghĩa:
- Giá trị priority số lớn luôn ưu tiên hơn số nhỏ.
- Aspect được compile trước sẽ chạy before trước.
- Các loại advice đều dùng cùng một phép sắp xếp.
- Advice thuộc cùng aspect được sắp giống lời gọi tới các aspect khác.
- Một aspect ưu tiên cao sẽ tự luôn chạy trên mọi đường gọi, kể cả đường không đi qua join point.

Có mô hình dùng thứ tự khai báo, có mô hình dùng số priority, có mô hình dùng quan hệ trước/sau hoặc đặc tả định hướng riêng. Điều quan trọng là **định nghĩa lại bằng lời ngữ nghĩa chính xác của priority trước khi dùng**.

### 3.1 Ưu tiên ở cấp aspect và advice có thể khác nhau

Một aspect có thể có nhiều advice cùng match một join point. Quy tắc thứ tự **giữa các aspect** có thể khác quy tắc **giữa các advice trong một aspect**; một số ngôn ngữ còn có quy tắc về kiểu advice, vị trí khai báo hoặc sự không xác định khi hai advice cùng điều kiện.

Vì thế cần ghi rõ:
- Thứ tự precedence chỉ áp dụng **khác aspect** hay cả **nội bộ một aspect**?
- Around ngoài có gọi `proceed` hay không?
- Before được ghép vào bên nào so với around?
- After-returning, after-throwing và finally có thứ tự nào sau khi lời gọi kết thúc?
- Khi equal priority hoặc không khai báo, thứ tự có được bảo đảm không?

Nếu công cụ không đưa ra thứ tự chắc chắn cho trường hợp quan trọng, đó là **rủi ro thiết kế**, không nên trông chờ hệ thống hiện tại “tình cờ chạy đúng”.

### 3.2 Dựng một quy tắc có thể kiểm chứng

Một mô hình tự thiết kế có thể dùng:
1. Mỗi rule được gán **mức độ ưu tiên khác nhau**.
2. Mức số **cao hơn** (theo quy ước riêng) nghĩa là **outermost**.
3. Sort giảm dần theo priority.
4. Ghép wrapper từ phần tử **cuối lên đầu** để bảo đảm outermost đúng ý.
5. Nếu hai rule cùng priority, **fail fast** khi không có chính sách tie-break được phê duyệt.
6. Kiểm tra các ràng buộc an ninh/tác dụng phụ sau khi ghép.

Đây là **quy tắc của một builder minh họa**, không phải luật chung của AOP. Mục tiêu là tạo kết quả ổn định và để người đọc có thể xác minh thứ tự từ code.

## 4. Thứ tự lồng nhau quyết định ai được chạy

Một chuỗi:

~~~text
Outer(Middle(Inner(Business)))
~~~

có ba trường hợp quan trọng:

**Đường thành công:** Outer vào trước, Inner chạy gần nghiệp vụ nhất; khi quay về, Inner kết thúc trước Outer.

**Đường lỗi:** advice đã vào có thể thấy ngoại lệ theo đường ngược; nếu Inner chuyển ngoại lệ thành kết quả thì Outer có thể không còn thấy lỗi.

**Đường short-circuit:** nếu Outer trả sớm mà không gọi Middle, Middle/Inner/Business **không chạy**; bản thân Outer có thể vẫn chạy phần cleanup do nó tự tổ chức.

Do đó câu “A có priority cao hơn B” phải được giải nghĩa cụ thể: A có bao ngoài B không? A có quyền bỏ qua B không? A có thể đổi lỗi thành kết quả không?

### 4.1 Thứ tự xây dựng wrapper có thể ngược thứ tự chạy

Giả sử:

~~~text
chain = Business
chain = Trace(chain)
chain = Cache(chain)
chain = Auth(chain)
~~~

Kết quả:

~~~text
Auth(Cache(Trace(Business)))
~~~

`Auth` được **thêm cuối**, nhưng ở **ngoài cùng** và vào trước. Nếu builder dùng kiểu `chain = Wrap(newAdvice, chain)`, không thể lấy thứ tự duyệt danh sách làm thứ tự BEFORE runtime nếu chưa biết builder duyệt từ đầu hay cuối.

Một bộ weaver khác có thể phân tích tất cả aspect rồi lập graph precedence trước khi tạo artifact, không chạy vòng lặp wrapper như trên.

## 5. Xung đột có những loại nào?

### 5.1 Xung đột thứ tự trước/sau

A cần chạy trước B, nhưng precedence hiện hành đưa B ra ngoài A. Ví dụ kiểm tra quyền phải trước cache trả dữ liệu cá nhân; nếu cache ở ngoài và trả hit thì phân quyền có thể bị bypass.

### 5.2 Xung đột selection

Hai pointcut chồng nhau và cùng áp dụng advice vào một phương thức, dẫn tới:
- Logging/metrics đếm hai lần.
- Hai validation rules có hành vi khác.
- Hai transaction/retry wrappers không được thiết kế chạy lồng nhau.
- Một pointcut quá rộng chọn cả mã helper của advice, gây reentrancy.
- Một helper method hoặc bridge method bị chọn thêm hoặc bỏ sót theo bộ weaver.

**Selection conflict khác order conflict.** Đổi precedence không giải quyết một pointcut đã chọn sai tập join point; cần sửa quy tắc match hoặc phân tách trách nhiệm.

### 5.3 Xung đột thay đổi dữ liệu

Một advice chuẩn hóa tham số thành dạng X; advice khác kỳ vọng dạng gốc Y. Nếu chạy theo thứ tự khác, dữ liệu nghiệp vụ/khóa cache có thể khác. Một advice sửa kết quả trả về cũng có thể làm outer advice thấy response khác.

Không phải mọi nền tảng AOP đều cho phép around advice thay args hoặc gọi tiếp nhiều lần. Cần kiểm tra hợp đồng continuation và kiểu.

### 5.4 Xung đột xử lý ngoại lệ

Ví dụ:
- ErrorTranslator chuyển ngoại lệ hạ tầng thành lỗi nghiệp vụ.
- Transaction advice cần nhìn thấy lỗi để rollback.
- Retry advice chọn một số loại lỗi tạm thời.
- Audit advice muốn ghi nhận cả lỗi và thành công.

Nếu Translator nuốt ngoại lệ **trước khi** Transaction có thể quan sát, transaction có thể xem lần gọi là thành công. Ngược lại, nếu Retry nằm ngoài Transaction và mỗi attempt tạo một transaction mới, ngữ nghĩa khác với Retry nằm trong một transaction kéo dài. Không thể quyết định chỉ từ tên aspect; phải biết **error path và side effects**.

### 5.5 Xung đột trạng thái

Hai aspect có thể cùng sửa một cache, registry, thread context hoặc thông tin tracing. Priority không tự giải quyết race condition. Thứ tự đồng bộ trong một thread không bảo đảm toàn vẹn khi nhiều thread chạy song song; cần thread-safety, ownership và lifecycle của state.

## 6. Các quy tắc phân xử có thể áp dụng

Một **bộ quy tắc phân xử** nên được viết như một phần của thiết kế, không dựa vào may rủi. Các nhóm quy tắc hữu ích:

| Quy tắc | Cách hiểu | Trường hợp dùng |
| --- | --- | --- |
| **Bắt buộc trước (must precede)** | A phải ở ngoài hoặc chạy kiểm tra trước hành vi B cụ thể | Authorization trước cache trả dữ liệu |
| **Bắt buộc sau (must follow)** | B chỉ được chạy sau khi A hoàn tất điều kiện | Audit sau khi biết outcome |
| **Bao phạm vi (must surround)** | A phải bao toàn bộ logic B, kể cả nhánh lỗi/cleanup | Đo latency end-to-end |
| **Không đồng tồn tại (mutual exclusion)** | Hai aspect không được cùng instrument một điểm theo một cách | Hai cơ chế retry không tương thích |
| **Gộp trách nhiệm** | Hai chức năng quá phụ thuộc để sắp độc lập | Validation và chuẩn hóa chung một precondition |
| **Phân tách phạm vi** | Sửa pointcut để loại overlap không mong muốn | Tránh logging hai lần |
| **Từ chối khi thiếu thứ tự** | Thiếu/đụng priority làm cấu hình fail fast | Security/transaction cần thứ tự bảo đảm |
| **Ràng buộc thứ tự bộ phận** | Chỉ công bố những cặp thật sự có quan hệ | Metrics và audit có thể độc lập |
| **Khả năng thử lại có kiểm soát** | Cho phép retry khi lỗi thuộc nhóm và thao tác idempotent | Temporary failure |
| **Bảo toàn hợp đồng** | Không biến đổi return/throw trừ khi chính sách cho phép | Logging/metrics chỉ quan sát |

**Quan trọng:** “ưu tiên cao nhất” không phải lúc nào cũng đồng nghĩa “được phép bỏ qua mọi thứ khác”. Với audit hoặc security bắt buộc, cần một bất biến: dù cache hit, deny, retry hay fallback, **mỗi đường đi phải đáp ứng nghĩa vụ tương ứng**.

### 6.1 Fail-fast hay tự chọn tie-break?

Với xung đột priority bằng nhau có hai hướng:
- **Fail fast:** từ chối khởi động/xây dựng cấu hình nếu thứ tự cần thiết nhưng không rõ. Dễ phát hiện vấn đề sớm, đặc biệt ở auth/transaction.
- **Tie-break ổn định:** ví dụ dựa trên thứ tự khai báo tường minh hoặc một ID ổn định, nhưng chỉ khi tie **được phép về ngữ nghĩa**. Một tie-break tùy ý có thể che lỗi thiết kế.

**Không nên dùng thứ tự của hash map hoặc kết quả reflection không có hợp đồng như tie-break cho an ninh.** Kết quả nhìn có vẻ ổn định ở một lần chạy không phải bằng chứng được bảo đảm qua phiên bản/JVM/build.

### 6.2 Khi nào không cần thứ tự toàn phần?

Nếu hai advice chỉ độc lập phát ra số liệu theo cơ chế an toàn, không biến đổi kết quả, và thứ tự không ảnh hưởng ý nghĩa, có thể chỉ cần một **partial order** giữa những cặp có phụ thuộc.

Ví dụ:

~~~text
Auth must precede Cache
Transaction must surround Mutation
Tracing may be outer or inner depending on metric scope
~~~

Một partial order hợp lệ không nhất thiết xác định vị trí duy nhất cho mọi aspect. Nhưng ở nơi kết quả quan sát có thể khác, như tracing scope, phải **định nghĩa rõ metric muốn đo** trước khi chấp nhận nhiều thứ tự.

## 7. Quan hệ ưu tiên dưới dạng đồ thị và xử lý chu trình

Mỗi ràng buộc `A -> B` có thể biểu thị “A phải nằm ngoài/đi trước B” trong ngữ cảnh đã quy ước. Tập ràng buộc tạo một **đồ thị có hướng**.

Ví dụ hợp lệ:

~~~text
Authorization -> Cache
Authorization -> BusinessEffects
Transaction   -> BusinessEffects
Audit         -> BusinessEffects
~~~

Có thể tạo một thứ tự topo nếu đồ thị **không có chu trình**. Thứ tự topo có thể không duy nhất nếu một vài cặp không có quan hệ; mọi kết quả hợp lệ phải vẫn bảo toàn các cạnh ràng buộc.

Ví dụ mâu thuẫn:

~~~text
A -> B
B -> C
C -> A
~~~

Không tồn tại thứ tự tuyến tính thỏa cả ba ràng buộc. Một builder đúng nên **phát hiện cycle và báo lỗi cấu hình** thay vì lờ một cạnh, chọn theo tên alphabet hoặc âm thầm tạo hành vi không phù hợp.

### 7.1 Thuật toán phân xử khái niệm

~~~text
input: tập aspect + tập ràng buộc bắt buộc
validate pointcut overlap and incompatible rules
construct directed precedence graph
if graph contains a cycle:
    reject configuration and report the cycle
compute topological order under the documented convention
for unconstrained ties:
    use an approved explicit stable policy or require more constraints
compose selected advice into an effective chain
assert protected invariants through success/error/short-circuit paths
~~~

Đây là **giả mã**, không phải API của một bộ AOP nào. Nếu một cơ chế chỉ hỗ trợ **priority số**, có thể phải ánh xạ những quan hệ cần thiết sang số không trùng; nếu nó không cho bảo đảm một ràng buộc bắt buộc, cần sửa kiến trúc hoặc chuyển trách nhiệm cần bảo vệ sang một ranh giới khác.

### 7.2 Không tạo chu trình do mô tả nhầm ngữ nghĩa

Một yêu cầu như “Tracing phải chạy trước business và cũng phải chạy sau business” **không phải** quan hệ ưu tiên có chu trình: đó có thể là một around advice có phần before và after. Hãy biểu diễn yêu cầu **bao phạm vi**, không tạo hai cạnh Tracing -> Business và Business -> Tracing rồi coi là conflict.

Đồ thị mô tả **vị trí lớp**, trong khi một lớp có thể có cả pha vào và pha ra. Phân biệt hai khái niệm giúp tránh báo chu trình giả.

## 8. Ví dụ Java 17: precedence, tie và short-circuit

Ví dụ Java dưới đây **không dùng trình biên dịch AOP đặc biệt**. Nó dựng một chuỗi wrapper có ngữ nghĩa quanh advice bằng Java 17, với **quy ước cục bộ priority số lớn hơn => wrapper ngoài hơn**. Builder sort theo priority giảm dần rồi bọc **từ cuối danh sách về đầu**.

Ba concern:
- `AUTH`: kiểm tra yêu cầu; từ chối ID `deny` trước khi cho chạy tiếp.
- `CACHE`: trả sớm với ID `cached`; nếu không hit, tiếp tục.
- `TRACE`: log before/after/error/finally khi đi tới lớp đó.

Ví dụ có cấu hình **an toàn** `AUTH > CACHE > TRACE`, một cấu hình **rủi ro** `CACHE > AUTH > TRACE`, và kiểm tra **priority trùng nhau**. Kết quả thể hiện tại sao thứ tự lắp ghép không phải chi tiết trang trí.

Lưu file `AspectPrecedenceDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class AspectPrecedenceDemo {
    @FunctionalInterface
    interface Action {
        String run(String id);
    }

    @FunctionalInterface
    interface Wrapper {
        Action wrap(Action next);
    }

    record Rule(String name, int priority, Wrapper factory) {}

    static Action business() {
        return id -> {
            System.out.println("BUSINESS " + id);
            if ("fail".equals(id)) {
                throw new IllegalStateException("failed");
            }
            return "OK:" + id;
        };
    }

    static Action authorize(Action next) {
        return id -> {
            System.out.println("AUTH CHECK");
            if ("deny".equals(id)) {
                System.out.println("AUTH REJECT");
                throw new SecurityException("forbidden");
            }
            return next.run(id);
        };
    }

    static Action cache(Action next) {
        return id -> {
            if ("cached".equals(id)) {
                System.out.println("CACHE HIT");
                return "CACHED:cached";
            }
            System.out.println("CACHE MISS");
            return next.run(id);
        };
    }

    static Action trace(Action next) {
        return id -> {
            System.out.println("TRACE BEFORE");
            try {
                String result = next.run(id);
                System.out.println("TRACE AFTER");
                return result;
            } catch (RuntimeException error) {
                System.out.println("TRACE ERROR "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println("TRACE FINALLY");
            }
        };
    }

    static Action compose(List<Rule> specs) {
        List<Rule> ordered = new ArrayList<>(specs);
        ordered.sort(
                Comparator.comparingInt(Rule::priority).reversed()
                        .thenComparing(Rule::name));

        for (int i = 1; i < ordered.size(); i++) {
            if (ordered.get(i - 1).priority()
                    == ordered.get(i).priority()) {
                throw new IllegalArgumentException(
                        "ambiguous priority");
            }
        }

        System.out.println("ORDER " + ordered.stream()
                .map(Rule::name)
                .collect(Collectors.joining(">")));

        Action result = business();
        for (int i = ordered.size() - 1; i >= 0; i--) {
            result = ordered.get(i).factory().wrap(result);
        }
        return result;
    }

    static void scenario(String name, Action action, String id) {
        System.out.println("CASE " + name);
        try {
            System.out.println("RESULT " + action.run(id));
        } catch (RuntimeException error) {
            System.out.println("CALLER "
                    + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Action safe = compose(List.of(
                new Rule("TRACE", 10, AspectPrecedenceDemo::trace),
                new Rule("CACHE", 20, AspectPrecedenceDemo::cache),
                new Rule("AUTH", 30, AspectPrecedenceDemo::authorize)));

        scenario("safe-normal", safe, "ok");
        scenario("safe-cached", safe, "cached");
        scenario("safe-denied", safe, "deny");
        scenario("safe-error", safe, "fail");

        Action risky = compose(List.of(
                new Rule("AUTH", 20, AspectPrecedenceDemo::authorize),
                new Rule("TRACE", 10, AspectPrecedenceDemo::trace),
                new Rule("CACHE", 30, AspectPrecedenceDemo::cache)));
        scenario("risky-cached", risky, "cached");

        System.out.println("CASE duplicate-priority");
        try {
            compose(List.of(
                    new Rule("AUTH", 10, AspectPrecedenceDemo::authorize),
                    new Rule("CACHE", 10, AspectPrecedenceDemo::cache)));
        } catch (IllegalArgumentException error) {
            System.out.println("CONFIG " + error.getMessage());
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac AspectPrecedenceDemo.java
java AspectPrecedenceDemo
~~~

Stdout dự kiến **theo chính chương trình Java 17 ở trên**:

~~~text
ORDER AUTH>CACHE>TRACE
CASE safe-normal
AUTH CHECK
CACHE MISS
TRACE BEFORE
BUSINESS ok
TRACE AFTER
TRACE FINALLY
RESULT OK:ok
CASE safe-cached
AUTH CHECK
CACHE HIT
RESULT CACHED:cached
CASE safe-denied
AUTH CHECK
AUTH REJECT
CALLER SecurityException
CASE safe-error
AUTH CHECK
CACHE MISS
TRACE BEFORE
BUSINESS fail
TRACE ERROR IllegalStateException
TRACE FINALLY
CALLER IllegalStateException
ORDER CACHE>AUTH>TRACE
CASE risky-cached
CACHE HIT
RESULT CACHED:cached
CASE duplicate-priority
CONFIG ambiguous priority
~~~

### 8.1 Đọc kết quả: trường hợp bình thường

Trong `safe-normal`, thứ tự `AUTH > CACHE > TRACE` dẫn tới:

~~~text
AUTH CHECK -> CACHE MISS -> TRACE BEFORE -> BUSINESS
                                     |
                                    return
                                     v
                              TRACE AFTER
                              TRACE FINALLY
~~~

`AUTH` chạy trước cache; `TRACE` ở bên trong chỉ đo **lời gọi thực sự đi tiếp qua cache**. Nếu mục tiêu tracing là đo tổng thời gian từ lúc caller gọi tới lúc cache trả về, vị trí `TRACE` này **không đáp ứng** yêu cầu, vì nhánh cache hit không đi qua nó.

### 8.2 Đọc kết quả: cache hit an toàn và không an toàn

`safe-cached` vẫn in `AUTH CHECK` **trước** `CACHE HIT`. `risky-cached` in duy nhất `CACHE HIT`: Authorization bên trong **không được gọi**.

Trong demo, chuỗi cache giả trả giá trị cố định cho một ID và **không xử lý dữ liệu người dùng thật**. Đây chỉ là minh họa thứ tự. Trong hệ thống thật, cache key, policy và quyền truy cập còn phải chính xác theo principal/tenant/tài nguyên.

### 8.3 Đọc kết quả: từ chối và ngoại lệ

Với `safe-denied`, AUTH ném `SecurityException` trước continuation; các lớp CACHE, TRACE, BUSINESS không được vào. Nếu audit bắt buộc ghi **mọi lần từ chối**, audit phải đặt ở ranh giới phù hợp (ví dụ bao ngoài kiểm tra quyền) hoặc được gọi tường minh trong chính nhánh từ chối.

Với `safe-error`, TRACE đã vào và thấy `IllegalStateException`, nên in `TRACE ERROR` rồi `TRACE FINALLY`. Không có `TRACE AFTER` vì target không trả về bình thường.

### 8.4 Priority trùng là một quyết định thiết kế

Builder của ví dụ **không âm thầm đoán** giữa hai rule cùng số: nó ném `IllegalArgumentException("ambiguous priority")`. Đây là quy ước bảo vệ chính demo, **không phải hành vi mặc định bắt buộc của mọi công cụ AOP**.

Ở một hệ thống thực, có thể cho phép tie giữa hai advice độc lập; nhưng với tương tác an ninh/giao dịch, nên yêu cầu thứ tự rõ hoặc chứng minh hai thứ tự đều giữ hợp đồng. Thứ tự tên alphabet chỉ là một chính sách khi được **công bố và phê duyệt**, không tự có giá trị bảo mật.

### 8.5 Hạn chế cần nhớ

- Mẫu này chỉ **dựng wrapper Java thuần**, không khai báo pointcut của một bộ weaver.
- `priority` cao ở ngoài là **quy tắc tự đặt**; không suy ra cú pháp/ký hiệu tương tự ở mọi AOP.
- Trong demo, CACHE cố tình short-circuit và AUTH chỉ từ chối ID `deny`; không phải xác thực/phân quyền thật.
- Không có transaction, retry, audit store, logging backend, dữ liệu nhạy cảm hoặc concurrency production.
- Không chứng minh mọi `before`, `after` độc lập ở một ngôn ngữ AOP sẽ xếp như các method wrapper này.
- Nếu gọi `business()` trực tiếp, không có wrapper; phạm vi proxy/delegation khác với biến đổi bytecode trực tiếp ở method execution.

## 9. Phân xử xung đột giữa authorization, cache và audit

Đây là tình huống dễ tạo lỗi bảo mật.

### 9.1 Authorization phải bảo vệ cả cache hit

Nếu cache có dữ liệu phụ thuộc danh tính hoặc quyền, chuỗi:

~~~text
Cache(Authorize(Business))
~~~

cho phép cache ở ngoài trả kết quả mà không gọi `Authorize` bên trong. Thiết kế này **không đáp ứng** bất biến “mọi lần đọc được bảo vệ bởi kiểm tra quyền trước khi trả dữ liệu” trừ khi chính Cache có một cơ chế xác thực/phân quyền tương đương và chứng minh được.

Một cấu trúc rõ ràng hơn:

~~~text
Authorize(Cache(Business))
~~~

Nhưng vẫn phải đảm bảo mọi caller cần bảo vệ đi qua outer boundary; nếu có một lời gọi trực tiếp target hoặc cache không được bảo vệ, thứ tự wrapper không cứu được.

### 9.2 Audit cần ghi gì?

Nếu yêu cầu audit là **mọi quyết định cho phép/từ chối**, đặt Audit bên trong Authorization và chỉ để nó ghi khi tiếp tục là không đủ:

~~~text
Authorization(Audit(Business))
~~~

Nhánh từ chối có thể không gọi Audit. Phải xác định:
- Audit ghi **request attempt** hay **business success**?
- Cần ghi cả **denied requests** không?
- Có cần ghi cache hit/fallback/exception không?
- Dữ liệu tối thiểu nào được phép giữ lại?
- Event phải phát trước/đồng thời/sau tác dụng phụ theo tiêu chuẩn nào?

Không nên tự log token hoặc raw arguments chỉ vì một aspect được đặt ở ngoài. **Thứ tự đúng và data minimization là hai yêu cầu riêng**.

### 9.3 Không biến kiểm soát quyền thành “best effort”

Một advice bảo mật chỉ ghi cảnh báo rồi `proceed` khi thiếu quyền không tạo ra bảo đảm chặn. Với các ranh giới an ninh, hãy định nghĩa **fail-closed** khi không thể xác minh quyền (theo chính sách nghiệp vụ phù hợp) và kiểm thử mọi đường thoát.

## 10. Transaction, retry, ngoại lệ và precedence

Một tương tác phức tạp thường có dạng:

~~~text
Retry(Transaction(Business))
Transaction(Retry(Business))
~~~

Nếu Retry nằm ngoài Transaction và gọi continuation ba lần, **mỗi lần thử có thể đi qua vùng Transaction mới**, nếu Transaction thực sự tạo/kết thúc một giao dịch khi continuation được gọi. Nếu Transaction nằm ngoài Retry, các lần thử có thể diễn ra **trong một ranh giới giao dịch**, thay đổi khả năng rollback/commit.

Không được kết luận chắc chắn từ hai cái tên `Retry` và `Transaction`: cần biết implementation thật, cơ chế truyền transaction, loại lỗi nào được retry, và các ràng buộc khi thao tác đã gây tác dụng phụ.

### 10.1 Các nhánh lỗi phải được định nghĩa

Giả mã:

~~~text
around retry:
    for attempt in 1..max:
        try:
            return proceed()
        catch transientError:
            if canRetrySafely(attempt): continue
            else: throw
~~~

Nếu advice Retry **nuốt mọi exception** mà không phân loại, nó có thể lặp lại lỗi validation cố định hoặc tác dụng phụ đã thành công ở lần đầu nhưng response bị mất. Cần:
- Chỉ retry lỗi có khả năng tạm thời.
- Giới hạn attempts và backoff.
- Có deadline/cancellation.
- Bảo đảm idempotency hoặc deduplication khi cần.
- Ghi rõ số lần gọi logic khác số lần target thực thi.

### 10.2 Exception translation và rollback

Giả sử:

~~~text
Transaction(Translate(Business))
Translate(Transaction(Business))
~~~

Ở cấu trúc đầu, nếu `Translate` bắt một lỗi rồi trả **fallback thành công**, Transaction bên ngoài có thể xem lần gọi là success và commit, trừ khi policy transaction có tín hiệu rollback độc lập.

Ở cấu trúc thứ hai, Transaction có thể thấy lỗi gốc, quyết định rollback, rồi Translate bên ngoài mới chuyển lỗi sang response phù hợp.

Đây là **khả năng theo logic lồng nhau**, không phải cam kết mọi transaction manager sẽ hành xử như vậy. Nếu transaction được đánh dấu rollback-only hoặc có các quy tắc khác, kết quả cần được kiểm chứng bằng test thực.

### 10.3 Khi nào đặt metrics ngoài/ trong?

~~~text
Metrics(Retry(Transaction(Business)))
Retry(Transaction(Metrics(Business)))
~~~

Mẫu đầu có thể đo **toàn bộ thời gian** gồm nhiều attempt; mẫu sau có thể ghi một metric cho mỗi attempt hoặc chỉ đoạn business, tùy vị trí.

Tên metric nên phân biệt:
- Request-level latency.
- Attempt-level latency.
- Transaction-level latency.
- Target-execution latency.

Không thể quyết định thứ tự metrics chỉ dựa vào nguyên tắc “ưu tiên số lớn nhất”. Cần bắt đầu từ **câu hỏi quan sát**.

## 11. Xung đột giá trị trả về, args và short-circuit

Một around advice có thể có khả năng:
- Chuyển đổi args trước `proceed` khi mô hình hỗ trợ.
- Gọi `proceed` một hoặc nhiều lần nếu hợp đồng cho phép.
- Trả giá trị cache, fallback hoặc kết quả đã được biến đổi.
- Chuyển exception thành kết quả.
- Ném một exception mới.

Nếu hai advice cùng muốn **sửa args**, thứ tự có thể ảnh hưởng giá trị thật đến target. Một filter chuẩn hóa `trim` rồi một filter mã hóa khác với làm ngược thứ tự khi phép biến đổi không giao hoán.

Nếu hai advice cùng muốn **sửa result**, outer advice nhận kết quả mà inner đã biến đổi; kết quả cuối có thể phụ thuộc thứ tự. Với kiểu trả về primitive, generic, nullability hoặc checked exceptions, bất kỳ biến đổi nào cũng phải giữ hợp đồng mà caller kỳ vọng.

### 11.1 Phép biến đổi có thể không giao hoán

Ký hiệu hai phép xử lý `A` và `B`:

~~~text
A(B(x)) != B(A(x))   (trong một số tình huống)
~~~

Đây không phải định lý rằng **mọi** advice không giao hoán. Logging độc lập có thể cho cùng kết quả nghiệp vụ theo cả hai thứ tự, nhưng kết quả log/latency có thể vẫn khác.

Cần xác định **điều gì được phép thay đổi**:
- Chỉ thứ tự quan sát?
- Số metric?
- Giá trị trả về?
- Loại ngoại lệ?
- Side effects?
- Trạng thái transaction?
- Quyền truy cập và audit?

Nếu câu trả lời vượt quá sự khác biệt cho phép, precedence là một phần của **hợp đồng chương trình**, không thể để mặc định.

## 12. Weaving order khác advice precedence

Trong compile-time hoặc post-compile weaving, một bộ weaver có thể xử lý các aspect theo một thứ tự nội bộ; nhưng thứ tự ấy **không mặc định** quyết định thứ tự advice runtime. Công cụ có thể xây graph precedence độc lập rồi mới kết hợp mã.

Ngược lại, nếu dùng code wrapper thủ công:

~~~text
chain = Target
chain = A(chain)
chain = B(chain)
~~~

`B` bao ngoài `A`, vì mỗi lần thêm tạo lớp ngoài mới. Một người đọc thứ tự lệnh A rồi B mà kết luận `A.before` chạy trước B sẽ sai.

Thêm một phép biến đổi bytecode khác có thể làm thay đổi **tập join point** mà weaver sau nhìn thấy. Đây là xung đột **transformation order** chứ chưa chắc xung đột **advice precedence**.

### 12.1 Dệt nhiều lần có thể làm thêm advice?

Một số công cụ hỗ trợ reweaving có kiểm soát, số khác từ chối hoặc có hành vi khác. Không mặc định `W(W(P)) == W(P)` hay mặc định luôn có double logging. Phải theo hợp đồng của công cụ, giữ đầu vào unwoven và kiểm tra artifact.

### 12.2 Runtime proxy có thể bỏ qua advice

Một chuỗi interceptor nằm trên proxy chỉ nhận những lời gọi **qua proxy**. Direct-call target hoặc self-invocation trên target có thể bypass, bất kể priority đã khai báo. Với weaving trực tiếp method execution, phạm vi có thể khác.

**Quy tắc ưu tiên không thể sửa một join point chưa từng được instrument.**

## 13. Tránh chu trình và tie giả khi phối hợp aspect

**Chu trình precedence** khác với hai aspect có priority bằng nhau. Nếu A phải bao ngoài B, B bao ngoài C và C bao ngoài A trong **cùng một chuỗi**, không thể dựng một thứ tự thỏa cả ba. Bộ phối hợp nên từ chối cấu hình mâu thuẫn thay vì âm thầm bỏ một ràng buộc; cách phát hiện chu trình và xử lý các vòng khởi tạo/runtime được thực hành riêng khi phân tích phụ thuộc vòng.

**Tie** chưa chắc là lỗi: nếu hai advice thật sự độc lập theo hợp đồng, hệ thống có thể dùng tie-break đã công bố hoặc cho phép thứ tự không xác định khi mọi kết quả hợp lệ đều tương đương. Nếu chính sách phụ thuộc thứ tự, phải thêm ràng buộc tường minh, không lấy tên lớp, thứ tự tìm file hoặc thời điểm đăng ký để chữa cháy.

### 13.1. Phân loại ràng buộc thay vì đặt một bảng priority cứng

Khi review, phân biệt **bất biến bắt buộc** (quyền, toàn vẹn, commit/audit theo nghĩa vụ), **hợp đồng chức năng** (validation, caching, retry) và **quan sát/tối ưu** (tracing, metrics). Đây là nhóm câu hỏi để phát hiện xung đột, **không phải trật tự chung**: audit bắt buộc hoặc metric end-to-end đôi khi phải bao ngoài chính sách khác. Chỉ tuyên bố hai aspect có thể hoán đổi khi đã kiểm chứng không làm thay đổi những bất biến liên quan.

## 14. Test matrix bắt buộc cho nhiều aspect

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Một join point có hai before advice | Thứ tự đã xác định và không lặp ngoài ý muốn |
| Around A bao Around B | Đường vào/ra đúng mô hình precedence |
| Bên ngoài short-circuit | Lớp bên trong không chạy; nghĩa vụ vẫn được bảo vệ |
| Nghiệp vụ thành công | Return value và side effects đúng |
| Nghiệp vụ ném lỗi | After-success không chạy sai; after-error/finally đúng |
| Inner bắt lỗi trả fallback | Outer thấy success hay lỗi theo hợp đồng |
| Cache hit trước authentication | Không trả dữ liệu trái quyền |
| Authorization deny | Target không gây tác dụng phụ; audit bắt buộc vẫn có |
| Retry nhiều attempts | Không lặp side effects trái ý, transaction đúng |
| Transaction rollback | Exception translation không che mất tín hiệu rollback |
| Pointcut overlap | Không instrument trùng hoặc thiếu điểm |
| Hai advice đồng priority | Có tie-break được phê duyệt hoặc fail fast |
| Ràng buộc precedence có chu trình | Phát hiện và báo cấu hình không hợp lệ |
| Đổi thứ tự dựng proxy | Kết quả theo đúng thuật toán bọc |
| Recompile/reweave/redeploy | Artifact/runtime dùng precedence mới |
| Direct-call và self-invocation | Biết phạm vi proxy có chặn hay không |
| Concurrent invocations | State aspect không race, thứ tự cục bộ mỗi call hợp lệ |
| Async return | Phân biệt return của handle với completion thực tế |
| Log/metrics/audit | Không ghi dữ liệu nhạy cảm và không đếm sai phạm vi |

### 14.1 Test thứ tự bằng danh sách sự kiện

Trong bài test đồng bộ, dùng một danh sách event thay vì nhìn log không bảo đảm đồng bộ:

~~~text
expected_success:
  AUTH.before
  TX.begin
  METRIC.start
  business
  METRIC.end
  TX.commit
  AUTH.after
~~~

Đây là **expected trace minh họa một cấu trúc cụ thể**, không phải thứ tự mặc định của mọi AOP. Với nhiều thread, không kiểm tra một tổng thứ tự log toàn hệ thống nếu hợp đồng chỉ yêu cầu thứ tự **trong mỗi invocation**; dùng correlation ID và assert từng chuỗi riêng.

### 14.2 Test phủ định cần thiết

Không chỉ chứng minh điều **phải xảy ra**, mà còn điều **không được xảy ra**:
- Không có business side effect sau `AUTH DENY`.
- Không trả cached private data nếu không kiểm tra quyền.
- Không commit khi transaction phải rollback.
- Không phát audit "SUCCESS" cho một attempt lỗi.
- Không lặp ghi tiền do retry.
- Không ghi token/secret vào log từ arguments.
- Không có advice lặp hai lần vì overlap sai.
- Không có một precedence tùy hứng khi các rule xung đột.

## 15. Chẩn đoán khi thứ tự thực tế khác mong muốn

Hãy đi từ **cấu trúc** tới **hành vi**:

1. Xác minh runtime đang dùng **artifact, proxy hoặc aspect config phiên bản nào**.
2. Xác minh **loại join point** đang xét: call, execution hay loại công cụ hỗ trợ.
3. Liệt kê **pointcut nào thật sự match**, không chỉ pointcut dự kiến.
4. Liệt kê **advice type** và các rule precedence/tie-break.
5. Xem **effective interceptor chain** sau khi resolve, nếu nền tảng cung cấp.
6. Đặt dấu vết an toàn cho **entry, proceed, exit, throw và finally**.
7. Kiểm tra có lớp nào return trước, cache hit, deny, fallback hoặc retry không.
8. Đối chiếu **kết quả cuối và side effects** với hợp đồng nghiệp vụ.
9. So sánh đường success, error, async và direct/proxy call.
10. Ghi regression test cho từng ràng buộc bắt buộc.

Một trace trông “ngược” có thể là đúng: around ngoài chạy BEFORE trước nhưng AFTER sau. Đừng sửa cấu hình chỉ để đảo thứ tự vài dòng log nếu như vậy làm phá nghĩa vụ bảo mật.

## 16. Các ngộ nhận thường gặp

1. **“Aspect được biên dịch trước có precedence cao hơn.”** Không có quy tắc chung như vậy.
2. **“Priority số nhỏ luôn trước.”** Quy ước số phụ thuộc nền tảng, cần đọc hợp đồng.
3. **“Một join point khớp nhiều aspect thì tất cả chắc chắn chạy.”** Around ngoài có thể short-circuit.
4. **“Thứ tự after giống thứ tự before.”** Trong wrapper lồng nhau, thường đi ra theo hướng ngược.
5. **“Equal priority thì không sao, Java luôn giữ thứ tự khai báo.”** Không có bảo đảm chung của AOP.
6. **“Đổi precedence sửa được pointcut match sai.”** Selection và composition khác nhau.
7. **“Audit nằm trong Auth vẫn thấy mọi lần bị từ chối.”** Không nếu Auth trả/throw trước khi gọi tiếp.
8. **“Cache và Auth có thể đảo tùy ý.”** Cache hit ở ngoài có thể bypass Auth bên trong.
9. **“Retry và Transaction luôn giao hoán.”** Có thể thay đổi ranh giới giao dịch và side effects.
10. **“ExceptionTranslator trả fallback không ảnh hưởng rollback.”** Có thể che tín hiệu lỗi.
11. **“Mọi advice chỉ đọc đều không có xung đột.”** Thứ tự log/metric, số lần và việc thu thập dữ liệu vẫn có thể khác.
12. **“Một priority chung giải quyết mọi chiều phụ thuộc.”** Có thể cần graph ràng buộc hoặc sửa kiến trúc.
13. **“Có cycle thì chọn ngẫu nhiên một thứ tự vẫn chạy được.”** Nó không thỏa tất cả bất biến.
14. **“Đảo file aspect có nghĩa đảo runtime advice order.”** Tùy mô hình weaving, không được suy.
15. **“Proxy có precedence đúng thì mọi đường gọi đều chịu advice.”** Direct target/self-invocation có thể bypass.
16. **“Trace không thấy advice nghĩa advice không match.”** Log sampling, short-circuit hoặc đường gọi khác cũng có thể gây ra.
17. **“Thứ tự trong một aspect giống thứ tự giữa các aspect.”** Cần kiểm tra quy tắc riêng.
18. **“Priority cao đồng nghĩa an toàn.”** Chỉ một thứ tự thỏa các bất biến cụ thể mới có ý nghĩa.

## 17. Checklist thiết kế quy tắc phân xử

Trước khi chốt cấu hình nhiều aspect:

- [ ] Xác định chính xác **tập join point** của từng aspect; loại bỏ overlap không chủ ý.
- [ ] Phân loại **advice type**: before, after-returning, after-throwing, finally, around.
- [ ] Xác định advice nào có thể **không proceed**, retry, sửa args/result hoặc chuyển exception.
- [ ] Viết các **bất biến bảo mật, transaction, audit và side effects** bằng ngôn ngữ kiểm chứng được.
- [ ] Biểu diễn ràng buộc thứ tự theo quan hệ **must precede / must surround**, không chỉ đặt số.
- [ ] Xác định **quy ước số priority** nếu công cụ dùng số: hướng tăng/giảm, ý nghĩa outer.
- [ ] Giải quyết equal priorities bằng policy được phê duyệt hoặc fail fast.
- [ ] Phát hiện **chu trình** ràng buộc và báo lỗi sớm.
- [ ] Đảm bảo cấu trúc đáp ứng cả nhánh **success/error/short-circuit/cache-hit**.
- [ ] Xác minh **effective chain** khi dùng proxy và tập điểm khi dùng bytecode weaving.
- [ ] Kiểm tra **direct/self calls** và các điểm không được instrument.
- [ ] Phân biệt request-level, attempt-level và target-level metrics.
- [ ] Giữ log/tracing/audit theo nguyên tắc **ít dữ liệu nhất**.
- [ ] Viết regression tests cho order, outcome, rollback, idempotency và cleanup.
- [ ] Pin version công cụ/cấu hình nếu build/reweave có thể đổi rule precedence.
- [ ] Có quy trình rollback khi thay đổi priority tác động nghiệp vụ.

## 18. Bài tập ôn tập

**Câu 1.** Có `A(B(Business))`. Khi cả A và B là around advice chuyển tiếp một lần, lớp nào chạy phần before trước và phần after sau?

**Đáp:** A.before chạy trước B.before; khi quay về bình thường, B.after chạy trước A.after. Không được đọc tên A/B rồi suy cùng thứ tự cho mọi loại advice trong công cụ khác.

**Câu 2.** Cache ngoài Authorization và cache hit không proceed. Authorization bên trong có chạy không?

**Đáp:** không qua đường này. Nếu dữ liệu cần bảo vệ, phải đưa kiểm tra quyền ra ranh giới không thể bypass hoặc có cơ chế kiểm tra tương đương đáng tin.

**Câu 3.** Hai aspect cùng priority và đều tác động đến kết quả. Có thể dùng thứ tự tên lớp làm tie-break không?

**Đáp:** chỉ khi đó là policy tường minh, được phê duyệt và chứng minh giữ hợp đồng. Với bất biến bắt buộc, nên yêu cầu thứ tự rõ hoặc fail fast.

**Câu 4.** A phải ngoài B, B ngoài C, C ngoài A. Có sắp được không?

**Đáp:** không; đồ thị có chu trình. Cần sửa các ràng buộc/kiến trúc chứ không bỏ ngẫu nhiên một cạnh.

**Câu 5.** Vì sao `Retry(Transaction(Business))` có thể khác `Transaction(Retry(Business))`?

**Đáp:** ranh giới transaction có thể được tạo cho mỗi attempt hoặc bao nhiều attempts; điều này ảnh hưởng rollback, retry side effects và idempotency. Cần test theo implementation thực tế.

**Câu 6.** Tracing đặt trong Cache, cache hit trả sớm. Metric đo toàn bộ request có đủ không?

**Đáp:** không. Tracing bên trong không thấy cache hit; nếu cần request-level latency, phải đặt span ngoài cache hoặc có kênh đo tương đương.

**Câu 7.** Một ErrorTranslator nuốt lỗi bên trong Transaction và trả success. Nguy cơ gì?

**Đáp:** Transaction có thể xem execution đã thành công và commit khi đáng lẽ rollback. Kết quả còn tùy policy transaction cụ thể, nên cần kiểm chứng lỗi/rollback.

**Câu 8.** Pointcut chọn quá rộng làm advice chạy hai lần. Có thể sửa chỉ bằng precedence không?

**Đáp:** không chắc. Cần phân tích overlap, loại join point, generated/bridge methods và số layer instrument; sửa selection hoặc loại lặp đúng chỗ.

## 19. Kết luận

**Phối hợp nhiều aspect** không chỉ là gom các advice vào cùng join point. Ta phải phân xử **ai được vào trước, ai bao ai, ai có quyền dừng continuation, ai quan sát success/error, và bất biến nào bắt buộc đúng ở mọi đường đi**.

Bốn ý quan trọng:

1. **Precedence là quan hệ ngữ nghĩa**; số priority và thứ tự tệp chỉ có ý nghĩa nếu cơ chế AOP định nghĩa rõ.
2. **Around nesting có hai chiều vào/ra**, nên “ưu tiên cao hơn” không đồng nghĩa chạy cả before lẫn after trước.
3. **Xung đột phải được phân loại**: overlap pointcut, biến đổi dữ liệu/kết quả, ngoại lệ, state, short-circuit, security, transaction và audit.
4. **Phân xử phải kiểm chứng được**: khai báo các ràng buộc, xử lý tie/cycle, fail fast khi không an toàn và test nhánh thành công/lỗi/cache-hit/retry cùng tác dụng phụ.

**Ghi nhớ:** thứ tự aspect đúng là thứ tự bảo toàn **hợp đồng của chương trình**, không phải thứ tự khiến vài dòng log trông thuận mắt.
