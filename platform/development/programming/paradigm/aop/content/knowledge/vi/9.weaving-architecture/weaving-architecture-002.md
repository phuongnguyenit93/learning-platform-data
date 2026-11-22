# Chèn hành vi vào mã nguồn, mã trung gian hoặc đường gọi trong kiến trúc weaving AOP

## 1. Vấn đề cần giải quyết

Trong **Aspect-Oriented Programming (AOP)**, các mối quan tâm xuyên cắt như tracing, kiểm toán, đo thời gian, chính sách truy cập hoặc ghi nhận lỗi có thể cần được áp dụng cho nhiều vị trí của chương trình. Thay vì sao chép mã xử lý cùng một concern vào hàng trăm phương thức, ta mô tả **aspect**, **pointcut** và **advice**, rồi dùng một cơ chế kết hợp hành vi (**weaving hoặc interception**) để thực hiện chúng tại những **join point** được hỗ trợ.

Câu hỏi kiến trúc quan trọng không chỉ là “advice thực hiện gì?”, mà còn là **“hành vi bổ sung được chèn vào lớp biểu diễn nào của chương trình?”**. Có ba nhóm hình thức rất hữu ích khi phân tích:

1. **Chèn ở mức mã nguồn (source-level transformation/weaving):** biến đổi hoặc sinh mã ở mức ngôn ngữ nguồn trước khi biên dịch.
2. **Chèn ở mức biểu diễn trung gian/mã đã biên dịch (IR/bytecode weaving):** biến đổi cấu trúc biên dịch như abstract syntax representation, intermediate representation, Java bytecode hay định dạng trung gian khác; vị trí chính xác phụ thuộc pipeline.
3. **Chèn vào đường gọi (runtime interception/call routing):** sắp xếp để lời gọi đi qua proxy, decorator, dispatcher, interceptor hoặc chain bao quanh target, thường không cần thay thân bytecode của target.

Ba cách này có thể **tạo trace bề ngoài giống nhau** nhưng khác đáng kể về **phạm vi join point, thời điểm áp dụng, artifact sinh ra, chi phí, cấu hình, khả năng debug và rủi ro bỏ qua advice**.

Mục tiêu của bài:

- Nhận diện rõ **điểm chèn hành vi** trong từng kiến trúc.
- Phân biệt **lớp biểu diễn bị tác động** với **thời điểm weaving**.
- Hiểu khái niệm **join point/pointcut/advice** khi ánh xạ vào nguồn, bytecode hoặc đường gọi.
- Dự đoán khác biệt giữa **method call** và **method execution**, kể cả override, self-invocation, constructor, private/final/static và field access.
- Đánh giá **mã sau biến đổi** và **hành vi runtime** bằng một quy trình kiểm thử có thể lặp.
- Biết khi nào cần source transformation, binary weaving, load-time weaving hay một proxy đơn giản.

Đây là bài về **AOP nói chung**. Không có công cụ AOP nào được xem là quy tắc phổ quát; đặc biệt việc một công cụ hỗ trợ một loại join point không có nghĩa mọi công cụ khác cũng hỗ trợ.

## 2. Ba lớp thể hiện chương trình

Trước hết cần hiểu ranh giới của từng lớp.

### 2.1. Mã nguồn

Đây là những tệp hoặc cấu trúc tương ứng với ngôn ngữ lập trình mà người phát triển có thể đọc và sửa, ví dụ một phương thức Java:

~~~java
class PriceService {
    int quote(int base) {
        return base + 20;
    }
}
~~~

Đoạn này là **minh họa**, không phải chương trình độc lập có phương thức main.

Nếu chèn logging tại nguồn, phần mã mà trình biên dịch nhìn thấy có thể trở thành:

~~~java
class PriceService {
    int quote(int base) {
        System.out.println("trace: begin");
        try {
            return base + 20;
        } finally {
            System.out.println("trace: end");
        }
    }
}
~~~

Phần thứ hai thể hiện **cấu trúc source sau biến đổi ở dạng minh họa**. Một source weaver thật có thể tạo code khác, helper method khác hoặc file nguồn được sinh tự động; không cần tạo chính xác đoạn code trên.

### 2.2. Mã trung gian hoặc bytecode

Chương trình Java thường được biên dịch thành **class file/bytecode** trước khi JVM thực thi. Một công cụ có thể phân tích và biến đổi **representation** này, ví dụ:

~~~text
Bytecode chưa dệt
  → phân tích class / method / control flow
  → xác định join point được hỗ trợ
  → tạo instruction / wrapper / helper phù hợp
  → bytecode sau dệt
~~~

Ở lớp này, mã Java source có thể **không hề thay đổi**, nhưng artifact class hoặc định nghĩa lớp nạp vào JVM đã mang hành vi bổ sung.

**Cẩn thận về thuật ngữ:** “intermediate representation (IR)” là một nhóm khái niệm rộng, bao gồm biểu diễn bên trong compiler, mô hình cây cú pháp, IR dạng control-flow graph, bytecode VM, v.v. Java class-file bytecode là một **dạng biểu diễn biên dịch**, không phải mọi IR đều có định dạng hay ngữ nghĩa như Java bytecode. Công cụ có thể transform một IR compiler rồi sinh bytecode, hoặc sửa chính bytecode đã biên dịch.

### 2.3. Đường gọi khi chạy

Một đối tượng gốc có thể được giữ nguyên, còn caller nhận **đối tượng đại diện** hoặc dùng một dispatcher:

~~~text
Caller → Proxy/Decorator/Interceptor → Target
             │
             ├── before
             ├── delegate / invoke
             └── after/finally
~~~

Hành vi ở đường được định tuyến qua interceptor đã thay đổi. Tuy nhiên nếu có một caller khác **gọi trực tiếp target**, interceptor đó có thể **không được kích hoạt**.

Có thể xem cơ chế này như **kết hợp hành vi tại runtime**. Một số tài liệu gọi rộng là “runtime weaving”, nhưng về mặt kỹ thuật cần nói rõ rằng **routing/interception không đồng nghĩa đã chỉnh sửa bytecode target**.

## 3. Không nhầm lớp chèn với thời điểm chèn

Một lỗi thường gặp là coi **compile-time weaving**, **load-time weaving** và **runtime proxy** đều là ba “nơi chèn” ngang hàng. Thực tế có hai trục phân loại khác nhau:

- **Trục A – tác động vào cái gì?** Source, IR/bytecode, hay đường gọi.
- **Trục B – tác động lúc nào?** Khi sinh source, lúc compile, sau compile, khi load class hoặc khi runtime dựng/điều phối đối tượng.

| Cơ chế thường gặp | Lớp bị tác động | Thời điểm | Tệp nguồn gốc có thể giữ nguyên? |
|---|---|---|---|
| Source transformation | AST/source/generated source | Trước hoặc trong biên dịch | Có, nếu tạo file sinh riêng; không, nếu ghi đè trực tiếp |
| Compiler-integrated IR weaving | IR nội bộ của compiler | Trong compile | Thường có |
| Post-compile/binary weaving | Class/JAR/bytecode đã biên dịch | Sau compile, trước chạy | Có |
| Load-time weaving | Bytecode khi lớp được định nghĩa/nạp | Khi class loading | Có; file class trên đĩa có thể chưa đổi |
| Runtime proxy/decorator | Object graph và đường gọi | Khi tạo proxy/decorator hoặc khi có invocation | Có |

Điểm quan trọng: **load-time weaving vẫn có thể là bytecode weaving**, trong khi **runtime interception có thể không biến đổi bytecode**. Định nghĩa và công cụ cụ thể mới quyết định điều gì xảy ra.

Một ứng dụng cũng có thể dùng **nhiều cơ chế đồng thời**: code generation tạo adapter, binary weaving thêm trace, và một gateway runtime bao quanh các lời gọi nghiệp vụ. Khi đó phải phân biệt từng concern và tầng mà nó được áp dụng.

## 4. Từ pointcut đến hành vi: pipeline khái niệm

Một kiến trúc AOP có thể được mô tả qua bốn pha logic, dù nhiều hệ thống gộp các pha hoặc thực hiện ở thời điểm khác nhau.

~~~text
Đầu vào 1: chương trình gốc
    source / AST / IR / bytecode / objects
                   │
                   ├──────────────────────┐
                   │                      │
Đầu vào 2: aspect                         │
    pointcut + advice + precedence         │
                   │                      │
                   └──────────┬───────────┘
                              ▼
                      Join point matching
                              │
                       Weaving strategy
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
           Source edit     IR/bytecode    Call routing
                │             │             │
                └─────────────┼─────────────┘
                              ▼
                       Woven behavior
                              │
                              ▼
                  Test kết quả và phạm vi
~~~

Trong đó:

1. **Join point model:** công cụ định nghĩa những điểm nào có thể can thiệp, ví dụ method call/execution, field get/set, constructor execution hoặc static initialization.
2. **Pointcut matching:** xác định các điểm khớp theo chữ ký, kiểu, vị trí lexical và điều kiện runtime được hỗ trợ.
3. **Advice composition:** quyết định thứ tự của before/after/around, điều kiện proceed, binding argument/target/exception và tương tác giữa nhiều aspect.
4. **Emission/routing:** tạo nguồn mới, biến đổi mã biên dịch hoặc dựng chuỗi lời gọi.

Một công cụ chỉ intercept các method qua interface proxy có thể không có join point kiểu field read, constructor hoặc static initializer. Do đó **không được lấy danh sách join point của một bytecode weaver làm hợp đồng cho mọi proxy runtime**.

## 5. Chèn hành vi vào mã nguồn

### 5.1. Source weaving thực hiện gì?

Một source-level transformer có thể đọc code, parse thành **abstract syntax tree (AST)**, tìm cấu trúc khớp quy tắc, chèn các node tương ứng với advice, rồi sinh lại source hoặc chuyển AST đã biến đổi vào compiler.

Ví dụ muốn bảo đảm ghi dấu kết thúc cả khi method ném lỗi, transformer có thể tạo cấu trúc tương tự:

~~~java
int calculate(int input) {
    traceStart();
    try {
        return compute(input);
    } finally {
        traceEnd();
    }
}
~~~

Đây là đoạn minh họa không chứa khai báo traceStart/compute/traceEnd. Cấu trúc **try/finally** được chọn nhằm tránh bỏ lỡ traceEnd khi lời gọi bên trong ném ngoại lệ. Nhưng nếu **traceStart tự throw**, phần target chưa chạy; nếu **traceEnd throw**, lỗi từ finally có thể thay thế lỗi ban đầu. Đây vẫn là quyết định về exception policy, không được AOP tự giải quyết.

### 5.2. Pipeline khi dùng source transformation

~~~text
Original Java sources
       │
       ▼
Parser / AST construction
       │
       ▼
Pointcut-like matching ở source/AST
       │
       ▼
AST rewrite hoặc source generation
       │
       ▼
Generated/modified Java sources
       │
       ▼
javac → .class → JVM
~~~

Có ít nhất hai hình thức:

- **Ghi đè tệp nguồn gốc:** trực tiếp thay những file mà người phát triển sửa.
- **Sinh artifact trung gian:** giữ nguồn tác giả nguyên vẹn, tạo tệp sinh trong build output rồi compile chúng.

Thông thường nên tách source tác giả và source generated để dễ review, tránh conflict với công cụ format, tránh sửa nhầm file được người dùng bảo trì. Tuy nhiên việc có nên đưa generated source vào version control tùy quy trình dự án.

### 5.3. Ưu điểm

- Mã sau biến đổi có thể được xem hoặc debug gần với ngôn ngữ nguồn.
- Có thể tận dụng compiler và công cụ phân tích tĩnh của ngôn ngữ.
- Có thể cung cấp diagnostic kèm file/line nếu transformer giữ source mapping tốt.
- Có thể sinh các wrapper hoặc adapter có API rõ mà không cần agent runtime.

### 5.4. Đánh đổi

- Phải parse và sinh code đúng với phiên bản cú pháp ngôn ngữ.
- AST rewrite có thể ảnh hưởng import, generic, annotation, formatting, comments và source location.
- Code sinh có thể gặp collision tên biến/helper và vấn đề phạm vi truy cập.
- Nếu chạy lại một transformer không idempotent, advice có thể bị chèn trùng.
- Build incremental có thể tạo artifact cũ khi đổi pointcut mà không thực hiện lại transform đúng cách.
- Một pointcut có điều kiện runtime vẫn cần sinh mã kiểm tra động; source analysis không thể biết trước mọi giá trị của invocation.

### 5.5. Vấn đề “đổi source là đã weave toàn bộ chưa?”

Không. Nếu cùng một lớp đã biên dịch từ bản nguồn cũ tồn tại trong artifact triển khai, thay source nhưng không build lại sẽ không đổi runtime. Nếu một thư viện bên thứ ba không có source trong pipeline này, transformer source có thể không tác động đến thư viện đó.

Như vậy, coverage phụ thuộc **tập nguồn được xử lý và phiên bản artifact thực sự được chạy**, chứ không chỉ sự tồn tại của một plugin tạo code.

## 6. Chèn hành vi tại biểu diễn trung gian/bytecode

### 6.1. Tại sao chọn lớp biểu diễn này?

Một công cụ có thể cần tác động tới chương trình **đã biên dịch**, chẳng hạn một class được tạo bởi compiler khác hoặc thư viện không được build từ source trong dự án hiện tại. Nếu IR/bytecode chứa thông tin đủ để xác định join point, weaver có thể thực hiện transform ở lớp đó.

Với JVM, class file chứa thông tin như method descriptors, instruction, constant pool, exception tables, stack frames/verification metadata và có thể có annotation/line information. Thao tác đổi bytecode phải giữ các ràng buộc của JVM; không thể chỉ thêm một instruction văn bản mà bỏ qua luồng điều khiển và stack.

### 6.2. Hai vị trí chèn thường gặp

**A. Tại thân method (execution weaving)**

~~~text
Trước:
Method Service.run:
    body instructions
    return

Sau:
Method Service.run:
    advice-before instructions
    body instructions
    advice-after instructions / finally path
    return
~~~

Đây là **mô hình đơn giản hóa**, không phải disassembly thật của một weaver. Khi exception xảy ra, phần after/finally có thể cần các nhánh/handler bổ sung; khi có nhiều return, instrument phải bảo toàn ý nghĩa rời method.

**B. Tại vị trí invocation (call-site weaving)**

~~~text
Trước ở Caller:
    invoke Service.run

Sau ở Caller:
    before-call
    invoke Service.run
    after-call
~~~

Một pointcut chọn **call join point** có thể khiến công cụ instrument **mã caller**, không cần sửa thân Service.run. Ngược lại, execution weaving có thể tác động **bên callee**. Hai chiến lược này không đồng nghĩa về phạm vi.

### 6.3. Compiler IR so với binary bytecode

**IR rewriting trong compiler** có thể làm việc với cấu trúc đã biết về type, control-flow và biểu thức trước khi sinh bytecode. **Post-compile bytecode weaving** làm việc với artifact đã sinh, đôi khi mất một số chi tiết nguồn hoặc có thêm cấu trúc synthetic/bridge do compiler tạo.

Do đó cùng một quy tắc AOP có thể cần kỹ thuật matching khác nhau:

| Vấn đề | IR/compiler-level | Post-compile bytecode |
|---|---|---|
| Type info | Có thể dựa vào hệ thống kiểu của compiler | Dựa descriptor, class metadata, classpath/module context |
| Generic | Có thể thấy generic source-level | Gặp erasure và generic signatures nếu được lưu |
| Lambda | Có thể còn cấu trúc nguồn | Có thể đã biểu diễn qua invokedynamic/synthetic methods |
| Source location | Có thể chính xác hơn | Phụ thuộc debug metadata |
| Code emission | Compiler sinh artifact | Weaver sửa class/JAR hoặc tạo class mới |
| Binary library | Chỉ nếu được đưa vào pipeline thích hợp | Có thể tác động vào artifact binary khi công cụ hỗ trợ |

Không phải mọi công cụ giữ hoặc xử lý cùng một mức semantic information; đây là câu hỏi cần tra cứu theo công nghệ cụ thể.

## 7. Bytecode weaving đòi hỏi điều kiện đúng đắn nào?

### 7.1. Stack và verifier

JVM bytecode dùng operand stack và các quy tắc kiểm tra kiểu. Nếu weaver thêm instruction gọi advice nhưng không giữ tính đúng của stack, local variables hoặc control flow, class có thể bị từ chối ở giai đoạn verify/load.

Những thao tác dễ sai:

- Chèn code vào giữa chuỗi dùng operand stack mà không bảo toàn stack state.
- Đổi control-flow branch mà không cập nhật offset/targets.
- Chèn exception handler không đúng vùng protected.
- Không cập nhật stack map frames, max stack/max locals hoặc metadata cần thiết theo class-file version.
- Gọi helper có descriptor không tương thích với giá trị đang nằm trên stack.

Một bộ thư viện bytecode tốt có thể hỗ trợ tính toán và xác minh các cấu trúc này, nhưng người triển khai vẫn phải hiểu giới hạn của công cụ và mã bị biến đổi.

### 7.2. Exception safety và đường return

Nếu muốn after-finally, phải xử lý cả:

- Return bình thường từ một hoặc nhiều nhánh.
- Exception được ném trong method.
- Exception do advice phát sinh.
- Nhánh có thể bypass một đoạn nếu pointcut chỉ chọn một số instruction.
- Trường hợp target bị skip hoặc retry do around advice.

Một phép thay bytecode chỉ chèn lời gọi after ngay trước một return đầu tiên có thể bỏ sót các nhánh return khác hoặc exceptional exit.

### 7.3. Đặc điểm class đặc biệt

Class có thể chứa bridge/synthetic method, generated code, lambda, constructor chain, static initializer, default interface methods, synchronized methods và các cấu trúc mới theo phiên bản JVM. Bộ dệt phải chọn đúng loại điểm, tránh đếm trùng và tuân theo khả năng hỗ trợ của chính nó.

### 7.4. Class-file version và module boundaries

Weaver phải hiểu class-file version được compiler sinh. Khi JVM hoặc ngôn ngữ phát triển, instrumenter lỗi thời có thể không đọc được format mới.

Module boundaries, class loader, access rules và bytecode verification vẫn tồn tại sau weaving. Không nên cho rằng sửa bytecode tự cấp mọi quyền truy cập Java private hoặc mở các module bị đóng.

### 7.5. Chẩn đoán artifact sau dệt

Các công cụ như **javap** có thể giúp xem disassembly:

~~~bash
javac --release 17 Example.java
javap -c -p Example
~~~

Lệnh trên chỉ là hướng dẫn tổng quát; để chạy phải có file Example.java hợp lệ trong môi trường. **javap không phải bộ dệt**, nó chỉ giúp xem class được compile/đã biến đổi. Nếu muốn so sánh trước và sau, phải lưu hai artifact riêng biệt và dùng đúng classpath phiên bản tương ứng.

Không nên kết luận weaving đúng chỉ vì bytecode có thêm một lời gọi. Còn phải xác minh pointcut match, thứ tự advice, tính đúng kiểu, exception behavior và kết quả runtime.

## 8. Post-compile weaving và load-time weaving

Hai cơ chế này đều có thể tác động vào **bytecode**, nhưng khác thời điểm.

### 8.1. Post-compile hoặc binary weaving

~~~text
Source
  │
  ▼
javac
  │
  ▼
Unwoven .class/.jar
  │
  ▼
Binary weaver + aspects
  │
  ▼
Woven .class/.jar
  │
  ▼
JVM
~~~

Thích hợp khi muốn kiểm soát artifact đã dệt trước deploy. Cần đảm bảo pipeline đóng gói **bản woven** chứ không nhầm bản unwoven. Hash, manifest, artifact provenance hoặc bước kiểm tra build có thể giúp xác nhận đúng hiện vật được đưa vào runtime.

### 8.2. Load-time weaving

~~~text
Source → compiler → original .class/.jar
                               │
                               ▼
                         Class loader
                               │
                     Bytecode transformer
                               │
                               ▼
                     Class definition đã dệt
                               │
                               ▼
                              JVM
~~~

Ở đây file class trên đĩa có thể giữ nguyên, nhưng bytecode dùng để **define class** đã được biến đổi. Vì thế không thể chỉ so file trong JAR rồi kết luận aspect không hoạt động.

Các rủi ro đặc thù:

- Transformer được kích hoạt quá muộn, sau khi một lớp cần weave đã được định nghĩa.
- Class loader khác nạp class nằm ngoài phạm vi cấu hình.
- Aspect/helper class cần được tải đúng nhưng việc tải chúng lại gây reentrancy.
- Transformer của nhiều thư viện cùng tác động, thứ tự transform ảnh hưởng kết quả.
- Instrumentation phiên bản mới không tương thích với bytecode của một thư viện.

Một số runtime còn hỗ trợ khả năng retransform/redefine class theo những giới hạn của nền tảng; không nên giả định có thể bổ sung, xóa hoặc đổi bất kỳ cấu trúc class nào vào bất kỳ lúc nào. Giới hạn phải được xem xét riêng.

## 9. Chèn vào đường gọi bằng proxy, decorator và interceptor

### 9.1. Cấu trúc tổng quát

~~~text
Caller
  │
  ▼
Intercepted reference
  │
  ├─ Before behavior
  │
  ├─ Invocation target
  │
  └─ After/finally behavior
  │
  ▼
Caller nhận result/exception
~~~

Một **proxy** có thể implement một interface, giữ reference target và dùng một invocation handler để xử lý những method được gọi qua proxy. Một **decorator** là object bao ngoài target qua một interface chung và thêm hành vi có chủ đích. Một **interceptor chain** cho phép nhiều thành phần bao quanh cùng invocation.

Đây là **đường gọi đã được lắp ghép**, không phải nhất thiết đã sửa implementation của target.

### 9.2. JDK dynamic proxy

JDK dynamic proxy tạo một object triển khai các interface được khai báo và chuyển invocation qua **InvocationHandler**. Handler thường nhận:

- Object proxy.
- Method đại diện cho method được gọi qua interface.
- Object[] arguments (hoặc null nếu không có đối số).

Nó có thể chạy logic before, gọi method.invoke(target,args), xử lý ngoại lệ và sửa result nếu hợp đồng kiểu cho phép.

Giới hạn thiết yếu:

- Chỉ những invocation **đi qua reference proxy** mới bị handler đó chặn.
- Một caller có reference đến target gốc có thể gọi thẳng, bỏ qua proxy.
- Một lời gọi nội bộ từ target đến method khác trên chính target thường không quay lại proxy.
- Proxy interface không tự biến thành cơ chế chặn constructor, field access hoặc static method.
- Reflection invocation có quy tắc exception wrapper, access và return type riêng.

### 9.3. Decorator

Decorator được viết với interface chung và ủy quyền tới target:

~~~java
interface Action {
    void act();
}

final class AuditAction implements Action {
    private final Action target;

    AuditAction(Action target) {
        this.target = target;
    }

    @Override
    public void act() {
        System.out.println("before");
        try {
            target.act();
        } finally {
            System.out.println("after");
        }
    }
}
~~~

Đây là đoạn Java minh họa, chưa có lớp main. Mã rất rõ ràng, dễ hiểu và không cần một bộ dệt. Tuy nhiên người sử dụng phải **nhận đúng reference decorator**; nếu code khác giữ reference target thì đường đó không bị bao.

### 9.4. Interceptor chain

Có thể tổ chức nhiều hành vi:

~~~text
Caller
  │
  ▼
AuthorizationInterceptor
  │
  ▼
TracingInterceptor
  │
  ▼
MetricInterceptor
  │
  ▼
Target
~~~

**Thứ tự rất quan trọng**. Ví dụ nếu Authorization từ chối không gọi tiếp, tracing nằm bên trong có thể không được kích hoạt. Nếu Tracing nằm ngoài Retry thì metric thời gian khác so với khi Tracing nằm trong mỗi lần retry.

Đừng suy thứ tự theo tên class hay thứ tự file nếu cơ chế interceptor không định nghĩa điều đó. Nếu policy phụ thuộc precedence, cấu hình và test phải thể hiện rõ.

## 10. Java 17 runnable: cùng mối quan tâm, ba đường đưa hành vi vào

Ví dụ sau có một chức năng lõi chuẩn hóa chuỗi thành chữ hoa và bốn cách gọi:

1. **Direct:** gọi target Core trực tiếp, không có hành vi xuyên cắt.
2. **SourceEdited:** mã bao ngoài mô phỏng phần được chèn tại lớp mã nguồn, nhưng được viết thủ công để chạy chỉ với JDK.
3. **Decorator:** caller đi qua object bao ngoài target.
4. **Dynamic proxy:** caller đi qua đối tượng đại diện do JDK tạo.

**Điểm trung thực kỹ thuật:** SourceEdited chỉ là **mô phỏng hình dạng source sau khi chèn**, không phải kết quả do một source weaver tự động sinh ra. Decorator và proxy là đường gọi runtime, **không có phần nào trong demo tự biến đổi Java bytecode**.

Tạo file **WeavingArchitectureDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.Locale;

public class WeavingArchitectureDemo {
    interface Action {
        String apply(String input);
    }

    static final class Core implements Action {
        @Override
        public String apply(String input) {
            System.out.println("core: " + input.trim());
            return input.trim().toUpperCase(Locale.ROOT);
        }
    }

    static final class SourceEdited implements Action {
        private final Action target;

        SourceEdited(Action target) {
            this.target = target;
        }

        @Override
        public String apply(String input) {
            System.out.println("source: before");
            try {
                return target.apply(input);
            } finally {
                System.out.println("source: after");
            }
        }
    }

    static final class Decorator implements Action {
        private final Action target;

        Decorator(Action target) {
            this.target = target;
        }

        @Override
        public String apply(String input) {
            System.out.println("route: before");
            try {
                return target.apply(input);
            } finally {
                System.out.println("route: after");
            }
        }
    }

    static Action proxy(Action target) {
        return (Action) Proxy.newProxyInstance(
                Action.class.getClassLoader(),
                new Class<?>[]{Action.class},
                (proxy, method, args) -> {
                    System.out.println("proxy: before");
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException exception) {
                        throw exception.getCause();
                    } finally {
                        System.out.println("proxy: after");
                    }
                });
    }

    public static void main(String[] args) {
        Action raw = new Core();

        System.out.println("direct:");
        System.out.println("result=" + raw.apply(" alpha "));

        System.out.println("source simulation:");
        System.out.println("result=" +
                new SourceEdited(raw).apply(" beta "));

        System.out.println("decorator:");
        System.out.println("result=" +
                new Decorator(raw).apply(" gamma "));

        System.out.println("proxy:");
        Action intercepted = proxy(raw);
        System.out.println("result=" +
                intercepted.apply(" delta "));

        System.out.println("bypass:");
        System.out.println("result=" +
                raw.apply(" epsilon "));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 WeavingArchitectureDemo.java
java WeavingArchitectureDemo
~~~

Stdout chính xác:

~~~text
direct:
core: alpha
result=ALPHA
source simulation:
source: before
core: beta
source: after
result=BETA
decorator:
route: before
core: gamma
route: after
result=GAMMA
proxy:
proxy: before
core: delta
proxy: after
result=DELTA
bypass:
core: epsilon
result=EPSILON
~~~

### 10.1. Giải thích thứ tự

- Ở **direct**, chỉ có Core.apply, nó in thông báo lõi và trả chuỗi đã chuẩn hóa.
- **SourceEdited** có before/finally được viết sẵn ở lớp bao: đó là cách **mô phỏng ý tưởng source chèn thêm behavior**. Nếu một transformer sinh ra lớp tương tự, artifact source chứa logic đó trước lúc javac xử lý.
- **Decorator** gọi Core qua lớp bao ngoài; kết quả ALPHA/BETA/GAMMA theo đầu vào tương ứng không bị biến đổi ngoài logging.
- **Proxy** chặn invocation đi qua interface Action, chạy before, ủy quyền bằng Method.invoke, in after trong finally, rồi trả result.
- **Bypass** dùng trực tiếp raw nên không có thông báo proxy: before/proxy: after. Điều này làm rõ bản chất **phụ thuộc đường gọi** của cơ chế proxy.

### 10.2. Vì sao cần catch InvocationTargetException?

Reflection API Method.invoke có thể bao exception do method target ném trong **InvocationTargetException**. Handler bắt exception wrapper rồi ném **getCause()** để caller nhận lỗi gốc phù hợp hơn. Ngoài ra JDK proxy có thể bọc một checked exception mà method interface không cho phép truyền ra thành **UndeclaredThrowableException**.

Điểm này cho thấy một interceptor có thể thay **exception behavior** nếu không xử lý đúng, dù chỉ định làm trace. Bytecode weaving cũng phải bảo toàn exception semantics, nhưng cách cài đặt và các wrapper cụ thể có thể khác.

### 10.3. Không kết luận bytecode weaving từ stdout

Các đường trong demo có kết quả tương tự về “log trước/log sau”, nhưng demo **không hề chạy một bytecode weaver**. Để chứng minh bytecode weaving thật, phải chạy compiler/weaver phù hợp trên một artifact đã chọn rồi kiểm tra class/runtime đã dệt, không được chỉ thay tên SourceEdited thành WovenCode.

Ngược lại, một ứng dụng có load-time bytecode weaving có thể tạo stdout tương tự **mà không sinh bất kỳ source file mới nào**.

## 11. So sánh ba vị trí chèn hành vi

| Tiêu chí | Source-level | IR/bytecode-level | Runtime call routing |
|---|---|---|---|
| Điểm tác động chính | Code/AST trước compile | Representation biên dịch hoặc class definition | Đối tượng đại diện, dispatcher, interceptor chain |
| Có cần source target? | Thường cần hoặc cần biểu diễn nguồn | Không nhất thiết, nếu có binary phù hợp | Thường không |
| Có cần rebuild/reweave? | Thường có khi thay rule | Binary weaving có; load-time có thể áp dụng khi định nghĩa lớp | Có thể thay cấu hình/khởi tạo proxy khi runtime |
| Thay class file target? | Có thể tạo class khác sau compile | Có thể có, hoặc chỉ biến đổi lúc load | Không bắt buộc |
| Khả năng chặn direct target call | Có nếu source/đường được biến đổi phù hợp | Có thể nếu execution được weave | Thường không khi bypass proxy |
| Self-invocation | Có thể nếu method execution/đường liên quan đã được chèn | Có thể nếu execution được weave | Thường bỏ qua đường proxy nội bộ |
| Constructor/field/static join points | Phụ thuộc transformer và cú pháp | Phụ thuộc weaver | Proxy method-call không tự hỗ trợ |
| Debug artifact | Generated source/source map | Disassembly/bytecode diagnostics | Proxy chain và runtime reference |
| Rủi ro chính | Source drift, generated code lỗi, build cache | Verify/class loader/compatibility/transformer | Routing bypass, proxy limitations, ordering |
| Thứ tự advice | Do công cụ/composition quyết định | Do công cụ/composition quyết định | Do chain/order quyết định |
| Phù hợp | Build pipeline kiểm soát nguồn | Cần chèn ở lớp đã biên dịch hoặc execution sâu | Chủ động kiểm soát API và đường đi đối tượng |

Bảng là **hướng dẫn tư duy kiến trúc**, không phải ma trận khẳng định tính năng của một sản phẩm cụ thể. Một số công cụ kết hợp nhiều lớp và có khả năng khác bảng điển hình.

## 12. Call join point so với execution join point quyết định nơi chèn

Đây là vấn đề quan trọng nhất khi lựa chọn kiến trúc.

### 12.1. Chọn nơi phát lời gọi

~~~java
class Client {
    void handle(Service service) {
        service.execute();
    }
}
~~~

Đây là đoạn minh họa, thiếu định nghĩa Service. Nếu pointcut chọn **call** ở biểu thức service.execute(), một source/bytecode transformer có thể instrument **Caller.handle**, thậm chí khi Service.execute nằm trong thư viện khác.

Điều đó khác với interceptor proxy: proxy nhận lời gọi sau khi caller đã quyết định reference nào nó đang dùng; nó không nhất thiết biết hay chèn code tại **mọi dòng gọi cụ thể trong source**.

### 12.2. Chọn nơi thực thi

Nếu pointcut chọn **execution** của Service.execute, bộ dệt có thể instrument **thân của method được thực thi**. Bất kể có bao nhiêu caller, lượt thực thi đi vào thân đã dệt đều có thể chạy advice, kể cả lời gọi nội bộ khi compiler/bytecode weaver hỗ trợ.

### 12.3. Call site đa hình

~~~java
Service service = new FastService();
service.execute();
~~~

Kiểu reference tại caller là Service, nhưng runtime dispatch có thể chọn FastService.execute. Một rule chọn call signature có thể nhìn giao diện Service ở caller, còn một rule chọn execution có thể nhìn thân FastService thật được gọi.

Do đó **cùng câu lệnh nguồn** có thể tương ứng một call join point và một execution join point **thuộc kiểu khai báo khác nhau**. Kiểu static, runtime receiver và declaring method đều ảnh hưởng kết quả matching theo ngữ nghĩa của công cụ.

### 12.4. Self-invocation

~~~java
class Service {
    void outer() {
        inner();
    }

    void inner() {
        // Công việc cần quan sát
    }
}
~~~

Một proxy chặn outer khi caller gọi qua proxy nhưng không nhất thiết chặn inner bên trong target. Một execution weaver chèn trực tiếp vào inner có thể quan sát được lời gọi đó. **Giới hạn của proxy không phải định luật của AOP**.

## 13. Có thể chèn tại constructor, field hoặc khởi tạo lớp không?

Cần xét **join point model**, không chỉ thời điểm weave.

- **Constructor call:** biên nơi caller yêu cầu tạo object.
- **Constructor execution:** thân constructor được thực hiện trong chuỗi khởi tạo.
- **Field get/set:** vị trí đọc/ghi trường nếu engine hỗ trợ.
- **Static initialization:** sự kiện lớp được khởi tạo theo JVM.
- **Method execution/call:** hai nhóm join point thường dùng nhất.

Với source hoặc bytecode weaving có hỗ trợ, các điểm trên có thể được biểu diễn thành vị trí chèn cụ thể. Với một **interface proxy** chỉ intercept method, không tự nhiên có field get hay static initialization join point.

Đặc biệt, constructor và static initializer rất nhạy cảm:

- Object có thể chưa có các invariant hoàn chỉnh.
- Lời gọi superclass/subclass có thứ tự quy định.
- Một advice có thể vô tình làm object **escape** trước khi khởi tạo xong.
- Một advice đọc field chưa khởi tạo có thể nhìn thấy giá trị mặc định.
- Class initialization có quy tắc synchronization và failure riêng.

Không nên chèn logic AOP nặng, gọi I/O hoặc tạo dependency vòng ở các giai đoạn này mà không hiểu kỹ hợp đồng khởi tạo.

## 14. Bảo toàn nghĩa khi chèn hành vi

Weaver có thể tạo artifact “biên dịch được” nhưng **đổi hành vi ngoài ý định**. Khi đánh giá kiến trúc, cần tách:

1. **Bảo toàn cấu trúc:** class hợp lệ, method signature phù hợp, control flow hợp lệ.
2. **Bảo toàn chức năng:** giá trị trả về, exception, side effect nghiệp vụ và thứ tự gọi vẫn đúng theo hợp đồng.
3. **Thay đổi có chủ đích:** trace, audit, retry, giới hạn quyền hoặc policy khác thực sự được thực hiện đúng.
4. **Phạm vi áp dụng:** không bỏ sót điểm phải chạy và không áp dụng nhầm điểm ngoài phạm vi.

### 14.1. Before advice

Nếu before chỉ ghi log rồi hoàn tất bình thường, target thường tiếp tục. Nhưng nếu before tự throw, target có thể chưa chạy. Nếu before mutate argument hoặc shared state, kết quả target cũng có thể đổi.

### 14.2. After/finally advice

Nếu muốn log “end” cả khi target throw, cần gắn advice tại các đường rời thích hợp. Ở source dùng try/finally; ở bytecode cần cấu trúc điều khiển/exception tương đương; ở decorator/proxy có thể dùng finally quanh delegate.

Tuy nhiên **finally của advice tự throw** có thể che lỗi gốc. Cần policy về việc ghi nhận secondary failure, không vô ý đổi contract exception.

### 14.3. Around advice

Around có thể thay argument/result, skip target hoặc retry tùy công cụ. Cơ chế chèn phải tuân theo quyền hạn proceed/continuation của engine. Một trình bao runtime có thể gọi target.invoke nhiều lần; một bộ dệt IR có thể tạo control flow tương ứng.

Nếu có retry, phải xét **idempotency**. Việc lặp một thao tác có side effect như gửi tiền, phát thông điệp hoặc ghi đơn hàng có thể gây duplicate behavior.

## 15. Thứ tự của nhiều aspect và nhiều cơ chế

Giả sử có ba concerns: **Authorization**, **Tracing** và **Retry**. Thứ tự lồng nhau có thể làm khác ý nghĩa:

~~~text
Tracing(Retry(Core))
    Trace thấy một thao tác gồm nhiều lượt thử.

Retry(Tracing(Core))
    Trace có thể thấy từng lượt thử.
~~~

Nếu Authorization nằm ngoài Retry, quyền được kiểm tra trước toàn bộ chuỗi retry; nếu nằm trong, quyền có thể được kiểm tra ở mỗi attempt. Cách nào đúng phụ thuộc chính sách.

Khi hệ thống dùng cả bytecode weaving và proxy:

~~~text
Caller → Proxy interceptor → Target class có bytecode đã dệt
                               │
                               └─ Advice trong woven execution
~~~

Một invocation qua proxy có thể kích hoạt **hai lớp advice**. Nếu cả hai cùng ghi metric “một request” mà không có deduplication, số đếm có thể gấp đôi.

Cần có **bản đồ trách nhiệm concern**: concern nào do source-generated code xử lý, concern nào do bytecode weaver, concern nào do interceptor runtime. Đừng dựa vào tên logger giống nhau để suy ra chúng thuộc cùng một điểm.

## 16. Khi nào nên dùng kiến trúc nào?

### 16.1. Nghiêng về source transformation nếu

- Bạn kiểm soát build pipeline và nguồn cần chuyển đổi.
- Cần generated code dễ review, kiểm tra hoặc dùng công cụ compiler tĩnh.
- Chấp nhận build lại để thay aspect.
- Có chiến lược tránh source drift và duplicate injection.
- Phạm vi là phần source nằm trong hệ thống kiểm soát.

### 16.2. Nghiêng về IR/bytecode weaving nếu

- Cần tác động tại **execution** hoặc call site mà caller không nhất thiết đi qua một proxy.
- Cần hỗ trợ một loại join point nằm sâu trong class, ví dụ field access/constructor, và công cụ thật có capability đó.
- Có artifact binary hoặc class không thuộc nguồn bạn muốn sửa.
- Có khả năng kiểm soát bytecode version, verification, class loader và artifact deployment.
- Chấp nhận đầu tư cho test tích hợp, chẩn đoán và toolchain compatibility.

### 16.3. Nghiêng về runtime interceptor nếu

- Có thể **kiểm soát đường tạo và phân phối object reference**.
- Phần lớn concern nằm tại public API/interface hoặc boundary rõ.
- Muốn composition động, dễ bật/tắt hoặc sắp xếp interceptor chain.
- Không cần quan sát constructor, field access hoặc mọi self-invocation trong target.
- Muốn giảm độ phức tạp của binary instrumentation.

### 16.4. Khi không cần AOP

Nếu logic chỉ áp dụng cho một method và là phần rõ ràng của hợp đồng nghiệp vụ, một helper, decorator hoặc đối tượng cộng tác có thể dễ đọc hơn. Không nên đưa mọi biến đổi vào aspect chỉ để “không phải viết thêm một dòng code”.

**Nguyên tắc:** lựa chọn kiến trúc theo **phạm vi join point cần bao phủ** và **mức minh bạch/khả năng vận hành**, không chọn theo việc demo có in dòng before/after giống nhau hay không.

## 17. Chẩn đoán “advice không chạy” theo lớp chèn

### 17.1. Source-level

Kiểm tra:

1. Tệp nguồn nào được transformer chọn?
2. Generated source có được tạo từ phiên bản aspect mới nhất?
3. Mã được chèn nằm đúng method và đủ mọi nhánh?
4. Build có compile từ generated source thay vì original source?
5. Incremental build có bỏ qua bước transform không?
6. Có chèn trùng khi chạy transformer nhiều lần không?

### 17.2. Binary weaving

Kiểm tra:

1. Class/JAR input nào thực sự được dệt?
2. Pointcut chọn call site hay execution?
3. Artifact đóng gói có phải bản woven?
4. Weaver có hỗ trợ class-file version được dùng?
5. Các class cần thiết thuộc class loader/module nào?
6. Bytecode verifier hoặc runtime có báo lỗi không?
7. Advice precedence có khiến phần liên quan không chạy không?

### 17.3. Load-time weaving

Kiểm tra thêm:

1. Transformer đã được đăng ký trước khi class cần weave được định nghĩa chưa?
2. Class nào đã load trước khi thiết lập cấu hình?
3. Có class loader khác dùng cùng tên class nhưng định nghĩa khác không?
4. Có nhiều transformer cùng sửa một class không?
5. Định nghĩa runtime có thực sự chứa instrumented behavior không?

### 17.4. Runtime proxy

Kiểm tra:

1. Caller đang giữ **proxy** hay **target gốc**?
2. Method có thuộc tập được proxy expose/chặn không?
3. Caller có gọi **self-invocation** bên trong target không?
4. Target có được tạo trực tiếp ngoài factory/interceptor chain không?
5. Có class/proxy/interface khác với assumption của pointcut không?
6. Around interceptor bên ngoài có short-circuit trước khi đến advice bên trong không?

## 18. Kiểm chứng kiến trúc theo hai hướng: artifact và hành vi

**Kiểm tra artifact** trả lời: “Điều gì đã được biến đổi ở source/bytecode/đường object?”. **Kiểm tra hành vi** trả lời: “Advice có thực sự chạy ở những lần sử dụng mà chính sách yêu cầu không?”. Cần cả hai khi bảo đảm quan trọng.

### 18.1. Baseline trước weaving

Tạo test trên lớp gốc không có advice:

- Kết quả nghiệp vụ đúng.
- Exception được ném đúng.
- Side effect và số lần gọi đúng.
- Đường đồng thời/bất đồng bộ đã được đại diện nếu liên quan.

### 18.2. Kiểm chứng pointcut match

Tạo danh sách **join point phải khớp** và **không được khớp**. Kiểm tra cả:

- Method của superclass và override ở subclass.
- Method được kế thừa nhưng không override.
- Overload và generic bridge nếu quan trọng.
- Caller khác nhau ở call join point.
- Gọi nội bộ và gọi trực tiếp target.
- Method không thuộc vùng weave/không đi qua proxy.

### 18.3. Kiểm tra thứ tự và số lần

Ghi correlation ID và join point kind trong trace thử nghiệm. Với một request, phân biệt:

~~~text
call join point
execution join point
nested helper
retry attempt
after / exception path
~~~

Một metric “advice chạy 4 lần” không tự nghĩa target chạy 4 lần; có thể bốn join point khác nhau được chọn. Ngược lại target có thể chạy nhiều lần qua retry trong khi một interceptor ngoài chỉ log một lần.

### 18.4. Kiểm chứng lỗi

Thử ba ca độc lập:

1. **Advice trước ném lỗi**: target có được gọi không?
2. **Target ném lỗi**: advice finally/after throwing có hoạt động đúng không?
3. **Advice sau ném lỗi**: caller nhận lỗi nào? Có vô ý che lỗi target không?

Nếu có load-time weaving, các lỗi xảy ra lúc khởi tạo lớp cũng cần test riêng vì failure có thể làm class không khởi tạo thành công.

## 19. Ma trận test đề xuất

| Tình huống | Source transform | IR/bytecode | Proxy/route |
|---|---|---|---|
| Method được chọn từ caller thông thường | Đúng nếu source đã transform | Đúng nếu điểm được weave | Đúng nếu caller dùng proxy |
| Method không thuộc phạm vi pointcut | Không chèn | Không chèn | Không kích hoạt interceptor |
| Self-invocation | Phụ thuộc vị trí source được chèn | Có thể quan sát execution được weave | Thường không quay lại proxy |
| Caller giữ target gốc | Source target đã đổi thì vẫn có behavior | Execution target đã weave thì vẫn có behavior | Có thể bypass |
| Override ở subclass | Phải transform đúng thân cần chọn | Phải weave đúng implementation | Phải kiểm tra đường proxy và method exposed |
| Constructor/field access | Phụ thuộc transformer | Phụ thuộc join point model của weaver | Method proxy không tự bao |
| Target throw | Finally/advice exception đúng | Bytecode handler đúng | Handler/decorator xử lý đúng |
| Class loader khác | Generated source/class có áp dụng không? | Weaver/transformer có bao phủ loader không? | Reference proxy có được phân phối không? |
| Hai aspect cùng khớp | Thứ tự composition đúng | Precedence/bytecode output đúng | Interceptor chain order đúng |
| Phiên bản công cụ mới | Generated source còn biên dịch? | Class-file format còn tương thích? | API/interceptor contract còn tương thích? |
| Build/deploy | Compile generated artifact đúng | Đóng gói đúng binary woven | Wiring object graph đúng |

Bảng mô tả **câu hỏi cần kiểm chứng**, không hứa hẹn mọi source/IR weaver hỗ trợ tất cả loại điểm. Một bộ dệt cụ thể có thể không có khả năng xử lý một số trường hợp.

## 20. Rủi ro vận hành và bảo mật

### 20.1. Side effect và leak dữ liệu

Advice có thể nhận argument và target, rồi ghi log toàn bộ object. Đây là nguy cơ lộ thông tin nếu object chứa credential/token hoặc dữ liệu nhạy cảm. Vị trí chèn không tự quyết định dữ liệu nào được phép ghi.

### 20.2. Khả năng quan sát và debug

Generated source dễ nhìn nhưng có thể làm stack trace lệch nguồn tác giả. Bytecode instrumentation có thể thay method size, thêm synthetic frames và ảnh hưởng thông tin nguồn. Proxy tạo thêm lớp call stack và exception wrappers. Các khác biệt này cần được hỗ trợ bằng log có cấu trúc, source mapping và quy trình debug được ghi nhận.

### 20.3. Hiệu năng

Chi phí phụ thuộc số join point khớp, động tác advice, allocation, serialization, logging I/O, reflection, dynamic dispatch và caching. Source/bytecode weaving có thể tránh một số lớp delegation nhưng vẫn có overhead; proxy có thể được JVM tối ưu ở các mức độ khác nhau.

Không kết luận “bytecode luôn nhanh hơn proxy” chỉ từ hình dạng kiến trúc. Phải đo theo workload, tần suất gọi, latency và chi phí của chính concern.

### 20.4. Class loading và vòng phụ thuộc

Một load-time transformer dùng logging library mà logging library lại nằm trong tập lớp bị transform có thể gây recursion/class initialization problems. Cần giới hạn phạm vi, kiểm tra thứ tự nạp và tránh advice có dependency vòng.

### 20.5. Vùng quyền hạn

Một source transformer hoặc bytecode weaver có khả năng chèn mã rộng nên có thể tạo ảnh hưởng lớn nếu quy tắc pointcut sai. Cần code review, test tự động, kiểm soát artifact và nguyên tắc giới hạn quyền của helper. Một proxy policy có thể bị bỏ qua nếu object graph không được kiểm soát. Cả hai đều cần thiết kế boundary rõ ràng.

## 21. Những hiểu lầm phổ biến

**Hiểu lầm 1 — “Weaving luôn sửa file nguồn Java.”** Binary/load-time weaving có thể thay bytecode hoặc định nghĩa class mà source vẫn nguyên.

**Hiểu lầm 2 — “Load-time weaving và proxy là một.”** Load-time weaving có thể sửa bytecode lúc define class; proxy chủ yếu thay đường gọi qua object đại diện.

**Hiểu lầm 3 — “Có log before/after chứng minh bytecode đã bị dệt.”** Decorator hoặc proxy cũng có thể tạo cùng log. Cần kiểm tra artifact/cơ chế.

**Hiểu lầm 4 — “Pointcut chọn một tên method thì mọi lời gọi đều được chặn.”** Phải xét call/execution, subtype, visibility, vùng weave và routing.

**Hiểu lầm 5 — “Proxy bắt được mọi self-invocation.”** Thường không khi target tự gọi method trên chính nó mà không qua proxy.

**Hiểu lầm 6 — “Sửa bytecode là chỉ thêm vài instruction.”** JVM verifier, control-flow, exception tables, stack frames và class-file format là những ràng buộc thực.

**Hiểu lầm 7 — “Source transformation luôn cần chỉnh sửa file do người dùng viết.”** Có thể sinh file trung gian và giữ nguyên bản tác giả.

**Hiểu lầm 8 — “Class trên đĩa không thay đổi nghĩa là load-time advice không chạy.”** Bytecode có thể được biến đổi chỉ ở lúc class definition.

**Hiểu lầm 9 — “Aspect thứ tự nào cũng như nhau.”** Around/precondition/retry/metric có thể thay semantics khi thứ tự lồng khác nhau.

**Hiểu lầm 10 — “Instrument quá rộng chỉ ảnh hưởng hiệu năng.”** Nó còn có thể làm đổi exception, làm rò dữ liệu, tạo recursion hoặc tác động class initialization.

**Hiểu lầm 11 — “Chỉ kiểm tra source hoặc bytecode đã đủ.”** Artifact có thể đúng nhưng caller vẫn dùng đường bypass; cần kiểm chứng hành vi thật.

**Hiểu lầm 12 — “Công nghệ đã dệt rồi thì mọi rule nghiệp vụ có thể đặt trong advice.”** Một invariant miền quan trọng cần hợp đồng và test rõ ràng, tránh phụ thuộc ẩn vào cấu hình weave.

## 22. Quy trình lựa chọn cơ chế chèn cho một dự án

1. **Xác định concern.** Là trace/metrics, audit bắt buộc, cache/retry hay chính sách có khả năng từ chối thao tác?
2. **Xác định join point thật sự cần.** Public method, execution nội bộ, method call tại caller, constructor hay field?
3. **Xác định phạm vi mã kiểm soát.** Có source? Có binary? Có khả năng kiểm soát object reference?
4. **Đặt yêu cầu bao phủ.** Mọi caller, chỉ một API, cả self-invocation, thư viện ngoài hay class loader đặc biệt?
5. **Chọn lớp chèn.** Source nếu quản lý build/source, bytecode nếu cần điểm sâu hoặc binary, runtime route nếu có boundary object rõ.
6. **Chọn thời điểm.** Generate source, compile, post-compile, load-time hoặc tạo interceptor runtime.
7. **Thiết kế precedence và lỗi.** Advice có được throw/skip/retry không? Tầng nào chịu trách nhiệm final cleanup?
8. **Làm demo tối thiểu.** Có một target, một join point, một advice và baseline kiểm chứng được.
9. **Thử ca biên.** Ngoại lệ, overload, override, self-call, target bypass, nhiều aspects và concurrent calls.
10. **Đưa vào pipeline vận hành.** Với binary weaving lưu provenance artifact, với source transform kiểm tra generated sources, với proxy kiểm soát object graph.
11. **Đo hiệu năng và mức độ quan sát.** Thử workload thật, không chỉ xem stdout.
12. **Viết regression tests.** Tập điểm match và số advice invocation phải còn đúng sau refactor hoặc đổi toolchain.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Source gốc không có System.out.println nhưng lúc chạy có log trước method. Có thể khẳng định source transformer đã chạy không?

**Đáp:** Không. Log có thể đến từ bytecode weaving, load-time transformation, proxy, decorator hoặc một đường khác.

**Câu 2.** Class file trên đĩa nguyên vẹn nhưng runtime đã có advice được chèn vào method execution. Có thể xảy ra không?

**Đáp:** Có. Load-time weaving có thể biến đổi bytecode khi lớp được định nghĩa mà không ghi lại file class trên đĩa.

**Câu 3.** Một caller sử dụng reference target gốc thay vì proxy. Handler của proxy có chạy không?

**Đáp:** Không trong mô hình chỉ intercept qua reference proxy ấy. Dynamic dispatch Java vẫn diễn ra nhưng không đi qua handler.

**Câu 4.** Muốn chặn mọi method execution của một thư viện đã biên dịch mà không điều khiển caller, tại sao binary weaving có thể thích hợp hơn proxy?

**Đáp:** Nó có thể tác động trực tiếp đến thân đã biên dịch nếu công cụ hỗ trợ và lớp thuộc phạm vi weave, trong khi proxy phụ thuộc caller được định tuyến qua đối tượng đại diện.

**Câu 5.** Tại sao bytecode weaver cần xem xét stack map frames và exception handlers?

**Đáp:** Việc chèn instruction phải tạo class hợp lệ với JVM verifier và giữ đúng các đường điều khiển, kể cả exceptional exit.

**Câu 6.** Nếu source transformer chèn finally một lần nhưng chạy lại transformer và chèn thêm lớp finally giống hệt, trace có thể ra sao?

**Đáp:** Có thể xuất hiện advice trùng hoặc lồng nhau. Transformer cần cơ chế tránh tái chèn ngoài ý định hoặc pipeline dùng source gốc bất biến.

**Câu 7.** Hai lần gọi method thông qua hai caller khác nhau nhưng cùng target. Execution weaving và call-site weaving có nhất thiết thấy cùng một tập điểm không?

**Đáp:** Không. Execution nhìn thân được thực thi, call-site nhìn những vị trí caller được weave; phạm vi và chữ ký có thể khác nhau.

**Câu 8.** Hai interceptor được xếp theo thứ tự Tracing(Retry(Core)) và Retry(Tracing(Core). Kết quả số event trace có thể khác nhau không?

**Đáp:** Có. Tracing ngoài retry có thể thấy một chu kỳ tổng, Tracing bên trong có thể thấy từng attempt.

**Câu 9.** Khi nào một decorator minh bạch có thể phù hợp hơn một bytecode weaver?

**Đáp:** Khi boundary nhỏ, reference có thể kiểm soát được và cần logic bao rõ ràng, dễ debug mà không yêu cầu instrument method nội bộ/constructor/field.

**Câu 10.** Để xác nhận AOP hoạt động đúng, kiểm tra mỗi việc “có thêm lời gọi advice trong bytecode” đã đủ chưa?

**Đáp:** Chưa. Cần kiểm tra matching chính xác, runtime invocation, exception/return contract, thứ tự, số lượt và các đường không được khớp.

## 24. Sơ đồ ghi nhớ

~~~text
           ASPECT = POINTCUT + ADVICE
                      │
                      ▼
                Chọn JOIN POINT
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
     SOURCE/AST    IR/BYTECODE   CALL ROUTE
        │             │           │
     Rewrite      Transform     Proxy / decorator
     trước      trong/sau      / interceptor chain
     compile     compile/load        │
        │             │           │
        └─────────────┼───────────┘
                      ▼
               WOVEN BEHAVIOR
                      │
                      ▼
          KIỂM CHỨNG BẰNG ARTIFACT
          + ĐƯỜNG THỰC THI THẬT
~~~

**Điểm ghi nhớ cuối:** “chèn hành vi” có thể diễn ra tại **source**, **mã trung gian/bytecode** hoặc **đường gọi runtime**. Đừng suy cơ chế từ log bên ngoài. Hãy xác định **lớp biểu diễn được tác động**, **thời điểm áp dụng**, **join point được hỗ trợ**, **đường gọi có được bao phủ** và **kết quả đối chiếu với hợp đồng nghiệp vụ**. Đó là nền tảng để thiết kế weaving đáng tin, kiểm thử được và có khả năng vận hành.

## Tài liệu đối chiếu

- [Java Virtual Machine Specification, Java SE 17 – Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): cấu trúc class file, bytecode và metadata cần được giữ hợp lệ.
- [Java Virtual Machine Specification, Java SE 17 – Loading, Linking, Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): vòng đời định nghĩa/nạp class và những ràng buộc liên quan đến load-time instrumentation.
- [Java SE 17 – Instrumentation API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): API hỗ trợ transformer, khả năng retransform/redefine và giới hạn của nền tảng.
- [Java SE 17 – InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): một cơ chế runtime interception dùng trong ví dụ Java.
- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): tài liệu tham khảo về mô hình join point, pointcut, advice, static/dynamic weaving của một ngôn ngữ AOP cụ thể.