# Intersection type và ràng buộc nhiều interface trong suy luận kiểu Java

Java không hỗ trợ một class `extends` nhiều class, nhưng một đối tượng có thể thực hiện **nhiều interface cùng lúc**. Đôi khi một phương thức cần đối tượng **đồng thời** có hai hay nhiều năng lực, chẳng hạn vừa có mã định danh, vừa có thể so sánh, hoặc vừa chạy được vừa đóng tài nguyên. Khi ấy, **intersection type** (kiểu giao) và **multiple bounds** (nhiều ràng buộc của tham số kiểu) là công cụ diễn đạt hợp đồng chính xác.

Điểm cốt lõi: `A & B` nói về một kiểu thỏa **cả A lẫn B**, không phải chọn A **hoặc** B. Trong Java hiện đại, kiểu giao xuất hiện qua các ràng buộc generic, cast, suy luận kiểu và một số ngữ cảnh kiểu đích của lambda/method reference. Cú pháp đã có từ Java 8 và vẫn còn được hỗ trợ; bài này tập trung các kỹ thuật đang có giá trị trong mã Java 17+.

## 1. Khái niệm: “vừa là A, vừa là B”

Xét hai interface độc lập:

```java
interface HasCode {
    String code();
}

interface HasAmount {
    long amount();
}
```

Đây là **định nghĩa minh họa**, chưa phải chương trình độc lập. Nếu một class implement cả hai:

```java
final class Invoice implements HasCode, HasAmount {
    @Override
    public String code() { return "INV-7"; }

    @Override
    public long amount() { return 250L; }
}
```

Một `Invoice` thỏa đồng thời hợp đồng của `HasCode` và `HasAmount`. Chỉ truyền nó qua biến kiểu `HasCode` thì bên trong phương thức không thể trực tiếp gọi `amount()` vì **kiểu khai báo** không hứa hẹn điều đó; tương tự với biến `HasAmount` và `code()`.

Với generic bound:

```java
static <T extends HasCode & HasAmount> String describe(T item) {
    return item.code() + ":" + item.amount();
}
```

Đây là **phương thức minh họa**, cần đặt cùng ngữ cảnh có hai interface trên. Compiler bảo đảm rằng **mọi T hợp lệ** đều hỗ trợ cả `code()` lẫn `amount()`. Do đó không cần cast riêng từng năng lực trong thân `describe`.

Ý nghĩa kiểu giao:

```text
             HasCode
                \
                 \   Invoice
                 /   implements both
                /
             HasAmount

T extends HasCode & HasAmount
=> mọi giá trị T phải thỏa cả hai hợp đồng
```

Hình trên chỉ là minh họa quan hệ kiểu; `&` ở đây không phải toán tử bitwise-and hay boolean-and được dùng trong biểu thức tính toán.

## 2. Multiple bounds: cú pháp generic chính xác

Một tham số kiểu có thể có một ràng buộc đầu tiên và các ràng buộc tiếp theo:

```java
<T extends InterfaceA & InterfaceB & InterfaceC>
```

Trong khai báo này, từ khóa `extends` chỉ xuất hiện **một lần**, còn các bound nối bằng `&`. Mỗi bound tiếp theo phải là **interface**. Bound đầu tiên có thể là **class hoặc interface**.

Ví dụ hợp lệ:

```java
static <T extends CharSequence & Comparable<? super T>>
T later(T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}
```

Đây là một **phương thức minh họa** đặt trong class. Nó đòi `T` vừa là `CharSequence`, vừa có thể so sánh với các giá trị kiểu `T`. `String` đáp ứng hai điều kiện này:

```java
String winner = later("Ada", "Binh"); // "Binh"
```

`CharSequence` cung cấp `length()`, `charAt(...)` và những khả năng đọc chuỗi, còn `Comparable<? super T>` cho phép `compareTo` với kiểu so sánh tương thích. Thân phương thức có thể gọi các method phù hợp từ **mọi bound**.

### Một class bound, rồi các interface bound

```java
static <T extends Number & Comparable<T>>
T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Đây là phương thức minh họa. `Number` là class bound đứng **đầu tiên**; `Comparable<T>` là interface bound. `Integer` và `BigDecimal` đều có thể là kiểu `T` trong những lời gọi phù hợp **riêng biệt**. Phương thức không hứa có thể lấy một `Integer` và một `BigDecimal` để so sánh trực tiếp dưới cùng `T`.

Ví dụ **không hợp lệ**:

```java
// SAI: class bound phải đứng trước các interface bound.
// <T extends Comparable<T> & Number>

// SAI: không thể dùng hai class bounds khác nhau.
// <T extends Number & Thread>

// SAI: dùng extends lại cho bound thứ hai.
// <T extends Number extends Comparable<T>>
```

Các dòng trên là các dạng lỗi đã comment, **không dùng làm mã chạy**. Kể cả khi hai interface độc lập có các phương thức hợp lệ, một class có thể implement cả hai; nhưng Java vẫn chỉ cho **tối đa một class bound và nó phải đứng trước**.

### Những giới hạn ở danh sách bound

Không phải cứ viết nhiều tên interface sau `&` là hợp lệ. Các bound phải có cách thỏa mãn nhất quán: cùng một generic interface không thể xuất hiện với hai parameterizations không tương thích, và các yêu cầu về phương thức không được tạo các signature/return type bất khả thi.

```java
// SAI: cùng generic interface với hai type argument khác nhau.
// <T extends Comparable<String> & Comparable<Integer>>
```

Java không có cách tạo một class implement đồng thời cả `Comparable<String>` và `Comparable<Integer>` như hai hiện thực generic độc lập, vì ràng buộc liên quan đến erasure và tính nhất quán của hệ kiểu.

## 3. Vì sao dùng bound thay vì nhận Object rồi cast?

So sánh hai thiết kế:

```java
// KHÔNG NÊN: nhận Object khiến compiler không bảo đảm hợp đồng.
static String unsafe(Object input) {
    HasCode code = (HasCode) input;
    HasAmount amount = (HasAmount) input;
    return code.code() + ":" + amount.amount();
}
```

Đây là phương thức minh họa. Người gọi có thể truyền một object chỉ implement `HasCode`, dẫn tới `ClassCastException` khi runtime ép sang `HasAmount`.

Phiên bản generic:

```java
static <T extends HasCode & HasAmount> String safe(T value) {
    return value.code() + ":" + value.amount();
}
```

Dưới những lời gọi Java bình thường với kiểu tĩnh đầy đủ, compiler sẽ từ chối đối số không thỏa cả hai interface. Ngay trong body, cả hai phương thức được gọi không cần cast. Giải pháp cũng tự mô tả hợp đồng cho API documentation và IDE.

Lưu ý: **generic bounds không phải cơ chế xác thực dữ liệu ngoài**. Raw types, unchecked casts và reflection có thể vượt qua một số bảo đảm compile-time; kiểu runtime vẫn có những kiểm tra riêng. Cách thiết kế tốt là không dùng cast không an toàn tại ranh giới API.

## 4. Intersection cast: thể hiện một kiểu giao tại biểu thức

Ngoài khai báo generic, Java cho phép viết intersection type trong **cast expression**:

```java
Object unknown = new Invoice();

HasCode view = (HasCode & HasAmount) unknown;
System.out.println(view.code()); // INV-7
```

Đây là đoạn minh họa phụ thuộc vào `Invoice` đã được định nghĩa. Cast yêu cầu đối tượng runtime tương thích **cả hai interface**. Biểu thức `(HasCode & HasAmount) unknown` có kiểu giao trong ngữ cảnh biểu thức, nhưng biến `view` được khai báo là `HasCode`, nên trên biến này chỉ gọi trực tiếp những phương thức của `HasCode`.

Để dùng cả hai năng lực, hãy truyền **chính biểu thức kiểu giao** vào một phương thức yêu cầu multiple bounds:

```java
Object unknown = new Invoice();
String text = describe((HasCode & HasAmount) unknown);
// "INV-7:250"
```

Đoạn minh họa phụ thuộc vào `describe` và `Invoice`. Đây là điểm giao nhau giữa **casting** và **type inference**: compiler có thể sử dụng kiểu giao của biểu thức làm bằng chứng rằng đối số thỏa hai bound.

### Cast kiểm tra điều gì lúc runtime?

Nếu object chỉ implement một interface:

```java
Object onlyCode = (HasCode) () -> "X";
// describe((HasCode & HasAmount) onlyCode);
// Sẽ thất bại với ClassCastException ở runtime.
```

Dòng cast thứ nhất là minh họa hợp lệ vì `HasCode` có một abstract method và là functional interface. Dòng tiếp theo được comment: một lambda object tạo từ target `HasCode` không tự động implement `HasAmount`. **Cast không thêm khả năng mới** cho object; nó chỉ kiểm tra khả năng thực sự tồn tại.

Tương tự, `(A & B) value` không có nghĩa “nếu là A thì chấp nhận, nếu không là B cũng được”: đó là **điều kiện đồng thời**, không phải union type.

### Không dùng dấu & trong khai báo biến bình thường

```java
// SAI: đây không phải cú pháp khai báo biến cục bộ hợp lệ.
// HasCode & HasAmount both = new Invoice();
```

Nếu cần một tên kiểu sử dụng ở nhiều vị trí, hãy định nghĩa interface tổng hợp:

```java
interface CodedAmount extends HasCode, HasAmount {}
```

Nhưng phải chú ý **Java dùng nominal typing**: việc `Invoice implements HasCode, HasAmount` không tự khiến `Invoice` trở thành subtype của `CodedAmount`. Để gán `Invoice` cho biến `CodedAmount`, `Invoice` phải trực tiếp hoặc gián tiếp implement `CodedAmount`. Nếu không muốn sửa class, helper có type parameter `<T extends HasCode & HasAmount>` thường là lựa chọn tốt.

## 5. Kiểu giao và suy luận kiểu của generic method

Khi gọi generic method, Java thu thập các **ràng buộc kiểu** từ lời gọi và target context để chọn type argument phù hợp.

```java
static <T extends HasCode & HasAmount> long doubled(T value) {
    return value.amount() * 2;
}
```

Đây là phương thức minh họa. Với:

```java
Invoice invoice = new Invoice();
long amount = doubled(invoice); // 500
```

Compiler có thể suy luận `T = Invoice`, vì `Invoice` đáp ứng tất cả bound. Ngược lại:

```java
HasCode generalView = invoice;
// doubled(generalView); // Lỗi biên dịch: kiểu tĩnh chưa chứng minh HasAmount.
```

Mặc dù receiver runtime là `Invoice`, **biến `generalView` có kiểu tĩnh `HasCode`**, nên compiler không tự sử dụng thông tin “đằng sau” để giả định nó có `amount()`.

Nếu ranh giới dữ liệu thực sự đã kiểm tra đủ hai interface, có thể cast hợp lệ hoặc thiết kế API trả kiểu mang đủ hai hợp đồng. Nhưng đừng thêm cast chỉ để vượt lỗi compile-time mà không có bảo đảm về runtime type.

### Suy luận từ nhiều đối số

```java
static <T extends CharSequence & Comparable<? super T>>
T maxText(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Đây là phương thức minh họa. Với hai `String`, `T` được xác định dễ dàng. Khi các đối số có **hai kiểu con khác nhau**, compiler phải tìm một kiểu phù hợp cho *tất cả* ràng buộc và target context. Kết quả không phải lúc nào cũng bằng “tên class chung gần nhất”; những phép suy luận hiện đại còn có thể sinh ra một kiểu giao. Vì vậy, nên để compiler kiểm tra, không cố tự đoán kiểu chỉ từ một đoạn hierarchy.

Đối với API phức tạp, có thể dùng biến trung gian có kiểu rõ, chia method thành các bước dễ suy luận hoặc bổ sung type witness như `ClassName.<Type>method(...)` khi thích hợp. Type witness chỉ định một type argument, **không xóa các bound bắt buộc**.

## 6. Intersection type và lambda: cần một function type hợp lệ

Lambda cần một **target type mang hợp đồng SAM**. Một intersection có thể là target hợp lệ nếu phần chức năng của giao vẫn xác định được **một functional interface** theo quy tắc JLS.

Ví dụ: một interface chức năng và một marker interface không có method trừu tượng:

```java
interface Tracked {}

java.util.function.IntUnaryOperator twice =
        (java.util.function.IntUnaryOperator & Tracked) n -> n * 2;
```

Đây là đoạn minh họa, cần đặt `Tracked` trong scope hợp lệ. Intersection `IntUnaryOperator & Tracked` có SAM là `int applyAsInt(int)`; `Tracked` chỉ đóng vai trò marker và không thêm abstract method.

Có thể kiểm tra:

```java
System.out.println(twice.applyAsInt(5)); // 10
System.out.println(twice instanceof Tracked); // true
```

Cú pháp `(IntUnaryOperator & Tracked) n -> ...` **không có nghĩa cast một lambda đã tồn tại sang Tracked**. Nó cung cấp target intersection **khi lambda được chuyển thành object**, nên object được tạo tương thích cả hai interface theo hợp đồng. Đây là khác biệt quan trọng với ví dụ `onlyCode` đã được tạo trước đó.

### Giao hai interface cùng mô tả một chức năng tương thích

Một intersection vẫn có thể là functional nếu các phương thức trừu tượng có thể hợp nhất thành một SAM hợp lệ.

```java
interface Sender {
    void send(String message);
}

interface Reporter {
    void send(String message);
}

Sender combined = (Sender & Reporter) msg ->
        System.out.println(msg);
```

Đây là định nghĩa và câu lệnh minh họa. Hai interface có **cùng chữ ký và cùng kiểu kết quả void**; chức năng có thể được xem như một hợp đồng chung. Khi tạo lambda với intersection target, object thực hiện cả hai interface. Biến `combined` được khai báo là `Sender`; nếu muốn dùng như `Reporter`, cần một tham chiếu kiểu thích hợp.

### Giao hai SAM không tương thích không phải target cho lambda

```java
interface CanRun {
    void run();
}

interface CanClose {
    void close();
}

// SAI: hai abstract methods khác nhau; không phải một SAM.
// Object invalid = (CanRun & CanClose) () -> System.out.println("go");
```

Các interface trên là định nghĩa minh họa; dòng gán lỗi đã comment. Hai method `run()` và `close()` không thể trở thành một phương thức chức năng duy nhất chỉ bằng intersection cast.

**Nhưng** một **object class bình thường** vẫn có thể implement cả hai:

```java
class RunAndClose implements CanRun, CanClose {
    @Override public void run() { System.out.println("go"); }
    @Override public void close() { System.out.println("closed"); }
}
```

Định nghĩa trên hợp lệ; `(CanRun & CanClose) new RunAndClose()` có thể cast thành công. **Khả năng cast một object** và **khả năng target một lambda** là hai điều khác nhau.

## 7. Dùng intersection với Runnable và AutoCloseable

Nhiều ứng dụng cần một đối tượng vừa `Runnable`, vừa `AutoCloseable`. Một type parameter nhiều bound thể hiện điều đó chính xác:

```java
static <T extends Runnable & AutoCloseable> void execute(T job)
        throws Exception {
    try (job) {
        job.run();
    }
}
```

Đây là phương thức minh họa, cần đặt trong class. **Java 9+** cho phép đưa một biến resource đã khai báo và effectively final vào `try (job)`; ví dụ chạy trên Java 17+. Nếu cần hỗ trợ Java 8, khai báo resource ngay trong `try (...)` với một biến mới hợp lệ, hoặc dùng API quản lý vòng đời phù hợp.

`try-with-resources` tự gọi `close()` sau block, kể cả khi body ném ngoại lệ, theo các quy tắc exception suppression của Java. Vì `AutoCloseable.close()` có thể ném checked `Exception`, method trên khai báo `throws Exception`.

Ví dụ class triển khai:

```java
final class WorkUnit implements Runnable, AutoCloseable {
    @Override
    public void run() {
        System.out.println("running");
    }

    @Override
    public void close() {
        System.out.println("closed");
    }
}
```

Đây là class minh họa. `execute(new WorkUnit())` hợp lệ và **trình tự output là `running` rồi `closed`**. Nếu method chỉ nhận `Runnable`, compiler không thể bảo đảm gọi `close()`; nếu chỉ nhận `AutoCloseable`, không thể bảo đảm gọi `run()`. Hai bound giúp mã hóa ràng buộc của API.

### Interface tổng hợp hay generic bound?

Có thể định nghĩa:

```java
interface ClosableTask extends Runnable, AutoCloseable {}
```

Nên dùng **interface tổng hợp** khi đây là một **khái niệm miền ổn định** mà các implementor chủ động cam kết thực hiện. Dùng **generic multiple bounds** khi method cần phối hợp các năng lực **đã độc lập**, không nên buộc tất cả class phải implement thêm một interface mới chỉ để gọi helper.

Ví dụ một class đã `implements Runnable, AutoCloseable` nhưng không `implements ClosableTask` vẫn hợp lệ với `execute(T)` generic; nó không tự động là subtype của `ClosableTask`.

## 8. Ràng buộc kiểu class và interface: thứ tự ảnh hưởng cả erasure

Giả sử:

```java
static <T extends Number & Comparable<T>> int compare(
        T left, T right) {
    return left.compareTo(right);
}
```

Đây là minh họa. Thứ tự bound có ý nghĩa ở nhiều cấp:

1. **Cú pháp:** nếu có class bound, class bắt buộc đứng đầu.
2. **Hợp đồng:** mọi `T` hợp lệ đều phải là `Number` và `Comparable<T>`.
3. **Type erasure:** erasure của type variable được xác định bởi erasure của **bound đầu tiên**, nên việc chọn thứ tự các interface bound cũng có thể ảnh hưởng chữ ký sau erasure và tính tương thích nhị phân của API.

Đừng tùy tiện thay đổi thứ tự bound trong **public library API** mà không xem xét binary compatibility. Compiler thực hiện các kiểm tra/cast cần thiết để code generic sử dụng được các method từ bound khác; người viết code không nên suy ra rằng mọi thông tin generic được giữ nguyên tại runtime.

### Generic không tự sinh “kiểu giao có tên” ở runtime

Java generic dùng **type erasure**. Tham số `T` bị xóa về bound đầu tiên theo quy tắc JLS; không có một class JVM mới tên “`Number & Comparable`” được tạo cho mỗi tổ hợp. Compile-time vẫn xác nhận các bound, còn runtime dựa trên những cơ chế như class/interface, object casts và bridge methods khi cần.

Vì vậy, **đừng dùng reflection hoặc chuỗi tên kiểu** để tự suy diễn một “intersection object” tồn tại như class riêng biệt. Intersection type là thành phần của **hệ thống kiểu Java**, không phải một kiểu object có constructor độc lập.

## 9. Wildcard không hỗ trợ trực tiếp cú pháp nhiều bounds

Một lỗi phổ biến:

```java
// SAI: wildcard bound không dùng cú pháp A & B như type parameter.
// List<? extends HasCode & HasAmount> items;
```

Đây là **dòng lỗi minh họa**. `? extends HasCode` hợp lệ, nhưng cú pháp wildcard không cho liệt kê thêm `& HasAmount` theo cách khai báo type parameter.

Cách viết hợp lệ là tạo một method generic với named type parameter:

```java
static <T extends HasCode & HasAmount> void printAll(
        java.util.List<T> values) {
    for (T value : values) {
        System.out.println(value.code() + ":" + value.amount());
    }
}
```

Đây là phương thức minh họa. Nếu class nguồn đã implement cả hai interface, chẳng hạn `Invoice`, có thể truyền `List<Invoice>` vào `printAll`.

Hoặc định nghĩa **interface tổng hợp có tên** và dùng `List<? extends CodedAmount>` nếu các class đã implement `CodedAmount`. Không nên dùng raw `List` hay unchecked cast chỉ để mô phỏng multiple bounds trên wildcard.

## 10. Điều gì xảy ra nếu các bound có phương thức xung đột?

Một intersection type yêu cầu các bound có thể cùng đúng. Java không tự chọn ngẫu nhiên implementation từ hai interface ngang hàng có cùng default method.

```java
interface Left {
    default String label() {
        return "L";
    }
}

interface Right {
    default String label() {
        return "R";
    }
}

// Class này không thể để nguyên mà không giải quyết xung đột.
// class Broken implements Left, Right {}
```

Đây là ví dụ minh họa với class lỗi đã comment. Cách triển khai:

```java
class Combined implements Left, Right {
    @Override
    public String label() {
        return Left.super.label() + "/" + Right.super.label();
    }
}
```

Class trên hợp lệ và `new Combined().label()` trả `"L/R"`. **Multiple bounds không bỏ qua quy tắc kế thừa/override default method của interface**. Nếu một tổ hợp interface không thể cùng được implement hợp lệ, không thể dùng cast hay suy luận kiểu để “cưỡng ép” nó trở thành một hợp đồng có thể hiện thực.

Khi các bound có phương thức abstract cùng signature hợp lệ, một class có thể triển khai một method thỏa cả hai hợp đồng. Khi có kết quả trả về không tương thích, compiler sẽ phát hiện sự bất nhất ở nơi thích hợp. Hãy kiểm tra đầy đủ **signature, kiểu trả về, generic erasure và khả năng truy cập**, không chỉ so tên phương thức.

## 11. Multiple bounds và method reference

Method reference, giống lambda, là một **poly expression** và cần target type phù hợp. Có thể dùng nó trong generic API nhận hàm có ràng buộc kiểu, nhưng không nên suy luận rằng chỉ nhìn cú pháp `Type::method` là biết mọi khả năng được yêu cầu.

Ví dụ:

```java
static <T extends CharSequence & Comparable<? super T>>
String report(T first, T second) {
    T winner = first.compareTo(second) >= 0 ? first : second;
    return winner.toString() + " (" + winner.length() + ")";
}
```

Đây là phương thức minh họa. Java biết `T` có `compareTo` và `length` từ hai bound. Cách dùng:

```java
String result = report("An", "Binh"); // "Binh (4)"
```

Một tình huống lambda với các interface kế thừa nhiều năng lực:

```java
@FunctionalInterface
interface NamedRule extends java.util.function.Predicate<String>,
                            java.io.Serializable {
}
```

Đây là **định nghĩa minh họa**: `Predicate<String>` cung cấp `boolean test(String)`, còn `Serializable` là marker interface; vì vậy `NamedRule` có SAM phù hợp để dùng lambda:

```java
NamedRule rule = s -> s.length() > 2;
System.out.println(rule.test("Java")); // true
```

Việc kết hợp marker interface với functional interface vẫn dùng được. **Không nên suy ra rằng mọi lambda đều serialize an toàn để lưu lâu dài** chỉ vì một target có `Serializable`. Các đối tượng lambda có thể thay đổi biểu diễn qua phiên bản code/runtime; việc serialization cần contract và chiến lược tương thích riêng. Nếu chỉ muốn gắn metadata nghiệp vụ, một class rõ ràng thường dễ kiểm soát hơn.

## 12. Intersection cast: không nên dùng để thay thiết kế API rõ ràng

Cast kiểu giao hữu dụng nhưng nên là công cụ có chủ đích. Xét trường hợp một thư viện trả `Object`:

```java
Object response = getResponseFromLegacyBoundary();
// Không biết chắc runtime type của response.
```

Đây là **đoạn giả lập minh họa** (phương thức `getResponseFromLegacyBoundary` không tồn tại trong JDK). Viết thẳng:

```java
// RỦI RO: chỉ có thể chạy nếu runtime object thực sự thỏa cả hai.
// String output = describe((HasCode & HasAmount) response);
```

sẽ có nguy cơ `ClassCastException`. Thiết kế hiện đại ưu tiên trả kiểu có hợp đồng chính xác từ đầu: generic return type, interface tổng hợp có tên, sealed hierarchy khi phù hợp hoặc lớp DTO rõ ràng. Nếu dữ liệu thực sự động, hãy **kiểm tra từng năng lực** rồi xử lý:

```java
if (response instanceof HasCode code
        && response instanceof HasAmount amount) {
    System.out.println(code.code() + ":" + amount.amount());
} else {
    throw new IllegalArgumentException(
            "Response lacks required capabilities");
}
```

Đây là **đoạn minh họa cần biến `response` trong scope**, và sử dụng pattern matching for `instanceof` đã được chuẩn hóa từ Java 16. Nó diễn đạt rõ nhánh hợp lệ và lỗi, thay vì để cast ném lỗi không có ngữ cảnh.

**Lưu ý quan trọng:** cú pháp `instanceof HasCode & HasAmount` **không hợp lệ**. Ở đây là **hai phép kiểm tra `instanceof` riêng** kết hợp bằng toán tử logic `&&`. Intersection type ở *casting context* dùng cú pháp `(HasCode & HasAmount) expression`, không dùng cú pháp đó để viết một `instanceof` duy nhất.

## 13. Chương trình Java 17+ hoàn chỉnh: tất cả kỹ thuật chính

Ví dụ sau kiểm chứng trong một file:

- Một class thực hiện hai interface độc lập và đi qua generic method nhiều bound.
- Suy luận `T` với giao của `CharSequence` và `Comparable<? super T>`.
- Một lambda có intersection target gồm functional interface và marker interface.
- Một object được cast sang kiểu giao tại call site.
- Một resource vừa `Runnable` vừa `AutoCloseable` dùng trong `try-with-resources`.
- Nhánh pattern matching `instanceof` để kiểm tra hai interface mà không dựa vào cast không kiểm soát.

Lưu thành **IntersectionBoundsDemo.java**:

```java
import java.util.List;
import java.util.function.IntUnaryOperator;

public class IntersectionBoundsDemo {

    interface HasCode {
        String code();
    }

    interface HasAmount {
        long amount();
    }

    static final class Invoice implements HasCode, HasAmount {
        private final String code;
        private final long amount;

        Invoice(String code, long amount) {
            this.code = code;
            this.amount = amount;
        }

        @Override
        public String code() {
            return code;
        }

        @Override
        public long amount() {
            return amount;
        }
    }

    static <T extends HasCode & HasAmount> String describe(T item) {
        return item.code() + ":" + item.amount();
    }

    static <T extends CharSequence & Comparable<? super T>>
    T later(T first, T second) {
        return first.compareTo(second) >= 0 ? first : second;
    }

    interface Tracked {
    }

    static final class WorkUnit implements Runnable, AutoCloseable {
        boolean closed;

        @Override
        public void run() {
            System.out.println("running");
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("closed");
        }
    }

    static <T extends Runnable & AutoCloseable> void execute(T job)
            throws Exception {
        try (job) {
            job.run();
        }
    }

    public static void main(String[] args) throws Exception {
        Invoice first = new Invoice("INV-7", 250L);
        Invoice second = new Invoice("INV-8", 75L);

        System.out.println("direct: " + describe(first));

        List<String> descriptions = List.of(first, second)
                .stream()
                .map(IntersectionBoundsDemo::describe)
                .toList();
        System.out.println("mapped: " + descriptions);

        System.out.println("later: " + later("Ada", "Binh"));

        IntUnaryOperator twice = (IntUnaryOperator & Tracked)
                value -> value * 2;
        System.out.println("lambda: " + twice.applyAsInt(7));
        System.out.println("tracked: " + (twice instanceof Tracked));

        Object fromBoundary = second;
        System.out.println("cast: " +
                describe((HasCode & HasAmount) fromBoundary));

        WorkUnit work = new WorkUnit();
        execute(work);
        System.out.println("closedFlag: " + work.closed);

        Object candidate = first;
        if (candidate instanceof HasCode code
                && candidate instanceof HasAmount amount) {
            System.out.println("checked: "
                    + code.code() + ":" + amount.amount());
        }
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac IntersectionBoundsDemo.java
java IntersectionBoundsDemo
```

**Kết quả chuẩn (stdout):**

```text
direct: INV-7:250
mapped: [INV-7:250, INV-8:75]
later: Binh
lambda: 14
tracked: true
cast: INV-8:75
running
closed
closedFlag: true
checked: INV-7:250
```

**Giải thích lần lượt:**

1. `Invoice` implements cả `HasCode` và `HasAmount`, nên `describe(first)` được chấp nhận mà không cần cast.
2. `map(IntersectionBoundsDemo::describe)` dùng method reference đến một **generic method**; với Stream các `Invoice`, compiler suy luận kiểu phù hợp và thu được hai chuỗi đã mô tả.
3. `later("Ada","Binh")` nhận `String` thỏa `CharSequence & Comparable<? super String>`; so sánh `String.compareTo` theo thứ tự từ điển cho `"Binh"` lớn hơn `"Ada"`.
4. `(IntUnaryOperator & Tracked) value -> value * 2` là lambda được target typed theo kiểu giao chức năng, nên `applyAsInt(7)` trả `14` và object trả lời `true` với `instanceof Tracked`.
5. `fromBoundary` được khai báo là `Object`, nhưng thực tế giữ `Invoice`, nên cast sang `HasCode & HasAmount` hợp lệ. Nếu thay bằng object không thỏa cả hai interface, cast sẽ thất bại ở runtime.
6. `execute(work)` nhận `WorkUnit` thỏa cả `Runnable` lẫn `AutoCloseable`. Block gọi `run()` trước; khi rời block, `try-with-resources` gọi `close()`. Do đó các dòng `running`, `closed` rồi `closedFlag: true` xuất hiện theo đúng thứ tự.
7. Hai pattern `instanceof` kiểm tra năng lực độc lập trước khi truy cập; trường hợp này trả `INV-7:250`.

Ví dụ chỉ dùng API còn được hỗ trợ hiện nay. Nó không phụ thuộc thư viện ngoài, không tự serialize lambda và không dùng raw types hay unchecked casts.

## 14. Lỗi thường gặp khi dùng intersection và nhiều bound

### Lỗi 1 — Dùng dấu phẩy thay cho &

```java
// SAI:
// static <T extends HasCode, HasAmount> void show(T x) {}
```

Dấu phẩy ở generic declaration dùng để tách **các type parameters khác nhau**, không phải nhiều bound của **cùng một type parameter**. Muốn một `T` phải thỏa cả hai, viết:

```java
static <T extends HasCode & HasAmount> void show(T x) {
    System.out.println(x.code() + ":" + x.amount());
}
```

Đây là phương thức minh họa; cần hai interface đã định nghĩa.

### Lỗi 2 — Viết hai class trong một bound

```java
// SAI: Java class không có multiple inheritance bằng extends.
// <T extends Number & Thread>
```

Một tham số kiểu có thể có **nhiều interface bounds**, nhưng tối đa một bound là class và nó đứng đầu.

### Lỗi 3 — Nghĩ implements A, B đồng nghĩa implements C extends A, B

```java
interface A {}
interface B {}
interface C extends A, B {}

class AB implements A, B {}

// SAI: AB không tự là subtype của C.
// C value = new AB();
```

Các định nghĩa trong đoạn minh họa hợp lệ, dòng gán lỗi đã comment. Java là **nominally typed**. Nếu cần kiểu `C`, class phải công khai implement `C` hoặc kế thừa từ type đã implement `C`. Đừng dùng unchecked cast để vượt giới hạn này.

### Lỗi 4 — Nghĩ intersection cast tự cấp thêm interface

```java
Object value = new Object();
// SAI LÚC CHẠY: Object này không thỏa Runnable và AutoCloseable.
// Object both = (Runnable & AutoCloseable) value;
```

Cast chỉ kiểm tra, không “trang bị” hành vi. Khi kết hợp với lambda, target intersection có thể yêu cầu lambda object sinh ra implement thêm marker interface, nhưng đây là **quá trình tạo lambda có target type**, không phải phép nâng cấp một object có sẵn.

### Lỗi 5 — Tạo lambda cho hai SAM độc lập

```java
interface Openable { void open(); }
interface Closable { void close(); }

// SAI: giao của hai SAM không tương thích không phải functional.
// Object action = (Openable & Closable) () -> {};
```

Cần một class/record hoặc adapter **cụ thể** thực hiện cả hai, hoặc thiết kế lại interface nếu cả hai hành vi thực chất là một contract.

### Lỗi 6 — Cho rằng generic bảo đảm không còn cast runtime

Trong mã generic, erasure xóa nhiều thông tin type argument. Compiler chèn các kiểm tra/cast cần thiết khi dùng thêm bounds. Dù đó là thực thi đúng của Java, nó không biến một cast không an toàn hoặc raw type thành an toàn. Hãy bảo đảm lời gọi và kiểu khai báo khớp với contract.

### Lỗi 7 — Đặt serialization làm lý do chính để dùng intersection lambda

Cú pháp `(Runnable & Serializable) () -> ...` hợp lệ về mặt kiểu, nhưng việc lưu lambda đã serialize để khôi phục xuyên phiên bản code là một rủi ro bảo trì. Trừ khi đã có hợp đồng serialization rõ ràng, nên dùng một kiểu dữ liệu có định dạng ổn định để lưu trạng thái; tạo lại hành vi từ dữ liệu lúc runtime.

### Lỗi 8 — Overengineering

Nếu mọi giá trị trong hệ thống đều có cùng một khái niệm nghiệp vụ rõ ràng, việc lặp lại `<T extends A & B & C>` trên nhiều phương thức có thể khiến API khó đọc. Cân nhắc interface tổng hợp có tên để mô tả vai trò. Ngược lại, nếu chỉ một utility method tạm thời cần hai năng lực độc lập, multiple bounds là công cụ hợp lý, không cần tạo thêm một hierarchy.

## 15. Quy trình suy luận và kiểm thử kiểu giao

Khi đọc một chữ ký như `<T extends A & B>`:

1. **Định nghĩa hợp đồng:** `A` và `B` thực sự cung cấp những method hoặc tính chất nào? Có default methods/abstract methods xung đột không?
2. **Kiểm tra vị trí bound:** có class bound không? Nếu có, nó đã đứng đầu chưa? Các bound còn lại có phải interface không?
3. **Xác định kiểu tĩnh của đối số:** một biến `A` không tự đủ điều kiện truyền vào `T extends A & B` dù runtime object có thể là `B`.
4. **Xem type inference:** compiler có thể tìm một `T` thỏa mọi ràng buộc từ đối số và target context không?
5. **Nếu cast intersection:** runtime object có thực sự implement từng thành phần không? Nếu sai sẽ ném `ClassCastException`.
6. **Nếu lambda/method reference:** intersection có SAM hợp lệ không? Marker/default method không thêm abstract method, nhưng hai SAM không tương thích làm target không hợp lệ.
7. **Nếu API public:** có nên dùng interface tổng hợp tên rõ hơn? Có ảnh hưởng erasure/binary compatibility không?
8. **Thử trường hợp lỗi:** đối số chỉ thỏa `A`, chỉ thỏa `B`, hai interface default xung đột, input đến từ `Object`, generic type khác dự kiến.

### Bài tập 1 — Thêm một năng lực

Cho `interface HasName { String name(); }` và `interface HasAge { int age(); }`. Viết `static <T extends HasName & HasAge> String summary(T person)` ghép tên và tuổi. **Gợi ý:** compiler cho phép gọi cả `name()` lẫn `age()` trên biến `T`.

### Bài tập 2 — Kiểu tĩnh và kiểu thực

Một class `Person` implement `HasName` và `HasAge`, nhưng biến `HasName p = new Person();`. Tại sao `summary(p)` lỗi dù runtime object là `Person`? **Đáp án:** static type `HasName` không bảo đảm bound `HasAge`. Cần biểu diễn đủ contract ở call site.

### Bài tập 3 — Lambda intersection với marker

Tạo `interface Marked {}` rồi viết lambda dạng `(IntPredicate & Marked) n -> n > 0`. Kiểm tra `test(5)` và `instanceof Marked`. **Đáp án định hướng:** `true` và `true`.

### Bài tập 4 — Hai SAM khác nhau

Vì sao không thể viết `(Runnable & AutoCloseable) () -> ...` trực tiếp để có đủ cả `run` và `close`? **Đáp án:** giao này không có một SAM hợp lệ; cần một class thực hiện cả hai.

### Bài tập 5 — Cast có rủi ro

Một API trả `Object`. Viết kiểm tra hai điều kiện `instanceof HasName` và `instanceof HasAge` bằng `&&` trước khi truy cập. Giải thích vì sao kiểm tra này không giống `instanceof HasName & HasAge` (không hợp lệ về cú pháp).

### Bài tập 6 — Chữ ký bound và erasure

Đánh giá hai chữ ký:

```java
static <T extends CharSequence & Comparable<? super T>>
int compareText(T a, T b) {
    return a.compareTo(b);
}

static <T extends Number & Comparable<T>>
int compareNumber(T a, T b) {
    return a.compareTo(b);
}
```

**Câu hỏi:** hai bound làm gì? Erasure của `T` trong mỗi phương thức bắt đầu từ bound nào? **Đáp án:** cả hai yêu cầu đồng thời hai năng lực; first bound lần lượt là `CharSequence` và `Number`, là cơ sở erasure của type variable.

### Bài tập 7 — Thiết kế API

Khi nào nên tạo `interface IdentifiedAndPriced extends HasCode, HasAmount`, khi nào nên chọn `<T extends HasCode & HasAmount>`? **Gợi ý:** cân nhắc đây là vai trò nghiệp vụ ổn định hay chỉ một yêu cầu cho method, và các class đang tồn tại có sẵn implement interface tổng hợp hay không.

## 16. Ghi nhớ ngắn gọn

- **Intersection type** `A & B` diễn đạt **phải thỏa đồng thời A và B**.
- **Multiple bounds** `<T extends A & B>` giúp code generic truy cập năng lực từ cả hai interface với kiểm tra compile-time.
- **Class bound** nếu có phải đứng trước; những bound tiếp theo phải là interface.
- **Intersection cast** `(A & B) expression` kiểm tra khả năng runtime, không thêm interface cho object.
- **Lambda target intersection** chỉ hợp lệ khi kiểu giao có SAM duy nhất theo quy tắc Java; functional interface + marker interface là trường hợp phổ biến.
- **Nominal typing** nghĩa là implement riêng `A` và `B` không tự đồng nghĩa implement một interface mới `C extends A,B`.
- **Type inference** dựa vào kiểu tĩnh và mọi bound, không suy từ việc compiler “biết” runtime object nào sẽ xuất hiện.
- **Erasure** vẫn tồn tại; bound đầu tiên quan trọng khi thiết kế API generic và tương thích nhị phân.
- Chỉ dùng cast khi có căn cứ về runtime type. Ưu tiên thiết kế kiểu và API có hợp đồng rõ ràng trước khi dùng thủ thuật ép kiểu.

### Tài liệu chính thức

- [JLS `4.9 — Intersection Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.9)
- [JLS `4.4 — Type Variables and Bounds](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.4)
- [JLS `5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.5)
- [JLS `9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.8)
- [JLS `18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html)
- [Java SE 25 — java.util.function.IntUnaryOperator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/IntUnaryOperator.html)
