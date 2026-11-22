# Giới hạn tác dụng của việc chia nhỏ theo số dòng

Trong chương **Độ phức tạp** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu một quan niệm dễ gây nhầm lẫn khi cải thiện mã nguồn: **chỉ cần chia một phương thức dài thành nhiều phương thức ngắn thì mã sẽ đơn giản hơn**.

Việc chia nhỏ thường có ích, nhưng **số dòng là dấu hiệu để xem xét chứ không phải thước đo đầy đủ của độ phức tạp**. Một phương thức 60 dòng với ba bước nghiệp vụ rõ ràng có thể dễ hiểu hơn một chuỗi 12 phương thức, mỗi phương thức năm dòng, mà người đọc phải lần theo để tìm điều kiện thực sự quyết định kết quả. Ngược lại, một phương thức 12 dòng chứa biểu thức lồng nhau, trạng thái ngầm và tác dụng phụ khó đoán có thể rất khó bảo trì.

Mục tiêu của **CODE_QUALITY_FUNDAMENTALS** là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Vì vậy, câu hỏi nên đặt ra khi chia nhỏ mã là:

> **Sau khi chia nhỏ, người bảo trì có hiểu hành vi, tìm đúng nơi sửa và kiểm chứng kết quả dễ hơn không?**

Nếu câu trả lời chỉ là “mỗi phương thức đã ngắn hơn”, cải thiện có thể mới dừng ở hình thức.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **độ dài mã**, **độ phức tạp luồng điều khiển**, **độ phức tạp nhận thức** và **độ phức tạp của sự phối hợp giữa thành phần**.
2. Giải thích vì sao tách phương thức theo số dòng có thể chuyển độ phức tạp từ một vị trí sang nhiều vị trí mà không làm nó biến mất.
3. Nhận diện dấu hiệu chia nhỏ có ích: trách nhiệm rõ ràng, tên có ý nghĩa, giao diện nhỏ, giảm trạng thái ngầm và có ranh giới kiểm thử hợp lý.
4. Nhận diện việc chia nhỏ quá mức: chuỗi helper trung gian, truyền nhiều tham số, phụ thuộc thứ tự gọi và phải nhảy qua nhiều file để hiểu một quy tắc.
5. Giữ đúng hành vi khi refactor, bao gồm thứ tự đánh giá điều kiện, ngoại lệ, làm tròn số, giao dịch và tác dụng phụ.
6. Đánh giá refactor qua chi phí đọc, sửa, kiểm thử và review thay vì chỉ dựa vào chỉ số số dòng.

## 2. Vì sao số dòng không đủ để đo độ phức tạp?

Độ dài là số lượng mã được biểu diễn trong một phạm vi: dòng, câu lệnh hoặc token. Nó dễ đo, hữu ích để **gợi ý những đoạn cần xem xét**, nhưng bản thân nó không cho biết logic khó đến mức nào.

So sánh hai ví dụ Java:

~~~java
int maxOfThree(int a, int b, int c) {
    int max = a;
    if (b > max) {
        max = b;
    }
    if (c > max) {
        max = c;
    }
    return max;
}
~~~

~~~java
int result(int a, int b, int c) {
    return a > b ? (a > c ? a : c) : (b > c ? b : c);
}
~~~

Ví dụ thứ hai ngắn hơn theo số dòng, nhưng phải giải mã các nhánh của toán tử ba ngôi lồng nhau. Hai phiên bản cùng chọn giá trị lớn nhất trong ba số, với hành vi như nhau đối với cả trường hợp bằng nhau, nhưng phiên bản đầu thường giúp người mới theo dõi điều kiện dễ hơn.

Một phương thức dài cũng có thể chủ yếu chứa **khai báo dữ liệu có cấu trúc** hoặc các bước xử lý tuyến tính. Ngược lại, một phương thức rất ngắn có thể gọi đến nhiều tác vụ bên ngoài, tạo luồng bất đồng bộ hoặc thực hiện một điều kiện nghiệp vụ khó đoán.

### 2.1. Bốn khía cạnh cần phân biệt

| Khía cạnh | Câu hỏi đánh giá | Điều số dòng không thể hiện đầy đủ |
| --- | --- | --- |
| **Độ dài mã (size)** | Mất bao nhiêu dòng để diễn đạt đoạn mã? | Mục đích, độ khó của từng dòng, mức độ liên kết. |
| **Độ phức tạp luồng điều khiển** | Có bao nhiêu điều kiện, nhánh, vòng lặp và đường đi cần xét? | Khi tách nhánh sang helper, số nhánh nghiệp vụ tổng thể có thể vẫn giữ nguyên. |
| **Độ phức tạp nhận thức** | Người đọc cần giữ bao nhiêu điều kiện, trạng thái và quan hệ trong đầu? | Một phương thức ngắn nhưng toàn tên mơ hồ có thể rất khó hiểu. |
| **Độ phức tạp liên kết** | Cần hiểu bao nhiêu phương thức, lớp, hợp đồng và thứ tự gọi để giải thích hành vi? | Sau khi tách nhiều helper, chi phí điều hướng có thể tăng. |

Độ phức tạp còn có thể là **thuật toán** (thời gian, bộ nhớ theo kích thước đầu vào) hoặc **vận hành** (retry, transaction, phân tán, lỗi mạng). Chia nhỏ file không tự động cải thiện các khía cạnh đó.

### 2.2. Một mô hình suy nghĩ về chi phí hiểu mã

Để giải thích hành vi của một chức năng, người đọc thường cần:

~~~text
Tìm điểm bắt đầu
      ↓
Hiểu điều kiện và thứ tự xử lý
      ↓
Theo các lời gọi quan trọng
      ↓
Kết nối dữ liệu, trạng thái và tác dụng phụ
      ↓
Xác định kết quả và trường hợp lỗi
~~~

Một lần trích xuất phương thức có thể giảm công sức ở bước “hiểu điều kiện tại chỗ”, nhưng lại tăng công sức ở bước “theo lời gọi” nếu tên không đủ thông tin.

Có thể hình dung **chi phí hiểu ≈ chi phí đọc logic cục bộ + chi phí theo quan hệ giữa các phần + chi phí tìm và nhớ ngữ cảnh**. Đây là cách phân tích định tính, **không phải công thức chấm điểm chính xác**; các thành phần có thể tác động lẫn nhau.

## 3. Chia nhỏ thực sự giúp ích khi nào?

Một phép trích xuất tốt đặt một **khái niệm có thể gọi tên** vào một ranh giới hợp lý. Ở nơi gọi, tên giúp hiểu ý định; khi cần sửa chi tiết, người đọc biết mở đúng nơi.

### 3.1. Tách theo trách nhiệm, không theo độ dài

Giả sử xử lý báo giá gồm ba quyết định:

1. Kiểm tra dữ liệu đơn hàng.
2. Áp dụng chính sách chiết khấu.
3. Tính phí vận chuyển và tổng tiền.

Nếu chính sách chiết khấu do một nhóm bảo trì và phí vận chuyển do nhóm khác bảo trì, việc tách hai chính sách có cơ sở rõ ràng: **chúng thay đổi vì các lý do khác nhau**.

Nếu cả chức năng chỉ là một phép so sánh hai số và không có dấu hiệu phát sinh biến thể, việc tạo interface, factory và ba lớp helper có thể khiến nó khó hiểu hơn.

### 3.2. Tên phải thay thế được một phần công sức đọc

Các tên như `calculateMembershipDiscount`, `validatePaymentRequest`, `isEligibleForRefund` truyền tải ý nghĩa nghiệp vụ. Các tên `processStep1`, `handleData`, `doCalculation` hoặc `helper2` chỉ yêu cầu người đọc mở phần triển khai mới biết mục đích.

Một phép kiểm tra hữu ích:

> “Chỉ đọc tên phương thức ở nơi gọi, tôi có hiểu **vì sao** bước này tồn tại không?”

Nếu không, trích xuất có thể tạo thêm một tầng che giấu thông tin.

### 3.3. Ranh giới cần hợp đồng đơn giản

Một helper tốt thường nhận những dữ liệu nó cần, trả một kết quả dễ giải thích và có ít phụ thuộc ẩn. Nếu muốn gọi một helper phải biết trước ba biến của object đã được gán ở những bước nào, phương thức đó chưa thực sự độc lập.

Các lợi ích có thể kiểm chứng được gồm:

- Có thể kiểm thử một quy tắc độc lập bằng đầu vào rõ ràng.
- Khi chính sách thay đổi, nơi sửa và phạm vi tác động dễ xác định.
- Luồng chính ngắn gọn ở mức khái niệm, không làm mất các bước quan trọng.
- Mã trùng lặp có cùng ý nghĩa được gom về một nguồn chịu trách nhiệm.
- Người review có thể kiểm tra hợp đồng ở ranh giới thay vì đọc lặp một khối chi tiết ở nhiều nơi.

Không phải mọi trích xuất đều cần đạt tất cả các lợi ích; điều quan trọng là **có lý do thực tế đủ bù cho chi phí thêm một lời gọi và một ranh giới**.

## 4. Chia nhỏ máy móc có thể làm khó hiểu hơn

### 4.1. Tách theo số dòng tạo những tên không có ý nghĩa

Ví dụ trước:

~~~java
int calculateFee(int subtotalCents) {
    if (subtotalCents < 0) {
        throw new IllegalArgumentException("Negative subtotal");
    }
    if (subtotalCents >= 500_000) {
        return 0;
    }
    return 30_000;
}
~~~

Nếu mục tiêu là “mỗi phương thức tối đa ba dòng”, ta có thể nhận được phiên bản sau:

~~~java
int calculateFee(int subtotalCents) {
    check1(subtotalCents);
    return check2(subtotalCents) ? 0 : value1();
}

void check1(int amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("Negative subtotal");
    }
}

boolean check2(int amount) {
    return amount >= 500_000;
}

int value1() {
    return 30_000;
}
~~~

Phiên bản sau có nhiều phương thức ngắn, nhưng người đọc phải mở `check1`, `check2` và `value1` để hiểu ba điều vốn được thấy ngay trong một hàm. Không có trách nhiệm mới, biến thể mới hay khả năng tái sử dụng có ý nghĩa. **Độ phức tạp được di chuyển thành chi phí điều hướng và đặt tên.**

Với một quy tắc nhỏ, rõ và chỉ dùng tại chỗ, **giữ nguyên phương thức đầu** có thể là lựa chọn tốt.

### 4.2. Chuỗi chuyển tiếp không thêm thông tin

~~~java
void handle(Request request) {
    process(request);
}

void process(Request request) {
    execute(request);
}

void execute(Request request) {
    send(request);
}
~~~

Nếu các phương thức chỉ chuyển tiếp tham số mà không thiết lập hợp đồng, phân quyền, giao dịch hay hành vi rõ ràng, người đọc phải nhảy qua nhiều điểm trung gian mới tìm được lời gọi có tác dụng.

Có trường hợp một wrapper mỏng vẫn có ích: nó là ranh giới API ổn định, adapter chuyển đổi kiểu dữ liệu hoặc điểm kiểm soát lỗi/quyền truy cập. Nhưng wrapper ấy nên **thể hiện trách nhiệm có thể giải thích**, không chỉ tồn tại để cắt số dòng.

### 4.3. Trạng thái ngầm làm helper phụ thuộc vào thứ tự

~~~java
class QuoteBuilder {
    private long subtotal;
    private long discount;

    void loadSubtotal(Order order) {
        subtotal = order.subtotalCents();
    }

    void applyDiscount() {
        discount = subtotal / 10;
    }

    long total() {
        return subtotal - discount;
    }
}
~~~

Các phương thức đều ngắn, nhưng `applyDiscount` chỉ đúng khi `loadSubtotal` đã chạy; `total` phụ thuộc vào trạng thái từ các bước trước. Nếu một object được dùng lại, có thể xuất hiện tình huống dùng dữ liệu của lần gọi cũ.

Trong trường hợp này, một hàm nhận tham số và trả kết quả rõ ràng thường dễ kiểm thử và khó dùng sai hơn:

~~~java
static long discountedTotal(long subtotalCents) {
    if (subtotalCents < 0) {
        throw new IllegalArgumentException("Negative subtotal");
    }
    return subtotalCents - subtotalCents / 10;
}
~~~

Việc bỏ trạng thái ngầm có thể làm tăng khả năng suy luận hơn nhiều so với giảm vài dòng.

### 4.4. Truyền quá nhiều tham số và kết quả trung gian

Nếu tách một đoạn của phương thức dài thành helper cần 10 tham số và trả về object có 8 trường để “đưa biến ra ngoài”, có thể ta đang **cắt ngang một khối logic vốn gắn kết**. Trước khi thêm object trung gian, nên kiểm tra xem:

- Helper có một khái niệm nghiệp vụ riêng không?
- Những tham số đó có tự nhiên thuộc cùng một kiểu dữ liệu không?
- Có trạng thái nào nên được tính trực tiếp ở nơi sử dụng không?
- Có đang truyền dữ liệu chỉ vì buộc một đoạn mã phải dưới ngưỡng số dòng không?

Một kiểu dữ liệu mới có thể tốt khi biểu diễn một khái niệm thực sự, chẳng hạn `ShippingPolicy`; nó ít hữu ích nếu chỉ là `MethodParameters1` chứa đủ mọi biến cục bộ từ phương thức cũ.

## 5. Ví dụ Java: cùng một nghiệp vụ, ba cách tổ chức

Giả sử ứng dụng báo giá đơn hàng với chính sách đơn giản:

- Tổng tiền hàng (`subtotalCents`) phải không âm.
- Khách hàng **premium** có đơn từ 200.000 đơn vị tiền nhỏ nhất trở lên được giảm **10% tiền hàng**, làm tròn xuống theo đơn vị nhỏ nhất.
- Đơn có tổng tiền hàng từ 500.000 trở lên được miễn phí vận chuyển; nếu thấp hơn, phí là 30.000.
- Ngưỡng vận chuyển dựa trên **tiền hàng trước chiết khấu**.
- Tổng thanh toán bằng tiền hàng trừ giảm giá cộng phí vận chuyển.
- Với đơn có dữ liệu đầu vào sai, hàm báo lỗi.

Để tập trung vào độ phức tạp cấu trúc, ví dụ dùng Java 17+ với `record` và `long`. Đơn vị tiền nhỏ nhất được dùng để tránh số thực dấu phẩy động trong phép tính tiền. Phạm vi ví dụ chưa xử lý thuế, nhiều loại tiền tệ, thay đổi chính sách theo thời gian hay giao dịch thanh toán.

Các kiểu dữ liệu:

~~~java
record Customer(boolean premium) {}
record Order(long subtotalCents, Customer customer) {}
record Quote(long discountCents, long shippingCents, long totalCents) {}
~~~

### 5.1. Phương án A: một phương thức ngắn, gắn kết và dễ theo dõi

~~~java
import java.util.Objects;

final class QuoteService {
    static Quote quote(Order order) {
        Objects.requireNonNull(order, "order");
        Objects.requireNonNull(order.customer(), "customer");

        long subtotal = order.subtotalCents();
        if (subtotal < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        long discount = order.customer().premium() && subtotal >= 200_000
                ? subtotal / 10
                : 0;
        long shipping = subtotal >= 500_000 ? 0 : 30_000;
        long total = Math.addExact(
                Math.subtractExact(subtotal, discount), shipping);

        return new Quote(discount, shipping, total);
    }
}
~~~

Hành vi có thể được giải thích theo trình tự: xác thực → tính giảm giá → tính phí vận chuyển → tính tổng → trả báo giá. Những phép tính liên quan cùng nằm trong một vùng ngắn và không có trạng thái lưu ở object.

**Điểm mạnh:** ít điểm điều hướng, thấy toàn bộ phép tính, dễ kiểm thử như một hàm thuần túy. **Giới hạn:** nếu quy tắc giảm giá hoặc vận chuyển thường xuyên có nhiều biến thể, một phương thức sẽ phải sửa mỗi khi biến thể mới xuất hiện.

Ở giai đoạn chính sách đơn giản, **chưa có lý do chắc chắn để buộc tách thêm phương thức**.

### 5.2. Phương án B: tách để đạt chỉ tiêu số dòng

~~~java
final class SplitByLineCount {
    static Quote quote(Order order) {
        validate(order);
        long subtotal = order.subtotalCents();
        long d = part1(order, subtotal);
        long s = part2(subtotal);
        return part3(subtotal, d, s);
    }

    private static void validate(Order order) {
        java.util.Objects.requireNonNull(order, "order");
        java.util.Objects.requireNonNull(order.customer(), "customer");
        if (order.subtotalCents() < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
    }

    private static long part1(Order order, long subtotal) {
        return order.customer().premium() && subtotal >= 200_000
                ? subtotal / 10 : 0;
    }

    private static long part2(long subtotal) {
        return subtotal >= 500_000 ? 0 : 30_000;
    }

    private static Quote part3(long subtotal, long d, long s) {
        long total = Math.addExact(Math.subtractExact(subtotal, d), s);
        return new Quote(d, s, total);
    }
}
~~~

Các phép tính giữ cùng kết quả với phương án A cho dữ liệu hợp lệ, nhưng cách gọi `part1`, `part2`, `part3` buộc người đọc xem từng triển khai. Các tham số `d` và `s` cũng che ý nghĩa nghiệp vụ. Việc chia nhỏ không loại bỏ bất kỳ điều kiện hoặc công thức nào.

Kể cả một công cụ báo số dòng trên mỗi phương thức thấp hơn, **tổng chi phí hiểu và thay đổi có thể tăng**.

### 5.3. Phương án C: tách theo quy tắc có lý do thay đổi riêng

Nếu sau một thời gian, chiết khấu và vận chuyển thực sự được bảo trì theo các chính sách riêng, có thể viết:

~~~java
import java.util.Objects;

final class QuoteServiceByPolicy {
    static Quote quote(Order order) {
        Objects.requireNonNull(order, "order");
        Objects.requireNonNull(order.customer(), "customer");

        long subtotal = order.subtotalCents();
        if (subtotal < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        long discount = membershipDiscount(order.customer(), subtotal);
        long shipping = shippingFee(subtotal);
        long total = Math.addExact(
                Math.subtractExact(subtotal, discount), shipping);

        return new Quote(discount, shipping, total);
    }

    private static long membershipDiscount(Customer customer, long subtotal) {
        return customer.premium() && subtotal >= 200_000
                ? subtotal / 10
                : 0;
    }

    private static long shippingFee(long subtotal) {
        return subtotal >= 500_000 ? 0 : 30_000;
    }
}
~~~

Điều khác biệt không nằm ở số dòng, mà ở hai tên `membershipDiscount` và `shippingFee` mô tả **hai trách nhiệm có thể thay đổi độc lập**. Ở nơi gọi, người đọc có thể hiểu trình tự tính tiền. Khi sửa chính sách giảm giá, họ biết đi đâu và có thể tập trung vào các ca biên của chính sách ấy.

Tuy vậy, nếu các quy tắc vẫn chỉ là một phép so sánh và không có thay đổi độc lập thực tế, phương án A **vẫn có thể dễ đọc hơn**. Một phép trích xuất “đẹp” không tự động trở thành bắt buộc.

### 5.4. So sánh ba phương án

| Tiêu chí | A: giữ chung mạch lạc | B: cắt theo số dòng | C: tách theo trách nhiệm |
| --- | --- | --- | --- |
| Đọc toàn bộ phép tính | Trực tiếp tại một nơi. | Phải mở ba helper tên mơ hồ. | Đọc luồng tại một nơi, mở quy tắc khi cần. |
| Trách nhiệm nghiệp vụ | Thấy trong một phương thức. | Bị chia thành các phần không tên rõ nghĩa. | Đặt tên rõ chiết khấu và vận chuyển. |
| Chi phí thêm ranh giới | Rất ít. | Cao hơn, không có ích rõ ràng. | Có chi phí, có thể đáng khi chính sách biến động. |
| Thay đổi ngưỡng phí | Sửa tại phương thức báo giá. | Sửa `part2` nhưng cần nhớ `part2` là gì. | Sửa `shippingFee`. |
| Bảo đảm tính đúng | Phụ thuộc test, hợp đồng và review. | Không tăng chỉ vì có thêm helper. | Cũng cần test, hợp đồng và review. |

Ba phương án thể hiện **một quyết định theo bối cảnh**. Không có công thức “phương thức tối đa N dòng” có thể chọn đáp án đúng thay cho hiểu biết về nghiệp vụ và đội ngũ.

## 6. Bảo toàn hành vi quan trọng hơn giảm số dòng

Chia nhỏ thường được thực hiện trong một đợt **refactor**: cải thiện cấu trúc trong khi giữ nguyên hành vi quan sát được. Việc di chuyển câu lệnh sang helper có thể gây thay đổi hành vi nếu không xem kỹ.

### 6.1. Thứ tự kiểm tra và ngoại lệ

~~~java
if (order == null) {
    throw new IllegalArgumentException("Missing order");
}
if (order.customer() == null) {
    throw new IllegalArgumentException("Missing customer");
}
~~~

Không thể tự ý gộp hoặc đảo thứ tự nếu người gọi dựa vào loại ngoại lệ và thông điệp lỗi cụ thể. Biểu thức `order.customer()` sẽ ném `NullPointerException` nếu `order` đang `null`. Ngay cả khi chỉ đổi thông điệp lỗi, một số test hoặc API contract cũng có thể bị ảnh hưởng.

Trong ví dụ A–C, lời gọi `Objects.requireNonNull` cùng thứ tự giúp các phiên bản có cùng quy ước lỗi đầu vào. Trong codebase thực, cần xác nhận **hợp đồng đang tồn tại**, không tự chọn loại ngoại lệ khác trong khi refactor.

### 6.2. Tác dụng phụ và thời điểm thực thi

~~~java
if (hasPermission(user) && reserveInventory(order)) {
    confirmOrder(order);
}
~~~

`hasPermission` và `reserveInventory` có thể liên quan trạng thái bên ngoài. Việc đảo thứ tự hai lời gọi hoặc gọi `reserveInventory` trước khi kiểm tra quyền có thể tạo tác dụng phụ không mong muốn. Java đánh giá `&&` từ trái sang phải và ngắn mạch; tách thành helper mà thay đổi thứ tự sẽ đổi hành vi.

Khi refactor, cần xem xét:

- Lời gọi nào có thể ghi dữ liệu, phát sự kiện, gọi API hoặc tạo log?
- Điều kiện nào phải được kiểm tra trước tác dụng phụ?
- Ngoại lệ phát sinh ở đâu và có được xử lý tương đương không?
- Trạng thái có thể thay đổi giữa các lần gọi không?
- Các bước có thuộc cùng transaction hoặc ranh giới đồng bộ không?

### 6.3. Số học, làm tròn và tràn số

Trong ví dụ báo giá, cách tính `subtotal / 10` làm tròn xuống đến đơn vị tiền nhỏ nhất theo chính sách minh họa. Việc thay thành `Math.round(subtotal * 0.1)` có thể tạo kết quả khác do cách làm tròn và sử dụng số thực, dù phương thức mới ngắn hơn.

Tương tự, đổi `Math.addExact` thành `+` có thể thay hành vi khi `long` tràn số. **Trích xuất phương thức không phải cơ hội tự ý đổi thuật toán** nếu phạm vi nhiệm vụ là giữ nguyên hành vi.

### 6.4. Tài nguyên và giao dịch

Với cơ sở dữ liệu, một khối mã dài có thể nằm trong phạm vi transaction. Nếu tách các thao tác vào những service độc lập nhưng mỗi service tự mở transaction khác nhau, tính nguyên tử có thể thay đổi. Khi một bước thành công và bước sau thất bại, dữ liệu có thể rơi vào trạng thái mà phiên bản cũ không cho phép.

Với tài nguyên như stream hoặc kết nối, việc đặt `return` sớm trong helper phải được xem xét cùng cơ chế dọn dẹp như `try-with-resources`.

**Bài học:** ranh giới mã nguồn mới không nhất thiết trùng với **ranh giới giao dịch, đồng bộ và vòng đời tài nguyên**. Những ranh giới thực thi đó phải được duy trì rõ.

## 7. Kiểm thử để đánh giá refactor, không chỉ đếm phương thức

Một bộ kiểm thử cho ví dụ báo giá có thể bảo vệ các điều kiện và giá trị biên. Các đoạn test dưới đây dùng JUnit 5, giả định `Customer`, `Order`, `Quote` và `QuoteServiceByPolicy` được khai báo như mục 5 trong source set phù hợp.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class QuoteServiceByPolicyTest {
    @Test
    void premiumCustomerGetsDiscountAtMinimum() {
        Quote quote = QuoteServiceByPolicy.quote(
                new Order(200_000, new Customer(true)));

        assertEquals(20_000, quote.discountCents());
        assertEquals(30_000, quote.shippingCents());
        assertEquals(210_000, quote.totalCents());
    }

    @Test
    void premiumCustomerBelowDiscountThresholdHasNoDiscount() {
        Quote quote = QuoteServiceByPolicy.quote(
                new Order(199_999, new Customer(true)));

        assertEquals(0, quote.discountCents());
        assertEquals(30_000, quote.shippingCents());
        assertEquals(229_999, quote.totalCents());
    }

    @Test
    void shippingUsesSubtotalBeforeDiscount() {
        Quote quote = QuoteServiceByPolicy.quote(
                new Order(500_000, new Customer(true)));

        assertEquals(50_000, quote.discountCents());
        assertEquals(0, quote.shippingCents());
        assertEquals(450_000, quote.totalCents());
    }

    @Test
    void regularCustomerDoesNotGetDiscount() {
        Quote quote = QuoteServiceByPolicy.quote(
                new Order(500_000, new Customer(false)));

        assertEquals(0, quote.discountCents());
        assertEquals(500_000, quote.totalCents());
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> QuoteServiceByPolicy.quote(
                        new Order(-1, new Customer(true))));
    }

    @Test
    void rejectsMissingCustomer() {
        assertThrows(NullPointerException.class,
                () -> QuoteServiceByPolicy.quote(new Order(100_000, null)));
    }
}
~~~

Các test kiểm tra **hợp đồng quan sát được** qua kết quả và ngoại lệ. Chúng không phụ thuộc vào việc chính sách nằm trong một hay ba phương thức private. Nhờ đó, người bảo trì có thể thay đổi cấu trúc mà vẫn có bằng chứng cho hành vi quan trọng.

Với một refactor giữ hành vi, có thể chạy cùng tập trường hợp trên **phiên bản trước và sau**; so sánh kết quả, ngoại lệ và tác dụng phụ. Nếu một phiên bản có hành vi đã được người dùng dựa vào, mọi thay đổi ngoài chủ đích cần được xác định trước khi nhận refactor.

Coverage hoặc số test tăng không tự động chứng minh refactor an toàn. Phải xem test có đúng oracle, có chạm giá trị biên và có bao phủ phần dễ bị đổi hành vi hay không.

## 8. Chia nhỏ không tự giảm độ phức tạp thuật toán

Xét yêu cầu tìm xem có mã sản phẩm nào thuộc danh sách chặn. Cách thực hiện đơn giản:

~~~java
static boolean hasBlockedProduct(
        java.util.List<String> productCodes,
        java.util.List<String> blockedCodes) {
    for (String code : productCodes) {
        if (blockedCodes.contains(code)) {
            return true;
        }
    }
    return false;
}
~~~

Với `n` mã sản phẩm và `m` mã bị chặn, nếu `blockedCodes` là danh sách thường, phương thức `contains` có thể quét tối đa `m` phần tử, nên thời gian trường hợp xấu nhất là **O(n × m)**. Việc tách phép kiểm tra sang helper:

~~~java
static boolean isBlocked(
        String code, java.util.List<String> blockedCodes) {
    return blockedCodes.contains(code);
}
~~~

không thay đổi bản chất thuật toán; vòng lặp ngoài vẫn có thể gọi thao tác quét tuyến tính nhiều lần.

Nếu yêu cầu và dữ liệu phù hợp, có thể dùng tập hợp:

~~~java
static boolean hasBlockedProduct(
        java.util.List<String> productCodes,
        java.util.List<String> blockedCodes) {
    java.util.Set<String> blocked = new java.util.HashSet<>(blockedCodes);
    for (String code : productCodes) {
        if (blocked.contains(code)) {
            return true;
        }
    }
    return false;
}
~~~

Trong điều kiện băm phân bố phù hợp, việc tạo `HashSet` mất thời gian trung bình O(m) và tra cứu trung bình gần O(1) mỗi mã, dẫn đến **O(n + m) trung bình**, đổi lại bộ nhớ bổ sung O(m). Đây là một **thay đổi thuật toán và cấu trúc dữ liệu**, không đơn thuần chia dòng. Chi phí dựng tập có thể không đáng nếu danh sách rất nhỏ hoặc hàm hiếm gọi.

Độ phức tạp theo Big O không đánh giá hết khả năng đọc, nhưng ví dụ cho thấy phải giải quyết **đúng nguồn phức tạp**: tách phương thức có thể cải thiện tổ chức mã, còn thay thuật toán mới tác động đến số phép tính khi dữ liệu lớn.

## 9. Đọc các chỉ số chất lượng theo ngữ cảnh

### 9.1. Lines of Code (LOC)

LOC có thể giúp tìm phương thức quá dài để review, theo dõi xu hướng kích thước module hoặc nhận ra một thành phần đang gánh nhiều trách nhiệm.

Nhưng LOC chịu ảnh hưởng của định dạng, comment, dòng trống, biểu thức nhiều dòng và phong cách viết. Vì vậy không nên kết luận “A tốt hơn B” chỉ vì A có 20 dòng, B có 40 dòng.

### 9.2. Cyclomatic complexity

Độ phức tạp chu trình (cyclomatic complexity) phản ánh số đường đi độc lập trong đồ thị điều khiển ở một phạm vi được phân tích. Số nhánh điều kiện thường làm chỉ số tăng; giá trị chính xác phụ thuộc mô hình và công cụ.

Khi chuyển những nhánh điều kiện sang helper, chỉ số **của phương thức gọi** có thể giảm, trong khi các quyết định nghiệp vụ vẫn tồn tại ở các helper. Không thể chỉ nhìn một giá trị ở phương thức cấp cao rồi khẳng định **toàn bộ hành vi đã bớt phức tạp**.

### 9.3. Cognitive complexity

Các công cụ đo cognitive complexity cố gắng phản ánh một số yếu tố gây khó cho việc hiểu luồng điều khiển, như lồng nhau và chuyển hướng. Chúng hữu ích để nhận diện đoạn mã cần xem kỹ.

Tuy nhiên, công cụ không biết đầy đủ ý nghĩa nghiệp vụ, kiến thức nhóm hoặc chi phí mở nhiều file. Việc tách phương thức có thể làm điểm của từng phương thức thấp hơn nhưng khiến người đọc phải theo một đồ thị lời gọi sâu hơn.

### 9.4. Coupling, cohesion và phạm vi tác động

Một module **cohesion** tốt tập trung vào một trách nhiệm có liên hệ; **coupling** giữa các module là mức độ chúng phụ thuộc lẫn nhau. Tách nhiều class chỉ để mỗi class ít dòng có thể làm coupling tăng mà không làm trách nhiệm rõ hơn.

Một câu hỏi thực dụng: khi quy tắc A đổi, ta phải sửa bao nhiêu nơi và bao nhiêu phần khác có nguy cơ bị tác động? Nếu “một chỉnh sửa nhỏ” bắt buộc chạm bốn helper, hai DTO trung gian và một factory, cấu trúc đã tạo chi phí phối hợp đáng cân nhắc.

### 9.5. Đặt các chỉ số vào cùng một bức tranh

| Tín hiệu | Có ích để hỏi gì? | Không nên suy ra gì? |
| --- | --- | --- |
| Phương thức nhiều dòng | Có đang trộn nhiều trách nhiệm hoặc nhiều nhánh không? | Cứ cắt thành hàm ngắn là tốt. |
| Cyclomatic complexity cao | Có cần kiểm tra thêm nhánh và đường đi lỗi không? | Tách nhánh sang helper sẽ xóa rủi ro logic. |
| Cognitive complexity cao | Có điều kiện lồng sâu hoặc luồng khó theo dõi không? | Điểm thấp là người đọc chắc chắn hiểu nhanh. |
| Quá nhiều helper nhỏ | Có thể đang thiếu khái niệm bao trùm hoặc có wrapper thừa không? | Mọi helper nhỏ đều xấu. |
| Nhiều lớp phải sửa cùng một yêu cầu | Ranh giới trách nhiệm có phù hợp chiều thay đổi không? | Chỉ cần gom tất cả vào một file. |
| Test hồi quy hay hỏng sau refactor | Có phụ thuộc vào chi tiết triển khai hoặc hành vi đã đổi không? | Cần loại bỏ các test đang báo lỗi. |

Các thước đo nên **mở đầu một cuộc điều tra về chất lượng**, không tự thay thế quyết định của người review.

## 10. Khi nào nên giữ mã cùng nhau?

Có những trường hợp việc đọc một khối mã liền mạch có giá trị hơn tách nó thành nhiều phương thức:

- **Thuật toán nhỏ có các bước phụ thuộc trực tiếp:** để hiểu bước ba cần thấy biến được tính ở bước một và hai; tách đi có thể làm tăng số tham số và luồng dữ liệu.
- **Một phép biến đổi dữ liệu tuyến tính:** các bước tuần tự, đơn giản và ít trạng thái, có thể đọc tốt ở cùng một nơi.
- **Logic nằm trong một phạm vi tài nguyên hoặc transaction rõ:** người đọc cần nhìn thấy thứ tự thao tác và điểm bảo đảm dọn dẹp.
- **Quy tắc nhỏ chỉ dùng một lần:** trích xuất có thể không thêm tên ý nghĩa hay khả năng kiểm thử riêng.
- **Các điều kiện phải được xem đồng thời:** khi tách khiến người đọc không còn nhìn thấy mối tương quan quan trọng.

Giữ chung không có nghĩa chấp nhận phương thức tùy ý dài. Nếu một khối bắt đầu có nhiều lý do thay đổi, các nhánh khó theo dõi hoặc dữ liệu không liên quan, cần cân nhắc tách theo trách nhiệm.

### 10.1. “Nhiều dòng” đôi khi là một dạng minh bạch

Một bảng ánh xạ tường minh có thể dài nhưng dễ kiểm tra hơn thuật toán rút gọn nhiều nhánh khó đoán. Chẳng hạn, nếu nghiệp vụ có một tập mã trạng thái hữu hạn và quy tắc ánh xạ khác nhau, một `switch` rõ ràng và được kiểm thử có thể giúp reviewer đối chiếu từng trường hợp tốt hơn một hệ thống reflection hoặc cấu hình động phức tạp.

Không nên thay một cấu trúc dễ đối chiếu với giải pháp khó theo dõi chỉ để giảm số dòng hiển thị.

## 11. Khi nào nên tách phương thức, lớp hoặc module?

Việc tách nên phản ánh **ranh giới trách nhiệm và thay đổi**. Có thể bắt đầu với ba câu hỏi:

1. **Đoạn mã này làm một việc có thể gọi tên riêng không?** Nếu có, tách phương thức có thể làm rõ ý định.
2. **Nó có dữ liệu và bất biến riêng không?** Nếu có, một kiểu dữ liệu hoặc lớp có trách nhiệm rõ có thể phù hợp.
3. **Nó có vòng đời, phụ thuộc, chính sách hoặc nhóm bảo trì khác không?** Nếu có, ranh giới module có thể cần được xem xét.

Quy mô trích xuất cần tương xứng với nhu cầu thực. Ví dụ, chỉ để đổi một ngưỡng giá thì tham số hoặc cấu hình có kiểm tra dữ liệu thường đủ; không nhất thiết dựng một microservice. Khi chính sách thực sự khác nhau và được phát triển độc lập, việc tách thành các thành phần có hợp đồng riêng có thể giảm chi phí thay đổi.

### 11.1. Đánh đổi khi trích xuất

| Lợi ích có thể đạt | Chi phí cần xem xét |
| --- | --- |
| Đặt tên quy tắc và giảm nhiễu ở nơi gọi. | Thêm bước điều hướng khi cần xem triển khai. |
| Tạo điểm kiểm thử độc lập. | Có thể phát sinh test bám chặt chi tiết triển khai. |
| Cô lập chính sách thay đổi. | Thêm interface, kiểu dữ liệu hoặc tham số cần bảo trì. |
| Thu hẹp trách nhiệm của thành phần. | Tăng kết nối và số nơi cần sửa nếu chia sai ranh giới. |
| Dùng lại một quy tắc có cùng nghĩa. | Dễ tạo “shared utility” chứa nhiều trách nhiệm không liên quan. |
| Có thể triển khai hoặc quản lý riêng một module. | Tăng chi phí tích hợp, versioning, giám sát và vận hành. |

Một phép trích xuất chất lượng giúp **mức dễ hiểu ở nơi gọi và nơi định nghĩa cùng tăng**, không chỉ làm nơi gọi trông sạch hơn.

## 12. Tình huống review: chia 240 dòng thành 24 phương thức

Một pull request thay một phương thức xử lý yêu cầu dài 240 dòng bằng 24 phương thức, mỗi phương thức khoảng 10 dòng. Người viết mô tả: “Đã loại bỏ phương thức dài; mọi hàm hiện dưới giới hạn 15 dòng.”

Khi review, nhóm phát hiện:

- Nhiều helper chỉ có tên `step1`, `step2`, `handleResult`.
- Sáu helper cùng đọc và thay đổi một object `ProcessingContext` chứa nhiều trường mutable.
- Để biết khi nào đơn hàng bị từ chối, phải mở 11 phương thức.
- Có một số trường hợp exception bị bắt và trả về mặc định, trong khi phiên bản cũ truyền lỗi lên.
- Toàn bộ test hiện có vẫn chạy, nhưng thiếu test cho trường hợp dịch vụ ngoài trả timeout.

### 12.1. Vì sao không thể kết luận “đã đơn giản hơn”?

Giới hạn 15 dòng đã được đáp ứng, nhưng người đọc phải theo **nhiều lời gọi và một trạng thái dùng chung**. Việc thay đổi cách xử lý ngoại lệ có thể làm sai hợp đồng. Các test không đủ bao phủ trường hợp timeout nên một hồi quy quan trọng có thể lọt qua.

Ở tình huống này, cách xử lý không phải đơn giản là gộp ngược tất cả. Nên xác định:

- Những trách nhiệm nghiệp vụ nào thật sự có thể tách?
- Những bước nào chỉ chuyển dữ liệu hoặc cập nhật trạng thái mà không có tên ý nghĩa?
- Có thể bỏ `ProcessingContext` mutable bằng kết quả rõ ràng cho từng giai đoạn không?
- Các trường hợp lỗi nào là phần của hợp đồng và cần test?
- Khi review, có thể giải thích đường đi thành công và đường đi thất bại bằng một sơ đồ luồng ngắn không?

### 12.2. Một hướng refactor hợp lý

Giả sử chức năng gồm: **xác thực yêu cầu → kiểm tra chính sách → dự trữ hàng → tạo đơn → gửi xác nhận**. Một phương thức điều phối với các bước có tên nghiệp vụ có thể giúp đọc luồng tổng thể. Logic chính sách phức tạp được tách thành thành phần riêng; thao tác lưu và giao tiếp với dịch vụ ngoài có hợp đồng rõ về lỗi và kết quả.

Nếu bước dự trữ hàng và tạo đơn cần một cơ chế nhất quán đặc biệt, ranh giới đó phải được thiết kế ở mức nghiệp vụ và hạ tầng, không đơn thuần theo số dòng. Cần kiểm thử tích hợp cho lỗi giữa các bước và quy trình hoàn tác phù hợp.

Mục tiêu là **người đọc thấy được ý định, ranh giới và tác dụng phụ**, chứ không phải tăng số phương thức.

## 13. Quy trình ra quyết định khi muốn chia nhỏ mã

Có thể áp dụng chuỗi câu hỏi sau trong một buổi refactor hoặc code review:

**Bước 1 — Mô tả hành vi trước khi sửa.** Xác định đầu vào, kết quả, lỗi, tác dụng phụ và các bất biến cần giữ. Liệt kê những trường hợp biên có rủi ro.

**Bước 2 — Chỉ rõ điểm khó hiểu.** Người đọc đang vướng ở lồng nhau sâu, nhiều trách nhiệm, biến trạng thái dài hạn, tên không rõ, thuật toán kém hay phụ thuộc bên ngoài? Đừng giả định số dòng là nguyên nhân.

**Bước 3 — Đặt tên trách nhiệm cần tách.** Nếu không thể đặt tên có ý nghĩa, thử làm rõ điều kiện, giảm trạng thái hoặc viết lại cấu trúc cục bộ trước. Đừng tạo helper chỉ để thỏa ngưỡng dòng.

**Bước 4 — Chọn phạm vi tách nhỏ nhất đủ ích.** Ưu tiên trích xuất một khối gắn kết. Chỉ đưa sang class hoặc module khi có ranh giới dữ liệu, chính sách hoặc quyền sở hữu thật sự.

**Bước 5 — Đọc thử ở cả hai mức.** Nhìn phương thức gọi có hiểu luồng chính không? Mở helper có thấy logic khép kín và hợp đồng rõ không? Có phải nhảy giữa nhiều file để giải thích một điều kiện nhỏ không?

**Bước 6 — Xác minh hành vi.** Chạy test phù hợp; kiểm tra ngoại lệ, thứ tự tác dụng phụ, giao dịch, làm tròn và dữ liệu biên. Bổ sung test khi phát hiện khoảng trống có ý nghĩa.

**Bước 7 — Đánh giá lợi ích sau thay đổi.** Người review có tìm vị trí sửa nhanh hơn, bớt thông tin ngầm và ít phải sửa nhiều nơi cho một thay đổi không? Nếu chỉ có số dòng mỗi hàm giảm, cần đánh giá lại.

### 13.1. Ví dụ giải thích trade-off trong PR

> “Chính sách chiết khấu và phí vận chuyển hiện được hai nhóm cập nhật độc lập. Tôi tách hai phép tính thành phương thức có tên theo nghiệp vụ để người sửa định vị đúng quy tắc. Phương thức báo giá vẫn thể hiện trình tự, làm tròn và cách tính tổng; các test ở đúng ngưỡng 200.000 và 500.000 bảo vệ hành vi. Tôi giữ phần tính tổng tại nơi gọi vì đó là một phép tính ngắn cần thấy cùng báo giá.”

Một mô tả như vậy cho người review kiểm tra **lý do thay đổi, trách nhiệm và bằng chứng**, hữu ích hơn câu “đã giảm số dòng”.

## 14. Câu hỏi tự kiểm tra

1. Một hàm 70 dòng chỉ tạo một báo cáo bằng các bước tuần tự. Có nên chia thành bảy hàm 10 dòng không? Những dấu hiệu nào quyết định?
2. Một hàm 8 dòng có bốn toán tử ba ngôi lồng nhau. Vì sao số dòng ít không chứng minh nó dễ đọc?
3. Sau khi tách hàm, chỉ số cyclomatic của phương thức gọi giảm, nhưng số nhánh nghiệp vụ không đổi. Ta có thể kết luận điều gì và không thể kết luận điều gì?
4. Một helper cần 12 tham số và phải sửa chung với ba helper khác ở mỗi yêu cầu. Điều này gợi ý xem lại ranh giới nào?
5. Khi tách logic tính phí sang `ShippingPolicy`, những test nào giúp xác minh rằng hành vi không đổi?

**Gợi ý trả lời:**

- Với câu 1, hãy tìm trách nhiệm độc lập, mức độ khó theo dõi và chi phí điều hướng; không cần chia chỉ vì vượt ngưỡng dòng.
- Với câu 2, cấu trúc điều kiện lồng nhau và tên không rõ có thể làm tăng tải nhận thức.
- Với câu 3, phương thức gọi có thể đơn giản hơn ở mức cục bộ, nhưng cần đọc cả các helper để đánh giá chức năng.
- Với câu 4, có thể đoạn bị tách không có trách nhiệm riêng hoặc dữ liệu đang được đóng gói không hợp lý.
- Với câu 5, kiểm tra tại ngưỡng, sát dưới ngưỡng, khách đủ/không đủ điều kiện, ngoại lệ đầu vào, làm tròn và bất kỳ tác dụng phụ nào thuộc hợp đồng.

## 15. Checklist áp dụng khi review và refactor

- [ ] Tôi biết phần khó hiểu cụ thể là gì; không dùng độ dài mã làm lý do duy nhất để chia.
- [ ] Trách nhiệm được tách có một tên mang ý nghĩa nghiệp vụ hoặc kỹ thuật rõ.
- [ ] Sau khi tách, luồng chính có thể hiểu mà không phải mở quá nhiều helper mơ hồ.
- [ ] Helper nhận đầu vào và trả kết quả rõ ràng; ít phụ thuộc vào trạng thái hoặc thứ tự gọi ngầm.
- [ ] Tôi không tạo chuỗi wrapper hoặc object trung gian chỉ để giữ phương thức dưới ngưỡng số dòng.
- [ ] Các quy tắc thường thay đổi cùng nhau được đặt trong phạm vi có trách nhiệm rõ ràng.
- [ ] Việc tách giữ nguyên hợp đồng đầu vào, ngoại lệ, thứ tự đánh giá và tác dụng phụ.
- [ ] Các phép tính có tiền, thời gian, số học hoặc giao dịch được kiểm tra ở giá trị biên.
- [ ] Những tác động về độ phức tạp thuật toán, bộ nhớ, I/O và tích hợp được xem xét riêng.
- [ ] Các chỉ số LOC, cyclomatic và cognitive complexity được dùng để gợi ý review, không làm mục tiêu tuyệt đối.
- [ ] Test xác minh hành vi quan sát được và không phụ thuộc quá mức vào cấu trúc private helper.
- [ ] Người bảo trì khác có thể nhanh chóng xác định nơi sửa khi yêu cầu thay đổi.

## 16. Kết luận

**Chia nhỏ theo số dòng có giới hạn tác dụng**: nó có thể cải thiện cách trình bày và giúp cô lập một trách nhiệm rõ ràng, nhưng cũng có thể tạo thêm tầng lời gọi, trạng thái ngầm và chi phí theo dõi thông tin. Việc giảm số dòng của mỗi phương thức không tự giảm số quyết định nghiệp vụ, độ khó thuật toán hoặc rủi ro tích hợp.

Trong **CODE_QUALITY_FUNDAMENTALS**, một cấu trúc mã tốt là cấu trúc giúp người bảo trì **hiểu hành vi, tin vào những gì đã được xác minh và sửa đúng chỗ với ít tác động ngoài ý muốn**. Hãy chia nhỏ dựa trên **ý định, trách nhiệm và bằng chứng về chi phí thay đổi**, đồng thời giữ những logic đơn giản, gắn kết ở cùng một nơi khi đó là cách dễ hiểu nhất.

