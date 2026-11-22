# Mã đã dệt, thông tin gỡ lỗi và khả năng truy vết trong kiến trúc AOP

## 1. Mục tiêu: nhìn thấy điều gì sau khi weaving?

Trong **Aspect-Oriented Programming (AOP)**, ứng dụng được tổ chức thành mã xử lý nghiệp vụ và những hành vi xuyên suốt (logging, kiểm toán, đo thời gian, chính sách truy cập...). Một **aspect** mô-đun hóa hành vi xuyên suốt; **pointcut** chọn các **join point**; **advice** là mã được áp dụng tại những điểm đó. **Weaving** là quá trình kết hợp các hành vi thành một đường thực thi có hiệu lực.

Khi gỡ lỗi, ta cần phân biệt ít nhất ba hình ảnh của cùng một thao tác:

1. **Mã nguồn người lập trình viết**: phương thức nghiệp vụ và các khai báo aspect/advice.
2. **Mã hoặc đường thực thi đã được kết hợp**: chỉ thị, phương thức cầu nối, interceptor hoặc proxy được công cụ tạo/sử dụng để gọi advice.
3. **Những gì debugger và hệ thống quan sát nhìn thấy khi chạy**: stack frame, vị trí nguồn, sự kiện, ngoại lệ, trace ID, thời lượng và đường gọi thực tế.

Ba hình ảnh đó có thể liên quan nhưng **không phải lúc nào cũng trùng một-một**. Một breakpoint trong mã nghiệp vụ có thể dừng sau khi advice trước đã chạy; stack trace có thể chứa frame trung gian; một phương thức mới sinh có thể không có dòng Java tương ứng; hoặc một bộ dệt có thể thay bytecode ngay khi nạp mà không tạo tệp “mã đã dệt” trên ổ đĩa.

Bài này giúp trả lời:

- “Mã đã dệt” chính xác là gì trong các kiến trúc AOP khác nhau?
- Vì sao breakpoint, số dòng và stack trace đôi khi khó đọc hơn trước weaving?
- Những metadata gỡ lỗi nào hỗ trợ ánh xạ từ runtime về mã nguồn?
- Làm thế nào truy vết được **điểm nào được chọn**, **aspect/advice nào chạy**, **vì sao chúng chạy**, và **kết quả cuối cùng thế nào**?
- Cần kiểm thử và thu thập chứng cứ gì để xác định weaving đúng, không chọn thừa hoặc bỏ sót?

Phạm vi là **kiến thức AOP tổng quát, cơ bản và nâng cao**. Những ví dụ về bytecode, proxy, Java debugger, Java 17 dùng để minh họa cơ chế cụ thể; không được suy rằng mọi công cụ AOP áp dụng cùng một cách weaving hoặc có cùng khả năng ánh xạ nguồn.

## 2. Các thực thể trong câu chuyện gỡ lỗi

| Thành phần | Điều cần biết khi gỡ lỗi | Dữ liệu hữu ích |
| --- | --- | --- |
| **Join point** | Đang can thiệp loại sự kiện nào? | Call, execution, field access... nếu hỗ trợ |
| **Pointcut** | Vì sao điểm đó thuộc tập được chọn? | Biểu thức, quy tắc tĩnh/động |
| **Join-point shadow** | Vị trí mã nào có thể tạo ra join point? | Chữ ký, vị trí, loại điểm |
| **Advice** | Hành vi nào được chèn/thực hiện? | Before, after, around, thứ tự |
| **Weaver** | Việc kết hợp xảy ra ở đâu và khi nào? | Compiler, loader, runtime interception |
| **Woven representation** | Mã/đường chạy hiệu lực khác mã gốc thế nào? | Bytecode, adapter, proxy, handler |
| **Debug information** | Có ánh xạ được instruction về source không? | Source file, line, local variables, mapping |
| **Runtime trace** | Lần gọi cụ thể đã đi qua những bước nào? | Trace ID, join-point ID, event và outcome |
| **Build provenance** | Đang chạy đúng bản mã nào? | Phiên bản, hash, cấu hình weaving |

Cần phân biệt **provenance của mã** (bản build nào, cấu hình nào, lớp nào được biến đổi) với **trace của một lần thực thi** (lời gọi nào xảy ra, trên dữ liệu nào, advice nào chạy). Chỉ có stack trace mà không biết build đang chạy đôi khi không đủ để tìm lỗi.

## 3. “Mã đã dệt” không nhất thiết là một tệp source mới

Thuật ngữ **woven code** thường chỉ **biểu diễn thực thi đã kết hợp hành vi aspect**. Tùy cách triển khai, nó có thể là:

- Một tệp mã nguồn được sinh hoặc biến đổi trước khi biên dịch.
- Một class file/bytecode đã thay đổi so với phần nguồn nghiệp vụ ban đầu.
- Một lớp được biến đổi trong lúc class loader nạp vào runtime.
- Một hoặc nhiều adapter, proxy, dispatcher, wrapper hoặc interceptor tham gia đường gọi.
- Một cấu trúc trong runtime hoặc JIT dùng để thực hiện advice.

Không có quy tắc chung rằng weaving luôn sinh ra `WovenOrderService.java` mà người lập trình có thể mở trong IDE. Ngay cả khi tạo class file, việc lưu bản bytecode trước và sau weaving ra đĩa cũng là một khả năng công cụ hoặc bước build tùy chọn.

### 3.1. Từ mã nguồn đến hành vi có hiệu lực

Ví dụ mã nghiệp vụ:

```java
class PaymentService {
    void charge(long amount) {
        System.out.println("charge:" + amount);
    }
}
```

Đây là đoạn minh họa; không có `main` độc lập.

Một chính sách AOP có thể muốn ghi sự kiện trước và sau method execution của `charge`. Bộ dệt có thể tạo đường chạy khái niệm:

```text
beforeAdvice()
try:
    PaymentService.charge(amount)
finally:
    afterAdvice()
```

**Đây là mã giả về hành vi**, không có nghĩa bytecode được dệt luôn có đúng một khối `try/finally` như trên. Advice sau có thể mang ngữ nghĩa chỉ khi thành công, chỉ khi ném ngoại lệ hoặc khi kết thúc; cách biến đổi phải tương ứng đúng loại advice.

### 3.2. Woven representation và advice logic không đồng nhất

Một bytecode biến đổi có thể chỉ chứa lời gọi tới một hàm dispatch/advice được đặt ở nơi khác. Một proxy có thể thực thi logic trong handler mà không sửa phần thân target. Ngược lại, một bộ dệt trực tiếp có thể chèn lệnh ngay tại ranh giới method.

Vì vậy muốn trả lời “lỗi phát sinh trong mã đã dệt hay trong advice?”, cần hiểu **vị trí instruction** và **nguồn logic** chứ không chỉ nhìn tên lớp trong stack trace.

## 4. Ba thời điểm weaving và hệ quả gỡ lỗi

### 4.1. Compile-time weaving

```text
Source nghiệp vụ + khai báo aspect
                 |
              Compiler/
               Weaver
                 |
        Class/bytecode đã dệt
                 |
              Runtime
```

Bộ dệt có thể phân tích AST hoặc biểu diễn trung gian, tìm điểm phù hợp, tạo phương thức/đoạn mã trung gian và biên dịch thành mã thực thi.

Khả năng hỗ trợ gỡ lỗi có thể gồm:

- Báo cáo shadow nào được chọn và advice nào áp dụng.
- Giữ hoặc biến đổi metadata ánh xạ source.
- Sinh thông tin để debugger bước giữa mã gốc và mã advice.
- Lưu artifact đã dệt để so sánh với artifact trước khi dệt.

Điểm cần cảnh giác: line number sau biến đổi có thể không còn tương ứng một-một với một dòng nguồn ban đầu. Cần biết công cụ duy trì thông tin debug ra sao.

### 4.2. Load-time weaving

```text
Bytecode chưa dệt
       |
   Class loading
       |
 Transformer / Weaver
       |
 Bytecode trong runtime
       |
     Execute
```

Ở cách này, bytecode đã biến đổi có thể tồn tại **chỉ trong quá trình nạp và bộ nhớ runtime**. Tệp trên ổ đĩa có thể vẫn là phiên bản chưa dệt. Nếu dùng công cụ để kiểm tra tệp class ban đầu và thấy không có lời gọi advice, **chưa đủ** để kết luận advice không được chèn lúc nạp.

Những yếu tố cần xác minh:

- Class loader nào nạp lớp?
- Transformer được đăng ký trước hay sau khi lớp nạp?
- Cấu hình weaving áp dụng cho lớp/module nào?
- Có hỗ trợ retransform/redefine không, và giới hạn là gì?
- Runtime có cung cấp cơ chế dump bytecode sau biến đổi không?

Không suy rằng tất cả transformer đều cho phép biến đổi lại lớp đã nạp; điều đó phụ thuộc công cụ và cơ chế môi trường.

### 4.3. Runtime interception

```text
Caller -> Proxy/Dispatcher -> Advice chain -> Target
```

Với cơ chế này, phần thân target **có thể hoàn toàn không bị sửa**. Thay vào đó, caller đi qua trung gian; handler chọn advice và chuyển tiếp lời gọi.

Tình huống gỡ lỗi phổ biến:

- Breakpoint ở proxy/handler chạy, rồi mới tới target.
- Stack trace có thể xuất hiện frame adapter/reflection.
- Lời gọi trực tiếp trên target bỏ qua proxy có thể không nhận advice.
- Self-invocation trên target có thể không đi qua đối tượng trung gian.
- Một bộ lọc theo method signature có thể đúng nhưng đường chạy không vào proxy.

Giới hạn này thuộc **một kiểu interception**, không phải định nghĩa chung của mọi AOP.

## 5. Metadata debug trong Java class file

Với Java, thông tin gỡ lỗi trong bytecode giúp debugger liên hệ instruction đang chạy với mã nguồn. Một số thành phần đáng biết:

| Metadata hoặc cơ chế | Công dụng | Giới hạn cần nhớ |
| --- | --- | --- |
| `SourceFile` attribute | Thường ghi tên tệp nguồn liên quan đến class | Chưa phải ánh xạ đầy đủ từng instruction |
| `LineNumberTable` | Liên kết vị trí bytecode với số dòng nguồn | Một dòng có thể tương ứng nhiều instruction; có thể thiếu hoặc thay đổi |
| `LocalVariableTable` | Tên và phạm vi biến local để debugger hiển thị | Thường phụ thuộc cách biên dịch và thông tin debug có được giữ |
| `LocalVariableTypeTable` | Thông tin kiểu chữ ký generic của local khi có | Không bảo đảm tồn tại cho mọi class |
| `MethodParameters` | Tên/thuộc tính tham số khi được lưu | Khác cơ chế local variable debug; tùy tùy chọn biên dịch |
| `SourceDebugExtension` / SMAP | Có thể biểu diễn ánh xạ nguồn mở rộng trong công cụ hỗ trợ | Không phải mọi weaver/debugger đều cung cấp hoặc tiêu thụ |
| Stack trace elements | Tên lớp, method, tệp và dòng khi có | Không phải bản đồ đầy đủ về chuỗi advice đã áp dụng |
| Debugger protocol / VM | Quan sát frame, breakpoint, local variables | Khả năng bước qua code sinh và hiển thị nội dung phụ thuộc công cụ |

**Không phải mọi class file đều có đầy đủ các metadata trên.** Thông tin có thể bị bỏ khi biên dịch, bị biến đổi, bị obfuscate hoặc thiếu tương ứng với source. Debugger có thể hiển thị dòng không xác định hoặc một dòng mang tính xấp xỉ/được chọn cho instruction.

### 5.1. Compile với thông tin debug

Ví dụ từ một chương trình Java có thể biên dịch bằng:

```bash
javac -g WovenTraceDemo.java
javap -c -l -p WovenTraceDemo
```

`javac -g` yêu cầu phát sinh thông tin debug được hỗ trợ. `javap -c -l -p` hiển thị lệnh bytecode, thông tin dòng/local và thành viên private trong class được xem. Đây là **lệnh để khảo sát**, không phải bằng chứng rằng lớp đã được AOP weaving.

So sánh có thể được thực hiện trên bản build khác với `javac -g:none` để quan sát ảnh hưởng của việc bỏ debug info. Khi làm vậy nên giữ toàn bộ điều kiện biên dịch khác giống nhau, và nhớ rằng **compiler/JDK phiên bản khác nhau có thể tạo bytecode khác nhau**.

### 5.2. Source mapping sau biến đổi

Bộ dệt chèn thêm instruction, tạo bridge/helper hoặc dời logic có thể cần cập nhật metadata dòng. Nếu công cụ giữ ánh xạ phù hợp, debugger vẫn có thể nhảy về source nghiệp vụ hoặc source advice.

Nếu không giữ ánh xạ, tình huống có thể gồm:

- Breakpoint tại một dòng trông hợp lý nhưng không khớp instruction dự kiến.
- Stepping nhảy qua các frame sinh tự động.
- Stack trace chỉ hiển thị tệp/dòng của lớp trung gian hoặc `Unknown Source`.
- Dòng code hiển thị không giúp nhận diện advice nào đã gây tác động.

**Không có bảo đảm ánh xạ đa nguồn hoàn hảo.** Một instruction đã dệt có thể biểu diễn logic có nguồn gốc từ cả join point và advice. Một số công cụ dùng mapping mở rộng; công cụ khác chỉ dùng line numbers thông thường.

## 6. Tại sao bước debug từng dòng khó hơn sau weaving?

Giả sử mã nguồn chỉ có:

```java
payment.charge(1000L);
```

Nhưng đường chạy hiệu lực có thêm:

```text
before advice
pointcut runtime guard
security advice
business charge()
after returning advice
audit advice
```

Khi chọn **Step Into** ở dòng gọi, debugger có thể đi qua proxy, handler, bridge method hoặc chính code advice trước khi tới phương thức `charge`. Nếu dùng **Step Over**, debugger có thể vẫn chạy toàn bộ advice rồi mới trở lại caller.

Không nên diễn giải việc debugger “nhảy” từ dòng này sang dòng khác là lỗi lập trình ngay lập tức. Cần biết đang xem **nguồn gốc nghiệp vụ**, **advice** hay **code sinh**.

### 6.1. Breakpoint ở đâu để trả lời từng câu hỏi?

| Muốn biết | Breakpoint/log phù hợp |
| --- | --- |
| Caller đã gọi đường nào? | Tại call site hoặc adapter nhập |
| Pointcut có được áp dụng? | Báo cáo weaving hoặc điểm vào interceptor |
| Guard động nhận dữ liệu gì? | Trước/đang đánh giá guard, nếu công cụ cho quan sát |
| Advice nào chạy trước? | Điểm vào before/around advice |
| Target có thực sự được gọi? | Đầu thân phương thức nghiệp vụ |
| Kết quả bị thay đổi ở đâu? | Trước/sau mỗi lớp advice quanh |
| Ngoại lệ gốc từ đâu? | Điểm ném trong thân và các catch/translator |
| Cleanup có che lỗi không? | Đường finally và xử lý lỗi phụ |
| Có bypass proxy? | So sánh đường qua proxy với gọi trực tiếp target |

Một breakpoint ở phương thức nghiệp vụ chỉ chứng minh **phần thân đã được chạy**. Nó không tự trả lời vì sao advice nào được chọn hoặc không được chọn.

### 6.2. Conditional breakpoints và side effect

Debugger có thể cho đặt breakpoint có điều kiện. Nhưng biểu thức điều kiện có thể phải **đánh giá trong runtime đang bị dừng**. Nếu điều kiện gọi phương thức có side effect hoặc I/O, trạng thái ứng dụng có thể thay đổi hoặc việc debug trở nên chậm, gây hiện tượng khác với chạy bình thường.

Khi có thể, ưu tiên điều kiện đơn giản dựa trên dữ liệu đã có hoặc event trace có cấu trúc thay vì biến debugger thành một phần của workflow nghiệp vụ.

## 7. Stack trace sau weaving: nên đọc như thế nào?

Một stack trace Java cho biết một chuỗi frame của ngăn xếp tại thời điểm ngoại lệ hoặc lúc thu thập trace. Nó giúp xác định nơi ngoại lệ được tạo/lan truyền, nhưng không phải nhật ký đầy đủ mọi advice đã chạy và kết thúc.

Ví dụ mô hình:

```text
IllegalArgumentException: invalid amount
    at payment.RealPayment.pay(RealPayment.java:42)
    at ...reflectiveInvocation(...)
    at ...AdviceDispatcher.invoke(...)
    at ...GeneratedProxy.pay(...)
    at checkout.Caller.checkout(Caller.java:18)
```

**Đây là stack trace minh họa, không phải đầu ra cam kết của JDK hoặc một công cụ AOP cụ thể.** Tên frame, lớp sinh, số dòng và thứ tự chính xác sẽ khác theo cơ chế interceptor, JDK, compiler và vị trí ném lỗi.

Cách đọc:

1. **Lỗi được tạo ở đâu?** Phân biệt thân target với advice hoặc adapter.
2. **Các frame trung gian có nghĩa gì?** Chúng có thể do reflection/proxy/weaver tạo để nối đường đi.
3. **Có bọc lỗi không?** `cause` có thể chứa lỗi gốc bên dưới một exception chuyển đổi.
4. **Có lỗi thứ cấp không?** `suppressed` có thể ghi nhận cleanup hoặc việc báo lỗi bị hỏng.
5. **Có mất thông tin nguồn không?** `Unknown Source` hoặc dòng không chính xác cần kiểm tra debug metadata.
6. **Có trace ID không?** Stack trace của một thời điểm không liên kết được tất cả giai đoạn của một yêu cầu phân tán.

### 7.1. Stack trace không chứng minh mọi advice đã chạy

Một before advice có thể đã ghi log rồi kết thúc, nên frame của nó không còn nằm trên stack lúc target ném lỗi. Một advice ở sau khi trả về cũng chưa hề chạy tại thời điểm target đang ném lỗi.

Muốn biết **trình tự thực tế**, cần trace sự kiện hoặc instrumentation có điểm ghi bắt đầu/kết thúc, không chỉ một ảnh chụp stack.

### 7.2. Reflection và ngoại lệ có lớp bọc

Khi interceptor gọi đích bằng `Method.invoke`, Java reflection có thể bọc ngoại lệ do target ném thành `InvocationTargetException`. Handler thường cần phân biệt lớp bọc kỹ thuật với `getCause()` là lỗi từ target.

Công cụ weaving không dùng reflection có thể không có lớp bọc này. Vì vậy không nên tự giả định mọi lỗi trong AOP đều xuất hiện dưới dạng `InvocationTargetException`.

### 7.3. JIT và bytecode tối ưu hóa

Các môi trường runtime hiện đại có tối ưu như JIT/inlining. Debugger và stack-walking API thường phối hợp với VM để tái hiện frame có ý nghĩa, nhưng độ chi tiết, hiệu năng và trải nghiệm stepping có thể phụ thuộc phiên bản/runtime. Đừng suy từ một phép đo đơn lẻ rằng một frame trong stack chính là một lần gọi vật lý chưa từng được tối ưu.

## 8. Truy vết “vì sao advice đã chạy” cần hơn stack trace

Một trace phục vụ chẩn đoán pointcut nên giúp trả lời ít nhất:

- **Join point nào?** Loại, chữ ký và một định danh ổn định thích hợp.
- **Vị trí hay shadow nào?** Source location/định danh call site khi có.
- **Pointcut nào?** Tên quy tắc hoặc một ID tương ứng với bản cấu hình.
- **Advice nào?** ID/loại advice, thứ tự hiệu lực.
- **Khi nào?** Thời điểm vào/ra, thời lượng theo đồng hồ phù hợp.
- **Ngữ cảnh nào?** Trace ID, request ID, loại đối tượng hoặc thuộc tính đã được phép ghi.
- **Điều kiện động đã khớp không?** Phân biệt bị loại bởi guard hay không thuộc phạm vi tĩnh.
- **Kết quả là gì?** Return, throw, bị chặn trước proceed, fallback hoặc retry.
- **Build nào?** Phiên bản artifact đã dệt, cấu hình và chính sách áp dụng.

Không phải mọi công cụ cung cấp sẵn tất cả trường trên. Có trường là **weaving report**, có trường cần do advice thêm vào **runtime log** và có trường do hệ thống build cung cấp.

### 8.1. Static join-point ID và dynamic invocation ID

Giả sử cùng một phương thức `Payment.pay(String,long)` được gọi 1.000 lần. Dùng chỉ **chữ ký** không thể phân biệt 1.000 lần chạy.

Nên suy nghĩ theo hai tầng:

```text
Static identity:
  point = Payment.pay(String,long)
  kind = method execution
  source = phiên bản build đang chạy

Dynamic identity:
  traceId = req-0042
  invocationId = span-009
  outcome = success / failure
```

Đây là mẫu cấu trúc sự kiện, không phải API bắt buộc. Một method call join point ở hai vị trí khác nhau có thể cần thêm **call-site identity**, dù chữ ký phương thức đích giống nhau.

### 8.2. ID phải được gắn đúng vòng đời

- **Request ID** có thể dùng xuyên nhiều thao tác.
- **Invocation/span ID** phân biệt các lần gọi lồng nhau.
- **Build ID** định danh mã và cấu hình weaving.
- **Pointcut/advice ID** mô tả chính sách được áp dụng.

Đừng dùng một biến mutable toàn cục `currentRequestId` cho mọi luồng. Nó có thể khiến log của yêu cầu này mang nhãn của yêu cầu khác. Cần cơ chế context per invocation/tác vụ, cùng chính sách truyền và dọn ngữ cảnh.

## 9. Thiết kế bản ghi truy vết có cấu trúc

Một sự kiện minh họa:

```json
{
  "buildId": "build-2026-10",
  "traceId": "req-0042",
  "invocationId": "call-03",
  "joinPoint": {
    "kind": "method-execution",
    "signature": "Payment.pay(String,long)"
  },
  "advice": {
    "id": "audit-payments",
    "phase": "before"
  },
  "event": "entered"
}
```

Các giá trị trong JSON chỉ mang tính minh họa; đây **không phải schema chuẩn do mọi AOP engine phát ra**.

Một sự kiện kết thúc có thể dùng cùng trace/invocation và mô tả `outcome=returned`, `outcome=thrown` hoặc `outcome=short-circuited`. Với around advice, cần xác định **có gọi proceed hay không**, vì sự kiện “đã vào advice” không đồng nghĩa “target đã chạy”.

### 9.1. Tránh log quá nhiều dữ liệu

Join-point context có thể chứa mật khẩu, token, thông tin thanh toán và dữ liệu cá nhân. Không tự động ghi `args.toString()` hoặc giá trị trả về toàn bộ chỉ để debug.

Ưu tiên:

- Ghi tên/loại điểm, chính sách và kết quả tổng quát.
- Ghi mã tương quan đã được thiết kế, không dùng đối tượng hoặc địa chỉ bộ nhớ làm ID nghiệp vụ.
- Che, loại bỏ hoặc băm có kiểm soát các giá trị nhạy cảm nếu thực sự cần.
- Giới hạn kích thước payload và vòng đời lưu giữ.
- Không để lỗi ghi log tùy chọn che kết quả nghiệp vụ, trừ khi hợp đồng audit bắt buộc yêu cầu khác.

### 9.2. Độ chính xác của thời gian

Đo duration thường cần **đồng hồ đơn điệu** tương ứng (ví dụ `System.nanoTime()` trong Java), còn timestamp để đối chiếu giữa máy cần đồng hồ thời gian thực và phương án đồng bộ/ước lượng sai số.

Không tính duration chỉ bằng phép trừ hai timestamp wall-clock nếu môi trường có thể điều chỉnh đồng hồ. Và không kết luận một dòng `after returning` cho phương thức trả future đồng nghĩa tác vụ bất đồng bộ đã hoàn thành.

## 10. Ví dụ Java 17 chạy được: dấu vết caller → interceptor → business

Java thuần không cung cấp một cú pháp pointcut/weaver AOP thống nhất. Để quan sát **đường gọi đã được kết hợp qua interceptor**, ta có thể dùng `java.lang.reflect.Proxy` của JDK.

Ví dụ này là **mô phỏng một cơ chế runtime interception**: phương thức giao diện được gọi qua proxy, handler ghi sự kiện advice, gọi target và chuyển tiếp kết quả/ngoại lệ. Nó không tạo bytecode weaving cho mọi join point, không tự chặn field access và không thay thế engine AOP tổng quát.

Tạo tệp `WovenTraceDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public class WovenTraceDemo {

    interface Payment {
        String pay(String orderId, long cents);
    }

    static final class RealPayment implements Payment {
        @Override
        public String pay(String orderId, long cents) {
            System.out.println("business:pay:" + orderId + ":" + cents);
            if (cents < 0) {
                throw new IllegalArgumentException("negative cents");
            }
            return "RECEIPT:" + orderId;
        }
    }

    public static void main(String[] args) {
        Payment target = new RealPayment();
        AtomicInteger sequence = new AtomicInteger();

        Payment traced = (Payment) Proxy.newProxyInstance(
                Payment.class.getClassLoader(),
                new Class<?>[] { Payment.class },
                (Object proxy, Method method, Object[] values) -> {
                    String traceId = "req-" + sequence.incrementAndGet();
                    String point = method.getDeclaringClass()
                            .getSimpleName() + "." + method.getName();

                    System.out.println("trace:enter:" + traceId + ":" + point);
                    System.out.println("advice:before:" + traceId);

                    try {
                        Object result = method.invoke(target, values);
                        System.out.println("advice:afterReturning:" + traceId);
                        return result;
                    } catch (InvocationTargetException wrapped) {
                        Throwable original = wrapped.getCause();
                        System.out.println("advice:afterThrowing:" + traceId
                                + ":" + original.getClass().getSimpleName());
                        throw original;
                    } finally {
                        System.out.println("trace:exit:" + traceId);
                    }
                }
        );

        System.out.println("caller:start");
        System.out.println("caller:result:" + traced.pay("O-1", 1200));

        try {
            traced.pay("O-2", -1);
        } catch (IllegalArgumentException error) {
            System.out.println("caller:error:" + error.getMessage());
        }

        System.out.println("caller:end");
    }
}
```

Lệnh biên dịch và chạy (JDK 17+):

```bash
javac -g WovenTraceDemo.java
java WovenTraceDemo
```

Đầu ra:

```text
caller:start
trace:enter:req-1:Payment.pay
advice:before:req-1
business:pay:O-1:1200
advice:afterReturning:req-1
trace:exit:req-1
caller:result:RECEIPT:O-1
trace:enter:req-2:Payment.pay
advice:before:req-2
business:pay:O-2:-1
advice:afterThrowing:req-2:IllegalArgumentException
trace:exit:req-2
caller:error:negative cents
caller:end
```

### 10.1. Đọc output theo hai trục

**Trục cấu trúc (tĩnh):**

- Handler nhận `Method` tương ứng với phương thức giao diện `Payment.pay`.
- Tên `Payment.pay` mô tả phương thức nhìn qua giao diện proxy trong ví dụ.
- `RealPayment` là lớp target thực tế, không nhất thiết đồng nhất với declaring type của `Method` mà handler nhận.
- Một công cụ weaving vào thân method có thể cung cấp metadata khác, đặc biệt về call site hoặc execution.

**Trục diễn tiến (động):**

- `req-1` và `req-2` phân biệt hai invocation.
- Cả hai đi qua advice trước.
- `req-1` trả về bình thường, có `afterReturning` và caller nhận receipt.
- `req-2` ném `IllegalArgumentException` từ target; reflection bọc tạm thời trong `InvocationTargetException`, handler lấy `getCause()` rồi truyền lỗi gốc để caller bắt.
- `trace:exit` chạy từ `finally` của handler ngay cả trên đường lỗi.

### 10.2. Vì sao ví dụ không in stack trace đầy đủ?

Dấu vết stack có thể chứa tên lớp proxy được sinh, frame reflection và thông tin dòng thay đổi theo JDK/cách thực thi. Ví dụ dùng **sự kiện có cấu trúc xác định** để stdout ổn định, không phỏng đoán một stack trace cụ thể.

Nếu muốn khảo sát stack thật trên máy đang chạy, có thể thêm `new Exception("diagnostic").printStackTrace()` tại điểm được chọn rồi đọc kết quả thực tế. Không nên hard-code một bản stack trace giả làm “stdout chính xác” cho mọi môi trường.

### 10.3. Giới hạn và giá trị của ví dụ

- Gọi `target.pay(...)` trực tiếp **không** đi qua handler proxy này.
- Phương thức `RealPayment` tự gọi phương thức khác của cùng đối tượng có thể bypass proxy.
- Đây là **interception minh họa**, không phải weaving ở mọi method call/execution.
- `AtomicInteger` chỉ làm bộ đếm cho ví dụ; trace ID production cần bền vững/độc lập theo yêu cầu, không tự coi `req-1` là định danh phân tán an toàn.
- Runtime trace cho thấy **chuỗi đã thực sự chạy**, nhưng không chứng minh toàn bộ **tập static shadows** mà một weaver khác có thể chọn.

## 11. Soi bytecode và debug metadata bằng công cụ JDK

Có thể tiếp tục từ tệp `WovenTraceDemo.java`:

```bash
javap -c -l -p WovenTraceDemo
```

Ý nghĩa các tùy chọn:

- `-c`: hiển thị bytecode instructions đã biên dịch.
- `-l`: hiển thị line number và local variable tables nếu có.
- `-p`: bao gồm thành viên private trong phần liệt kê.

Nếu muốn quan sát lớp target lồng bên trong, trên một số shell có thể cần quote/escape ký tự `$` trong tên binary class:

```text
WovenTraceDemo$RealPayment
```

Lệnh xem lớp lồng phải phù hợp với cú pháp shell đang dùng. Không nên giả định dấu `$` trong tên class là cú pháp thuộc Java source hoặc cú pháp wildcard của pointcut.

### 11.1. So sánh “trước” và “sau” weaving đúng cách

Với một hệ thống thực sự có compiler/bytecode weaver, cách điều tra có thể là:

1. Giữ bản bytecode **chưa dệt** từ cùng nguồn/build.
2. Lấy bản bytecode **đã dệt** từ đầu ra build hoặc chức năng dump được hỗ trợ.
3. Xác nhận cùng phiên bản JDK, dependency, cấu hình và tên class.
4. Dùng công cụ xem bytecode để so sánh các phương thức/nhánh/handler.
5. Kiểm tra `LineNumberTable` và metadata debug có được giữ/cập nhật không.
6. Đối chiếu báo cáo weaving: pointcut nào khớp shadow nào.
7. Chạy kiểm thử để xác nhận đường thực thi thực tế đúng.

**Không nên chỉ so sánh hai tệp class ở hai bản build khác nhau** rồi kết luận mọi khác biệt đều do weaving: compiler option, thay đổi nguồn, tối ưu và dependency cũng có thể tạo bytecode khác.

### 11.2. Trong load-time weaving, tệp class trên đĩa có thể chưa dệt

Một nguyên tắc chẩn đoán: nếu weaving xảy ra lúc nạp, công cụ `javap` trên tệp lớp có sẵn **chỉ cho thấy tệp ấy**, không nhất thiết là bytecode sau biến đổi đã được class loader định nghĩa trong VM. Muốn kiểm tra phiên bản runtime phải dùng cơ chế quan sát/dump do môi trường cho phép.

## 12. Weaving report: truy vết tĩnh trước khi chạy

Một công cụ AOP có thể phát báo cáo về các join-point shadows được so khớp. Nội dung thường cần đến:

- Aspect và pointcut/advice nào được áp dụng.
- Loại join point (call/execution/...).
- Chữ ký và vị trí nguồn/mã của điểm nếu có.
- Class hoặc artifact được weaving.
- Điểm bị loại, nếu có chế độ chẩn đoán tương ứng.
- Thông báo lỗi/cảnh báo khi không thể can thiệp.

Một dòng báo cáo **minh họa**, không phải cú pháp cố định:

```text
WEAVE matched:
  advice=auditPayment
  kind=method-execution
  point=PaymentService.pay(String,long)
  class=PaymentService
  source=PaymentService.java
```

Báo cáo này trả lời **điểm tĩnh nào được chọn**. Nó không tự chứng minh một lời gọi đã xảy ra hoặc guard động đã khớp. Một method có thể được dệt nhưng chưa bao giờ chạy trong ca kiểm thử.

### 12.1. Không nhầm “khớp” với “đã áp dụng thành công”

Một weaver có thể tìm thấy điểm có khả năng khớp nhưng thất bại khi biến đổi class hoặc không được phép sửa một thành phần. Cần phân biệt:

1. Điểm được biểu thức chọn.
2. Điểm nằm trong phạm vi có thể weaving.
3. Weaving hoàn tất thành công.
4. Runtime thực sự đi qua điểm.
5. Điều kiện động thỏa và advice chạy.

Nếu thiếu bước (3), báo cáo matcher tích cực không đủ. Nếu thiếu (4), sẽ không có sự kiện runtime dù weaving đúng. Nếu thiếu (5), guard có thể đã lọc invocation.

### 12.2. Cách dùng report trong CI

Với pointcut quan trọng, nhóm phát triển có thể lưu một bản kiểm kê được xem xét về tập join point mong muốn. Trong CI, so sánh report mới với kỳ vọng:

- Điểm nào mới được chọn do thêm method/class?
- Điểm nào biến mất sau refactor?
- Có điểm nào bị chọn ngoài vùng cho phép?
- Có thay đổi loại join point hoặc class loader?
- Có cảnh báo không thể weaving một lớp cần thiết?

Cần tránh dùng **chính report hiện tại** làm “đáp án chuẩn” mà không có yêu cầu độc lập. Kiểm thử chỉ so report với bản thân không phát hiện sai phạm vi.

## 13. Ánh xạ source và bytecode khi xuất hiện mã sinh

Mã được compiler hoặc weaver tạo có thể có:

- Bridge methods.
- Synthetic methods.
- Helper methods giữ đoạn logic được tách.
- Wrapper hoặc dispatcher cho advice.
- Anonymous/lambda classes.
- Proxy classes được sinh runtime.

Những phần này không nhất thiết tồn tại như một method có tên tương đương trong source. Debugger có thể hiển thị frame sinh tự động hoặc ẩn một số chi tiết tùy khả năng.

### 13.1. Source map không thể luôn chỉ đến một dòng duy nhất

Một instruction “gọi advice quanh method” có thể phản ánh cả:

- Vị trí join point trong source nghiệp vụ.
- Dòng khai báo advice trong source aspect.
- Logic sinh tự động của weaver.

Không phải mọi VM/debugger đều hỗ trợ ánh xạ đa nguồn hoàn chỉnh ở cùng một instruction. Nếu stack trace đặt lỗi ở lớp sinh thay vì dòng advice, có thể cần đối chiếu report weaving và mã/bytecode sinh.

### 13.2. Obfuscation và tối ưu build

Nếu tên lớp/method được đổi hoặc debug metadata bị loại, stack trace production có thể khó đọc. Cần giữ artifact/mapping tương ứng với **đúng bản build** để giải mã. Không áp dụng mapping từ phiên bản khác, vì cùng một tên rút gọn có thể chỉ đến mã khác.

Nếu hệ thống ký hoặc checksum artifact, việc weaving sau thời điểm ký cũng ảnh hưởng việc kiểm chứng phiên bản thực thi. Kiến trúc build/release phải tính đến thời điểm weaving.

## 14. Ngoại lệ, cause và suppressed trong đường đã dệt

Một advice có thể ném ngoại lệ **trước** khi phần gốc chạy hoặc **sau** khi phần gốc đã thành công. Vì vậy:

```text
Caller nhận exception
          |
          +-- Có thể body nghiệp vụ chưa được gọi
          |
          +-- Có thể body đã ném exception gốc
          |
          +-- Có thể body đã thành công nhưng after advice lỗi
          |
          +-- Có thể lỗi của advice trong đã bị advice ngoài chuyển đổi
```

Khi gỡ lỗi:

1. Xác định lỗi đầu tiên phát sinh ở đâu.
2. Xác định phần gốc đã được gọi bao nhiêu lần.
3. Xác định có advice nào đổi loại lỗi hoặc trả fallback không.
4. Đọc `Throwable.getCause()` và `getSuppressed()` nếu áp dụng.
5. Kiểm tra có retry nào đã thực thi lại nghiệp vụ hoặc gây side effect không.

Một `finally` tự ném lỗi có thể **che ngoại lệ gốc**; Java `try-with-resources` có cơ chế suppressed cho lỗi khi đóng tài nguyên, nhưng không được suy rằng mọi after/finally advice đều tự động bảo toàn primary error như vậy.

### 14.1. Mã đã dệt và thay đổi hợp đồng quan sát

Nếu phần nghiệp vụ trả về nhưng after advice ném lỗi, caller có thể nhận ngoại lệ. Đây không nhất thiết là “lỗi của weaver”: có thể chính advice gây ra theo logic đã được cấu hình. Cần phân biệt **lỗi biến đổi mã** với **hành vi của advice**.

## 15. Đa luồng, đệ quy và bất đồng bộ làm trace phức tạp hơn

### 15.1. Hai invocation có thể xen kẽ

```text
T1: before(A) --- business(A) ------- after(A)
T2:     before(B) --- business(B) --- after(B)
```

Nếu chỉ nhìn thứ tự timestamp trong một file log, dòng của A/B có thể xen kẽ. Điều đó không chứng minh advice chạy sai thứ tự **bên trong từng invocation**.

Cần gắn event theo trace ID và invocation/span ID. Các ID này không nên lấy từ một biến mutable dùng chung không đồng bộ.

### 15.2. Đệ quy tạo nhiều frame cho cùng join point

Một method đệ quy có thể phát sinh nhiều invocation lồng nhau của cùng shadow. Nếu advice đo thời gian bằng một biến `startTime` dùng chung, lần gọi sâu hơn có thể ghi đè mốc của lần ngoài.

Một thiết kế an toàn thường lưu thông tin theo invocation/frame tương ứng.

### 15.3. Method return khác task completion

Một method trả `CompletableFuture<Result>` có thể trả handle rất nhanh trong khi công việc tiếp tục ở một thread khác.

- Trace around **method execution** có thể kết thúc lúc trả Future.
- Trace **tác vụ bất đồng bộ** cần theo dõi tới completion phù hợp.
- Ngoại lệ xảy ra sau này có thể nằm trong completion state, không xuất hiện trong `catch` đồng bộ bao lời gọi tạo Future.
- Context cần được truyền sang task nếu thiết kế trace xuyên ranh giới.

Một trace sai ranh giới dễ báo “success” quá sớm. Hãy đặt tên event phân biệt `method-returned` và `task-completed` nếu thực sự cần cả hai.

### 15.4. Không coi thread ID là trace ID

Một thread pool xử lý nhiều request nối tiếp hoặc xen kẽ. Thread ID có thể hữu ích để chẩn đoán, nhưng **không đại diện duy nhất cho một request**. Với bất đồng bộ, cùng một request có thể chạy trên nhiều thread.

## 16. Khi nào log tracing tự làm thay đổi hệ thống?

Instrumentation không “miễn phí”. Nó có thể:

- Tăng CPU và cấp phát.
- Gây contention do logger đồng bộ.
- Thực hiện I/O trong đường nóng.
- Làm lộ dữ liệu nhạy cảm.
- Ném ngoại lệ từ formatter hoặc sink.
- Tạo vòng lặp nếu hàm logging cũng khớp pointcut.
- Thay đổi lịch chạy của thread, khiến race condition khó tái hiện.

Do đó một trace phục vụ debug nên **tối thiểu đủ dùng**, có giới hạn và chính sách lỗi rõ ràng.

### 16.1. Dùng sampling có chấp nhận được không?

Với telemetry chẩn đoán, sampling có thể giảm chi phí, miễn không làm mất những event cần thiết cho mục đích đo. Nhưng với audit bắt buộc, lấy mẫu có thể không chấp nhận được. Không tự dùng sampling cho dữ liệu tuân thủ chỉ vì tracing quá nặng.

### 16.2. Tránh tự kích hoạt aspect

Nếu advice ghi log qua một method cũng thuộc pointcut, có thể tạo chuỗi:

```text
advice -> logger.log() -> cùng pointcut -> advice -> ...
```

Cần thiết kế ranh giới lọc rõ ràng hoặc cơ chế chống reentrancy phù hợp. Một cờ global không phân biệt invocation có thể khiến yêu cầu khác mất advice.

## 17. Khi nào nên lấy dump mã đã dệt?

Dump bytecode hoặc bản representation có thể hữu ích để:

- Xác nhận có thực sự chèn advice/guard không.
- So sánh vị trí lệnh trước và sau.
- Giải thích frame sinh hoặc line-number bất thường.
- Xác minh một method không được weaving vì nằm ngoài phạm vi.
- Chẩn đoán lỗi verifier/loader hoặc giới hạn biến đổi.

Nhưng dump cần thận trọng:

- Có thể chứa mã độc quyền, hằng số nhạy cảm, tên module và đường dẫn.
- Có thể rất lớn, ảnh hưởng I/O và bộ nhớ.
- Có thể không thể tái tạo chính xác ở runtime khác.
- Phải gắn đúng build ID/cấu hình và thời điểm lấy.
- Không phát hành public hoặc gửi dump sản phẩm thực nếu chưa có quyền và quy trình bảo mật.

Trong nhiều trường hợp, **weaving report + trace có cấu trúc + stack trace lỗi + artifact build đúng phiên bản** đã đủ để xác định vấn đề mà không cần dump toàn bộ VM.

## 18. Quy trình điều tra một advice “biến mất”

Tình huống: phương thức `Payment.pay` chạy, nhưng không thấy log audit.

Tiến trình có hệ thống:

1. **Xác nhận mã nguồn và bản build**: lớp đang chạy đúng phiên bản nào? Cấu hình weaving có đúng không?
2. **Xác nhận pointcut**: loại join point là call hay execution? Chữ ký, modifier, package, annotation có khớp không?
3. **Kiểm tra phạm vi weaving**: module/class nào được áp dụng? Nếu load-time weaving, transformer đã hoạt động trước khi lớp nạp chưa?
4. **Kiểm tra weaving report**: shadow tương ứng có được chọn và dệt thành công không?
5. **Kiểm tra điều kiện runtime**: có guard dựa trên args, target hoặc control flow đang sai không?
6. **Kiểm tra đường gọi**: có đi qua proxy/interceptor không? Có self-invocation hoặc gọi trực tiếp target không?
7. **Kiểm tra advice ngoài**: có advice nào không gọi proceed, từ chối hoặc đổi đường thực thi không?
8. **Kiểm tra logger**: việc ghi log có lỗi hoặc bộ lọc log có bỏ event không?
9. **Tạo ca tối thiểu**: gọi một lần đúng và một lần sai điều kiện, gắn invocation ID để quan sát.
10. **Đối chiếu report + trace**: tách khớp tĩnh khỏi advice runtime và loại trừ từng nguyên nhân.

Đừng sửa wildcard thành “chọn mọi method” để chữa triệu chứng chưa xác định. Nó có thể mở rộng advice tới những vùng nguy hiểm mà vẫn không giải quyết lỗi đường weaving.

## 19. Quy trình điều tra một stack trace “lạ”

Tình huống: ứng dụng ném ngoại lệ ở một frame tên khó hiểu, debugger nhảy sang method sinh.

Nên làm:

1. Lưu **stack trace đầy đủ**, bao gồm `cause` và `suppressed`.
2. Ghi lại bản build, phiên bản JDK, loại weaving và cấu hình.
3. Xác định frame nào thuộc target, advice, proxy/reflection hoặc code sinh.
4. Kiểm tra `SourceFile`/`LineNumberTable` của đúng class đang chạy hoặc artifact tương ứng.
5. Nếu phù hợp, xem weaving report và bytecode đã dệt.
6. Tái hiện với breakpoint/log tại entry/exit của advice và target.
7. So sánh đầu ra khi **có** và **không có** advice trong một môi trường kiểm thử có kiểm soát, nếu công cụ cho phép mà không thay đổi nghĩa nghiệp vụ.
8. Kiểm tra lỗi do advice sau thành công, advice ngoài đổi lỗi, hoặc cleanup che lỗi gốc.
9. Ghi kết luận bằng **đường thực thi có chứng cứ**, không chỉ từ tên phương thức gần đỉnh stack.

Không nên “xóa frame proxy” khi phân tích, vì đôi khi chính adapter/handler mới là nơi lỗi xảy ra. Có thể rút gọn cách trình bày cho người đọc, nhưng phải giữ bản gốc để chẩn đoán.

## 20. Kiểm thử weaving và traceability

Một bộ kiểm thử đáng tin cậy phải chứng minh cả **đúng phạm vi** lẫn **đúng thông tin quan sát**:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Phương thức phải được advice | Weaving/matching đúng và advice chạy đúng lần |
| Phương thức không thuộc chính sách | Advice không chạy, kể cả sau refactor |
| Overload/override | Không chọn sai chữ ký hoặc kiểu |
| Call vs execution | Quan sát đúng ranh giới dự kiến |
| Guard động đúng/sai | Có/không có advice tương ứng |
| Lời gọi qua proxy và trực tiếp | Hiểu rõ phạm vi interception |
| Self-invocation | Hành vi đúng giới hạn công cụ |
| Advice trả kết quả | Caller nhận đúng kết quả theo hợp đồng |
| Target ném ngoại lệ | Cause và nhánh after-throwing đúng |
| Advice ném ngoại lệ | Không gán nhãn sai nguồn hoặc che lỗi gốc ngoài ý định |
| Hai advice cùng khớp | Thứ tự hiệu lực đúng |
| Đệ quy/đa luồng | Trace ID, invocation ID và state độc lập |
| Method trả Future | Không nhầm return với task completion |
| Debug info có/không | Hiểu độ tin cậy của file/line trong stack |
| Thay bản build | Report, mapping và trace vẫn khớp phiên bản |

### 20.1. Kiểm thử trace bằng sự kiện xác định

Trong kiểm thử, nên dùng bộ ghi sự kiện trong bộ nhớ thay cho logger bất đồng bộ nếu mục tiêu là so thứ tự chính xác. Ví dụ kỳ vọng:

```text
before#req-1
business#req-1
afterReturning#req-1
exit#req-1
```

Với ngoại lệ:

```text
before#req-2
business#req-2
afterThrowing#req-2
exit#req-2
```

Sau đó kiểm tra **chuỗi sự kiện theo từng invocation**, tránh giả định rằng các event của hai thread phải đứng liền nhau trong log chung.

### 20.2. Kiểm thử metadata gỡ lỗi

Nếu dự án yêu cầu debugger/source mapping chính xác, hãy có một quy trình kiểm thử build artifact với thông tin debug cần thiết, xem class thực tế và xác nhận line mapping ở những vị trí trọng yếu. Không chỉ dựa vào mã nguồn trong IDE, vì mã chạy có thể là phiên bản đã biến đổi.

## 21. Những hiểu nhầm thường gặp

**“Weaving luôn tạo một file Java đã sửa.”** Không. Có thể tạo bytecode, adapter hoặc chỉ biến đổi lớp trong khi nạp.

**“Mã trong repository luôn đúng y hệt bytecode đang chạy.”** Không bảo đảm khi có weaving, code generation, proxy, compiler optimization hoặc khác phiên bản build.

**“Breakpoint ở target không dừng nghĩa là pointcut không khớp.”** Có thể target chưa được gọi vì advice chặn trước, đường gọi khác hoặc breakpoint ánh xạ sai.

**“Stack trace là toàn bộ lịch sử advice.”** Không. Nó là ảnh chụp ngăn xếp tại một thời điểm, không ghi đầy đủ advice đã hoàn tất.

**“Một dòng stack trace luôn ánh xạ một dòng Java.”** Không bảo đảm khi có code sinh, biến đổi hoặc thiếu metadata.

**“Có `LineNumberTable` thì gỡ lỗi woven code luôn hoàn hảo.”** Không. Bảng dòng không nhất thiết diễn tả nguồn gốc đa chiều của advice và join point.

**“Có weaving report nghĩa advice chắc chắn đã chạy.”** Chưa đủ. Cần invocation thật và điều kiện runtime khớp.

**“Không có log nghĩa advice không chạy.”** Có thể logger lỗi, lọc log, sampling hoặc advice ghi sự kiện không đúng chỗ.

**“Proxy có thể chặn mọi lời gọi tới target.”** Không. Đường gọi trực tiếp và lời gọi nội bộ có thể bypass proxy.

**“Trace ID chính là thread ID.”** Không. Một request có thể chuyển thread, còn một thread phục vụ nhiều request.

**“Exception do caller nhận chắc chắn do business.”** Không. Advice trước/sau/bao quanh có thể tạo hoặc chuyển đổi ngoại lệ.

**“Dump đã dệt ở một build đủ chứng minh production cùng bytecode.”** Không nếu cấu hình, class loader, JDK hoặc artifact khác nhau.

## 22. Câu hỏi tự luyện

**1.** Một lớp được load-time weaving nhưng tệp `.class` trên ổ đĩa không có lời gọi advice. Có phải weaving không hoạt động?

Chưa chắc. Tệp đĩa có thể là bytecode trước biến đổi. Phải kiểm tra transformer, class loader, log/report và bytecode thực được nạp nếu môi trường cho phép.

**2.** Weaving report nói có năm shadows khớp. Có thể kết luận advice chạy đúng năm lần không?

Không. Mỗi shadow có thể chạy nhiều lần, không lần nào hoặc trượt guard động.

**3.** Stack trace có frame proxy trước target. Có phải source gốc bị sửa trực tiếp không?

Không. Frame proxy có thể chỉ ra lời gọi qua adapter, trong khi thân target chưa bị biến đổi.

**4.** Debugger dừng ở một dòng mã nguồn nhưng instruction đang chạy thuộc logic advice chèn thêm. Làm sao kiểm chứng?

Đối chiếu loại weaving, mapping/source line, bytecode của đúng artifact, report weaving và điểm vào advice; không dựa duy nhất vào một con số dòng.

**5.** Một phương thức trả `CompletableFuture`, advice ghi “success” ngay khi method trả Future. Có phải tác vụ đã thành công?

Không. Method return và task completion là hai ranh giới khác nhau.

**6.** Hai request cùng gọi một join point. Chỉ dùng chữ ký để log có đủ phân biệt không?

Không. Cần invocation/span ID hoặc correlation ID, và context phải đi theo từng invocation/tác vụ.

**7.** Một after advice ném ngoại lệ sau khi nghiệp vụ đã ghi dữ liệu. Caller nhận lỗi. Có được kết luận dữ liệu chưa ghi không?

Không. Lỗi hậu xử lý có thể xuất hiện sau side effect. Cần xác minh trạng thái và chính sách retry/idempotency.

**8.** Một call site ở hai nơi khác nhau gọi cùng method. Nếu muốn biết vị trí gọi nào đã được can thiệp, metadata tối thiểu là gì?

Ngoài chữ ký, cần định danh **loại join point** và **vị trí call site/shadow** (source location hoặc ID khác do công cụ cung cấp); runtime thêm invocation ID nếu muốn phân biệt các lần gọi.

## 23. Checklist thiết kế và vận hành

- [ ] Biết tool đang dùng compile-time, load-time hay runtime interception.
- [ ] Biết loại join point thực sự được hỗ trợ.
- [ ] Có nguồn xác thực các điểm khớp tĩnh (report hoặc kiểm thử).
- [ ] Có kiểm thử đường chạy thực tế và guard động.
- [ ] Đã xác định cách lấy bản bytecode hoặc representation đã dệt khi cần.
- [ ] Giữ artifact, build ID, cấu hình weaving và mapping đúng phiên bản.
- [ ] Có chính sách giữ debug metadata đủ cho môi trường đích.
- [ ] Debugger có thể phân biệt code nghiệp vụ, advice và frame sinh.
- [ ] Có trace ID/invocation ID cho event trước/sau/ngoại lệ.
- [ ] Không hiểu stack trace là nhật ký toàn bộ advice.
- [ ] Có cách đọc `cause`/`suppressed` để truy nguyên lỗi.
- [ ] Không nhầm success của method trả Future với completion.
- [ ] Không dựa vào thread ID duy nhất để ghép các event.
- [ ] Không để instrumentation log dữ liệu nhạy cảm.
- [ ] Đã cân nhắc chi phí và nguy cơ tái nhập của logging.
- [ ] Có kiểm thử dương/âm khi thay pointcut hoặc refactor.
- [ ] Có phương án kiểm chứng khi production khác môi trường local.

## 24. Kết luận

**Mã đã dệt là biểu diễn thực thi có hiệu lực sau khi hành vi AOP được kết hợp**, không nhất thiết là một tệp source mới. Thông tin gỡ lỗi như dòng nguồn, biến local, source mapping và stack frame giúp kết nối runtime với mã người lập trình viết, nhưng weaving có thể thêm frame, chèn instruction hoặc tạo thành phần trung gian khiến phép ánh xạ không còn đơn giản.

Để truy vết đáng tin cậy, cần kết hợp **chứng cứ cấu trúc** (pointcut, shadow, weaving report, artifact/build ID), **chứng cứ runtime** (invocation, guard, advice order, return/exception) và **chứng cứ debug** (bytecode/source mapping/stack trace). Chỉ khi ba lớp chứng cứ nhất quán, ta mới trả lời được chính xác *điểm nào được dệt, vì sao advice chạy, phần gốc đã thực thi ra sao và caller đã quan sát kết quả nào*.
