# Phân biệt dùng lambda với thiết kế có tính chất hàm trong Java

## 1. Hai khái niệm ở hai cấp độ khác nhau

**Dùng lambda** là chọn một cách viết ngắn gọn để cung cấp hành vi cho một *functional interface* (giao diện có một phương thức trừu tượng). Lambda giúp truyền hành vi vào phương thức, tạo callback, triển khai `Comparator`, `Predicate`, `Function`, `Consumer` hoặc thao tác với Stream. Bản thân cú pháp `x -> ...` **không bảo đảm** chương trình được thiết kế theo phong cách hàm.

**Thiết kế có tính chất hàm** (*functional-style design*) là tổ chức dữ liệu, quy tắc nghiệp vụ và luồng xử lý theo các nguyên tắc như hàm thuần khiết, dữ liệu ít thay đổi, biến đổi dữ liệu rõ ràng, kết hợp các phép biến đổi và cô lập tác dụng phụ. Trong Java, có thể áp dụng các nguyên tắc này bằng phương thức thông thường, lambda, method reference, `record`, `Stream` và các functional interface. Không bắt buộc mọi phương thức đều là lambda hay mọi logic đều phải dùng Stream.

Ví dụ hai dòng sau cùng sử dụng lambda nhưng có tính chất thiết kế rất khác nhau:

~~~java
// Có tác dụng phụ: ghi vào trạng thái bên ngoài lambda.
orders.forEach(order -> mutableReport.add(order));

// Biến đổi từng giá trị rồi tổng hợp bằng phép toán trên dữ liệu.
long total = orders.stream().mapToLong(Order::total).sum();
~~~

Đây là **đoạn minh họa**, giả định `orders`, `mutableReport` và kiểu `Order` đã tồn tại. Dòng thứ hai tránh sửa `mutableReport` trong pipeline, nhưng chỉ được xem là thuần khiết nếu `Order::total` cũng không gây tác dụng phụ và không phụ thuộc trạng thái thay đổi bên ngoài.

## 2. Lambda thực sự mang lại điều gì?

Java không có kiểu hàm độc lập như một số ngôn ngữ hàm. Một biểu thức lambda được dùng trong *ngữ cảnh kiểu đích* là functional interface:

~~~java
java.util.function.Function<Integer, Integer> doubleIt = x -> x * 2;
java.util.function.Predicate<Integer> positive = x -> x > 0;
java.util.function.Consumer<String> printer = s -> System.out.println(s);
~~~

- `doubleIt` mô tả phép biến đổi; `positive` mô tả điều kiện; `printer` thực hiện I/O nên có tác dụng phụ.
- Lambda có thể được truyền như một giá trị qua biến, tham số hay kết quả theo kiểu functional interface, giúp tách hành vi khỏi nơi sử dụng.
- Lambda được phép đọc biến cục bộ bên ngoài nếu biến đó là `final` hoặc *effectively final*. Điều này chỉ giới hạn **việc gán lại biến tham chiếu**, không khiến đối tượng được tham chiếu trở thành bất biến.
- Method reference như `String::trim` hoặc `Order::total` là một cách cung cấp hành vi tương thích với functional interface; nó cũng không tự bảo đảm tính thuần khiết.

Ví dụ `List<String> buffer = new ArrayList<>();` có thể là biến effectively final, nhưng lambda `x -> buffer.add(x)` vẫn thay đổi nội dung danh sách. Tính hợp lệ của cú pháp và chất lượng thiết kế là hai câu hỏi riêng.

## 3. Nhận diện khác biệt khi đọc và thiết kế mã

| Góc nhìn | Chỉ sử dụng lambda | Thiết kế có tính chất hàm |
|---|---|---|
| Mục đích | Truyền một đoạn hành vi hoặc viết callback ngắn | Làm luồng dữ liệu và quy tắc biến đổi dễ suy luận, kết hợp và kiểm thử |
| Trạng thái | Có thể đọc/ghi biến chia sẻ, đối tượng mutable, database | Ưu tiên biến đổi từ đầu vào sang kết quả; giới hạn nơi cập nhật trạng thái |
| Hàm thuần | Không được bảo đảm bởi cú pháp `->` | Ưu tiên cùng đầu vào cho cùng kết quả, không có tác dụng phụ quan sát được |
| Dữ liệu | Có thể thay đổi collection trong `forEach` | Thường tạo kết quả mới, sử dụng giá trị không thay đổi trong quá trình xử lý |
| Kết hợp hành vi | Lambda có thể đứng riêng lẻ, thao tác từng bước | Dùng `map`, `filter`, `reduce`, `Function.compose` / `andThen` và hàm nhỏ |
| Dòng điều khiển | Có thể vẫn là vòng lặp mệnh lệnh viết bằng lambda | Mô tả *cần tính gì* qua các phép biến đổi có tên và hợp đồng rõ |
| Tác dụng phụ | Có thể xen vào bất kỳ bước nào | Đưa đọc/ghi, logging, gửi sự kiện đến ranh giới ứng dụng khi khả thi |
| Kiểm thử | Có thể phải dựng trạng thái hoặc mock nhiều phụ thuộc | Phần tính toán thuần dễ kiểm thử theo cặp đầu vào/kết quả |

Đây là các **xu hướng thiết kế**, không phải định nghĩa máy móc: một vòng `for` gọi hàm thuần có thể phù hợp hơn một Stream dài; một pipeline Stream chứa lambda cập nhật biến toàn cục vẫn mang tác dụng phụ.

## 4. Ví dụ chạy được: cùng tổng tiền, cách tiếp cận khác nhau

Lưu thành `LambdaVsDesign.java`:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class LambdaVsDesign {
    static int sumWithSideEffect(List<Integer> amounts) {
        AtomicInteger total = new AtomicInteger();
        amounts.forEach(amount -> total.addAndGet(amount));
        return total.get();
    }

    static int sumWithReduction(List<Integer> amounts) {
        return amounts.stream()
                .mapToInt(Integer::intValue)
                .sum();
    }

    public static void main(String[] args) {
        List<Integer> amounts = List.of(120, 80, 50);
        System.out.println("Lambda + state: " + sumWithSideEffect(amounts));
        System.out.println("Reduction: " + sumWithReduction(amounts));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac LambdaVsDesign.java
java LambdaVsDesign
~~~

Kết quả chuẩn:

~~~text
Lambda + state: 250
Reduction: 250
~~~

**Phân tích:**

1. `sumWithSideEffect` có lambda và dùng `forEach`, nhưng từng phần tử làm thay đổi đối tượng `AtomicInteger` nằm ngoài lambda. `AtomicInteger` giúp phép cộng nguyên tử giữa các luồng; nó **không làm** cho hàm trở thành hàm thuần hoặc biến kiểu xử lý này thành thiết kế hàm.
2. `sumWithReduction` mô tả đầu vào là danh sách số, phép chuyển sang `int` và phép tổng hợp `sum`. Không có accumulator mutable do mã ứng dụng quản lý trong callback. Việc thực thi bên trong Stream vẫn có thể dùng trạng thái nội bộ, nhưng hợp đồng bên ngoài là một phép tổng hợp giá trị.
3. Trong ví dụ này hai hàm cùng cho kết quả `250`. Giá trị đầu ra giống nhau **không đủ** để kết luận phong cách thiết kế giống nhau.
4. Danh sách được tạo bởi `List.of` không cho thêm, xóa hoặc thay phần tử. Vì `Integer` là kiểu giá trị bất biến, đầu vào này thuận lợi cho lập luận về trạng thái.
5. Ví dụ nhỏ dùng `int` để tập trung vào thiết kế; số lượng thực tế lớn có thể làm tràn `int`. Với giá trị tiền tệ thật cần mô hình đơn vị tiền và xử lý số, tràn và làm tròn phù hợp.

Lưu ý: `sumWithReduction` không sửa đầu vào nhưng vẫn nhận tham chiếu đến `List`. Nếu một caller khác thay đổi danh sách mutable trong lúc đọc, tính ổn định không còn được bảo đảm. Tính chất hàm cần xem xét cả **hợp đồng dữ liệu** và điều kiện sử dụng, chứ không chỉ đoạn mã trong thân phương thức.

## 5. Ví dụ thiết kế: lõi tính toán bằng hàm nhỏ, I/O ở ranh giới

Giả sử yêu cầu là: lọc các dòng hàng không phải quà tặng, tính tổng tiền, giảm 10%, rồi cộng 15 đơn vị phí vận chuyển. Thay vì vừa lặp vừa cập nhật tổng, sửa đơn hàng và in log giữa các bước, ta mô hình hóa dữ liệu và các phép tính độc lập.

Lưu thành `FunctionalOrderDemo.java`:

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class FunctionalOrderDemo {
    record Item(String code, int quantity, long unitPrice) {}

    static long lineTotal(Item item) {
        return Math.multiplyExact(item.unitPrice(), item.quantity());
    }

    static long subtotal(List<Item> items, Predicate<Item> includes) {
        return items.stream()
                .filter(includes)
                .mapToLong(FunctionalOrderDemo::lineTotal)
                .sum();
    }

    static long applyDiscount(long amount, int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("Invalid percent");
        }
        return amount - amount * percent / 100;
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("BOOK", 2, 100),
                new Item("PEN", 3, 20),
                new Item("GIFT", 1, 50)
        );

        Predicate<Item> nonGift = item -> !"GIFT".equals(item.code());
        long base = subtotal(items, nonGift);

        Function<Long, Long> discount10 =
                amount -> applyDiscount(amount, 10);
        Function<Long, Long> addShipping = amount -> amount + 15;
        Function<Long, Long> pricing = discount10.andThen(addShipping);

        System.out.println("Subtotal: " + base);
        System.out.println("Final: " + pricing.apply(base));
        System.out.println("Original lines: " + items.size());
    }
}
~~~

Chạy:

~~~bash
javac FunctionalOrderDemo.java
java FunctionalOrderDemo
~~~

Kết quả:

~~~text
Subtotal: 260
Final: 249
Original lines: 3
~~~

**Vì sao đây là ví dụ về thiết kế có tính chất hàm?**

- `Item` là `record` giữ dữ liệu đơn giản; ở ví dụ này các thành phần `String`, `int`, `long` không chứa collection mutable. `List.of` giữ cấu trúc danh sách không đổi.
- `lineTotal(item)` tính một kết quả từ một đầu vào, không đọc đồng hồ, không gọi dịch vụ và không sửa `item`; có thể kiểm tra riêng bằng dữ liệu cụ thể.
- `subtotal(items, includes)` nhận điều kiện lọc như tham số. `filter`, `mapToLong` và `sum` biểu diễn các bước **chọn → chuyển đổi → tổng hợp**. Để toàn phép tính có tính chất thuần, `includes` phải là predicate ổn định, không gây tác dụng phụ.
- `applyDiscount(amount, percent)` tách quy tắc giảm giá khỏi việc đọc đơn hàng. Với các đối số hợp lệ, kết quả có thể tính lại mà không thay đổi hệ thống.
- `discount10.andThen(addShipping)` cho thấy thành phần xử lý có thể **kết hợp theo thứ tự**: 260 giảm 10% thành 234, cộng 15 thành 249. Nếu đổi thứ tự, bài toán nghiệp vụ có thể cho giá trị khác.
- `System.out.println` là I/O có tác dụng phụ, được đặt ở `main` để hiển thị kết quả; ứng dụng thực tế có thể đặt thao tác lưu cơ sở dữ liệu, gửi HTTP hoặc phát sự kiện ở lớp điều phối tương tự.

**Giới hạn có chủ ý của ví dụ:** Phần tiền dùng số nguyên và phép chia nguyên để minh họa. Trong hệ thống thanh toán thật cần xác định đơn vị nhỏ nhất, chính sách làm tròn, cách tính nhiều loại thuế/giảm giá, giới hạn tràn số và thường chọn `BigDecimal` hoặc phép toán số nguyên được kiểm soát. `Math.multiplyExact` phát hiện tràn ở `lineTotal`, nhưng phép cộng trong `sum` và phép nhân ở công thức giảm giá chưa được kiểm soát tràn. Đây không phải mã thanh toán triển khai sản xuất.

## 6. Những nguyên tắc làm nên thiết kế có tính chất hàm

### 6.1. Hàm thuần và tính dễ dự đoán

Một hàm thuần có hai đặc điểm chính:

1. Với cùng các đầu vào có ý nghĩa, hàm trả về cùng kết quả.
2. Việc gọi hàm không tạo tác dụng phụ quan sát được: không thay dữ liệu caller, biến toàn cục, file, database hoặc gửi thông điệp.

`static int square(int x) { return x * x; }` là ví dụ đơn giản. Ngược lại, `x -> x + counter.get()` phụ thuộc vào `counter` bên ngoài, còn `x -> log.info("x={}", x)` có hiệu ứng logging dù mang cú pháp lambda. Một hàm có thể trả kết quả xác định nhưng vẫn không thuần nếu âm thầm cập nhật thống kê.

Tính thuần khiết giúp viết kiểm thử trực tiếp, thay thế một lần gọi bằng kết quả của nó khi hợp lệ, dễ cache hơn và giảm việc phải hiểu lịch sử thực thi. Tuy vậy, Java không có bộ kiểm tra kiểu bắt buộc hàm thuần; đó là đặc tính ta thiết kế và duy trì bằng hợp đồng, review và test.

### 6.2. Dữ liệu bất biến và tránh chia sẻ trạng thái thay đổi

Ưu tiên truyền vào một giá trị và trả về giá trị mới. Đừng để một phép tính bất ngờ sửa collection mà caller đang giữ. `List.of`, `List.copyOf`, `record` hoặc lớp immutable có thể giúp, song cần hiểu:

- `final` ngăn gán lại một biến hay trường; không khiến đối tượng được trỏ đến bất biến.
- `record` chỉ giữ trường `final` ở mức nông: nếu thành phần là `List` mutable hoặc một bean mutable, trạng thái bên trong vẫn có thể đổi.
- `List.copyOf` tạo danh sách không thể sửa qua danh sách kết quả nhưng không sao chép sâu các đối tượng phần tử.
- Giảm mutability thường giúp lý luận về concurrency; nó không tự bảo đảm mọi thao tác là thread-safe khi còn dịch vụ hoặc dữ liệu chia sẻ khác.

### 6.3. Hàm bậc cao và kết hợp hành vi

Hàm bậc cao là hàm nhận hàm hoặc trả hàm. Trong Java, điều này thường thực hiện qua `Predicate<T>`, `Function<T,R>`, `UnaryOperator<T>`, `Consumer<T>`, `Supplier<T>` hoặc functional interface tự định nghĩa.

Ví dụ dùng `Predicate.and` để xây điều kiện từ các quy tắc nhỏ:

~~~java
java.util.function.Predicate<String> nonBlank = s -> s != null && !s.isBlank();
java.util.function.Predicate<String> shortText = s -> s.length() <= 12;
java.util.function.Predicate<String> accepted = nonBlank.and(shortText);
~~~

Đây là **đoạn minh họa** để chèn vào một phương thức. Toán tử `and` đánh giá ngắn mạch theo thứ tự: nếu `nonBlank` sai thì `shortText` không chạy, nhờ vậy giá trị `null` không gây lỗi ở `length()`. Kết hợp predicate chỉ giữ được khả năng dự đoán nếu các predicate thành phần không dựa vào trạng thái thay đổi.

### 6.4. Biến đổi dữ liệu thay vì thao tác trên accumulator chia sẻ

Trong pipeline Stream, `filter` chọn phần tử, `map` chuyển đổi phần tử, `flatMap` làm phẳng các tập kết quả và `reduce`/`collect`/`sum` tổng hợp. Các phép trung gian thường thực thi lười cho đến khi gọi terminal operation. Pipeline thường nên có các hành vi **không can thiệp nguồn** (*non-interfering*) và **không phụ thuộc trạng thái mutable ngoài pipeline** (*stateless*).

Các API Stream không tự làm sạch tác dụng phụ trong lambda. `map(x -> { audit.add(x); return x * 2; })` vẫn ghi vào `audit`; `peek` cũng không phải nơi tin cậy để chạy nghiệp vụ có hiệu ứng vì thời điểm/số lần callback được chạy phụ thuộc vào cách pipeline được thực thi và tối ưu hóa.

### 6.5. Lõi hàm, vỏ điều phối tác dụng phụ

Chương trình Java thực tế bắt buộc có I/O: HTTP, database, hàng đợi, log, cache... Một cấu trúc thực dụng là:

1. **Nhận dữ liệu** từ controller, repository hoặc message.
2. **Chuyển về mô hình đầu vào rõ ràng** rồi gọi các hàm tính toán/kiểm tra độc lập.
3. **Nhận kết quả và quyết định hiệu ứng**, ví dụ lưu hoặc gửi sự kiện, tại lớp điều phối.
4. **Kiểm soát lỗi và transaction** ở ranh giới thích hợp.

Vỏ điều phối có thể viết mệnh lệnh; lõi tính toán có thể dùng vòng lặp hoặc Stream tùy cách rõ ràng nhất. Mục tiêu là đặt hiệu ứng nơi dễ nhìn thấy, tránh để một hàm tên `calculateTotal` lại âm thầm ghi database.

## 7. Những nhầm lẫn và lỗi phổ biến

**Nhầm 1: Có `->` nghĩa là lập trình hàm.** Sai. `list.forEach(x -> repository.save(x))` chỉ chuyển tác dụng phụ sang callback. Việc lưu từng phần tử có thể hoàn toàn hợp lý, nhưng đây vẫn là thao tác I/O cần chính sách transaction, lỗi và idempotency.

**Nhầm 2: Stream luôn tốt hơn vòng lặp.** Sai. Một `for` ngắn, rõ ràng, gọi các hàm thuần có thể dễ đọc, dễ debug hơn pipeline dùng nhiều `flatMap` hoặc xử lý ngoại lệ phức tạp. Chọn mô hình theo yêu cầu và khả năng giải thích.

**Nhầm 3: `final` hay effectively final biến dữ liệu thành bất biến.** Sai. Lambda có thể thay đổi các trường hoặc phần tử trong đối tượng được capture, dù không thể gán lại biến cục bộ đó.

**Nhầm 4: Có `AtomicInteger` thì `forEach` có side effect tương đương reduce.** Sai. Atomicity giải quyết một vấn đề đồng bộ cụ thể; nó không thay tính phụ thuộc vào trạng thái hay làm biểu thức tự có hợp đồng tổng hợp đúng.

**Nhầm 5: Chuyển sang `parallelStream()` sẽ tự an toàn hoặc nhanh hơn.** Sai. `parallelStream().forEach(x -> sharedList.add(x))` có nguy cơ race với `ArrayList`; thứ tự `forEach` cũng không được bảo đảm. Phép reduce song song cần phép kết hợp thích hợp (thường là kết hợp được, có phần tử đơn vị đúng), nguồn và hành vi không can thiệp, không phụ thuộc trạng thái ngoài. Cũng cần đo hiệu năng với dữ liệu thực, không suy luận từ cú pháp.

**Nhầm 6: Callback in log hay gọi HTTP là hàm thuần vì không sửa tham số.** Sai. Tác dụng phụ bao gồm hiệu ứng ra bên ngoài, không chỉ sửa đối số.

**Nhầm 7: Method reference luôn thuần.** Sai. `service::send` vẫn gửi dữ liệu ra bên ngoài, còn `object::increment` vẫn có thể đổi trạng thái đối tượng.

**Nhầm 8: Muốn thiết kế hàm phải loại bỏ OOP.** Sai. Java thường kết hợp OOP để đóng gói mô hình, interface để biểu diễn hợp đồng, và nguyên tắc hàm cho các quy tắc biến đổi. `record`, lớp immutable và dependency injection có thể cùng tồn tại với thiết kế hàm.

## 8. Cách chuyển một đoạn mã sang thiết kế dễ suy luận

Giả sử gặp một phương thức vừa duyệt danh sách, sửa đối tượng, cập nhật tổng và lưu database. Có thể cải thiện theo thứ tự:

1. **Liệt kê đầu vào, kết quả và hiệu ứng**: dữ liệu nào thật sự cần để tính toán, kết quả là gì, chỗ nào đang ghi trạng thái hoặc I/O?
2. **Tách quy tắc tính toán** thành các phương thức nhận tham số cụ thể và trả giá trị; kiểm tra chúng bằng ví dụ đầu vào/kết quả.
3. **Giảm chia sẻ mutable state**: tạo snapshot khi cần, dùng loại dữ liệu phù hợp, hạn chế sửa đối tượng đầu vào.
4. **Kết hợp các phép biến đổi** bằng phương thức thường, `Predicate`/`Function` hoặc Stream nếu chúng làm ý định rõ hơn.
5. **Đưa hiệu ứng ra ranh giới**: lưu kết quả, log hoặc gửi thông điệp sau khi phần tính toán xác định kết quả mong muốn.
6. **Kiểm tra lại hành vi nghiệp vụ**: thứ tự giảm giá/thuế/phí, lỗi, null, overflow, trạng thái đồng thời và hiệu năng. Chỉ thay đổi cấu trúc sau khi có bằng chứng kết quả tương đương.

Đừng cố “đổi mọi vòng lặp thành lambda”. Hãy bắt đầu từ **hợp đồng dữ liệu, kiểm soát trạng thái và tách hiệu ứng**; cú pháp lambda chỉ là công cụ thuận tiện để diễn đạt.

## 9. Câu hỏi tự kiểm tra

1. `items.forEach(item -> inventory.decrease(item))` có lambda nhưng có thuần không? Vì sao?
2. Vì sao `String::trim` và `repository::save` đều có thể là method reference nhưng khác nhau về hiệu ứng?
3. Nếu một lambda capture danh sách `final` rồi gọi `add`, đảm bảo nào của `final` vẫn đúng và đảm bảo nào **không** có?
4. Phép tổng hợp bằng `mapToLong(...).sum()` có ích gì so với callback sửa accumulator bên ngoài? Khi nào phần lambda bên trong Stream vẫn có thể vi phạm nguyên tắc hàm?
5. Trong ví dụ tính đơn hàng, nếu thực hiện cộng phí trước rồi mới giảm 10%, kết quả có còn là 249 không? Quy tắc nào quyết định thứ tự đúng?
6. Vì sao không thể kết luận pipeline an toàn khi chạy song song nếu không biết hàm được truyền vào `filter` và `map` làm gì?

**Kết luận học tập:** Lambda là **cú pháp biểu diễn và truyền hành vi** qua functional interface. Thiết kế có tính chất hàm là **cách tổ chức dữ liệu và hiệu ứng** để quy tắc dễ dự đoán, kết hợp và kiểm thử. Ta có thể dùng lambda mà không thiết kế theo phong cách hàm; cũng có thể có thiết kế hàm tốt mà chỉ dùng phương thức Java thông thường.