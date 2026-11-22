# Vấn đề ABA khi so sánh giá trị tham chiếu

## 1. CAS nhìn thấy hiện tại, còn thuật toán có thể cần lịch sử

Khi nhiều luồng cùng thay đổi một tham chiếu, ta thường dùng thao tác so sánh và cập nhật (compare-and-set, CAS):

```java
boolean changed = reference.compareAndSet(expected, replacement);
```

Với `AtomicReference`, phép so sánh dùng đồng nhất tham chiếu `==`: đối tượng đang được giữ phải chính là đối tượng `expected`. Nó không gọi `equals()`. Nếu điều kiện đúng, thao tác thay tham chiếu diễn ra nguyên tử. Đó là hợp đồng của [AtomicReference.compareAndSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html#compareAndSet(V,V)).

Giả sử một luồng đọc được tham chiếu A rồi tạm dừng để tính toán. Trong thời gian đó, một luồng khác đổi tham chiếu theo chuỗi:

```text
A → B → A
```

Khi luồng đầu quay lại, nó vẫn nhìn thấy đúng A. CAS với giá trị kỳ vọng A có thể thành công dù tham chiếu đã thay đổi hai lần. Đây là hình dạng của vấn đề **ABA**.

Điều nguy hiểm xuất hiện nếu quyết định cập nhật của luồng đầu dựa vào giả định: “Từ lần đọc A đến giờ, trạng thái liên quan chưa thay đổi”. Việc A xuất hiện trở lại không chứng minh giả định đó.

**CAS vẫn làm đúng việc so sánh hiện tại. Sai sót nằm ở việc thuật toán dùng kết quả đó để suy ra một lịch sử mà CAS không kiểm tra.**

## 2. Một lịch thực thi cụ thể

Gọi T1 là luồng đang xử lý chậm, T2 là luồng thay đổi trạng thái:

| Thời điểm | T1 | T2 | Tham chiếu hiện tại |
| --- | --- | --- | --- |
| 1 | Đọc A, giữ A làm giá trị kỳ vọng | | A |
| 2 | Tính kết quả dựa trên trạng thái đã đọc | Đổi A thành B | B |
| 3 | | Đổi B trở lại **cùng đối tượng A** | A |
| 4 | CAS từ A sang C | | C nếu CAS thành công |

Ở bước 4, câu hỏi “hiện tại có phải cùng A không?” có đáp án là có. Câu hỏi “đã có cập nhật nào kể từ lần đọc của T1 chưa?” cũng có đáp án là có. Hai câu hỏi độc lập.

Không phải mọi chuỗi A → B → A đều gây lỗi. Nếu yêu cầu nghiệp vụ chỉ là “thay giá trị khi hiện tại đang là A” và kết quả không phụ thuộc dữ liệu cũ khác, CAS thành công có thể hoàn toàn đúng. Ta cần chống ABA khi **sự thay đổi trung gian làm mất hiệu lực của quyết định đang giữ**, kể cả khi giá trị được so sánh đã quay về ban đầu.

## 3. Vì sao ABA có thể làm hỏng cấu trúc dữ liệu?

Xét mô hình ngăn xếp liên kết sau; đây là diễn giải thuật toán, không phải mã ngăn xếp hoàn chỉnh:

```text
head → A → B → C
```

Một thao tác lấy phần tử đầu có thể đọc:

```java
// Mã minh họa: head là AtomicReference<Node>.
Node oldHead = head.get();       // A
Node next = oldHead.next;        // B
// ... có thể bị gián đoạn ...
boolean removed = head.compareAndSet(oldHead, next);
```

T1 đã giữ cả `oldHead = A` và `next = B`. Trong lúc đó T2 thực hiện:

1. Lấy A ra; đầu ngăn xếp trở thành B.
2. Lấy B ra; đầu ngăn xếp trở thành C.
3. Dùng lại **chính nút A**, đặt liên kết của A trỏ đến C rồi đưa A trở lại.

Trạng thái mới là:

```text
head → A → C
```

T1 tiếp tục CAS với A và B cũ. Vì đầu ngăn xếp lại đúng cùng nút A, CAS có thể đưa `head` về B, dù B đã bị lấy ra. T1 đã dùng một liên kết cũ để cập nhật cấu trúc mới.

Ví dụ cho thấy vai trò của **tái sử dụng nút** và **dữ liệu đi kèm ảnh chụp cũ**. Nó không phải lời khẳng định mọi ngăn xếp dùng CAS đều có lỗi này. Cách cấp phát nút, tính bất biến của liên kết và quy tắc đưa nút trở lại quyết định liệu lịch thực thi nguy hiểm có khả thi hay không.

Trong Java, bộ thu gom rác (garbage collector, GC) không tự giải quyết tình huống này. GC quản lý vòng đời bộ nhớ; nó không cấm ứng dụng đưa lại cùng một đối tượng còn sống vào cấu trúc. Ngược lại, hai đối tượng mới chỉ tình cờ có nội dung bằng nhau không tạo thành cùng tham chiếu A đối với `==`.

## 4. Chạy thử: tham chiếu giống nhau nhưng phiên bản đã khác

Chương trình sau dùng hai luồng. Luồng chính đọc trước; luồng `other` hoàn tất A → B → A; sau `join()`, luồng chính mới thử cập nhật. Cách sắp thứ tự này tái hiện đúng khoảng thời gian nguy hiểm, không phụ thuộc `sleep()` hay may rủi của bộ lập lịch.

Phần thứ nhất chỉ giữ tham chiếu. Phần thứ hai giữ tham chiếu kèm dấu phiên bản (stamp). Các A, B, C là những đối tượng tạo riêng để quan sát đồng nhất tham chiếu rõ ràng.

Tệp `AbaReferenceDemo.java`, chạy với JDK 17 trở lên:

```java
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicStampedReference;

public class AbaReferenceDemo {
    private static void plainAba() throws InterruptedException {
        Object a = new Object();
        Object b = new Object();
        Object c = new Object();
        AtomicReference<Object> reference = new AtomicReference<>(a);

        // Main has already observed A before the other thread changes it.
        Object observed = reference.get();

        Thread other = new Thread(() -> {
            if (!reference.compareAndSet(a, b)
                    || !reference.compareAndSet(b, a)) {
                throw new AssertionError("Unexpected concurrent writer");
            }
        });
        other.start();
        other.join();

        System.out.println("plain.sameReference=" + (reference.get() == observed));
        boolean accepted = reference.compareAndSet(observed, c);
        System.out.println("plain.staleCas=" + accepted);
        System.out.println("plain.isC=" + (reference.get() == c));
    }

    private static void stampedAba() throws InterruptedException {
        Object a = new Object();
        Object b = new Object();
        Object c = new Object();
        AtomicStampedReference<Object> reference =
                new AtomicStampedReference<>(a, 0);

        int[] observedStamp = new int[1];
        Object observed = reference.get(observedStamp);

        Thread other = new Thread(() -> {
            if (!reference.compareAndSet(a, b, 0, 1)
                    || !reference.compareAndSet(b, a, 1, 2)) {
                throw new AssertionError("Unexpected concurrent writer");
            }
        });
        other.start();
        other.join();

        int[] currentStamp = new int[1];
        Object current = reference.get(currentStamp);
        System.out.println("stamped.sameReference=" + (current == observed));
        System.out.println("stamped.observedStamp=" + observedStamp[0]);
        System.out.println("stamped.currentStamp=" + currentStamp[0]);
        boolean accepted = reference.compareAndSet(
                observed, c, observedStamp[0], observedStamp[0] + 1);
        System.out.println("stamped.staleCas=" + accepted);
        System.out.println("stamped.isA=" + (reference.getReference() == a));
    }

    public static void main(String[] args) throws InterruptedException {
        plainAba();
        stampedAba();
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 AbaReferenceDemo.java
java AbaReferenceDemo
```

Kết quả:

```text
plain.sameReference=true
plain.staleCas=true
plain.isC=true
stamped.sameReference=true
stamped.observedStamp=0
stamped.currentStamp=2
stamped.staleCas=false
stamped.isA=true
```

Ở phần `plain`, `staleCas=true` cho biết cập nhật dùng ảnh chụp trước hai lần thay đổi vẫn được chấp nhận. Chương trình này chỉ chứng minh khả năng chấp nhận đó; nó chưa mô hình hóa một lỗi nghiệp vụ hay ngăn xếp hoàn chỉnh.

Ở phần `stamped`, tham chiếu vẫn là A nhưng cặp trạng thái đã chuyển như sau:

```text
(A, 0) → (B, 1) → (A, 2)
```

T1 kỳ vọng `(A, 0)`, trong khi hiện tại là `(A, 2)`, nên CAS thất bại. `join()` bảo đảm luồng `other` đã xong trước các phép kiểm tra; kết quả thất bại đến từ dấu phiên bản khác nhau, không phải vì T1 chưa nhìn thấy cập nhật.

## 5. Dùng AtomicStampedReference theo một giao thức thống nhất

`AtomicStampedReference<V>` giữ cặp tham chiếu và số nguyên. `get(int[])` đọc một cặp nhất quán; `compareAndSet(expectedReference, newReference, expectedStamp, newStamp)` kiểm tra cả tham chiếu lẫn dấu rồi cập nhật cả hai nguyên tử. Xem [hợp đồng AtomicStampedReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html).

Áp dụng vào bài toán có yêu cầu nhận biết thay đổi trung gian:

- Xác định những thay đổi nào làm quyết định cũ hết hiệu lực.
- Mỗi thay đổi đó phải đi qua cùng giao thức cập nhật cặp tham chiếu và phiên bản.
- Đọc tham chiếu và phiên bản thành một ảnh chụp; giữ nguyên cặp kỳ vọng trong lúc tính.
- Nếu CAS thất bại, đọc lại trạng thái rồi tính lại quyết định phù hợp.

Hai lỗi dễ mắc:

**Đọc rời hai nửa của ảnh chụp.** Đoạn sau không bảo đảm hai giá trị thuộc cùng một lần quan sát:

```java
// Mã minh họa cách đọc không tạo ảnh chụp nguyên tử của cả cặp.
Object observed = reference.getReference();
int version = reference.getStamp();
```

Một luồng khác có thể cập nhật giữa hai lời gọi. Dùng `get(holder)` khi cần cặp nhất quán, như chương trình phía trên.

**Mượn phiên bản mới để hợp thức hóa quyết định cũ.** Sau khi phát hiện có thay đổi, chỉ đọc `getStamp()` mới rồi CAS lại với kết quả tính từ dữ liệu cũ sẽ làm mất ý nghĩa kiểm tra phiên bản. Cần tính lại từ ảnh chụp mới khi kết quả phụ thuộc trạng thái đã thay đổi.

Dấu phiên bản không tự tăng. Lớp nhận `newStamp` do chương trình cung cấp. Nếu đường cập nhật A → B → A giữ nguyên dấu, đặt lại dấu cũ hoặc bỏ qua việc đánh dấu một thay đổi quan trọng, T1 vẫn có thể bị đánh lừa.

Dấu cũng có miền hữu hạn vì là `int`. Quy tắc tăng đều có thể quay vòng sau đủ nhiều lần cập nhật. Nếu cùng tham chiếu và cùng dấu xuất hiện trở lại trong thời gian một ảnh chụp cũ còn được dùng, cặp đó lại không phân biệt được lịch sử. Phải xét giới hạn số lần cập nhật, thời gian giữ ảnh chụp và quy tắc tái sử dụng theo bài toán; không coi dấu `int` là bằng chứng tuyệt đối cho mọi khoảng thời gian.

## 6. Những lựa chọn thiết kế khác

### 6.1. Xuất bản một đối tượng trạng thái mới cho mỗi lần cập nhật

Nếu dữ liệu phù hợp, có thể dùng `AtomicReference<State>` và tạo một đối tượng trạng thái bất biến mới sau mỗi thay đổi. Đây là phác thảo, không phải chương trình độc lập:

```java
record State(int balance) {}

AtomicReference<State> state = new AtomicReference<>(new State(100));

for (;;) {
    State before = state.get();
    State after = new State(before.balance() + 10);
    if (state.compareAndSet(before, after)) {
        break;
    }
}
```

Nếu mọi đường cập nhật luôn xuất bản đối tượng mới và không đưa lại đối tượng trạng thái cũ, giá trị `balance` có thể quay về 100 nhưng tham chiếu trạng thái không quay về đối tượng ban đầu. CAS trên tham chiếu sẽ phân biệt được hai lần xuất bản.

Đây là một **bất biến thiết kế phải được duy trì trên mọi đường ghi**. Nếu mã khác vẫn `set(oldState)`, tái sử dụng đối tượng cũ hoặc sửa dữ liệu khả biến ẩn phía trong trạng thái, lập luận không còn đúng. `record` chỉ làm các trường thành phần là `final`; nếu thành phần trỏ tới một đối tượng khả biến thì nó không tự tạo tính bất biến sâu. Ví dụ dùng thành phần `int` để tránh vấn đề đó.

### 6.2. Bảo vệ toàn bộ giao dịch bằng khóa

Nếu một thao tác phải giữ nhất quán nhiều liên kết hoặc nhiều điều kiện, khóa có thể giúp diễn đạt yêu cầu dễ kiểm tra hơn:

```java
// Mã minh họa: mọi đường truy cập cấu trúc phải theo cùng giao thức khóa.
synchronized (lock) {
    // Đọc trạng thái, kiểm tra điều kiện và cập nhật liên quan trong vùng này.
}
```

Chỉ khóa đoạn cuối CAS trong khi các luồng khác vẫn sửa dữ liệu ngoài khóa không bảo vệ được toàn bộ quyết định. Khóa có ích khi mọi bên cùng tuân thủ phạm vi bảo vệ đã xác định.

### 6.3. Không coi một bit đánh dấu là bộ đếm phiên bản tổng quát

`AtomicMarkableReference` gắn một dấu `boolean` với tham chiếu và có thể cập nhật cả cặp nguyên tử. Dấu này thường biểu diễn trạng thái như “đã xóa về mặt logic”. Xem [AtomicMarkableReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicMarkableReference.html).

Một bit có thể quay từ `false → true → false`. Nếu tham chiếu cũng quay về A, cặp `(A, false)` có thể xuất hiện lại. Vì vậy lớp này không thay thế bộ đếm lịch sử một cách tổng quát. Nó phù hợp khi thuật toán có quy tắc riêng cho trạng thái đánh dấu, chẳng hạn đánh dấu xóa không bị đảo lại đối với cùng nút.

## 7. Phân biệt ABA với các lỗi gần giống

| Hiện tượng | Vấn đề thực sự | Chỉ CAS tham chiếu có đủ không? |
| --- | --- | --- |
| A → B và vẫn đang ở B | Tham chiếu đã khác giá trị kỳ vọng | CAS với A thất bại |
| A → B → cùng A | Tham chiếu quay về trước khi kiểm tra | Có thể cần phiên bản nếu lịch sử quan trọng |
| Hai đối tượng khác nhau có `equals()` trả về `true` | Nội dung bằng nhau, đồng nhất khác nhau | CAS tham chiếu vẫn phân biệt bằng `==` |
| Tham chiếu vẫn là A nhưng trường của A bị sửa | Trạng thái bên trong đối tượng đổi | AtomicReference không tự bảo vệ các trường đó |
| Phiên bản đặt ở biến nguyên tử riêng | Hai biến được cập nhật riêng, không thành một cặp nguyên tử | Cần thiết kế giao thức cho toàn bộ trạng thái |

Đặc biệt, `AtomicReference<MutableObject>` chỉ làm các thao tác trên **ô chứa tham chiếu** nguyên tử. Nếu trường của đối tượng thay đổi mà không thay phiên bản, một CAS thành công không chứng minh những trường đó còn giống lúc đọc.

Dùng `volatile` giúp giải quyết yêu cầu quan sát và thứ tự theo mô hình bộ nhớ, nhưng không tự ghi lại chuỗi A → B → A. Tăng số lần thử CAS cũng không sửa được điều kiện so sánh thiếu thông tin: nếu kỳ vọng vẫn khớp, CAS không có lý do để từ chối.

## 8. Thực hành kiểm tra một thuật toán dùng CAS

Khi đọc hoặc thiết kế thuật toán, hãy trả lời theo thứ tự:

1. Giá trị kỳ vọng đang biểu diễn **giá trị hiện tại**, **đồng nhất đối tượng** hay **một phiên bản của toàn bộ trạng thái**?
2. Kết quả chuẩn bị ghi có phụ thuộc liên kết hoặc trường nào đọc trước đó không?
3. Cùng đối tượng có thể bị lấy ra rồi đưa lại, hoặc trạng thái có thể quay về giá trị cũ không?
4. Mỗi thay đổi làm kết quả tính cũ hết hiệu lực có được phản ánh trong điều kiện CAS không?
5. Khi CAS thất bại, chương trình có đọc và tính lại mọi dữ liệu phụ thuộc không?

Bài tập:

- Trong `stampedAba()`, đổi hai lần cập nhật thành `(A, 0) → (B, 0) → (A, 0)`. Dự đoán rồi chạy: CAS cũ sẽ được chấp nhận vì chương trình đã bỏ dấu hiệu của hai thay đổi.
- Trong `plainAba()`, sau A → B hãy đưa một `new Object()` vào thay vì đưa chính A trở lại. Dự đoán: CAS kỳ vọng A thất bại vì đồng nhất tham chiếu khác.
- Với ví dụ ngăn xếp, chỉ ra dữ liệu nào đã hết hiệu lực: không chỉ ảnh chụp đầu A, mà cả liên kết kế tiếp B được T1 giữ từ cấu trúc trước đó.

Kỹ năng quan trọng là xác định **điều gì phải còn đúng khi cập nhật**, rồi chọn cách biểu diễn trạng thái để thao tác nguyên tử kiểm tra được điều đó.
