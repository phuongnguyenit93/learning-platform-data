# ObjIntConsumer và phối hợp đối tượng với kiểu nguyên thủy trong Java

## 1. Mục tiêu

**ObjIntConsumer<T>** là functional interface thuộc **java.util.function**. Nó nhận một đối tượng kiểu **T** và một giá trị nguyên thủy **int**, thực hiện một hành động rồi kết thúc mà không trả về giá trị. Đây là công cụ phù hợp khi bạn cần truyền hành vi xử lý cặp **đối tượng + số nguyên**, ví dụ nhập thêm số lượng vào một mặt hàng, cộng điểm cho tài khoản hoặc ghi một giá trị số vào bộ đệm.

Sau bài học, bạn có thể nhận ra chữ ký SAM, viết lambda và method reference tương thích, phân biệt ObjIntConsumer với BiConsumer/IntConsumer và các specialization khác, phối hợp nhiều thao tác theo thứ tự, kiểm soát tác dụng phụ, null, tràn số và truy cập đồng thời.

## 2. Chữ ký của ObjIntConsumer<T>

Khai báo được đơn giản hóa từ Java 17:

~~~java
@FunctionalInterface
public interface ObjIntConsumer<T> {
    void accept(T t, int value);
}
~~~

Đây là mô tả để học **API có sẵn trong JDK**, không phải code cần tự khai báo lại. Import khi sử dụng:

~~~java
import java.util.function.ObjIntConsumer;
~~~

Đọc từng phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| **T** | Kiểu tham chiếu của đối số thứ nhất, chẳng hạn Account, Stock, StringBuilder |
| **int** | Kiểu nguyên thủy của đối số thứ hai, chẳng hạn số lượng hay điểm |
| **accept(T t, int value)** | Phương thức trừu tượng duy nhất (SAM) |
| **void** | Không có giá trị trả về; tác dụng của lời gọi thường nằm ở việc cập nhật hoặc thao tác với dữ liệu |
| **@FunctionalInterface** | Cho phép trình biên dịch kiểm tra hợp đồng một SAM |

Do có đúng một phương thức trừu tượng, ObjIntConsumer dùng được **lambda** và **method reference**. Lambda được xác định kiểu theo ngữ cảnh gán (target typing):

~~~java
ObjIntConsumer<StringBuilder> appendNumber =
        (builder, number) -> builder.append(number);

StringBuilder b = new StringBuilder("Qty=");
appendNumber.accept(b, 12);
System.out.println(b); // Qty=12
~~~

Ở đây **builder** có kiểu StringBuilder và **number** là primitive int. Dòng **appendNumber.accept(b, 12)** thay đổi chính đối tượng b. Giá trị trả về **void** không đồng nghĩa không có kết quả quan sát được: đối tượng hoặc tài nguyên bên ngoài có thể đã thay đổi.

**Cần nhận diện đúng rằng generic T chỉ áp dụng cho đối số thứ nhất.** Chữ ký này luôn nhận int ở vị trí thứ hai; không thể viết ObjIntConsumer<Account, Integer> hoặc ObjIntConsumer<Account, Long> vì interface chỉ có một type parameter.

## 3. So sánh với các interface liên quan

| Interface | SAM | Chức năng |
| --- | --- | --- |
| **Consumer<T>** | **void accept(T t)** | Nhận một đối tượng |
| **IntConsumer** | **void accept(int value)** | Nhận một int |
| **BiConsumer<T,U>** | **void accept(T t, U u)** | Nhận hai đối tượng |
| **ObjIntConsumer<T>** | **void accept(T t, int value)** | Nhận một đối tượng và một int |
| **ObjLongConsumer<T>** | **void accept(T t, long value)** | Nhận một đối tượng và một long |
| **ObjDoubleConsumer<T>** | **void accept(T t, double value)** | Nhận một đối tượng và một double |
| **BiFunction<T,U,R>** | **R apply(T t, U u)** | Nhận hai đối tượng và trả một kết quả |

**ObjIntConsumer không phải là interface con của BiConsumer.** Nó là một **biến thể chuyên biệt (primitive specialization)** cho trường hợp đối số thứ hai là int. Vì vậy bạn không thể trực tiếp gán biến ObjIntConsumer<T> cho biến BiConsumer<T,Integer>; cần lambda adapter nếu API yêu cầu đổi interface.

### 3.1. Primitive giúp tránh boxing ở ranh giới SAM

So sánh:

~~~java
BiConsumer<StringBuilder, Integer> boxed =
        (target, number) -> target.append(number);

ObjIntConsumer<StringBuilder> primitive =
        (target, number) -> target.append(number);
~~~

BiConsumer sử dụng **Integer** vì type parameter của generic không thể là primitive. Khi gọi **boxed.accept(builder, 42)** với đối số literal int, Java phải thực hiện autoboxing để đưa 42 thành Integer phù hợp với SAM. ObjIntConsumer nhận **int trực tiếp**, nên không cần boxing chỉ để truyền đối số thứ hai qua lời gọi **accept**.

Điều này giảm nhu cầu chuyển kiểu không cần thiết, nhất là khi xử lý rất nhiều giá trị nguyên thủy. Tuy vậy, **không nên kết luận mọi chương trình dùng ObjIntConsumer đều chạy nhanh hơn**: JIT, escape analysis, allocation và phần code bên trong còn ảnh hưởng nhiều. Nếu hiệu năng là mục tiêu, cần benchmark đúng tình huống thực tế.

### 3.2. Khi nào chọn loại nào?

- Cần **thực hiện hành động** trên một đối tượng và một số nguyên: ObjIntConsumer<T>.
- Cần cập nhật một đối tượng cùng số **long** hay **double**: ObjLongConsumer<T> hoặc ObjDoubleConsumer<T>.
- Cần hành động trên hai kiểu tham chiếu: BiConsumer<T,U>.
- Cần **trả kết quả mới** thay vì chỉ thực hiện hiệu ứng: BiFunction hoặc phương thức miền nghiệp vụ thích hợp.
- Cần một hành động chỉ nhận primitive int: IntConsumer.

Chọn interface theo **hợp đồng** hơn là chạy theo sự ngắn gọn của lambda.

## 4. Viết lambda và method reference

Một ObjIntConsumer có thể được biểu diễn bằng lambda:

~~~java
ObjIntConsumer<StringBuilder> addInt =
        (builder, amount) -> builder.append(amount);
~~~

Hoặc method reference:

~~~java
ObjIntConsumer<StringBuilder> addInt =
        StringBuilder::append;
~~~

Cả hai đoạn ở trên là những lựa chọn thay thế nhau, **không khai báo cùng tên addInt trong cùng một scope**. Method reference **StringBuilder::append** dùng đối số đầu của **accept** làm receiver (builder), đối số thứ hai làm tham số **append(int)**. Mặc dù **append(int)** trả StringBuilder, lời gọi của nó có thể phù hợp với mục tiêu **void** khi kết quả bị bỏ đi.

Nếu lớp tự định nghĩa như sau:

~~~java
class Counter {
    private int total;

    void add(int value) {
        total = Math.addExact(total, value);
    }

    int total() {
        return total;
    }
}
~~~

Thì:

~~~java
ObjIntConsumer<Counter> increase = Counter::add;
Counter c = new Counter();
increase.accept(c, 3);
System.out.println(c.total()); // 3
~~~

Hai đoạn code cần nằm trong ngữ cảnh có khai báo lớp Counter và import ObjIntConsumer; đây là ví dụ **mảnh ghép**, không phải file độc lập.

**Không cần dùng lambda trong mọi trường hợp.** Nếu consumer không được truyền đi hoặc kết hợp, lời gọi **counter.add(3)** trực tiếp đôi khi rõ ràng hơn. Consumer hữu ích khi hành vi được cung cấp như tham số của một API, được chuyển cho lớp điều phối hoặc được cấu hình động.

## 5. Định nghĩa hợp đồng cập nhật rõ ràng

ObjIntConsumer thường biểu diễn một **side effect**. Tác vụ nhận dữ liệu và có thể:

- Sửa trạng thái đối tượng nhận vào.
- Ghi dữ liệu hoặc gọi API khác.
- Tích lũy số vào một accumulator.
- Ghi log hoặc phát sự kiện.

Vì **accept** trả void, nơi gọi không thể lấy một giá trị kết quả mới trực tiếp từ lời gọi. Nếu trạng thái thay đổi, kết quả được quan sát qua đối tượng hoặc hệ thống ngoài.

Trước khi viết consumer, hãy làm rõ:

1. **Ý nghĩa của int:** giá trị tăng thêm, giá trị tuyệt đối, vị trí, đơn vị hay mã trạng thái?
2. **Miền giá trị:** 0 có hợp lệ không? Có cho phép âm không? Giới hạn tối đa?
3. **Quyền sở hữu đối tượng:** có được sửa trực tiếp không, hay phải tạo bản sao?
4. **Thất bại:** dữ liệu null, tràn số hoặc lỗi I/O được phát hiện ở đâu?
5. **Đồng thời:** có nhiều thread cùng sửa một object không?

Đối với một phương thức tính toán thuần mong trả đối tượng mới, nên chọn một kiểu **có giá trị trả về**. Consumer không làm dữ liệu bất biến hay tạo transaction tự động.

## 6. Phối hợp các bước: không có andThen()

Một khác biệt dễ nhầm trong Java 17: **ObjIntConsumer<T> không cung cấp default method andThen()**. Điều này khác với Consumer<T>, IntConsumer và BiConsumer<T,U>, vốn có **andThen**.

Đoạn sau **không biên dịch**:

~~~java
// ObjIntConsumer<Stock> validate = ...;
// ObjIntConsumer<Stock> update = ...;
// ObjIntConsumer<Stock> both = validate.andThen(update);
~~~

Muốn làm nhiều việc theo thứ tự, hãy ghép bằng một lambda mới:

~~~java
ObjIntConsumer<Stock> combined = (item, amount) -> {
    validate.accept(item, amount);
    update.accept(item, amount);
};
~~~

Đoạn này giả định **Stock**, **validate** và **update** đã được định nghĩa trong ngữ cảnh.

Có thể tạo một hàm trợ giúp dùng lại ở nơi cần thiết:

~~~java
static <T> ObjIntConsumer<T> sequence(
        ObjIntConsumer<? super T> first,
        ObjIntConsumer<? super T> second) {
    java.util.Objects.requireNonNull(first);
    java.util.Objects.requireNonNull(second);
    return (target, number) -> {
        first.accept(target, number);
        second.accept(target, number);
    };
}
~~~

Đây là **phương thức minh họa** cần đặt trong một lớp có import ObjIntConsumer. Nếu **first.accept** ném exception, **second.accept** sẽ không được gọi. Nếu first đã thay đổi trạng thái và second mới thất bại, lambda **không tự rollback** trạng thái.

Để điều phối tác vụ gồm validation, update và audit, một thứ tự phổ biến là:

~~~text
Đối tượng + int
    |
    v
validate -- thất bại --> thông báo lỗi
    |
    v
update  -- thất bại --> thông báo lỗi
    |
    v
audit thành công
~~~

Thứ tự này chỉ mô tả lời gọi; nếu cần giao dịch nguyên tử hoặc bảo đảm event được ghi sau commit database, hãy thiết kế transaction/outbox hoặc cơ chế điều phối riêng.

## 7. Chương trình Java 17 hoàn chỉnh: nhập kho

Ví dụ quản lý tồn kho dưới đây kết hợp **ObjIntConsumer<Stock>**, method reference, một mảng **int[]**, và adapter sang **BiConsumer<Stock,Integer>**. Phần validation, cập nhật và báo kết quả được tách thành từng hành động.

Tạo file **ObjIntConsumerDemo.java**:

~~~java
import java.util.Objects;
import java.util.function.BiConsumer;
import java.util.function.ObjIntConsumer;

public class ObjIntConsumerDemo {
    static final class Stock {
        private final String sku;
        private int units;

        Stock(String sku, int units) {
            this.sku = Objects.requireNonNull(sku);
            if (units < 0) {
                throw new IllegalArgumentException("Negative initial stock");
            }
            this.units = units;
        }

        String sku() {
            return sku;
        }

        int units() {
            return units;
        }

        void receive(int amount) {
            units = Math.addExact(units, amount);
        }
    }

    public static void main(String[] args) {
        Stock notebook = new Stock("NOTE", 10);
        Stock pen = new Stock("PEN", 0);

        ObjIntConsumer<Stock> validate = (item, amount) -> {
            Objects.requireNonNull(item, "item");
            if (amount < 0) {
                throw new IllegalArgumentException("Negative amount");
            }
        };

        ObjIntConsumer<Stock> update = Stock::receive;

        ObjIntConsumer<Stock> audit = (item, amount) ->
                System.out.println("Added " + amount + " to " + item.sku());

        ObjIntConsumer<Stock> receiveAndAudit = (item, amount) -> {
            validate.accept(item, amount);
            update.accept(item, amount);
            audit.accept(item, amount);
        };

        receiveAndAudit.accept(notebook, 4);

        BiConsumer<Stock, Integer> boxedAdapter =
                (item, amount) -> receiveAndAudit.accept(item, amount);
        boxedAdapter.accept(pen, 2);

        int[] laterDeliveries = {1, 3};
        for (int amount : laterDeliveries) {
            validate.accept(notebook, amount);
            update.accept(notebook, amount);
        }

        System.out.println("NOTE=" + notebook.units());
        System.out.println("PEN=" + pen.units());
    }
}
~~~

Dùng JDK 17 trở lên:

~~~bash
javac ObjIntConsumerDemo.java
java ObjIntConsumerDemo
~~~

**Đầu ra chính xác:**

~~~text
Added 4 to NOTE
Added 2 to PEN
NOTE=18
PEN=2
~~~

Giải thích:

- Notebook bắt đầu có 10 đơn vị. Lần nhận 4 làm số lượng thành 14 rồi in thông báo.
- Pen bắt đầu có 0 đơn vị. **boxedAdapter** nhận Integer và ủy quyền lại cho ObjIntConsumer; pen thành 2 và in thông báo.
- Vòng lặp **int[] {1, 3}** cộng tiếp 1 rồi 3 cho notebook, nên **14 → 15 → 18**. Vòng lặp chỉ chạy validation và update, không chạy audit; vì thế không có hai dòng Added bổ sung.
- **Stock::receive** là method reference nhận receiver Stock và tham số int, đúng hợp đồng **accept(Stock,int)**.
- **Math.addExact** phát sinh ArithmeticException khi tổng int vượt phạm vi, thay vì âm thầm tràn số. Phép tính được đánh giá trước khi gán nên nếu nó ném exception, trường **units** không bị cập nhật bởi chính lời gán đó.
- **main** sử dụng System.out.println và thay đổi đối tượng, nên đây là quy trình có tác dụng phụ. Không nên nhầm với hàm thuần.

**Giới hạn cần lưu ý:** phương thức **Stock.receive(int)** không trực tiếp cấm số âm; quy tắc đó hiện do **validate** kiểm tra ở lớp gọi. Nếu mọi đường cập nhật đều phải bảo vệ bất biến tồn kho, hãy đưa validation cốt lõi vào chính method Stock.receive hoặc một điểm cập nhật nghiệp vụ duy nhất. Không được coi một lambda bao ngoài là bảo vệ đầy đủ nếu caller khác vẫn có thể bỏ qua nó.

## 8. Kết hợp với mảng nguyên thủy và IntStream

Khi đã có một **Stock** và nhiều lượng nhập **int**, vòng lặp trực tiếp là lựa chọn đơn giản:

~~~java
int[] amounts = {2, 5, 1};
for (int amount : amounts) {
    receiver.accept(stock, amount);
}
~~~

Đoạn code minh họa giả định biến **receiver** là ObjIntConsumer<Stock> và **stock** đã khởi tạo. Không cần chuyển từng phần tử mảng thành Integer.

Dùng **IntStream** cũng được:

~~~java
java.util.Arrays.stream(amounts)
        .forEach(amount -> receiver.accept(stock, amount));
~~~

Ở đây **forEach** của IntStream đòi **IntConsumer**. Lambda **amount -> receiver.accept(stock, amount)** có một tham số int và capture tham chiếu **stock**; bên trong nó gọi ObjIntConsumer có hai đối số.

Điểm phải thận trọng: **forEach có thể là thao tác có side effect**. Nếu chạy stream song song mà nhiều callback cùng cập nhật **stock**, có thể sinh race condition hoặc kết quả không ổn định, trừ khi trạng thái và logic được đồng bộ đúng cách.

Khi có nhiều đối tượng và nhiều lượng cập nhật tương ứng, kiểm tra số lượng và quan hệ giữa hai nguồn trước khi xử lý:

~~~java
if (stocks.size() != amounts.length) {
    throw new IllegalArgumentException("Different lengths");
}
for (int i = 0; i < amounts.length; i++) {
    receiver.accept(stocks.get(i), amounts[i]);
}
~~~

Đoạn này cũng chỉ là mảnh ghép với các biến đã khai báo. Nếu lỗi ở phần tử thứ ba, hai phần tử đầu có thể đã được cập nhật. Nếu nghiệp vụ yêu cầu toàn bộ batch cùng thành công hoặc cùng thất bại, cần validate toàn bộ dữ liệu và có chiến lược transaction thích hợp, không thể dựa riêng vào vòng lặp.

## 9. Adapter giữa ObjIntConsumer và BiConsumer

Đôi lúc một API nhận BiConsumer<T,Integer> nhưng logic hiện có là ObjIntConsumer<T>. Ta có thể bọc:

~~~java
ObjIntConsumer<StringBuilder> primitive =
        StringBuilder::append;

BiConsumer<StringBuilder, Integer> boxed =
        (builder, number) -> primitive.accept(builder, number);
~~~

Đối với một API cần ObjIntConsumer, nhưng đã có BiConsumer:

~~~java
BiConsumer<StringBuilder, Integer> boxed =
        (builder, number) -> builder.append(number);

ObjIntConsumer<StringBuilder> primitive =
        (builder, number) -> boxed.accept(builder, number);
~~~

Hai đoạn là **hai cách chuyển riêng biệt**, dùng tên biến giống nhau nên không nên dán chung trong cùng scope.

Hợp đồng null cũng khác nhau:

- Tham số thứ hai **int** của ObjIntConsumer không thể là null.
- Tham số thứ hai **Integer** của BiConsumer có thể là null nếu API và lambda chấp nhận; khi unbox Integer null thành int sẽ ném **NullPointerException**.
- Tham số đầu **T** vẫn là tham chiếu và có thể null; cần chính sách cụ thể hoặc **Objects.requireNonNull**.

Adapter không tự sửa tính an toàn luồng, lỗi overflow hay tác dụng phụ của consumer gốc.

## 10. An toàn dữ liệu và đa luồng

Giao diện ObjIntConsumer **không cam kết thread safety**. Hai thread cùng gọi consumer lên một đối tượng mutable có thể gây mất cập nhật nếu thao tác cộng chỉ thực hiện đọc–tính–ghi thông thường:

~~~java
// Minh họa mô hình sai khi dùng chung counter chưa đồng bộ:
ObjIntConsumer<Counter> add = Counter::add;
add.accept(sharedCounter, 1);
~~~

Đây là mảnh ghép cần khai báo Counter, sharedCounter. Một thao tác như **total += delta** không tự bảo đảm nguyên tử. Các giải pháp tùy bối cảnh:

- Mỗi thread sở hữu một accumulator riêng, rồi gộp kết quả sau.
- Dùng **synchronized** hoặc lock để bảo vệ vùng kiểm tra và thay đổi trạng thái.
- Với duy nhất một bộ đếm phù hợp, cân nhắc **AtomicInteger**, kèm chính sách giới hạn/overflow phù hợp.
- Đưa cập nhật qua hàng đợi và xử lý tuần tự.
- Nếu có thể, chuyển từ mutation sang hàm tạo dữ liệu mới rồi điều phối trạng thái ở tầng có trách nhiệm.

Việc dùng ObjIntConsumer không khiến xử lý tự chạy bất đồng bộ. Lời gọi **accept(...)** bình thường chạy ngay trên thread đang gọi; muốn lập lịch thread phải thông qua thread/executor hoặc API khác.

## 11. Lỗi thường gặp khi sử dụng

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Viết ObjIntConsumer<T,Integer> | Interface chỉ có một generic T | Dùng ObjIntConsumer<T> |
| Mong **accept** trả một giá trị | SAM trả void | Dùng hàm trả kết quả |
| Gọi **a.andThen(b)** | ObjIntConsumer không có andThen | Viết lambda điều phối hoặc helper sequence |
| Truyền **Integer** null rồi unbox | Unboxing null gây NullPointerException | Kiểm tra null trước |
| Không xác định ý nghĩa số int | Người gọi nhầm amount với index hoặc giá trị tuyệt đối | Đặt tên và contract nghiệp vụ rõ ràng |
| Cộng int không kiểm tra tràn | Kết quả có thể quay vòng sai | Math.addExact hoặc kiểu số thích hợp |
| Bỏ qua kiểm tra giá trị âm | Số lượng trở thành dữ liệu không hợp lệ | Validate tại điểm bảo vệ bất biến |
| Cùng sửa đối tượng trên parallel stream | Race condition hoặc mất cập nhật | Quản lý ownership, đồng bộ hoặc thiết kế khác |
| Audit trước update rồi coi đã thành công | Có thể ghi thành công khi cập nhật thất bại | Xác định thứ tự và chiến lược lỗi/giao dịch |

## 12. Kiểm thử từng hợp đồng

Hãy kiểm tra ít nhất các trường hợp sau với consumer quản lý tồn kho:

1. Đối tượng có 5 đơn vị, nhận thêm 3 thì thành 8.
2. Lượng nhận bằng 0 có hợp lệ theo quy tắc hay không; nếu có thì không đổi số lượng.
3. Lượng âm bị từ chối trước cập nhật.
4. Đối tượng null bị từ chối, không chạy update hay audit.
5. Tại **Integer.MAX_VALUE**, cộng thêm 1 làm Math.addExact ném ArithmeticException và không ghi tổng đã tràn.
6. Nếu update thất bại, audit “thành công” không chạy.
7. Nếu có nhiều thread, test đúng thiết kế đồng bộ hoặc cơ chế quyền sở hữu, không suy luận tính nguyên tử từ functional interface.

Ví dụ kiểm tra phép cộng và trạng thái, đặt trong lớp được phép truy cập Stock:

~~~java
Stock item = new Stock("TEST", 5);
ObjIntConsumer<Stock> receive = Stock::receive;
receive.accept(item, 3);
if (item.units() != 8) {
    throw new AssertionError("Expected 8 units");
}
~~~

Một test đơn lẻ không chứng minh mọi điều kiện an toàn, đặc biệt với concurrency. Cần xem hợp đồng đối tượng, đường đi lỗi và cách người gọi sử dụng consumer.

## 13. Bài tập tự luyện

**Bài 1 — Chọn interface.** Chọn kiểu đúng cho bốn công việc: (a) cập nhật số điểm int của Student, (b) cập nhật lượng tiền long của Account, (c) chỉ in một int, (d) nhận hai đối tượng và trả về một đối tượng mới.

**Đáp án:** (a) ObjIntConsumer<Student>; (b) ObjLongConsumer<Account> nếu thật sự là hành động; (c) IntConsumer; (d) BiFunction<T,U,R> với các kiểu phù hợp.

**Bài 2 — Dự đoán output.**

~~~java
StringBuilder text = new StringBuilder("S=");
ObjIntConsumer<StringBuilder> append = StringBuilder::append;
append.accept(text, 3);
append.accept(text, 7);
System.out.println(text);
~~~

**Đáp án:** **S=37**. Hai số được nối vào chuỗi theo thứ tự; đây không phải phép cộng 3 + 7.

**Bài 3 — Chỉnh lỗi composition.**

~~~java
ObjIntConsumer<StringBuilder> first =
        (b, n) -> b.append(n);
ObjIntConsumer<StringBuilder> second =
        (b, n) -> b.append("!");
// Sai: first.andThen(second)
~~~

**Lời giải:**

~~~java
ObjIntConsumer<StringBuilder> both = (b, n) -> {
    first.accept(b, n);
    second.accept(b, n);
};
~~~

Với builder ban đầu **X** và n=2, kết quả sau một lời gọi **both.accept(builder, 2)** là **X2!**.

**Bài 4 — Thiết kế.** Một hệ thống cộng điểm cho Student bằng ObjIntConsumer<Student> nhưng có hai thread cùng cập nhật. Hãy đề xuất hợp đồng null, kiểm tra điểm âm/overflow, bảo vệ bất biến trong method của Student và một chiến lược đồng bộ hoặc sở hữu trạng thái phù hợp. Chỉ sau đó viết lambda hoặc method reference chuyển hành vi thành ObjIntConsumer.

## 14. Ghi nhớ

**ObjIntConsumer<T> có SAM void accept(T object, int value).** Đây là functional interface cho một hành động phối hợp đối tượng và **int nguyên thủy**, giúp tránh boxing không cần thiết ở tham số thứ hai của SAM. Nó **không phải BiConsumer con**, không có sẵn **andThen**, và lời gọi **accept** thông thường không tạo thread mới.

Khi dùng, hãy đặt ý nghĩa nghiệp vụ cho tham số số, kiểm tra null/miền giá trị/overflow, xác định thứ tự tác dụng phụ và ranh giới lỗi. Nếu cần kết quả mới thay vì cập nhật trạng thái, hãy chọn phương thức hoặc functional interface có giá trị trả về.
