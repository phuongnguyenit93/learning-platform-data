# Rủi ro dùng collection dựa trên giá trị làm khóa đồng bộ (Java 10+)

## 1. Vấn đề cần hiểu

Các collection không cho sửa đổi được tạo bởi những factory như `List.of(...)`, `Set.of(...)`, `Map.of(...)` và `List.copyOf(...)` là lựa chọn thuận tiện để lưu dữ liệu chỉ đọc. Tuy nhiên, các collection do nhóm factory này tạo ra được Java API quy định là **value-based** (dựa trên giá trị). **Không được dùng chúng làm khóa đồng bộ cho `synchronized`.**

```java
var permissions = List.of("read", "write");

// KHÔNG NÊN LÀM:
synchronized (permissions) {
    // cập nhật trạng thái dùng chung
}
```

Đoạn trên là mã minh họa trong một phương thức, cần `import java.util.List;`. Java có thể cho phép biên dịch và chạy dạng `synchronized (permissions)` trên một số JDK hiện nay, nhưng tài liệu API chính thức cảnh báo rằng đồng bộ hóa trên instance value-based có thể dẫn tới hành vi khó dự đoán; khả năng đồng bộ trên những instance đó cũng có thể thay đổi trong các bản Java về sau.

**Tách bạch hai thuộc tính:**

- **Không thể sửa đổi collection qua API**: `add`, `remove`, `put`, `set`... không được hỗ trợ. Đây là tính chất của nội dung cấu trúc collection.
- **Danh tính đối tượng phù hợp để khóa**: `synchronized` phải dựa vào **cùng một đối tượng monitor có danh tính ổn định và được các bên phối hợp sở hữu**. Các instance value-based không cung cấp hợp đồng danh tính kiểu đó.

Collection chỉ đọc rất hữu ích để truyền dữ liệu; nó không tự động trở thành một khóa đồng bộ an toàn.

## 2. Value-based là gì và áp dụng cho những collection nào?

Một đối tượng **value-based** được sử dụng theo **giá trị** thay vì theo danh tính riêng biệt của từng lần tạo. Với các instance loại này, Java API yêu cầu người dùng coi các instance `equals` nhau là có thể thay thế được trong các thao tác mang ngữ nghĩa giá trị. Các factory có quyền tạo object mới hoặc tái sử dụng instance có sẵn; **không hứa mỗi lần gọi sẽ có một identity khác**, cũng không hứa cùng nội dung sẽ luôn trả về **cùng identity**.

Những trường hợp quan trọng còn áp dụng trong Java hiện đại:

| Cách tạo | Kết quả | Điều cần nhớ |
| --- | --- | --- |
| `List.of("A", "B")` | List không sửa đổi được, value-based | Không đồng bộ bằng chính instance trả về |
| `List.copyOf(collection)` | List không sửa đổi được, value-based | Có thể tái sử dụng một list đã phù hợp, không bảo đảm tạo object mới |
| `Set.of("A", "B")`, `Set.copyOf(source)` | Set không sửa đổi được, value-based | Thứ tự duyệt Set không phải cơ sở để khóa |
| `Map.of("a", 1)`, `Map.ofEntries(...)`, `Map.copyOf(source)` | Map không sửa đổi được, value-based | Không dùng instance Map làm monitor |
| `Map.entry("a", 1)` | Map.Entry không sửa đổi được, value-based | Không dùng entry làm khóa đồng bộ |

`List.copyOf`, `Set.copyOf` và `Map.copyOf` có từ Java 10; những quy tắc value-based này **vẫn áp dụng**. `List.of`, `Set.of` và `Map.of` được giới thiệu sớm hơn nhưng vẫn là API hiện hành và liên quan trực tiếp tới collection chỉ đọc.

**Không khái quát nhầm:** không phải mọi đối tượng triển khai `List`, `Set` hay `Map` đều value-based. Ví dụ `new ArrayList<>()` là một collection thông thường, còn `Collections.unmodifiableList(backingList)` là **view không cho sửa trực tiếp** trên một backing list và không có cùng hợp đồng value-based như nhóm `List.of`/`copyOf`. Dù dùng loại nào, cho người ngoài nhìn thấy đối tượng dùng làm monitor vẫn có rủi ro phối hợp và tranh chấp khóa; khóa chuyên dụng do lớp sở hữu thường là cách dễ kiểm soát hơn.

## 3. `synchronized` dựa trên danh tính monitor, không dựa trên `equals`

Trong Java, mỗi thao tác `synchronized (lock)` được tổ chức quanh **monitor của đối tượng thực tế** mà tham chiếu `lock` trỏ tới. Muốn hai luồng loại trừ lẫn nhau đối với cùng một trạng thái, chúng phải đồng bộ trên **cùng một monitor**.

```java
var a = List.of("A", "B");
var b = List.of("A", "B");

boolean sameValue = a.equals(b); // true
// Không suy luận a == b là true hoặc false!
// Không dùng a và b làm khóa để thử "chứng minh" chúng cùng monitor.
```

Hai danh sách cùng nội dung theo `equals`, nhưng **bằng nhau về giá trị không đồng nghĩa được bảo đảm có chung identity**. Factory có thể tạo hai object khác nhau hoặc dùng chung object theo lựa chọn của implementation. Mã nguồn không được dựa vào bất kỳ kết quả cụ thể nào của `a == b`.

Do đó, cả hai cách suy luận sau đều sai:

- “Hai collection có cùng phần tử nên `synchronized(a)` sẽ chặn `synchronized(b)`.”
- “Tôi gọi `List.of(...)` hai lần nên chắc chắn nhận được hai monitor độc lập.”

Ngay cả khi quan sát thấy một kết quả trên JDK đang chạy, đó không phải một bảo đảm để xây dựng cơ chế đồng bộ lâu dài.

## 4. Các rủi ro cụ thể khi lấy value-based collection làm khóa

### 4.1. Không khóa cùng một monitor như dự định

Giả sử hai thành phần độc lập cùng muốn bảo vệ một biến dùng chung, mỗi thành phần tự tạo một “khóa” dựa trên giá trị:

```java
// Thành phần A
synchronized (List.of("order", 42)) {
    updateSharedState();
}

// Thành phần B
synchronized (List.of("order", 42)) {
    updateSharedState();
}
```

Đây là **mã giả minh họa**, giả định `updateSharedState()` đã được định nghĩa. Cả hai biểu thức có thể tạo các instance `equals` nhau nhưng **không chắc dùng cùng monitor**, nên không bảo đảm loại trừ lẫn nhau. Một lần chạy tình cờ đồng bộ thành công không biến việc dựa vào identity của factory thành thiết kế hợp lệ.

### 4.2. Vô tình tranh chấp khóa với code không liên quan

Trường hợp ngược lại cũng nguy hiểm: nếu factory tái sử dụng instance, những phần mã tưởng dùng “khóa riêng” có thể đang đồng bộ trên cùng một object. Điều đó có thể gây **tranh chấp ngoài ý muốn**, chờ lâu hoặc phụ thuộc vào đường thực thi của các thành phần khác.

Hợp đồng value-based không yêu cầu factory luôn chia sẻ instance; rủi ro ở đây là **ứng dụng không kiểm soát được danh tính dùng để phối hợp**.

### 4.3. Thay snapshot làm thay đổi monitor

Khi dùng collection chỉ đọc để biểu diễn các phiên bản cấu hình, một biến có thể được gán snapshot mới:

```java
private List<String> currentRules = List.of("read");

// KHÔNG NÊN: khóa phụ thuộc vào giá trị snapshot đang được trỏ tới
void update() {
    synchronized (currentRules) {
        currentRules = List.copyOf(List.of("read", "write"));
    }
}
```

Đoạn trên thuộc **một lớp minh họa**, cần `import java.util.List;`. Ngoài vấn đề value-based, đọc và đổi `currentRules` ở các luồng khác nhau có thể khiến luồng sau khóa **một tham chiếu khác** luồng trước. Khi monitor thay đổi, việc loại trừ lẫn nhau không được bảo đảm. Cần dùng một object khóa **ổn định**, đồng thời thiết kế quy tắc đọc/ghi và công bố snapshot phù hợp.

### 4.4. Mã hôm nay có vẻ chạy được nhưng không có bảo đảm API

Tài liệu Java API ghi rõ các instance value-based **không nên** được dùng để synchronization, và hành vi đồng bộ trong tương lai có thể thay đổi. Không nên dựa vào việc một bản JDK hiện tại có cho phép thao tác monitor hay không để khẳng định mã sẽ luôn đúng.

Các cơ chế phụ thuộc vào identity khác cũng nên tránh khi xử lý collection value-based, như:

- Dùng `==` thay `equals` để so sánh nội dung.
- Dùng `System.identityHashCode(...)` làm mã nhận diện bền vững.
- Dùng chúng làm khóa của `IdentityHashMap` khi nghiệp vụ thực sự cần nhận diện theo **giá trị**.
- Phụ thuộc vào `wait()`/`notify()` trên chính instance value-based.

Những thao tác trên dựa vào identity, trong khi hợp đồng của value-based khuyến khích sử dụng giá trị và không bảo đảm identity theo cách code đó giả định.

## 5. Thiết kế đúng: khóa riêng, ổn định và do thành phần sở hữu

Khi cần bảo vệ trạng thái dùng chung trong một object, sử dụng một monitor riêng:

```java
final class Counter {
    private final Object lock = new Object();
    private int count;

    void increment() {
        synchronized (lock) {
            count++;
        }
    }

    int get() {
        synchronized (lock) {
            return count;
        }
    }
}
```

Đây là lớp Java độc lập về mặt khai báo, có thể được gọi từ chương trình khác.

**Vì sao an toàn hơn?**

1. `lock` được tạo riêng bằng `new Object()` và lưu vào trường `private final`: code bên ngoài không truy cập được, không có factory value-based quyết định tái sử dụng identity.
2. Mọi phương thức bảo vệ `count` cùng khóa trên **một object ổn định**.
3. Việc thêm hoặc thay collection chỉ đọc không ảnh hưởng tới monitor.
4. Quyền sở hữu khóa được thể hiện rõ trong lớp, tránh code bên ngoài vô tình giữ khóa quá lâu.

Không viết `synchronized (new Object())` mỗi lần gọi vì mỗi lần là một object mới, các luồng không phối hợp được. Cũng không nên tạo một `Object` mới cục bộ trong từng phương thức nếu chúng phải bảo vệ **cùng** trạng thái.

Một biến thể hữu ích khi ứng dụng có nhiều trạng thái độc lập là tạo khóa riêng **cho mỗi đối tượng quản lý trạng thái**. Không dùng một khóa `static` toàn cục nếu các instance không cần chặn lẫn nhau.

## 6. Nếu không cần block nhiều lệnh, dùng công cụ đồng thời chuyên dụng

Với một biến đếm đơn giản, `AtomicInteger` là lựa chọn ngắn gọn:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
```

`AtomicInteger` cung cấp phép tăng nguyên tử với cơ chế đồng thời do thư viện quản lý; không cần chọn bất kỳ collection nào làm monitor.

Với cấu trúc cần cập nhật nhiều bước dưới cùng một bất biến, có thể dùng `synchronized` trên khóa riêng hoặc `ReentrantLock` (kèm `unlock()` trong `finally`). Với map được nhiều luồng cập nhật độc lập, `ConcurrentHashMap` có thể phù hợp, tùy bài toán. Đây là các công cụ hiện hành; lựa chọn phụ thuộc vào **trạng thái cần bảo vệ**, không phụ thuộc việc ta đang có sẵn một collection chỉ đọc.

## 7. Collection không sửa được không đồng nghĩa toàn bộ dữ liệu đều thread-safe

Một danh sách do `List.of` tạo ra không cho thay đổi cấu trúc trực tiếp, nhưng **đối tượng phần tử có thể là mutable**:

```java
var buffer = new StringBuilder("A");
var list = List.of(buffer); // không được add/remove phần tử
buffer.append("B");         // đối tượng phần tử vẫn có thể thay đổi
System.out.println(list.get(0)); // AB
```

Đây là ví dụ trong phương thức, cần `import java.util.List;`. Nếu nhiều luồng truy cập và thay đổi `StringBuilder` đồng thời, việc list không thể sửa cấu trúc **không tự bảo vệ trạng thái của StringBuilder**.

Tương tự, `List.copyOf` chụp lại các tham chiếu phần tử ở thời điểm tạo và không phản chiếu việc **thêm/xóa phần tử** trong collection nguồn về sau, nhưng không thực hiện deep copy mọi object phần tử. Cần thiết kế độc lập cơ chế an toàn luồng cho các phần tử mutable.

Tính *unmodifiable*, khả năng **công bố snapshot an toàn** (safe publication) và **đồng bộ truy cập trạng thái dùng chung** là những vấn đề riêng biệt. Một snapshot có thể đọc được mà không khóa nếu thiết kế dữ liệu và cách công bố phù hợp; điều đó không biến bản thân snapshot thành một monitor đáng tin cậy.

## 8. `copyOf` có thể dùng lại instance: không dựa vào identity của bản sao

Khi dùng `List.copyOf`, đừng mặc định “copy” đồng nghĩa với “có object mới”:

```java
var original = List.of("A", "B");
var copy = List.copyOf(original);

System.out.println(original.equals(copy)); // true
// Không suy đoán hoặc kiểm tra một lần rồi phụ thuộc original == copy.
```

Theo implementation note của `List.copyOf`, nếu đầu vào vốn là một List không cho sửa đổi, việc gọi `copyOf` **thường không tạo bản sao mới**. Dù vậy, đây không phải lời hứa identity trên mọi lần gọi hoặc mọi phiên bản JDK. `Set.copyOf` và `Map.copyOf` cũng không nên được dùng theo cách dựa vào danh tính instance.

**Không dùng cả `original` lẫn `copy` làm các khóa được kỳ vọng độc lập hay được kỳ vọng giống nhau.** Dùng đối tượng riêng do chính thành phần tạo ra để phối hợp các luồng.

## 9. Chương trình đầy đủ: snapshot chỉ đọc và khóa riêng (Java 17+)

Lưu mã sau vào `ValueBasedLockDemo.java`:

```java
import java.util.List;

public class ValueBasedLockDemo {

    static final class Counter {
        private final Object lock = new Object();
        private final List<String> permissions = List.of("read", "write");
        private int value;

        void increment() {
            synchronized (lock) {
                value++;
            }
        }

        int get() {
            synchronized (lock) {
                return value;
            }
        }

        List<String> permissions() {
            return permissions;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        var counter = new Counter();

        Runnable task = () -> {
            for (int i = 0; i < 1_000; i++) {
                counter.increment();
            }
        };

        var first = new Thread(task);
        var second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        var fromFactory = List.of("read", "write");
        var copied = List.copyOf(fromFactory);

        System.out.println("permissions=" + counter.permissions());
        System.out.println("count=" + counter.get());
        System.out.println("equal=" + fromFactory.equals(copied));
        System.out.println("copy=" + copied);
    }
}
```

Biên dịch và chạy:

```bash
javac ValueBasedLockDemo.java
java ValueBasedLockDemo
```

Kết quả:

```text
permissions=[read, write]
count=2000
equal=true
copy=[read, write]
```

**Giải thích:**

- `Counter.permissions` là danh sách chỉ đọc dùng để biểu diễn **dữ liệu**. Không phương thức nào đồng bộ trên danh sách đó.
- `Counter.lock` là một instance `Object` riêng, ổn định, chỉ được lớp sở hữu.
- Hai luồng mỗi luồng gọi `increment()` đúng 1.000 lần. `join()` bảo đảm luồng chính chỉ đọc kết quả sau khi hai luồng kết thúc; `synchronized(lock)` bảo vệ phép `value++` nên kết quả là `2000`.
- Hai danh sách `fromFactory` và `copied` được so sánh theo `equals`, nên kết quả là `true`. Chương trình **cố ý không so sánh `==`** và không dùng chúng như khóa.

Cần lưu ý: ví dụ này chứng minh một **thiết kế có khóa riêng** và cách sử dụng collection theo giá trị, không cố tình tạo một race condition để quan sát. Lỗi đồng bộ do sai identity thường phụ thuộc lịch chạy của luồng và lựa chọn implementation, nên một vài lần chạy thành công không chứng minh cách khóa sai là an toàn.

## 10. Phân biệt khóa dữ liệu với khóa điều phối

Bảng sau giúp chọn đúng đối tượng:

| Đối tượng | Vai trò nên dùng | Có nên dùng làm monitor? |
| --- | --- | --- |
| `List.of(...)`, `List.copyOf(...)` | Dữ liệu list chỉ đọc, so sánh theo `equals` | **Không**: value-based |
| `Set.of(...)`, `Set.copyOf(...)` | Tập giá trị không cho sửa | **Không**: value-based |
| `Map.of(...)`, `Map.copyOf(...)` | Ánh xạ không cho sửa | **Không**: value-based |
| `Collections.unmodifiableList(backing)` | View không cho sửa trực tiếp, có thể phản chiếu thay đổi từ backing list | Không nên tận dụng làm khóa công khai; chọn lock riêng |
| `private final Object lock = new Object();` | Monitor dành riêng cho trạng thái của một instance | **Có**, khi mọi truy cập cần bảo vệ thống nhất dùng monitor này |
| `AtomicInteger` | Biến đếm với thao tác nguyên tử | Không cần monitor bên ngoài cho các thao tác nguyên tử riêng của nó |
| `ReentrantLock` | Điều phối critical section theo hợp đồng `Lock` | Dùng `lock()`/`unlock()` đúng cách, không lấy collection làm lock |

Một `ArrayList` thông thường về kỹ thuật có thể được dùng trong `synchronized` vì có danh tính đối tượng, nhưng dùng một collection làm khóa cũng có thể khiến các phần mã khác đồng bộ trên nó ngoài ý muốn. Một `private final Object` độc lập thường giúp phạm vi và quyền sở hữu rõ ràng hơn.

## 11. Tình huống thực tế: cấu hình chỉ đọc được thay phiên bản

Giả sử có cấu hình quyền truy cập gồm danh sách action. Ứng dụng cần:

- Công bố các snapshot list chỉ đọc để người tiêu thụ đọc.
- Tăng số lần cập nhật cấu hình.
- Tránh để việc thay list làm thay đổi khóa bảo vệ bộ đếm.

Một thiết kế phù hợp:

```java
import java.util.List;

final class Configuration {
    private final Object lock = new Object();
    private volatile List<String> actions = List.of("read");
    private int updates;

    void replaceActions(List<String> input) {
        var snapshot = List.copyOf(input);
        synchronized (lock) {
            actions = snapshot;
            updates++;
        }
    }

    List<String> actions() {
        return actions;
    }

    int updateCount() {
        synchronized (lock) {
            return updates;
        }
    }
}
```

Đây là lớp minh họa có thể biên dịch khi đặt trong tệp Java phù hợp. Trường `actions` được công bố qua `volatile` để các luồng đọc nhận được tham chiếu snapshot mới; điều này phù hợp khi bản thân danh sách có các phần tử được quản lý an toàn. `lock` giữ nguyên identity khi `actions` thay đổi và bảo vệ cập nhật `updates`. Nếu cần một thao tác đọc **đồng thời, nhất quán giữa cả `actions` và `updates`**, phải đọc cả hai dưới cùng một khóa hoặc dùng một đối tượng snapshot kết hợp; hai getter độc lập không cung cấp snapshot nguyên tử của cặp giá trị.

Lưu ý: đây là ví dụ về bảo vệ bộ đếm và công bố tham chiếu snapshot. Nếu phần tử trong `input` là object có trạng thái mutable, `List.copyOf` không biến chúng thành immutable.

## 12. Checklist kiểm tra mã đồng bộ

Khi gặp `synchronized (expression)`, hãy tự hỏi:

1. **`expression` đang trả về loại object gì?** Nếu là kết quả `List.of`/`copyOf`, `Set.of`/`copyOf`, `Map.of`/`copyOf`, không dùng làm monitor.
2. **Mọi luồng cần phối hợp có chắc đang dùng đúng cùng một object không?** Bằng nhau theo `equals` chưa đủ.
3. **Khóa có bị thay khi dữ liệu được cập nhật hoặc tạo snapshot mới không?** Nếu có, tách khóa thành một trường `private final`.
4. **Khóa có bị lộ ra ngoài API không?** Nếu có, code không liên quan có thể giữ hoặc tranh chấp khóa; nên giới hạn quyền sở hữu.
5. **Cơ chế nào thực sự bảo vệ trạng thái?** `List.of` không làm phép tăng `count++` trở thành nguyên tử.
6. **Có thể thay bằng primitive đồng thời chuẩn không?** Với bộ đếm, cân nhắc `AtomicInteger`; với map cập nhật nhiều luồng, cân nhắc `ConcurrentHashMap`; với nhiều bước phải nguyên tử, dùng khóa chuyên dụng.
7. **Có đang dựa vào kết quả `==`, `identityHashCode` hay hành vi cụ thể của một JDK không?** Nếu có, bỏ giả định identity.

Một vài công cụ kiểm tra của JDK có thể cảnh báo việc đồng bộ trên **một số** lớp value-based (tham khảo JEP 390), nhưng **không nên xem việc thiếu cảnh báo là bằng chứng collection nào đó an toàn làm khóa**. Chữ ký API và hợp đồng của factory mới là căn cứ quan trọng.

## 13. Tự kiểm tra

### Câu 1

```java
var a = List.of("X");
var b = List.of("X");
System.out.println(a.equals(b));
// System.out.println(a == b);
```

Có thể kết luận điều gì?

**Đáp án:** `a.equals(b)` là `true`. Không thể dựa vào API để kết luận `a == b` sẽ là `true` hay `false` trên mọi JDK/lần gọi. Hai instance không phải khóa đồng bộ đáng tin cậy.

### Câu 2

```java
private final Object lock = new Object();
private List<String> rules = List.of("read");

void replace(List<String> next) {
    synchronized (lock) {
        rules = List.copyOf(next);
    }
}
```

Tại sao cách này tốt hơn `synchronized(rules)`?

**Đáp án:** Mọi lần cập nhật đều sử dụng cùng đối tượng `lock` do lớp tạo và sở hữu; thay snapshot không đổi monitor. Nếu các luồng khác đọc `rules`, cần có quy tắc đọc dưới `lock` hoặc cơ chế công bố phù hợp, chứ không tự coi List chỉ đọc là đã đủ để đảm bảo toàn bộ trạng thái thread-safe.

### Câu 3

Một phương thức gọi `List.copyOf(alreadyUnmodifiable)`. Có nên dùng danh sách kết quả làm “khóa mới độc lập” không?

**Đáp án:** Không. `List.copyOf` có thể tái sử dụng một instance unmodifiable đã có. Bên cạnh đó, kết quả value-based không cung cấp bảo đảm identity phục vụ synchronization.

## Kết luận

**Collection value-based phục vụ dữ liệu theo giá trị; monitor phục vụ phối hợp luồng theo danh tính đối tượng.** Hai mục đích này có hợp đồng khác nhau. Khi dùng các collection không sửa được từ `List.of`/`copyOf`, `Set.of`/`copyOf` hoặc `Map.of`/`copyOf`, hãy sử dụng chúng để lưu, truyền và so sánh dữ liệu theo `equals`; nếu cần khóa, tạo một monitor `private final Object` hoặc chọn cấu trúc đồng thời thích hợp.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `java.util.List`, mục Unmodifiable Lists](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html): `List.of`/`List.copyOf` trả về instance value-based và khuyến cáo không dùng chúng cho synchronization.
- [Java SE 26 — `java.util.Set`, mục Unmodifiable Sets](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html): hợp đồng tương tự cho `Set.of`/`Set.copyOf`.
- [Java SE 26 — `java.util.Map`, mục Unmodifiable Maps](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html): hợp đồng value-based và identity cho `Map.of`/`Map.copyOf`; `Map.entry` cũng value-based.
- [OpenJDK JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): nền tảng của các collection factory.
- [OpenJDK JEP 390 — Warnings for Value-Based Classes](https://openjdk.org/jeps/390): cảnh báo khi lạm dụng identity/synchronization ở các lớp value-based.
