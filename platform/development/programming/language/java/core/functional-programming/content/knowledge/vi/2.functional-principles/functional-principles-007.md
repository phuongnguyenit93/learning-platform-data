# Kết hợp các phép biến đổi nhỏ thành quy trình lớn trong Java

## 1. Mục tiêu bài học

Khi một bài toán cần nhiều bước như **lọc dữ liệu → chuẩn hóa → tính toán → sắp xếp → trình bày**, cách tổ chức code dễ hiểu là tách mỗi bước thành một phép biến đổi nhỏ, sau đó **ghép chúng theo một thứ tự có chủ đích** thành quy trình lớn (pipeline).

Sau bài này, bạn có thể:

- Nhìn một quy trình nghiệp vụ và xác định đầu vào, đầu ra, trách nhiệm của từng bước.
- Sử dụng **Function**, **andThen**, **compose**, method reference, **Predicate** và Java **Stream** để ghép phép biến đổi.
- Hiểu vì sao thứ tự biến đổi quan trọng: **filter**, **map**, **sorted** và tác động đến cả kết quả lẫn chi phí xử lý.
- Nhận diện bước có tác dụng phụ, dữ liệu có thể thay đổi, ngoại lệ và các vấn đề khi tái sử dụng hoặc chạy song song pipeline.
- Kiểm thử từng bước độc lập và kiểm thử toàn bộ pipeline với dữ liệu ví dụ có kết quả xác định.

## 2. Ý tưởng nền tảng: đầu ra của bước trước là đầu vào của bước sau

Giả sử hệ thống cần xử lý đơn hàng:

1. Nhận danh sách đơn hàng đầu vào.
2. Chỉ chọn đơn hợp lệ theo quy tắc nghiệp vụ.
3. Chuẩn hóa tên khách và tính tổng tiền cho mỗi đơn.
4. Sắp xếp theo tổng tiền giảm dần.
5. Chuyển kết quả sang chuỗi dùng để hiển thị.

Mỗi công đoạn nên có **hợp đồng đầu vào/đầu ra** rõ ràng:

~~~text
List<Order>
    │
    ├─ filter: Order -> boolean
    ▼
List<Order> hợp lệ
    │
    ├─ map: Order -> OrderView
    ▼
List<OrderView> đã tính tổng tiền
    │
    ├─ sorted: so sánh OrderView.totalVnd
    ▼
List<OrderView> đã sắp xếp
    │
    ├─ map: OrderView -> String
    ▼
List<String> kết quả
~~~

Điều quan trọng là mỗi phép biến đổi chỉ cần biết **dữ liệu nó nhận và dữ liệu nó trả**, không phải toàn bộ màn hình, database hay API của ứng dụng. Các bước tính toán ít phụ thuộc vào hiệu ứng bên ngoài sẽ dễ kiểm thử, tái sử dụng và đổi thứ tự khi có lý do hợp lệ.

Không phải mọi bước đều có kiểu trả về giống nhau. Một bước **Order → OrderView** không thể ghép trực tiếp với bước chỉ nhận **LocalDate**, trừ khi có phép chuyển kiểu thích hợp. Hệ thống kiểu của Java sẽ phát hiện nhiều lỗi nối sai kiểu ngay lúc biên dịch.

### 2.1. Biến đổi giá trị và thao tác có hiệu ứng

Phân biệt hai vai trò:

- **Transformation:** nhận giá trị, trả giá trị mới; ví dụ chuẩn hóa tên, nhân số lượng với đơn giá, tạo DTO.
- **Effect:** đọc/ghi dữ liệu bên ngoài; ví dụ truy vấn database, lấy thời gian hiện tại, in console, gửi HTTP request, lưu kết quả.

Một thiết kế thực dụng là đưa I/O vào ranh giới, thực hiện các phép tính bằng giá trị rõ ràng ở phần giữa rồi chuyển kết quả ra ngoài. Không cần ép mọi thao tác của ứng dụng thành hàm thuần; cần biết bước nào gây hiệu ứng để kiểm soát lỗi và thử nghiệm.

## 3. Ghép hàm bằng Function<T, R>

Giao diện **java.util.function.Function<T, R>** biểu diễn phép biến đổi từ kiểu **T** sang kiểu **R**, với phương thức chính **R apply(T value)**.

Với hai hàm **f: A → B** và **g: B → C**, có thể tạo một hàm mới **A → C**:

- **f.andThen(g)**: chạy **f** trước, lấy kết quả truyền vào **g**.
- **g.compose(f)**: cũng chạy **f** trước rồi **g**; **compose** nhìn theo hướng “hàm nào thực thi trước hàm hiện tại”.

Hai biểu thức **f.andThen(g)** và **g.compose(f)** có cùng thứ tự chạy **f**, sau đó **g**, khi hai phép biến đổi tương thích kiểu.

### 3.1. Ví dụ thứ tự thực thi

~~~java
import java.util.function.Function;

Function<Integer, Integer> plusThree = x -> x + 3;
Function<Integer, Integer> doubleIt = x -> x * 2;

int first = plusThree.andThen(doubleIt).apply(4);
int second = plusThree.compose(doubleIt).apply(4);
~~~

Giá trị **first = 14** vì **(4 + 3) × 2 = 14**. Giá trị **second = 11** vì **4 × 2 + 3 = 11**.

**Thứ tự quan trọng:** phép cộng và nhân ở đây không thể tùy tiện đổi chỗ. Trong bài toán thật, “làm tròn trước khi áp thuế” và “áp thuế trước khi làm tròn” cũng có thể tạo kết quả khác nhau.

Nếu hàm **f** trả **B** nhưng **g** chỉ nhận kiểu không tương thích với **B**, lệnh **andThen** sẽ không biên dịch. Đây là ưu điểm của việc mô tả rõ loại dữ liệu giữa các bước.

### 3.2. Hàm được đặt tên rõ mục đích

~~~java
Function<String, String> trim = String::strip;
Function<String, String> upper =
        value -> value.toUpperCase(java.util.Locale.ROOT);

Function<String, String> normalize = trim.andThen(upper);
String result = normalize.apply("  Java  "); // "JAVA"
~~~

Tách thành **trim** và **upper** cho phép đổi quy tắc chuẩn hóa, kiểm thử riêng và tái sử dụng ở những quy trình khác. **Locale.ROOT** giúp kết quả không phụ thuộc locale mặc định của máy. Với các quy tắc ngôn ngữ tự nhiên cụ thể, cần chọn locale theo yêu cầu sản phẩm.

**Lưu ý:** phương thức **compose** và **andThen** chỉ cung cấp cách ghép lời gọi. Chúng không tự biến hàm có side effect thành hàm thuần, không tự xử lý null và không tự bắt ngoại lệ.

## 4. Kết hợp điều kiện bằng Predicate<T>

**Predicate<T>** biểu diễn phép kiểm tra trả về **boolean**, với phương thức **test(T)**. Các phương thức **and**, **or** và **negate** giúp xây dựng quy tắc lớn từ những điều kiện nhỏ.

~~~java
import java.util.function.Predicate;

Predicate<String> notNull = value -> value != null;
Predicate<String> notBlank = value -> !value.isBlank();

Predicate<String> validName = notNull.and(notBlank);
~~~

**and** và **or** thực hiện **short-circuit**: với **and**, nếu điều kiện đầu là false thì điều kiện sau không chạy. Vì thế **validName.test(null)** trả false mà không truy cập **null.isBlank()**.

Khi ghép điều kiện, thứ tự vẫn có ý nghĩa nếu một predicate có thể ném ngoại lệ, tốn chi phí lớn hoặc gây hiệu ứng. Trong thực hành, hãy đặt kiểm tra an toàn như null trước các thao tác dereference, đặt điều kiện rẻ trước điều kiện tốn kém khi phù hợp, và tránh side effect trong predicate.

Ví dụ đánh giá đơn hàng:

~~~java
Predicate<Order> hasCustomer =
        order -> order != null
                && order.customer() != null
                && !order.customer().isBlank();

Predicate<Order> valid = hasCustomer
        .and(order -> order.quantity() > 0)
        .and(order -> order.unitPriceVnd() >= 0);
~~~

Đoạn trên giả định một kiểu **Order** có các accessor **customer()**, **quantity()**, **unitPriceVnd()**; kiểu này sẽ được khai báo đầy đủ ở ví dụ chạy độc lập bên dưới.

Quy tắc “lọc đơn không hợp lệ” chỉ phù hợp nếu hệ thống **chủ đích bỏ qua** các đơn đó. Với nghiệp vụ yêu cầu phản hồi lỗi đầy đủ, nên phân loại đầu vào thành nhóm hợp lệ và nhóm lỗi để hiển thị/ghi nhận, thay vì âm thầm loại bỏ.

## 5. Java Stream: ghép nhiều bước trên tập dữ liệu

**Stream** cho phép mô tả chuỗi thao tác trên nhiều phần tử mà không cần tự viết vòng lặp trung gian cho từng bước. Các thao tác thường gặp:

| Phép toán | Ý nghĩa | Kiểu kết quả điển hình |
| --- | --- | --- |
| **filter(predicate)** | Giữ các phần tử thỏa điều kiện | Stream<T> |
| **map(function)** | Biến đổi mỗi phần tử | Stream<R> |
| **flatMap(function)** | Biến một phần tử thành một stream rồi trải phẳng | Stream<R> |
| **distinct()** | Loại trùng theo **equals/hashCode** | Stream<T> |
| **sorted(comparator)** | Sắp xếp các phần tử | Stream<T> |
| **limit(n)** | Giới hạn tối đa **n** phần tử | Stream<T> |
| **toList()** | Thu thập thành danh sách | List<T> |
| **reduce(...)** | Kết hợp phần tử thành một giá trị | Giá trị hoặc Optional |

**filter**, **map**, **flatMap**, **distinct**, **sorted**, **limit** là các phép toán trung gian (**intermediate operations**) và thường **lazy**: việc khai báo chuỗi thao tác chưa đồng nghĩa đã duyệt dữ liệu. **toList**, **forEach**, **count**, **reduce** là ví dụ về thao tác kết thúc (**terminal operations**) kích hoạt xử lý.

~~~java
List<String> names = List.of(" An ", " ", "Binh");

List<String> cleaned = names.stream()
        .map(String::strip)
        .filter(value -> !value.isEmpty())
        .map(value -> value.toUpperCase(java.util.Locale.ROOT))
        .toList();
~~~

Kết quả **cleaned** là **[AN, BINH]**. **Stream.toList()** (Java 16+) trả danh sách không hỗ trợ các thao tác thay đổi như **add**; nó không tự làm mọi phần tử trở nên bất biến sâu.

**Stream không phải dữ liệu có thể chạy lại:** một đối tượng **Stream** đã kết thúc không được dùng thêm một terminal operation khác. Khi cần thực thi lại, hãy tạo stream mới từ nguồn, ví dụ **names.stream()**. Các nguồn dữ liệu mutable có thể dẫn đến kết quả khác nhau nếu bị sửa giữa các lần chạy.

## 6. Ví dụ hoàn chỉnh Java 17: pipeline xử lý đơn hàng

Ví dụ dưới đây ghép các phép biến đổi nhỏ thành chương trình chạy được. Mọi phép tính sử dụng dữ liệu đầu vào rõ ràng; chỉ **main** in kết quả ra console.

Lưu thành file **OrderPipelineDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.Function;
import java.util.function.Predicate;

public class OrderPipelineDemo {
    record Order(String customer, int quantity, long unitPriceVnd) {
    }

    record OrderView(String customer, long totalVnd) {
    }

    static String normalizeName(String name) {
        return name.strip().toUpperCase(Locale.ROOT);
    }

    static long total(Order order) {
        return Math.multiplyExact((long) order.quantity(),
                                  order.unitPriceVnd());
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order(" an ", 2, 15_000),
                new Order("Binh", 0, 20_000),
                new Order(" Chi ", 3, 12_000),
                new Order("Dung", 1, 10_000)
        );

        Predicate<Order> hasCustomer =
                order -> order != null
                        && order.customer() != null
                        && !order.customer().isBlank();

        Predicate<Order> valid = hasCustomer
                .and(order -> order.quantity() > 0)
                .and(order -> order.unitPriceVnd() >= 0);

        Function<Order, OrderView> summarize =
                order -> new OrderView(
                        normalizeName(order.customer()),
                        total(order)
                );

        Function<OrderView, String> render =
                view -> view.customer() + ": "
                        + view.totalVnd() + " VND";

        Function<Order, String> describe = summarize.andThen(render);

        List<String> lines = orders.stream()
                .filter(valid)
                .map(summarize)
                .sorted(Comparator.comparingLong(
                        OrderView::totalVnd).reversed())
                .map(render)
                .toList();

        System.out.println("andThen: "
                + describe.apply(orders.get(0)));
        System.out.println("compose: "
                + render.compose(summarize).apply(orders.get(0)));
        System.out.println("pipeline: " + lines);
        System.out.println("source size: " + orders.size());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac OrderPipelineDemo.java
java OrderPipelineDemo
~~~

**Đầu ra chính xác:**

~~~text
andThen: AN: 30000 VND
compose: AN: 30000 VND
pipeline: [CHI: 36000 VND, AN: 30000 VND, DUNG: 10000 VND]
source size: 4
~~~

### 6.1. Giải thích từng bước

**Bước 1 — lọc:** **valid** giữ ba đơn có khách hàng hợp lệ, số lượng dương và đơn giá không âm. Đơn của **Binh** bị loại vì **quantity = 0**. Với quy tắc này, một đơn có đơn giá bằng 0 vẫn được xem là hợp lệ; thay quy tắc nếu nghiệp vụ không cho phép.

**Bước 2 — biến đổi:** **summarize** tạo **OrderView** mới, chuẩn hóa tên và tính tổng tiền. **Math.multiplyExact** phát sinh **ArithmeticException** nếu phép nhân **long** bị tràn; do đó chương trình không âm thầm trả kết quả tiền sai. **normalizeName** giả định tên không null vì đã qua điều kiện lọc.

**Bước 3 — sắp xếp:** **Comparator.comparingLong(OrderView::totalVnd).reversed()** sắp **OrderView** theo tổng tiền giảm dần. Việc sắp xếp dựa trên **giá trị số** diễn ra **trước** khi đổi sang chuỗi, nên không mắc lỗi so sánh theo thứ tự từ điển của giá trị định dạng.

**Bước 4 — hiển thị:** **render** chuyển mỗi **OrderView** thành một chuỗi. Hai cách **summarize.andThen(render)** và **render.compose(summarize)** có cùng thứ tự thực thi và cho ra cùng chuỗi với cùng đơn đầu vào.

**Bước 5 — thu thập:** **toList()** kết thúc pipeline và tạo danh sách kết quả. Danh sách nguồn **orders** vẫn có bốn phần tử vì pipeline không sửa hoặc loại bỏ phần tử trong nguồn.

### 6.2. Vì sao không ghép mọi thao tác vào một hàm khổng lồ?

Có thể viết tất cả trong một phương thức dài, nhưng khi thay đổi cách tính tiền, muốn trả JSON thay vì chuỗi, hoặc cần kiểm thử riêng quy tắc chọn đơn, người đọc phải sửa nhiều logic cùng lúc.

Cách tách nhỏ tạo ra những đơn vị có tên, trách nhiệm, kiểu dữ liệu và test riêng. Phần điều phối chỉ còn nói rõ **các bước được nối như thế nào**. Tuy nhiên, không nên chia đến mức mỗi phép toán tầm thường có thêm một lớp hoặc interface nếu nó khiến code khó theo dõi hơn.

## 7. Thứ tự pipeline ảnh hưởng kết quả và hiệu năng

Hai chuỗi thao tác sau **không luôn tương đương**:

~~~java
// Chỉ giữ dữ liệu rồi mới làm công việc chuyển đổi.
stream.filter(valid).map(transform)

// Làm công việc chuyển đổi cho mọi phần tử rồi mới kiểm tra.
stream.map(transform).filter(validTransformed)
~~~

Nếu phép biến đổi tốn kém, lọc sớm thường tránh được tính toán thừa. Nhưng nếu điều kiện chỉ có thể đánh giá **sau khi transform**, không thể hoán đổi như vậy. Cũng phải cân nhắc side effect, ngoại lệ và quy tắc dữ liệu để bảo đảm không làm thay đổi hành vi.

### 7.1. Sắp xếp trước hay sau khi giới hạn?

~~~java
// Lấy ba phần tử có giá trị lớn nhất.
numbers.stream()
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .toList();

// Chỉ lấy ba phần tử đầu nguồn rồi sắp xếp ba phần tử ấy.
numbers.stream()
        .limit(3)
        .sorted(Comparator.reverseOrder())
        .toList();
~~~

Hai cách chỉ trùng kết quả trong những trường hợp ngẫu nhiên. Với đầu vào **[1, 9, 2, 8, 3]**, cách thứ nhất trả **[9, 8, 3]**, cách thứ hai trả **[9, 2, 1]**. **limit** tác động đến tập phần tử nào được phép đi tiếp, vì vậy vị trí của nó là một phần hợp đồng nghiệp vụ.

### 7.2. flatMap khi một phần tử tạo ra nhiều phần tử

Giả sử mỗi đơn có nhiều tag:

~~~java
List<List<String>> groups = List.of(
        List.of("java", "stream"),
        List.of("function", "java")
);

List<String> tags = groups.stream()
        .flatMap(List::stream)
        .distinct()
        .toList();
~~~

Kết quả **tags** là **[java, stream, function]**, theo thứ tự gặp đầu tiên của nguồn có thứ tự. **map(List::stream)** tạo ra **Stream<Stream<String>>**, còn **flatMap(List::stream)** trải thành **Stream<String>** để các bước sau xử lý từng tag. **distinct** phân biệt theo hợp đồng **equals/hashCode** của phần tử.

## 8. Kết hợp các kết quả tính toán

Pipeline không chỉ biến **List<A>** thành **List<B>**, mà còn có thể gom thành một giá trị:

~~~java
int totalLength = List.of("An", "Binh", "Chi")
        .stream()
        .mapToInt(String::length)
        .sum();
~~~

**totalLength = 9** vì độ dài chuỗi lần lượt là 2, 4, 3. Dùng **mapToInt** giúp kết quả thuộc primitive stream và có **sum()** thuận tiện.

Một phép **reduce** phù hợp khi bạn có phần tử trung hòa (identity) và phép kết hợp đáp ứng các quy tắc cần thiết:

~~~java
int sum = List.of(2, 3, 4).stream()
        .reduce(0, Integer::sum); // 9
~~~

Với quy trình có thể chạy song song, phép kết hợp phải **associative** và phải tương thích với identity để kết quả không phụ thuộc cách nhóm phần tử. Phép trừ không associative: **(a - b) - c** có thể khác **a - (b - c)**, vì vậy không thể dùng tùy tiện như phép gom song song có thứ tự nhóm bất kỳ.

**Integer::sum** là phép cộng **int** của Java, có thể tràn số nguyên theo quy tắc **int**; đối với dữ liệu tài chính hãy dùng kiểu số và chính sách làm tròn/tràn số thích hợp, ví dụ **long** kèm **Math.addExact**, hoặc **BigDecimal** theo nghiệp vụ.

## 9. Giữ hiệu ứng bên ngoài quy trình tính toán

Một lambda nằm trong **map** vẫn có thể làm việc không mong muốn:

~~~java
List<String> names = List.of("An", "Binh");
List<String> result = names.stream()
        .map(name -> {
            System.out.println("Processing: " + name);
            return name.toUpperCase(Locale.ROOT);
        })
        .toList();
~~~

Đoạn này biên dịch và chạy, nhưng phần **map** có hiệu ứng console. Tái cấu trúc, thay terminal operation hoặc chạy song song có thể khiến thứ tự hay số lần thực thi callback không như người viết kỳ vọng. **Stream.peek** hữu ích khi quan sát/debug, nhưng không phải nơi bảo đảm thực thi thao tác nghiệp vụ quan trọng; một số phép tối ưu có thể bỏ qua những công đoạn không cần thiết để tính terminal result.

Thay vào đó, tách phần biến đổi dữ liệu:

~~~java
List<String> upper = names.stream()
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();

upper.forEach(System.out::println);
~~~

**forEach** lúc này là phần thao tác có hiệu ứng, tách khỏi việc tạo dữ liệu. Ngay cả **forEach** cũng không phải nơi thuần; đây là lựa chọn có chủ đích ở ranh giới hiển thị.

Với database/API, nên đọc dữ liệu ở lớp adapter/service, truyền snapshot hoặc DTO tới lớp tính toán, rồi lưu kết quả ở bước ngoài. Khi thực hiện nhiều hiệu ứng nối tiếp (ví dụ ghi database rồi gửi email), cần thiết kế giao dịch, retry, idempotency và xử lý thất bại riêng; **Function.andThen** không tự cung cấp cơ chế ấy.

## 10. Xử lý lỗi, null và dữ liệu không hợp lệ

Một pipeline có nhiều bước sẽ thất bại nếu một bước ném exception mà không có xử lý phù hợp. Ví dụ **Integer.parseInt("12x")** ném **NumberFormatException**; **map(Integer::parseInt)** không tự chuyển nó thành kết quả lỗi thân thiện.

Ba hướng xử lý tùy hợp đồng nghiệp vụ:

1. **Fail fast** với dữ liệu không hợp lệ khi mọi phần tử bắt buộc đúng; cho lỗi lan lên tầng có thể phản hồi rõ ràng.
2. **Lọc có giải thích** khi nghiệp vụ cho phép bỏ qua dữ liệu, nhưng cần lưu thống kê hoặc danh sách lý do bị loại tại ranh giới xử lý.
3. **Mô hình hóa lỗi thành dữ liệu**, ví dụ record mang **value/error** hoặc kiểu **Result<T, E>** tự định nghĩa; sau đó chia nhánh thành thành công và thất bại trước khi tiếp tục.

Ví dụ đơn giản với **Optional** chỉ thích hợp khi trạng thái “không có giá trị” đủ để biểu diễn quyết định:

~~~java
import java.util.Optional;

static Optional<Integer> parsePositive(String raw) {
    if (raw == null || !raw.matches("[0-9]+")) {
        return Optional.empty();
    }
    try {
        int parsed = Integer.parseInt(raw);
        return parsed > 0 ? Optional.of(parsed) : Optional.empty();
    } catch (NumberFormatException ex) {
        return Optional.empty(); // Ví dụ cố ý gộp lỗi thành "không có".
    }
}
~~~

Đây là **đoạn phương thức minh họa** đặt trong một lớp Java; không phải file chạy độc lập. Chú ý cách này không phân biệt chuỗi lỗi định dạng, tràn **int** hay số không dương. Nếu cần báo cáo từng lỗi, hãy dùng kết quả có mã lỗi/thông điệp rõ ràng thay vì **Optional.empty()**.

**Function** thường nhận/trả **null** nếu logic cho phép, nhưng phần lớn bước tiếp theo sẽ gặp **NullPointerException** nếu không xử lý. Định nghĩa hợp đồng null rõ ràng: cấm null và kiểm tra sớm, hoặc dùng **Optional**/kiểu kết quả để mô tả khả năng thiếu dữ liệu.

## 11. Kiểm thử mỗi bước và cả chuỗi

**Kiểm thử từng phép biến đổi:** xác nhận đầu ra cho đầu vào đại diện và ranh giới.

- **normalizeName(" an ")** phải ra **"AN"**.
- **total(new Order("An", 2, 15000))** phải ra **30000**.
- **valid.test(new Order("Binh", 0, 20000))** phải trả false.
- **render.apply(new OrderView("CHI", 36000))** phải ra **"CHI: 36000 VND"**.

**Kiểm thử hợp đồng pipeline:** đưa vào một bộ đơn có tổng tiền bằng nhau, đơn không hợp lệ và tên cần chuẩn hóa; xác nhận kết quả được lọc, sắp xếp và hiển thị theo đúng đặc tả. Nếu thứ tự giữa các đơn có cùng tổng tiền quan trọng, phải định nghĩa rõ tiêu chí phụ (ví dụ mã đơn hàng), thay vì dựa vào thứ tự tình cờ.

Ví dụ đơn giản có thể tự xác nhận ngay trong **main** sau khi tạo **lines**:

~~~java
List<String> expected = List.of(
        "CHI: 36000 VND",
        "AN: 30000 VND",
        "DUNG: 10000 VND"
);
if (!lines.equals(expected)) {
    throw new AssertionError("Unexpected pipeline result: " + lines);
}
~~~

Đoạn kiểm tra này thuộc chương trình **OrderPipelineDemo** đã khai báo **lines**, không chạy độc lập. Nó chỉ kiểm thử một trường hợp; kiểm thử thực tế nên bổ sung dữ liệu rỗng, null theo hợp đồng, số lớn gây tràn, dữ liệu đã sắp xếp, các giá trị bằng nhau và thất bại của nguồn dữ liệu.

Một quy trình tính toán thuần, tách biệt I/O, giúp test không cần kết nối network hoặc database để xác minh công thức và quy tắc lọc.

## 12. Những lỗi thường gặp khi ghép pipeline

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nhầm **compose** với **andThen** | Chạy phép toán theo thứ tự sai | Viết sơ đồ kiểu A → B → C và kiểm tra bằng ví dụ số |
| **map** trước **filter** không cần thiết | Biến đổi dữ liệu sẽ bị loại, tăng chi phí hoặc gây lỗi | Xem có thể lọc an toàn từ dữ liệu gốc trước không |
| **sorted** sau khi định dạng số thành chuỗi | Sắp xếp từ điển thay vì số học | Sắp xếp theo thuộc tính số trước khi render |
| Sửa collection bên ngoài trong **map/forEach** | Dễ sai khi đổi thứ tự, lặp lại, chạy parallel | Trả giá trị mới hoặc dùng collector phù hợp |
| Giữ Stream để dùng terminal lần thứ hai | **IllegalStateException** do stream đã tiêu thụ | Tạo stream mới từ nguồn |
| Dùng **peek** để ghi dữ liệu bắt buộc | Hiệu ứng có thể không chạy như dự tính | Đưa thao tác ghi sang ranh giới có chủ đích |
| Bỏ qua dữ liệu lỗi bằng **filter** mà không báo | Mất bản ghi âm thầm | Chọn chính sách lỗi rõ ràng |
| Cho nguồn mutable đổi giữa lúc duyệt | Kết quả sai, không xác định hoặc lỗi truy cập | Snapshot, bất biến hoặc cơ chế đồng bộ đúng |
| Dùng **parallelStream** cho lambda có trạng thái chia sẻ | Race condition, kết quả khó tái lập | Hàm không trạng thái, associative reduction, đo hiệu năng thực tế |
| Chia nhỏ quá mức và đặt tên mơ hồ | Pipeline khó đọc hơn code ban đầu | Mỗi bước có mục đích nghiệp vụ rõ ràng |

**Không phải pipeline nào cũng nên chạy song song.** Một chuỗi thao tác thường đã đủ đơn giản và nhanh. Chạy song song chỉ nên xét khi công việc đủ lớn, các bước độc lập, dữ liệu/collector an toàn, các phép gom hợp lệ và phép đo thực tế cho thấy có lợi. Stream song song không bảo đảm thứ tự chạy side effect của các callback như thứ tự encounter.

## 13. Bài tập áp dụng

### Bài 1: Ghép hàm theo hai cách

Cho **trim: String → String**, **lower: String → String** và **length: String → Integer**. Viết một **Function<String, Integer>** trả độ dài chuỗi sau khi cắt khoảng trắng và đổi thành chữ thường. Hãy dùng cả **andThen** và **compose**, với locale tường minh nếu phép chuyển chữ có liên quan.

**Gợi ý đáp án:**

~~~java
Function<String, String> trim = String::strip;
Function<String, String> lower =
        s -> s.toLowerCase(Locale.ROOT);
Function<String, Integer> length = String::length;

Function<String, Integer> a =
        trim.andThen(lower).andThen(length);
Function<String, Integer> b =
        length.compose(lower).compose(trim);
~~~

Hai hàm đều trả **4** khi nhận **"  JAVA  "**. Các khai báo này là đoạn code đặt trong ngữ cảnh đã import **Function** và **Locale**, không phải file độc lập. Chú ý rằng **String.length()** đếm đơn vị UTF-16, không nhất thiết bằng số ký tự người dùng nhìn thấy trong mọi ngôn ngữ/emoji.

### Bài 2: Sắp xếp thao tác

Với các số **[8, 1, 3, 5]**, thiết kế pipeline “chỉ lấy số lẻ, nhân đôi, sắp tăng dần”. Kết quả phải là **[2, 6, 10]**.

~~~java
List<Integer> answer = List.of(8, 1, 3, 5)
        .stream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * 2)
        .sorted()
        .toList();
~~~

Thử thay **filter** và **map** cho nhau nhưng giữ nguyên predicate **n % 2 != 0**: khi nhân đôi trước, mọi phần tử đều trở thành số chẵn và bị loại, chứng tỏ **thứ tự thay đổi ý nghĩa quy trình**.

### Bài 3: Thiết kế từ mô tả nghiệp vụ

Một danh sách nhân viên có **họ tên, phòng ban, lương**. Yêu cầu:

1. Chỉ chọn nhân viên đang hoạt động.
2. Chuẩn hóa tên phòng ban.
3. Tính thu nhập sau khi áp quy tắc phụ cấp đã cho.
4. Sắp xếp theo thu nhập giảm dần.
5. Tạo bản ghi kết quả để trả về API.

Hãy viết hợp đồng kiểu của mỗi bước trước khi viết Stream; xác định bước nào cần thông tin phụ cấp và cách đưa nó vào như **tham số đầu vào**, thay vì đọc cấu hình toàn cục trong lambda. Quy định rõ cách làm tròn và kiểu số tiền trước khi tính toán. Viết test cho từng phép biến đổi rồi mới kiểm thử toàn chuỗi.

## 14. Ghi nhớ

**Từ phép biến đổi nhỏ đến quy trình lớn** nghĩa là thiết kế các hàm có hợp đồng rõ ràng và ghép chúng theo thứ tự đúng. **Function.andThen/compose** ghép các phép đổi giá trị; **Predicate.and/or/negate** ghép điều kiện; **Stream.filter/map/flatMap/sorted/toList** diễn đạt pipeline trên nhiều phần tử.

Hãy vẽ rõ **dữ liệu đầu vào → từng bước → đầu ra**, cân nhắc vị trí lọc/sắp xếp/gom, giữ phần tính toán dễ tái lập, đưa hiệu ứng I/O vào ranh giới và quyết định cách xử lý lỗi trước khi đưa pipeline vào nghiệp vụ. Cách tổ chức này giúp một quy trình dài vẫn đọc được như một chuỗi thao tác nhỏ có ý nghĩa.
