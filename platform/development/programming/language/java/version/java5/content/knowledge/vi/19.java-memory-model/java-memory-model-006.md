# Giới hạn của volatile với thao tác đọc sửa ghi

## Khái niệm: một biểu thức ngắn có thể gồm nhiều thao tác

`volatile` cung cấp ngữ nghĩa đồng bộ hóa cho các lần đọc và ghi field, nhưng không tự biến một chuỗi **đọc–sửa–ghi (read-modify-write)** thành một thao tác nguyên tử.

Ví dụ:

```java
volatile int count;

void increment() {
    count++;
}
```

Đây là mảnh khai báo minh họa, chưa phải chương trình độc lập.

`count++` không chỉ là “ghi count”. Về mặt phân tích đồng thời, nó cần lấy giá trị hiện tại, tính giá trị cộng một rồi ghi lại. Một luồng khác có thể tham gia giữa các bước đó.

Điều cần phân biệt:

- **Từng truy cập nguyên tử:** một lần đọc hoặc ghi không bị chia thành các phần giá trị quan sát được.
- **Toàn bộ cập nhật nguyên tử:** cả việc đọc giá trị cũ và thay bằng giá trị mới có một điểm thực hiện thống nhất, không làm mất cập nhật của luồng khác.

`volatile` không hứa điều thứ hai cho `++`, `--`, `+=` hoặc các chuỗi tự viết gồm đọc rồi gán.

Quy tắc này vẫn áp dụng trong Java hiện đại. Ví dụ của bài chạy trên JDK 17 trở lên.

## Vì sao thấy dữ liệu mới không đồng nghĩa tăng đúng số lần?

Khả năng quan sát dữ liệu và khả năng ngăn các luồng xen kẽ là hai yêu cầu khác nhau.

Với count ban đầu bằng 0, có thể có lịch:

| Bước | Luồng A | Luồng B | Giá trị chung |
| --- | --- | --- | --- |
| 1 | Đọc count được 0 | | 0 |
| 2 | | Đọc count được 0 | 0 |
| 3 | Tính 0 + 1 | | 0 |
| 4 | | Tính 0 + 1 | 0 |
| 5 | Ghi 1 | | 1 |
| 6 | | Ghi 1 | 1 |

Cả hai luồng đều đã làm một lần tăng theo mã nguồn, nhưng kết quả chung chỉ là 1.

Không nhất thiết có lần đọc nào “bị cũ do cache” trong lịch này. Luồng B đọc 0 ở thời điểm chưa có luồng nào ghi 1. Sau đó mỗi luồng ghi kết quả tính từ bản đã đọc của chính nó.

Đây là **mất cập nhật (lost update)**. Giá trị do một luồng tạo ra bị luồng khác ghi đè bằng kết quả không tính đến cập nhật đó.

Các lần đọc/ghi volatile vẫn có thể tuân thủ đầy đủ JMM trong khi toàn bộ thuật toán cập nhật bị sai. Xem ngữ nghĩa đồng bộ hóa tại [JLS §17.4.5](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.5).

## Không nhầm với kiểu kết quả của ++

`count++` trả giá trị trước khi tăng cho biểu thức bao ngoài; `++count` trả giá trị sau khi tăng. Khác biệt đó không làm một trong hai trở thành cập nhật nguyên tử khi count là volatile.

Tương tự:

```java
count += 1;
count = count + 1;
```

đều có phần đọc giá trị chung rồi ghi giá trị mới. Cú pháp ngắn hơn không tự tạo khóa hoặc cơ chế so sánh-và-đổi.

Mô hình “đọc, tính, ghi” trong bài dùng để lý giải lịch xen kẽ. Nó không bắt buộc JVM phải dịch mỗi biểu thức thành đúng ba lệnh máy cụ thể; dù triển khai tối ưu ra sao, Java cũng không cấp bảo đảm cập nhật nguyên tử cho các biểu thức này chỉ nhờ volatile.

Định nghĩa toán tử tăng nằm tại [JLS §15.14.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.14.2).

## Chương trình đầy đủ: tạo lịch mất cập nhật một cách có chủ đích

Một thí nghiệm dùng trực tiếp hai luồng tăng rất nhiều lần có thể tình cờ cho đúng tổng ở một lượt chạy. Điều đó làm người học khó quan sát nguyên nhân.

Ví dụ dưới đây tách bước đọc và ghi, dùng `Phaser` để bảo đảm cả hai luồng đã đọc giá trị 0 trước khi luồng nào ghi giá trị mới. Nhờ đó, lịch mất cập nhật được tạo có chủ đích.

Đây là phép mô phỏng rõ ràng các bước của một cập nhật ghép, không phải tuyên bố mọi lượt chạy `count++` đều chắc chắn cho cùng một kết quả sai.

Lưu thành `VolatileReadModifyWriteDemo.java`:

```java
import java.util.concurrent.Phaser;
import java.util.concurrent.atomic.AtomicInteger;

public class VolatileReadModifyWriteDemo {
    static final class SplitCounter {
        volatile int value;

        void incrementWithForcedInterleaving(Phaser afterRead) {
            int observed = value;
            afterRead.arriveAndAwaitAdvance();
            value = observed + 1;
        }
    }

    static final class LockedCounter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    static void runPair(Runnable action) throws InterruptedException {
        Thread first = new Thread(action);
        Thread second = new Thread(action);
        first.start();
        second.start();
        first.join();
        second.join();
    }

    public static void main(String[] args) throws InterruptedException {
        SplitCounter split = new SplitCounter();
        Phaser afterRead = new Phaser(2);
        runPair(() -> split.incrementWithForcedInterleaving(afterRead));
        System.out.println("split.volatile=" + split.value);

        LockedCounter locked = new LockedCounter();
        runPair(locked::increment);
        System.out.println("locked=" + locked.get());

        AtomicInteger atomic = new AtomicInteger();
        runPair(atomic::incrementAndGet);
        System.out.println("atomic=" + atomic.get());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 VolatileReadModifyWriteDemo.java
java VolatileReadModifyWriteDemo
```

Kết quả:

```text
split.volatile=1
locked=2
atomic=2
```

## Giải thích vai trò của từng phần

### SplitCounter: volatile không giữ cả khoảng đọc–ghi

Trong `incrementWithForcedInterleaving`:

1. Mỗi luồng đọc `value` vào biến cục bộ `observed`.
2. Cả hai chờ tại điểm đồng bộ sau khi đọc.
3. Sau khi cùng tới điểm đó, mỗi luồng ghi `observed + 1`.

Lúc khởi đầu value là 0 và chưa luồng nào ghi trước hàng rào, nên cả hai observed đều bằng 0. Sau đó cả hai đều ghi 1.

Một lần đọc volatile về sau không thể tự cập nhật lại biến cục bộ `observed` đã được lấy từ trước. `volatile` không làm phép tính dựa trên một bản chụp cũ tự tính lại.

### Phaser là dụng cụ tạo lịch, không phải vùng loại trừ lẫn nhau

`Phaser(2)` có hai bên tham gia. `arriveAndAwaitAdvance()` giữ các bên ở điểm đó cho đến khi cả hai đã tới.

Bản thân Phaser có ngữ nghĩa đồng bộ hóa. Nhưng việc đồng bộ tại **giữa** bước đọc và bước ghi không biến cả đoạn bao quanh thành một cập nhật nguyên tử. Trong ví dụ, nó được dùng chính để làm hai luồng đọc cùng giá trị trước khi ghi.

Không đặt một hàng rào như vậy vào bên trong một phương thức đã khóa rồi chờ hai luồng cùng tới: luồng thứ nhất có thể giữ khóa trong khi luồng thứ hai không thể vào để đến hàng rào. Phần có khóa của ví dụ chỉ thực hiện phép tăng, không dùng Phaser bên trong.

Xem API [Phaser](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Phaser.html).

### runPair chỉ điều phối thí nghiệm

`runPair` khởi động hai luồng với cùng tác vụ và gọi `join` để main đợi chúng hoàn tất trước khi in kết quả.

Việc đợi hoàn tất không sửa những lần tăng đã bị mất. Nếu hai luồng đã cùng ghi 1, `join` không tự bổ sung một lần tăng còn thiếu.

Lịch minh họa không dùng `sleep` hoặc trông chờ luồng nào chạy trước một số mili giây cố định.

## Cách sửa 1: giữ toàn bộ thao tác trong cùng một khóa

`LockedCounter.increment()` là phương thức `synchronized`. Hai lời gọi trên cùng đối tượng dùng cùng monitor, nên không thể cùng thực hiện đoạn tăng vào một thời điểm.

Luồng sau phải đọc giá trị đã được luồng trước cập nhật trong hợp đồng đồng bộ hóa đó. Hai lần tăng từ 0 cho kết quả 2.

Điều cần bảo vệ là **toàn bộ thao tác**:

```java
synchronized void increment() {
    value++;
}
```

Nếu chỉ khóa riêng từng bước:

```java
// Mã giả minh họa cách chia khóa chưa đủ:
int before = synchronizedRead();
synchronizedWrite(before + 1);
```

thì vẫn có khoảng giữa đọc và ghi để luồng khác xen vào. Mỗi hàm có khóa không đồng nghĩa hai lời gọi kết hợp thành một thao tác nguyên tử.

Cần dùng chung quy tắc khóa cho mọi đường truy cập có thể làm thay đổi bất biến. Một nơi dùng khóa còn nơi khác tự ghi trực tiếp vào field có thể phá vỡ lập luận.

Trong ví dụ khóa, field `value` không cần volatile vì các thao tác liên quan được bảo vệ bằng monitor của cùng đối tượng. `get()` cũng dùng synchronized để giữ một giao diện truy cập nhất quán.

## Cách sửa 2: dùng thao tác cập nhật nguyên tử phù hợp

`AtomicInteger.incrementAndGet()` thực hiện việc tăng nguyên tử. Hai luồng mỗi luồng gọi một lần từ 0 cho kết quả 2.

Một số thao tác cần phân biệt:

| Thao tác | Ý nghĩa |
| --- | --- |
| `get()` | Đọc giá trị theo ngữ nghĩa API |
| `set(value)` | Ghi giá trị theo ngữ nghĩa API |
| `incrementAndGet()` | Tăng nguyên tử, trả giá trị mới |
| `getAndIncrement()` | Tăng nguyên tử, trả giá trị cũ |
| `addAndGet(delta)` | Cộng nguyên tử, trả giá trị mới |
| `compareAndSet(expected, update)` | Chỉ đổi nếu giá trị hiện tại khớp expected, như một thao tác nguyên tử |

Không phải cứ chuyển field sang `AtomicInteger` là mọi chuỗi dùng nó đều nguyên tử. Cách sau vẫn sai nếu nhiều luồng cần cộng dồn:

```java
// Mảnh minh họa cần tránh cho phép tăng đồng thời:
counter.set(counter.get() + 1);
```

`get` và `set` là hai thao tác riêng. Khoảng giữa chúng vẫn cho phép mất cập nhật. Cần gọi đúng API cập nhật ghép, như `incrementAndGet`.

Hợp đồng các thao tác có trong [AtomicInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html).

Tính nguyên tử cũng không tự ngăn tràn số `int` hoặc làm một giá trị âm trở nên hợp lệ về nghiệp vụ. Những yêu cầu miền giá trị cần được thiết kế riêng.

## Kiểm tra-rồi-hành động cũng là thao tác ghép

Ví dụ:

```java
// Mảnh minh họa có thể sai khi nhiều luồng tranh cùng một chỗ:
if (remaining > 0) {
    remaining--;
    return true;
}
return false;
```

Nếu `remaining` là volatile và đang bằng 1, hai luồng có thể cùng thấy điều kiện đúng trước khi một luồng cập nhật. Chỉ khả năng quan sát mới không bảo đảm chỉ một lời gọi được chấp nhận.

Đây là cùng một vấn đề ở mức quy tắc:

1. Đọc trạng thái.
2. Quyết định dựa trên trạng thái.
3. Thay đổi trạng thái.

Có thể bảo vệ toàn bộ ba bước bằng khóa. Với một biến trạng thái đơn giản, cũng có thể thiết kế vòng lặp so sánh-và-đổi (compare-and-set, CAS).

Ví dụ dưới đây là mảnh thành viên của một lớp, chưa phải chương trình độc lập; nó giả sử `remaining` bắt đầu không âm và mọi cập nhật phải tuân thủ giao thức này:

```java
private final AtomicInteger remaining = new AtomicInteger(1);

boolean tryAcquire() {
    for (;;) {
        int current = remaining.get();
        if (current == 0) {
            return false;
        }
        if (remaining.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
```

Nếu một luồng đã đổi giá trị kể từ lần đọc, CAS thất bại và luồng đang xét phải đọc lại rồi quyết định lại. Nó không tự ghi kết quả được tính từ trạng thái không còn khớp.

Ví dụ CAS này chỉ xử lý một biến trạng thái và một quyết định cụ thể. Nó không phải giao dịch cho mọi tác động bên ngoài có thể gắn với việc “nhận chỗ”.

## Không đặt tác động bên ngoài vào một bước có thể thử lại

Một vòng CAS hoặc một API cập nhật theo hàm có thể phải tính lại khi có tranh chấp.

Nếu việc tính giá trị mới đồng thời gửi thông báo, gọi dịch vụ hoặc ghi một kết quả bên ngoài, việc thử lại có thể tạo tác động nhiều lần.

Cần tách việc tính trạng thái mới khỏi các tác động không được lặp tùy ý, và xác định rõ cách hệ thống hoàn tất thao tác sau khi cập nhật thành công.

Đặc biệt, các hàm truyền vào `AtomicInteger.updateAndGet` được yêu cầu không có tác động phụ vì có thể bị áp dụng lại khi tranh chấp. Chọn atomic cho một field không tự mang lại ngữ nghĩa “thực hiện đúng một lần” cho cả một nghiệp vụ.

Nếu yêu cầu gồm nhiều bước có lỗi hoặc nhiều tài nguyên, có thể cần một thiết kế phối hợp rộng hơn thay vì chỉ một CAS.

## Nhiều field volatile không giữ một bất biến chung

Giả sử hai field biểu diễn giới hạn dưới và giới hạn trên. Cả hai đều volatile không tự bảo đảm người đọc luôn nhận một cặp thuộc cùng một phiên bản cập nhật.

Tương tự, hai `AtomicInteger` độc lập không tự tạo một giao dịch giữa hai giá trị. Từng phép cập nhật có thể đúng, còn bất biến tổng hợp vẫn bị phá vỡ trong lúc xen kẽ.

Các hướng thiết kế có thể là:

- Dùng một khóa chung để bảo vệ cả trạng thái cần thay đổi cùng nhau.
- Gói trạng thái vào một đối tượng không sửa sau công bố và cập nhật một tham chiếu nguyên tử theo giao thức phù hợp.
- Dùng một cấu trúc đồng thời đã cung cấp đúng thao tác ghép cần thiết.

Phải xác định **đơn vị nguyên tử** theo yêu cầu thật sự. Nếu đơn vị cần giữ là một cặp giá trị hoặc một quyết định nhiều bước, bảo vệ riêng một lần ghi là chưa đủ.

## Khi nào phép cập nhật trên volatile có thể không mất cập nhật?

Không nên biến bài học thành quy tắc thiếu điều kiện rằng “mọi `++` trên volatile luôn cho kết quả sai”.

Nếu chỉ có đúng một luồng thực hiện mọi phép tăng và không có tác nhân khác sửa field, sẽ không có hai luồng cùng đọc-sửa-ghi field đó để tạo lịch mất cập nhật như trên. Các luồng khác có thể chỉ quan sát giá trị theo hợp đồng volatile.

Nhưng khi thiết kế dựa trên điều kiện một luồng ghi, cần giữ điều kiện ấy rõ ràng:

- Không có đường khởi tạo lại hoặc gán mới từ luồng khác.
- Không thêm một tác vụ mới cùng tăng field mà quên đổi cơ chế.
- Không suy ra một ảnh chụp nhất quán cho các field khác chỉ từ bộ đếm này.

Nếu yêu cầu đã là nhiều luồng cùng cập nhật, phải dùng thao tác nguyên tử hoặc loại trừ lẫn nhau thích hợp. Đừng dựa vào việc tác vụ “thường chạy nối nhau” trên máy phát triển.

## Vì sao một lượt thử ra đúng tổng chưa chứng minh đúng?

Chương trình dùng trực tiếp `count++` nhiều lần có thể:

- Chưa tạo tranh chấp đáng kể trong một lượt chạy.
- Được lập lịch theo cách gần như tuần tự.
- Tình cờ cho tổng đúng dù thuật toán vẫn cho phép lịch sai.
- Thay đổi hành vi quan sát khi thêm log hoặc đổi môi trường.

Không thể suy ra bảo đảm nguyên tử từ một số lần chạy ra kết quả mong muốn.

Ngược lại, thí nghiệm có lịch cố định trong bài cho thấy cụ thể một cập nhật ghép có thể thất bại mà từng lần truy cập volatile vẫn hợp lệ. Lập luận đúng cần nằm ở đơn vị thao tác và cơ chế đồng bộ hóa, không chỉ trong số lần thử.

## Chọn cơ chế theo yêu cầu

| Yêu cầu | Cơ chế cần cân nhắc |
| --- | --- |
| Một luồng ghi cờ, luồng khác đọc trạng thái | Volatile có thể phù hợp |
| Công bố một giá trị/tham chiếu theo giao thức rõ ràng | Volatile có thể phù hợp |
| Nhiều luồng cộng vào một biến | API tăng/cộng nguyên tử hoặc khóa |
| Kiểm tra điều kiện rồi đổi một trạng thái | CAS đúng giao thức hoặc khóa toàn thao tác |
| Giữ bất biến giữa nhiều field | Khóa chung hoặc mô hình trạng thái nguyên tử phù hợp |
| Thực hiện cập nhật kèm tác động bên ngoài | Thiết kế phối hợp; không coi một field atomic là đủ |

Không chọn khóa chỉ vì “chắc hơn” hoặc chọn atomic chỉ vì “không khóa”. Trước tiên cần biết đơn vị thao tác nào phải không bị xen kẽ, rồi chọn công cụ diễn đạt được hợp đồng đó.

## Lỗi phổ biến và cách phát hiện

| Hiểu nhầm | Điều cần kiểm tra |
| --- | --- |
| Volatile mới nhất nên không thể mất cập nhật | Hai luồng có thể cùng đọc trước khi có lần ghi mới |
| Một dòng Java là một thao tác nguyên tử | Tách các lần truy cập và bước quyết định |
| ++count an toàn hơn count++ về đồng thời | Cả hai vẫn là cập nhật ghép |
| Atomic get rồi set là tăng nguyên tử | Dùng một thao tác cập nhật ghép đúng nghĩa |
| Có khóa cho từng hàm đọc và ghi là đủ | Khoảng giữa hai lời gọi còn cho phép xen kẽ |
| Có hai biến atomic là có giao dịch hai biến | Xác định bất biến tổng hợp |
| CAS thành công nghĩa là mọi tác động chỉ chạy một lần | Xem bước tính lại và tác động bên ngoài |
| Test ra đúng tổng là chứng minh an toàn | Cần lập luận cơ chế và kiểm chứng lịch có ý nghĩa |

## Thực hành kiểm chứng

1. Chạy chương trình và giải thích vì sao hai observed đều bằng 0 trước khi có lần ghi đầu tiên.
2. Bỏ volatile khỏi `SplitCounter.value` trong một bản sao thử nghiệm. Thí nghiệm có Phaser và join vẫn có các quan hệ đồng bộ hóa riêng; giải thích vì sao không được dùng biến thể đó để kết luận “volatile luôn không cần”.
3. Viết thêm một bộ đếm volatile dùng trực tiếp `value++` ở nhiều luồng. Phân biệt việc quan sát mất cập nhật với yêu cầu sai rằng mỗi lượt đều phải thất bại.
4. Thay phép tăng nguyên tử bằng `set(get() + 1)` trong một thí nghiệm có lịch đọc-trước-ghi để thấy vì sao ghép hai API không tự nguyên tử.
5. Thiết kế một trạng thái chỉ còn một quyền nhận, rồi so sánh cách khóa cả thao tác với vòng CAS.
6. Với một bất biến hai field, chỉ ra vì sao bảo vệ riêng từng lần ghi vẫn chưa phải một cam kết cập nhật chung.

Điều cần nắm là **volatile bảo đảm từng truy cập theo mô hình bộ nhớ; muốn đọc–sửa–ghi đúng khi nhiều luồng cập nhật, phải bảo vệ toàn bộ thao tác theo đơn vị mà thiết kế yêu cầu**.
