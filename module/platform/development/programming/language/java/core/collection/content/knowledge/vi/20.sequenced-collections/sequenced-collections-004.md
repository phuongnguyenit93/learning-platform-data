# addFirst, addLast và thao tác tùy chọn trên tập đã sắp xếp

## 1. Có thứ tự không đồng nghĩa được tự chọn vị trí

Từ Java 21, một tập đã sắp xếp như TreeSet có thể được sử dụng qua hệ giao diện Sequenced Collections. Vì thế, người học có thể nhìn thấy addFirst và addLast trên SortedSet rồi nghĩ rằng mình được đặt một phần tử vào đầu hoặc cuối tập.

Điều cần hiểu là **ai quyết định thứ tự**. Với TreeSet, quan hệ so sánh quyết định vị trí của phần tử. Với LinkedHashSet, chương trình có thể điều khiển thứ tự gặp các phần tử mà không cần tuân theo một Comparator.

Ví dụ, tập số được sắp theo thứ tự tự nhiên đang có 10,20,30:

- Thêm 25 bằng add làm tập thành 10,20,25,30.
- Yêu cầu đặt 25 vào đầu bằng addFirst trái với chính sách định vị của tập.
- Ngay cả yêu cầu đặt 5 vào đầu cũng bị TreeSet từ chối bằng addFirst; API không cung cấp thao tác này có điều kiện theo giá trị.
- Có thể đọc hoặc xóa phần tử đầu mà không phá quy tắc sắp xếp của các phần tử còn lại.

Bài học này giải thích vì sao phương thức tồn tại nhưng có thể không được hỗ trợ, cách chọn thao tác đúng, và cách kiểm tra hành vi trên Java 21. Tất cả chương trình đầy đủ trong bài cần **JDK 21 trở lên**; chúng không dùng tính năng preview.

### 1.1. Các từ cần phân biệt

| Khái niệm | Ý nghĩa trong bài |
|---|---|
| Tập hợp, Set | Lưu các phần tử theo tính duy nhất của tập; không có chỉ số như List |
| Thứ tự gặp, encounter order | Thứ tự các phần tử xuất hiện khi duyệt collection |
| Tập đã sắp xếp, SortedSet | Thứ tự do thứ tự tự nhiên hoặc Comparator chi phối |
| SequencedSet | Set có thứ tự gặp được xác định, cùng các thao tác theo hai đầu |
| Định vị tường minh | Yêu cầu một phần tử phải nằm ở đầu hoặc cuối bằng addFirst/addLast |
| Thao tác tùy chọn | Phương thức được khai báo trong API nhưng một triển khai có thể từ chối bằng UnsupportedOperationException |
| View | Một cách nhìn lên dữ liệu của collection khác, không mặc nhiên là bản sao |

Đọc đúng những quan hệ này giúp tránh hai kết luận sai: “TreeSet có addFirst nên chắc chắn gọi được” và “TreeSet không hỗ trợ addFirst nên toàn bộ tập không sửa được”.

## 2. Java 21 nối các giao diện như thế nào?

Trước Java 21, SortedSet đã có first, last và các thao tác theo khoảng. Từ Java 21, SortedSet còn thuộc hệ SequencedSet. Vì vậy cùng một tập đã sắp xếp có thể được đọc thông qua các giao diện có quy ước chung về đầu và cuối.

Sơ đồ dưới đây chỉ thể hiện nhánh quan hệ cần cho bài:

```text
SequencedCollection<E> + Set<E>
                  ↓
           SequencedSet<E>
                  ↓
             SortedSet<E>
                  ↓
           NavigableSet<E>
                  ↓
               TreeSet<E>
```

Mũi tên đi từ giao diện rộng hơn đến giao diện/lớp chuyên biệt hơn. SequencedSet kết hợp khả năng có thứ tự gặp với đặc tính của Set. SortedSet bổ sung chính sách thứ tự dựa trên so sánh.

Không phải mọi Set đều có giao diện SequencedSet. Ví dụ, một biến khai báo là Set chỉ cho phép gọi các phương thức thuộc Set ở mức biên dịch. Muốn viết mã sử dụng API mới, cần chọn kiểu khai báo phù hợp với hợp đồng thật sự muốn dùng.

Tài liệu [SequencedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html) mô tả giao diện kết hợp này. Nó không biến mọi thao tác sửa thứ tự thành thao tác bắt buộc được hỗ trợ.

### 2.1. Hai câu hỏi riêng ở hai thời điểm

| Câu hỏi | Được quyết định bởi |
|---|---|
| Mã có gọi được tên phương thức này không? | Kiểu khai báo, generic và phiên bản API khi biên dịch |
| Lời gọi có thực hiện được không? | Hợp đồng và khả năng của đối tượng thực tế lúc chạy |

Với SortedSet<Integer> trên Java 21, addFirst tồn tại nên lời gọi có thể biên dịch. Nhưng đối tượng TreeSet từ chối thao tác bằng UnsupportedOperationException.

Đổi biến nhận từ SortedSet sang SequencedSet không tạo ra một collection khác. Thao tác trên đối tượng thực tế vẫn giữ chính sách của TreeSet. Ép kiểu cũng không cài thêm một cơ chế thay đổi thứ tự cho đối tượng.

## 3. addFirst và addLast yêu cầu điều gì?

### 3.1. Hậu điều kiện về vị trí

addFirst nhận một phần tử và yêu cầu sau khi hoàn thành bình thường, phần tử đó là phần tử đầu theo thứ tự gặp. addLast yêu cầu phần tử ở cuối.

Hai phương thức trả void. Không dùng giá trị trả về của chúng như kết quả boolean của add.

| Phương thức | Giá trị trả về | Điều chương trình đang yêu cầu |
|---|---|---|
| add(e) trên một Set sửa được | boolean | Bảo đảm có phần tử theo quy tắc của tập, báo tập có thay đổi do thêm hay không |
| addFirst(e) | void | Đặt phần tử ở đầu theo thứ tự gặp |
| addLast(e) | void | Đặt phần tử ở cuối theo thứ tự gặp |

Cùng tên phương thức trên các collection khác nhau không xóa đi chính sách riêng của collection đó. Trên List, thêm đầu/cuối và phần tử trùng mang ý nghĩa khác với một Set chỉ giữ phần tử duy nhất. Trong bài, trọng tâm là các tập và giới hạn định vị của tập đã sắp xếp.

### 3.2. “Tùy chọn” không có nghĩa tham số có thể bỏ trống

Một thao tác tùy chọn vẫn có chữ ký đầy đủ; người gọi không bỏ tham số e. Tính tùy chọn ở đây là khả năng hỗ trợ thao tác sửa dữ liệu của triển khai.

[SequencedCollection — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html) khai báo addFirst và addLast là thao tác tùy chọn. Phần mặc định trong giao diện từ chối chúng. Lớp hỗ trợ định vị sẽ cung cấp hành vi thích hợp; lớp không thể cho người gọi chọn vị trí sẽ giữ hoặc công bố việc từ chối.

UnsupportedOperationException là ngoại lệ không được trình biên dịch buộc phải khai báo/catch. Mã biên dịch được không chứng minh lời gọi sẽ thành công.

### 3.3. TreeSet không định vị theo yêu cầu đầu/cuối

[SortedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html) xác định addFirst và addLast ném UnsupportedOperationException; quy tắc so sánh đã chịu trách nhiệm đặt vị trí. [TreeSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html) công bố cùng hành vi.

Với TreeSet tiêu chuẩn, không có nhánh “nếu phần tử vốn sẽ nằm ở đầu thì cho addFirst”. Các trường hợp sau đều bị từ chối:

- Phần tử mới nhỏ hơn mọi phần tử khi dùng thứ tự tự nhiên.
- Phần tử mới lớn hơn mọi phần tử khi gọi addLast.
- Phần tử đã tồn tại.
- Tập đang rỗng.
- Biến tham chiếu đang có kiểu rộng hơn là SequencedSet.

Điểm này cần đọc như một hợp đồng của thao tác. Không tự viết mã phụ thuộc vào dự đoán “giá trị của mình chắc chắn hợp với đầu tập”.

## 4. Chương trình 1: thao tác bị từ chối nhưng add vẫn hoạt động

Lưu vào `SortedPositionDemo.java`. Hàm expectUnsupported dùng để kiểm tra các lời gọi được dự kiến phải thất bại; nếu lời gọi không ném ngoại lệ, chương trình ném AssertionError để không báo một kết quả kiểm tra sai.

```java
import java.util.List;
import java.util.SequencedSet;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedPositionDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        SortedSet<Integer> sorted = new TreeSet<>(List.of(10, 30));
        System.out.println("initial=" + sorted);
        expectUnsupported("addFirstSmaller", () -> sorted.addFirst(5));
        expectUnsupported("addLastLarger", () -> sorted.addLast(40));
        expectUnsupported("addFirstExisting", () -> sorted.addFirst(10));
        System.out.println("afterRejected=" + sorted);
        System.out.println("add20=" + sorted.add(20));
        System.out.println("add10Again=" + sorted.add(10));
        System.out.println("afterAdd=" + sorted);
        System.out.println("ends=" + sorted.getFirst() + "," + sorted.getLast());

        SequencedSet<Integer> throughInterface = sorted;
        expectUnsupported("throughSequencedSet",
                () -> throughInterface.addFirst(5));

        SortedSet<Integer> empty = new TreeSet<>();
        expectUnsupported("emptyAddFirst", () -> empty.addFirst(1));
        expectUnsupported("emptyAddLast", () -> empty.addLast(1));
        System.out.println("emptyStillEmpty=" + empty.isEmpty());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 SortedPositionDemo.java
java SortedPositionDemo
```

Stdout:

```text
initial=[10, 30]
addFirstSmaller=UnsupportedOperationException
addLastLarger=UnsupportedOperationException
addFirstExisting=UnsupportedOperationException
afterRejected=[10, 30]
add20=true
add10Again=false
afterAdd=[10, 20, 30]
ends=10,30
throughSequencedSet=UnsupportedOperationException
emptyAddFirst=UnsupportedOperationException
emptyAddLast=UnsupportedOperationException
emptyStillEmpty=true
```

### 4.1. Phần tử phù hợp với hai đầu vẫn bị từ chối

5 nhỏ hơn 10, còn 40 lớn hơn 30. Tuy nhiên, hai lời gọi định vị tương ứng đều ném UnsupportedOperationException. TreeSet không thực hiện add rồi xác nhận vị trí; nó không cung cấp quyền định vị tường minh.

Lời gọi addFirst(10) cũng thất bại dù 10 đã là phần tử đầu. Không thể biến addFirst thành một lệnh “không làm gì cũng được” chỉ vì phần tử đã ở đúng nơi.

`afterRejected=[10, 30]` xác nhận ba lời gọi thử nghiệm không làm thay đổi tập trong ví dụ.

### 4.2. add vẫn thêm theo quy tắc sắp xếp

add(20) trả true và tập thành `[10, 20, 30]`. add(10) sau đó trả false vì phần tử đã có. Đây là hành vi của add trên tập số dùng thứ tự tự nhiên, không liên quan đến quyền đặt phần tử ở đầu.

getFirst và getLast đọc hai đầu là 10 và 30. Việc đọc phần tử ở hai đầu hoàn toàn tương thích với chính sách sắp xếp.

### 4.3. Kiểu tham chiếu và trạng thái rỗng không mở thêm quyền

throughInterface vẫn trỏ tới đúng TreeSet ban đầu. Vì vậy addFirst qua SequencedSet cũng bị từ chối.

Tập empty chưa có phần tử, nhưng addFirst và addLast vẫn ném ngoại lệ; `emptyStillEmpty=true`. Không cần thử xem tập có rỗng rồi mới quyết định dùng addFirst cho TreeSet. Nếu mục đích là thêm một giá trị vào tập theo Comparator, dùng add.

## 5. Thêm vào tập đã sắp xếp đúng cách

### 5.1. Để Comparator quyết định vị trí

Với TreeSet sửa được, cách thông thường là add(e) hoặc addAll(collection). Phần tử được đặt theo thứ tự tự nhiên hoặc Comparator đã chọn khi tạo tập.

Nếu một tác vụ cần “thêm phần tử nhỏ nhất mới” theo nghiệp vụ, trước hết tính được giá trị đó, rồi vẫn gọi add để tập đặt đúng vị trí. Tên yêu cầu nghiệp vụ không làm addFirst trở thành API được hỗ trợ.

Nếu nghiệp vụ muốn một phần tử bất kỳ đứng trước tất cả phần tử khác bất kể Comparator, yêu cầu đó đã khác với một tập luôn sắp theo Comparator hiện tại. Cần đổi mô hình dữ liệu hoặc thiết kế một khóa ưu tiên phù hợp, thay vì phá hợp đồng của SortedSet.

### 5.2. Phần tử trùng được xét theo phép so sánh

Trong TreeSet<Integer> của ví dụ, 10 so sánh bằng 10 nên add lần nữa không tạo thêm vị trí. Với kiểu dữ liệu tùy chỉnh, Comparator quyết định hai phần tử có được tập xem như cùng một phần tử hay không qua kết quả so sánh bằng 0.

Comparator cần nhất quán với equals để tập thực hiện đúng hợp đồng Set nói chung. Đừng dùng một Comparator chỉ nhằm ép một đối tượng lên đầu mà vô tình làm nhiều phần tử khác nhau so sánh bằng 0 và bị gộp.

Nếu thứ tự phụ thuộc một thuộc tính của phần tử, không sửa thuộc tính đó khi phần tử còn nằm trong TreeSet rồi kỳ vọng cây tự sắp xếp lại. Thiết kế thông thường là loại phần tử khỏi tập trước khi đổi khóa sắp xếp, rồi thêm lại; thao tác cần được phối hợp theo yêu cầu truy cập của chương trình.

### 5.3. Không âm thầm đổi ý nghĩa khi gặp ngoại lệ

Một mẫu xử lý sai về ý định là: thử addFirst; nếu UnsupportedOperationException thì gọi add và coi như yêu cầu đã hoàn thành.

Với TreeSet, add có thể đặt phần tử vào giữa. Khi đó mã không thực hiện yêu cầu “đặt đầu” của người gọi. Nếu chỉ cần bảo đảm phần tử thuộc tập, chọn add ngay từ đầu. Nếu bắt buộc định vị, phải dùng cấu trúc hỗ trợ hoặc báo rõ tiền điều kiện của API.

Không dùng một thao tác có tác dụng sửa dữ liệu như phép dò khả năng vô hại trên một collection bất kỳ. Trên lớp hỗ trợ, lời gọi thử có thể thật sự làm đổi thứ tự.


## 6. Khi cần điều khiển vị trí, hãy chọn chính sách thứ tự phù hợp

### 6.1. LinkedHashSet có thể thay đổi thứ tự gặp

Một tập có thứ tự gặp không nhất thiết phải được sắp theo Comparator. LinkedHashSet là ví dụ: nó giữ tính duy nhất của Set và có thứ tự duyệt mà chương trình có thể điều chỉnh bằng addFirst/addLast trên Java 21.

Với một phần tử mới, addFirst đưa nó lên đầu, addLast đưa nó xuống cuối. Với một phần tử đã có, hai phương thức này có thể chuyển vị trí của phần tử đó đến đầu/cuối; không tạo thêm một bản trùng trong tập.

Điều này khác add thông thường trên LinkedHashSet. Gọi add với phần tử đã tồn tại không chuyển phần tử đó xuống cuối. Phải phân biệt yêu cầu “bảo đảm phần tử có mặt” với yêu cầu “đưa phần tử đến đầu/cuối”.

Hợp đồng cụ thể được mô tả tại [LinkedHashSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html). Đây là hành vi của một cấu trúc hỗ trợ định vị; không thể suy ngược rằng TreeSet cũng phải làm như vậy.

### 6.2. Sao chép sang cấu trúc khác là quyết định thay đổi chính sách

Có thể tạo LinkedHashSet từ các phần tử đang duyệt của TreeSet. Khi mới tạo, bản sao nhận thứ tự duyệt đó. Sau này, addFirst/addLast trên LinkedHashSet có thể làm thứ tự khác hẳn thứ tự so sánh của TreeSet.

Việc này phù hợp nếu tác vụ đã chuyển sang yêu cầu giữ thứ tự thủ công. Nó không phải một cách bổ sung addFirst cho chính TreeSet nguồn. Tập nguồn và tập đích có cấu trúc chứa khác nhau.

Với kiểu tùy chỉnh, cần xét thêm cách xác định tính duy nhất: TreeSet dựa vào so sánh, còn LinkedHashSet sử dụng hợp đồng equals/hashCode của Set dựa trên băm. Nếu Comparator không nhất quán với equals, việc đổi cấu trúc có thể thay đổi ý nghĩa giữ/loại phần tử về sau. Không chọn bản sao chỉ để vượt qua một ngoại lệ mà bỏ qua yêu cầu nghiệp vụ.

## 7. Chương trình 2: thêm mới và di chuyển phần tử trên LinkedHashSet

Lưu vào `SequencedInsertionDemo.java`:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;

public class SequencedInsertionDemo {
    public static void main(String[] args) {
        LinkedHashSet<String> names = new LinkedHashSet<>(List.of("beta", "gamma"));
        names.addFirst("alpha");
        names.addLast("delta");
        System.out.println("afterNewElements=" + names);
        names.addFirst("gamma");
        System.out.println("afterMoveFirst=" + names);
        System.out.println("sizeAfterMove=" + names.size());
        System.out.println("ordinaryAddExisting=" + names.add("alpha"));
        System.out.println("afterOrdinaryAdd=" + names);
        names.addLast("gamma");
        System.out.println("afterMoveLast=" + names);

        TreeSet<Integer> sorted = new TreeSet<>(List.of(3, 1, 2));
        LinkedHashSet<Integer> manualOrder = new LinkedHashSet<>(sorted);
        manualOrder.addFirst(99);
        System.out.println("manualOrder=" + manualOrder);
        System.out.println("originalSorted=" + sorted);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 SequencedInsertionDemo.java
java SequencedInsertionDemo
```

Stdout:

```text
afterNewElements=[alpha, beta, gamma, delta]
afterMoveFirst=[gamma, alpha, beta, delta]
sizeAfterMove=4
ordinaryAddExisting=false
afterOrdinaryAdd=[gamma, alpha, beta, delta]
afterMoveLast=[alpha, beta, delta, gamma]
manualOrder=[99, 1, 2, 3]
originalSorted=[1, 2, 3]
```

### 7.1. Một phần tử mới được đưa đến đầu hoặc cuối

names bắt đầu với beta,gamma. addFirst(alpha) và addLast(delta) tạo `[alpha, beta, gamma, delta]`. Không có Comparator bắt alpha hay delta phải tìm vị trí bằng so sánh chữ.

Đây là thứ tự do các thao tác tạo ra. Không xem việc dãy tên tình cờ dễ đọc như bằng chứng LinkedHashSet tự sắp xếp.

### 7.2. Phần tử có sẵn được chuyển vị trí, không nhân đôi

gamma đã tồn tại. addFirst(gamma) đưa nó lên đầu, tạo `[gamma, alpha, beta, delta]`; size vẫn là 4.

add(alpha) trả false, không đổi thứ tự. Sau đó addLast(gamma) chuyển gamma xuống cuối, tạo `[alpha, beta, delta, gamma]`. Tập vẫn chỉ có một gamma.

Vì addFirst/addLast trả void, ví dụ kiểm tra thứ tự và size sau lời gọi. Không có boolean từ chúng để báo “vừa thêm mới hay chỉ chuyển vị trí”.

### 7.3. Bản sao thứ tự thủ công không còn tự sắp theo TreeSet

TreeSet số được in là `[1, 2, 3]` dù tạo từ dữ liệu 3,1,2. LinkedHashSet sao chép từ nó ban đầu có cùng thứ tự, rồi addFirst(99) làm bản sao thành `[99, 1, 2, 3]`.

TreeSet nguồn vẫn là `[1, 2, 3]`. Nếu tác vụ yêu cầu mọi phần tử luôn tăng dần, bản sao sau thao tác không thỏa yêu cầu đó. Nếu tác vụ muốn ưu tiên hiển thị 99 trước, cấu trúc có thứ tự thủ công có thể phù hợp hơn.

## 8. reversed và tập con không bỏ chính sách sắp xếp

### 8.1. Đảo chiều nhìn không biến SortedSet thành danh sách tự do

TreeSet là NavigableSet. Trên Java 21, reversed của NavigableSet tương đương descendingSet: nhìn các phần tử theo chiều ngược của thứ tự đang có.

Với TreeSet tự nhiên chứa 10,20,30,40, view ngược có thứ tự 40,30,20,10. “Đầu” trong view ngược là 40; “cuối” trong view ngược là 10.

Tuy vậy, view vẫn là tập có chính sách sắp xếp. Không dùng reversed để mở quyền addFirst/addLast. Thêm thông thường bằng add trên view được đặt theo thứ tự của tập và phản ánh lên tập nguồn nếu view sửa được.

Quan hệ đảo chiều của API được nêu tại [NavigableSet.reversed — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html). Với TreeSet trong ví dụ, các view chia sẻ dữ liệu nguồn; chúng không phải các bản sao độc lập.

### 8.2. Tập con giữ thêm ràng buộc khoảng

Một view subSet của TreeSet chỉ cho phép làm việc với các phần tử thuộc khoảng được chọn. Nó vẫn duy trì thứ tự, và một lần thêm hợp lệ phải thỏa cả giới hạn khoảng lẫn các điều kiện phần tử của tập.

Hai lỗi khác nhau:

- addFirst/addLast yêu cầu định vị, nên bị từ chối trên view TreeSet này.
- add với giá trị ngoài khoảng là thao tác thêm theo thứ tự nhưng vi phạm giới hạn view, nên ném IllegalArgumentException.

Không giải thích mọi ngoại lệ của tập con bằng một nguyên nhân “không sửa được”. View có thể sửa trong phạm vi, nhưng không hỗ trợ định vị tường minh và không chấp nhận giá trị vượt khoảng.

## 9. Chương trình 3: view ngược và view theo khoảng

Lưu vào `SortedViewsDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedViewsDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        NavigableSet<Integer> base = new TreeSet<>(List.of(10, 20, 30, 40));
        NavigableSet<Integer> reverse = base.reversed();
        System.out.println("reverseInitial=" + reverse);
        expectUnsupported("reverseAddFirst", () -> reverse.addFirst(50));
        expectUnsupported("reverseAddLast", () -> reverse.addLast(5));
        System.out.println("reverseAdd25=" + reverse.add(25));
        System.out.println("baseAfterAdd=" + base);
        System.out.println("reverseAfterAdd=" + reverse);
        System.out.println("reverseRemoveFirst=" + reverse.removeFirst());
        System.out.println("baseAfterReverseRemove=" + base);

        SortedSet<Integer> middle = base.subSet(15, true, 30, false);
        System.out.println("middleInitial=" + middle);
        expectUnsupported("middleAddFirst", () -> middle.addFirst(17));
        System.out.println("middleAdd17=" + middle.add(17));
        try {
            middle.add(50);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("middleOutside=IllegalArgumentException");
        }
        System.out.println("middleAfterAdd=" + middle);
        System.out.println("middleRemoveLast=" + middle.removeLast());
        System.out.println("baseFinal=" + base);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 SortedViewsDemo.java
java SortedViewsDemo
```

Stdout:

```text
reverseInitial=[40, 30, 20, 10]
reverseAddFirst=UnsupportedOperationException
reverseAddLast=UnsupportedOperationException
reverseAdd25=true
baseAfterAdd=[10, 20, 25, 30, 40]
reverseAfterAdd=[40, 30, 25, 20, 10]
reverseRemoveFirst=40
baseAfterReverseRemove=[10, 20, 25, 30]
middleInitial=[20, 25]
middleAddFirst=UnsupportedOperationException
middleAdd17=true
middleOutside=IllegalArgumentException
middleAfterAdd=[17, 20, 25]
middleRemoveLast=25
baseFinal=[10, 17, 20, 30]
```

### 9.1. add trên view ngược vẫn đặt theo so sánh

reverse ban đầu là `[40, 30, 20, 10]`. addFirst(50) và addLast(5) đều thất bại dù các giá trị này có vẻ phù hợp với hai đầu của chiều ngược.

reverse.add(25) thành công. Tập nguồn trở thành `[10, 20, 25, 30, 40]`, còn view ngược hiển thị `[40, 30, 25, 20, 10]`. Không có phần tử mới bị ép đứng ở đầu hoặc cuối.

### 9.2. Xóa đầu của view ngược là xóa cuối theo chiều nguồn

reverse.removeFirst lấy và xóa 40. Tập nguồn sau đó là `[10, 20, 25, 30]`.

Xóa phần tử không yêu cầu đặt lại vị trí tùy ý của một phần tử còn tồn tại. Các phần tử còn lại vẫn đúng thứ tự nên TreeSet sửa được có thể hỗ trợ thao tác xóa ở hai đầu, dù nó không hỗ trợ thêm theo vị trí.

### 9.3. Khoảng [15,30) và ba lời gọi khác nhau

middle dùng overload của NavigableSet với cận dưới bao gồm 15, cận trên không bao gồm 30. Dữ liệu ban đầu trong khoảng là 20,25.

- middle.addFirst(17) ném UnsupportedOperationException vì định vị không được hỗ trợ.
- middle.add(17) trả true vì 17 hợp lệ trong khoảng và chưa có.
- middle.add(50) ném IllegalArgumentException vì 50 nằm ngoài khoảng.

Sau đó middle là `[17, 20, 25]`. middle.removeLast xóa 25 khỏi view và khỏi tập nguồn. Tập nguồn cuối là `[10, 17, 20, 30]`.

Biến middle khai báo SortedSet dù được tạo từ một TreeSet có khả năng NavigableSet. Điều đó vẫn cho gọi addFirst, getFirst hoặc removeLast trên Java 21. Kiểu tham chiếu không thay đổi chính sách định vị hoặc giới hạn khoảng của đối tượng thực tế.


## 10. Các thao tác khác trên hai đầu phải được xét riêng

### 10.1. Đọc đầu/cuối không phải thêm đầu/cuối

getFirst và getLast trả phần tử tại hai đầu theo thứ tự của collection đang xét. Với SortedSet, chúng tương ứng với first và last. Chúng không xóa phần tử.

Không mặc định “đầu luôn là số nhỏ nhất”. Nếu TreeSet dùng Comparator.reverseOrder, thứ tự là 30,20,10; getFirst trả 30 và getLast trả 10. “Đầu” được hiểu theo Comparator của tập, không theo trực giác tăng dần của số.

Khi tập sửa được đang rỗng, không có phần tử để getFirst/getLast trả về; các thao tác đọc này ném NoSuchElementException. Không dùng null làm kết quả rỗng của chúng.

### 10.2. Xóa ở hai đầu có thể được hỗ trợ

TreeSet sửa được hỗ trợ removeFirst và removeLast trên Java 21. Chúng trả phần tử đã xóa; các phần tử còn lại vẫn duy trì thứ tự.

Với một TreeSet rỗng, removeFirst/removeLast ném NoSuchElementException. NavigableSet còn có pollFirst/pollLast trả null khi rỗng. Ví dụ của bài dùng Integer không null nên kết quả null của pollFirst minh họa trường hợp rỗng rõ ràng.

Không khái quát rằng mọi SortedSet đều cho xóa. Các thao tác xóa vẫn có thể không được hỗ trợ trên một view không cho sửa hoặc một triển khai có giới hạn tương ứng. Cần xét từng thao tác trên đối tượng thực tế.

### 10.3. Từ chối định vị khác với không cho sửa mọi dữ liệu

TreeSet thông thường từ chối addFirst/addLast vì chính sách thứ tự, nhưng có thể add và remove.

Một view do Collections.unmodifiableSortedSet tạo ra còn có ràng buộc khác: không cho người dùng sửa dữ liệu qua view đó. Vì vậy ngay cả add hoặc removeFirst cũng bị từ chối, dù TreeSet nguồn sửa được.

View không cho sửa không nhất thiết là bản dữ liệu độc lập bất biến theo thời gian. Nếu một tham chiếu khác còn sửa được tập nguồn, việc đọc qua view có thể thấy dữ liệu nguồn mới. Hợp đồng này được mô tả tại [Collections.unmodifiableSortedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

Không dùng addFirst làm phép kiểm tra “collection này có sửa được không”: TreeSet sửa được cũng từ chối nó. Cũng không dùng add thành công để suy ra mọi thao tác sửa khác sẽ thành công.

## 11. Chương trình 4: Comparator, xóa hai đầu và view không cho sửa

Lưu vào `SortedOptionalOperationsDemo.java`:

```java
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedOptionalOperationsDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    static void expectEmpty(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (java.util.NoSuchElementException expected) {
            System.out.println(label + "=NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        TreeSet<Integer> descending = new TreeSet<>(Comparator.reverseOrder());
        descending.addAll(List.of(10, 20, 30));
        System.out.println("descending=" + descending);
        System.out.println("ends=" + descending.getFirst() + "," + descending.getLast());
        expectUnsupported("descendingAddFirst", () -> descending.addFirst(40));
        expectUnsupported("descendingAddLast", () -> descending.addLast(0));
        System.out.println("removeFirst=" + descending.removeFirst());
        System.out.println("removeLast=" + descending.removeLast());
        System.out.println("afterEndRemovals=" + descending);

        SortedSet<Integer> readOnly = Collections.unmodifiableSortedSet(descending);
        System.out.println("readOnlyFirst=" + readOnly.getFirst());
        expectUnsupported("readOnlyAdd", () -> readOnly.add(25));
        expectUnsupported("readOnlyRemoveFirst", () -> readOnly.removeFirst());
        descending.add(15);
        System.out.println("readOnlyAfterSourceAdd=" + readOnly);

        TreeSet<Integer> empty = new TreeSet<>();
        expectEmpty("emptyGetFirst", () -> empty.getFirst());
        expectEmpty("emptyRemoveFirst", () -> empty.removeFirst());
        System.out.println("emptyPollFirst=" + empty.pollFirst());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 SortedOptionalOperationsDemo.java
java SortedOptionalOperationsDemo
```

Stdout:

```text
descending=[30, 20, 10]
ends=30,10
descendingAddFirst=UnsupportedOperationException
descendingAddLast=UnsupportedOperationException
removeFirst=30
removeLast=10
afterEndRemovals=[20]
readOnlyFirst=20
readOnlyAdd=UnsupportedOperationException
readOnlyRemoveFirst=UnsupportedOperationException
readOnlyAfterSourceAdd=[20, 15]
emptyGetFirst=NoSuchElementException
emptyRemoveFirst=NoSuchElementException
emptyPollFirst=null
```

### 11.1. Đầu/cuối đi theo Comparator

descending có thứ tự `[30, 20, 10]` và ends in `30,10`. addFirst(40) và addLast(0) bị từ chối dù hai giá trị phù hợp với hai đầu theo thứ tự giảm.

removeFirst xóa 30; removeLast xóa 10. Tập còn `[20]`. Kết quả cho thấy không thể gom mọi thao tác có từ First/Last vào cùng một mức hỗ trợ.

### 11.2. View không cho sửa vẫn đọc được và còn dựa trên nguồn

readOnly đọc được phần tử đầu 20. add(25) và removeFirst đều ném UnsupportedOperationException vì được gọi qua view không cho sửa.

Lời gọi descending.add(15) thực hiện qua tham chiếu TreeSet nguồn nên thành công. Sau đó readOnly đọc thấy `[20, 15]`, theo Comparator giảm của nguồn.

Ví dụ không sử dụng nhiều luồng. Việc hai tham chiếu chia sẻ dữ liệu không có nghĩa TreeSet tự an toàn cho truy cập đồng thời; các yêu cầu đồng bộ là một vấn đề riêng.

### 11.3. Không có phần tử khác với không hỗ trợ thao tác

empty là TreeSet sửa được, đang rỗng. getFirst và removeFirst ném NoSuchElementException vì không có phần tử, còn pollFirst trả null.

Trường hợp này khác addFirst trên tập rỗng ở chương trình 1: thao tác định vị bị từ chối bằng UnsupportedOperationException. Nếu đối tượng đồng thời có nhiều giới hạn, không viết logic dựa trên một thứ tự kiểm tra ngoại lệ chung cho mọi triển khai. Các ví dụ thử riêng từng điều kiện với đối tượng cụ thể.

## 12. Thiết kế mã gọi theo đúng yêu cầu

### 12.1. Chọn thao tác từ ý định

| Ý định của mã gọi | Lựa chọn phù hợp | Điều cần bảo đảm |
|---|---|---|
| Giữ các giá trị duy nhất và luôn theo Comparator | TreeSet với add/addAll | Phần tử so sánh được, Comparator đúng, đối tượng cho phép thêm |
| Đọc phần tử đầu hoặc cuối của tập đã sắp xếp | getFirst/getLast hoặc first/last | Có phần tử; dùng đúng nghĩa đầu/cuối theo Comparator |
| Lấy và xóa phần tử đầu/cuối | removeFirst/removeLast trên TreeSet sửa được | Không rỗng và thao tác xóa được hỗ trợ |
| Lấy và xóa với kết quả null khi rỗng | pollFirst/pollLast của NavigableSet | Hiểu chính sách null của nguồn và thao tác xóa |
| Điều khiển thứ tự gặp nhưng vẫn giữ tính duy nhất | LinkedHashSet với addFirst/addLast | Chấp nhận thứ tự thủ công thay vì luôn sắp theo Comparator |
| Cần nhiều vị trí có phần tử trùng và thứ tự tự chọn | Một List phù hợp | Yêu cầu đã khác tính duy nhất của Set |
| Chỉ cung cấp quyền đọc một tập đã sắp xếp | View unmodifiable thích hợp | Không coi view là bản sao sâu hay ảnh chụp cố định |

Không chọn chỉ dựa trên tên “collection có thứ tự”. Cần hỏi thứ tự đến từ so sánh, lần thêm hay thao tác điều chỉnh vị trí.

### 12.2. Chữ ký SequencedSet chưa đủ để hứa định vị được

Một phương thức nhận SequencedSet<E> có thể nhận LinkedHashSet, TreeSet hoặc view không cho sửa. Vì vậy chỉ nhìn chữ ký này chưa đủ để hứa rằng addFirst luôn thành công.

Nếu phương thức thực sự cần định vị, phải công bố yêu cầu đối số hỗ trợ thao tác đó hoặc tự sở hữu một cấu trúc phù hợp bên trong. Nếu đầu vào chỉ dùng để đọc, có thể tạo một cấu trúc kết quả mới với chính sách thứ tự đã chọn.

Không tự nhận biết khả năng bằng một danh sách vài lớp rồi coi mọi lớp khác giống nhau. Các wrapper và lớp tùy chỉnh có thể có giới hạn riêng. Hợp đồng của API nhận và trả dữ liệu cần làm rõ quyền sửa.

### 12.3. Phiên bản Java là một phần của hợp đồng triển khai

Các ví dụ sử dụng API thêm từ Java 21, nên cả mức biên dịch và môi trường chạy phải phù hợp. Dùng một JDK mới nhưng đặt --release 17 vẫn không làm API Java 21 xuất hiện trong mã nguồn đang biên dịch cho Java 17.

Kiểm tra javac và java đang trỏ đến bản JDK nào nếu có nhiều bản cài đặt. Không chỉ đổi tên kiểu biến hoặc ép kiểu để giải quyết lỗi thiếu API do phiên bản.

Trong mã phải giữ tương thích Java 17, TreeSet vẫn có add, first, last và các API cũ tương ứng; không gọi những phương thức mới như addFirst/getFirst thông qua API Java 21 rồi kỳ vọng chạy nguyên dạng trên Java 17.

### 12.4. Phần tử hợp lệ vẫn là điều kiện riêng

add thông thường cũng có thể thất bại vì các phần tử không so sánh được, null không được nguồn chấp nhận, hoặc giá trị nằm ngoài khoảng view. “Dùng add thay addFirst cho TreeSet” không có nghĩa bỏ qua mọi tiền điều kiện khác.

Ví dụ trong bài dùng số nguyên không null hoặc chuỗi với hợp đồng đơn giản để tách rõ lỗi không hỗ trợ định vị. Khi đổi sang dữ liệu nghiệp vụ, cần kiểm tra thêm Comparator, equals/hashCode và giới hạn view tương ứng.

## 13. Lỗi phổ biến và cách kiểm tra

| Lỗi | Vì sao sai | Cách sửa cách hiểu |
|---|---|---|
| Có addFirst trong gợi ý IDE nên chắc chắn dùng được | Có phương thức ở mức kiểu không bảo đảm hỗ trợ lúc chạy | Đọc hợp đồng của đối tượng thực tế |
| TreeSet rỗng thì addFirst chắc hợp lệ | TreeSet từ chối thao tác định vị ngay cả khi rỗng | Dùng add nếu cần thêm theo thứ tự |
| Chỉ thử giá trị nhỏ hơn mọi phần tử để tránh ngoại lệ | Việc từ chối không phụ thuộc vị trí dự đoán của giá trị | Không dùng addFirst/addLast trên TreeSet |
| Đổi biến thành SequencedSet để mở quyền | Vẫn cùng đối tượng TreeSet | Chọn cấu trúc đúng chính sách nếu cần định vị |
| Gặp UnsupportedOperationException rồi kết luận tập không sửa được | Có thể chỉ thao tác định vị không được hỗ trợ | Xét từng thao tác và các wrapper |
| Catch lỗi addFirst rồi gọi add như thể cùng ý nghĩa | add không bảo đảm đặt đầu | Chọn rõ yêu cầu thêm theo thứ tự hay định vị |
| Dùng add để chuyển phần tử cũ của LinkedHashSet xuống cuối | add phần tử cũ không đổi thứ tự gặp | Dùng addLast khi thực sự muốn chuyển cuối |
| Mong addFirst trên Set tạo thêm bản trùng | Set vẫn giữ tính duy nhất | Dùng cấu trúc khác nếu yêu cầu có phần tử trùng |
| Cho rằng reversed bỏ chính sách so sánh | View ngược vẫn có thứ tự được ràng buộc | Dùng add theo thứ tự, không định vị |
| Nhầm thêm ngoài khoảng với không hỗ trợ định vị | IllegalArgumentException và UnsupportedOperationException là hai điều kiện khác nhau | Kiểm tra khoảng và loại thao tác riêng |
| Cho getFirst trả null khi tập rỗng | Thao tác này ném NoSuchElementException | Kiểm tra rỗng hoặc chọn API có hợp đồng khác |
| Xem view không cho sửa như bản sao không bao giờ đổi | Tập nguồn vẫn có thể bị sửa qua tham chiếu khác | Tạo bản sao nếu yêu cầu dữ liệu chứa độc lập |

Khi kiểm tra mã sử dụng API này, nên có các trường hợp: tập có dữ liệu; tập rỗng; phần tử mới; phần tử đã có; Comparator tăng và giảm; view ngược; view theo khoảng; view không cho sửa. Kiểm tra cả dữ liệu sau lời gọi để phát hiện việc vô tình đổi thứ tự hoặc đổi tập nguồn.

Các helper expectUnsupported trong bài phục vụ ví dụ xác minh. Trong mã nghiệp vụ, không catch chung Exception rồi bỏ qua: điều đó che cả lỗi phần tử, lỗi khoảng và những lỗi không liên quan khác.

## 14. Tự kiểm tra và thực hành

### 14.1. Câu hỏi với đáp án

1. **Vì sao SortedSet có addFirst từ Java 21 nhưng TreeSet lại ném ngoại lệ?** SortedSet tham gia hệ SequencedSet, còn vị trí trong TreeSet do so sánh quyết định. API chung có thao tác tùy chọn; TreeSet không hỗ trợ định vị tường minh.
2. **TreeSet chứa 10,30; addFirst(5) có được vì 5 đúng là nhỏ nhất không?** Không. TreeSet ném UnsupportedOperationException. Muốn thêm 5 theo quy tắc sắp xếp, gọi add(5).
3. **Đổi sang biến SequencedSet có thay hành vi không?** Không. Đối tượng vẫn là TreeSet, nên giới hạn của nó vẫn giữ nguyên.
4. **TreeSet không hỗ trợ addLast có chứng minh removeLast cũng không được hỗ trợ không?** Không. TreeSet sửa được có thể xóa phần tử cuối, còn không cho định vị phần tử bằng addLast.
5. **LinkedHashSet có beta,gamma; addFirst(gamma) làm size tăng không?** Không. gamma được chuyển lên đầu nếu cần, không được nhân đôi.
6. **add(alpha) với alpha đã có trong LinkedHashSet có đưa alpha xuống cuối không?** Không. add phần tử cũ không đổi thứ tự gặp; addLast mới thể hiện yêu cầu chuyển cuối.
7. **TreeSet có Comparator giảm thì getFirst trả số nhỏ nhất hay lớn nhất trong ví dụ số không null?** Với Comparator.reverseOrder và các số trong ví dụ, getFirst trả số lớn nhất theo thứ tự số thông thường, vì nó đứng đầu theo Comparator giảm.
8. **View ngược của TreeSet có cho addFirst không?** Không. Nó vẫn chịu chính sách định vị của tập đã sắp xếp.
9. **Vì sao subSet có thể add(17) được nhưng addFirst(17) không được?** 17 có thể hợp lệ trong khoảng cho thêm thông thường; thao tác định vị vẫn không được hỗ trợ.
10. **Một view unmodifiable có add bị từ chối thì có kết luận tập nguồn không bao giờ đổi được không?** Không. Nguồn có thể còn được sửa qua tham chiếu khác; view cung cấp giới hạn quyền sửa qua chính nó.

### 14.2. Bài tập: phân loại thao tác trên cùng dữ liệu

Tạo TreeSet<Integer> với dữ liệu 9,3,6. Trước khi chạy, dự đoán riêng từng thao tác: add(1), addFirst(0), addLast(10), getFirst, removeLast.

Thực hiện trên những tập mới có cùng dữ liệu nếu muốn các phép thử độc lập. Kỳ vọng:

- add(1) thành công và tập có thứ tự 1,3,6,9.
- addFirst(0) và addLast(10) ném UnsupportedOperationException.
- getFirst trên tập ban đầu trả 3 mà không xóa.
- removeLast trên tập ban đầu trả 9 và còn 3,6.

Giải thích bằng chính sách thứ tự và hỗ trợ thao tác, không chỉ ghi tên ngoại lệ.

### 14.3. Bài tập: chọn cấu trúc từ yêu cầu

Một màn hình cần giữ các mã duy nhất theo thứ tự tăng dần. Màn hình khác cần cho người dùng đưa một mã đã có lên đầu danh sách ưu tiên.

Với màn hình đầu, dùng TreeSet và add theo quy tắc sắp xếp. Với màn hình sau, một LinkedHashSet có thao tác addFirst có thể phù hợp nếu vẫn cần tính duy nhất và chỉ cần điều khiển đầu/cuối.

Hãy nêu rõ điều gì bị thay đổi nếu sao chép tập tăng dần sang LinkedHashSet rồi chuyển một mã lớn lên đầu: dữ liệu chứa đã độc lập về cấu trúc, còn chính sách luôn tăng dần không được duy trì ở bản sao đó.

### 14.4. Bài tập: xem đầu theo Comparator và view

Tạo TreeSet<Integer> với Comparator giảm chứa 4,8,12. Dự đoán getFirst trên tập gốc, getFirst trên reversed, rồi thử addFirst trên từng phía.

Kỳ vọng đầu của tập gốc là 12; đầu của view ngược là 4. Cả hai lời gọi addFirst vẫn bị từ chối. Nếu muốn thêm 10 vào tập, dùng add và quan sát vị trí 10 theo hai chiều nhìn.

## 15. Nguồn đối chiếu và kiểm chứng

- [SortedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html): quan hệ với SequencedSet, thao tác định vị không được hỗ trợ, đọc/xóa theo hai đầu.
- [TreeSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html): thứ tự theo so sánh và hành vi addFirst/addLast của lớp cụ thể.
- [SequencedCollection — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): các thao tác chung ở hai đầu và tính tùy chọn của thao tác sửa.
- [SequencedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): Set có thứ tự gặp, vẫn giữ tính duy nhất.
- [LinkedHashSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html): định vị phần tử mới hoặc chuyển phần tử đã có.
- [NavigableSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html): reversed, removeFirst/removeLast và view theo khoảng.
- [Collections — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): view unmodifiableSortedSet.

Bốn chương trình đầy đủ được biên dịch với `javac --release 21 -encoding UTF-8` và chạy bằng JDK 21.0.9. Stdout trong bài khớp kết quả chạy. Những lời gọi dự kiến ném ngoại lệ được kiểm tra trực tiếp, đồng thời in dữ liệu trước/sau để minh họa khả năng sửa và quan hệ giữa tập nguồn với view.
