# Cách bộ dệt tìm điểm phù hợp với pointcut trong kiến trúc AOP

## 1. Đặt vấn đề: từ một quy tắc pointcut đến những chỗ advice thực sự chạy

Trong **Aspect-Oriented Programming (AOP)**, **pointcut** là quy tắc chọn những **join point** cần được áp dụng **advice**. Join point là điểm trong mô hình thực thi được cơ chế AOP hỗ trợ, chẳng hạn một lần gọi phương thức, thực thi phương thức hoặc truy cập trường dữ liệu, tùy công cụ.

**Weaver (bộ dệt)** là thành phần phối hợp mã ứng dụng với hành vi aspect. Một câu hỏi kiến trúc quan trọng là: **bằng cách nào bộ dệt biết một biểu thức pointcut áp dụng ở những nơi nào trong chương trình?**

Ví dụ một yêu cầu bằng ngôn ngữ tự nhiên:

> Đo thời gian của các thao tác thanh toán, chỉ khi số tiền vượt một ngưỡng, nhưng không đo thao tác chẩn đoán.

Yêu cầu này gồm hai loại thông tin:

- **Thông tin cấu trúc**: tên/chữ ký phương thức, loại join point, kiểu khai báo, vùng mã hoặc metadata. Nhiều phần có thể phân tích trước lúc chạy.
- **Thông tin từng lần chạy**: số tiền thực tế, đối tượng đích hoặc ngữ cảnh điều khiển. Phải đánh giá ở thời điểm thích hợp khi join point thực sự xảy ra.

Bộ dệt thường không “quét toàn bộ chương trình rồi chạy advice cho mọi thứ” một cách mù quáng. Nó phải xác định những **điểm có khả năng khớp**, biểu diễn hoặc chèn cách kiểm tra điều kiện cần thiết, và kết hợp advice vào các ranh giới mà công cụ **thực sự có thể can thiệp**.

**Phạm vi bài:** kiến trúc weaving và cơ chế chọn điểm trong AOP nói chung, từ nền tảng đến các tình huống nâng cao. Không có một thuật toán hay API duy nhất bắt buộc cho tất cả công cụ AOP. Những pipeline bên dưới là **mô hình khái niệm**, còn cách hiện thực phụ thuộc ngôn ngữ, compiler, bytecode, class loader, runtime và loại interception.

## 2. Các khái niệm cần phân biệt trước khi tìm điểm

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Aspect** | Mô-đun chứa logic của một mối quan tâm xuyên suốt | Kiểm toán thao tác |
| **Advice** | Đoạn hành vi được kết hợp tại điểm được chọn | Ghi trước/sau, bao quanh lời gọi |
| **Join point** | Điểm/sự kiện có thể can thiệp thuộc mô hình thực thi | Một lần thực thi `pay()` |
| **Join-point shadow** | Vị trí cấu trúc có thể phát sinh join point khi chạy trong những mô hình dùng khái niệm này | Phần thực thi `pay` hoặc một call site |
| **Pointcut** | Điều kiện chọn các join point | Chọn execution của phương thức thuộc nhóm thanh toán |
| **Static match** | Kết quả kiểm tra từ dữ liệu cấu trúc | Chữ ký có tên `pay`, số tham số phù hợp |
| **Dynamic guard/residue** | Điều kiện còn phải quyết định khi chạy | `amount > 1000` |
| **Weaving** | Kết hợp lời gọi/logic advice với chương trình | Biến đổi bytecode, biên dịch, hoặc cấu trúc chặn lời gọi |
| **Target/subject** | Mã, đối tượng hoặc thao tác được can thiệp | Dịch vụ xử lý thanh toán |

Từ **shadow** hữu ích vì một vị trí tĩnh có thể được đi qua nhiều lần:

```java
for (int i = 1; i <= 3; i++) {
    gateway.pay(i * 100L);
}
```

Đây là mảnh mã minh họa, giả định `gateway` đã được khai báo. Trong một mô hình hỗ trợ method-call join point, **một vị trí gọi** có thể phát sinh **ba lần xuất hiện động**. Nếu pointcut phụ thuộc giá trị số tiền, ba lần xuất hiện có thể nhận ba kết quả kiểm tra khác nhau.

Đừng đồng nhất “một vị trí mã khớp” với “advice chỉ chạy đúng một lần”.

## 3. Sơ đồ pipeline khái niệm của bộ dệt

Có thể hình dung quá trình bằng một chuỗi bước:

```text
Nguồn mã / bytecode / metadata      Khai báo aspect + pointcut
               |                               |
               v                               v
       Phân tích chương trình           Phân tích biểu thức
               |                               |
               +--------------+----------------+
                              |
                              v
                  Xây mô hình các điểm
                  có thể can thiệp (shadows)
                              |
                              v
                Khớp điều kiện tĩnh
                    /       |       \
                  NO       MAYBE     YES
                   |         |        |
                bỏ qua       |        |
                             v        v
                     Chuẩn bị guard /
                       binding runtime
                              |
                              v
                  Kết hợp advice / tạo
                   đường interception
                              |
                              v
                  Chương trình thực thi
                              |
                              v
               Guard động (nếu cần)
                  /             \
               không khớp       khớp
                  |               |
            tiếp tục thường   áp dụng advice
```

**YES / NO / MAYBE chỉ là mô hình suy luận minh họa**, không phải tên trạng thái hoặc giao diện bắt buộc trong mọi bộ dệt. Một engine có thể có nhiều tầng phân tích, dùng tối ưu compiler, dùng cấu trúc nội bộ khác hoặc trì hoãn một phần công việc đến runtime.

Mỗi bước giải quyết một câu hỏi:

1. **Pointcut muốn chọn gì?**
2. **Mã nào có những điểm can thiệp tương ứng?**
3. **Đặc điểm tĩnh nào đủ để loại bỏ hoặc xác nhận điểm?**
4. **Còn điều kiện nào phải đánh giá theo invocation?**
5. **Advice được kết hợp vào đường thực thi bằng cách nào?**
6. **Khi chạy, điểm đó có thực sự xuất hiện và thỏa điều kiện không?**

Nếu hiểu sáu câu hỏi này, người học có thể phân tích cả cơ chế weaving tĩnh và cơ chế chặn lời gọi bằng đối tượng trung gian mà không nhầm phạm vi hỗ trợ.

## 4. Bước 1 — Phân tích cú pháp và biểu diễn pointcut

Một pointcut được viết ở dạng văn bản, annotation hoặc cấu trúc cấu hình nào đó. Trước khi so khớp, bộ máy cần hiểu **ý nghĩa** của biểu thức đó.

Ví dụ dưới đây là **mã giả trung lập công cụ**, không phải cú pháp DSL bắt buộc:

```text
pointcut auditedOperations =
    executionOf(PaymentService.pay)
    OR executionOf(RefundService.refund)

pointcut largeAuditedOperations =
    auditedOperations
    AND runtimeAmountGreaterThan(1000)
```

Một biểu thức như vậy có thể được diễn giải thành **cây biểu thức (abstract syntax tree — AST)**:

```text
AND
├── OR
│   ├── EXECUTION(signature: PaymentService.pay)
│   └── EXECUTION(signature: RefundService.refund)
└── RUNTIME_GUARD(amount > 1000)
```

Để sử dụng AST, một bộ dệt có thể phải:

- Phân tích token và cấu trúc ngoặc/toán tử.
- Kiểm tra biểu thức có hợp cú pháp không.
- Giải quyết tên kiểu và thành viên về các thực thể của chương trình.
- Kiểm tra tính tương thích giữa designator và loại join point.
- Xác định biến được bind từ ngữ cảnh join point, nếu DSL có binding.
- Biểu diễn biểu thức dưới dạng thuận lợi cho tối ưu và so khớp.

Ví dụ, một điều kiện đòi **đối tượng đích** có thể không có ý nghĩa tại loại join point không mang đối tượng tương ứng. Một trình kiểm tra tốt nên phát hiện các tổ hợp không hợp lệ hoặc xử lý chúng theo quy tắc đã định.

### 4.1. Tên phương thức không phải định danh đầy đủ

Trong Java, `pay(String)` và `pay(String,long)` là overload khác nhau. Mẫu chứa tên `pay` và wildcard tham số có thể chọn cả hai, nhưng một mẫu ràng buộc `(String,long)` có phạm vi hẹp hơn.

Tương tự, kiểu khai báo, phạm vi package, modifier, kiểu trả về và quan hệ kế thừa có thể là một phần của dữ liệu so khớp. Bộ dệt không nên coi mọi method có cùng tên là cùng một điểm.

### 4.2. Cú pháp công cụ không đồng nhất

Một số DSL AOP có toán tử logic, mẫu tên/kiểu, điều kiện ngữ cảnh và pointcut được đặt tên. Một số API interception chỉ cho phép danh sách phương thức hoặc annotation. **Khả năng biểu diễn pointcut phụ thuộc công cụ**: không thể đưa một biểu thức từ DSL này sang DSL khác và cho rằng cú pháp lẫn ý nghĩa giữ nguyên.

Điều quan trọng ở mức kiến trúc là bước **biến khai báo chọn điểm thành một biểu diễn có thể kiểm tra**.

## 5. Bước 2 — Xây danh mục điểm có khả năng can thiệp

Sau khi hiểu pointcut, bộ dệt phải biết **các điểm join point mà chương trình và công cụ có thể tạo ra**.

Tùy thời điểm và dạng weaving, việc này có thể dựa trên:

- **AST nguồn:** compiler nhìn thấy định nghĩa hàm, biểu thức gọi, trường, constructor và vị trí handler.
- **Bytecode/trung gian:** thao tác đọc instruction, method descriptor, thông tin class và các metadata còn giữ sau biên dịch.
- **Reflection hoặc metadata runtime:** bộ chặn xét những method mà đối tượng trung gian biết cách chuyển tiếp.
- **Cấu trúc runtime riêng:** trình thông dịch hoặc runtime AOP có thể đưa join point vào mô hình thực thi của nó.

Không phải tất cả nguồn này có cùng khả năng quan sát.

### 5.1. Ví dụ hai loại điểm khác nhau

```java
class Checkout {
    void run(Gateway gateway) {
        gateway.charge(2000L);
    }
}

class Gateway {
    void charge(long amount) {
        System.out.println(amount);
    }
}
```

Đây là đoạn code minh họa, chưa có `main`. Có ít nhất hai góc nhìn nếu công cụ hỗ trợ:

1. **Method-call shadow:** vị trí biểu thức `gateway.charge(2000L)` trong `Checkout.run`.
2. **Method-execution shadow:** phần thực thi của `Gateway.charge(long)`.

Một bộ dệt chọn `call` có thể phải xem **những vị trí lời gọi**, còn một bộ dệt chọn `execution` quan sát **ranh giới thực thi thân phương thức**.

Nếu chỉ dùng proxy giao diện, công cụ thường chỉ chặn được **những lời gọi đi qua proxy**. Nó không tự tìm và sửa mọi bytecode method-call site như một bộ dệt bytecode đầy đủ.

### 5.2. “Ứng viên” không có nghĩa đã khớp

Nếu chương trình có 10.000 method executions và pointcut chỉ chọn `PaymentService.pay`, 9.999 method khác có thể bị loại ở các bước đầu. Trong thực tế, compiler và index có thể dùng tên kiểu/phương thức để giảm số điểm cần xem xét, thay vì kiểm tra mọi chi tiết của mọi instruction theo một thứ tự cố định.

Tập ứng viên do mô hình join point quyết định trước khi pointcut kiểm tra sâu. Một công cụ không hỗ trợ field-read join point sẽ không thể tự tạo interception cho mọi lần đọc field chỉ nhờ biểu thức pointcut có từ “field”.

## 6. Bước 3 — So khớp tĩnh: loại nhanh điểm không phù hợp

Một phần lớn pointcut có thể kiểm tra bằng metadata không phụ thuộc dữ liệu từng invocation:

| Điều kiện tĩnh | Dữ liệu có thể dùng để so khớp |
| --- | --- |
| Loại join point | Method call, method execution, constructor execution… |
| Tên/chữ ký | Tên, số lượng và kiểu tham số, kiểu trả về |
| Kiểu khai báo | Class/interface, quan hệ kế thừa phù hợp |
| Modifier | `public`, `private`, `static`… nếu loại mẫu hỗ trợ |
| Package/vùng mã | Namespace, declaring type, vị trí từ vựng |
| Annotation/metadata | Dấu đánh dấu đã có ở cấu trúc mã phù hợp |
| Vị trí mã nguồn | Tên file/dòng, nếu công cụ giữ và hỗ trợ |
| Ngữ cảnh mã bao quanh | Phương thức hay kiểu chứa call site |

Ví dụ pointcut theo ý nghĩa:

```text
kind == METHOD_EXECUTION
AND declaringType belongsTo package "example.payment"
AND methodName startsWith "charge"
AND parameterTypes == [String, long]
```

Đây là mã giả; với một method có chữ ký `charge(String,long)` trong đúng vùng kiểu, các điều kiện tĩnh có thể xác nhận khả năng khớp mà không cần biết `String id` và `long amount` đang chứa giá trị gì.

Một method `healthCheck()` có thể bị loại ngay theo tên. Một method `charge(String)` có thể bị loại theo số và kiểu tham số.

### 6.1. Ý nghĩa của so khớp tĩnh

Để giảm chi phí runtime, bộ dệt cố gắng:

- **Loại (definitely no):** vị trí không thể thỏa.
- **Xác nhận đủ bằng metadata (definitely yes):** không còn điều kiện động tại điểm đó.
- **Giữ làm ứng viên động (maybe):** vị trí đúng loại/chữ ký nhưng kết quả còn phụ thuộc dữ liệu runtime.

Một số công cụ có thể dùng phân tích khác, không phơi bày trạng thái “maybe”. Nhưng cách suy luận “biết chắc / không thể / cần kiểm tra khi chạy” là rất hữu ích.

### 6.2. So khớp static không phải thực thi advice

Nếu method thuộc tập khớp tĩnh nhưng chương trình không bao giờ gọi nó, sẽ không có lần chạy advice tương ứng. Nếu điểm chạy nhiều lần, advice có thể chạy nhiều lần. Nếu còn điều kiện động, một số lần có thể bị loại.

## 7. Bước 4 — Giữ lại điều kiện động cho runtime

Ví dụ chọn tất cả method execution `transfer(String,long)` với số tiền lớn hơn 1000.

Chữ ký là phần tĩnh. Nhưng biểu thức `amount > 1000` chỉ quyết định được ở từng lần gọi. Một bộ dệt có thể biểu diễn phần này thành **runtime guard** hay **dynamic residue**:

```text
Tĩnh:
    method == TransferService.transfer(String,long)

Động tại mỗi invocation:
    amount > 1000

Khi guard true:
    chạy advice

Khi guard false:
    bỏ qua advice này; thao tác được tiếp tục theo cơ chế thực thi
```

Điểm cần nhấn mạnh:

- Runtime guard có thể đọc tham số, kiểu đối tượng, ngữ cảnh luồng điều khiển hoặc trạng thái liên quan.
- Guard không nhất thiết là một lời gọi Java tách biệt; nó có thể được biên dịch thành nhánh điều kiện hoặc được interceptor đánh giá.
- Một biểu thức có thể được rút gọn nếu bộ dệt chứng minh được điều kiện luôn đúng hoặc luôn sai ở một shadow cụ thể.
- Nếu guard chứa công việc quá đắt, chi phí có thể xuất hiện ở **mọi lần kiểm tra**, ngay cả khi advice hiếm khi chạy.

### 7.1. Đừng nhầm kiểu đối số với giá trị đối số

Điều kiện “tham số thứ hai có kiểu `long`” có thể kiểm tra từ chữ ký. Điều kiện “giá trị tham số thứ hai lớn hơn 1000” phải quan sát số tiền thực tế. Không thể dùng wildcard kiểu tham số để biểu diễn ngữ nghĩa so sánh giá trị.

### 7.2. Điều kiện theo kiểu runtime

Trong chương trình đa hình:

```java
PaymentGateway gateway = obtainGateway();
gateway.charge(1500L);
```

Đây là đoạn minh họa với biến và hàm giả định. Kiểu khai báo tại call site là `PaymentGateway`, còn đối tượng thực có thể thuộc một class triển khai. Nếu pointcut phụ thuộc **kiểu thực tế của đối tượng**, bộ dệt có thể phải để lại kiểm tra runtime.

Cần biết cụ thể designator trong công cụ xét **kiểu tĩnh**, **declaring type** hay **runtime target type**. Các điều kiện có tên giống nhau giữa công cụ khác nhau chưa chắc mang nghĩa giống nhau.

## 8. Bước 5 — Kết hợp advice vào đường thực thi

Sau khi xác định các shadow được chọn hoặc có khả năng khớp, bộ dệt phải tạo một đường thực thi mà advice có thể chạy.

Tùy kiến trúc, nó có thể:

1. **Chèn trực tiếp các lệnh bổ sung** trước/sau một điểm vào mã hoặc bytecode.
2. **Tạo hàm/đoạn mã trung gian** để chuyển tiếp qua advice.
3. **Tạo proxy/interceptor** nhận lời gọi trước khi chuyển cho target.
4. **Kết hợp metadata và handler** để runtime quyết định gọi advice tại thời điểm xảy ra sự kiện.

Với advice có điều kiện động, phần chèn có thể mang dạng tư duy:

```text
operation(args):
    if dynamicGuard(args):
        runAdviceAround(operation, args)
    else:
        runOriginalOperation(args)
```

Đây là **mã giả khái niệm**, không có nghĩa mọi bộ dệt đều nhân đôi thân method hay sửa trực tiếp lời gọi ở một dạng duy nhất. Trong thực tế cần xử lý return value, ngoại lệ, stack, local variables và ngữ nghĩa ngôn ngữ.

### 8.1. Around advice và continuation

Một quanh-advice có thể dùng `proceed` để tiếp tục, nhận kết quả hoặc ngoại lệ. Bộ dệt phải bảo đảm đường continuation được nối đúng với điểm đã chọn. Ví dụ mã giả:

```text
around timing(operation):
    started = monotonicClock()
    try:
        return proceed(operation)
    finally:
        recordDuration(monotonicClock() - started)
```

Nếu có nhiều advice cùng khớp, “phần được tiếp tục” có thể gồm **advice khác** và phần gốc. Việc weaving phải giữ thứ tự hiệu lực theo cơ chế ưu tiên đã định. Không thể coi `proceed` luôn là lời gọi trực tiếp tới target.

### 8.2. Điều gì xảy ra nếu nhiều pointcut cùng khớp?

Một shadow có thể được chọn bởi pointcut ghi audit và pointcut đo thời gian. Bộ dệt phải kết hợp các advice có thể được áp dụng theo **thứ tự** phù hợp. Ví dụ ý niệm:

```text
AuditAround(
    TimingAround(
        BusinessOperation
    )
)
```

Đổi thứ tự có thể làm khác hành vi khi một advice từ chối hoặc ném lỗi. **Thứ tự không nên suy ra từ thứ tự tên file**; cần xác minh ngữ nghĩa precedence của công cụ.

## 9. Ba nơi có thể diễn ra việc tìm điểm và dệt advice

### 9.1. Weaving khi biên dịch

Khi compiler hoặc bộ dệt nhận mã nguồn/biểu diễn trung gian, nó có thể phân tích cấu trúc chương trình, tìm shadow, so khớp pointcut và tạo mã đã kết hợp advice.

Ưu điểm có thể có:

- Thông tin kiểu, cấu trúc và một số metadata thuận lợi cho matching.
- Nhiều loại điểm can thiệp hơn một proxy chỉ chặn lời gọi ngoài.
- Có cơ hội tối ưu các điều kiện tĩnh.

Đánh đổi:

- Quy trình build cần bước weaving rõ ràng.
- Phạm vi mã được build/weave phải được kiểm soát.
- Chẩn đoán cần công cụ xem mã hoặc báo cáo weaving.

### 9.2. Weaving khi nạp mã

Một bộ biến đổi có thể can thiệp khi lớp/thành phần được nạp vào runtime. Nó phân tích bytecode/metadata lúc đó rồi chèn cơ chế advice tương ứng.

Ưu điểm có thể có: không cần thay đổi nguồn cho mọi thành phần có thể weaving. Đổi lại phải xét thời điểm lớp được nạp, class loader, khả năng biến đổi, module boundary và các giới hạn của môi trường.

**Không được tự giả định** một lớp đã nạp trước khi bộ dệt được kích hoạt sẽ nhận cùng kết quả với lớp được nạp sau. Điều đó phụ thuộc khả năng tái biến đổi và cấu hình của công cụ.

### 9.3. Interception tại runtime

Một proxy hoặc dispatcher có thể chọn method mà nó quản lý, rồi quyết định chạy advice dựa trên metadata và ngữ cảnh động.

Ưu điểm: dễ minh họa, không nhất thiết sửa bytecode phần gốc. Giới hạn thường gặp:

- Chỉ nhìn thấy lời gọi đi **qua trung gian**.
- Một lời gọi trực tiếp tới target có thể không bị chặn.
- **Self-invocation** bên trong target có thể bỏ qua proxy.
- Không tự biến mọi field access, constructor hay call site thành join point.

**Đây là khác biệt về khả năng triển khai, không phải luật rằng tất cả AOP đều bỏ qua lời gọi nội bộ.**

## 10. Ví dụ Java 17: mô phỏng tìm ứng viên tĩnh và guard động

Để quan sát được hai bước khác nhau, ta xây một chương trình **Java thuần**:

1. Quét các phương thức của một giao diện bằng reflection.
2. Chọn method theo tên, kiểu trả về và kiểu tham số (**bộ lọc tĩnh**).
3. Dùng `Proxy` chuyển tiếp cuộc gọi qua interceptor.
4. Chạy guard `amount >= 1000` (**điều kiện động**) trước khi ghi advice.
5. Gọi target và xử lý kết quả/ngoại lệ.

**Lưu ý giới hạn:** đây là bộ mô phỏng quy trình matching ở mức phương thức giao diện. Nó **không phải bộ dệt AOP đầy đủ**, không tạo join point shadow cho mọi call site, không biến đổi bytecode, và việc chọn method theo reflection không chứng minh hỗ trợ mọi loại join point.

Tạo file `WeaverMatchDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;

public class WeaverMatchDemo {

    interface Operations {
        String checkout(String id, long amount);
        String refund(String id, long amount);
        String ping();
    }

    static final class DefaultOperations implements Operations {
        @Override
        public String checkout(String id, long amount) {
            System.out.println("business:checkout:" + id + ":" + amount);
            return "checkout:" + id;
        }

        @Override
        public String refund(String id, long amount) {
            System.out.println("business:refund:" + id + ":" + amount);
            if ("ERR".equals(id)) {
                throw new IllegalStateException("refund rejected");
            }
            return "refund:" + id;
        }

        @Override
        public String ping() {
            System.out.println("business:ping");
            return "pong";
        }
    }

    static boolean staticMatches(Method method) {
        if (method.getReturnType() != String.class) {
            return false;
        }

        Class<?>[] types = method.getParameterTypes();
        if (types.length != 2
                || types[0] != String.class
                || types[1] != long.class) {
            return false;
        }

        return method.getName().equals("checkout")
                || method.getName().equals("refund");
    }

    public static void main(String[] args) {
        Method[] methods = Operations.class.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(Method::getName));

        Set<Method> selected = new HashSet<>();
        for (Method method : methods) {
            if (staticMatches(method)) {
                selected.add(method);
                System.out.println("scan:match:" + method.getName());
            } else {
                System.out.println("scan:skip:" + method.getName());
            }
        }

        Operations target = new DefaultOperations();
        InvocationHandler handler = (proxy, method, values) -> {
            boolean staticSelected = selected.contains(method);
            boolean dynamicAllowed = staticSelected
                    && values != null
                    && (Long) values[1] >= 1000L;

            if (dynamicAllowed) {
                System.out.println("advice:before:" + method.getName());
            }

            try {
                Object result = method.invoke(target, values);
                if (dynamicAllowed) {
                    System.out.println("advice:after:" + method.getName());
                }
                return result;
            } catch (InvocationTargetException wrapped) {
                Throwable original = wrapped.getCause();
                if (dynamicAllowed) {
                    System.out.println("advice:error:" + method.getName()
                            + ":" + original.getClass().getSimpleName());
                }
                throw original;
            }
        };

        Operations proxy = (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[] { Operations.class },
                handler
        );

        System.out.println("caller:" + proxy.checkout("A", 1500));
        System.out.println("caller:" + proxy.checkout("B", 50));
        System.out.println("caller:" + proxy.refund("C", 2000));

        try {
            proxy.refund("ERR", 3000);
        } catch (IllegalStateException error) {
            System.out.println("caller:error:" + error.getMessage());
        }

        System.out.println("caller:" + proxy.ping());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac WeaverMatchDemo.java
java WeaverMatchDemo
```

Kết quả dự kiến:

```text
scan:match:checkout
scan:skip:ping
scan:match:refund
advice:before:checkout
business:checkout:A:1500
advice:after:checkout
caller:checkout:A
business:checkout:B:50
caller:checkout:B
advice:before:refund
business:refund:C:2000
advice:after:refund
caller:refund:C
advice:before:refund
business:refund:ERR:3000
advice:error:refund:IllegalStateException
caller:error:refund rejected
business:ping
caller:pong
```

### 10.1. Hai tầng matching được thể hiện thế nào?

**Tầng tĩnh:**

- `checkout` và `refund` có đúng tên thuộc danh sách, return type `String` và hai tham số `String,long` nên được thêm vào `selected`.
- `ping` không có hai tham số, nên bị loại.
- Danh sách được sort để đầu ra `scan` có thứ tự xác định.

**Tầng động:**

- `checkout("A",1500)` và `refund("C",2000)` thỏa `amount >= 1000` nên có advice trước/sau.
- `checkout("B",50)` khớp tĩnh nhưng guard động sai, nên phần nghiệp vụ vẫn thực thi mà không có log advice.
- `refund("ERR",3000)` thỏa cả hai tầng nhưng target ném lỗi; interceptor gỡ `InvocationTargetException` của reflection để ghi/lan truyền `IllegalStateException` gốc.
- `ping()` không khớp tĩnh, nên handler không truy cập `values[1]` và tránh lỗi chỉ số. Đây là hệ quả trực tiếp của việc dùng `&&` ngắn mạch trong **mã Java mô phỏng**, không phải cam kết về thứ tự đánh giá của mọi DSL pointcut.

### 10.2. Mô phỏng khác weaver thật ở đâu?

- Reflection trên giao diện không quét các **vị trí gọi** trong mã ứng dụng.
- `HashSet<Method>` chỉ là bộ nhớ kết quả lọc, không phải cấu trúc shadow của một compiler AOP.
- Proxy chỉ thấy những lời gọi **đi qua proxy**; nó không can thiệp vào mọi execution/call trong runtime.
- Quy tắc `staticMatches` là logic Java thủ công, không phải parser ngôn ngữ pointcut.
- Một bộ dệt bytecode có thể đưa guard và advice vào những chỗ khác hoặc tối ưu chúng khác.

Điều rút ra là **hai giai đoạn tư duy**: loại những điểm chắc chắn không phù hợp bằng metadata, và chỉ kiểm tra điều kiện runtime trên các đường còn có khả năng khớp.

## 11. Các tối ưu quan trọng của quá trình tìm điểm

Một bộ dệt có thể giảm chi phí bằng nhiều kỹ thuật:

### 11.1. Index theo kiểu, tên hoặc signature

Nếu pointcut chọn những method trong `example.payment`, không nhất thiết phải xem chi tiết mọi method ở các package không liên quan. Compiler hoặc bộ dệt có thể dùng bảng ký hiệu, index lớp hoặc metadata để rút gọn tập ứng viên.

### 11.2. Constant folding và loại shadow không thể khớp

Nếu một phần pointcut mâu thuẫn với signature của shadow, bộ dệt có thể bỏ shadow ngay. Ví dụ yêu cầu tham số đầu `String` sẽ không khớp một method có tham số đầu `int` theo điều kiện chữ ký tĩnh tương ứng.

### 11.3. Trì hoãn điều kiện chỉ biết ở runtime

Điều kiện theo giá trị tham số không thể quyết định từ signature. Giữ lại **guard nhỏ nhất cần thiết** ở runtime có thể giảm chi phí hơn so với chạy toàn bộ biểu thức hoặc advice cho mọi invocation.

### 11.4. Tái sử dụng dữ liệu tĩnh

Thông tin signature và kiểu có thể được giữ hoặc tái sử dụng theo điểm, thay vì tạo chuỗi mô tả và đối tượng phản xạ mới ở từng lời gọi, nếu thiết kế và API cho phép.

### 11.5. Tránh điều kiện động có side effect

Nếu biểu thức động gọi mạng hoặc sửa dữ liệu nghiệp vụ chỉ để quyết định khớp, việc tối ưu hoặc đánh giá lại có thể làm hệ thống khó dự đoán. Nên giữ điều kiện chọn điểm **thuần, đơn giản và có hợp đồng rõ**, rồi đưa hành vi phụ trợ cần thiết vào advice.

**Quan trọng:** không có bảo đảm mọi công cụ sử dụng những tối ưu trên. Cách tối ưu phải giữ ngữ nghĩa được công cụ cam kết; không nên viết pointcut phụ thuộc vào một thứ tự kiểm tra mà ngôn ngữ không bảo đảm.

## 12. Những trường hợp khiến matching khó hơn tên phương thức

### 12.1. Overload

```java
void send(String message);
void send(String message, int priority);
```

Hai method có cùng tên nhưng khác signature. Mẫu chọn `send(..)` (trong một DSL hỗ trợ ký hiệu tương ứng) có thể chọn cả hai; mẫu yêu cầu đúng `(String,int)` hẹp hơn.

### 12.2. Override và dispatch động

Một biến kiểu giao diện có thể trỏ đến nhiều triển khai. Thông tin tại **method-call site** và thông tin về **phần thân thực thi thực tế** không luôn giống nhau.

Một bộ dệt phải tôn trọng cách ngôn ngữ giải quyết lời gọi, kế thừa, overriding và dynamic dispatch. Không thể chỉ xem tên lớp khai báo tại chỗ gọi rồi chắc chắn biết mọi method body sẽ chạy.

### 12.3. Bridge và synthetic methods

Compiler Java có thể tạo phương thức bridge/synthetic để duy trì ngữ nghĩa generics và đa hình. Ở mức bytecode, tập các method mà bộ dệt gặp có thể nhiều hơn những khai báo người lập trình trực tiếp nhìn thấy.

Cần biết công cụ chọn/loại những method này ra sao để tránh áp advice hai lần hoặc bỏ sót đường thực thi. **Không có quy tắc chung** rằng mọi công cụ đều xử lý chúng y hệt nhau.

### 12.4. Annotation ở interface và implementation

Một method được đánh dấu ở giao diện, lớp cha hoặc implementation có thể hiện ra khác nhau khi phản xạ hoặc khi matching bytecode. Không nên mặc định dấu được kế thừa đến mọi override, đặc biệt với annotation phương thức của Java.

Muốn chọn theo metadata, cần xác định rõ **đọc annotation ở thành phần nào** và kiểm thử khi có override/interface.

### 12.5. Constructor, field và exception handler

Nếu công cụ hỗ trợ những loại join point này, nó phải tìm các vị trí/bytecode tương ứng và áp dụng ngữ nghĩa matching khác method execution. Một số trường hợp như việc **ném ngoại lệ** và việc **đi vào exception handler** là hai sự kiện khác nhau. Không thể suy rằng hỗ trợ handler join point nghĩa là chặn được mọi lệnh `throw`.

## 13. Phạm vi control flow và điều kiện theo ngữ cảnh

Một số mô hình AOP có pointcut phụ thuộc **luồng điều khiển động**: chỉ áp advice khi đang thực thi trong một thao tác cha.

```text
runBatch()
  |
  +-- stepA()
  |     |
  |     +-- save()
  |
  +-- stepB()
        |
        +-- save()

interactiveRequest() -> save()
```

Nếu mục tiêu là chỉ can thiệp `save` khi đang trong luồng `runBatch`, không thể suy từ **chữ ký của save** để biết điểm xuất hiện thuộc batch hay tương tác độc lập.

Bộ dệt có thể chuẩn bị cơ chế theo dõi entry/exit của phạm vi điều khiển và để lại điều kiện runtime cho các join point bên trong, nếu công cụ có tính năng tương ứng.

Các giới hạn:

- Điều kiện theo call stack đồng bộ không tự động lan sang worker thread bất đồng bộ.
- Gọi lồng nhau và đệ quy cần quản lý đúng độ sâu/vòng đời context.
- Ngoại lệ phải được xử lý sao cho trạng thái theo dõi không bị kẹt “đang trong batch”.
- Giữ ngữ cảnh toàn cục không phân biệt invocation có thể gây can thiệp sai giữa các request.

Chi phí của một guard theo control flow có thể khác phép so sánh tham số đơn giản; cần đo dưới tải phù hợp.

## 14. Đúng tên nhưng không thấy advice: phân tích theo từng tầng

Khi một method tưởng như khớp pointcut nhưng advice không chạy, có nhiều nguyên nhân độc lập:

| Tầng | Vấn đề có thể xảy ra |
| --- | --- |
| Phân tích cú pháp | Biểu thức sai ngữ pháp hoặc độ ưu tiên toán tử |
| Giải quyết kiểu | Tên kiểu hoặc method signature không đúng |
| Mô hình join point | Công cụ không hỗ trợ loại điểm được yêu cầu |
| Phạm vi quét | Lớp hoặc thư viện không nằm trong vùng weaving |
| Matching tĩnh | Modifier, tham số, package hoặc metadata không khớp |
| Matching động | Args, runtime type, control flow hoặc trạng thái không thỏa |
| Đường interception | Lời gọi bỏ qua proxy, xảy ra trên target trực tiếp |
| Chuỗi advice | Advice ngoài ngăn tiếp tục tới advice trong hoặc body |
| Thời điểm nạp mã | Lớp đã nạp hoặc đã được xử lý theo cơ chế khác |
| Quan sát | Logging của advice lỗi hoặc trace không bao gồm đường đó |

Cách điều tra hiệu quả là đi **từ trên xuống**, không nới wildcard thật rộng ngay khi không thấy log. Nới quá rộng có thể tạo tác động ngoài ý muốn mà vẫn không giải quyết vấn đề phạm vi weaving.

### 14.1. Tập matching tĩnh khác số lượt advice chạy

Một build có thể báo “12 join-point shadows matched”, nhưng trong một ca kiểm thử chỉ có ba trong số đó được thực thi. Nếu còn guard động, số lượt advice chạy có thể ít hơn số lượt invocation tại các shadow đó.

Nên báo riêng ba số liệu:

1. **Shadows tĩnh được chọn hoặc có khả năng khớp**.
2. **Số lần đi qua các điểm ứng viên**.
3. **Số lần guard cho phép advice thực sự chạy**.

Đây là ba đại lượng khác nhau.

## 15. Tác động đến correctness: weaving không được phá hợp đồng gốc

Bộ dệt cần giữ đúng ngữ nghĩa chương trình trừ những thay đổi mà advice chủ động cho phép. Những điểm cần bảo toàn thường bao gồm:

- **Thứ tự đánh giá** các biểu thức ban đầu.
- **Tham số** và đối tượng đích.
- **Giá trị trả về**, kể cả primitive, reference và `void`.
- **Ngoại lệ**, cause và hành vi unwinding.
- **Ranh giới đồng bộ**, monitor/lock và finally.
- **Đệ quy** và các lời gọi lồng nhau.
- **Tính nhìn thấy/kiểu hợp lệ** theo quy tắc compiler/runtime.
- **Trạng thái xác minh bytecode** đối với những môi trường yêu cầu kiểm tra bytecode.

Một lỗi weaving có thể là lỗi kỹ thuật trước khi advice chạy; một lỗi trong advice cũng có thể gây thay đổi kết quả/ngoại lệ của caller. Cần phân biệt hai nguồn này khi chẩn đoán.

### 15.1. Không hiểu “weaving” là sao chép nguyên văn lệnh advice ở mọi nơi

Công cụ có thể sinh cầu nối, gọi handler, kết hợp closure/continuation hoặc chèn câu lệnh có điều kiện. Hình thức mã sinh ra khác nhau nhưng phải tương thích mô hình semantics đã công bố.

### 15.2. Khi advice được cho phép thay đổi luồng

Một around advice có thể không gọi `proceed`, trả fallback hoặc gọi tiếp nhiều lần nếu ngôn ngữ cho phép. Đó là thay đổi **có chủ đích của advice**, không được nhầm với lỗi weaver. Với thao tác có side effect, quyền này phải được quản lý và kiểm thử kỹ.

## 16. Hiệu năng của quá trình matching và đường đã weave

Chi phí có thể nằm ở hai giai đoạn:

**Chi phí trước khi chạy hoặc lúc nạp:**

- Parse biểu thức.
- Giải quyết kiểu, kiểm tra cú pháp/ngữ nghĩa.
- Duyệt mã và xây shadow.
- So khớp static, tối ưu và sinh mã.
- Biến đổi hoặc kiểm tra bytecode.

**Chi phí mỗi invocation:**

- Đi qua interceptor hoặc nhánh đã weave.
- Lấy ngữ cảnh runtime.
- Đánh giá guard động.
- Chạy advice.
- Tạo dữ liệu log/trace và side effect khác.

Mô hình gần đúng:

```text
Tổng chi phí vận hành =
    chi phí phân tích/weaving phân bổ theo vòng đời
  + số invocation qua ứng viên * chi phí kiểm tra/interception
  + số invocation khớp động * chi phí advice
  + ảnh hưởng cấp phát, I/O, đồng bộ, GC, cache
```

Đây là sơ đồ tư duy, không phải công thức benchmark chính xác. Một công cụ có thể tối ưu các bước thành các instruction đơn giản; một lời gọi mạng trong advice có thể lấn át toàn bộ overhead matching.

### 16.1. Điều kiện tĩnh nên loại nhiều điểm càng sớm càng tốt?

Về nguyên tắc, loại sớm điểm chắc chắn không khớp giúp giảm chi phí runtime. Nhưng không nên thay đổi **ngữ nghĩa** pointcut chỉ để cải thiện số đo. Nếu yêu cầu cần giá trị runtime, không thể “cache kết quả matching” chỉ theo method name cho mọi invocation.

### 16.2. Cách đo phù hợp

Tách biến thể baseline, có instrumentation nhưng guard false, guard true với advice nhẹ và advice thực. Dùng workload đại diện, warm-up hợp lý và đo throughput/latency/allocation; tránh kết luận từ vài lần chạy `System.nanoTime()` hay từ ví dụ có `System.out.println`.

## 17. Chiến lược kiểm thử để chứng minh bộ dệt đã tìm đúng điểm

Một bộ kiểm thử tốt cần cả ca **dương tính** và **âm tính**.

### 17.1. Kiểm thử matching tĩnh

Dựng các method gần giống nhau:

```java
void charge(String id);
void charge(String id, long amount);
void charge(int number, long amount);
void chargePreview(String id, long amount);
```

Đây là danh sách chữ ký minh họa, chưa phải class Java độc lập.

Nếu pointcut chỉ chọn `charge(String,long)`, cần xác minh:

- Phương thức đúng chữ ký được chọn.
- Overload một tham số không được chọn.
- Overload có tham số đầu `int` không được chọn.
- `chargePreview` không được chọn nếu mẫu yêu cầu tên chính xác.

### 17.2. Kiểm thử điều kiện động

Trên cùng một method, gọi với `amount=999`, `1000` và `1001` nếu guard quy định `amount > 1000`. Kiểm tra chính xác ranh giới lớn hơn hay lớn hơn/bằng, kèm dữ liệu null, kiểu runtime và ngữ cảnh control flow nếu áp dụng.

### 17.3. Kiểm thử loại join point

Một method được gọi từ hai nơi: nếu pointcut là **call**, kiểm tra hai call sites; nếu là **execution**, kiểm tra thân được thực thi. Không dùng kết quả ở một loại điểm để kết luận engine hỗ trợ loại còn lại.

### 17.4. Kiểm thử đường trực tiếp và lời gọi nội bộ

Nếu hệ thống dùng proxy, kiểm tra lời gọi qua proxy, trực tiếp tới target và gọi từ chính target. Nếu dùng bytecode weaving, xác minh tập lớp đã được biến đổi và đường code tương ứng.

### 17.5. Kiểm thử ngoại lệ, đệ quy và đồng thời

Đảm bảo advice chạy đúng số lần trong trường hợp method ném lỗi, gọi lồng nhau, chạy đa luồng hoặc có điều kiện control flow. Không dùng một biến mutable chung để lưu ngữ cảnh matching của mọi invocation.

### 17.6. Kiểm thử nhiều aspect

Khi hai aspect cùng chọn một shadow, kiểm tra thứ tự có hiệu lực, điều kiện guard của từng aspect và trường hợp advice ngoài dừng trước khi đến advice bên trong.

## 18. Lập ma trận so khớp để đối chiếu kỳ vọng

Giả sử quy tắc tổng quát:

> Chọn method execution `transfer(String,long)` với giá trị `amount > 1000` trong những lớp được dệt.

| Trường hợp | Khớp tĩnh? | Guard động? | Advice mong đợi? |
| --- | --- | --- | --- |
| `transfer("A",2000)` đúng loại điểm | Có | Đúng | Có |
| `transfer("A",500)` đúng loại điểm | Có | Sai | Không |
| `transfer("A",1000)` đúng loại điểm | Có | Sai | Không |
| `transfer("A")` | Không | Không cần đánh giá | Không |
| `transfer(99,2000)` | Không | Không cần đánh giá | Không |
| `ping()` | Không | Không cần đánh giá | Không |
| Chỉ tồn tại method, chưa được gọi | Có thể có shadow | Không xuất hiện invocation | Không có lần advice chạy |
| Method đúng chữ ký nhưng nằm ngoài weaving | Không có interception tại đường đó | Không được đánh giá ở đó | Không |
| Lời gọi đi trực tiếp qua target, bỏ qua proxy | Tùy mô hình tĩnh | Proxy không thấy | Không qua proxy |
| Thực thi trong vùng control flow cần theo dõi | Có | Tùy trạng thái luồng | Theo guard và công cụ |

Cần tách **điểm có khả năng khớp theo cấu trúc** khỏi **đường thực sự được can thiệp**. Bảng là ma trận kỳ vọng để xây kiểm thử, không phải lời hứa mọi công cụ hoạt động giống nhau.

## 19. Các lỗi hiểu sai thường gặp

**“Weaver chỉ tìm tên phương thức.”** Không. Mô hình join point, signature, declaring type, modifier, metadata và ngữ cảnh đều có thể ảnh hưởng matching.

**“Pointcut hợp cú pháp là chắc chắn có advice chạy.”** Không. Có thể không có shadow khớp, không có invocation hoặc không có đường weaving.

**“Một shadow khớp đồng nghĩa một lần advice.”** Không. Shadow là cấu trúc; invocation có thể xảy ra nhiều lần.

**“Tất cả điều kiện đều kiểm tra khi biên dịch.”** Không. Giá trị args, đối tượng runtime và control flow có thể chỉ biết lúc chạy.

**“Mọi điều kiện runtime đều phải đánh giá cho mọi method.”** Không nhất thiết. Matching tĩnh có thể loại phần lớn ứng viên.

**“Method call và method execution chỉ là hai tên giống nhau.”** Không. Chúng mô tả hai loại điểm, có phạm vi quan sát khác nhau.

**“Proxy là bộ dệt có thể chặn mọi bytecode.”** Không. Proxy thường chỉ can thiệp lời gọi đi qua nó.

**“Chọn kiểu interface nghĩa là đã chọn mọi implementation trong mọi công cụ.”** Chưa chắc. Phải biết ngữ nghĩa subtype và điểm được weaving.

**“Thêm annotation thì bộ dệt tự nhìn thấy ở mọi override.”** Không thể mặc định; cần kiểm tra cách đọc metadata.

**“Điều kiện khớp tĩnh có thể cache kết quả động theo chữ ký.”** Sai khi kết quả phụ thuộc dữ liệu từng lần gọi.

**“Không thấy log chứng minh pointcut sai.”** Có thể lỗi ở weaving, guard, đường gọi hoặc chính log advice.

## 20. Bài tập có đáp án

**1.** Một call site trong vòng lặp chạy 100 lần. Bộ dệt báo một static shadow khớp. Advice chạy mấy lần?

Không kết luận chỉ từ một shadow. Có thể có 100 invocation, nhưng còn phụ thuộc điều kiện động, đường có thực sự được weave và việc điểm có xảy ra hay không.

**2.** Một method có tên `transfer`, nhưng chữ ký là `transfer(String)`; pointcut đòi `transfer(String,long)`. Có cần kiểm tra amount ở runtime không?

Không đối với shadow đó, vì kiểu/số tham số đã không khớp tĩnh.

**3.** `transfer("A",500)` và `transfer("B",5000)` có cùng chữ ký. Có thể cache kết quả điều kiện `amount>1000` theo chữ ký không?

Không. Một lần không khớp, một lần khớp; kết quả phụ thuộc dữ liệu động.

**4.** Mã ở `checkout()` gọi `gateway.pay()`. Điểm method call nằm ở đâu, điểm method execution nằm ở đâu?

Call nằm tại vị trí gọi ở `checkout`; execution nằm ở phần thực thi method `pay`. Công cụ có thể hỗ trợ các tập điểm khác nhau.

**5.** Bộ dệt chỉ chặn qua proxy. Vì sao một lời gọi nội bộ không thấy advice?

Vì lời gọi có thể đi trực tiếp trên đối tượng target, không đi qua proxy. Không suy rằng mọi cơ chế AOP đều có cùng giới hạn.

**6.** Nếu một pointcut có phần tĩnh đúng nhưng điều kiện control flow sai, advice có chạy không?

Không chạy theo điều kiện pointcut ấy tại invocation đó, dù shadow có khả năng khớp.

**7.** Một advice ngoài nhận lỗi từ `proceed`. Có chắc nghiệp vụ ném không?

Không. Advice bên trong có thể phát sinh lỗi hậu xử lý; cần xác định ranh giới và nguồn.

**8.** Làm sao kiểm chứng danh sách 20 shadows đã được weave đồng nghĩa đầy đủ chính sách?

Cần tập mong muốn độc lập, kiểm thử cả ca phải khớp/không được khớp, và xác minh runtime trên các đường gọi thật. Con số 20 tự nó không chứng minh correctness.

## 21. Checklist áp dụng khi phân tích một weaver

- [ ] Đã xác định mô hình và **loại join point** mà công cụ hỗ trợ.
- [ ] Đã hiểu cú pháp pointcut, logic nhóm và cơ chế giải quyết kiểu.
- [ ] Đã phân biệt vị trí tĩnh (shadow) với invocation thực tế.
- [ ] Đã biết công cụ duyệt source, bytecode hay metadata runtime.
- [ ] Có danh sách những điều kiện được giải quyết tĩnh.
- [ ] Có danh sách các guard còn phải kiểm tra runtime.
- [ ] Đã biết weaving xảy ra lúc compile, load hay runtime.
- [ ] Đã xác nhận phạm vi các lớp/module được can thiệp.
- [ ] Có kiểm thử overload, override, interface và metadata nếu liên quan.
- [ ] Có ca kiểm thử call vs execution và các đường bypass proxy.
- [ ] Có ca âm tính chứng minh không chọn thừa.
- [ ] Đã xác nhận số invocation/advice thay vì chỉ đếm shadow.
- [ ] Đã kiểm tra thứ tự nhiều advice, kết quả, ngoại lệ và side effect.
- [ ] Có đo overhead hợp lý và tránh giả định mọi guard đều miễn phí.
- [ ] Không đưa dữ liệu nhạy cảm vào logging của advice.
- [ ] Có cách truy vết cấu hình weaving và thông báo matching của công cụ.

## 22. Tổng kết

**Bộ dệt tìm điểm phù hợp với pointcut bằng cách hiểu biểu thức chọn điểm, xác định các join-point shadow thuộc mô hình được hỗ trợ, so khớp những điều kiện có thể biết từ cấu trúc và chuẩn bị kiểm tra những điều kiện còn phụ thuộc runtime.** Sau đó nó kết hợp advice vào các đường thực thi phù hợp theo cơ chế của mình — có thể lúc biên dịch, nạp mã hoặc chặn lời gọi khi chạy.

Để hiểu đúng một kết quả AOP, phải phân biệt bốn câu hỏi: **pointcut mô tả gì**, **những điểm nào được weaver thực sự xử lý**, **lần thực thi nào thỏa guard**, và **advice nào cuối cùng chạy**. Tư duy theo các tầng đó giúp giải thích điểm được chọn hay bỏ sót, cải thiện hiệu năng, kiểm thử tính đúng đắn và tránh việc một chính sách xuyên suốt vô tình làm thay đổi nghiệp vụ ngoài ý định.
