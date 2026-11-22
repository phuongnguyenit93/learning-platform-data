# Kế thừa nhiều interface và tính hợp lệ của phương thức hàm

Một **functional interface** trong Java có thể `extends` **nhiều interface khác nhau** mà vẫn nhận được lambda hoặc method reference. Điều quyết định không phải số interface cha, cũng không đơn giản là đếm các dòng khai báo có từ khóa `abstract`, mà là **hợp đồng phương thức trừu tượng cuối cùng sau khi tính đến kế thừa và quy tắc ghi đè**.

Ví dụ, hai interface cha cùng khai báo `void accept(String)` sẽ không buộc interface con phải có hai hành vi riêng: nếu các phương thức có chữ ký tương đương theo quy tắc Java, chúng cùng biểu diễn **một** hợp đồng. Nhưng nếu hai cha khai báo `void accept(String)` và `void accept(int)`, interface con có **hai** phương thức trừu tượng khác nhau; dù việc kế thừa có thể hợp lệ, interface con **không còn là functional interface**.

Bài học dựa vào các quy tắc của **Java Language Specification (JLS) `9.8, `9.4.1 và `9.9** vẫn áp dụng trong Java hiện đại. Ví dụ chạy đầy đủ dùng JDK 17+; các chức năng lambda, `@FunctionalInterface`, đa kế thừa interface và default method có từ Java 8. Những tính năng mới hơn được nêu rõ phiên bản khi cần.

## 1. Functional interface thực chất được xác định thế nào?

Functional interface là interface **không được khai báo `sealed`** và có đúng **một hợp đồng phương thức trừu tượng có ý nghĩa**, xét sau các quy tắc loại trừ và hợp nhất được Java xác định. Một interface có thể tự khai báo phương thức đó hoặc thừa hưởng nó từ một hay nhiều interface cha.

Để đánh giá theo JLS `9.8:

1. Xét các phương thức trừu tượng là thành viên của interface, **không tính những phương thức có cùng chữ ký với phương thức instance `public` của `Object`** như `equals(Object)`, `hashCode()` và `toString()`.
2. Trong nhóm còn lại, cần tồn tại một phương thức có **chữ ký là subsignature** của các phương thức còn lại và có **kiểu trả về có thể thay thế** (*return-type-substitutable*) cho các kiểu trả về còn lại.
3. Nếu hai phương thức kế thừa đụng nhau theo cách không hợp lệ, như cùng erasure nhưng không thỏa điều kiện ghi đè, hoặc có kiểu trả về xung đột, Java có thể từ chối **chính khai báo interface con**.
4. Nếu interface con hợp lệ nhưng còn **nhiều hợp đồng trừu tượng khác nhau**, nó là interface thông thường, **không thể lấy lambda làm instance của nó**.
5. Các phương thức `default`, `static` và `private` không tạo thêm hợp đồng trừu tượng cần lambda cài đặt. Tuy nhiên, kế thừa các phương thức `default` có thể tạo ra **xung đột phải giải quyết**.

### `@FunctionalInterface` kiểm tra ở thời điểm biên dịch

~~~java
@FunctionalInterface
interface StringAction {
    void accept(String text);

    default void acceptTrimmed(String text) {
        accept(text.trim());
    }

    static StringAction noop() {
        return text -> {};
    }
}
~~~

Đây là đoạn **khai báo kiểu**, đặt tại phạm vi lớp hoặc tệp Java; không phải cả một chương trình độc lập. Java kiểm tra rằng interface có đúng một hợp đồng trừu tượng là `accept(String)`. Default method `acceptTrimmed` và static factory `noop` không làm mất tính functional.

- Gắn `@FunctionalInterface` **không biến** interface nhiều phương thức trừu tượng thành functional interface; nếu sai hợp đồng, compiler báo lỗi.
- Không có annotation, interface vẫn có thể là functional interface theo định nghĩa ngôn ngữ. Nên dùng annotation khi API được thiết kế cố ý cho lambda/method reference, để thay đổi về sau không vô tình phá hợp đồng.
- Functional interface không đồng nghĩa với “chỉ có một method hiện ra trong IDE”; nó có thể có thêm default/static/private method, các method tương đương của `Object` và các method kế thừa phù hợp.

## 2. Kế thừa hai phương thức trừu tượng trùng hợp đồng: vẫn hợp lệ

Hai interface cha:

~~~java
interface AuditA {
    void accept(String message);
}

interface AuditB {
    void accept(String message);
}
~~~

Interface con:

~~~java
@FunctionalInterface
interface Audit extends AuditA, AuditB {
}
~~~

`Audit` là functional interface vì hai phương thức trừu tượng có **cùng chữ ký**; trong hệ thống kiểu chúng cùng quy về một hợp đồng `void accept(String)`. Không cần khai báo lại `accept` trong `Audit`.

~~~java
Audit audit = message -> System.out.println(message);
audit.accept("ok");
~~~

Đoạn dùng đặt trong phương thức với các interface ở trên. Lambda cài đặt hành vi cho **cả hai đường kế thừa**. Đây là khả năng thiết yếu khi tích hợp các API nhỏ có cùng hợp đồng.

### Cùng chữ ký quan trọng hơn cùng tên

~~~java
interface TextSink {
    void accept(String value);
}

interface NumberSink {
    void accept(int value);
}

// HỢP LỆ ở mức khai báo một interface thông thường:
interface TwoSinks extends TextSink, NumberSink {
}
~~~

`TwoSinks` có hai phương thức **overload** theo tham số, nên **không phải** functional interface. Nếu thêm `@FunctionalInterface`, compiler báo lỗi. Cũng không thể gán `TwoSinks x = value -> ...;` vì một lambda không được dùng để cài đặt đồng thời hai hợp đồng độc lập. Muốn sử dụng interface này, tạo lớp hoặc lớp vô danh cài đặt đủ hai phương thức, hoặc thiết kế lại API thành hai callback riêng nếu mục đích chính là lambda.

**Không nên khắc phục bằng cách bỏ annotation.** Bỏ `@FunctionalInterface` chỉ làm mất cảnh báo có chủ đích; nó không sửa thực tế interface có hai abstract methods.

## 3. Kiểu trả về hiệp biến (covariant return): hai cha có thể ghép thành một

Các interface cha có cùng tên phương thức, cùng tham số, nhưng kiểu trả về khác nhau:

~~~java
interface NumericA {
    Number read();
}

interface NumericB {
    Integer read();
}

@FunctionalInterface
interface NumericSource extends NumericA, NumericB {
}
~~~

Vì `Integer extends Number`, kiểu trả về `Integer` **có thể thay thế** cho `Number`. `NumericSource` vẫn hợp lệ và có một hợp đồng hàm. Đối tượng trả `Integer` cũng đáp ứng yêu cầu của cha `NumericA`.

~~~java
NumericSource source = () -> 42;
Integer exact = source.read();
Number general = source.read();
~~~

Đoạn khai báo là minh họa trong một phương thức với các interface phía trên; Java boxing số `42` thành `Integer` theo kiểu đích. Với trường hợp cùng chữ ký này, kiểu trả về hiệu lực của phương thức ở `NumericSource` là kiểu cụ thể hơn, `Integer`.

### Trả về không tương thích: lỗi ngay tại interface con

~~~java
interface ReadNumber {
    Number read();
}

interface ReadText {
    String read();
}

// KHÔNG BIÊN DỊCH:
interface BrokenSource extends ReadNumber, ReadText {
}
~~~

Cùng chữ ký `read()` nhưng không có kiểu trả về nào trong hai kiểu `Number` và `String` có thể thay thế cho kiểu còn lại. Java không thể tạo một hợp đồng ghi đè hợp lệ, nên **bản thân `BrokenSource` là lỗi biên dịch**. Không thể “sửa” bằng một lambda có biểu thức trả `Object`, vì `Object` còn ít cụ thể hơn.

Điểm phân biệt khi chẩn đoán:

| Trường hợp | Interface con có hợp lệ? | Có phải functional interface? |
| --- | --- | --- |
| Hai `void accept(String)` | Có | Có |
| `Number read()` + `Integer read()` | Có | Có |
| `Number read()` + `String read()` | Không | Không xét gán lambda vì interface đã lỗi |
| `void accept(String)` + `void accept(int)` | Có | Không; có hai abstract methods khác nhau |
| Một abstract method + nhiều default/static methods không xung đột | Có | Có |

**Lưu ý:** Kiểu trả về khác nhau **không phải là overload**. Java phân biệt overload chủ yếu bằng danh sách tham số/chữ ký; hai phương thức chỉ khác return type không tự tạo được hai overload hợp lệ.

## 4. Generic và kế thừa: xét sau khi thay thế kiểu

Functional interface có thể mang tham số kiểu. Khi một interface con chuyên biệt hóa interface cha, kiểu của phương thức được nhìn theo đối số kiểu đã chỉ định:

~~~java
interface Mapper<T> {
    T transform(T input);
}

@FunctionalInterface
interface TextMapper extends Mapper<String> {
}
~~~

`TextMapper` có hợp đồng `String transform(String input)`, vì `T` đã được thay bằng `String`. Cách dùng:

~~~java
TextMapper normalize = String::trim;
String text = normalize.transform(" Java "); // "Java"
~~~

Tránh hiểu rằng vì bản gốc `Mapper<T>` có type parameter nên JVM tạo thêm abstract method riêng trong `TextMapper`. Với thiết kế này, vẫn chỉ có một phương thức hàm; cơ chế generic và bridge methods của Java xử lý việc tương thích sau type erasure ở mức biên dịch/runtime.

### Cùng erasure nhưng tham số generic xung đột

Ví dụ **cố ý sai, không biên dịch**:

~~~java
interface A {
    void save(java.util.List<String> values);
}

interface B {
    void save(java.util.List<Integer> values);
}

interface Broken extends A, B {
}
~~~

Hai tham số `List<String>` và `List<Integer>` không biểu thị một cùng hợp đồng có thể ghi đè nhau ở đây, nhưng cùng xóa kiểu về `List` khi *type erasure*. Đây là xung đột tên theo erasure, không phải hai overload chạy độc lập. Đừng thiết kế API đa kế thừa bằng cách hy vọng Java chọn đúng dựa trên type argument generic đã bị xóa.

Khi xử lý generic trong hierarchy phức tạp, **không chỉ đếm tên method**, hãy xác định chữ ký sau khi thay thế type parameter, quan hệ subsignature, kiểu trả về và xung đột erasure. Nếu cần hai ý nghĩa xử lý khác nhau, dùng tên thao tác khác nhau hoặc tách callback thành hai contract rõ ràng.

## 5. Phương thức từ `Object` không làm tăng số phương thức trừu tượng

Mọi đối tượng Java đều có các phương thức cơ bản như `equals`, `hashCode`, `toString`. JLS `9.8` loại các phương thức có cùng chữ ký với **public instance methods** của `Object` khi xác định hợp đồng functional interface.

~~~java
interface ObjectSignatures {
    boolean equals(Object other);
    int hashCode();
    String toString();
}

@FunctionalInterface
interface Handler extends ObjectSignatures {
    void handle(String value);
}
~~~

`Handler` hợp lệ: phương thức hàm thực sự cần cài đặt là `void handle(String)`. Có thể dùng:

~~~java
Handler h = value -> System.out.println("handle=" + value);
h.handle("ok");
~~~

Đây là ví dụ trong phương thức, dựa trên khai báo interface ở trên. Các phương thức `equals/hashCode/toString` vẫn có hành vi `Object` tương ứng của đối tượng lambda tại runtime; việc loại chúng khỏi phép đếm SAM **không có nghĩa** chúng không tồn tại.

**Giới hạn chính xác:** JLS nói *public instance methods* của `Object`, không phải mọi method trong `Object`. Chẳng hạn `clone()` vốn là `protected` trong `Object`; nếu interface công khai khai báo một phương thức `clone()` có chữ ký thích hợp, đừng tùy tiện bỏ nó khỏi phép đếm. Tương tự, interface không được định nghĩa một **default method** tương đương `equals(Object)` hoặc `toString()` để “thay” hành vi chuẩn của `Object`.

## 6. Default method: không tạo SAM mới nhưng có thể gây xung đột kế thừa

Các `default` method là phương thức có implementation. Khi không xung đột, chúng giúp nhiều interface cha cung cấp hành vi dùng chung mà interface con vẫn giữ một abstract method.

Ví dụ có hai cha cùng cung cấp `default String label()`:

~~~java
interface Left {
    default String label() { return "L"; }
}

interface Right {
    default String label() { return "R"; }
}

// KHÔNG BIÊN DỊCH:
interface Broken extends Left, Right {
    void run();
}
~~~

`Broken` gặp xung đột **hai default methods cùng chữ ký được kế thừa**. Java không mặc định chọn cha ở bên trái hay bên phải trong `extends`. Vì vậy dù `run()` là abstract method duy nhất cần callback cài đặt, **khai báo interface vẫn lỗi** trước khi xét lambda.

Cách giải quyết rõ ràng:

~~~java
@FunctionalInterface
interface Resolved extends Left, Right {
    void run();

    @Override
    default String label() {
        return Left.super.label() + Right.super.label();
    }
}
~~~

Trong `Resolved`, override `label()` đã giải quyết xung đột, và chỉ còn `run()` là hợp đồng trừu tượng; interface con là functional interface:

~~~java
Resolved job = () -> System.out.println("resolved-run");
job.run();
System.out.println(job.label()); // "LR"
~~~

**Một abstract method và một default method cùng chữ ký từ hai cha cũng có thể xung đột.** Chẳng hạn cha A khai báo `void run();`, cha B khai báo `default void run() { ... }`; không nên dựa vào quy tắc “default thắng abstract”. Khi kế thừa tạo đụng độ, interface con phải giải quyết với khai báo override phù hợp. Bản chất vấn đề là hợp đồng kế thừa, không đơn thuần là số method trừu tượng.

### Default, static, private và quan hệ kế thừa

| Loại method | Interface con có kế thừa? | Tính vào hợp đồng SAM? | Điểm cần nhớ |
| --- | --- | --- | --- |
| Abstract method | Có nếu đáp ứng quy tắc ghi đè | Có, sau khi gộp theo JLS | Có thể nhiều khai báo nhưng một hợp đồng |
| Default instance method | Có nếu không bị override và không xung đột | Không | Hai default cùng chữ ký có thể buộc override |
| Static method | Không được kế thừa như instance method | Không | Gọi qua **tên interface khai báo** |
| Private method trong interface (Java 9+) | Không được kế thừa | Không | Dùng làm helper nội bộ cho default/static methods |
| Phương thức tương đương public instance method của `Object` | Có quy tắc đặc biệt | Không | `equals`, `hashCode`, `toString` |

Các quy tắc static/default của interface vẫn hữu ích trong các thư viện và ứng dụng Java hiện đại; tránh nhầm chúng với một kiểu đa kế thừa implementation theo thứ tự ưu tiên tự động.

## 7. Chương trình đầy đủ: sáu trường hợp hợp lệ trong cùng một tệp

Ví dụ sau tự chứa, chạy được với **JDK 17+**. Nó cho thấy hai cha cùng chữ ký, hai kiểu return hiệp biến, generic specialization, Object methods, default-method conflict được giải quyết và static method factory. Trong ví dụ, mọi interface lồng nhau được khai báo trong cùng tệp nên không cần tạo thêm tệp.

Lưu dưới tên **FunctionalInheritanceDemo.java**:

~~~java
import java.util.*;
import java.util.function.*;

public class FunctionalInheritanceDemo {
    interface AuditA { void accept(String message); }
    interface AuditB { void accept(String message); }

    @FunctionalInterface
    interface Audit extends AuditA, AuditB {
        default String kind() { return "audit"; }
        static Audit silent() { return message -> {}; }
    }

    interface NumericA { Number read(); }
    interface NumericB { Integer read(); }

    @FunctionalInterface
    interface NumericSource extends NumericA, NumericB { }

    interface Mapper<T> { T transform(T value); }

    @FunctionalInterface
    interface TextMapper extends Mapper<String> { }

    interface ObjectSignatures {
        boolean equals(Object other);
        int hashCode();
        String toString();
    }

    @FunctionalInterface
    interface Handler extends ObjectSignatures {
        void handle(String value);
    }

    interface Left {
        default String label() { return "L"; }
    }

    interface Right {
        default String label() { return "R"; }
    }

    @FunctionalInterface
    interface Resolved extends Left, Right {
        void run();

        @Override
        default String label() {
            return Left.super.label() + Right.super.label();
        }
    }

    public static void main(String[] args) {
        Audit audit = text -> System.out.println("audit=" + text);
        audit.accept(audit.kind());

        NumericSource source = () -> 42;
        System.out.println("number=" + source.read());

        TextMapper mapper = String::trim;
        System.out.println("text=" + mapper.transform(" Java "));

        Handler handler = text -> System.out.println("handle=" + text);
        handler.handle("ok");

        Resolved resolved = () -> System.out.println("resolved-run");
        resolved.run();
        System.out.println("label=" + resolved.label());

        Audit.silent().accept("ignored");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 FunctionalInheritanceDemo.java
java FunctionalInheritanceDemo
~~~

Stdout **đã xác minh bằng biên dịch và thực thi**:

~~~text
audit=audit
number=42
text=Java
handle=ok
resolved-run
label=LR
~~~

Giải thích các quan hệ kế thừa trong chương trình:

1. `Audit` thừa hưởng hai abstract methods `accept(String)` trùng chữ ký, nên lambda `text -> ...` chỉ cần một hành vi. Default method `kind()` và static factory `silent()` không làm tăng số abstract methods.
2. `NumericSource` nhận hai hợp đồng `Number read()` và `Integer read()` có return hiệp biến; lambda `() -> 42` trả `Integer` hợp lệ.
3. `TextMapper` kế thừa `Mapper<T>` sau khi thay `T = String`, method reference `String::trim` đáp ứng `String transform(String)`.
4. `Handler` loại các chữ ký tương đương public methods của `Object` khỏi phép đếm SAM; `handle` là thao tác duy nhất lambda phải thực hiện.
5. `Resolved` override `label()` để giải quyết hai default method trùng chữ ký. Nó vẫn có một abstract method `run()` để lambda cài đặt.
6. `Audit.silent()` là static factory trả về một lambda không có side effect; vì không in gì nên dòng cuối không bổ sung stdout.

Các trường hợp **cố ý sai** ở những phần khác chỉ phục vụ phân tích lỗi biên dịch; **không đưa chúng vào cùng tệp demo**.

## 8. “Interface hợp lệ” và “functional interface hợp lệ” là hai câu hỏi

Một số người chỉ kiểm tra có đặt được `@FunctionalInterface` không rồi kết luận interface kế thừa sai. Cần tách hai cấp đánh giá.

### Cấp 1: bản thân khai báo interface có hợp lệ không?

Kiểm tra xung đột giữa cha mẹ trước:

- Hai phương thức cùng tên và cùng thông số nhưng kiểu trả về không có quan hệ cho phép ghi đè -> lỗi.
- Hai phương thức có cùng erasure nhưng không thể override nhau -> lỗi name clash.
- Hai default methods hoặc default với abstract method có chữ ký override-equivalent từ hai đường kế thừa mà chưa được giải quyết -> lỗi.
- Những ràng buộc chung về static/default, visibility, tên method, sealed hierarchy và generic vẫn áp dụng.

Nếu **Cấp 1 không qua**, không có kiểu đích hợp lệ để tạo lambda.

### Cấp 2: nếu interface hợp lệ, nó có phải functional interface không?

Lấy nhóm abstract methods còn lại, trừ chữ ký public instance methods của `Object`, rồi xét có thể quy về một functional descriptor hợp lệ hay không. Nếu vẫn có hai phương thức độc lập, interface có thể được triển khai bằng lớp nhưng không thể được dùng trực tiếp làm target type cho một lambda.

Ví dụ:

~~~java
interface CanRead {
    String read();
}

interface CanWrite {
    void write(String text);
}

// Hợp lệ nhưng KHÔNG PHẢI functional interface:
interface Store extends CanRead, CanWrite {
}
~~~

`Store` định nghĩa cả `read()` và `write(String)`; một lambda không thể biểu diễn cả hai. Đây không phải lỗi thiết kế nếu Store thực sự đại diện một đối tượng có hai hành vi. Nhưng nếu mục tiêu là callback, lựa chọn rõ ràng hơn là truyền hai functional interfaces riêng biệt hoặc thiết kế hợp đồng chỉ có một thao tác trừu tượng.

## 9. `throws` và chữ ký phương thức hàm khi kế thừa nhiều nguồn

Khi hai abstract methods tương đương nhau về chữ ký và kiểu trả về, **khác biệt `throws` không tự động làm interface con lỗi**. Tuy nhiên, hợp đồng phương thức hàm dùng cho lambda còn có tập checked exceptions được tính từ các phương thức kế thừa; lambda phải phù hợp với hợp đồng có thể dùng an toàn qua mọi đường tham chiếu.

Ví dụ minh họa:

~~~java
interface MayThrow {
    String load() throws java.io.IOException;
}

interface NoCheckedThrow {
    String load();
}

@FunctionalInterface
interface CombinedLoad extends MayThrow, NoCheckedThrow {
}
~~~

`CombinedLoad` vẫn là functional interface; lambda `CombinedLoad load = () -> "ok";` là hợp lệ. Nhưng đừng mặc định rằng lambda của `CombinedLoad` được ném `IOException` chỉ vì **một** cha có khai báo đó: đường gọi từ `NoCheckedThrow` không cho phép checked exception ấy. Với tổ hợp này, lambda không thể làm `throw new IOException()` không xử lý trong thân hàm.

Trong chương trình thật, hãy xác định chính sách lỗi tại tầng API: bắt và xử lý checked exception, chuyển sang kết quả nghiệp vụ có cấu trúc, hoặc thiết kế functional interface có `throws` phù hợp với nơi tiêu thụ. Không tạo nhiều đường kế thừa chỉ để “né” kiểm tra exception.

## 10. Marker interface, intersection type và `sealed`

### Kế thừa marker interface

Một marker interface không khai báo thêm abstract method có thể được ghép với một functional interface:

~~~java
@FunctionalInterface
interface TaggedTask extends Runnable, java.io.Serializable {
}
~~~

`TaggedTask` có một hợp đồng `void run()`; `Serializable` không đưa thêm phương thức trừu tượng. Lambda `TaggedTask task = () -> System.out.println("run");` là hợp lệ. Đây là ví dụ thể hiện hợp đồng kế thừa; khi xây dựng ứng dụng, **không nên chọn serialize lambda để làm định dạng lưu trữ hoặc giao tiếp bền vững** vì hình thức/định danh triển khai lambda có thể thay đổi khi cập nhật code.

Java còn cho phép *intersection type* ở một số ngữ cảnh, chẳng hạn `(Runnable & Serializable) () -> System.out.println("x")`. Khi phần giao các kiểu tạo ra được một functional interface type, lambda có thể khớp với intersection. Cơ chế này hữu ích để hiểu đặc tả, nhưng trong API phổ thông một interface có tên rõ ràng thường dễ đọc và bảo trì hơn.

### `sealed interface` không phải functional interface

Từ Java 17, `sealed interface` là công cụ hiện hành để giới hạn các kiểu trực tiếp được phép triển khai/mở rộng. Theo JLS hiện đại, **sealed interface không được xem là functional interface**, kể cả khi chỉ khai báo một abstract method. Không dựa vào việc có một phương thức để gán lambda cho một sealed interface; sealed hierarchy nhằm kiểm soát tập kiểu triển khai, trong khi lambda có cơ chế sinh kiểu triển khai riêng.

Tóm lại, trước khi gán lambda vào interface con, phải xét cả các modifier và ràng buộc ngôn ngữ của interface, chứ không chỉ số lượng chữ ký.

## 11. Cách đánh giá một thiết kế đa kế thừa thực tế

Khi gặp interface kế thừa nhiều cha trong một codebase Java hiện đại, có thể kiểm tra theo thứ tự:

1. **Ghi lại các abstract methods** (kể cả inherited). Đối chiếu method name, số/kiểu tham số, type parameters và kiểu trả về.
2. **Bỏ những phương thức khớp public instance methods của `Object`** khỏi phép đếm hợp đồng chức năng.
3. **Gộp những chữ ký override-equivalent** nếu đáp ứng subsignature và return-type-substitutable; đừng suy luận chỉ dựa vào tên.
4. **Phát hiện xung đột** return type, cùng erasure, default methods và abstract/default. Đây là các lỗi có thể làm chính interface không biên dịch.
5. **Kiểm tra số hợp đồng trừu tượng còn lại**. Một hợp đồng -> ứng viên functional interface; nhiều hợp đồng -> interface thông thường.
6. **Kiểm tra ràng buộc bổ sung**: non-sealed, throws của function descriptor, generic parameterization, visibility và target type của lambda.
7. **Gắn `@FunctionalInterface`** cho API được chủ đích dùng với lambda và biên dịch để IDE/compiler phát hiện thay đổi phá hợp đồng.
8. **Kiểm thử bằng ví dụ nhỏ** khi hierarchy phức tạp. Dùng compiler thật với đúng JDK release mục tiêu; không dựa hoàn toàn vào mô tả trực giác “một phương thức”.

### Lưu ý với thư viện công khai

Một interface hiện là functional interface nhưng kế thừa thêm phương thức trừu tượng mới trong phiên bản sau có thể không còn dùng được với các lambda của người tiêu dùng. Đây là **thay đổi hợp đồng nguồn** đáng quan tâm. Nếu cần mở rộng API, cân nhắc thêm default method có implementation hợp lý hoặc tạo giao diện chuyên biệt mới thay vì tự ý thêm abstract method vào SAM hiện hữu. Đừng tùy tiện thêm default method trùng chữ ký method đã có ở một interface cha khác: thay đổi tưởng như không bắt người gọi cài thêm method vẫn có thể tạo **default conflict** trong hierarchy của họ.

## 12. Những lỗi thường gặp

| Nhận định sai / mã có vấn đề | Nguyên nhân | Cách hiểu hoặc xử lý đúng |
| --- | --- | --- |
| “Cứ `extends` hai interface thì không thể là SAM” | Đếm cha thay vì đếm hợp đồng | Hai abstract methods tương đương vẫn có thể tạo một SAM |
| “Hai method cùng tên luôn là một” | Bỏ qua tham số/kiểu generic | `run(String)` và `run(int)` là hai hợp đồng |
| “Hai return type khác nhau chắc chắn lỗi” | Bỏ qua covariance | `Integer` có thể thay thế `Number`; hai kiểu không tương thích mới xung đột |
| “Interface khai báo được nghĩa là functional” | Trộn tính hợp lệ của interface và của SAM | Interface có `read()` và `write()` hợp lệ nhưng không có một SAM |
| “Cứ xóa `@FunctionalInterface` là dùng lambda được” | Annotation không tạo ra quy tắc lambda | Phải sửa số hợp đồng thực tế hoặc thiết kế target type |
| “Default method luôn tự thắng abstract method cùng tên” | Java cần giải quyết xung đột giữa đường kế thừa | Override tường minh trong interface con khi xung đột |
| “`static` method từ cha được kế thừa như instance method” | Interface static methods không được kế thừa | Gọi qua tên interface khai báo |
| “`equals/hashCode/toString` làm interface mất tính functional” | Các public instance signatures của `Object` bị loại khỏi phép đếm SAM | Chỉ tính abstract method còn lại |
| “`List<String>` và `List<Integer>` là overload độc lập” | Cùng erasure và không thể override | Thiết kế tên/hợp đồng khác, không dựa vào type erasure |
| “Cả hai cha có `throws` thì lambda cứ ném mọi checked exception được” | Function type phải an toàn qua các hợp đồng kế thừa | Kiểm tra tập ngoại lệ hợp lệ của descriptor |
| “Một `sealed interface` với một method là SAM” | JLS loại sealed interface khỏi định nghĩa functional | Dùng non-sealed functional interface cho lambda, sealed hierarchy cho mô hình kiểu đóng |

## 13. Tự kiểm tra

1. Hai interface cha đều có `void notify(String text)`. Khi con `extends` cả hai, vì sao nó vẫn có thể nhận một lambda?
2. Nếu cha A có `String value()` còn cha B có `Object value()`, con có thể là functional interface không? Thay `Object` bằng `Integer` thì sao?
3. Một interface con kế thừa `void save(String)` và `void save(int)` có thể khai báo và biên dịch không? Có được dùng trực tiếp với lambda không?
4. Vì sao `@FunctionalInterface` hữu ích dù không bắt buộc? Điều gì xảy ra khi bổ sung một abstract method không tương đương?
5. Tại sao kế thừa hai `default String label()` gây lỗi, và override trong con giải quyết vấn đề như thế nào?
6. Nếu một interface kế thừa `Runnable` và `Serializable`, vì sao nó vẫn có một hợp đồng trừu tượng? Dùng lambda được có đồng nghĩa nên serialize lambda bền vững không?
7. Vì sao `boolean equals(Object)` không tính là abstract method của SAM nhưng `Object clone()` khai báo trong interface có thể làm thay đổi phép đếm?
8. Hãy viết `@FunctionalInterface interface StringMapper extends Mapper<String>` và lambda thực hiện `trim`. Giải thích functional descriptor sau khi thay `T`.
9. Với `interface A { Number read(); }` và `interface B { Integer read(); }`, kiểu trả về hiệu lực của con là gì? Vì sao?
10. Một interface có `String load() throws IOException` và một interface có `String load()` được kế thừa cùng lúc. Khi cài lambda, điều gì cần kiểm tra về checked exceptions?

## Tài liệu chuẩn

- [Java Language Specification SE 26, `9.8 Functional Interfaces và `9.9 Function Types](https://docs.oracle.com/javase/specs/jls/se26/jls26.pdf)
- [Java Language Specification SE 26, `9.4.1 Interface Inheritance and Overriding](https://docs.oracle.com/javase/specs/jls/se26/jls26.pdf)
- [Java SE 17, annotation `@FunctionalInterface`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/FunctionalInterface.html)
- [Java SE 17, các functional interfaces chuẩn trong `java.util.function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)

**Điều cần giữ khi đọc một hierarchy:** Xác định phương thức hàm theo **chữ ký ghi đè, kiểu trả về, quy tắc kế thừa và các loại trừ do JLS quy định**. Một interface có nhiều cha vẫn có thể là đích lambda rất tốt; điều quan trọng là cuối cùng nó có đúng **một hợp đồng hành vi hợp lệ** để lambda thực hiện.
