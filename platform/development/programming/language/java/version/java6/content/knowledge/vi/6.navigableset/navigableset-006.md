# TreeSet triển khai NavigableSet

## 1. Từ yêu cầu nghiệp vụ đến cấu trúc cụ thể

Giả sử ứng dụng lưu các mức giá cho phép: 40, 10, 30 và 20. Mỗi mức chỉ cần giữ một lần, nhưng ứng dụng còn phải tìm mức ngay dưới ngân sách, mức đầu tiên đủ yêu cầu, hoặc duyệt từ thấp lên cao.

Một tập hợp chỉ trả lời “có giá trị này không?” chưa đủ. Ta cần ba khả năng:

1. Không lưu phần tử trùng theo quy tắc so sánh.
2. Duy trì phần tử trong một thứ tự xác định.
3. Tìm phần tử lân cận hoặc lấy một khoảng theo thứ tự ấy.

`NavigableSet<E>` mô tả hợp đồng đáp ứng các khả năng này. `TreeSet<E>` là một lớp cài đặt cụ thể. Cách khai báo thường gặp là:

```java
NavigableSet<Integer> prices = new TreeSet<>();
```

Đây là khai báo minh họa, cần đặt trong phương thức và import `java.util.NavigableSet`, `java.util.TreeSet`. Người gọi làm việc với khả năng điều hướng của giao diện; đối tượng `TreeSet` chịu trách nhiệm lưu và tổ chức dữ liệu.

Bài này giải thích quan hệ **hợp đồng → cách cài đặt → quy tắc so sánh → hành vi quan sát được → cách chọn dùng**. Các API được dùng vẫn áp dụng trong Java hiện đại; ví dụ dùng cú pháp Java 17 trở lên.

## 2. Giao diện quy định điều gì, lớp quyết định điều gì?

Có thể nhìn quan hệ khả năng theo sơ đồ rút gọn:

```text
Set
  -> SortedSet
      -> NavigableSet
          <- được cài đặt bởi TreeSet
```

- `Set`: mô hình tập hợp.
- `SortedSet`: thêm thứ tự cho phần tử.
- `NavigableSet`: thêm tìm lân cận, duyệt đảo chiều và lấy khoảng với biên rõ ràng.
- `TreeSet`: cung cấp cách lưu dữ liệu để thực hiện các thao tác ấy.

Giao diện `NavigableSet` không yêu cầu mọi lớp cài đặt phải dùng cùng thuật toán hoặc có cùng đặc tính đồng thời. Khi cần biết chi phí thao tác, cách nhận diện trùng và điều kiện sử dụng an toàn, phải xem lớp thực tế đang được khởi tạo.

Theo tài liệu [TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html), lớp này dựa trên `TreeMap`, dùng thứ tự tự nhiên hoặc `Comparator` được cung cấp, và bảo đảm O(log n) cho `add`, `remove`, `contains`.

## 3. Vì sao cấu trúc cây giúp tìm theo thứ tự?

Mô hình giải thích đơn giản là mỗi lần so sánh với một giá trị trong cây, phép tìm quyết định đi về phía trước hay phía sau trong thứ tự. Không phải duyệt mọi phần tử để biết giá trị cần tìm nằm phía nào.

`TreeMap`, nền tảng của `TreeSet`, dùng cây đỏ đen, một dạng cây tìm kiếm tự cân bằng. Cân bằng giúp tránh tình huống cây liên tục lệch thành một chuỗi dài khi dữ liệu được chèn theo thứ tự. Xem mô tả cài đặt của [TreeMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html).

Hình dưới chỉ minh họa quan hệ thứ tự, không mô tả chính xác hình dạng hay màu nút mà một phiên bản JDK sẽ tạo:

```text
        30
       /  \
     20    40
    /
   10
```

Với ví dụ này, tìm 25 sẽ đi về phía nhỏ hơn 30 rồi lớn hơn 20. Dù 25 không tồn tại, quá trình tìm vẫn có đủ thông tin để xác định hai ứng viên lân cận là 20 và 30.

Không nên viết mã phụ thuộc vào nút gốc cụ thể, thứ tự xoay cây hoặc màu của một phần tử. Chương trình cần dựa trên hợp đồng thứ tự và kết quả truy vấn, còn việc tổ chức cây là trách nhiệm của lớp cài đặt.

## 4. Hai cách xác định thứ tự

### Thứ tự tự nhiên

`new TreeSet<Integer>()` dùng thứ tự tự nhiên của `Integer`: số nhỏ đứng trước số lớn. Các phần tử phải hỗ trợ so sánh phù hợp.

Với kiểu tự định nghĩa, nếu không có thứ tự tự nhiên phù hợp, hãy cung cấp comparator thay vì giả định Java biết sắp đối tượng theo trường nào.

### Comparator được cung cấp

Có thể tạo tập hợp số nguyên giảm dần bằng:

```java
NavigableSet<Integer> descending =
        new TreeSet<>(Comparator.reverseOrder());
```

Đoạn minh họa này cần thêm import `java.util.Comparator`. Khi ấy số 40 đứng trước số 30. `first()` trả phần tử đứng đầu theo comparator, không nhất thiết là số nhỏ nhất theo số học.

Với đối tượng, comparator cần thể hiện thứ tự nghiệp vụ. Chẳng hạn xếp công việc theo mức ưu tiên rồi theo mã. Dùng `Comparator.comparingInt` và `thenComparing` giúp diễn đạt từng tiêu chí thay vì tự trừ hai số có nguy cơ tràn.

Comparator phải nhất quán: quan hệ trước/sau/bằng cần đáp ứng hợp đồng so sánh. Thứ tự nhất quán với `equals` nghĩa là so sánh trả 0 đúng khi hai phần tử bằng nhau theo `equals`. Xem [Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html).

## 5. TreeSet nhận diện trùng bằng phép so sánh

Điều rất dễ bỏ sót: `TreeSet` dùng `compareTo` hoặc `Comparator.compare` để quyết định hai phần tử có được coi là cùng một phần tử của tập hợp hay không.

- Kết quả nhỏ hơn 0: phần tử thứ nhất đứng trước.
- Kết quả lớn hơn 0: phần tử thứ nhất đứng sau.
- Kết quả bằng 0: hai phần tử được coi là tương đương trong `TreeSet`.

Vì vậy một comparator chỉ so sánh độ ưu tiên sẽ coi hai công việc khác mã nhưng cùng độ ưu tiên là trùng. Lần thêm thứ hai trả `false`; tập hợp không giữ cả hai và không dùng thao tác đó để thay thế đối tượng trước.

Đó có thể là lỗi mô hình dữ liệu. Nếu cần giữ các công việc khác nhau, phải thiết kế thứ tự và sự bằng nhau phù hợp, hoặc dùng cấu trúc có thể biểu diễn nhiều công việc trong cùng một nhóm ưu tiên.

Tài liệu [TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html) nhấn mạnh rằng thứ tự cần nhất quán với `equals` để tuân thủ đầy đủ hợp đồng của `Set`. Không thể giả định chỉ sửa `hashCode` sẽ làm hai phần tử có kết quả so sánh 0 cùng tồn tại trong cây.

## 6. Chương trình Java: quan sát hợp đồng qua TreeSet

Chương trình sau có hai phần độc lập:

- Các mức giá là `Integer`, dùng thứ tự tự nhiên.
- Các công việc là `record Task`, có cả độ ưu tiên và mã tham gia định nghĩa giá trị.

Lưu tệp `TreeSetNavigableDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class TreeSetNavigableDemo {
    record Task(int priority, String id) {}

    public static void main(String[] args) {
        NavigableSet<Integer> prices =
                new TreeSet<>(List.of(40, 10, 30, 20));

        System.out.println("prices=" + prices);
        System.out.println("add.20=" + prices.add(20));
        System.out.println("contains.25=" + prices.contains(25));
        System.out.println("floor.25=" + prices.floor(25));
        System.out.println("ceiling.25=" + prices.ceiling(25));
        System.out.println("lower.20=" + prices.lower(20));
        System.out.println("higher.20=" + prices.higher(20));
        System.out.println("first=" + prices.first());
        System.out.println("last=" + prices.last());
        System.out.println("range="
                + prices.subSet(20, true, 40, false));
        System.out.println("descending=" + prices.descendingSet());
        System.out.println("poll.first=" + prices.pollFirst());
        System.out.println("after.poll=" + prices);

        Comparator<Task> byPriority =
                Comparator.comparingInt(Task::priority);
        NavigableSet<Task> incomplete =
                new TreeSet<>(byPriority);
        incomplete.add(new Task(1, "A"));
        System.out.println("priority.only.add.B="
                + incomplete.add(new Task(1, "B")));
        System.out.println("priority.only.size="
                + incomplete.size());

        Comparator<Task> byPriorityAndId =
                byPriority.thenComparing(Task::id);
        NavigableSet<Task> tasks =
                new TreeSet<>(byPriorityAndId);
        tasks.add(new Task(2, "C"));
        tasks.add(new Task(1, "B"));
        tasks.add(new Task(1, "A"));
        System.out.println("task.ids="
                + tasks.stream().map(Task::id).toList());
        System.out.println("task.duplicate="
                + tasks.add(new Task(1, "A")));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 TreeSetNavigableDemo.java
java TreeSetNavigableDemo
```

Stdout:

```text
prices=[10, 20, 30, 40]
add.20=false
contains.25=false
floor.25=20
ceiling.25=30
lower.20=10
higher.20=30
first=10
last=40
range=[20, 30]
descending=[40, 30, 20, 10]
poll.first=10
after.poll=[20, 30, 40]
priority.only.add.B=false
priority.only.size=1
task.ids=[A, B, C]
task.duplicate=false
```

Tự đối chiếu:

1. Thứ tự duyệt khác thứ tự thêm ban đầu vì cây duy trì thứ tự so sánh.
2. Không có đúng giá trị 25, nhưng vẫn tìm được mức ngay dưới và ngay trên nó.
3. `subSet` lấy 20 và 30 vì bao gồm 20, loại 40.
4. `pollFirst` vừa trả về 10 vừa xóa 10; các truy vấn `floor/ceiling` trước đó không xóa dữ liệu.
5. Comparator chỉ theo ưu tiên làm mất khả năng giữ cả A và B.
6. Comparator theo ưu tiên rồi mã giữ được A và B, đồng thời coi hai `Task(1, "A")` là trùng. Với các mã khác null trong ví dụ, thứ tự này phù hợp với sự bằng nhau của record hai thành phần.

## 7. Những hành vi cần biết khi dùng thực tế

### Truy vấn lân cận có thể không có kết quả

`lower`, `floor`, `ceiling`, `higher` trả `null` khi không có phần tử thỏa điều kiện. `pollFirst/pollLast` cũng trả `null` khi rỗng. Trong khi đó, `first/last` ném `NoSuchElementException` khi tập hợp rỗng. Xem [NavigableSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableSet.html).

Nếu dùng số nguyên, nhận kết quả điều hướng bằng `Integer` rồi kiểm tra trước khi chuyển sang `int`. Tự mở hộp `null` không tạo ra giá trị mặc định.

### Quy tắc null phụ thuộc thứ tự

`TreeSet` với thứ tự tự nhiên không chấp nhận `null`. Một comparator được thiết kế cho null có thể cho phép nó, nhưng khi ấy kết quả null từ phương thức điều hướng dễ gây mơ hồ.

Với tập hợp dùng để tra cứu lân cận, thường nên quy định phần tử khác null để việc không có kết quả được diễn đạt rõ. Không khái quát rằng mọi constructor và mọi comparator của `TreeSet` đều có cùng cách xử lý null.

### Thay đổi trường dùng để so sánh có thể phá giả định của cây

Nếu một công việc đang nằm trong cây rồi độ ưu tiên của chính đối tượng ấy bị sửa, cây không tự nhận thông báo để di chuyển nó đến vị trí mới.

Trong chương trình, record giữ các thành phần bất biến nên tránh được kiểu sửa trực tiếp đó. Với lớp có thể thay đổi, hãy xóa đối tượng khỏi cây trước khi đổi khóa so sánh rồi thêm lại. Việc thay đổi comparator theo trạng thái bên ngoài cũng có thể gây vấn đề tương tự: cùng hai phần tử không nên hôm nay so sánh theo một cách, ngày mai tự đổi sang cách khác trong cùng tập hợp.

### Khung nhìn không phải bản sao

`subSet`, `headSet`, `tailSet` và `descendingSet` tạo khung nhìn liên kết với dữ liệu gốc. Xóa phần tử qua khung nhìn có thể xóa ở gốc; thêm qua khung nhìn có giới hạn phải nằm trong khoảng cho phép.

Khi cần một tập hợp riêng, tạo bản sao cấu trúc có chủ đích. Nếu thứ tự tùy chỉnh quan trọng, bảo đảm bản sao dùng đúng comparator; đừng bỏ qua kiểu nguồn và constructor đang được chọn.

## 8. Đặc tính hiệu năng và phạm vi phù hợp

Với n phần tử, bảo đảm O(log n) cho thêm/xóa/kiểm tra tồn tại của `TreeSet` dựa trên cách tổ chức cây và các phép so sánh. Nếu comparator tự làm công việc tốn kém, chi phí thực tế còn chịu ảnh hưởng của chính comparator. O(log n) không có nghĩa số mili giây cố định.

Duyệt và xuất toàn bộ tập hợp vẫn cần xử lý từng phần tử. Không thể in n phần tử trong thời gian hằng số chỉ vì chúng nằm trong cây. Cũng không có truy cập `get(index)` trên giao diện này như danh sách.

Các tình huống phù hợp:

- Duy trì các mức giá duy nhất và tìm mức vừa dưới/vừa trên ngân sách.
- Duyệt các khóa được sắp xếp trong khi vẫn thường xuyên thêm/xóa.
- Làm việc với cửa sổ giá trị theo biên.
- Giữ các đối tượng có thứ tự và quy tắc nhận diện trùng được thiết kế rõ.

Nếu chỉ cần kiểm tra tồn tại và không cần thứ tự, xem xét `HashSet`. Nếu phải giữ thứ tự thêm, xem xét `LinkedHashSet`. Nếu nhiều phần tử khác nhau có thể cùng giá trị khóa, cần thiết kế giữ nhóm hoặc số lần xuất hiện phù hợp.

`TreeSet` không tự đồng bộ. Nếu nhiều luồng cùng truy cập và có luồng sửa dữ liệu, cần thiết kế cơ chế đồng bộ hoặc chọn cách cài đặt phục vụ đồng thời phù hợp. Một khung nhìn lấy từ cây cũng không tự biến dữ liệu ấy thành an toàn giữa các luồng.

## 9. Bài tập kiểm tra cách hiểu

1. Vì sao khai báo biến kiểu `NavigableSet<Integer>` vẫn dùng được đối tượng tạo bằng `new TreeSet<>()`?
2. Với tập hợp `[10, 20, 30]`, `floor(25)` và `ceiling(25)` là gì? Có phần tử nào bị xóa không?
3. Hai công việc khác mã nhưng cùng ưu tiên sẽ ra sao nếu comparator chỉ xét ưu tiên?
4. Nếu cần giữ cả hai, ngoài việc “sắp cho đẹp”, comparator còn phải phù hợp với điều gì?
5. Vì sao một lớp có trường ưu tiên thay đổi được cần thận trọng hơn record trong ví dụ?

Định hướng: (1) lớp thực hiện hợp đồng giao diện; (2) 20 và 30, không xóa; (3) lần thêm sau bị coi là trùng; (4) quy tắc nhận diện phần tử và sự bằng nhau của dữ liệu; (5) thay đổi khóa so sánh khi đang nằm trong cây có thể khiến vị trí lưu không còn phù hợp.

Khi chọn `TreeSet`, hãy xác định rõ thứ tự đang dùng, khi nào hai phần tử được coi là trùng, và ai được phép thay đổi dữ liệu. Đó là nền tảng để các phương thức của `NavigableSet` cho kết quả đúng với yêu cầu.
