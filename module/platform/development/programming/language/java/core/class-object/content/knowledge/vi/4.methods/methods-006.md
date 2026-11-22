# Phân tách phương thức truy vấn và phương thức thay đổi trạng thái trong Java

Khi thiết kế class Java, một phương thức có thể **hỏi đối tượng đang ở trạng thái nào** hoặc **yêu cầu đối tượng làm một việc khiến trạng thái thay đổi**. Việc chủ động tách hai ý định này giúp API dễ đọc, dễ kiểm thử và tránh những thay đổi bất ngờ khi người khác chỉ định xem thông tin.

Nguyên tắc thường được gọi là **Command–Query Separation (CQS)**: một method nên đóng vai trò **query** (truy vấn và trả thông tin, không thay đổi trạng thái có thể quan sát được) hoặc **command** (thực hiện thay đổi/hành động, theo phiên bản nghiêm ngặt thường không trả dữ liệu kết quả). Đây là **nguyên tắc thiết kế**, không phải cú pháp hay quy tắc mà trình biên dịch Java bắt buộc. Trong thực tế có những ngoại lệ hợp lý, đặc biệt với thao tác nguyên tử, báo cáo kết quả của một hành động hoặc API chuẩn có sẵn.

Bài học áp dụng cho Java 17+, tập trung vào **thiết kế các phương thức trong một class và hợp đồng của chúng**, chưa cần mô hình ứng dụng nhiều tầng hoặc hạ tầng cơ sở dữ liệu.

## 1. Query và command trả lời hai câu hỏi khác nhau

- **Query:** “Trạng thái hiện tại là gì?” Chẳng hạn `account.getBalance()`, `cart.itemCount()` hoặc `student.isActive()`. Gọi query không được âm thầm thay đổi dữ liệu nghiệp vụ của đối tượng.
- **Command:** “Hãy thay đổi trạng thái theo quy tắc này.” Chẳng hạn `account.deposit(amount)`, `cart.addItem(item)` hoặc `student.activate()`. Command kiểm tra điều kiện, thực hiện thay đổi hợp lệ hoặc báo lỗi rõ ràng.

Ví dụ lớp đếm đơn giản:

~~~java
class Counter {
    private int count;

    int current() {    // query
        return count;
    }

    void increment() { // command
        count++;
    }

    void reset() {     // command
        count = 0;
    }
}
~~~

Đoạn này minh họa khai báo class, chưa có phương thức `main` để tự chạy. `current()` trả về giá trị của field mà không ghi vào field nào. `increment()` và `reset()` thể hiện ý định sửa dữ liệu ngay trong tên gọi.

| Tiêu chí | Query | Command |
| --- | --- | --- |
| Mục tiêu | Quan sát hoặc tính toán thông tin | Thay đổi trạng thái hoặc yêu cầu hành động |
| Ví dụ | `getBalance()`, `size()`, `isEmpty()` | `deposit()`, `add()`, `clear()` |
| Ảnh hưởng đến trạng thái nghiệp vụ | Không thay đổi trạng thái có thể quan sát được theo hợp đồng | Có thể thay đổi; cũng có thể từ chối thao tác |
| Giá trị trả về | Thường trả dữ liệu | Trong CQS nghiêm ngặt thường là `void` |
| Gọi lặp lại không có cập nhật xen giữa | Kết quả logic thường giữ nguyên, nếu không phụ thuộc môi trường ngoài | Có thể thực hiện hành động nhiều lần |
| Lỗi thiết kế phổ biến | Getter vừa đọc vừa cập nhật | Command ngầm trả dữ liệu và che giấu cập nhật khác |

**Không suy luận chỉ từ kiểu trả về:** một method `void print()` vẫn có tác dụng phụ I/O; một method `int getAndIncrement()` vừa trả số vừa thay đổi field. Query và command được phân loại theo **hành vi/hợp đồng**, không phải chỉ bởi tên hay `void`.

**Không đồng nhất CQS với tính thuần khiết tuyệt đối:** một query có thể tạo đối tượng kết quả mới hoặc tính toán cục bộ mà vẫn không sửa trạng thái nghiệp vụ. Với query phụ thuộc đồng hồ, dữ liệu bên ngoài hoặc đồng thời, kết quả cũng có thể thay đổi giữa hai lần gọi dù query không tự thực hiện cập nhật.

## 2. Vì sao tách hai loại phương thức?

### 2.1. Giảm tác dụng phụ bất ngờ

Xem thiết kế sau:

~~~java
class BadScore {
    private int points;

    int getPoints() {
        points++;       // Sai kỳ vọng: chỉ hỏi nhưng lại sửa
        return points;
    }
}
~~~

Đoạn khai báo minh họa một **query bị trộn command**. Người đọc có thể dùng `getPoints()` nhiều lần để hiển thị giao diện hoặc ghi log, vô tình làm điểm tăng mỗi lần. Việc debug trở nên khó vì “đọc dữ liệu” lại gây thay đổi.

Thiết kế có ý định rõ hơn:

~~~java
class Score {
    private int points;

    int getPoints() {
        return points;  // Query: chỉ đọc
    }

    void awardPoint() {
        points++;       // Command: sửa trạng thái
    }
}
~~~

Cách gọi `awardPoint()` báo cho người sử dụng rằng hành động có thể làm thay đổi điểm, còn `getPoints()` có thể được gọi để quan sát mà không tăng điểm.

### 2.2. Dễ viết kiểm thử

Với query, có thể kiểm tra kết quả trả về và khẳng định trạng thái trước/sau không đổi. Với command, có thể kiểm tra một thay đổi hợp lệ, invariant sau thay đổi và trường hợp nhập dữ liệu sai không để lại trạng thái dở dang.

### 2.3. Hợp đồng rõ ràng khi mở rộng class

Khi nhiều method đều có cả “đọc rồi âm thầm sửa”, code gọi khó biết trình tự tác động. Phân tách giúp định nghĩa được điều kiện trước/sau: gọi query để lấy thông tin, gọi command khi thật sự có ý định thay đổi. Điều này hỗ trợ đóng gói (*encapsulation*) và giảm phụ thuộc vào các chi tiết field nội bộ.

## 3. Ví dụ hoàn chỉnh: ví tiền với query, command và snapshot

Tạo một ví giữ số dư bằng **`long` đơn vị nhỏ nhất** (ví dụ đồng nếu mô hình phù hợp), tránh dùng `double` cho một khoản tiền cần tính chính xác. Constructor thiết lập invariant “số dư không âm”, query chỉ đọc, command phải kiểm tra trước khi thay đổi.

Lưu đoạn sau thành tệp **`WalletCqsDemo.java`**:

~~~java
public class WalletCqsDemo {
    record WalletSnapshot(
            String owner,
            long balanceCents,
            int transactionCount) {
    }

    static final class Wallet {
        private final String owner;
        private long balanceCents;
        private int transactionCount;

        Wallet(String owner, long openingBalanceCents) {
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("Chủ ví không hợp lệ");
            }
            if (openingBalanceCents < 0) {
                throw new IllegalArgumentException("Số dư âm");
            }
            this.owner = owner;
            this.balanceCents = openingBalanceCents;
        }

        String getOwner() {
            return owner;                       // query
        }

        long getBalanceCents() {
            return balanceCents;                // query
        }

        int getTransactionCount() {
            return transactionCount;            // query
        }

        WalletSnapshot snapshot() {
            return new WalletSnapshot(
                    owner, balanceCents, transactionCount); // query
        }

        void deposit(long cents) {               // command
            if (cents <= 0) {
                throw new IllegalArgumentException("Số tiền phải dương");
            }

            long nextBalance = Math.addExact(balanceCents, cents);
            int nextCount = Math.incrementExact(transactionCount);
            balanceCents = nextBalance;
            transactionCount = nextCount;
        }

        void withdraw(long cents) {              // command
            if (cents <= 0) {
                throw new IllegalArgumentException("Số tiền phải dương");
            }
            if (cents > balanceCents) {
                throw new IllegalStateException("Không đủ số dư");
            }

            int nextCount = Math.incrementExact(transactionCount);
            balanceCents -= cents;
            transactionCount = nextCount;
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet("Lan", 1_000);
        WalletSnapshot before = wallet.snapshot();

        System.out.println("Chủ ví: " + wallet.getOwner());
        wallet.deposit(500);
        wallet.withdraw(200);

        System.out.println("Ảnh chụp ban đầu: "
                + before.balanceCents());
        System.out.println("Số dư hiện tại: "
                + wallet.getBalanceCents());
        System.out.println("Số giao dịch: "
                + wallet.getTransactionCount());

        long firstRead = wallet.getBalanceCents();
        long secondRead = wallet.getBalanceCents();
        System.out.println("Hai lần truy vấn: "
                + firstRead + ", " + secondRead);

        try {
            wallet.withdraw(2_000);
        } catch (IllegalStateException ex) {
            System.out.println("Rút lỗi: " + ex.getMessage());
        }

        System.out.println("Sau rút lỗi: "
                + wallet.getBalanceCents());
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 WalletCqsDemo.java
java WalletCqsDemo
~~~

**Stdout chính xác:**

~~~text
Chủ ví: Lan
Ảnh chụp ban đầu: 1000
Số dư hiện tại: 1300
Số giao dịch: 2
Hai lần truy vấn: 1300, 1300
Rút lỗi: Không đủ số dư
Sau rút lỗi: 1300
~~~

Cách đọc kết quả:

1. Constructor tạo ví với `1_000` đơn vị và số giao dịch mặc định bằng `0`. Hai field dữ liệu chỉ được thay đổi qua các command được thiết kế cho chúng.
2. `snapshot()` tạo một **record bất biến về mặt cấu trúc của ví dụ** có số dư `1000`. Sau đó ví thay đổi; biến `before` vẫn giữ số cũ. Việc tạo giá trị trả về mới **không phải sửa trạng thái của ví**.
3. `deposit(500)` tính trước số dư mới bằng `Math.addExact`, sau đó tăng số lần giao dịch; `withdraw(200)` kiểm tra đủ tiền trước khi trừ. Số dư cuối là `1000 + 500 - 200 = 1300`.
4. Hai lời gọi `getBalanceCents()` không ghi dữ liệu, nên cùng nhận `1300` khi không có command xen giữa và ví không bị một thread khác sửa.
5. `withdraw(2000)` bị từ chối **trước khi sửa field** vì số tiền vượt số dư. Lỗi được báo bằng `IllegalStateException`; số dư vẫn `1300`, số giao dịch vẫn `2`.

Sử dụng `Math.addExact` và `Math.incrementExact` để phát hiện tràn số thay vì lặng lẽ ghi sai giá trị. Trong ví dụ, các giá trị mới được tính trước khi gán field nhằm tránh cập nhật một phần nếu phép tính ném `ArithmeticException`. Ví dụ được thiết kế cho **một luồng hoặc được đồng bộ ở nơi khác**; hai command đồng thời gọi trên cùng `Wallet` vẫn có nguy cơ race nếu không bổ sung đồng bộ.

**Thiết kế quan trọng:** `getBalanceCents()`, `getTransactionCount()` và `snapshot()` đều là query. `deposit()` và `withdraw()` là command. Constructor xác lập trạng thái ban đầu nhưng không phải một method query/command được gọi trên object đã có.

## 4. Command có nhất thiết phải trả `void`?

Phiên bản CQS nghiêm ngặt khuyến nghị:

- Query trả dữ liệu và không thay đổi trạng thái quan sát được.
- Command thực hiện hành động, không kết hợp việc hỏi để trả dữ liệu nghiệp vụ; trong Java thường viết `void` và biểu diễn thất bại bằng exception phù hợp.

Tuy nhiên, **Java không cấm command trả kết quả**. Rất nhiều API thư viện chuẩn kết hợp thay đổi và trả thông tin:

~~~java
// Các ví dụ dùng trong method đã có đối tượng tương ứng:
boolean removed = list.remove("A");       // sửa list, trả kết quả
String previous = map.put("id", "new");    // sửa map, trả giá trị cũ
int old = atomicInteger.getAndIncrement(); // tăng atomic, trả giá trị trước
~~~

Đây là các mảnh minh họa, không phải chương trình độc lập; cần biến `list`, `map` và `atomicInteger` có kiểu phù hợp. Những method này chủ động ghép thay đổi và kết quả thành **một thao tác logic**, đôi khi cần thiết để tránh race hoặc cung cấp API tiện dụng.

Nếu yêu cầu nghiệp vụ là “thử đặt chỗ, rồi cho biết đã thành công chưa”, một method `boolean tryReserve()` có thể là API hợp lý dù không tuân theo CQS nghiêm ngặt. Khi áp dụng thực dụng, hãy đặt tên lộ rõ hành động (`tryReserve`, `remove`, `getAndIncrement`) và ghi hợp đồng kết quả/side effect.

**Đừng máy móc tách mọi thao tác kết hợp thành hai lời gọi** nếu như vậy làm hỏng tính nguyên tử. Ví dụ thay `getAndIncrement()` bằng `get()` rồi `incrementAndGet()` từ hai thread khác nhau không còn đảm bảo đọc giá trị cũ và tăng là một hành động không bị xen kẽ.

## 5. Getter không luôn là query đúng nghĩa

Tên `get...` thường gợi ý một phép đọc, nhưng phải xem **thân method và hiệu ứng quan sát được**.

### 5.1. Getter âm thầm thay đổi field

~~~java
class BadSequence {
    private int nextId = 1;

    int getNextId() {
        return nextId++; // trả số và làm thay đổi trạng thái
    }
}
~~~

Đây không phải query thuần. Tên rõ nghĩa hơn là `allocateId()` hoặc `getAndIncrementId()` để nói hành động **tiêu thụ** một ID. Nếu cần chỉ xem số tiếp theo dự kiến, thêm query độc lập `peekNextId()` không sửa field, còn command cấp phát ID có thể trả kết quả như một ngoại lệ thực dụng.

### 5.2. Getter trả thẳng mutable reference

Giả sử class nội bộ giữ danh sách có thể thay đổi:

~~~java
import java.util.ArrayList;
import java.util.List;

class UnsafePlaylist {
    private final List<String> songs = new ArrayList<>();

    List<String> getSongs() {
        return songs; // caller có thể sửa trực tiếp!
    }
}
~~~

Method `getSongs()` tự nó không ghi field, nhưng caller nhận **tham chiếu đến chính collection nội bộ** và có thể gọi `getSongs().clear()`, vượt qua kiểm tra trong các command của class. Nếu một command phải duy trì invariant, đây là đường làm hỏng đóng gói.

Với danh sách gồm các `String` bất biến, cách thiết kế rõ ràng hơn:

~~~java
import java.util.ArrayList;
import java.util.List;

class Playlist {
    private final List<String> songs = new ArrayList<>();

    List<String> getSongs() {
        return List.copyOf(songs); // query trả snapshot không sửa được
    }

    void addSong(String song) {
        if (song == null || song.isBlank()) {
            throw new IllegalArgumentException("Tên bài hát trống");
        }
        songs.add(song); // command
    }
}
~~~

Cả hai là **đoạn khai báo để học**, chưa phải chương trình có `main`. `List.copyOf` tạo kết quả không sửa được qua các API thay đổi danh sách và không chứa `null`. Với phần tử `String` bất biến, đây là snapshot thích hợp. Đối với collection chứa object mutable, `List.copyOf` chỉ sao chép cấu trúc danh sách **nông (shallow)**, không tự biến từng phần tử thành immutable.

`Collections.unmodifiableList(songs)` cung cấp một **view không cho sửa qua view**, nhưng có thể phản ánh các thay đổi sau đó của danh sách gốc; nó không tương đương một snapshot cố định. Hãy chọn theo hợp đồng API mong muốn.

### 5.3. Getter cần tính toán có được coi là query?

Có, miễn là nó không thay đổi trạng thái nghiệp vụ quan sát được:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    long area() {
        return (long) width * height; // query tính giá trị
    }
}
~~~

`area()` có phép nhân và phép chuyển kiểu nhưng không ghi field; vẫn là query. Dùng `long` cho kết quả để tránh phép nhân `int * int` tràn trong phạm vi mà phép nhân `long` này biểu diễn được.

## 6. Có phải query tuyệt đối không được có bất kỳ side effect nào?

CQS hướng tới **không thay đổi trạng thái có thể quan sát của đối tượng/hợp đồng nghiệp vụ** khi hỏi thông tin. Trong hệ thống thực tế, ranh giới “side effect” có thể tinh tế:

- **Cấp phát object tạm thời, tính toán giá trị trả về:** thường được phép trong query; đó không phải thay đổi trạng thái nghiệp vụ.
- **Ghi log, cập nhật metric:** là side effect kỹ thuật. Chúng có thể được chấp nhận theo hợp đồng hệ thống, nhưng nếu một metric/log có ý nghĩa quan sát rõ ràng thì query không còn “không có bất cứ tác dụng phụ nào” theo nghĩa nghiêm ngặt.
- **Lazy cache/memoization:** một getter tính rồi lưu cache làm thay đổi state triển khai. Nếu thay đổi này hoàn toàn trong suốt đối với caller, một số thiết kế vẫn xem getter là query về mặt nghiệp vụ; cần đặc biệt kiểm soát thread safety, invalidation, lỗi và chi phí tính toán.
- **Đọc đồng hồ, file hoặc database:** có thể không sửa đối tượng nhưng trả kết quả thay đổi theo thời gian hoặc external state. Không nên hứa query luôn trả cùng giá trị mọi lúc.
- **Gọi service ngoài có tác động:** nếu method mang tên `get...` lại phát lệnh thanh toán hay cập nhật database thì rõ ràng vi phạm kỳ vọng của API truy vấn.

Khi API cần những bảo đảm nghiêm ngặt (ví dụ kiểm thử hoặc giao dịch), hãy **viết rõ hợp đồng**: trạng thái nào không đổi, dữ liệu lấy từ đâu và việc truy vấn có thể ném exception hay gây I/O không.

## 7. Thiết kế command để giữ invariant

*Invariant* là điều kiện mà đối tượng cần thỏa khi ở trạng thái hợp lệ. Với ví dụ ví tiền, invariant là `balanceCents >= 0`. Command phải bảo vệ invariant trong lúc kiểm tra và cập nhật.

Ví dụ **không nên làm**:

~~~java
class UnsafeWallet {
    private long balance;

    long getBalance() {
        return balance;
    }

    void setBalance(long newBalance) {
        balance = newBalance; // caller có thể gán số âm
    }
}
~~~

Đây là đoạn minh họa. Setter mở ra việc thay đổi tùy ý; tên `setBalance` không nêu nghiệp vụ. Nên cân nhắc thay bằng command có ý nghĩa như `deposit(cents)` và `withdraw(cents)`, mỗi command quản lý validation phù hợp.

Một command tốt thường có ba giai đoạn rõ ràng:

1. **Kiểm tra:** điều kiện đầu vào, quyền thao tác, trạng thái hiện tại và invariant.
2. **Tính toán:** chuẩn bị giá trị mới; các phép có thể lỗi nên thực hiện trước những phép gán không thể rollback, khi khả thi.
3. **Áp dụng:** thay đổi trạng thái trong ranh giới đồng bộ/giao dịch thích hợp; không để object vào trạng thái dở dang.

Nếu command thất bại, hợp đồng nên nói trạng thái có thể đã thay đổi một phần hay được bảo đảm giữ nguyên. Trong ví dụ `Wallet`, các nhánh validation và tràn số đã được kiểm tra trước khi gán; ở ứng dụng có nhiều hệ thống ngoài, bảo đảm rollback còn phụ thuộc transaction và hạ tầng.

**Không nhất thiết mọi command đều làm trạng thái khác đi.** Ví dụ `activate()` trên đối tượng đã active có thể được định nghĩa là idempotent, không sửa gì khi trạng thái đã đạt mục tiêu. Nó vẫn là command vì ý định yêu cầu chuyển/thiết lập trạng thái.

## 8. Trả về giá trị từ command: cách đặt hợp đồng rõ nghĩa

Đối với Java API thực tế, có ba phong cách phổ biến:

| Phong cách | Ví dụ | Đặc điểm |
| --- | --- | --- |
| CQS chặt | `void withdraw(long amount)` | Lệnh thay đổi; query riêng để đọc số dư |
| Command trả trạng thái thực thi | `boolean tryWithdraw(long amount)` | Một hành động kết hợp kết quả thành công/thất bại |
| Command trả object kết quả | `WithdrawalResult withdraw(...)` | Trả mã trạng thái, biên nhận hoặc thông tin giao dịch |

Cách chọn dựa vào hợp đồng, nhất là yêu cầu nguyên tử. Một command có thể trả về **mã kết quả không mang nghĩa query trước đó**, chẳng hạn id được cấp khi tạo mới, nếu đây là cách duy nhất tránh mất tính đúng đắn khi nhiều thread cạnh tranh.

Nếu chọn strict CQS, lỗi có thể được báo bằng exception phù hợp; nhưng không nên biến exception thành luồng xử lý thường xuyên khi nghiệp vụ coi từ chối là kết quả dự kiến và xảy ra phổ biến. Khi đó `try...` hoặc kiểu kết quả có cấu trúc dễ hiểu hơn.

Không đặt tên `getOrCreateSession()` rồi coi nó là query: method “get or create” **có thể tạo session**. Tên `findOrCreate...` ít nhất thể hiện khả năng thay đổi, nhưng nếu cần áp dụng CQS chặt nên tách query `findSession` và command `createSession`, miễn là vẫn giải quyết được race giữa việc tìm và tạo.

## 9. Thread safety: tách hai method không thay thế synchronization

CQS giúp ý định rõ ràng, **không tự giải quyết vấn đề đồng thời**. Với một `Wallet` được nhiều thread sử dụng, `getBalanceCents()` và `withdraw()` có thể cùng chạy; nếu không dùng cơ chế đồng bộ, việc đọc và ghi có thể gây race/visibility và invariant có thể bị phá vỡ.

Một phiên bản đơn giản bảo vệ bộ đếm bằng cùng monitor:

~~~java
class SynchronizedCounter {
    private int count;

    synchronized int current() { // query được đồng bộ
        return count;
    }

    synchronized void increment() { // command được đồng bộ
        count++;
    }
}
~~~

Đây là đoạn khai báo minh họa. `synchronized` bảo vệ access khi **mọi** thao tác liên quan đều đi qua monitor phù hợp. Query vẫn là query vì không sửa count.

Nhưng **hai lời gọi riêng lẻ vẫn không tạo một thao tác nguyên tử ghép**:

~~~java
// Không đủ để đảm bảo thao tác "nếu count < 10 thì tăng" atomic:
if (counter.current() < 10) {
    counter.increment();
}
~~~

Giả sử hai thread cùng đọc `9`, cả hai có thể quyết định tăng và tổng trở thành `11`. Để giữ invariant “không vượt 10”, đưa **kiểm tra + cập nhật** vào cùng một synchronized command:

~~~java
class BoundedCounter {
    private int count;

    synchronized int current() {
        return count; // query
    }

    synchronized void incrementIfBelowTen() {
        if (count < 10) {
            count++;
        }
    }
}
~~~

Đoạn này cũng là minh họa. Method command bảo vệ được điều kiện giới hạn vì không có thread khác xen giữa kiểm tra và cập nhật khi các truy cập đều tuân theo cùng khóa.

**Quy tắc thực hành:** query có thể giúp giao diện **hiển thị** trạng thái, nhưng không dùng kết quả query cũ làm bằng chứng rằng command tương lai sẽ chắc chắn hợp lệ trong môi trường đồng thời. Command phải **kiểm tra lại** điều kiện trong ranh giới đồng bộ hoặc transaction thích hợp.

## 10. Query có thể phụ thuộc trạng thái ngoài object

Một số trường hợp query không hoàn toàn xác định chỉ bởi instance field:

~~~java
import java.time.Clock;
import java.time.Instant;

class Deadline {
    private final Instant expiresAt;
    private final Clock clock;

    Deadline(Instant expiresAt, Clock clock) {
        this.expiresAt = expiresAt;
        this.clock = clock;
    }

    boolean isExpired() {
        return !Instant.now(clock).isBefore(expiresAt);
    }
}
~~~

Đây là đoạn khai báo, không có `main`. `isExpired()` **không thay đổi trạng thái của `Deadline`**, nên phù hợp vai trò query, nhưng kết quả có thể đổi từ `false` sang `true` khi thời gian trôi qua. Inject `Clock` giúp kiểm thử kiểm soát thời gian mà không cần thao tác với đồng hồ hệ thống.

Tương tự, query đọc một bảng database có thể trả kết quả mới sau khi người khác cập nhật bảng, dù query không trực tiếp thực hiện thay đổi. Phân loại query/command là về **ý định và tác dụng của chính lời gọi**, không phải lời hứa “mỗi lần gọi mãi mãi cùng kết quả”.

## 11. CQS khác CQRS như thế nào?

**CQS** (*Command–Query Separation*) là nguyên tắc ở mức **phương thức/API**: một method nên có trách nhiệm đọc **hoặc** thay đổi trạng thái.

**CQRS** (*Command Query Responsibility Segregation*) là một **mẫu kiến trúc** tách đường xử lý lệnh và đường xử lý truy vấn (thường ở tầng ứng dụng, service hoặc hệ thống). Một hệ thống CQRS có thể có model đọc/model ghi riêng, nhưng **không bắt buộc** mọi dự án cần hai database hoặc cần event sourcing.

| Đặc điểm | CQS | CQRS |
| --- | --- | --- |
| Cấp độ áp dụng | Method, class, API | Kiến trúc ứng dụng, luồng xử lý read/write |
| Mục tiêu | Hợp đồng method và side effect rõ nghĩa | Tối ưu mô hình và trách nhiệm đọc/ghi |
| Có cần hạ tầng riêng? | Không | Không bắt buộc; tùy thiết kế |
| Có bắt buộc event sourcing? | Không | Không |
| Ví dụ | `getBalance()` khác `deposit()` | `AccountQueryService` khác `AccountCommandService` |

Trong module Java class-object, hãy nắm CQS **ngay trong class** trước; CQRS chỉ là điểm phân biệt khái niệm để tránh dùng nhầm hai tên.

## 12. Chọn tên method cho đúng ý định

Tên method là tài liệu ngắn nhất về side effect. Một số gợi ý:

| Ý định | Tên minh họa | Lý do |
| --- | --- | --- |
| Đọc field/thuộc tính | `getName()`, `balance()` | Người gọi kỳ vọng không thay đổi nghiệp vụ |
| Truy vấn boolean | `isActive()`, `hasItems()` | Thể hiện câu hỏi |
| Tính toán từ trạng thái | `calculateTotal()`, `estimatedCost()` | Trả kết quả tính toán |
| Tìm kiếm | `findById()`, `contains()` | Thể hiện phép hỏi |
| Tăng, giảm, cập nhật | `increment()`, `rename()`, `deposit()` | Thể hiện hành động thay đổi |
| Xóa hoặc đặt lại | `removeItem()`, `clear()` | Thể hiện ý định thay đổi |
| Thực hiện có điều kiện và trả kết quả | `tryReserve()`, `removeIfPresent()` | Người gọi biết đây là hành động có kết quả |
| Đọc và sửa nguyên tử | `getAndIncrement()`, `computeIfAbsent()` | Tên chủ động cho thấy method có thể thay đổi |

Không phải cứ method bắt đầu bằng `get` là query; đọc **hợp đồng và implementation** để xác nhận. Ngược lại, một `calculateTotal()` trả tiền từ các item không nên tự ý thêm item, chốt đơn hàng hoặc ghi phí vào field.

Getter và setter theo phong cách JavaBeans có giá trị với một số framework, nhưng trong domain model, việc tự động viết setter cho mọi field thường phá mất quyền kiểm soát invariant. Chỉ mở các thao tác hợp lệ với nghiệp vụ.

## 13. Trường hợp cần suy nghĩ kỹ hơn

### 13.1. Cập nhật object rồi trả `this` để chain

~~~java
class MutableBuilder {
    private String value = "";

    MutableBuilder append(String text) {
        value += text;
        return this;
    }
}
~~~

Đây là đoạn minh họa về API dạng builder; `append()` là **command có return**, vì nó thay đổi `value` rồi trả về `this` để viết chuỗi lời gọi. Đây là một ngoại lệ thiết kế có chủ ý, không phải query. Trong ứng dụng cần strict CQS, có thể chọn builder command trả `void` hoặc áp dụng kiểu bất biến trả object mới theo hợp đồng khác.

### 13.2. Immutable object và phương thức “with”

~~~java
record Point(int x, int y) {
    Point movedBy(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}
~~~

`movedBy()` **không sửa** `Point` hiện tại; nó trả một instance khác. Với một immutable value object, method này có thể xem là phép tính/query tạo giá trị mới dù tên gợi hành động dịch chuyển. Điều quan trọng là hợp đồng “không mutate receiver”; code gọi nên biết cần giữ kết quả trả về nếu muốn dùng điểm mới.

### 13.3. Query trả giá trị tham chiếu

Nếu query trả `List<OrderItem>` và các `OrderItem` mutable, dù dùng `List.copyOf`, người nhận vẫn có thể sửa trạng thái các phần tử được chia sẻ. Khi thiết kế query không cho phép caller can thiệp dữ liệu nội bộ, cân nhắc trả **immutable DTO/record snapshot**, deep copy thích hợp hoặc các API chỉ đọc có hợp đồng rõ. “Method không gán field” chưa đủ để bảo đảm đóng gói nếu nó làm lộ object con mutable.

### 13.4. Event và notification

Nếu command `rename("New")` phát một domain event, event là kết quả của việc thay đổi trạng thái và thường phù hợp với trách nhiệm command. Còn query `getName()` mà lại âm thầm gửi email hoặc kích hoạt cập nhật bên ngoài gây bất ngờ lớn và làm khó kiểm thử. Cần phân biệt logging/metrics thuần kỹ thuật với tác động nghiệp vụ.

## 14. Kiểm thử hợp đồng CQS

Không bắt buộc một framework kiểm thử mới có thể suy luận đúng. Với một object đơn giản, có thể kiểm chứng:

1. **Query trả giá trị đúng:** trạng thái ban đầu tạo từ constructor dẫn đến `getBalanceCents() == 1000`.
2. **Query không thay đổi state:** chụp trạng thái trước; gọi query một hoặc nhiều lần; chụp lại và so sánh các giá trị nghiệp vụ.
3. **Command tạo kết quả đúng:** sau `deposit(500)`, số dư tăng đúng một lần; `getTransactionCount()` tăng một.
4. **Command từ chối dữ liệu sai:** nhập số âm hoặc yêu cầu rút vượt số dư phải lỗi như hợp đồng; state giữ nguyên nếu đó là bảo đảm thiết kế.
5. **Không rò mutable state:** sửa collection/đối tượng trả về từ query không được phá invariant của object nếu API hứa cung cấp dữ liệu chỉ đọc.
6. **Đồng thời:** nếu đối tượng được chia sẻ giữa thread, phải có test và lập luận theo synchronization protocol; chỉ chạy nhiều lần rồi “chưa thấy sai” không đủ làm bằng chứng thread-safe.

Ví dụ kiểm tra thủ công sau (mảnh code nằm trong một method có đối tượng `wallet` từ ví dụ `WalletCqsDemo`):

~~~java
long before = wallet.getBalanceCents();

wallet.getOwner();
wallet.snapshot();
wallet.getTransactionCount();

long after = wallet.getBalanceCents();
System.out.println(before == after); // true nếu không có cập nhật xen giữa
~~~

Các query này được thiết kế để chỉ đọc, vì vậy trong ngữ cảnh đơn luồng kết quả so sánh là `true`. Không nên dùng riêng điều kiện `before == after` làm phép chứng minh cho **mọi** dạng side effect: ví dụ method có thể tạm đổi rồi hoàn lại field, ghi log hoặc sửa một object con mà phép so sánh chỉ số dư không phát hiện.

## 15. Những lỗi phổ biến và cách sửa

1. **Getter tăng bộ đếm mỗi lần gọi:** `getVisits()` lại thực hiện `visits++`. Hãy tách `registerVisit()` (command) và `getVisits()` (query).
2. **Đọc danh sách bằng getter rồi sửa danh sách qua kết quả:** `cart.getItems().clear()` phá đóng gói. Chỉ cung cấp bản xem hoặc snapshot thích hợp; tạo `clearCart()` với validation nếu xóa giỏ là hành động nghiệp vụ.
3. **Cho mọi field một setter tùy ý:** có thể tạo trạng thái bất hợp lệ. Thay bằng command theo hành động được phép.
4. **Dựa vào tên `get` để giả định không side effect:** các method `getOrCreate...` hay `getAndIncrement...` có ý nghĩa thay đổi. Đọc hợp đồng và đặt tên rõ.
5. **Tách thao tác nguyên tử thành query rồi command:** ví dụ kiểm tra số dư rồi rút sau ở hai lời gọi độc lập khi có nhiều thread. Đưa kiểm tra và cập nhật vào cùng transaction/lock.
6. **Cho rằng command luôn phải `void`:** nhiều API đúng đắn cần trả mã kết quả, phiên bản mới hay giá trị trước cập nhật. Hiểu CQS là nguyên tắc định hướng và chọn ngoại lệ có lý do.
7. **Query ghi dữ liệu để “tiện” cho lượt sau:** memoization/lazy initialization có thể phù hợp nhưng cần hợp đồng, tính nhất quán và đồng bộ rõ ràng. Tránh cache khiến mỗi lần query đổi ngữ nghĩa hoặc thất bại khác nhau ngoài mong đợi.
8. **Quên phản ứng với lỗi:** command ném exception sau khi đã sửa một số field có thể để lại object không hợp lệ. Tính toán/kiểm tra trước và áp dụng cập nhật atomically khi yêu cầu.
9. **Nhầm CQS và CQRS:** CQS là thiết kế method; CQRS nói đến phân chia trách nhiệm trong kiến trúc hệ thống, không đồng nghĩa yêu cầu microservice hoặc hai database.
10. **Cho rằng query luôn trả cùng giá trị:** trạng thái có thể được sửa giữa các lần gọi hoặc nguồn dữ liệu ngoài thay đổi. CQS không loại bỏ biến thiên do thời gian hay các actor khác.

## 16. Tự kiểm tra

**Câu 1.** Vì sao `int getBalanceAndChargeFee()` là một tên gây chú ý khi xét CQS?

**Đáp án:** Tên cho biết method vừa đọc số dư vừa thu phí (thay đổi state). Nếu caller chỉ muốn đọc số dư thì hành động thu phí là side effect bất ngờ. Nên phân tách query đọc số dư và command thu phí, hoặc dùng tên/hợp đồng rõ ràng nếu thao tác kết hợp là bắt buộc.

**Câu 2.** Một getter không gán field nhưng trả thẳng `ArrayList` nội bộ có đủ để được xem là query an toàn không?

**Đáp án:** Việc gọi getter có thể không mutate tức thời, nhưng API làm lộ tham chiếu mutable, cho phép caller bypass command và phá invariant. Nên trả view hoặc snapshot phù hợp, hoặc thiết kế read-only DTO.

**Câu 3.** Method `void reset()` có phải query vì nó không trả kết quả không?

**Đáp án:** Không. `reset()` là command vì ý định thay đổi trạng thái, dù trả `void`.

**Câu 4.** Có nên thay `AtomicInteger.getAndIncrement()` bằng `get()` rồi `incrementAndGet()` chỉ để tuân thủ CQS nghiêm ngặt không?

**Đáp án:** Không nên nếu cần trả giá trị trước cập nhật một cách nguyên tử. Hai lời gọi riêng tạo cơ hội cho các thread khác xen vào; `getAndIncrement()` là một API ghép có chủ ý.

**Câu 5.** Đối tượng `Wallet` có `getBalanceCents()` và `withdraw(...)`. Vì sao logic `if (wallet.getBalanceCents() >= amount) wallet.withdraw(amount)` không đủ để đảm bảo đúng trong môi trường đa luồng?

**Đáp án:** Có thể có cập nhật xen vào giữa query và command. Command phải tự kiểm tra lại điều kiện trong vùng đồng bộ/transaction thích hợp; phép kiểm tra ngoài chỉ dùng cho gợi ý hiển thị.

**Câu 6.** `Point movedBy(...)` trên immutable record trả một `Point` mới có sửa receiver không?

**Đáp án:** Không. Nó tạo giá trị mới, giữ nguyên đối tượng cũ. Ý nghĩa method phải được thể hiện rõ với caller để caller biết dùng kết quả trả về nếu muốn “điểm đã di chuyển”.

**Câu 7.** Việc áp dụng CQS cho class có bắt buộc dùng CQRS, event sourcing hoặc kiến trúc microservice không?

**Đáp án:** Không. Một Java class đơn giản cũng có thể tuân theo CQS, hoàn toàn không cần các mẫu kiến trúc đó.

Khi thiết kế một method Java, hãy đặt bốn câu hỏi: **người gọi đang hỏi hay yêu cầu thay đổi?**; **method có side effect nào dễ gây bất ngờ?**; **invariant được bảo vệ ở đâu?**; và **nếu cần vừa thay đổi vừa trả kết quả, có yêu cầu nguyên tử hoặc hợp đồng nghiệp vụ nào biện minh cho việc kết hợp không?** Trả lời rõ các câu hỏi này sẽ giúp cách phân tách query/command mang lại tính đúng đắn thực tế thay vì chỉ là quy tắc đặt tên.
