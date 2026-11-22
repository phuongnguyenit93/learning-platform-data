# Danh tính, trạng thái và hành vi của đối tượng trong Java

Khi nói **đối tượng (object)** trong lập trình hướng đối tượng (OOP), ta không chỉ nói về một tập hợp các biến và hàm. Một đối tượng là một thực thể cụ thể trong lúc chương trình chạy, có **danh tính**, có **trạng thái** và cung cấp **hành vi**. Ba khía cạnh này giúp ta mô hình hóa các thực thể như đơn hàng, tài khoản ngân hàng, giỏ hàng, người chơi hoặc thiết bị trong phần mềm.

Hãy hình dung hai đơn hàng cùng của khách Lan, cùng chứa một quyển sổ và đều có trạng thái “Đã xác nhận”. Chúng có thể trông hoàn toàn giống nhau về dữ liệu, nhưng vẫn là **hai đơn hàng khác nhau**. Ngược lại, cùng một đơn hàng lúc mới tạo có trạng thái “Nháp”, sau khi xác nhận chuyển thành “Đã xác nhận”, nhưng nó vẫn là **chính đơn hàng đó**.

Đó là sự khác biệt cốt lõi:

- **Danh tính (identity):** Đây là đối tượng nào? Nó có phải chính đối tượng đang được tham chiếu ở nơi khác không?
- **Trạng thái (state):** Tại thời điểm này đối tượng đang giữ những dữ liệu gì?
- **Hành vi (behavior):** Đối tượng có thể thực hiện những thao tác gì, trả lời được những câu hỏi gì, và được phép thay đổi trạng thái theo quy tắc nào?

## 1. So sánh ba khía cạnh

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ với `Order` | Có thể thay đổi theo thời gian? |
|---|---|---|---|
| **Danh tính** | Đây có phải *cùng một đối tượng*? | Hai biến cùng trỏ đến một `Order` | Danh tính của một object không đổi trong thời gian nó tồn tại |
| **Trạng thái** | Object hiện có những dữ liệu nào? | Danh sách món, trạng thái `DRAFT`/`CONFIRMED` | Có thể thay đổi nếu thiết kế cho phép |
| **Hành vi** | Object có thể làm gì? | `addItem()`, `confirm()`, `cancel()` | Các phương thức được định nghĩa bởi kiểu; kết quả/hành động có thể phụ thuộc trạng thái |

Một cách nhìn khác: **danh tính** cho phép theo dõi *cùng một đối tượng qua thời gian*; **trạng thái** mô tả *nó đang như thế nào*; **hành vi** quy định *nó có thể phản ứng ra sao*.

### Ví dụ đời thường

Một chiếc thẻ ra vào có mã thẻ riêng. Hôm nay nó ở trạng thái hoạt động, ngày mai có thể bị khóa. Hành vi `unlock()` chỉ hợp lệ khi người thực hiện có quyền, và hành vi `enter()` phải kiểm tra trạng thái hiện hành. Việc khóa thẻ không biến nó thành một thẻ khác.

Trong hệ thống phần mềm, cần phân biệt hai loại danh tính:

1. **Danh tính của đối tượng Java:** một instance cụ thể đang tồn tại trong bộ nhớ JVM, được nhận biết khi so sánh tham chiếu bằng `==`.
2. **Danh tính nghiệp vụ:** mã đơn hàng, UUID, số tài khoản… dùng để theo dõi cùng thực thể nghiệp vụ giữa database, lần chạy ứng dụng và các dịch vụ. Hai đối tượng Java khác nhau vẫn có thể mô tả cùng một bản ghi nghiệp vụ.

Hai khái niệm này có liên quan nhưng **không tương đương**.

## 2. Đối tượng, lớp và tham chiếu

**Lớp (class)** mô tả kiểu dữ liệu và các thao tác; **đối tượng (object)** là instance cụ thể của kiểu đó; **biến tham chiếu (reference variable)** là cách mã Java trỏ tới đối tượng.

~~~java
Order first = new Order("Lan");
Order second = new Order("Lan");
Order alias = first;
~~~

Trong đoạn này:

- `new Order("Lan")` được gọi hai lần, tạo hai instance riêng biệt: `first` và `second`.
- `alias = first` chỉ sao chép **giá trị tham chiếu**. Không có `new`, nên không tạo đối tượng thứ ba.
- `first == second` là `false`; `first == alias` là `true`.
- Nếu `alias` gọi một phương thức làm đổi trạng thái, `first` cũng sẽ quan sát được sự thay đổi đó vì cả hai cùng trỏ đến **một object**.

~~~mermaid
flowchart LR
    F["Biến first"] --> A["Order object #1<br/>customer: Lan<br/>status: DRAFT"]
    AL["Biến alias"] --> A
    S["Biến second"] --> B["Order object #2<br/>customer: Lan<br/>status: DRAFT"]
~~~

Đây là mô hình quan hệ tham chiếu, không phải sơ đồ vị trí bộ nhớ vật lý của JVM. Số lượng biến tham chiếu **không bằng** số lượng đối tượng.

Lưu ý thêm: `Order x;` mới chỉ *khai báo* một biến tham chiếu cục bộ; nó chưa tạo đối tượng nào và phải được gán trước khi đọc. `Order x = null;` cũng không tạo đối tượng: `null` biểu thị hiện không trỏ tới đối tượng nào.

## 3. Ví dụ Java hoàn chỉnh: một đơn hàng có danh tính, trạng thái và hành vi

Ví dụ dưới đây mô hình hóa một đơn hàng với các quy tắc:

- Mỗi instance có một mã định danh `UUID` được tạo khi khởi tạo.
- Đơn hàng lưu tên khách hàng, danh sách mặt hàng và trạng thái hiện hành.
- Chỉ đơn hàng ở trạng thái nháp mới được thêm mặt hàng hoặc xác nhận.
- Đơn hàng rỗng không được xác nhận; chỉ đơn hàng đã xác nhận mới được hủy.

Lưu toàn bộ vào **`Demo.java`**, chạy bằng **Java 17+**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class Demo {
    public static void main(String[] args) {
        Order first = new Order("Lan");
        Order second = new Order("Lan");
        Order alias = first;

        System.out.println("first == second: " + (first == second));
        System.out.println("first == alias: " + (first == alias));

        alias.addItem("Sổ tay");
        first.confirm();

        System.out.println("first status: " + first.getStatus());
        System.out.println("alias status: " + alias.getStatus());
        System.out.println("first items: " + first.getItems());
        System.out.println("second items: " + second.getItems());
        System.out.println("first.equals(second): " + first.equals(second));

        first.cancel();
        System.out.println("alias after cancel: " + alias.getStatus());
    }
}

enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}

final class Order {
    private final UUID id;
    private final String customer;
    private final List<String> items;
    private OrderStatus status;

    public Order(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new IllegalArgumentException("Tên khách hàng không hợp lệ");
        }

        this.id = UUID.randomUUID();
        this.customer = customer;
        this.items = new ArrayList<>();
        this.status = OrderStatus.DRAFT;
    }

    public UUID getId() {
        return id;
    }

    public String getCustomer() {
        return customer;
    }

    public OrderStatus getStatus() {
        return status;
    }

    // Tạo một bản sao chỉ đọc để bên ngoài không sửa trực tiếp items.
    public List<String> getItems() {
        return List.copyOf(items);
    }

    public void addItem(String item) {
        ensureDraft();

        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException("Tên mặt hàng không hợp lệ");
        }

        items.add(item);
    }

    public void confirm() {
        ensureDraft();

        if (items.isEmpty()) {
            throw new IllegalStateException(
                    "Đơn hàng phải có ít nhất một mặt hàng"
            );
        }

        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status != OrderStatus.CONFIRMED) {
            throw new IllegalStateException(
                    "Chỉ được hủy đơn hàng đã xác nhận"
            );
        }

        status = OrderStatus.CANCELLED;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Thao tác chỉ hợp lệ khi đơn hàng là DRAFT"
            );
        }
    }
}
~~~

Chạy:

~~~bash
javac Demo.java
java Demo
~~~

Kết quả:

~~~text
first == second: false
first == alias: true
first status: CONFIRMED
alias status: CONFIRMED
first items: [Sổ tay]
second items: []
first.equals(second): false
alias after cancel: CANCELLED
~~~

### Phân tích từ ví dụ

**Danh tính:** `first` và `second` được tạo từ hai biểu thức `new`, nên chúng là hai instance khác nhau dù ban đầu có cùng tên khách hàng, trạng thái và danh sách mặt hàng trống. `alias` và `first` trỏ cùng một instance, bởi vậy `first == alias` là `true`. Mã `id` giúp nhận diện đơn hàng ở tầng nghiệp vụ, nhưng không phải nguyên nhân làm phép so sánh `==` đúng hay sai.

**Trạng thái:** bộ dữ liệu `id`, `customer`, `items` và `status` mô tả trạng thái của từng `Order`. Sau `alias.addItem("Sổ tay")`, danh sách mặt hàng của `first` thay đổi nhưng `second` vẫn giữ danh sách trống. Sau `first.confirm()`, biến `alias` đọc được trạng thái `CONFIRMED` vì cùng trỏ đến đối tượng ấy.

**Hành vi:** `addItem()`, `confirm()`, `cancel()` là những việc một đối tượng `Order` được phép thực hiện. Chúng áp dụng quy tắc nghiệp vụ trước khi sửa field. Các phương thức `getStatus()` và `getItems()` là hành vi truy vấn, không cần thay đổi trạng thái.

**Tính đóng gói:** các field được khai báo `private`; bên ngoài không thể viết `first.status = ...` hoặc trực tiếp chèn một phần tử vào danh sách nội bộ. Các phương thức công khai là cổng kiểm soát trạng thái hợp lệ. `final class` ở ví dụ giữ thiết kế đơn giản và ngăn lớp con thay đổi quy tắc bằng kế thừa.

### Hành vi tạo thành chuyển trạng thái

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: new Order(...)
    DRAFT --> DRAFT: addItem(item)
    DRAFT --> CONFIRMED: confirm() khi items không rỗng
    CONFIRMED --> CANCELLED: cancel()
~~~

Sơ đồ chỉ vẽ **các chuyển trạng thái hợp lệ được cài đặt**. Ví dụ, `cancel()` ở trạng thái `DRAFT` hoặc `addItem()` ở trạng thái `CONFIRMED` đều ném `IllegalStateException` và không thực hiện chuyển trạng thái mong muốn. Một đối tượng có thể giữ nguyên danh tính xuyên suốt các trạng thái `DRAFT → CONFIRMED → CANCELLED`.

## 4. Nhận diện đúng danh tính của đối tượng

Khi theo dõi một đối tượng qua các lần thay đổi trạng thái, cần đặt câu hỏi **“có còn là chính instance ấy không?”**. Với hai biến tham chiếu, Java dùng `==` để trả lời câu hỏi đó. Một phép so sánh **theo giá trị** lại phụ thuộc vào hợp đồng `equals()` của lớp:

~~~java
Order first = new Order("Lan");
Order alias = first;
Order another = new Order("Lan");

System.out.println(first == alias);   // true: cùng một instance
System.out.println(first == another); // false: hai instance
~~~

Ở lớp `Order` mẫu, `equals()` không được override nên mặc định cũng kiểm tra identity. Với một value object, chẳng hạn `record Point(int x, int y) {}`, hai instance khác nhau có cùng tọa độ lại có thể `equals()` bằng `true`.

**Danh tính nghiệp vụ** như `orderId` cũng là khái niệm riêng: hai đối tượng Java được nạp từ cùng một bản ghi có thể cùng ID nhưng không cùng instance. Đừng dùng `System.identityHashCode()` làm mã đơn hàng: nó không bảo đảm duy nhất hoặc bền vững. Khi cần so sánh theo giá trị và làm khóa collection, phải thiết kế `equals()/hashCode()` có hợp đồng nhất quán. Phần này được đào sâu ở bài về *cùng đối tượng và bằng nhau về giá trị*.

## 5. Trạng thái không chỉ là giá trị của một biến

Trạng thái của đối tượng có thể gồm:

- **Giá trị đơn giản:** `int quantity`, `boolean active`, `OrderStatus status`.
- **Tham chiếu tới các đối tượng khác:** `List<String> items`, `Customer customer`, `Address shippingAddress`.
- **Giá trị được suy ra:** `getItemCount()` có thể tính từ `items.size()` thay vì giữ một field đếm riêng.

Mỗi `Order` chứa một field `items` riêng. Tuy nhiên, tham chiếu là một phần của trạng thái: hai đối tượng *vẫn có thể cùng trỏ tới một danh sách* nếu chương trình cố tình chia sẻ nó. Vì thế, câu “mỗi đối tượng có field riêng” **không có nghĩa** mọi dữ liệu được tham chiếu bên trong đều tự động được sao chép sâu.

### Ví dụ rò rỉ trạng thái nội bộ

~~~java
class UnsafeCart {
    private final List<String> items = new ArrayList<>();

    public List<String> getItems() {
        return items; // Làm lộ danh sách có thể sửa.
    }
}
~~~

Khi đó code bên ngoài có thể gọi `cart.getItems().add("Mặt hàng bất kỳ")` mà không đi qua quy tắc `addItem()`. Đây là **representation exposure**: đối tượng mất quyền kiểm soát trạng thái của mình.

Trong `Order` mẫu, `List.copyOf(items)` cung cấp một snapshot không thể chỉnh sửa qua các thao tác của `List`. Do các phần tử của danh sách là `String` bất biến, nó phù hợp với ví dụ. Nếu danh sách chứa các đối tượng *có thể thay đổi*, sao chép danh sách vẫn chưa đủ để bảo đảm **deep immutability**; cần cân nhắc bản sao phòng vệ của cả phần tử hoặc thiết kế các phần tử bất biến.

### Bất biến của đối tượng (*invariant*)

Invariant là điều luôn phải đúng ở những điểm mà đối tượng được sử dụng hợp lệ. Với `Order`:

- `customer` không được `null` hoặc rỗng.
- `id` được thiết lập khi tạo và không bị gán lại.
- `items` không chứa tên mặt hàng rỗng hoặc `null`.
- Một đơn `CONFIRMED` phải có ít nhất một mặt hàng.
- Không được thêm mặt hàng sau khi rời trạng thái `DRAFT`.

Constructor thiết lập trạng thái ban đầu hợp lệ; các phương thức thay đổi trạng thái có trách nhiệm bảo vệ invariant. Nếu chỉ có dữ liệu mà không có hành vi kiểm tra, trạng thái sai có thể xuất hiện ở khắp nơi trong hệ thống.

### `final` không tự động khiến toàn bộ object bất biến

~~~java
final class Notebook {
    private final List<String> pages = new ArrayList<>();

    public void addPage(String text) {
        pages.add(text); // Vẫn được: nội dung List thay đổi.
    }
}
~~~

`final class` ngăn kế thừa, còn `final` trên field tham chiếu ngăn gán field đó sang đối tượng khác. Cả hai **không tự động** ngăn sửa nội dung của đối tượng được tham chiếu. Một immutable object cần thiết kế để không có cách quan sát thấy trạng thái của nó thay đổi sau khi tạo, đồng thời phải xét các tham chiếu tới dữ liệu mutable.

## 6. Hành vi là hợp đồng, không chỉ là một hàm có tên

Một phương thức đối tượng thường bao gồm:

1. **Điều kiện trước (precondition):** Khi nào lời gọi hợp lệ? Ví dụ `confirm()` chỉ chạy khi đơn ở `DRAFT` và có hàng.
2. **Tác động (effect):** Thay đổi trạng thái hoặc trả dữ liệu gì? Ví dụ chuyển `status` thành `CONFIRMED`.
3. **Điều kiện sau (postcondition):** Điều gì phải đúng khi thành công? Ví dụ đơn đã xác nhận và có ít nhất một mặt hàng.
4. **Xử lý tình huống sai:** Ném exception hoặc trả một kết quả lỗi có cấu trúc theo quy ước API.

**Hành vi thay đổi trạng thái** (command):

~~~java
order.addItem("Bút"); // Có thể làm thay đổi items.
order.confirm();       // Có thể đổi status.
~~~

**Hành vi truy vấn trạng thái** (query):

~~~java
OrderStatus current = order.getStatus();
List<String> lines = order.getItems();
~~~

Trong nhiều thiết kế, tách bạch “lệnh” và “truy vấn” giúp dễ kiểm thử và hiểu code: việc hỏi trạng thái không nên âm thầm thay đổi trạng thái quan sát được nếu không có lý do rõ ràng. Đây là hướng dẫn thiết kế, không phải hạn chế cú pháp Java.

### Vì sao `this` quan trọng?

Trong một instance method, `this` tham chiếu tới đối tượng nhận lời gọi:

~~~java
class Counter {
    private int value;

    public void increment() {
        this.value++;
    }

    public int getValue() {
        return this.value;
    }
}
~~~

~~~java
Counter a = new Counter();
Counter b = new Counter();

a.increment();
a.increment();
b.increment();

System.out.println(a.getValue()); // 2
System.out.println(b.getValue()); // 1
~~~

Phương thức có cùng mã cài đặt trong lớp, nhưng mỗi lời gọi tác động lên **đối tượng nhận lời gọi khác nhau**. Trong phương thức instance, có thể bỏ `this.` khi không gây mơ hồ tên biến; viết rõ `this.value` giúp nhấn mạnh field của object.

Phương thức `static` không có `this` ngầm định và thuộc về lớp. Ví dụ `main` là static vì JVM có thể gọi nó mà không cần tạo `Demo`. Khi học về danh tính và trạng thái của đối tượng, đừng nhầm field static dùng chung với trạng thái instance của từng đối tượng.

## 7. Cùng hành vi được gọi theo kiểu thực tế của đối tượng

OOP còn cho phép một biến có kiểu interface hoặc lớp cha tham chiếu những đối tượng thuộc các lớp cụ thể khác nhau. Lúc gọi instance method đã được override, Java chọn implementation theo **kiểu đối tượng thực tế** (*dynamic dispatch*).

~~~java
interface Notification {
    String message();
}

class EmailNotification implements Notification {
    @Override
    public String message() {
        return "Gửi email";
    }
}

class SmsNotification implements Notification {
    @Override
    public String message() {
        return "Gửi SMS";
    }
}

Notification channel = new SmsNotification();
System.out.println(channel.message()); // Gửi SMS.
~~~

Biến `channel` có kiểu khai báo `Notification`, nhưng tham chiếu một instance `SmsNotification`. Hành vi `message()` được triển khai bởi kiểu cụ thể. Cần phân biệt điều này với phương thức `static`: static method không tham gia override theo cơ chế dispatch này.

### Danh tính không được quyết định bởi hành vi giống nhau

Hai `SmsNotification` đều trả “Gửi SMS” nhưng vẫn là hai object độc lập nếu được tạo bằng hai lần `new`. Việc chúng phản hồi giống nhau không khiến `a == b` thành `true`. Ngược lại, một đối tượng có thể phản hồi khác nhau ở các thời điểm khác nhau do trạng thái thay đổi mà không mất danh tính.

## 8. Hành vi nhận đối tượng khác: biến tham số không phải biến của caller

Một hành vi có thể nhận tham chiếu tới đối tượng khác. Java **luôn truyền tham số theo giá trị**: khi đối số là một tham chiếu, phương thức nhận **bản sao giá trị tham chiếu** ấy. Ví dụ sau là các phương thức đặt trong lớp Java phù hợp:

~~~java
static void addOne(Counter counter) {
    counter.increment(); // Sửa object được chia sẻ.
}

static void replace(Counter counter) {
    counter = new Counter(); // Chỉ gán lại tham số cục bộ.
}
~~~

Khi người gọi truyền cùng một `Counter`, `addOne` có thể làm nó tăng; `replace` không tự đổi biến tham chiếu của người gọi. Cách truyền tham số, ví dụ thực thi và những trường hợp swap được giải thích kỹ ở bài *Tham chiếu, giá trị và cách truyền đối tượng*. Ở đây hãy gắn nguyên tắc đó với trách nhiệm của hành vi: **phương thức có được phép sửa đối tượng nhận vào không?**

## 9. Danh tính tồn tại trong vòng đời của instance

Đối tượng được tạo, khởi tạo trạng thái hợp lệ, nhận lời gọi và có thể đổi trạng thái nhiều lần mà vẫn là **cùng instance**. Khi nó không còn *reachable* từ các GC roots, bộ thu gom rác có thể thu hồi bộ nhớ vào một thời điểm không xác định. Gán một biến bằng `null` không xóa đối tượng nếu vẫn có đường tham chiếu khác tới nó.

Danh tính Java chỉ có ý nghĩa trong vòng đời instance ở JVM đang chạy. Để theo dõi một thực thể sau khi tải lại dữ liệu hoặc chạy chương trình lần khác, cần dùng **mã định danh nghiệp vụ** và dữ liệu được lưu rõ ràng. Các trường hợp `null`, biến chưa gán và object không còn truy cập được có phần phân tích riêng ở bài *Giá trị rỗng và đối tượng chưa tồn tại*.

## 10. Giữ trạng thái và hành vi nhất quán

Một đối tượng có hành vi tốt bảo đảm các *invariant* đã công bố. Khi kiểm tra thiết kế `Order`, hãy hỏi:

1. **Ai được đổi trạng thái?** Nếu trả thẳng `ArrayList` nội bộ, caller có thể bỏ qua kiểm tra `addItem()`. Trả snapshot hoặc hành vi công khai phù hợp sẽ tránh việc này.
2. **Điều kiện của phương thức có rõ không?** `confirm()` chỉ thành công khi đơn đang `DRAFT` và đã có mặt hàng; gọi sai phải có kết quả lỗi nhất quán.
3. **Thông tin quan sát được có khớp quy tắc không?** `getStatus()` không được ngầm thay đổi trạng thái trong ví dụ; `cancel()` phải chuyển đúng từ `CONFIRMED` sang `CANCELLED`.
4. **Có nhiều luồng cập nhật cùng instance không?** Kiểm tra rồi ghi ở các phương thức riêng lẻ không tự thành thao tác nguyên tử. Với truy cập đồng thời, cần ownership hoặc đồng bộ hóa phù hợp.

`private` che giấu field, `final` ngăn gán lại field tham chiếu, còn tính bất biến và an toàn đồng thời đòi hỏi thiết kế rộng hơn. Đây là các lựa chọn triển khai để phục vụ **hợp đồng hành vi**, không thay đổi danh tính của `Order`.

## 11. Cách nhận diện trong bài toán thực tế

Xét hệ thống quản lý máy bán hàng tự động:

| Thực thể | Danh tính | Trạng thái | Hành vi |
|---|---|---|---|
| `VendingMachine` | Mã máy duy nhất trong hệ thống | Hàng còn lại, tiền tạm giữ, chế độ bảo trì | `insertMoney()`, `selectProduct()`, `dispense()` |
| `BankAccount` | Số tài khoản nghiệp vụ | Số dư, trạng thái phong tỏa | `deposit()`, `withdraw()`, `freeze()` |
| `GameCharacter` | ID nhân vật | Máu, vị trí, trang bị | `move()`, `attack()`, `heal()` |
| `Order` | Mã đơn hàng | Mặt hàng, tình trạng xử lý | `addItem()`, `confirm()`, `cancel()` |

Khi thiết kế class, hãy đặt ba câu hỏi theo thứ tự:

1. **Đối tượng nào cần được theo dõi như một thực thể riêng?** Quyết định ranh giới danh tính và có cần ID nghiệp vụ không.
2. **Những dữ liệu nào mô tả trạng thái của chính đối tượng đó?** Xác định field, quan hệ tới đối tượng khác, và invariant cần duy trì.
3. **Những thao tác hợp lệ nào được phép với trạng thái ấy?** Xây dựng phương thức có ý nghĩa nghiệp vụ, kiểm tra precondition và bảo đảm postcondition.

Nếu một thao tác được đặt ở một lớp khác nhưng liên tục cần lấy toàn bộ dữ liệu nội bộ để ra quyết định, nên xem lại liệu hành vi ấy có thuộc trách nhiệm của đối tượng đang nắm giữ trạng thái hay không. Tuy nhiên, tương tác liên đối tượng, domain service và lưu trữ vẫn có chỗ đứng khi một quy tắc không thuộc riêng một thực thể.

## 12. Tự kiểm tra kiến thức

**Bài 1: Hai biến, mấy đối tượng?**

~~~java
Order x = new Order("Minh");
Order y = x;
Order z = new Order("Minh");
~~~

Hỏi: có bao nhiêu `Order` instance? `x == y` và `x == z` lần lượt bằng gì?

**Đáp án:** Có hai instance. `x == y` là `true` vì cùng tham chiếu; `x == z` là `false` vì hai lần tạo riêng.

**Bài 2: Thay đổi trạng thái có làm đổi danh tính?**

~~~java
Order order = new Order("Hà");
Order savedRef = order;

order.addItem("Balo");
order.confirm();
~~~

Hỏi: `savedRef == order` còn là `true` không? `savedRef.getStatus()` trả gì?

**Đáp án:** Vẫn `true`; trạng thái quan sát qua `savedRef` là `CONFIRMED`. Việc cập nhật trạng thái không sinh object mới trong ví dụ này.

**Bài 3: Hành vi và invariant**

Hỏi: `new Order("Hà").confirm()` có hợp lệ không?

**Đáp án:** Không. Đơn chưa có mặt hàng nên `confirm()` ném `IllegalStateException`. Hành vi bảo vệ invariant “đơn đã xác nhận phải có ít nhất một mặt hàng”.

**Bài 4: So sánh giá trị**

~~~java
record Size(int width, int height) {}
Size a = new Size(10, 20);
Size b = new Size(10, 20);
~~~

Hỏi: `a == b` và `a.equals(b)` trả gì?

**Đáp án:** `false` và `true`. Chúng là hai instance nhưng biểu diễn cùng giá trị.

**Bài 5: Mã nghiệp vụ có chứng minh hai biến trỏ cùng object?**

Hỏi: hai đối tượng `Order` khác nhau được nạp từ database với cùng một `orderId` thì phép `==` có nhất thiết trả `true` không?

**Đáp án:** Không. Cùng mã nghiệp vụ có thể là hai biểu diễn trong bộ nhớ khác nhau. Cần xác định quy tắc so sánh theo ID ở tầng nghiệp vụ, tránh nhầm với reference identity.

## Điểm cốt lõi cần ghi nhớ

Một **đối tượng Java** giữ danh tính xuyên suốt thời gian tồn tại, có trạng thái được biểu diễn bằng các field và các đối tượng liên quan, đồng thời cung cấp hành vi thông qua phương thức. Nhiều biến có thể trỏ cùng một đối tượng; nhiều đối tượng có thể mang trạng thái giống nhau. Hành vi tốt giúp chuyển trạng thái một cách có kiểm soát và duy trì invariant. Khi thiết kế OOP, phân biệt rõ **cùng object**, **cùng giá trị**, và **cùng thực thể nghiệp vụ** sẽ tránh rất nhiều lỗi trong thao tác dữ liệu, kiểm thử và tích hợp hệ thống.