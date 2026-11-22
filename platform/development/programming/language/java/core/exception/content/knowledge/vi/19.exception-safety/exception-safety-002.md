# Kiểm tra điều kiện trước khi thay đổi trạng thái trong Java

> **Chủ đề:** Java Core — Exception · **Nhóm kiến thức:** Bảo toàn trạng thái. Mục tiêu là thiết kế phương thức sao cho lỗi đầu vào hoặc điều kiện nghiệp vụ không hợp lệ được phát hiện trước khi đối tượng bị cập nhật dở dang; từ đó giữ các bất biến và cung cấp hợp đồng thất bại dễ dự đoán.

## 1. Vì sao phải kiểm tra trước khi thay đổi trạng thái?

Một thao tác có thể thất bại do tham số sai, trạng thái hiện tại không đáp ứng yêu cầu, phép tính tràn số, tài nguyên hết chỗ, hoặc lời gọi phụ thuộc bên ngoài ném ngoại lệ. Nếu phương thức sửa một phần dữ liệu rồi mới phát hiện lỗi, đối tượng có thể ở trạng thái khó hiểu: số dư đã trừ nhưng lịch sử giao dịch chưa ghi, một mặt hàng đã giảm tồn kho nhưng mặt hàng thứ hai vẫn giữ nguyên, hoặc cấu hình chỉ được cập nhật một nửa.

Với đối tượng có trạng thái, cần phân biệt ba khái niệm:

- **Tiền điều kiện (precondition):** điều kiện cần thỏa mãn *trước thao tác*, ví dụ số lượng đặt hàng phải lớn hơn 0, mã sản phẩm phải tồn tại, tài khoản đích hợp lệ.
- **Bất biến (invariant):** điều kiện phải đúng ở mọi trạng thái có thể quan sát hợp lệ, ví dụ tồn kho không âm, tổng số dư giữa các tài khoản không bị tự sinh hoặc mất đi khi chuyển tiền nội bộ, danh sách mục và tổng tiền nhất quán.
- **Hậu điều kiện (postcondition):** điều kiện đúng khi thao tác thành công, ví dụ lượng tồn kho giảm chính xác theo yêu cầu.

**Quy tắc thực hành:** xác minh tiền điều kiện và tính trước những gì có thể thất bại, sau đó mới công bố trạng thái mới. Nếu ném ngoại lệ ở đường kiểm tra, trạng thái quan sát được của đối tượng nên giữ nguyên, trừ khi API công bố rõ một bảo đảm yếu hơn.

Thứ tự có ý nghĩa vì `throw` lập tức chuyển điều khiển ra khỏi luồng thông thường. Những phép gán đã xảy ra **không tự hoàn tác** chỉ vì mã đi vào `catch` hoặc `finally`.

## 2. Ví dụ phản diện: cập nhật một phần rồi mới phát hiện lỗi

Giả sử một giỏ hàng lưu số lượng và tổng tiền, có bất biến `quantity >= 0` và `totalCents >= 0`. Đoạn **minh họa chưa hoàn chỉnh** sau rất dễ mắc lỗi:

~~~java
// Minh họa sai: chỉ là phần thân phương thức của một lớp có trường quantity, totalCents.
void add(int amount, long unitPriceCents) {
    quantity += amount;                      // Trạng thái bị đổi trước
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    if (unitPriceCents < 0) {
        throw new IllegalArgumentException("negative price");
    }
    totalCents += amount * unitPriceCents;  // Có thể tràn long
}
~~~

Có ít nhất ba nguy cơ:

1. `amount <= 0` bị phát hiện **sau khi** `quantity` đã thay đổi.
2. `unitPriceCents < 0` làm phương thức dừng sau một phép cập nhật nhưng trước phép cập nhật tiếp theo.
3. Phép nhân hoặc cộng trên kiểu `long` tràn theo số học Java mà **không tự ném ngoại lệ**; kết quả có thể sai và khiến trạng thái lệch với quy tắc miền nghiệp vụ.

Đưa mọi `if` lên trước hai phép gán cải thiện thiết kế, nhưng chưa đủ nếu sau đó còn phép tính, cấp phát, callback hoặc I/O có thể thất bại. Phải xem toàn bộ các bước có khả năng ném ngoại lệ, không chỉ những dòng `throw` được viết tường minh.

## 3. Mô hình triển khai: kiểm tra → chuẩn bị → ghi nhận

Một cách thiết kế dễ kiểm soát là phân biệt rõ ba giai đoạn:

1. **Validate — kiểm tra:** xác định đầu vào đúng kiểu, không null, nằm trong miền giá trị cho phép; xác nhận trạng thái hiện tại đủ điều kiện; kiểm tra quyền, ràng buộc quan hệ và mọi điều kiện có thể biết trước.
2. **Prepare — chuẩn bị:** tính toán kết quả, sao chép hoặc xây dựng trạng thái mới trong biến cục bộ, có thể phát hiện tràn số bằng `Math.addExact`/`Math.multiplyExact`. Nếu bước này lỗi, trạng thái đang dùng vẫn nguyên vẹn.
3. **Commit — ghi nhận:** đưa trạng thái đã hợp lệ vào sử dụng ở một điểm rõ ràng, ví dụ gán một tham chiếu đến một giá trị bất biến mới. Nếu cập nhật nhiều nơi, cần cơ chế bảo đảm tính nguyên tử thích hợp.

~~~text
đầu vào + trạng thái hiện tại
            |
       kiểm tra hợp lệ?
         /        \
       không       có
        |           |
   ném exception  dựng trạng thái đề xuất
     không sửa       |
    trạng thái    chuẩn bị thành công?
                  /          \
                không         có
                 |             |
             ném exception    commit
             không sửa          |
            trạng thái      trạng thái mới hợp lệ
~~~

Một quy tắc hữu ích: **cố gắng chuyển những thao tác có thể lỗi sang trước thời điểm commit**, còn thao tác commit nên ngắn, đơn giản và không gọi mã người dùng tùy ý. Đừng nhầm “đã kiểm tra hết `if`” với “không còn câu lệnh nào có thể ném ngoại lệ”.

### Các kiểm tra thường cần

| Loại ràng buộc | Ví dụ Java / cách đánh giá | Hậu quả nếu bỏ qua |
|---|---|---|
| Null | `Objects.requireNonNull(value, "value")` | NPE xảy ra giữa chừng thay vì tại ranh giới API |
| Miền số | `amount > 0`, `discount <= 100` | Cập nhật giá trị âm/vượt giới hạn |
| Chỉ số | `index >= 0 && index < size` | `IndexOutOfBoundsException` sau tác dụng phụ khác |
| Quan hệ giữa tham số | `start <= end`, số lượng và đơn giá phù hợp | Dữ liệu nội bộ bất nhất |
| Trạng thái đối tượng | đủ tồn kho, đang mở, còn quyền thao tác | Thay đổi trong lúc trạng thái không cho phép |
| Ràng buộc trên cả tập hợp | tất cả phần tử hợp lệ; mã không trùng; tổng nhu cầu không vượt ngân sách | Cập nhật từng phần tử rồi phát hiện phần tử lỗi |
| Tràn số | `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact` | Số học bị vòng và làm sai invariant |
| Dữ liệu đầu vào biến đổi được | tạo bản sao hợp lý trước khi duyệt; quy định caller không sửa đồng thời | Mỗi vòng kiểm tra thấy một nội dung khác nhau |

Kiểm tra cần dựa vào **trạng thái cùng thời điểm sẽ ghi**, nhất là khi có nhiều luồng. Kiểm tra sớm ở tầng giao diện hữu ích cho thông báo lỗi nhưng không thay thế được kiểm tra nhất quán tại tầng quản lý trạng thái.

## 4. Ví dụ Java 17+ chạy độc lập: đặt tồn kho theo lô

Yêu cầu: kho lưu số lượng hiện có theo mã hàng; một lần `reserve` có thể yêu cầu nhiều mặt hàng. Nếu **bất kỳ** mã hàng nào không tồn tại, số lượng không hợp lệ hoặc không đủ hàng, toàn bộ lời gọi phải thất bại mà **không giảm tồn kho của mặt hàng nào**.

Thiết kế dùng một `Map` làm trạng thái riêng tư. Phương thức tạo một bản đề xuất trong bộ nhớ, kiểm tra tất cả yêu cầu, tính lượng tồn mới và chỉ gán lại trường trạng thái **sau cùng**. Tất cả phương thức quan sát và cập nhật sử dụng cùng khóa `synchronized` để tránh luồng khác chen vào giữa kiểm tra và commit của đối tượng này.

Lưu chương trình dưới tên **`ValidateBeforeMutationDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ValidateBeforeMutationDemo {
    static final class Inventory {
        private Map<String, Integer> stock;

        Inventory(Map<String, Integer> initial) {
            Objects.requireNonNull(initial, "initial");
            Map<String, Integer> copy = new HashMap<>();

            for (Map.Entry<String, Integer> entry : initial.entrySet()) {
                String sku = Objects.requireNonNull(entry.getKey(), "sku");
                Integer count = Objects.requireNonNull(entry.getValue(), "count");
                if (count < 0) {
                    throw new IllegalArgumentException("negative initial stock: " + sku);
                }
                copy.put(sku, count);
            }

            stock = copy;
        }

        public synchronized void reserve(Map<String, Integer> request) {
            Objects.requireNonNull(request, "request");

            // Giai đoạn 1: kiểm tra toàn bộ yêu cầu trước khi đổi trạng thái thật.
            Map<String, Integer> validated = new HashMap<>();
            for (Map.Entry<String, Integer> entry : request.entrySet()) {
                String sku = Objects.requireNonNull(entry.getKey(), "sku");
                Integer quantity = Objects.requireNonNull(entry.getValue(), "quantity");
                if (quantity <= 0) {
                    throw new IllegalArgumentException("quantity must be positive");
                }

                Integer available = stock.get(sku);
                if (available == null) {
                    throw new IllegalArgumentException("unknown SKU: " + sku);
                }
                if (quantity > available) {
                    throw new IllegalArgumentException("insufficient stock: " + sku);
                }

                validated.put(sku, quantity);
            }

            // Giai đoạn 2: mọi cập nhật chỉ tác động lên bản sao cục bộ.
            Map<String, Integer> next = new HashMap<>(stock);
            for (Map.Entry<String, Integer> entry : validated.entrySet()) {
                String sku = entry.getKey();
                next.put(sku, next.get(sku) - entry.getValue());
            }

            // Giai đoạn 3: công bố trạng thái mới trong một phép gán.
            stock = next;
        }

        public synchronized int available(String sku) {
            Objects.requireNonNull(sku, "sku");
            Integer count = stock.get(sku);
            if (count == null) {
                throw new IllegalArgumentException("unknown SKU: " + sku);
            }
            return count;
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory(Map.of("book", 4, "pen", 3));

        try {
            inventory.reserve(Map.of("book", 2, "pen", 5));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        System.out.printf("After failure: book=%d, pen=%d%n",
                inventory.available("book"), inventory.available("pen"));

        inventory.reserve(Map.of("book", 2, "pen", 1));

        System.out.printf("After success: book=%d, pen=%d%n",
                inventory.available("book"), inventory.available("pen"));
    }
}
~~~

Biên dịch và chạy (JDK 17 hoặc mới hơn):

~~~bash
javac ValidateBeforeMutationDemo.java
java ValidateBeforeMutationDemo
~~~

**Standard output chính xác:**

~~~text
Rejected: insufficient stock: pen
After failure: book=4, pen=3
After success: book=2, pen=2
~~~

Tại lần đặt đầu tiên, mặt hàng `pen` yêu cầu 5 nhưng chỉ còn 3; yêu cầu `book` dù hợp lệ cũng **không làm giảm** hàng tồn vì trạng thái `stock` chưa được gán lại. Thứ tự duyệt của `Map.of` không được bảo đảm, nhưng mẫu này chỉ có một mặt hàng sai nên thông báo ngoại lệ vẫn ổn định. Lần gọi thứ hai thành công và cập nhật cùng lúc hai mã hàng ở mức trạng thái quan sát được qua API của `Inventory`.

**Vì sao cách này vững hơn việc chỉ thêm `if`?** Sau giai đoạn kiểm tra vẫn còn hai bước có thể gặp sự cố: tạo bản sao `HashMap` và ghi các giá trị vào bản sao đó. Cả hai diễn ra trước `stock = next`; nếu lỗi được ném trong các thao tác đó, trường `stock` vẫn trỏ đến bản cũ. Đối tượng không làm lộ `Map` bên trong cho bên ngoài sửa trực tiếp.

**Giới hạn đã chọn:** các lời gọi truy cập `Inventory` phải đi qua những phương thức đồng bộ nói trên. Caller không được sửa `request` đồng thời khi `reserve` đang duyệt; muốn hỗ trợ đầu vào thay đổi đồng thời phải thiết kế thêm cơ chế snapshot hoặc đồng bộ hóa với chủ sở hữu đầu vào. Ví dụ hoạt động trong bộ nhớ một JVM; nó không tự cung cấp giao dịch cho cơ sở dữ liệu hay nhiều tiến trình.

## 5. Trạng thái cần đúng sau khi ném ngoại lệ đến mức nào?

Các thuật ngữ sau giúp diễn đạt **mức bảo đảm** của API. Đây là cách mô tả về tính an toàn khi có ngoại lệ, không phải phân loại cú pháp `throws` của Java.

| Mức bảo đảm | Khi thao tác thất bại | Ví dụ |
|---|---|---|
| Không có bảo đảm rõ ràng | Đối tượng có thể không còn thỏa bất biến | Trừ số dư rồi ném lỗi trước khi hoàn thành cập nhật |
| **Bảo đảm cơ bản (basic)** | Đối tượng vẫn hợp lệ theo invariant, nhưng một phần thay đổi có thể đã xảy ra | Bộ sưu tập bổ sung được một số phần tử, rồi thao tác tiếp theo lỗi |
| **Bảo đảm mạnh (strong)** | Lỗi không làm thay đổi trạng thái có thể quan sát của đối tượng (*all-or-nothing*) | Dựng bản sao và chỉ thay tham chiếu sau khi chuẩn bị thành công |
| Không thất bại trong phạm vi đã cam kết | Bước thao tác không phát sinh lỗi thuộc phạm vi hợp đồng xác định | Phép gán tham chiếu đơn giản ở commit, trong điều kiện runtime bình thường |

Đối với thao tác nhiều bước mang ý nghĩa một giao dịch, **bảo đảm mạnh** thường là mục tiêu hợp lý: thành công thì áp dụng toàn bộ, thất bại thì không áp dụng gì. Tuy nhiên, không được hứa bảo đảm tuyệt đối cho các lỗi hạ tầng như JVM bị dừng đột ngột, hết bộ nhớ, mất nguồn hoặc hệ thống bên ngoài đã nhận một phần yêu cầu. Xác định phạm vi trạng thái và loại thất bại mà API cam kết bảo toàn.

Đừng suy ra bảo đảm mạnh chỉ từ việc mọi nhánh sai đầu vào đều có `throw` trước khi cập nhật. Một `OutOfMemoryError`, một setter gọi callback, một phép tính chưa kiểm tra hoặc một lời gọi I/O vẫn có thể làm thao tác thất bại giữa quá trình cập nhật.

## 6. Kiểm tra phép tính trước commit: tránh tràn số âm thầm

Kiểm tra `amount >= 0` không có nghĩa `balance + amount` vẫn nằm trong miền số nguyên. Với `long`, phép cộng tràn sẽ tạo kết quả khác theo quy tắc số học cố định của Java, **không** tự phát sinh exception.

Cách kiểm soát khi cập nhật một trường:

~~~java
// Trích đoạn trong lớp có trường private long balance;
// yêu cầu balance >= 0 và không nhận số tiền âm.
public void deposit(long amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("negative amount");
    }
    long next = Math.addExact(balance, amount);
    balance = next;
}
~~~

`Math.addExact` ném `ArithmeticException` nếu `long` bị tràn, và phép gán không được thực hiện. Ở hệ thống nhiều luồng, cả đọc `balance`, kiểm tra, tính toán và gán phải được bảo vệ bằng cùng cơ chế đồng bộ; đoạn này chỉ minh họa logic cập nhật trong ngữ cảnh đơn luồng hoặc khi đã giữ khóa.

Với phép nhân giá × số lượng, tính trước:

~~~java
// Trích đoạn: amount và unitPriceCents đã được kiểm tra hợp lệ.
long addedCents = Math.multiplyExact((long) amount, unitPriceCents);
long nextTotal = Math.addExact(totalCents, addedCents);
int nextQuantity = Math.addExact(quantity, amount);

// Chỉ commit sau khi cả ba phép tính thành công.
totalCents = nextTotal;
quantity = nextQuantity;
~~~

Hai phép gán cuối là hai cập nhật riêng biệt. Với một đối tượng chỉ được quan sát khi đang giữ cùng khóa, thao tác có thể đáp ứng tính nguyên tử ở mức API; nếu có callback, getter không đồng bộ hoặc quan sát trực tiếp giữa hai lần gán, cần thiết kế lại để bảo vệ snapshot nhất quán. Một cách rõ ràng hơn là đóng gói số lượng và tổng tiền trong một đối tượng giá trị bất biến rồi thay một tham chiếu tới đối tượng đó.

## 7. Phân biệt kiểm tra tham số và kiểm tra trạng thái nghiệp vụ

**Tham số sai:** các giá trị tự thân không phù hợp với hợp đồng, chẳng hạn số lượng âm, mã đầu vào `null` hoặc chỉ số vượt miền hợp lệ. Trong nhiều API Java, `IllegalArgumentException`, `NullPointerException` (qua `Objects.requireNonNull`) và `IndexOutOfBoundsException` là những lựa chọn rõ nghĩa.

**Trạng thái không cho phép thao tác:** tham số có thể hợp lệ nhưng đối tượng đang đóng, đơn hàng đã xác nhận hoặc giao dịch đã hoàn tất. `IllegalStateException` thường thích hợp cho vi phạm trạng thái sử dụng API.

**Từ chối theo luật nghiệp vụ bình thường:** ví dụ hết hàng hoặc vượt hạn mức tín dụng. Với hệ thống cần phân loại và xử lý điều kiện này, một exception nghiệp vụ riêng (hoặc kiểu kết quả thể hiện thất bại dự kiến) có thể rõ hơn. Không nhất thiết coi mọi kết quả từ chối như lỗi lập trình. Việc chọn checked hay unchecked phụ thuộc khả năng khôi phục của caller và hợp đồng public đã công bố.

Ví dụ:

~~~java
// Trích đoạn kiểm tra đầu vào và trạng thái trong một phương thức.
Objects.requireNonNull(orderId, "orderId");
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
if (closed) {
    throw new IllegalStateException("order is already closed");
}
if (quantity > availableStock) {
    throw new InsufficientStockException(orderId);
}
~~~

Đây là **mã minh họa**, giả định các biến và lớp `InsufficientStockException` đã có trong ứng dụng. Kiểu ngoại lệ và thông điệp lỗi nên là phần có tài liệu của API khi client cần dựa vào chúng.

Trước khi cho phép thao tác thay đổi trạng thái, việc kiểm tra nên xuất phát từ **nguồn sự thật hiện tại**. Với database, giá trị đọc trước đó ở UI hoặc cache có thể đã lỗi thời; với một đối tượng, trạng thái phải được bảo vệ khỏi cập nhật cạnh tranh.

## 8. Tránh lỗi “check-then-act” khi có nhiều luồng

Mẫu không an toàn:

~~~java
// Sai nếu nhiều luồng cùng truy cập mà không đồng bộ.
if (account.balance() >= amount) {
    account.withdraw(amount);
}
~~~

Giữa lần `balance()` và lần `withdraw()`, một luồng khác có thể đã rút tiền. Kiểm tra đúng tại thời điểm đọc nhưng không còn đúng tại thời điểm ghi: đây là lỗi *time-of-check to time-of-use* (TOCTOU).

Giải pháp là đưa **kiểm tra và cập nhật vào cùng một thao tác nguyên tử theo phạm vi trạng thái liên quan**:

- Trong một đối tượng JVM: bảo vệ đọc-kiểm tra-tính-toán-ghi bằng cùng lock, hoặc dùng kỹ thuật CAS với `AtomicReference` tới trạng thái bất biến nếu phù hợp.
- Trong cơ sở dữ liệu: sử dụng transaction cùng mức cô lập thích hợp, khóa hàng hoặc câu lệnh cập nhật có điều kiện; kiểm tra số dòng cập nhật để biết điều kiện còn đúng ở lúc commit.
- Với nhiều đối tượng/tài nguyên: xác định phạm vi khóa và thứ tự khóa nhất quán để tránh deadlock; đừng cho rằng `synchronized` trên một đối tượng tự bảo vệ các đối tượng khác.
- Với input mutable do caller sở hữu: cần bản sao/snapshot hoặc hợp đồng không sửa đồng thời; khóa trên đối tượng đích không tự khóa một `Map` mà caller vẫn đang thay đổi.

**Lưu ý:** `volatile` giúp quy định khả năng nhìn thấy và thứ tự bộ nhớ của một số truy cập nhưng không biến một chuỗi lệnh “kiểm tra rồi cập nhật” thành nguyên tử. Đối với mẫu thay thế một snapshot bất biến, `volatile` có thể giúp công bố tham chiếu an toàn; vẫn cần khóa hoặc CAS để ngăn các writer ghi đè kết quả lẫn nhau.

## 9. Cập nhật nhiều trường, nhiều đối tượng hoặc tài nguyên bên ngoài

### 9.1. Nhiều trường trong một đối tượng

Có thể kiểm tra hết rồi mới thực hiện hai phép gán; nhưng nếu hai trường phải đồng bộ về mặt ngữ nghĩa, hãy ưu tiên gộp thành trạng thái bất biến:

~~~java
// Trích đoạn độc lập về ý tưởng; MoneyState là một record bất biến.
record MoneyState(long cents, int version) {}

private MoneyState state = new MoneyState(0L, 0);

public synchronized void add(long cents) {
    if (cents < 0) {
        throw new IllegalArgumentException("negative cents");
    }
    long nextCents = Math.addExact(state.cents(), cents);
    int nextVersion = Math.addExact(state.version(), 1);
    state = new MoneyState(nextCents, nextVersion);
}
~~~

Trích đoạn nằm trong một lớp chứa `state` và `add`, không phải file Java độc lập. Cả `MoneyState` và giá trị thay thế đều được tạo trước phép gán; API đọc `state` cần có chính sách đồng bộ/công bố nhất quán. Kiểu `record` là một công cụ hữu ích để biểu diễn dữ liệu bất biến khi các thành phần của nó cũng không làm lộ trạng thái mutable.

### 9.2. Hai đối tượng hoặc nhiều tài nguyên

Chuyển tiền từ tài khoản A sang B gồm ít nhất một lần trừ và một lần cộng. Kiểm tra A đủ tiền là cần thiết, nhưng **nếu trừ A thành công rồi ghi B thất bại**, việc kiểm tra trước đó không cứu được tính toàn vẹn. Cần kết hợp kiểm tra trước với một cơ chế commit nguyên tử cho cả hai tài khoản, như khóa cả hai trong cùng JVM theo thứ tự khóa ổn định, hoặc transaction khi dữ liệu ở database.

### 9.3. I/O, mạng và side effect

Ghi file, gửi email, thanh toán, publish event hoặc gọi API từ xa có thể đã gây tác dụng phụ trước khi client nhận được lỗi timeout. Chưa nhận được phản hồi thành công **không chứng minh** thao tác bên kia chưa xảy ra. Vì vậy:

- Kiểm tra dữ liệu trước khi tạo side effect.
- Khi có transaction database, đặt các cập nhật cần nhất quán trong cùng transaction.
- Khi gửi sự kiện cần đi cùng commit dữ liệu, cân nhắc *transactional outbox*.
- Với lệnh có thể gửi lại, thiết kế *idempotency key* để giảm rủi ro thực hiện trùng.
- Xác định trạng thái “đã commit nhưng thông báo thất bại” và cách hòa giải; `finally` chỉ hữu ích cho cleanup, không tự rollback tác dụng phụ.

Tách **lỗi xác thực điều kiện** khỏi **lỗi thực thi sau commit** trong hợp đồng API. Nếu listener hoặc callback được gọi trước khi commit, chúng có thể nhìn thấy trạng thái cũ hoặc ném lỗi làm hỏng quá trình; nếu gọi sau commit, phải tài liệu hóa khả năng “trạng thái đã đổi nhưng thông báo lỗi”.

## 10. Những sai lầm thường gặp

1. **Sửa dữ liệu trước rồi mới `throw`:** nhánh lỗi bỏ lại đối tượng dở dang. Hãy chuyển các kiểm tra và tính toán lên trước commit.
2. **Kiểm tra từng phần tử rồi sửa ngay:** phần tử thứ ba sai nhưng hai phần tử đầu đã đổi. Hãy xác nhận toàn bộ batch hoặc dựng bản kết quả riêng.
3. **Kiểm tra số học nhưng bỏ qua overflow:** `int`/`long` có thể vòng; dùng `Math.*Exact` hoặc giới hạn miền dữ liệu đúng theo nghiệp vụ.
4. **Rely on `assert` for input validation:** `assert` có thể bị tắt khi chạy JVM; không dùng nó làm cơ chế kiểm tra hợp đồng public hay đầu vào không tin cậy.
5. **Giữ tham chiếu mutable của caller:** caller có thể sửa collection sau validation. Sao chép phòng vệ hoặc dùng value object bất biến; nếu có đồng thời phải quy định snapshot.
6. **Cho getter/setter phụ tác dụng phụ vào giai đoạn kiểm tra:** những lời gọi này có thể ném exception hoặc đổi trạng thái. Giảm phụ thuộc vào callback và mã ngoài trước commit.
7. **Ghi đè exception gốc bằng lỗi xử lý lỗi:** rollback, cleanup hay logging cũng có thể lỗi. Bảo toàn `cause`, suppressed exceptions khi phù hợp; không nuốt lỗi gốc.
8. **Bắt `Exception` và giả vờ đã thành công:** nếu không rollback được hoặc không thể chứng minh invariant, phải báo thất bại đúng cách.
9. **Kiểm tra ngoài khóa, cập nhật trong khóa:** kết quả kiểm tra có thể đã lỗi thời; kiểm tra lại bên trong cùng vùng đồng bộ.
10. **Coi việc ném `RuntimeException` là bảo đảm rollback:** loại exception không quyết định trạng thái được hoàn tác. Cần thiết kế thứ tự thao tác và phạm vi giao dịch.

## 11. Cách kiểm thử hợp đồng bảo toàn trạng thái

Thiết kế test từ góc nhìn trạng thái quan sát được **trước và sau lỗi**, thay vì chỉ viết `assertThrows`:

| Kịch bản | Điều cần xác minh |
|---|---|
| Tham số `null`, số âm, vượt giới hạn | Exception đúng loại; trạng thái cũ không thay đổi |
| Một phần tử không hợp lệ ở đầu/giữa/cuối batch | Không có phần tử hợp lệ nào bị commit trước |
| Thiếu tài nguyên, hết hạn mức, trạng thái đã đóng | Invariant vẫn đúng, thông báo đủ rõ để caller quyết định |
| Phép tính tràn | Không commit kết quả số học bị sai |
| Bước chuẩn bị ném lỗi | Trạng thái live vẫn trỏ đến snapshot cũ |
| Hai thao tác cạnh tranh trên cùng tài nguyên | Không phát sinh mất cập nhật, lượng âm hoặc vi phạm điều kiện |
| Lỗi I/O/transaction/callback | Quan sát và ghi nhận chính xác trạng thái đã commit hay chưa |
| Thành công | Hậu điều kiện chính xác; trạng thái mới thỏa tất cả invariant |

Với `Inventory` ở ví dụ đầy đủ, một kiểm thử tối thiểu kiểm tra cả **thất bại và thành công**: thử `reserve(book=2, pen=5)`, xác nhận `book=4`, `pen=3`; sau đó thử `reserve(book=2, pen=1)` và xác nhận `book=2`, `pen=2`. Nếu test chỉ kiểm tra có `IllegalArgumentException`, nó có thể bỏ sót lỗi đã giảm `book` trước khi ném ngoại lệ.

Với hệ thống nhiều luồng, bổ sung test tranh chấp có kiểm soát (barrier/latch), kiểm tra invariant cuối cùng và xem xét các kỹ thuật kiểm thử concurrency thích hợp. Một lần test chạy đúng không chứng minh thuật toán không có race; thiết kế khóa/CAS và lập luận về điểm commit vẫn rất quan trọng.

## 12. Checklist áp dụng khi thiết kế phương thức mới

- **Định nghĩa invariant:** trạng thái thế nào mới hợp lệ, bên ngoài quan sát qua API nào?
- **Viết tiền điều kiện:** thông số, quyền, trạng thái nghiệp vụ; chỉ ra ngoại lệ hoặc kết quả khi sai.
- **Đánh dấu từng tác dụng phụ:** phép gán, sửa collection, ghi DB, I/O, gọi callback, publish event.
- **Xác định bước có thể lỗi:** cấp phát bộ nhớ, phép tính, chuyển đổi kiểu, dịch vụ phụ thuộc, validation có side effect.
- **Chọn điểm commit:** ưu tiên thay snapshot hợp lệ; với nhiều tài nguyên dùng transaction hoặc cơ chế phối hợp phù hợp.
- **Giữ kiểm tra và commit nhất quán khi có concurrency:** cùng lock, CAS, hoặc transaction có điều kiện.
- **Không để thoát tham chiếu mutable trước khi commit:** tránh bên ngoài thấy bản đang chỉnh sửa.
- **Kiểm thử đường lỗi:** sau mỗi ngoại lệ có thể gặp, invariant và mức bảo đảm đã cam kết có còn đúng?
- **Tài liệu hóa các trường hợp không thể rollback:** đặc biệt với mạng, file, thanh toán hoặc sự kiện đã phát.

## 13. Ghi nhớ cốt lõi

**Kiểm tra điều kiện trước khi thay đổi trạng thái** là bước đầu của thiết kế API an toàn khi gặp ngoại lệ. Để có bảo đảm mạnh, cần mở rộng thành quy trình **validate → prepare → commit**, trong đó các phép tính và thay đổi có thể thất bại được thực hiện trên dữ liệu tạm trước khi trạng thái thật trở nên quan sát được. Với đồng thời hoặc tài nguyên bên ngoài, điểm commit phải được bảo vệ bằng khóa, CAS, transaction hay một giao thức tương ứng. Quy tắc quan trọng nhất để tự đánh giá là: *Nếu thao tác ném ngoại lệ tại từng bước, caller sẽ nhìn thấy trạng thái nào?*

### Tham khảo

- [Java SE 17 — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T))
- [Java SE 17 — `Math.addExact` và các phép toán kiểm tra tràn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
- [Java SE 17 — `synchronized` và Java Memory Model (JLS §17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
- [Java SE 17 — `AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
