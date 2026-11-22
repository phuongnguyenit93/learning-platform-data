# AtomicStampedReference và AtomicMarkableReference

## 1. Khi một tham chiếu chưa mô tả đủ trạng thái

Một `AtomicReference<V>` cho phép cập nhật tham chiếu bằng thao tác so sánh và đặt (compare-and-set, CAS). Nhưng đôi khi câu hỏi của thuật toán không chỉ là “hiện đang trỏ tới đối tượng nào?”.

Ví dụ:

- “Tham chiếu có còn ở đúng phiên bản mà tôi đã đọc không?”
- “Liên kết này đã được đánh dấu xóa về mặt logic chưa?”
- “Tôi có thể đổi tham chiếu và thông tin đi kèm như một đơn vị không?”

Nếu đặt thông tin đi kèm vào một biến nguyên tử riêng, hai biến vẫn có thể bị đọc hoặc cập nhật xen kẽ. `AtomicStampedReference<V>` và `AtomicMarkableReference<V>` cung cấp hai dạng cặp trạng thái:

| Lớp | Trạng thái chung | Ý nghĩa thường dùng |
| --- | --- | --- |
| `AtomicStampedReference<V>` | `(reference, int stamp)` | Tham chiếu kèm dấu phiên bản |
| `AtomicMarkableReference<V>` | `(reference, boolean mark)` | Tham chiếu kèm cờ trạng thái |

Điểm quan trọng là **cặp được quản lý như một đơn vị nguyên tử**. Bản thân thư viện không quyết định stamp phải tăng thế nào hoặc mark mang nghĩa gì; đó là quy ước của thuật toán sử dụng.

Hai lớp xuất hiện từ Java 5 và vẫn là API dùng được trong Java hiện đại. Bài dùng Java 17 trở lên, tập trung vào các thao tác rõ hợp đồng: đọc cặp và `compareAndSet`.

## 2. Vì sao ABA gây vấn đề?

Giả sử một luồng đọc tham chiếu `A`, tính toán dựa trên nó rồi chuẩn bị CAS. Trong lúc đó, luồng khác đổi tham chiếu:

```text
A → B → A
```

Khi luồng đầu thử CAS với kỳ vọng `A`, tham chiếu hiện tại lại chính là `A`. CAS trên tham chiếu đơn có thể thành công dù đã có thay đổi trung gian.

Không phải mọi lần xuất hiện ABA đều làm thuật toán sai. Vấn đề chỉ xuất hiện khi tính đúng của phép tính cũ còn phụ thuộc vào lịch sử đó: chẳng hạn một nút đã bị gỡ ra rồi tái sử dụng, hoặc phiên bản cấu hình đã đổi rồi quay lại đối tượng trước.

CAS so sánh trạng thái hiện tại với kỳ vọng; nó không tự lưu lịch sử. Nếu lịch sử liên quan đến tính đúng, cần mã hóa đủ thông tin đó vào trạng thái được so sánh.

Với stamp được cập nhật đúng quy ước:

```text
(A, 0) → (B, 1) → (A, 2)
```

Một CAS kỳ vọng `(A, 0)` sẽ thất bại khi trạng thái hiện tại là `(A, 2)`, dù phần tham chiếu giống nhau.

## 3. AtomicStampedReference: tham chiếu và dấu phiên bản

Khởi tạo:

```java
AtomicStampedReference<String> state =
        new AtomicStampedReference<>("initial", 0);
```

Đọc một cặp nhất quán:

```java
int[] stampHolder = new int[1];
String observed = state.get(stampHolder);
int observedStamp = stampHolder[0];
```

`get` trả tham chiếu và ghi stamp tương ứng vào phần tử số 0 của mảng. Mảng phải có ít nhất một phần tử. Nên để mảng này cục bộ cho từng luồng hoặc từng lời gọi; bản thân mảng chứa kết quả không phải một biến nguyên tử dùng chung.

Không thay cách đọc trên bằng:

```java
// Hai lần đọc riêng: không bảo đảm một ảnh chụp chung.
String observed = state.getReference();
int observedStamp = state.getStamp();
```

Giữa hai lời gọi, một luồng khác có thể đổi cả cặp. Bạn có thể lấy tham chiếu của phiên bản trước và stamp của phiên bản sau. Từng phương thức có ích khi chỉ cần một thành phần, nhưng ghép kết quả của chúng không tạo ảnh chụp nguyên tử.

Cập nhật có điều kiện:

```java
boolean changed = state.compareAndSet(
        observed,
        replacement,
        observedStamp,
        observedStamp + 1);
```

Đoạn trên minh họa cách gọi; `replacement` là tham chiếu đề xuất đã có. Thứ tự tham số là:

```text
expectedReference, newReference, expectedStamp, newStamp
```

Đừng nhầm thành thứ tự hai cặp `(expectedReference, expectedStamp)`, `(newReference, newStamp)`.

CAS thành công khi đồng thời khớp tham chiếu và stamp kỳ vọng. Tham chiếu được so bằng `==`, không bằng `equals`. Hai đối tượng có nội dung bằng nhau vẫn có thể là hai kỳ vọng khác nhau.

Stamp không tự tăng. Thư viện cũng không cấm giảm stamp hay đặt lại về giá trị cũ. Nếu một đường cập nhật làm `(A, 0) → (B, 0) → (A, 0)`, lợi ích phát hiện phiên bản đã bị bỏ qua bởi chính quy ước sử dụng.

## 4. AtomicMarkableReference: cờ trạng thái gắn với tham chiếu

Khởi tạo và đọc:

```java
AtomicMarkableReference<String> link =
        new AtomicMarkableReference<>("node", false);

boolean[] markHolder = new boolean[1];
String observed = link.get(markHolder);
boolean observedMark = markHolder[0];
```

Cập nhật có điều kiện:

```java
boolean marked = link.compareAndSet(
        observed,
        observed,
        false,
        true);
```

Ở đây giữ nguyên tham chiếu và đổi cờ từ `false` sang `true`. Một quy ước thường gặp là `false` nghĩa là liên kết đang hoạt động, `true` nghĩa là đã bị xóa về mặt logic.

Cờ này không tự xóa nút, không tự ngắt liên kết và không tự giải phóng tài nguyên. Trong một cấu trúc dữ liệu không dùng khóa, xóa logic có thể là bước đầu, còn việc gỡ nút khỏi chuỗi là một bước riêng do thuật toán thực hiện.

Ngoài ra, mark thuộc về **cặp tham chiếu do đối tượng AtomicMarkableReference quản lý**. Nó không phải trường boolean được tự động thêm vào đối tượng được trỏ tới. Nếu có nhiều liên kết cùng trỏ một nút, đánh dấu một liên kết không tự đánh dấu các liên kết còn lại.

Tương tự stamp, muốn đọc cả tham chiếu lẫn cờ phải dùng `get(markHolder)`. Gọi riêng `getReference()` và `isMarked()` không bảo đảm hai kết quả cùng một ảnh chụp.

## 5. Ví dụ chạy được: phiên bản, đánh dấu và giới hạn của một bit

Chương trình sau mô phỏng một lịch xen kẽ bằng thứ tự thao tác cố định. Nó không cần tạo nhiều luồng: mục tiêu là kiểm chứng điều kiện CAS bằng các trạng thái đã biết, không đo hiệu năng hay phụ thuộc lịch của bộ lập lịch.

Lưu thành `StampedAndMarkableDemo.java`:

```java
import java.util.concurrent.atomic.AtomicMarkableReference;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicStampedReference;

public class StampedAndMarkableDemo {
    private static void require(boolean success) {
        if (!success) {
            throw new AssertionError("Unexpected CAS failure");
        }
    }

    public static void main(String[] args) {
        Object a = new Object();
        Object b = new Object();
        Object c = new Object();

        AtomicReference<Object> plain = new AtomicReference<>(a);
        Object oldPlain = plain.get();
        require(plain.compareAndSet(a, b));
        require(plain.compareAndSet(b, a));
        System.out.println("plainStaleCas="
                + plain.compareAndSet(oldPlain, c));

        AtomicStampedReference<Object> stamped =
                new AtomicStampedReference<>(a, 0);
        int[] stampHolder = new int[1];
        Object oldStamped = stamped.get(stampHolder);
        int oldStamp = stampHolder[0];

        require(stamped.compareAndSet(a, b, 0, 1));
        require(stamped.compareAndSet(b, a, 1, 2));
        System.out.println("stampedStaleCas="
                + stamped.compareAndSet(oldStamped, c, oldStamp, 3));
        System.out.println("stamp=" + stamped.getStamp());

        AtomicMarkableReference<Object> marked =
                new AtomicMarkableReference<>(a, false);
        boolean[] markHolder = new boolean[1];
        Object oldMarked = marked.get(markHolder);
        boolean oldMark = markHolder[0];

        require(marked.compareAndSet(a, a, false, true));
        System.out.println("markedStaleCas="
                + marked.compareAndSet(oldMarked, b, oldMark, false));
        System.out.println("marked=" + marked.isMarked());

        AtomicMarkableReference<Object> cycled =
                new AtomicMarkableReference<>(a, false);
        Object oldCycled = cycled.get(markHolder);
        boolean oldCycleMark = markHolder[0];
        require(cycled.compareAndSet(a, b, false, true));
        require(cycled.compareAndSet(b, a, true, false));
        System.out.println("markCycleStaleCas="
                + cycled.compareAndSet(oldCycled, c, oldCycleMark, false));
    }
}
```

Chạy bằng JDK 17 trở lên:

```shell
javac --release 17 StampedAndMarkableDemo.java
java StampedAndMarkableDemo
```

Stdout chính xác:

```text
plainStaleCas=true
stampedStaleCas=false
stamp=2
markedStaleCas=false
marked=true
markCycleStaleCas=true
```

Diễn giải:

1. Tham chiếu đơn trở lại đúng đối tượng `a`, nên kỳ vọng cũ vẫn được chấp nhận.
2. Cặp stamped trở lại `a` nhưng stamp đã là `2`, nên kỳ vọng stamp `0` bị từ chối.
3. Cặp marked vẫn trỏ `a` nhưng cờ đã thành `true`, nên phép đổi dựa trên cờ cũ `false` thất bại.
4. Cặp cuối cùng đi một vòng rồi trở lại đúng `(a, false)`; kỳ vọng cũ lại hợp lệ theo phép so sánh của API.

Dòng cuối chỉ ra rằng **một bit mark không phải bộ đếm phiên bản và không phát hiện được mọi lịch ABA**. Một thuật toán dùng mark cho xóa logic thường cần quy tắc vòng đời, chẳng hạn không “hồi sinh” cùng liên kết sau khi đã đánh dấu xóa. Quy tắc này do thuật toán thực hiện; lớp thư viện không tự áp đặt.

## 6. Viết vòng lặp stamped đúng cách

Đoạn dưới là các thành phần để đặt trong một lớp có sẵn. Mô hình dùng giá trị bất biến để không sửa dữ liệu của ảnh chụp cũ:

```java
record Settings(String mode) {}

static boolean replaceIfMode(
        AtomicStampedReference<Settings> state,
        String requiredMode,
        String nextMode) {
    int[] stampHolder = new int[1];

    for (;;) {
        Settings observed = state.get(stampHolder);
        int observedStamp = stampHolder[0];

        if (!observed.mode().equals(requiredMode)) {
            return false;
        }

        Settings next = new Settings(nextMode);
        int nextStamp = Math.addExact(observedStamp, 1);

        if (state.compareAndSet(
                observed, next, observedStamp, nextStamp)) {
            return true;
        }
    }
}
```

Giả định: tham chiếu ban đầu và các chuỗi `mode` khác null; mọi nơi cập nhật đều theo cùng quy ước stamp. Có thể bổ sung kiểm tra đầu vào tại ranh giới gọi nếu cần.

Sau thất bại, đọc lại **cả cặp**, kiểm tra lại điều kiện và tạo lại đề xuất. Không chỉ đọc stamp mới rồi ghép với tham chiếu cũ. Không giữ đề xuất được tính từ một ảnh chụp không còn hợp lệ.

`Math.addExact` giúp ví dụ từ chối tràn stamp bằng ngoại lệ, thay vì âm thầm quay vòng số nguyên. Trong hệ thống thực tế, cần xác định rõ chính sách khi hết miền phiên bản. Ném ngoại lệ là một chính sách minh họa, không phải khả năng tự mở rộng stamp của thư viện.

Phần có thể thử lại không nên gửi email, trừ tiền hoặc sửa đối tượng dùng chung. CAS thất bại chỉ có nghĩa cặp nguyên tử chưa được cập nhật bởi lần thử đó; nó không hoàn tác những tác dụng phụ đã thực hiện trước CAS.

Một CAS thành công là điểm ghi nhận phép chuyển cặp trạng thái. Giá trị có thể bị đổi tiếp ngay sau đó; thành công không cho luồng quyền sở hữu độc quyền đối tượng.

## 7. Những phương thức dễ bị hiểu nhầm

### set không kiểm tra phiên bản trước

`set(newReference, newStamp)` hoặc `set(newReference, newMark)` đặt cặp mới vô điều kiện. Chúng hữu ích khi hợp đồng cho phép đặt lại toàn bộ trạng thái, nhưng không thay được CAS khi phép cập nhật phải dựa trên một ảnh chụp cụ thể.

Nếu mọi luồng đều dùng CAS tăng stamp nhưng một đường khác dùng `set` khôi phục stamp cũ, cơ chế phát hiện phiên bản có thể bị phá vỡ.

### attemptStamp và attemptMark không so sánh metadata cũ

`attemptStamp(expectedReference, newStamp)` và `attemptMark(expectedReference, newMark)` yêu cầu tham chiếu hiện tại khớp kỳ vọng, nhưng không nhận stamp hoặc mark kỳ vọng làm đối số.

Vì vậy, chúng không diễn đạt điều kiện “cả tham chiếu và metadata vẫn đúng như lúc tôi đọc”. Khi thuật toán cần điều kiện đó, dùng `compareAndSet`.

Hợp đồng các phương thức `attempt...` cũng cho phép thất bại giả. Không kết luận rằng mỗi kết quả `false` của chúng chứng minh tham chiếu đã bị thay đổi.

### weakCompareAndSet không phải thay thế máy móc

Hai lớp có `weakCompareAndSet`, với những khác biệt về khả năng thất bại giả và bảo đảm thứ tự theo tài liệu API. Bài dùng `compareAndSet` để tránh đưa các giả định đó vào thuật toán của người mới. Không đổi tên phương thức trong một vòng lặp rồi cho rằng tính đúng được giữ nguyên mà không phân tích hợp đồng bộ nhớ.

## 8. Giới hạn của stamped và markable

### Stamp có miền hữu hạn

Stamp là `int`, không phải số phiên bản vô hạn. Nếu để nó quay vòng hoặc chủ động tái sử dụng stamp, một ảnh chụp rất cũ có thể lại trùng cặp hiện tại. Do đó, phát biểu “AtomicStampedReference loại bỏ hoàn toàn ABA trong mọi chương trình” là quá mạnh.

Điều cần chứng minh là quy ước phiên bản không bị lặp lại trong khoảng thời gian một ảnh chụp cũ còn có thể được sử dụng. Trong ứng dụng có vòng đời phức tạp, cần thiết kế chính sách phiên bản hoặc cấu trúc trạng thái khác phù hợp.

### Đối tượng bên trong vẫn có thể khả biến

Cặp nguyên tử bảo vệ việc công bố tham chiếu và metadata. Nó không tự làm các trường của đối tượng được tham chiếu an toàn khi nhiều luồng cùng sửa.

Nếu luồng A sửa `observed.field` trước CAS rồi CAS thất bại, sửa đổi trên đối tượng vẫn đã xảy ra. Dùng dữ liệu bất biến và tạo đối tượng đề xuất mới thường giúp lập luận rõ ràng hơn.

### Mark không thay thế cơ chế quản lý vòng đời

Đánh dấu xóa không làm đối tượng biến mất tức thời. Luồng khác có thể vẫn giữ tham chiếu đã đọc. Bộ thu gom rác của Java và các quy tắc cấu trúc dữ liệu giải quyết những vấn đề khác nhau: có tham chiếu còn sống không đồng nghĩa nút vẫn thuộc cấu trúc về mặt logic.

Nếu đối tượng giữ tài nguyên bên ngoài như tệp hoặc kết nối, cờ mark cũng không tự quyết định khi nào đóng tài nguyên là an toàn.

### Không có bảo đảm công bằng từ riêng lớp nguyên tử

Một luồng có thể CAS thất bại nhiều lần. Mức tiến triển và tính đúng của toàn bộ cấu trúc dữ liệu phụ thuộc thuật toán xung quanh, không chỉ tên lớp. Cặp nguyên tử cũng có chi phí quản lý bổ sung; không mặc định nó nhanh hơn khóa trong mọi mức tranh chấp.

## 9. Chọn công cụ theo điều kiện cần bảo vệ

| Nhu cầu | Điểm bắt đầu phù hợp |
| --- | --- |
| Chỉ cần thay một tham chiếu nếu nó còn đúng đối tượng cũ | `AtomicReference` |
| Cần kiểm tra thêm dấu phiên bản cùng tham chiếu | `AtomicStampedReference` với quy ước phiên bản rõ ràng |
| Cần một cờ trạng thái nguyên tử đi cùng tham chiếu | `AtomicMarkableReference` với quy tắc vòng đời rõ ràng |
| Cần nhiều trường tạo thành một trạng thái nhất quán | Cân nhắc một đối tượng bất biến được công bố nguyên tử, hoặc khóa chung |
| Cần giao dịch với cơ sở dữ liệu hoặc dịch vụ ngoài | Cơ chế giao dịch/phối hợp phù hợp; CAS bộ nhớ không bao trùm thao tác ngoài |

Không dùng stamp chỉ vì dữ liệu “có thể thay đổi”; hãy xác định lịch sử thay đổi có ảnh hưởng tính đúng hay không. Không dùng mark như số phiên bản rút gọn nếu thuật toán cần phân biệt nhiều lần chuyển trạng thái.

## 10. Tự kiểm tra

1. Vì sao `getReference()` rồi `getStamp()` không thay được `get(holder)` khi cần ảnh chụp cặp?
2. Nếu stamp không thay đổi trong chuỗi `A → B → A`, CAS cũ có được chặn chắc chắn không?
3. Hai đối tượng `String` có `equals` bằng nhau có tự được coi là cùng tham chiếu kỳ vọng không?
4. Mark chuyển `false → true → false` có lưu được số lần chuyển không?
5. Sau khi đánh dấu xóa logic, nút có tự bị gỡ khỏi mọi liên kết không?

Đáp án:

1. Hai lần đọc có thể bị một cập nhật chen giữa.
2. Không; cặp hiện tại có thể trùng cặp kỳ vọng cũ.
3. Không; CAS so sánh tham chiếu bằng `==`.
4. Không; nó chỉ lưu một trạng thái boolean hiện tại.
5. Không; việc gỡ liên kết thuộc thuật toán cấu trúc dữ liệu.

Trước khi dùng một trong hai lớp, cần viết rõ ba điều: cặp trạng thái biểu diễn điều gì, mọi đường cập nhật phải tuân theo quy ước nào, và ảnh chụp cũ bị loại bỏ bằng điều kiện nào.

## Tài liệu đối chiếu

- [AtomicStampedReference — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html).
- [AtomicMarkableReference — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicMarkableReference.html).
