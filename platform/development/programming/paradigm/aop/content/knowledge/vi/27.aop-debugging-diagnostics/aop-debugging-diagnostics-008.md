# Chẩn đoán đệ quy, advice chạy nhiều lần hoặc sai thứ tự trong Aspect-Oriented Programming (AOP)

## 1. Vấn đề cần hiểu

Trong AOP, một `aspect` đóng gói hành vi cắt ngang (ghi log, kiểm tra quyền, đo thời gian, audit...), một `pointcut` chọn những `join point` cần tác động, còn `advice` là đoạn xử lý được thực thi trước, sau hoặc bao quanh join point đó. Cơ chế áp dụng advice có thể là weaving vào bytecode, biên dịch có weaving, nạp lớp có weaving, hoặc một tầng interception khác. Vì thế, số lần một phương thức nghiệp vụ được gọi **không nhất thiết bằng** số lần một advice chạy.

Ba nhóm triệu chứng thường bị lẫn với nhau:

- **Đệ quy hoặc tái nhập (recursion/reentrancy):** advice hoặc phương thức được advice gọi tiếp một đường thực thi lại khớp pointcut, tạo vòng lặp hoặc lời gọi lồng nhau không mong muốn.
- **Advice chạy nhiều lần:** một tác vụ nhìn từ bên ngoài chỉ xảy ra một lần, nhưng có nhiều join point phù hợp, nhiều advice cùng khớp, advice gọi `proceed` nhiều lần, hoặc có cơ chế gọi lại.
- **Advice sai thứ tự:** thứ tự trước/sau của các aspect khác dự kiến do precedence, nesting của `around`, dạng `before`/`after`, ngoại lệ, hoặc phụ thuộc vào thứ tự không được bảo đảm.

Mục tiêu chẩn đoán là tìm **join point nào đã khớp, advice nào chạy, vì sao chạy và quan hệ gọi lồng nhau giữa chúng**. Không vội kết luận lỗi chỉ từ việc xuất hiện hai dòng log giống nhau.

## 2. Mô hình thực thi để đọc đúng dấu vết

Các thành phần phải phân biệt:

| Thành phần | Câu hỏi chẩn đoán |
| --- | --- |
| Join point | Sự kiện thực thi nào được quan sát: gọi hàm (`call`), thực thi hàm (`execution`), khởi tạo đối tượng, truy cập trường...? |
| Pointcut | Biểu thức nào chọn sự kiện đó, ở phạm vi lớp/gói/phương thức nào? |
| Advice | `before`, `after`, `after returning`, `after throwing` hay `around`? Có bao nhiêu khai báo áp dụng? |
| Weaving/interception | Mã bị tác động tại vị trí gọi hay vị trí thực thi? Những lớp nào thực sự được instrument/weave? |
| Control flow | Có lời gọi lồng, gọi lại, vòng lặp, callback hoặc chuyển luồng không? |
| Precedence | Nếu nhiều advice cùng áp dụng, quy tắc nào xác lập thứ tự bao ngoài và bên trong? |

Ví dụ một vòng `around` lồng nhau với thứ tự ngoài là Trace, trong là Guard:

```text
Trace.before
  Guard.before
    Target.execute
  Guard.after
Trace.after
```

Các dòng `after` xuất hiện **ngược thứ tự** `before` là hành vi đúng của cơ chế stack/unwind, không phải dấu hiệu advice sắp xếp sai. Nếu `Target.execute` ném ngoại lệ, chỉ các khối `finally` hoặc advice loại phù hợp mới nhất thiết hoàn tất; `after returning` không chạy trên đường ngoại lệ.

Đặc biệt với AOP có join point `call` và `execution`: một lời gọi thông thường có thể kích hoạt cả advice bắt sự kiện gọi ở caller **và** advice bắt sự kiện chạy thân phương thức ở callee. Đây là hai join point khác nhau dù cùng tên phương thức. Cần kiểm tra code ở cả hai phía có được weave hay không.

## 3. Chẩn đoán đệ quy hoặc advice tái nhập

### 3.1. Advice gọi hàm phụ nhưng hàm phụ lại khớp pointcut

Mẫu điển hình: pointcut bắt mọi phương thức trong `demo.service`; advice gọi `AuditService.record` nằm trong chính phạm vi đó.

```java
// Ví dụ cú pháp AspectJ để phân tích; cần toolchain hỗ trợ weaving,
// không phải một tệp Java biên dịch độc lập bằng javac.
public aspect BroadAuditAspect {
    before(): execution(* demo.service..*.*(..)) {
        demo.service.AuditService.record("entered");
    }
}
```

Nếu `AuditService.record` cũng khớp `execution(* demo.service..*.*(..))` thì luồng có thể là:

```text
PaymentService.pay
  -> BroadAuditAspect.before
       -> AuditService.record
            -> BroadAuditAspect.before
                 -> AuditService.record
                      -> ... (StackOverflowError)
```

Dấu hiệu: stack trace xen kẽ frame của advice và hàm phụ; cùng một signature xuất hiện nhiều lần, độ sâu tăng liên tục; số dòng log tăng đột biến.

**Cách sửa gốc:** thu hẹp pointcut theo đúng nghiệp vụ, đặt logger/audit sink ngoài vùng bị bắt, hoặc loại trừ rõ vùng hạ tầng. Chẳng hạn:

```java
public aspect NarrowAuditAspect {
    before(): execution(* demo.service.PaymentService.pay(..)) {
        System.out.println("payment entered");
    }
}
```

Một điều kiện loại trừ hợp lý khi vẫn cần pointcut rộng:

```java
pointcut tracked():
    execution(* demo.service..*.*(..))
    && !within(demo.service.AuditService);
```

`within(T)` xét **vị trí khai báo (lexical)** của join point; nó hữu ích để bỏ thực thi nằm trong lớp `T`. Nhưng `!within(MyAspect)` **không đủ** để chặn lời gọi từ advice đi vào một phương thức của lớp nghiệp vụ khác rồi quay lại pointcut: thực thi phương thức nghiệp vụ ấy vẫn được khai báo ngoài aspect.

### 3.2. Đệ quy do logic nghiệp vụ, advice chỉ ghi nhận

Có trường hợp `A.f()` gọi lại `A.f()` hoặc hai hàm `A.f() → B.g() → A.f()`. Advice trước mỗi lần `execution` sẽ chạy đúng một lần cho **mỗi mức đệ quy**. Không sửa bằng cách tắt advice nếu lỗi thực sự ở điều kiện dừng hoặc chu trình gọi của nghiệp vụ.

Cách nhận diện: stack trace chủ yếu lặp lại hàm nghiệp vụ; khi vô hiệu hóa advice quan sát, vòng gọi vẫn tồn tại. Đếm riêng số **lần vào join point** và số **lần chạy advice** để tránh quy trách nhiệm nhầm.

### 3.3. Ngăn ghi log lồng nhau bằng control-flow pointcut

Khi mục đích chỉ là đo một tác vụ cấp ngoài, có thể loại sự kiện nằm **bên dưới** một execution đã khớp:

```java
public aspect OutermostTraceAspect {
    pointcut task():
        execution(* demo.service.PaymentService.pay(..));

    before(): task() && !cflowbelow(task()) {
        System.out.println("outermost payment");
    }
}
```

`cflowbelow(task())` nhận diện join point trong luồng thực thi động bên dưới một `task()` đã hoạt động. Phủ định nó chỉ ghi nhận lần vào ngoài cùng trong cùng control flow. Đổi lại, các lời gọi lồng nhau có chủ đích sẽ bị bỏ khỏi log. Đây là biện pháp **lọc quan sát**, không tự chữa vòng đệ quy nghiệp vụ hay vòng advice gọi helper. `cflow` và `cflowbelow` phụ thuộc vào đặc tính runtime của công cụ AOP đang dùng; xác nhận công cụ hỗ trợ trước khi áp dụng.

### 3.4. Reentrancy guard bằng trạng thái theo luồng

Trong một interception tùy biến, có thể tránh việc chính hoạt động logging kích hoạt lại logging bằng guard theo thread, với `try/finally` bắt buộc để giải phóng cờ. Ví dụ Java 17 sau **chạy độc lập**, mô phỏng wrapper advice (không phải ví dụ weaving):

```java
public final class ReentryGuardDemo {
    private static final ThreadLocal<Boolean> ACTIVE =
            ThreadLocal.withInitial(() -> false);

    static void advised(Runnable action) {
        if (ACTIVE.get()) {
            action.run(); // Vẫn cho hành vi nghiệp vụ tiếp tục.
            return;
        }

        ACTIVE.set(true);
        try {
            System.out.println("enter");
            action.run();
        } finally {
            System.out.println("exit");
            ACTIVE.remove();
        }
    }

    static void audit() {
        advised(() -> System.out.println("audit"));
    }

    public static void main(String[] args) {
        advised(() -> {
            System.out.println("work");
            audit();
        });
    }
}
```

Chạy:

```bash
javac ReentryGuardDemo.java
java ReentryGuardDemo
```

```text
enter
work
audit
exit
```

Guard này chặn **wrapper logging lặp lại trong cùng thread**, không chặn `action.run()` tự gọi đệ quy vô hạn; muốn chữa lỗi đó phải sửa call graph và điều kiện dừng. Luôn `remove()` trong `finally` để không giữ cờ trên thread được tái sử dụng. Không coi `ThreadLocal` là cơ chế lan truyền ngữ cảnh qua tác vụ bất đồng bộ: công việc trên thread khác có trạng thái riêng, cần một chính sách truyền context rõ ràng.

## 4. Vì sao advice chạy nhiều lần?

| Nguyên nhân | Quan sát điển hình | Kiểm tra và hướng xử lý |
| --- | --- | --- |
| Một request đi qua nhiều join point | Một request ID, nhiều signature hoặc nhiều tầng delegate | Ghi rõ signature và depth; chỉ bắt tầng cần đo |
| `call` và `execution` cùng được bắt | Cùng hành vi nhưng event kind khác | Kiểm tra loại join point và vị trí weave; chọn event phù hợp |
| Nhiều aspect/advice khớp một join point | Cùng signature, khác advice/aspect ID | Liệt kê advice và pointcut; tách trách nhiệm hoặc đặt precedence |
| Advice `around` gọi `proceed()` nhiều lần | Target chạy hai lần từ cùng một advice invocation | Đếm số `proceed()`, kiểm tra retry và nhánh điều kiện |
| Có retry, callback, listener, vòng lặp hoặc lời gọi lồng | Join point thực sự bị gọi lặp | Theo dõi từng attempt, phân biệt request ID và invocation ID |
| Weaving/interception được đăng ký hoặc áp dụng lặp | Trace xuất hiện nhiều lớp wrapper giống nhau | Kiểm tra cấu hình build, agent, classloader và điểm instrument |
| Hàm được biên dịch thành nhiều đường gọi (ví dụ bridge/delegation) | Khác signature descriptor, tên gần giống | Kiểm tra bytecode/signature, test theo join point thực thay vì tên hiển thị |

**Điểm mấu chốt của `around`:** nhiều API AOP cho phép advice quyết định có tiếp tục vào mục tiêu hay không; gọi `proceed` hai lần có thể cố ý thực thi lại nghiệp vụ, kèm hai lần side effect. Trong chính sách retry, phải kiểm tra idempotency và chỉ retry ở trường hợp được cho phép. Nếu không có chủ đích retry, `proceed` thường chỉ được gọi một lần trên nhánh thành công.

Không suy luận rằng hai log trùng nhau chứng minh cùng một advice chạy hai lần. Một advice có thể ghi log lúc vào và lúc ra; hai instance aspect cũng có thể in nội dung giống nhau; hệ thống log có thể có hai appender. Cần thêm nhãn `phase`, `aspect`, `advice`, `event-kind`, `invocation-id` và số thứ tự sự kiện để phân biệt.

## 5. Vì sao thứ tự advice không như dự kiến?

### 5.1. Precedence và nesting

Khi nhiều aspect cùng áp dụng tại một join point, thứ tự không nên suy ra từ tên class, thứ tự khởi tạo, hay vị trí file trong dự án. Trong AOP kiểu AspectJ, có thể khai báo precedence tường minh (mảnh cú pháp sau đặt trong một `aspect`):

```java
declare precedence: SecurityAspect, TraceAspect, MetricsAspect;
```

Theo thứ tự này, aspect có precedence cao hơn được áp dụng như lớp bao ngoài: `before` của nó chạy sớm hơn; phần kết thúc của `after`/`around` xảy ra muộn hơn khi unwinding. Không nhầm “Trace trước Metrics” ở đầu vào với “Trace trước Metrics” cả lúc thoát.

Nếu công cụ AOP khác không hỗ trợ `declare precedence`, cần dùng cơ chế ordering/priority được nó công bố và viết phép thử về thứ tự thực thi. Khi không có quy tắc xác định, thứ tự giữa các aspect độc lập có thể không được bảo đảm; không dựa vào thứ tự vô tình thấy trong một lần chạy.

### 5.2. Ví dụ Java 17 về thứ tự `around`

Chương trình độc lập sau mô phỏng chuỗi advice lồng nhau; nó minh họa nguyên lý thứ tự mà không cần thư viện AOP:

```java
public final class AdviceOrderDemo {
    interface Action {
        void run();
    }

    static Action around(String name, Action next) {
        return () -> {
            System.out.println(name + " before");
            try {
                next.run();
            } finally {
                System.out.println(name + " after");
            }
        };
    }

    public static void main(String[] args) {
        Action target = () -> System.out.println("business");
        Action chain = around("Trace", around("Guard", target));
        chain.run();
    }
}
```

Chạy:

```bash
javac AdviceOrderDemo.java
java AdviceOrderDemo
```

```text
Trace before
Guard before
business
Guard after
Trace after
```

Giải thích: `Trace` bao ngoài `Guard`, nên “before” đi từ ngoài vào trong, còn `finally` chạy khi stack trở ra. Nếu phát hiện “after” ngược “before”, trước tiên hãy so với mô hình nesting này.

### 5.3. Advice sau, ngoại lệ, và tác động của `around`

- `before`: chạy trước join point; nếu nó ném ngoại lệ, mục tiêu có thể không được thực thi.
- `after returning`: chỉ chạy khi join point kết thúc bình thường; không dùng để bảo đảm dọn tài nguyên sau lỗi.
- `after throwing`: chạy khi join point kết thúc bằng ngoại lệ thuộc kiểu được bắt.
- `after` (kiểu finally): áp dụng khi join point thoát bình thường hoặc bất thường.
- `around`: có thể bao quanh, bắt/chuyển ngoại lệ, không gọi `proceed`, hoặc gọi nhiều lần; do đó quyết định cả số lần vào mục tiêu và phần advice nào được tới.

Trên đường ngoại lệ, một log “end” đặt sau `proceed()` mà không ở `finally` có thể biến mất. Đây là nhánh thực thi khác, chưa đủ chứng minh “sai thứ tự”. Cần phân tích cả thứ tự trên đường thành công và trên đường lỗi.

### 5.4. Trường hợp nhiều advice nằm trong cùng aspect

Thứ tự tương đối có thể chịu quy tắc riêng của ngôn ngữ/weaver, bao gồm loại advice và vị trí khai báo. Khi nghiệp vụ yêu cầu một thứ tự bắt buộc, tránh dựa vào những chi tiết dễ thay đổi: gom thao tác phụ thuộc nhau vào một `around` với cấu trúc `try/finally` rõ ràng, hoặc tách thành các aspect có precedence được khai báo và kiểm chứng bằng test.

## 6. Quy trình chẩn đoán có thể lặp lại

1. **Cố định ca tái hiện.** Ghi input, số lần gọi dự kiến, đường thành công/thất bại, số thread và cấu hình weaving. Tắt retry ngoài ý muốn trong phép thử cơ sở nếu có quyền kiểm soát.
2. **Phân biệt các mức đếm.** Ghi `requestId` cho tác vụ ngoài, `invocationId` cho từng lần vào join point, `adviceId` cho từng advice, `thread` và `depth` cho nesting. Một request có thể hợp lệ chứa nhiều invocation.
3. **Lấy dấu vết ít can thiệp.** Ghi signature tĩnh (loại lớp, tên phương thức, event kind), advice name, phase và timestamp/sequence. Tránh gọi `toString()` tùy ý lên tham số: nó có thể gây side effect hoặc lại khớp pointcut.
4. **Dựng call graph.** Nếu cùng ID có độ sâu tăng mãi, lần theo chu kỳ `advice → helper → join point → advice` hay chu kỳ nghiệp vụ. Nếu depth không tăng mà invocation tăng, ưu tiên xem vòng lặp, retry, callback, `proceed` lặp hoặc nhiều request.
5. **Liệt kê điểm khớp thực tế.** So từng advice với pointcut của nó: `execution` hay `call`, package/type pattern, `within`/`withincode`, điều kiện tham số, control flow, cấu hình weave. Đừng chỉ đọc tên phương thức in trên log.
6. **Kiểm tra thứ tự xác định.** Vẽ các wrapper `around`; xác nhận precedence và thứ tự `before`/`after`. Thử ít nhất một nhánh thành công và một nhánh ném ngoại lệ.
7. **Thử sửa tối thiểu.** Thu hẹp pointcut, loại trừ helper hoặc điều chỉnh precedence; so số invocation và side effect trước/sau. Nếu sửa lỗi đệ quy, xác nhận logic nghiệp vụ hoàn tất đúng.
8. **Bật lại điều kiện thực tế.** Thử tải đồng thời, callback bất đồng bộ, retry chủ đích và cùng phiên bản weaving khi chạy thật. Ghi nhận khác biệt thread/classloader nếu có.

Một dạng trace hữu ích:

```text
seq=01 req=R7 inv=I1 depth=0 thread=T1 event=execution:PaymentService.pay aspect=Trace advice=around phase=enter
seq=02 req=R7 inv=I1 depth=0 thread=T1 event=execution:PaymentService.pay aspect=Guard advice=around phase=enter
seq=03 req=R7 inv=I2 depth=1 thread=T1 event=execution:AuditService.record aspect=Trace advice=before phase=enter
seq=04 req=R7 inv=I1 depth=0 thread=T1 event=execution:PaymentService.pay aspect=Guard advice=around phase=exit
seq=05 req=R7 inv=I1 depth=0 thread=T1 event=execution:PaymentService.pay aspect=Trace advice=around phase=exit
```

Các dòng chỉ minh họa **định dạng dấu vết**, không phải output của mã Java bên trên. `I2` giúp nhận ra một join point khác xuất hiện bên trong `I1`. Nếu liên tục xuất hiện `I3`, `I4`,... ở depth tăng, cần điều tra tái nhập. Nếu `I1` xuất hiện với hai `aspect` ở cùng depth, đó có thể chỉ là nhiều advice hợp lệ.

## 7. Chẩn đoán sâu theo cơ chế AOP

### 7.1. Vị trí weave và định nghĩa join point

- Với `execution`, advice chạy tại việc **thực thi thân phương thức**; mọi nơi gọi vào cùng thân được weave đều có thể quan sát.
- Với `call`, advice gắn vào **vị trí lệnh gọi**; caller không được weave thì sự kiện call ở caller đó sẽ không bị advice quan sát.
- Một lớp được instrument từ nhiều tầng, hoặc đoạn gọi qua decorator/delegate, có thể tạo các wrapper lồng nhau. Cần đối chiếu class thực tế, classloader và điểm instrument.
- Những phương thức cầu nối (bridge), overload, hàm sinh bởi compiler hay chuyển tiếp nội bộ có thể làm số event lớn hơn trực giác. Không “dedupe” bằng tên phương thức đơn thuần; so đầy đủ signature và event kind.

Với weaving trực tiếp vào bytecode, lời gọi nội bộ từ một phương thức sang phương thức khác vẫn có thể gặp join point `execution` của phương thức đích nếu đã weave. Với các mô hình interception chỉ chặn ở biên lời gọi, lời gọi nội bộ có thể không đi qua interceptor. Phải xác định **cơ chế đang dùng** thay vì áp dụng một quy tắc chung cho mọi AOP.

### 7.2. Đa luồng và bất đồng bộ

Sự kiện hoàn tất trên thread khác có thể xen vào trace của thread đầu tiên. Timestamp một mình không mô tả thứ tự nhân quả giữa hai thread. Nên có correlation ID được truyền chủ động và sequence theo mỗi invocation; nếu cần xác lập thứ tự xuyên thread, theo dõi sự kiện schedule/start/complete hoặc quan hệ parent/child.

Guard theo `ThreadLocal` chỉ chặn tái nhập trong thread hiện tại. Không dùng nó để bảo đảm duy nhất một lần trên toàn request phân tán qua nhiều thread. Những đường chạy dùng async, callback hoặc executor đòi hỏi chính sách truyền context và ranh giới scope riêng.

### 7.3. Khi điều tra StackOverflowError

Lấy stack trace đầy đủ khi có thể; tìm đoạn frame lặp ngắn nhất. Nếu có helper logging/audit trong chu kỳ, tạm thay nó bằng xuất dữ liệu tối thiểu không gây side effect để cô lập vòng. Tránh thêm log trên mọi lời gọi khi lỗi nặng: chính instrumentation mới có thể làm tràn stack sớm hơn hoặc tạo vòng mới. Đối với tiến trình thật, giới hạn sampling và kích thước log, tái hiện trong môi trường có kiểm soát trước khi thay đổi pointcut.

## 8. Chiến lược sửa theo đúng nguyên nhân

| Nguyên nhân đã xác nhận | Sửa ưu tiên | Kiểm tra sau sửa |
| --- | --- | --- |
| Advice gọi helper nằm trong pointcut | Thu hẹp pointcut; loại trừ helper hoặc chuyển sink ra ngoài phạm vi | Một nghiệp vụ tạo số event mong muốn; không có frame lặp |
| Đệ quy nghiệp vụ thật | Sửa điều kiện dừng hoặc chu trình phụ thuộc | Nghiệp vụ có kết quả đúng, không còn đệ quy vô hạn |
| Quan sát cả `call` lẫn `execution` | Chọn join point đúng nhu cầu hoặc phân biệt hai nguồn đếm | Số lần ghi tương ứng với định nghĩa metric |
| `around` gọi `proceed` lặp | Chỉ gọi đúng số lần cần thiết; tách retry có kiểm soát | Side effect không nhân đôi ngoài thiết kế |
| Nhiều advice thiếu thứ tự | Khai báo precedence hoặc một pipeline rõ thứ tự | Trace vào/ra đúng nesting trên cả success và exception |
| Dọn dẹp sai nhánh ngoại lệ | Dùng `finally` hoặc advice tương ứng | Resource cleanup xuất hiện ở cả hai nhánh |
| Interception/weaving bị lặp | Sửa vị trí cấu hình/đăng ký và vòng build/load | Một lớp chỉ được gắn số interceptor dự kiến |
| Async làm mất correlation | Truyền context rõ qua task boundary | Trace ghép đúng request và invocation |

Tránh cách “sửa” bằng cách xóa toàn bộ aspect quan sát, bỏ qua mọi lần gọi lồng nhau hoặc dùng biến `static boolean` chung cho toàn tiến trình: các cách này dễ che lỗi thật và khiến concurrent request ảnh hưởng lẫn nhau. Guard chỉ dành cho thao tác có nguy cơ tái nhập, phải có scope rõ và giải phóng trong `finally`.

## 9. Phép thử xác nhận

Nên kiểm thử đủ các trường hợp sau, với kỳ vọng mô tả bằng số lượng **join point**, **lần chạy từng advice**, **lần thực thi nghiệp vụ** và thứ tự sự kiện:

1. **Một lời gọi thành công, không lồng:** mỗi advice khớp một lần theo định nghĩa, `around` bao ngoài đúng thứ tự, một side effect.
2. **Một lời gọi ném ngoại lệ:** xác định advice nào được phép chạy; `finally` vẫn dọn tài nguyên, lỗi không bị vô tình nuốt.
3. **Lời gọi lồng có chủ đích:** quyết định có đo cả cấp con hay chỉ cấp ngoài; bảo đảm lọc `cflowbelow` phù hợp kỳ vọng.
4. **Helper/audit gọi từ advice:** không tạo chu kỳ tái nhập; audit vẫn thực hiện đúng một lần theo thiết kế.
5. **Nhiều aspect cùng khớp:** thứ tự được kiểm chứng trên cả pha enter/exit, không dựa vào một lần quan sát ngẫu nhiên.
6. **Retry có chủ đích:** tổng số attempt và side effect đúng contract; `proceed` lặp chỉ khi chính sách cho phép.
7. **Nhiều thread hoặc async:** trace giữ đúng correlation, guard không rò rỉ và không làm ảnh hưởng request khác.
8. **Chạy với cấu hình weave thật:** kết quả test phản ánh đúng call/execution, classloader và phạm vi instrumentation khi triển khai.

## 10. Những lỗi suy luận phổ biến

- “Một request chỉ được gọi phương thức một lần, vậy advice chỉ được chạy một lần.” Sai khi request chứa nhiều join point, lời gọi lồng, retry hoặc nhiều advice.
- “Advice `after` in ra ngược `before` chứng tỏ sai precedence.” Sai nếu đó là thứ tự stack unwind của các wrapper lồng nhau.
- “Thêm `!within(AspectName)` luôn chữa đệ quy.” Không đúng nếu advice gọi **phương thức khác** vẫn nằm trong phạm vi pointcut.
- “Dùng `!cflowbelow(...)` là hết lỗi đệ quy.” Nó có thể chỉ ẩn các sự kiện con; vòng gọi nghiệp vụ vẫn tiếp diễn.
- “Bỏ `finally` không sao vì đã có log sau `proceed`.” Khi có ngoại lệ, code sau `proceed` có thể không chạy.
- “ThreadLocal là một cờ cho cả request.” Nó gắn với thread, không tự lan qua thread khác.
- “Tên phương thức giống nhau là cùng join point.” Phải xem event kind, signature, lớp khai báo và vị trí weave.
- “Cứ có hai log là bị weave hai lần.” Cần loại trừ appender trùng, hai advice khác nhau và logging ở cả enter/exit trước.

## 11. Checklist kết thúc điều tra

- [ ] Đã xác định chính xác pointcut, join point kind, signature và tất cả advice khớp.
- [ ] Đã dựng quan hệ `caller → advice → helper → target` và đánh dấu chỗ tái nhập hoặc lặp.
- [ ] Đã phân biệt lời gọi nghiệp vụ thật, `proceed`, retry, lời gọi lồng và nhiều aspect.
- [ ] Đã xác nhận precedence, thứ tự nesting và hành vi khi ném ngoại lệ.
- [ ] Đã sửa nguyên nhân gốc: phạm vi match, call graph, guard/scope hoặc cấu hình weaving.
- [ ] Đã kiểm chứng số lần chạy và side effect trên đường thành công, thất bại, concurrent và async nếu có.
- [ ] Đã bảo đảm công cụ chẩn đoán tự nó không tạo vòng gọi hoặc làm thay đổi đáng kể hành vi đang quan sát.

**Nguyên tắc cốt lõi:** luôn đối chiếu “một lần chạy advice” với **join point cụ thể và chuỗi điều khiển thực tế**, sau đó sửa đúng điểm gây tái nhập, nhân đôi hoặc thứ tự không xác định.