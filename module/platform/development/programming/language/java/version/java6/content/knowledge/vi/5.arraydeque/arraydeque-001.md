# Cấu trúc mảng mở rộng và hiệu quả thao tác hai đầu

## 1. ArrayDeque giải quyết bài toán gì?

Một hàng đợi hai đầu cần thêm và lấy phần tử ở cả đầu trước lẫn đầu sau. Nếu dùng một mảng theo cách luôn đặt phần tử đầu tại chỉ số 0, mỗi lần xóa đầu có thể phải dời hàng loạt phần tử sang trái.

`ArrayDeque<E>` giải quyết nhu cầu này bằng một bộ chứa dựa trên mảng có thể mở rộng, kết hợp việc quản lý hai đầu theo vòng. Thao tác ở đầu trước không bắt buộc phải dồn toàn bộ dữ liệu về chỉ số 0 sau mỗi lần lấy.

Ý tưởng quan trọng gồm hai phần:

- **Mảng vòng:** tái sử dụng các vị trí trống khi đầu hoặc cuối đi tới ranh giới mảng.
- **Mảng mở rộng:** cấp thêm vùng chứa khi không còn đủ chỗ để thêm phần tử.

Nhờ vậy, `ArrayDeque` phù hợp với hàng đợi FIFO hoặc ngăn xếp LIFO trong nhiều thuật toán cục bộ. Tuy nhiên, “mở rộng được” không đồng nghĩa bộ nhớ vô hạn, còn “hiệu quả ở hai đầu” không đồng nghĩa mọi thao tác đều có cùng chi phí.

Bài sử dụng Java 17 trở lên. Các hình bên dưới là mô hình giải thích cơ chế, không phải lời cam kết rằng mọi JDK dùng đúng số ô, vị trí hoặc hệ số tăng trưởng như hình.

## 2. Tách thứ tự logic khỏi vị trí trong mảng

Giả sử deque có thứ tự logic từ First đến Last là:

```text
First -> A, B, C, D <- Last
```

Một hình minh họa mảng vòng có thể đặt dữ liệu như sau:

```text
Chỉ số mảng:       0     1     2     3     4     5
Nội dung:        [ C ] [ D ] [ . ] [ . ] [ A ] [ B ]
                                          ^
                                          |
                                 vị trí phần tử đầu

Thứ tự logic:     A -> B -> C -> D
```

Dấu `.` biểu diễn ô không chứa phần tử trong hình. Đọc từ vị trí A, ta đi sang phải tới B, rồi quay về đầu mảng để đọc C và D.

Vì vậy:

- Thứ tự deque không nhất thiết trùng với thứ tự chỉ số mảng tăng từ 0.
- Dữ liệu đang có có thể nằm ở hai đoạn của mảng.
- Việc đi qua ranh giới cuối mảng không có nghĩa phải cấp mảng mới.

Từ trạng thái trên, lấy đầu A có thể chỉ cần bỏ tham chiếu A và chuyển vị trí đầu sang B. Thêm cuối E có thể sử dụng một ô trống sau D theo vòng.

```text
Sau khi lấy A, thêm E:

Chỉ số mảng:       0     1     2     3     4     5
Nội dung:        [ C ] [ D ] [ E ] [ . ] [ . ] [ B ]

Thứ tự logic:     B -> C -> D -> E
```

Không cần dời B, C, D chỉ để đưa B về chỉ số 0.

Đây là khác biệt nền tảng giữa “dữ liệu được đọc theo một thứ tự” và “dữ liệu phải luôn nằm liền từ đầu mảng”. Người dùng API quan sát thứ tự logic; lớp triển khai quản lý vị trí lưu bên trong.

## 3. Hai đầu được quản lý như thế nào?

Một mô hình thường dùng có:

- Một mảng chứa tham chiếu đến phần tử.
- Vị trí của phần tử đầu.
- Vị trí dùng cho bước thêm tiếp theo ở phía cuối.
- Quy tắc đi tiếp hoặc lùi lại khi chạm ranh giới.

Trong mã OpenJDK 25 được đối chiếu, `ArrayDeque` dùng mảng `elements` cùng các vị trí `head` và `tail`; các ô không dùng có giá trị `null`. Đây là chi tiết triển khai đã kiểm tra ở một phiên bản cụ thể, không phải các trường mà ứng dụng được phép truy cập như API công khai. [Mã nguồn ArrayDeque của OpenJDK 25](https://raw.githubusercontent.com/openjdk/jdk/jdk-25%2B36/src/java.base/share/classes/java/util/ArrayDeque.java)

Có thể hiểu thao tác hai đầu ở mức khái niệm:

| Thao tác | Công việc thông thường khi không phải mở rộng |
| --- | --- |
| Thêm cuối | Đặt tham chiếu vào phía cuối rồi tiến vị trí cuối |
| Thêm đầu | Lùi vị trí đầu rồi đặt tham chiếu mới |
| Lấy đầu | Đọc phần tử đầu, bỏ tham chiếu ở ô đó rồi tiến đầu |
| Lấy cuối | Lùi vị trí cuối, đọc phần tử và bỏ tham chiếu ở ô đó |
| Xem đầu hoặc cuối | Đọc vị trí biên phù hợp mà không xóa |

Quy tắc “đi theo vòng” có thể được minh họa bằng phép chuyển chỉ số trở về đầu khi tới hết mảng. Không nên từ hình vẽ suy ra ứng dụng phải tự dùng phép chia dư hoặc một phép toán bit cụ thể: các công thức nội bộ có thể thay đổi giữa các JDK.

### Mảng giữ tham chiếu, không sao chép toàn bộ đối tượng

Với `ArrayDeque<Person>`, ô mảng giữ tham chiếu đến một `Person`. Thêm phần tử không tự sao chép toàn bộ đối tượng.

Tương tự, khi mở rộng bộ chứa, việc di chuyển dữ liệu chủ yếu liên quan đến các tham chiếu trong mảng, không phải tạo một bản sao sâu của mọi đối tượng được tham chiếu.

Sau khi xóa phần tử khỏi deque, bỏ tham chiếu tại ô đã dùng giúp bộ chứa không tiếp tục giữ đối tượng đó chỉ vì dữ liệu cũ còn trong mảng. Đối tượng chỉ có thể được thu hồi khi không còn tham chiếu có thể truy cập khác; xóa khỏi deque không bảo đảm bộ thu gom rác sẽ thu hồi ngay lập tức.

## 4. Mở rộng khác với quay vòng

Hai tình huống dễ bị nhầm:

**Quay vòng:** còn chỗ trong mảng đang dùng, nhưng vị trí tiếp theo nằm ở đầu mảng sau khi đi qua cuối mảng.

**Mở rộng:** bộ chứa cần thêm không gian để đáp ứng lần thêm; lớp phải có một mảng lớn hơn và tổ chức lại dữ liệu cần giữ.

Ví dụ minh họa việc mở rộng:

```text
Trước:
  Thứ tự logic A, B, C, D nằm qua ranh giới mảng cũ.

Khi cần thêm không gian:
  Cấp mảng lớn hơn.
  Chuyển các tham chiếu và điều chỉnh vị trí hai đầu.
  Giữ nguyên thứ tự logic A, B, C, D.
  Tiếp tục thêm phần tử mới.
```

Một hình giải thích có thể vẽ dữ liệu được đưa về đoạn đầu của mảng mới để dễ nhìn. Không nên coi cách bố trí minh họa đó là quy tắc bắt buộc của mã triển khai.

Những gì ứng dụng cần dựa vào là thứ tự deque được giữ đúng và bộ chứa có thể tăng theo nhu cầu, trong giới hạn tài nguyên. Không nên phụ thuộc vào:

- Mảng luôn có kích thước là lũy thừa của hai.
- Mọi lần tăng đều nhân đôi đúng kích thước.
- Chỉ số đầu luôn trở về 0 sau mở rộng.
- Hàm tạo cấp chính xác bằng số ô mà người gọi truyền vào.
- Việc xóa dữ liệu luôn thu nhỏ ngay mảng bên trong.

Các giả định này thuộc cách cài đặt, không phải lý do để viết thuật toán nghiệp vụ.

## 5. Vì sao thao tác hai đầu có chi phí hằng số khấu hao?

Nếu không cần mở rộng, thao tác thêm hoặc lấy ở một đầu chỉ làm việc với một số ít vị trí biên. Nó không phải tìm phần tử trên toàn bộ deque hoặc dời cả dãy sau mỗi lần thao tác.

Nhưng đôi khi một lần thêm phải mở rộng và chuyển nhiều tham chiếu. Vì vậy cần phân biệt:

- **Chi phí một lần cụ thể:** có thể tăng khi xảy ra mở rộng.
- **Chi phí khấu hao trên một chuỗi thao tác:** chi phí những lần tốn kém được phân bổ cho nhiều lần thao tác thông thường.

Đó là ý nghĩa của nhận định hằng số khấu hao đối với các thao tác phù hợp của `ArrayDeque`. Nó không phải cam kết mỗi lời gọi đều hoàn thành trong cùng số nano giây hoặc không bao giờ phải cấp phát.

Hãy xét một mô hình mảng động tăng theo cấp số nhân. Sau mỗi lần tăng, có thêm một khoảng không gian để nhiều lần thêm tiếp theo không cần chuyển dữ liệu. Khi cộng chi phí chuyển tham chiếu qua cả chuỗi tăng trưởng, tổng vẫn tăng cùng bậc với số lần thêm. Đây là mô hình phân tích để hiểu khấu hao, không phải khẳng định một hệ số tăng trưởng cụ thể của mọi JDK.

### Những thao tác không nên coi là hằng số

| Thao tác | Điều phải làm | Nhận xét về chi phí |
| --- | --- | --- |
| Thêm ở hai đầu | Cập nhật biên, đôi khi mở rộng | Hằng số khấu hao |
| Lấy hoặc xem ở hai đầu | Dùng vị trí biên | Không cần tìm theo giá trị |
| `contains(value)` | Tìm phần tử phù hợp | Có thể duyệt toàn bộ |
| `remove(Object)` | Tìm theo giá trị rồi xóa | Có thể tốn thời gian tuyến tính |
| `removeFirstOccurrence`, `removeLastOccurrence` | Tìm lần xuất hiện theo hướng đã chọn | Có thể tốn thời gian tuyến tính |
| Duyệt toàn bộ hoặc `clear()` | Làm việc trên nhiều phần tử | Chi phí tăng theo lượng dữ liệu |

Tài liệu API phân biệt phần lớn thao tác hằng số khấu hao với các ngoại lệ tuyến tính như tìm kiếm, xóa theo giá trị và các thao tác hàng loạt. [Đặc điểm chi phí của ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html)

Tên phương thức phải được đọc cùng chữ ký: `remove()` không đối số lấy đầu, còn `remove(Object)` tìm và xóa theo giá trị. Hai thao tác có nhu cầu xử lý khác nhau dù dùng cùng tên.

## 6. Dung lượng khởi tạo không phải sức chứa tối đa

Đoạn sau không tạo một deque chỉ được phép chứa hai phần tử:

```java
Deque<Integer> values = new ArrayDeque<>(2);
```

Số 2 cung cấp nhu cầu dung lượng ban đầu. `ArrayDeque` có thể mở rộng khi thêm nhiều hơn. API cũng không cung cấp một phương thức công khai để đọc chính xác độ dài mảng nội bộ.

Có thể chọn dung lượng ban đầu hợp lý nếu ước lượng được số phần tử thường có cùng lúc. Điều này có thể giảm việc tăng trưởng trong giai đoạn nạp dữ liệu, nhưng không tự bảo đảm độ trễ hay mức dùng bộ nhớ cụ thể.

Tránh cấp trước theo một con số rất lớn chỉ để “khỏi phải tăng”. Bộ nhớ dự trữ cũng có chi phí, còn nhu cầu thực tế có thể nhỏ hơn rất nhiều.

Nếu yêu cầu nghiệp vụ là “chỉ nhận tối đa N việc đang chờ”, hãy dùng một cơ chế có giới hạn sức chứa và chính sách tiếp nhận phù hợp. Đừng dùng đối số hàm tạo của `ArrayDeque` làm hàng rào giới hạn.

## 7. Chương trình hoàn chỉnh: quan sát thứ tự ở hai đầu

Ví dụ chỉ kiểm chứng hành vi API. Nó không dùng phản chiếu để đọc trường riêng và không suy ra thời điểm mở rộng chính xác từ stdout.

Lưu tệp `ArrayDequeEndsDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class ArrayDequeEndsDemo {
    public static void main(String[] args) {
        Deque<Integer> deque = new ArrayDeque<>(2);
        for (int i = 1; i <= 6; i++) {
            deque.addLast(i);
        }
        System.out.println("afterAppend=" + deque);

        System.out.println("removedFirst=" + deque.removeFirst()
                + "," + deque.removeFirst());
        deque.addLast(7);
        deque.addLast(8);
        deque.addFirst(0);
        System.out.println("afterBothEnds=" + deque);
        System.out.println("ends=" + deque.peekFirst() + "," + deque.peekLast());

        System.out.println("removedLast=" + deque.removeLast());
        System.out.println("removedValue=" + deque.remove(Integer.valueOf(4)));
        System.out.println("afterValueRemoval=" + deque);

        ArrayDeque<Integer> copy = new ArrayDeque<>(deque);
        deque.clear();
        System.out.println("originalAfterClear=" + deque);
        System.out.println("copy=" + copy);
        System.out.println("emptyPoll=" + deque.pollFirst());

        try {
            deque.addLast(null);
        } catch (NullPointerException e) {
            System.out.println("nullRejected=" + e.getClass().getSimpleName());
        }
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac --release 17 ArrayDequeEndsDemo.java
java ArrayDequeEndsDemo
```

Stdout:

```text
afterAppend=[1, 2, 3, 4, 5, 6]
removedFirst=1,2
afterBothEnds=[0, 3, 4, 5, 6, 7, 8]
ends=0,8
removedLast=8
removedValue=true
afterValueRemoval=[0, 3, 5, 6, 7]
originalAfterClear=[]
copy=[0, 3, 5, 6, 7]
emptyPoll=null
nullRejected=NullPointerException
```

### Những gì có thể kết luận từ chương trình

**Bộ chứa nhận nhiều hơn dung lượng khởi tạo:** ban đầu yêu cầu 2 nhưng chương trình thêm 6 phần tử. Vì thế số truyền vào không phải giới hạn số phần tử được nhận.

**Lấy đầu không làm sai thứ tự phần còn lại:** sau khi lấy 1 và 2, các phần tử còn lại theo thứ tự 3, 4, 5, 6.

**Hai đầu hoạt động độc lập theo hợp đồng:** thêm 7, 8 ở cuối và 0 ở đầu tạo 0, 3, 4, 5, 6, 7, 8. Xem đầu và cuối trả 0 và 8 mà không xóa dữ liệu.

**Xóa theo giá trị khác xóa ở đầu:** `remove(Integer.valueOf(4))` chọn giá trị 4 trong dãy, không phải phần tử thứ tư và không phải đầu hiện tại.

**Bản sao là bộ chứa riêng:** sau khi tạo `copy`, `clear()` trên nguồn không làm rỗng bản sao. Với phần tử có thể thay đổi, vẫn cần nhớ hàm tạo từ collection không tự sao chép sâu từng đối tượng.

**Rỗng và đầu vào không hợp lệ có cách báo khác nhau:** `pollFirst()` trên rỗng trả `null`; thử thêm `null` bị từ chối bằng ngoại lệ.

### Những gì không thể kết luận từ stdout

Chương trình không cho biết mảng nội bộ đang dài bao nhiêu, lúc nào có cấp mảng mới, hay đầu đang ở chỉ số nào.

Nó cũng không chứng minh một thao tác nhanh hơn một cấu trúc khác. Đúng thứ tự và đúng giá trị trả về là bằng chứng về chức năng, không phải kết quả đo hiệu năng.

## 8. Vì sao thường phù hợp cho FIFO và LIFO cục bộ?

Với FIFO, dùng thêm cuối và lấy đầu:

```java
// Minh họa trong phương thức; jobs là Deque<String>.
jobs.offerLast("A");
jobs.offerLast("B");
String next = jobs.pollFirst(); // A
```

Với LIFO, dùng thêm đầu và lấy đầu thông qua các tên ngăn xếp:

```java
// Minh họa trong phương thức; history là Deque<String>.
history.push("A");
history.push("B");
String latest = history.pop(); // B
```

Cả hai cách chủ yếu thao tác ở biên, đúng với điểm mạnh của cấu trúc mảng vòng. Chúng không cần tìm kiếm tùy ý trong phần giữa.

Một danh sách liên kết đôi như `LinkedList` cũng hỗ trợ hai đầu, nhưng quản lý các nút liên kết thay vì một mảng tham chiếu mở rộng. Do cấu trúc lưu trữ khác nhau, chi phí cấp phát và cách truy cập bộ nhớ cũng khác. Không nên chỉ dựa vào việc cả hai cùng có thao tác hai đầu để cho rằng chúng tương đương về hiệu năng. [Cấu trúc LinkedList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedList.html)

Lựa chọn vẫn phụ thuộc nhu cầu:

- Cần chủ yếu hai đầu trong một luồng: `ArrayDeque` là ứng viên trực tiếp.
- Cần truy cập theo chỉ số: `Deque` không cung cấp `get(index)`; nên xét một hợp đồng cấu trúc phù hợp hơn.
- Cần nhiều luồng cùng thao tác: phải chọn hoặc thiết kế cơ chế đồng thời.
- Cần sức chứa cố định hay chờ khi đầy/rỗng: cần thêm hợp đồng tương ứng.
- Cần dữ liệu bền vững: một deque cục bộ trong bộ nhớ chưa đáp ứng yêu cầu.

Không cần thay một cấu trúc đang phù hợp chỉ vì nghe nói cấu trúc kia “luôn nhanh hơn”. Hãy xét loại thao tác, lượng dữ liệu đang giữ, cách truy cập và điều kiện chạy.

## 9. Giới hạn và ngộ nhận cần tránh

### Mảng vòng không phải hàng đợi giới hạn tự ghi đè

Quay vòng chỉ mô tả cách sử dụng các vị trí mảng. `ArrayDeque` không có chính sách tự ghi đè phần tử cũ nhất khi tới ranh giới mảng.

Nếu ứng dụng cần bộ đệm chỉ giữ N sự kiện gần nhất, phải định nghĩa rõ khi nào bỏ phần tử cũ. Không được suy ra hành vi ấy từ từ “vòng”.

### Mở rộng không có nghĩa không bao giờ thất bại

Bộ nhớ và giới hạn mảng của môi trường vẫn tồn tại. Một chương trình tiếp nhận dữ liệu không giới hạn có thể cạn tài nguyên. Cần kiểm soát quy mô dữ liệu từ thiết kế, không đợi vấn đề bộ nhớ xuất hiện.

### clear không đồng nghĩa trả ngay toàn bộ vùng nhớ cho hệ thống

`clear()` làm deque không còn phần tử theo hợp đồng API. Đừng dựa vào nó như một cam kết thu nhỏ ngay mảng nội bộ hoặc giải phóng ngay bộ nhớ cho hệ điều hành.

Nếu cần quản lý một đợt dữ liệu rất lớn rồi quay về mức nhỏ, phải xem xét vòng đời của bộ chứa và các tham chiếu đang giữ nó. Không có bảo đảm thu hồi tức thì chỉ từ một lời gọi xóa.

### Hiệu quả hai đầu không làm tìm kiếm ở giữa trở thành miễn phí

Nếu thuật toán liên tục tìm rồi xóa theo giá trị trong một deque lớn, chi phí có thể tăng đáng kể. Hãy đánh giá đúng tần suất thao tác cần duyệt thay vì chỉ nhìn tên lớp có chữ “Array”.

### Cấu trúc nội bộ không tạo an toàn đa luồng

Mảng vòng vẫn cần một giao thức đúng khi nhiều bên truy cập. `ArrayDeque` không tự an toàn đa luồng; việc hai luồng dùng hai đầu khác nhau không làm chúng tự động độc lập.

Các iterator có cơ chế hỗ trợ phát hiện thay đổi không phù hợp, nhưng không được dùng việc có hoặc không có ngoại lệ làm bằng chứng đồng bộ đúng.

## 10. Cách kiểm chứng hiệu quả mà không suy luận quá mức

Trước khi đo thời gian, cần xác định một chuỗi thao tác phản ánh đúng nhu cầu:

- Tỷ lệ thêm, lấy, xem và tìm theo giá trị là bao nhiêu?
- Số phần tử đồng thời trong deque thường là bao nhiêu?
- Có đợt tăng đột biến hay không?
- Có cần đo riêng lần mở rộng với trạng thái ổn định?
- Dữ liệu phần tử có gây cấp phát hoặc công việc khác che lấp chi phí bộ chứa không?

Một lần chạy ngắn bằng đồng hồ không đủ để khẳng định cấu trúc luôn nhanh hơn cấu trúc khác. Máy ảo cần thời gian tối ưu mã, các lần cấp phát và thu gom rác có thể ảnh hưởng kết quả, còn việc in ra màn hình thường không đại diện cho chi phí thao tác deque.

Đối với việc học trong bài này, bằng chứng cần tách thành hai loại:

1. **Kiểm chứng chức năng:** thứ tự, kết quả trả về, trạng thái rỗng và việc thêm quá dung lượng khởi tạo.
2. **Lập luận cấu trúc:** vì sao cập nhật vị trí biên tránh dồn cả dãy trong các thao tác thông thường, và vì sao mở rộng tạo ra những lần tốn kém hơn.

Một phép đo có kiểm soát có thể bổ sung cho quyết định thực tế, nhưng không thay thế việc hiểu hợp đồng và loại thao tác.

## 11. Thực hành để củng cố mô hình

### Bài 1: Phân biệt quay vòng và mở rộng

Trong hình mảng 6 ô, dữ liệu ở vị trí 4, 5, 0, 1. Hỏi có phải cứ đi từ 5 về 0 là phải tăng mảng không?

Không. Đó là đi theo vòng trong cùng mảng. Chỉ khi không đủ không gian theo quy tắc triển khai mới cần mở rộng.

### Bài 2: Dự đoán thứ tự logic

Bắt đầu với deque rỗng, lần lượt thêm cuối A, B, C; lấy đầu một lần; thêm đầu X; thêm cuối D.

Thứ tự từ First đến Last là X, B, C, D. Kết quả không phụ thuộc việc các tham chiếu nằm ở những chỉ số nội bộ nào.

### Bài 3: Đọc đúng chữ ký remove

So sánh:

```java
deque.remove();                   // Lấy đầu.
deque.remove(Integer.valueOf(4)); // Tìm và xóa giá trị 4.
```

Hãy giải thích vì sao thao tác thứ hai có thể cần duyệt nhiều phần tử dù thao tác thứ nhất chỉ cần vị trí biên.

### Bài 4: Chọn giả định ổn định

Với một thuật toán dùng `ArrayDeque`, hãy đánh dấu những điều có thể dựa vào:

- Thứ tự thao tác hai đầu theo hợp đồng: có.
- Luôn nhân đôi đúng kích thước mảng: không.
- Dung lượng khởi tạo là giới hạn tối đa: không.
- `pollFirst()` trả `null` khi rỗng: có.
- Tất cả thao tác đều có thời gian như nhau: không.
- Bản thân bộ chứa tự bảo đảm truy cập nhiều luồng: không.

Mục tiêu là dùng mô hình mảng vòng để giải thích hiệu quả, đồng thời viết mã dựa vào API công khai. Khi nắm được sự tách biệt đó, ta có thể chọn thao tác đúng mà không gắn chương trình vào các chi tiết dễ thay đổi của một phiên bản JDK.
