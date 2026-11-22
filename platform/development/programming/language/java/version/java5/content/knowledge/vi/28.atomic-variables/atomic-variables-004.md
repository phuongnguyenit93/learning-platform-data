# get, set, getAndSet và compareAndSet

## 1. Bốn thao tác, bốn ý định

Biến nguyên tử cho phép nhiều luồng đọc hoặc thay đổi **một giá trị** qua các thao tác có hợp đồng đồng thời rõ ràng. Các lớp thường gặp gồm `AtomicInteger`, `AtomicLong`, `AtomicBoolean` và `AtomicReference<V>`.

Điều quan trọng không chỉ là “phương thức này an toàn khi nhiều luồng gọi”. Cần chọn thao tác đúng với điều mình muốn làm:

| Thao tác | Ý định | Giá trị trả về |
|---|---|---|
| `get()` | Đọc giá trị | Giá trị được đọc |
| `set(newValue)` | Ghi giá trị mới vô điều kiện | Không trả giá trị |
| `getAndSet(newValue)` | Đổi sang giá trị mới và lấy giá trị trước lần đổi đó | Giá trị cũ |
| `compareAndSet(expected, newValue)` | Chỉ ghi nếu giá trị hiện tại khớp giá trị kỳ vọng | `true` nếu điều kiện khớp và thao tác thành công; `false` nếu không |

Ví dụ với một ô trạng thái đang chứa `10`:

```text
get()                 → trả 10, vẫn giữ 10
set(20)               → không trả giá trị, chuyển thành 20
getAndSet(30)          → trả 20, chuyển thành 30
compareAndSet(20, 40)  → trả false, vẫn là 30
compareAndSet(30, 40)  → trả true, chuyển thành 40
```

Các kết quả trên mô tả một chuỗi không có luồng khác chen vào. Trong chương trình đồng thời, mỗi lời gọi có kết quả riêng tại thời điểm thao tác có hiệu lực; một lời gọi `get()` về sau có thể đã thấy giá trị khác.

## 2. get(): đọc một giá trị, không giữ quyền sở hữu

`get()` lấy giá trị hiện tại qua một lần đọc có ngữ nghĩa bộ nhớ tương ứng với đọc `volatile` của các lớp nguyên tử đang xét.

Nhưng giá trị trả về không phải một sự đặt chỗ. Sau khi luồng A đọc được `10`, luồng B có thể đổi biến ngay lập tức.

Mã sau là đoạn minh họa bên trong một phương thức; `count` là `AtomicInteger` đã được tạo:

```java
int observed = count.get();
// Another thread may change count here.
System.out.println(observed);
```

Biến cục bộ `observed` giữ kết quả lần đọc của A. Nó không tự cập nhật theo `count`.

Điều này đặc biệt quan trọng với kiểm tra rồi hành động:

```java
if (remaining.get() > 0) {
    remaining.set(remaining.get() - 1);
}
```

Đoạn trên **không phải** một phép “lấy một suất nếu còn” nguyên tử. Nhiều luồng có thể cùng vượt qua điều kiện hoặc dùng những giá trị đọc ở thời điểm khác nhau. Phải kết hợp điều kiện với thay đổi, chẳng hạn bằng CAS, nếu yêu cầu là bảo toàn số suất không âm.

Không có lỗi ở bản thân `get()`. Lỗi nằm ở việc coi nhiều lần gọi riêng là một giao dịch duy nhất.

## 3. set(): công bố một giá trị mới vô điều kiện

`set(value)` ghi giá trị được đưa vào, không kiểm tra xem trạng thái có còn giống lúc luồng đọc trước đó hay không.

Nó phù hợp khi yêu cầu thực sự là thay thế giá trị, chẳng hạn:

- Đặt cờ yêu cầu dừng thành `true`.
- Công bố một đối tượng cấu hình bất biến mới.
- Gán lại một chỉ số theo chính sách đã xác định.

Mã minh họa sau không phải phép tăng nguyên tử:

```java
count.set(count.get() + 1);
```

Một cách xen kẽ gây mất cập nhật:

```text
Ban đầu count = 0
A đọc 0
B đọc 0
A tính 1 và set(1)
B tính 1 và set(1)
Kết quả count = 1, dù có hai lần muốn tăng
```

Mỗi lần đọc/ghi riêng đều an toàn theo hợp đồng của nó, nhưng cả chuỗi đọc–tính–ghi chưa được kết hợp.

Nếu chỉ cần tăng bộ đếm, dùng thao tác chuyên biệt như `incrementAndGet()` hoặc `getAndIncrement()`. CAS hữu ích khi phép cập nhật có điều kiện riêng; không cần tự viết vòng CAS cho mọi phép toán đã có API phù hợp.

Một lần `set()` cũng có thể ghi đè kết quả mà luồng khác vừa cập nhật thành công bằng CAS. Vì vậy, tất cả các đường ghi phải tuân thủ cùng giao thức. Không thể thiết kế chuyển trạng thái bằng CAS ở một phương thức nhưng cho phương thức khác tùy ý đặt lại trạng thái rồi vẫn suy ra các bảo đảm của giao thức ban đầu.

## 4. getAndSet(): thay giá trị và nhận chính giá trị bị thay

`getAndSet(newValue)` kết hợp việc đọc giá trị cũ với ghi giá trị mới thành một thao tác nguyên tử.

Nó khác với:

```java
int old = number.get();
number.set(newValue);
```

Trong hai lời gọi tách rời, luồng khác có thể cập nhật ở giữa. Khi đó `old` không nhất thiết là giá trị ngay trước lần ghi của luồng hiện tại.

Với `getAndSet()`, giá trị trả về chính là giá trị mà thao tác đó thay thế. Tuy nhiên, biến có thể tiếp tục bị luồng khác đổi sau khi thao tác hoàn tất.

### Ví dụ cờ đã nhận yêu cầu

Với một `AtomicBoolean` ban đầu `false`, đoạn sau có thể phân biệt lần đầu chuyển cờ sang `true`:

```java
boolean wasRequested = requested.getAndSet(true);
if (!wasRequested) {
    // Handle the first transition to requested.
}
```

Đây là đoạn minh họa, trong đó `requested` đã được khai báo và mọi lời gọi chỉ chuyển từ `false` sang `true`. Nếu không ai đặt lại cờ, chỉ một lời gọi nhận giá trị cũ là `false`.

Lưu ý `getAndSet(true)` vẫn là thao tác ghi ngay cả khi cờ đã `true`. Nếu mục tiêu là “chỉ giành quyền khi còn false”, `compareAndSet(false, true)` thể hiện ý định trực tiếp hơn và trả ngay kết quả giành quyền.

Nếu cờ đánh dấu “đã bắt đầu”, đừng diễn giải nó thành “đã hoàn tất thành công”. Công việc sau lần đổi cờ có thể thất bại; khi cần phân biệt đang chạy/thành công/thất bại, một boolean có thể không đủ diễn đạt trạng thái.

## 5. compareAndSet(): kiểm tra và ghi tại cùng một điểm

CAS là viết tắt của compare-and-set. Với `AtomicInteger`:

```java
boolean changed = state.compareAndSet(expected, replacement);
```

Thao tác kiểm tra giá trị đang giữ có bằng `expected` hay không:

- Khớp: ghi `replacement`, trả `true`.
- Không khớp: không ghi giá trị thay thế, trả `false`.

Kiểm tra và ghi không tách thành hai cửa sổ cho luồng khác chen vào.

`compareAndSet()` ở đây là CAS mạnh: không có thất bại giả khi điều kiện so sánh khớp tại điểm thao tác có hiệu lực. Không nhầm nó với các phương thức `weakCompareAndSet...`, vốn có hợp đồng khác.

Giá trị `false` không cho biết giá trị thực tế mà CAS vừa gặp, và không chứng minh giá trị đã khác trong cả một khoảng thời gian. Muốn ra quyết định tiếp, có thể đọc lại rồi đánh giá lại điều kiện.

Giá trị `true` cũng không giữ trạng thái cố định cho mã phía sau. Luồng khác có thể đổi ngay sau đó. Ngoài ra, `compareAndSet(5, 5)` có thể thành công mà không làm thay đổi giá trị số; “thành công” nghĩa là điều kiện khớp và thao tác được thực hiện theo hợp đồng.

### Không viết lại CAS bằng if

Đoạn sau không tương đương:

```java
if (state.get() == expected) {
    state.set(replacement);
}
```

Sau khi kiểm tra đúng, một luồng khác có thể thay đổi `state` trước lần `set()`. Lời gọi `set()` vẫn ghi đè vô điều kiện.

## 6. Chương trình kiểm chứng cả bốn thao tác

Lưu thành `AtomicOperationsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicOperationsDemo {
    private record User(String name) {
    }

    public static void main(String[] args) {
        AtomicInteger number = new AtomicInteger(10);

        System.out.println("get=" + number.get());

        number.set(20);
        System.out.println("afterSet=" + number.get());

        int old = number.getAndSet(30);
        System.out.println("swap.old=" + old);
        System.out.println("swap.current=" + number.get());

        boolean wrongExpected = number.compareAndSet(20, 40);
        System.out.println("cas.wrong=" + wrongExpected);
        System.out.println("afterWrong=" + number.get());

        boolean matched = number.compareAndSet(30, 40);
        System.out.println("cas.matched=" + matched);
        System.out.println("afterMatched=" + number.get());

        User original = new User("Ada");
        User equalButDifferent = new User("Ada");
        AtomicReference<User> owner = new AtomicReference<>(original);

        System.out.println("reference.equalValue="
                + original.equals(equalButDifferent));
        System.out.println("reference.sameObject="
                + (original == equalButDifferent));

        boolean equalValueCas = owner.compareAndSet(
                equalButDifferent, new User("Grace"));
        System.out.println("reference.casEqual=" + equalValueCas);

        boolean sameObjectCas = owner.compareAndSet(
                original, new User("Grace"));
        System.out.println("reference.casSame=" + sameObjectCas);
        System.out.println("reference.name=" + owner.get().name());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 AtomicOperationsDemo.java
java AtomicOperationsDemo
```

Stdout:

```text
get=10
afterSet=20
swap.old=20
swap.current=30
cas.wrong=false
afterWrong=30
cas.matched=true
afterMatched=40
reference.equalValue=true
reference.sameObject=false
reference.casEqual=false
reference.casSame=true
reference.name=Grace
```

Phần đầu cho thấy giá trị trả về của từng thao tác. Phần sau chứng minh CAS tham chiếu không dùng `equals()`.

### AtomicReference so sánh bằng ==

Với `AtomicReference<V>`, đối số kỳ vọng phải là **đúng tham chiếu đang giữ**, không chỉ là một đối tượng có nội dung bằng nhau.

Trong ví dụ:

- Hai `User("Ada")` bằng nhau theo `equals()` do cách `record` định nghĩa so sánh.
- Chúng vẫn là hai đối tượng riêng.
- CAS với đối tượng thứ hai thất bại.
- CAS với tham chiếu `original` đang được giữ thành công.

Khi cập nhật tham chiếu bằng vòng CAS, thường lấy tham chiếu kỳ vọng từ `get()`, tạo một trạng thái mới dựa trên nó, rồi CAS chính tham chiếu đã đọc đó.

Không dùng `AtomicReference<Integer>` như một bản thay thế máy móc cho `AtomicInteger`: cơ chế đóng hộp và việc tái sử dụng một số đối tượng `Integer` có thể làm phép so sánh danh tính gây nhầm. Chọn lớp nguyên tử số khi mô hình là một giá trị số nguyên.

## 7. Vòng CAS cho cập nhật có điều kiện

Giả sử còn một số suất hữu hạn. Mỗi yêu cầu chỉ được lấy một suất nếu số còn lại dương. Cần bảo toàn điều kiện:

```text
remaining >= 0
mỗi lần thành công giảm đúng 1
```

Một vòng CAS làm như sau:

1. Đọc giá trị quan sát được.
2. Nếu đã hết, trả thất bại.
3. Tính giá trị mới từ lần đọc đó.
4. CAS với giá trị kỳ vọng.
5. Thành công thì kết thúc; thất bại thì đọc lại và đánh giá lại.

Không tiếp tục dùng mãi giá trị kỳ vọng cũ khi đã thất bại. Điều kiện nghiệp vụ có thể đã đổi.

### Chương trình nhiều luồng lấy suất

Lưu thành `CasQuotaDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CasQuotaDemo {
    private static final class Quota {
        private final AtomicInteger remaining;

        Quota(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial must be non-negative");
            }
            remaining = new AtomicInteger(initial);
        }

        boolean tryTake() {
            for (;;) {
                int observed = remaining.get();
                if (observed == 0) {
                    return false;
                }

                int next = observed - 1;
                if (remaining.compareAndSet(observed, next)) {
                    return true;
                }
            }
        }

        int remaining() {
            return remaining.get();
        }
    }

    public static void main(String[] args) throws Exception {
        Quota quota = new Quota(10);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        List<Future<Boolean>> results = new ArrayList<>();

        try {
            for (int i = 0; i < 100; i++) {
                results.add(pool.submit(quota::tryTake));
            }

            int accepted = 0;
            for (Future<Boolean> result : results) {
                if (result.get(10, TimeUnit.SECONDS)) {
                    accepted++;
                }
            }

            System.out.println("accepted=" + accepted);
            System.out.println("rejected=" + (results.size() - accepted));
            System.out.println("remaining=" + quota.remaining());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 CasQuotaDemo.java
java CasQuotaDemo
```

Stdout khi các tác vụ hoàn thành trong giới hạn chờ:

```text
accepted=10
rejected=90
remaining=0
```

Thứ tự luồng nào lấy được suất không xác định, nhưng số lần thành công là `10`: không có thao tác bổ sung suất hoặc đặt lại số dư trong chương trình.

Nếu hai luồng cùng đọc `remaining=1`, cả hai thử CAS `1→0`. Chỉ một lần có thể thực hiện chuyển đổi đó. Luồng còn lại đọc lại, thấy `0` và trả thất bại.

`accepted` trong `main` không cần là biến nguyên tử vì chỉ luồng chính sửa nó sau khi nhận các kết quả. Ta không cần biến mọi biến của chương trình thành `AtomicInteger`.

### Phần tính lại phải an toàn khi lặp

Trong ví dụ, `observed - 1` không có tác dụng phụ. Nó có thể được tính nhiều lần nếu CAS thất bại.

Không đặt việc gửi email, trừ tiền bên ngoài, tăng một bộ đếm nghiệp vụ khác hoặc ghi dữ liệu ngoài hệ thống vào giữa lần đọc và CAS rồi giả định chỉ chạy một lần. Mỗi lần thử lại có thể thực hiện chúng lần nữa.

CAS thành công cũng không tạo giao dịch chung với một hệ thống bên ngoài. Nếu sau khi lấy suất thành công còn cần thực hiện công việc có thể thất bại, phải định nghĩa thêm cách xác nhận, hoàn trả hoặc bù trừ. Ví dụ chỉ giải quyết thao tác lấy suất trong bộ nhớ.

## 8. Ngữ nghĩa bộ nhớ: nguyên tử và nhìn thấy dữ liệu

Với các phương thức không có hậu tố đặc biệt trong bài:

| Thao tác | Tác dụng bộ nhớ cần nhận biết |
|---|---|
| `get()` | Đọc theo ngữ nghĩa `volatile` |
| `set()` | Ghi theo ngữ nghĩa `volatile` |
| `getAndSet()` | Thao tác đọc–ghi nguyên tử với hiệu ứng đọc/ghi `volatile` |
| `compareAndSet()` | Đọc theo ngữ nghĩa `volatile`; khi thành công có phần ghi theo ngữ nghĩa `volatile` |

Các mô tả chính thức dẫn đến các [chế độ truy cập tương ứng của `VarHandle`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/VarHandle.html). Không cần tự viết `VarHandle` để dùng bốn phương thức này đúng.

Một mẫu công bố một lần có thể được hiểu như sau:

```text
Luồng sản xuất:
    chuẩn bị dữ liệu
    ready.set(true)

Luồng tiêu thụ:
    nếu ready.get() thấy true do lần công bố đó
        sử dụng dữ liệu đã chuẩn bị trước khi công bố
```

Mối quan hệ đồng bộ giúp công bố các ghi xảy ra trước lần đặt cờ. Nhưng cờ không tự bảo vệ những thay đổi tiếp theo vào đối tượng dữ liệu. Mẫu còn cần quy tắc công bố một lần hoặc giao thức phiên bản rõ ràng; không tùy ý đặt cờ về `false` rồi tái sử dụng như thể mọi chu kỳ đều tự được ghép đúng.

Tương tự, `AtomicReference` phù hợp để công bố một đối tượng trạng thái bất biến mới. Nó bảo vệ tham chiếu và hỗ trợ công bố trạng thái đã chuẩn bị, không tự biến các trường sửa được của đối tượng đó thành an toàn khi nhiều luồng cùng sửa.

Không đánh đồng các phương thức trong bài với `getPlain()`, `setPlain()`, `getOpaque()`, các biến thể acquire/release hay CAS yếu. Chúng có ngữ nghĩa bộ nhớ khác nhau. Khi chưa có nhu cầu và phân tích cụ thể, dùng đúng hợp đồng của API đang chọn, không thay thế dựa trên tên gần giống.

## 9. Những giới hạn phải nhớ

### Một biến nguyên tử không gộp nhiều biến thành một giao dịch

Nếu có `AtomicInteger used` và `AtomicInteger available`, cập nhật lần lượt hai biến không làm người đọc luôn thấy một cặp nhất quán.

Khi nhiều trường phải chuyển cùng nhau, có thể cân nhắc:

- Khóa bao trùm toàn bộ trạng thái liên quan.
- Một đối tượng trạng thái bất biến chứa cả nhóm trường, được thay bằng CAS trên một `AtomicReference`.

Hướng thứ hai vẫn yêu cầu toàn bộ quy tắc chuyển trạng thái đi qua cùng tham chiếu và đúng vòng kiểm tra/cập nhật.

### CAS không ghi lại lịch sử: vấn đề ABA

Giả sử A đọc giá trị `5`. Trong lúc A tính toán, B đổi `5→6→5`. Sau đó CAS của A với kỳ vọng `5` vẫn có thể thành công.

CAS kiểm tra giá trị tại điểm thao tác, không chứng minh “chưa ai thay đổi kể từ lần đọc của tôi”.

Điều này có thể hoàn toàn chấp nhận được với một số mô hình giá trị. Nếu nghiệp vụ cần phát hiện từng lần thay đổi, phải mang thêm thông tin phiên bản hoặc dùng một giao thức phù hợp, chẳng hạn trạng thái bất biến có phiên bản hay tham chiếu có dấu phiên bản. Thông tin phiên bản cũng phải được cập nhật nhất quán với trạng thái; chỉ đặt nó ở một biến độc lập không tự giải quyết vấn đề.

### Không có cam kết công bằng cho vòng thử lại

Vòng CAS có thể thất bại nhiều lần khi tranh chấp cao. Không suy ra rằng mỗi luồng đều thành công trong một số lần thử cố định hoặc có độ trễ tối đa.

Các thao tác nhỏ trên một biến thường dễ sử dụng, nhưng một thuật toán gồm nhiều bước vẫn cần xem xét tiến triển, tải CPU và chi phí tạo đối tượng ứng viên. Khi yêu cầu đồng bộ phức tạp, khóa hoặc công cụ mức cao có thể diễn đạt ý định rõ hơn.

### Giá trị trả về cần được dùng đúng

- `getAndSet()` trả giá trị cũ, không phải giá trị mới.
- `compareAndSet()` trả boolean, không trả giá trị cũ.
- Không bỏ qua kết quả `false` nếu công việc phía sau chỉ hợp lệ sau khi chuyển trạng thái thành công.
- Không dùng `get()` sau CAS để suy ngược chắc chắn giá trị tại thời điểm CAS: một cập nhật khác có thể đã xảy ra.

## 10. Cách chọn nhanh theo yêu cầu

| Yêu cầu | Thao tác phù hợp để bắt đầu xem xét |
|---|---|
| Chỉ cần quan sát một giá trị | `get()` |
| Cần công bố/ghi đè một giá trị đã xác định | `set()` |
| Cần ghi giá trị mới và biết giá trị mình vừa thay | `getAndSet()` |
| Chỉ chuyển khi vẫn đúng trạng thái kỳ vọng | `compareAndSet()` |
| Tăng/giảm một bộ đếm không có điều kiện riêng | Các phép cộng/tăng/giảm nguyên tử chuyên biệt |
| Cập nhật có điều kiện phụ thuộc lần đọc | Vòng CAS với đánh giá lại điều kiện |
| Cần bảo toàn quan hệ của nhiều giá trị | Thiết kế miền trạng thái chung trước khi chọn công cụ |

Một phép đọc và một phép ghi đều nguyên tử không làm tổng hợp của chúng nguyên tử. Câu hỏi thực hành hữu ích là: **Điều kiện và thay đổi có cần xảy ra như một thao tác duy nhất không?** Nếu có, không tách chúng thành `get()` rồi `set()`.

## 11. Tự kiểm tra

1. `number.getAndSet(7)` trả `3` thì có thể kết luận gì?  
   Thao tác đó thay giá trị `3` bằng `7`. Không thể kết luận biến vẫn là `7` sau đó nếu còn luồng khác ghi.

2. Hai luồng cùng chạy `set(get()+1)` có bảo đảm tăng hai lần không?  
   Không. Hai luồng có thể cùng tính từ một giá trị cũ và ghi đè nhau.

3. CAS trên `AtomicReference<User>` có chấp nhận một `User` mới nhưng `equals()` bằng đối tượng đang giữ không?  
   Không chỉ vì `equals()` bằng nhau. Điều kiện so sánh là danh tính tham chiếu.

4. CAS thất bại thì nên giữ nguyên giá trị kỳ vọng và thử mãi không?  
   Thông thường cần đọc lại và đánh giá lại yêu cầu; nếu không, có thể tiếp tục thử một điều kiện đã không còn phù hợp.

5. CAS thành công có nghĩa là công việc gửi ra hệ thống bên ngoài cũng đã hoàn tất đúng một lần không?  
   Không. Nó chỉ quyết định thao tác cập nhật biến theo hợp đồng; công việc ngoài biến cần giao thức riêng.

## 12. Tài liệu chính thức

- [AtomicInteger — get, set, getAndSet và compareAndSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
- [AtomicReference — so sánh tham chiếu và cập nhật nguyên tử](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
- [AtomicBoolean — các thao tác trên cờ nguyên tử](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html)
- [Gói java.util.concurrent.atomic — phạm vi và các lớp liên quan](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)

Các API trọng tâm vẫn được sử dụng trong Java hiện đại; hai chương trình đầy đủ chạy được trên JDK 17 trở lên.
