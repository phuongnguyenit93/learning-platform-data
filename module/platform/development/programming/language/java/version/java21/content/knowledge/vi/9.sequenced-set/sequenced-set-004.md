# Truy cập hoặc xóa phần tử ở hai đầu của set

Java 21 bổ sung **SequencedSet<E>**, một interface biểu diễn tập hợp vừa bảo đảm tính duy nhất của Set vừa có thứ tự duyệt xác định. Nhờ đó, có thể đọc hoặc lấy bỏ phần tử ở đầu và cuối bằng các phương thức chung **getFirst()**, **getLast()**, **removeFirst()** và **removeLast()**.

Các thao tác này đặc biệt hữu ích với tập hợp có thứ tự gặp phần tử, chẳng hạn danh sách công việc theo thứ tự thêm vào hoặc tập giá trị được sắp xếp. Ý nghĩa của "đầu" và "cuối" phụ thuộc vào thứ tự mà implementation duy trì. Không nên dùng một Set không có thứ tự xác định rồi giả định phần tử đầu hoặc cuối luôn giống nhau.

## 1. SequencedSet là gì?

**SequencedSet<E>** được giới thiệu trong Java 21 cùng nhóm Sequenced Collections. Interface này mở rộng cả **SequencedCollection<E>** và **Set<E>**:

- Kế thừa hợp đồng của Set: không chứa các phần tử trùng nhau theo quy tắc equals.
- Có encounter order: thứ tự mà iterator và các thao tác duyệt nhìn thấy.
- Có thể truy cập hoặc loại bỏ phần tử ở hai đầu theo cùng một API.
- Có phương thức **reversed()** trả về một view có encounter order ngược lại.

Các phương thức đầu/cuối được định nghĩa trong SequencedCollection và được SequencedSet sử dụng:

| Phương thức | Kết quả |
|---|---|
| **getFirst()** | Trả về phần tử đầu tiên mà không xóa |
| **getLast()** | Trả về phần tử cuối cùng mà không xóa |
| **removeFirst()** | Xóa và trả về phần tử đầu tiên |
| **removeLast()** | Xóa và trả về phần tử cuối cùng |
| **reversed()** | Trả về view có thứ tự duyệt đảo ngược |

Nếu set rỗng, bốn phương thức get/remove ở hai đầu đều ném **NoSuchElementException**. Vì vậy, nếu phần tử có thể không tồn tại, hãy kiểm tra **isEmpty()** trước khi gọi hoặc chủ động xử lý exception phù hợp.

## 2. Dùng getFirst và getLast để đọc hai đầu

**LinkedHashSet** là một implementation của SequencedSet từ Java 21. Nó duy trì encounter order theo thứ tự chèn thông thường. Có thể khai báo biến bằng kiểu interface SequencedSet để gọi trực tiếp các phương thức mới:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

class ReadSetEnds {
    public static void main(String[] args) {
        SequencedSet<String> steps =
                new LinkedHashSet<>(List.of("compile", "test", "package"));

        String first = steps.getFirst();
        String last = steps.getLast();

        System.out.println("Đầu: " + first); // compile
        System.out.println("Cuối: " + last); // package
    }
}
~~~

Hai phương thức chỉ đọc phần tử, không thay đổi số lượng hay encounter order của set. Với LinkedHashSet, phần tử đầu thường là phần tử được thêm sớm nhất còn hiện diện; phần tử cuối là phần tử được thêm gần nhất còn hiện diện, có xét đến các thao tác đặt phần tử ở hai đầu.

### Kiểu khai báo của biến quyết định API có thể gọi

Nếu khai báo đối tượng bằng kiểu **Set<E>**, compiler chỉ cho phép gọi các phương thức được khai báo trên Set. Dù đối tượng thực tế là LinkedHashSet, biến Set không thể gọi getFirst() trực tiếp:

~~~java
import java.util.LinkedHashSet;
import java.util.SequencedSet;
import java.util.Set;

class SetStaticType {
    static void example() {
        Set<String> names = new LinkedHashSet<>();
        // names.getFirst(); // Lỗi biên dịch: Set không khai báo getFirst()

        SequencedSet<String> orderedNames = new LinkedHashSet<>();
        orderedNames.add("An");
        String firstName = orderedNames.getFirst();
    }
}
~~~

Khi cần thao tác theo hai đầu, hãy thể hiện yêu cầu thứ tự ngay trong kiểu biến bằng **SequencedSet<E>**. Không ép kiểu một HashSet sang SequencedSet: HashSet không cung cấp encounter order và không triển khai interface này.

## 3. Dùng removeFirst và removeLast để lấy bỏ phần tử

Hai phương thức removeFirst() và removeLast() vừa trả về phần tử ở vị trí tương ứng vừa loại bỏ phần tử đó khỏi set. Điều này phù hợp khi xử lý phần tử ở đầu hoặc cuối của một hàng đợi có tính duy nhất.

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

class RemoveSetEnds {
    public static void main(String[] args) {
        SequencedSet<String> tasks =
                new LinkedHashSet<>(List.of("compile", "test", "package"));

        String nextTask = tasks.removeFirst();
        String latestTask = tasks.removeLast();

        System.out.println(nextTask);   // compile
        System.out.println(latestTask); // package
        System.out.println(tasks);      // [test]
    }
}
~~~

Sau mỗi lần xóa, phần tử đầu và cuối được xác định lại theo encounter order mới. Nếu chỉ còn một phần tử, gọi removeFirst() hoặc removeLast() sẽ lấy bỏ chính phần tử đó và làm set rỗng.

### Xử lý set rỗng

Không gọi trực tiếp các phương thức get/remove ở hai đầu nếu set có thể rỗng mà chưa có chính sách xử lý:

~~~java
import java.util.SequencedSet;

class TaskProcessor {
    static void processNext(SequencedSet<String> tasks) {
        if (tasks.isEmpty()) {
            System.out.println("Không còn công việc");
            return;
        }

        String task = tasks.removeFirst();
        System.out.println("Đang xử lý: " + task);
    }
}
~~~

Kiểm tra isEmpty() giúp xử lý trường hợp rỗng theo luồng nghiệp vụ mong muốn. Nếu có nhiều luồng cùng thay đổi một set, kiểm tra rồi xóa không tự trở thành một thao tác nguyên tử; cần đồng bộ hóa hoặc dùng cấu trúc dữ liệu đồng thời phù hợp với yêu cầu của ứng dụng.

## 4. Đảo thứ tự bằng reversed()

**reversed()** trả về một view có encounter order ngược với set ban đầu. Đây là view được hỗ trợ bởi set gốc, không phải một bản sao độc lập. Thay đổi qua view được phản ánh vào set ban đầu và ngược lại.

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

class ReversedSetView {
    public static void main(String[] args) {
        SequencedSet<String> names =
                new LinkedHashSet<>(List.of("An", "Bình", "Chi"));

        SequencedSet<String> reversed = names.reversed();

        System.out.println(reversed.getFirst()); // Chi
        System.out.println(reversed.getLast());  // An

        String removed = reversed.removeFirst(); // Xóa Chi

        System.out.println(removed);
        System.out.println(names); // [An, Bình]
    }
}
~~~

Trong view đảo ngược, phần tử đầu tương ứng với phần tử cuối của set gốc và ngược lại. Vì view chia sẻ dữ liệu với collection ban đầu, thao tác removeFirst() trên view sẽ xóa phần tử cuối trong thứ tự của set gốc.

Sử dụng reversed() khi cần duyệt hoặc thao tác từ cuối về đầu mà không phải tự tạo một set mới rồi sao chép phần tử. Nếu cần một bản sao độc lập, hãy tạo collection mới và thêm các phần tử theo thứ tự mong muốn; đừng nhầm view đảo chiều với bản sao.

## 5. Thứ tự của LinkedHashSet và TreeSet khác nhau

SequencedSet xác định API cho encounter order, nhưng không quy định mọi implementation phải dùng cùng một cách sắp xếp. Cần hiểu quy tắc của implementation đang sử dụng:

| Implementation | Encounter order | Ý nghĩa của getFirst/getLast |
|---|---|---|
| **LinkedHashSet** | Thứ tự chèn, có thể điều chỉnh hai đầu | Phần tử đầu/cuối trong thứ tự chèn hiện tại |
| **TreeSet** | Thứ tự tăng dần theo natural ordering hoặc Comparator | Phần tử nhỏ nhất/lớn nhất theo comparator |

**TreeSet** triển khai NavigableSet; trong Java 21, SortedSet mở rộng SequencedSet nên TreeSet cũng có thể dùng các phương thức truy cập hai đầu.

~~~java
import java.util.SequencedSet;
import java.util.TreeSet;

class SortedSetEnds {
    public static void main(String[] args) {
        SequencedSet<Integer> scores = new TreeSet<>();
        scores.add(30);
        scores.add(10);
        scores.add(20);

        System.out.println(scores.getFirst()); // 10
        System.out.println(scores.getLast());  // 30

        int smallest = scores.removeFirst(); // 10
        int largest = scores.removeLast();   // 30

        System.out.println(smallest);
        System.out.println(largest);
        System.out.println(scores); // [20]
    }
}
~~~

Với TreeSet, "đầu" và "cuối" được xác định bởi thứ tự sắp xếp, không phải thứ tự thêm vào. Nếu truyền Comparator đảo ngược, ý nghĩa đầu/cuối cũng đảo theo comparator đó.

TreeSet không cho phép tùy ý đặt phần tử vào đầu hoặc cuối bằng addFirst() và addLast(), vì vị trí phải tuân theo quy tắc sắp xếp. Các thao tác đó có thể ném UnsupportedOperationException trên sorted set. Việc đọc hoặc xóa phần tử đầu/cuối vẫn có ý nghĩa và được hỗ trợ.

Với LinkedHashSet, addFirst(e) và addLast(e) có thể đặt phần tử ở đầu hoặc cuối encounter order. Vì đây vẫn là Set, nếu e đã có mặt thì implementation di chuyển phần tử hiện có tới vị trí được yêu cầu thay vì tạo một phần tử trùng lặp. Hành vi đặt vị trí này không áp dụng được cho TreeSet vì comparator quyết định vị trí.

## 6. Phân biệt SequencedSet với các kiểu Set khác

Không phải mọi Set đều có encounter order:

- **HashSet** không bảo đảm thứ tự duyệt; không dùng nó khi logic phụ thuộc vào đầu/cuối.
- **LinkedHashSet** duy trì encounter order và phù hợp với thao tác hai đầu.
- **TreeSet** duy trì thứ tự theo Comparable hoặc Comparator; đầu/cuối là hai cực của thứ tự sắp xếp.

Set vẫn giữ quy tắc không trùng phần tử. SequencedSet bổ sung thứ tự gặp phần tử, nhưng không biến Set thành List: không có truy cập theo chỉ số và không cho phép hai phần tử bằng nhau cùng tồn tại. Hợp đồng equals/hashCode của Set vẫn dựa trên các phần tử, không dựa vào thứ tự gặp phần tử.

## 7. Chọn giữa removeFirst/removeLast và pollFirst/pollLast

Nếu biến có kiểu **SequencedSet<E>**, dùng removeFirst() hoặc removeLast() để diễn đạt thao tác lấy bỏ ở đầu/cuối theo hợp đồng chung. Các phương thức này ném NoSuchElementException khi set rỗng.

Với biến có kiểu **NavigableSet<E>**, các phương thức pollFirst() và pollLast() vẫn là API hiện hành. Chúng trả về null khi set rỗng. Chỉ dùng null làm tín hiệu không có phần tử nếu implementation hoặc Comparator không cho phép null là một phần tử hợp lệ:

~~~java
import java.util.NavigableSet;
import java.util.TreeSet;

class PollSortedSet {
    public static void main(String[] args) {
        NavigableSet<Integer> values = new TreeSet<>();

        Integer first = values.pollFirst();
        if (first == null) {
            System.out.println("Set đang rỗng");
        }
    }
}
~~~

Đây không phải API lỗi thời. Hãy chọn theo hợp đồng mong muốn: removeFirst/removeLast báo lỗi khi rỗng; pollFirst/pollLast trả về null khi rỗng và chỉ có trên NavigableSet. Nếu cấu hình Comparator cho phép null trong set, giá trị null trả về không đủ để phân biệt set rỗng với phần tử null được lấy ra.

## 8. Lưu ý về khả năng thay đổi và đồng bộ

SequencedSet là interface mô tả thứ tự và thao tác, không bảo đảm mọi implementation đều hỗ trợ mọi kiểu thay đổi. Các wrapper không sửa đổi có thể từ chối thao tác xóa; sorted set có thể từ chối việc chèn vào một vị trí cụ thể. Hãy đọc hợp đồng của implementation và wrapper đang dùng.

Các phương thức getFirst(), getLast(), removeFirst() và removeLast() không tự đồng bộ hóa một chuỗi thao tác gồm kiểm tra, đọc và xóa. Nếu nhiều thread cùng truy cập và cập nhật set, cần chọn cơ chế đồng bộ phù hợp; không coi SequencedSet là collection thread-safe chỉ vì có API hai đầu.

## 9. Checklist thao tác với hai đầu của set

- [ ] Dùng SequencedSet<E> khi cần API truy cập hai đầu.
- [ ] Chọn implementation có encounter order phù hợp với nghiệp vụ.
- [ ] Dùng getFirst/getLast để đọc mà không xóa.
- [ ] Dùng removeFirst/removeLast để lấy và loại bỏ phần tử.
- [ ] Xử lý NoSuchElementException hoặc kiểm tra isEmpty() khi set có thể rỗng.
- [ ] Hiểu rằng reversed() trả về view đảo thứ tự, không phải bản sao.
- [ ] Nhớ rằng TreeSet dùng thứ tự comparator và không hỗ trợ tùy ý addFirst/addLast.
- [ ] Không dựa vào thứ tự của HashSet.
- [ ] Đồng bộ hóa phù hợp nếu nhiều thread cùng sửa set.

## Tài liệu tham khảo

- [Java SE 21 API: SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html)
- [Java SE 21 API: SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Java SE 21 API: LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html)
- [Java SE 21 API: SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html)
- [Java SE 21 API: TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html)
- [JEP 431: Sequenced Collections](https://openjdk.org/jeps/431)
