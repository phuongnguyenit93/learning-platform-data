# Trạng thái, hành vi và danh tính của một đối tượng trong Java

Một **đối tượng (object)** trong Java không chỉ là một tập hợp dữ liệu. Khi chương trình làm việc với đối tượng, cần phân biệt ba khía cạnh: **trạng thái (state)**, **hành vi (behavior)** và **danh tính (identity)**. Ba khía cạnh liên quan chặt chẽ nhưng trả lời ba câu hỏi khác nhau:

| Khía cạnh | Câu hỏi | Trong Java thường thể hiện qua |
| --- | --- | --- |
| Trạng thái | Đối tượng đang có dữ liệu gì? | Giá trị của các trường (instance fields) ở thời điểm quan sát |
| Hành vi | Đối tượng có thể làm gì và phản ứng ra sao? | Phương thức (instance methods), quy tắc và điều kiện khi thao tác |
| Danh tính | Đây có phải đúng cùng một đối tượng hay không? | Quan hệ tham chiếu đến cùng đối tượng; kiểm tra bằng `==` với hai tham chiếu |

Ví dụ, một ví điện tử có mã ví, chủ sở hữu và số dư. Đó là trạng thái. Ví cho phép nạp, rút tiền sau khi kiểm tra điều kiện. Đó là hành vi. Hai biến cùng trỏ đến một ví là cùng một đối tượng; hai ví khác nhau có mã và số dư giống nhau vẫn là hai đối tượng khác nhau trong bộ nhớ thực thi. Đó là danh tính.

## 1. Trạng thái: dữ liệu của từng đối tượng

Một `class` khai báo các trường; mỗi đối tượng được tạo từ class thường có **bản giá trị riêng của các instance field**. Trạng thái có thể thay đổi khi phương thức cập nhật các trường đó.

~~~java
final class TemperatureSensor {
    private final String sensorId;
    private double celsius;

    TemperatureSensor(String sensorId, double initialCelsius) {
        this.sensorId = sensorId;
        this.celsius = initialCelsius;
    }

    double readCelsius() {
        return celsius;
    }

    void updateReading(double nextCelsius) {
        celsius = nextCelsius;
    }
}
~~~

`sensorId` được gán lúc khởi tạo và không thể gán lại bởi mã Java bình thường sau đó vì trường có `final`. `celsius` có thể thay đổi. Hai instance `TemperatureSensor` có thể cùng nhiệt độ nhưng vẫn có trạng thái độc lập. Trạng thái không chỉ là dữ liệu có thể thay đổi: các trường `final` cũng thuộc trạng thái của đối tượng.

**Cần phân biệt instance field và static field.** Một trường `static` thuộc class và được chia sẻ giữa các đối tượng, nên không đại diện cho dữ liệu riêng của từng instance.

~~~java
final class Ticket {
    private static int nextNumber = 1; // Chung cho class Ticket
    private final int number;           // Riêng từng đối tượng Ticket

    Ticket() {
        number = nextNumber++;
    }

    int number() {
        return number;
    }
}
~~~

`new Ticket()` lần thứ nhất nhận `number = 1`, lần thứ hai nhận `number = 2` nếu đoạn mã chạy tuần tự từ trạng thái ban đầu. `nextNumber` là trạng thái chia sẻ, không phải một bản sao riêng cho mỗi ticket. Ví dụ đếm này chưa an toàn nếu nhiều luồng đồng thời gọi constructor.

### Trạng thái khi khởi tạo

- Trường instance nhận giá trị mặc định trước khi các bước khởi tạo tương ứng hoàn tất: số nguyên `0`, `boolean` là `false`, tham chiếu là `null`. Sau đó initializer và constructor có thể thiết lập giá trị có ý nghĩa.
- Constructor phải thiết lập trạng thái ban đầu hợp lệ; nếu không, những phương thức về sau sẽ phải đối phó với đối tượng không nhất quán.
- Một biến cục bộ trong phương thức **không** trở thành trạng thái của đối tượng chỉ vì được khai báo trong phương thức đó; nó tồn tại trong lần gọi tương ứng.

Không nên hiểu “trạng thái” là toàn bộ mọi biến có thể truy cập từ một phương thức. Khi nói trạng thái riêng của đối tượng, trọng tâm là các instance field và dữ liệu mà chúng tham chiếu đến.

## 2. Hành vi: đối tượng thực hiện công việc và bảo vệ quy tắc

Hành vi thường được biểu diễn bằng instance method. Phương thức có thể **đọc** trạng thái (`balance()`), **thay đổi** trạng thái (`deposit()`), **tính toán** kết quả mà không thay đổi trạng thái, hoặc phối hợp với đối tượng khác. Mục tiêu của thiết kế hướng đối tượng là giữ dữ liệu và những thao tác hợp lệ lên dữ liệu cùng một ranh giới trách nhiệm.

Đối tượng ví có quy tắc: chỉ được nạp/rút số tiền dương, không được rút vượt số dư. Thay vì cho mọi nơi tự sửa `balance`, ta để trường `private` và công khai các hành vi hợp lệ.

## 3. Ví dụ Java 17+: cả ba khía cạnh trong một chương trình

Lưu tệp dưới tên **`ObjectStateBehaviorIdentityDemo.java`**:

~~~java
public class ObjectStateBehaviorIdentityDemo {

    static final class Wallet {
        private final String id;
        private String owner;
        private long balance;

        Wallet(String id, String owner, long openingBalance) {
            this.id = requireText(id, "id");
            this.owner = requireText(owner, "owner");
            if (openingBalance < 0) {
                throw new IllegalArgumentException("openingBalance must be >= 0");
            }
            this.balance = openingBalance;
        }

        String id() {
            return id;
        }

        long balance() {
            return balance;
        }

        void renameOwner(String newOwner) {
            owner = requireText(newOwner, "owner");
        }

        void deposit(long amount) {
            requirePositive(amount);
            balance = Math.addExact(balance, amount);
        }

        void withdraw(long amount) {
            requirePositive(amount);
            if (amount > balance) {
                throw new IllegalArgumentException("Insufficient balance");
            }
            balance -= amount;
        }

        String describe() {
            return id + " | " + owner + " | " + balance;
        }

        private static String requireText(String value, String fieldName) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(fieldName + " is required");
            }
            return value;
        }

        private static void requirePositive(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be > 0");
            }
        }
    }

    public static void main(String[] args) {
        Wallet a = new Wallet("W-01", "An", 1_000);
        Wallet alias = a;
        Wallet other = new Wallet("W-01", "An", 1_000);

        System.out.println("Ban đầu: " + a.describe());
        System.out.println("a == alias: " + (a == alias));
        System.out.println("a == other: " + (a == other));
        System.out.println("a.equals(other): " + a.equals(other));
        System.out.println("Cùng mã ví: " + a.id().equals(other.id()));

        alias.deposit(250);
        a.withdraw(100);

        System.out.println("Ví a sau cập nhật: " + a.describe());
        System.out.println("Ví other: " + other.describe());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac ObjectStateBehaviorIdentityDemo.java
java ObjectStateBehaviorIdentityDemo
~~~

Kết quả chuẩn:

~~~text
Ban đầu: W-01 | An | 1000
a == alias: true
a == other: false
a.equals(other): false
Cùng mã ví: true
Ví a sau cập nhật: W-01 | An | 1150
Ví other: W-01 | An | 1000
~~~

**Phân tích theo ba khía cạnh:**

1. **Trạng thái:** đối tượng `a` ban đầu có `id = "W-01"`, `owner = "An"`, `balance = 1000`. Sau hai thao tác, `balance = 1150`. `other` vẫn giữ số dư `1000`.
2. **Hành vi:** `deposit(250)` tăng số dư, `withdraw(100)` giảm số dư và từ chối rút vượt quá số dư. `describe()` đọc trạng thái để tạo chuỗi, không chỉnh sửa trường.
3. **Danh tính:** `a` và `alias` chứa tham chiếu đến **cùng một Wallet**. `other` là instance khác do một lần `new` riêng tạo ra, dù dữ liệu ban đầu giống hệt. Vì vậy `a == alias` là `true` còn `a == other` là `false`.
4. `Wallet` không override `equals`, nên kế thừa `Object.equals`: với các đối tượng Wallet này, nó cho kết quả `true` khi hai tham chiếu là cùng đối tượng. Do đó `a.equals(other)` là `false`.
5. Chuỗi mã ví của `a` và `other` bằng nhau theo nội dung, nên `a.id().equals(other.id())` là `true`. Đây là việc so sánh **giá trị mã định danh nghiệp vụ**, không chứng minh hai Wallet có cùng danh tính đối tượng trong JVM.

`Math.addExact` được dùng để ném `ArithmeticException` nếu phép cộng `long` tràn số; nếu chỉ dùng `balance += amount`, số dư có thể bị tràn và trở thành kết quả sai. Đây là ví dụ về hành vi bảo vệ bất biến của trạng thái. Trong hệ thống tiền tệ thực tế còn phải quy định đơn vị tiền nhỏ nhất, xử lý giao dịch và đồng thời; ví dụ này chỉ tập trung vào mô hình đối tượng.

## 4. Danh tính và tham chiếu: hai biến có thể chỉ cùng một đối tượng

Trong Java, biến có kiểu tham chiếu (`Wallet`, `String`, mảng, v.v.) giữ một **giá trị tham chiếu** đến đối tượng hoặc `null`. Bản thân biến tham chiếu và đối tượng mà biến đó trỏ tới là hai khái niệm khác nhau.

~~~text
a ────────┐
          ├────> Wallet #1 { id: "W-01", balance: 1150 }
alias ────┘

other ─────────> Wallet #2 { id: "W-01", balance: 1000 }
~~~

Sơ đồ chỉ diễn tả quan hệ tham chiếu, không biểu diễn địa chỉ bộ nhớ thực tế hay bố cục heap.

- `Wallet alias = a;` sao chép **giá trị tham chiếu**. Nó không gọi constructor, không clone và không tạo thêm Wallet.
- `alias.deposit(250)` gọi hành vi trên đối tượng mà cả `alias` và `a` đều tham chiếu. Vì vậy đọc `a.balance()` sẽ thấy cập nhật.
- `Wallet other = new Wallet(...);` tạo một instance mới. Trùng nội dung các trường không làm instance mới hợp nhất với instance trước.
- Gán lại biến, ví dụ `alias = other;`, chỉ thay đổi đối tượng mà **biến alias** đang tham chiếu; không biến Wallet #1 thành Wallet #2 và không tự sửa tham chiếu trong `a`.
- Nếu trạng thái của một đối tượng thay đổi, **danh tính của chính đối tượng đó vẫn giữ nguyên** trong thời gian đối tượng tồn tại.

### So sánh `==` và `equals()`

| Biểu thức | Ý nghĩa với kiểu tham chiếu | Điều cần nhớ |
| --- | --- | --- |
| `x == y` | Hai tham chiếu có cùng trỏ đến một đối tượng không; hoặc cùng `null`? | Kiểm tra quan hệ tham chiếu, không kiểm tra nội dung các trường |
| `x.equals(y)` | So sánh theo logic do class quy định | `Object.equals` mặc định so sánh như `==`; nhiều class override để so sánh giá trị |
| `x.id().equals(y.id())` | Hai mã nghiệp vụ có cùng nội dung không? | Không tương đương với `x == y`, cũng không nhất thiết tương đương với `x.equals(y)` |

`==` dùng với kiểu nguyên thủy như `int`, `char`, `boolean` lại so sánh **giá trị nguyên thủy**, vì không có đối tượng để so sánh tham chiếu. Không áp dụng trực giác về `==` của số nguyên cho hai đối tượng.

`null` là giá trị thể hiện chưa tham chiếu đến đối tượng nào. `x == null` là cách kiểm tra hợp lệ; gọi `x.equals(...)` khi `x` là `null` gây `NullPointerException`. Khi muốn so sánh hai giá trị có thể null, dùng `java.util.Objects.equals(x, y)`: trả `true` nếu cả hai null, `false` nếu chỉ một null, còn lại ủy quyền cho `x.equals(y)`.

## 5. “Danh tính đối tượng” và “định danh nghiệp vụ” là hai khái niệm khác nhau

Trong ví dụ Wallet, trường `id` là **định danh nghiệp vụ**. Một hệ thống có thể quy định không được có hai ví cùng mã; tuy vậy JVM không tự kiểm tra quy tắc đó khi chạy hai biểu thức `new`. Muốn đảm bảo tính duy nhất theo mã, ứng dụng phải kiểm soát việc tạo đối tượng, quản lý kho lưu trữ hoặc áp dụng ràng buộc dữ liệu.

Cần tách ba quan hệ:

- **Cùng một instance:** `a == b`.
- **Bằng nhau theo hợp đồng của class:** `a.equals(b)`. Ý nghĩa tùy cách triển khai.
- **Có cùng khóa nghiệp vụ:** chẳng hạn `a.id().equals(b.id())`.

Một entity có thể chọn định nghĩa `equals/hashCode` dựa trên khóa nghiệp vụ ổn định. Một value object thường định nghĩa bằng nhau theo toàn bộ các thành phần giá trị liên quan. Không có quy tắc rằng mọi class phải override `equals`, hay cứ có trường tên `id` thì `==` sẽ trở thành so sánh mã.

### Value object minh họa bằng `record` (Java 17+)

`record` phù hợp với các cấu trúc mang dữ liệu, mặc định cung cấp `equals`, `hashCode` và `toString` dựa trên các thành phần record. Lưu tệp **`CoordinateComparison.java`**:

~~~java
public class CoordinateComparison {
    record Coordinate(int x, int y) {}

    public static void main(String[] args) {
        Coordinate left = new Coordinate(2, 3);
        Coordinate right = new Coordinate(2, 3);

        System.out.println(left == right);
        System.out.println(left.equals(right));
        System.out.println(left);
    }
}
~~~

~~~bash
javac CoordinateComparison.java
java CoordinateComparison
~~~

Stdout:

~~~text
false
true
Coordinate[x=2, y=3]
~~~

`left` và `right` là hai instance khác nhau, nhưng hai `Coordinate` có cùng `x` và `y` nên bằng nhau theo `equals`. Record không có các setter cho record component và thành phần `int` không thể tự thay đổi. Tuy nhiên nếu một record chứa tham chiếu tới đối tượng có thể thay đổi, `record` **không tự làm bất biến sâu** đối tượng được tham chiếu đó.

**Hợp đồng `equals/hashCode`:** khi override `equals` để thay đổi định nghĩa bằng nhau, phải override `hashCode` nhất quán: nếu `x.equals(y)` là `true`, hai đối tượng phải có cùng `hashCode()`. Quan hệ bằng nhau còn cần tính phản xạ, đối xứng, bắc cầu và nhất quán khi những dữ liệu liên quan không đổi. Điều này quan trọng với `HashSet` và khóa `HashMap`. Một khóa dựa trên trường mutable có thể khiến việc tra cứu sai sau khi trường thay đổi.

Đừng dùng `System.identityHashCode(object)` làm ID duy nhất. Hàm này trả mã băm theo danh tính, không phụ thuộc `hashCode` bị override, nhưng **hai đối tượng khác nhau vẫn có thể cùng mã băm**; giá trị không phải địa chỉ bộ nhớ được bảo đảm, cũng không phải khóa bền vững giữa những lần chạy ứng dụng.

## 6. Truyền tham chiếu vào phương thức: Java luôn truyền đối số bằng giá trị

Java **truyền đối số bằng giá trị**. Với kiểu đối tượng, giá trị được sao chép vào tham số là **giá trị tham chiếu**. Hậu quả là phương thức có thể sửa trạng thái đối tượng đang được tham chiếu, nhưng gán lại chính biến tham số không làm biến của bên gọi đổi theo.

Ví dụ chạy độc lập, tệp **`ReferenceCopyDemo.java`**:

~~~java
public class ReferenceCopyDemo {
    static final class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }
    }

    static void touch(Counter parameter) {
        parameter.value += 3;         // Sửa cùng đối tượng với bên gọi
        parameter = new Counter(99);  // Chỉ gán lại biến tham số cục bộ
        parameter.value++;            // Sửa đối tượng mới
    }

    public static void main(String[] args) {
        Counter original = new Counter(10);
        touch(original);
        System.out.println(original.value);
    }
}
~~~

~~~bash
javac ReferenceCopyDemo.java
java ReferenceCopyDemo
~~~

Stdout:

~~~text
13
~~~

Thao tác đầu làm Counter của `original` tăng từ 10 lên 13. Gán `parameter = new Counter(99)` sau đó không thay đổi tham chiếu của `original`. Đối tượng mới được thao tác riêng; `original` tiếp tục trỏ đến Counter ban đầu. Đây là một nguồn gây nhầm lẫn nếu gọi Java là “pass by reference”.

## 7. Đóng gói trạng thái, quyền thay đổi và bất biến

Thiết kế tốt giới hạn nơi có thể thay đổi trạng thái để đối tượng luôn giữ những điều kiện hợp lệ (**invariants**).

- Đặt trường nhạy cảm ở `private`, cung cấp phương thức đọc hoặc hành vi cần thiết. Không buộc phải có setter cho mọi trường.
- Kiểm tra đầu vào tại constructor và phương thức thay đổi. Chẳng hạn không cho phép số dư khởi tạo âm hoặc số tiền nạp không dương.
- Tránh trả trực tiếp tham chiếu mutable nội bộ nếu mã bên ngoài có thể sửa nó mà bỏ qua quy tắc của class. Cân nhắc bản sao phòng vệ hoặc giao diện chỉ đọc.
- Phân biệt **`final` trên biến tham chiếu** và **bất biến của đối tượng**. `final Wallet w = ...` cấm gán `w` sang Wallet khác nhưng **không cấm** `w.deposit(10)`. `final` trên một trường tham chiếu cũng không tự khóa trạng thái của đối tượng mà trường đó trỏ tới.
- Một đối tượng immutable được thiết kế để trạng thái quan sát được không thay đổi sau khi tạo. Nó vẫn có danh tính khi xét bằng `==`. Hai đối tượng immutable có nội dung bằng nhau không nhất thiết là cùng instance.

Đôi khi hành vi chỉ trả kết quả và không đổi state, chẳng hạn `balance()` hoặc một hàm tính phí. “Có hành vi” không đồng nghĩa với “luôn có side effect”. Ngược lại, phương thức thực hiện chuyển tiền, ghi tệp hoặc gọi mạng có thể tạo side effect ngoài các instance field; khi thiết kế API phải trình bày rõ các tác động đó.

### Trạng thái thay đổi trong môi trường nhiều luồng

Ví dụ Wallet giúp nhận diện đối tượng và quy tắc nghiệp vụ, nhưng bản thân nó **không thread-safe**. Hai luồng cập nhật `balance` cùng lúc có thể gây race condition hoặc làm mất cập nhật. Nếu nhiều luồng chia sẻ cùng một đối tượng mutable, cần thiết kế cơ chế đồng bộ hoặc mô hình dữ liệu/giao dịch phù hợp. Đây là vấn đề về **chia sẻ trạng thái và phối hợp hành vi**, không làm thay đổi định nghĩa danh tính của đối tượng.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Hai đối tượng có các trường bằng nhau nên là cùng một đối tượng.” | Các giá trị trùng nhau không suy ra `==` là `true`. |
| “`Wallet alias = a` tạo bản sao Wallet.” | Lệnh gán sao chép tham chiếu; cả hai biến trỏ đến cùng instance. |
| “`equals` luôn kiểm tra cùng một object.” | `Object.equals` mặc định làm vậy, nhưng `String`, record và nhiều class khác định nghĩa equality theo nội dung. |
| “Trường `id` chính là JVM identity.” | `id` chỉ là dữ liệu do ứng dụng định nghĩa; JVM identity độc lập với tên hoặc giá trị trường. |
| “`final` làm tất cả thuộc tính không thể thay đổi.” | `final` giới hạn gán lại biến/trường tương ứng, không tự bảo đảm bất biến sâu. |
| “Truyền object vào method là truyền biến của caller qua tham chiếu.” | Tham số chứa một bản sao giá trị tham chiếu; method không thể gán lại biến của caller. |
| “`identityHashCode` xác định duy nhất mọi đối tượng.” | Mã băm có thể va chạm và không thích hợp làm định danh duy nhất. |
| “Mọi instance method đều sửa trường.” | Method có thể chỉ đọc, tính toán hoặc phối hợp tác vụ. |
| “Có cùng object thì cập nhật từ hai nơi luôn an toàn.” | Các alias thấy cùng state, nhưng cập nhật đa luồng cần xử lý an toàn đồng thời. |

**Lưu ý về `String`:** Java có cơ chế intern và tái sử dụng một số đối tượng. Vì vậy không suy ra hai biến là hai object chỉ từ việc nhìn thấy hai biểu thức chuỗi. Khi mục tiêu là kiểm tra nội dung chuỗi, dùng `equals` thay vì `==`; trong bài học về danh tính, cần nhìn rõ các tham chiếu và cách đối tượng được tạo.

## 9. Tự kiểm tra tư duy

Giả sử class đơn giản sau, trong đó `Box` không override `equals`:

~~~java
final class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}
~~~

Xét đoạn mã đặt bên trong một phương thức:

~~~java
Box x = new Box(1);
Box y = x;
Box z = new Box(1);

y.value = 7;

System.out.println(x.value);
System.out.println(x == y);
System.out.println(x == z);
System.out.println(x.equals(z));
System.out.println(z.value);
~~~

Đoán đầu ra trước khi xem đáp án:

~~~text
7
true
false
false
1
~~~

Giải thích: `x` và `y` cùng tham chiếu Box đầu tiên nên việc sửa qua `y` xuất hiện khi đọc qua `x`. `z` được tạo riêng, giữ giá trị `1`. Class `Box` không override `equals` nên `x.equals(z)` chỉ đúng nếu hai biến trỏ đến cùng một instance, điều không xảy ra ở đây.

Hãy tự trả lời thêm:

1. Nếu gán `y = z` **sau khi** thay đổi `y.value`, giá trị `x.value` có tự trở về `1` không? **Không.** Việc gán lại tham chiếu không hoàn tác trạng thái đã cập nhật.
2. Nếu hai Box cùng có `value = 7`, biểu thức `x == z` có đổi thành `true` không? **Không.** Việc sửa trường không thay đổi danh tính.
3. Nếu sửa `Box` để override `equals` theo `value`, `x == z` có đổi kết quả không? **Không.** Override `equals` chỉ thay đổi phép so sánh logic bằng phương thức, không thay đổi `==` với hai tham chiếu.

## 10. Khi áp dụng vào mã nguồn thật

Khi đọc hoặc thiết kế một class, hãy lần lượt xác định:

1. **State:** Những instance field nào mô tả đối tượng? Giá trị ban đầu hợp lệ là gì? Dữ liệu nào là mutable và dữ liệu nào cần ổn định?
2. **Behavior:** Phương thức nào là thao tác hợp lệ trên state? Những bất biến nào phải đúng trước và sau mỗi thao tác? Ai có quyền thay đổi?
3. **Identity:** Ứng dụng cần nhận biết **cùng instance**, **bằng nhau theo giá trị** hay **cùng mã nghiệp vụ**? Định nghĩa equality phù hợp với nhu cầu nào? Có alias hoặc chia sẻ giữa nhiều luồng không?
4. **Tham chiếu:** Đối tượng nào đang được dùng chung? Việc sao chép biến là sao chép tham chiếu hay tạo bản sao đối tượng? Phương thức nào có thể tạo side effect?

Ba góc nhìn trên giúp giải thích các lỗi như “sửa một biến mà biến khác cũng đổi”, “hai đối tượng in ra giống nhau nhưng so sánh sai”, “trạng thái không hợp lệ dù setter vẫn chạy”, và “key trong collection không tìm lại được”. Hiểu rõ state, behavior và identity là nền tảng để thiết kế các class có trách nhiệm rõ ràng, dễ kiểm thử và dùng an toàn trong chương trình Java.
