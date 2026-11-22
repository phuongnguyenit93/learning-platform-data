# Collection, List và AbstractList: hợp đồng và triển khai khung

Trong Java Collections Framework, Collection và List mô tả **hợp đồng sử dụng** một tập hợp phần tử, còn AbstractList cung cấp một phần **triển khai nền** để ta không phải viết lại mọi hành vi của một danh sách. Hiểu rõ ranh giới này giúp chọn đúng kiểu dữ liệu, triển khai List tùy chỉnh an toàn và tránh lỗi về chỉ số, iterator, thay đổi cấu trúc hay hiệu năng.

## 1. Quan hệ giữa các kiểu

~~~text
Iterable<E>
   |
   v
Collection<E>                 Map<K, V> là nhánh riêng
   |
   v
List<E>
   ^
   | implements
AbstractList<E>  (lớp trừu tượng)
   ^
   |
TaskList       (lớp cụ thể do ứng dụng định nghĩa)
~~~

- **Collection&lt;E&gt;** là interface gốc cho nhiều loại nhóm phần tử và mở rộng Iterable&lt;E&gt;. Nó cung cấp các thao tác tổng quát như đọc kích thước, duyệt, tìm, thêm và xóa phần tử.
- **List&lt;E&gt;** là interface con của Collection&lt;E&gt;. List biểu diễn một chuỗi có thứ tự, hỗ trợ truy cập theo chỉ số và cho phép phần tử trùng lặp.
- **AbstractList&lt;E&gt;** là lớp trừu tượng triển khai một phần hợp đồng List. Nó kế thừa AbstractCollection và cung cấp những thuật toán chung dựa trên một số thao tác cốt lõi mà lớp con phải định nghĩa.
- **ArrayList&lt;E&gt;** và **LinkedList&lt;E&gt;** là các triển khai có sẵn. Khi cần kiểu danh sách riêng, có thể kế thừa AbstractList hoặc AbstractSequentialList tùy cấu trúc lưu trữ.
- **Map&lt;K, V&gt;** không kế thừa Collection. Map mô hình hóa ánh xạ khóa–giá trị; các view như keySet(), values() và entrySet() mới cung cấp những Collection tương ứng.

Hãy phân biệt ba câu hỏi: interface quy định người gọi được kỳ vọng làm gì; lớp trừu tượng cung cấp sẵn những thuật toán nào; lớp cụ thể lưu trữ dữ liệu ra sao và hỗ trợ những thao tác nào.

## 2. Hợp đồng của Collection

Collection&lt;E&gt; mô tả một nhóm phần tử mà người gọi có thể thao tác thông qua một API thống nhất, bất kể dữ liệu bên dưới được lưu bằng mảng, danh sách liên kết, bảng băm hay cấu trúc khác.

Các nhóm phương thức chính:

| Nhóm | Phương thức tiêu biểu | Ý nghĩa |
|---|---|---|
| Kích thước | size(), isEmpty() | Đọc số phần tử hoặc kiểm tra rỗng |
| Tìm kiếm | contains(Object), containsAll(Collection) | Kiểm tra phần tử hoặc một nhóm phần tử |
| Duyệt/chuyển đổi | iterator(), toArray() | Duyệt hoặc chuyển phần tử sang mảng |
| Thay đổi | add(E), remove(Object), clear() | Thêm, xóa phần tử hoặc xóa toàn bộ |
| Thao tác nhóm | addAll(), removeAll(), retainAll() | Hợp nhất, loại bỏ hoặc chỉ giữ phần giao theo hợp đồng của từng phương thức |
| API hiện đại | removeIf(), stream(), parallelStream(), spliterator(), forEach() | Lọc, xử lý luồng hoặc duyệt bằng callback |

Một số điểm trong hợp đồng cần nhớ:

- Collection không tự bảo đảm thứ tự duyệt. Thứ tự phụ thuộc interface con và triển khai cụ thể.
- Collection không bắt buộc cho phép phần tử trùng lặp hay null theo một quy tắc chung cho mọi triển khai. Hợp đồng cụ thể có thể cho phép hoặc từ chối chúng.
- Một số thao tác thay đổi là **optional operations**. Triển khai không hỗ trợ thao tác đó có thể ném UnsupportedOperationException.
- add(element) trả về true nếu lời gọi làm Collection thay đổi. Với tập hợp không cho trùng lặp, thêm phần tử đã có có thể trả về false.
- Không nên giả định mọi loại Collection đều định nghĩa equals() và hashCode() theo nội dung giống nhau. List và Set có hợp đồng riêng cho những phương thức này.

Interface giúp code phụ thuộc vào hành vi cần dùng thay vì phụ thuộc vào lớp cụ thể. Ví dụ, một method nhận Collection&lt;String&gt; có thể xử lý nhiều loại tập hợp mà không cần biết dữ liệu đến từ ArrayList hay HashSet, miễn là method chỉ dựa vào các bảo đảm của Collection.

## 3. Hợp đồng riêng của List

List&lt;E&gt; bổ sung ngữ nghĩa của một **chuỗi có thứ tự**. Mỗi phần tử có vị trí, bắt đầu từ chỉ số 0; các phần tử bằng nhau có thể xuất hiện ở nhiều vị trí.

Những quy tắc quan trọng:

- get(index) đọc phần tử ở vị trí đã cho. Chỉ số âm hoặc bằng hay lớn hơn size() sẽ dẫn đến IndexOutOfBoundsException.
- add(index, element) chèn phần tử tại vị trí đó và dịch các phần tử phía sau sang phải. Chỉ số chèn hợp lệ từ 0 đến size(), bao gồm size().
- set(index, element) thay phần tử hiện có tại vị trí đó và trả về phần tử cũ. Nó không làm thay đổi kích thước danh sách.
- remove(index) xóa phần tử ở vị trí đó, trả về phần tử vừa bị xóa và dịch các phần tử phía sau sang trái.
- indexOf(value) tìm vị trí xuất hiện đầu tiên; lastIndexOf(value) tìm vị trí cuối cùng. Nếu không tìm thấy, kết quả là -1.
- iterator() duyệt theo thứ tự của List. listIterator() còn hỗ trợ đi lùi, xem chỉ số và thực hiện một số thao tác sửa đổi nếu triển khai hỗ trợ.
- Hai List bằng nhau theo hợp đồng List khi chúng có cùng kích thước và các phần tử ở từng vị trí tương ứng bằng nhau theo quy tắc equals. Thứ tự vì vậy ảnh hưởng đến equals() và hashCode() của List.

List vẫn có thể là bất biến, chỉ đọc, kích thước cố định hoặc thay đổi được. Interface không có nghĩa mọi phương thức sửa đổi đều được hỗ trợ. Hãy đọc hợp đồng của triển khai đang sử dụng và không suy luận khả năng sửa đổi chỉ từ kiểu List.

## 4. AbstractList cung cấp những gì?

AbstractList là **skeletal implementation**: một phần triển khai có sẵn của interface List. Mục tiêu là giảm số phương thức phải tự viết khi lớp con có thể cung cấp cách đọc phần tử theo chỉ số.

Thông thường, lớp con phải triển khai tối thiểu:

- get(int index): lấy phần tử tại chỉ số.
- size(): trả về số phần tử.

Chỉ với hai phương thức này, lớp con đã có thể kế thừa nhiều hành vi như iterator/listIterator, contains, indexOf, lastIndexOf, equals, hashCode và subList. Một số phương thức sửa đổi trong AbstractList mặc định ném UnsupportedOperationException, nên lớp con chỉ đọc có thể không cần ghi đè chúng.

Nếu muốn danh sách thay đổi được, lớp con thường cần ghi đè thêm những thao tác phù hợp với thiết kế lưu trữ:

- set(int index, E element) nếu cho phép thay thế phần tử.
- add(int index, E element) nếu cho phép chèn.
- remove(int index) nếu cho phép xóa.

AbstractList có thể suy ra các thao tác khác từ những phương thức này. Ví dụ, add(element) gọi add(size(), element); clear() và các thao tác duyệt sửa đổi dựa vào cơ chế xóa phần tử. Nếu chỉ hỗ trợ một số thao tác, cần kiểm tra rõ các thao tác còn lại có được kế thừa an toàn hay phải ném UnsupportedOperationException.

**Chọn lớp nền đúng với cấu trúc dữ liệu:**

- Dùng AbstractList khi truy cập theo chỉ số có hiệu năng phù hợp, chẳng hạn mảng hoặc bộ lưu trữ có thể đọc trực tiếp vị trí.
- Dùng AbstractSequentialList khi cấu trúc dữ liệu truy cập tuần tự, chẳng hạn danh sách liên kết. Nếu get(index) phải đi qua lần lượt nhiều node, các thuật toán mặc định của AbstractList có thể tạo ra chi phí O(n²) khi duyệt cả danh sách.
- Cân nhắc composition (giữ một đối tượng List bên trong và ủy quyền) nếu mục tiêu chỉ là bọc hoặc giới hạn API của một List có sẵn. Kế thừa AbstractList hữu ích khi thực sự muốn định nghĩa một kiểu List với hợp đồng rõ ràng.

## 5. Ví dụ Java 17+: tự triển khai một List bằng AbstractList

Ví dụ sau tạo TaskList, một danh sách chuỗi dùng ArrayList làm nơi lưu trữ. Lớp con chỉ định nghĩa cách đọc, thay thế, chèn và xóa phần tử; các hành vi còn lại được kế thừa từ AbstractList.

~~~java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.RandomAccess;

public class AbstractListDemo {
    private static final class TaskList
            extends AbstractList<String> implements RandomAccess {
        private final ArrayList<String> elements = new ArrayList<>();

        @Override
        public String get(int index) {
            return elements.get(index);
        }

        @Override
        public int size() {
            return elements.size();
        }

        @Override
        public String set(int index, String element) {
            return elements.set(index, element);
        }

        @Override
        public void add(int index, String element) {
            elements.add(index, element);
            modCount++;
        }

        @Override
        public String remove(int index) {
            String removed = elements.remove(index);
            modCount++;
            return removed;
        }
    }

    public static void main(String[] args) {
        List<String> tasks = new TaskList();

        tasks.add("read");
        tasks.add("test");
        System.out.println("initial = " + tasks);
        System.out.println("indexOf(test) = " + tasks.indexOf("test"));

        tasks.set(0, "design");
        System.out.println("after set = " + tasks);
        System.out.println("subList = " + tasks.subList(0, 1));

        tasks.remove(1);
        System.out.println("after remove = " + tasks);

        Iterator<String> iterator = tasks.iterator();
        tasks.add("deploy");
        try {
            iterator.next();
        } catch (ConcurrentModificationException ex) {
            System.out.println("iterator detected structural change");
        }

        System.out.println("final = " + tasks);
    }
}
~~~

Lưu vào file AbstractListDemo.java, rồi biên dịch và chạy:

~~~text
javac AbstractListDemo.java
java AbstractListDemo
~~~

Kết quả stdout:

~~~text
initial = [read, test]
indexOf(test) = 1
after set = [design, test]
subList = [design]
after remove = [design]
iterator detected structural change
final = [design, deploy]
~~~

### Vì sao ví dụ này hoạt động?

1. TaskList cung cấp get() và size(), nên AbstractList có đủ thông tin để triển khai nhiều thao tác đọc và duyệt.
2. add(int, element) và remove(int) ủy quyền thay đổi dữ liệu cho ArrayList bên trong. Sau khi thao tác thành công, chúng tăng modCount của TaskList để iterator do AbstractList cung cấp nhận ra thay đổi cấu trúc.
3. set() chỉ thay giá trị tại một vị trí, không làm đổi kích thước hoặc cấu trúc của danh sách, nên không tăng modCount.
4. indexOf() và subList() được thừa hưởng từ lớp nền. subList() tạo một **view** dựa trên danh sách gốc, thay vì luôn sao chép toàn bộ phần tử sang danh sách mới.
5. Sau khi tạo iterator, chương trình thêm phần tử bằng danh sách. Lần gọi next() tiếp theo phát hiện modCount đã đổi và ném ConcurrentModificationException.

RandomAccess là marker interface không có phương thức. Nó báo hiệu rằng truy cập theo chỉ số của TaskList phù hợp với các thuật toán tối ưu cho truy cập ngẫu nhiên. Trong ví dụ, get(index) gọi ArrayList.get(index), vốn có chi phí truy cập chỉ số hằng số theo mô hình thông thường.

## 6. modCount, thay đổi cấu trúc và iterator

AbstractList cung cấp trường protected modCount để hỗ trợ cơ chế fail-fast của iterator. Khi lớp con thay đổi cấu trúc danh sách, nó cần cập nhật trường này theo hợp đồng của AbstractList.

Một thay đổi cấu trúc thường là thao tác làm thay đổi kích thước hoặc thay đổi cấu trúc theo cách khiến quá trình duyệt hiện tại không còn đáng tin cậy, chẳng hạn thêm hoặc xóa phần tử. Thay giá trị bằng set() thường không phải thay đổi cấu trúc.

Các quy tắc triển khai:

- Chỉ tăng modCount sau khi thay đổi cấu trúc đã thành công. Nếu thao tác thêm hoặc xóa thất bại vì chỉ số không hợp lệ, danh sách chưa đổi thì không được tăng.
- Mỗi thao tác làm thay đổi cấu trúc cần cập nhật modCount đúng theo hợp đồng của AbstractList; không tăng tùy tiện trong các phương thức đọc hoặc set().
- Nếu ghi đè thêm các phương thức sửa đổi hoặc dùng nhiều lớp bọc, phải tránh cập nhật modCount hai lần cho cùng một thay đổi cấu trúc.
- Iterator do lớp nền cung cấp dùng giá trị modCount đã ghi nhận để phát hiện thay đổi ngoài iterator. Cơ chế này giúp phát hiện lỗi lập trình trong nhiều tình huống.
- Fail-fast chỉ là cơ chế phát hiện lỗi theo nỗ lực tốt nhất, không phải bảo đảm đồng bộ hóa. Không dùng ConcurrentModificationException làm cách điều phối luồng và không coi AbstractList là thread-safe.

Khi cần hỗ trợ sửa đổi thông qua ListIterator, hãy kiểm tra đường đi của add(), remove() và set() trên iterator. Các phương thức này phải tương thích với cách lớp con cập nhật dữ liệu và modCount. Nếu tự viết iterator, lớp con cũng phải xác định rõ cách phát hiện thay đổi ngoài iterator.

## 7. subList là view, không nhất thiết là bản sao

List.subList(fromIndex, toIndex) trả về một view của đoạn từ fromIndex (bao gồm) đến toIndex (không bao gồm). Ví dụ, subList(0, 1) của danh sách [design, test] biểu diễn đoạn [design].

- Thay đổi phần tử thông qua view được phản ánh vào danh sách nền và ngược lại theo hợp đồng của List.
- Thay đổi cấu trúc danh sách nền bên ngoài view trong khi view còn được sử dụng có thể làm hành vi của view không còn xác định theo hợp đồng hoặc gây ConcurrentModificationException tùy triển khai.
- Nếu cần một danh sách độc lập, hãy tạo bản sao rõ ràng, chẳng hạn new ArrayList<>(source.subList(from, to)).

Không giữ một subList lâu dài rồi tùy ý chèn/xóa ở danh sách gốc mà không xem xét vòng đời của view. Đây là lỗi dễ xuất hiện khi một đoạn danh sách được truyền sang lớp khác để xử lý.

## 8. Chọn triển khai và tránh nhầm lẫn

| Nhu cầu | Lựa chọn thường phù hợp | Điều cần kiểm tra |
|---|---|---|
| Danh sách tổng quát, truy cập chỉ số nhanh, thay đổi được | ArrayList&lt;E&gt; | Chi phí chèn/xóa ở giữa, khả năng sửa đổi |
| Truy cập chỉ số hoặc duyệt tuần tự theo node | LinkedList&lt;E&gt; hoặc triển khai tuần tự phù hợp | Chi phí truy cập chỉ số và bộ nhớ |
| Kiểu List riêng với lưu trữ ngẫu nhiên | Kế thừa AbstractList&lt;E&gt; | get, size, thao tác sửa đổi, modCount |
| Kiểu List riêng với lưu trữ tuần tự | Cân nhắc AbstractSequentialList&lt;E&gt; | listIterator và hiệu năng duyệt |
| Danh sách chỉ đọc tùy chỉnh | AbstractList với get và size, không mở thao tác sửa đổi | Các thao tác mutator có thể ném UnsupportedOperationException |
| Bản sao độc lập có thể sửa đổi | new ArrayList<>(source) | Sao chép phần tử tham chiếu, không tự sao chép sâu object |

Các nhầm lẫn phổ biến:

- **Cho rằng Collection luôn có thứ tự:** chỉ dựa vào hợp đồng của interface cụ thể. List có thứ tự; Collection tổng quát không bảo đảm điều đó.
- **Cho rằng List luôn sửa đổi được:** List.of(...) là không sửa đổi được; Arrays.asList(...) có kích thước cố định, cho phép set() nhưng không hỗ trợ add/remove theo cách thông thường.
- **Quên trường hợp optional operation:** một thao tác có thể hợp lệ về kiểu nhưng bị triển khai từ chối bằng UnsupportedOperationException.
- **Không kiểm tra chỉ số:** chèn cho phép index == size(); get, set và remove thì không.
- **Quên cập nhật modCount:** iterator của AbstractList có thể không phát hiện đúng thay đổi cấu trúc nếu lớp con quên cập nhật trường này.
- **Tăng modCount trong set():** thay thế phần tử tại vị trí hiện có không phải thay đổi cấu trúc thông thường; tăng không đúng sẽ khiến iterator báo lỗi không cần thiết.
- **Dùng AbstractList cho lưu trữ tuần tự nhưng không xét độ phức tạp:** các thuật toán dựa trên get(index) có thể lặp qua danh sách nhiều lần.
- **Coi subList là bản sao:** view liên kết với danh sách nền; hãy sao chép nếu cần dữ liệu độc lập.
- **Dựa vào fail-fast để đảm bảo an toàn đa luồng:** modCount không thay thế khóa, đồng bộ hóa hoặc thiết kế concurrency phù hợp.

## 9. Checklist khi tự triển khai AbstractList

Trước khi dùng một lớp con trong ứng dụng, hãy kiểm tra các điểm sau:

1. get(index) trả về đúng phần tử và xử lý chỉ số sai nhất quán với hợp đồng.
2. size() luôn phản ánh số phần tử thực tế.
3. set(), add(index, element) và remove(index) chỉ được hỗ trợ khi lớp thực sự định nghĩa được ngữ nghĩa đó.
4. Chèn/xóa cập nhật modCount đúng một lần cho mỗi thay đổi cấu trúc thành công; set() không tăng modCount chỉ vì thay giá trị.
5. Các thao tác kế thừa như clear(), addAll(), iterator.remove() và listIterator() hoạt động đúng với những thao tác mà lớp con hỗ trợ.
6. Độ phức tạp của get(index) phù hợp với AbstractList; nếu truy cập theo chỉ số tuần tự, cân nhắc AbstractSequentialList.
7. Hợp đồng về null, phần tử trùng lặp, khả năng sửa đổi và thread-safety được mô tả rõ.
8. Kiểm tra hành vi của equals(), hashCode(), subList(), iterator và các chỉ số biên, không chỉ kiểm tra add/remove cơ bản.

## 10. Tự kiểm tra

1. Collection và List khác nhau ở điểm cốt lõi nào? Collection mô tả nhóm phần tử tổng quát; List bổ sung thứ tự, chỉ số và ngữ nghĩa chuỗi.
2. Vì sao AbstractList giúp giảm công việc khi triển khai List? Nó cung cấp sẵn nhiều thuật toán dựa trên get(), size() và các thao tác cốt lõi mà lớp con định nghĩa.
3. Một lớp chỉ đọc kế thừa AbstractList cần tối thiểu những gì? Thông thường là get() và size(); các thao tác sửa đổi mặc định có thể ném UnsupportedOperationException.
4. Vì sao ví dụ tăng modCount sau add/remove nhưng không tăng sau set? Thêm/xóa làm thay đổi cấu trúc; thay giá trị tại vị trí có sẵn không làm đổi kích thước.
5. Có nên dùng AbstractList nếu get(index) phải đi qua nhiều node? Thường nên cân nhắc AbstractSequentialList để tránh các thuật toán dựa trên chỉ số gây chi phí lặp lại.
6. subList() có phải bản sao độc lập không? Không; nó là view của đoạn danh sách nền theo hợp đồng của List.

