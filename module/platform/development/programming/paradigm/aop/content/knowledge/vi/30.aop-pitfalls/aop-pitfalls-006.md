# Sai lầm: Không xác định thứ tự cho các aspect có phụ thuộc trong AOP

## 1. Vì sao thứ tự aspect là một phần của tính đúng?

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), một **aspect** đóng gói hành vi xuyên suốt như kiểm tra đầu vào, kiểm toán, bảo vệ truy cập, đo lường hoặc quản lý vòng đời thao tác. **Pointcut** chọn các **join point**, còn **advice** thực thi trước, sau hoặc bao quanh phép tính tại join point được chọn. Khi **nhiều advice từ nhiều aspect cùng khớp một join point**, chúng không chỉ là những “hàm chạy cùng lúc”: lời gọi thường có một thứ tự điều khiển cụ thể.

Sai lầm **“không xác định thứ tự cho các aspect có phụ thuộc”** xuất hiện khi thiết kế ngầm giả định aspect A phải chạy trước hoặc bao ngoài aspect B, nhưng mã/cấu hình không biểu đạt quan hệ này. Trình dệt (weaver), classpath, cách sắp xếp mã hoặc phiên bản công cụ có thể dẫn đến một thứ tự khác kỳ vọng. Kể cả khi quan sát thấy thứ tự ổn định trong nhiều lần thử, đó chưa phải là **hợp đồng ngữ nghĩa** mà hệ thống được phép dựa vào.

Ví dụ điển hình:

- **Kiểm toán và xác thực:** nhật ký cần ghi cả yêu cầu bị từ chối. Nếu xác thực từ chối trước khi advice kiểm toán được vào, yêu cầu thất bại không được ghi.
- **Chuẩn hóa và kiểm tra:** kiểm tra yêu cầu nhận dữ liệu đã chuẩn hóa; đảo thứ tự có thể dẫn đến lỗi giả hoặc bỏ sót lỗi.
- **Đo lường và cache:** cần phân biệt đo toàn bộ đường request kể cả cache hit hay chỉ đo thân phương thức thật sự chạy.
- **Transaction và kiểm toán kết quả:** kiểm toán “đã commit” khi nghiệp vụ mới return nhưng commit thực sự có thể thất bại sau đó là sai ngữ nghĩa; vị trí advice và ranh giới hoàn tất cần đúng.
- **Retry và tính idempotent:** retry bao quanh kiểm toán có thể ghi nhiều bản ghi cho một yêu cầu; kiểm toán bao quanh retry có thể ghi một bản ghi tổng thể. Không có thứ tự nào luôn đúng cho mọi nghiệp vụ.

Đây là bài về **AOP nói chung**, có ví dụ ngôn ngữ **AspectJ code-style** để minh họa một cơ chế xác định precedence rõ ràng. Các công cụ AOP khác có thể đặt tên/khai báo thứ tự khác; hãy dựa trên hợp đồng của công cụ đang sử dụng.

## 2. Phân biệt thứ tự áp dụng, thứ tự chạy và quan hệ phụ thuộc

Ba khái niệm dễ bị lẫn:

1. **Thứ tự precedence (độ ưu tiên):** quan hệ quyết định advice nào bao ngoài hoặc được xét trước advice khác khi cùng khớp một join point.
2. **Thứ tự thực thi thực tế:** thứ tự các lệnh trong advice/body/exception path xuất hiện khi chạy, phụ thuộc loại advice, nhánh, `proceed` và việc có exception.
3. **Quan hệ phụ thuộc nghiệp vụ:** một bước chỉ hợp lệ sau bước khác, hoặc cần bao trọn bước khác. Đây là thứ ta phải đặc tả trước khi chọn cơ chế precedence.

Một precedence xác định không tự chứng minh hành vi đúng: **nếu cấu hình ưu tiên được khai báo theo thứ tự sai**, ứng dụng vẫn sai nhưng sai một cách nhất quán. Để tránh điều đó, cần viết hợp đồng bằng ngôn ngữ nghiệp vụ:

- “Audit phải thấy cả thất bại từ Validation.”
- “Validation phải chạy trước Metrics bên trong.”
- “Metrics chỉ đo đường nghiệp vụ được phép thực thi.”
- “Nếu Validation từ chối, thân nghiệp vụ không được chạy.”
- “Khi nội bộ ném exception, bước bao ngoài phải dọn dẹp và ghi lại kết quả lỗi.”

Sau đó mới thiết kế dạng advice và precedence đáp ứng từng yêu cầu.

### 2.1. Khi nào các aspect thực sự có phụ thuộc?

Không phải mọi cặp aspect đều cần ép thứ tự. Hai aspect có thể độc lập nếu chúng không cùng chọn một join point, hoặc nếu hoán đổi vị trí không làm thay đổi dữ liệu, side effect, kết quả, exception, thời điểm xử lý hay dữ liệu giám sát cần quan sát.

Tuy vậy, nhiều tác vụ tưởng độc lập lại không giao hoán:

```text
normalize -> validate  !=  validate -> normalize
authorize -> execute   !=  execute -> authorize
retry -> audit         !=  audit -> retry
decrypt -> inspect     !=  inspect -> decrypt
```

Ký hiệu `!=` ở đây nói rằng **không thể mặc định tương đương**; với một số đầu vào đặc biệt kết quả có thể trùng. Hãy kiểm thử ngữ nghĩa thay vì dựa vào trực giác “cả hai advice đều chỉ là before”.

## 3. Các loại advice và tác động của precedence

Trong mô hình AspectJ, độ ưu tiên cao hơn được đặt ở **phía ngoài** khi dựng chuỗi áp dụng advice tại join point. Tác động quan sát tùy loại advice:

| Advice | Khi có ưu tiên cao hơn | Ý nghĩa cần nhớ |
| --- | --- | --- |
| `before` | Thực thi trước advice có ưu tiên thấp hơn nếu đường đi tiếp diễn | Nếu ném exception có thể chặn advice phía trong và thân gốc |
| `around` | Đi vào trước, có thể gọi `proceed(...)` để vào advice thấp hơn/thân gốc | Có thể bỏ qua, thay tham số/kết quả hoặc gọi tiếp nhiều lần |
| `after returning` | Bao ngoài phép tính phía trong, body chạy khi phần phía trong hoàn thành bình thường | Trên đường trở ra, tầng ngoài chạy sau tầng trong |
| `after throwing` | Body chạy khi phần phía trong ném lỗi phù hợp | Một tầng trong có thể chuyển exception thành kết quả tùy thiết kế |
| `after` (finally) | Body chạy khi phần phía trong kết thúc theo hai đường | Tầng ngoài chạy khi unwind trở ra, kể cả lỗi |

Một hình dung hữu ích cho hai `around` có thứ tự `Outer` cao hơn `Inner`:

```text
Caller
  |
  v
Outer: enter
  |
  +--> proceed Outer
           |
           v
       Inner: enter
           |
           +--> proceed Inner --> original body
           |
       Inner: exit
  |
Outer: exit
  |
Caller
```

Vì vậy, **ưu tiên cao nhất không có nghĩa advice đó luôn in log đầu tiên và cũng luôn in log kết thúc đầu tiên**. Tầng có độ ưu tiên cao đi vào trước nhưng khi hoàn tất bình thường sẽ rời ra sau. Điều này rất quan trọng với `around` và `after`.

Nếu một `around` không gọi `proceed`, advice ưu tiên thấp hơn và thân gốc ở phía trong có thể **không được chạy**. Một `before` ném exception cũng có thể ngăn các tầng sau chạy. Khi xem log chỉ từ thành công, bạn có thể bỏ sót hành vi này trên đường lỗi.

## 4. Quy tắc precedence trong AspectJ code-style

Để có ví dụ cụ thể, AspectJ định nghĩa các quy tắc cho advice tại **cùng một join point**:

1. Nếu có `declare precedence` và aspect A được liệt kê trước B, **advice của A có precedence cao hơn** advice của B.
2. Nếu không có khai báo có hiệu lực mà A là **subaspect** của B, advice định nghĩa trong A có precedence cao hơn advice định nghĩa trong B.
3. Nếu các advice ở **hai aspect khác nhau**, không có quan hệ precedence được xác định từ các quy tắc trên, thì **thứ tự giữa chúng không được định nghĩa**. Không nên dựa vào thứ tự tên file, compiler input, đường classpath hay lần chạy quan sát được.
4. Nếu advice cùng nằm trong **một aspect**, AspectJ có quy tắc dựa trên thứ tự khai báo: nếu một trong hai là `after` thì advice xuất hiện **sau** có precedence cao hơn; trong các trường hợp còn lại, advice xuất hiện **trước** có precedence cao hơn. Những tình huống tạo vòng thứ tự không hợp lệ có thể làm compiler báo lỗi.

Cú pháp khai báo:

```aspectj
declare precedence: FirstAspect, SecondAspect, ThirdAspect;
```

Một aspect riêng có thể quản lý quy tắc:

```aspectj
public aspect AspectOrder {
    declare precedence: AuditAspect, ValidationAspect, MetricsAspect;
}
```

Ý nghĩa: khi cùng match join point, `AuditAspect` ở ngoài `ValidationAspect`, và `ValidationAspect` có precedence cao hơn `MetricsAspect`. Khai báo precedence là ràng buộc **về advice**, không phải lời bảo đảm tất cả advice luôn được gọi trong mỗi đường chạy: pointcut và nhánh `proceed` vẫn quyết định mức độ thực thi.

### 4.1. Type pattern, wildcard và kế thừa

AspectJ hỗ trợ `TypePatternList` trong `declare precedence`, chẳng hạn:

```aspectj
declare precedence: *..*Security*, TracingAspect, *;
```

Ý nghĩa khái quát: các aspect khớp nhóm tên Security có precedence cao, tiếp theo `TracingAspect`, sau đó nhóm aspect còn lại. Trong một danh sách precedence, wildcard `*` dùng cho “các kiểu không khớp pattern nào khác” chỉ được xuất hiện **tối đa một lần** theo cú pháp được hỗ trợ.

Phải kiểm tra **tên kiểu cụ thể**, package và aspect kế thừa mà pattern thực sự match. Với aspect trừu tượng làm lớp cha, đôi khi cần `+` để chọn cả các subaspect cụ thể: một khai báo chỉ nhắm tới abstract aspect mà không match concrete aspect có thể không cho hiệu lực mong đợi.

Không nên đưa mọi aspect vào một thứ tự toàn cục quá rộng nếu chỉ vài nhóm có phụ thuộc. Một thứ tự ép buộc không cần thiết làm tăng coupling và dễ tạo va chạm khi thêm aspect mới.

### 4.2. Khai báo mâu thuẫn và vòng precedence

Nếu hai khai báo đặt hai thứ tự trái nhau:

```aspectj
declare precedence: FirstAspect, SecondAspect;
declare precedence: SecondAspect, FirstAspect;
```

Khi advice của hai aspect đó cùng gặp tại một join point, mâu thuẫn phải được xử lý; AspectJ có thể báo lỗi vòng precedence. Theo mô tả chính thức, các khai báo riêng lẻ có thể cùng tồn tại hợp lệ khi hai aspect **không cùng chia sẻ join point**. Không đơn giản kết luận “hai khai báo đảo nhau luôn là lỗi biên dịch” mà bỏ qua điều kiện có/không có join point chồng lấn.

Trong một danh sách, lặp một aspect ở nhiều vị trí là lỗi:

```aspectj
declare precedence: FirstAspect, SecondAspect, FirstAspect;
```

Thay vì phân tán các ràng buộc quan trọng qua nhiều module khó kiểm tra, hãy dùng một nguồn khai báo kiến trúc đủ dễ tìm và có kiểm thử hợp đồng.

## 5. Ví dụ hoàn chỉnh: Audit phải bao ngoài Validation và Metrics

Yêu cầu nghiệp vụ:

- Audit ghi bắt đầu/kết thúc **kể cả khi Validation từ chối**.
- Validation chạy trước việc ghi metric của thao tác hợp lệ.
- Metrics bao quanh thân `TransferService.transfer` để ghi bắt đầu/kết thúc khi xử lý tiếp tục.
- Nếu số tiền không hợp lệ thì Validation ném lỗi, Metrics và thân chuyển tiền không chạy.
- Caller xử lý lỗi và in kết quả rõ ràng.

Vì vậy, quan hệ cần có: **`AuditAspect > ValidationAspect > MetricsAspect`** khi cả ba match cùng join point.

### 5.1. Tệp `src/demo/Main.java`

```java
package demo;

public class Main {
    public static void main(String[] args) {
        TransferService service = new TransferService();

        service.transfer(5);

        try {
            service.transfer(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}

class TransferService {
    void transfer(int amount) {
        System.out.println("core=" + amount);
    }
}
```

### 5.2. Tệp `src/demo/AuditAspect.aj`

```aspectj
package demo;

public aspect AuditAspect {
    void around():
        execution(void demo.TransferService.transfer(int)) {
        System.out.println("audit enter");
        try {
            proceed();
        } finally {
            System.out.println("audit exit");
        }
    }
}
```

`AuditAspect` dùng `around` để bọc toàn bộ đường thực thi phía trong. `finally` bảo đảm ghi `audit exit` trên cả đường thành công và đường ném exception. Việc ghi này ở ví dụ là `System.out.println` để quan sát thứ tự; hệ thực tế cần chính sách ghi log phù hợp, nhất là khi log cũng có thể ném exception hoặc bị chặn.

### 5.3. Tệp `src/demo/ValidationAspect.aj`

```aspectj
package demo;

public aspect ValidationAspect {
    before(int amount):
        execution(void demo.TransferService.transfer(int))
        && args(amount) {
        System.out.println("validate=" + amount);
        if (amount <= 0) {
            throw new IllegalArgumentException(
                "amount must be positive");
        }
    }
}
```

`ValidationAspect` kiểm tra input. Nếu không hợp lệ, `before` ném lỗi; advice và thân gốc có precedence thấp hơn không được tiếp tục như đường thành công. `args(amount)` bind số tiền từ join point.

### 5.4. Tệp `src/demo/MetricsAspect.aj`

```aspectj
package demo;

public aspect MetricsAspect {
    void around():
        execution(void demo.TransferService.transfer(int)) {
        System.out.println("metrics enter");
        try {
            proceed();
        } finally {
            System.out.println("metrics exit");
        }
    }
}
```

`MetricsAspect` được chạy phía trong Validation. Trong ví dụ, metrics chỉ đếm công việc đã qua kiểm tra. Nếu yêu cầu là đo **mọi** request, gồm request bị từ chối, cần thiết kế metrics ở phía ngoài Validation hoặc thêm metric từ chối; đó là quyết định về semantics.

### 5.5. Tệp `src/demo/AspectOrder.aj`

```aspectj
package demo;

public aspect AspectOrder {
    declare precedence:
        AuditAspect,
        ValidationAspect,
        MetricsAspect;
}
```

Đây là **một khai báo tường minh** bảo vệ thứ tự phụ thuộc. `AspectOrder` không cần advice riêng; nó chứa ràng buộc precedence giữa ba aspect cụ thể. Khi compiler/weaver hỗ trợ kiểu khai báo này, source order và số thứ tự file không cần được dùng để suy diễn.

### 5.6. Biên dịch và chạy

Dùng **JDK 17+**, phiên bản **AspectJ compiler** hỗ trợ Java 17 và thư viện runtime `aspectjrt.jar` tương thích. Java thông thường không biên dịch được `.aj`; dùng `ajc`. Giả sử đang đứng ở thư mục gốc project, có `aspectjrt.jar` cạnh thư mục `src`:

```powershell
ajc -17 -showWeaveInfo -d out -classpath "aspectjrt.jar" src/demo/Main.java src/demo/AuditAspect.aj src/demo/ValidationAspect.aj src/demo/MetricsAspect.aj src/demo/AspectOrder.aj
java -cp "out;aspectjrt.jar" demo.Main
```

Trên Linux/macOS, dùng classpath separator `:`:

```bash
ajc -17 -showWeaveInfo -d out -classpath aspectjrt.jar src/demo/Main.java src/demo/AuditAspect.aj src/demo/ValidationAspect.aj src/demo/MetricsAspect.aj src/demo/AspectOrder.aj
java -cp "out:aspectjrt.jar" demo.Main
```

**Stdout của chương trình Java (không tính thông tin weaving compiler):**

```text
audit enter
validate=5
metrics enter
core=5
metrics exit
audit exit
audit enter
validate=0
audit exit
caught=amount must be positive
```

Phân tích:

- Lượt `transfer(5)`: Audit vào trước, Validation kiểm tra, Metrics vào, thân `TransferService` chạy. Khi return, Metrics thoát trước rồi Audit thoát.
- Lượt `transfer(0)`: Audit vào trước, Validation ném `IllegalArgumentException`. Metrics và thân gốc không chạy; Audit `finally` vẫn chạy trước khi lỗi thoát tới caller.
- `AspectOrder` bảo vệ đúng ý định “Audit thấy cả lỗi từ Validation”, không phụ thuộc việc công cụ hôm nay tình cờ chọn thứ tự nào.
- Nếu bỏ `AspectOrder`, **không khẳng định một stdout thay thế cụ thể**: thứ tự không được xác định theo hợp đồng khi các advice ở những aspect độc lập không có quan hệ precedence; cần dùng kiểm thử để bắt vi phạm.

**Điều kiện của ví dụ:** đây là ba aspect cùng chọn `execution(void demo.TransferService.transfer(int))`; một thay đổi pointcut khiến chúng không còn chia sẻ join point sẽ thay đổi phạm vi áp dụng mà không nhất thiết thay đổi thứ tự khai báo.

## 6. Vì sao thay thứ tự có thể tạo lỗi rất khó tìm?

### 6.1. Audit đặt phía trong Validation

Nếu đảo `ValidationAspect` trước `AuditAspect`, với input `0` thì Validation có thể ném lỗi **trước** khi Audit được gọi. Kết quả: mất log bắt đầu/kết thúc cho request bị từ chối. Đường happy path có thể vẫn hợp lý nên chỉ test input thành công sẽ không phát hiện lỗi.

### 6.2. Metrics đặt phía ngoài Validation

Nếu Metrics có precedence cao hơn Validation, lời gọi bị từ chối vẫn đi qua `metrics enter/exit`. Đây không nhất thiết là bug; nó là bug **nếu** metric được định nghĩa là “số thao tác đã qua xác thực và vào thân xử lý”. Phải ghi rõ metric đo điều gì rồi mới xác định thứ tự.

### 6.3. Retry đặt trong hay ngoài Audit

Giả sử có RetryAspect dùng `around` và `proceed` nhiều lần khi lỗi tạm thời. Nếu Audit nằm **bên trong** Retry, mỗi lần thử có thể sinh một cặp log. Nếu Audit **bên ngoài**, một request có thể có một bản ghi tổng thể cho toàn bộ quá trình retry. Cả hai đều hữu ích cho những mục đích khác nhau.

Nhưng cần đặc biệt cẩn trọng: **gọi lại `proceed` không mặc nhiên bảo đảm idempotence**. Với cập nhật dữ liệu, thanh toán hay gửi thông điệp, advice retry sai có thể nhân đôi side effect. Precedence phải được xem cùng chính sách retry, transaction boundary và cơ chế chống thực thi trùng.

### 6.4. Transaction và lưu dấu vết kết quả

Nếu một around advice ghi “success” ngay sau khi phần bên trong return nhưng **việc commit thực tế xảy ra ở tầng bên ngoài sau đó**, dấu vết có thể báo thành công sớm. Ngược lại, nếu phần ghi log nằm ngoài toàn bộ ranh giới transaction, nó có thể quan sát cả lỗi commit. Vấn đề không giải quyết chỉ bằng đặt tên `TransactionAspect` trước/ sau `AuditAspect`: phải biết **đúng điểm commit**, xử lý exception và yêu cầu bền vững của audit.

### 6.5. Mã chuẩn hóa dữ liệu và kiểm tra

Nếu NormalizationAspect sửa dữ liệu trước ValidationAspect, kết quả kiểm tra phụ thuộc phiên bản **đã chuẩn hóa**. Nếu đảo thứ tự, Validation kiểm tra dữ liệu thô. Khi request chứa whitespace, Unicode form, kiểu chữ hoặc format chưa chuẩn, hai kết quả có thể khác. Đặc tả cần nói rõ validation thực hiện trên dữ liệu nào và kiểm thử các ca gây khác biệt.

## 7. Tính toán thứ tự bằng đồ thị phụ thuộc

Khi nhiều aspect liên quan, xem mỗi aspect là một node; quan hệ “A phải bao ngoài hoặc chạy trước B” là một cạnh `A -> B` với **ngữ nghĩa được ghi rõ** (không chỉ là nhãn “A trước B”). Ví dụ:

```text
Audit -> Validation -> Metrics -> Original
```

Nếu quan hệ chỉ áp dụng tại một nhóm join point, hãy giới hạn phạm vi trong bản thiết kế. Một aspect có thể cần đi ngoài aspect khác ở luồng xử lý A nhưng đi trong ở luồng B; áp một precedence toàn cục lên hai aspect đó có thể **không mô tả được cả hai yêu cầu**. Khi xuất hiện mâu thuẫn, hãy tách aspect theo trách nhiệm, đổi vị trí join point hoặc thiết kế lại contract, thay vì đoán thứ tự.

### 7.1. Quy trình phân tích đồ thị

1. Liệt kê các aspect và join point mà chúng có thể cùng match.
2. Với từng cặp có tác động qua lại, ghi rõ **quan hệ bắt buộc** và lý do: dữ liệu, kết quả, side effect, exception hay phạm vi đo lường.
3. Chuyển quan hệ nhất quán thành các cạnh có hướng. Nếu phát hiện chu trình A -> B -> C -> A tại cùng nhóm join point, các yêu cầu có thể mâu thuẫn.
4. Xác định cách biểu đạt tương ứng bằng precedence, nhóm aspect hoặc cơ chế áp dụng của AOP engine.
5. Thêm **test hành vi** để kiểm tra thứ tự và đường lỗi; sơ đồ không thay thế test.

Topological sort hữu ích trong thiết kế để nhận biết thứ tự hợp lệ, nhưng không được nhầm nó với một thuật toán tự động của mọi AOP engine. Chính compiler/weaver mới có hợp đồng cụ thể về giải quyết precedence.

### 7.2. Phụ thuộc không đồng nghĩa mọi advice phải chạy

Một `before` có thể throw. Một `around` có thể return sớm hoặc gọi `proceed` nhiều lần. Điều kiện động như `if(...)` hoặc `cflow(...)` có thể khiến một advice chỉ chạy ở một số lời gọi. Vì vậy, precedence là quan hệ **điều phối khi advice cùng áp dụng**, còn số lần thực thi vẫn phụ thuộc đường đi thực tế.

## 8. Kiểm chứng thứ tự bằng test thay vì suy từ file build

Một test tốt nên có **cả đường thành công và đường lỗi**:

| Tình huống | Điều cần khẳng định |
| --- | --- |
| Input hợp lệ | Audit vào trước Validation; Metrics bắt đầu trước core; Metrics thoát trước Audit |
| Input không hợp lệ | Audit vẫn chạy; Validation ném lỗi; Metrics và core không chạy |
| Body ném exception | Hai finally thực thi đúng đường unwind nếu đã đi vào; caller nhận loại lỗi mong muốn |
| Around không gọi `proceed` | Advice/thân ở phía trong bị chặn theo contract |
| Around gọi `proceed` nhiều lần | Số lượt advice/thân bên trong được tính đúng, side effect an toàn |
| Nhiều threads | Không dùng một StringBuilder/log chung không đồng bộ để suy thứ tự tất cả thread |
| Một aspect mới cùng pointcut | Precedence vẫn rõ và test phản ánh contract mới |
| Compiler/weaver được nâng phiên bản | Thứ tự quan sát và handling của exception không đổi ngoài phạm vi được duyệt |

Với ví dụ ở mục 5, CI có thể chụp stdout rồi so với golden output ở trên. Khi kiểm thử thực tế, tốt hơn là thu **các sự kiện có cấu trúc** (ví dụ `AUDIT_ENTER`, `VALIDATE`, `METRICS_ENTER`, `CORE`, `METRICS_EXIT`, `AUDIT_EXIT`) vào một collector dùng riêng cho mỗi test hoặc mỗi luồng; từ đó khẳng định quan hệ có thứ tự và số lần. Đừng so chuỗi log toàn cục của nhiều thread như thể tất cả sự kiện phải theo một thứ tự tuần tự duy nhất.

**Không chỉ chạy cùng compiler một lần và kết luận precedence đúng.** Bản build tiếp theo có thể thêm aspect, nới wildcard pointcut hoặc đổi tập class được dệt. Cần giữ test khi refactor, đổi công cụ build, thay JDK và thay cấu hình dệt mã.

### 8.1. Phân biệt phát hiện thứ tự với phát hiện điểm dệt

`ajc -showWeaveInfo` hữu ích để biết advice được dệt tại join point nào. Tuy nhiên, thông tin đó **không thay thế** test xác nhận thứ tự thực thi và nhánh throw/return. Nên kết hợp:

- **Weaving inventory:** aspect và advice nào áp dụng tại method/join point nào.
- **Precedence declaration:** hợp đồng xếp lớp giữa các aspect phụ thuộc.
- **Behavior tests:** sự kiện thực tế, exception, số lần `proceed`, kết quả và side effect.
- **Bytecode/source inspection:** khi nghi build dùng class chưa dệt, class loader khác hoặc helper do weaver sinh.

Một bộ test chỉ xác nhận các aspect **đều chạy** vẫn có thể bỏ qua lỗi **chạy sai thứ tự**.

## 9. Những cách khắc phục sai lầm

### 9.1. Khai báo precedence tường minh, có chỗ sở hữu rõ ràng

Với AspectJ code-style, dùng `declare precedence` cho các cặp/nhóm có phụ thuộc. Đặt quy tắc tại module kiến trúc phù hợp, có bình luận mô tả **vì sao** cần thứ tự; kiểm tra rằng bản build thực sự bao gồm aspect chứa khai báo này.

Không phân tán những ràng buộc chồng chéo vào nhiều thư viện mà không có cơ chế rà soát. Khi version dependency thêm một aspect mới, xác minh pattern trong precedence vẫn chọn đúng tập aspect.

### 9.2. Ưu tiên contract theo hành vi thay vì thứ tự “tên nghe có vẻ đúng”

“Security trước Logging” quá mơ hồ: có thể cần logging **bao ngoài** security để ghi cả yêu cầu bị từ chối, hoặc logging **bên trong** security để tránh ghi dữ liệu chưa được xác thực. Phải ghi rõ ngữ nghĩa mong muốn và điều kiện fail. Tương tự, transaction ngoài/ trong retry ảnh hưởng rollback, phạm vi lock và thời điểm side effect.

### 9.3. Tránh coupling vòng và vòng phụ thuộc ngầm

Nếu Validation đọc dữ liệu do Normalization tạo, đồng thời Normalization lại cần kết quả Validation, đó là vòng logic. Không có một danh sách precedence tuyến tính nào đồng thời đáp ứng hai quan hệ ngược nhau tại cùng một phép tính. Tách bước, xác định dữ liệu trung gian hoặc chuyển một phần logic về nơi thích hợp.

### 9.4. Giảm số aspect cùng chặn một join point nếu cần

Nếu sáu aspect cùng viết lại cùng đối số, biến đổi kết quả và bắt exception, độ khó kiểm soát tăng mạnh. Có thể gộp logic thuộc **cùng một trách nhiệm** vào một aspect có thứ tự nội bộ rõ ràng hoặc tách join point theo giai đoạn xử lý. Chỉ gộp khi kiến trúc và khả năng bảo trì cho phép, tránh tạo aspect khổng lồ.

### 9.5. Đặt test âm tính, exception và kiểm thử tải

Các vấn đề precedence thường lộ rõ khi validation thất bại, `proceed` bị bỏ qua hoặc aspect bắt rồi đổi exception. Chọn ca test khiến các thứ tự **cho kết quả khác nhau**; chỉ chạy happy path thường không đủ. Với side effect và concurrency, kiểm tra thread context, tương tác lock, dữ liệu chia sẻ, retry và tính idempotent.

## 10. Gỡ lỗi khi thứ tự quan sát khác kỳ vọng

Thực hiện theo trình tự:

1. **Đúng bản runtime chưa?** Kiểm tra classpath và lớp đã dệt. Nếu dùng load-time weaving, xem cấu hình agent/class loader và thời điểm nạp lớp.
2. **Pointcut có cùng match join point?** So chữ ký, `call` so với `execution`, phạm vi `within`, dynamic conditions.
3. **Các aspect có concrete không?** Kiểm tra aspect được dệt thực sự; abstract aspect và pattern inheritance có thể tác động đến precedence.
4. **`declare precedence` có được biên dịch/nạp không?** Một file khai báo chỉ nằm trong source tree nhưng không được đưa vào build sẽ không có hiệu lực.
5. **Quan hệ có bị che bởi khai báo khác?** Tìm các ràng buộc tạo vòng hoặc mâu thuẫn tại cùng join point; không dựa vào thứ tự compiler input.
6. **Tầng quanh `proceed` có short-circuit không?** Đặt breakpoint trước/sau `proceed` và ở advice phía trong.
7. **Có exception không?** `before` throw hoặc `around` bắt/throw có thể cắt ngắn trình tự log.
8. **Logger có bất đồng bộ không?** Thứ tự dòng xuất log giữa threads không hẳn phản ánh thứ tự sự kiện trong một call stack.
9. **Có thay đổi tại weaving không?** So weave info, artifact, cấu hình và bản weaver.

Trong ví dụ, breakpoint ở `AuditAspect` trước `proceed`, `ValidationAspect` trước kiểm tra, `MetricsAspect` trước `proceed` và thân `TransferService` sẽ cho biết cụ thể tầng nào đã chạy. Với input `0`, nếu debugger không vào `MetricsAspect` thì đó là hành vi đúng theo ràng buộc đã khai báo.

## 11. Các ngộ nhận và lỗi phổ biến

**“File aspect nào được compile trước thì advice của nó chạy trước.”** Không có hợp đồng như vậy cho các aspect độc lập không có quan hệ precedence.

**“Tên aspect bắt đầu bằng A sẽ ưu tiên hơn B.”** Thứ tự chữ cái không phải quy tắc ngữ nghĩa của AOP.

**“Advice ưu tiên cao chạy đầu cả khi vào lẫn khi ra.”** Tầng ưu tiên cao thường nằm ngoài: đi vào trước, nhưng `after`/phần sau `proceed` của tầng ngoài chạy sau khi phần phía trong hoàn tất.

**“Khai báo thứ tự là xong, khỏi cần test.”** Nếu thứ tự khai báo sai hoặc dynamic pointcut/exception làm cắt luồng, hệ thống vẫn có thể sai.

**“Chỉ cần mọi advice được gọi là đủ.”** Thứ tự thực hiện có thể thay đổi kết quả, exception, side effect và metric.

**“`around` luôn phải gọi `proceed` đúng một lần.”** Nó có thể gọi không lần nào hoặc nhiều lần tùy cú pháp và ngữ nghĩa. Thiết kế nghiệp vụ có thể yêu cầu đúng một lần nhưng cần kiểm thử điều đó.

**“`after returning` và `after` luôn giống nhau.”** `after` kiểu finally bao cả đường throw; `after returning` chỉ trên return bình thường.

**“Thêm một aspect mới không ảnh hưởng aspect cũ.”** Aspect mới có thể chia sẻ join point, chặn tiếp tục, biến đổi kết quả hoặc làm precedence thiếu xác định.

**“Khai báo toàn cục một thứ tự cho mọi aspect là an toàn.”** Có thể tạo coupling khó bảo trì và mâu thuẫn nếu các cặp cần thứ tự khác nhau ở các nhóm join point.

**“Quan sát được thứ tự đúng qua hai lần chạy là đủ chứng minh.”** Cần ràng buộc tường minh và test hồi quy, nhất là khi nâng công cụ hoặc đổi phạm vi weaving.

## 12. Checklist thiết kế trước khi phát hành

1. Liệt kê **tập aspect có thể cùng match** từng nhóm join point quan trọng.
2. Viết **thứ tự phụ thuộc theo ngữ nghĩa**: dữ liệu cần có, vị trí xử lý exception, ranh giới side effect, đo lường và kiểm toán.
3. Xác định aspect nào **bao ngoài** và aspect nào **nằm trong**; hiểu thứ tự khi đi vào và khi unwind.
4. Phát hiện mâu thuẫn hoặc vòng phụ thuộc, điều chỉnh thiết kế trước khi cấu hình.
5. Khai báo precedence bằng cơ chế chính thức của AOP engine; với AspectJ code-style là `declare precedence` khi thích hợp.
6. Kiểm tra các type pattern, abstract/concrete aspects và những khai báo precedence chồng lấn.
7. Kiểm thử happy path, validation thất bại, body throw, `around` short-circuit, retry và dữ liệu bị biến đổi.
8. Dùng weave info hoặc artifact inspection để chắc chắn các aspect đã được dệt vào đúng join point.
9. Giữ test hồi quy chạy khi thay đổi dependency, aspect, JDK, weaver và cấu hình.
10. Chỉ kết luận hệ thống đúng khi **precedence được xác định và quan sát hành vi phù hợp contract**.

**Kết luận:** khi hai hoặc nhiều aspect có quan hệ phụ thuộc, để thứ tự mặc định là một lỗi thiết kế tiềm ẩn. Hãy xác định rõ **ai phải bao ngoài ai, điều gì xảy ra trên đường thành công và đường lỗi**, biểu đạt quan hệ bằng cơ chế precedence phù hợp và bảo vệ nó bằng kiểm thử hành vi. Đừng dựa vào thứ tự tình cờ từ tên file, build hay một lần debug.

## Tài liệu tham khảo

- Eclipse AspectJ Programming Guide — Advice Precedence, quy tắc giữa/cùng aspect và ảnh hưởng của `proceed`: https://eclipse.dev/aspectj/doc/latest/progguide/semantics-advice.html
- Eclipse AspectJ Programming Guide — `declare precedence`, TypePatternList và các khai báo mâu thuẫn: https://eclipse.dev/aspectj/doc/latest/progguide/semantics-declare.html
- Eclipse AspectJ Quick Reference — cú pháp advice và `declare precedence`: https://eclipse.dev/aspectj/doc/latest/progguide/quickreference.html
- Eclipse AspectJ Language Semantics — precedence ở concrete/sub-aspects: https://eclipse.dev/aspectj/doc/latest/progguide/semantics.html
