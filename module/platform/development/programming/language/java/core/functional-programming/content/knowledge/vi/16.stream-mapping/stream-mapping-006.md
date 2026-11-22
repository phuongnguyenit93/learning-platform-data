# Tạo đối tượng kết quả thay cho sửa đối tượng đầu vào trong Java

Trong lập trình hàm, một nguyên tắc quan trọng là **biến đổi dữ liệu bằng cách trả về giá trị mới thay vì sửa trực tiếp giá trị được truyền vào**. Đối với Java, điều này thường có nghĩa một phương thức nhận đối tượng nguồn, tính toán các trường cần thay đổi, rồi tạo một **đối tượng kết quả**. Đối tượng nguồn vẫn có thể được sử dụng ở nơi khác mà không bị tác động bất ngờ.

Ví dụ, thay vì cập nhật trường trạng thái của một đơn hàng đang được nhiều thành phần tham chiếu, ta viết một hàm trả về **đơn hàng mới** có trạng thái đã thay đổi. Khi logic được tổ chức tốt, cách này giảm phụ thuộc vào trạng thái mutable, thuận lợi cho kiểm thử, phối hợp nhiều bước biến đổi và xử lý đồng thời.

Bài học tập trung vào **biến đổi không gây đột biến dữ liệu đầu vào (non-mutating transformation)** trong Java 17+: so sánh cách viết trước và sau, dùng record và class immutable, phòng tránh sao chép nông, sử dụng Stream.map, xử lý danh sách/map, tối ưu hiệu năng và kiểm chứng tính đúng đắn.

## 1. Sửa tại chỗ và tạo kết quả mới khác nhau thế nào?

Cho một lớp mutable:

~~~java
class MutableCustomer {
    String name;
    String status;

    MutableCustomer(String name, String status) {
        this.name = name;
        this.status = status;
    }
}
~~~

Một cách cập nhật trực tiếp:

~~~java
static void activate(MutableCustomer customer) {
    customer.status = "ACTIVE";
}
~~~

Sau khi gọi activate(customer), **chính instance customer** bị thay đổi. Nếu nhiều biến hoặc thành phần cùng giữ tham chiếu đến instance này, chúng đều có thể quan sát trạng thái mới.

Trong mô hình không sửa đầu vào, thay vì một thủ tục void có side effect, ta có thể định nghĩa một kiểu kết quả và trả đối tượng mới:

~~~java
record Customer(String name, String status) {}

static Customer activate(Customer customer) {
    return new Customer(customer.name(), "ACTIVE");
}
~~~

Bây giờ:

~~~java
Customer oldValue = new Customer("An", "NEW");
Customer newValue = activate(oldValue);

System.out.println(oldValue.status()); // NEW
System.out.println(newValue.status()); // ACTIVE
~~~

Đây là các đoạn minh họa cần đặt trong ngữ cảnh class/method hợp lệ; phần 9 có chương trình Java độc lập đã được biên dịch và chạy.

**Điểm cốt lõi:** kết quả mới không làm cho tham chiếu đang giữ đối tượng cũ tự đổi sang đối tượng mới. Caller **chủ động** sử dụng kết quả vừa trả.

### 1.1. Mutation không đồng nghĩa phép gán tham chiếu

~~~java
Customer before = new Customer("An", "NEW");
Customer after = new Customer(before.name(), "ACTIVE");
~~~

Việc khai báo biến after không sửa before.

~~~java
Customer current = before;
current = new Customer(current.name(), "ACTIVE");
~~~

Phép gán lại **biến cục bộ current** thay tham chiếu mà biến đó giữ; nó không thay đổi các field của instance before. Vì thế **tính bất biến của đối tượng** và **việc một biến tham chiếu có được gán lại hay không** là hai khái niệm khác nhau.

Trong Java, biến final ngăn gán lại tham chiếu sau khi được gán giá trị, nhưng **không** tự biến đối tượng được tham chiếu thành immutable. Một final List<String> vẫn có thể là ArrayList mutable và cho phép add.

## 2. Vì sao cách tạo đối tượng kết quả có ích?

Có bốn lợi ích thường gặp.

**Dễ dự đoán:** cùng đối tượng đầu vào và cùng quy tắc có thể cho kết quả nhất quán, miễn là hàm không phụ thuộc trạng thái ngoài thay đổi. Không ai phải hỏi “phương thức này có lén sửa tham số không?”.

**Dễ kiểm thử:** ta có thể assert cả **kết quả đúng** và **đầu vào không bị sửa**. Với dữ liệu có tính bất biến thực sự, test không cần khôi phục trạng thái gốc sau mỗi lần chạy.

**Dễ kết hợp:** mỗi hàm nhận giá trị và trả giá trị, có thể dùng trong Stream.map, Function.andThen hoặc các bước xử lý liên tiếp. Các bước không cần chia sẻ một đối tượng mutable để truyền kết quả ngầm.

**Giảm rủi ro đồng thời:** immutable data thường đơn giản hơn khi được chia sẻ giữa các luồng, vì không có thao tác viết thay đổi trạng thái của chính dữ liệu đó. Tuy nhiên, bất biến không tự bảo đảm mọi thao tác I/O, cache, publication hoặc dependency ngoài đều thread-safe.

Đổi lại, phương pháp này có thể tạo nhiều đối tượng hoặc bản sao collection. Vì vậy cần cân bằng giữa **độ rõ ràng của hợp đồng** và **chi phí dữ liệu**; không nên máy móc copy toàn bộ một đồ thị lớn sau từng thao tác nhỏ.

## 3. Cấu trúc kết quả bất biến bằng record Java

Java 17 hỗ trợ **record** như một dạng khai báo lớp mang dữ liệu ngắn gọn:

~~~java
record Product(String sku, String name, int price) {}
~~~

Record tự cung cấp constructor, accessor như sku(), name(), price(), các phương thức equals, hashCode và toString với các quy tắc tương ứng.

Một hàm biến đổi:

~~~java
static Product rename(Product original, String newName) {
    return new Product(original.sku(), newName, original.price());
}
~~~

Trạng thái của original không thay đổi. Nhưng cần hiểu giới hạn:

- Các component field của record là **private final**.
- Record **không tự thực hiện deep copy** của component là đối tượng mutable.
- Nếu record giữ ArrayList hoặc một mảng, nội dung của chúng vẫn có thể thay đổi qua tham chiếu, trừ khi tác giả thiết kế phòng vệ.
- Record không bảo đảm mỗi phương thức trên record đều thuần; một phương thức có thể đọc/ghi global state, gọi I/O hoặc làm thay đổi đối tượng mutable được giữ trong component.

Vì thế hãy xem record là công cụ thiết kế **dữ liệu hướng giá trị**, chứ không phải chứng chỉ bảo đảm immutable sâu hoặc pure function trong mọi trường hợp.

### 3.1. Đặt quy tắc biến đổi gần kiểu dữ liệu

Có thể cung cấp phương thức với tên dễ hiểu:

~~~java
record Product(String sku, String name, int price) {
    Product withPrice(int nextPrice) {
        return new Product(sku, name, nextPrice);
    }
}
~~~

Tên withPrice gợi ý việc tạo kết quả thay thế một component; nó **không** phải cú pháp tự động của mọi record. Java record không tự tạo các phương thức withX. Ta tự viết chúng hoặc dùng một kỹ thuật sinh mã phù hợp ở dự án cụ thể.

~~~java
Product oldProduct = new Product("P1", "Book", 100);
Product updated = oldProduct.withPrice(120);
~~~

oldProduct vẫn có price = 100; updated có price = 120.

Không cần tên withX cho mọi trường hợp. Một tên theo nghiệp vụ như applyDiscount hoặc markAsPaid có thể diễn đạt hợp đồng tốt hơn nếu có validation, transition rule hoặc tính toán cụ thể.

## 4. Bảo vệ danh sách thành phần bằng defensive copy

Một Order có danh sách các dòng hàng là ví dụ quan trọng. Code sau **có vấn đề** dù Order là record:

~~~java
record UnsafeOrder(String id, List<String> items) {}

List<String> external = new ArrayList<>();
external.add("Book");

UnsafeOrder order = new UnsafeOrder("O-1", external);
external.add("Pen");

// order.items() hiện có thêm "Pen", dù không tạo Order mới.
~~~

Vì record chỉ giữ một tham chiếu List, cả biến external và record chia sẻ **cùng một đối tượng List mutable**.

Giải pháp:

~~~java
record Order(String id, List<String> items) {
    Order {
        items = List.copyOf(items);
    }
}
~~~

Trong **compact constructor** của record, gán lại tham số items sẽ quyết định giá trị lưu vào component field. List.copyOf tạo một List không thể chỉnh sửa theo hợp đồng, và thực hiện snapshot các phần tử ở mức danh sách (có thể tái sử dụng instance đầu vào khi nó đã là một collection phù hợp).

~~~java
List<String> external = new ArrayList<>(List.of("Book"));
Order original = new Order("O-1", external);

external.add("Pen");
System.out.println(original.items()); // [Book]
~~~

Order không chịu ảnh hưởng của thao tác add vào external sau khi được tạo.

### 4.1. Unmodifiable view không phải bản sao tách biệt

Cẩn thận với:

~~~java
List<String> view = Collections.unmodifiableList(external);
~~~

View chặn thao tác sửa **qua view**, nhưng khi external là một ArrayList vẫn được giữ ở nơi khác, thao tác external.add(...) có thể được quan sát qua view. Vì thế một unmodifiable view trên List mutable **không** đồng nghĩa một snapshot độc lập.

List.copyOf(external) là lựa chọn phù hợp khi cần danh sách kết quả không thể sửa và muốn cách ly thay đổi cấu trúc từ List đầu vào. Lưu ý List.copyOf **không chấp nhận phần tử null**, và đối tượng chứa bên trong vẫn có thể là mutable.

### 4.2. Sao chép nông và bất biến sâu

Giả sử danh sách chứa đối tượng mutable:

~~~java
final class MutableLine {
    int quantity;
    MutableLine(int quantity) {
        this.quantity = quantity;
    }
}
~~~

Một List.copyOf(...) chỉ bảo vệ **cấu trúc danh sách** khỏi thêm/xóa/thay thế phần tử qua danh sách mới. Nó không tự tạo bản sao từng MutableLine:

~~~java
MutableLine line = new MutableLine(1);
List<MutableLine> snapshot = List.copyOf(List.of(line));

line.quantity = 9;
// snapshot.get(0).quantity bây giờ là 9.
~~~

Nếu muốn bất biến xuyên suốt, dùng các element type bất biến (ví dụ record chứa String, int, long) hoặc tự tạo bản sao phòng vệ cho từng phần tử mutable, theo một hợp đồng deep-copy rõ ràng.

**Không có một thao tác chung trong JDK giúp biến mọi đồ thị đối tượng thành deep immutable**. Các chu kỳ tham chiếu, custom class, dữ liệu ngoài và mutable nested structure đòi hỏi thiết kế riêng.

## 5. Stream.map: mỗi phần tử vào, đối tượng kết quả ra

Trong Java functional programming, **map** là phép biến đổi điển hình để tạo dữ liệu mới:

~~~java
record Item(String name, int price) {}

List<Item> original = List.of(
    new Item("Book", 100),
    new Item("Pen", 20)
);

List<Item> discounted = original.stream()
    .map(item -> new Item(
        item.name(), item.price() - 10))
    .toList();
~~~

original không thay đổi; discounted có các đối tượng Item kết quả. Ở ví dụ này, giá mới của Pen là 10. Trong ứng dụng thật cần kiểm tra không âm, overflow, đơn vị tiền, tỷ lệ giảm và chính sách làm tròn phù hợp.

**Nguyên tắc:** lambda của map trả một giá trị, không dùng nó làm nơi sửa tham số rồi trả lại chính tham số đó.

### 5.1. Cách viết nên tránh

~~~java
List<MutableItem> result = items.stream()
    .map(item -> {
        item.setPrice(item.getPrice() - 10);
        return item;
    })
    .toList();
~~~

Đây là đoạn minh họa với lớp MutableItem giả định; nó sửa **chính các instance Item của nguồn** và trả chúng trong kết quả. Hai danh sách lúc này có thể cùng tham chiếu những phần tử đã bị sửa. Dù danh sách kết quả của toList không thể chỉnh sửa, các MutableItem bên trong vẫn có thể mutable.

Cách nên ưu tiên khi có kiểu dữ liệu kết quả rõ ràng:

~~~java
List<Item> result = items.stream()
    .map(item -> new Item(item.name(), item.price() - 10))
    .toList();
~~~

map không tự buộc đối tượng mới; đó là lựa chọn của lambda. Nếu lambda trả cùng instance hoặc sửa trạng thái ngoài, Stream API không thể tự sửa tính thuần cho ứng dụng.

### 5.2. Các phép xử lý khác có cùng tinh thần

- **filter:** chọn phần tử theo điều kiện, thường không sửa nguồn.
- **map:** biến từng phần tử thành kết quả.
- **flatMap:** biến từng phần tử thành stream con rồi làm phẳng.
- **sorted:** tạo pipeline có thứ tự xử lý sắp xếp, không trực tiếp gọi sort trên List nguồn.
- **collect/toList:** thu dữ liệu kết quả.

Không nên nhầm Stream.sorted với List.sort: gọi List.sort trên List mutable là cập nhật trực tiếp danh sách đó; Stream.sorted trả một pipeline mô tả thứ tự kết quả.

### 5.3. Kết quả bất biến có thể chia sẻ phần tử gốc

~~~java
List<Product> filtered = products.stream()
    .filter(product -> product.price() > 0)
    .toList();
~~~

Đây là phép **lọc**, không nhất thiết tạo Product mới. Nếu Product là immutable, có thể chia sẻ phần tử an toàn theo hợp đồng dữ liệu. Nhưng nếu Product mutable, việc chỉ tạo List mới không bảo đảm mỗi Product bên trong đã được sao chép.

Do đó cần phân biệt hai mục tiêu:

1. **Không sửa đối tượng đầu vào trong phép tính hiện tại**.
2. **Đảm bảo kết quả là snapshot bất biến không chịu ảnh hưởng của thay đổi tương lai**.

Mục tiêu thứ hai mạnh hơn và có thể yêu cầu immutable elements hoặc defensive copy sâu hơn.

## 6. Biến đổi object với method reference và Function

Một hàm nhận dữ liệu và trả đối tượng mới có thể được truyền như Function<T,R>:

~~~java
static Product increasePrice(Product product) {
    return new Product(
        product.sku(),
        product.name(),
        Math.addExact(product.price(), 10)
    );
}

List<Product> updated = products.stream()
    .map(MyClass::increasePrice)
    .toList();
~~~

Đây là mẫu minh họa; MyClass phải là tên lớp chứa phương thức. Cách viết method reference làm rõ hành vi và có thể giúp testing độc lập với pipeline.

### 6.1. Kết hợp hàm để tổ chức nhiều bước

~~~java
Function<Product, Product> normalizeName =
    product -> new Product(
        product.sku(),
        product.name().trim(),
        product.price()
    );

Function<Product, Product> addFee =
    product -> new Product(
        product.sku(),
        product.name(),
        Math.addExact(product.price(), 5)
    );

Function<Product, Product> pipeline =
    normalizeName.andThen(addFee);
~~~

Mỗi Function nhận Product, tạo Product khác. Function.andThen thực hiện bước trước rồi truyền giá trị trả về cho bước sau.

Không bắt buộc kết quả mới phải là instance khác **trong mọi nhánh**: một hàm thuần có thể trả lại instance nguồn nếu dữ liệu đã đáp ứng điều kiện và dữ liệu thực sự immutable. Mấu chốt là **không thay đổi trạng thái quan sát được của nguồn**, không phải buộc mọi lời gọi cấp phát object mới để chứng minh phong cách hàm.

### 6.2. Tính thuần: nhiều hơn không mutation

Một hàm không sửa tham số vẫn có thể **không thuần** nếu nó đọc thời gian hiện tại, random, mutable static field, truy vấn database hoặc ghi log ngoài. Ví dụ:

~~~java
static Receipt stamp(Order order) {
    return new Receipt(order.id(), Instant.now());
}
~~~

Đoạn trên là minh họa với các kiểu Receipt/Order phù hợp; kết quả phụ thuộc Instant.now, nên cùng order có thể cho kết quả khác nhau.

Nếu muốn determinism, truyền thời gian hoặc Clock như một dependency rõ:

~~~java
static Receipt stamp(Order order, Instant issuedAt) {
    return new Receipt(order.id(), issuedAt);
}
~~~

Đoạn này có thể có tính thuần khi các dữ liệu liên quan bất biến và hàm không có side effect. Tách phụ thuộc môi trường giúp kiểm thử chính xác hơn.

## 7. Chuyển dữ liệu theo các bước: input → value → output

Trong code nghiệp vụ, phân biệt **data model gốc** và **result model** thường làm rõ ý nghĩa:

~~~java
record OrderInput(String sku, int quantity, int price) {}
record OrderSummary(String sku, long amount) {}

static OrderSummary summarize(OrderInput input) {
    long amount = Math.multiplyExact(
        (long) input.quantity(), input.price());
    return new OrderSummary(input.sku(), amount);
}
~~~

Đối tượng OrderInput giữ dữ liệu gốc; OrderSummary lưu dạng kết quả. Không cần thêm field amount vào OrderInput hoặc sửa giá/trạng thái để tạm lưu kết quả.

Ưu điểm thiết kế:

- Tầng input giữ ý nghĩa của dữ liệu đầu vào.
- Tầng transformation thể hiện rõ **đổi loại giá trị**, chẳng hạn OrderInput → OrderSummary.
- Tầng output có thể định nghĩa validation, serialization hoặc format riêng.
- Có thể tạo nhiều góc nhìn từ cùng input mà không sửa lẫn nhau.

Cách này hữu ích cho DTO mapping, tạo báo cáo, chuẩn hóa dữ liệu, chuyển entity sang response, tính tổng giỏ hàng và pipeline ETL.

### 7.1. Không đồng nhất domain entity với DTO

Một entity có identity, lifecycle, persistence context và quy tắc cập nhật riêng; một immutable DTO thường có mục đích trao đổi dữ liệu. Việc tạo DTO mới từ entity thường là lựa chọn tốt cho read-only projection. Nhưng không nên tự suy luận rằng toàn bộ hệ thống persistence sẽ lưu đối tượng mới chỉ vì bạn tạo bản copy: với JPA/Hibernate, entity managed và dirty checking có hợp đồng khác.

Chọn ranh giới:

- **Đọc và chuẩn bị trả dữ liệu:** thường tạo DTO/record kết quả.
- **Thực thi thay đổi nghiệp vụ có chủ đích:** dùng command hoặc service cập nhật theo transaction, validation và persistence.
- **Tính toán trung gian:** ưu tiên hàm nhận giá trị và trả giá trị.

Mục tiêu là tránh **mutation ngầm không chủ đích**, không phải phủ nhận nhu cầu cập nhật database thực tế.

## 8. Mảng, Map và các collection kết quả

### 8.1. Với List

~~~java
List<String> trimmed = original.stream()
    .map(String::trim)
    .toList();
~~~

Stream.toList trên Java 17 trả List không thể chỉnh sửa. Nếu cần ArrayList mutable cho API tiếp theo:

~~~java
List<String> mutable = original.stream()
    .map(String::trim)
    .collect(Collectors.toCollection(ArrayList::new));
~~~

Những ví dụ này cần import java.util.List, java.util.ArrayList và java.util.stream.Collectors ở lớp chứa chúng.

### 8.2. Với Map

Có thể tạo map kết quả thay vì dùng putAll/replaceAll để sửa Map nguồn:

~~~java
Map<String, Integer> source = Map.of("A", 10, "B", 20);

Map<String, Integer> result = source.entrySet().stream()
    .collect(Collectors.toUnmodifiableMap(
        Map.Entry::getKey,
        entry -> Math.multiplyExact(entry.getValue(), 2)
    ));
~~~

source không đổi; result chứa A → 20 và B → 40. Collectors.toUnmodifiableMap tạo map không thể chỉnh sửa, **không chấp nhận khóa/giá trị null** và có thể ném IllegalStateException khi gặp khóa trùng nếu dùng overload hai tham số. Nếu muốn xử lý khóa trùng, dùng overload có merge function phù hợp.

Không nên giả định iteration order của Map.of hay Collectors.toUnmodifiableMap là thứ tự đã nhập. Khi cần thứ tự xác định, dùng cấu trúc hoặc collector có hợp đồng thứ tự rõ và cân nhắc việc tạo bản sao/bọc phù hợp.

### 8.3. Với array

Mảng Java mutable, nên trả về một mảng mới thay vì sửa mảng nguồn:

~~~java
int[] original = {1, 2, 3};

int[] doubled = java.util.Arrays.stream(original)
    .map(value -> Math.multiplyExact(value, 2))
    .toArray();
~~~

original vẫn là [1, 2, 3]; doubled là [2, 4, 6]. Nhưng doubled vẫn là **mảng mutable**: việc tạo bản sao giải quyết alias với mảng nguồn, không tự làm kết quả immutable.

Nếu một class giữ int[] như field và muốn bất biến theo nghĩa quan sát được, thường phải **clone khi nhận vào** và **clone khi trả ra**, không cung cấp thẳng mảng nội bộ.

## 9. Ví dụ Java 17+ độc lập: Order và Receipt

Chương trình sau mô hình hóa đơn hàng theo hướng giá trị. **Order** chứa danh sách Item bất biến ở mức cấu trúc, có các phương thức tạo kết quả **withStatus** và **withAddedItem**. **Receipt** là một kết quả tách biệt từ Order; phần mô tả của nó cũng được phòng vệ qua List.copyOf.

Tạo tệp **ImmutableTransformDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableTransformDemo {
    record Item(String sku, int quantity, int unitPrice) {
        Item {
            Objects.requireNonNull(sku);
            if (sku.isBlank() || quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }

        long amount() {
            return Math.multiplyExact((long) quantity, unitPrice);
        }
    }

    record Order(String id, List<Item> items, String status) {
        Order {
            Objects.requireNonNull(id);
            Objects.requireNonNull(status);
            items = List.copyOf(items);
        }

        Order withStatus(String next) {
            return new Order(id, items, next);
        }

        Order withAddedItem(Item item) {
            List<Item> copy = new ArrayList<>(items);
            copy.add(item);
            return new Order(id, copy, status);
        }

        long total() {
            return items.stream().map(Item::amount)
                .reduce(0L, Math::addExact);
        }
    }

    record Receipt(String orderId, String status,
                   long total, List<String> lines) {
        Receipt {
            lines = List.copyOf(lines);
        }
    }

    static Receipt toReceipt(Order order) {
        List<String> lines = order.items().stream()
            .map(item -> item.sku() + " x" +
                item.quantity() + "=" + item.amount())
            .toList();
        return new Receipt(order.id(), order.status(),
            order.total(), lines);
    }

    public static void main(String[] args) {
        List<Item> seed = new ArrayList<>(List.of(
            new Item("Book", 2, 40)
        ));
        Order original = new Order("O-1", seed, "NEW");
        seed.add(new Item("Hidden", 9, 9));

        Order paid = original.withStatus("PAID");
        Order extended = paid.withAddedItem(new Item("Pen", 3, 10));
        Receipt receipt = toReceipt(extended);

        System.out.println("original=" + original.status() +
            ",total=" + original.total() +
            ",items=" + original.items().size());
        System.out.println("paid=" + paid.status() +
            ",total=" + paid.total() +
            ",items=" + paid.items().size());
        System.out.println("extended=" + extended.status() +
            ",total=" + extended.total() +
            ",items=" + extended.items().size());
        System.out.println("receipt=" + receipt);
        System.out.println("same-instance=" + (original == paid));

        try {
            original.items().add(new Item("Eraser", 1, 5));
        } catch (UnsupportedOperationException error) {
            System.out.println("items-unmodifiable=true");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ImmutableTransformDemo.java
java ImmutableTransformDemo
~~~

**Stdout chính xác:**

~~~text
original=NEW,total=80,items=1
paid=PAID,total=80,items=1
extended=PAID,total=110,items=2
receipt=Receipt[orderId=O-1, status=PAID, total=110, lines=[Book x2=80, Pen x3=30]]
same-instance=false
items-unmodifiable=true
~~~

### 9.1. Phân tích kết quả

**Bước 1:** original được tạo từ seed chứa Book × 2 × 40, tổng là 80. Constructor compact của Order dùng List.copyOf(items), tạo snapshot không thể sửa ở mức cấu trúc. Vì vậy sau khi seed.add(Hidden), original.items vẫn có đúng 1 mục.

**Bước 2:** original.withStatus("PAID") trả một Order mới giữ danh sách Item hiện có nhưng thay trạng thái. original.status vẫn là NEW, còn paid.status là PAID. Hai Order là hai instance khác nhau.

**Bước 3:** paid.withAddedItem(Pen × 3 × 10) tạo một ArrayList tạm từ danh sách cũ, thêm mục Pen rồi tạo Order mới; constructor của Order chuyển nó thành List không thể chỉnh sửa. paid giữ 1 mục; extended có 2 mục, tổng bằng 80 + 30 = 110.

**Bước 4:** toReceipt chuyển Order thành kiểu Receipt hoàn toàn khác, gồm mã đơn, trạng thái, tổng và danh sách chuỗi diễn giải. Receipt không cần sửa Order để thêm các trường phục vụ giao diện.

**Bước 5:** original == paid là false vì phương thức withStatus đã tạo Order instance khác. Nếu dữ liệu được so sánh bằng equals, Java record cung cấp value-based equality dựa trên component, nhưng không nên lấy **đồng nhất tham chiếu** làm tiêu chí duy nhất để đánh giá một hàm có gây mutation hay không.

**Bước 6:** cố thêm phần tử vào original.items() gây UnsupportedOperationException; ví dụ bắt đúng lỗi chỉ để in cờ minh họa. Trong sản phẩm thật, không nên dùng exception làm phép thử thường xuyên cho khả năng mutable của một collection.

### 9.2. Vì sao không có rò rỉ mutation qua Item?

Item là record với component String và các primitive int. String immutable và primitive không có trạng thái đối tượng để sửa qua tham chiếu, nên bản thân Item trong ví dụ là kiểu dữ liệu bất biến theo thiết kế này.

Nếu thay Item bằng một lớp có List mutable hoặc Calendar mutable mà không sao chép phòng vệ, cùng mã Order dùng List.copyOf **chưa đủ** để giữ bất biến sâu. Muốn bảo đảm dữ liệu an toàn khi chia sẻ, phải kiểm tra toàn bộ cấu trúc component.

### 9.3. Chi phí và giới hạn của ví dụ

- withStatus tạo Order mới nhưng có thể chia sẻ danh sách Item bất biến sẵn có.
- withAddedItem tạo List tạm và snapshot kết quả; chi phí thường tăng theo số phần tử.
- toReceipt tạo danh sách chuỗi mới và Receipt mới.
- Mỗi lần gọi total() đang tính tổng từ các Item; với dữ liệu lớn, có thể xem xét mô hình cache được thiết kế cẩn thận hoặc tính toán khi tạo snapshot.
- Math.multiplyExact và Math.addExact phát hiện tràn số trong đường tính tổng; tuy nhiên unitPrice dùng int là mô hình đơn giản để tập trung vào immutability, không phải kiến trúc tiền tệ hoàn chỉnh.
- Ví dụ không bao gồm database, giao dịch, event sourcing hay xử lý nhiều writer cạnh tranh. Việc tạo Order mới trong bộ nhớ **không đồng nghĩa** dữ liệu đã được persist vào hệ thống bên ngoài.

## 10. Hiệu năng: copy toàn bộ, structural sharing và các trade-off

### 10.1. Sao chép có chi phí thật

Với một List có n phần tử, sao chép bằng new ArrayList<>(old) thường có chi phí bộ nhớ và thời gian **O(n)**. Nếu sau đó List.copyOf tiếp tục tạo snapshot, có thể có thêm bước sao chép tùy nguồn và implementation.

Nếu một đối tượng lớn có nhiều component immutable và chỉ đổi một component nhỏ, có thể chia sẻ các component bất biến sẵn có thay vì copy mọi giá trị.

Ví dụ:

~~~java
Order withStatus(String nextStatus) {
    return new Order(id, items, nextStatus);
}
~~~

items đã là List không thể sửa trong Order ví dụ, và Item bất biến nên **có thể chia sẻ an toàn** giữa Order cũ/mới. Đừng sao chép sâu tất cả component một cách vô ích nếu chúng thực sự immutable và hợp đồng cho phép.

### 10.2. Persistent data structures và structural sharing

Một số thư viện cung cấp cấu trúc dữ liệu persistent, khi cập nhật có thể tạo phiên bản mới nhưng **chia sẻ nhiều node bất biến** với phiên bản cũ. Điều này có thể giảm chi phí so với copy nguyên một danh sách/map lớn mỗi lần thay đổi.

JDK Collections thông thường không cung cấp đầy đủ persistent collection API kiểu vector/trie như một thành phần chung thay thế ArrayList/HashMap. Nếu cần tối ưu cấu trúc khổng lồ được cập nhật nhiều lần, hãy cân nhắc thư viện được hỗ trợ trong dự án, cách truy cập thực tế và đo benchmark.

**Không ngầm khẳng định record tự dùng structural sharing.** Record chỉ lưu component theo thiết kế của class; việc có chia sẻ cấu trúc hay không phụ thuộc kiểu component và cách tạo kết quả.

### 10.3. Khi mutation có chủ đích vẫn hợp lý

Trong thuật toán tại chỗ, buffer xử lý dữ liệu lớn, giao tiếp I/O hoặc entity persistence, cập nhật mutable state có thể là lựa chọn đúng. Tách rõ **vùng code có mutation được kiểm soát** khỏi **vùng biến đổi dữ liệu theo giá trị**, thay vì cố tránh mọi phép gán hay thay đổi trạng thái.

Ví dụ khi xây dựng kết quả gồm hàng triệu phần tử, dùng một ArrayList mutable nội bộ để tích lũy rồi trả snapshot bất biến có thể hiệu quả hơn việc tạo bản sao List sau từng phần tử. Hàm vẫn có thể đáp ứng hợp đồng **không làm thay đổi đầu vào và không lộ mutable internals**:

~~~java
static List<String> normalize(List<String> source) {
    List<String> buffer = new ArrayList<>();
    for (String text : source) {
        buffer.add(text.trim());
    }
    return List.copyOf(buffer);
}
~~~

Mutation trên buffer **cục bộ, không được chia sẻ ra ngoài** khác với mutation trên source do caller giữ. Tính thuần còn phụ thuộc vào kiểu phần tử, null, sự can thiệp đồng thời và môi trường bên ngoài, nhưng thiết kế này thể hiện ranh giới rõ ràng.

## 11. Kiểm thử: xác nhận cả kết quả lẫn đầu vào không đổi

Một unit test phù hợp cần kiểm tra:

1. Kết quả có đúng dữ liệu mong đợi không?
2. Đối tượng đầu vào có giữ nguyên trạng thái quan sát được không?
3. Nếu có nhiều tham chiếu đến nguồn, tham chiếu cũ còn thấy dữ liệu cũ không?
4. Nếu có nested collection, thay đổi từ ngoài có ảnh hưởng đến giá trị đã tạo không?
5. Những collection được công bố là không thể sửa có thực sự chặn thao tác sửa không?
6. Các trường hợp null, overflow, giá trị không hợp lệ có xử lý theo hợp đồng không?

Ví dụ JUnit 5 theo mô hình ở phần 9:

~~~java
// Minh họa assertion JUnit 5, cần dependency JUnit 5.
Order original = new Order("O-1",
    List.of(new Item("Book", 2, 40)), "NEW");

Order updated = original.withStatus("PAID");

assertEquals("NEW", original.status());
assertEquals("PAID", updated.status());
assertEquals(80L, original.total());
assertNotSame(original, updated);
~~~

Các record trong chương trình mẫu là nested types của ImmutableTransformDemo; khi viết test ngoài class cần import hoặc ghi rõ ImmutableTransformDemo.Order nếu visibility/package cho phép.

Nên bổ sung test defensive copy:

~~~java
List<Item> seed = new ArrayList<>();
seed.add(new Item("Book", 1, 40));

Order original = new Order("O-1", seed, "NEW");
seed.add(new Item("Pen", 1, 10));

assertEquals(1, original.items().size());
assertThrows(UnsupportedOperationException.class,
    () -> original.items().clear());
~~~

Test này xác nhận danh sách của Order không chịu thêm/xóa từ seed và không cho sửa qua accessor. Nó **không** chứng minh mọi item nested đều immutable trong mô hình tổng quát; phải kiểm tra riêng kiểu Item.

## 12. Những lỗi thường gặp

**Lỗi 1 — sửa rồi trả chính object nguồn.** Lambda map gọi setter lên tham số và trả tham số đó làm mất hợp đồng non-mutating, có thể khiến nhiều nơi thấy dữ liệu bị thay đổi.

**Lỗi 2 — tin rằng final đồng nghĩa immutable.** final trên field/tham chiếu ngăn gán lại, không ngăn sửa nội dung ArrayList hay object bên trong.

**Lỗi 3 — tin rằng mọi record đều deep immutable.** Record có thể giữ mutable List, array hoặc custom object. Cần defensive copy đúng mức và chọn immutable component.

**Lỗi 4 — dùng Collections.unmodifiableList như một snapshot tuyệt đối.** Đây thường là unmodifiable view, có thể phản ánh thay đổi của List gốc. List.copyOf giúp tạo snapshot cấu trúc khi cần.

**Lỗi 5 — quên copy khi trả array.** Một class giữ array rồi trả array nội bộ cho caller sẽ cho phép sửa qua accessor; cần cân nhắc clone cả đầu vào và đầu ra.

**Lỗi 6 — nghĩ Stream.filter/map tự bảo đảm tính thuần.** Callback có thể sửa field ngoài, gửi log hoặc update DB. Stream API chỉ tạo một khuôn xử lý, không ngăn side effect của lập trình viên.

**Lỗi 7 — dùng Stream.toList rồi cho rằng element immutable.** List kết quả không thể chỉnh sửa nhưng element có thể mutable; cần phân biệt bất biến của collection với bất biến của từng phần tử.

**Lỗi 8 — sao chép đối tượng mà quên nested references.** Hai object “khác instance” vẫn có thể chia sẻ một List mutable gây aliasing. Thiết kế chia sẻ chỉ an toàn khi phần được chia sẻ có hợp đồng bất biến phù hợp.

**Lỗi 9 — copy toàn bộ quá mức.** Sao chép sâu một đồ thị lớn cho mỗi phép biến đổi có thể lãng phí tài nguyên. Xem xét chia sẻ phần tử immutable, gom nhiều cập nhật vào một lần dựng kết quả hoặc dùng persistent collection phù hợp.

**Lỗi 10 — không sử dụng giá trị trả về.** Nếu phương thức withStatus trả Order mới, gọi original.withStatus("PAID") nhưng bỏ qua kết quả sẽ không cập nhật original. Caller phải gán hoặc truyền tiếp instance mới một cách rõ ràng.

**Lỗi 11 — coi Object identity là nội dung.** Record cung cấp equals theo component; hai instance khác nhau có thể bằng nhau về giá trị. Đừng quyết định trạng thái nghiệp vụ chỉ dựa vào == khi yêu cầu là equality.

**Lỗi 12 — bỏ qua validation khi tạo bản mới.** Mọi constructor/factory cần giữ invariant như số lượng dương, đơn giá hợp lệ, status hợp lệ và không chứa phần tử null nếu hợp đồng cấm.

**Lỗi 13 — cho rằng immutable DTO tự lưu database.** Một đối tượng mới chỉ là giá trị bộ nhớ; persistence, transaction và cạnh tranh cập nhật là trách nhiệm của tầng lưu trữ.

**Lỗi 14 — hàm không sửa đầu vào nhưng phụ thuộc global state.** Một hàm đọc clock, random hoặc mutable static map có thể không thuần dù không gọi setter trên tham số.

**Lỗi 15 — tối ưu sớm bằng cache mutable chia sẻ.** Cache có thể làm phức tạp thread-safety và invalidation. Nếu cần cache, thiết kế theo hợp đồng bất biến của input/output và kiểm thử đồng thời phù hợp.

## 13. Checklist lựa chọn thiết kế

| Tình huống | Hướng làm thường phù hợp |
| --- | --- |
| Chuẩn hóa một đối tượng đầu vào | Tạo object kết quả với các giá trị chuẩn hóa |
| Đổi trạng thái có kiểm soát | Hàm withStatus/markAsPaid trả object mới |
| Chuyển domain entity sang response | Tạo DTO/record mới, không gắn field hiển thị vào entity |
| Biến đổi nhiều phần tử | Stream.map trả kết quả, toList/collector phù hợp |
| Cần giữ bản gốc để audit/so sánh | Value object bất biến hoặc snapshot có phòng vệ |
| Kết quả có List/Map nested | Defensive copy, kiểm tra element mutability |
| Cần chia sẻ giữa thread | Bất biến dữ liệu và publication đúng hợp đồng |
| Tính toán lớn với nhiều cập nhật | Mutation cục bộ hoặc cấu trúc persistent, đo hiệu năng |
| Cần lưu thay đổi vào DB | Command/service/transaction tường minh |
| Dữ liệu đầu vào là array | Clone hoặc tạo array kết quả mới theo yêu cầu |

Không có một quy tắc bắt buộc mọi hoạt động trong ứng dụng phải tạo đối tượng mới. Chọn abstraction theo nghĩa nghiệp vụ và chi phí, nhưng nên **tránh sửa input không được caller mong đợi**.

## 14. Câu hỏi tự kiểm tra

1. Điểm khác biệt giữa việc gán lại một biến tham chiếu và sửa field của object mà biến trỏ tới là gì?
2. Vì sao một record có component List<MutableItem> không tự được xem là deep immutable?
3. List.copyOf và Collections.unmodifiableList khác nhau thế nào khi bên ngoài vẫn giữ ArrayList nguồn?
4. Nếu Stream.map sửa field của từng phần tử rồi trả lại phần tử đó, List mới có bảo vệ dữ liệu gốc không?
5. Khi dùng phương thức withStatus trả Order mới, điều gì xảy ra nếu caller không dùng kết quả?
6. Tại sao một DTO mới tạo từ entity không tự động được persist?
7. Vì sao chia sẻ immutable Item giữa hai Order có thể an toàn, còn chia sẻ MutableItem lại có rủi ro?
8. Trường hợp nào một buffer mutable cục bộ vẫn phù hợp với thiết kế không sửa đầu vào?
9. Những trường hợp nào nên cân nhắc persistent data structures hoặc structural sharing?
10. Làm thế nào kiểm tra đồng thời kết quả đúng và đầu vào không đổi bằng unit test?
11. Stream.toList trả List không thể chỉnh sửa; điều này có chứng minh các object phần tử cũng bất biến không?
12. Nếu hàm luôn tạo record mới nhưng gọi Instant.now, hàm đó có thuần hoàn toàn không?
13. Khi cần thay đổi dữ liệu lưu trữ thật sự, nên đặt mutation ở ranh giới nào?
14. Vì sao final List không đủ để ngăn source.add làm thay đổi danh sách?
15. Các invariant về quantity, price, null và status cần được kiểm tra ở đâu khi tạo object mới?

**Kết luận:** Trong biến đổi dữ liệu Java, ưu tiên **hàm nhận đầu vào và trả về đối tượng kết quả** thay vì lén sửa instance do caller truyền vào. Record, class immutable, defensive copy và Stream.map là những công cụ hữu ích, nhưng phải hiểu **aliasing, shallow/deep immutability, mutation nội bộ, chi phí sao chép và persistence**. Tính đúng đắn nằm ở hợp đồng quan sát được: kết quả có giá trị mong muốn và dữ liệu đầu vào vẫn đáng tin cậy sau phép biến đổi.