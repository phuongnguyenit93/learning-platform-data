# CopyOnWriteArraySet và trường hợp tập ít thay đổi

## 1. Bài toán: một tập đăng ký nhỏ, được duyệt rất nhiều lần

Giả sử một ứng dụng giữ danh sách các bộ xử lý đăng ký nhận sự kiện. Mỗi sự kiện cần được gửi tới các bộ xử lý hiện có. Việc phát sự kiện xảy ra liên tục, còn đăng ký hoặc hủy đăng ký chỉ xảy ra thỉnh thoảng. Ta muốn tránh phần tử trùng và muốn một lượt duyệt tiếp tục ổn định dù có đăng ký thay đổi trong lúc đó.

`CopyOnWriteArraySet<E>` là một lựa chọn cho mô hình ấy: một `Set` an toàn cho nhiều luồng, không chứa phần tử trùng theo quy tắc bằng nhau, và cung cấp iterator theo ảnh chụp (snapshot). Nó dùng `CopyOnWriteArrayList` bên trong, đánh đổi chi phí cập nhật để việc đọc/duyệt thuận lợi.

Điều kiện “ít thay đổi” là tương đối so với số lần đọc và kích thước tập. Một tập hàng trăm nghìn phần tử dù chỉ thay đổi vài lần mỗi giây vẫn có thể tốn đáng kể chi phí sao chép. Đừng chỉ nhìn tên lớp rồi dùng nó cho mọi dữ liệu chia sẻ.

API này vẫn phù hợp với các trường hợp nêu trên trong Java hiện đại. Ví dụ trong bài chạy được với Java 17 trở lên.

## 2. Cơ chế copy-on-write

Hãy hình dung một mảng tham chiếu chứa `[alpha, beta]`. Khi một luồng tạo iterator, iterator giữ phiên bản mảng đó. Nếu luồng khác thêm `gamma`, thao tác cập nhật tạo/xuất bản phiên bản chứa dữ liệu mới; iterator cũ tiếp tục dùng phiên bản cũ.

```text
Phiên bản đang dùng lúc tạo iterator I1: [alpha, beta]

Thêm gamma vào set:
Set hiện tại:                         [alpha, beta, gamma]
I1 tiếp tục duyệt:                    [alpha, beta]
```

Không phải mỗi lần đọc đều sao chép toàn bộ tập. Chi phí sao chép chủ yếu xuất hiện khi thay đổi cấu trúc có hiệu lực. Thêm một phần tử đã có trả `false` và không làm tăng tập; không nên mô tả nó như một lần luôn tạo phiên bản lớn hơn.

Các luồng cập nhật phải phối hợp để không tạo phần tử trùng hoặc làm mất thay đổi của nhau. Copy-on-write không có nghĩa mọi thao tác đều không dùng khóa hay mọi cập nhật đều chạy đồng thời không tranh chấp.

Tính chất, trường hợp phù hợp và iterator ảnh chụp được quy định trong [CopyOnWriteArraySet — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CopyOnWriteArraySet.html).

## 3. Quy tắc Set vẫn là phần cốt lõi

| Thao tác | Ý nghĩa và kết quả |
| --- | --- |
| `add(e)` | Thêm nếu chưa có phần tử bằng `e`; trả `true` khi tập thay đổi, `false` nếu đã có |
| `remove(e)` | Xóa phần tử bằng `e` nếu có; trả `true` khi đã xóa |
| `contains(e)` | Kiểm tra phần tử bằng `e` có trong tập tại lần quan sát |
| `size()` | Số phần tử của phiên bản được quan sát |
| `iterator()` | Duyệt ảnh chụp các phần tử theo thứ tự được thêm |

Sự duy nhất dựa vào so sánh bằng nhau (`equals`), không phải luôn dựa vào cùng địa chỉ đối tượng. Hai đối tượng `String` khác nhau nhưng cùng nội dung không trở thành hai phần tử riêng.

`CopyOnWriteArraySet` không phải một bảng băm. Việc kiểm tra tồn tại cần tìm trên cấu trúc mảng và có thể thực hiện nhiều phép so sánh; không mặc định `contains` có chi phí trung bình giống `HashSet`.

Lớp cho phép phần tử `null`, và vì là set nên nhiều lần thêm `null` không tạo nhiều phần tử `null`. Điều này khác với tập khóa của `ConcurrentHashMap`. Tuy nhiên, nếu tập đại diện cho các bộ xử lý có thể gọi, thường nên chặn đăng ký `null` ở API ứng dụng để vòng phát sự kiện không gặp `NullPointerException`.

Thứ tự iterator là thứ tự thêm của phiên bản được giữ. Xóa một phần tử rồi thêm lại là một lần thêm mới ở cuối; thêm trùng không chuyển phần tử cũ xuống cuối. Tính bằng nhau của hai set vẫn không phụ thuộc thứ tự duyệt như một list.

## 4. Ảnh chụp ổn định có ý nghĩa gì với một lượt phát sự kiện?

Một vòng `for-each` tạo iterator để duyệt. Nếu vòng đó đã lấy ảnh chụp `[alpha, beta]`, sau đó một luồng khác xóa alpha và thêm gamma, vòng đang chạy vẫn có thể gửi tới alpha và beta. Vòng được tạo sau thay đổi sẽ thấy phiên bản mới.

Điều này thường phù hợp với quy tắc “mỗi lượt phát sử dụng tập đăng ký tại lúc bắt đầu duyệt”. Nó tránh việc tập đích bị thay đổi giữa lượt. Nhưng nó không đáp ứng một yêu cầu mạnh hơn là “sau khi hủy đăng ký trả về, tuyệt đối không còn lượt gọi nào tới bộ xử lý đó”.

Muốn bảo đảm không còn lần gọi đang diễn ra hoặc sắp thực hiện từ ảnh chụp cũ, cần giao thức vòng đời riêng: trạng thái hoạt động, theo dõi lượt gọi đang chạy, chờ hoàn tất hoặc cơ chế phối hợp phù hợp. Chỉ đổi loại collection không tự cung cấp bảo đảm đó.

Iterator cũng không tự phân phối độc quyền công việc. Nếu hai luồng đồng thời phát hai sự kiện hoặc cùng duyệt để xử lý một sự kiện, một bộ xử lý có thể được gọi đồng thời. Bản thân bộ xử lý vẫn phải an toàn theo cách ứng dụng sử dụng nó.

## 5. Chương trình chạy đầy đủ

Chương trình dùng tên người đăng ký để tập trung vào cấu trúc tập. Nó kiểm tra thêm trùng, ảnh chụp của lượt đang chạy, cách xóa hợp lệ và việc hai luồng cùng thêm một phần tử.

Lưu vào `RarelyChangedSetDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class RarelyChangedSetDemo {
    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected set result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CopyOnWriteArraySet<String> subscribers = new CopyOnWriteArraySet<>();
        check(subscribers.add("alpha"));
        check(subscribers.add("beta"));
        boolean duplicate = subscribers.add(new String("alpha"));
        check(!duplicate);
        System.out.println("duplicate add: " + duplicate);

        Iterator<String> inFlight = subscribers.iterator();
        check(subscribers.remove("alpha"));
        check(subscribers.add("gamma"));

        List<String> oldRound = new ArrayList<>();
        inFlight.forEachRemaining(oldRound::add);
        check(oldRound.equals(List.of("alpha", "beta")));
        System.out.println("in-flight round: " + oldRound);
        System.out.println("current subscribers: " + subscribers);

        Iterator<String> readOnly = subscribers.iterator();
        readOnly.next();
        try {
            readOnly.remove();
            throw new AssertionError("iterator.remove must be unsupported");
        } catch (UnsupportedOperationException expected) {
            System.out.println("iterator.remove: UnsupportedOperationException");
        }

        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger successfulAdds = new AtomicInteger();
        Runnable register = () -> {
            try {
                start.await();
                if (subscribers.add("delta")) {
                    successfulAdds.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread one = new Thread(register, "one");
        Thread two = new Thread(register, "two");
        one.start();
        two.start();
        start.countDown();
        one.join();
        two.join();

        check(successfulAdds.get() == 1);
        System.out.println("successful concurrent adds: " + successfulAdds.get());
        System.out.println("final subscribers: " + subscribers);

        CopyOnWriteArraySet<String> nullable = new CopyOnWriteArraySet<>();
        check(nullable.add(null));
        check(!nullable.add(null));
        System.out.println("null elements after two adds: " + nullable.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 RarelyChangedSetDemo.java
java RarelyChangedSetDemo
```

Stdout:

```text
duplicate add: false
in-flight round: [alpha, beta]
current subscribers: [beta, gamma]
iterator.remove: UnsupportedOperationException
successful concurrent adds: 1
final subscribers: [beta, gamma, delta]
null elements after two adds: 1
```

`new String("alpha")` tạo một đối tượng khác nhưng bằng chuỗi đã lưu, nên `add` trả `false`. Việc này cho thấy tính duy nhất dùng quy tắc bằng nhau của phần tử.

`inFlight` được tạo trước khi xóa alpha và thêm gamma, nên nó vẫn duyệt `[alpha, beta]`. Dòng in tập hiện hành được thực hiện sau các thay đổi ấy và thấy `[beta, gamma]`. Đây là hai phiên bản khác nhau, không phải bằng chứng rằng thao tác xóa thất bại.

`iterator.remove()` không được hỗ trợ. Muốn thay tập, gọi phương thức của set như `remove(value)`, không sửa ảnh chụp qua iterator.

Hai luồng được mở bằng `CountDownLatch` để cùng có cơ hội thêm delta. Lịch chạy không bảo đảm chúng thực hiện cùng một thời điểm, nhưng vì không có bên xóa delta nên chỉ một lời gọi `add` trả `true`. `join()` đợi cả hai luồng trước khi in kết quả; do đó phần tử delta xuất hiện đúng một lần ở cuối.

Phép thử `null` dùng một tập riêng, giúp phân biệt khả năng của collection với quy tắc thường cần có của một API đăng ký bộ xử lý.

## 6. Không cần contains rồi mới add

```java
// Đoạn minh họa không cần thiết; subscribers là CopyOnWriteArraySet<String>.
if (!subscribers.contains("delta")) {
    subscribers.add("delta");
}
```

Bản thân `add` đã biểu diễn đúng thao tác “thêm nếu chưa có” và trả kết quả. Bước `contains` phía trước vừa thêm một lượt tìm kiếm vừa không giữ chỗ cho bên gọi: luồng khác có thể thay tập sau khi `contains` trả về.

```java
// Đoạn minh họa trong một phương thức.
boolean newlyRegistered = subscribers.add("delta");
if (newlyRegistered) {
    System.out.println("Registration was added by this call");
}
```

Set không tạo trùng chỉ vì hai bên cùng thực hiện đoạn kiểm tra rồi thêm, nhưng các tác động nghiệp vụ đặt trong nhánh `if (!contains(...))` có thể bị thực hiện nhiều lần. Khi cần biết chính lời gọi của mình có thêm được hay không, dựa vào giá trị trả về của `add`.

Thành công cũng chỉ áp dụng tại thao tác đó. Một luồng khác có thể xóa đăng ký ngay sau khi `add` trả về. Không dùng kết quả ấy để suy rằng toàn bộ một quy trình nhiều bước được giữ nguyên trạng thái.

## 7. Các giới hạn quan trọng của ảnh chụp

### Chỉ chụp tham chiếu, không sao chép sâu phần tử

Nếu phần tử là một đối tượng mutable, ảnh chụp cũ và set hiện tại vẫn có thể trỏ tới cùng đối tượng đó. Luồng khác sửa trường bên trong không tự tạo một phần tử bất biến cho iterator cũ.

Ví dụ một bộ xử lý chứa `enabled` hoặc cấu hình có thể đổi, collection không tự đồng bộ mọi lần đọc/ghi các trường ấy. Cần dữ liệu bất biến, `volatile`, khóa hoặc giao thức phù hợp với chính đối tượng. Cũng nên giữ những thuộc tính tham gia `equals` ổn định trong thời gian phần tử nằm trong set; đổi chúng có thể làm quy tắc duy nhất và tìm/xóa trở nên khó dự đoán.

### Iterator không sửa được phiên bản đang duyệt

`remove()` trên iterator ném `UnsupportedOperationException`. Gọi `set.remove(element)` trong khi duyệt là thao tác thay đổi set hiện hành; nó không thay ảnh chụp iterator đang giữ. Điều đó có thể đúng mục đích, nhưng không dùng nó để mong những phần tử còn lại trong ảnh chụp tự biến mất.

### Giữ ảnh chụp lâu có thể giữ bộ nhớ lâu

Khi iterator còn được giữ, phiên bản mảng cũ và những tham chiếu nó chứa có thể còn được giữ lại. Một phần tử đã xóa khỏi set hiện tại chưa chắc đã được thu gom nếu ảnh chụp cũ còn trỏ tới nó. Tránh lưu iterator dài hạn nếu không có nhu cầu rõ ràng.

Nguyên tắc ảnh chụp của cấu trúc nền được giải thích trong [CopyOnWriteArrayList — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

## 8. Chi phí và điều kiện lựa chọn

| Đặc điểm tải | Đánh giá |
| --- | --- |
| Tập nhỏ, phát sự kiện/duyệt nhiều, đăng ký ít đổi | Thường là trường hợp phù hợp để cân nhắc |
| Tập lớn, cần kiểm tra tồn tại liên tục | Cần cân nhắc chi phí tìm tuyến tính |
| Thêm/xóa liên tục | Chi phí sao chép, cấp phát và thu gom bộ nhớ có thể lớn |
| Cần một phiên bản tập ổn định cho mỗi lượt duyệt | Iterator ảnh chụp đáp ứng ở mức cấu trúc/tham chiếu |
| Cần đối tượng bên trong bất biến hoặc lệnh hủy có hiệu lực tức thì với mọi lượt gọi | Cần thiết kế thêm, collection không tự bảo đảm |

Với `n` phần tử, tìm một phần tử có thể phải so sánh với nhiều phần tử, còn một cập nhật thay đổi mảng thường phải sao chép lượng tham chiếu tỷ lệ với `n`. Bộ nhớ cho mỗi mảng cũng tỷ lệ với số phần tử. Chi phí thực tế còn phụ thuộc tần suất ghi, số ảnh chụp còn sống và chi phí `equals` của phần tử.

Không có một ngưỡng số lượng “nhỏ” đúng cho mọi hệ thống. Đo số lần duyệt so với ghi, thời gian thêm/xóa, độ trễ lúc tranh chấp, lượng cấp phát và áp lực GC trong tải thực tế. Một vòng benchmark chỉ đọc không chứng minh lớp phù hợp với một hệ thống thực tế thay đổi thành viên liên tục.

## 9. So sánh với các lựa chọn gần

| Lựa chọn | Điểm phù hợp | Khác biệt cần nhớ |
| --- | --- | --- |
| `CopyOnWriteArraySet` | Tập nhỏ, ít thay đổi, muốn lượt duyệt theo ảnh chụp | Tìm tuyến tính và cập nhật thường sao chép mảng |
| `ConcurrentHashMap.newKeySet()` | Tập đồng thời cần nhiều cập nhật/tìm kiếm, không cần thứ tự thêm | Iterator nhất quán yếu, không phải cùng ảnh chụp cố định; không cho phần tử `null` |
| `Collections.synchronizedSet(...)` | Có thể chấp nhận phối hợp bằng khóa chung | Khi duyệt phải giữ khóa wrapper đúng hợp đồng; bên ghi có thể phải chờ |
| `CopyOnWriteArrayList` | Cần danh sách thay vì tập, cho phép phần tử trùng hoặc cần vị trí | Không tự mang quy tắc duy nhất của set |

Tập khóa đồng thời là một lựa chọn khác được cung cấp trong [ConcurrentHashMap — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet()). Không thay giữa các loại chỉ dựa trên tên “thread-safe”: thứ tự, cách duyệt, quy tắc `null` và chi phí đều có thể khác.

## 10. Lưu ý khi dùng cho bộ xử lý sự kiện

Set giúp quản lý thành viên, không tự định nghĩa cách gọi callback. Nếu một callback ném ngoại lệ, vòng gọi thông thường có thể dừng trước các phần tử sau; ứng dụng cần chọn rõ cách cô lập lỗi. Nếu callback có thể bị gọi đồng thời từ nhiều lượt phát, cần thiết kế khả năng chịu gọi đồng thời của nó.

Việc một callback đăng ký/hủy đăng ký trong lúc chạy không sửa tập đích của chính iterator đang dùng. Đây thường là lợi ích của ảnh chụp, nhưng cũng cần được ghi thành hợp đồng API để người dùng biết thay đổi sẽ áp dụng cho lượt nào.

## 11. Tự kiểm tra

1. Hai đối tượng khác nhau nhưng `equals` trả `true` có thể cùng tồn tại như hai phần tử riêng không? Không, nếu quy tắc bằng nhau của chúng ổn định và hợp lệ.
2. Xóa một phần tử sau khi tạo iterator có làm iterator cũ chắc chắn bỏ qua nó không? Không; iterator cũ giữ ảnh chụp.
3. Gọi `iterator.remove()` có hợp lệ không? Không; dùng thao tác của set khi muốn thay đổi set hiện hành.
4. Vì sao tập lớn và ghi liên tục thường không phù hợp? Vì tìm kiếm và việc sao chép mảng khi cập nhật có chi phí đáng kể.
5. Xóa bộ xử lý khỏi set có bảo đảm nó không còn được gọi từ một lượt phát đang chạy không? Không.
6. Copy-on-write có làm mọi trường mutable của phần tử tự an toàn cho nhiều luồng không? Không.
