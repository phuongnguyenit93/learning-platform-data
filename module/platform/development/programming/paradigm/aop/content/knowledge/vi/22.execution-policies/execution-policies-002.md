# Thứ tự giữa giao dịch, thử lại và ghi nhận kết quả trong AOP

## 1. Tại sao thứ tự advice quyết định hành vi?

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), nhiều **aspect** có thể tác động lên cùng một join point. Ví dụ, một lời gọi nghiệp vụ có thể đồng thời cần:

- **Giao dịch (transaction):** xác lập ranh giới commit hoặc rollback cho những thao tác thuộc giao dịch.
- **Thử lại (retry):** thực hiện lại khi gặp một số lỗi được xác định là có thể phục hồi.
- **Ghi nhận kết quả (result recording):** ghi log, metric, audit hoặc phát sự kiện về thành công và thất bại.

Mỗi concern có lý do tồn tại riêng, nhưng **thứ tự bao quanh** của các advice làm thay đổi phạm vi nhìn thấy, vòng đời tài nguyên, số lần thực thi nghiệp vụ và ý nghĩa của “thành công”.

Giả sử hành vi đích là **operation()**. Biểu thức:

~~~text
Retry(Transaction(operation))
~~~

có nghĩa: retry ở ngoài, mỗi lượt retry đi vào transaction mới. Ngược lại:

~~~text
Transaction(Retry(operation))
~~~

có nghĩa: mở một transaction bên ngoài, rồi thử lại nhiều lần bên trong transaction ấy. Hai biểu thức không tương đương.

Đây là ký pháp mô hình hóa thứ tự bao quanh, **không phải cú pháp khai báo của một thư viện AOP**. Công cụ AOP cụ thể có thể dùng precedence, priority, explicit ordering hoặc quy tắc weaving riêng. Cần kiểm tra thứ tự thực tế ở runtime thay vì suy đoán từ tên aspect hoặc thứ tự xuất hiện trong mã nguồn.

**Mục tiêu học tập:** từ một tập advice và một join point, xác định chính xác advice nào là lớp ngoài, lớp trong; transaction bắt đầu và kết thúc lúc nào; lỗi nào dẫn đến retry; trạng thái nào được ghi theo từng attempt và trạng thái nào thực sự là kết quả cuối.

## 2. Ba chính sách phải được xác định độc lập

### 2.1. Chính sách giao dịch

Một transaction cung cấp ranh giới thống nhất cho các thao tác tài nguyên có tham gia vào transaction đó. Trong trường hợp thông thường, thành công có nghĩa transaction đã **commit thành công**; thất bại cần xử lý **rollback** hoặc một trạng thái chưa chắc chắn tùy hệ thống.

Một advice bao giao dịch thường tuân theo trình tự khái niệm:

~~~text
transaction advice:
    begin transaction
    try:
        value = proceed()
        commit transaction
        return value
    catch failure:
        rollback nếu còn phù hợp
        rethrow failure
    finally:
        release/restore transaction context and resources
~~~

Đây là giản lược để học cách xếp lớp. Khi **commit thất bại**, một số hệ thống đã kết thúc transaction, một số có trạng thái kết quả không chắc chắn, và thao tác rollback sau đó có thể không còn hợp lệ. Implementation thực phải tuân theo hợp đồng transaction manager, tài nguyên và giao thức commit. Không giả định rằng cứ bắt được lỗi commit là chắc chắn không có thay đổi nào đã được ghi nhận.

Ngoài ra, transaction chỉ bao phủ tài nguyên thực sự tham gia. Một cuộc gọi HTTP hoặc email gửi từ trong transaction cơ sở dữ liệu không tự bị rollback theo dữ liệu cơ sở dữ liệu.

### 2.2. Chính sách retry

Retry quyết định **lỗi nào** được thử lại, **số lượt tối đa**, khoảng chờ, deadline, cancellation và cách báo lỗi cuối. Retry phải bảo toàn nguyên nhân lỗi cho người gọi khi không còn điều kiện thử tiếp.

Ví dụ:

~~~text
retry advice:
    for attempt in 1..maxAttempts:
        try:
            return proceed()
        catch failure:
            if failure not retryable:
                throw failure
            if attempt is last:
                throw failure
            wait according to backoff/deadline policy
~~~

Một vài lỗi có thể tạm thời như tranh chấp khóa, deadlock được báo có thể retry hoặc sự cố kết nối ngắn hạn; lỗi cú pháp, dữ liệu không hợp lệ hoặc bất biến nghiệp vụ bị vi phạm thường không thể sửa chỉ bằng gọi lại. Phân loại phải dựa trên **hợp đồng thực tế của hệ thống và ngữ nghĩa lỗi**, không dựa vào tên ngoại lệ một cách tùy tiện.

Retry không phải lúc nào cũng an toàn. Nếu lần trước đã gửi thanh toán hoặc commit thành công nhưng phản hồi bị mất, gọi lại có thể gây tác động phụ lặp. Vì vậy **idempotency** và trạng thái commit là một phần bắt buộc của thiết kế retry.

### 2.3. Chính sách ghi nhận kết quả

“Ghi nhận kết quả” có thể mang nhiều nghĩa:

- Ghi **mỗi attempt**: biết lần đầu thất bại, lần thứ hai thành công.
- Ghi **kết quả cuối của operation**: người gọi cuối cùng nhận thành công hay lỗi sau tất cả các attempt.
- Ghi **kết quả commit**: xác nhận transaction đã commit hay thất bại.
- Ghi **audit bền vững**: lưu bằng chứng được yêu cầu vào kho lưu trữ phù hợp.
- Phát **sự kiện hậu giao dịch**: hệ thống khác phải thấy thay đổi đã cam kết.

Những kết quả này không thể tráo đổi. Một attempt thất bại có thể nằm trong operation thành công; một hàm nghiệp vụ trả về bình thường có thể đi trước một lần commit thất bại; một bản ghi log được in ra không phải bằng chứng chắc chắn rằng commit đã xảy ra.

Muốn ghi nhận đúng, phải xác định **đối tượng được ghi**, **mốc thời gian**, **định nghĩa outcome**, **độ bền dữ liệu yêu cầu** và **ai chịu trách nhiệm khi ghi nhận thất bại**.

## 3. Cách đọc thứ tự khi advice lồng nhau

Có thể hình dung mỗi around advice như một hàm nhận vào hành vi phía trong:

~~~text
Outer(
    Middle(
        Inner(
            operation
        )
    )
)
~~~

Lượt đi vào: Outer → Middle → Inner → operation. Lượt trở về bình thường: operation → Inner → Middle → Outer. Ngoại lệ có thể đi qua các lớp ngược chiều, trừ khi một lớp bắt rồi xử lý hoặc biến đổi nó.

Một chi tiết quan trọng: **lớp bao ngoài nhìn thấy toàn bộ việc hoàn tất của lớp phía trong**. Do đó, nếu Transaction bao quanh operation và thực hiện commit trước khi trả về, một advice ghi kết quả đặt bên ngoài Transaction có thể đánh giá cả outcome của commit; advice đặt bên trong Transaction thường chưa biết commit cuối cùng thành công hay chưa.

Sơ đồ:

~~~text
Record(
  Transaction(
    operation
  )
)

vào: Record -> begin -> operation
ra thành công: operation -> commit -> Record thấy success
ra lỗi: operation/commit -> xử lý transaction -> Record thấy failure
~~~

So với:

~~~text
Transaction(
  Record(
    operation
  )
)

vào: begin -> Record -> operation
ra: operation -> Record ghi success -> commit
                                   ^ commit vẫn có thể thất bại
~~~

Đặt Record bên trong Transaction còn có thể khiến log hoặc ghi nhận “success” xảy ra trước commit, trong khi transaction có thể rollback về sau. Đối với log chẩn đoán, có thể chấp nhận nếu sự kiện được đặt tên là “business-returned” hoặc “attempt-finished-before-commit”; đối với báo cáo **đã cam kết**, đó là sai ranh giới.

## 4. Thứ tự giữa retry và transaction: lựa chọn nền tảng

### 4.1. Retry bao transaction: mỗi attempt có transaction riêng

~~~text
Retry(
  Transaction(
    operation
  )
)
~~~

Dòng thời gian khi attempt đầu thất bại có thể retry:

~~~text
Retry attempt #1
    Transaction T1: begin
        operation -> transient failure
    Transaction T1: rollback/close
Retry quyết định thử tiếp

Retry attempt #2
    Transaction T2: begin
        operation -> returns
    Transaction T2: commit
Retry returns success
~~~

Ý nghĩa:

1. Mỗi attempt có ranh giới transaction mới, nếu transaction advice thực sự tạo scope mới theo hợp đồng.
2. Lỗi được retry sẽ được nhìn thấy **sau khi** lớp transaction đã xử lý thất bại và trả quyền điều khiển ra ngoài.
3. Nếu commit được thực hiện trong lớp transaction, retry có thể quan sát cả lỗi commit được truyền ra.
4. Một attempt đã thất bại không khiến transaction đang dùng cho attempt sau bị giữ trong trạng thái rollback-only hoặc aborted.
5. Các tác động phụ ngoài transaction vẫn phải được quản lý để retry không tạo kết quả lặp.

Đây thường là cấu trúc phù hợp cho retry **toàn bộ một đơn vị công việc giao dịch**, đặc biệt khi một lỗi khiến transaction hiện hành không còn có thể tiếp tục. Tuy nhiên, vẫn cần điều kiện retry cụ thể, idempotency và kiểm tra trường hợp kết quả commit không chắc chắn.

**Điều kiện then chốt:** lớp Transaction phải thật sự tạo transaction độc lập cho mỗi attempt. Nếu cơ chế giao dịch ngầm tái sử dụng một transaction bao ngoài hiện hữu, biểu thức hình thức trên chưa chứng minh rằng mỗi attempt có một giao dịch mới. Phải kiểm tra chính sách join/create của giao dịch và môi trường thực thi.

### 4.2. Transaction bao retry: mọi attempt trong một transaction

~~~text
Transaction(
  Retry(
    operation
  )
)
~~~

Dòng thời gian:

~~~text
Transaction T1: begin
    Retry attempt #1
        operation -> failure
        Retry bắt lỗi
    Retry attempt #2
        operation -> returns
Transaction T1: commit?
~~~

Rủi ro không nằm ở cú pháp, mà ở **trạng thái transaction sau thất bại đầu tiên**:

- Một số hệ quản trị đánh dấu transaction là aborted sau một loại lỗi, nên những câu lệnh tiếp theo không thể chạy thành công cho đến khi rollback.
- Một cơ chế quản lý transaction có thể đánh dấu transaction **rollback-only**, kể cả khi lớp Retry bắt ngoại lệ. Lần commit cuối vì vậy vẫn thất bại hoặc dẫn đến rollback.
- Trạng thái trung gian của attempt trước có thể còn tác động tới attempt tiếp theo nếu chưa rollback đến một ranh giới hợp lệ.
- Lock hoặc resource có thể bị giữ xuyên suốt các attempt, tăng thời gian chờ và nguy cơ tranh chấp.

Cấu trúc này **không phải luôn sai**: đôi khi nhiều phép thử được thiết kế để cùng thuộc một giao dịch, hoặc có cơ chế savepoint phù hợp. Nhưng không được giả định “bắt được exception thì transaction sạch như trước”. Muốn dùng, phải chứng minh mọi lỗi được retry cho phép tiếp tục transaction theo hợp đồng và có chiến lược rollback/savepoint chính xác.

### 4.3. Savepoint và transaction lồng nhau

Savepoint có thể cho phép quay lại một trạng thái bên trong transaction hiện tại để thử một bước khác mà không bỏ cả transaction ngoài. Tuy nhiên:

- Savepoint không đồng nghĩa một transaction top-level độc lập.
- Khả năng recovery sau lỗi phụ thuộc loại lỗi và hệ quản trị tài nguyên.
- Một số lỗi làm cả transaction mất khả năng tiếp tục, bất kể có ý định rollback tới savepoint.
- Các tác động phụ bên ngoài transaction không được khôi phục nhờ savepoint.

Hãy chọn savepoint khi thật sự muốn giữ transaction ngoài và có bằng chứng runtime hỗ trợ; nếu mục tiêu là retry toàn bộ đơn vị giao dịch, tạo transaction mới mỗi attempt thường là mô hình rõ ràng hơn.

## 5. Đặt advice ghi nhận kết quả ở đâu?

Không có một vị trí Record duy nhất đúng cho mọi mục đích. Phải phân biệt **record final** và **record attempt**.

### 5.1. Ghi nhận kết quả cuối cùng sau retry và commit

~~~text
RecordFinal(
  Retry(
    Transaction(
      operation
    )
  )
)
~~~

RecordFinal ở ngoài cùng quan sát một lượt xử lý logic hoàn chỉnh. Nếu Retry kết thúc thành công sau attempt thứ ba và transaction cuối commit thành công, RecordFinal ghi **một lần success**. Nếu hết lượt hoặc gặp lỗi không được retry, RecordFinal ghi **một lần failure**.

Vì RecordFinal bao quanh Transaction, điều kiện “success” có thể bao gồm commit, với giả định transaction wrapper chỉ return sau khi commit được xác nhận.

RecordFinal **không tự có thông tin chi tiết về từng attempt** nếu Retry không xuất số attempt hoặc không có observer bên trong.

### 5.2. Ghi nhận từng attempt, bao gồm transaction outcome

~~~text
Retry(
  RecordAttempt(
    Transaction(
      operation
    )
  )
)
~~~

Mỗi lượt Retry đều đi qua RecordAttempt. RecordAttempt thấy commit/rollback outcome của attempt đó theo hợp đồng của Transaction. Ví dụ, attempt 1 thất bại, attempt 2 thành công thì có hai bản ghi.

Nếu chỉ sử dụng Recorder ở vị trí này mà dùng tổng số bản ghi failure để suy ra số operation thất bại, số liệu sẽ sai: một operation có thể thành công sau retry nhưng có một hoặc nhiều attempt lỗi.

### 5.3. Kết hợp hai mức quan sát

~~~text
RecordFinal(
  Retry(
    RecordAttempt(
      Transaction(
        operation
      )
    )
  )
)
~~~

Đây là mô hình tham khảo khi cần **cả outcome tổng thể lẫn từng lượt thử**:

- RecordFinal ghi đúng một outcome của operation tại mốc cuối.
- RecordAttempt ghi outcome của mỗi attempt sau phần xử lý transaction.
- Transaction sở hữu begin/commit/rollback của attempt.
- Retry quyết định có tạo attempt tiếp theo hay dừng.

Ví dụ attempt 1 thất bại, attempt 2 thành công:

~~~text
attempt=1 outcome=failure   (transaction T1 rollback)
attempt=2 outcome=success   (transaction T2 commit)
operation outcome=success   (retry kết thúc)
~~~

Bản ghi **attempt=failure** không mâu thuẫn với **operation=success**, vì chúng mô tả hai đơn vị đếm khác nhau.

Nếu metric phân biệt hai mức, đặt tên rõ như operation_attempts_total và operations_total (tên chỉ minh họa); không cộng chung thành “số request lỗi”.

### 5.4. Ghi nhận bên trong transaction: khi nào hợp lệ?

~~~text
Transaction(
  Record(
    operation
  )
)
~~~

Record nhìn thấy operation trả về nhưng chưa thấy commit. Vị trí này hợp lý nếu mục đích là log chẩn đoán *business returned*, quan sát những sự kiện trước commit hoặc ghi một phần dữ liệu nghiệp vụ **cùng transaction** để dữ liệu ấy rollback cùng dữ liệu chính.

Nhưng một audit ghi cùng transaction sẽ bị rollback nếu transaction rollback; nó **không thể** làm nguồn ghi nhận bền vững cho mọi lần thất bại. Nếu cần audit thất bại tồn tại dù giao dịch chính rollback, phải dùng một cơ chế lưu bền độc lập và cân nhắc tính nhất quán/bảo mật, chứ không chỉ đổi tên advice thành audit.

## 6. Ví dụ Java 17+ chạy được: thứ tự ghi nhận đầy đủ

Đoạn mã sau **mô phỏng chuỗi around advice bằng các wrapper Java thuần**, không phải implementation transaction database hay cơ chế weaving. Wrapper Transaction chỉ in begin/commit/rollback nhằm làm rõ thứ tự; attempt đầu cố ý ném lỗi tạm thời, attempt thứ hai thành công.

Tạo tệp **AdviceOrderDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class AdviceOrderDemo {
    @FunctionalInterface
    interface Work {
        String run();
    }

    static final class TransientFailure extends RuntimeException {
        TransientFailure() {
            super("temporary problem");
        }
    }

    static final AtomicInteger TRANSACTIONS = new AtomicInteger();

    static Work transaction(Work next) {
        return () -> {
            int id = TRANSACTIONS.incrementAndGet();
            System.out.println("tx " + id + " begin");
            try {
                String result = next.run();
                System.out.println("tx " + id + " commit");
                return result;
            } catch (RuntimeException failure) {
                System.out.println("tx " + id + " rollback");
                throw failure;
            }
        };
    }

    static Work retry(Work next, int maxAttempts) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be positive");
        }
        return () -> {
            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                System.out.println("retry attempt=" + attempt);
                try {
                    return next.run();
                } catch (TransientFailure failure) {
                    if (attempt == maxAttempts) {
                        throw failure;
                    }
                }
            }
            throw new AssertionError("unreachable");
        };
    }

    static Work recordAttempt(Work next) {
        return () -> {
            try {
                String result = next.run();
                System.out.println("attempt outcome=success");
                return result;
            } catch (RuntimeException failure) {
                System.out.println("attempt outcome=failure");
                throw failure;
            }
        };
    }

    static Work recordFinal(Work next) {
        return () -> {
            try {
                String result = next.run();
                System.out.println("operation outcome=success");
                return result;
            } catch (RuntimeException failure) {
                System.out.println("operation outcome=failure");
                throw failure;
            }
        };
    }

    static Work flakyBusiness() {
        AtomicInteger calls = new AtomicInteger();
        return () -> {
            int call = calls.incrementAndGet();
            System.out.println("business invocation=" + call);
            if (call == 1) {
                throw new TransientFailure();
            }
            return "OK";
        };
    }

    public static void main(String[] args) {
        Work operation = recordFinal(
                retry(
                        recordAttempt(
                                transaction(flakyBusiness())),
                        3));

        String result = operation.run();
        System.out.println("caller result=" + result);
    }
}
~~~

Chạy:

~~~bash
javac AdviceOrderDemo.java
java AdviceOrderDemo
~~~

Stdout chính xác:

~~~text
retry attempt=1
tx 1 begin
business invocation=1
tx 1 rollback
attempt outcome=failure
retry attempt=2
tx 2 begin
business invocation=2
tx 2 commit
attempt outcome=success
operation outcome=success
caller result=OK
~~~

Kết quả minh họa các điều cần quan sát:

1. Retry là lớp ở ngoài Transaction: attempt 1 dùng T1, attempt 2 dùng T2.
2. RecordAttempt đặt bên ngoài Transaction: ghi failure **sau rollback** và success **sau commit** của wrapper.
3. RecordFinal đặt bên ngoài Retry: chỉ ghi một success cuối, dù trước đó có thất bại tạm thời.
4. Retry bắt riêng TransientFailure. Các RuntimeException khác truyền lên ngay; không bị thử lại vô điều kiện.
5. RecordAttempt và RecordFinal ném lại lỗi, không thay thế outcome của hành vi đích.

Trong hệ thống thực, lệnh commit có thể ném ngoại lệ, có thể có rollback-only hoặc kết quả chưa chắc chắn; wrapper mô phỏng này không thay thế transaction manager. Việc ghi log đơn giản cũng không đảm bảo audit bền vững hay “exactly once”.

## 7. Cơ chế lỗi theo vị trí phát sinh

### 7.1. Lỗi trong phương thức nghiệp vụ

Nếu operation ném lỗi trước commit:

~~~text
RecordFinal -> Retry -> RecordAttempt -> Transaction -> operation throws
Transaction handles rollback
RecordAttempt records failed attempt
Retry classifies failure, either repeats or rethrows
RecordFinal records final outcome after Retry finishes
~~~

Nếu lỗi không retryable, không tạo attempt mới. Nếu retryable và chưa hết budget, lặp lại Transaction ở lượt mới. Dù retry quyết định thế nào, ghi kết quả cuối phải phản ánh trạng thái người gọi thực sự nhận được từ toàn bộ composition.

### 7.2. Lỗi tại commit

Có trường hợp operation **đã trả về bình thường**, nhưng transaction commit lỗi. Nếu Record ở bên trong Transaction, nó đã ghi success quá sớm. Nếu RecordAttempt bên ngoài Transaction, nó nhìn thấy lỗi commit được wrapper truyền ra.

Tuy nhiên, **commit exception không đồng nghĩa chắc chắn rollback**. Ví dụ, phản hồi xác nhận có thể bị mất sau khi hệ thống lưu trữ đã hoàn tất commit. Retry mù toàn bộ operation trong tình huống này có thể tạo bản ghi hoặc tác động phụ lần hai.

Cách xử lý phụ thuộc vào tính chất resource manager và giao thức commit: dùng idempotency key, khóa nghiệp vụ duy nhất, kiểm tra trạng thái theo một mã yêu cầu ổn định hoặc cơ chế reconciliation. Trong log, outcome có thể cần trạng thái **unknown/in-doubt** thay vì ép về failure có rollback chắc chắn.

### 7.3. Lỗi khi rollback

Rollback cũng có thể thất bại. Cần giữ thông tin về **lỗi nghiệp vụ ban đầu** và lỗi rollback để chẩn đoán. Không tùy tiện thay thế lỗi gốc bằng lỗi xuất hiện khi ghi log hoặc dọn dẹp.

Trong Java, khi dùng cơ chế đóng tài nguyên chuẩn, ngoại lệ thứ cấp có thể được lưu làm suppressed exception; còn việc kết hợp ngoại lệ nghiệp vụ và rollback phụ thuộc transaction API. Advice phải có chính sách bảo toàn nguyên nhân lỗi rõ ràng.

### 7.4. Lỗi trong advice ghi nhận

Nếu một recorder bên trong Retry ném ngoại lệ, Retry có thể vô tình coi lỗi **telemetry** là lỗi của operation và kích hoạt thêm attempt. Việc chỉ đặt đúng thứ tự lớp chưa đủ; phải xác định recorder là:

- **Best effort observation:** thất bại ghi log/metric không làm thay đổi kết quả nghiệp vụ; bắt và xử lý lỗi trong observer theo chính sách chẩn đoán.
- **Required durable write:** lỗi ghi audit là lỗi thực sự của operation; phải thiết kế vị trí transaction, retry và cơ chế bảo đảm dữ liệu một cách rõ ràng.

Không nên giữ nguyên recorder có thể throw tùy ý rồi đặt nó trong Retry mà không xét việc throw ấy khiến nghiệp vụ bị gọi lại.

### 7.5. Lỗi vĩnh viễn, timeout và cancellation

Một lỗi dữ liệu không hợp lệ thường nên kết thúc ngay. Timeout có thể là **hết thời gian chờ kết quả**, không chứng minh thao tác gốc đã ngừng; cancellation cũng có thể chỉ hủy việc chờ. Trước khi retry, cần biết lần trước có thể còn đang thực hiện, có khả năng commit và có thể tạo side effect hay không.

Nếu có deadline tổng thể, mọi khoảng backoff và thời gian của từng attempt phải nằm trong budget đó; không được chỉ tăng số lượt rồi kéo dài operation vô hạn.

## 8. Retry chỉ an toàn khi effect có cơ chế chống lặp

Thứ tự `Retry(Transaction(operation))` giúp tách giao dịch mỗi attempt **nếu transaction manager thật sự tạo scope mới**, nhưng **không** tự ngăn side effect ở nơi khác. Đặc biệt, attempt đầu có thể đã commit thanh toán trong khi response bị mất; attempt kế tiếp sẽ tạo hiệu ứng thứ hai nếu backend không nhận ra cùng **logical operation**.

~~~text
attempt=1  charge(key=PAY-104) → committed; response lost
attempt=2  charge(key=PAY-104) → return prior receipt; NO new charge
~~~

An toàn cần **idempotency key giữ nguyên qua attempts**, phạm vi khóa đúng tenant/operation, kiểm tra payload fingerprint khi sử dụng lại khóa, và lưu/cập nhật trạng thái đủ **nguyên tử, bền vững** ở nơi sở hữu effect. Correlation ID để trace và attempt ID để quan sát **không đương nhiên** là khóa chống trùng.

Nội dung chính của bài này là **thứ tự các advice và mốc ghi kết quả**: recorder cần ghi attempt khác với operation, còn lỗi commit không chắc chắn phải được đối soát trước retry. Đối với HTTP/email/message nằm ngoài giao dịch DB, áp dụng deduplication, outbox hoặc cơ chế phối hợp theo hợp đồng; rollback DB không tự thu hồi effect đó.

## 9. Ghi nhận kết quả bền vững sau commit

Một log in ra màn hình, bộ đếm metric và bản ghi audit trong database có **độ bảo đảm khác nhau**:

| Loại ghi nhận | Có thể ghi ở đâu? | Điều phải hiểu |
| --- | --- | --- |
| Log chẩn đoán per-attempt | Sau Transaction trong RecordAttempt | Ghi cả lỗi tạm thời; log có thể mất hoặc trùng tùy pipeline |
| Metric outcome cuối | Sau Retry trong RecordFinal | Một operation có một outcome; không dùng attempt failure làm operation failure |
| Audit là dữ liệu nghiệp vụ bắt buộc | Trong giao dịch thích hợp hoặc cơ chế lưu bền được thiết kế | Độ bền và rollback theo hợp đồng dữ liệu |
| Sự kiện công bố sau commit | Sau xác nhận commit hoặc qua cơ chế outbox | Không thể đảm bảo công bố một lần chỉ bằng gọi callback sau commit |
| Audit thất bại phải còn dù rollback | Kênh lưu bền độc lập với giao dịch bị rollback | Cần định nghĩa độ tin cậy, quyền truy cập và lỗi của kênh này |

### 9.1. Vì sao “ghi sau commit” vẫn có khe hở?

Xét:

~~~text
commit database -> process crash -> publish event
~~~

Database đã commit nhưng event không được gửi. Nếu đổi thứ tự:

~~~text
publish event -> process crash -> database rollback
~~~

Event đã đến nơi khác dù transaction chưa commit. Chỉ thay đổi thứ tự hai lời gọi **không tạo tính nguyên tử** giữa hai hệ thống độc lập.

### 9.2. Transactional outbox

Nếu cần dữ liệu đã commit cuối cùng phải dẫn đến một thông điệp, có thể dùng transactional outbox:

~~~text
Trong cùng database transaction:
    cập nhật dữ liệu nghiệp vụ
    lưu outbox record với event ID duy nhất
    commit cùng nhau

Sau commit:
    publisher đọc outbox
    gửi thông điệp
    đánh dấu trạng thái đã gửi theo cơ chế đáng tin cậy
    retry việc gửi khi cần

Consumer:
    xử lý idempotent/deduplicate bằng event ID
~~~

Outbox thu hẹp khe hở giữa dữ liệu nghiệp vụ và ý định phát sự kiện, nhưng publisher có thể gửi **nhiều lần** nếu crash giữa send và đánh dấu đã gửi. Vì vậy consumer cần xử lý trùng lặp hoặc một giao thức tương đương. “Exactly once” không tự xuất hiện chỉ vì có aspect và outbox.

**Lưu ý:** outbox là một chiến lược nghiệp vụ hạ tầng, không phải chức năng tự có của mọi advice. Một aspect có thể áp dụng chính sách, nhưng việc ghi outbox cần đúng transaction, schema và cơ chế phân phối.

## 10. Quan sát attempt và operation cho đúng thống kê

Giả sử 100 operation đến hệ thống. Có 20 operation phải retry một lần; trong 20 operation ấy, 18 cuối cùng thành công và 2 thất bại.

Khi đó các số liệu có thể là:

| Chỉ số | Diễn giải |
| --- | --- |
| operations_total | 100 operation gốc |
| operations_failed_total | 2 operation cuối cùng thất bại nếu 80 operation còn lại đều thành công |
| attempts_total | 120 lượt attempt |
| attempts_failed_total | Ít nhất 20 attempt đầu thất bại; số chính xác còn tùy outcome của lượt retry sau |
| retries_total | 20 lượt thử bổ sung |

Các giá trị giả định phục vụ phân biệt đơn vị đếm. Không lấy attempts_failed_total làm tỷ lệ lỗi cuối của người dùng. Có thể tính tỷ lệ cần retry từ số operation có attempt vượt 1, trong khi tỷ lệ lỗi cuối lấy từ RecordFinal.

Độ trễ cũng có hai định nghĩa:

- **Attempt duration:** thời gian của một lần Transaction + operation, có thể bao gồm commit/rollback.
- **Operation duration:** thời gian từ lúc vào RecordFinal đến lúc tất cả retry kết thúc, gồm cả backoff nếu policy có backoff.

Cùng một operation có thể có attempt nhanh nhưng operation tổng kéo dài. Metric nên có nhãn ổn định như operation, outcome, error_class đã chuẩn hóa; không dùng correlation ID hoặc idempotency key làm nhãn metric cardinality cao.

Một bản ghi nên thể hiện scope, ví dụ:

~~~text
event=attempt.finished operation=placeOrder attempt=2 outcome=success tx=committed
event=operation.finished operation=placeOrder attempts=2 outcome=success
~~~

Không cần ghi thông tin nhạy cảm vào log chỉ để tương quan; dùng ID và dữ liệu đã được kiểm soát.

## 11. Tương tác với thời gian và giới hạn retry

Một chính sách retry cần nhiều thứ hơn maxAttempts:

1. **Backoff:** khoảng nghỉ giữa attempt, có thể tăng dần; thêm jitter khi nhiều client có nguy cơ retry đồng thời.
2. **Deadline tổng:** giới hạn thời gian operation, không chỉ từng attempt.
3. **Timeout mỗi attempt:** hạn chế một lượt bị kẹt; phải hiểu hành vi của tài nguyên sau timeout.
4. **Phân loại lỗi:** thử lại khi có bằng chứng lỗi tạm thời và việc lặp an toàn.
5. **Cancellation:** dừng tạo attempt mới nếu operation đã bị hủy hoặc thread bị interrupt theo hợp đồng.
6. **Retry budget:** giới hạn lượng công việc bổ sung tránh gây quá tải khi dịch vụ downstream đang lỗi.

Nếu advice retry sử dụng Thread.sleep để chờ backoff trong một API đồng bộ, cần xử lý InterruptedException đúng ngữ nghĩa (thường khôi phục cờ interrupt và chấm dứt retry hoặc truyền tín hiệu lên theo hợp đồng), thay vì nuốt ngắt. Trong API bất đồng bộ, nên dùng cơ chế lập lịch phi chặn tương ứng.

**Đặc biệt tránh giữ transaction mở trong thời gian backoff** chỉ vì Transaction nằm ngoài Retry. Transaction dài có thể giữ lock và tài nguyên, làm nặng thêm nguyên nhân lỗi ban đầu.

## 12. Giá trị trả về, ngoại lệ và trạng thái nghiệp vụ

Advice thường dựa trên việc return/throw, nhưng không phải mọi thất bại nghiệp vụ đều được biểu diễn bằng exception:

~~~text
operation() -> Result(status = DECLINED)
~~~

Nếu Transaction coi return bình thường là điều kiện commit và Recorder coi return là success, hệ thống có thể vừa commit vừa ghi “success”, dù về nghiệp vụ kết quả là từ chối.

Phải thống nhất hợp đồng:

- **Technical success:** phương thức hoặc transaction hoàn tất theo giao thức mà không có lỗi kỹ thuật.
- **Business outcome:** APPROVED, DECLINED, NOT_FOUND, PARTIAL… tùy domain.
- **Final delivery outcome:** người gọi nhận được kết quả hay lỗi, có thể khác trạng thái hệ thống bên dưới trong trường hợp timeout/mất phản hồi.

Nếu một kết quả kiểu DECLINED cần rollback, adapter nghiệp vụ/transaction phải có chính sách tường minh. Nếu DECLINED là kết quả hợp lệ cần lưu lại thì commit có thể đúng. Không tự cho rằng mọi giá trị “false” phải rollback hoặc mọi return đều là thành công nghiệp vụ.

Retry cũng vậy: retry một kết quả nghiệp vụ chỉ khi hợp đồng rõ ràng cho phép; không mặc định retry tất cả exception hoặc tất cả mã trạng thái khác success.

## 13. Transaction propagation, transaction bao ngoài và thứ tự thực tế

Ngay cả khi thiết kế có vẻ là Retry(Transaction(operation)), kết quả còn phụ thuộc chính sách transaction khi đã tồn tại transaction bên ngoài:

~~~text
External transaction T0
    -> RecordFinal
       -> Retry
          -> Transaction wrapper
             -> operation
~~~

Nếu Transaction wrapper chỉ tham gia T0, mọi attempt có thể vẫn ở cùng T0. Muốn khởi tạo transaction mới mỗi attempt phải cấu hình/triển khai chính sách phù hợp với transaction manager và xác định hậu quả của việc tách transaction.

Cũng cần phân biệt:

- **Transaction nested** có thể dùng savepoint và vẫn thuộc một transaction top-level.
- **Transaction independent/new** có thể commit riêng, không tự rollback cùng transaction ngoài.
- **Distributed transaction** hoặc nhiều resource có thể có nhiều trạng thái commit khác nhau.
- **Tài nguyên ngoài giao dịch** không được bao phủ chỉ vì code nằm giữa begin và commit.

Đừng dùng tên advice, annotation hoặc vị trí trong source file làm chứng cứ về ranh giới thực. Kiểm tra scope và outcome ở runtime.

## 14. Điều gì xảy ra nếu có nhiều aspect chồng lên nhau?

Một điểm cắt có thể đồng thời bị ảnh hưởng bởi retry, transaction, cache, authorization, correlation, timeout và result recording. Khi đó thứ tự cần được xác định cùng nhau.

Ví dụ:

~~~text
CorrelationScope(
  RecordFinal(
    Authorization(
      Retry(
        RecordAttempt(
          Transaction(
            operation
          )
        )
      )
    )
  )
)
~~~

Ví dụ chỉ minh họa cách đọc thứ tự, **không đề xuất duy nhất** thứ tự cho authorization. Có hệ thống cần kiểm tra quyền một lần, có hệ thống cần kiểm tra lại mỗi attempt; lựa chọn ảnh hưởng semantics, chi phí và an toàn.

Tương tự, nếu Cache ở ngoài Transaction, một cache hit có thể khiến Transaction không chạy; điều đó có thể đúng khi không cần nghiệp vụ cập nhật, nhưng sai nếu audit hoặc invariant bắt buộc phải đi qua transaction. Nếu timeout ở ngoài Retry, nó thường là deadline toàn operation; nếu ở trong, timeout có thể được tính riêng từng attempt. Nếu correlation ở trong Retry, mỗi attempt có thể vô tình nhận correlation ID mới; nếu bên ngoài, có thể giữ chung ID và tạo attempt ID riêng.

**Bài học:** cần vẽ chuỗi bao quanh hoàn chỉnh cho join point thực tế, không đánh giá từng aspect tách rời.

Ngoài ra, ở một số kiểu AOP, advice chỉ áp dụng cho các join point thật sự được weaving hoặc dispatch qua cơ chế interception. Tự gọi phương thức trong cùng đối tượng, phương thức không thuộc phạm vi điểm cắt hoặc lời gọi đi tắt cơ chế interception có thể không kích hoạt advice tùy công cụ. Phải kiểm chứng đường gọi thực tế trước khi tin rằng transaction/retry/record đang hoạt động.

## 15. Bất đồng bộ làm thay đổi ranh giới “kết thúc”

Nếu một phương thức trả về CompletableFuture hoặc một handle bất đồng bộ, around advice theo **lượt thực thi phương thức** có thể kết thúc ngay lúc phương thức trả về handle, trong khi công việc vẫn đang diễn ra.

~~~text
RecordFinal(
  Retry(
    Transaction(
      methodReturningFuture
    )
  )
)
~~~

Biểu thức ấy **không chứng minh** transaction sống đến khi future hoàn tất, không chứng minh retry quan sát lỗi xảy ra về sau và không chứng minh RecordFinal nhìn thấy outcome cuối. Nếu methodReturningFuture trả về future bình thường nhưng future hoàn tất lỗi sau đó, các advice theo return/throw đồng bộ có thể đã báo “success” quá sớm.

Muốn áp dụng chính sách vào tác vụ bất đồng bộ thực sự, cần định nghĩa:

- **Ranh giới operation:** completion của future, callback cuối, hoặc terminal signal được API công bố.
- **Ranh giới transaction:** tài nguyên và thread nào thực hiện công việc; transaction được mở/đóng lúc nào, ai sở hữu nó.
- **Ranh giới retry:** mỗi attempt mới khởi tạo công việc và tài nguyên mới hay chỉ lấy lại handle cũ.
- **Ranh giới recorder:** ghi outcome cuối sau completion hợp đồng, không chỉ sau khi trả về future.
- **Truyền context:** correlation, cancellation và transaction context phải có cơ chế propagation thích hợp; không giả định ThreadLocal tự truyền sang executor khác.

Một transaction gắn với thread không thể tùy tiện giữ mở xuyên qua các callback chạy bất kỳ thread nào chỉ bằng cách trì hoãn return. Thiết kế cần cơ chế transaction thật sự hỗ trợ mô hình thực thi đang dùng, hoặc đặt transaction quanh phần công việc diễn ra tại worker.

## 16. Điều kiện đảm bảo mỗi kết quả chỉ được ghi một lần

Ngay cả RecordFinal nằm ngoài Retry, lời gọi có thể được thực hiện lại bởi client hoặc hệ thống hàng đợi, khiến toàn bộ composition được chạy lại. Vì vậy “một RecordFinal trên một lượt gọi” **khác** với “một bản ghi bền vững cho một hành động nghiệp vụ toàn cục”.

Có ít nhất ba mức đảm bảo:

1. **Một callback trong một lượt advice:** lập trình đúng scope để callback/observer không kích hoạt hai lần không chủ đích.
2. **Một outcome logic trong một execution:** recorder ngoài cùng chỉ ghi sau khi Retry kết thúc; tránh ghi final trong từng attempt.
3. **Một bản ghi nghiệp vụ bền vững qua retry/restart:** dùng khóa định danh nghiệp vụ, transaction, unique constraint, trạng thái bền và quy trình deduplication tương ứng.

Nếu hệ thống cần audit thất bại **và** audit thành công ngay cả khi tiến trình crash, một lời gọi log trong finally chưa đảm bảo điều đó. Cần cơ chế lưu trữ và xác nhận có thể kiểm tra lại sau sự cố.

## 17. Kiểm thử thứ tự: kiểm tra sự kiện, không chỉ kết quả trả về

Kết quả cuối “OK” chưa đủ chứng minh advice được xếp đúng. Cần kiểm tra **chuỗi sự kiện** và trạng thái giao dịch.

| Tình huống kiểm thử | Kỳ vọng của mô hình tham khảo |
| --- | --- |
| Thành công ngay attempt 1 | Một transaction commit, một attempt success, một final success |
| Attempt 1 lỗi retryable; attempt 2 thành công | T1 rollback, T2 begin/commit; hai attempt records, một final success |
| Lỗi không retryable | Không có attempt tiếp; rollback phù hợp, một final failure |
| Hết maxAttempts | Số lần gọi không vượt budget, final failure chỉ một lần |
| Lỗi tại commit | Attempt phải thể hiện commit failure/uncertain; không ghi committed success giả |
| Lỗi tại recorder best effort | Không vô tình gây retry nghiệp vụ |
| Recorder bắt buộc thất bại | Lỗi được xử lý theo hợp đồng về độ bền và transaction |
| Retry sau phản hồi commit bị mất | Không tạo side effect trùng nhờ idempotency/reconciliation |
| Transaction có sẵn bên ngoài | Xác minh thực tế transaction mới hay tham gia transaction cũ |
| Lời gọi trả về future | Không đánh đồng return handle với completion logic |

Một kỹ thuật hữu ích là tiêm fake/stub có khả năng ghi thứ tự sự kiện:

~~~text
events = [
  "retry-1",
  "tx-begin-1",
  "business-fail",
  "tx-rollback-1",
  "attempt-fail",
  "retry-2",
  "tx-begin-2",
  "business-ok",
  "tx-commit-2",
  "attempt-success",
  "operation-success"
]
~~~

Bài kiểm thử quan trọng ở đây là **quan hệ thứ tự và số lần xảy ra**. Trong thực tế, nên có thêm integration test với transaction manager và loại database sử dụng để xác nhận rollback-only, lock, commit failure và cấu hình propagation. Một fake in log không thể chứng minh transaction thật có đúng hành vi.

## 18. Cách ra quyết định khi thiết kế chính sách thực thi

Khi chuẩn bị nhiều advice cho một operation, lần lượt trả lời:

1. **Đơn vị retry là gì?** Một câu lệnh, một thao tác nghiệp vụ, hay toàn bộ giao dịch?
2. **Mỗi attempt cần transaction mới không?** Nếu có, phải bảo đảm transaction boundary được tạo lại thật sự.
3. **Lỗi nào retryable?** Phân loại theo hợp đồng, khả năng phục hồi và idempotency.
4. **Điều kiện thành công là gì?** Return bình thường, business result hợp lệ, commit xác nhận, hay phản hồi từ hệ thống downstream?
5. **Ghi nhận từng attempt hay chỉ final?** Nếu cả hai, dùng recorder ở hai tầng và đặt tên event khác nhau.
6. **Độ bền của bản ghi cần đến đâu?** Log/metric chẩn đoán, audit bắt buộc hay event hậu commit cần thiết kế khác nhau.
7. **Có side effect nằm ngoài transaction không?** Payment/email/message cần idempotency hoặc cơ chế riêng.
8. **Có transaction bao ngoài không?** Xem xét propagation, nested transaction, savepoint và trạng thái rollback-only.
9. **Join point có thực sự được instrument không?** Kiểm tra precedence, weaving, đường gọi và ranh giới bất đồng bộ.
10. **Trường hợp commit in-doubt sẽ xử lý thế nào?** Tránh retry mù; cần reconciliation nếu không biết kết quả.
11. **Khi observer lỗi thì sao?** Quy định best effort hay mandatory, tránh biến lỗi log thành retry nghiệp vụ ngoài ý muốn.
12. **Có thể quan sát trực tiếp chuỗi sự kiện không?** Dùng test xác minh số attempt, số commit, số final record và thời lượng.

## 19. Các lỗi phổ biến và cách sửa

**Lỗi 1: Transaction bao Retry nhưng kỳ vọng có transaction mới mỗi attempt.** Đây là nhầm ranh giới. Hãy đặt Retry ngoài wrapper tạo transaction, hoặc dùng cơ chế transaction explicit per-attempt có hợp đồng tương đương, rồi xác minh trong integration test.

**Lỗi 2: Ghi success của nghiệp vụ trước commit.** Advice ghi kết quả nằm trong Transaction có thể thấy operation trả về nhưng chưa biết commit. Hãy ghi trạng thái “returned” nếu chỉ đo lượt gọi; nếu cần “committed”, đặt observer ở vị trí nhìn thấy commit hoặc dùng cơ chế sau commit đủ tin cậy.

**Lỗi 3: Ghi final failure cho từng attempt lỗi.** Người dùng có thể vẫn nhận success sau retry. Hãy phân biệt RecordAttempt và RecordFinal, với outcome cuối chỉ được ghi sau Retry.

**Lỗi 4: Retry mọi RuntimeException.** Có thể retry cả lỗi dữ liệu, vi phạm nghiệp vụ và lỗi của chính hệ thống ghi log. Hãy giới hạn loại lỗi, max attempts, backoff, deadline và idempotency.

**Lỗi 5: Cho rằng rollback database thu hồi luôn side effect ngoài database.** Gửi email hoặc thanh toán ở attempt 1 có thể tồn tại sau rollback; attempt 2 có thể lặp tác động. Dùng outbox, idempotency key, deduplication hoặc điều phối tác vụ phù hợp.

**Lỗi 6: Cho rằng lỗi commit chứng minh operation chưa từng commit.** Phản hồi commit có thể bị mất. Hãy phân biệt failure chắc chắn với trạng thái unknown và dùng cơ chế kiểm tra/đối soát.

**Lỗi 7: Đặt recorder có thể throw bên trong Retry mà không phân biệt nguồn lỗi.** Một lỗi telemetry có thể làm operation bị thực thi lại. Định nghĩa recorder best effort hoặc bắt lỗi recorder riêng; nếu mandatory, thiết kế transaction và retry cho nó độc lập.

**Lỗi 8: Dùng metric failure của attempt làm failure rate của operation.** Hãy đo hai cấp độ và giữ mẫu số thống nhất.

**Lỗi 9: Retry bên trong transaction trong lúc chờ backoff dài.** Transaction có thể giữ resource/lock và làm tăng tải. Ưu tiên giải phóng transaction sau mỗi attempt khi chính sách yêu cầu giao dịch mới.

**Lỗi 10: Bỏ qua hợp đồng asynchronous.** Method return future không đồng nghĩa task hoàn tất. Áp dụng transaction, retry và recorder vào đúng vòng đời logic của tác vụ và đúng đơn vị thực thi.

## 20. Tình huống tự kiểm tra

**Tình huống A.** Một operation ném lỗi transient ở lần đầu, rồi trả về thành công ở lần thứ hai. Nếu dùng RecordFinal(Retry(RecordAttempt(Transaction(operation)))), có bao nhiêu record?

**Đáp án:** hai record ở cấp attempt (một failure, một success) và một record ở cấp operation (success). Transaction có hai lượt riêng nếu wrapper thật sự tạo mới mỗi lần. Final success chỉ xuất hiện sau khi commit của lượt thành công được xác nhận.

**Tình huống B.** Transaction(Retry(operation)) nhận một lỗi làm database đánh dấu transaction là aborted. Retry bắt lỗi và gọi lại ngay trong transaction ấy. Lần tiếp theo có chắc chạy thành công không?

**Đáp án:** không. Retry đã nuốt exception nhưng không làm transaction trở về trạng thái hợp lệ. Cần rollback transaction và tạo transaction mới, hoặc một cơ chế phục hồi/savepoint được tài nguyên thực sự hỗ trợ.

**Tình huống C.** Operation cập nhật database và gửi email trước commit. Attempt đầu gửi email thành công rồi lỗi DB rollback, attempt sau chạy lại. Có rủi ro nào?

**Đáp án:** email có thể được gửi hai lần vì email không tham gia rollback DB. Cần thiết kế idempotency, transactional outbox hoặc một chiến lược tách side effect theo hợp đồng.

**Tình huống D.** Business method trả về bình thường, nhưng commit ném lỗi. Recorder nằm ngay trong transaction wrapper và đã ghi “committed”. Đúng không?

**Đáp án:** sai. Recorder bên trong chỉ biết business method return, chưa biết commit. Nên quan sát transaction outcome ở bên ngoài hoặc ghi sự kiện mô tả đúng “business returned”.

**Tình huống E.** Một log exporter tạm thời không truy cập được, RecordAttempt ném lỗi và Retry gọi lại nghiệp vụ. Lỗi thiết kế ở đâu?

**Đáp án:** nguồn lỗi telemetry bị trộn với nguồn lỗi nghiệp vụ để retry. Cần chính sách best effort/mandatory tường minh và không cho lỗi log tự kích hoạt lặp nghiệp vụ ngoài dự kiến.

**Tình huống F.** Operation lần đầu đã commit nhưng client timeout và gửi lại cùng idempotency key. Retry an toàn cần gì?

**Đáp án:** xử lý idempotent ở phía thực thi, ví dụ unique key bền vững và trả lại kết quả đã có; timeout không phải bằng chứng rollback. Có thể cần reconciliation nếu không xác định được outcome.

## 21. Kết luận kỹ thuật

Thứ tự aspect là một phần của **hợp đồng thực thi**. Với một nghiệp vụ đồng bộ có retry toàn giao dịch, cấu trúc tham khảo rõ ràng là:

~~~text
RecordFinal(
  Retry(
    RecordAttempt(
      Transaction(
        operation
      )
    )
  )
)
~~~

Cấu trúc này cho phép mỗi attempt đi qua một transaction theo đúng chính sách tạo transaction; recorder bên trong retry ghi từng attempt **sau xử lý transaction**, recorder ngoài cùng ghi outcome **cuối cùng** sau toàn bộ retry. Tính đúng đắn vẫn phụ thuộc loại lỗi được retry, trạng thái commit, idempotency, độ bền của ghi nhận, transaction propagation và ranh giới thực thi bất đồng bộ.

Khi thiết kế, luôn xác định rõ **cái gì được lặp**, **cái gì được commit**, **khi nào được gọi là thành công**, và **mỗi bản ghi đại diện cho một attempt hay một operation**. Sau đó kiểm tra thứ tự sự kiện trên implementation thật.