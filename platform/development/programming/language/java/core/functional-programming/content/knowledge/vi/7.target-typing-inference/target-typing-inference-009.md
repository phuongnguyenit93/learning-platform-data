# Không dựa vào lớp triển khai hoặc danh tính tham chiếu của lambda

## 1. Vấn đề cần hiểu

Trong Java, một biểu thức lambda cung cấp cách triển khai phương thức trừu tượng duy nhất của một **functional interface**. Trình biên dịch xác định **kiểu đích (target type)** từ ngữ cảnh sử dụng, chẳng hạn `IntUnaryOperator`, `Predicate<String>`, `Runnable` hoặc `Supplier<T>`.

Giá trị của biểu thức lambda là một tham chiếu đến đối tượng có thể được dùng thông qua functional interface đó. Tuy nhiên, **Java không cam kết tên lớp triển khai, cấu trúc lớp, việc cấp phát đối tượng mới ở mỗi lần đánh giá lambda hay việc tái sử dụng một đối tượng đã tồn tại**. Đây là điểm quan trọng khi học về kiểu đích và suy luận kiểu: kiểu được phép dùng trong chương trình là giao diện chức năng và hợp đồng của phương thức SAM (single abstract method), chứ không phải lớp ẩn phía sau lambda.

Ví dụ:

```java
IntUnaryOperator square = x -> x * x;
int result = square.applyAsInt(4); // 16
```

Điều được bảo đảm là có thể gọi `applyAsInt` và nhận kết quả theo phần thân lambda. Không có hợp đồng nào yêu cầu `square.getClass().getName()` có một tên cố định hoặc hai lần tạo lambda phải có cùng/khác tham chiếu.

## 2. Đâu là hợp đồng ổn định, đâu là chi tiết triển khai?

| Có thể dựa vào | Không nên dựa vào |
| --- | --- |
| Lambda tương thích với functional interface do ngữ cảnh xác định. | Tên lớp, tên phương thức tổng hợp, gói hoặc định dạng tên của lớp sinh ra cho lambda. |
| Gọi phương thức SAM thực hiện hành vi mà lambda mô tả. | `getClass()`, các phương thức phản chiếu và cấu trúc bytecode của lớp triển khai luôn giống nhau giữa JVM hoặc lần build. |
| Một biến khác trỏ tới **chính cùng tham chiếu** thì `a == alias` là `true`. | Đánh giá lại lambda phải tạo đối tượng mới, hay JVM chắc chắn sẽ cache và tái sử dụng đối tượng. |
| Cú pháp lambda được kiểm tra và suy luận dựa trên **target type**. | Hai lambda có cùng phần thân sẽ có cùng class, cùng identity hay bằng nhau theo `equals`. |
| Các lời gọi hợp lệ của API chức năng như `test`, `apply`, `get`, `run`. | `toString()`, `hashCode()`, `System.identityHashCode()` phản ánh ý nghĩa nghiệp vụ của hàm. |

**Đừng nhầm tính tương đương hành vi với tính đồng nhất đối tượng.** Hai hàm đều trả `x + 2` có thể cho cùng kết quả đối với mọi `x`, nhưng điều đó không buộc `f == g` hoặc `f.equals(g)` phải là `true`. Ngược lại, một đối tượng lambda có thể giữ trạng thái hoặc tham chiếu tới đối tượng có trạng thái, nên không thể suy ra toàn bộ ngữ nghĩa chỉ từ một lần gọi thử.

## 3. Vì sao lớp triển khai và identity không ổn định?

Theo mô hình ngôn ngữ Java (JLS `15.27.4), việc đánh giá lambda có thể tạo một đối tượng mới hoặc trả về một đối tượng hiện có; JVM có quyền tối ưu miễn là hành vi chương trình được giữ đúng. Với các lambda **không capture**, runtime có thể tái sử dụng instance; với lambda **có capture**, cách tạo instance vẫn là vấn đề triển khai. Không suy diễn quy tắc `new mỗi lần` từ cú pháp `->`.

Các bản OpenJDK hiện đại thường hiện thực lambda bằng cơ chế `invokedynamic` và `LambdaMetafactory`; JVM có thể sử dụng các lớp được tạo động hoặc hidden class. Cơ chế và tên lớp cụ thể có thể thay đổi theo phiên bản JDK, JVM, trình biên dịch và tối ưu hóa. Đây là lời giải thích về triển khai phổ biến, **không phải API để chương trình phụ thuộc**.

Ba trường hợp cần phân biệt:

1. **Alias của cùng tham chiếu:** `IntUnaryOperator alias = f;` luôn làm `f == alias` đúng, bởi đây là phép so sánh hai biến trỏ cùng đối tượng.
2. **Đánh giá lại một lambda expression:** không có quyền giả định rằng đối tượng được tạo mới ở mỗi lượt, kể cả khi phần thân không capture.
3. **Hai lambda expression hoặc method reference:** dù cú pháp hay kết quả quan sát giống nhau, không có quy tắc chung rằng class/identity/`equals` của chúng bằng nhau.

Không thể dùng output của một lần chạy như bằng chứng quy luật cho tất cả JVM. Ví dụ sau chỉ minh họa điều **không** được phép kết luận:

```java
IntUnaryOperator first = x -> x + 1;
IntUnaryOperator second = x -> x + 1;

// Không khẳng định first == second hoặc first.getClass() == second.getClass().
// Không dùng các biểu thức so sánh đó làm quy tắc nghiệp vụ.
```

Đây là **đoạn mã nằm trong một phương thức**, không phải tệp Java độc lập.

## 4. Ví dụ Java 17+ chạy được, có kết quả xác định

Tạo tệp `LambdaIdentityDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.function.IntUnaryOperator;

public class LambdaIdentityDemo {
    private static IntUnaryOperator add(int amount) {
        return value -> value + amount;
    }

    public static void main(String[] args) {
        IntUnaryOperator first = add(2);
        IntUnaryOperator alias = first;
        IntUnaryOperator second = add(2);

        System.out.println(first == alias);
        System.out.println(first.applyAsInt(5));
        System.out.println(second.applyAsInt(5));
        System.out.println(
                first.applyAsInt(5) == second.applyAsInt(5));

        Map<String, IntUnaryOperator> operations = new HashMap<>();
        operations.put("add-two", first);
        System.out.println(operations.get("add-two").applyAsInt(10));

        // Cố ý KHÔNG in first == second hoặc first.getClass().
        // Chúng không có kết quả di động cần dựa vào.
    }
}
```

Chạy:

```bash
javac LambdaIdentityDemo.java
java LambdaIdentityDemo
```

Output:

```text
true
7
7
true
12
```

Giải thích:

- `first == alias` luôn là `true` vì `alias` được gán chính tham chiếu `first`, không cần giả định gì về cách JVM tạo lambda.
- Hai phép gọi `applyAsInt(5)` đều trả `7` theo quy tắc `value + amount` với `amount = 2`; so sánh **hai kết quả số nguyên** luôn đúng.
- `operations` tra cứu thao tác bằng khóa nghiệp vụ `"add-two"`. Mã không tra cứu bằng đối tượng lambda, tên lớp hay identity của nó.
- Ví dụ cố ý không đoán giá trị `first == second`: hai lời gọi `add(2)` không tạo ra một hợp đồng identity có thể đem đi dùng.

## 5. Liên hệ với target typing và suy luận kiểu

Một lambda không có một kiểu lớp triển khai độc lập, cố định tại nơi gõ biểu thức. Ngữ cảnh quyết định functional interface mà nó được chuyển đổi sang, và chữ ký SAM quyết định kiểu tham số, kiểu trả về, kiểm tra exception.

Tạo tệp `LambdaTargetTypeDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

public class LambdaTargetTypeDemo {
    public static void main(String[] args) throws Exception {
        Supplier<Integer> supplier = () -> 42;
        Callable<Integer> callable = () -> 42;

        System.out.println(supplier.get());
        System.out.println(callable.call());
    }
}
```

Chạy bằng:

```bash
javac LambdaTargetTypeDemo.java
java LambdaTargetTypeDemo
```

Output:

```text
42
42
```

Cùng hình dạng phần thân `() -> 42` nhưng một biểu thức có target type `Supplier<Integer>` với SAM `get()`, biểu thức kia có target type `Callable<Integer>` với SAM `call() throws Exception`. Chỉ nên lập trình theo các giao diện này. Không so sánh hai lớp triển khai do JVM tạo ra để suy luận tính tương thích. Cũng vì cần target type, khai báo `var function = () -> 42;` không hợp lệ: trình biên dịch thiếu kiểu đích để suy luận lambda; có thể dùng `var function = (Supplier<Integer>) () -> 42;` hoặc khai báo tường minh `Supplier<Integer> function = () -> 42;`.

Method reference như `Integer::parseInt` cũng được chuyển đổi sang một functional interface phù hợp với target type, và không nên dùng identity hay lớp hiện thực của object method reference để phân biệt nghiệp vụ.

## 6. Hậu quả khi viết hệ thống thực tế

### 6.1. Không dùng class hoặc identity làm mã định danh thao tác

Mẫu dễ lỗi:

```java
// Ví dụ cách thiết kế cần tránh:
Map<Class<?>, String> names = new HashMap<>();
names.put(action.getClass(), "add-two");

// Hoặc suy ra cùng thao tác từ action1 == action2.
```

Đoạn trên phụ thuộc vào class/identity, vốn không biểu diễn bản chất thao tác. Thay vào đó, dùng một ID nghiệp vụ, một enum hoặc một record mô tả cấu hình tường minh:

```java
record OperationSpec(String id, int amount) {}
```

Ví dụ `OperationSpec("add-two", 2)` có thể dùng làm cấu hình/khóa theo `equals`, `hashCode` được record sinh từ dữ liệu thành phần, còn lambda là hàm thực thi. Khi cần registry, có thể dùng `Map<String, IntUnaryOperator>` như ví dụ hoàn chỉnh ở trên.

### 6.2. Không dùng bằng nhau của tham chiếu để kiểm thử tính đúng

Trong test, hãy kiểm tra **hợp đồng quan sát được**, ví dụ `add(2).applyAsInt(5) == 7`, kiểm tra input biên, exception, các side effect đã được quy định hoặc tương tác với dependency. Tránh assert rằng hai lần gọi factory trả cùng instance, khác instance, cùng `getClass()` hoặc cùng `hashCode()`.

Nếu yêu cầu nghiệp vụ là khử trùng lặp thao tác, hãy so sánh ID, đặc tả/metadata chuẩn hóa hoặc giá trị cấu hình đã định nghĩa rõ. Việc hai hàm cùng cho một vài kết quả giống nhau **không** chứng minh chúng tương đương với mọi đầu vào và trạng thái.

### 6.3. Không dùng identity của lambda làm khóa đồng bộ hay dữ liệu bền vững

Nếu muốn bảo vệ vùng tới hạn, hãy dùng một đối tượng lock có vòng đời do chương trình quản lý:

```java
private final Object lock = new Object();

void updateSafely(Runnable action) {
    synchronized (lock) {
        action.run();
    }
}
```

Đây là đoạn mã thành viên của một lớp, không phải chương trình độc lập. Không thay `lock` bằng việc liên tục đánh giá một lambda rồi kỳ vọng thu được cùng monitor. Tương tự, tránh dùng tên runtime class, `System.identityHashCode` hoặc biểu diễn `toString` của lambda làm khóa lưu trữ, tên metric, tên thao tác hay dữ liệu cần ổn định sau khi nâng cấp JDK.

### 6.4. Không nhầm identity của closure với ý nghĩa capture

Ví dụ `add(int amount)` ở trên capture giá trị `amount` tại thời điểm tạo hàm. Trong Java, biến local được capture phải là `final` hoặc **effectively final**; nếu capture một tham chiếu tới đối tượng có thể thay đổi, hành vi lambda có thể nhìn thấy trạng thái đối tượng đó khi gọi. Quy tắc capture là vấn đề **ngữ nghĩa và trạng thái**, không cho phép suy ra class hoặc instance identity. Nếu chia sẻ lambda giữa nhiều luồng, cần quản lý an toàn luồng của trạng thái được truy cập; không kỳ vọng mỗi lần tạo lambda tự động cô lập trạng thái.

## 7. Các hiểu nhầm thường gặp

- **“Lambda luôn tạo object mới.”** Không đúng như một bảo đảm của ngôn ngữ; JVM có thể tái sử dụng đối tượng.
- **“Lambda không capture luôn là singleton.”** Không có cam kết singleton. Một JVM có thể tối ưu theo cách đó, nhưng chương trình không được phụ thuộc.
- **“Hai lambda cùng body phải bằng nhau.”** Java không định nghĩa `equals` theo mã nguồn hay ý nghĩa hàm. Tránh dùng `HashSet`/`HashMap` với khóa là lambda nếu mục tiêu là loại trùng theo ý nghĩa nghiệp vụ.
- **“Có thể dùng `getClass().getName()` để biết lambda là thao tác gì.”** Tên và tổ chức lớp runtime là chi tiết triển khai; có thể thay đổi.
- **“Lambda là một lớp vô danh viết tắt nên có thể dựa vào tính chất identity của anonymous class.”** Lambda và anonymous class có các khác biệt về scope, `this` và cơ chế thực thi; không đồng nhất hai mô hình.
- **“Method reference là tên ổn định của một đối tượng hàm.”** `object::method` hay `Type::method` là cú pháp biểu thức tham chiếu phương thức theo target type, không phải ID nghiệp vụ ổn định của một object.
- **“Có `Serializable` thì tên lớp hoặc cấu trúc lambda có thể lưu bền vững.”** Serialization của lambda có các ràng buộc và nguy cơ tương thích riêng; không dùng hình dạng lớp triển khai làm schema lâu dài.

## 8. Quy tắc áp dụng

Khi viết API nhận hàm, chọn functional interface phù hợp (`Predicate<T>`, `Function<T,R>`, `Consumer<T>`, `Supplier<T>`, `Runnable` hoặc interface riêng). Khi chạy, gọi phương thức SAM và kiểm tra kết quả/hợp đồng của nó. Khi cần nhận diện, quản lý vòng đời, cache hoặc so sánh, hãy gắn **danh tính nghiệp vụ tường minh** vào dữ liệu riêng do ứng dụng sở hữu.

Hãy tự hỏi: “Nếu JDK khác chọn một lớp triển khai khác hoặc tái sử dụng instance lambda, chương trình có còn đúng không?” Nếu câu trả lời là có, mã đang tôn trọng ranh giới giữa **target type và hành vi được bảo đảm** với **lớp runtime và identity phụ thuộc triển khai**.

**Tài liệu nền tảng:** Java Language Specification `15.27 (Lambda Expressions), đặc biệt `15.27.3 (Type of a Lambda Expression) và `15.27.4 (Run-Time Evaluation of Lambda Expressions); Java SE `java.util.function`.