# Bảo toàn kiểu trả về và ý nghĩa giá trị trả về

## 1. Vì sao “return đúng kiểu” vẫn chưa đủ?

Trong **Aspect-Oriented Programming (AOP)**, advice can thiệp vào các **join point** được pointcut chọn. Đặc biệt với **around advice**, cơ chế có thể cho phép advice nhận kết quả của `proceed()`, trả kết quả đó về caller, thay thế nó, hoặc không gọi continuation mà tự quyết định giá trị trả về.

Đây là quyền rất mạnh, nhưng cũng là nguồn lỗi khó nhận ra: một method có thể **trả về một giá trị đúng kiểu ở mức ngôn ngữ** nhưng **sai hợp đồng nghiệp vụ**. Ví dụ một method trả `int` để biểu diễn số lượng:

- Trả `0` có thể nghĩa là *không có bản ghi phù hợp*.
- Trả `-1` có thể là một mã trạng thái hợp lệ theo hợp đồng cũ.
- Trả `7` có thể là số phần tử thực.
- Ném exception có thể nghĩa là *không thể tính kết quả*, hoàn toàn khác với trả `0`.

Nếu một advice gặp lỗi rồi tự ý trả `0`, kiểu `int` vẫn hợp lệ nhưng caller có thể tưởng rằng phép tính thành công và kết quả thực là không có bản ghi. Một lời gọi được **che lỗi bằng giá trị hợp lệ về mặt cú pháp** có thể nguy hiểm hơn việc ném lỗi rõ ràng.

Bài này làm rõ hai câu hỏi tách biệt:

1. **Type correctness:** giá trị do advice trả có phù hợp với declared return type, runtime cast/unboxing, generic contract và abstraction của method không?
2. **Semantic correctness:** giá trị ấy có giữ đúng ý nghĩa success, absence, failure, identity, side effect và lifecycle mà caller được hứa không?

**Nguyên tắc trung tâm:** Một advice quan sát thuần túy nên **giữ nguyên result và error của target**, trừ khi chính sách biến đổi đã được định nghĩa và kiểm thử rõ. Một advice có chủ đích thay kết quả phải giữ cả **hợp đồng kiểu lẫn hợp đồng ý nghĩa**, không chỉ làm cho compiler hết báo lỗi.

### Mục tiêu học tập

Sau bài bạn có thể:

1. Phân biệt **declared return type**, kiểu runtime, generic type, dữ liệu được trả và ý nghĩa nghiệp vụ.
2. Phân tích around advice, after-returning, short-circuit, caching, fallback và retry trên kết quả trả về.
3. Hiểu các trường hợp **primitive, boxed type, `void`, `null`, `Optional<T>`, collection, generic, covariant return**.
4. Phân biệt **trả handle bất đồng bộ** với **task completion**, giữ semantics của `CompletionStage` và callback.
5. Nhận diện lỗi do **unboxing null**, **runtime cast**, **generic erasure**, **nuốt exception**, **đổi identity** và **làm mất chính sách lỗi**.
6. Hiểu giới hạn và hành vi của **JDK dynamic proxy/reflection**, nhưng không nhầm nó với mọi engine AOP.
7. Thiết kế quy tắc **transparency** cho advice quan sát và **explicit transformation** cho advice thay kết quả.
8. Chạy ví dụ Java 17 có đầu ra xác định để thấy primitive, `Optional`, `void`, future và các lỗi kiểu.
9. Xây ma trận kiểm thử bảo toàn result/error trên happy path, failure, cache hit, async và concurrency.

Bài thuộc AOP nói chung, không dựa vào cú pháp của một sản phẩm cụ thể. Cách một engine kiểm tra type hoặc cho phép `proceed`/return transformation có thể khác nhau.

## 2. Hợp đồng trả về thực sự gồm những lớp nào?

Một method có thể được mô tả ở nhiều tầng:

| Tầng hợp đồng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Declared type** | Chữ ký phương thức công bố kiểu gì? | `int count()`, `Optional<Item> find()`. |
| **Runtime representation** | Caller/proxy nhận object nào, có cast/unbox không? | `int` có thể được biểu diễn bằng `Integer` khi đi qua reflection. |
| **Nullability** | `null` có hợp lệ không? | `String` có thể là nullable theo hợp đồng; `Optional<T>` thường không nên là `null`. |
| **Generic shape** | Phần tử/giá trị bên trong có kiểu hợp lệ không? | `List<String>` không nên chứa `Integer`. |
| **Domain meaning** | Mỗi giá trị có ý nghĩa gì? | `0` = không có kết quả, không phải request thất bại. |
| **Identity/mutability** | Có phải cùng object/reference hoặc phải bảo toàn trạng thái không? | Stream, entity, iterator, mutable DTO. |
| **Side effects** | Target được chạy bao nhiêu lần, làm gì? | Advice cache có thể bỏ qua target; retry có thể chạy lại. |
| **Error contract** | Lỗi là exception đồng bộ hay được mã hóa trong result? | Throw, `Result.failure`, exceptional future. |
| **Temporal contract** | Khi nào result “sẵn sàng”? | Future return trước khi task complete. |
| **Ownership/lifecycle** | Ai đóng, hủy hoặc giải phóng? | Stream, cursor, publisher, resource handle. |

Một advice chỉ giữ được **declared type** chưa chắc giữ được các tầng còn lại.

### 2.1. Ví dụ: cùng kiểu `boolean`, nghĩa khác nhau

Một method `boolean transfer(...)` có thể quy định:
- `true`: chuyển thành công;
- `false`: yêu cầu được xử lý nhưng không đủ điều kiện;
- exception: hệ thống chưa biết liệu thao tác có commit hay không.

Nếu advice bắt mọi lỗi rồi trả `false`, nó đã đánh đồng **bị từ chối có chủ đích** với **hệ thống không thể xác nhận kết quả**. Compiler không phát hiện sai lệch ngữ nghĩa này.

### 2.2. Ví dụ: cùng kiểu `List<Item>`, số lượng và thứ tự khác nhau

Advice trả `Collections.emptyList()` thay cho một danh sách có dữ liệu: đúng kiểu tham chiếu nhưng sai nội dung. Advice sắp xếp lại danh sách: phần tử có thể vẫn đúng nhưng hợp đồng “giữ thứ tự nhập” bị vi phạm. Advice trả **cùng reference** thay vì bản sao hoặc ngược lại có thể ảnh hưởng caller khi collection mutable.

### 2.3. Không phải mọi biến đổi đều sai

Một **mapping/normalization advice** có thể được thiết kế để:
- Loại dữ liệu nhạy cảm theo chính sách;
- Chuyển một kết quả thành dạng chuẩn;
- Trả dữ liệu từ cache;
- Áp quy tắc fallback rõ ràng;
- Bọc kết quả thành một abstraction khác nếu method signature cho phép.

Nhưng ở đó, **thay đổi result chính là hành vi có chủ đích**, cần được công bố, định nghĩa thứ tự và kiểm thử, không được gọi nhầm là “advice chỉ quan sát”.

## 3. Before, after và around khác nhau ở quyền xử lý return

### 3.1. Before advice

Before advice chạy trước phần tiếp theo. Trong một mô hình đơn giản, nó **không trực tiếp nhận result của target đã hoàn thành**, bởi result chưa tồn tại. Nó có thể chuẩn bị context, kiểm tra điều kiện hoặc ném lỗi, tùy khả năng công cụ.

Nếu before advice ném lỗi trước `proceed`, target có thể chưa chạy. Đó là thay đổi **execution contract**, dù không trực tiếp đổi kiểu của một giá trị trả về.

### 3.2. After-returning advice

After-returning quan sát một lần kết thúc bình thường. Nó có thể được dùng để log kiểu, tính metric hoặc phân loại success. Tuy nhiên, một số AOP API chỉ **cung cấp quyền quan sát**, không cho phép thay result chỉ bằng cách gán lại parameter nhận được. Một engine khác có thể hỗ trợ transformation rõ ràng.

**Không suy:** “đổi biến `result` bên trong after-returning thì caller chắc chắn nhận giá trị mới”. Nếu muốn thay kết quả, phải sử dụng đúng abstraction mà engine bảo đảm có tác động lên caller, và test thực tế.

### 3.3. After-throwing advice

Nếu target ném exception đồng bộ, after-throwing có thể quan sát exception thoát khỏi join point. Nhưng nếu around advice phía trong đã bắt lỗi rồi trả fallback, tầng ngoài thấy **normal return**, không tự thấy lỗi gốc.

Khi method trả future, một exception được báo **bên trong future ở completion về sau** cũng không tự trở thành exception đồng bộ thoát khỏi method invocation.

### 3.4. Around advice

Một around advice có thể mô tả logic:

~~~text
around:
    before()
    try:
        original = proceed()
        observeResult(original)
        return original
    catch failure:
        observeError(failure)
        throw sameFailure
    finally:
        cleanup()
~~~

Đây là **giả mã**, không phải cú pháp chung. Nó minh họa **transparent observer**: result được trả nguyên, lỗi được ném lại, cleanup không cố tình biến đổi outcome.

Nếu thay `return original` bằng `return newValue`, ta phải trả lời:
- `newValue` có hợp lệ với declared return type?
- `null` có hợp lệ với caller?
- Tính bất biến/thứ tự/identity có đổi không?
- Có làm mất lỗi hoặc tạo false success không?
- Nếu target trả stream/future, có giữ lifecycle và cancellation không?
- Caller đã được thông báo việc transform như một phần hợp đồng chưa?

### 3.5. `proceed()` không phải phép bảo toàn ngữ nghĩa tự động

Một số around advice **có thể không gọi `proceed`** (cache hit, rate limit, fallback) hoặc gọi nhiều lần (retry, nếu engine cho phép). Một advice khác có thể sửa arguments trước khi gọi tiếp. Vì vậy ngay cả khi giá trị cuối đúng kiểu, **số lần target thực thi và side effects** cũng có thể thay đổi.

Một advice retry không được giả định mọi method idempotent. Hai lần gọi có thể tạo hai giao dịch hoặc hai thông báo dù cuối cùng trả về cùng một `String` thành công.

## 4. Primitive và boxed type: đúng giá trị, đúng cách biểu diễn

Java có kiểu nguyên thủy như `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `char`. Reflection/proxy thường truyền các giá trị primitive thông qua **wrapper objects** như `Integer` hoặc `Boolean` tại tầng `Object`.

Với method:

~~~java
interface Counter {
    int getCount();
}
~~~

Một `InvocationHandler` của **JDK dynamic proxy** có thể trả `Integer.valueOf(5)` để biểu diễn `int 5`. Generated proxy thực hiện cast/unboxing phù hợp khi trả về caller. Nhưng:

- Trả `null` cho method `int` làm quá trình unboxing thất bại với `NullPointerException`.
- Trả `String "5"` cho method `int` không tự parse thành số; có thể gây `ClassCastException`.
- Trả một wrapper **không đúng kiểu** như `Long` cho method `int` cũng không tự được coi là phép đổi kiểu primitive hợp lệ ở boundary JDK proxy.
- Trả `Integer.valueOf(0)` là **hợp lệ về kiểu**, nhưng `0` có đúng ý nghĩa không vẫn do domain contract quyết định.

Các điểm trên được nêu chính xác trong phạm vi **JDK dynamic proxy**. Một bytecode weaver khác có thể kiểm tra type tại compile time hoặc từ chối một transformation theo cơ chế khác; không suy rằng mọi engine đều báo đúng loại exception ở cùng chỗ.

### 4.1. Cẩn thận với kiểu số

`int` và `long` khác nhau về miền giá trị. Nếu advice tự chuyển `long` thành `int`, dữ liệu có thể tràn/thu hẹp. Nếu advice dùng `double` để thay `BigDecimal`, mất độ chính xác có thể làm sai nghiệp vụ tài chính. Chữ ký compile-time phù hợp không tự bảo đảm precision, rounding và unit semantics.

### 4.2. `boolean` không đồng nghĩa “không throw”

Trả `false` thay exception có thể đánh đồng một kết quả hợp lệ với việc hệ thống thất bại. Nếu API định nghĩa một sentinel như `-1`, không được đoán sentinel mới từ primitive default chỉ vì advice không biết trả gì.

### 4.3. Giữ nguyên `0`, `false` và `-1` khi quan sát thuần túy

Một advice metrics có thể cần phân biệt:
- Target trả `0`: bình thường, có kết quả bằng 0;
- Target trả `-1`: bình thường nếu domain có sentinel đó;
- Target ném lỗi: không có giá trị trả về bình thường.

Không tự đặt cùng nhãn “error” cho mọi số không dương, trừ khi hợp đồng method nói rõ.

## 5. `void`: không trả giá trị nghiệp vụ vẫn có hợp đồng

Một method `void notifyUser(...)` **không cung cấp giá trị return cho caller**. Nhưng nó có thể có side effects: ghi dữ liệu, phát event, gửi email hoặc thay đổi trạng thái.

Trong JDK reflection, `Method.invoke` trả `null` khi method trả `void` và hoàn tất bình thường. Trong JDK dynamic proxy, `InvocationHandler` có kiểu `Object invoke(...)`; trả `null` cho `void` là cách tự nhiên.

**Không được suy:** `null` trong tầng reflection có nghĩa target “trả một dữ liệu null”. Với `void`, caller không nhận bất kỳ giá trị nghiệp vụ nào để đọc.

### 5.1. `void` vẫn có success/failure

Nếu method `void save()` ném `IOException`, around advice quan sát cần ném lại đúng lỗi theo hợp đồng. Nếu advice nuốt lỗi và return bình thường, caller có thể tưởng side effect đã thành công dù thực tế không hoàn tất.

### 5.2. Không nhầm “không có result” với “không có side effect”

Một cache advice không thể mặc định bỏ qua một method `void` và trả ngay chỉ vì không có result cần cache. Target có thể đang thực hiện side effect quan trọng; skip là hành vi nghiệp vụ, không phải phép tối ưu an toàn mặc định.

## 6. Reference type và `null`: có thể hợp kiểu nhưng vi phạm contract

Với kiểu tham chiếu `String`, `Customer`, `List<Item>`, `Optional<Item>` hay `CompletionStage<T>`, `null` là một reference value có thể đi qua runtime cast mà không gây `ClassCastException` ngay lập tức.

Điều này **không chứng minh null hợp lệ về mặt API**.

Ví dụ một API:

~~~java
Optional<String> find(String id);
~~~

Có thể công bố:

> “Luôn trả một `Optional` không-null; `Optional.empty()` nghĩa là không tìm thấy.”

Nếu advice khi cache miss trả `null`, lời gọi **vẫn có thể qua boundary kiểu** vì `Optional` là reference type. Nhưng caller sau đó gọi `result.isPresent()` sẽ gặp `NullPointerException` hoặc phải viết phòng vệ trái với hợp đồng. `null` và `Optional.empty()` không tương đương.

### 6.1. `Optional.empty()` không phải error

Một `Optional.empty()` thường biểu diễn **không có giá trị thành công** theo API; một exception biểu diễn **không thực hiện được việc tìm kiếm** có thể là trạng thái khác. Advice không nên chuyển mọi exception thành empty chỉ vì method trả Optional.

Ví dụ việc tra tài khoản:
- `Optional.empty()`: tài khoản không tồn tại.
- Exception từ storage: không thể xác định tồn tại hay không.
- `Optional.of(account)`: có tài khoản hợp lệ.

Che lỗi storage bằng empty có thể dẫn đến quyết định sai như “tạo tài khoản mới vì chưa tồn tại”.

### 6.2. Nullable contract phải được ghi rõ

Một method `String title()` có thể cho phép `null` nếu không có tên, hoặc có thể hứa không-null. Advice muốn biến đổi dữ liệu phải biết điều đó; annotation nullability (nếu có) cũng chỉ là một phần của hợp đồng, cần được công cụ/QA thật sự sử dụng.

### 6.3. `null` có thể là dữ liệu hợp lệ trong một abstraction

Không nên cực đoan “không bao giờ trả null”. Với API legacy, `null` có thể là sentinel được công bố. Một advice transparent observer phải **giữ nguyên null hợp lệ**; tự thay thành chuỗi rỗng hoặc object mặc định cũng là đổi semantics.

## 7. Generics, type erasure và kiểu phần tử

Java generics thường có **type erasure** tại runtime. Method:

~~~java
List<String> names();
~~~

có thể bị một around advice/reflective interceptor trả một `List<Integer>` ở tầng raw `Object` mà không có cast kiểm tra từng phần tử ngay tại boundary. Caller sau đó đọc phần tử dưới giả định `String` mới gặp lỗi.

~~~java
// Minh họa không độc lập.
@SuppressWarnings({"rawtypes", "unchecked"})
List<String> incorrect = (List) List.of(123);
String first = incorrect.get(0); // có thể ClassCastException lúc đọc
~~~

Đoạn này chỉ minh họa cơ chế erasure và unchecked conversion, **không phải khuyến nghị** dùng raw types. Sự tồn tại của generics trong chữ ký không bảo đảm một proxy runtime trả object đúng nội dung nếu advice cố ý dùng cast không an toàn.

### 7.1. Generic container có nhiều tầng cần bảo toàn

Với `Map<String,List<Order>>`, hợp đồng bao gồm:
- Key thực là `String`.
- Values chứa `List<Order>`.
- Quy tắc null key/value nếu được cho phép.
- Thứ tự duyệt nếu API hứa.
- Mutability/immutability.
- Khả năng serialization.
- Các invariant của `Order`.

Không thể chứng minh đầy đủ bằng một `instanceof Map` duy nhất.

### 7.2. Type parameters phụ thuộc context

Một method generic như `<T> T decode(byte[], Class<T>)` cần duy trì quan hệ giữa đối số `Class<T>` và result `T`. Nếu advice trả object sai kiểu từ cache do dùng key chỉ theo bytes mà bỏ qua requested type, lỗi có thể xuất hiện về sau ở caller.

### 7.3. Covariant return types

Java cho phép override method với **return type là subtype hợp lệ**. Ví dụ interface công bố `Number read()`, implementation trả `Integer`. Một advice có thể quan sát result dưới kiểu `Number` nhưng nếu lời gọi thật yêu cầu một API trả `Integer` thì không được thay bằng `Double` chỉ vì cả hai đều là `Number`.

Khi viết interceptor/reflection matcher, chú ý chữ ký method quan sát, bridge methods và kiểu trả về thực; type matching của engine phụ thuộc loại join point và declaration mà nó nhìn thấy.

## 8. Identity, equality, mutability và ownership

Ngay cả khi two values có cùng kiểu và `equals()`, caller vẫn có thể yêu cầu điều kiện mạnh hơn.

### 8.1. Identity có thể là một phần của hợp đồng

Ví dụ method `getBuffer()` trả một **buffer dùng chung do owner quản lý**. Advice tạo một buffer mới cùng nội dung thay vì trả reference gốc có thể khiến code cần identity hoặc mutation sharing bị sai.

Ngược lại, API có thể yêu cầu **defensive copy** để caller không sửa state nội bộ. Advice thay result thành reference gốc sẽ phá tính cách ly.

**Câu hỏi cần kiểm tra:** caller hứa nhận cùng instance, một bản sao độc lập, một immutable view hay chỉ một giá trị tương đương?

### 8.2. Collection rỗng cũng có thể khác nhau

`List.of()` và `new ArrayList<>()` đều là `List` rỗng, nhưng mutability khác nhau. Nếu caller được phép thêm phần tử, thay một mutable list bằng immutable list có thể tạo `UnsupportedOperationException` sau khi method return.

### 8.3. Không lén sửa object của target trong một “observer”

Nếu advice log result rồi đồng thời gọi `result.clear()` hoặc mutate một DTO, dù advice cuối cùng `return result`, nghĩa của result đã đổi. “Trả đúng reference” **không đủ** để chứng minh trong suốt nếu advice làm biến đổi trạng thái của object ấy.

### 8.4. Resource ownership

Một result như `InputStream`, cursor, iterator hoặc file handle có thể cần caller đóng. Advice không nên tự đóng trong `finally` ngay sau khi target return nếu caller còn cần đọc; cũng không nên giữ result/reference vô hạn trong logger/cache. Lifetime và ownership là một phần của hợp đồng trả về.

## 9. Proxy và reflection: nơi type error thật sự xảy ra

Với **JDK dynamic proxy**, một `InvocationHandler` thường nhận:
- Object proxy.
- `Method` đại diện invocation.
- Mảng arguments.
- Kết quả ở dạng `Object` mà handler phải trả.

Nhiều interface methods có primitive return types. Generated proxy kiểm tra/cast/unbox kết quả `Object` theo declared return type khi trả cho caller.

Mô hình khái niệm:

~~~text
caller calls proxy.number()
    |
    v
InvocationHandler.invoke()
    |
    v
reflection calls target.number()
    |
    +--> target returns int 7
             |
             v
          Method.invoke returns Integer(7)
             |
             v
          handler returns Integer(7)
             |
             v
          proxy unboxes to int 7
             |
             v
          caller sees 7
~~~

### 9.1. Reflective invocation bọc exception

Khi `Method.invoke(target,args)` khiến target ném exception, reflection thường ném `InvocationTargetException`, chứa exception gốc qua `getCause()` hoặc `getTargetException()`. Một handler quan sát trung thực thường **gỡ wrapper reflection** và truyền lại lỗi gốc theo quy định interface/proxy.

Nếu handler tự ý ném một checked exception **không được khai báo** trong throws clause của interface method, JDK proxy có thể bọc bằng `UndeclaredThrowableException`. Đây là một phần của **exception contract**; ví dụ dưới chỉ dùng unchecked exceptions để tránh rối phần checked throws.

### 9.2. Sai kiểu của handler có thể bị phát hiện sau khi handler return

Nếu handler trả `"7"` cho method `int number()`, handler tự nó có thể hoàn tất bình thường, nhưng generated proxy gặp cast không phù hợp. Trong ví dụ Java, caller bắt `ClassCastException`.

Nếu handler trả `null`, generated proxy unbox thành primitive thất bại; caller bắt `NullPointerException`.

Nếu handler trả `null` cho `Optional<String>`, runtime cast có thể thành công vì null là một reference hợp lệ về mặt JVM, nhưng **null phá vỡ semantic contract** API mong đợi một Optional object.

### 9.3. Không đồng nhất JDK proxy với mọi cơ chế AOP

Một weaver làm việc tại source/bytecode có thể dùng typed advice API, kiểm tra lúc compile/load, chèn cast hoặc tạo bridge khác. Nếu công cụ cấm một loại kết quả, lỗi có thể xuất hiện sớm hơn. Nguyên tắc chung vẫn là **phải giữ kiểu và hợp đồng mà caller được hứa**, nhưng hình thức kiểm tra và loại lỗi phải dựa trên engine thật.

## 10. Java 17 runnable: bảo toàn và vi phạm hợp đồng ở proxy boundary

Chương trình sau dùng một interface có bốn kiểu return:

- `int number(String)`: primitive, `0` là giá trị thành công hợp lệ.
- `Optional<String> find(String)`: luôn trả `Optional` không-null, empty biểu diễn không tìm thấy.
- `CompletionStage<String> loadAsync(String)`: trả một handle, outcome có thể xuất hiện sau method return.
- `void emit(String)`: không có result nghiệp vụ, nhưng target có side effect.

`transparent` handler gọi đúng target, log giá trị/kiểu, đăng ký quan sát async mà **trả stage gốc**, và gỡ `InvocationTargetException` để giữ lỗi đồng bộ. Cuối chương trình dùng ba proxy cố ý sai để thấy `null` cho primitive, sai wrapper type và `null` cho `Optional`.

Tạo file **`AdviceReturnContractDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

public class AdviceReturnContractDemo {
    interface Service {
        int number(String key);
        Optional<String> find(String key);
        CompletionStage<String> loadAsync(String key);
        void emit(String event);
    }

    static final class RealService implements Service {
        private CompletableFuture<String> pending;

        @Override
        public int number(String key) {
            System.out.println("TARGET number " + key);
            if ("BAD".equals(key)) {
                throw new IllegalArgumentException("illegal key");
            }
            return "ZERO".equals(key) ? 0 : 7;
        }

        @Override
        public Optional<String> find(String key) {
            System.out.println("TARGET find " + key);
            if ("MISSING".equals(key)) {
                return Optional.empty();
            }
            return Optional.of("DATA:" + key);
        }

        @Override
        public CompletionStage<String> loadAsync(String key) {
            System.out.println("TARGET loadAsync " + key);
            pending = new CompletableFuture<>();
            return pending;
        }

        @Override
        public void emit(String event) {
            System.out.println("TARGET emit " + event);
        }

        CompletableFuture<String> pending() {
            return pending;
        }

        void completeSuccess(String value) {
            CompletableFuture<String> stage = pending;
            pending = null;
            stage.complete(value);
        }

        void completeFailure() {
            CompletableFuture<String> stage = pending;
            pending = null;
            stage.completeExceptionally(
                    new IllegalStateException("remote failed"));
        }
    }

    static Service transparent(Service target) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                (proxy, method, arguments) -> {
                    System.out.println("ADVICE enter " + method.getName());
                    try {
                        Object value = method.invoke(target, arguments);

                        if (value instanceof CompletionStage<?> stage) {
                            stage.whenComplete((result, failure) -> {
                                if (failure == null) {
                                    System.out.println(
                                            "ADVICE async success " + result);
                                } else {
                                    System.out.println(
                                            "ADVICE async failure "
                                            + failure.getClass().getSimpleName());
                                }
                            });
                        }

                        String type = method.getReturnType() == void.class
                                ? "void"
                                : value == null
                                    ? "null"
                                    : value.getClass().getSimpleName();
                        System.out.println("ADVICE return "
                                + method.getName() + " type=" + type);
                        return value;
                    } catch (InvocationTargetException wrapped) {
                        Throwable cause = wrapped.getCause();
                        System.out.println("ADVICE throw "
                                + method.getName() + " "
                                + cause.getClass().getSimpleName());
                        throw cause;
                    }
                }
        );
    }

    static Service alwaysReturn(Object result) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                (proxy, method, args) -> result
        );
    }

    public static void main(String[] args) {
        RealService target = new RealService();
        Service service = transparent(target);

        System.out.println("CALLER number=" + service.number("ZERO"));
        System.out.println("CALLER missing=" + service.find("MISSING"));
        System.out.println("CALLER found=" + service.find("YES"));

        service.emit("EVT");

        CompletionStage<String> task = service.loadAsync("JOB");
        System.out.println("CALLER original stage="
                + (task == target.pending()));
        target.completeSuccess("READY");
        System.out.println("CALLER async result="
                + task.toCompletableFuture().join());

        CompletionStage<String> failed = service.loadAsync("ASYNC_BAD");
        target.completeFailure();
        try {
            failed.toCompletableFuture().join();
        } catch (CompletionException error) {
            System.out.println("CALLER async failure cause="
                    + error.getCause().getClass().getSimpleName());
        }

        try {
            service.number("BAD");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER sync failure=" + error.getMessage());
        }

        try {
            alwaysReturn(null).number("ZERO");
        } catch (NullPointerException error) {
            System.out.println("BAD primitive=null -> NullPointerException");
        }

        try {
            alwaysReturn("not-an-integer").number("ZERO");
        } catch (ClassCastException error) {
            System.out.println("BAD wrong type -> ClassCastException");
        }

        System.out.println("BAD Optional returned null="
                + (alwaysReturn(null).find("MISSING") == null));
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac AdviceReturnContractDemo.java
java AdviceReturnContractDemo
~~~

**Stdout kỳ vọng:**

~~~text
ADVICE enter number
TARGET number ZERO
ADVICE return number type=Integer
CALLER number=0
ADVICE enter find
TARGET find MISSING
ADVICE return find type=Optional
CALLER missing=Optional.empty
ADVICE enter find
TARGET find YES
ADVICE return find type=Optional
CALLER found=Optional[DATA:YES]
ADVICE enter emit
TARGET emit EVT
ADVICE return emit type=void
ADVICE enter loadAsync
TARGET loadAsync JOB
ADVICE return loadAsync type=CompletableFuture
CALLER original stage=true
ADVICE async success READY
CALLER async result=READY
ADVICE enter loadAsync
TARGET loadAsync ASYNC_BAD
ADVICE return loadAsync type=CompletableFuture
ADVICE async failure IllegalStateException
CALLER async failure cause=IllegalStateException
ADVICE enter number
TARGET number BAD
ADVICE throw number IllegalArgumentException
CALLER sync failure=illegal key
BAD primitive=null -> NullPointerException
BAD wrong type -> ClassCastException
BAD Optional returned null=true
~~~

### 10.1. Đường `int number("ZERO")`

Target trả **`int 0`**. Vì `Method.invoke` biểu diễn primitive qua wrapper ở tầng `Object`, handler ghi `Integer`, rồi trả lại đúng object ấy. Proxy unbox thành `int 0`; caller in `CALLER number=0`.

**Điều được bảo toàn:** số 0 không bị coi là “không có result” hoặc lỗi. Advice không ép thành `null` và không tự thay `0` bằng một số khác.

### 10.2. Đường `Optional.empty()`

Target trả một object `Optional.empty()`, handler thấy kiểu runtime `Optional` rồi trả nguyên. Caller nhận đúng abstraction để biểu diễn absence.

Với `find("YES")`, result là `Optional[DATA:YES]`. **Hai kết quả đều là return bình thường**, không đồng nghĩa một cái thành công và cái còn lại thất bại. Cách diễn giải absence/failure thuộc hợp đồng method.

### 10.3. Đường `void emit("EVT")`

Target in `TARGET emit EVT`, tức đã thực thi side effect minh họa. Reflection trả `null` cho method `void`, nhưng handler in `type=void` dựa vào **declared return type**, không gắn nhầm nhãn “target trả null như một giá trị nghiệp vụ”.

### 10.4. Đường `CompletionStage` thành công

`loadAsync` tạo `CompletableFuture` còn pending. Handler đăng ký `whenComplete` **chỉ để quan sát** và trả `value` gốc. Caller so sánh identity `task == target.pending()` và in `true`. Lúc `target.completeSuccess("READY")`, callback log `ADVICE async success READY`, sau đó caller `join()` đọc kết quả.

Trong demo tuần tự, callback không dùng hậu tố `Async` và completion do `main` kích hoạt nên stdout có thứ tự nêu trên. Không suy ra mọi callback `whenComplete` trong ứng dụng đa luồng luôn chạy trên caller thread hoặc luôn sắp trước một log ở thread khác.

### 10.5. Đường `CompletionStage` thất bại

`loadAsync("ASYNC_BAD")` **return bình thường** một `CompletableFuture`. Exception xuất hiện khi `completeExceptionally` được gọi. Handler callback ghi failure, còn caller bắt `CompletionException` lúc `join()`.

Đây **không** phải một synchronous throw của method `loadAsync`. Around advice chỉ catch `InvocationTargetException` của `Method.invoke`; nó không tự biến completion failure thành lỗi ném trước return.

### 10.6. Đường lỗi đồng bộ của `number("BAD")`

Target ném `IllegalArgumentException`. Reflection bọc lỗi trong `InvocationTargetException`. Handler gỡ `getCause()`, log `ADVICE throw number IllegalArgumentException` và ném lại cause. Caller thấy `IllegalArgumentException` kèm message `illegal key`.

Đây là **bảo toàn exception contract**, cũng là một phần của hợp đồng return/outcome. Nếu handler tự ý return `0`, caller sẽ mất khả năng phân biệt lỗi này với `number("ZERO")` hợp lệ.

### 10.7. Ba advice cố ý sai

**Sai primitive null:** handler cố ý trả `null` cho `int`; proxy unboxing gặp `NullPointerException`.

**Sai primitive wrapper type:** handler trả `String` cho `int`; generated proxy cast thất bại với `ClassCastException`.

**Sai `Optional` semantics:** handler trả `null` cho `Optional<String>`. Không có cast error ngay tại boundary vì đây là reference type, nên chương trình chứng minh `BAD Optional returned null=true`. Đây vẫn là **vi phạm hợp đồng** nếu API hứa luôn trả `Optional` không-null.

**Lưu ý giới hạn:** các bad proxies trong demo không gọi target, nên ngoài lỗi kiểu, chúng còn thay đổi side-effect semantics. Chúng được tạo tách biệt chỉ để minh họa vi phạm return contract.

### 10.8. Giới hạn của mã runnable

- `RealService.pending` chỉ phục vụ **một future pending tại một thời điểm** trong demo tuần tự. Không dùng cấu trúc đó làm job registry production concurrent.
- Các callbacks chỉ log, chưa có chính sách error handling cho chính instrumentation.
- Handler không xử lý chi tiết `equals`, `hashCode`, `toString` và các default interface methods; chỉ dùng bốn methods đã công bố.
- Không có bytecode weaving, pointcut DSL, cache/retry implementation hay kiểm chứng dynamic class loading.
- Code dùng `Optional<String>`, `CompletableFuture` và reflection theo đúng API Java 17, nhưng không giả định một engine AOP nào có cùng thứ tự advice hay behavior riêng.
- Mục đích ví dụ là phân biệt **runtime type safety** với **semantic safety**, không chứng minh GC hoặc thread-safe state.

## 11. Short-circuit, cache hit và chính sách trả kết quả

Một around advice có thể **không gọi `proceed`** khi cache hit:

~~~text
around:
    key = makeKey(arguments)
    if cache.contains(key):
        return cache.get(key)
    value = proceed()
    cache.put(key, value)
    return value
~~~

Đây là giả mã. Dù cache trả về một object đúng kiểu, vẫn phải xem:

1. Cache key có chứa đủ arguments, type information, tenant và security scope không?
2. Giá trị đã stale chưa?
3. Nếu original target return `null` hợp lệ, cache có phân biệt “không có entry” với “entry có null” không?
4. Nếu target trả mutable object, caller có làm thay đổi cached instance không?
5. Nếu target có side effects, bỏ qua target có được cho phép không?
6. Nếu result là stream/future/iterator sống theo invocation, cache handle gốc có an toàn không?
7. Cache có phân biệt success value với exception hoặc failure state không?
8. Nếu authorization advice nằm bên trong cache và cache short-circuit, có tạo đường bỏ qua policy không?

### 11.1. Không cache lỗi như giá trị thành công khi chưa có chính sách

Một API phân biệt `Optional.empty()` với exception lỗi storage; nếu advice cache ghi empty khi gặp exception, những lần sau sẽ thấy “không tồn tại” dù hệ thống chỉ vừa không truy cập được storage. Nếu muốn negative caching, phải định nghĩa rõ trạng thái nào được phép cache, TTL và invalidation.

### 11.2. Không cache resource handle tùy tiện

Một `InputStream` có thể đã được caller đọc hết/đóng; trả lại cùng stream instance từ cache cho caller tiếp theo thường phá lifecycle. Tương tự, một future đã failed không tự trở thành một task mới chỉ vì caller gọi lại method; caching future có thể cố tình chia sẻ một computation, nhưng phải là hành vi được thiết kế.

### 11.3. Identity và key equality

Nếu API hứa singleton-like identity cho một entity, cache có thể chủ đích giữ cùng instance. Nếu API hứa bản sao tách biệt cho mỗi caller, trả cùng mutable instance là sai dù nội dung ban đầu giống nhau.

## 12. Fallback và chuyển đổi lỗi thành giá trị

Một advice fallback có thể thay exception bằng result. Đó là một **thay đổi hợp đồng**, cần được biện minh.

Ví dụ ba mức:

~~~text
(1) Target returns 0
    -> successful outcome value 0

(2) Target throws IllegalArgumentException
    -> synchronous exceptional outcome

(3) Target returns CompletionStage that later fails
    -> normal method return of handle;
       exceptional completion later
~~~

Nếu fallback đưa (2) hoặc (3) về `0`, caller mất thông tin khác biệt, trừ khi API **cố ý định nghĩa** fail-closed/default result và đã ghi nhận error bằng kênh khác.

### 12.1. Phân loại failure trước khi fallback

Một fallback hợp lý có thể áp riêng cho:
- Lỗi tạm thời từ dependency có kết quả dự phòng được công bố.
- Cache stale được phép dùng trong một khoảng.
- Trường hợp giá trị không có nhưng API rõ ràng coi đó là absence hợp lệ.

Nó không nên ngẫu nhiên bắt mọi `Throwable` và trả default. Những lỗi lập trình, hỏng invariant, authentication failures hoặc commit ambiguities có semantics riêng.

### 12.2. Giữ nguyên cause khi ném lại

Nếu advice chỉ log exception rồi rethrow, ưu tiên giữ **type, cause và stack information** theo hợp đồng. Nếu chính sách phải chuyển exception, tài liệu hóa mapping và giữ cause khi phù hợp. Tránh biến một lỗi domain có thể xử lý thành một unchecked generic error vô nghĩa.

### 12.3. Checked exceptions qua proxy

Một interface method khai báo `throws IOException` không đồng nghĩa handler có thể tự ném **bất kỳ checked exception** nào và caller luôn nhận trực tiếp đúng loại ấy. Với JDK dynamic proxy, checked exception không khai báo/không hợp lệ qua method signature có thể được bọc trong `UndeclaredThrowableException`. Cần test thực tế nếu advice biến đổi checked errors.

## 13. Retry: cuối cùng trả đúng giá trị vẫn có thể sai side effects

Giả sử advice retry gọi `proceed()` ba lần cho cùng logical operation và cuối cùng trả `"OK"`. Kiểu `String` hợp lệ, giá trị cuối trông đúng, nhưng có thể đã:
- Gửi ba thông báo.
- Ghi ba bản ghi.
- Tạo nhiều giao dịch.
- Thực hiện một remote action đã commit trước khi response timeout.

Do đó **return contract bao gồm quan hệ giữa result và những tác động được phép**. Chỉ nên retry khi xác định idempotency, attempt boundary, timeout tổng, backoff, loại lỗi được phép thử lại và tác vụ nền có thực sự được hủy hay không.

### 13.1. Số lượng advice calls thay đổi theo thứ tự

Với chuỗi:

~~~text
Retry(
    MetricsAttempt(
        Target
    )
)
~~~

MetricsAttempt có thể chạy **mỗi attempt**. Với:

~~~text
MetricsLogical(
    Retry(
        Target
    )
)
~~~

MetricsLogical có thể chạy **một lần cho logical operation**, nếu engine cho phép Retry gọi continuation nhiều lần. Lỗi nội bộ đã được Retry xử lý có thể không thoát ra MetricsLogical; không gán nhầm một success cuối với zero attempt failures.

### 13.2. Retry future khác retry synchronous throw

Nếu method trả một future trước khi tác vụ lỗi, catch quanh `proceed()` không tự nhận completion failure. Để retry logical async work, cần compose theo future completion, tạo **attempt mới** có chủ đích, không chỉ `join()` lại cùng future đã fail.

## 14. `CompletionStage`: kiểu handle không nói hết outcome

Một method:

~~~java
CompletionStage<Receipt> submitAsync(Order order);
~~~

khai báo trả `CompletionStage<Receipt>`. Hợp đồng thường tách hai giai đoạn:

1. **Invocation outcome:** method có return một stage hay ném lỗi ngay?
2. **Task outcome:** stage hoàn tất success với `Receipt`, exceptionally, cancellation hoặc timeout?

Một handler around trả **đúng stage object** vẫn có thể là một transparent observer ở method boundary. Nếu muốn quan sát task outcome, nó cần completion hook tương ứng.

### 14.1. Stage gốc và stage phụ thuộc không luôn tương đương

Trong Java:

~~~java
// Mã minh họa: giả định stage và observe(...) đã được định nghĩa.
CompletionStage<Receipt> original = stage;
original.whenComplete((value, failure) -> observe(value, failure));
return original;
~~~

Trong ví dụ này, observer đăng ký một callback và **trả stage gốc**. Method `whenComplete` lại **tạo một dependent stage**; code bỏ qua dependent stage trong minh họa.

Nếu đổi thành:

~~~java
// Mã minh họa: return một dependent stage.
return stage.whenComplete((value, failure) -> observe(value, failure));
~~~

caller nhận **dependent stage**, không phải original. Nếu `observe` ném lỗi, outcome của dependent stage có thể thay đổi theo hợp đồng `whenComplete`. Đây không chỉ là chuyện kiểu vì cả hai cùng là `CompletionStage<Receipt>`; **identity và completion semantics có thể khác**.

### 14.2. `handle` có thể chuyển failure thành success

~~~java
// Mã minh họa.
return stage.handle((value, failure) -> {
    if (failure != null) {
        return fallbackReceipt;
    }
    return value;
});
~~~

Đây là một transformation có chủ đích. Nếu nghiệp vụ cho phép fallback, cần công bố nghĩa của `fallbackReceipt`; nếu không, nó che failure. Ngoài ra, generic inference phải bảo đảm result type và mọi code paths cùng thuộc hợp đồng `Receipt`.

### 14.3. Không block để “biến async thành sync” khi chưa được phép

Một advice gọi `stage.toCompletableFuture().join()` chỉ để lấy result rồi trả value có thể:
- Block thread không được phép block.
- Phá latency và scheduling của caller.
- Biến lỗi future thành `CompletionException` đồng bộ.
- Không khớp declared return type nếu method vẫn khai báo `CompletionStage<T>`.
- Gây deadlock trong mô hình event loop hoặc pool cạn thread.

Nếu API đã hứa async handle, một advice quan sát thuần không nên tự biến nó thành synchronous wait.

### 14.4. Cancellation và timeout

Đổi future gốc thành dependent stage có thể làm **cancellation propagation** khác đi tùy abstraction. Cancel handle không tự bảo đảm worker I/O đã ngừng. Nếu caller có quyền cancel, time out, hoặc so identity của handle, một replacement cần được thiết kế theo hợp đồng đầy đủ chứ không chỉ generic type.

## 15. Stream, iterator, publisher: return type còn là giao thức sử dụng

Một method `Stream<Row> streamRows()` không nhất thiết tính toàn bộ dữ liệu trước khi return. Một `Iterator<T>` chỉ cung cấp phần tử khi caller gọi `next()`. Một publisher có thể lazy, chạy khi có subscriber/demand.

### 15.1. Không tiêu thụ result chỉ để log

Một advice muốn log “toàn bộ rows trả về” rồi tự thực thi terminal operation trên `Stream` có thể **tiêu thụ stream**, khiến caller không thể duyệt lại. Nó có thể giữ resource hoặc làm thay đổi side effects. Tương tự gọi `Iterator.next()` để kiểm tra có dữ liệu có thể làm mất phần tử đầu.

### 15.2. Biến stream thành list làm đổi semantics

Nếu advice gọi `toList()` rồi tạo stream mới:
- Lazy có thể thành eager.
- Bộ nhớ tiêu thụ khác.
- Timing và exception xuất hiện tại thời điểm khác.
- Resource close semantics có thể khác.
- Trật tự và parallel behavior có thể khác.

Chỉ làm nếu đó là transformation được API cho phép và có test.

### 15.3. Publisher không có một return value duy nhất

Publisher có thể phát nhiều values, onComplete/onError hoặc cancellation. Around advice chỉ bao method tạo publisher chưa chắc bao toàn bộ subscription lifecycle. Muốn bảo toàn contract phải tính cả số lần subscribe, backpressure, ordering, terminal signals và resource cleanup.

## 16. Thứ tự nhiều aspect và ý nghĩa result

Hai around advices có thể tương tác:

~~~text
Normalize(
    Cache(
        Target
    )
)
~~~

Hoặc:

~~~text
Cache(
    Normalize(
        Target
    )
)
~~~

Nếu Normalize thay đổi result, vị trí của Cache quyết định nó giữ **raw value** hay **normalized value**. Nếu cache key phụ thuộc arguments đã biến đổi hoặc identity của principal, còn nhiều ràng buộc nữa.

### 16.1. Authorization trước short-circuit

Nếu một cache advice ngoài trả ngay mà không vào authorization advice bên trong, chính sách quyền có thể bị skip. Không được kết luận một ordering đủ đảm bảo bảo mật nếu caller có đường bypass proxy/target; cần trusted boundary và test.

### 16.2. Exception mapping và logging

Nếu một advice trong chuyển exception `E` thành fallback value, advice ngoài nhận **normal return**. Một after-throwing của tầng ngoài không tự thấy `E`. Nếu hệ thống cần metric attempt failures, phải thu ở vị trí còn quan sát được lỗi gốc.

### 16.3. Giữ logical outcome nhất quán

Khi nhiều advice cùng biến đổi result, cần thiết lập thứ tự tường minh, đơn vị success/failure, và chính sách ai có quyền sửa:
- Result normalization.
- Cache.
- Retry/fallback.
- Security masking.
- Auditing.
- Metrics/tracing.

Một pipeline biến đổi mà mỗi advice nghĩ mình là “observer” rất dễ tạo semantics không dự đoán được.

## 17. Thiết kế contract cho advice quan sát thuần

Một **transparent observer** có thể được đánh giá theo các invariant sau:

1. **Return identity:** nếu target trả object `R`, advice trả đúng `R` trừ khi API cho phép tạo equivalent wrapper.
2. **Primitive value:** giữ nguyên `0`, `false`, negative values và mọi sentinel hợp lệ.
3. **Nullability:** giữ `null` nếu đó là result hợp lệ; không tự chèn `null` vào API hứa non-null.
4. **Reference content:** không mutate result/arguments ngoài mục tiêu quan sát.
5. **Exceptional behavior:** không tự swallow, map hoặc che lỗi gốc nếu không được phép.
6. **Execution count:** gọi continuation đúng một lần nếu observer không có chức năng skip/retry.
7. **Temporal behavior:** không biến future/stream lazy thành synchronous/eager ngoài ý định.
8. **Ownership:** không đóng result resource trước khi caller dùng xong.
9. **Thread/context:** không giữ request context lâu vô hạn; dọn scope đúng khi throw/return.
10. **Instrumentation failure:** chính sách rõ khi logger/metric sink lỗi; không vô tình thay outcome của nghiệp vụ.
11. **Security/privacy:** không log dữ liệu nhạy cảm chỉ để ghi kiểu/giá trị.
12. **Concurrency:** không giữ `lastResult` hoặc `startTime` trong shared mutable field gây race.
13. **Performance:** không deep-copy/serialize toàn object graph nếu chỉ cần một metric.
14. **Engine contract:** kiểm tra kiểu advice được phép thay result và những method/join point nó thực sự nhận.

### 17.1. Một observer không nhất thiết tuyệt đối “không có side effect”

Logging và metrics vốn là side effects quan sát. Cụm “transparent” ở đây nghĩa là **không cố tình đổi outcome/side effects nghiệp vụ theo hợp đồng đã công bố**. Vẫn phải xử lý rủi ro log I/O blocking, privacy, exception do instrumentation và resource usage.

### 17.2. Nếu cần thay result, công bố transformation rõ

Một advice thay result nên có hợp đồng riêng:
- Điều kiện được thay.
- Mapping từ original → transformed.
- Cách xử lý `null`, absence, exception.
- Identity/mutability/ordering.
- Async/cancellation/stream lifecycle.
- Failure path khi transformation tự lỗi.
- Testing chứng minh caller nhận đúng semantics.

## 18. Kiểm thử: không chỉ assert kiểu trả về

### 18.1. Ma trận test cơ bản

| Nhóm | Target | Expected từ observer | Lỗi cần phát hiện |
| --- | --- | --- | --- |
| Primitive zero | `int 0` | Caller nhận `0`. | Thay bằng null hoặc default khác. |
| Primitive false | `boolean false` | Caller nhận `false`. | Coi false là lỗi và throw. |
| Primitive negative | `int -1` hợp lệ theo domain | Caller nhận `-1`. | Tự normalize thành 0. |
| Primitive wrong wrapper | `int` nhưng handler trả `String` | Test xác nhận proxy báo type error. | Tin rằng `"7"` tự cast thành int. |
| Nullable reference | `null` được phép | Giữ null. | Thay thành empty string trái contract. |
| Non-null Optional | `Optional.empty()` | Giữ Optional object, không null. | Trả null rồi lỗi về sau. |
| Generic collection | `List<String>` | Giữ kiểu phần tử, thứ tự và mutability. | Raw list chứa Integer. |
| Identity-sensitive | Trả object dùng chung | Giữ same instance nếu API hứa. | Tạo copy khác identity. |
| Defensive-copy API | Trả bản sao | Vẫn không lộ internal mutable reference. | Advice trả state gốc. |
| Void | Side effect rồi normal return | Không invent result hay skip side effect. | Nuốt lỗi hoặc bỏ qua target. |
| Sync exception | Target throw loại E | Caller thấy E theo contract. | Swallow/map vô cớ. |
| Async pending | Trả stage còn pending | Caller nhận handle đúng, chưa báo task success. | Chặn join hoặc kết luận success sớm. |
| Async exceptional | Stage fail sau return | Callback quan sát lỗi; caller nhận failure. | Biến failure thành fake success. |
| Async identity | Stage original được hứa | Giữ original khi observer. | Trả dependent stage sai contract. |
| Short-circuit cache | Có cached value hợp lệ | Không chạy target theo policy, value đúng. | Cache sai key/identity/permissions. |
| Retry | Nhiều attempts | Kết quả cuối và side effects theo policy. | Lặp tác dụng không idempotent. |
| Stream/publisher | Lazy resource | Giữ thứ tự/lifecycle/terminal signals. | Advice tiêu thụ trước caller. |

### 18.2. Test với cùng input hai đường gọi

Nếu có một proxy/decorator và target gốc, test so sánh:
- Result của `target.method(args)`.
- Result của `proxy.method(args)`.
- Exception/cause nếu target throw.
- Số lần target side effects xảy ra.
- Nếu contract yêu cầu identity, dùng `==`; nếu yêu cầu value equivalence, kiểm `equals` và semantic constraints.

Đối với cache/retry policy cố ý làm khác target, thay vì so tất cả bằng nhau, ghi **expected transformation** rõ theo từng nhánh.

### 18.3. Test golden path chưa đủ

Một advice có thể pass với giá trị `7` nhưng fail với `0`, `null`, empty collection, exception hoặc future exceptional. Cần test **điểm biên** và negative cases.

### 18.4. Property-based/metamorphic tests

Nếu observer phải trong suốt, có thể kiểm tra trên nhiều inputs:
- Khi target return bình thường, proxy return cùng value/reference theo policy.
- Khi target throw, proxy truyền cùng exception type/cause.
- Target được gọi đúng một lần.
- Advice không mutate arguments hoặc result.
- Nullable/generic contract được giữ.

Nếu targets có nondeterminism (thời gian, random, network), dùng controlled doubles thay vì so hai lời gọi thật có thể có side effects khác nhau.

### 18.5. Concurrency và async tests

Dùng `CompletableFuture` chưa hoàn tất rồi tự `complete`/`completeExceptionally` để test chính xác method-return và task-completion. Với threads, dùng synchronization primitives thay `Thread.sleep` đoán thời gian. Đảm bảo completion callback không giữ raw request/args lâu hơn nhu cầu, không trộn result của invocation A với B.

## 19. Lỗi phổ biến khi xử lý result trong advice

**“Chỉ cần return cùng kiểu Java là an toàn.”** Sai. Có thể phá nullability, sentinel, identity, side effects và error meaning.

**“Primitive int có thể được thay bằng null khi không có dữ liệu.”** Sai đối với JVM return primitive của proxy; unboxing null có thể gây NPE.

**“Trả String `"7"` cho method int là Java tự đổi kiểu.”** Sai trong JDK dynamic proxy; có thể ClassCastException.

**“`Optional.empty()` và null là như nhau.”** Sai. Optional là abstraction có hợp đồng không-null tùy API, null có thể phá caller.

**“Method trả Optional mà gặp exception thì trả empty cho đơn giản.”** Không nếu exception nghĩa là kết quả chưa biết do storage failure.

**“Void nghĩa là không có việc gì để bảo toàn.”** Sai. Side effects và exception contract vẫn tồn tại.

**“Một `List<String>` luôn được runtime kiểm tra từng phần tử ngay khi proxy return.”** Sai; type erasure có thể đẩy lỗi tới lúc đọc phần tử.

**“Result `equals()` nhau nghĩa là việc đổi reference luôn vô hại.”** Sai nếu identity, mutability hoặc ownership có ý nghĩa.

**“Advice trả chính result reference thì không thể đổi dữ liệu.”** Sai nếu advice đã mutate object trước return.

**“Dùng `join()` trên future trong around sẽ luôn an toàn.”** Không; có thể block, deadlock hoặc đổi thời điểm lỗi.

**“Stage gốc và stage từ `whenComplete` luôn có cùng hợp đồng.”** Không mặc định; callback error và identity có thể khác.

**“After-returning cho phép thay return bằng cách gán một biến local.”** Không phải mọi engine đều có semantics đó.

**“Bắt mọi lỗi rồi return `0` là bảo toàn kiểu.”** Có thể hợp kiểu nhưng thay lỗi thành false success.

**“Cache hit được phép skip mọi advice bên trong.”** Về cơ chế có thể skip; về bảo mật/semantics phải bảo đảm policy không bị bypass.

**“Retry chỉ ảnh hưởng thời gian chờ.”** Sai; có thể lặp side effects và thay số invocation.

**“Stream chỉ là một List lười, đọc thử để log cũng được.”** Không; có thể tiêu thụ stream và làm hỏng lifecycle.

**“Một lần pass integration test chứng minh AOP tương thích mọi caller.”** Không; còn direct-target bypass, self-invocation, overload, generic bridges và classloader/pointcut scopes.

## 20. Bài tập vận dụng và đáp án

### Bài 1 — Giá trị `0`

`countActive()` trả `0` khi không có mục nào hoạt động. Around advice trả `null` để biểu diễn “không có dữ liệu”. Có đúng không?

**Đáp án:** Không. Method trả primitive int; trong JDK proxy có thể NPE do unboxing. Quan trọng hơn, `0` là **giá trị hợp lệ** phải được giữ.

### Bài 2 — Che lỗi bằng `false`

`boolean isAuthorized()` ném exception vì permission service không khả dụng. Advice bắt lỗi rồi trả `false`. Điều gì thay đổi?

**Đáp án:** Trả `false` có thể biểu diễn từ chối có căn cứ, còn exception nghĩa là không xác minh được. Đó là mapping policy phải có chủ đích, không phải observer transparent.

### Bài 3 — `Optional` và mất dữ liệu

Một `Optional<Account>` được trả từ DB, DB lỗi nhưng advice return `Optional.empty()`. Caller có thể làm sai điều gì?

**Đáp án:** Caller tưởng tài khoản không tồn tại và thực hiện thao tác tạo mới hoặc xử lý sai khác. Phải phân biệt absence với inability-to-query.

### Bài 4 — Raw list

Advice trả `List<Integer>` qua interface khai báo `List<String>` bằng raw cast. Tại sao caller có thể chỉ lỗi khi đọc phần tử?

**Đáp án:** Java generics erasure; cast container không bảo đảm kiểm từng element.

### Bài 5 — Identity

Method hứa trả cùng một token object cho các lời gọi; advice clone object mỗi lần. Kiểu có đúng không và hợp đồng ra sao?

**Đáp án:** Kiểu có thể đúng nhưng identity promise bị phá. Cần bảo toàn same reference nếu được API yêu cầu.

### Bài 6 — Void method bị skip

Một advice cache thấy method return void nên quyết định không gọi `proceed`. Rủi ro?

**Đáp án:** Side effect của method có thể bị bỏ qua hoàn toàn; return type void không làm side effects trở nên tùy chọn.

### Bài 7 — Two futures

Một handler đăng ký `whenComplete` rồi trả **dependent stage** thay stage gốc, callback đôi khi ném lỗi. Tại sao caller có thể thấy outcome khác?

**Đáp án:** Dependent stage có thể exceptional do callback; dù generic return type giống nhau, stage identity và completion semantics khác.

### Bài 8 — Synchronous vs asynchronous failure

Method async trả future bình thường rồi future fail sau 1 giây. After-throwing dành cho invocation method có tự nhận lỗi đó không?

**Đáp án:** Không. Method invocation đã return handle bình thường; cần quan sát completion nếu muốn thấy lỗi task.

### Bài 9 — Retry “thành công”

Advice retry ghi dữ liệu hai lần vì lần đầu response timeout sau commit. Caller cuối nhận OK. Type/result đã bảo toàn toàn bộ contract chưa?

**Đáp án:** Không chắc; có thể duplicate side effects. Cần idempotency/transaction guarantees.

### Bài 10 — Stream log

Advice nhận `Stream<Order>`, gọi `count()` rồi return stream gốc. Caller gọi terminal operation sau. Rủi ro gì?

**Đáp án:** Stream đã bị tiêu thụ, thường không thể dùng terminal operation lần hai. Advice cần quan sát mà không tiêu thụ pipeline, hoặc dùng abstraction được thiết kế rõ.

### Bài 11 — Fallback checked exception

Interface method khai `throws IOException`, handler tự ném một checked exception khác không khai báo. Có bảo đảm caller thấy trực tiếp loại mới không?

**Đáp án:** Không với JDK dynamic proxy; có thể xuất hiện `UndeclaredThrowableException`. Checked error mapping phải theo method signature/proxy contract.

### Bài 12 — Mutation dù cùng reference

Around advice nhận `List<String>`, gọi `clear()` rồi return chính list đó. Có phải transparent observer vì `return original`?

**Đáp án:** Không. State của result đã bị thay đổi; cùng identity không có nghĩa cùng semantic value.

## 21. Checklist trước khi triển khai advice thao tác với result

1. **Signature:** Method declared return type là gì: primitive, reference, void, generic, future hay stream?
2. **Type validation:** Engine/proxy kiểm tra runtime cast/unboxing ở đâu?
3. **Nullability:** `null` hợp lệ không, Optional/Result có nghĩa riêng không?
4. **Domain meaning:** `0`, `false`, empty, sentinel và absence được định nghĩa ra sao?
5. **Failure:** Exception là state khác return value không, có nguyên nhân cần giữ không?
6. **Identity:** Caller cần same instance, snapshot, defensive copy hay chỉ value equivalence?
7. **Mutability:** Advice có mutate arguments/result hay thay ordering của collection không?
8. **Execution count:** Advice có skip hoặc retry khiến side effects thay đổi không?
9. **Cache:** Key đầy đủ, security scope/tenant, TTL và ownership có đúng không?
10. **Async:** Method return-handle và task completion có phân biệt không?
11. **Future stage:** Caller nhận original hay dependent stage; cancellation/callback failure thế nào?
12. **Lazy result:** Stream/publisher/iterator có bị tiêu thụ trước caller không?
13. **Resources:** Ai sở hữu handle; khi nào được close/dispose?
14. **Exception mapping:** Có vô tình thay checked type hoặc cause không?
15. **Ordering:** Các advice khác có transform result/failure trước hoặc sau advice này không?
16. **Interception:** Caller có thể bypass proxy hoặc join point nằm ngoài weaving scope không?
17. **Privacy:** Có log raw result chứa dữ liệu nhạy cảm không?
18. **Thread safety:** Result/context có bị giữ trong shared aspect field không?
19. **Performance:** Có deep-copy/serialize/block I/O chỉ để quan sát không?
20. **QA:** Có test zero/false/null/empty, error, generic, identity, cache hit, async và stream?
21. **Production evidence:** Có integration tests với đúng engine/JDK/classloader và artifact được triển khai không?

## Kết luận

Trong AOP, **bảo toàn kiểu trả về** là yêu cầu tối thiểu để caller tiếp tục sử dụng method theo chữ ký, nhưng **bảo toàn ý nghĩa giá trị trả về** mới là yêu cầu đầy đủ của hợp đồng. Một advice có thể sai dù return đúng generic container, đúng class, hoặc đúng primitive wrapper: nó vẫn có thể che exception, biến `Optional.empty()` thành `null`, phá identity/mutability, làm mất side effect, tiêu thụ stream, hoặc thay future gốc bằng một dependent stage có lifecycle khác.

Với **advice quan sát thuần túy**, ưu tiên **trả nguyên result, bảo toàn lỗi, không mutate dữ liệu và không thay số lần target chạy**. Với **advice được phép transform** như cache, fallback, retry hay normalization, phải công bố chính sách về type, nullability, error, identity, side effects, resource ownership và completion. Hãy kiểm chứng các mốc có thể thất bại — primitive unboxing, generics erasure, checked exceptions, async completion — bằng test thực tế thay vì chỉ nhìn compiler pass. Một thiết kế AOP tốt không chỉ giữ cho method “trả được gì đó”, mà giữ nguyên điều **caller có quyền tin** khi nhận kết quả ấy.
