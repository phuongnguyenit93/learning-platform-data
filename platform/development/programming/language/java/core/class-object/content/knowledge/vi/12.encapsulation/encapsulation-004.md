# Kiểm tra dữ liệu ở điểm tạo và điểm cập nhật trong Java

**Đóng gói (encapsulation)** không chỉ là khai báo trường `private` rồi tạo getter/setter. Mục tiêu quan trọng hơn là **kiểm soát mọi con đường có thể làm thay đổi trạng thái của một đối tượng**, sao cho đối tượng luôn tuân thủ các quy tắc hợp lệ (*invariants*) do lớp định nghĩa. Vì vậy, kiểm tra dữ liệu phải diễn ra ở **điểm tạo** — thường là constructor hoặc static factory — và **điểm cập nhật** — các phương thức thay đổi trạng thái.

Ví dụ, một mặt hàng có thể yêu cầu mã hàng không rỗng, giá bán dương và số lượng tồn không âm. Constructor cần từ chối dữ liệu sai ngay khi tạo; các phương thức nhập hàng, bán hàng và đổi giá cũng phải từ chối các thao tác khiến một đối tượng đã hợp lệ trở thành không hợp lệ.

Bài này giải thích cách đặt invariant, phân biệt validation của tham số với validation trạng thái kết quả, trình tự **kiểm tra trước — cập nhật sau**, xử lý nhiều trường phụ thuộc nhau, tránh lộ dữ liệu mutable, ranh giới của `final`, lỗi và kiểm thử. Các chương trình độc lập biên dịch và chạy với **Java 17 trở lên**.

## 1. Tại sao phải kiểm tra cả lúc tạo lẫn lúc cập nhật?

Xét lớp có các trường:

~~~java
class Item {
    private String name;
    private int quantity;

    Item(String name, int quantity) {
        this.name = name;
        this.quantity = quantity;
    }

    void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

Đây là **lớp minh họa hợp lệ** nhưng còn thiếu kiểm tra. Caller có thể tạo `new Item("", -3)`; hoặc tạo `new Item("Bút", 10)` rồi gọi `setQuantity(-99)`. Chỉ dùng `private` không ngăn những giá trị sai lọt qua **phương thức được phép truy cập**.

Nếu quy tắc nghiệp vụ là:

~~~text
name != null
name không chỉ gồm khoảng trắng
quantity >= 0
~~~

thì một lớp đúng phải giữ được chúng **sau mọi lần tạo hoặc cập nhật thành công**. Đó là ý nghĩa của invariant.

| Điểm kiểm soát | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Constructor | Có được tạo object với dữ liệu đầu vào này không? | Tên phải hợp lệ, tồn kho ban đầu không âm |
| Static factory | Có thể xác thực và chuẩn hóa trước khi trả object không? | `Item.of("  Bút  ", 5)` |
| Phương thức thay đổi trạng thái | Kết quả sau hành động có còn hợp lệ? | Nhập hàng không tràn số |
| Phương thức nhiều tham số | Các trường **kết hợp** có thỏa ràng buộc không? | `start <= end` |
| Đầu vào mutable | Dữ liệu có thể bị sửa qua một tham chiếu giữ bên ngoài không? | Sao chép mảng/danh sách khi nhận và trả |
| Nhiều luồng | Kiểm tra rồi cập nhật có bị xen ngang không? | Khóa hoặc cơ chế atomic cho trạng thái chia sẻ |

**Không nên chỉ kiểm tra ở giao diện hoặc controller.** Mã khác trong chương trình, bài kiểm thử, tác vụ nền hoặc một API khác vẫn có thể gọi trực tiếp constructor/method. Lớp nên tự bảo vệ những invariant thuộc trách nhiệm của nó.

## 2. Phân biệt precondition, postcondition và invariant

Ba khái niệm liên quan nhưng không đồng nhất:

- **Precondition:** điều kiện caller cần đáp ứng trước khi phương thức thực hiện thành công. Ví dụ `receive(amount)` yêu cầu `amount > 0`.
- **Postcondition:** điều đúng sau khi phương thức hoàn thành bình thường. Ví dụ `receive(3)` làm số lượng tồn tăng đúng 3.
- **Invariant:** điều phải đúng ở những thời điểm quan sát hợp lệ của object. Ví dụ `quantity >= 0` sau constructor và sau các thao tác công khai hoàn tất.

Ví dụ:

~~~text
Trước khi gọi sell(4):
  quantity = 10                   (invariant: quantity >= 0)
  amount = 4                      (precondition: amount > 0)

Sau khi sell(4) thành công:
  quantity = 6                    (postcondition: giảm đúng 4)
  quantity >= 0                   (invariant vẫn được giữ)

Nếu gọi sell(99):
  amount > 0 nhưng không đủ tồn
  -> từ chối và giữ quantity = 10
~~~

Một quy tắc như “không được bán quá số lượng đang có” không thể kiểm tra bằng `amount > 0` đơn lẻ. Nó phụ thuộc **cả tham số và trạng thái hiện tại**.

**Đóng gói tốt** là giữ quyền sửa dữ liệu ở những phương thức biết đủ thông tin để bảo vệ invariant, thay vì công bố nhiều setter cho mọi field một cách máy móc.

## 3. Xác định invariant trước khi viết constructor

Trước khi viết code, hãy lập bảng cho từng trường:

| Trường | Loại dữ liệu | Invariant đề xuất | Có được thay đổi? |
| --- | --- | --- | --- |
| `sku` | `String` | Khác null và không trắng | Không, mã hàng ổn định |
| `name` | `String` | Khác null và không trắng | Có, qua thao tác đổi thông tin |
| `quantity` | `int` | Không âm | Có, qua nhập/bán |
| `priceCents` | `long` | Lớn hơn 0 | Có, qua đổi thông tin |

Đây là **quy tắc minh họa**, không phải luật bắt buộc cho mọi hệ thống bán hàng. Tùy bài toán, giá bằng 0 có thể hợp lệ cho hàng tặng, hoặc tồn kho âm có thể được biểu diễn khi quản lý đặt trước. Điều quan trọng là chọn quy tắc **rõ ràng và nhất quán**.

Dùng `private` để tránh caller tự gán field; dùng `final` khi trường không được gán lại sau khởi tạo; và cung cấp những phương thức **diễn đạt hành vi** như `receive`, `sell`, `updateDetails` thay vì mọi thao tác đều chỉ là `setX`.

Trong Java, constructor cho phép object được tạo ở trạng thái ban đầu hợp lệ. Một phương thức cập nhật phải tiếp tục duy trì trạng thái hợp lệ, không được giả định “đã kiểm tra ở constructor rồi thì về sau không cần nữa”.

## 4. Chương trình hoàn chỉnh: bảo vệ invariant của mặt hàng

Tạo tệp **`EncapsulationValidationDemo.java`** gồm một lớp `InventoryItem` được đóng gói và một lớp `public` chứa `main`.

~~~java
final class InventoryItem {
    private final String sku;
    private String name;
    private int quantity;
    private long priceCents;

    InventoryItem(String sku, String name, int quantity, long priceCents) {
        this.sku = checkedText(sku, "sku");
        this.name = checkedText(name, "name");
        this.quantity = checkedQuantity(quantity);
        this.priceCents = checkedPrice(priceCents);
    }

    private static String checkedText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " không hợp lệ");
        }
        return value.strip();
    }

    private static int checkedQuantity(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("quantity không được âm");
        }
        return value;
    }

    private static long checkedPrice(long value) {
        if (value <= 0) {
            throw new IllegalArgumentException("priceCents phải dương");
        }
        return value;
    }

    void receive(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }
        int nextQuantity = Math.addExact(quantity, amount);
        quantity = nextQuantity;
    }

    void sell(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }
        if (amount > quantity) {
            throw new IllegalArgumentException("không đủ hàng");
        }
        quantity -= amount;
    }

    void updateDetails(String newName, long newPriceCents) {
        String checkedName = checkedText(newName, "name");
        long checkedPrice = checkedPrice(newPriceCents);

        name = checkedName;
        priceCents = checkedPrice;
    }

    String summary() {
        return sku + " | " + name
                + " | q=" + quantity
                + " | price=" + priceCents;
    }
}

public class EncapsulationValidationDemo {
    public static void main(String[] args) {
        InventoryItem item = new InventoryItem(
                "SKU-01", "  Bút  ", 10, 5000);

        System.out.println("created=" + item.summary());

        item.receive(5);
        item.sell(3);
        System.out.println("updated=" + item.summary());

        try {
            item.receive(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject receive=" + ex.getMessage());
        }

        try {
            item.updateDetails("Vở", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject details=" + ex.getMessage());
        }
        System.out.println("after errors=" + item.summary());

        item.updateDetails("Vở", 7000);
        System.out.println("valid change=" + item.summary());

        try {
            item.sell(99);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject sell=" + ex.getMessage());
        }

        try {
            item.receive(Integer.MAX_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("reject overflow");
        }

        try {
            new InventoryItem("X", "Sai", -1, 100);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject create=" + ex.getMessage());
        }
        System.out.println("final=" + item.summary());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 EncapsulationValidationDemo.java
java EncapsulationValidationDemo
~~~

**Stdout chính xác:**

~~~text
created=SKU-01 | Bút | q=10 | price=5000
updated=SKU-01 | Bút | q=12 | price=5000
reject receive=amount phải dương
reject details=priceCents phải dương
after errors=SKU-01 | Bút | q=12 | price=5000
valid change=SKU-01 | Vở | q=12 | price=7000
reject sell=không đủ hàng
reject overflow
reject create=quantity không được âm
final=SKU-01 | Vở | q=12 | price=7000
~~~

### Phân tích các điểm kiểm tra

**Trong constructor:** `sku` và `name` được kiểm tra không null/không trắng, rồi `strip()` để bỏ khoảng trắng đầu/cuối; `quantity` phải không âm và `priceCents` phải dương. Do đó `"  Bút  "` trở thành `"Bút"`. Trường `sku` là `final`, nghĩa là tham chiếu trường này không thể được gán lại sau khi khởi tạo.

**Trong `receive`:** kiểm tra `amount > 0`, tính `nextQuantity` qua `Math.addExact` để phát hiện tràn kiểu `int`. Chỉ sau khi phép tính hoàn thành bình thường mới thực hiện `quantity = nextQuantity`. Khi thử cộng `Integer.MAX_VALUE` vào 12, phép tính ném `ArithmeticException`, còn `quantity` giữ 12.

**Trong `sell`:** số bán phải dương và không lớn hơn tồn kho. Vì đã kiểm tra hai điều kiện, phép trừ giữ quantity không âm.

**Trong `updateDetails`:** kiểm tra **cả hai giá trị mới trước khi gán bất kỳ field nào**. Lời gọi `updateDetails("Vở", 0)` bị từ chối và giữ nguyên cả tên `Bút` lẫn giá 5000. Khi cả hai hợp lệ, hai field cùng được cập nhật.

**Khi constructor lỗi:** `new InventoryItem("X", "Sai", -1, 100)` bị từ chối. Biểu thức tạo object không hoàn thành bình thường, không trả về tham chiếu object hợp lệ cho bên gọi.

Nhờ `final class InventoryItem`, ví dụ cũng tránh việc subclass tự làm thay đổi các quy tắc cập nhật hoặc override hành vi. Một lớp cho phép kế thừa sẽ cần thiết kế và kiểm thử hợp đồng kế thừa riêng.

## 5. Kiểm tra ở điểm tạo: constructor và factory

Constructor là ranh giới quan trọng vì nó quyết định object có được tạo thành công với trạng thái ban đầu hay không.

Một constructor cần:

1. Xác định các tham số bắt buộc và trường nào có giá trị mặc định.
2. Từ chối giá trị không đáp ứng invariant.
3. Chuẩn hóa dữ liệu đầu vào nếu hợp đồng yêu cầu, như `strip()` với tên.
4. Thiết lập đầy đủ các trường và mối quan hệ giữa trường.
5. Không công bố `this` quá sớm cho listener/thread trong khi trạng thái chưa hoàn tất.

Một static factory cũng có thể đảm nhiệm kiểm tra trước khi trả một object, nhưng **không nên biến constructor nội bộ thành con đường bỏ qua invariant** nếu các đoạn code khác trong lớp còn có thể gọi constructor đó.

Ví dụ, khi muốn tên factory biểu thị mục đích:

~~~java
final class Percent {
    private final int value;

    private Percent(int value) {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("percent ngoài 0..100");
        }
        this.value = value;
    }

    static Percent of(int value) {
        return new Percent(value);
    }

    int value() {
        return value;
    }
}
~~~

Đây là lớp minh họa hợp lệ; caller có thể dùng `Percent.of(75)`, nhưng `Percent.of(150)` bị constructor từ chối. Factory cung cấp cách gọi rõ nghĩa và constructor tiếp tục là **cửa bảo vệ cuối cùng**.

Nếu có nhiều constructor overload, nên gom logic kiểm tra về một constructor lõi hoặc các hàm validation dùng chung để tránh mỗi đường tạo áp dụng một bộ quy tắc khác nhau. **Không nên gọi phương thức instance có thể override từ constructor** nếu nó có thể quan sát subclass chưa khởi tạo hoàn chỉnh.

## 6. Kiểm tra ở điểm cập nhật: tham số hợp lệ chưa chắc trạng thái kết quả hợp lệ

Một setter đơn giản có thể kiểm tra miền giá trị:

~~~java
void setPriceCents(long priceCents) {
    if (priceCents <= 0) {
        throw new IllegalArgumentException("giá phải dương");
    }
    this.priceCents = priceCents;
}
~~~

Đây là một **phương thức minh họa** trong lớp có field `priceCents`. Nó kiểm tra đúng điều kiện nội tại của giá.

Nhưng cập nhật theo hành vi thường cần cả **trạng thái cũ**. Ví dụ:

~~~java
void sell(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount phải dương");
    }
    if (amount > quantity) {
        throw new IllegalArgumentException("không đủ hàng");
    }
    quantity -= amount;
}
~~~

Một yêu cầu bán 20 đơn vị có thể hợp lệ khi tồn kho 50 nhưng **không hợp lệ** khi tồn kho 5. Vì vậy không thể thay thế validation ở điểm cập nhật bằng mỗi việc “`amount` phải là số nguyên dương”.

**Điều kiện đúng cần kiểm tra trên trạng thái kết quả**, chẳng hạn `nextQuantity >= 0`. Với phép cộng số nguyên, cần tính bằng `Math.addExact` để loại rủi ro overflow làm `nextQuantity` bất ngờ trở thành âm.

## 7. Kiểm tra trước — cập nhật sau để tránh trạng thái cập nhật dở

Giả sử một method cần thay đổi **hai field**. Cách nguy hiểm:

~~~java
void updateDetails(String newName, long newPrice) {
    name = checkedText(newName, "name");
    priceCents = checkedPrice(newPrice);
}
~~~

Đây là ví dụ **biên dịch được nhưng thiết kế không tốt** khi yêu cầu “thất bại thì giữ nguyên trạng thái”. Nếu tên hợp lệ nhưng giá không hợp lệ, method đã sửa `name` trước khi phép kiểm tra giá ném ngoại lệ.

Cách phù hợp hơn:

~~~java
void updateDetails(String newName, long newPrice) {
    String checkedName = checkedText(newName, "name");
    long checkedPrice = checkedPrice(newPrice);
    name = checkedName;
    priceCents = checkedPrice;
}
~~~

Các đoạn trên chỉ minh họa hai **phiên bản thay thế** của cùng một phương thức, không phải hai overload được phép khai báo đồng thời. Trong phiên bản sau, việc kiểm tra và chuẩn hóa diễn ra trước; nếu một phép kiểm tra thất bại thì **chưa có field nào được gán lại**.

Mô hình:

~~~text
Nhận các giá trị mới
        |
        v
Kiểm tra từng tham số
        |
        v
Kiểm tra quan hệ giữa các giá trị
        |
        v
Tính trạng thái kết quả (có thể lỗi/tràn)
        |
        +-- lỗi --> ném exception, giữ trạng thái cũ
        |
        v
Gán các field theo kế hoạch
        |
        v
Trả kết quả thành công
~~~

**Giới hạn quan trọng:** hai phép gán liên tiếp không trở thành một transaction nguyên tử đối với **nhiều luồng** chỉ vì đã validate trước. Mẫu này giúp tránh trạng thái cập nhật dở do lỗi đồng bộ trong cùng lời gọi; nếu object được chia sẻ đồng thời, cần cơ chế đồng bộ riêng.

## 8. Ràng buộc liên trường: phải kiểm tra quan hệ, không chỉ từng giá trị

Một đối tượng biểu diễn đoạn số nguyên có invariant `0 <= start <= end`. Hai field có thể riêng lẻ không âm nhưng vẫn **kết hợp sai**, ví dụ `start=9`, `end=3`.

Tạo tệp **`RangeValidationDemo.java`**:

~~~java
final class Range {
    private int start;
    private int end;

    Range(int start, int end) {
        validate(start, end);
        this.start = start;
        this.end = end;
    }

    void moveTo(int newStart, int newEnd) {
        validate(newStart, newEnd);
        this.start = newStart;
        this.end = newEnd;
    }

    private static void validate(int start, int end) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("range không hợp lệ");
        }
    }

    String describe() {
        return "[" + start + "," + end + "]";
    }
}

public class RangeValidationDemo {
    public static void main(String[] args) {
        Range range = new Range(2, 5);
        System.out.println("original=" + range.describe());

        try {
            range.moveTo(9, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("after reject=" + range.describe());

        range.moveTo(6, 8);
        System.out.println("updated=" + range.describe());

        try {
            new Range(-1, 4);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject create=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RangeValidationDemo.java
java RangeValidationDemo
~~~

**Stdout:**

~~~text
original=[2,5]
reject=range không hợp lệ
after reject=[2,5]
updated=[6,8]
reject create=range không hợp lệ
~~~

Bài học từ ví dụ:

- `validate` được dùng chung tại **constructor và điểm cập nhật**.
- `moveTo` nhận **hai giá trị dự kiến**, kiểm tra cả quan hệ giữa chúng trước khi đổi field.
- Gọi `range.moveTo(9,3)` bị từ chối và giữ `[2,5]`.
- Kiểu `Range` được khai báo `final` để không có subclass override logic khởi tạo/cập nhật; với lớp có kế thừa cần thiết kế khác phù hợp.

Nếu cung cấp hai setter độc lập `setStart` và `setEnd`, rất dễ phát sinh trạng thái trung gian vi phạm `start <= end`, dù kết quả mong muốn cuối cùng hợp lệ. Khi invariant liên quan nhiều field, một **phương thức cập nhật theo nhóm** như `moveTo(start,end)` thường rõ và an toàn hơn.

## 9. Chọn kiểu ngoại lệ nhất quán

Java không bắt buộc chỉ một kiểu exception cho mọi validation. Những lựa chọn thông dụng:

| Tình huống | Ngoại lệ có thể phù hợp |
| --- | --- |
| Tham số không thuộc miền cho phép | `IllegalArgumentException` |
| Tham số bắt buộc không được null | `NullPointerException` từ `Objects.requireNonNull`, hoặc `IllegalArgumentException` theo hợp đồng |
| Gọi thao tác ở trạng thái đối tượng chưa cho phép | `IllegalStateException` |
| Chỉ số mảng/list ngoài phạm vi | `IndexOutOfBoundsException` hoặc ngoại lệ do collection phát sinh |
| Phép cộng/nhân số nguyên có kiểm tra tràn | `ArithmeticException` từ `Math.addExact`/`multiplyExact` |
| Kích thước/nội dung chuỗi không hợp lệ | `IllegalArgumentException` hoặc kiểu ngoại lệ API đã công bố |

Trong `InventoryItem`, chương trình chủ động chọn `IllegalArgumentException` cho cả null và chuỗi chỉ chứa khoảng trắng. Đây là **quy ước được thực hiện nhất quán trong class**, không phải quy tắc buộc tất cả API phải dùng cùng exception.

Thông báo lỗi nên xác định **điều kiện không hợp lệ** mà không làm rò rỉ dữ liệu nhạy cảm. Ví dụ `quantity không được âm` có ích hơn một thông báo chung `invalid`.

### Validation không phải lạm dụng `try/catch`

Phương thức cập nhật nên **từ chối bằng exception** nếu hợp đồng của nó quy định như vậy. Bên gọi có thể bắt lỗi tại ranh giới giao diện để trình bày thông báo thân thiện; không nên tự động bắt mọi exception trong setter rồi âm thầm bỏ qua khiến caller tin rằng cập nhật đã thành công.

Một lựa chọn khác là API trả một kết quả có trạng thái thành công/thất bại. Hãy dùng cách đó khi lỗi đầu vào là tình huống nghiệp vụ bình thường, nhưng vẫn phải bảo vệ invariant trong triển khai.

## 10. Chuẩn hóa dữ liệu và validation: phân biệt rõ thứ tự

“Kiểm tra” và “chuẩn hóa” không hoàn toàn giống nhau:

- **Validation:** xác định có chấp nhận giá trị hay không.
- **Normalization:** biến một đầu vào hợp lệ thành biểu diễn thống nhất, ví dụ `"  Bút  "` thành `"Bút"`.

Trong `checkedText`:

~~~java
private static String checkedText(String value, String field) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException(field + " không hợp lệ");
    }
    return value.strip();
}
~~~

Kiểm tra tránh `NullPointerException` trước khi gọi phương thức `isBlank()`. Dùng `String.strip()` (Java 11+) để loại khoảng trắng theo khái niệm Unicode mà method hỗ trợ. Kết quả chuẩn hóa được ghi vào field, không sửa `String` gốc vì `String` là bất biến.

Tùy yêu cầu, ứng dụng có thể cần chuẩn hóa **trước khi kiểm tra độ dài**. Ví dụ chuỗi `"  A  "` dài 5 nhưng sau `strip()` chỉ dài 1. Cần chọn rõ miền đo trước/sau, tránh các quy tắc bất nhất giữa constructor và setter.

**Không chuẩn hóa tùy tiện mọi dữ liệu.** Mã SKU, mật khẩu, khóa định danh, tên pháp lý hoặc chuỗi chứa khoảng trắng có ý nghĩa có thể yêu cầu giữ nguyên. Một phương thức có tên `normalize` phải diễn đạt rõ điều được thay đổi.

## 11. Kiểm soát đầu vào mutable: constructor phải cân nhắc sao chép phòng vệ

Nếu constructor nhận `int[]`, `List`, `Date` hoặc object mutable khác rồi **lưu trực tiếp tham chiếu**, caller có thể giữ alias và sửa dữ liệu sau khi object được tạo. Khi ấy invariant có thể bị phá vỡ **mà không đi qua bất kỳ setter nào**.

Ví dụ không nên dùng nếu cần sở hữu dữ liệu độc lập:

~~~java
class WeakGradeBook {
    private final int[] grades;

    WeakGradeBook(int[] grades) {
        this.grades = grades;
    }
}
~~~

Đây là lớp minh họa hợp lệ. `private final int[] grades` chỉ ngăn gán lại **tham chiếu field** sau constructor; nó không làm **phần tử mảng** bất biến.

Nếu caller truyền `int[] scores = {80,90}` và constructor lưu trực tiếp `scores`, caller có thể sửa `scores[0] = -10` về sau; object đang giữ **cùng mảng** sẽ nhìn thấy giá trị không hợp lệ.

Cách bảo vệ thường là:

1. Kiểm tra mảng tham số khác null.
2. **Sao chép dữ liệu sang mảng riêng** trước khi đưa vào trạng thái object.
3. Kiểm tra từng phần tử của bản sao.
4. Chỉ gán field sau khi toàn bộ dữ liệu đã hợp lệ.
5. Khi trả mảng ra ngoài, **trả bản sao** thay vì lộ mảng nội bộ.

## 12. Chương trình hoàn chỉnh: sao chép và kiểm tra mảng ở cả hai chiều

Tạo tệp **`GradeBookValidationDemo.java`**:

~~~java
import java.util.Arrays;

final class GradeBook {
    private int[] grades;

    GradeBook(int[] input) {
        grades = checkedCopy(input);
    }

    void replaceGrades(int[] input) {
        int[] replacement = checkedCopy(input);
        grades = replacement;
    }

    int[] grades() {
        return grades.clone();
    }

    String summary() {
        return Arrays.toString(grades);
    }

    private static int[] checkedCopy(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("grades null");
        }
        int[] copy = input.clone();
        for (int grade : copy) {
            if (grade < 0 || grade > 100) {
                throw new IllegalArgumentException("grade ngoài 0..100");
            }
        }
        return copy;
    }
}

public class GradeBookValidationDemo {
    public static void main(String[] args) {
        int[] source = {80, 90};
        GradeBook book = new GradeBook(source);
        System.out.println("created=" + book.summary());

        source[0] = -10;
        System.out.println("after external edit=" + book.summary());

        int[] exported = book.grades();
        exported[1] = -10;
        System.out.println("after getter edit=" + book.summary());

        try {
            book.replaceGrades(new int[] {90, 101});
        } catch (IllegalArgumentException ex) {
            System.out.println("reject replace=" + ex.getMessage());
        }
        System.out.println("after reject=" + book.summary());

        int[] newSource = {100, 95};
        book.replaceGrades(newSource);
        newSource[1] = -1;
        System.out.println("after valid replace=" + book.summary());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GradeBookValidationDemo.java
java GradeBookValidationDemo
~~~

**Stdout:**

~~~text
created=[80, 90]
after external edit=[80, 90]
after getter edit=[80, 90]
reject replace=grade ngoài 0..100
after reject=[80, 90]
after valid replace=[100, 95]
~~~

Ba hướng bảo vệ:

- **Constructor copy:** `source[0] = -10` không sửa được `GradeBook.grades`.
- **Getter copy:** nhận `exported` rồi sửa mảng ấy không sửa mảng nội bộ.
- **Update copy + validation:** `replaceGrades` tạo bản sao và duyệt kiểm tra **trước khi gán field**. Nếu một điểm ngoài `0..100`, state cũ được giữ. Sau cập nhật hợp lệ, sửa `newSource` cũng không ảnh hưởng object.

Với mảng primitive `int[]`, `clone()` sao chép các phần tử số nên đủ cho yêu cầu này. Với `List<MutableStudent>` hoặc mảng của object mutable, sao chép collection/mảng chỉ sao chép **tham chiếu phần tử**: muốn chống sửa từ bên ngoài còn phải thiết kế phần tử bất biến hoặc deep copy phù hợp.

## 13. Getter không nên làm lộ đường sửa invariant

Đặt field `private` nhưng cung cấp getter trả lại trực tiếp object mutable có thể mở một **cửa hậu**:

~~~java
class LeakySettings {
    private final java.util.List<String> tags =
            new java.util.ArrayList<>();

    java.util.List<String> tags() {
        return tags;
    }
}
~~~

Đây là một lớp minh họa hợp lệ. Caller có thể gọi `settings.tags().add(null)` nếu giữ được object `settings`, dù class muốn cấm tag null.

Các cách cải thiện phụ thuộc hợp đồng:

- Trả **bản sao**: `return new ArrayList<>(tags);` để caller sửa bản sao.
- Trả **snapshot không sửa được**: `return List.copyOf(tags);` khi phần tử được phép theo điều kiện `List.copyOf` (không chứa null).
- Dùng API truy vấn riêng như `containsTag`, `tagCount` khi không cần lộ collection.
- Đối với object con mutable, tiếp tục cân nhắc cách kiểm soát quyền sở hữu của từng phần tử.

Chỉ viết `Collections.unmodifiableList(tags)` cung cấp một **view không cho sửa qua view**, nhưng nếu ai đó còn giữ list gốc và sửa nó, view vẫn phản ánh thay đổi. **Unmodifiable view không nhất thiết là snapshot độc lập**.

Tương tự, `final` trên tham chiếu field không bảo đảm toàn bộ object graph trở thành bất biến.

## 14. Setter chung hay phương thức hành vi có nghĩa?

Một lớp có thể có:

~~~java
void setQuantity(int quantity) {
    if (quantity < 0) {
        throw new IllegalArgumentException("quantity âm");
    }
    this.quantity = quantity;
}
~~~

Đây là phương thức minh họa. Nó có thể hợp lý nếu nghiệp vụ thật sự cho phép **đặt lại số lượng tồn tuyệt đối**, chẳng hạn qua quy trình kiểm kê có kiểm soát.

Nhưng nếu nghiệp vụ thực tế chỉ cho **nhập hàng hoặc bán hàng**, dùng `receive(amount)` và `sell(amount)` giúp:

- Diễn đạt hành động và tiền điều kiện rõ.
- Kiểm tra lượng nhập/bán, tràn số và tồn kho trước cập nhật.
- Giới hạn những chuyển trạng thái được phép.
- Ghi log sự kiện hoặc áp dụng quyền nghiệp vụ nếu cần, tại một điểm rõ ràng.

Với tài khoản, `deposit(amount)` và `withdraw(amount)` thường phù hợp hơn `setBalance(anyValue)` công khai. Với đặt chỗ, `reserveSeats(count)` phù hợp hơn thay mọi trường bằng setter độc lập không kiểm soát giới hạn.

**Không có quy tắc tuyệt đối cấm setter.** Hãy dùng nó khi thao tác “đặt giá trị” thực sự là một hành vi được phép và có thể bảo vệ đầy đủ invariant. Không tự sinh getter/setter cho mọi `private field` chỉ vì có công cụ hỗ trợ.

## 15. Validation có thể phụ thuộc trạng thái vòng đời

Ngoài invariant tĩnh của field, nhiều object có **trạng thái vòng đời**: `NEW`, `ACTIVE`, `CLOSED`; hoặc đơn hàng `DRAFT`, `PAID`, `CANCELLED`.

Một tham số tự nó hợp lệ nhưng thao tác có thể không hợp lệ ở trạng thái hiện tại:

~~~java
final class DocumentState {
    private boolean closed;

    void close() {
        closed = true;
    }

    void edit() {
        if (closed) {
            throw new IllegalStateException("tài liệu đã đóng");
        }
    }

    boolean isClosed() {
        return closed;
    }
}
~~~

Đây là lớp minh họa hợp lệ. `edit()` không làm gì ngoài kiểm tra trạng thái để tập trung vào quy tắc lifecycle; một API tài liệu thực tế sẽ kết hợp kiểm tra này **trước hành vi sửa tài liệu** trong cùng phương thức.

**`IllegalArgumentException` và `IllegalStateException` khác nhau về nguyên nhân:** trường hợp đầu thường nói tham số bị sai; trường hợp sau nói **đối tượng đang ở trạng thái không cho phép thao tác**. Một phương thức có thể phải kiểm tra cả hai.

Đừng dùng exception để che một lỗi thiết kế vòng đời có thể tránh được, chẳng hạn tiếp tục cho external code gọi mọi setter trên một object đã bị đóng.

## 16. Lớp cho kế thừa: tránh bỏ qua validation bằng override

Nếu class không phải `final` và có phương thức có thể override, subclass có thể thay đổi ý nghĩa cập nhật. Một phương thức lớp cha kiểm tra dữ liệu đúng nhưng bị override bởi code không giữ invariant có thể tạo rủi ro.

Các chiến lược tùy thiết kế:

- Khai báo lớp `final` nếu không chủ đích hỗ trợ kế thừa.
- Khai báo các thao tác thiết yếu là `final` khi không muốn subclass thay đổi hợp đồng.
- Tập trung validation trong private method hoặc các thành phần mà subclass không thể override.
- Nếu thiết kế cho kế thừa, ghi rõ những invariant mà subclass phải giữ và kiểm thử subtype phù hợp.
- Tránh gọi phương thức **có thể override** từ constructor: override ở subclass có thể chạy khi field subclass chưa được khởi tạo.

Trong ví dụ `InventoryItem`, class là `final`, các field đều `private` và mọi thay đổi có thể thực hiện qua đúng những hành vi đã định nghĩa. Đây là một thiết kế đơn giản thích hợp cho bài học, không có nghĩa mọi hệ thống đều phải cấm kế thừa.

## 17. Kiểm tra ở nhiều lớp hệ thống: tránh nhầm trách nhiệm

Một ứng dụng có thể có validation ở nhiều tầng:

| Tầng | Trách nhiệm điển hình |
| --- | --- |
| UI/form | Phản hồi nhanh cho người nhập; hỗ trợ trải nghiệm |
| API/controller | Kiểm tra định dạng yêu cầu, quyền gọi, giới hạn request |
| Domain class | Giữ invariant của một object qua mọi đường tạo/cập nhật |
| Service/use case | Kiểm tra quy tắc cần nhiều object hoặc giao dịch |
| Database | Ràng buộc tồn tại bền vững, tính nhất quán, unique/check/foreign key |

Các tầng có thể cùng kiểm tra một điều kiện nhưng **mục đích khác nhau**. Form kiểm tra `quantity >= 0` để hiển thị lỗi ngay; domain object vẫn phải bảo vệ invariant khi service được gọi không qua form.

Một domain object không thể một mình bảo đảm quy tắc **liên đối tượng và bền vững** như “SKU là duy nhất trong toàn bộ cơ sở dữ liệu” chỉ bằng kiểm tra trong constructor. Điều đó thường cần service/repository và ràng buộc giao dịch phù hợp.

**Đừng đặt toàn bộ nghiệp vụ vào setter** hoặc chỉ dựa vào annotation ở giao diện để kết luận trạng thái object đã an toàn. Hãy phân định đâu là invariant nội bộ, đâu là quy tắc liên quan repository/hệ thống.

## 18. Thất bại không cập nhật là một cam kết cần chủ động thiết kế

Một API tốt thường muốn khi thao tác bị từ chối thì **trạng thái object không đổi**. Ví dụ `InventoryItem.updateDetails` và `Range.moveTo` đều được thiết kế như vậy.

Nhưng **ngoại lệ không tự làm rollback** mọi thứ. Xét:

~~~java
void unsafeRename(String newName) {
    this.name = newName;
    if (newName == null || newName.isBlank()) {
        throw new IllegalArgumentException("name sai");
    }
}
~~~

Đây là một phương thức minh họa **có lỗi logic**. Nó đã gán một giá trị không hợp lệ vào field trước khi ném exception, nên invariant có thể bị phá vỡ dù caller nhận được thông báo thất bại.

Nếu phương thức ghi file, gửi sự kiện hoặc cập nhật một object khác trước khi validation xong, việc ném exception cũng **không tự hoàn tác tác dụng phụ đó**.

Để bảo đảm mạnh hơn:

1. Chuẩn hóa và kiểm tra toàn bộ dữ liệu cần thiết trước.
2. Tính trước các giá trị có thể gặp overflow hoặc lỗi.
3. Chỉ cập nhật trạng thái khi các bước dễ thất bại đã hoàn thành.
4. Tránh công bố trạng thái trung gian cho listener/luồng khác.
5. Nếu có nhiều tài nguyên ngoại vi phải thay cùng nhau, dùng cơ chế transaction/compensation phù hợp thay vì chỉ hy vọng exception sẽ hoàn tác.

Với class có invariant giữa nhiều field và chia sẻ giữa nhiều luồng, hai bước “validate rồi gán” cần được bảo vệ bằng đồng bộ đúng cách để không có thread khác làm thay đổi trạng thái giữa chúng.

## 19. Concurrency: validation đúng chưa đủ nếu thao tác không nguyên tử

Giả sử hai thread cùng gọi `sell(7)` trên một mặt hàng có tồn kho 10. Nếu method không đồng bộ, cả hai có thể **đọc cùng giá trị 10**, đều vượt qua kiểm tra “đủ hàng”, rồi cập nhật chồng chéo. Kết quả không bảo đảm phản ánh đúng tổng số đã bán.

Trong Java Memory Model, `private` không tạo *thread safety*. Việc để field private chỉ giới hạn quyền truy cập từ mã nguồn; nhiều thread vẫn có thể gọi đồng thời phương thức instance công khai trên **cùng object**.

Những cách thiết kế tùy tình huống:

- Bảo vệ **toàn bộ chuỗi đọc–kiểm tra–ghi** bằng một lock hoặc `synchronized` thống nhất.
- Với trạng thái phù hợp, dùng các phép cập nhật nguyên tử hoặc CAS có kiểm tra lại điều kiện.
- Giới hạn ownership để một object mutable chỉ được sửa bởi một luồng.
- Đưa thao tác nghiệp vụ cần nhất quán bền vững vào **giao dịch ở tầng lưu trữ** nếu cần.

Ví dụ, với một object chỉ quản lý `quantity` trong bộ nhớ, một method `synchronized void sell(int amount)` bao trùm cả kiểm tra và cập nhật sẽ cung cấp mutual exclusion cho các lời gọi dùng **cùng monitor**. Nhưng hệ thống phải áp dụng đồng bộ cho **mọi con đường đọc/ghi liên quan**; `synchronized` riêng một method không tự làm toàn bộ chương trình thread-safe.

**Không gộp hai khái niệm:** invariant của một object lúc tuần tự và tính nguyên tử/visibility khi có nhiều luồng là hai yêu cầu cần cùng được xem xét.

## 20. Thiết kế bất biến để giảm các điểm cập nhật

Một lựa chọn khác là tạo **immutable value object**: object không có thao tác thay đổi trạng thái, và mọi thay đổi biểu diễn bằng một giá trị mới.

Ví dụ Java 17:

~~~java
record Temperature(int celsius) {
    Temperature {
        if (celsius < -273) {
            throw new IllegalArgumentException("dưới giới hạn");
        }
    }

    Temperature warmerBy(int delta) {
        int next = Math.addExact(celsius, delta);
        return new Temperature(next);
    }
}
~~~

Đây là một record minh họa hợp lệ. Constructor compact kiểm tra trạng thái mỗi lần tạo. `warmerBy` tính giá trị mới có kiểm tra tràn và gọi constructor để tái kiểm tra invariant; object cũ không bị sửa.

Caller muốn giữ giá trị mới phải gán lại:

~~~java
Temperature current = new Temperature(20);
current = current.warmerBy(5);
// current.celsius() bằng 25.
~~~

Với record chứa chỉ kiểu nguyên thủy như `int`, việc giữ trạng thái bất biến khá đơn giản. Với record chứa `List<MutableItem>`, bản thân record không tự deep-copy các thành phần mutable; vẫn phải cân nhắc sao chép phòng vệ.

Immutable object giảm số điểm cập nhật cần quản lý, nhưng không tự thay thế đồng bộ nếu nhiều luồng cùng **gán lại một tham chiếu dùng chung** theo kiểu đọc–tính–ghi.

## 21. Kiểm thử validation theo ma trận thành công, lỗi và giữ nguyên trạng thái

Một bài kiểm thử hữu ích cần đo **ba điều**: trường hợp hợp lệ hoạt động đúng; đầu vào sai bị từ chối; sau thất bại object vẫn giữ invariant.

Ma trận cho `InventoryItem`:

| Hành động | Kết quả cần kiểm tra |
| --- | --- |
| Tạo SKU hợp lệ, tên `"  Bút  "`, tồn 10, giá 5000 | Tạo thành công; tên chuẩn hóa `"Bút"` |
| Tạo tên `null` hoặc trắng | `IllegalArgumentException` |
| Tạo tồn -1 | `IllegalArgumentException` |
| Tạo giá 0 | `IllegalArgumentException` |
| `receive(5)` từ tồn 10 | Tồn thành 15 |
| `receive(0)` hoặc `receive(-1)` | Từ chối và giữ tồn cũ |
| `receive(Integer.MAX_VALUE)` khi tồn dương | `ArithmeticException`, tồn cũ không đổi |
| `sell(3)` khi tồn 15 | Tồn thành 12 |
| `sell(99)` khi tồn 12 | Từ chối, tồn vẫn 12 |
| `updateDetails("Vở",0)` | Từ chối và **cả tên lẫn giá cũ** giữ nguyên |
| `updateDetails("Vở",7000)` | Tên và giá đổi như yêu cầu |
| Thay dữ liệu mutable qua tham chiếu đầu vào hoặc getter | Không làm hỏng object nếu hợp đồng có defensive copy |

Đối với `Range`, cần kiểm tra `start<0`, `end<start`, hai giá trị bằng nhau và các biên như `Integer.MAX_VALUE` khi có tính toán.

### Một số phép kiểm tra Java trực tiếp

Không cần thư viện kiểm thử để hiểu nguyên tắc, chẳng hạn:

~~~java
Range range = new Range(2, 5);
if (!"[2,5]".equals(range.describe())) {
    throw new AssertionError("trạng thái ban đầu sai");
}
try {
    range.moveTo(9, 3);
    throw new AssertionError("phải từ chối khoảng sai");
} catch (IllegalArgumentException expected) {
    if (!"[2,5]".equals(range.describe())) {
        throw new AssertionError("thất bại nhưng trạng thái đổi");
    }
}
~~~

Đây là đoạn minh họa chạy được khi đặt cùng định nghĩa `Range` ở mục 8 trong một phương thức. Nó kiểm tra được cả **exception mong đợi** và trạng thái sau exception. Với dự án thật, có thể dùng JUnit `assertThrows`, `assertEquals` và các test biên, nhưng bản chất cần kiểm tra không thay đổi.

**Đừng chỉ kiểm tra rằng constructor/setter không ném lỗi.** Một phương thức sai như `quantity = quantity;` có thể chạy bình thường nhưng không cập nhật field; vì vậy phải **đọc lại trạng thái kết quả**.

## 22. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ kiểm tra ở constructor, setter gán thẳng | Object hợp lệ lúc đầu rồi thành sai | Dùng chung quy tắc ở mọi đường cập nhật |
| Chỉ kiểm tra ở UI | Lời gọi từ API/task khác có thể bỏ qua | Domain object tự bảo vệ invariant của nó |
| Nghĩ `private` tự từ chối giá trị sai | Field vẫn nhận giá trị qua method thiếu validation | Kiểm tra ở các hành vi công khai |
| Gán field trước, validate sau | Thất bại nhưng object đã bị sửa | Validate/tính trước rồi mới gán |
| Cập nhật hai field qua hai setter khi có invariant liên trường | Trạng thái trung gian có thể sai | Thao tác cập nhật cả nhóm |
| Không kiểm tra overflow | Giá trị mới có thể tràn và sai miền | `Math.addExact`/`multiplyExact` khi phù hợp |
| Lộ trực tiếp mảng/list nội bộ qua getter | Caller có thể sửa mà không qua method | Defensive copy hoặc API truy vấn |
| Lưu trực tiếp list/mảng caller truyền | Caller sửa sau constructor và phá invariant | Sao chép khi nhận; kiểm tra phần tử |
| Tin rằng `final List` nghĩa là list bất biến | Final chỉ khóa tham chiếu field | Bảo vệ object con mutable |
| Bắt exception rồi im lặng bỏ qua | Caller tưởng cập nhật thành công | Định nghĩa hợp đồng lỗi rõ ràng |
| Cho subclass override logic cập nhật tùy ý | Invariant của lớp cha có thể bị phá | Thiết kế cho kế thừa hoặc dùng `final` |
| Gọi method override từ constructor | Subclass chưa khởi tạo xong | Tránh dynamic dispatch trong constructor |
| Cho rằng kiểm tra và ghi hai dòng là atomic giữa thread | Có thể bị xen ngang hoặc mất cập nhật | Lock/atomic update phù hợp |
| Mọi lỗi đều xử lý bằng setter | Có quy tắc cần nhiều object/giao dịch | Đặt vào tầng nghiệp vụ/lưu trữ thích hợp |
| Chỉ test lỗi mà không kiểm tra trạng thái sau lỗi | Không phát hiện sửa dở | Kiểm tra invariant và tính nguyên trạng |

## 23. Bài tập tự luyện

**Câu 1 — Invariant.** Lớp `BankAccount` có `private long balance` và yêu cầu `balance >= 0`. Những đường nào cần kiểm tra nếu có constructor, `deposit`, `withdraw` và `setBalance`?

**Câu 2 — Tạo mới.** Constructor `Product(String name,int stock)` viết `this.name=name; this.stock=stock;` nhưng không kiểm tra. Hãy bổ sung quy tắc tên không trắng, tồn không âm và giải thích nơi cần gọi validation.

**Câu 3 — Trạng thái sau cập nhật.** Tồn kho là 5. `sell(7)` có tham số số dương. Vì sao vẫn phải từ chối? Sau thất bại, tồn kho phải bằng bao nhiêu nếu API cam kết không thay đổi khi lỗi?

**Câu 4 — Overflow.** Khi `quantity=20`, việc cộng `Integer.MAX_VALUE` bằng `quantity += amount` có thể gây điều gì? Vì sao `Math.addExact` rồi mới gán field an toàn hơn?

**Câu 5 — Cập nhật nhiều trường.** Có `start=2,end=5`, muốn đổi thành `start=7,end=9`. Tại sao `setStart(7)` có thể bị từ chối tạm thời dù đích cuối hợp lệ? Gợi ý thiết kế mới.

**Câu 6 — Sao chép phòng vệ.** Lớp `Scores` giữ trực tiếp `int[] scores` được truyền vào constructor. Caller sửa `scores[0]=-1` sau đó. Tại sao `private final int[]` không ngăn điều này?

**Câu 7 — Getter.** `List<String> getTags() { return tags; }` có thể làm lộ đường sửa nào? Khi nào `List.copyOf(tags)` hữu ích và hạn chế của nó là gì?

**Câu 8 — Kiểu exception.** Khi nhận tham số `amount=-3` và khi object đã `CLOSED` nhưng caller gọi `edit`, hai trường hợp thường thuộc loại lỗi nào?

**Câu 9 — Kế thừa.** Vì sao một lớp cho phép subclass override phương thức kiểm tra/cập nhật phải đặt hợp đồng chặt hơn lớp `final`?

**Câu 10 — Concurrency.** Hai thread cùng bán hàng trên một object. Tại sao cả hai cùng vượt qua `if (amount <= quantity)` không chứng minh tổng số đã bán là hợp lệ?

**Câu 11 — Immutable object.** Nếu có `record Temperature(int celsius)` với invariant, vì sao `warmerBy` nên tạo giá trị mới qua constructor đã kiểm tra? Caller giữ kết quả thế nào?

**Câu 12 — Phân tầng.** “Mã hàng là duy nhất trong database” có phải chỉ dùng constructor để bảo đảm được không? Nên đặt ràng buộc ở đâu?

### Đáp án tham khảo

1. Constructor và **mọi thao tác cập nhật** cần bảo vệ `balance>=0`; `deposit` kiểm tra số tiền dương/tràn, `withdraw` kiểm tra đủ số dư, `setBalance` nếu tồn tại phải không âm.
2. Kiểm tra `name != null`, `!name.isBlank()` và `stock>=0` trước khi chấp nhận trạng thái; áp dụng lại tại mọi đường sửa tương ứng.
3. Vì `sell` phụ thuộc cả tham số và lượng tồn hiện tại; phải từ chối và giữ tồn 5.
4. Phép cộng `int` có thể tràn và trở thành giá trị sai; `Math.addExact` phát hiện tràn trước phép gán vào field.
5. `setStart(7)` riêng lẻ làm `start > end` khi `end` vẫn 5; dùng `moveTo(7,9)` kiểm tra cặp rồi cập nhật.
6. Field giữ tham chiếu tới **cùng mảng**; `final` không khóa phần tử. Dùng clone/copy và sao chép khi trả ra nếu cần.
7. Caller có thể `add`/`clear` list nội bộ mà không qua validation; `List.copyOf` giúp tạo danh sách không hỗ trợ sửa, nhưng không deep-copy phần tử mutable.
8. Tham số sai thường là `IllegalArgumentException`; thao tác sai theo trạng thái object thường là `IllegalStateException`.
9. Vì subclass có thể thay đổi cách thực thi và phá invariant; cần hợp đồng override rõ, hoặc `final` cho các thao tác không được thay đổi.
10. Chuỗi đọc–kiểm tra–ghi không tự nguyên tử giữa các thread; cần lock hoặc cập nhật atomic phù hợp.
11. Constructor kiểm tra lại invariant ở mọi giá trị mới; caller muốn áp dụng thì gán `current=current.warmerBy(delta)`, còn object cũ không bị sửa.
12. Không. Cần kiểm tra ở tầng nghiệp vụ và ràng buộc unique/giao dịch phù hợp trong kho dữ liệu bền vững.

## 24. Tài liệu đối chiếu

- [Java Language Specification 17, §8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): trường instance, `private`, `final` và quy tắc khai báo.
- [Java Language Specification 17, §8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructor và thiết lập object.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): ngữ nghĩa tạo instance.
- [Java SE 17 API — Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(int,int)): phát hiện tràn khi cộng số nguyên.
- [Java SE 17 API — String.isBlank](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#isBlank()): xác định chuỗi rỗng hoặc chỉ chứa khoảng trắng.
- [Java SE 17 API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): danh sách không hỗ trợ sửa và ý nghĩa sao chép.
- [Java Language Specification 17, §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): memory model và các yêu cầu đồng bộ khi chia sẻ mutable state.

**Ghi nhớ:** đóng gói hiệu quả bảo vệ invariant ở **hai thời điểm bắt buộc**: **khởi tạo** và **mọi cập nhật**. Giữ field private, kiểm tra cả tham số lẫn **trạng thái kết quả**, xác thực toàn bộ trước khi gán, bảo vệ dữ liệu mutable qua tham chiếu và kiểm thử rằng thao tác thất bại **không làm hỏng object**. Nếu có nhiều luồng hoặc giao dịch nhiều đối tượng, phải bổ sung cơ chế nhất quán phù hợp; riêng validation trong một phương thức không đủ.
