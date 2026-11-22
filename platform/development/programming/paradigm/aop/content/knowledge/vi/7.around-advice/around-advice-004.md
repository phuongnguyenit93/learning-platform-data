# Thay đổi tham số hoặc kết quả khi công cụ cho phép trong Around Advice

## 1. Bản chất của việc thay đổi dữ liệu tại điểm can thiệp

Trong **Aspect-Oriented Programming (AOP)**, một **around advice** có thể được đặt bao quanh một **join point** được pointcut chọn. Trong mô hình có khả năng điều phối tiếp tục thực thi, around advice nhận quyền quyết định **có tiếp tục vào hành vi gốc hay không**, **tiếp tục với dữ liệu nào** và **giá trị nào được trả về phía caller**. Điều này khác before advice, vốn thông thường chỉ chạy trước join point mà không trực tiếp sở hữu cơ chế tiếp tục hay giá trị cuối cùng.

Một số ngôn ngữ AOP hỗ trợ gọi một thao tác tương tự **proceed** với đối số mới. Một số cơ chế interceptor cho phép chỉnh sửa danh sách đối số trước khi gọi target hoặc thay giá trị trả về sau lời gọi. Nhưng **không có bảo đảm phổ quát rằng mọi công cụ AOP đều cho phép sửa tham số, đổi kết quả hoặc bỏ qua target**: quyền hạn phụ thuộc loại join point, weaving/interception, API tiếp tục và hợp đồng kiểu của công cụ.

Mô hình ý tưởng:

~~~text
Caller gửi đối số A
        │
        ▼
Pointcut chọn join point
        │
        ▼
Around advice nhận ngữ cảnh ban đầu
        │
        ├─ Kiểm tra A, quyết định gọi tiếp hay dừng
        │
        ├─ Nếu gọi tiếp: tạo đối số A' hợp lệ
        │       │
        │       ▼
        │    proceed(A') / invoke(target, A')
        │       │
        │       ▼
        │    Target thực thi và trả R
        │       │
        └─ Có thể đổi R thành R' hợp lệ
                │
                ▼
         Caller nhận R'
~~~

Có ba quyết định **khác nhau** cần học:

1. **Thay đổi đối số đi vào target:** caller truyền A, target có thể nhận A' nếu cơ chế cho phép.
2. **Thay đổi kết quả đưa về caller:** target trả R, caller có thể nhận R' nếu advice thay kết quả hợp lệ.
3. **Bỏ qua hoặc lặp target:** advice có thể không tiếp tục, hoặc tiếp tục nhiều lần trong một số mô hình; điều này không đồng nhất với việc chỉ thay đối số/kết quả.

Thay đổi tham số hoặc kết quả là **thay đổi hành vi quan sát được của chương trình**, không còn là logging thuần túy. Vì thế phải có yêu cầu thiết kế cụ thể và kiểm thử hợp đồng.

## 2. Phân biệt bốn kiểu thay đổi thường bị nhầm lẫn

| Kiểu thay đổi | Ví dụ | Có chắc target nhận thay đổi không? |
|---|---|---|
| **Gán lại biến local trong advice** | Đổi biến amount từ 10 thành 20 trong scope advice | Không; việc gán lại local không tự sửa tham số của lời gọi gốc |
| **Sửa trạng thái object mutable được chia sẻ** | Thêm phần tử vào List được bind từ argument | Target có thể thấy thay đổi trên cùng object, nhưng đó là side effect, không nhất thiết là thay thế argument |
| **Thay argument lúc tiếp tục** | Gọi cơ chế proceed với amount mới | Có nếu công cụ cho phép và dữ liệu mới được bind đúng vị trí/chữ ký |
| **Thay return sau khi target chạy** | Target trả 50, advice trả 52 | Caller có thể nhận 52 nếu công cụ cho phép, return type tương thích và không có advice bao ngoài đổi thêm |

Ví dụ Java về reference:

~~~java
static void inspect(java.util.List<String> values) {
    values.add("marker"); // Mutate object mà caller và target có thể cùng thấy.
    values = new java.util.ArrayList<>(); // Chỉ đổi local reference.
}
~~~

Đây là đoạn minh họa, không phải chương trình Java độc lập. Java truyền **giá trị của reference** cho parameter. Nếu advice chỉ gán lại một local parameter, target không tự nhận reference mới; muốn thay argument ở ranh giới tiếp tục, phải dùng chức năng do mô hình AOP cung cấp.

Một lỗi nghiêm trọng là gọi việc mutate object là “thay tham số an toàn” rồi quên rằng caller vẫn giữ reference đến object gốc. Điều này có thể gây side effect lâu dài ngoài join point.

## 3. Around advice khác before, after và after returning như thế nào?

| Loại advice | Khi nào chạy? | Có thể tự điều phối target không? | Có thể trực tiếp đổi return của target theo nghĩa thông thường không? |
|---|---|---|---|
| **Before** | Trước join point | Thông thường không có proceed | Không; có thể throw hoặc mutate dữ liệu dùng chung |
| **After returning** | Sau khi hoàn tất bình thường | Không trực tiếp điều phối việc gọi target | Thông thường để quan sát kết quả; không tự thay return theo kiểu around |
| **After throwing** | Khi join point kết thúc bằng ngoại lệ phù hợp | Không trực tiếp điều phối | Thường dùng để quan sát/ghi lỗi |
| **After/finally** | Khi rời join point theo quy tắc của engine | Không trực tiếp điều phối | Không có bảo đảm thay kết quả |
| **Around** | Bao quanh phần tiếp tục của join point | Có thể quyết định khi nào/bao nhiêu lần tiếp tục nếu engine hỗ trợ | Có thể trả kết quả khác nếu API và hợp đồng kiểu cho phép |

“Có thể” không nghĩa “nên”. Một around advice chỉ để đo thời gian thường nên **trả nguyên kết quả và lan truyền nguyên ngoại lệ**, dù về kỹ thuật nó có khả năng thay đổi chúng.

Ngược lại, một around advice thực hiện **cache**, **chặn thao tác**, **retry**, **giới hạn giá trị**, **chuyển đổi kiểu dữ liệu** hoặc **fallback** có thể có lý do chính đáng để thay đối số hoặc return. Lý do cần thể hiện qua hợp đồng và test, không giấu trong tên gọi chung “advice”.

## 4. Quyền tiếp tục là điều kiện để biến đổi dữ liệu

`proceed` hoặc continuation tương đương chuyển điều khiển vào phần còn lại của chuỗi advice, có thể qua nhiều advice trước target. Vì vậy cần tách **khả năng đọc đối số**, **quyền thay đối số lúc tiếp tục**, **quyền thay result** và **quyền điều phối số lần gọi**.

| Quyết định quanh continuation | Điều phải kiểm tra |
|---|---|
| **Gọi tiếp một lần** | Target/inner advice nhận đúng args; kết quả và lỗi được chuyển tiếp hoặc biến đổi có hợp đồng |
| **Không gọi tiếp** | Nếu trả fallback, đó phải là kết quả hợp lệ; side effect bắt buộc của target không được bỏ sót |
| **Gọi tiếp nhiều lần** | Công cụ có hỗ trợ và thao tác có an toàn khi lặp không? Retry phải xét idempotency và số effect |
| **Thay args/result** | API và loại join point có cho phép không? Kiểu, thứ tự, nullability và ý nghĩa nghiệp vụ có còn đúng không? |

Đặc biệt, **gán lại một biến local không tự thay argument mà target nhận**. Những điểm này là ranh giới trước khi đi sâu vào việc thay dữ liệu ở các phần tiếp theo, không phải lời hứa rằng mọi AOP đều cung cấp một lệnh `proceed(newArgs)` thống nhất.

## 5. Thay đổi đối số đầu vào: có những bước nào?

Xét một phương thức:

~~~java
int charge(int units);
~~~

Đây là khai báo minh họa. Một chính sách kỹ thuật có thể yêu cầu **giới hạn units tối đa 5** trước khi tiếp tục.

Trình tự:

1. Nhận giá trị caller truyền, ví dụ units = 9.
2. Kiểm tra loại dữ liệu, phạm vi, hợp lệ/ngữ nghĩa của đơn vị.
3. Tạo giá trị mới, ví dụ min(9, 5) = 5.
4. Tiếp tục gọi target **với 5**, nếu engine cho phép đổi argument.
5. Target thực thi trên giá trị 5, không phải 9.
6. Advice có thể quan sát kết quả hoặc thay đổi kết quả sau đó.

Điểm then chốt: bước 4 **phải thực sự chuyển 5 vào đường tiếp tục**. Việc chỉ in “normalized = 5” hoặc gán lại biến local không bảo đảm target nhận được 5.

### 5.1. Đúng số lượng và đúng vị trí

Với chữ ký:

~~~java
String build(String name, int count, boolean urgent);
~~~

Nếu cơ chế dùng argument array, phần tử 0 phải tương ứng name, phần tử 1 tương ứng count, phần tử 2 tương ứng urgent. Một thay đổi vị trí sẽ làm sai ý nghĩa hoặc thất bại kiểm tra kiểu.

Khi dùng overload, **tên phương thức không đủ** phân biệt chữ ký. Hai overload có thể cần quy tắc normalize hoàn toàn khác.

### 5.2. Primitive, wrapper và chuyển kiểu

Java phân biệt primitive như int, long, boolean và kiểu reference như Integer, Long, Boolean. Khi engine dùng reflection, primitive có thể được đại diện dưới wrapper trong Object array, nhưng giá trị được truyền cuối cùng vẫn phải tương thích với method signature.

Không nên giả định:

- Có thể gửi null cho primitive int.
- Có thể gửi String thay cho int mà Java tự parse.
- Có thể thu hẹp long sang int không mất dữ liệu.
- Mọi conversion hợp lệ ở source Java cũng được interceptor thực hiện ngầm theo cách giống compiler.

Nếu cần convert, hãy convert có kiểm tra, xác định chính sách overflow và validate lại theo hợp đồng method.

### 5.3. Reference type và immutable object

Nếu caller truyền một String, không thể mutate nội dung bên trong String; muốn target thấy String khác phải thay reference được dùng tại lời gọi tiếp tục. Với mutable List, có hai lựa chọn mang nghĩa khác nhau:

~~~text
Option A: mutate list cũ rồi tiếp tục với chính list đó
Option B: tạo bản sao đã chuẩn hóa rồi tiếp tục với list mới
~~~

Option A thay dữ liệu mà caller có thể đang giữ; Option B có thể cô lập một số side effect nếu sao chép đúng độ sâu và loại dữ liệu. Copy shallow chỉ sao chép container, không sao chép mọi object con.

### 5.4. Null và validation

Null có thể là giá trị hợp lệ theo API hoặc là dấu hiệu input bị lỗi. Một around advice tự đổi null thành giá trị mặc định có thể che mất lỗi hoặc biến một tham số mang ý nghĩa “không có” thành dữ liệu giả.

Chỉ normalize null khi **hợp đồng API** yêu cầu hoặc cho phép; ghi rõ sự khác nhau giữa “caller không cung cấp” và “caller cung cấp giá trị mặc định”.

## 6. Thay đổi giá trị trả về: phải bảo toàn những ràng buộc nào?

Giả sử target trả về 50 nhưng advice thêm một khoản tính phí 2 và trả 52. Điều này hợp lệ về mặt kỹ thuật nếu:

- Cả target và advice trả giá trị phù hợp với kiểu trả về khai báo.
- Policy tính phí được phép áp dụng đúng tại điểm đó.
- Không tạo tính phí kép khi có aspect hoặc wrapper khác.
- Nếu target throw, không vô ý trả 52 như thể target thành công.
- Nếu target được gọi nhiều lần, kết quả và side effect vẫn nhất quán.

Một giả mã:

~~~text
around selectedMethod:
    raw = proceed()
    adjusted = raw + surcharge
    return adjusted
~~~

Không phải mọi ngôn ngữ AOP chấp nhận biểu thức trên đúng cú pháp. Ý tưởng là **advice lấy kết quả từ đường tiếp tục và chủ động chọn giá trị trả về**.

### 6.1. Kiểu trả về phải tương thích

| Kiểu method gốc | Thay đổi phù hợp về mặt kiểu | Rủi ro thường gặp |
|---|---|---|
| **int / long / double** | Trả giá trị cùng kiểu tương thích theo engine | Overflow, precision, nhầm đơn vị tiền tệ |
| **String** | Trả một String khác | Đổi ngữ nghĩa, encoding, nội dung bí mật |
| **Object/interface** | Trả object triển khai interface được yêu cầu | ClassCastException hoặc thay behavior bất ngờ |
| **Optional<T>** | Trả Optional phù hợp | Nhầm empty với lỗi/thất bại |
| **void** | Không có return value nghiệp vụ | Không thể thay thành một số hoặc object như method có giá trị |
| **Future/CompletionStage** | Trả một kết quả bất đồng bộ tương thích | Advice chỉ sửa wrapper, chưa chắc sửa payload khi future hoàn tất |

Với method trả primitive, một interceptor trả null hoặc object không tương thích có thể gây lỗi runtime. Với generic, type erasure và bridge methods có thể khiến kiểm tra kiểu ở nhiều lớp khác nhau; phải xác minh với engine thực.

### 6.2. Trả kết quả thay thế mà không gọi target

Nếu quanh một method có **cache hit**, advice có thể trả dữ liệu được lưu từ trước theo chính sách. Nhưng phải trả dữ liệu đúng tuổi, đúng key, đúng phân quyền và đúng type.

Nếu target lẽ ra phải tăng bộ đếm nghiệp vụ, ghi transaction hoặc giữ invariant, bỏ qua target chỉ vì cache hit có thể làm sai hệ thống. Cache quanh **đọc dữ liệu thuần hoặc đọc được phép tái sử dụng** thường có hợp đồng dễ chứng minh hơn.

### 6.3. Trả fallback sau ngoại lệ

Một around advice có thể bắt lỗi từ proceed và trả giá trị fallback, nếu công cụ hỗ trợ:

~~~text
around:
    try:
        return proceed()
    catch TemporaryFailure:
        return approvedFallback
~~~

Đây là quyết định thay đổi **exception contract**. Nếu caller cần biết rằng thao tác thất bại để rollback hoặc cảnh báo, nuốt lỗi rồi trả giá trị mặc định sẽ làm sai hành vi.

Fallback cần giới hạn loại ngoại lệ được xử lý, khả năng chấp nhận dữ liệu cũ/mặc định và cách ghi nhận failure. Không nên catch mọi Throwable rồi trả một giá trị “cho hệ thống ổn định”.

## 7. Ví dụ Java 17 chạy được: biến đổi đối số, thay kết quả, bỏ qua target

Để quan sát điều khiển một cách rõ ràng mà không cần cài ngôn ngữ AOP riêng, ví dụ sau dùng **JDK dynamic proxy**. Invocation handler đóng vai trò **mô phỏng một around interceptor**: nhận tham số, quyết định gọi target, thay tham số trước khi invoke và đổi giá trị sau khi target trả về.

Đây **không phải bộ dệt bytecode** và **không phải một pointcut language hoàn chỉnh**. Nó là ví dụ Java độc lập để kiểm tra hành vi.

Tạo file **AroundTransformationDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class AroundTransformationDemo {
    interface Checkout {
        int charge(int units);
    }

    static final class Core implements Checkout {
        int calls;

        @Override
        public int charge(int units) {
            calls++;
            System.out.println("core: units=" + units);
            return units * 10;
        }
    }

    static Checkout intercepted(Checkout target) {
        return (Checkout) Proxy.newProxyInstance(
                Checkout.class.getClassLoader(),
                new Class<?>[]{Checkout.class},
                (proxy, method, args) -> {
                    int original = (int) args[0];
                    System.out.println("around: original=" + original);

                    if (original < 0) {
                        throw new IllegalArgumentException(
                                "units must be nonnegative");
                    }
                    if (original == 0) {
                        System.out.println("around: skipped");
                        return 0;
                    }

                    int rewritten = Math.min(original, 5);
                    System.out.println("around: proceeding=" + rewritten);
                    try {
                        int raw = (int) method.invoke(
                                target, new Object[]{rewritten});
                        System.out.println("around: raw=" + raw);
                        return raw + 2;
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        Core core = new Core();
        Checkout checkout = intercepted(core);

        System.out.println("request=3");
        System.out.println("result=" + checkout.charge(3));

        System.out.println("request=9");
        System.out.println("result=" + checkout.charge(9));

        System.out.println("request=0");
        System.out.println("result=" + checkout.charge(0));

        System.out.println("request=-1");
        try {
            checkout.charge(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("caught=" + e.getMessage());
        }

        System.out.println("core calls=" + core.calls);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AroundTransformationDemo.java
java AroundTransformationDemo
~~~

Stdout chính xác:

~~~text
request=3
around: original=3
around: proceeding=3
core: units=3
around: raw=30
result=32
request=9
around: original=9
around: proceeding=5
core: units=5
around: raw=50
result=52
request=0
around: original=0
around: skipped
result=0
request=-1
around: original=-1
caught=units must be nonnegative
core calls=2
~~~

**Giải thích theo từng trường hợp:**

- **charge(3):** advice nhận 3, chuyển tiếp 3 cho Core; Core tính 30; interceptor thêm 2; caller nhận 32.
- **charge(9):** advice nhận 9, giới hạn đối số thành 5, target chỉ thấy 5; Core tính 50; interceptor trả 52. Đó là **thay input và output** trên cùng một lượt.
- **charge(0):** advice không gọi method.invoke; target hoàn toàn không chạy ở lượt này, và interceptor trả 0.
- **charge(-1):** advice ném IllegalArgumentException trước khi gọi target. Ngoại lệ đến caller, không có kết quả nghiệp vụ bình thường.
- **core calls=2:** chỉ lượt charge(3) và charge(9) đi vào Core, minh chứng rõ việc skip/throw ảnh hưởng số lần target chạy.

Nếu caller giữ reference trực tiếp tới **core** và gọi **core.charge(9)**, lời gọi ấy sẽ đi thẳng vào Core và trả 90, vì không đi qua interceptor. Do đó kỹ thuật proxy chỉ áp dụng chính sách lên đường đã được bao bằng proxy; không nên suy thành “mọi lần gọi charge ở toàn ứng dụng đều tự động được biến đổi”.

Trong ví dụ thực tế về hóa đơn, việc giới hạn số lượng và cộng khoản phí **chỉ là giả định phục vụ giải thích cơ chế**. Không nên coi đây là chính sách tính phí đúng cho mọi ứng dụng; những biến đổi nghiệp vụ phải được chủ sở hữu API quy định.

### 7.1. Vì sao phải unwrap InvocationTargetException?

Khi Java reflection gọi target bằng Method.invoke, một lỗi do target ném có thể được bọc trong InvocationTargetException. Handler dùng **getCause()** để chuyển lỗi gốc đúng hơn đến caller.

Nếu không tách lỗi, caller có thể thấy dạng exception khác với contract nghiệp vụ. Ngoài ra, một dynamic proxy có thể dùng UndeclaredThrowableException để bọc checked exception không hợp lệ theo interface. Đây là rủi ro cần quan sát khi thiết kế around interceptor dùng reflection.

### 7.2. Vì sao cùng một ví dụ có thể biểu diễn nhiều lựa chọn quanh target?

Handler không chỉ chạy một lệnh before. Nó **quyết định cả phần trước, phần tiếp tục và phần sau**:

~~~text
Before: nhận và kiểm tra original
Decision: throw / skip / proceed với rewritten
Target: chạy hoặc không chạy
After: đọc raw và trả adjusted
~~~

Đó là những năng lực khiến around advice khác before/after thuần túy.

## 8. Ví dụ pointcut tổng quát với proceed thay tham số

Đoạn dưới là **giả mã AOP**, độc lập công cụ:

~~~text
aspect QuantityPolicy
    pointcut selected =
        execution of Checkout.charge(int)

    around selected(originalUnits):
        if originalUnits < 0:
            throw InvalidUnits

        if originalUnits == 0:
            return 0

        safeUnits = min(originalUnits, 5)

        raw = proceedWith(safeUnits)
        return raw + 2
end
~~~

Khi chuyển sang một ngôn ngữ AOP cụ thể, cần đổi đúng cú pháp và semantics của công cụ. Ví dụ một số hệ thống ràng buộc tham số qua **args(...)**, rồi cho truyền giá trị mới tương ứng qua **proceed**; một số API cung cấp phương thức tương đương **proceed(newArguments)**.

Không phải cứ đổi nội dung một mảng args do metadata cung cấp là target chắc chắn nhận mảng mới. Một số metadata chỉ để **đọc**; một số request context không đồng nghĩa đối số của method. Hãy kiểm tra ví dụ và test với phiên bản công cụ đang dùng.

## 9. Điều kiện tiên quyết để thay đối số đúng

### 9.1. Chọn đúng join point

Nếu chọn method-call join point, thao tác thay argument gắn với **một vị trí gọi**. Nếu chọn method-execution join point, nó gắn với **phần thân được thực thi** theo cơ chế được hỗ trợ. Sự khác biệt quan trọng khi:

- Một method được gọi từ nhiều caller.
- Một interface có nhiều implementation.
- Lớp con override method.
- Lời gọi nội bộ hoặc private method không đi qua proxy.
- Một method có nhiều overload.

Không nên viết một pattern theo tên method rồi giả định nó bao phủ mọi implementation và mọi caller.

### 9.2. Khớp signature sau khi thay

Nếu method là **charge(int)** mà proceed nhận argument kiểu khác không chuyển đổi được, quá trình tiếp tục có thể thất bại trước khi target chạy. Cần test đường thành công và đường sai kiểu.

Nếu có varargs, array parameter, primitive boxing và generic, phải hiểu representation ở API interception. Một reflection API có thể biểu diễn varargs dưới dạng một array ở vị trí cuối; không được tùy tiện trải nó thành nhiều argument riêng.

### 9.3. Hợp đồng nghiệp vụ không được tự tiện đổi

Một method nhận **requestedUnits = 9** nhưng thực thi với **5** sẽ làm caller dễ hiểu sai nếu nó tưởng cả 9 đã được xử lý. Hãy quyết định xem API có cần:

- Trả về số lượng **đã thực xử lý**.
- Báo rõ việc input bị giới hạn.
- Từ chối thay vì âm thầm sửa input.
- Ghi audit về original và effective value.
- Bảo đảm downstream không tính phí 9 cho một thao tác chỉ xử lý 5.

Với thay đổi chính sách nghiệp vụ, nên cân nhắc đặt normalization/validation vào API hoặc một component tường minh nếu tính minh bạch quan trọng. AOP thích hợp khi quy tắc thực sự là concern xuyên cắt và việc tự động áp dụng có lợi ích rõ.

### 9.4. Không làm hỏng invariant của đối tượng

Thay argument reference bằng một object thuộc subtype hợp lệ về compile type chưa chắc đáp ứng mọi invariant mà target trông đợi, ví dụ object phải được tạo từ một factory có kiểm tra. AOP không làm biến mất những ràng buộc này.

## 10. Hợp đồng kết quả: caller thấy gì?

Hình dung ba giá trị:

~~~text
Caller đưa input A
     │
     ▼
Advice đổi thành A'
     │
     ▼
Target tính R = f(A')
     │
     ▼
Advice đổi thành R' = g(R)
     │
     ▼
Caller nhận R'
~~~

Nếu không có các thay đổi bổ sung, caller quan sát hàm mới **g(f(transform(A)))**, khác với **f(A)** của code gốc. Đó là sự biến đổi có thể chứng minh bằng test.

Một số tình huống cần làm rõ:

1. **Method void:** advice có thể chạy trước/sau và ngăn target trong mô hình hỗ trợ, nhưng không thể trả một “giá trị thành công” kiểu int thay cho method void theo contract thông thường.
2. **Primitive result:** phải tương thích primitive, tránh null và sai boxing.
3. **Reference result:** phải bảo đảm object phù hợp loại mà caller mong đợi và invariant của API.
4. **Generic result:** compiler/bytecode có thể dùng erasure; kết quả giả có thể thất bại khi caller cast hoặc sử dụng.
5. **Exception:** nếu target throw, không có R bình thường để biến đổi; muốn fallback phải chủ động bắt loại lỗi tương ứng.
6. **Async result:** nếu method trả CompletionStage, giá trị ở biên hiện tại là một stage; kết quả nghiệp vụ sau này có thể chỉ xuất hiện khi stage hoàn tất. Phải quyết định biến đổi wrapper hay payload bất đồng bộ.

### 10.1. Bất đồng bộ: biến đổi kết quả ở đúng thời điểm

Ví dụ một API trả CompletionStage<Integer>. Around advice gọi target và nhận stage. Việc cộng 2 trực tiếp vào stage là không có nghĩa; nếu muốn biến đổi payload, có thể cần dùng một phép ánh xạ bất đồng bộ tương tự **thenApply**, hoặc một khả năng được API interception cung cấp.

Điều này thay đổi các cân nhắc khác: exception bất đồng bộ được truyền qua stage, cancellation có thể ảnh hưởng pipeline và context của request có thể không tự đi qua thread khác.

Nếu mục đích chỉ là logging, before/after ở thời điểm method trả stage có thể ghi “đã tạo tác vụ” chứ không phải “tác vụ đã hoàn tất”.

## 11. Khi nhiều around advice cùng bao lấy join point

Giả sử có hai aspect:

- **Normalize:** đổi A thành A'.
- **Fee:** cộng 2 vào kết quả target.

Nếu thứ tự lồng nhau là:

~~~text
Fee(Normalize(Core))
~~~

Thì fee nhận kết quả sau khi Normalize đã thực hiện lời gọi tiếp tục. Nếu thứ tự đảo ngược và các advice cùng can thiệp argument/return, kết quả có thể khác tùy cách triển khai.

Ví dụ cụ thể với toán học:

~~~text
Core(x) = x * 10
Normalize(x) = min(x, 5)
DoubleResult(r) = r * 2
AddTwo(r) = r + 2

AddTwo(DoubleResult(Core(5))) = 102
DoubleResult(AddTwo(Core(5))) = 104
~~~

Thứ tự có thể làm thay đổi giá trị nghiệp vụ, nên phải xác định **precedence** khi nhiều aspect chọn cùng join point. Không được suy thứ tự từ tên file, thứ tự class được tải hoặc vị trí được liệt kê trừ khi công cụ chính thức định nghĩa như vậy.

Nếu around bên ngoài bỏ qua proceed, around bên trong cùng target có thể không chạy. Nếu around bên ngoài gọi proceed hai lần, around bên trong có thể chạy hai lần. Vì thế việc đếm invocation chỉ ở một advice có thể khác số lần caller gọi vào API.

## 12. Ngoại lệ và tính đúng đắn khi đổi kết quả

Một around advice có ba nguồn lỗi:

1. **Lỗi do chính advice tạo ra**, ví dụ validate input âm và throw.
2. **Lỗi do target/proceed tạo ra**, như timeout, lỗi dữ liệu hoặc exception nghiệp vụ.
3. **Lỗi khi biến đổi output**, ví dụ overflow, cast sai hoặc ghi nhận dữ liệu sau xử lý thất bại.

Khi một trong ba lỗi xảy ra, phải quyết định về hợp đồng:

- Lỗi nào được truyền nguyên đến caller?
- Lỗi nào được chuyển thành lỗi khác có chủ ý?
- Có được trả fallback không?
- Có cần ghi event “đã thử”, “đã hoàn tất” hay “thất bại”?
- Khi retry, side effect đã xảy ra có thể lặp không?

### 12.1. Không nuốt lỗi rộng

Giả mã nguy hiểm:

~~~text
try:
    return proceed()
catch any error:
    return defaultValue
~~~

Nếu lỗi phát sinh từ vi phạm invariant hoặc lỗi lập trình, trả default có thể biến sự cố nghiêm trọng thành dữ liệu tưởng như hợp lệ. Chỉ xử lý những lỗi được policy cho phép; giữ metadata lỗi khi cần và không vô ý xóa dấu vết thất bại.

### 12.2. Checked exceptions và reflection

Khi dùng API reflection/proxy, exception từ target có thể được bọc. Nếu xử lý không đúng, caller có thể nhận exception khác với chữ ký method đã khai báo. Một around advice có kiểu trả về đúng nhưng exception không đúng vẫn có thể phá hợp đồng API.

### 12.3. Transaction và tính nguyên tử

Biến đổi tham số hoặc return có thể ảnh hưởng tính nhất quán khi target đã ghi dữ liệu xuống kho. Nếu advice đổi R sau khi target commit, caller có thể tưởng đã ghi một giá trị khác với thực tế. Nếu quanh một thao tác có transaction boundary, hãy xác định rõ advice thực thi **trước, trong hay sau** biên transaction theo thứ tự wrapping; không dựa vào hình thức tên advice.

## 13. Trường hợp dùng hợp lý và trường hợp cần thận trọng

| Nhu cầu | Khả năng around có thể dùng | Rủi ro phải quản lý |
|---|---|---|
| **Chuẩn hóa đầu vào kỹ thuật** | Đổi A thành A' ở điểm chung | Caller có biết giá trị hiệu lực không; mutation ngoài ý định |
| **Cache ở API đọc** | Trả cache hit mà không gọi target | Freshness, authorization, invalidation, side effects |
| **Fallback được định nghĩa** | Bắt một loại lỗi đã cho và trả R' | Che mất lỗi nghiêm trọng hoặc báo thành công giả |
| **Retry hữu hạn** | Gọi tiếp nhiều lần khi lỗi tạm thời | Idempotency, duplicate side effects, timeout |
| **Thay đổi representation của output** | Chuyển một value object sang format yêu cầu | Kiểu dữ liệu, precision, invariant, compatibility |
| **Redaction ở biên xuất dữ liệu** | Bỏ nội dung nhạy cảm khỏi output | Đủ coverage, không mất dữ liệu cần thiết |
| **Trả kết quả giả lập trong test** | Không gọi target trên một đường kiểm thử | Test có đại diện production behavior không |
| **Tính phí/quy tắc miền** | Về kỹ thuật có thể thay input/output | Phụ thuộc ẩn, double charge, sai trạng thái; thường cần contract rõ trong tầng miền |

Nên áp dụng around khi **khả năng điều phối thực sự cần thiết**. Nếu chỉ muốn log thời điểm bắt đầu thì before đã đủ về mặt ý nghĩa; nếu chỉ muốn ghi lỗi sau khi target throw thì after-throwing thường dễ hiểu hơn trong mô hình có nó.

## 14. Cơ chế weaving quyết định giới hạn thay dữ liệu

### 14.1. Compile-time hoặc load-time weaving

Một bộ dệt có thể sửa bytecode tại method call/execution hoặc loại join point khác mà nó hỗ trợ. Việc điều chỉnh dữ liệu phải tuân theo API và luật binding/proceed của ngôn ngữ AOP.

Có trường hợp một lời gọi nội bộ trên cùng object vẫn được weave nếu bộ dệt instrument trực tiếp execution; điều đó không tự đúng ở tất cả cơ chế.

### 14.2. Runtime proxy/interception

Một proxy chỉ áp dụng khi caller thực sự gọi qua proxy. Nếu code gọi target gốc, interceptor không hoạt động trên đường đó.

Một JDK dynamic proxy dựa vào interface, handler nhận đối số theo representation của reflective invocation. Vì thế có thể tạo đối số mới cho method.invoke, nhưng không được suy rằng nó chặn static/private/field access/constructor ở toàn ứng dụng.

### 14.3. Loại join point và quan hệ đến proceed

Method-call, method-execution, constructor, field-access có hợp đồng tiếp tục khác nhau. Ví dụ ghi giá trị field mới không có cùng return/argument contract như gọi method trả int. Nếu công cụ không hỗ trợ thay giá trị của một loại join point, không được dùng cú pháp của loại khác rồi mong nó có tác dụng.

## 15. Những lỗi thường gặp

**Lỗi 1 — Chỉ gán lại biến local rồi tưởng target nhận tham số mới.** Phải dùng cơ chế proceed/invoke nhận dữ liệu đã biến đổi, hoặc thừa nhận rằng chỉ có object mutable bị sửa side effect.

**Lỗi 2 — Thay đầu vào mà không kiểm tra signature.** Null cho primitive, sai thứ tự argument, nhầm overload hoặc kiểu không tương thích có thể gây exception runtime.

**Lỗi 3 — Đổi kết quả không tương thích return type.** Trả String cho method int hoặc null cho int làm hỏng hợp đồng.

**Lỗi 4 — Cộng phí hai lần vì nhiều advice trùng nhau.** Khi policy chạy ở nhiều biên, caller có thể nhận giá trị vượt kỳ vọng; phải chọn một chủ sở hữu concern và kiểm tra số lượt.

**Lỗi 5 — Bỏ qua target khi target có side effect bắt buộc.** Cache/short-circuit chỉ an toàn khi contract cho phép.

**Lỗi 6 — Retry thao tác không idempotent.** Một lần caller gọi có thể khiến target chạy nhiều lần; cần cơ chế chống trùng, giới hạn số lần và nhận diện lỗi có thể thử lại.

**Lỗi 7 — Nuốt mọi ngoại lệ rồi trả fallback.** Làm sai semantics thất bại và gây khó chẩn đoán.

**Lỗi 8 — Nhầm method trả Future với đã hoàn tất nghiệp vụ.** Giá trị tại return boundary có thể là một tác vụ còn chạy.

**Lỗi 9 — Không kiểm tra lời gọi trực tiếp bỏ qua proxy.** Một pointcut hay interceptor đúng ở biên này không chứng minh đã bao phủ mọi đường gọi khác.

**Lỗi 10 — Lạm dụng around cho mọi concern.** Quyền điều phối tăng độ khó đọc/kiểm thử; trước hoặc sau đơn giản có thể phù hợp hơn.

**Lỗi 11 — Dựa vào thứ tự aspect không được định nghĩa.** Khi hai advice đều đổi return, kết quả có thể phụ thuộc thứ tự wrapping; cần quy định precedence và kiểm thử.

**Lỗi 12 — Làm biến đổi dữ liệu nhạy cảm mà không kiểm soát.** Logging original input có thể làm lộ bí mật; biến đổi/redact phải có policy, coverage và audit rõ ràng.

## 16. Quy trình thiết kế an toàn một around advice thay dữ liệu

**Bước 1 — Viết hợp đồng gốc.** Method nhận input nào, trả output gì, ngoại lệ nào được phép, có side effect nào không?

**Bước 2 — Định nghĩa phép biến đổi.** Ví dụ: input bị giới hạn tại 5; output cộng 2; phải nêu rõ dữ liệu thay đổi có ý nghĩa gì.

**Bước 3 — Xác định loại join point.** Method call hay execution? Đối tượng nào thực thi? Phạm vi của policy gồm những caller và implementation nào?

**Bước 4 — Xác minh khả năng engine.** Có thể bind arguments không? Có thể gọi proceed với giá trị mới không? Return type và exception được kiểm tra ở đâu?

**Bước 5 — Định nghĩa số lần gọi tiếp tục.** Mặc định đúng một lần nếu chỉ transform. Nếu skip/retry, phải có điều kiện rõ.

**Bước 6 — Đảm bảo tương thích kiểu.** Primitive, reference, generic, varargs, null, overload và return type phải được kiểm thử.

**Bước 7 — Xử lý lỗi cụ thể.** Phân biệt lỗi advice, lỗi target và lỗi transform output.

**Bước 8 — Kiểm tra thứ tự nhiều aspect.** Dùng precedence hợp lệ nếu kết quả phụ thuộc lớp bọc.

**Bước 9 — Kiểm tra concurrency và dữ liệu.** Advice có trạng thái dùng chung không? Có mutate input object được caller giữ không? Có log bí mật không?

**Bước 10 — Kiểm chứng đường thật.** Test qua đúng proxy/weaving, cả ca khớp và không khớp pointcut, các đường bypass và self-invocation nếu có.

## 17. Ma trận kiểm thử đề xuất

| Kịch bản | Điều cần chứng minh |
|---|---|
| Input bình thường | Target nhận argument đúng; caller nhận result đúng |
| Input cần normalize | Target thật sự nhận giá trị mới, không chỉ log giá trị mới |
| Input bị từ chối | Target không được gọi, exception truyền đúng |
| Chính sách skip | Target không có side effect, return hợp lệ |
| Target throw | Advice không vô tình đổi lỗi thành thành công |
| Output transformation | Giá trị trả về kiểu đúng, không double transform |
| Primitive/null/generic | Không có lỗi boxing/cast ngoài dự kiến |
| Concurrent calls | Không rò dữ liệu giữa request, counter chính xác |
| Around advice lồng nhau | Thứ tự rõ và phép biến đổi đúng |
| Retry | Số lần target, tính idempotent và giới hạn retry đúng |
| Caller giữ target gốc | Biết chính xác khi nào interceptor bị bỏ qua |
| Lời gọi nội bộ | Xác minh giới hạn proxy hoặc mức bao phủ bytecode weaving |
| Asynchronous return | Biến đổi payload tại đúng thời điểm và bảo toàn lỗi |
| Pointcut không khớp | Không có biến đổi ngoài phạm vi |

Một assertion chỉ kiểm tra result chưa đủ. Ví dụ result = 52 có thể xuất phát từ việc target nhận 5 và fee +2; cũng có thể xuất phát từ một đường tính hoàn toàn khác. Nên ghi nhận **argument target thực sự nhận**, **số lần target chạy**, **giá trị target trả**, **giá trị caller nhận** và **exception**.

## 18. Bài tập vận dụng

**Bài 1.** Caller truyền 9. Advice tạo biến local effective = 5 nhưng gọi proceed không truyền giá trị mới trong mô hình yêu cầu proceed(args). Target nhận 9 hay 5?

**Đáp:** Target vẫn có thể nhận 9. Muốn target nhận 5 phải chuyển 5 đúng cách vào đường tiếp tục.

**Bài 2.** Target trả 50, around advice cộng 2. Một around bên ngoài nhân đôi kết quả. Tại sao có thể có 104 thay vì 102?

**Đáp:** Thứ tự wrapping khác nhau: (50 + 2) × 2 = 104, còn (50 × 2) + 2 = 102.

**Bài 3.** Advice không gọi proceed và trả cache value. Có chắc hành vi tương đương target không?

**Đáp:** Không. Nếu target có side effect, kiểm soát quyền hoặc dữ liệu đã đổi, short-circuit có thể phá hợp đồng.

**Bài 4.** Advice bắt mọi exception và trả 0. Điều gì nguy hiểm?

**Đáp:** Caller không biết thao tác thật đã thất bại; lỗi lập trình hoặc thất bại nghiêm trọng có thể bị che giấu như kết quả hợp lệ.

**Bài 5.** Method trả CompletionStage<Integer>. Around advice muốn cộng 2 vào giá trị trả thật. Có thể chỉ cast stage thành int rồi cộng không?

**Đáp:** Không. Phải biến đổi kết quả của stage theo cơ chế bất đồng bộ phù hợp và bảo toàn exception/cancellation.

**Bài 6.** Một aspect được triển khai bằng JDK dynamic proxy. Caller gọi target trực tiếp. Pointcut của proxy có đổi tham số trên đường đó không?

**Đáp:** Không. Đường gọi trực tiếp không qua interceptor của proxy.

**Bài 7.** Một trước advice mutate List và một around advice thay argument bằng List mới. Hai hành động có tác dụng như nhau với caller không?

**Đáp:** Không nhất thiết. Mutate List cũ có thể ảnh hưởng object caller giữ; thay reference trong proceed có thể dùng một List khác và giữ bản cũ không đổi.

**Bài 8.** Một around advice gọi proceed hai lần vì retry. Metric đếm target calls là 2 nhưng caller calls là 1. Có nhất thiết là bug?

**Đáp:** Không; đó có thể là kết quả đúng của retry, nhưng chỉ an toàn nếu policy cho phép và thao tác có biện pháp kiểm soát side effect/trùng lặp.

## 19. Sơ đồ tổng kết cơ chế

~~~text
                    POINTCUT MATCH?
                  ┌─────────┴─────────┐
                 Không                Có
                  │                   │
                  ▼                   ▼
              Chạy gốc          AROUND ADVICE
                                     │
                             nhận args gốc A
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
                  Throw             Skip          Transform A→A'
                    │                │                │
                    ▼                ▼                ▼
                  Lỗi             Return R'       Proceed(A')
                                                      │
                                                      ▼
                                               Target trả R
                                                      │
                                                      ▼
                                               Transform R→R'
                                                      │
                                                      ▼
                                                  Return R'
~~~

**Nguyên tắc cốt lõi:** ability to transform data belongs to the **around interception contract**, not merely to the fact that a variable named argument or result exists. Muốn thay dữ liệu một cách đúng đắn, cần biết **pointcut khớp ở đâu, engine có hỗ trợ proceed với dữ liệu mới không, target chạy bao nhiêu lần, hợp đồng kiểu và nghiệp vụ có còn đúng không, và caller thực sự thấy kết quả nào**. Nếu không có yêu cầu thay đổi hành vi, hãy giữ dữ liệu và lỗi gốc.

## Tài liệu đối chiếu

- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): ngữ nghĩa join point, advice, around và proceed trong một ngôn ngữ AOP có weaving.
- [Java Language Specification, Java SE 17 — Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html): truyền đối số, method invocation, đánh giá biểu thức và kiểu kết quả.
- [Java SE 17 — java.lang.reflect.Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): API phản xạ dùng để gọi target trong ví dụ Java.
- [Java SE 17 — java.lang.reflect.InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): cơ chế chặn lời gọi bằng JDK dynamic proxy.