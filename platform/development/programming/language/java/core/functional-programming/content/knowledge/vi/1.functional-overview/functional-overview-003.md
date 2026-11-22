# Mối liên hệ giữa hàm, dữ liệu, lambda và Stream trong Java

## 1. Bức tranh tổng thể

Trong lập trình Java, một tác vụ xử lý dữ liệu thường có dạng: lấy danh sách đầu vào, chọn ra các phần tử phù hợp, chuyển mỗi phần tử thành thông tin cần thiết, rồi tổng hợp thành kết quả. Bốn khái niệm **dữ liệu**, **hàm**, **lambda** và **Stream** đảm nhận những vai trò liên quan nhau nhưng khác nhau:

| Thành phần | Câu hỏi nó trả lời | Hình thức điển hình trong Java |
| --- | --- | --- |
| **Dữ liệu** | Chúng ta đang xử lý những giá trị nào? | Một Order, List<Order>, mảng, tập hợp, các giá trị số/chữ |
| **Hàm / hành vi** | Phải làm gì với từng giá trị? | Kiểm tra điều kiện, biến đổi kiểu, tính tiền, kết hợp hai giá trị |
| **Lambda / method reference** | Biểu diễn và truyền hành vi đó bằng cú pháp nào? | order -> order.paid(), Order::amount |
| **Stream** | Kết nối và thực thi các bước xử lý thành quy trình ra sao? | stream().filter(...).map(...).toList() |

Có thể đọc một pipeline theo cách sau:

~~~text
Dữ liệu nguồn (List<Order>)
    |
    | stream()
    v
Stream<Order>
    | filter(Predicate<Order>)       -- chọn phần tử
    v
Stream<Order>
    | map(Function<Order, String>)  -- biến đổi mỗi phần tử
    v
Stream<String>
    | distinct() / sorted()         -- xử lý bổ sung nếu cần
    v
toList()                            -- thao tác kết thúc
    |
    v
Dữ liệu kết quả (List<String>)
~~~

**Điểm mấu chốt:** dữ liệu là *đối tượng xử lý*; hàm xác định *quy tắc xử lý*; lambda là *một cách cung cấp hàm*; Stream là *cơ chế tổ chức và thực thi chuỗi thao tác*. Không thể thay thế trực tiếp khái niệm này bằng khái niệm khác: Stream không phải dữ liệu đã được tính sẵn, và lambda tự nó không phải Stream.

## 2. Dữ liệu là đầu vào và đầu ra

Java dùng object, giá trị nguyên thủy, array và collection để biểu diễn dữ liệu. Ví dụ, ta mô hình hóa đơn hàng bằng một record:

~~~java
record Order(String id, String customer, long amount, boolean paid) {}
~~~

Record giúp khai báo dữ liệu ngắn gọn và sinh các accessor như id(), customer(), amount(), paid(). Nó phù hợp để mang giá trị qua các bước xử lý. Tuy nhiên, record chỉ bảo đảm bất biến nông: nếu một thành phần chứa đối tượng có thể sửa, đối tượng đó vẫn có thể thay đổi bên trong.

Một nguồn Stream thường đến từ collection:

~~~java
List<Order> orders = List.of(
    new Order("O1", "Linh", 120_000, true),
    new Order("O2", "Nam", 75_000, false)
);
Stream<Order> source = orders.stream();
~~~

Đây là **đoạn mã minh họa**, giả định đã import java.util.List và java.util.stream.Stream, và đặt trong một phương thức hoặc class. Collection là nơi chứa các phần tử; Stream đại diện cho một quy trình xử lý chúng. Khi tạo Stream, không có nghĩa toàn bộ nguồn đã được biến đổi hoặc sao chép.

Danh sách List.of không cho phép thêm, xóa hay thay phần tử, nhưng điều đó không tự động làm mọi phần tử bất biến. Với ví dụ Order chỉ chứa String và kiểu nguyên thủy, các trường dữ liệu đáp ứng tốt cách lập luận theo giá trị.

Nguồn không nhất thiết phải là List: Arrays.stream(...), Stream.of(...), IntStream.range(...) và nhiều API khác cũng có thể cung cấp Stream. Dữ liệu còn có thể được tạo từng phần khi pipeline được tiêu thụ.

## 3. Hàm là quy tắc biến đổi hoặc kiểm tra giá trị

Trong Java, **method** là một khai báo hành vi trong class/interface. Khi nói **hàm** trong lập trình hàm, ta thường nhấn mạnh một phép toán nhận dữ liệu vào và trả giá trị hoặc quyết định, có thể truyền như một thành phần xử lý.

Ví dụ hai phép toán:

~~~java
static boolean isPaid(Order order) {
    return order.paid();
}

static String customerName(Order order) {
    return order.customer();
}
~~~

Đây cũng là **đoạn minh họa**, đặt trong một class chứa hoặc truy cập được kiểu Order. Quy tắc thứ nhất kiểm tra một đơn; quy tắc thứ hai lấy tên khách. Một hàm rõ ràng có thể được kiểm thử riêng và tái sử dụng ở nhiều nơi.

Để truyền hành vi vào API trong Java, ta thường dùng **functional interface**: giao diện có một phương thức trừu tượng theo quy tắc SAM (*single abstract method*). Một số kiểu chuẩn từ java.util.function:

| Kiểu | Phương thức | Dùng cho |
| --- | --- | --- |
| Predicate<T> | boolean test(T value) | Kiểm tra điều kiện, thường truyền vào filter |
| Function<T, R> | R apply(T value) | Chuyển phần tử T thành phần tử R, thường truyền vào map |
| Consumer<T> | void accept(T value) | Thực hiện tác vụ có tác dụng phụ, ví dụ hiển thị |
| Supplier<T> | T get() | Cung cấp giá trị khi cần |
| UnaryOperator<T> | T apply(T value) | Trường hợp đặc biệt Function<T, T> |
| BinaryOperator<T> | T apply(T left, T right) | Kết hợp hai giá trị cùng kiểu |
| ToLongFunction<T> | long applyAsLong(T value) | Chuyển sang long, dùng với mapToLong tránh boxing |

**Functional interface là kiểu dữ liệu của hành vi; lambda là phần cài đặt hành vi.** Ví dụ Predicate<Order> diễn đạt một điều kiện nhận Order và trả boolean. Điều này khác Predicate<String>, vì kiểu tham số quyết định phép toán nào hợp lệ.

## 4. Lambda kết nối quy tắc với API

Lambda biểu diễn phần thân của một phương thức hàm bằng cú pháp ngắn:

~~~java
Predicate<Order> paid = order -> order.paid();
Function<Order, String> customer = order -> order.customer();
~~~

Các ví dụ trên giả định đã import java.util.function.Predicate và Function. Dấu mũi tên phân tách tham số với biểu thức/thân lệnh. Java suy luận kiểu tham số từ **kiểu đích** (*target type*) của functional interface. Đặc điểm quan trọng này giải thích vì sao Java không đối xử lambda như một giá trị không kiểu có thể gán vào mọi nơi.

Ví dụ sau **không hợp lệ**:

~~~java
// Không biên dịch được vì lambda thiếu kiểu đích:
// var paid = order -> order.paid();
~~~

Trong khi khai báo Predicate<Order> paid = ... cung cấp kiểu đích rõ ràng và hợp lệ. Lambda có thể viết dạng biểu thức hoặc dạng khối có return tương ứng:

~~~java
Predicate<Order> paid = order -> {
    boolean result = order.paid();
    return result;
};
~~~

Lambda cũng có thể dùng biến cục bộ ở phạm vi bao quanh nếu biến đó **final hoặc effectively final** (đã gán và không bị gán lại):

~~~java
long minimum = 100_000;
Predicate<Order> expensive = order -> order.amount() >= minimum;
~~~

Nếu sau đó gán lại minimum trong cùng phạm vi thì chương trình không biên dịch được, vì biến được capture không còn effectively final. Điều này **không đồng nghĩa** lambda luôn thuần: lambda vẫn có thể sửa trường của object, gọi I/O hoặc truy cập trạng thái có thể thay đổi bên ngoài.

### Method reference: cùng ý tưởng, cú pháp khác

Khi lambda chỉ gọi một phương thức sẵn có, có thể viết method reference:

~~~java
Predicate<Order> paid = Order::paid;
Function<Order, String> customer = Order::customer;
~~~

Về hành vi quan sát được trong ví dụ, Order::paid tương đương order -> order.paid(). Method reference thường giúp nhấn mạnh “dùng phương thức này làm phép xử lý”, nhưng vẫn cần một kiểu đích phù hợp. Nó không tạo ra công việc thực thi riêng và cũng không mặc định gọi phương thức ngay lập tức.

### Lambda không đồng nhất với hàm thuần

Lambda viết dưới dạng order -> order.amount() là biểu thức không có tác dụng phụ nếu đối tượng đầu vào có hành vi ổn định như record minh họa. Còn lambda order -> { auditLog.add(order); return true; } thay đổi danh sách dùng chung, nên có tác dụng phụ. Cần đánh giá **hành vi thực tế**, không đánh giá độ ngắn của cú pháp.

## 5. Stream nhận hành vi làm tham số rồi kết nối các bước

Stream API định nghĩa các phép toán xử lý trên chuỗi phần tử. Đáng chú ý, nhiều phương thức Stream là **phép toán bậc cao** (*higher-order operation*): chúng nhận một hàm/hành vi khác làm đối số.

Ví dụ:

~~~java
List<String> paidCustomers = orders.stream()
        .filter(Order::paid)
        .map(Order::customer)
        .distinct()
        .sorted()
        .toList();
~~~

Đây là đoạn minh họa, giả định orders là List<Order> và đã import java.util.List. Từng lời gọi có ý nghĩa:

1. **orders.stream():** tạo pipeline Stream<Order> từ dữ liệu nguồn.
2. **filter(Order::paid):** nhận Predicate<Order>, chỉ cho đơn đã thanh toán đi tiếp.
3. **map(Order::customer):** nhận Function<Order, String>, tạo tên khách; từ đây kiểu phần tử chuyển thành String.
4. **distinct():** loại các tên trùng nhau theo quy tắc equals/hashCode của giá trị.
5. **sorted():** sắp xếp chuỗi theo thứ tự tự nhiên.
6. **toList():** thao tác kết thúc, tạo List<String> chứa kết quả và không cho phép thay đổi cấu trúc danh sách.

Cùng một Stream có thể được diễn đạt qua các kiểu tổng quát:

~~~text
Stream<Order>
  --filter(Predicate<? super Order>)--> Stream<Order>
  --map(Function<? super Order, ? extends String>)--> Stream<String>
  --distinct()--> Stream<String>
  --sorted()--> Stream<String>
  --toList()--> List<String>
~~~

Chỗ dấu ? super / ? extends trong chữ ký generic cho phép truyền các hàm có kiểu tương thích, không cần mọi kiểu cụ thể khớp tuyệt đối. Ở mức nhập môn, điều cần nhớ là **filter giữ nguyên kiểu phần tử**, trong khi **map có thể đổi kiểu phần tử**.

### Stream pipeline gồm hai nhóm thao tác

- **Trung gian (*intermediate*):** filter, map, flatMap, distinct, sorted, limit và nhiều phương thức khác thường tạo Stream mới mà chưa đánh giá ngay dữ liệu.
- **Kết thúc (*terminal*):** toList, count, reduce, collect, sum, forEach... khởi động quá trình đánh giá để lấy một kết quả hoặc thực hiện hành động.

Phần lớn thao tác trung gian là *lazy*. Khi viết:

~~~java
Stream<Order> selected = orders.stream().filter(Order::paid);
~~~

Chưa có kết quả List mới được tạo. Pipeline mới chỉ mô tả điều kiện lọc. Khi gọi selected.count() hoặc selected.toList(), Stream mới được tiêu thụ. Java có quyền tối ưu những bước trung gian không cần thiết theo hợp đồng API; vì thế không nên dựa vào tác dụng phụ trong lambda để đoán số lần gọi chính xác ở mọi pipeline.

**Một Stream chỉ nên tiêu thụ một lần.** Nếu cần hai kết quả khác nhau (ví dụ danh sách tên và tổng tiền), hãy tạo hai Stream mới từ cùng collection, hoặc thiết kế collector để tổng hợp cùng một lượt.

## 6. Ví dụ Java 17 hoàn chỉnh: từ dữ liệu tới kết quả

Tạo file **DataFunctionLambdaStream.java** với nội dung sau. Ví dụ cho thấy dữ liệu được khai báo bằng record và List, quy tắc được truyền qua Predicate/Function, Stream nhận các quy tắc đó và thao tác kết thúc tạo kết quả cụ thể.

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class DataFunctionLambdaStream {
    record Order(String id, String customer, long amount, boolean paid) {}

    public static void main(String[] args) {
        // 1. Dữ liệu nguồn.
        List<Order> orders = List.of(
                new Order("O1", "Linh", 120_000, true),
                new Order("O2", "Nam", 75_000, false),
                new Order("O3", "Mai", 80_000, true),
                new Order("O4", "Linh", 20_000, true)
        );

        // 2. Hai quy tắc xử lý có kiểu cụ thể.
        Predicate<Order> isPaid = Order::paid;
        Function<Order, String> toCustomer = Order::customer;

        // 3. Kết hợp dữ liệu + hành vi thông qua Stream.
        List<String> customers = orders.stream()
                .filter(isPaid)
                .map(toCustomer)
                .distinct()
                .sorted()
                .toList();

        // 4. Một phép tổng hợp dùng primitive long.
        long paidTotal = orders.stream()
                .filter(isPaid)
                .mapToLong(Order::amount)
                .sum();

        // 5. Nhóm dữ liệu bằng một collector.
        Map<String, Long> totalsByCustomer = orders.stream()
                .filter(isPaid)
                .collect(Collectors.groupingBy(
                        Order::customer,
                        TreeMap::new,
                        Collectors.summingLong(Order::amount)
                ));

        // 6. Ghép hai Function độc lập.
        Function<String, String> trim = String::trim;
        Function<String, String> upper =
                text -> text.toUpperCase(Locale.ROOT);
        Function<String, String> normalize = trim.andThen(upper);

        System.out.println("Khách đã thanh toán: " + customers);
        System.out.println("Tổng tiền đã thanh toán: " + paidTotal);
        System.out.println("Theo khách: " + totalsByCustomer);
        System.out.println("Chuẩn hóa: " + normalize.apply("  java  "));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac DataFunctionLambdaStream.java
java DataFunctionLambdaStream
~~~

Kết quả chính xác:

~~~text
Khách đã thanh toán: [Linh, Mai]
Tổng tiền đã thanh toán: 220000
Theo khách: {Linh=140000, Mai=80000}
Chuẩn hóa: JAVA
~~~

**Kiểm tra từng phép tính:**

- Chỉ O1, O3, O4 có paid = true. O2 bị loại bởi filter.
- customer của ba đơn còn lại lần lượt là Linh, Mai, Linh. distinct loại Linh trùng và sorted đưa ra [Linh, Mai].
- Tổng tiền: 120.000 + 80.000 + 20.000 = 220.000.
- Nhóm theo khách: Linh có 120.000 + 20.000 = 140.000; Mai có 80.000. TreeMap tạo thứ tự khóa xác định để output dễ kiểm chứng.
- trim.andThen(upper) áp dụng String::trim trước, sau đó chuyển thành chữ hoa bằng Locale.ROOT, nên đầu vào có khoảng trắng "  java  " trở thành JAVA.

**Vì sao có ba lời gọi orders.stream()?** Mỗi thao tác kết thúc tiêu thụ một pipeline. Chúng ta đang cần ba kết quả độc lập: danh sách tên khách, tổng tiền và tổng theo khách. List orders là dữ liệu nguồn có thể dùng lại, còn Stream đã tiêu thụ thì không dùng lại được.

**Tại sao mapToLong thay vì map?** Sau mapToLong(Order::amount), pipeline mang primitive long dưới dạng LongStream và có phương thức sum() phù hợp, giúp tránh đóng gói Long không cần thiết.

**Vai trò của Collectors.groupingBy:** nó nhận hàm chọn khóa nhóm (Order::customer), nơi lưu map (TreeMap::new) và collector dùng để tính giá trị mỗi nhóm (summingLong). Đây là minh họa khác cho việc truyền hành vi vào API. TreeMap được tạo và thay đổi nội bộ khi thu thập kết quả; tư duy hàm không cấm mọi trạng thái nội bộ mà tập trung tránh tác dụng phụ khó kiểm soát trong logic người dùng.

## 7. Đặt cùng bài toán cạnh cách viết vòng lặp

Giả sử chỉ cần danh sách khách đã thanh toán, không trùng và được sắp xếp. Một cách viết với vòng lặp (đoạn minh họa, giả định kiểu Order đã khai báo) có thể là:

~~~java
Set<String> selected = new TreeSet<>();
for (Order order : orders) {
    if (order.paid()) {
        selected.add(order.customer());
    }
}
List<String> customers = List.copyOf(selected);
~~~

Đoạn trên cần import java.util.Set, java.util.TreeSet, java.util.List. Cách làm hoàn toàn hợp lệ. Vòng lặp giải thích chi tiết cách duyệt, kiểm tra và thêm vào Set. Còn cách Stream:

~~~java
List<String> customers = orders.stream()
        .filter(Order::paid)
        .map(Order::customer)
        .distinct()
        .sorted()
        .toList();
~~~

Diễn đạt trực tiếp các phép biến đổi dữ liệu. Các thao tác **filter** và **map** nhận hành vi dưới dạng hàm, do đó có thể tái sử dụng cơ chế duyệt mà không chép lại cấu trúc lặp.

Không nên hiểu Stream tự động nhanh hơn: với đầu vào nhỏ, chi phí pipeline có thể lớn hơn vòng lặp; với logic cần điều khiển phức tạp, vòng lặp có thể dễ đọc hơn. Chọn cách thể hiện theo độ rõ ràng, yêu cầu hiệu năng và nhu cầu xử lý.

## 8. Ghép hàm và tách quy tắc kinh doanh khỏi dữ liệu

Một lợi ích của việc có hành vi như giá trị là **không cần gắn cứng điều kiện vào thuật toán duyệt**.

Ví dụ sau giả định đã có kiểu `Order`; khai báo phương thức `static` `chooseOrders` ở cấp lớp (class hoặc record), còn những lời gọi có thể đặt bên trong phương thức khác:

~~~java
static List<Order> chooseOrders(
        List<Order> orders, Predicate<Order> condition) {
    return orders.stream().filter(condition).toList();
}
~~~

Phương thức chooseOrders là một phép toán bậc cao vì nhận Predicate<Order> làm tham số. Bên gọi có thể cung cấp những quy tắc khác nhau:

~~~java
Predicate<Order> paid = Order::paid;
Predicate<Order> large = order -> order.amount() >= 100_000;
Predicate<Order> paidAndLarge = paid.and(large);

List<Order> selected = chooseOrders(orders, paidAndLarge);
~~~

Ở đây Predicate.and ghép hai điều kiện thành điều kiện mới. Kết quả selected chứa những đơn vừa đã thanh toán vừa có giá trị từ 100.000 trở lên. Cấu trúc duyệt bên trong chooseOrders không cần sửa khi chính sách chọn thay đổi.

Tương tự, Function.andThen ghép hai phép biến đổi; Function.compose đảo thứ tự ghép. Trong những hàm có tác dụng phụ, thứ tự gọi có thể quan trọng; vì vậy nên ưu tiên các phép biến đổi nhỏ, dễ quan sát và có hợp đồng rõ.

Ví dụ khác minh họa sự khác biệt về kiểu dữ liệu:

~~~java
Function<Order, Long> amount = Order::amount;
Function<Long, String> toLabel = value -> value + " VND";
Function<Order, String> label = amount.andThen(toLabel);
~~~

Trong chuỗi này, kết quả Long của Function đầu trở thành đầu vào cho Function tiếp theo; kiểu của toàn bộ hàm ghép là Function<Order, String>. Java kiểm tra các kiểu này tại thời điểm biên dịch.

## 9. Những ranh giới cần hiểu đúng

### 9.1. Dữ liệu không luôn bất biến

Tính an toàn của pipeline phụ thuộc vào dữ liệu nguồn, hành vi được truyền vào và cách sử dụng. Với List mutable, thay đổi cấu trúc collection trong khi duyệt Stream có thể gây hành vi không xác định theo hợp đồng nguồn hoặc lỗi như ConcurrentModificationException. Tránh sửa nguồn ngay trong filter/map/forEach. Khi cần tạo kết quả, ưu tiên tạo collection kết quả độc lập.

Phương thức `Stream.toList()` (Java 16+) trả về danh sách không cho phép thêm, xóa hay thay phần tử; `List` không có phương thức `toList()`. Tuy nhiên, phần tử trong danh sách vẫn có thể là object mutable. Điều này không bảo đảm dữ liệu ở mọi tầng đều bất biến.

### 9.2. Lambda không tự tạo luồng riêng

Viết lambda không đồng nghĩa chạy đa luồng. Một Stream tuần tự thường xử lý phần tử trên luồng gọi hiện tại. parallelStream() hoặc parallel() có thể dùng nhiều worker thread trong môi trường phù hợp, nhưng cần xem xét phép gộp có tính kết hợp, tránh trạng thái chia sẻ và đo hiệu năng thực tế. Không phải pipeline nào cũng thích hợp để chạy song song.

### 9.3. Thứ tự phần tử và tính xác định

Nguồn List có thứ tự gặp phần tử (*encounter order*). filter và map thường bảo toàn thứ tự đó khi pipeline có thứ tự; distinct, sorted và một số thao tác khác có các quy tắc riêng. Không nên giả định dữ liệu từ HashSet hay mọi pipeline song song luôn trả ra thứ tự mong muốn. Nếu output cần cố định, hãy chọn nguồn/bộ sắp xếp phù hợp như sorted() hoặc TreeMap theo yêu cầu.

### 9.4. Thao tác có tác dụng phụ phải được lựa chọn có chủ đích

Một lambda như phần sau có thể làm code khó dự đoán, đặc biệt với Stream song song:

~~~java
// Không khuyến nghị: cập nhật danh sách bên ngoài từ forEach.
List<String> result = new ArrayList<>();
orders.stream().forEach(order -> result.add(order.customer()));
~~~

Đây là đoạn minh họa, giả định đã import java.util.List và java.util.ArrayList. Thay vào đó:

~~~java
List<String> result = orders.stream()
        .map(Order::customer)
        .toList();
~~~

forEach phù hợp với những mục đích như xuất kết quả ở ranh giới ứng dụng, nhưng không nên dùng nó để thu thập dữ liệu vào một biến chia sẻ khi map/collect/toList diễn đạt mục tiêu rõ hơn. Các tác vụ I/O vẫn có chỗ trong ứng dụng; chỉ nên tách chúng khỏi phần tính toán dễ kiểm thử khi có thể.

### 9.5. Null và ngoại lệ không biến mất

Hàm s -> s.trim() sẽ ném NullPointerException nếu s là null. Lambda và Stream không làm phép toán này an toàn hơn. Cần thiết kế hợp đồng đầu vào hoặc lọc null trước khi truy cập phương thức, ví dụ filter(Objects::nonNull) nếu dữ liệu được phép chứa null. List.of(...) vốn không chấp nhận phần tử null.

Một exception phát sinh trong map/filter có thể làm thao tác kết thúc thất bại. Một số functional interface chuẩn không khai báo checked exception tùy ý; xử lý ngoại lệ cần thiết kế rõ ở lambda hoặc chuyển logic sang phương thức thích hợp.

### 9.6. Hàm thuần và Stream là hai chuyện khác nhau

Một hàm không có tác dụng phụ có thể được gọi từ vòng lặp thường; vẫn là tư duy hàm. Mặt khác, một pipeline Stream có lambda sửa biến toàn cục vẫn có thể khó kiểm thử và nguy hiểm trong môi trường đồng thời. Không được kết luận “dùng Stream nên tự động là lập trình hàm thuần”.

## 10. Từ mô hình khái niệm sang quyết định thiết kế

Khi đứng trước một tác vụ xử lý dữ liệu Java, có thể tự hỏi theo thứ tự:

1. **Dữ liệu là gì?** Xác định kiểu phần tử, nguồn, các trường bắt buộc và khả năng có null.
2. **Quy tắc là gì?** Mỗi bước là điều kiện, biến đổi, tổng hợp hay tác dụng phụ? Có thể viết thành hàm nhỏ và kiểm thử độc lập không?
3. **Truyền quy tắc bằng cách nào?** Nếu API cần Predicate, Function hay Consumer, hãy chọn lambda hoặc method reference dễ đọc nhất. Lambda phức tạp nên được tách thành phương thức có tên.
4. **Tổ chức luồng dữ liệu thế nào?** Dùng Stream khi filter/map/group/reduce bộc lộ tốt ý định; dùng vòng lặp khi dễ hiểu hơn.
5. **Kết quả và chi phí?** Xác định thao tác kết thúc, thứ tự, kiểu output, xử lý lỗi và nhu cầu hiệu năng. Không mặc định gọi parallel().

Nhìn một dòng như sau:

~~~java
orders.stream().filter(Order::paid).map(Order::customer).toList();
~~~

Ta có thể giải thích không nhập nhằng: **orders** giữ dữ liệu; **Order::paid** và **Order::customer** cung cấp hai hành vi phù hợp với Predicate và Function; **filter** và **map** là các thao tác Stream nhận hành vi đó; **toList** thực thi pipeline để tạo dữ liệu kết quả.

## 11. Câu hỏi tự kiểm tra

1. **Khác biệt giữa List<Order> và Stream<Order> là gì?** List chứa phần tử; Stream diễn đạt quá trình xử lý các phần tử từ nguồn, thường đánh giá khi có thao tác kết thúc.
2. **Nếu đã có method isPaid(Order), có cần viết lambda hay không?** Không nhất thiết; có thể truyền method reference phù hợp với kiểu đích của functional interface.
3. **Vì sao filter thường không đổi kiểu phần tử còn map có thể đổi?** filter quyết định giữ/bỏ phần tử T; map dùng Function<T, R> để tạo giá trị R.
4. **Vì sao không thể dùng var trực tiếp với lambda đứng một mình?** Lambda cần kiểu đích của functional interface để suy luận kiểu và chữ ký phương thức.
5. **Tại sao không dùng lại Stream sau toList()?** Thao tác kết thúc tiêu thụ pipeline; muốn xử lý lại, hãy tạo Stream mới từ nguồn.
6. **Một lambda không sửa biến cục bộ có tự động thuần không?** Không; nó có thể đọc trạng thái thay đổi hoặc gây tác dụng phụ qua object, log, mạng, file.
7. **Khi nào nên chọn vòng lặp?** Khi phép xử lý mang tính điều khiển, dễ đọc hơn dạng pipeline, hoặc khi phép đo hiệu năng chỉ ra lợi ích rõ rệt.

**Ghi nhớ:** Bốn khái niệm liên kết thành một cấu trúc thực hành: **dữ liệu cung cấp giá trị → hàm định nghĩa phép xử lý → lambda/method reference truyền phép xử lý → Stream nối các phép xử lý và tạo kết quả khi được tiêu thụ**. Hiểu vai trò và ranh giới của từng thành phần giúp viết Java dễ đọc, dễ kiểm thử và ít phụ thuộc trạng thái ẩn hơn.
