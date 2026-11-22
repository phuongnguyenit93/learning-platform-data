# Điều kiện đầu vào, điều kiện đầu ra và tác dụng phụ của phương thức trong Java

Một phương thức Java có thể nhận dữ liệu, tính toán, trả về kết quả và làm thay đổi trạng thái trong lúc thực thi. Để sử dụng đúng một phương thức, chỉ biết tên và kiểu dữ liệu trong chữ ký là chưa đủ: người gọi còn cần biết **điều kiện đầu vào** (*precondition*), **điều kiện đầu ra** (*postcondition*) và **tác dụng phụ** (*side effect*). Ba khái niệm này tạo thành phần quan trọng của **hợp đồng phương thức** (*method contract*).

Bài học sử dụng Java 17 trở lên và tập trung vào cách thiết kế, cài đặt, sử dụng và kiểm tra hợp đồng của một phương thức. Các ví dụ có chương trình chạy độc lập và kết quả được giải thích theo thứ tự thực thi.

## 1. Một phương thức có “hợp đồng” gì?

Xét yêu cầu “giữ trước một số lượng hàng còn trong kho”. Ta có thể mô tả phương thức bằng lời:

- **Đầu vào:** số lượng cần giữ là số nguyên dương, không vượt lượng hàng hiện có.
- **Đầu ra khi thành công:** phương thức trả về số lượng còn có thể bán.
- **Tác dụng phụ:** giảm lượng hàng còn bán được, tăng lượng hàng đã giữ.
- **Khi đầu vào không hợp lệ:** từ chối thao tác bằng ngoại lệ và giữ nguyên trạng thái tồn kho.

Bản mô tả trên bổ sung ý nghĩa mà chữ ký sau không thể hiện hết:

~~~java
int reserve(int quantity)
~~~

Chữ ký cho biết phương thức tên `reserve` nhận `int` và trả `int`; nó **không tự nói rõ** `quantity` có phải dương không, số tồn kho có thay đổi không, hay lỗi sẽ được xử lý thế nào.

Một cách ghi nhớ:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Điều kiện đầu vào | Điều gì phải đúng khi **bắt đầu** lời gọi? | `quantity > 0`, `quantity <= available` |
| Điều kiện đầu ra | Điều gì được đảm bảo **sau khi kết thúc bình thường**? | Trả về số lượng hàng còn lại, không âm |
| Tác dụng phụ | Ngoài giá trị trả về, trạng thái hay môi trường nào bị ảnh hưởng? | Hai trường `available`, `reserved` đổi giá trị |
| Hành vi khi thất bại | Lỗi gì xảy ra, dữ liệu có còn nguyên không? | Ném `IllegalArgumentException`, không đổi số tồn |

**Quan trọng:** điều kiện đầu ra thường chỉ được bảo đảm trong những trường hợp hợp đồng quy định, chẳng hạn khi đầu vào hợp lệ và phương thức **hoàn thành bình thường**. Phải phân biệt trạng thái sau thành công với trạng thái sau khi ném ngoại lệ; không phải mọi phương thức Java đều tự động “rollback” khi gặp lỗi.

## 2. Điều kiện đầu vào (precondition)

**Precondition** là yêu cầu người gọi hoặc hệ thống phải thỏa trước khi phương thức thực hiện công việc được hứa hẹn. Ví dụ:

~~~java
double divide(double numerator, double denominator) {
    if (denominator == 0.0) {
        throw new IllegalArgumentException("Mẫu số không được bằng 0");
    }
    return numerator / denominator;
}
~~~

*Đây là đoạn phương thức nằm trong một lớp; không phải chương trình độc lập.* Hợp đồng của ví dụ quy định `denominator != 0.0`. Java cho phép phép chia dấu phẩy động cho 0 tạo `Infinity` hoặc `NaN` theo trường hợp, nhưng **chính phương thức này** lựa chọn từ chối đầu vào có mẫu số bằng 0.

Precondition có thể liên quan đến:

1. **Giới hạn giá trị:** số lượng dương, tuổi không âm, chỉ số nằm trong khoảng hợp lệ.
2. **Nullability:** tham chiếu bắt buộc khác `null`, như `Objects.requireNonNull(path)`.
3. **Định dạng và ngữ nghĩa:** mã hàng không rỗng, chuỗi có dạng phù hợp, giá trị thuộc tập cho phép.
4. **Trạng thái hiện tại của đối tượng:** hàng còn đủ để đặt chỗ, đối tượng đã được mở, tài nguyên chưa đóng.
5. **Quan hệ giữa các tham số:** `start <= end`, kích thước dữ liệu tương thích với giới hạn cho phép.

### Ai chịu trách nhiệm bảo đảm precondition?

Người gọi có trách nhiệm **cung cấp đầu vào đáp ứng hợp đồng**. Người viết phương thức nên bảo vệ các quy tắc quan trọng bằng kiểm tra ở biên công khai phù hợp, nhất là khi đầu vào có thể đến từ bên ngoài.

Ví dụ:

~~~java
static int percent(int part, int total) {
    if (total <= 0) {
        throw new IllegalArgumentException("Tổng phải dương");
    }
    if (part < 0 || part > total) {
        throw new IllegalArgumentException("Phần phải nằm trong [0, tổng]");
    }
    return (int) ((100L * part) / total);
}
~~~

*Đây là đoạn phương thức minh họa, chưa có `main`.* Phép nhân `100L * part` sử dụng `long` để tránh tràn số trong phạm vi số nguyên `int` không âm đã được kiểm tra; phép chia nguyên thực hiện làm tròn về 0, ở đây tương đương lấy phần nguyên. Hợp đồng cần làm rõ cách làm tròn này nếu nó quan trọng với bên gọi.

Không nên chỉ kiểm tra precondition tại một màn hình nhập liệu rồi bỏ mặc phương thức xử lý: cùng phương thức có thể được gọi từ kiểm thử, API, batch job hoặc một phần chương trình khác.

### Chọn cách từ chối đầu vào

Trong Java, lựa chọn thường gặp là:

- `IllegalArgumentException`: giá trị đối số không hợp lệ theo hợp đồng.
- `NullPointerException` hoặc `Objects.requireNonNull(...)`: đối số bắt buộc khác `null`.
- `IllegalStateException`: **trạng thái đối tượng** không cho phép thực hiện thao tác, dù tham số có thể hợp lệ.
- Giá trị kết quả như `boolean`, `Optional<T>` hoặc một kiểu kết quả miền nghiệp vụ: khi “không tìm thấy” hoặc “không thể thực hiện” là một tình huống **bình thường** được thiết kế trong API, thay vì lỗi sử dụng hợp đồng.

Không có quy tắc rằng mọi đầu vào không đáp ứng yêu cầu đều phải dùng đúng một loại ngoại lệ. Điều quan trọng là API có **hợp đồng rõ ràng và nhất quán** để bên gọi biết cách xử lý.

## 3. Điều kiện đầu ra (postcondition)

**Postcondition** mô tả điều phương thức bảo đảm **khi đã thực hiện xong theo đường thành công**. Nó bao gồm cả kết quả trả về và trạng thái quan sát được nếu phương thức cho phép thay đổi dữ liệu.

Ví dụ với tồn kho:

~~~text
Trước reserve(4):
    available = 10
    reserved  = 0

Sau reserve(4) thành công:
    available = 6
    reserved  = 4
    return    = 6
~~~

Viết bằng ký hiệu ngắn, đặt `old(x)` là giá trị **trước khi gọi**:

~~~text
pre:  quantity > 0
      quantity <= old(available)

post: available == old(available) - quantity
      reserved  == old(reserved) + quantity
      result    == available
~~~

Các dòng này là **đặc tả minh họa**, không phải cú pháp Java được compiler thực thi. Java không có từ khóa `old` trong mã nguồn thông thường.

### Postcondition khác kiểu trả về như thế nào?

`int reserve(int quantity)` chỉ buộc kết quả trả về có kiểu tương thích với `int`. Nó không buộc kết quả phải bằng số hàng còn lại. Lời hứa `return == available` là **quy tắc nghiệp vụ** do tác giả phương thức định nghĩa, triển khai, kiểm thử và ghi trong tài liệu.

Nếu một phương thức trả `void`, nó vẫn có thể có postcondition:

~~~java
void reset() {
    count = 0;
}
~~~

Đây là đoạn phương thức trong một lớp có trường `count`; hợp đồng sau thành công là `count == 0`, dù **không có giá trị trả về**.

Một phương thức chỉ đọc cũng có postcondition mà không sửa trạng thái: ví dụ `size()` trả đúng số phần tử quan sát được tại thời điểm đọc. Cần tránh hứa rằng một giá trị vẫn giữ nguyên mãi sau khi phương thức trả về nếu đối tượng có thể bị luồng khác thay đổi.

## 4. Tác dụng phụ (side effect)

**Side effect** là thay đổi có thể quan sát được ngoài việc đơn thuần trả một giá trị cho người gọi. Trong Java, các ví dụ phổ biến:

| Hành vi | Có tác dụng phụ? | Giải thích |
| --- | --- | --- |
| `return a + b;` với hai `int` | Không, nếu không có thao tác khác | Chỉ tính và trả giá trị |
| `this.balance += amount;` | Có | Đổi trạng thái đối tượng nhận |
| `list.add(value);` | Có | Sửa đối tượng `List` mà bên gọi có thể đang giữ |
| `sharedCount++;` với trường `static` | Có | Đổi trạng thái dùng chung cấp lớp |
| `System.out.println(text);` | Có | Ghi ra luồng xuất |
| `Files.writeString(path, text);` | Có | Có thể thay đổi dữ liệu trên hệ thống tệp |
| Gửi HTTP request hoặc lưu database | Có thể có | Ảnh hưởng tài nguyên/hệ thống bên ngoài |
| `new StringBuilder("A")` chỉ để tính toán nội bộ | Thông thường không có tác dụng phụ quan sát được ở ngoài | Tạo object tạm riêng không đồng nghĩa sửa trạng thái bên ngoài |

Ngoại lệ có thể thay đổi luồng điều khiển và là một phần **kết cục** cần mô tả của phương thức. Tuy nhiên, việc ném một ngoại lệ không nhất thiết đã sửa dữ liệu; nếu trước lúc ném ngoại lệ có ghi field hoặc ghi tệp, các thay đổi đó có thể vẫn còn.

### Tham chiếu khiến side effect lan tới bên gọi

Java truyền đối số **theo giá trị**. Nếu đối số có kiểu tham chiếu, bản sao giá trị tham chiếu có thể trỏ đến **cùng object** với biến bên gọi. Vì vậy:

~~~java
static void addName(java.util.List<String> names) {
    names.add("An");
}
~~~

*Đây là đoạn phương thức minh họa, không có `main`.* Phương thức **không thể** làm biến `names` ở bên gọi tự đổi thành tham chiếu khác bằng phép gán lại tham số, nhưng **có thể** thay đổi đối tượng danh sách mà hai bên đang trỏ tới. Điều này là nguồn tác dụng phụ rất thường gặp.

Cần phân biệt:

- **Thay đổi biến tham số cục bộ:** `names = new ArrayList<>();` chỉ đổi biến `names` bên trong phương thức.
- **Thay đổi đối tượng được tham chiếu:** `names.add("An");` sửa chính danh sách đã được truyền vào nếu danh sách hỗ trợ sửa đổi.
- **Trả một đối tượng mutable:** người gọi có thể thay đổi đối tượng sau khi phương thức kết thúc; cần xem đây có phải dữ liệu nội bộ bị “lộ tham chiếu” hay không.

## 5. Ví dụ hoàn chỉnh: kiểm tra hợp đồng khi giữ hàng tồn kho

Ta tạo lớp `StockItem` để quản lý số lượng còn bán (`available`) và số lượng đã giữ (`reserved`). Một đối tượng đại diện một mã hàng. Trạng thái hợp lệ yêu cầu cả hai số lượng **không âm**.

Phương thức `reserve(quantity)` có hợp đồng:

- **Precondition:** `quantity > 0` và không vượt số hàng còn bán.
- **Postcondition khi thành công:** số hàng còn bán giảm đúng `quantity`, số đã giữ tăng đúng `quantity`, kết quả trả về là `available` mới.
- **Side effect:** thay đổi hai trường instance của đối tượng nhận.
- **Khi thất bại có kiểm soát:** ném `IllegalArgumentException` trước mọi cập nhật; hai trường không đổi.

Phương thức `release(quantity)` làm thao tác ngược lại, nhưng chỉ được giải phóng số lượng đã giữ thực sự tồn tại.

Tạo tệp **`MethodContractDemo.java`**:

~~~java
record StockSnapshot(String sku, int available, int reserved) {
}

class StockItem {
    private final String sku;
    private int available;
    private int reserved;

    StockItem(String sku, int initialAvailable) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Mã hàng không hợp lệ");
        }
        if (initialAvailable < 0) {
            throw new IllegalArgumentException("Số lượng không được âm");
        }
        this.sku = sku;
        this.available = initialAvailable;
        this.reserved = 0;
    }

    boolean canReserve(int quantity) {
        return quantity > 0 && quantity <= available;
    }

    int reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        if (quantity > available) {
            throw new IllegalArgumentException("Không đủ hàng");
        }

        available -= quantity;
        reserved += quantity;
        return available;
    }

    void release(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        if (quantity > reserved) {
            throw new IllegalArgumentException("Chưa giữ đủ hàng");
        }

        reserved -= quantity;
        available += quantity;
    }

    StockSnapshot snapshot() {
        return new StockSnapshot(sku, available, reserved);
    }
}

public class MethodContractDemo {
    public static void main(String[] args) {
        StockItem item = new StockItem("BOOK-01", 10);
        StockSnapshot before = item.snapshot();

        System.out.println("Trước: " + before);
        System.out.println("Có thể giữ 4: " + item.canReserve(4));

        int remaining = item.reserve(4);
        System.out.println("Giá trị trả về: " + remaining);
        System.out.println("Sau giữ: " + item.snapshot());

        try {
            item.reserve(7);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
        System.out.println("Sau lỗi: " + item.snapshot());

        item.release(2);
        System.out.println("Sau giải phóng: " + item.snapshot());
        System.out.println("Ảnh chụp cũ: " + before);
    }
}
~~~

Đứng trong thư mục chứa tệp, biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MethodContractDemo.java
java MethodContractDemo
~~~

Stdout chính xác:

~~~text
Trước: StockSnapshot[sku=BOOK-01, available=10, reserved=0]
Có thể giữ 4: true
Giá trị trả về: 6
Sau giữ: StockSnapshot[sku=BOOK-01, available=6, reserved=4]
Từ chối: Không đủ hàng
Sau lỗi: StockSnapshot[sku=BOOK-01, available=6, reserved=4]
Sau giải phóng: StockSnapshot[sku=BOOK-01, available=8, reserved=2]
Ảnh chụp cũ: StockSnapshot[sku=BOOK-01, available=10, reserved=0]
~~~

### Theo dõi trạng thái

| Thời điểm | `available` | `reserved` | Giải thích |
| --- | ---: | ---: | --- |
| Sau constructor | 10 | 0 | Trạng thái ban đầu hợp lệ |
| Sau `canReserve(4)` | 10 | 0 | Chỉ tính `boolean`, không sửa trạng thái |
| Sau `reserve(4)` | 6 | 4 | Thành công và trả `6` |
| Sau `reserve(7)` | 6 | 4 | Ném ngoại lệ trước phép cập nhật |
| Sau `release(2)` | 8 | 2 | Chuyển 2 đơn vị từ đã giữ về còn bán |

Trong mọi thao tác `reserve`/`release` **thành công** của mô hình tuần tự này, tổng `available + reserved` giữ nguyên. Constructor bắt đầu với tổng không vượt `Integer.MAX_VALUE`; do chuyển số lượng giữa hai nhóm với kiểm tra biên, phép cộng trong các thao tác này không bị tràn khi trạng thái chỉ được tạo và cập nhật bằng chính API đã định nghĩa.

`StockSnapshot` là **record** của Java 17. Các component trong ví dụ gồm một `String` bất biến và hai `int`, nên đối tượng snapshot không bị sửa khi `StockItem` đổi trạng thái về sau. Đây là lý do dòng “Ảnh chụp cũ” vẫn in số liệu ban đầu. Nếu record chứa `List` mutable, record không tự tạo bản sao sâu cho danh sách đó.

### Tại sao thứ tự kiểm tra quan trọng?

Trong `reserve`, mọi kiểm tra đều đứng **trước** hai phép cập nhật:

~~~java
available -= quantity;
reserved += quantity;
~~~

Nếu đầu vào không hợp lệ, phương thức ném ngoại lệ trước khi chạm vào trạng thái. Đây là bảo đảm hữu ích của API hiện tại. Nếu đảo thứ tự và trừ `available` trước rồi mới kiểm tra số tồn, thất bại có thể làm đối tượng rơi vào trạng thái sai.

**Giới hạn:** hai phép gán ở đây không phải một giao dịch nguyên tử trong chương trình có nhiều luồng hoặc cơ sở dữ liệu. Nếu hai luồng cùng sửa một `StockItem`, cần thêm cơ chế bảo vệ đồng thời; nếu chuyển sang dữ liệu lưu trữ bền vững, cần thiết kế giao dịch tương ứng.

## 6. Postcondition và invariant khác nhau thế nào?

**Postcondition** nói về kết quả của **một lời gọi**; **invariant** nói về quy tắc phải được duy trì đối với trạng thái hợp lệ của object.

Trong `StockItem`:

- **Invariant:** `available >= 0`, `reserved >= 0`.
- **Postcondition của `reserve(q)`:** `available` mới bằng `available` cũ trừ `q`, `reserved` mới bằng `reserved` cũ cộng `q`, kết quả trả về bằng `available` mới.
- **Postcondition của `release(q)`:** `reserved` mới bằng `reserved` cũ trừ `q`, `available` mới bằng `available` cũ cộng `q`.
- **Postcondition của `canReserve(q)`:** trả `true` đúng khi `q > 0` và `q <= available`; không thay đổi trạng thái.

Trong bài này, `canReserve` được cố ý thiết kế để nhận cả số không dương và trả `false` thay vì ném ngoại lệ, trong khi `reserve` coi yêu cầu không dương là **vi phạm hợp đồng**. Hai phương thức có mục đích khác nhau nên hành vi với cùng dữ liệu đầu vào không bắt buộc giống nhau, miễn được ghi rõ.

Đừng mặc định precondition chỉ liên quan tham số. Ví dụ phương thức `close()` có thể yêu cầu tài nguyên đang mở; nếu trạng thái đã đóng, ngay cả khi phương thức không có tham số vẫn có thể không được gọi tiếp theo hợp đồng.

## 7. Thiết kế phương thức không có tác dụng phụ: pure function

Một **hàm thuần (pure function)** theo nghĩa thông dụng sẽ cho cùng kết quả với cùng đầu vào và không gây tác dụng phụ quan sát được. Trong Java, nhiều `static` method hữu ích có thể viết theo kiểu này:

~~~java
static int shippingFee(int distanceKm, int feePerKm) {
    if (distanceKm < 0 || feePerKm < 0) {
        throw new IllegalArgumentException("Giá trị không được âm");
    }
    return Math.multiplyExact(distanceKm, feePerKm);
}
~~~

*Đây là khai báo phương thức minh họa đặt trong một lớp, chưa có `main`.* Với hai đầu vào hợp lệ, phương thức chỉ tính và trả kết quả; không thay đổi field, tham số hay môi trường bên ngoài. `Math.multiplyExact` ném `ArithmeticException` nếu phép nhân `int` vượt miền biểu diễn; điều kiện đầu vào “không âm” **không đảm bảo** phép nhân luôn vừa kiểu `int`.

Lợi ích khi hạn chế side effect:

- Dễ suy luận kết quả và kiểm thử với bảng đầu vào/đầu ra.
- Dễ tái sử dụng vì không phụ thuộc trạng thái ẩn.
- Dễ kết hợp trong các phép tính khác mà không lo thay đổi object ngoài ý muốn.
- Trong nhiều tình huống, giảm phần trạng thái phải bảo vệ khi chạy đồng thời.

Tuy nhiên, chương trình thực tế vẫn cần thao tác có tác dụng phụ như cập nhật giỏ hàng, ghi tệp hoặc gửi dữ liệu. Mục tiêu là **định nghĩa rõ ràng, giới hạn và kiểm soát side effect**, không phải loại bỏ chúng bằng mọi giá.

Một phương thức `static` **không mặc nhiên thuần**: nó vẫn có thể sửa trường `static`, danh sách được truyền vào, hoặc ghi tệp. Tương tự, một instance method có thể chỉ đọc trường và trả kết quả mà không gây thay đổi, ví dụ `snapshot()` trong ví dụ trên (đối với trạng thái `StockItem`; nó tạo một đối tượng kết quả mới).

## 8. Ví dụ thứ hai: tác dụng phụ trên tham số mutable

Nhiều lỗi thực tế xuất hiện vì phương thức sửa đối tượng do người gọi truyền vào, dù chữ ký trông như một hàm tiện ích.

Tạo tệp độc lập **`SideEffectDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SideEffectDemo {
    static void sortInPlace(List<String> names) {
        Collections.sort(names);
    }

    static List<String> sortedCopy(List<String> names) {
        List<String> copy = new ArrayList<>(names);
        Collections.sort(copy);
        return copy;
    }

    public static void main(String[] args) {
        List<String> original = new ArrayList<>(List.of("Binh", "An"));

        List<String> result = sortedCopy(original);
        System.out.println("Bản gốc: " + original);
        System.out.println("Bản sao: " + result);

        sortInPlace(original);
        System.out.println("Sau sửa tại chỗ: " + original);
    }
}
~~~

~~~bash
javac -encoding UTF-8 SideEffectDemo.java
java SideEffectDemo
~~~

Stdout:

~~~text
Bản gốc: [Binh, An]
Bản sao: [An, Binh]
Sau sửa tại chỗ: [An, Binh]
~~~

**`sortInPlace`** có tác dụng phụ: sửa thứ tự của chính danh sách mà bên gọi đã truyền vào. Hợp đồng nên nói rõ danh sách phải **mutable** và hỗ trợ `set`/thay đổi phần tử cần thiết để sắp xếp; nếu truyền danh sách bất biến hoặc không hỗ trợ thao tác, phương thức có thể thất bại.

**`sortedCopy`** tạo một danh sách mới bằng `new ArrayList<>(names)`, rồi sắp xếp bản sao. Nó không thay đổi thứ tự của danh sách đầu vào và trả về danh sách kết quả. Vì danh sách chứa `String` bất biến, việc sao chép phần tử không phát sinh vấn đề chia sẻ mutable element trong ví dụ. Với `List<MutableObject>`, bản sao danh sách là **shallow copy**: các phần tử đối tượng vẫn có thể được chia sẻ.

### Chọn API nào?

Nếu mục đích là **sửa dữ liệu bên gọi**, tên như `sortInPlace`, tài liệu “modifies the input list” và kiểu trả `void` thể hiện ý đồ tương đối rõ. Nếu mục đích là trả một thứ tự mới mà không làm thay đổi dữ liệu đầu vào, `sortedCopy` có hợp đồng phù hợp hơn. Trong cả hai trường hợp, kiểm tra `null` và quy tắc thứ tự cần được làm rõ ở API thực tế.

## 9. Phân biệt kết quả trả về, dữ liệu đầu ra và tác dụng phụ

Không phải mọi “đầu ra” đều nằm ở `return`.

~~~java
static int twice(int value) {
    return value * 2;
}

static void announce(int value) {
    System.out.println(value);
}
~~~

Đây là hai phương thức minh họa, không phải chương trình độc lập:

- `twice(3)` **trả về** `6`; bên gọi có thể gán `int result = twice(3);`. Việc nhân `int` có thể tràn khi giá trị lớn; muốn hợp đồng tính toán chính xác phải xử lý điều này.
- `announce(3)` **in** `3` ra stdout nhưng có kiểu trả về `void`. Bên gọi không thể viết `int result = announce(3);`.

Đầu ra còn có thể là thay đổi vào một object được truyền vào, một tệp được ghi, một sự kiện được gửi hoặc một trạng thái được lưu trong cơ sở dữ liệu. Nếu API có những tác dụng phụ đó, tài liệu cần mô tả rõ: dữ liệu nào được sửa, có thể xảy ra lỗi nào, và dữ liệu sau lỗi có được bảo toàn không.

Một phương thức trả về một `List` không mặc nhiên là thuần; nó có thể vừa cập nhật cơ sở dữ liệu vừa trả một danh sách. Ngược lại, một phương thức trả `void` không tự chứng minh nó có side effect; phương thức rỗng `void noop() {}` không làm gì quan sát được.

## 10. Cách ghi hợp đồng bằng Javadoc

Javadoc giúp người đọc biết điều kiện sử dụng và bảo đảm sau lời gọi. Ví dụ sau là **đoạn mã dùng bên trong lớp `StockItem`**, thay cho tài liệu đặt trước phương thức `reserve`:

~~~java
/**
 * Giữ hàng cho một yêu cầu.
 *
 * @param quantity số lượng phải dương và không vượt số hàng còn bán
 * @return số lượng hàng còn bán sau khi giữ thành công
 * @throws IllegalArgumentException nếu quantity không hợp lệ
 *
 * Side effect: available giảm quantity và reserved tăng quantity.
 * Khi bị từ chối vì dữ liệu không hợp lệ, trạng thái giữ nguyên.
 */
int reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Số lượng phải dương");
    }
    if (quantity > available) {
        throw new IllegalArgumentException("Không đủ hàng");
    }
    available -= quantity;
    reserved += quantity;
    return available;
}
~~~

`@param`, `@return`, `@throws` là thẻ Javadoc thông dụng. Dòng giải thích “Side effect” ở đây là văn bản tài liệu bình thường, không phải từ khóa được Java tự kiểm tra.

Có thể dùng `@throws` nhiều lần nếu cần tài liệu hóa các loại exception khác nhau. Nếu một phương thức trả `void`, thường không cần `@return`. Khi contract phức tạp hơn, hãy mô tả thêm trường hợp thất bại, tình trạng tài nguyên, ownership của dữ liệu và khả năng sử dụng đồng thời.

Javadoc không phải cơ chế thực thi hợp đồng. Compiler chủ yếu kiểm tra cú pháp, kiểu, quyền truy cập và những quy tắc ngôn ngữ; điều kiện kiểu `quantity > 0` cần kiểm tra trong code hoặc được bảo đảm bằng thiết kế kiểu/API, và cần kiểm thử.

## 11. Xác minh precondition, postcondition và side effect

Một bộ kiểm tra hữu ích phải xác nhận **cả giá trị trả về lẫn trạng thái đối tượng**, không chỉ kiểm tra rằng phương thức không ném lỗi.

Với `StockItem("BOOK-01", 10)`, các trường hợp chính là:

| Trường hợp | Kết quả mong đợi | Trạng thái sau |
| --- | --- | --- |
| `canReserve(4)` | `true` | Vẫn 10 còn bán, 0 đã giữ |
| `reserve(4)` | Trả `6` | 6 còn bán, 4 đã giữ |
| `reserve(0)` ngay sau đó | `IllegalArgumentException` | Vẫn 6 và 4 |
| `reserve(7)` ngay sau đó | `IllegalArgumentException` | Vẫn 6 và 4 |
| `release(2)` sau đó | Hoàn tất bình thường | 8 còn bán, 2 đã giữ |
| `release(3)` sau đó | `IllegalArgumentException` | Vẫn 8 và 2 |

Nếu kiểm thử JUnit, những phép kiểm tra tương ứng có thể dùng `assertEquals`, `assertThrows` và so sánh snapshot **trước/sau**. Với ví dụ đơn giản, một đoạn chương trình `main` in kết quả cũng giúp học, nhưng kiểm thử tự động nên so sánh điều kiện được hứa hẹn thay vì dựa duy nhất vào quan sát console.

Đặc biệt cần kiểm tra **giá trị biên**: `0`, `1`, đúng bằng số hiện có, lớn hơn số hiện có một đơn vị, `null`, chuỗi trắng và các giá trị gần `Integer.MAX_VALUE` hoặc `Long.MAX_VALUE` nếu có phép tính liên quan.

### Kiểm tra tính chất bằng đối chiếu trạng thái cũ

Với trạng thái trước là `(a, r)` và `0 < q <= a`, một phép gọi `reserve(q)` thành công phải cho:

~~~text
newAvailable == a - q
newReserved  == r + q
result       == newAvailable
newAvailable >= 0
newReserved  >= 0
~~~

Đây là **đặc tả kiểm tra**, không phải mã Java độc lập. Bài kiểm thử có thể chụp snapshot trước, gọi phương thức, rồi chụp snapshot sau để đối chiếu từng điều kiện. Nếu thao tác thất bại theo trường hợp được quy định “không đổi trạng thái”, cần so sánh cả hai trường trước và sau ngoại lệ.

## 12. Lưu ý: ngoại lệ không mặc định hoàn tác tác dụng phụ

Hãy xem đoạn phương thức **cố ý có thiết kế lỗi**:

~~~java
void unsafeReserve(int quantity) {
    available -= quantity;
    if (available < 0) {
        throw new IllegalArgumentException("Không đủ hàng");
    }
    reserved += quantity;
}
~~~

Đoạn này giả định đặt trong lớp có trường `available`, `reserved`; **không nên dùng làm API thực tế**. Nếu `available = 6` và gọi `unsafeReserve(7)`, câu lệnh đầu tiên làm `available = -1`, rồi phương thức ném ngoại lệ. Ngoại lệ **không tự đặt available trở về 6**.

Ngay cả khi kiểm tra đầu vào trước, một phương thức có nhiều thao tác ghi tệp, gọi API hoặc lưu DB vẫn có thể thất bại **giữa các tác dụng phụ**. Vì thế cần phân biệt:

- **Bảo đảm cơ bản:** các invariant còn được duy trì sau lỗi, nhưng một phần trạng thái có thể đổi.
- **Bảo đảm mạnh:** thao tác thất bại thì trạng thái quan sát được được giữ như trước khi gọi.
- **Bảo đảm giao dịch:** nhóm thay đổi được thực hiện/hoàn tác theo cơ chế transaction tương ứng; trong hệ thống phân tán còn phải xác định ranh giới, tính nhất quán và cách xử lý lỗi.

Đây là các mức **bảo đảm do thiết kế cài đặt**, không phải ba chế độ mà Java tự cấp cho mọi phương thức. Với `reserve` trong ví dụ, các precondition được kiểm tra trước phép gán nên những lỗi đầu vào đã nêu được xử lý mà không đổi trạng thái, trong bối cảnh tuần tự và không có sửa field từ bên ngoài.

## 13. Dữ liệu mutable, sao chép phòng vệ và bảo đảm đầu ra

Nếu muốn một phương thức chỉ cung cấp **thông tin**, cần cân nhắc việc nó trả về tham chiếu tới dữ liệu nội bộ. Ví dụ lớp có `private final List<String> names;`, phương thức sau không tạo bản sao:

~~~java
List<String> names() {
    return names;
}
~~~

Đây là đoạn trong lớp minh họa, không thể biên dịch độc lập. Nếu `names` là danh sách có thể sửa và người gọi có quyền truy cập được tham chiếu, họ có thể viết `object.names().clear()` để thay đổi dữ liệu nội bộ mà không đi qua phương thức cập nhật dự kiến.

Một lựa chọn cho dữ liệu cần đọc là:

~~~java
List<String> namesSnapshot() {
    return List.copyOf(names);
}
~~~

`List.copyOf` trả một danh sách **không hỗ trợ sửa qua API** và không chấp nhận phần tử `null`. Nó chụp các tham chiếu phần tử tại thời điểm gọi, **không tự sao chép sâu** các object mutable bên trong. Nếu hợp đồng cần ảnh chụp độc lập của những object con có thể sửa, phải cân nhắc sao chép sâu hoặc dùng kiểu giá trị bất biến.

Vấn đề tương tự tồn tại ở chiều **đầu vào**: lưu trực tiếp một `List` do người gọi truyền vào constructor khiến bên gọi có thể sửa list sau này và tác động lên trạng thái của object chứa list. Quyền sở hữu tham chiếu nên được ghi rõ trong hợp đồng.

## 14. Nhiều luồng làm phức tạp hợp đồng

Trong ví dụ đơn luồng, `canReserve(4)` trả `true` rồi `reserve(4)` có thể thành công nếu không có thao tác nào xen vào. Với nhiều luồng, **kiểm tra trước không đảm bảo thao tác sau vẫn hợp lệ** nếu một luồng khác đã thay đổi tồn kho.

~~~text
Luồng A: canReserve(4) -> true
Luồng B: reserve(8)    -> success
Luồng A: reserve(4)    -> có thể bị từ chối vì hết hàng
~~~

Dòng trên là kịch bản khái niệm khi trạng thái ban đầu đủ hàng cho một trong hai lần giữ, không phải kết quả thực thi chính xác của code hiện tại khi truy cập không đồng bộ. Lớp `StockItem` **chưa thread-safe**: nếu dùng chung qua nhiều luồng, lỗi data race có thể khiến phép kiểm tra và phép cập nhật không còn đáng tin. Muốn minh họa kịch bản thật phải dùng phiên bản đã bảo vệ thao tác truy cập đồng thời bằng cơ chế thích hợp.

Trong thiết kế đồng thời cần xác định lại:

- Điều kiện đầu vào được kiểm tra **ở thời điểm nào**?
- Thao tác đọc–kiểm tra–ghi có được thực hiện **như một bước nguyên tử** không?
- Giá trị trả về phản ánh trạng thái nào, tại thời điểm nào?
- Bảo đảm sau thành công có còn đúng dưới các thao tác đồng thời không?

Đây là lý do contract của phương thức thao tác dữ liệu chia sẻ không thể chỉ ghi “đọc rồi ghi”; cần nêu rõ trách nhiệm đồng bộ và nhất quán khi phạm vi ứng dụng yêu cầu.

## 15. Sai lầm thường gặp

| Hiểu nhầm | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “Kiểu `int` nghĩa là đầu vào nào cũng hợp lệ” | Truyền 0, số âm, vượt giới hạn nghiệp vụ | Precondition thường chặt hơn kiểu Java |
| “`return` nói hết mọi đầu ra” | Bỏ sót việc cập nhật field, list, tệp | Xem thêm side effect và trạng thái sau |
| “Phương thức `void` không có kết quả” | Quên mô tả thay đổi trạng thái | `void` vẫn có thể có postcondition |
| “Ném exception là dữ liệu tự trở lại như cũ” | Đối tượng bị thay đổi dở dang | Kiểm tra và chuẩn bị trước khi cập nhật, hoặc dùng cơ chế hoàn tác thích hợp |
| “Phương thức `static` luôn thuần” | Không thấy thay đổi biến static hoặc tài nguyên chung | Tính thuần phụ thuộc toàn bộ hành vi, không phụ thuộc chữ `static` |
| “Dùng `final` cho tham số sẽ làm object bất biến” | Vẫn sửa được list/đối tượng mutable | `final` chỉ ngăn gán lại biến tham số |
| “Trả `List` chỉ cho phép bên gọi đọc” | Bên gọi sửa collection nội bộ | Cân nhắc bản sao, immutable view và quyền sở hữu dữ liệu |
| “Kiểm tra điều kiện ở ngoài một lần là đủ” | Trạng thái có thể thay đổi trước lúc thao tác | Kiểm tra tại điểm áp dụng quy tắc và đồng bộ khi cần |
| “Đầu vào sai chỉ cần xử lý bằng `System.out.println`” | Bên gọi không biết thao tác thất bại một cách có cấu trúc | Thiết kế exception/giá trị kết quả rõ ràng |
| “Không ném lỗi nghĩa là postcondition đúng” | Logic sai có thể trả hoặc lưu kết quả sai | Kiểm thử cả kết quả trả về và trạng thái quan sát được |

## 16. Quy trình thiết kế một phương thức có hợp đồng rõ ràng

Trước khi viết code cho một phương thức mới, hãy thực hiện tuần tự:

1. **Nêu mục đích:** ví dụ “giữ số lượng hàng còn bán” thay vì một tên chung chung `update`.
2. **Xác định đầu vào:** kiểu dữ liệu, `null` có được phép không, miền giá trị và những điều kiện gắn với trạng thái hiện tại.
3. **Xác định thành công:** kết quả trả về và trạng thái nào phải thay đổi (hoặc phải giữ nguyên).
4. **Xác định tác dụng phụ:** field, collection, tệp, console, database, network hoặc đối tượng được truyền vào.
5. **Xác định thất bại:** các tình huống lỗi, loại ngoại lệ/kiểu kết quả và mức bảo toàn trạng thái.
6. **Viết code để kiểm tra trước khi thay đổi:** chuẩn bị các giá trị có thể gây lỗi trước những cập nhật khó hoàn tác.
7. **Ghi lại hợp đồng:** dùng tên rõ nghĩa, Javadoc, kiểu dữ liệu phù hợp và các ràng buộc truy cập.
8. **Kiểm thử biên và ngoại lệ:** so sánh giá trị trả về, trạng thái trước/sau và các tác dụng phụ quan sát được.
9. **Xem xét đồng thời:** nếu có khả năng nhiều luồng cùng thao tác, bảo vệ quy tắc theo cơ chế đúng.

Một câu hỏi rất hữu ích khi review mã: **“Nếu phương thức này bị từ chối ở dòng cuối, những gì đã thay đổi trước đó?”** Câu trả lời giúp phát hiện rủi ro side effect không được kiểm soát.

## 17. Bài tập tự luyện

**Bài 1 — Xác định hợp đồng.** Cho phương thức:

~~~java
int withdraw(int amount) {
    if (amount <= 0 || amount > balance) {
        throw new IllegalArgumentException("Không thể rút");
    }
    balance -= amount;
    return balance;
}
~~~

Giả định đây là một phương thức instance trong lớp có trường `int balance` được giữ không âm. Hãy nêu precondition, postcondition khi thành công, side effect và hành vi khi thất bại.

**Bài 2 — Pure hay có side effect?** Phân loại `int doubleValue(int x) { return x * 2; }`, `void add(List<String> xs) { xs.add("A"); }` và `String upper(String x) { return x.toUpperCase(); }` (với đầu vào không `null`). Một phương thức có thể không sửa object nhưng vẫn không thuần nếu đọc thời gian hiện tại hay trạng thái ngoài không?

**Bài 3 — Phát hiện bug.** Cho code:

~~~java
void give(int quantity) {
    reserved -= quantity;
    if (quantity <= 0 || reserved < 0) {
        throw new IllegalArgumentException();
    }
    available += quantity;
}
~~~

Chỉ ra điều gì sai về thứ tự kiểm tra và trạng thái khi thất bại. Viết lại sao cho kiểm tra `quantity > 0` và `quantity <= reserved` **trước** khi cập nhật.

**Bài 4 — Danh sách truyền vào.** Nếu một phương thức gọi `Collections.sort(list)` trên `list` nhận từ tham số, thay đổi có xuất hiện ở bên gọi không? Nếu thay bằng tạo `new ArrayList<>(list)` rồi sort bản sao, điều gì khác?

**Bài 5 — Snapshot.** Tại sao `StockSnapshot before = item.snapshot()` trong ví dụ vẫn có số lượng cũ sau khi `item.reserve(4)`? Nếu snapshot chứa một danh sách mutable do item cũng giữ, bảo đảm độc lập còn đúng hoàn toàn không?

**Gợi ý đối chiếu:**

1. Precondition: `0 < amount <= balance`; sau thành công `balance` giảm `amount`, kết quả trả về là số dư mới; side effect là đổi trường `balance`; nếu đầu vào sai, ném ngoại lệ trước cập nhật.
2. Nhân đôi `int` và chuyển hoa `String` là phép tính không gây side effect trong ví dụ; thêm vào `List` thì có. Đọc thời gian/trạng thái biến đổi bên ngoài có thể làm kết quả không ổn định dù không ghi dữ liệu.
3. Phép trừ `reserved` đã thực hiện trước khi kiểm tra, có thể tạo giá trị âm sau lỗi. Kiểm tra hai điều kiện trước rồi mới `reserved -= quantity; available += quantity;`.
4. Sort tại chỗ sửa cùng object danh sách; sort bản sao không đổi thứ tự list nguồn, nhưng đối tượng phần tử có thể vẫn được chia sẻ.
5. Record chứa `String` và các primitive là một bản mô tả tách biệt của dữ liệu đã đọc; record không deep-copy object con mutable.

## 18. Tài liệu tham khảo

- [Java Language Specification 17, §8.4 — Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4): khai báo, kiểu trả về, tham số, phần thân phương thức và ngoại lệ.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): ngữ nghĩa gọi phương thức, truyền đối số.
- [Oracle Java API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): kiểm tra đối số bắt buộc không null.
- [Oracle Java API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): tạo danh sách không hỗ trợ sửa qua API và các giới hạn liên quan.

**Ghi nhớ:** precondition mô tả điều phải đúng **trước** khi gọi thành công; postcondition mô tả điều được bảo đảm **sau** một lần thực hiện thành công; side effect cho biết **đối tượng hoặc môi trường nào thay đổi** ngoài giá trị trả về. Một phương thức đáng tin cậy cần ghi rõ cả ba và có hành vi thất bại nhất quán với hợp đồng đã hứa.
