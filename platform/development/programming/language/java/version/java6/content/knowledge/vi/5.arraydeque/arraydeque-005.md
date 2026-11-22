# Iterator fail-fast và giới hạn phát hiện sửa đổi

## 1. Fail-fast dùng để phát hiện lỗi sử dụng

`Iterator<E>` giữ trạng thái để duyệt một cấu trúc: phần tử kế tiếp ở đâu, còn gì để duyệt và phần tử vừa trả về là gì. Nếu cấu trúc bị thêm/xóa trong lúc bộ duyệt đang hoạt động, trạng thái duyệt có thể không còn phù hợp.

Bộ duyệt của `ArrayDeque` có đặc tính **fail-fast**: khi phát hiện sửa đổi không phù hợp, nó có thể báo `ConcurrentModificationException` để làm lộ lỗi sớm. Việc phát hiện theo nguyên tắc cố gắng phát hiện (best effort), không phải bảo đảm bắt được mọi sửa đổi. [Hợp đồng ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

Cần giữ hai ý tách biệt:

- Nếu có ngoại lệ, cần tìm thao tác đã làm thay đổi cấu trúc trong khi bộ duyệt còn được sử dụng.
- Nếu không có ngoại lệ, chưa thể kết luận cách duyệt là hợp lệ hoặc chương trình an toàn khi dùng nhiều luồng.

**Fail-fast là công cụ phát hiện lỗi; nó không phải khóa, giao dịch hay cơ chế phục hồi dữ liệu.**

Bài này dùng Java 17+. Các đoạn ngắn là trích đoạn minh họa; chương trình đầy đủ ở phần 6 có cả ví dụ đúng và thí nghiệm cố ý vi phạm hợp đồng để quan sát giới hạn phát hiện.

## 2. “Concurrent” không bắt buộc phải có hai luồng

Một luồng cũng có thể làm thay đổi cấu trúc trong khi đang duyệt:

```java
Deque<String> jobs = new ArrayDeque<>(List.of("A", "B", "C"));
for (String job : jobs) {
    if (job.equals("A")) {
        jobs.removeFirst();
    }
}
```

Đoạn mã trên cố ý minh họa cách sử dụng không phù hợp. Vòng `for-each` dùng một bộ duyệt, còn `jobs.removeFirst()` đi trực tiếp qua Deque để xóa. Bộ duyệt không được điều chỉnh bằng thao tác xóa hợp lệ của chính nó.

Ngoại lệ mang tên `ConcurrentModificationException` không chứng minh đã có luồng khác can thiệp. Tài liệu ngoại lệ nêu rõ một chuỗi lời gọi vi phạm hợp đồng trong cùng một luồng cũng có thể gây ngoại lệ này. [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ConcurrentModificationException.html).

Điều cần tìm là **hai cách truy cập xung đột với nhau**, không chỉ tìm từ khóa tạo luồng:

```text
iterator đang duyệt ArrayDeque
              +
một lời gọi thêm/xóa qua chính Deque hoặc qua một tham chiếu khác
              ↓
trạng thái duyệt có thể mất hiệu lực
              ↓
có thể bị phát hiện bằng ConcurrentModificationException
```

Một biến khác trỏ tới cùng Deque vẫn có thể làm thay đổi cấu trúc đó. Đổi tên biến không tạo ra bản sao.

## 3. Cách xóa được hỗ trợ: Iterator.remove()

Với bộ duyệt do ArrayDeque cung cấp, có thể xóa phần tử vừa được `next()` trả về bằng chính `iterator.remove()`:

```java
Iterator<Integer> iterator = numbers.iterator();
while (iterator.hasNext()) {
    int number = iterator.next();
    if (number % 2 == 0) {
        iterator.remove();
    }
}
```

Đoạn mã giả sử `numbers` là Deque<Integer> đã được tạo và không có nơi khác sửa đồng thời. Đây là thao tác sửa có hợp đồng rõ ràng trong khi duyệt: bộ duyệt xóa phần tử vừa đọc và điều chỉnh trạng thái của nó.

Quy tắc gọi:

1. Phải có một lần `next()` thành công trước khi gọi remove.
2. Với mỗi phần tử vừa được next trả về, chỉ gọi remove một lần.
3. Không thay remove của bộ duyệt bằng `numbers.remove(number)`; đó là một lời gọi qua cấu trúc, dù kết quả mong muốn nhìn có vẻ giống nhau.

Gọi remove trước next hoặc gọi hai lần sau cùng một next gây `IllegalStateException`. Đây là lỗi trình tự gọi, khác `ConcurrentModificationException`. Với Iterator nói chung, remove là thao tác tùy chọn; ArrayDeque hỗ trợ thao tác này. [Hợp đồng Iterator.remove](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html#remove()), [ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

Lưu ý: việc dùng `iterator.remove()` chỉ điều chỉnh **bộ duyệt đó**. Một bộ duyệt thứ hai được tạo trước đó không được biến thành an toàn trước thay đổi chỉ vì bộ duyệt thứ nhất xóa đúng cách.

## 4. Giới hạn phát hiện: hasNext không phải bước xác thực

Một suy luận dễ nhầm:

```text
hasNext() trả true
→ chắc chắn không có sửa đổi
→ next() sẽ an toàn
```

Suy luận này không có cơ sở khi cấu trúc đã bị thay đổi trái hợp đồng. `hasNext()` không được dùng như một khóa hoặc một phép xác nhận tính hợp lệ của toàn bộ dữ liệu.

Mã nguồn OpenJDK 25 cho thấy bộ duyệt ArrayDeque quản lý vị trí và số phần tử còn lại, cùng các kiểm tra tại một số thao tác duyệt. Chẳng hạn, hasNext dựa vào số phần tử còn lại mà bộ duyệt theo dõi; kiểm tra khác nằm ở next hoặc forEachRemaining. Không nên áp mô hình “mọi thao tác đều so sánh một biến modCount” cho mọi bộ duyệt. [Mã nguồn bộ duyệt ArrayDeque](https://github.com/openjdk/jdk/blob/jdk-25-ga/src/java.base/share/classes/java/util/ArrayDeque.java).

Các điểm cần rút ra:

- Sửa đổi có thể được phát hiện ở một lời gọi sau thời điểm sửa.
- Có trường hợp sửa đổi chưa bị phát hiện ở lời gọi đang quan sát.
- Cách phát hiện có thể khác giữa phiên bản, cách tạo Deque, hướng duyệt hoặc phương thức duyệt.
- Không viết kiểm thử nghiệp vụ yêu cầu “bất kỳ sửa đổi ngoài nào cũng phải gây ngoại lệ tại đúng dòng này”.

Một lần chạy không có ngoại lệ chỉ là quan sát của lần chạy đó. Chính hợp đồng best effort đã giới hạn điều có thể suy ra.

## 5. Sửa cấu trúc và sửa trạng thái phần tử

So sánh:

| Thao tác | Điều thay đổi |
|---|---|
| addLast, addFirst, pollFirst, remove, clear | Thành phần hoặc bố trí dữ liệu trong Deque |
| iterator.remove sau next hợp lệ | Xóa phần tử bằng đường thao tác mà bộ duyệt hỗ trợ |
| Gán job.done = true cho đối tượng đang nằm trong Deque | Trạng thái của đối tượng; không tự thêm/xóa phần tử Deque |

Ví dụ một Deque đang giữ tham chiếu tới đối tượng `Job`. Thay đổi `job.done` trong cùng một luồng không tự làm số phần tử hoặc thứ tự tham chiếu của Deque thay đổi. Fail-fast không phải hệ thống giám sát mọi thuộc tính bên trong các đối tượng.

Điều này có hai hệ quả:

- Không được dựa vào fail-fast để phát hiện các thay đổi dữ liệu nghiệp vụ bên trong phần tử.
- Việc thay đổi thuộc tính không sửa cấu trúc vẫn có thể cần một hợp đồng đồng bộ riêng nếu nhiều luồng cùng đọc/ghi đối tượng đó.

Chương trình bên dưới dùng phần tử có thuộc tính thay đổi được để làm rõ ranh giới này và để minh họa sao chép nông.

## 6. Chương trình đầy đủ: cách dùng đúng và thí nghiệm phát hiện

Lưu thành `FailFastLab.java`:

```java
import java.util.ArrayDeque;
import java.util.ConcurrentModificationException;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;

public final class FailFastLab {
    private FailFastLab() {
    }

    private static final class Job {
        private boolean done;
    }

    private static void removeDuringIteration() {
        Deque<Integer> numbers = new ArrayDeque<>(List.of(1, 2, 3, 4, 5));
        Iterator<Integer> iterator = numbers.iterator();
        while (iterator.hasNext()) {
            int value = iterator.next();
            if (value % 2 == 0) {
                iterator.remove();
            }
        }
        System.out.println("filtered=" + numbers);

        Iterator<Integer> check = numbers.iterator();
        try {
            check.remove();
        } catch (IllegalStateException ex) {
            System.out.println("remove before next=" + ex.getClass().getSimpleName());
        }
        check.next();
        check.remove();
        try {
            check.remove();
        } catch (IllegalStateException ex) {
            System.out.println("double remove=" + ex.getClass().getSimpleName());
        }
    }

    private static void observeExternalRemoval() {
        Deque<String> deque = new ArrayDeque<>(List.of("A", "B", "C"));
        Iterator<String> iterator = deque.iterator();
        deque.removeFirst();
        try {
            System.out.println("after removal hasNext=" + iterator.hasNext());
            System.out.println("after removal next=" + iterator.next());
        } catch (ConcurrentModificationException ex) {
            System.out.println("after removal detected=" + ex.getClass().getSimpleName());
        }
    }

    private static void observeExternalAppend() {
        Deque<String> deque = new ArrayDeque<>(16);
        deque.addAll(List.of("A", "B", "C"));
        Iterator<String> iterator = deque.iterator();
        deque.addLast("D");
        try {
            System.out.println("after append next=" + iterator.next());
        } catch (ConcurrentModificationException ex) {
            System.out.println("after append detected=" + ex.getClass().getSimpleName());
        }
    }

    private static void showShallowCopy() {
        Job job = new Job();
        Deque<Job> original = new ArrayDeque<>();
        original.addLast(job);
        Deque<Job> copy = new ArrayDeque<>(original);

        Iterator<Job> iterator = original.iterator();
        job.done = true;
        System.out.println("element state=" + iterator.next().done);
        original.clear();
        System.out.println("copy size=" + copy.size());
        System.out.println("same job=" + (copy.getFirst() == job));
        job.done = false;
        System.out.println("copy sees changed state=" + copy.getFirst().done);
    }

    public static void main(String[] args) {
        removeDuringIteration();
        observeExternalRemoval();
        observeExternalAppend();
        showShallowCopy();
    }
}
```

Biên dịch và chạy:

```shell
javac -Xlint:all -Werror FailFastLab.java
java FailFastLab
```

**Stdout quan sát được trên Amazon Corretto 17.0.15 và Microsoft OpenJDK 21.0.9:**

```text
filtered=[1, 3, 5]
remove before next=IllegalStateException
double remove=IllegalStateException
after removal hasNext=true
after removal detected=ConcurrentModificationException
after append next=A
element state=true
copy size=1
same job=true
copy sees changed state=false
```

Các dòng thuộc `observeExternalRemoval` và `observeExternalAppend` là thí nghiệm vi phạm hợp đồng, **không phải đầu ra bắt buộc cho mọi JDK**. Hai hàm có nhánh in nếu phát hiện ngoại lệ; nền tảng khác có thể quan sát nhánh khác. Phần đúng của chương trình không cần dựa vào kết quả của hai thí nghiệm này.

### 6.1. Bộ duyệt xóa đúng cách

`removeDuringIteration` loại 2 và 4 bằng `iterator.remove()`, để lại `[1, 3, 5]`. Hai phép thử gọi sai remove cho `IllegalStateException`. Chúng cho thấy quy tắc trình tự gọi được kiểm tra riêng với vấn đề sửa đổi bên ngoài.

### 6.2. hasNext vẫn true, next mới phát hiện

`observeExternalRemoval` tạo bộ duyệt, rồi xóa phần tử đầu trực tiếp qua Deque trước khi dùng bộ duyệt. Trên các môi trường đã kiểm tra, hasNext vẫn true, còn next báo ngoại lệ. Điều đó đủ bác bỏ việc dùng hasNext như một bước kiểm tra sửa đổi.

### 6.3. Sửa đổi nhưng một lời gọi next chưa phát hiện

`observeExternalAppend` chuẩn bị dung lượng, tạo bộ duyệt rồi thêm D ở cuối. Trong kết quả quan sát, next vẫn trả A. Đây là ví dụ cho giới hạn phát hiện, không phải mẫu để tiếp tục duyệt sau khi sửa bên ngoài.

Không được biến quan sát này thành quy tắc “thêm cuối luôn an toàn”. Thay đổi chi tiết tạo cấu trúc, lượng dữ liệu hoặc phương thức duyệt có thể thay đổi nơi phát hiện.

### 6.4. Bản sao cấu trúc vẫn chia sẻ đối tượng phần tử

`showShallowCopy` tạo một ArrayDeque mới từ original. Sau khi original bị clear, copy vẫn có một phần tử. Nhưng phần tử đó vẫn là cùng đối tượng `job`; đổi `job.done` khiến copy thấy giá trị mới.

Như vậy, sao chép Deque có thể tách thành phần cấu trúc, nhưng không tự tạo bản chụp sâu của trạng thái từng phần tử.

## 7. Chọn mẫu xử lý theo mục đích

### Xóa có điều kiện ngay khi duyệt

Dùng vòng `while (iterator.hasNext())`, đọc bằng next và xóa bằng chính iterator.remove như chương trình đầy đủ.

Nếu chỉ cần lọc theo một điều kiện, có thể dùng thao tác cấp collection:

```java
numbers.removeIf(number -> number % 2 == 0);
```

Đây là đoạn minh họa một phép lọc độc lập, với `numbers` là ArrayDeque<Integer>. Hàm điều kiện nên chỉ kiểm tra phần tử, không tự thêm/xóa cùng Deque. Không tiếp tục dùng một bộ duyệt cũ đã được tạo trước phép lọc này.

### Lấy hết phần tử để xử lý

Nếu mục tiêu là tiêu thụ công việc, không cần tạo bộ duyệt:

```java
String job;
while ((job = jobs.pollFirst()) != null) {
    System.out.println("process " + job);
}
```

Đoạn minh họa giả sử jobs là ArrayDeque<String>, không có nơi khác sửa thiếu đồng bộ. ArrayDeque cấm phần tử null, nên null từ pollFirst dùng được làm tín hiệu rỗng. Vòng lặp làm thay đổi Deque theo mục tiêu tiêu thụ, không có một iterator riêng bị bỏ lại phía sau.

### Thêm/xóa nhiều bước dựa trên kết quả duyệt

Có thể tách hai pha: duyệt để tính danh sách thay đổi, kết thúc việc dùng bộ duyệt, sau đó mới áp dụng thay đổi. Cần định nghĩa phần tử cần sửa theo danh tính hay theo giá trị, đặc biệt khi có nhiều phần tử bằng nhau.

Nếu cần tiếp tục duyệt dữ liệu cũ trong khi sửa cấu trúc gốc, có thể tạo bản sao cấu trúc rồi duyệt bản sao. Việc tạo bản sao cũng phải diễn ra dưới một điều kiện truy cập an toàn; sao chép trong lúc nguồn đang bị sửa không có đồng bộ không tự tạo ra bản chụp nhất quán.

### Không đặt thao tác sửa vào forEachRemaining

Đừng suy ra rằng vì iterator.remove hợp lệ trong vòng lặp next/remove nên cũng hợp lệ khi đặt vào hàm xử lý của `forEachRemaining`. Hợp đồng Iterator không bảo đảm hành vi khi hàm xử lý sửa cấu trúc, kể cả qua remove, trừ khi lớp triển khai có chính sách riêng được công bố. Nếu cần xóa theo từng phần tử, vòng lặp tường minh giúp giữ đúng trình tự. [Iterator.forEachRemaining](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html#forEachRemaining(java.util.function.Consumer)).

## 8. Fail-fast không thay thế đồng bộ

ArrayDeque không an toàn cho truy cập đồng thời khi thiếu đồng bộ phù hợp. Nếu chọn bảo vệ bằng khóa, mọi nơi đọc/ghi có liên quan phải tuân thủ cùng một quy tắc; chỉ khóa lúc tạo iterator rồi duyệt bên ngoài khóa không bảo vệ toàn bộ lần duyệt.

Tùy yêu cầu, có thể cần một trong các thiết kế:

- Một luồng sở hữu ArrayDeque và các luồng khác gửi yêu cầu tới nó.
- Một khóa chung bảo vệ cả lần duyệt và các thao tác sửa liên quan.
- Một bản sao được tạo nhất quán để xử lý ngoài vùng khóa, với chính sách rõ cho các đối tượng phần tử.
- Một cấu trúc đồng thời có hợp đồng duyệt phù hợp.

Ví dụ, `ConcurrentLinkedDeque` có các thao tác truy cập đồng thời an toàn và bộ duyệt nhất quán yếu (weakly consistent). Điều đó khác hợp đồng fail-fast và không đồng nghĩa một bản chụp nguyên tử của toàn bộ dữ liệu. Đổi cấu trúc cần đánh giá lại yêu cầu về những thay đổi mà người duyệt có thể thấy. [ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html).

Không nên bắt `ConcurrentModificationException` rồi lặp lại vô hạn như một cách “đợi dữ liệu ổn định”. Một số tác dụng của lần duyệt trước có thể đã xảy ra, ví dụ đã ghi log, cộng tổng hoặc gọi xử lý. Ngoại lệ không tự hoàn tác các tác dụng đó; chạy lại thiếu thiết kế có thể xử lý lặp.

## 9. Cách kiểm thử có ý nghĩa

Nên kiểm thử các bảo đảm của mã đúng:

1. Sau khi lọc bằng iterator.remove, các phần tử cần giữ và thứ tự của chúng đúng.
2. Các phần tử cần xử lý không bị bỏ sót hoặc xử lý lặp theo hợp đồng đã chọn.
3. Việc tiêu thụ bằng poll kết thúc ở trạng thái dự kiến.
4. Nếu dùng bản sao, cấu trúc gốc và bản sao thay đổi độc lập đúng mức yêu cầu; tính bất biến của phần tử được đánh giá riêng.
5. Nếu có nhiều luồng, kiểm tra cơ chế sở hữu/đồng bộ và các bất biến nghiệp vụ.

Có thể viết thí nghiệm để quan sát fail-fast trên một phiên bản cụ thể, nhưng không dùng chúng để chứng minh mọi sửa đổi không hợp lệ đều được phát hiện. Không thấy ngoại lệ không phải tiêu chí xác nhận an toàn đồng thời.

Tự thực hành:

- Thay thao tác xóa trong vòng iterator bằng `numbers.remove(value)`. Xác định vì sao đây là cách truy cập khác, dù cả hai đều mong muốn xóa một số chẵn.
- Tạo hai bộ duyệt trước khi xóa bằng một bộ duyệt. Giải thích vì sao bộ duyệt còn lại không nhận được cùng một bảo đảm điều chỉnh trạng thái.
- Thay cách tạo Deque trong thí nghiệm append, rồi ghi nhận kết quả trên JDK đang dùng. Phân biệt quan sát triển khai với hợp đồng API.
- Thay `Job` bằng một kiểu bất biến và xác định vấn đề chia sẻ trạng thái nào được loại bỏ.
- Thiết kế cách duyệt và cập nhật một hàng đợi công việc mà không cần dựa vào việc bắt ConcurrentModificationException.

Điểm cốt lõi khi dùng bộ duyệt ArrayDeque là giữ **một cách sửa có hợp đồng rõ ràng trong suốt lần duyệt**. Fail-fast giúp phát hiện một phần các vi phạm; độ đúng vẫn đến từ quy tắc truy cập mà chương trình thiết lập.
