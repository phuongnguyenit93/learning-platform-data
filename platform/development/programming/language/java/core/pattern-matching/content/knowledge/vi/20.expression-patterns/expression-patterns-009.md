# Giới hạn khi nhồi quá nhiều logic vào expression

## 1. Vấn đề: biểu thức ngắn chưa chắc đã dễ hiểu

Pattern matching cho phép Java kiểm tra kiểu dữ liệu và lấy thông tin trong cùng một biểu thức. Từ Java 21, ta có thể dùng `instanceof` với record pattern, hoặc đặt pattern trong `case` của `switch`. Nhờ đó, những đoạn code nhiều lần ép kiểu và gọi accessor có thể gọn hơn.

Tuy nhiên, **gộp càng nhiều kiểm tra vào một expression không đồng nghĩa code càng tốt**. Khi một biểu thức vừa kiểm tra cấu trúc, xử lý `null`, áp dụng hàng loạt quy tắc nghiệp vụ, tạo thông báo và thực hiện tác dụng phụ, người đọc khó trả lời:

- Điều kiện nào phải đúng trước điều kiện nào?
- Biến được ràng buộc từ pattern có dùng được ở vị trí này không?
- Nhánh nào sẽ được thực hiện khi dữ liệu thiếu hoặc điều kiện sai?
- Có thể kiểm tra từng quy tắc một cách độc lập hay không?

Trong bài này, “giới hạn” là **giới hạn về khả năng đọc, sửa, kiểm tra và hiểu đúng hành vi**, chứ không phải Java đặt ra một con số cố định về độ dài biểu thức hoặc số lượng toán tử `&&` được phép dùng.

## 2. Ví dụ: một expression chứa quá nhiều trách nhiệm

Giả sử đơn hàng có thông tin khách hàng và địa chỉ:

```java
record Address(String city) {}
record Customer(String name, Address address, boolean active) {}
record Order(String id, Customer customer, int total) {}
```

Quy tắc đơn được xét ưu tiên:

1. `Order` phải có `Customer` và `Address` có cấu trúc hợp lệ.
2. Khách hàng phải còn hoạt động.
3. Mã đơn và tên khách hàng không được để trống.
4. Giá trị đơn hàng phải từ `100` trở lên.
5. Thành phố phải là `Hà Nội` hoặc `Đà Nẵng`.

Có thể viết một biểu thức boolean dài:

```java
static boolean eligibleInline(Object input) {
    return input instanceof Order(
            String id,
            Customer(String name, Address(String city), boolean active),
            int total)
            && active
            && !id.isBlank()
            && !name.isBlank()
            && total >= 100
            && ("Hà Nội".equals(city) || "Đà Nẵng".equals(city));
}
```

Đây là **mã Java 21 hợp lệ**, giả định ba record đã được khai báo cùng phạm vi. Nó có lợi thế là các điều kiện được đánh giá theo trình tự; nhưng muốn thay đổi quy tắc địa điểm, ngưỡng giá trị hoặc định nghĩa khách hàng hợp lệ, người đọc phải mở lại toàn bộ expression.

Khi danh sách quy tắc tăng lên, việc bảo trì thường khó hơn vì ba lớp ý nghĩa bị trộn lẫn:

- **Cấu trúc dữ liệu:** `input` có phải `Order` chứa `Customer` và `Address` hay không?
- **Quy tắc nghiệp vụ:** khách hàng hoạt động, mã hợp lệ, tổng tiền đủ ngưỡng, thành phố hỗ trợ?
- **Quyết định xử lý:** nếu đủ điều kiện thì trả về gì, nếu không thì cần giải thích lý do nào?

Điều kiện ngắn và ổn định vẫn có thể để nguyên. Cần tách nhỏ khi các quy tắc thay đổi độc lập, xuất hiện nhiều nhánh hoặc người đọc phải liên tục đếm ngoặc và suy luận thứ tự đánh giá.

## 3. Pattern trước, điều kiện phụ thuộc sau

Trong ví dụ trên, phần:

```java
input instanceof Order(
        String id,
        Customer(String name, Address(String city), boolean active),
        int total)
```

làm hai việc: kiểm tra giá trị thuộc kiểu record tương ứng và **phân rã** các component. Các biến `id`, `name`, `city`, `active`, `total` chỉ được ràng buộc khi toàn bộ pattern khớp.

Sau đó, các phép kiểm tra được nối bằng `&&`. Toán tử này đánh giá ngắn mạch (*short-circuit*): nếu phần bên trái là `false`, Java không tính phần bên phải. Đây là lý do có thể dùng các biến pattern ở những toán hạng `&&` sau khi mẫu đã khớp.

Ví dụ minh họa:

```java
if (input instanceof Order(
        String id, var customer, int total)
        && total >= 100) {
    System.out.println(id);
}
```

Ở đây, `total` chỉ được kiểm tra khi record pattern đã khớp. Nếu `input` không phải `Order` hoặc bằng `null`, điều kiện `instanceof` trả về `false` và phần `total >= 100` không chạy.

**Không tùy tiện thay `&&` bằng `||` hoặc `&`:**

```java
// Không biên dịch: vế phải của || có thể chạy khi pattern không khớp,
// nên biến total không chắc đã được ràng buộc.
// if (input instanceof Order(String id, var customer, int total)
//         || total >= 100) {
//     System.out.println(id);
// }
```

Đây là ví dụ lỗi có chủ đích, được chú thích để tránh hiểu nhầm là chương trình chạy hoàn chỉnh. Với `||`, vế phải được đánh giá khi vế trái sai; còn với `&` trên boolean, cả hai vế được tính, làm mất đặc tính ngắn mạch. Khi điều kiện thứ hai **phụ thuộc** vào biến từ pattern, hãy thể hiện phụ thuộc đó bằng `&&` hoặc tách luồng xử lý thành các bước.

Ngoài ra, cặp ngoặc trong:

```java
&& ("Hà Nội".equals(city) || "Đà Nẵng".equals(city))
```

làm rõ rằng lựa chọn thành phố là **một nhóm điều kiện con**. Nếu bỏ ngoặc và thay đổi cấu trúc `&&`/`||`, thứ tự ưu tiên toán tử có thể làm thay đổi cả ý nghĩa nghiệp vụ.

## 4. Tách quy tắc thành các hàm có tên

Giữ record pattern ở vị trí kiểm tra cấu trúc, nhưng đưa quy tắc nghiệp vụ ra các hàm nhỏ. Ví dụ:

```java
static boolean hasIdentity(String id, String name) {
    return id != null && !id.isBlank()
            && name != null && !name.isBlank();
}

static boolean isSupportedCity(String city) {
    return "Hà Nội".equals(city) || "Đà Nẵng".equals(city);
}

static boolean eligibleReadable(Object input) {
    if (!(input instanceof Order(
            String id,
            Customer(String name, Address(String city), boolean active),
            int total))) {
        return false;
    }

    return active
            && hasIdentity(id, name)
            && total >= 100
            && isSupportedCity(city);
}
```

Đoạn minh họa giả định các kiểu `Address`, `Customer`, `Order` có sẵn. Các hàm `hasIdentity`, `isSupportedCity` nói rõ **quy tắc nào** đang được áp dụng; phương thức `eligibleReadable` nói rõ **khi nào** áp dụng các quy tắc.

Phủ định pattern ở guard đầu tiên có dạng:

```java
if (!(input instanceof Order(...))) {
    return false;
}
```

Điểm quan trọng là nhánh không khớp **kết thúc ngay bằng `return`**. Sau nhánh ấy, mọi đường đi tiếp đều đã khớp pattern nên các biến `id`, `name`, `city`, `active`, `total` có thể được dùng theo quy tắc *flow scoping* của Java. Nếu nhánh không khớp không thoát khỏi luồng xử lý, trình biên dịch không nhất thiết cho phép dùng các biến bên dưới.

Cách tách này mang lại ba lợi ích rõ ràng: tên hàm cho biết ý nghĩa nghiệp vụ, từng điều kiện có thể được kiểm thử riêng, và một thay đổi về thành phố phục vụ không đòi hỏi viết lại toàn bộ pattern.

Cũng không nên tách cực đoan mọi phép so sánh thành hàm riêng. `total >= 100` vẫn dễ hiểu; chỉ nên tạo hàm hoặc hằng `MINIMUM_TOTAL` nếu ngưỡng này mang ý nghĩa nghiệp vụ, dùng lặp lại hoặc cần đổi theo cấu hình.

## 5. Khi cần thông báo lý do: dùng guard clause

Một expression boolean chỉ trả lời **đúng hoặc sai**. Nếu cần phân biệt *thiếu địa chỉ*, *khách ngừng hoạt động* hoặc *đơn chưa đạt ngưỡng*, việc nhồi thông báo vào biểu thức ba ngôi `?:` lồng nhau khiến code khó kiểm tra.

Có thể dùng chuỗi guard clause:

```java
static String explain(Object input) {
    if (!(input instanceof Order(
            String id,
            Customer(String name, Address(String city), boolean active),
            int total))) {
        return "Thiếu cấu trúc đơn hàng";
    }
    if (!active) {
        return "Khách hàng không hoạt động";
    }
    if (!hasIdentity(id, name)) {
        return "Thiếu mã đơn hoặc tên khách";
    }
    if (total < 100) {
        return "Giá trị đơn thấp";
    }
    if (!isSupportedCity(city)) {
        return "Chưa hỗ trợ thành phố";
    }
    return "Đủ điều kiện";
}
```

Các điều kiện được đặt theo thứ tự mà người đọc có thể theo dõi: **kiểm tra cấu trúc → khách hàng → định danh → số tiền → địa điểm → kết quả**. Mỗi nhánh trả về sớm, nên không cần nhiều tầng `if` lồng nhau.

Lưu ý rằng thứ tự guard clause **quyết định thông báo đầu tiên** khi dữ liệu vi phạm nhiều quy tắc. Nếu muốn thu thập tất cả lỗi cùng lúc thì cần thiết kế khác, ví dụ danh sách kết quả kiểm tra; khi ấy việc thay đổi từ “trả về lỗi đầu tiên” sang “gom nhiều lỗi” là thay đổi hành vi nghiệp vụ, không chỉ là làm đẹp cú pháp.

## 6. Khi có nhiều trường hợp: switch expression với guard gọn

Java 21 cho phép dùng pattern trong `case` và thêm điều kiện `when`:

```java
static String describe(Object input) {
    return switch (input) {
        case Order order when eligibleReadable(order) ->
                "Đủ điều kiện: " + order.id();
        case Order order ->
                "Cần kiểm tra: " + order.id();
        case null ->
                "Không có dữ liệu";
        default ->
                "Không phải đơn hàng";
    };
}
```

Cách viết này giữ `switch` có cấu trúc dễ đọc: **khớp kiểu → gọi điều kiện có tên → trả kết quả**. Guard `when eligibleReadable(order)` chỉ được xét sau khi `case Order order` khớp, nên `order` đã sẵn sàng để truyền vào hàm.

Đặt `case Order order` tổng quát **sau** nhánh có `when`. Nếu đặt trước, nhánh cụ thể ở phía sau có thể bị bao phủ (*dominated case*) và gây lỗi biên dịch.

Với selector có kiểu `Object`, cần xử lý cả các kiểu khác; ở đây `default` giải quyết việc đó. `case null` tách riêng trường hợp selector không có dữ liệu. Nhánh mũi tên `->` không thực hiện *fall-through* sang nhánh kế tiếp.

Một `switch expression` có thể chứa block và `yield`:

```java
String result = switch (input) {
    case Order order when eligibleReadable(order) -> {
        String message = "Đủ điều kiện: " + order.id();
        yield message;
    }
    case Order order -> "Cần kiểm tra: " + order.id();
    case null -> "Không có dữ liệu";
    default -> "Không phải đơn hàng";
};
```

Đây là **đoạn mã minh họa khi biến `input` và các khai báo đã có sẵn**, không cần đưa mọi bước tạo thông báo vào toán tử ba ngôi. Tuy nhiên, nếu block của một nhánh dài hàng chục dòng, có nhiều `try/catch`, cập nhật trạng thái hoặc gọi dịch vụ, nên chuyển logic ấy sang phương thức có tên. Mục tiêu là để `switch` cho thấy **lựa chọn**, còn phương thức riêng thể hiện **cách xử lý**.

## 7. Chương trình Java 21 chạy hoàn chỉnh

Tạo tệp **`ReadablePatternExpressionsDemo.java`**:

```java
public class ReadablePatternExpressionsDemo {
    record Address(String city) {}
    record Customer(String name, Address address, boolean active) {}
    record Order(String id, Customer customer, int total) {}

    static boolean eligibleInline(Object input) {
        return input instanceof Order(
                String id,
                Customer(String name, Address(String city), boolean active),
                int total)
                && active
                && !id.isBlank()
                && !name.isBlank()
                && total >= 100
                && ("Hà Nội".equals(city) || "Đà Nẵng".equals(city));
    }

    static boolean hasIdentity(String id, String name) {
        return id != null && !id.isBlank()
                && name != null && !name.isBlank();
    }

    static boolean isSupportedCity(String city) {
        return "Hà Nội".equals(city) || "Đà Nẵng".equals(city);
    }

    static boolean eligibleReadable(Object input) {
        if (!(input instanceof Order(
                String id,
                Customer(String name, Address(String city), boolean active),
                int total))) {
            return false;
        }

        return active
                && hasIdentity(id, name)
                && total >= 100
                && isSupportedCity(city);
    }

    static String describe(Object input) {
        return switch (input) {
            case Order order when eligibleReadable(order) ->
                    "Đủ điều kiện: " + order.id();
            case Order order ->
                    "Cần kiểm tra: " + order.id();
            case null ->
                    "Không có dữ liệu";
            default ->
                    "Không phải đơn hàng";
        };
    }

    public static void main(String[] args) {
        Object good = new Order("O-1",
                new Customer("Lan", new Address("Hà Nội"), true),
                150);
        Object inactive = new Order("O-2",
                new Customer("Minh", new Address("Đà Nẵng"), false),
                250);
        Object lowTotal = new Order("O-3",
                new Customer("An", new Address("Hà Nội"), true),
                80);
        Object missingAddress = new Order("O-4",
                new Customer("Bình", null, true),
                300);

        System.out.println(eligibleInline(good));
        System.out.println(eligibleReadable(good));
        System.out.println(describe(good));
        System.out.println(describe(inactive));
        System.out.println(describe(lowTotal));
        System.out.println(describe(missingAddress));
        System.out.println(describe("khác"));
        System.out.println(describe(null));
    }
}
```

Dùng **JDK 21 trở lên** và chạy:

```bash
javac ReadablePatternExpressionsDemo.java
java ReadablePatternExpressionsDemo
```

Kết quả dự kiến:

```text
true
true
Đủ điều kiện: O-1
Cần kiểm tra: O-2
Cần kiểm tra: O-3
Cần kiểm tra: O-4
Không phải đơn hàng
Không có dữ liệu
```

Giải thích:

- `good` có cấu trúc đầy đủ, khách đang hoạt động, mã và tên hợp lệ, tổng tiền `150`, thành phố `Hà Nội`. Hai cách viết `eligibleInline` và `eligibleReadable` đều trả về `true`; `describe` chọn nhánh `when`.
- `inactive` có dữ liệu đầy đủ nhưng `active == false` nên không đủ điều kiện. `describe` chọn nhánh `Order` tổng quát.
- `lowTotal` có tổng tiền `80`, dưới ngưỡng `100`, nên không đủ điều kiện.
- `missingAddress` có `address == null`. Mẫu lồng `Address(String city)` không khớp; `eligibleReadable` trả về `false` ngay ở guard đầu tiên. `describe` vẫn nhận được toàn bộ `Order` và in “Cần kiểm tra”.
- Chuỗi `"khác"` đi vào `default`, còn selector `null` đi vào `case null`.

Các phương thức điều kiện trong ví dụ chỉ tính toán và trả về giá trị, không cập nhật dữ liệu bên ngoài. Nhờ vậy, việc so sánh hai phiên bản và kiểm thử trở nên đơn giản.

## 8. Những rủi ro khi nhồi quá nhiều logic vào expression

### 8.1. Khó tìm nguyên nhân một điều kiện false

Một biểu thức dài dùng nhiều `&&` sẽ trả về `false` ngay ở điều kiện sai đầu tiên. Đây là hành vi ngắn mạch đúng của Java, nhưng **nếu cần biết vì sao sai**, một giá trị boolean là không đủ. Hãy dùng guard clause với lý do cụ thể hoặc mô hình kết quả kiểm tra rõ ràng.

### 8.2. Lạm dụng toán tử ba ngôi

Ví dụ khó đọc:

```java
// Đoạn minh họa, giả định các biến đã được khai báo:
String label = active
        ? total >= 100
            ? isSupportedCity(city) ? "Ưu tiên" : "Sai địa điểm"
            : "Giá trị thấp"
        : "Ngừng hoạt động";
```

Biểu thức này có thể hợp lệ nhưng buộc người đọc theo các tầng `?:`. Khi có nhiều lý do và thứ tự ưu tiên nghiệp vụ, một phương thức với các `if` trả về sớm hoặc một `switch` đơn giản thường diễn đạt tốt hơn. Chuyển đổi cú pháp phải bảo toàn thứ tự kiểm tra và kết quả từng trường hợp.

### 8.3. Quên quy tắc phạm vi của biến pattern

Các biến ràng buộc bởi pattern chỉ tồn tại nơi trình biên dịch biết mẫu đã khớp. Không thể mặc nhiên dùng biến ấy ở nhánh `else`, ở vế phải `||`, trong các `case` khác hoặc ngoài phương thức. Khi điều kiện đã phức tạp, hãy tách thành guard đầu tiên như `eligibleReadable` để nhìn rõ vị trí biến trở nên hợp lệ.

### 8.4. Tạo tác dụng phụ trong điều kiện

Tránh nhét vào `&&` hoặc `when` những thao tác như ghi cơ sở dữ liệu, gửi thông báo hoặc cập nhật biến đếm nếu ý nghĩa của tác vụ không phụ thuộc hoàn toàn vào việc điều kiện trước đã đúng. Do ngắn mạch, một số biểu thức có thể **không bao giờ được đánh giá**. Hãy kiểm tra điều kiện trước, rồi thực hiện tác vụ thay đổi trạng thái ở phần xử lý rõ ràng.

### 8.5. Dùng pattern sâu hơn mức cần thiết

Một nested record pattern nhiều tầng chỉ phù hợp nếu phần xử lý thật sự cần các component nằm sâu bên trong. Nếu `switch` chỉ cần phân loại `Order`, `case Order order` kết hợp với một hàm có tên thường dễ đọc hơn một `case Order(String id, Customer(String name, Address(String city), boolean active), int total) when ...` kéo dài trên nhiều dòng.

### 8.6. Nhầm tính dễ đọc với hiệu năng

Tách biểu thức thành nhiều hàm không tự động làm chương trình chậm hơn hay nhanh hơn theo cách đáng kể; trình biên dịch và JVM có nhiều cơ chế tối ưu. Trước hết hãy đảm bảo code **đúng và dễ bảo trì**; nếu hiệu năng thực sự là yêu cầu quan trọng, dùng phép đo phù hợp thay vì suy đoán chỉ dựa vào số dòng.

## 9. Tiêu chí thực hành để quyết định có cần tách expression

| Dấu hiệu | Cách cải thiện |
| --- | --- |
| Một expression vừa kiểm tra kiểu, vừa xử lý nhiều quy tắc nghiệp vụ | Giữ pattern cho cấu trúc; tách quy tắc thành hàm có tên. |
| Nhiều tầng `?:` với các thông báo khác nhau | Dùng guard clause hoặc `switch` có nhánh dễ nhận diện. |
| Một `case ... when ...` quá dài và lặp lại ở nhiều nhánh | Đưa điều kiện thuần túy vào phương thức `isEligible(...)` hoặc tên tương ứng. |
| Dễ nhầm phạm vi biến trong `&&` và `||` | Đưa pattern vào guard đầu tiên; dùng biến ở đoạn đã chứng minh khớp. |
| Cần phân biệt nhiều lý do bị từ chối | Trả về kết quả có lý do, thay vì một boolean duy nhất. |
| Pattern lồng rất sâu trong khi chỉ cần cả record | Dùng type pattern để giữ biến record và gọi hàm xử lý riêng. |
| Điều kiện chứa tác dụng phụ, phụ thuộc thứ tự đánh giá | Tách kiểm tra khỏi hành động và làm thứ tự thực thi tường minh. |

Không có quy tắc “trên ba điều kiện là sai” hay “cứ thấy pattern lồng phải tách”. Hãy chọn cách viết cho phép người khác đọc từ trên xuống và giải thích được **mỗi nhánh chạy khi nào**, **vì sao giá trị phù hợp**, và **điều gì xảy ra khi không khớp**.

## 10. Tự kiểm tra

Giả sử có:

```java
record Score(String subject, int points) {}
Object input = new Score("Java", 85);
```

Một expression gọn, có cấu trúc rõ ràng vẫn rất phù hợp:

```java
boolean passed = input instanceof Score(String subject, int points)
        && "Java".equals(subject)
        && points >= 80;
System.out.println(passed);
```

Kết quả là `true`. Nếu chuyển sang ứng dụng có các ngưỡng khác nhau theo môn, cần kiểm tra học viên có được dự thi hay không và cần báo lý do không đạt, ta nên tách điều kiện nghiệp vụ ra hàm hoặc các guard clause. Việc đó giúp mỗi thay đổi có chỗ rõ ràng và không biến một expression thành nơi chứa mọi quy tắc.

**Ghi nhớ:** Pattern matching giúp biểu thức Java ngắn và chính xác hơn khi kiểm tra kiểu/cấu trúc. Hãy giữ expression **đủ đơn giản để đọc được điều kiện khớp, phạm vi biến và kết quả**. Khi xuất hiện quá nhiều điều kiện nghiệp vụ, thông báo, tác dụng phụ hoặc nhánh lồng nhau, hãy chuyển sang các phương thức có tên, guard clause hay `switch` có guard ngắn; giữ đúng thứ tự đánh giá và bảo toàn hành vi khi refactor.
