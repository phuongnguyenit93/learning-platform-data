# Tham chiếu hàm khởi tạo bằng Type::new trong Java

## 1. Tham chiếu constructor dùng để làm gì?

Trong Java, **constructor reference** là một dạng **method reference** cho phép biểu diễn thao tác tạo đối tượng bằng cú pháp `Type::new`. Thay vì viết lambda tự gọi `new Type(...)`, ta có thể truyền tham chiếu đến constructor vào API đang nhận một **functional interface** phù hợp.

~~~java
Supplier<StringBuilder> first = () -> new StringBuilder();
Supplier<StringBuilder> second = StringBuilder::new;
~~~

Đoạn mã trên là **minh họa** trong một phương thức, cần import `java.util.function.Supplier`. Hai biểu thức cùng diễn đạt một hành vi: khi được gọi, tạo một `StringBuilder` mới. `StringBuilder::new` không lập tức tạo đối tượng; nó biểu diễn một hàm tạo để `Supplier.get()` gọi sau.

Điểm quan trọng nhất: **`Type::new` không phải một kiểu dữ liệu tự đứng độc lập**. Nó cần một *target type* — kiểu đích là functional interface với một phương thức trừu tượng — để compiler biết có bao nhiêu đối số, kiểu đối số nào và kiểu kết quả nào được yêu cầu.

Ví dụ:

~~~java
Supplier<StringBuilder> noArg = StringBuilder::new;
Function<Integer, StringBuilder> withCapacity = StringBuilder::new;
~~~

Ở đoạn này cần import `java.util.function.Function`. Cùng chữ `StringBuilder::new` nhưng:
- Với `Supplier<StringBuilder>`, method descriptor là `() -> StringBuilder`, nên compiler chọn constructor không đối số.
- Với `Function<Integer,StringBuilder>`, descriptor là `(Integer) -> StringBuilder`; giá trị `Integer` có thể unbox thành `int` cho constructor `StringBuilder(int capacity)`.
- `withCapacity.apply(100)` tạo bộ đệm có **capacity ban đầu** 100, chứ không tạo chuỗi dài 100 ký tự.

**Constructor reference là cách truyền hành vi tạo đối tượng; không phải cách né quy tắc constructor, kiểm tra kiểu, khả năng truy cập hoặc xử lý lỗi.**

## 2. Cú pháp và cơ chế chọn constructor

Cấu trúc chung:

~~~text
ReferenceType::new
ArrayType::new
~~~

Trong đó `ReferenceType` là kiểu đối tượng có constructor có thể truy cập, còn `ArrayType` là kiểu mảng được xử lý bằng array constructor reference. Với kiểu generic, có thể dùng tham số kiểu tường minh, ví dụ `ArrayList<String>::new`, khi ngữ cảnh cho phép.

Bản chất có thể đọc theo bảng:

| Lambda minh họa | Constructor reference | Functional interface đích |
| --- | --- | --- |
| `() -> new Ticket()` | `Ticket::new` | `Supplier<Ticket>` |
| `code -> new Ticket(code)` | `Ticket::new` | `Function<String,Ticket>` |
| `(code,n) -> new Ticket(code,n)` | `Ticket::new` | `BiFunction<String,Integer,Ticket>` |
| `size -> new String[size]` | `String[]::new` | `IntFunction<String[]>` |
| `size -> new int[size]` | `int[]::new` | `IntFunction<int[]>` |

`Ticket` là class ví dụ sẽ được khai báo trong chương trình độc lập ở phần 7. Bảng nêu **tương đương về hành vi** khi target type, overload và khả năng truy cập được thỏa mãn; không khẳng định hai cách biên dịch tạo ra bytecode hay object trung gian giống hệt.

### 2.1. Đối số thuộc về lần gọi functional interface

Xét `Function<String,Ticket> factory = Ticket::new;`:

1. Compiler thấy target type có phương thức `Ticket apply(String)`.
2. Compiler tìm constructor phù hợp của `Ticket` nhận `String`.
3. Tham chiếu hàm tạo được sử dụng làm giá trị `factory`.
4. Khi gọi `factory.apply("A12")`, đối số `"A12"` được dùng để chạy constructor.
5. Nếu constructor thành công, lời gọi trả về một `Ticket` mới.

Vì vậy tham số không xuất hiện sau `new` ở thời điểm viết reference: danh sách đối số được xác định thông qua **function descriptor** của functional interface.

### 2.2. Constructor không có tên phương thức để gọi

Constructor trong Java không phải phương thức thông thường tên `new`. `Type::new` là **cú pháp đặc biệt** của ngôn ngữ để tham chiếu lời tạo object. Không viết `Type.new()` hoặc `Type::Type`.

So sánh:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `new Ticket("A")` | Tạo object ngay tại biểu thức đó |
| `Ticket::new` | Tham chiếu hành vi tạo Ticket, cần target type |
| `Ticket::someStaticFactory` | Tham chiếu một **static method** (nếu tồn tại), không phải constructor |
| `someObject::instanceMethod` | Tham chiếu instance method với receiver đã có |
| `Ticket::instanceMethod` | Tham chiếu unbound instance method; target type phải cung cấp receiver qua tham số |

Dù nằm trong nhóm method references, constructor reference không có instance receiver đã tồn tại: nó **tạo instance mới** khi chức năng tương ứng được gọi thành công.

## 3. Kết nối Type::new với các functional interface chuẩn

Số đối số và kiểu kết quả của constructor gợi ý functional interface thích hợp:

### 3.1. Supplier<T> — constructor không đối số

~~~java
Supplier<ArrayList<String>> createNames = ArrayList::new;
ArrayList<String> names = createNames.get();
~~~

Đoạn minh họa trên cần import `java.util.ArrayList` và `java.util.function.Supplier`, nằm trong một phương thức. `ArrayList::new` được chọn ở overload constructor không đối số. Danh sách được tạo khi gọi `get()`.

Cần phân biệt:

~~~java
Supplier<List<String>> supplier = ArrayList::new;
~~~

Hợp lệ vì `ArrayList<String>` có thể trả về ở vị trí yêu cầu `List<String>`. Class được khởi tạo vẫn là `ArrayList`, dù kiểu khai báo của kết quả là interface `List`.

### 3.2. Function<A,T> — constructor một đối số

~~~java
Function<String, Ticket> byCode = Ticket::new;
Ticket ticket = byCode.apply("A12");
~~~

Đoạn minh họa giả định `Ticket` có constructor `Ticket(String)` và cần import `java.util.function.Function`. `A` là kiểu tham số đầu vào, `T` là kiểu đối tượng được tạo. Vì `Function<A,T>` nhận đúng một đối số, nó không dùng được cho constructor chỉ có hai tham số bắt buộc.

### 3.3. BiFunction<A,B,T> — constructor hai đối số

~~~java
BiFunction<String, Integer, Ticket> bySeats = Ticket::new;
Ticket ticket = bySeats.apply("B20", 3);
~~~

Đây là đoạn minh họa, cần import `java.util.function.BiFunction`, giả định `Ticket(String,int)` đã được khai báo. Java tự unbox `Integer` sang `int` trong ngữ cảnh phù hợp. Nếu muốn tránh boxing hoặc có nhiều tham số primitive, cân nhắc một functional interface riêng đúng chữ ký.

### 3.4. Với ba đối số hoặc hơn

Package `java.util.function` không cung cấp sẵn một `TriFunction<A,B,C,R>` tổng quát. Nếu constructor có ba tham số, có thể định nghĩa một functional interface rõ ràng:

~~~java
@FunctionalInterface
interface TriFactory<A, B, C, R> {
    R create(A a, B b, C c);
}

record Shipment(String id, int quantity, boolean express) {}

TriFactory<String, Integer, Boolean, Shipment> factory =
        Shipment::new;
~~~

Hai khai báo `TriFactory` và `Shipment` được đặt **ở cấp class hoặc cấp top-level**; dòng gán `factory` được đặt trong một phương thức, hoặc ở vị trí khai báo biến hợp lệ. Đây là mã minh họa từng phần chứ không phải một tệp Java hoàn chỉnh. `record Shipment` có constructor chuẩn nhận `String,int,boolean`, nên tham chiếu có thể khớp descriptor nhận `String,Integer,Boolean` thông qua unboxing.

Với API công khai, nên cân nhắc dùng object tham số (record chứa cấu hình) nếu bộ tham số dài và các giá trị cần được nhóm theo ngữ nghĩa. Không tạo hàng loạt interface chỉ để né một lambda `(a,b,c) -> new Type(a,b,c)` khi việc dùng lambda rõ ràng hơn.

## 4. Constructor overload: cùng Type::new, nhiều cách chọn

Class có thể có nhiều constructor được nạp chồng:

~~~java
class Ticket {
    Ticket() { /* ... */ }
    Ticket(String code) { /* ... */ }
    Ticket(String code, int seats) { /* ... */ }
}
~~~

Các constructor trên là **đoạn minh họa**, phần thân chỉ là placeholder biểu diễn cú pháp; chương trình thực ở phần 7 cung cấp implementation hoàn chỉnh. Java phân giải reference theo **functional interface đích**, xét số tham số, kiểu tham số, khả năng chuyển đổi và quy tắc overload.

Ví dụ:

~~~java
Supplier<Ticket> a = Ticket::new;
Function<String, Ticket> b = Ticket::new;
BiFunction<String, Integer, Ticket> c = Ticket::new;
~~~

- `a.get()` gọi constructor không đối số.
- `b.apply("T7")` gọi constructor một `String`.
- `c.apply("T7", 2)` gọi constructor nhận `String,int`.

Nếu không tồn tại constructor phù hợp, compiler sẽ báo lỗi ngay tại constructor reference. Nếu có nhiều constructor đều phù hợp mà không tìm được lựa chọn duy nhất theo luật overload, reference có thể mơ hồ.

**Không suy đoán constructor chỉ từ chuỗi `Type::new`**; luôn đọc kiểu functional interface nơi nó được gán hoặc truyền vào.

### 4.1. Constructor reference cũng có thể bị ambiguous vì overload của phương thức nhận callback

Xét hai overload của một API:

~~~java
static void register(Supplier<Ticket> supplier) { /* ... */ }
static void register(Callable<Ticket> callable) { /* ... */ }
~~~

Đây là đoạn minh họa ở cấp class, cần import `Supplier` và `Callable`. Nếu `Ticket` có constructor không đối số, lời gọi trực tiếp `register(Ticket::new)` có thể phù hợp cả hai functional interface. Khi hai overload không có quan hệ cụ thể hơn giải quyết được, compiler báo **ambiguous method call**.

Làm rõ bằng khai báo biến hoặc cast:

~~~java
Supplier<Ticket> chosen = Ticket::new;
register(chosen);

// Hoặc:
register((Supplier<Ticket>) Ticket::new);
~~~

Đây là những lời gọi minh họa giả định hai method `register` đã được định nghĩa. Tránh thiết kế nhiều overload khác ngữ nghĩa mà nhận functional interface có cùng hình dạng; đặt tên API rõ ràng giúp người gọi không phải cast thường xuyên.

### 4.2. Cẩn thận khi dùng var

~~~java
// KHÔNG BIÊN DỊCH: thiếu target type.
// var create = Ticket::new;

// HỢP LỆ khi có functional interface cụ thể:
Supplier<Ticket> create = Ticket::new;
~~~

Tương tự lambda, method reference là poly expression và cần kiểu đích. `var` không suy ra một functional interface tùy ý chỉ từ `Ticket::new`.

## 5. Generics: cách Java xác định kiểu đối tượng được tạo

Constructor reference thường xuất hiện với class generic như `ArrayList<E>`:

~~~java
Supplier<List<String>> listFactory = ArrayList::new;
List<String> names = listFactory.get();
~~~

Java suy luận kiểu phù hợp trong ngữ cảnh target type: kết quả là một `ArrayList<String>` dùng ở vị trí `List<String>`. Cách viết có tham số kiểu tường minh cũng có thể dùng:

~~~java
Supplier<ArrayList<String>> factory = ArrayList<String>::new;
~~~

Cần import `java.util.List`, `java.util.ArrayList` và `java.util.function.Supplier`. Với cú pháp constructor reference, không chèn dấu ngoặc constructor `()` sau `new`; đây không phải lời gọi constructor ngay lập tức.

**Lưu ý về kiểu thô (raw type):** nên tránh `ArrayList::new` trong ngữ cảnh gán raw `Supplier`, vì có thể làm mất kiểm tra kiểu. Một kiểu đích generic cụ thể giúp compiler kiểm tra các phép chuyển đổi và phần tử an toàn hơn.

### 5.1. Constructor của record cũng tham chiếu được

Record được dùng để biểu diễn dữ liệu và có canonical constructor phù hợp với các thành phần của nó:

~~~java
record Label(String value) {}

Function<String, Label> createLabel = Label::new;
Label label = createLabel.apply("VIP");
~~~

Đây là mã minh họa: record khai báo ở cấp kiểu, dòng gán ở trong phương thức. `Label::new` tham chiếu constructor nhận một `String`. Kết quả của `label.toString()` trên Java 17 là `Label[value=VIP]`.

Nếu record khai báo thêm constructor hợp lệ, constructor reference có thể chọn overload tương thích, giống class thông thường.

## 6. Array constructor reference: một trường hợp đặc biệt

Java cho phép tham chiếu hàm tạo **mảng**, chẳng hạn `String[]::new` hoặc `int[]::new`. Dạng này rất quan trọng khi làm việc với Stream và API cần cấp phát mảng.

### 6.1. IntFunction<T[]> — cách dùng tự nhiên nhất

~~~java
IntFunction<String[]> factory = String[]::new;
String[] values = factory.apply(3);
~~~

Cần import `java.util.function.IntFunction`. Descriptor `int -> String[]` là một hàm nhận **độ dài mảng**, trả về một mảng `String[]` mới với độ dài đó. Ban đầu các phần tử tham chiếu của mảng là `null`.

Dạng tương đương bằng lambda:

~~~java
IntFunction<String[]> factory = size -> new String[size];
~~~

Khi giá trị độ dài âm, lời cấp phát mảng ném `NegativeArraySizeException` tại thời điểm thực thi hàm. Java không “tự chỉnh” độ dài âm về 0.

### 6.2. Mảng nguyên thủy và các target type khác

~~~java
IntFunction<int[]> intFactory = int[]::new;
Function<Integer, int[]> boxedLengthFactory = int[]::new;
~~~

Cần import `java.util.function.Function` và `IntFunction`. Trong trường hợp đầu, đối số độ dài là primitive `int`. Trường hợp thứ hai có tham số kiểu `Integer`, Java có thể unbox về `int` để cấp phát. Nếu API cho phép, `IntFunction<T>` là cách diễn đạt độ dài nguyên thủy trực tiếp và tránh boxing không cần thiết.

### 6.3. Mảng nhiều chiều: chỉ cấp phát kích thước ngoài

~~~java
IntFunction<String[][]> matrixFactory = String[][]::new;
String[][] matrix = matrixFactory.apply(2);
~~~

Tương đương với ý nghĩa `size -> new String[size][]`: tạo mảng ngoài dài 2, **chưa tự tạo các mảng hàng bên trong**. `matrix[0]` và `matrix[1]` ban đầu bằng `null`. Nếu cần ma trận chữ nhật đầy đủ, phải cấp phát các chiều còn lại riêng theo nhu cầu.

Đây là lý do không nên tự suy luận `String[][]::new` tương đương `(rows,cols) -> new String[rows][cols]`. Array constructor reference có một tham số độ dài `int` ở function descriptor.

### 6.4. Ví dụ với Stream.toArray

Một ứng dụng thường gặp:

~~~java
List<String> names = List.of("An", "Bình");
String[] array = names.stream().toArray(String[]::new);
~~~

Đoạn này giả định import `java.util.List`, đặt trong một phương thức. `Stream<T>.toArray(IntFunction<A[]>)` nhận một hàm cấp phát mảng; implementation cung cấp kích thước cần cấp phát khi gọi. `String[]::new` rõ ràng hơn so với `size -> new String[size]` trong tình huống này.

Không nhầm với `Stream.toArray()` không đối số, vốn trả về `Object[]`. Dạng có `String[]::new` giúp nhận `String[]` theo kiểu phần tử đích.

## 7. Chương trình Java 17 hoàn chỉnh

Tạo file **ConstructorReferenceDemo.java**. Chương trình kết hợp:
- Constructor không đối số, một đối số và hai đối số của class `Ticket`.
- Constructor canonical của record `Label`.
- Constructor generic `ArrayList::new`.
- Array references `String[]::new`, `int[]::new` và `String[][]::new`.
- Dùng constructor reference trực tiếp trong `Stream.map`.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.Supplier;

public class ConstructorReferenceDemo {
    static final class Ticket {
        private final String code;
        private final int seats;

        Ticket() { this("DEFAULT", 1); }
        Ticket(String code) { this(code, 1); }
        Ticket(String code, int seats) {
            this.code = code;
            this.seats = seats;
        }

        @Override
        public String toString() {
            return code + ":" + seats;
        }
    }

    record Label(String value) {}

    public static void main(String[] args) {
        Supplier<Ticket> defaultTicket = Ticket::new;
        Function<String, Ticket> ticketByCode = Ticket::new;
        BiFunction<String, Integer, Ticket> ticketBySeats = Ticket::new;
        Function<String, Label> label = Label::new;

        System.out.println(defaultTicket.get());
        System.out.println(ticketByCode.apply("A12"));
        System.out.println(ticketBySeats.apply("B20", 3));
        System.out.println(label.apply("VIP"));

        Supplier<List<String>> emptyList = ArrayList::new;
        Function<Integer, List<String>> listWithCapacity = ArrayList::new;
        System.out.println("list sizes: " + emptyList.get().size()
                + ", " + listWithCapacity.apply(50).size());

        IntFunction<String[]> stringArray = String[]::new;
        Function<Integer, int[]> intArray = int[]::new;
        IntFunction<String[][]> matrix = String[][]::new;

        System.out.println("array length: " + stringArray.apply(3).length);
        System.out.println("int array length: " + intArray.apply(4).length);
        System.out.println("matrix: " + matrix.apply(2).length
                + ", first row null: " + (matrix.apply(2)[0] == null));

        List<String> codes = List.of("X", "Y");
        List<Ticket> tickets = codes.stream().map(Ticket::new).toList();
        System.out.println("mapped: " + tickets);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 ConstructorReferenceDemo.java
java ConstructorReferenceDemo
~~~

**Stdout đã được kiểm tra trực tiếp:**

~~~text
DEFAULT:1
A12:1
B20:3
Label[value=VIP]
list sizes: 0, 0
array length: 3
int array length: 4
matrix: 2, first row null: true
mapped: [X:1, Y:1]
~~~

Giải thích các kết quả:

1. `defaultTicket.get()` chọn constructor `Ticket()`, constructor này gọi `Ticket("DEFAULT", 1)`, nên in `DEFAULT:1`.
2. `ticketByCode.apply("A12")` chọn `Ticket(String)` và gán mặc định một chỗ; `ticketBySeats.apply("B20", 3)` chọn `Ticket(String,int)`.
3. `Label::new` dùng constructor của record, nên biểu diễn chuỗi là `Label[value=VIP]`.
4. Hai cách tạo `ArrayList` đều cho `size() == 0`. Tham số 50 trong constructor `ArrayList(int initialCapacity)` biểu thị **sức chứa ban đầu**, không tự chèn 50 phần tử.
5. Mảng `String[]` dài 3, mảng `int[]` dài 4; `String[][]::new` cấp phát lớp mảng ngoài dài 2 và mảng con đầu tiên vẫn null.
6. `codes.stream().map(Ticket::new)` tạo một `Ticket(String)` cho mỗi code, tương đương về hành vi với `map(code -> new Ticket(code))`; kết quả giữ thứ tự gặp phần tử của `List.of("X","Y")`.

Chương trình trên đã được biên dịch bằng `javac --release 17` và thực thi, với kết quả khớp chính xác.

## 8. Constructor reference và thời điểm thực thi

Điểm khác biệt quan trọng là **biểu diễn hành vi** và **thực sự cấp phát object**.

~~~java
Supplier<StringBuilder> factory = StringBuilder::new; // chưa gọi constructor
StringBuilder first = factory.get();                    // gọi constructor
StringBuilder second = factory.get();                   // gọi constructor lần nữa
System.out.println(first == second);                   // false
~~~

Đoạn minh họa cần import `java.util.function.Supplier`. Mỗi lần `get()` thực hiện một lời tạo `StringBuilder` mới và nhận object khác nhau khi constructor thành công.

Nhưng API nhận callback có thể gọi zero lần, một lần hoặc nhiều lần. Ví dụ `Optional.orElseGet(supplier)` chỉ cần gọi `supplier.get()` khi không có giá trị; còn `Stream.map(Type::new)` thường áp dụng callback khi pipeline có terminal operation yêu cầu xử lý các phần tử tương ứng.

**Không được mặc định constructor chạy lúc gán `factory`**. Nếu constructor có tác dụng phụ (ghi log, truy cập tài nguyên, cập nhật biến đếm), những tác dụng phụ sẽ xuất hiện tại **lần callback thực sự được gọi**, không phải lúc cú pháp reference được đánh giá.

## 9. Phạm vi truy cập, class đặc biệt và giới hạn

### 9.1. Constructor phải tồn tại và có thể truy cập

Một constructor `private` chỉ được tham chiếu từ vị trí có quyền truy cập nó. Nếu constructor không thể truy cập từ điểm viết `Type::new`, compiler báo lỗi. Tương tự, không thể dùng `AbstractType::new` để tạo trực tiếp một abstract class hoặc interface vì không có constructor có thể gọi để tạo instance theo cách đó.

Đối với interface, thường chọn một class triển khai cụ thể:

~~~java
Supplier<List<String>> supplier = ArrayList::new;
~~~

Chứ không viết `List::new`, vì `List` là interface không có constructor để khởi tạo trực tiếp.

### 9.2. Constructor có checked exception

Nếu constructor khai báo checked exception như `IOException`, callback đích phải có hợp đồng cho phép ngoại lệ đó hoặc đoạn mã phải xử lý nó.

Ví dụ giả định có class:

~~~java
class CheckedResource {
    CheckedResource() throws java.io.IOException {
        throw new java.io.IOException("unavailable");
    }
}
~~~

Mã sau là **ví dụ lỗi khi biên dịch** (giữ trong comment):

~~~java
// Supplier<CheckedResource> wrong = CheckedResource::new;
// Không hợp lệ: Supplier.get() không khai báo IOException.
~~~

Có thể chọn functional interface cho phép checked exception, ví dụ:

~~~java
java.util.concurrent.Callable<CheckedResource> create =
        CheckedResource::new;
~~~

Đây là đoạn minh họa đặt trong phương thức có thể truy cập class `CheckedResource`; `Callable.call()` khai báo `throws Exception`. Lệnh tạo tham chiếu trên có thể biên dịch; nhưng `create.call()` sẽ ném `IOException` từ constructor ví dụ, nên bên gọi phải xử lý/khai báo exception.

Đừng hiểu rằng `Type::new` tự nuốt ngoại lệ hoặc biến ngoại lệ checked thành unchecked.

### 9.3. Non-static inner class

Một member inner class không khai báo `static` có quan hệ với instance của enclosing class, khác với nested class `static`. Constructor của inner class chịu các quy tắc về enclosing instance và cú pháp riêng; không áp dụng máy móc mô hình `Outer.Inner::new` như thể nó luôn tương đương một constructor static của class độc lập.

Để dạy hoặc sử dụng factory ít phụ thuộc context, ưu tiên class top-level, `static` nested class hoặc factory method biểu diễn rõ enclosing instance. Nếu thật sự cần tạo inner instance, hãy kiểm tra cú pháp và target type chính xác với compiler theo JDK sử dụng.

### 9.4. Generic inference và raw type

Kiểu generic suy luận được phụ thuộc vào target type và các ràng buộc kiểu. Không mặc định mọi chữ `Type::new` suy ra tham số generic mong muốn trong mọi ngữ cảnh. Khi compiler không đủ thông tin hoặc có overload cạnh tranh, khai báo callback có kiểu rõ ràng hoặc dùng lambda tường minh.

### 9.5. Không tham chiếu mọi cách tạo object bằng Type::new

Một số class dùng **static factory method** như `of(...)` hoặc `valueOf(...)` thay vì public constructor. Khi đó, target phù hợp thường là `Type::of` hoặc `Type::valueOf`, không phải `Type::new`.

Ví dụ `List.of(...)` là static factory tạo collection không cho phép sửa cấu trúc. Không có cú pháp `List::new` thay thế nó. API cũng có thể yêu cầu constructor riêng vì validation, caching, lifecycle hoặc bất biến; constructor reference không bỏ qua các quy ước này.

## 10. Khi nào nên chọn Type::new thay vì lambda hoặc factory method?

| Tình huống | Chọn cách nào? | Lý do |
| --- | --- | --- |
| Chỉ chuyển tham số trực tiếp cho một constructor | `Type::new` | Ngắn gọn, bộc lộ ý định tạo instance |
| Cần tính toán/chỉnh sửa trước khi gọi constructor | `arg -> new Type(normalize(arg))` | Lambda cho phép xử lý tham số |
| Cần nhiều câu lệnh, kiểm tra hoặc try/catch | Lambda dạng block hoặc helper factory | Diễn đạt logic và xử lý lỗi rõ hơn |
| Cần object có quy tắc caching/validation đặc thù | Static factory method được API cung cấp | Constructor không đồng nghĩa factory nghiệp vụ |
| Constructor overload khó nhận biết | Ghi rõ target type hoặc lambda tường minh | Dễ review và chẩn đoán lỗi |
| Cần cấp phát array trong `Stream.toArray` | `String[]::new` | Đúng signature `IntFunction<String[]>` |
| Cần truyền factory cho thư viện có lifecycle riêng | Chọn đúng functional interface API nhận | Thư viện kiểm soát khi nào callback chạy |

**Nguyên tắc:** ưu tiên cách thể hiện ý định rõ nhất. `Type::new` không được coi là “tốt hơn” lambda về hiệu năng trong mọi trường hợp; hãy tối ưu tính đọc được trước, đo hiệu năng khi có yêu cầu thực tế.

## 11. Sai lầm phổ biến

1. **Nghĩ `Type::new` tạo object ngay:** nó chỉ tạo biểu thức tham chiếu hành vi; constructor chạy khi callback tương ứng được thực thi.
2. **Viết `Type::new()`:** constructor reference không đặt dấu ngoặc gọi trực tiếp sau `new`.
3. **Viết `var factory = Type::new`:** không có functional interface đích để compiler xác định descriptor.
4. **Chọn sai số đối số:** `Supplier<T>` không thể tham chiếu một constructor chỉ nhận một tham số bắt buộc.
5. **Nhầm capacity với size:** `new ArrayList<>(100)` không có sẵn 100 phần tử; `size()` vẫn là 0.
6. **Bỏ qua checked exception của constructor:** `Supplier.get()` không khai báo ngoại lệ checked; cần interface hoặc xử lý phù hợp.
7. **Cố tạo interface hoặc abstract class bằng `Type::new`:** không có constructor gọi trực tiếp theo cách đó.
8. **Nhầm array factory là multi-dimensional full allocation:** `String[][]::new` nhận một độ dài cho mảng ngoài, chưa cấp phát các hàng.
9. **Cho rằng constructor reference luôn chọn cùng constructor:** target type khác nhau có thể dẫn đến overload khác nhau.
10. **Dùng raw generic type không cần thiết:** suy luận kiểu rõ ràng với `Supplier<List<String>>` an toàn và dễ kiểm tra hơn.
11. **Nhầm `Type::new` với static factory:** `Type::of` tham chiếu static method, không phải constructor.
12. **Bỏ qua khả năng callback được gọi nhiều lần:** một `Supplier<T>` có thể tạo nhiều đối tượng, nên không dùng như một biến giữ singleton cố định khi ý định là cache.

## 12. Bài tập tự kiểm tra

**Bài 1.** Với `Function<String,Ticket> factory = Ticket::new;`, thời điểm nào constructor chạy?

**Trả lời:** khi lời gọi như `factory.apply("A")` thực hiện, không phải ngay lúc khai báo factory.

**Bài 2.** Tại sao `Supplier<ArrayList<String>> list = ArrayList::new;` hợp lệ, còn `Supplier<List<String>> list = List::new;` không hợp lệ?

**Trả lời:** `ArrayList` là class cụ thể có constructor phù hợp; `List` là interface không thể khởi tạo trực tiếp.

**Bài 3.** Với `IntFunction<int[]> create = int[]::new;`, `create.apply(5)` trả gì?

**Trả lời:** một mảng `int[]` mới có độ dài 5, các phần tử ban đầu bằng 0.

**Bài 4.** `IntFunction<String[][]> create = String[][]::new;` rồi `create.apply(3)` tạo mấy hàng?

**Trả lời:** mảng ngoài dài 3, mỗi phần tử hàng lúc đầu `null`; chưa có các mảng con.

**Bài 5.** Tại sao `Function<Integer,ArrayList<String>> f = ArrayList::new;` không tạo danh sách có số phần tử bằng đối số?

**Trả lời:** constructor `ArrayList(int)` đặt sức chứa ban đầu, còn số phần tử hiện có là 0.

**Bài 6.** Nếu constructor ném checked exception và callback là `Supplier<T>`, nên làm gì?

**Trả lời:** chọn callback khác cho phép ngoại lệ phù hợp, thiết kế wrapper/lambda xử lý lỗi rõ ràng, hoặc sử dụng factory API có hợp đồng ngoại lệ thích hợp; không giả định `Supplier` tự cho phép checked exception.

**Bài 7.** `Stream<String>.map(Ticket::new)` cần constructor nào của `Ticket`?

**Trả lời:** constructor nhận `String` (hoặc một overload tương thích, được compiler chọn theo descriptor); `map` cần `Function<String,Ticket>` phù hợp.

**Bài 8.** Khi nào viết `x -> new Type(transform(x))` tốt hơn `Type::new`?

**Trả lời:** khi trước lúc gọi constructor cần biến đổi, kiểm tra hoặc kết hợp tham số; reference trực tiếp không chứa logic tùy chỉnh đó.

## 13. Tài liệu tham khảo

- [Java Language Specification 17, §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13).
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9).
- [Java Language Specification 17, §15.10 — Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10).
- [Java SE 17 API, IntFunction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/IntFunction.html).
- [Java SE 17 API, Stream.toArray(IntFunction)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toArray(java.util.function.IntFunction)).

**Ghi nhớ:** `Type::new` kết nối **constructor** với **functional interface**. Kiểu đích quyết định số/kiểu tham số và kết quả, constructor vẫn tuân thủ overload, accessibility và checked exception. Với array, `T[]::new` là một hàm cấp phát mảng theo độ dài `int`. Dùng reference khi chỉ cần chuyển đối số trực tiếp cho constructor; dùng lambda/factory method khi cần thêm logic hoặc ngữ nghĩa khác.
