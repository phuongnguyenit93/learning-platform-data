# Kết hợp phong cách hàm với hướng đối tượng trong Java

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao Java vừa là ngôn ngữ hướng đối tượng (OOP) vừa hỗ trợ phong cách lập trình hàm (FP); chọn nơi dùng lớp/đối tượng và nơi dùng hàm; truyền hành vi qua functional interface, lambda và method reference; phối hợp Stream với mô hình miền; đồng thời kiểm soát trạng thái và tác dụng phụ để mã dễ kiểm thử, bảo trì.

## 1. Hai phong cách giải quyết hai vấn đề khác nhau

**Hướng đối tượng** tổ chức chương trình quanh những đối tượng có danh tính, dữ liệu, quy tắc và trách nhiệm. Ví dụ, `Order` quản lý tập dòng hàng và bảo vệ bất biến: số lượng phải dương, đơn giá không âm. Encapsulation giúp bên ngoài không sửa tùy tiện trạng thái bên trong; interface cho phép thay thế cách triển khai theo hợp đồng.

**Phong cách hàm** tập trung vào phép biến đổi dữ liệu qua những hàm: nhận đầu vào, trả kết quả, có thể truyền hoặc kết hợp hàm như giá trị. Hàm thuần (pure function) không sửa trạng thái quan sát được ở bên ngoài và với cùng đầu vào luôn cho cùng đầu ra. Cách này thuận lợi cho suy luận, kiểm thử và tái sử dụng.

Java không bắt buộc chọn một trong hai. Một thiết kế thực tế thường dùng **đối tượng để mô hình hóa miền và quản lý vòng đời**, còn **hàm để biểu diễn quy tắc, phép chọn lọc và biến đổi**. Lambda, method reference và Stream là công cụ giúp viết các phép biến đổi đó; bản thân việc sử dụng Stream không tự động làm cho mã trở thành thuần hàm.

| Vấn đề | Công cụ Java thường phù hợp | Lý do |
| --- | --- | --- |
| Dữ liệu và bất biến của một thực thể | `class`, `record`, constructor, phương thức | Gom dữ liệu với quy tắc hợp lệ |
| Hợp đồng hoặc vai trò của dịch vụ | `interface` và lớp triển khai | Phân tách trách nhiệm, thay thế được |
| Quy tắc thay đổi theo ngữ cảnh | Functional interface, lambda, method reference | Truyền hành vi vào đối tượng thay vì nhân bản nhánh điều kiện |
| Lọc, ánh xạ, tổng hợp tập dữ liệu | `Stream`, `Predicate`, `Function`, `Collectors` | Biểu đạt đường đi của dữ liệu |
| Đọc/ghi tệp, cơ sở dữ liệu, gọi mạng | Đối tượng dịch vụ chuyên trách | Gom tác dụng phụ tại ranh giới rõ ràng |

## 2. Nối hai phong cách qua functional interface

Một **functional interface** là interface chỉ có một phương thức trừu tượng (SAM); các phương thức `default`, `static` hoặc phương thức tương ứng với `Object` không làm tăng số phương thức trừu tượng cần triển khai. `@FunctionalInterface` yêu cầu trình biên dịch kiểm tra ràng buộc đó. Java đã cung cấp các hợp đồng thông dụng trong `java.util.function`:

- `Predicate<T>`: `boolean test(T)` — điều kiện chọn; ghép với `and`, `or`, `negate`.
- `Function<T,R>`: `R apply(T)` — biến đổi giá trị; ghép với `andThen` hoặc `compose`.
- `UnaryOperator<T>`: một `Function<T,T>`, phù hợp biến đổi cùng kiểu.
- `Consumer<T>`: `void accept(T)` — thực hiện hành động, thường có tác dụng phụ.
- `Supplier<T>`: `T get()` — cung cấp giá trị khi cần.
- `ToLongFunction<T>`: `long applyAsLong(T)` — tránh boxing khi tính tiền dạng đơn vị nguyên trong ví dụ.
- `Comparator<T>`: quy tắc so sánh; cũng là functional interface.

Lambda `x -> x > 0` là cách tạo hành vi cho một functional interface tại nơi sử dụng. Method reference `Line::subtotal` biểu đạt việc gọi một phương thức đã có; cả hai vẫn là các đối tượng thực thi hợp đồng SAM. Lambda có thể đọc biến cục bộ được capture, nhưng biến đó phải là `final` hoặc **effectively final** (không bị gán lại); điều này không làm đối tượng mutable được capture trở nên bất biến hay thread-safe.

Khi chiến lược có nhiều phương thức, cần trạng thái/lifecycle riêng hoặc cấu hình phức tạp, interface cùng một lớp triển khai rõ ràng thường thích hợp hơn một lambda dài. Khi hành vi là quy tắc nhỏ, tự chứa và dễ đặt tên, lambda hoặc method reference có thể giảm sự rườm rà của các lớp chiến lược.

## 3. Ví dụ Java 17: đối tượng giữ bất biến, hàm quyết định giá

Bài toán: một đơn hàng lưu các dòng hàng hợp lệ. Cùng một đơn hàng phải tính được tổng thông thường, tổng sau chính sách giảm giá sách 10%, và tổng của riêng các dòng sách. Nếu viết từng hàm tính tổng bằng vòng lặp và lặp lại việc truy cập danh sách, logic xử lý dễ bị phân tán. Ta để `Order` chịu trách nhiệm lưu và duyệt dòng hàng, còn các phép chọn và định giá được truyền dưới dạng hàm.

Lưu đoạn mã sau vào **`FunctionalOopDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.function.ToLongFunction;

public class FunctionalOopDemo {
    record Line(String name, int quantity, long unitPrice) {
        Line {
            Objects.requireNonNull(name, "name");
            if (name.isBlank() || quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("Invalid line");
            }
        }

        long subtotal() {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    static final class Order {
        private final List<Line> lines;

        Order(List<Line> lines) {
            this.lines = List.copyOf(lines);
        }

        long total(Predicate<Line> select,
                   ToLongFunction<Line> priceRule) {
            Objects.requireNonNull(select, "select");
            Objects.requireNonNull(priceRule, "priceRule");
            return lines.stream()
                    .filter(select)
                    .mapToLong(priceRule)
                    .reduce(0L, Math::addExact);
        }
    }

    static long discount10Percent(long amount) {
        return Math.multiplyExact(amount, 9) / 10;
    }

    public static void main(String[] args) {
        Order order = new Order(List.of(
                new Line("Sách", 2, 100_000),
                new Line("Bút", 3, 10_000)
        ));

        Predicate<Line> all = line -> true;
        ToLongFunction<Line> normal = Line::subtotal;
        ToLongFunction<Line> campaign = line ->
                line.name().equals("Sách")
                        ? discount10Percent(line.subtotal())
                        : line.subtotal();

        System.out.println("Tổng gốc: " + order.total(all, normal));
        System.out.println("Sau ưu đãi: " + order.total(all, campaign));
        System.out.println("Chỉ sách: " + order.total(
                line -> line.name().equals("Sách"), normal));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac FunctionalOopDemo.java
java FunctionalOopDemo
```

Kết quả:

```text
Tổng gốc: 230000
Sau ưu đãi: 210000
Chỉ sách: 200000
```

**Giải thích từng vai trò:**

1. `Line` là `record` chứa dữ liệu của một dòng hàng. Compact constructor xác minh dữ liệu đầu vào; `subtotal()` giữ logic gắn chặt với dòng hàng. Với các thành phần `String` và kiểu nguyên thủy ở đây, một `Line` đã được tạo không thể bị sửa thông qua API của nó.
2. `Order` là lớp đối tượng có trách nhiệm quản lý các dòng hàng. `List.copyOf` tạo bản sao danh sách không thể thay đổi qua các thao tác cấu trúc và từ chối phần tử `null`; không cần công khai danh sách nội bộ. Bản sao này là **shallow copy**: nếu phần tử là đối tượng mutable thì trạng thái của chính phần tử vẫn có thể thay đổi.
3. `Predicate<Line>` quyết định dòng nào được tính. `ToLongFunction<Line>` quyết định số tiền đóng góp của mỗi dòng. Đối tượng `Order` không cần biết các chính sách cụ thể.
4. `stream()` lấy nguồn dữ liệu; `filter` loại dòng không đạt điều kiện; `mapToLong` đổi mỗi dòng thành số tiền; `reduce(0L, Math::addExact)` cộng các khoản, đồng thời báo lỗi nếu tổng kiểu `long` tràn số. Các thao tác trung gian `filter`/`mapToLong` là lazy, chỉ thực thi khi gọi terminal operation `reduce`.
5. `Line::subtotal` là method reference giúp tái sử dụng phương thức OOP như một hàm. `campaign` là lambda chiến lược, còn `discount10Percent` là hàm thuần: cùng `amount` cho cùng kết quả và không thay đổi đối tượng.
6. Tổng tiền dùng đơn vị nguyên để ví dụ dễ kiểm chứng; phép chia nguyên trong giảm giá **làm tròn xuống phần lẻ**. Trong hệ thống tiền tệ thật, cần quy định đơn vị tiền, chế độ làm tròn, xử lý số âm, thuế và quy tắc tài chính; thường cân nhắc `BigDecimal` với `RoundingMode` phù hợp thay vì tùy tiện áp dụng phép chia nguyên.

Trong ví dụ, việc thay đổi chiến lược tính giá không làm biến đổi đơn hàng gốc. Có thể thêm quy tắc giá mới bằng một `ToLongFunction<Line>` mà không sửa cấu trúc `Order`. Đây là một dạng **composition**: đối tượng ủy quyền cho hành vi được cung cấp, thay vì phải tạo hàng loạt subclass cho từng chính sách.

## 4. Functional core và imperative shell

Một ranh giới hữu ích là chia luồng xử lý thành:

1. **Imperative shell**: nhận HTTP request, đọc database, lấy thời gian hiện tại, gọi dịch vụ thanh toán, ghi log/ghi kết quả. Các bước này có tác dụng phụ, cần quản lý lỗi và giao dịch.
2. **Functional core**: nhận dữ liệu đã thu thập và quy tắc rõ ràng, tính toán hoặc biến đổi thành **kết quả mới** mà không tự truy cập môi trường bên ngoài.
3. Shell dùng kết quả core để quyết định các hành động cần thực hiện.

Ví dụ, ứng dụng có thể tải `Order` qua repository, gọi `order.total(...)` để tính số tiền rồi chuyển kết quả cho cổng thanh toán. Cổng thanh toán, repository và clock thuộc lớp tích hợp; phép tính số tiền nên độc lập với chúng. Để bảo đảm cùng đầu vào cho cùng kết quả, truyền rõ thời điểm, bảng thuế hay mã khuyến mãi đã được xác thực vào hàm thay vì đọc trạng thái toàn cục ngay giữa phép tính.

Điều này cũng giúp kiểm thử: phép tính có thể kiểm tra bằng dữ liệu Java thông thường mà không cần khởi động server hay kết nối database; shell được kiểm tra riêng với stub/fake thích hợp.

## 5. Phối hợp mô hình đối tượng với Stream và Optional

Stream diễn đạt pipeline trên dữ liệu, không thay cho tất cả phương thức đối tượng:

```java
// Đoạn minh họa dùng record Line đã khai báo ở ví dụ đầy đủ:
List<String> names = List.of(
        new Line("Sách", 2, 100_000),
        new Line("Bút", 3, 10_000))
        .stream()
        .filter(line -> line.quantity() >= 2)
        .map(Line::name)
        .toList(); // [Sách, Bút]; toList() có từ Java 16
```

`map` tạo giá trị mới từ mỗi phần tử; `filter` giữ phần tử thỏa điều kiện; `sorted` sắp xếp luồng; `collect` hoặc `toList()` tạo kết quả. `Stream.toList()` trả danh sách **không cho sửa cấu trúc**, nhưng không tự làm bất biến các đối tượng bên trong. Mỗi Stream thường chỉ tiêu thụ một lần; để xử lý lại, tạo Stream mới từ nguồn.

`Optional<T>` hữu ích khi kết quả có thể vắng mặt, đặc biệt ở ranh giới trả về từ phương thức tìm kiếm:

```java
// Minh họa độc lập với chương trình chính; products là List<Line>.
String firstBook = products.stream()
        .filter(line -> line.name().equals("Sách"))
        .findFirst()
        .map(Line::name)
        .orElse("Không có sách");
```

`findFirst()` trả `Optional<Line>`, `map` chuyển kết quả nếu có, `orElse` cung cấp giá trị dự phòng. Tránh gọi `get()` khi chưa kiểm tra có giá trị; cân nhắc `orElseGet` nếu việc tạo giá trị mặc định tốn chi phí vì `orElse` tính đối số ngay, dù Optional có giá trị. Không cần biến mọi field hoặc tham số thành Optional.

## 6. Khi nào ưu tiên class, khi nào ưu tiên hàm?

Giữ **class/record** cho các giá trị miền và quy tắc phải đúng ở mọi nơi, ví dụ `Line` có số lượng dương. Giữ **interface dịch vụ** cho hợp đồng lớn có nhiều thao tác, giao dịch, lifecycle và dependency. Truyền **hàm** cho điều kiện lọc, comparator, mapper, chính sách tính toán nhỏ có thể thay thế. Với thuật toán dài hoặc nhiều nhánh, tách thành phương thức có tên hoặc lớp chiến lược để không biến lambda thành “hộp đen”.

Quy tắc thiết kế hữu ích là: **đặt bất biến tại nơi dữ liệu được tạo, đặt phép biến đổi tại hàm có đầu vào/đầu ra rõ ràng, đặt tác dụng phụ ở lớp tích hợp**. Không cần xóa mọi vòng lặp `for`; với luồng có nhiều nhánh, `break`/`continue`, cập nhật trạng thái có chủ đích, hoặc tác vụ cần debug từng bước, một vòng lặp rõ ràng có thể dễ hiểu hơn pipeline Stream.

Việc kết hợp còn tuân theo SOLID theo nghĩa thực dụng: `Order` có một trách nhiệm miền rõ ràng; hành vi biến thiên truyền qua hợp đồng hàm, cho phép mở rộng chính sách với ít sửa đổi; dependency inversion vẫn có ích ở ranh giới repository hoặc dịch vụ lớn. Không nên đặt mọi thứ vào `Function<Object,Object>` vì nó đánh mất thông tin kiểu và ý nghĩa miền.

## 7. Những lỗi thường gặp

- **Tác dụng phụ trong `map`, `filter` hoặc `peek`**: ghi vào danh sách bên ngoài hay tăng bộ đếm dùng chung làm pipeline khó suy luận; với parallel stream có thể gặp race condition. Ưu tiên `map` tạo giá trị mới và `collect`/`reduce` để tổng hợp; chỉ đặt ghi log/I/O có chủ đích tại ranh giới phù hợp. `peek` chủ yếu để quan sát/debug.
- **Nhầm “biến không gán lại” với bất biến**: `final List<Line>` vẫn có thể bị sửa nếu là danh sách mutable; `record` chỉ ngăn gán lại các component, không tạo deep immutable cho mọi tham chiếu. Cân nhắc defensive copy và kiểu giá trị bất biến.
- **Đưa database hoặc thời gian hiện tại vào hàm tính**: cùng đối số có thể cho kết quả khác. Hãy đọc những đầu vào ngoại cảnh ở shell rồi truyền vào core.
- **Lạm dụng kế thừa để biểu diễn từng lựa chọn nghiệp vụ**: hàng chục subclass như `DiscountForBooksOrder` khó phối hợp. Chính sách đơn giản thường gọn hơn khi truyền qua một functional interface; với hành vi phức tạp, một strategy object rõ tên vẫn tốt.
- **Dùng `parallelStream()` như tối ưu mặc định**: phân luồng có chi phí, yêu cầu tránh shared mutable state và phụ thuộc tính kết hợp của phép tổng hợp; đo lường trước khi dùng. Phép reduce song song chỉ an toàn về ý nghĩa khi phép gộp có tính kết hợp và identity phù hợp.
- **Sử dụng `Stream` cho thao tác không phù hợp**: Stream là đường xử lý dữ liệu, không phải bộ sưu tập lưu trữ; không tái sử dụng cùng một stream sau terminal operation.
- **Dùng quá nhiều lambda lồng nhau**: tách `Predicate` và `Function`/`ToLongFunction` thành biến có tên hoặc phương thức có tên để kiểm thử và truyền đạt ý nghĩa.

## 8. Cách tự kiểm chứng

Với ví dụ đã chạy, thử đổi chính sách giảm giá từ 10% thành 20% bằng cách tạo **một hàm/chính sách mới**, không sửa `Order`; dự đoán trước stdout. Thử xây `Predicate<Line>` chỉ tính những dòng có `unitPrice >= 50_000`; tổng gốc của những dòng ấy là `200000`. Thử truyền số lượng `0` vào `new Line(...)`: constructor phải ném `IllegalArgumentException` trước khi đơn hàng được tạo. Thử dùng `List.copyOf` với một phần tử `null`: Java ném `NullPointerException`.

Để kiểm thử tự động, kiểm tra riêng `Line.subtotal()`, `discount10Percent(...)` và `Order.total(...)` cho danh sách rỗng, một dòng, nhiều dòng, chính sách lọc tất cả/không dòng nào, giá trị biên và tràn số. Sau đó kiểm tra lớp tích hợp rằng nó gọi đúng nguồn dữ liệu, thanh toán và ghi nhận kết quả. Phép tính rõ ràng ở functional core làm các kiểm thử này đơn giản và ổn định.

**Kết luận:** Java kết hợp OOP và FP hiệu quả khi mô hình đối tượng chịu trách nhiệm giữ dữ liệu hợp lệ, còn các hàm nhỏ chịu trách nhiệm chọn lọc và biến đổi. Ranh giới tác dụng phụ được giữ rõ ràng, giúp mở rộng chính sách nghiệp vụ mà vẫn dễ đọc, dễ thử nghiệm và bảo trì.
