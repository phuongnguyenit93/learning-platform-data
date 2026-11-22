# Điều kiện trước, điều kiện sau và bất biến của chương trình trong AOP

## 1. Mục tiêu bài học

**Design by Contract (DbC)** xem một thao tác như một thỏa thuận giữa **bên gọi** và **bên cung cấp**:

- **Điều kiện trước (precondition):** những gì phải đúng trước khi thao tác bắt đầu trong phạm vi hợp đồng.
- **Điều kiện sau (postcondition):** những gì được bảo đảm khi thao tác kết thúc theo đường kết quả mà hợp đồng mô tả.
- **Bất biến (invariant):** tính chất cần được duy trì tại các điểm quan sát hợp lệ trong vòng đời của đối tượng/hệ thống.

Trong **Aspect-Oriented Programming (AOP)**, **aspect** cho phép gắn logic xuyên suốt vào các **join point** được **pointcut** lựa chọn; **advice** có thể quan sát hoặc thay đổi đường vào, đường ra và đường lỗi. Vì thế AOP vừa là một công cụ để **kiểm tra hợp đồng một cách tập trung**, vừa có thể là **nguồn phá vỡ hợp đồng** khi advice đổi tham số, kết quả, ngoại lệ hoặc trạng thái.

Ví dụ: một thao tác cộng số dư có hợp đồng:

```text
Pre:  delta > 0
Post: newBalance == oldBalance + delta
Inv:  balance >= 0
```

Nếu một around advice trả `oldBalance` thay vì kết quả mới mà không gọi phần gốc, caller có thể nhận một giá trị đúng kiểu Java nhưng **sai hậu điều kiện**. Nếu after advice ném lỗi sau khi nghiệp vụ đã cập nhật số dư, caller nhận exception nhưng trạng thái vẫn có thể đã thay đổi.

Bài tập trung vào **AOP nói chung**, không phụ thuộc một framework cụ thể. Cú pháp kiểu `around/proceed` ở các phần khái niệm là **mã giả**; khả năng join point, thứ tự advice, ngoại lệ và weaving phải đối chiếu với công cụ thực tế.

Kết thúc bài, người học cần:

1. Phân biệt precondition, postcondition và invariant với input validation hoặc monitoring đơn thuần.
2. Biết điểm kiểm tra hợp đồng khi có before, after returning, after throwing và around advice.
3. Nhận ra cách một advice có thể làm hợp đồng mạnh hơn, yếu đi hoặc sai lệch.
4. Thiết kế hợp đồng cho nhánh thành công **và** nhánh ngoại lệ.
5. Hiểu giới hạn proxy, weaving, lời gọi nội bộ và dữ liệu bất đồng bộ.
6. Viết được kiểm thử phát hiện vi phạm thay vì chỉ xác nhận method trả đúng kiểu.
7. Dùng Java 17 để tái hiện đầy đủ các đường hợp đồng bình thường và bất thường.

## 2. Hợp đồng phương thức dưới dạng bộ ba Hoare

Một mô hình kinh điển là:

```text
{ P } Operation { Q }
```

Trong đó:

- `P` là điều kiện trước.
- `Operation` là thao tác đang xét.
- `Q` là điều kiện sau của **đường kết thúc được giả thiết**, thường là kết thúc bình thường nếu không định nghĩa riêng nhánh exception.

Ý nghĩa cơ bản: **nếu `P` đúng trước khi chạy, và thao tác kết thúc bình thường theo các giả thiết phù hợp, thì `Q` phải đúng sau thao tác**.

Ký hiệu này **không tự bảo đảm** chương trình sẽ kết thúc, không tự ngụ ý rollback khi ném exception và không bảo đảm mọi side effect bên ngoài đều được hoàn tác.

### 2.1. Ví dụ trạng thái

Một đối tượng `Counter` có giá trị `balance`:

```text
pre_add(delta): delta > 0
post_add(old, delta, result, current):
    result == old + delta
    AND current == result
invariant: current >= 0
```

Điều kiện trước ràng buộc **trách nhiệm caller**. Hậu điều kiện và bất biến công khai ràng buộc **trách nhiệm implementation** khi caller đã đáp ứng tiền điều kiện.

Với số nguyên hữu hạn của Java, còn phải định nghĩa **chính sách tràn số**. Nếu dùng `int`, phép cộng có thể overflow; một thiết kế production có thể dùng `Math.addExact` hoặc ràng buộc đầu vào sao cho không vượt miền giá trị. Ví dụ chạy bên dưới dùng số nhỏ để không chạm tình huống ấy, nhưng không nên coi đây là chi tiết có thể bỏ qua khi thiết kế hợp đồng thật.

### 2.2. Trách nhiệm khi tiền điều kiện sai

Nếu `delta <= 0`, hợp đồng trên không cam kết thực hiện phép cộng thành công. API có thể chọn ném `IllegalArgumentException` hay một lỗi riêng, nhưng phải **nêu rõ trong hợp đồng**, thay vì để caller đoán.

Không nên đồng nhất kiểm tra precondition với một cơ chế bảo vệ hoàn chỉnh. Với một bất biến bảo mật quan trọng, việc xác thực tại ranh giới tin cậy vẫn cần thiết, kể cả khi một caller “được kỳ vọng” cung cấp dữ liệu hợp lệ.

## 3. Phân biệt ba loại khẳng định

| Tiêu chí | Precondition | Postcondition | Invariant |
| --- | --- | --- | --- |
| Được kiểm tra khi nào? | Trước khi vào thao tác được bảo vệ | Sau khi thao tác hoàn tất theo nhánh được mô tả | Ở các ranh giới trạng thái quan sát được phù hợp |
| Dựa trên dữ liệu gì? | Tham số, quyền, trạng thái ban đầu | Kết quả, trạng thái mới, trạng thái cũ | Trạng thái tổng quát của đối tượng/hệ thống |
| Ai chịu trách nhiệm chính? | Caller đáp ứng hợp đồng | Implementation/advice có trách nhiệm bảo đảm | Thành phần quản lý vòng đời và các phép biến đổi |
| Ví dụ | Số tiền dương | Số dư mới đúng bằng số dư cũ cộng tiền | Số dư không âm |
| Vi phạm thường gây gì? | Từ chối lời gọi/lỗi đầu vào | Lỗi correctness sau một thao tác | Phát hiện object đang ở trạng thái không hợp lệ |
| Điều gì không suy ra được? | Không xác nhận thao tác đã chạy | Không bảo đảm rollback nếu sai | Không nhất thiết đúng tại mọi instruction nội bộ |

**Bất biến không có nghĩa mọi trạng thái trung gian đều hợp lệ.** Một thuật toán có thể tạm thay đổi nhiều field trong một vùng xử lý được đồng bộ hóa rồi khôi phục tính nhất quán trước khi công bố kết quả. Ranh giới kiểm tra invariant phải xác định trước, không tự áp đặt kiểm tra tại từng dòng nguồn.

## 4. Vì sao AOP hữu ích khi kiểm tra hợp đồng?

Một số hợp đồng xuất hiện lặp lại ở nhiều thao tác:

- Tham số không null, nằm trong miền hợp lệ.
- Đối tượng đang ở một trạng thái vòng đời cho phép thực hiện operation.
- Kết quả không null với nhóm API cam kết không null.
- Thời lượng hoặc số lần gọi nằm trong một giới hạn chính sách được xác định.
- Sau một thao tác, invariant của một tập object còn đúng.
- Khi kết thúc bằng exception, trạng thái được giữ trong tập trạng thái hợp lệ cho phép.

Một aspect có thể đặt các kiểm tra này ở những join point phù hợp mà không lặp lại từng khối mã trong mọi method.

Tuy nhiên, **điểm chọn sai hoặc thứ tự sai** có thể biến kiểm tra hợp đồng thành lỗi khó bảo trì:

- Pointcut quá rộng kiểm tra method không thuộc hợp đồng.
- Before advice nhìn dữ liệu đã bị một advice khác thay đổi thay vì input gốc.
- After advice kiểm tra kết quả **trước khi** một advice khác biến đổi kết quả.
- Một around advice bỏ `proceed` nhưng vẫn trả giá trị giả thành công.
- Hợp đồng chỉ chạy qua proxy; lời gọi trực tiếp target đi vòng.
- Kiểm tra invariant dùng getter mà getter cũng thuộc pointcut, gây vòng lặp advice.

AOP giúp **tách riêng** một phần kiểm tra, nhưng không biến tính đúng đắn thành hệ quả tự động của việc khai báo pointcut.

## 5. Đặt precondition trong chuỗi before advice

Mô hình đơn giản:

```text
Caller
  -> ContractBefore
       -> OriginalMethod
```

Mã giả:

```text
around add(delta):
    require delta > 0
    return proceed(delta)
```

Khi `delta <= 0`, một contract advice có thể chặn ngay **trước khi chạy target**, nếu nó đã là lớp ngoài thích hợp.

### 5.1. Thứ tự với advice biến đổi input

Giả sử có hai advice:

- `NormalizeAdvice` sửa dữ liệu đầu vào.
- `ContractAdvice` kiểm tra precondition.

Hai thứ tự khác nhau:

```text
Contract(Normalize(Business))
Normalize(Contract(Business))
```

Nếu normalization thay đổi tham số, `Contract` ở ngoài kiểm tra **input do caller cung cấp**; ở trong nó kiểm tra **input sau normalization**. Cả hai có thể hợp lý tùy hợp đồng, nhưng không tương đương.

Ví dụ:

```text
Caller passes rawId = "   A   "
Normalize trims to "A"

Contract outer: kiểm tra input thô
Contract inner: kiểm tra input đã chuẩn hóa
```

Phải chọn ngữ nghĩa rõ ràng: **ai chịu trách nhiệm làm dữ liệu hợp lệ?** Nếu hợp đồng của public API cho phép khoảng trắng và chủ động chuẩn hóa, kiểm tra giá trị thô bằng điều kiện quá mạnh có thể từ chối một input hợp lệ.

### 5.2. Không biến precondition thành một lỗi quan sát phụ

Nếu advice trước chỉ dùng telemetry, đừng để lỗi telemetry trở thành “không đáp ứng precondition” trừ khi hợp đồng thật yêu cầu. Precondition thất bại thường cần **thông báo đúng loại**, tách khỏi lỗi của cơ chế ghi log.

## 6. Kiểm tra postcondition sau khi trả kết quả bình thường

Một hậu điều kiện có thể phụ thuộc:

- Giá trị trả về.
- Trạng thái mới của object.
- Tham số đã được truyền.
- Trạng thái trước khi vào operation (ký hiệu `old`).
- Tác dụng phụ được cam kết trong ranh giới quan sát được.

Mã giả:

```text
around add(delta):
    old = readBalance()
    result = proceed(delta)
    require result == old + delta
    require readBalance() == result
    return result
```

Đây là mã giả không thuộc một DSL cụ thể. `require` sau `proceed` biểu diễn **kiểm tra postcondition**, không phải precondition về mặt ý nghĩa.

### 6.1. Vì sao cần `old`?

Nếu chỉ xem trạng thái sau:

```text
result >= 0
```

ta chưa chứng minh phép cộng đã thêm đúng `delta`. Hợp đồng mạnh hơn so sánh trạng thái cũ và mới:

```text
newBalance == oldBalance + delta
```

Phần `oldBalance` cần được ghi lại **trước khi operation tạo side effect**, và phải bảo đảm snapshot đại diện đúng đối tượng/invocation được kiểm tra.

### 6.2. Chụp snapshot không miễn phí

Sao chép toàn bộ object graph chỉ để xác minh hậu điều kiện có thể tốn bộ nhớ, thời gian hoặc tạo vòng lặp khi có object tham chiếu lẫn nhau. Với API lớn, chọn **những thuộc tính cần thiết** và dùng cơ chế snapshot/differencing có hợp đồng rõ ràng.

Cần phân biệt **bản sao giá trị** với reference đến object mutable. Lưu `oldList = currentList` rồi sửa `currentList` sẽ không cho một bản chụp độc lập để kiểm tra thay đổi.

### 6.3. Postcondition chỉ kiểm được phần có thể quan sát

Nếu operation gửi message sang hệ thống ngoài rồi trả `accepted`, việc kiểm tra một biến cục bộ không chứng minh phía nhận đã xử lý message. Hợp đồng nên tách “đã gửi”, “đã được broker chấp nhận” và “đã được consumer xử lý”, vì đây là các ranh giới khác nhau.

## 7. Bất biến của đối tượng và các ranh giới kiểm tra

Một **class invariant** diễn tả trạng thái hợp lệ của một object tại các điểm công khai được xác định.

Ví dụ:

```text
Account:
    balance >= 0
    currency in supportedCurrencies
    accountId != null
```

Một chiến lược kiểm tra:

1. Kiểm invariant khi nhận lời gọi vào public operation.
2. Kiểm precondition của operation.
3. Thực hiện operation.
4. Kiểm postcondition trên đường trả bình thường.
5. Kiểm invariant trước khi trả control cho caller.
6. Với exception, áp dụng **hợp đồng trạng thái lỗi** (nếu có) thay vì mặc định mọi hậu điều kiện thông thường vẫn đúng.

**Điểm quan trọng:** không phải invariant nào cũng phải đúng ngay trong constructor trước khi toàn bộ field được thiết lập. Các public method được gọi trong constructor còn có rủi ro “object chưa hoàn tất khởi tạo”.

### 7.1. Invariant và thao tác private/helper

Một public method có thể gọi các private helper làm trạng thái tạm thời không nhất quán rồi phục hồi trước khi return. Nếu một aspect weave vào mọi method execution (bao cả helper), việc áp invariant tại từng helper có thể **báo false positive**.

Cần định nghĩa hợp đồng ở đúng boundary (public operation, transaction boundary, quiescent state...) và hiểu khả năng can thiệp nội bộ của công cụ.

### 7.2. Shared state và tính nhất quán

Trong hệ thống concurrent, đọc từng field không có đồng bộ thích hợp có thể thấy **snapshot không nhất quán**. Một invariant có thể đúng ở cả trước và sau update nhưng bộ kiểm tra đọc xen vào giữa và cho kết quả sai.

Các lựa chọn cần xét: lock, immutable snapshot, versioning, atomic state, transaction isolation hoặc quy tắc thread confinement. Kiểm tra hợp đồng không thay thế cơ chế đồng bộ và còn có thể ảnh hưởng lịch chạy của thread.

## 8. Đường lỗi: hợp đồng nào còn có hiệu lực?

Một điểm dễ sai là áp postcondition của đường thành công sau **mọi** ngoại lệ.

Ví dụ:

```text
Pre: transfer amount > 0
Normal Post: debit completed AND credit completed
Exceptional Guarantee: không có chuyển khoản được xác nhận thành công
Invariant: tổng số dư nội bộ thỏa điều kiện nhất quán
```

Nếu transfer ném lỗi mạng ở giữa, **không thể** suy rằng Normal Post vẫn phải đúng. Thay vào đó, hợp đồng cần nói rõ:

- Exception nào có thể thoát?
- Trạng thái nào vẫn được phép sau exception?
- Có bảo đảm rollback hay không?
- Có thể đã tạo side effect ở hệ thống ngoài không?
- Caller được phép retry trong điều kiện nào?
- Trạng thái có thể xác minh lại qua request ID/idempotency key không?

### 8.1. Ba mức bảo đảm an toàn khi exception

Trong thiết kế exception-safety thường phân biệt những mục tiêu:

| Bảo đảm | Nghĩa khái quát | Không đồng nghĩa |
| --- | --- | --- |
| **No-throw guarantee** | Thao tác được thiết kế không cho exception thoát trong phạm vi công bố | Không phải mọi hoạt động đều chắc chắn thành công nếu có kênh báo lỗi khác |
| **Strong guarantee** | Khi thao tác thất bại, trạng thái liên quan được giữ như trước, theo phạm vi xác định | Không có nghĩa mọi side effect từ xa cũng rollback |
| **Basic guarantee** | Sau lỗi, đối tượng vẫn ở trạng thái hợp lệ, không rò tài nguyên, nhưng một phần trạng thái có thể thay đổi | Không phải operation đã hoàn tất |

Các từ trên là **mức bảo đảm theo hợp đồng thiết kế**, không phải tự động có sẵn do AOP hay Java exception. Một thao tác có thể chọn bảo đảm phù hợp với miền nghiệp vụ.

### 8.2. After throwing có thể kiểm exceptional invariant

Một after-throwing advice có thể ghi nguyên nhân rồi kiểm trạng thái còn hợp lệ:

```text
try:
    result = proceed()
    checkNormalPost(result)
    return result
catch original:
    checkExceptionalInvariant()
    throw original
```

Đây là mã giả. Cẩn thận: nếu `checkNormalPost` nằm trong `try`, lỗi do **chính kiểm tra hậu điều kiện** cũng đi vào catch và bị gán nhầm là lỗi từ `proceed`. Nên thiết kế phạm vi `try/catch` theo đúng **nguồn lỗi muốn phân loại**.

## 9. Thứ tự advice quyết định hợp đồng đang kiểm tra cái gì

Giả sử:

```text
ContractAdvice(
    NormalizeAdvice(
        Business
    )
)
```

Contract ngoài nhìn thấy input thô và kết quả **đã đi qua Normalize**.

Nếu đảo lại:

```text
NormalizeAdvice(
    ContractAdvice(
        Business
    )
)
```

Contract trong có thể nhìn input đã biến đổi, nhưng chưa thấy biến đổi kết quả do Normalize ngoài thực hiện sau khi tiếp tục.

Từ góc độ correctness, cần quyết định **hợp đồng của tầng nào**:

- Contract của **target gốc**.
- Contract của **public facade/proxy** mà caller nhìn thấy.
- Contract của **một advice** độc lập.
- Contract của **composition** gồm tất cả advice.

Một hệ thống có thể cần nhiều lớp kiểm tra khác nhau để bảo đảm **mỗi tầng** và **kết quả cuối cùng** đều đúng.

### 9.1. Chỉ kiểm target không đủ

Nếu target trả kết quả đúng hậu điều kiện nhưng after advice cộng thêm phí hoặc đổi đối tượng trả về, hợp đồng public của caller có thể bị vi phạm **sau khi target kết thúc**.

### 9.2. Chỉ kiểm kết quả cuối cũng chưa đủ

Nếu một advice bên trong gây side effect không phù hợp rồi advice ngoài sửa lại output, caller có thể nhận kết quả hợp lệ nhưng hệ thống đã thay đổi trạng thái sai.

Khi cần tính đúng đắn nội bộ, phải có invariant/contract tương ứng ở tầng phát sinh side effect, không chỉ ở lớp ngoài cùng.

## 10. Around advice có thể phá vỡ hợp đồng thế nào?

Around advice có thể thực hiện các thay đổi mạnh:

1. **Không gọi proceed:** chặn operation.
2. **Gọi proceed một lần:** phần gốc hoạt động bình thường.
3. **Gọi proceed nhiều lần:** retry/repetition, nếu công cụ cho phép.
4. **Thay tham số:** phần gốc nhận input khác input caller.
5. **Thay kết quả:** caller nhận result khác target tạo.
6. **Bắt và đổi exception:** caller quan sát kiểu lỗi khác.
7. **Trả fallback:** một lỗi từ phần gốc biến thành kết quả bình thường.

Mỗi thay đổi phải có **hợp đồng công khai** và kiểm thử tương ứng.

### 10.1. Short-circuit và postcondition

Nếu một around advice không gọi `proceed` nhưng trả `0`, trong khi hợp đồng của operation yêu cầu:

```text
result == old + delta
```

thì có thể vi phạm postcondition, dù Java type-check hoàn toàn hợp lệ.

Nếu yêu cầu cho phép trả fallback, **hợp đồng nên mô tả trạng thái fallback** và bảo đảm giá trị trả về không giả thành công. Ví dụ “trả bản cache có độ mới tối đa 30 giây” là một nhánh hợp đồng khác với “đã cập nhật cơ sở dữ liệu”.

### 10.2. Retry và hậu điều kiện

Nếu `proceed` chạy hai lần, invariant có thể được giữ sau mỗi lần nhưng **hậu điều kiện của operation logic một lần** bị sai (số dư tăng gấp đôi). Một around advice retry phải hiểu operation có idempotent không và thử lại có tái thực thi side effect không.

### 10.3. Exception translation

Đổi `IOException` thành `DomainUnavailable` có thể hợp đồng public, nhưng nếu không giữ `cause` sẽ khó truy vết nguyên nhân. Nếu error taxonomy làm caller retry sai, đó cũng là một vấn đề hợp đồng, không chỉ logging.

## 11. Mã Java 17 chạy được: pre, post, invariant và exception path

Java không có cú pháp AOP weaving chung tích hợp trong ngôn ngữ. Ví dụ dùng **JDK dynamic proxy** làm một lớp interceptor để minh họa việc kiểm tra hợp đồng tại **lời gọi qua giao diện**.

Chương trình có bốn trường hợp:

- **`ok`:** precondition, postcondition và invariant đều đúng.
- **`invalid`:** input vi phạm precondition, target không được gọi thêm.
- **`broken-post`:** target thực sự thay đổi state nhưng trả kết quả sai hậu điều kiện.
- **`throw-after-mutation`:** target thay đổi state rồi ném exception; invariant vẫn đúng nhưng không có strong rollback guarantee.

Tạo tệp `AopContractDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AopContractDemo {

    interface Counter {
        int add(int amount);
        int value();
    }

    static final class CoreCounter implements Counter {
        private int total;
        private final boolean wrongResult;
        private final boolean failAfterMutation;

        CoreCounter(int initial, boolean wrongResult,
                    boolean failAfterMutation) {
            this.total = initial;
            this.wrongResult = wrongResult;
            this.failAfterMutation = failAfterMutation;
        }

        @Override
        public int add(int amount) {
            total += amount;
            System.out.println("business:add:" + amount + ":total:" + total);

            if (failAfterMutation) {
                throw new IllegalStateException("storage unavailable");
            }

            return wrongResult ? total + 1 : total;
        }

        @Override
        public int value() {
            return total;
        }
    }

    static Counter withContract(Counter target) {
        return (Counter) Proxy.newProxyInstance(
                Counter.class.getClassLoader(),
                new Class<?>[] {Counter.class},
                (Object proxy, Method method, Object[] args) -> {
                    if (!method.getName().equals("add")) {
                        return method.invoke(target, args);
                    }

                    int amount = (Integer) args[0];
                    System.out.println("contract:pre:" + amount);

                    if (amount <= 0) {
                        throw new IllegalArgumentException(
                                "amount must be positive");
                    }

                    int oldValue = target.value();
                    if (oldValue < 0) {
                        throw new IllegalStateException(
                                "entry invariant violated");
                    }

                    System.out.println("advice:before");

                    try {
                        Object raw;
                        try {
                            raw = method.invoke(target, args);
                        } catch (InvocationTargetException wrapped) {
                            Throwable original = wrapped.getCause();
                            System.out.println("advice:throw:"
                                    + original.getClass().getSimpleName());

                            int current = target.value();
                            System.out.println("contract:exceptional-state:"
                                    + current);

                            if (current < 0) {
                                throw new IllegalStateException(
                                        "exceptional invariant violated",
                                        original);
                            }
                            throw original;
                        }

                        int result = (Integer) raw;
                        System.out.println("contract:post:expected:"
                                + (oldValue + amount) + ":actual:" + result);
                        if (result != oldValue + amount) {
                            throw new IllegalStateException(
                                    "postcondition violated");
                        }

                        int current = target.value();
                        System.out.println("contract:invariant:" + current);
                        if (current < 0) {
                            throw new IllegalStateException(
                                    "exit invariant violated");
                        }

                        System.out.println("advice:after");
                        return result;
                    } finally {
                        System.out.println("advice:finally");
                    }
                }
        );
    }

    static void execute(String label, Counter counter, int amount) {
        System.out.println("case:" + label);
        try {
            System.out.println("caller:result:" + counter.add(amount));
        } catch (RuntimeException error) {
            System.out.println("caller:error:"
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage());
        }
        System.out.println("caller:state:" + counter.value());
    }

    public static void main(String[] args) {
        Counter normal = withContract(new CoreCounter(10, false, false));
        Counter incorrect = withContract(new CoreCounter(10, true, false));
        Counter exceptional = withContract(new CoreCounter(10, false, true));

        execute("ok", normal, 5);
        execute("invalid", normal, 0);
        execute("broken-post", incorrect, 5);
        execute("throw-after-mutation", exceptional, 5);
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac AopContractDemo.java
java AopContractDemo
```

**Đầu ra chính xác:**

```text
case:ok
contract:pre:5
advice:before
business:add:5:total:15
contract:post:expected:15:actual:15
contract:invariant:15
advice:after
advice:finally
caller:result:15
caller:state:15
case:invalid
contract:pre:0
caller:error:IllegalArgumentException:amount must be positive
caller:state:15
case:broken-post
contract:pre:5
advice:before
business:add:5:total:15
contract:post:expected:15:actual:16
advice:finally
caller:error:IllegalStateException:postcondition violated
caller:state:15
case:throw-after-mutation
contract:pre:5
advice:before
business:add:5:total:15
advice:throw:IllegalStateException
contract:exceptional-state:15
advice:finally
caller:error:IllegalStateException:storage unavailable
caller:state:15
```

### 11.1. Trường hợp `ok`

Input `amount=5` thỏa precondition. Snapshot `oldValue=10`. Target tăng `total` thành 15 và trả 15, nên postcondition `result == old+amount` đúng. Invariant `total>=0` vẫn đúng. Caller nhận kết quả 15.

### 11.2. Trường hợp `invalid`

`amount=0` vi phạm precondition. Handler ném `IllegalArgumentException` **trước khi vào khối chứa lời gọi target**; vì vậy không có dòng `business:add`, `advice:before` hay `advice:finally` cho ca này. State vẫn là 15 sau ca trước.

Đây là ví dụ cho thấy **không phải mọi finally của mọi advice đều bắt buộc chạy khi precondition thất bại**: điều đó còn phụ thuộc phạm vi try/finally đã được thiết lập.

### 11.3. Trường hợp `broken-post`

Target tăng state từ 10 lên 15 nhưng cố ý trả 16. Handler phát hiện hậu điều kiện sai rồi ném `IllegalStateException`.

**Quan sát quan trọng:** caller nhận exception **nhưng state đã là 15**. Phát hiện postcondition sai **không tự hoàn tác mutation**. Nếu cần strong exception guarantee, cơ chế transaction/compensation hoặc thiết kế phép biến đổi phải thực sự cung cấp bảo đảm ấy.

### 11.4. Trường hợp `throw-after-mutation`

Target cập nhật state lên 15 rồi ném `IllegalStateException("storage unavailable")`. Handler kiểm **exceptional invariant** `total>=0` và truyền lỗi gốc lên caller.

Ở đây **basic guarantee** về invariant vẫn có thể đúng trong khi **strong guarantee** không đúng: state thay đổi so với trước khi gọi.

### 11.5. Giới hạn ví dụ

- Đây là **wrapper qua JDK proxy**, không phải công cụ tự phân tích pointcut hay weave bytecode.
- Chỉ invocation đi qua `Counter` proxy mới kích hoạt các kiểm tra; gọi trực tiếp `CoreCounter` sẽ bỏ qua handler.
- Handler chỉ áp hợp đồng riêng cho `add`; `value` được ủy quyền như getter để đọc state phục vụ ví dụ.
- `Method.invoke` bọc exception do target ném trong `InvocationTargetException`; code gỡ wrapper để giữ cause từ target.
- Ví dụ xử lý `int` với số nhỏ; bản production cần xử lý overflow và concurrent updates.
- Hợp đồng đang được kiểm tra tại **ranh giới proxy**, không chứng minh mọi method nội bộ hoặc lời gọi ngoài proxy đều được bảo vệ.

## 12. Vì sao phạm vi try/catch khi kiểm postcondition phải rõ?

Một cách viết dễ nhầm:

```text
try:
    result = proceed()
    checkPostcondition(result)
    logSuccess()
    return result
catch error:
    logBusinessFailure(error)
    throw error
```

Nếu `checkPostcondition` ném `ContractViolation`, catch cũng gắn nhãn “business failure”, mặc dù phần gốc có thể đã hoàn tất. Nếu `logSuccess` ném lỗi, tình trạng tương tự xảy ra.

Một tổ chức ranh giới dễ hiểu hơn:

```text
try:
    result = proceed()
catch continuationError:
    checkExceptionalGuarantee(continuationError)
    throw continuationError

checkNormalPostcondition(result)
checkInvariant()
return result
```

Cần định nghĩa chính sách cho **lỗi của chính phép kiểm tra hợp đồng**. Nó không phải lúc nào cũng nên bị xử lý như lỗi từ `proceed`.

### 12.1. Thứ tự giữa kiểm postcondition và kiểm invariant

Một thiết kế có thể chọn:

```text
Business return
  -> check normal postcondition
  -> check invariant
  -> return caller
```

Thiết kế khác có thể kiểm invariant trước postcondition. **Không có thứ tự được mọi AOP engine bảo đảm**. Nếu một phép kiểm tra ném lỗi, các phép kiểm tra sau có thể không chạy, khiến hệ thống chỉ báo một vi phạm trong nhiều vi phạm.

Hãy xác định thứ tự phục vụ **ngữ nghĩa và chẩn đoán**, tránh dựa vào thứ tự tình cờ giữa nhiều advice chưa khai báo precedence.

## 13. Hợp đồng của advice: aspect cũng là thành phần có trách nhiệm

Không chỉ method nghiệp vụ mới có hợp đồng. Một advice cũng có thể yêu cầu:

- Đầu vào context phải có thuộc tính cần thiết.
- Không được ghi dữ liệu nhạy cảm trong telemetry.
- Nếu chỉ đo thời gian, phải giữ nguyên return value/exception theo chính sách.
- Nếu có quyền retry, phải tôn trọng giới hạn attempt và idempotency.
- Nếu tự thay kết quả, kết quả thay phải thỏa hợp đồng public.
- Khi cleanup thất bại, phải xử lý primary/suppressed theo chính sách.
- Không giữ mutable invocation state giữa hai request độc lập.
- Không gọi `proceed` nếu điều kiện bảo mật từ chối.

### 13.1. Advice quan sát có “hợp đồng không can thiệp”

Với aspect chỉ logging, một yêu cầu tự nhiên:

```text
Nếu target returns R: caller vẫn nhận R.
Nếu target throws E: caller vẫn nhận E.
Số lần target chạy không bị thay đổi.
Advice không sửa args hoặc domain state.
```

Đây là **hợp đồng về tính trong suốt quan sát**. Nhưng chính logger có thể ném exception hoặc thay timing/locking, nên cần thiết kế cách xử lý telemetry failure và kiểm thử thực tế.

### 13.2. Advice làm chính sách cần hợp đồng mạnh hơn

Với authorization advice, **thay đổi hành vi** là có chủ đích: nó có thể không gọi `proceed` khi không được phép. Khi đó postcondition của nghiệp vụ gốc **không phải điều kiện phải đúng cho nhánh bị từ chối**. Thay vào đó cần một hợp đồng riêng:

```text
Nếu không được phép:
    target invocation count == 0
    caller nhận lỗi từ chối phù hợp
    không có side effect bị cấm
```

Đây là cách hợp đồng được mô tả theo **nhánh thực thi**, tránh coi mọi return/throw giống nhau.

## 14. Thiết kế hợp đồng theo lớp: target, aspect, public API

Trong hệ thống có nhiều aspect:

```text
Caller
  -> PublicContract
       -> Normalization
            -> Authorization
                 -> Business
```

Ta cần phân biệt:

1. **Target contract:** điều kiện mà Business cam kết khi được gọi đúng cách.
2. **Aspect contract:** hành vi mà Normalization/Authorization cam kết.
3. **Composed contract:** điều kiện toàn bộ chuỗi cung cấp cho caller.

Một target có thể chấp nhận chuỗi đã chuẩn hóa; public API có thể chấp nhận input chưa chuẩn hóa rồi normalize. Nếu dời precondition của target ra ngoài Normalization mà không điều chỉnh, ta có thể **vô tình siết chặt public precondition**.

Tương tự, nếu Business trả một ID nội bộ nhưng public API trả token khác, postcondition public cần kiểm tra **token**, không chỉ ID ở lớp trong.

### 14.1. Chịu trách nhiệm khi vi phạm

Khi một precondition public thất bại, caller có thể sai đầu vào. Khi target postcondition thất bại dù precondition đúng, implementation hoặc một advice bên trong có thể sai. Khi chỉ public postcondition thất bại, nguyên nhân có thể do advice biến đổi kết quả.

**Đừng chỉ in “contract violated”** rồi mất thông tin. Nên ghi rõ:

- Hợp đồng ở ranh giới nào.
- Điều kiện nào không thỏa.
- Trạng thái/giá trị liên quan đã được phép ghi.
- Aspect/operation/invocation ID tương ứng.
- Phân biệt vi phạm trước, sau hay bất biến.
- Cause chain nếu có lỗi khác kèm theo.

## 15. Subtyping và nguyên tắc thay thế theo hợp đồng

Khi một class triển khai interface hoặc một class con thay thế class cha, **nguyên tắc thay thế** khuyến khích:

- **Không tăng yêu cầu lên caller** một cách bất ngờ: subtype không nên đòi tiền điều kiện mạnh hơn hợp đồng supertype.
- **Không giảm bảo đảm cho caller**: subtype không nên hứa hậu điều kiện yếu hơn hợp đồng đã công bố.
- Giữ những bất biến có liên quan đến hợp đồng thay thế công khai.

Ví dụ interface cho phép `amount>=0`, nhưng một proxy subclass đột ngột chỉ cho `amount>100` mà caller không được thông báo. Nó có thể từ chối các lời gọi hợp lệ theo interface, làm phá khả năng thay thế.

### 15.1. Làm yếu precondition và làm mạnh postcondition

Nếu implementation chấp nhận **nhiều input hợp lệ hơn** và vẫn đáp ứng bảo đảm cũ, đó thường là mở rộng an toàn hơn. Nếu implementation cung cấp **bảo đảm mạnh hơn** cho kết quả đúng tiền điều kiện, caller cũ vẫn có thể hoạt động.

Ngược lại, giới hạn input đột ngột hoặc hạ bảo đảm đầu ra có thể phá hợp đồng mà caller dựa vào.

### 15.2. Aspect chính sách có thể thay đổi hợp đồng có chủ đích

Một security aspect có thể cố ý từ chối operation cho người dùng không có quyền. Điều này phải là **một phần công khai của hợp đồng public** hoặc boundary tin cậy, không bí mật xem như một before advice “không thay đổi API”.

**Khi advice thay đổi hợp đồng, hãy phiên bản hóa và mô tả thay đổi như thay đổi API/behavior**, không chỉ một cấu hình kỹ thuật.

## 16. Ngoại lệ và bất biến không hoàn toàn độc lập

Một lời gọi có thể thất bại ở nhiều giai đoạn:

| Giai đoạn | Ví dụ lỗi | Điều cần kiểm |
| --- | --- | --- |
| Kiểm precondition | Input không hợp lệ | Target đã chạy chưa? |
| Entry invariant | Object đã có state sai trước lời gọi | Ai đã làm sai và còn an toàn để xử lý không? |
| Before advice phụ | Logger không sẵn sàng | Có được phép che/chặn nghiệp vụ không? |
| Business body | I/O hoặc domain failure | Exceptional guarantee và state hiện tại |
| Normal postcondition | Result/state không như cam kết | Có side effect cần phục hồi không? |
| Exit invariant | Object rời operation với state sai | Có thể cô lập object hoặc chặn công bố không? |
| After advice phụ | Metrics/audit lỗi sau business | Caller thấy lỗi gì, có được retry không? |
| Cleanup/finally | Giải phóng tài nguyên thất bại | Giữ primary error/cause/suppressed đúng chính sách |

Nếu postcondition ném exception, lỗi ấy có thể lan lên after-throwing advice của **lớp ngoài**, mặc dù business đã return bình thường. Vì thế phân loại “thrown branch” ở một lớp không đồng nghĩa body nghiệp vụ ném exception.

### 16.1. Exception của check không phải một phép rollback

Một `ContractViolation` có thể xuất hiện **sau khi state đã bị thay đổi**. Muốn rollback cần cơ chế transaction hoặc compensation có hợp đồng riêng. Đừng viết test “thấy lỗi thì state không đổi” trừ khi operation cam kết strong guarantee và có implementation đúng.

## 17. Tác động của around advice và thứ tự nhiều aspect

Giả sử có:

```text
ContractAround(
    RetryAround(
        Business
    )
)
```

Contract ngoài chụp snapshot trước **toàn bộ retry** và kiểm tra trạng thái cuối. Nếu retry khiến Business chạy hai lần, postcondition của “một operation logic” có thể sai.

Đảo thứ tự:

```text
RetryAround(
    ContractAround(
        Business
    )
)
```

Contract trong có thể kiểm tra **mỗi attempt**, nhưng tổng thể retry vẫn có thể tạo side effect sai cho caller.

Do đó không chỉ quan tâm “ai chạy trước”; phải biết:

- Contract đo theo invocation logic hay theo từng attempt?
- Snapshot được lấy khi nào?
- Có cách nhận diện idempotent request không?
- Exception của chính ContractAround có bị RetryAround bắt và retry không?
- Retry có được phép xử lý **contract violation** không? Thường không nên thử lại bug logic chỉ vì một exception là unchecked.

### 17.1. Lỗi từ hợp đồng cần loại khác lỗi tạm thời

Nếu retry bắt toàn bộ `RuntimeException`, một `PostconditionViolation` có thể khiến target chạy lại mặc dù lần đầu đã hoàn tất mutation. **Chỉ retry nhóm lỗi đã được phân loại là có thể retry**, và luôn xét idempotency/trạng thái thực tế.

### 17.2. Aspect nào quan sát kết quả cuối?

Một contract checker đặt **bên trong** result-transforming advice có thể kiểm kết quả trước khi transform. Một checker **bên ngoài** có thể kiểm API đã transform. Khi cần cả hai, phải định nghĩa hai contract khác nhau thay vì cho một công thức áp dụng mù quáng.

## 18. AOP qua proxy và lỗ hổng phạm vi hợp đồng

Một proxy checker có thể áp đặt tiền điều kiện ở public interface. Nhưng nếu ứng dụng có:

```text
Caller A -> Proxy -> Contract -> Target
Caller B ---------------------> Target
```

thì Caller B **không chạy contract advice**.

Các đường dễ bypass:

- Caller dùng `new Target()` thay vì factory trả proxy.
- Một reference tới target gốc bị lưu trong cache/registry.
- Target gọi `this.otherMethod()` mà không quay qua proxy.
- Thư viện ngoài tự tạo object.
- Callback giữ raw target.
- Method final/private/static không thuộc cơ chế override mong đợi.

**Không suy rằng contract chỉ tồn tại ở proxy là một bảo đảm an toàn tuyệt đối.** Với invariant hoặc quyền bảo mật trọng yếu, cần bảo vệ ở boundary đáng tin và kiểm thử đường trực tiếp. Nếu muốn can thiệp vào method body hoặc call sites rộng hơn, phải xem khả năng weaving của công cụ thực tế.

### 18.1. Kiểm invariant tại public boundary khác kiểm mọi helper

Một method private có thể được gọi nội bộ trong lúc object đang tạm biến đổi trạng thái. Dệt kiểm invariant lên mọi helper có thể báo lỗi sai, vì hợp đồng invariant thường được xác định tại những trạng thái quan sát được từ bên ngoài.

Điểm kiểm tra phải **khớp abstraction boundary**, không chạy ở mọi vị trí chỉ vì công cụ có thể weave.

## 19. Contract assertions khác `assert` của Java

Java cung cấp câu lệnh:

```java
assert amount > 0 : "amount must be positive";
```

Đây là mảnh code Java. Các **assertion Java thường bị tắt mặc định**, được bật theo cấu hình runtime như `-ea`; ngoài ra assertion có ngữ nghĩa riêng và khi sai ném `AssertionError`.

Vì thế:

- Đừng dùng `assert` làm **cơ chế kiểm tra đầu vào/bảo mật bắt buộc** nếu cấu hình runtime có thể tắt.
- Một AOP contract checker chủ động ném `IllegalArgumentException` hoặc lỗi riêng có thể vẫn chạy khi Java assertion bị tắt, nhưng lại phụ thuộc việc invocation có đi qua interceptor và advice được bật hay không.
- Một chương trình Java không tự động có DbC đầy đủ chỉ vì có `assert`.
- Nếu checker được disable ở production, cần quyết định những invariant nào vẫn phải được bảo vệ trong code nghiệp vụ.

### 19.1. Contract checking trong production

Có thể phân loại:

1. **Validation bắt buộc tại trust boundary:** không thể tùy ý tắt.
2. **Internal correctness checks:** có thể bật ở test/staging và một phần production theo chính sách.
3. **Diagnostics đắt tiền:** có thể kiểm theo sampling hoặc chế độ điều tra, nếu không ảnh hưởng cam kết bắt buộc.

Không gọi mọi hợp đồng là “chỉ để debug”. Nếu caller được hứa rằng một mutation không bao giờ làm state âm, việc vô hiệu hóa checker không làm lời hứa hết hiệu lực; implementation vẫn phải đúng.

## 20. Contract checks nên ít side effect và không tái nhập

Một phương thức kiểm postcondition có thể gọi getter. Nếu getter lại khớp pointcut giống method gốc, checker có thể vô tình tái kích hoạt chính aspect:

```text
ContractAdvice -> checkInvariant() -> getState()
                    ^                   |
                    +---- interception--+
```

Các kỹ thuật tránh:

- Giới hạn pointcut loại trừ những method của checker.
- Định nghĩa contract trên các API đọc trạng thái đã được thiết kế không tái nhập.
- Quản lý reentrancy theo invocation phù hợp.
- Không dùng cờ global đơn giản làm tắt checker của request khác.
- Không ghi log toàn bộ object bằng `toString()` nếu `toString` có side effect hoặc tự bị intercept.
- Kiểm tra những giá trị được truy cập có phù hợp visibility/module và concurrency model không.

**Một phép kiểm tra lý tưởng nên có tính xác định và ít side effect.** Nếu chính checker thay đổi trạng thái rồi làm invariant sai, nó không còn là một công cụ quan sát đáng tin.

## 21. Điều kiện trước/sau với API bất đồng bộ

Ví dụ một method Java trả `CompletableFuture<Result>`:

```text
caller -> method executes -> returns Future
                            |
                            +-- task continues
                            |
                            +-- Future completes later
```

Nếu advice kiểm postcondition **ngay sau khi method trả Future**, nó có thể chỉ kiểm **hợp đồng trả handle**, không thể kết luận tác vụ đã hoàn tất.

Phải định nghĩa hai ranh giới:

- **Synchronous method postcondition:** Future không null, được đăng ký/có ID phù hợp.
- **Asynchronous completion contract:** khi Future hoàn tất bình thường, kết quả đáp ứng Q; khi hoàn tất đặc biệt, lỗi và trạng thái đáp ứng exceptional guarantee.

Một after throwing bao method execution có thể không nhận lỗi xảy ra **về sau** trong task. Kiểm completion cần API stage/handler tương ứng.

### 21.1. Callback kiểm hợp đồng có thể tự tạo lỗi

Nếu thêm `handle`, `thenApply` hoặc `whenComplete` vào một stage, callback có thể ném exception. Nó có thể làm stage tiếp theo thất bại hoặc làm thay đổi đường kết thúc tùy API và loại callback.

Cần phân biệt lỗi business với lỗi do **contract checker trong completion handler**; không chỉ gộp mọi exceptional completion thành “business threw”.

### 21.2. Context và snapshot qua thread

Nếu postcondition dùng `oldBalance` được lưu trong ThreadLocal, task chạy trên thread khác có thể không có snapshot đúng. Nên mang context theo invocation/task với vòng đời rõ, không phụ thuộc rằng thread ID đại diện cho request.

## 22. Hợp đồng trong hệ thống nhiều luồng

Một contract:

```text
post: value == oldValue + delta
```

không thể được kiểm đúng nếu **một thread khác cũng thay đổi value giữa lúc lấy snapshot và lúc kiểm**, trừ khi operation/hợp đồng có mô hình đồng bộ thích hợp.

Ví dụ:

```text
T1: old = 10
T1: add(5) -> total = 15
T2: add(2) -> total = 17
T1: check total == 15 -> false
```

Nếu cả hai phép cộng đều hợp lệ, checker của T1 có thể báo **false positive** chỉ vì snapshot và post-check không thuộc một vùng atomic.

Giải pháp tùy miền:

- Khóa để gắn pre/body/post vào critical section thích hợp.
- Cấu trúc immutable/atomic với linearization point rõ.
- So sánh theo version hoặc operation result thay vì trạng thái toàn cục sau khi thread khác chạy.
- Hợp đồng mô tả tính nhất quán theo event/session, không giả định chạy tuần tự.
- Tách hợp đồng thread-safe API khỏi hợp đồng truy cập dữ liệu nội bộ.

Một aspect tự động bao method **không tạo ra atomicity** chỉ nhờ thêm các phép đọc trước/sau. Nếu advice cầm lock, phải đánh giá deadlock, thứ tự khóa và latency.

## 23. Hợp đồng phân tán và bất biến liên đối tượng

Một invariant đơn giản `balance>=0` có thể kiểm cục bộ. Nhưng invariant:

```text
totalDebits == totalCredits
```

trên nhiều kho dữ liệu/dịch vụ có thể cần cách thiết kế khác.

Không nên dùng một after advice kiểm hai cơ sở dữ liệu tại một thời điểm rồi kết luận toàn bộ hệ thống “vi phạm” nếu hệ thống được thiết kế **eventual consistency** và cho phép trạng thái trung gian.

Cần xác định:

1. Invariant là **tức thời** hay **cuối cùng phải đạt**?
2. Điểm quan sát hợp lệ là sau commit, sau message ack hay sau saga completion?
3. Có operation bù (compensation) nếu một bước thất bại không?
4. Có correlation ID để ghép các sự kiện liên quan không?
5. Có timeout và trạng thái không xác định không?
6. Có contract riêng cho mỗi service/boundary không?

AOP có thể ghi telemetry hoặc kiểm guard tại từng API, nhưng **không tự chuyển hệ thống phân tán thành giao dịch nguyên tử**.

## 24. Contract violation phải mang thông tin chẩn đoán phù hợp

Khi một check thất bại, nên phân biệt rõ:

| Trường | Ý nghĩa |
| --- | --- |
| Contract kind | Precondition, normal postcondition, exceptional condition, invariant |
| Boundary | Public proxy, target method, advice hoặc async completion |
| Operation | Loại join point và chữ ký có ý nghĩa |
| Invocation ID | Phân biệt các lần gọi lồng nhau/đa luồng |
| Violation code | Mã ổn định cho automation/monitoring |
| Expected predicate | Điều kiện muốn giữ, không cần in bí mật |
| Observed state | Những giá trị đã được phép ghi |
| Cause | Lỗi gốc nếu một checker chuyển đổi/bao lỗi |
| Build/config ID | Biết chính sách pointcut/advice nào đang áp dụng |

Không nên log toàn bộ `args` hoặc domain object theo mặc định. Contract context có thể chứa token, thông tin tài chính hoặc dữ liệu người dùng. Dùng danh sách trường cho phép, che dữ liệu nhạy cảm và giới hạn thông tin công bố bên ngoài.

### 24.1. Lỗi của logging không nên vô tình che vi phạm gốc

Nếu checker phát hiện `PostconditionViolation` rồi logging ném `MetricUnavailable`, caller có thể chỉ thấy lỗi logger. Cần xác định primary/secondary error, có thể giữ lỗi phụ bằng `suppressed` khi phù hợp.

Nhưng đừng coi mọi audit failure là lỗi phụ có thể bỏ qua: yêu cầu pháp lý hoặc an ninh có thể quy định hành vi khác.

## 25. Ma trận kiểm thử Design by Contract qua AOP

| Trường hợp | Precondition | Business/advice | Postcondition / invariant | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Input hợp lệ | Đúng | Business chạy 1 lần | Đúng | Trả kết quả |
| Input sai | Sai | Business không chạy | Không kiểm normal post | Lỗi đầu vào rõ |
| Business trả sai giá trị | Đúng | Body đã chạy | Post sai | Báo violation, kiểm state thực |
| Business ném trước mutate | Đúng | Ném exception | Exceptional guarantee | Lỗi gốc/contract đúng |
| Business ném sau mutate | Đúng | Một phần state thay đổi | Basic invariant có thể còn đúng | Không mặc định rollback |
| Advice sửa args trước target | Tùy ranh giới | Input tới target khác | Contract public/target có thể khác | Test hai lớp contract |
| Advice trả fallback | Có thể đúng | Target có thể không chạy | Contract nhánh fallback | Không trả thành công giả |
| Advice đổi result sau body | Đúng | Body đã hoàn tất | Public post có thể sai | Checker đúng lớp ngoài phát hiện |
| Advice sau body tự ném | Đúng | Body đã thành công | Không có return bình thường ở lớp ngoài | Không nhầm lỗi business |
| Retry operation | Đúng | Body có thể chạy nhiều lần | Post cho operation logic | Không nhân đôi side effect |
| Direct target call | Không qua proxy | Body chạy | Proxy checker bị bypass | Architecture test phát hiện |
| Self-invocation | Tùy receiver | Lời gọi nội bộ | Checker method trong có thể bypass | Test đúng proxy/weaving |
| Concurrent updates | Đúng | Thread khác xen kẽ | Snapshot có thể cũ | Không báo sai vì race |
| Future trả trước completion | Đúng | Task chạy sau | Completion contract riêng | Không kết luận từ method return |
| Cleanup cùng lỗi gốc | Đúng | Business hoặc checker ném | Lỗi phụ cũng phát sinh | Cause/suppressed theo policy |

### 25.1. Kiểm thử cả đường không được chọn

Không nên chỉ assert checker chạy khi method khớp pointcut. Cần có **negative tests**:

- Method không thuộc scope không bị can thiệp.
- Constructor/helper nội bộ không bị check invariant ở thời điểm tạm mất nhất quán ngoài chủ đích.
- DTO/value object không cần contract advice không bị wrap chỉ vì có tên method giống nhau.
- Caller đi qua target trực tiếp được nhận diện là bypass nếu chính sách bắt buộc không cho phép.

### 25.2. Kiểm tra thứ tự và identity của exception

Nếu thiết kế truyền nguyên `IllegalStateException` từ target, có thể kiểm tra identity `caught == original` khi mô hình cho phép. Nếu advice wrap, kiểm tra `getCause()`, contract loại lỗi và những trường được phép công bố.

### 25.3. Kiểm tra không lặp side effect

Khi checker phát hiện postcondition sai sau mutation, một retry mechanism bên ngoài không được tự động chạy lại phép biến đổi nếu chưa chứng minh an toàn. Test nên đếm số lần business chạy và trạng thái cuối.

## 26. Quy trình áp dụng hợp đồng vào một mã nguồn AOP thật

1. **Viết hợp đồng trước:** đâu là input hợp lệ, normal post, exceptional guarantee và invariant?
2. **Chọn boundary:** public API, method execution, call site, task completion hay transaction?
3. **Xác định pointcut:** chỉ chọn những operation có contract tương ứng, tránh wildcard quá rộng.
4. **Phân loại advice:** trước, sau returning, sau throwing, finally hoặc quanh.
5. **Vẽ precedence:** checker nhìn input/result ở tầng nào, trước hay sau normalization/error translation?
6. **Chọn snapshot tối thiểu:** cần “old” ở những field nào, có an toàn với mutable/concurrent state không?
7. **Thiết kế loại lỗi vi phạm:** phân biệt caller violation, implementation violation, exceptional invariant.
8. **Giữ thông tin nguyên nhân:** cause/suppressed/trace ID; bảo vệ dữ liệu nhạy cảm.
9. **Kiểm thử đường thành công và thất bại:** bao gồm lỗi do advice tự tạo.
10. **Đo chi phí runtime:** reflection, snapshot, I/O, allocation, locking.
11. **Kiểm thử đường bypass:** direct target, self-invocation, external objects, async tasks.
12. **Đối chiếu yêu cầu production:** checker nào bắt buộc, checker nào chỉ debug, ai có quyền disable?
13. **Đánh giá khả năng phục hồi:** phát hiện vi phạm có cần cô lập object, rollback hay báo trạng thái chưa xác định?
14. **Theo dõi khi thay đổi API:** nếu public contract đổi, caller và test cũng phải được xem xét.

Một contract aspect ngắn không thay thế được bước **xác định nghĩa của contract**. Nếu `oldState`, outcome hay transaction boundary mơ hồ, tự động hóa kiểm tra sẽ tạo kết quả khó tin.

## 27. Những hiểu nhầm thường gặp

**“Precondition chỉ là if-check trước method.”** Không đủ. Nó còn là một phần của hợp đồng caller/supplier và phụ thuộc vị trí trong chuỗi advice.

**“Postcondition đúng nghĩa là chương trình chắc chắn không có bug.”** Không. Nó chứng minh một số thuộc tính được kiểm ở một boundary cụ thể, không bảo đảm mọi thuộc tính và side effect khác.

**“Invariant phải đúng sau từng instruction.”** Không nhất thiết. Nhiều invariant được quy định tại trạng thái công khai/quiescent.

**“Nếu có exception, tất cả hậu điều kiện vẫn phải đúng.”** Sai. Normal post và exceptional guarantee cần tách riêng.

**“Postcondition violation sẽ rollback state.”** Sai. Exception từ checker không tự thực hiện compensation.

**“Dùng after returning là luôn kiểm kết quả cuối caller nhận.”** Chưa chắc. Một advice ngoài có thể tiếp tục đổi kết quả.

**“Kiểm contract chỉ ở target đủ cho mọi aspect.”** Không khi advice thay đổi args/result/error hoặc side effect.

**“Aspect đặt ở proxy sẽ bao toàn bộ lời gọi method của class.”** Không nếu caller bypass proxy hoặc lời gọi nội bộ không đi qua interceptor.

**“Dùng Java assert là luôn kiểm hợp đồng trong production.”** Sai: assertion thường tắt mặc định, và không thay thế validation/bảo mật bắt buộc.

**“Một snapshot reference tới object mutable tương đương old-value.”** Không nếu object tiếp tục thay đổi.

**“Racing concurrent check chứng minh invariant sai.”** Chưa đủ nếu phép đọc không atomic hoặc không theo consistency model.

**“Advice chỉ logging không thể phá contract.”** Có thể ném lỗi, thay timing, reentrancy hoặc lộ dữ liệu.

**“Retry mọi ContractViolation sẽ tự sửa lỗi.”** Nguy hiểm: có thể nhân đôi side effect, che bug hoặc làm trạng thái lệch hơn.

**“Future trả bình thường đồng nghĩa task thành công.”** Không. Method return và completion là hai thời điểm khác nhau.

**“Checker kiểm đúng một thuộc tính nghĩa hệ thống phân tán đã nhất quán.”** Không. Phải xác định consistency window và phạm vi bảo đảm.

## 28. Bài tập luyện tập có đáp án

### Bài 1. Precondition ở ngoài hay trong normalization?

Public API cho phép `id = "  A  "` và cam kết tự trim. Target yêu cầu id đã trim. Đặt một contract check đòi “không có khoảng trắng” ở ngoài normalization có đúng không?

**Đáp án:** Không phù hợp public contract đã nêu. Public checker nên chấp nhận input được hứa hỗ trợ, còn target checker có thể yêu cầu giá trị đã normalize.

### Bài 2. Normal post sau exception?

Một method cam kết normal post `result == old + delta` nhưng ném `IOException` sau khi đã cập nhật state. Có bắt buộc normal post đúng không?

**Đáp án:** Không thể suy ra. Cần đọc exceptional guarantee. Có thể chỉ cam kết invariant cơ bản; một exception không tự rollback mutation.

### Bài 3. Lỗi do after advice?

Target trả result đúng, nhưng after advice đổi result thành một giá trị sai. Checker ở trong after advice ấy có phát hiện được sai phạm ở caller không?

**Đáp án:** Chưa chắc. Checker trong có thể chỉ thấy result trước biến đổi. Cần checker tại public boundary hoặc contract riêng cho advice đổi result.

### Bài 4. Retry sau postcondition violation?

Target đã ghi giao dịch xong, checker phát hiện postcondition sai và ném exception. Retry ngoài có nên gọi lại không?

**Đáp án:** Không tự động. Phải xác minh trạng thái và idempotency; ContractViolation thường chỉ ra lỗi cần sửa/điều tra chứ không phải transient failure mặc định.

### Bài 5. Bất biến trong helper?

Một helper tạm để `a=0` trước khi cập nhật `b`, sau đó khôi phục invariant `a+b==10` trước khi method public return. Dệt checker vào mọi helper exit có thể báo gì?

**Đáp án:** Có thể báo false positive nếu contract chỉ yêu cầu invariant tại public boundary/quiescent state.

### Bài 6. Race condition?

T1 đọc old=10, cộng 5 xong; T2 cộng 2 trước khi T1 đọc new=17. T1 kiểm `new==old+5` thất bại. Có thể kết luận implementation của T1 sai không?

**Đáp án:** Chưa thể. Snapshot/post-check không nằm trong ranh giới atomic; cần consistency model hoặc synchronization thích hợp.

### Bài 7. Caller bypass proxy?

Một class có contract advice trên interface proxy nhưng caller gọi target tạo bằng `new`. Advice có chắc chạy không?

**Đáp án:** Không trong mô hình JDK proxy delegation; lời gọi không qua handler. Một công cụ weaving body có thể khác.

### Bài 8. After throwing đọc gì?

Một around advice trong biến `IOException` thành `DomainUnavailable`, ngoài nó có checker after throwing. Checker ngoài nhìn exception nào?

**Đáp án:** Nó có thể nhìn `DomainUnavailable` vì đó là outcome của continuation ở lớp ngoài. Muốn tìm `IOException` có thể cần `getCause()` nếu lỗi gốc được bảo toàn.

### Bài 9. Java `assert` bị tắt?

Nếu code chỉ dùng `assert amount > 0` và runtime không bật assertion, có được bảo đảm input luôn được từ chối khi `amount=0` không?

**Đáp án:** Không. Validation bắt buộc phải dùng cơ chế luôn được thực thi ở boundary phù hợp.

### Bài 10. Fallback có hợp đồng không?

Một phương thức cập nhật trả `receiptId`. Around advice bắt mọi exception và trả `"OK"`. Đúng kiểu `String` nghĩa đã đúng hợp đồng chưa?

**Đáp án:** Chưa. Receipt phải có ý nghĩa xác nhận hợp lệ; lỗi có thể xảy ra sau side effect hoặc trước commit. Cần contract rõ cho nhánh fallback hoặc không cung cấp fallback giả thành công.

## 29. Checklist trước khi đưa Contract Aspect vào sử dụng

- [ ] Có văn bản precondition của public API.
- [ ] Có normal postcondition với kết quả/trạng thái và dữ liệu old cần thiết.
- [ ] Có invariant ở đúng boundary, không kiểm bừa trạng thái trung gian.
- [ ] Có exceptional guarantee riêng, không giả định rollback.
- [ ] Đã phân biệt target contract, advice contract và composed/public contract.
- [ ] Biết advice nào có thể sửa args, result, exception hoặc trạng thái.
- [ ] Đã vẽ thứ tự/precedence giữa contract checker và các aspect khác.
- [ ] Không vô tình kiểm hậu điều kiện trước khi advice ngoài sửa result.
- [ ] Không retry ContractViolation trừ khi có lý do và cơ chế an toàn cụ thể.
- [ ] Có snapshot old-state không bị thay đổi và đúng concurrency model.
- [ ] Kiểm tra tràn số/precision/timezone khi predicate liên quan dữ liệu ấy.
- [ ] Contract check ít side effect, không gây reentrancy ngoài ý muốn.
- [ ] Không dùng một global mutable state để giữ context giữa invocation.
- [ ] Có test direct target, self-invocation và phạm vi weaving/proxy.
- [ ] Có test lỗi business, lỗi advice, lỗi post và lỗi cleanup.
- [ ] Có test violation sau mutation để thấy state không tự rollback.
- [ ] Có test concurrent/async nếu ranh giới hoạt động liên quan.
- [ ] Có chính sách error type, cause/suppressed và telemetry an toàn.
- [ ] Bảo vệ thông tin nhạy cảm khi log contract context.
- [ ] Có cơ chế xử lý object ở trạng thái không hợp lệ sau violation.
- [ ] Có đo overhead snapshot/checker trên workload thực tế.
- [ ] Không dựa vào Java assertions có thể tắt cho validation bắt buộc.
- [ ] Có quy trình đổi contract cùng version và regression tests.
- [ ] Xác định quyền tắt/bật checker cho từng loại hợp đồng.
- [ ] Bảo đảm invariant cốt lõi vẫn được bảo vệ ở trust boundary đáng tin.

## 30. Tổng kết

**Precondition nói khi nào thao tác được phép chạy; postcondition nói thao tác cam kết điều gì sau khi hoàn tất theo nhánh được định nghĩa; invariant nói trạng thái nào được coi là hợp lệ ở các ranh giới quan sát thích hợp.**

Trong AOP, các điều kiện ấy phải được xem là **hợp đồng của cả đường thực thi**, không chỉ hợp đồng của thân phương thức nghiệp vụ. Before advice có thể từ chối trước target; around advice có thể thay input, bỏ `proceed`, thử lại hoặc trả fallback; after advice có thể đổi result hoặc ném lỗi sau khi trạng thái đã thay đổi. Bởi vậy thứ tự advice, phạm vi try/catch, nơi kiểm tra old/new state và loại exception đều ảnh hưởng tính đúng đắn.

Một giải pháp bền vững cần kết hợp **hợp đồng được viết rõ**, **kiểm tra ở ranh giới phù hợp**, **các bảo đảm riêng cho đường ngoại lệ**, **kiểm thử cả đường bypass và side effect**, cùng hiểu biết về concurrent/async execution. Việc phát hiện vi phạm là bằng chứng cần xử lý — **không phải bằng chứng thao tác được hoàn tác**.
