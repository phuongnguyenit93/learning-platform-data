# Khả năng thay thế của đối tượng sau khi áp dụng aspect

## 1. Vấn đề cốt lõi: đối tượng “đã áp dụng aspect” còn dùng thay đối tượng gốc được không?

Trong **Aspect-Oriented Programming (AOP)**, một aspect có thể được kết hợp với mã bằng **weaving** hoặc được áp dụng thông qua **proxy/decorator/interceptor**. Mục tiêu phổ biến là thêm logging, tracing, metrics, quản lý tài nguyên, kiểm soát quyền, retry hoặc caching mà không làm thay đổi logic chính.

Tuy nhiên, áp dụng aspect có thể tác động đến **kết quả trả về**, **ngoại lệ**, **thời điểm thực thi**, **số lần thực hiện side effect**, **identity của object**, **kiểu runtime**, **khả năng ép kiểu**, **đồng thời**, **thứ tự quan sát** và cả **lifecycle**. Vì vậy, không thể chỉ thấy “code vẫn compile” hoặc “proxy có cùng interface” rồi kết luận đối tượng sau khi áp dụng aspect **thay thế hoàn toàn** đối tượng ban đầu.

Câu hỏi trung tâm:

> **Với những client chỉ dựa vào hợp đồng đã công bố, việc thay một đối tượng gốc bằng đối tượng/cơ chế đã áp dụng aspect có còn bảo toàn các hành vi quan sát được mà client được quyền trông đợi không?**

Đây là vấn đề **substitutability** (khả năng thay thế), liên quan đến nguyên tắc **Liskov Substitution Principle — LSP**, thiết kế theo hợp đồng, tính trong suốt của advice và ranh giới abstraction. AOP có thể tăng chất lượng hệ thống, nhưng cũng có thể làm sai các giả định vốn hợp lệ trước khi áp dụng aspect.

### Bạn sẽ học được gì?

1. Phân biệt **khả năng gán theo kiểu** và **khả năng thay thế về hành vi**.
2. Phân tích **precondition**, **postcondition**, **invariant**, kết quả, ngoại lệ, side effect và điều kiện thời gian.
3. Hiểu khác biệt giữa **proxy**, **decorator** và **weaving trực tiếp** đối với class/type/identity.
4. Đánh giá `equals`, `hashCode`, `toString`, `getClass`, reflection, serialization và các kiểm tra kiểu cụ thể.
5. Hiểu khi nào advice quan sát có thể được thiết kế **transparent**, và khi nào retry/cache/fallback/authorization cố ý thay đổi hợp đồng.
6. Phân biệt **result đúng kiểu** với **result đúng ý nghĩa**, nhất là `null`, `Optional`, primitive, checked exceptions, future và stream.
7. Nhận diện giới hạn của **self-invocation** hoặc đường gọi bypass proxy đối với lời hứa “mọi invocation đều được can thiệp”.
8. Thiết kế integration tests dùng cùng bộ **contract tests** cho đối tượng gốc và đối tượng được bọc.
9. Chạy ví dụ **Java 17** chứng minh một proxy giữ được hành vi của interface nhưng **khác identity và class runtime**, cùng một proxy sai bảo toàn kiểu nhưng phá semantics.

**Phạm vi:** Bài nói về AOP cơ bản và nâng cao nói chung. Không giả định mọi engine AOP dùng một cơ chế proxy hoặc cùng một bộ quy tắc weaving.

## 2. Ba tầng “thay thế được” rất khác nhau

### 2.1. Tầng 1 — Gán được vào một biến/interface

Ví dụ:

~~~java
interface Store {
    String load(String key);
}
~~~

Nếu có object `wrapped` triển khai `Store`, caller có thể viết:

~~~java
Store store = wrapped;
~~~

Đây là **tương thích tại ranh giới kiểu**. Nó chỉ chứng minh object được gán hợp lệ vào kiểu `Store`, không chứng minh method `load` trả nội dung, exception và side effects theo hợp đồng.

Một proxy có thể implements cùng interface mà trả chuỗi rỗng cho mọi key, nuốt lỗi storage hoặc ghi đè dữ liệu. Code vẫn compile nhưng không đạt substitutability.

### 2.2. Tầng 2 — Giữ đúng hợp đồng hành vi của abstraction

Giả sử hợp đồng `Store.load("A")` hứa:
- Trả dữ liệu tương ứng nếu tồn tại.
- Ném `NotFound` khi key hợp lệ nhưng không có.
- Ném `Unavailable` khi storage lỗi, không biến thành `NotFound`.
- Không tự thay đổi dữ liệu.
- Không làm lộ key bí mật qua log.

Một advice logging **có thể** bảo toàn contract nếu nó chỉ quan sát đúng giới hạn, tiếp tục đúng một lần, trả nguyên result hoặc rethrow lỗi theo hợp đồng. Ngược lại, fallback “trả empty string cho mọi exception” đã phá phân biệt giữa *không tồn tại*, *storage không truy cập được* và *giá trị rỗng hợp lệ*.

### 2.3. Tầng 3 — Không phân biệt được qua mọi phép quan sát

Đây là mức mạnh hơn nhiều. Một interface proxy có thể hoạt động giống target ở các method của `Store`, nhưng:
- `wrapped == target` là `false`.
- `wrapped.getClass()` cho class proxy, không phải concrete target.
- Cast `(ConcreteStore) wrapped` có thể thất bại.
- `equals`, `hashCode` và `toString` có thể khác.
- Reflection/serialization annotations hoặc serialization format có thể khác.
- Stack traces và timing/logging có thể khác vì thêm interceptor.

Vì thế “thay thế được” phải được phát biểu **theo góc nhìn của client và những quan sát được hợp đồng cho phép**. Không hứa một proxy là bản sao không thể phân biệt với target dưới mọi phép quan sát Java.

## 3. LSP và design by contract khi có aspect

**Liskov Substitution Principle** được hiểu ở đây như yêu cầu: một implementation mới hoặc một đối tượng được bọc phải có thể được dùng tại chỗ abstraction hiện hành **mà không làm client tuân thủ hợp đồng trở nên sai**.

Các yếu tố thường cần kiểm:

| Phần của hợp đồng | Đối tượng gốc | Điều advice/proxy phải xem xét |
| --- | --- | --- |
| **Precondition** | Điều kiện caller phải thỏa trước invocation. | Có tự ý yêu cầu điều kiện mạnh hơn không? |
| **Postcondition** | Điều kiện được bảo đảm khi method hoàn tất thành công. | Return, state và side effects có còn đúng không? |
| **Invariant** | Tính chất phải giữ qua các thao tác hợp lệ. | Retry/cache/fallback có gây trạng thái không nhất quán không? |
| **Failure contract** | Ngoại lệ, mã lỗi, exceptional completion. | Có nuốt, thay, bọc hoặc phát sinh lỗi mới ngoài ý định không? |
| **Temporal contract** | Khi nào kết quả và side effects được xem là hoàn tất. | Có block/hứa success sớm/đổi async lifecycle không? |
| **Ownership** | Ai sở hữu resource hoặc result. | Advice có đóng sớm, giữ reference lâu hoặc trả shared resource sai không? |
| **Concurrency** | Điều kiện thread safety/linearizability/reentrancy. | State advice có data race, lock hoặc deadlock không? |
| **Identity/representation** | Caller được dựa vào interface hay concrete class? | Proxy có làm sai các giả định được công bố không? |

### 3.1. Không được tăng precondition ngoài ý định

Một method `read(key)` chấp nhận mọi key không-null. Nếu một aspect mới chỉ cho phép key bắt đầu `"admin/"`, ta đã **thu hẹp miền inputs hợp lệ**. Có thể đây là một security policy được chủ đích bổ sung, nhưng không còn là một replacement trong suốt đối với client đã được hứa đọc những key khác.

Nếu API đã công bố quyền đọc tùy authorization của caller, advice kiểm soát quyền có thể là cách thực thi chính xác contract hiện có. Tính thay thế phụ thuộc **hợp đồng được công bố**, không phụ thuộc ấn tượng “thêm security là tốt”.

### 3.2. Không được làm yếu postcondition

Nếu `deposit(5)` phải tăng balance đúng 5 và trả balance mới, một advice trả `999` mà không gọi target vi phạm postcondition dù return type vẫn là `int`.

Một advice cache trả balance cũ có thể vi phạm freshness/invariant; một advice retry làm deposit hai lần có thể vi phạm quy tắc “chỉ tăng đúng một lần”.

### 3.3. Giữ trạng thái quan sát được, không chỉ result

Một method `void publish(Event e)` không có return value nhưng có hợp đồng “đăng event đúng một lần khi thành công”. Một advice return bình thường mà skip `proceed()` không thể được coi là substitutable chỉ vì method trả `void`.

Tương tự, nếu method cập nhật DB rồi trả `true`, caller có thể quan sát DB bên ngoài; result đúng nhưng side effect sai vẫn là vi phạm.

### 3.4. Hợp đồng có thể cho phép nhiều implementation khác nhau

LSP không yêu cầu mọi implementation có cùng thuật toán, thời gian CPU hoặc cách logging. Nếu một interface chỉ hứa `get(id)` trả dữ liệu đúng và không công bố identity của object, một cache có thể thay đổi performance hoặc source của dữ liệu mà vẫn đáp ứng contract. Nếu interface hứa “đọc trực tiếp nguồn authoritative, luôn mới”, cache stale có thể không thay thế được.

## 4. Target, proxy và aspect: object nào thật sự được thay?

Các kỹ thuật AOP có **dấu vết runtime** rất khác nhau.

### 4.1. Delegating interface proxy

Một proxy implement interface và giữ một target:

~~~text
Caller -> InterfaceProxy -> InvocationHandler/advice -> Target
~~~

**Tính thay thế:** caller dựa vào interface có thể dùng proxy nếu operations, exceptions và state semantics được bảo toàn. Nhưng proxy thường **không phải instance** của concrete target class và không có cùng identity.

### 4.2. Decorator

Một decorator triển khai cùng abstraction rồi chuyển tiếp tới target:

~~~text
Caller -> ObservedStore implements Store -> RealStore
~~~

Mặc dù decorator được viết thủ công và có thể không cần runtime code generation, các vấn đề về identity, ownership, nested calls và result transformation vẫn tồn tại. Tên gọi “decorator” không tự bảo đảm substitutability.

### 4.3. Class-based proxy

Một số công cụ tạo subclass hoặc generated class. Proxy có thể assignable tới target base class, nhưng khả năng intercept còn bị ràng buộc bởi `final`, visibility, constructors, method dispatch và chi tiết engine. Subclass relationship không tự bảo đảm equals/hashCode, state initialization hoặc invariants của target.

**Không đưa ra quy tắc chung** như “class proxy luôn thay được concrete class” hoặc “self-invocation của mọi class proxy luôn bypass”. Những chi tiết này phải được xác minh trên implementation thật.

### 4.4. Source/bytecode weaving

Một engine có thể **dệt logic vào method execution/call site** thay vì tạo một wrapper object mới. Khi đó class identity của target có thể vẫn là chính class ấy, nhưng code/behavior đã thay đổi.

Đây không phải bảo đảm substitutability tuyệt đối: weaving có thể đổi exception, result, lock contention, timing, stack trace, thread context hoặc side effects. Dù object identity không đổi, **behavioral contract** vẫn có thể bị phá.

### 4.5. Runtime instrumentation/load-time weaving

Class có thể được biến đổi khi nạp hoặc trong quá trình runtime nếu công cụ cho phép. Thời điểm và phạm vi biến đổi ảnh hưởng classloader, module và những instances hiện có, nhưng vẫn phải kiểm tra các hợp đồng quan sát được. Không coi “biến đổi được bytecode” là bằng chứng giữ nguyên behavior.

## 5. Interface compatibility không đồng nghĩa concrete compatibility

Giả sử:

~~~java
interface CounterPort {
    int add(int step);
}

final class CounterImpl implements CounterPort {
    @Override
    public int add(int step) { /* implementation */ return 0; }
}
~~~

Nếu một JDK dynamic proxy implements `CounterPort`, caller chỉ biết `CounterPort` có thể gọi `add`. Nhưng:

~~~java
CounterPort wrapped = createProxySomehow(); // mã minh họa
CounterImpl concrete = (CounterImpl) wrapped; // runtime có thể lỗi cast
~~~

Đây là **đoạn mô tả**, chưa phải chương trình chạy đầy đủ. Phép cast không được bảo đảm vì một JDK proxy là object khác, không kế thừa `CounterImpl`.

### 5.1. “Programming to an interface” giúp đến đâu?

Nếu mọi client hợp lệ chỉ dùng `CounterPort`, không đòi concrete class, proxy có biên tương thích thuận lợi hơn. Nhưng trong dự án thực tế có thể có:
- Reflection đọc annotations trên implementation.
- Serialization cần concrete type.
- Framework hoặc native library cần exact class.
- Code dựa vào identity hoặc class name.
- Overload resolution hay API dùng concrete type.
- Method không nằm trong interface.
- Contract về finalizers/constructors/resource ownership.

Khi thay bằng interface proxy, phải **rà những yêu cầu ấy**, không chỉ sửa compiler errors.

### 5.2. Một interface có thể quá hẹp cho nhu cầu

Nếu client cần một method `close()` vốn chỉ có trên concrete target, một interface proxy không tự phơi bày method đó trừ khi interface/wrapper công bố. Khi design proxy boundary, cần bảo đảm interface chứa **đúng các operations có trong hợp đồng**, kể cả lifecycle operations.

### 5.3. Runtime type và generic type khác nhau

Một `List<Store>` có thể chứa target hoặc proxy cùng interface. Nhưng khi caller lấy ra và cast tới `ConcreteStore`, vẫn có thể lỗi. Generics chỉ đảm bảo những điều compiler có thể biết về kiểu công bố; không biến proxy thành subtype concrete tự động.

## 6. Identity, equals, hashCode, toString và Object methods

Đối với Java, nhiều client không chỉ gọi business methods. Chúng có thể:
- Dùng object làm key trong `HashMap`/`HashSet`.
- So sánh `==` hoặc `equals()`.
- Ghi log `toString()`.
- Lấy `System.identityHashCode()`.
- Gọi `getClass()` hoặc reflection để tra annotations.
- Khóa trên monitor của object.
- Dùng object identity như một token/correlation key.

Áp dụng proxy có thể thay những hành vi này.

### 6.1. `==` không thể được giả lập cho hai object riêng

Nếu `proxy` và `target` là hai object khác nhau thì:

~~~text
proxy == target  -> false
~~~

Một method `equals()` tự viết có thể quyết định hai object tương đương ở mức giá trị, nhưng **không thể làm toán tử `==` coi chúng là cùng reference**. Nếu contract của client phụ thuộc identity của target, một delegating proxy riêng biệt không đạt sự trong suốt tuyệt đối đối với phép quan sát ấy.

### 6.2. `equals()` phải giữ đối xứng, bắc cầu và nhất quán

Nếu proxy tự trả `true` khi so với target, nhưng `target.equals(proxy)` trả `false`, cặp đối tượng vi phạm **symmetry** của hợp đồng `Object.equals`. Điều này có thể gây lỗi trong collections và cache.

Đừng sửa đơn giản bằng “proxy.equals(target) luôn true”. Phải thiết kế equality strategy cho toàn bộ abstraction, cân nhắc symmetry/transitivity/consistency và việc code khác có thể vẫn dùng target gốc.

### 6.3. `hashCode()` phải phù hợp `equals()`

Nếu hai objects được coi là equal thì hash codes phải bằng nhau theo hợp đồng Java. Nếu proxy dùng một hash code mới trong khi `equals` cố liên kết nó với target, map/set behavior có thể bị lỗi.

Một chiến lược là **proxy identity semantics**: proxy chỉ equal chính nó, `hashCode` theo identity của proxy. Điều này có thể đúng về mặt Java nhưng **khác** cách client so sánh target theo giá trị hoặc identity gốc. Chọn đúng theo hợp đồng.

### 6.4. `toString()` và log cũng là quan sát được

Nếu caller kỳ vọng một chuỗi debug của target, trả chuỗi `"Proxy@..."` có thể làm thay đổi log hoặc snapshots. Nếu `toString` của target có side effect hoặc truy cập dữ liệu nhạy cảm, tự động delegate trong proxy cũng không hẳn an toàn.

### 6.5. JDK proxy xử lý Object methods như thế nào?

Một `InvocationHandler` của JDK dynamic proxy có thể nhận invocation của `equals`, `hashCode`, `toString`. Handler cần chọn chính sách rõ cho các method đó, không mặc định delegate mù quáng mọi `Method` đến target.

Riêng `getClass()` là method final của `Object` và phản ánh **runtime class thực của receiver**. Nó không biến một proxy thành target class. Một số Object methods khác có ý nghĩa monitor/lifecycle riêng không nên bị đánh đồng với business interception.

### 6.6. Equality của proxy và target: có thể không có đáp án thỏa mọi client

Nếu một nhóm clients yêu cầu proxy có identity riêng để là một component lifecycle mới, nhóm khác yêu cầu proxy và target equal, còn nhóm thứ ba dùng `==`, ta có những yêu cầu xung đột. Cần thiết kế **abstraction boundary** thay vì hứa “mọi phép so sánh đều tương đương”.

## 7. Runtime state, ownership và referential transparency

Một delegating proxy có thể giữ **strong reference** tới target. Nếu proxy sống suốt ứng dụng, target cũng có thể sống lâu hơn dự định. Đây là khác biệt lifecycle mà một client sử dụng resource có thể quan sát được.

### 7.1. Ai sở hữu target?

Câu hỏi cần làm rõ:
- Caller có được giữ và gọi target trực tiếp không?
- Proxy có phải owner duy nhất của target không?
- Khi proxy bị close, target có phải close theo không?
- Nếu một target được bọc trong nhiều proxy, proxy nào có quyền đóng resource?
- Nếu target là singleton shared, đóng một decorator có được phép đóng target không?

Không được chỉ vì wrapper triển khai `AutoCloseable` mà tự ý đóng một resource thuộc owner khác.

### 7.2. Aspect không nên giữ result/request vô hạn

Một shared aspect lưu `lastArguments`, `lastResult`, `lastException` hoặc `lastTarget` có thể giữ cả object graph lớn. Substitutability còn có khía cạnh hiệu năng/tài nguyên: target trước đây được giải phóng đúng scope nhưng sau khi gắn aspect thì memory retention tăng không kiểm soát.

Observer nên lưu dữ liệu tối thiểu, giới hạn cache cardinality, dọn `ThreadLocal` và unsubscribe listeners/callbacks khi scope kết thúc.

### 7.3. Một wrapper có thể làm thay đổi khả năng thu hồi classloader

Với hệ plugin, registry từ host giữ proxy/aspect metadata của module cũ có thể giữ classloader cũ reachable. Không giả định việc unload plugin tương đương mọi object đã được GC. Cần kiểm tra retained paths và lifecycle removal rõ ràng.

### 7.4. Referential transparency không phải yêu cầu của mọi method

Một pure function có thể có tính chất cùng input → cùng result và không side effect; một command thay trạng thái thì không. Không nên áp quy tắc pure-function lên mọi method để đánh giá substitutability.

Điều cần giữ là **những điều client có quyền dựa vào**: với method pure, việc thay result hay có side effect mới có thể phá contract; với command, việc làm đúng side effects là một phần của contract.

## 8. Bảo toàn return value và exception contract

### 8.1. Primitive và sentinel

Method trả `int` có thể dùng `0`, `-1` hoặc một khoảng giá trị đặc biệt theo hợp đồng. Một advice tự trả `0` khi lỗi để “đảm bảo có int” có thể biến failure thành success. Với JDK interface proxy, handler trả `null` cho primitive còn có thể gây lỗi unboxing.

### 8.2. `Optional.empty()` khác exception

`Optional.empty()` có thể nghĩa là **không tìm thấy**, trong khi exception nghĩa là **không thể tra cứu**. Advice fallback thay storage failure bằng empty có thể khiến caller thực hiện hành động sai.

### 8.3. `void` vẫn có postcondition

`void commit()` không trả result, nhưng phải bảo toàn trạng thái commit, số lần tác động và error handling. Một advice skip target rồi return bình thường có thể vi phạm contract nghiêm trọng.

### 8.4. Exception type, cause và timing

Nếu target ném `IllegalArgumentException` với một điều kiện input sai, proxy nên truyền lại đúng loại lỗi theo hợp đồng nếu chỉ quan sát. Nếu around advice wrap mọi lỗi trong `RuntimeException`, caller bắt riêng `IllegalArgumentException` có thể bị hỏng.

Trong JDK reflection, `Method.invoke` bọc exception ném từ target trong `InvocationTargetException`; handler quan sát thường cần lấy `getCause()` rồi ném lại. Với checked exceptions qua proxy, những loại không hợp lệ theo interface method signature có thể bị bọc trong `UndeclaredThrowableException`. Đừng dựa vào kiểu lỗi runtime “tình cờ” khi không có hợp đồng rõ.

### 8.5. Return identity và mutability

Một advice tạo bản sao của result có thể phá contract “trả cùng instance”; một advice trả cùng mutable instance cho nhiều caller có thể phá contract “defensive copy”. Kể cả `equals` trả true, identity/ownership có thể khác.

### 8.6. Generic erasure

Một interceptor trả `List<Integer>` cho API `List<String>` bằng raw cast có thể qua ranh giới `Object` nhưng gây `ClassCastException` khi caller đọc phần tử. Substitutability đòi giữ **kiểu dữ liệu thực bên trong**, không chỉ runtime container type.

### 8.7. Biến đổi result phải được công bố

Advice normalization, masking, cache hoặc fallback có thể đổi return hợp lệ nếu **đó là hợp đồng mới được công bố**. Khi ấy test dựa trên hợp đồng mới, không gọi advice “hoàn toàn trong suốt” nữa.

## 9. Java 17 runnable: tương thích interface khác với tương thích concrete class

Ví dụ sau dùng **JDK dynamic proxy** quanh `BalancePort`. Một proxy `audited` giữ nguyên hành vi business khi caller chỉ dùng interface: gọi target **một lần**, trả nguyên result và ném lại lỗi gốc. Handler định nghĩa `equals/hashCode/toString` theo **identity riêng của proxy**.

Sau đó một proxy `broken` cố ý trả `999` cho `deposit(5)` mà không gọi target. Result có đúng kiểu `int`, nhưng không thực hiện side effect ghi balance và sai postcondition.

Tạo file **`AopSubstitutabilityDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.Optional;

public class AopSubstitutabilityDemo {
    interface BalancePort {
        int deposit(int amount);
        int balance();
        Optional<String> owner();
        void reset();
    }

    static final class Ledger implements BalancePort {
        private int cents = 10;

        @Override
        public int deposit(int amount) {
            System.out.println("TARGET deposit " + amount);
            if (amount < 0) {
                throw new IllegalArgumentException("negative amount");
            }
            cents += amount;
            return cents;
        }

        @Override
        public int balance() {
            System.out.println("TARGET balance");
            return cents;
        }

        @Override
        public Optional<String> owner() {
            System.out.println("TARGET owner");
            return Optional.of("A");
        }

        @Override
        public void reset() {
            System.out.println("TARGET reset");
            cents = 0;
        }
    }

    static BalancePort audited(BalancePort target) {
        return (BalancePort) Proxy.newProxyInstance(
                BalancePort.class.getClassLoader(),
                new Class<?>[] { BalancePort.class },
                (proxy, method, args) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "equals" -> proxy == args[0];
                            case "hashCode" -> System.identityHashCode(proxy);
                            case "toString" -> "AuditedBalanceProxy";
                            default -> throw new UnsupportedOperationException(
                                    method.getName());
                        };
                    }

                    System.out.println("ADVICE before " + method.getName());
                    try {
                        Object result = method.invoke(target, args);
                        System.out.println("ADVICE return " + method.getName());
                        return result;
                    } catch (InvocationTargetException wrapped) {
                        Throwable cause = wrapped.getCause();
                        System.out.println("ADVICE throw " + method.getName()
                                + " " + cause.getClass().getSimpleName());
                        throw cause;
                    }
                }
        );
    }

    static BalancePort broken(BalancePort target) {
        return (BalancePort) Proxy.newProxyInstance(
                BalancePort.class.getClassLoader(),
                new Class<?>[] { BalancePort.class },
                (proxy, method, args) -> {
                    if ("deposit".equals(method.getName())) {
                        System.out.println("BROKEN skip deposit");
                        return 999;
                    }
                    return method.invoke(target, args);
                }
        );
    }

    static void runClient(BalancePort port) {
        System.out.println("CLIENT deposit=" + port.deposit(5));
        System.out.println("CLIENT balance=" + port.balance());
    }

    public static void main(String[] args) {
        Ledger target = new Ledger();
        BalancePort proxy = audited(target);

        System.out.println("TYPE interface=" + (proxy instanceof BalancePort));
        System.out.println("TYPE concrete=" + (proxy instanceof Ledger));
        System.out.println("IDENTITY same=" + (proxy == target));
        System.out.println("EQUALS reflexive=" + proxy.equals(proxy));
        System.out.println("EQUALS target=" + proxy.equals(target));
        System.out.println("STRING " + proxy);

        System.out.println("CLIENT owner=" + proxy.owner());
        runClient(proxy);

        try {
            proxy.deposit(-2);
        } catch (IllegalArgumentException error) {
            System.out.println("CLIENT rejected=" + error.getMessage());
        }

        proxy.reset();
        System.out.println("CLIENT resetState=" + proxy.balance());

        BalancePort invalid = broken(target);
        System.out.println("BROKEN returned=" + invalid.deposit(5));
        System.out.println("TARGET actualBalance=" + target.balance());

        try {
            Ledger concrete = (Ledger) proxy;
            System.out.println(concrete);
        } catch (ClassCastException error) {
            System.out.println("CAST to Ledger failed");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AopSubstitutabilityDemo.java
java AopSubstitutabilityDemo
~~~

**Stdout dự kiến, đúng theo thứ tự:**

~~~text
TYPE interface=true
TYPE concrete=false
IDENTITY same=false
EQUALS reflexive=true
EQUALS target=false
STRING AuditedBalanceProxy
ADVICE before owner
TARGET owner
ADVICE return owner
CLIENT owner=Optional[A]
ADVICE before deposit
TARGET deposit 5
ADVICE return deposit
CLIENT deposit=15
ADVICE before balance
TARGET balance
ADVICE return balance
CLIENT balance=15
ADVICE before deposit
TARGET deposit -2
ADVICE throw deposit IllegalArgumentException
CLIENT rejected=negative amount
ADVICE before reset
TARGET reset
ADVICE return reset
ADVICE before balance
TARGET balance
ADVICE return balance
CLIENT resetState=0
BROKEN skip deposit
BROKEN returned=999
TARGET balance
TARGET actualBalance=0
CAST to Ledger failed
~~~

### 9.1. “TYPE interface=true” nhưng “TYPE concrete=false”

`proxy` là một object JDK-generated proxy triển khai `BalancePort`, nên có thể truyền vào `runClient(BalancePort)`. Nó **không phải instance** của `Ledger`. Lời gọi `(Ledger) proxy` thất bại với `ClassCastException`.

Điều này minh họa hai phạm vi compatibility:
- **Client chỉ biết interface:** có thể dùng proxy khi behavior được giữ.
- **Client yêu cầu concrete class:** JDK interface proxy không thể tự là cùng subtype.

Một engine subclass proxy khác có khả năng assignability khác, nhưng vẫn phải test behavior chứ không chỉ cast.

### 9.2. Proxy khác identity của target

`proxy == target` là false. Handler cho `equals` trả `true` khi proxy so với chính nó và `false` khi so với target. `hashCode` theo identity của proxy; `toString` dùng một nhãn riêng.

Chiến lược này **có chủ đích** và hợp lý cho identity semantics của proxy, nhưng **không làm proxy hoàn toàn tương đương target** nếu client trước đó dựa vào target identity hoặc representation. Đó là lý do tài liệu của abstraction cần nói rõ caller được dựa vào điều gì.

### 9.3. Owner và kết quả primitive được giữ

`proxy.owner()` trả `Optional.of("A")` từ target. Handler không thay bằng `null` hay `Optional.empty()`. Với `deposit(5)`, target tăng balance từ 10 lên 15 và trả `int 15`, handler chuyển tiếp nguyên kết quả. Client nhận `15`, rồi `balance()` trả `15` — cả result và state postcondition đồng nhất.

Nếu chỉ assert kiểu `int` của kết quả deposit, ta có thể không phát hiện một proxy trả 999. Phải assert **state sau thao tác** nữa.

### 9.4. Lỗi negative amount được giữ nguyên

Target in `TARGET deposit -2` rồi ném `IllegalArgumentException("negative amount")`. `Method.invoke` bọc lỗi vào `InvocationTargetException`; handler lấy cause, ghi loại lỗi và ném lại. Caller bắt đúng loại đã công bố.

Handler không thay lỗi thành `0`, `false` hoặc generic error; advice quan sát giữ contract lỗi.

### 9.5. `void reset()` vẫn bảo toàn side effect

Method `reset()` không có result nhưng target thay balance về 0. Handler chạy trước/sau, caller gọi `balance()` thấy 0. Đây là ví dụ cho thấy **substitutability của command** không thể đánh giá chỉ bằng return type.

### 9.6. Proxy cố ý sai: đúng kiểu nhưng không đúng hợp đồng

`broken` gặp `deposit` thì in `BROKEN skip deposit` và trả `int 999` **mà không gọi target**. Cùng interface, cùng primitive type, không có exception, nhưng:
- Target balance không tăng 5.
- Result không phải balance mới.
- Client có thể tưởng mutation đã thành công.
- Postcondition và side effect contract đều sai.

Stdout chứng minh `BROKEN returned=999` nhưng `TARGET actualBalance=0`. Đây là một replacement **không hợp lệ về hành vi**.

### 9.7. Điều ví dụ không chứng minh

- Không phải một AOP engine source/bytecode weaving.
- Không có pointcut DSL hoặc matching annotations.
- Không chứng minh mọi class-based proxy có cast behavior giống JDK dynamic proxy.
- Không có concurrency; trường `cents` không được bảo vệ cho multi-thread access.
- Không xử lý checked exceptions ở interface.
- Không chứng minh tất cả Object methods/reflective/serialization behavior tương đương với target.
- `broken` chỉ dùng để dạy vi phạm semantic contract; không phải ví dụ thiết kế advice production.
- Không có transaction thực hoặc remote effects; kết quả in stdout là mô hình tuần tự có kiểm soát.

## 10. Tính thay thế khi advice có thể short-circuit

Một around advice có thể bỏ qua target:

~~~text
around load(key):
    if cache.hasValidEntry(key):
        return cache.value(key)
    return proceed()
~~~

Điều này **không tự sai**. Nếu interface contract chỉ yêu cầu trả giá trị hợp lệ, cache có thể đáp ứng. Nhưng cần kiểm tra các điều kiện:

- Có cho phép dữ liệu stale không?
- Có thay đổi theo quyền của user/tenant không?
- Có sự kiện phải xảy ra ở target mỗi lần không?
- Cache hit có bỏ qua authorization hoặc audit bắt buộc không?
- Value có thuộc về caller hay là shared mutable instance?
- Cache key có chứa đầy đủ loại đối số và principal context không?
- Khi target lỗi, có phân biệt exception với giá trị “not found” không?
- Nếu method trả stream/future/resource, caching **handle** có hợp lệ không?

### 10.1. Cache một future khác cache một value

Một `CompletionStage<T>` không chỉ là container giá trị. Nó biểu diễn một hoạt động có lifecycle: pending, success, exceptional completion, cancellation. Trả cùng future từ cache có thể cố tình chia sẻ một computation giữa callers, nhưng khác việc chạy target một lần mới cho mỗi request.

Nếu caller được hứa một fresh task/attempt, cache future có thể vi phạm contract dù generic type vẫn đúng.

### 10.2. Negative caching và failure semantics

Một method trả `Optional<Item>` có thể trả empty cho absent, ném lỗi khi DB unavailable. Nếu cache lưu empty khi DB lỗi, mọi caller sau có thể tin rằng item chắc chắn không tồn tại. Đó là thay đổi semantics cần policy riêng, không phải transparent optimization.

### 10.3. Cache ngoài security boundary

Nếu Cache nằm ngoài Authorization trong chuỗi advice, một cache hit có thể return mà không gọi authorization phía trong. Nếu policy bắt buộc kiểm quyền theo request, đây là vấn đề. Không dựa vào một thứ tự advice như biện pháp security duy nhất; cần trusted boundary mà mọi entry path phải đi qua.

## 11. Retry: cùng result cuối nhưng khác lịch sử thực thi

Một retry advice có thể biến chuỗi hai attempts `FAIL, OK` thành một logical success. Nếu method **đọc idempotent**, điều này có thể phù hợp contract. Nhưng nếu method **thay đổi trạng thái** hoặc phát external side effect, retry có thể thực hiện hai lần dù caller chỉ thấy một return.

Ví dụ một chuyển khoản đã commit nhưng response timeout. Advice tự retry có thể tạo duplicate payment nếu API không có idempotency key hoặc cơ chế kiểm tra outcome.

Vì vậy substitutability còn hỏi:
- Có được phép chạy target nhiều lần không?
- Attempt nào có side effects?
- Có timeout/deadline tổng và retry budget không?
- Exception nào được phép thử lại?
- Caller có thể phân biệt “đã commit nhưng response thất lạc” với “chưa commit” không?
- Có backoff hay circuit breaker làm thay đổi timing SLA?
- Lỗi cuối có còn type/cause theo contract?

### 11.1. Retry không phải “bảo toàn behavior” miễn phí

Một proxy retry đúng kiểu `Receipt` có thể trả một receipt hợp lệ nhưng đã gửi hàng hai lần. Nếu API hứa “chính xác một thao tác” thì failure. Nếu API công bố at-least-once behavior, client có trách nhiệm idempotency tương ứng. Đánh giá theo hợp đồng đã ký kết, không theo trực giác.

### 11.2. Nhiều aspect thay đổi đơn vị quan sát

Với `Metrics(Retry(Target))`, metric ngoài có thể đếm một logical call. Với `Retry(Metrics(Target))`, metric trong có thể đếm các attempts. Không nhất thiết có lỗi, nhưng đổi thứ tự thay dữ liệu thống kê mà operations consumers trông đợi.

## 12. Fallback: che lỗi có thể phá substitutability

Một advice:

~~~text
try:
    return proceed()
catch anyError:
    return defaultValue
~~~

rất dễ tạo **false success**. Với `int count()`, mặc định 0 có thể hợp kiểu nhưng “không có bản ghi” khác “không thể truy vấn”. Với `boolean authorized()`, mặc định false là một quyết định từ chối có thể phù hợp **fail-closed policy** nhưng không nhất thiết phù hợp contract “phân biệt lỗi service”.

Một fallback có thể được chấp nhận khi:
1. API công bố rõ trạng thái degrade/fallback.
2. Fallback chỉ áp cho những loại lỗi được phép.
3. Không làm sai invariant hoặc che outcome mơ hồ của side effect.
4. Có metric/alert về degraded mode theo policy.
5. Không trả result trái nullability, identity hoặc freshness promise.
6. Caller có cách hiểu success/failure hợp lệ với kiểu result.

Không tự bắt mọi `Throwable` để trả mặc định. `Throwable` còn gồm những `Error` mà việc nuốt bỏ có thể làm hệ thống ở trạng thái nguy hiểm.

## 13. Thay đổi điều kiện thời gian là thay đổi hợp đồng khi timing có ý nghĩa

Một advice tracing có thể thêm ít chi phí CPU; điều đó không nhất thiết vi phạm contract nếu API không công bố timing chặt. Nhưng:
- Synchronous API bị biến thành asynchronous API.
- Async API bị block cho tới completion.
- Một method cần phản hồi trước deadline bị advice I/O block.
- Một callback được chuyển sang thread khác ngoài thread-affinity promise.
- Một iterator lazy bị advice tiêu thụ eagerly.
- Một resource bị đóng trước khi caller có cơ hội dùng.

Những thay đổi này có thể phá contract dù **giá trị cuối cùng** giống nhau.

### 13.1. `CompletionStage`: method return khác task completion

Với `CompletionStage<Receipt> submitAsync(...)`, method return một handle trước khi task hoàn tất. Around advice chỉ đo/try-catch `proceed()` không tự quan sát exceptional completion xảy ra sau đó.

Một observer trong suốt có thể đăng ký completion callback để đo nhưng phải cân nhắc:
- Trả stage **gốc** hay dependent stage?
- Callback có ném lỗi vào dependent stage không?
- Cancellation propagation có thay đổi không?
- Caller có so identity hoặc dùng API riêng của original stage không?
- Context có bị giữ quá lâu qua completion callback không?

### 13.2. `whenComplete` cũng là phép biến đổi nếu thay handle

`stage.whenComplete(...)` tạo một dependent stage. Nếu callback ném lỗi, dependent stage có thể có outcome khác original. Một advice chỉ muốn log mà return dependent stage cần chứng minh semantics phù hợp, không chỉ rằng cả hai có kiểu `CompletionStage<T>`.

### 13.3. Không coi async success khi chỉ nhận được future

Method `submitAsync` trả handle thành công nhưng future fail sau đó. Nếu advice báo “transaction success” ngay khi nhận handle, nó đã thay ý nghĩa success signal theo contract. Muốn audit completion, cần hook đúng thời điểm hoàn thành thật.

## 14. Stream, iterator và resource trả về

Một `Stream<Row>`, `Iterator<T>`, cursor hoặc publisher có hành vi xảy ra **sau khi method return**.

Một logging advice gọi `stream.count()` để ghi số phần tử rồi trả stream gốc có thể đã tiêu thụ stream. Caller gặp lỗi khi dùng terminal operation tiếp theo. Một advice chuyển stream thành list có thể thay lazy/eager semantics, memory footprint, thứ tự, timing exception và resource cleanup.

### 14.1. Ownership quyết định close

Nếu method trả stream mà caller chịu trách nhiệm `close()`, một advice không nên tự close trong `finally` ngay sau `proceed()` return. Advice chỉ kết thúc invocation, không có nghĩa caller đã tiêu thụ result.

### 14.2. Publisher có protocol riêng

Với reactive/streaming publisher, hợp đồng có thể gồm:
- Khi nào subscribe thật sự kích hoạt work?
- Số lần subscribe hợp lệ.
- Backpressure/demand.
- Ordering và terminal events.
- Error/cancellation propagation.

Một proxy chỉ giữ “return cùng publisher type” không chứng minh nó bảo toàn mọi protocol event, nhất là khi advice wrap publisher và tự subscribe.

## 15. Concurrency, locks và reentrancy

Một aspect dùng chung có thể có mutable fields như `lastStartNanos`, `lastResult`, `currentUser`. Nhiều invocations đồng thời có thể ghi đè chúng và làm result/logging sai, đồng thời giữ references ngoài ý định.

### 15.1. Shared advice state và data race

Một timer aspect lưu thời điểm bắt đầu vào field chung có thể tính nhầm duration khi thread B overwrite giá trị của A. Dùng state local theo invocation hoặc cơ chế context/synchronization phù hợp thay vì trộn những requests.

### 15.2. Per-target không đồng nghĩa thread-safe

Một target singleton có thể nhận nhiều threads. Aspect state per-target cũng được nhiều threads dùng chung. `int count++` không atomic; cần `AtomicInteger`, `LongAdder` hoặc synchronized invariant tùy yêu cầu.

### 15.3. Locking behavior có thể khác giữa proxy và target

`synchronized(proxy)` và `synchronized(target)` là hai monitors khác nhau nếu chúng là hai objects riêng. Nếu client trước đây phối hợp threads bằng target monitor, thay reference bằng proxy có thể phá assumptions về synchronization.

Tương tự, một synchronized method trên target chỉ khóa **target monitor** khi body chạy; handler có thể làm việc trước/sau ngoài lock đó. Không khẳng định một proxy giữ nguyên atomicity toàn bộ advice+method nếu không có synchronization contract.

### 15.4. Reentrancy và self-invocation

Một target method có thể gọi `this.otherMethod()`. Với delegating proxy, internal call không nhất thiết đi qua handler, nên một policy như metrics/security/retry gắn ở proxy inner có thể không chạy.

Ngược lại, advice gọi vào chính các method được pointcut chọn có thể tạo vòng đệ quy instrumentation. Substitutability đòi kiểm tra **đường call thực**, không chỉ matcher có thể chọn method theo tên.

### 15.5. ThreadLocal và async context

Một advice lưu principal/trace context trong `ThreadLocal` nhưng quên restore/remove có thể để request sau trên cùng pool thread nhìn nhầm dữ liệu cũ. Một async callback ở thread khác không tự được thừa hưởng context. Đó là tác động tới behavior/privacy dù return value có thể đúng.

## 16. Type visibility, reflection, annotation và serialization

### 16.1. Exact class checks

Một code:

~~~java
if (object.getClass() == Ledger.class) {
    // một nhánh chỉ chạy với đúng concrete class
}
~~~

không đi vào nhánh với JDK interface proxy, dù proxy thực hiện cùng interface. Đây là ranh giới hợp đồng: nếu client được phép đòi exact class, proxy có thể không thay thế được.

### 16.2. `instanceof` cũng phụ thuộc proxy mechanism

JDK proxy implements declared interfaces; nó có thể `instanceof Interface` nhưng không phải `instanceof ConcreteTarget`. Class-based proxy có thể là subclass tương thích với concrete class khi kỹ thuật đó được phép; binary weaving có thể giữ type identity. Phải kiểm tra **artifact và engine cụ thể**.

### 16.3. Reflection tìm annotation

Annotation có thể đặt trên interface, implementation method, class hoặc inheritance hierarchy. Handler của JDK proxy thường nhận một `Method` liên quan tới interface invocation; reflection trên proxy class có thể thấy metadata khác implementation. Một annotation được đọc ở nhầm nơi có thể làm policy đổi behavior dù method vẫn trả đúng result.

### 16.4. Serialization

Nếu caller serialize object theo concrete class schema hoặc record mapping, thay target bằng proxy có thể:
- Làm kiểu runtime trong payload khác.
- Thêm handler/interceptor references vào graph.
- Không còn thỏa yêu cầu serializable.
- Kéo theo phiên bản code và classloader khác.
- Làm thay đổi equality/identity sau deserialize.

Không cho rằng “proxy có cùng interface” nghĩa là JSON/object serialization luôn tương đương. Cần test round-trip và schema ở consumer boundary.

### 16.5. Native/AOT và runtime code generation

Trong môi trường AOT/native, runtime code generation hoặc reflection có thể bị giới hạn. Một JDK proxy hoặc agent instrument hoạt động trong JVM thường không bảo đảm tương thích tự động với mọi runtime đóng. Đây là một điều kiện triển khai cần xác minh chứ không phải phần cốt lõi của substitutability.

## 17. Những biến đổi advice có chủ đích và tiêu chí chấp nhận

Thay kết quả hoặc hành vi không tự “vi phạm LSP” nếu abstraction **đã được định nghĩa** để cho phép chính sách ấy. Câu hỏi là **hợp đồng ở biên nào**.

| Loại advice | Có thể thay đổi gì? | Điều cần công bố/kiểm |
| --- | --- | --- |
| **Logging/tracing** | Thời gian, I/O telemetry, context. | Không che lỗi business, không rò dữ liệu, bounded overhead. |
| **Metrics** | Shared counters, sampling, callback. | Không mutate result, thread-safe, đúng đơn vị đo. |
| **Authorization** | Từ chối một số inputs/callers. | Điều kiện quyền là một phần contract, không có bypass. |
| **Cache** | Bỏ qua target, trả giá trị lưu. | Freshness, identity, tenant isolation, side effects. |
| **Retry** | Nhiều target attempts, delays. | Idempotency, attempt limits, timeout, lỗi được retry. |
| **Fallback** | Exception thành value. | Domain meaning, degraded mode, không false success. |
| **Normalization** | Kết quả/arguments đổi dạng. | Postcondition, type, ordering, nullability. |
| **Transaction boundary** | Commit/rollback behavior. | Resource scope, propagation, failure semantics. |
| **Audit** | External write/notification. | Thời điểm success, khả năng lưu bền, privacy. |
| **Resource management** | Open/close/release. | Ownership, async/lazy result lifecycle. |

### 17.1. Tách API contract với instrumentation policy

Một interface có thể công bố rằng tất cả operations được audit; khi đó audit không phải chi tiết “vô hình”. Một interface khác chỉ hứa kết quả nghiệp vụ và coi telemetry là implementation detail. Nên mô tả những effects được bảo đảm để tránh lời hứa substitutability mơ hồ.

### 17.2. Bảo mật là bài toán trust boundary

Nếu authorization phụ thuộc một proxy nhưng caller có thể giữ target gốc hoặc tự gọi nội bộ bypass handler, enforcement có thể thiếu độ phủ. Bảo vệ invariant quan trọng ở trusted boundary thích hợp, sau đó dùng aspect hỗ trợ nhất quán và observability. Đừng tuyên bố mọi lời gọi đã được bảo vệ chỉ vì pointcut có tên `secure*`.

### 17.3. Advice ordering là một phần của hợp đồng quan sát

`Auth(Cache(Target))` và `Cache(Auth(Target))` không nhất thiết tương đương khi Cache short-circuit. `Retry(Metrics(Target))` và `Metrics(Retry(Target))` cũng khác đơn vị đếm. Phải khai precedence tường minh và test đường return/throw/skip.

## 18. Ma trận contract tests cho đối tượng gốc và đối tượng đã áp dụng aspect

Để kiểm tra substitutability, viết **một bộ hợp đồng** dùng được cho nhiều implementations, gồm raw target, decorator, proxy hoặc woven variant (trong phạm vi kỹ thuật).

### 18.1. Những test về kiểu và method result

| Test | Cần xác minh |
| --- | --- |
| Interface compatibility | Client chỉ biết interface có gọi đủ API được không? |
| Primitive `0`, `false`, `-1` | Advice giữ đúng sentinel hợp lệ? |
| `null` cho reference | Nullability contract đúng không? |
| `Optional.empty()` | Có bị đổi thành null hoặc false success không? |
| Collections/generics | Kiểu phần tử, order, mutability đúng? |
| Identity | `==` có được contract cho phép khác không? |
| Concrete cast | Client có yêu cầu concrete type không? |
| Equality/hashing | Reflexive/symmetric/transitive/hashCode consistent? |
| `toString`/reflection | Những quan sát được hứa có giữ không? |
| `void` | Side effect và error contract có giữ không? |

### 18.2. Exception và failure tests

- Target throw đúng loại; advice truyền lỗi gốc hay mapping được công bố.
- Exception có cause/diagnostic metadata cần thiết.
- Checked exceptions qua proxy không bị bọc ngoài ý định.
- Target lỗi trước side effect và sau side effect được phân loại đúng.
- Timeout/cancellation ở async API không bị biến thành “success”.
- Lỗi logger/metrics không che nghiệp vụ nếu policy là best effort.

### 18.3. State and side-effect tests

- Một lần deposit tăng đúng lượng và result bằng state sau mutation.
- Retry không nhân side effects trái hợp đồng.
- Cache hit không bỏ qua một side effect được bảo đảm.
- Caching mutable result không làm caller B nhìn thay đổi bất hợp pháp của caller A.
- Các concurrent increments/updates thỏa contract thread safety đã công bố.
- Resource owner đóng đúng thời điểm; advice không giữ target/stream quá lâu.

### 18.4. Call-path tests

- Caller gọi qua proxy.
- Caller giữ target trực tiếp.
- Target gọi `this.inner()`.
- Callback/method reference capture proxy hay target.
- Classloader/module/pointcut include/exclude đủ điều kiện.
- Nhiều aspects áp cùng join point theo thứ tự đã định.

Nếu một policy là **bắt buộc**, test phải chứng minh đường bypass không thể vi phạm invariant; không chỉ chứng minh một happy path qua proxy chạy thành công.

### 18.5. Async và lazy result tests

- Method trả stage còn pending; không block.
- Thành công/exception/cancellation sau method return.
- Original/dependent stage identity nếu được công bố.
- Streaming iterator chưa bị consumed trước caller.
- Resource close theo ownership, không theo lúc around advice return.
- Completion callbacks lỗi không phá outcome nếu chúng chỉ quan sát.

### 18.6. Snapshot so sánh raw và proxied có giới hạn

Một cách tiếp cận là khởi tạo hai targets tương đương, chạy cùng sequence commands trên raw và proxied, rồi so **observations theo contract**.

Nhưng đừng so trực tiếp results khi method dùng time, randomness, network hoặc side effects không thể tái chạy: cần test doubles, fixed clocks, deterministic schedulers và stable fixtures. Nếu proxy được thiết kế có retry/cache/fallback, phải đưa **khác biệt được phép** vào oracle, thay vì yêu cầu mọi output byte-for-byte giống nhau.

## 19. Tiêu chí kết luận “substitutable” ở từng ranh giới

Một checklist phê duyệt thực tế:

1. **Client abstraction:** client đang giữ interface/base class hay concrete implementation?
2. **Methods available:** proxy/decorator expose đủ operations được phép không?
3. **Type contract:** primitive/ref/null/generic tương thích không?
4. **Semantic return:** giá trị cùng ý nghĩa, kể cả sentinel và absence không?
5. **Side effects:** số lần và thứ tự thay đổi trạng thái có đúng không?
6. **Exception contract:** loại/cause/timing lỗi có giữ không?
7. **Identity/equality:** caller có dựa vào `==`, `equals`, `hashCode`, `getClass` không?
8. **Lifecycle:** resource ownership, close/dispose, GC retention có bị đổi không?
9. **Concurrency:** thread-safety, synchronized/monitor, reentrancy và ThreadLocal có phù hợp không?
10. **Async:** future identity, completion, cancellation và thread context đúng không?
11. **Lazy results:** stream/publisher/iterator có giữ protocol không?
12. **Proxy coverage:** mọi caller cần policy đi qua interceptor đúng không?
13. **Weaving coverage:** class và join point đã thật sự được weave đúng chưa?
14. **Ordering:** retry/cache/auth/metrics/transaction lồng nhau theo ngữ nghĩa nào?
15. **Security:** trusted boundary và các invariant bắt buộc được bảo vệ ở đâu?
16. **Performance budget:** startup/latency/cpu/memory giới hạn đã được đo không?
17. **Compatibility:** JDK, classloader, serialization, build/runtime toolchain?
18. **Tests:** cả happy path, empty, failure, direct-call, concurrent và async đều PASS?
19. **Rollback:** nếu một aspect làm sai contract, có thể vô hiệu hóa/rollback artifact an toàn không?
20. **Documentation:** các khác biệt cố ý so với raw target có được công bố rõ không?

### 19.1. Không đòi “giống hệt” nếu contract không yêu cầu

Một proxy tăng vài dòng log có thể vẫn thay thế hợp lệ nếu logging không phá chính sách latency/privacy và caller không được quyền dựa vào stack trace/identity cụ thể. Mục tiêu không phải loại mọi khác biệt vật lý, mà là bảo toàn **tập thuộc tính đã cam kết với client**.

### 19.2. Một aspect không “transparent” vẫn có thể có giá trị

Một retry hoặc authorization aspect có thể cố ý làm hành vi khác raw target. Khi đó nó phải được xem là một **biến thể có hợp đồng rõ**, không được quảng cáo như bản thay thế hoàn toàn không quan sát được sự khác biệt. Client phải biết outcome và boundary nào được bảo đảm.

## 20. Các lỗi tư duy thường gặp

**“Proxy implement cùng interface nghĩa là thay thế được hoàn toàn.”** Sai. Kiểu không chứng minh semantics, identity hoặc side effects.

**“`instanceof Interface` true thì `instanceof ConcreteTarget` cũng true.”** Không với JDK interface proxy.

**“`equals` và `hashCode` không quan trọng vì chỉ là Object methods.”** Sai khi object dùng làm key trong collections hoặc làm identity token.

**“Làm proxy.equal(target) true chắc chắn tốt hơn.”** Không nếu target.equal(proxy) false hoặc hash codes khác.

**“Giữ nguyên return value bảo đảm hành vi giữ nguyên.”** Không nếu advice đã mutate result hoặc chạy target nhiều lần.

**“Một result cùng kiểu thì contract được bảo toàn.”** Sai nếu `0`, empty, null, exception và future biểu diễn các outcome khác nhau.

**“`void` không có contract trả về nên skip target vô hại.”** Sai: side effects và exception vẫn là hợp đồng.

**“Retry thành công cuối cùng nghĩa là toàn bộ operation đúng.”** Không nếu đã lặp external side effects.

**“Cache hit có thể skip mọi inner advice mà không ảnh hưởng gì.”** Không nếu nó bỏ qua quyền/audit được bảo đảm hoặc trả dữ liệu stale trái contract.

**“Object proxy và target khóa trên cùng một monitor.”** Không nếu là hai objects riêng biệt.

**“Một method async return stage tức toàn bộ task thành công.”** Không; completion có thể fail về sau.

**“Serialization của target và proxy luôn tương đương.”** Không; runtime type và object graph khác nhau.

**“Bytecode weaving không tạo proxy nên chắc chắn không phá substitutability.”** Sai; code được dệt vẫn có thể thay error/return/ordering/timing.

**“Cứ test proxy happy path là đủ.”** Không; các vi phạm thường nằm ở negative paths, async, identity, retries, concurrency hoặc resource lifetime.

**“Chỉ cần đảo priority để sửa đường gọi trực tiếp target.”** Không; ordering không bù cho đường bypass interception.

## 21. Bài tập tự đánh giá có đáp án

### Câu 1 — Interface và concrete class

Một `Ledger` được bọc bằng JDK proxy triển khai `BalancePort`. Caller dùng `BalancePort` ổn, nhưng caller cast sang `Ledger` lỗi. Có mâu thuẫn không?

**Đáp án:** Không. Proxy có khả năng thay thế ở **interface boundary** khi behavior đúng, không phải concrete subtype của target.

### Câu 2 — Cùng kiểu, sai state

`deposit(5)` trả `int 999`, balance không đổi. Method signature hợp lệ, vậy là substitutable?

**Đáp án:** Không. Postcondition balance tăng 5 và return balance mới bị vi phạm.

### Câu 3 — Equality bất đối xứng

Proxy.equals(target) true nhưng target.equals(proxy) false. Hợp đồng nào sai?

**Đáp án:** Tính đối xứng của `Object.equals`; nếu hash codes không khớp còn có lỗi liên quan `hashCode`.

### Câu 4 — `Optional.empty()` và storage error

Advice bắt lỗi DB rồi trả empty Optional. Vì sao có thể sai?

**Đáp án:** Empty nghĩa là không có dữ liệu, còn lỗi DB nghĩa là không biết. Caller có thể thực hiện một hành động sai dựa trên absence giả.

### Câu 5 — Side effect khi retry

Một lệnh external `charge()` có response timeout sau commit, advice retry lần hai rồi trả OK. Kiểu đúng có đủ không?

**Đáp án:** Không; duplicate charge có thể phá đúng-một-lần, cần idempotency hoặc reconciliation.

### Câu 6 — Monitor

Caller từng dùng `synchronized(target)`; bây giờ dùng `synchronized(proxy)` trong khi worker khác vẫn khóa target. Có chắc cùng lock?

**Đáp án:** Không nếu target/proxy là hai objects khác nhau. Cần thiết kế synchronization boundary rõ.

### Câu 7 — Async identity

Advice trả `stage.whenComplete(callback)` thay stage gốc. Cùng `CompletionStage<T>`, vậy hợp đồng chắc chắn giống?

**Đáp án:** Không. Dependent stage có identity và error/cancellation behavior khác nếu callback hoặc policy ảnh hưởng completion.

### Câu 8 — Self-invocation

Pointcut chọn method inner, nhưng target.outer gọi `this.inner()` không qua proxy. Có phải pointcut sai?

**Đáp án:** Không nhất thiết. Trong mô hình delegating proxy, handler không nhận inner invocation; đó là khác biệt coverage/call path.

### Câu 9 — Stream được đo bằng count

Advice nhận stream, gọi `count()` để log rồi return cùng stream. Vì sao có thể không substitutable?

**Đáp án:** Terminal operation có thể tiêu thụ stream, caller không còn dùng được theo hợp đồng lazy.

### Câu 10 — Authorization

Một aspect chặn unauthorized callers, làm behavior của raw target khác đi. Có được dùng không?

**Đáp án:** Có thể, nếu authorization là **một phần của API/security contract** và được bảo đảm tại trusted boundary; không gọi nó hoàn toàn transparent đối với tất cả inputs.

### Câu 11 — Concrete annotations

Một tool đọc annotation trên implementation class; thay target bằng JDK proxy rồi reflection trên `proxy.getClass()` không thấy annotation đó. Bài học?

**Đáp án:** Runtime class của proxy khác implementation; metadata lookup phải theo nơi annotation thực sự khai báo và theo hợp đồng công cụ.

### Câu 12 — Contract tests

Một proxy trả đúng mọi happy-path values, nhưng khi target ném lỗi thì handler nuốt lỗi và return 0. Nên bổ sung test nào?

**Đáp án:** Negative tests cho exception type/cause và phân biệt exception với sentinel `0`, kết hợp assert state/side effects.

## Kết luận

**Khả năng thay thế của đối tượng sau khi áp dụng aspect** phải được xét ở **ranh giới hợp đồng mà client thực sự sử dụng**. Một interface proxy có thể thay thế target rất tốt cho các operations của interface, nhưng không tự có cùng concrete class, identity, equality, reflection hay lifecycle. Một engine weave trực tiếp có thể giữ nguyên object identity mà vẫn làm sai kết quả, ngoại lệ, side effects hoặc thời gian hoàn thành.

Với aspect quan sát, hãy ưu tiên **bảo toàn result/error, số lần tiếp tục, trạng thái nghiệp vụ và quyền sở hữu resource**, đồng thời tránh rò dữ liệu/context. Với aspect can thiệp chủ động như cache, retry, fallback và authorization, cần **công bố rõ khác biệt được phép** rồi xác minh toàn bộ precondition, postcondition, invariant, temporal behavior và failure contract. Một thiết kế AOP tốt không chỉ khiến caller có thể **gọi được** object đã bọc, mà khiến caller tiếp tục **tin đúng những điều abstraction đã hứa**.
