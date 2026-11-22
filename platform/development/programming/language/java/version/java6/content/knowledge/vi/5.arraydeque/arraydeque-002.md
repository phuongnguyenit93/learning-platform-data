# Dung lượng ban đầu và quá trình mở rộng của ArrayDeque

## 1. Thêm vượt số đã truyền vào constructor có được không?

Có. Với:

```java
ArrayDeque<String> jobs = new ArrayDeque<>(2);
```

Số `2` là yêu cầu về **dung lượng ban đầu**, không phải giới hạn tối đa hai phần tử. Deque mới vẫn rỗng, có `size() == 0`; khi cần chứa thêm dữ liệu, ArrayDeque có thể mở rộng vùng lưu trữ.

Cần phân biệt ba đại lượng:

| Đại lượng | Ý nghĩa |
|---|---|
| Kích thước hiện tại — size | Số phần tử thực sự đang nằm trong Deque |
| Dung lượng ban đầu yêu cầu | Mức chứa ban đầu mà constructor được yêu cầu chuẩn bị |
| Dung lượng lưu trữ nội bộ | Số vị trí trong mảng triển khai; không có phương thức capacity() công khai để đọc |

Nhầm ba đại lượng này dễ dẫn tới hai lỗi: coi constructor là giới hạn hàng đợi, hoặc dùng `size()` để suy ra số ô mảng đã cấp phát.

Bài này dùng Java 17+. Các đoạn ngắn là trích đoạn minh họa; chương trình hoàn chỉnh nằm ở phần 6. Chi tiết triển khai được ghi rõ khi tham chiếu mã nguồn OpenJDK 25, để không biến một cách cài đặt thành hợp đồng cho mọi JDK.

## 2. Hợp đồng của các constructor

| Cách tạo | Trạng thái dữ liệu ban đầu | Điều cần hiểu |
|---|---|---|
| new ArrayDeque<>() | Rỗng | Dung lượng ban đầu đủ chứa 16 phần tử theo tài liệu API |
| new ArrayDeque<>(n) | Rỗng | Với n không âm trong ví dụ thông thường, yêu cầu dung lượng ban đầu đủ chứa ít nhất n phần tử |
| new ArrayDeque<>(collection) | Chứa các phần tử từ collection | Thứ tự ban đầu theo thứ tự bộ duyệt của collection |

Tham số `numElements` là cận dưới của dung lượng ban đầu, không công bố chính xác độ dài mảng bên trong. ArrayDeque không có giới hạn số phần tử do constructor đặt ra; nó tăng vùng chứa khi cần. [Hợp đồng ArrayDeque và constructor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

Điều này tạo ra các hệ quả trực tiếp:

- `new ArrayDeque<>(100)` không chèn sẵn 100 phần tử.
- Thêm phần tử thứ 101 không phải vi phạm một giới hạn 100 do constructor áp đặt.
- Hai đối tượng cùng `size() == 10` có thể đã trải qua các mức sử dụng và cấp phát khác nhau.
- Không thể tính dung lượng nội bộ bằng `deque.toArray().length`; đó là độ dài mảng kết quả chứa các phần tử, không phải cửa sổ xem mảng riêng của Deque.

Nếu cần hàng đợi tối đa 100 công việc, phải chọn một cấu trúc có hợp đồng giới hạn hoặc một chính sách giới hạn được thực hiện đúng tại tầng ứng dụng. Dung lượng khởi tạo không thay thế giới hạn tải.

## 3. Mảng vòng giúp dùng lại chỗ trống thế nào?

### Thứ tự logic và vị trí vật lý

Về mặt sử dụng, Deque là một dãy đầu → cuối. Trong triển khai OpenJDK được tham chiếu, ArrayDeque lưu các tham chiếu trong một mảng vòng, với chỉ số đầu và vị trí thêm ở cuối. Khi chỉ số tới cuối mảng, nó có thể quay về đầu.

Ví dụ **khái niệm**, các ô trống ký hiệu bằng dấu chấm:

```text
chỉ số vật lý:   0   1   2   3   4   5
mảng minh họa:  [E] [F] [.] [.] [C] [D]
                                ↑
                              đầu = C

thứ tự logic:   C → D → E → F
```

Dữ liệu có thể nằm thành hai đoạn trong mảng nhưng vẫn tạo thành một dãy logic liên tục. Sơ đồ dùng số ô tùy ý để giải thích mảng vòng; nó không khẳng định một constructor cụ thể sẽ cấp đúng sáu ô.

Lấy phần tử đầu thường chỉ cần đọc tham chiếu, bỏ tham chiếu tại ô đó và dịch chỉ số đầu. Không cần dồn toàn bộ phần tử còn lại về chỉ số 0 sau mỗi lần lấy.

Điều này giải thích vì sao một chuỗi “thêm ở cuối, lấy ở đầu” có thể tái sử dụng chỗ trống do các phần tử đã lấy ra, thay vì luôn cần mảng mới.

### Khi phải mở rộng

Khi cần thêm vùng chứa, triển khai có thể cấp mảng lớn hơn, sao chép hoặc sắp xếp lại các đoạn tham chiếu, rồi cập nhật vị trí quản lý. Thứ tự đầu → cuối và các đối tượng phần tử được giữ nguyên; việc mở rộng không có nghĩa tạo bản sao sâu của từng đối tượng.

Mã nguồn OpenJDK 25 thể hiện các thành phần `elements`, `head`, `tail` và hàm `grow`. Hệ số tăng, số ô dành riêng và bố trí sau sao chép là chi tiết triển khai. [Mã nguồn ArrayDeque của OpenJDK 25](https://github.com/openjdk/jdk/blob/jdk-25-ga/src/java.base/share/classes/java/util/ArrayDeque.java).

Đừng xây dựng logic ứng dụng dựa trên giả định “mỗi lần luôn tăng gấp đôi”, “độ dài luôn là lũy thừa hai” hoặc “phần tử đầu luôn ở ô số 0”. Hợp đồng API cần dùng ở đây là có thể tăng vùng chứa và bảo toàn hành vi của Deque.

## 4. Vì sao chi phí được gọi là O(1) khấu hao?

Một thao tác thêm không cần mở rộng thường chỉ cập nhật một vài ô và chỉ số. Một thao tác phải cấp mảng lớn hơn và sao chép nhiều tham chiếu có thể tốn O(n) ở thời điểm đó, với n tương ứng quy mô dữ liệu cần chuyển.

**O(1) khấu hao** không nói rằng mọi lần thêm đều có thời gian bằng nhau. Nó nói chi phí trung bình khi phân bổ tổng chi phí trên cả một chuỗi thao tác.

Mô hình minh họa đơn giản: giả sử một cấu trúc mảng tăng theo cấp số nhân, với các lần chuyển dữ liệu cỡ:

```text
1, 2, 4, 8, ... , 2^k
```

Tổng số tham chiếu được chuyển trong mô hình là:

```text
1 + 2 + 4 + ... + 2^k = 2^(k+1) - 1
```

Tổng này tăng cùng bậc với lượng dữ liệu đã thêm tới quy mô đó, nên chi phí sao chép có thể phân bổ thành hằng số trung bình cho mỗi phần tử. Đây là mô hình giải thích phân tích khấu hao, không phải công thức tăng chính xác của ArrayDeque trên JDK đang chạy.

Tài liệu ArrayDeque công bố phần lớn thao tác có thời gian hằng số khấu hao; tìm phần tử hoặc xóa theo giá trị có thể tốn tuyến tính. [Đặc tính hiệu năng ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

Hệ quả khi sử dụng:

- Chuỗi thao tác dài có thể có chi phí tốt, trong khi một lần thêm riêng lẻ vẫn bị tăng độ trễ do mở rộng.
- Tạo với dung lượng ước lượng phù hợp có thể giảm số lần cấp phát/mở rộng ban đầu.
- Dung lượng lớn hơn không làm tìm kiếm theo giá trị trở thành O(1).
- Không nên suy ra hiệu năng thực tế chỉ từ một phép đo thời gian cho một lời gọi.

## 5. Mở rộng vẫn chịu giới hạn bộ nhớ

“Không đặt giới hạn dung lượng” không có nghĩa “bộ nhớ vô hạn”. Mảng nội bộ, các đối tượng phần tử và phần còn lại của ứng dụng đều sử dụng tài nguyên của JVM.

Khi mở rộng, việc cấp mảng mới có thể làm nhu cầu bộ nhớ tăng trong giai đoạn chuyển dữ liệu. Nếu không thể cấp phát, JVM có thể báo `OutOfMemoryError`. Đây không phải trạng thái hàng đợi “đầy theo giới hạn nghiệp vụ” được báo bằng `offer(...) == false`. [OutOfMemoryError](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/OutOfMemoryError.html).

Với ArrayDeque, không nên viết vòng lặp nạp dữ liệu vô hạn rồi chờ `offerLast` trả false để dừng. Hãy xác định điều kiện dừng, giới hạn lượng công việc hoặc cơ chế điều tiết từ yêu cầu của ứng dụng.

Ngược lại, yêu cầu dung lượng ban đầu quá lớn chỉ để tránh mọi lần mở rộng có thể làm nhiều Deque sống cùng lúc giữ vùng lưu trữ không cần thiết. Bài toán tối ưu là cân bằng mức sử dụng dự kiến và tài nguyên, không phải chọn con số lớn nhất có thể.

## 6. Chương trình kiểm chứng hành vi công khai

Lưu thành `ArrayDequeGrowthLab.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public final class ArrayDequeGrowthLab {
    private ArrayDequeGrowthLab() {
    }

    private static final class Item {
        private final String name;

        private Item(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        int requestedInitialCapacity = 2;
        ArrayDeque<Integer> numbers = new ArrayDeque<>(requestedInitialCapacity);
        System.out.println("initial request=" + requestedInitialCapacity);
        System.out.println("initial size=" + numbers.size());

        for (int i = 0; i < 8; i++) {
            numbers.addLast(i);
        }
        System.out.println("after append=" + numbers);
        System.out.println("size=" + numbers.size());
        System.out.println("toArray length=" + numbers.toArray().length);

        for (int expected = 0; expected < 3; expected++) {
            int actual = numbers.removeFirst();
            if (actual != expected) {
                throw new AssertionError("unexpected removal order");
            }
        }
        for (int i = 8; i < 16; i++) {
            numbers.addLast(i);
        }
        System.out.println("after remove/add=" + numbers);
        System.out.println("first=" + numbers.getFirst() + ", last=" + numbers.getLast());

        int count = 0;
        int sum = 0;
        Integer value;
        while ((value = numbers.pollFirst()) != null) {
            if (value != count + 3) {
                throw new AssertionError("FIFO order changed");
            }
            sum += value;
            count++;
        }
        System.out.println("drained count=" + count + ", sum=" + sum);
        System.out.println("empty=" + numbers.isEmpty());

        Deque<Item> items = new ArrayDeque<>(1);
        Item anchor = new Item("anchor");
        items.addLast(anchor);
        for (int i = 0; i < 100; i++) {
            items.addLast(new Item("item-" + i));
        }
        System.out.println("same reference=" + (items.getFirst() == anchor));
        System.out.println("first item=" + items.getFirst().name);
        items.clear();
        System.out.println("after clear size=" + items.size());
        items.addLast(new Item("restart"));
        System.out.println("after reuse=" + items.getFirst().name);
    }
}
```

Biên dịch và chạy trên Java 17+:

```shell
javac -Xlint:all -Werror ArrayDequeGrowthLab.java
java ArrayDequeGrowthLab
```

Stdout:

```text
initial request=2
initial size=0
after append=[0, 1, 2, 3, 4, 5, 6, 7]
size=8
toArray length=8
after remove/add=[3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
first=3, last=15
drained count=13, sum=117
empty=true
same reference=true
first item=anchor
after clear size=0
after reuse=restart
```

### Các kết luận thực sự rút ra từ ví dụ

**Dung lượng yêu cầu khác size:** sau constructor với 2, kích thước bằng 0. Thêm 8 phần tử thành công chứng minh số 2 không phải giới hạn tối đa.

**Thứ tự được giữ:** lấy 0, 1, 2 rồi thêm 8 tới 15 cho dãy 3 tới 15. Vòng lặp lấy hết kiểm tra từng giá trị kỳ vọng; nếu thứ tự sai, chương trình phát sinh `AssertionError`. Tổng của 13 giá trị này là 117.

**toArray phản ánh dữ liệu:** độ dài mảng trả về là 8 khi đang có 8 phần tử. Không có dòng nào cho biết độ dài mảng nội bộ. [ArrayDeque.toArray](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html#toArray()).

**Tham chiếu phần tử không tự đổi:** `items.getFirst() == anchor` kiểm tra cùng đối tượng, sau khi đã thêm nhiều phần tử. Việc vùng chứa thay đổi không tự sao chép đối tượng `Item` thành một đối tượng khác.

**Có thể tái sử dụng sau clear:** clear xóa các phần tử khỏi Deque, rồi có thể thêm dữ liệu mới. Kết quả `size == 0` chỉ chứng minh đã hết phần tử, không chứng minh vùng chứa nội bộ đã nhỏ lại.

Chương trình không đo số lần cấp phát, số lần mở rộng hoặc dung lượng vật lý sau từng thao tác. Cách bố trí vật lý là phần nội bộ; đầu ra công khai không đủ để suy ra các con số đó.

## 7. Lấy hết hoặc clear có tự thu nhỏ không?

Cần tách **bỏ tham chiếu tới phần tử** khỏi **thay mảng lưu trữ bằng mảng nhỏ hơn**.

Trong OpenJDK 25 được tham chiếu, `clear()` xóa các tham chiếu phần tử và đặt lại chỉ số, giữ lại mảng lưu trữ hiện có. Vì vậy, một Deque từng chứa rất nhiều dữ liệu có thể tiếp tục giữ mảng lớn sau khi size về 0. Đây là quan sát về triển khai; API clear chỉ yêu cầu xóa phần tử. [Mã nguồn clear của ArrayDeque](https://github.com/openjdk/jdk/blob/jdk-25-ga/src/java.base/share/classes/java/util/ArrayDeque.java), [Hợp đồng clear](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html#clear()).

Điều đó có thể có lợi nếu ngay sau đó cấu trúc lại được nạp tới mức cũ: vùng chứa có sẵn giúp tránh chuẩn bị lại từ đầu. Nhưng nếu một đợt dữ liệu rất lớn chỉ xảy ra một lần, giữ đối tượng đó lâu dài có thể giữ mức cấp phát không còn phù hợp.

Một lựa chọn ở ranh giới kết thúc một đợt xử lý là thay đối tượng bằng một ArrayDeque mới với ước lượng phù hợp, nếu thiết kế cho phép:

```java
Deque<String> pending = new ArrayDeque<>(expectedForNextBatch);
```

Đây là trích đoạn tạo vùng chứa cho đợt mới; `expectedForNextBatch` phải là ước lượng đã được xác thực của ứng dụng. Nếu đang thay một Deque cũ, cần xử lý xong dữ liệu còn lại và bảo đảm không có nơi khác tiếp tục giữ hoặc sử dụng cấu trúc cũ theo một hợp đồng khác.

Việc bỏ tham chiếu không buộc JVM thu gom rác ngay. Các phần tử còn được tham chiếu từ nơi khác vẫn còn sống; mảng cũ cũng chỉ có thể được thu hồi khi không còn được sử dụng qua các tham chiếu liên quan.

Không có phương thức công khai `trimToSize()` hay `ensureCapacity()` trên ArrayDeque để điều khiển trực tiếp vùng chứa như một số cấu trúc mảng khác. Chọn dung lượng lúc tạo và quản lý vòng đời là hai công cụ thông thường ở tầng sử dụng.

## 8. Chọn dung lượng ban đầu theo tình huống

### Biết khá rõ quy mô một đợt

Nếu mỗi đợt thường có khoảng 2.000 công việc và chỉ vài Deque sống cùng lúc, một dung lượng khởi tạo phù hợp có thể giảm việc mở rộng trong giai đoạn nạp. Cần đo trên tải đại diện để biết lợi ích có đáng với vùng nhớ chuẩn bị trước hay không.

### Không biết trước hoặc có nhiều Deque nhỏ

Dùng constructor mặc định hoặc một ước lượng vừa phải thường dễ quản lý hơn việc chuẩn bị dung lượng rất lớn cho từng đối tượng. Quan sát mức sử dụng thực tế rồi điều chỉnh khi có bằng chứng.

### Quy mô bùng lên bất thường

Dung lượng ban đầu không giải quyết được tốc độ nạp liên tục vượt tốc độ xử lý. Cần một chính sách về lượng công việc đang chờ, điều tiết đầu vào hoặc lựa chọn cấu trúc có giới hạn. ArrayDeque chỉ quản lý vùng lưu trữ; nó không tự áp dụng chính sách tải.

### Cần dự đoán độ trễ chặt

O(1) khấu hao chưa đủ để cam kết thời gian tối đa cho từng lời gọi. Cấp phát, mở rộng và hoạt động của JVM đều cần được đánh giá trong bối cảnh thực tế. Tránh coi việc đã chuẩn bị dung lượng ban đầu là một chứng minh rằng không còn mọi nguồn biến động thời gian.

## 9. Lỗi thường gặp và bài tập

| Nhầm lẫn | Điều cần kiểm tra lại |
|---|---|
| ArrayDeque(10) chứa sẵn 10 phần tử | Constructor theo dung lượng tạo Deque rỗng |
| Phần tử thứ 11 làm offer trả false | Tham số 10 không đặt giới hạn tối đa |
| size là dung lượng mảng | size đếm phần tử hiện có |
| toArray cho thấy mảng bên trong | toArray tạo mảng kết quả từ dữ liệu hiện có |
| Mở rộng làm đổi đối tượng phần tử | Vùng chứa lưu/sao chép tham chiếu; không tự tạo bản sao sâu |
| O(1) khấu hao nghĩa là mọi lần thêm đều O(1) | Một lần mở rộng có thể phải chuyển nhiều tham chiếu |
| clear chắc chắn trả dung lượng về mức ban đầu | Không có cam kết thu nhỏ như vậy từ API |
| Ghi nhớ một hệ số tăng sẽ đúng cho mọi JDK | Dựa vào hợp đồng công khai, kiểm tra mã nguồn đúng phiên bản khi nghiên cứu nội bộ |

Thực hành:

1. Đổi `requestedInitialCapacity` thành 0, 1 và 64; giữ nguyên dữ liệu. Kiểm tra size và thứ tự đầu ra có thay đổi không. Không suy ra dung lượng vật lý chỉ từ kết quả này.
2. Thêm 10.000 phần tử rồi lấy ra một nửa, sau đó thêm 5.000 phần tử khác. Viết kiểm tra thứ tự của toàn bộ phần tử còn lại.
3. Tạo một phần tử có thuộc tính thay đổi được, thêm vào Deque rồi đổi thuộc tính qua một tham chiếu khác. Giải thích vì sao mở rộng vùng chứa không tạo ra một bản chụp độc lập của phần tử.
4. Với một hệ thống có 10.000 Deque thường chỉ chứa 0–3 phần tử, đánh giá hệ quả của việc cấp dung lượng yêu cầu 100.000 cho từng Deque.
5. Phân loại điều cần kiểm tra bằng chương trình và điều cần đọc từ hợp đồng/mã nguồn: thứ tự FIFO, size, số lần mở rộng, hệ số tăng, tác động của clear.

Khi dùng ArrayDeque, hãy chọn dung lượng ban đầu như một **ước lượng chuẩn bị vùng lưu trữ**. Độ đúng của chương trình vẫn nên dựa vào phần tử và thứ tự, còn giới hạn tải và vòng đời bộ nhớ cần quyết định rõ ở tầng ứng dụng.
