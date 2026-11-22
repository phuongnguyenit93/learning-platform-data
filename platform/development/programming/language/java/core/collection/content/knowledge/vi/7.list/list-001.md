# List: đặc trưng theo vị trí, phần tử trùng và thứ tự duyệt

`List<E>` biểu diễn một **dãy phần tử có thứ tự theo vị trí**. Khi đọc một list, ta quan tâm không chỉ “có những giá trị nào”, mà còn “mỗi giá trị đang xuất hiện ở vị trí nào và theo thứ tự nào”.

Ví dụ:

```text
[C, A, C, B]
```

Dãy này có bốn phần tử. Hai lần xuất hiện của C nằm ở hai vị trí khác nhau. Thứ tự hiện tại là C rồi A rồi C rồi B; nó không cần là thứ tự tăng dần.

Ba đặc điểm cần nắm cùng nhau:

1. **Theo vị trí:** có thể truy cập hoặc thao tác tại một chỉ số.
2. **Có thể giữ phần tử trùng:** các lần xuất hiện bằng nhau vẫn là những vị trí riêng.
3. **Duyệt theo thứ tự của dãy:** cách duyệt tiến thông thường đi từ vị trí đầu đến cuối.

## 1. Vì sao dùng mô hình List?

Một danh sách bài hát có thể phát cùng một bài nhiều lần. Một lịch sử thao tác có thể ghi cùng một hành động ở nhiều thời điểm. Các bước trong một quy trình có thứ tự trước–sau.

Với những tình huống này, chỉ biết tập các giá trị duy nhất là chưa đủ:

```text
Danh sách phát 1: [A, B, A]
Danh sách phát 2: [A, A, B]
```

Cả hai cùng có A và B, cùng ba lần xuất hiện, nhưng trải nghiệm phát khác nhau vì thứ tự khác nhau.

List phù hợp khi **vị trí và số lần xuất hiện** là một phần của dữ liệu cần giữ. Nếu yêu cầu là không có giá trị trùng, không nên mong List tự thực thi ràng buộc duy nhất đó.

List là một interface của Java Collections Framework, kế thừa Collection và Iterable. Các lớp như ArrayList và LinkedList cung cấp cách triển khai khác nhau cho mô hình này. Xem [API List của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## 2. Chỉ số bắt đầu từ 0 và gắn với trạng thái hiện tại

Với:

```text
List:   [C, A, C, B]
Index:   0  1  2  3
```

- Phần tử đầu ở chỉ số 0.
- Phần tử cuối ở chỉ số `size() - 1`.
- Với size bằng 4, chỉ số phần tử hợp lệ là 0, 1, 2, 3.

Chỉ số không phải mã định danh bền vững của một đối tượng. Nó mô tả vị trí trong **dãy hiện tại**.

### 2.1. size đếm số lần xuất hiện

`size()` của `[C, A, C, B]` là 4, không phải 3. C xuất hiện hai lần và mỗi lần chiếm một vị trí.

Nếu list cho phép null, một null cũng là một phần tử được tính vào size. Null không tự tạo “lỗ trống” ngoài dãy chỉ số.

### 2.2. Giới hạn chỉ số khác nhau theo thao tác

Giả sử list có n phần tử và các thao tác thay đổi tương ứng được hỗ trợ:

| Thao tác | Miền chỉ số |
| --- | --- |
| `get(index)` | `0 <= index < n` |
| `set(index, value)` | `0 <= index < n` |
| `remove(index)` | `0 <= index < n` |
| `add(index, value)` | `0 <= index <= n` |

Với thao tác chèn, index bằng n nghĩa là chèn vào cuối. Nhưng `get(n)` không hợp lệ vì chưa có phần tử nào ở đó.

List rỗng có size bằng 0:

- Không có chỉ số nào dùng được để đọc phần tử.
- Có thể chèn tại 0 nếu list hỗ trợ thêm.

Không gọi `get(size())` để lấy phần tử cuối. Với list không rỗng, vị trí cuối là `size() - 1`.

### 2.3. Chèn và xóa làm thay đổi vị trí

Ban đầu:

```text
[C, A, C, B]
 0  1  2  3
```

Chèn X tại index 1:

```text
[C, X, A, C, B]
 0  1  2  3  4
```

Phần tử trước ở index 1 chuyển sang index 2. Những phần tử phía sau cũng có chỉ số mới.

Nếu lưu một chỉ số rồi tiếp tục chèn hoặc xóa ở phía trước, chỉ số cũ có thể trỏ tới giá trị khác hoặc không còn hợp lệ. Khi nghiệp vụ cần nhận diện một bản ghi qua nhiều thay đổi, hãy dùng mã định danh phù hợp thay vì coi chỉ số là danh tính.

## 3. Phân biệt thêm, chèn, thay thế và xóa

Các thao tác sau không cùng ý nghĩa:

| Thao tác | Tác động nếu thành công | Thay đổi size |
| --- | --- | --- |
| `add(value)` | Thêm vào cuối dãy | Tăng 1 |
| `add(index, value)` | Chèn trước phần tử đang ở vị trí đó, hoặc cuối dãy | Tăng 1 |
| `set(index, value)` | Thay giá trị ở một vị trí đã có | Không đổi |
| `remove(index)` | Loại lần xuất hiện ở vị trí đó | Giảm 1 |
| `remove(value)` | Loại lần xuất hiện đầu tiên phù hợp theo giá trị | Giảm 1 nếu có phần tử bị loại |

Ví dụ ban đầu là `[C, A, C, B]`:

- `add(1, "X")` cho `[C, X, A, C, B]`.
- Từ kết quả đó, `set(2, "M")` cho `[C, X, M, C, B]`; A được thay thế, không có vị trí mới.
- `remove(0)` loại C đầu tiên, cho `[X, M, C, B]`.

`set` trả giá trị cũ ở vị trí được thay. `remove(int)` trả phần tử bị xóa. `remove(Object)` trả boolean cho biết có loại được một lần xuất hiện hay không.

Những khác biệt này giúp giải thích thay đổi của dãy mà không cần biết bên trong lớp triển khai dùng mảng hay các nút liên kết.

## 4. Phần tử trùng là nhiều lần xuất hiện riêng biệt

### 4.1. Trùng theo giá trị không đòi cùng tham chiếu

Một list có thể chứa hai đối tượng khác nhau nhưng bằng nhau theo equals.

Với record:

```java
record Entry(String code) {}
```

hai lệnh `new Entry("A")` tạo hai đối tượng riêng. Tuy nhiên, equals của record xem chúng bằng nhau vì cùng code.

Nếu cùng đưa cả hai vào ArrayList, cả hai lần xuất hiện được giữ. Đây không phải hai biến “trỏ vào cùng một ô danh sách”.

List cũng có thể giữ chính cùng một tham chiếu ở nhiều vị trí. Khi đó, sửa trạng thái đối tượng có thể được nhìn thấy ở mọi vị trí đang tham chiếu nó. List chứa các tham chiếu; thêm lại một đối tượng không tự sao chép sâu đối tượng đó.

### 4.2. indexOf và lastIndexOf trả lời hai câu hỏi khác nhau

Với `[A, B, A]`:

| Câu hỏi | Kết quả |
| --- | --- |
| `indexOf("A")` | 0 |
| `lastIndexOf("A")` | 2 |
| `indexOf("Z")` | -1 |
| `contains("A")` | true |

IndexOf tìm lần xuất hiện đầu, lastIndexOf tìm lần cuối, còn contains chỉ hỏi có ít nhất một phần tử phù hợp.

Các thao tác tìm theo đối tượng sử dụng hợp đồng equals phù hợp, không chỉ so tham chiếu bằng `==`.

Không dùng kết quả -1 làm chỉ số để get. Cần kiểm tra đã tìm thấy hay chưa.

### 4.3. remove theo giá trị không xóa mọi bản sao

Trên `[A, B, A]`, `remove("A")` loại A đầu, còn `[B, A]`.

Muốn loại mọi lần xuất hiện thỏa điều kiện phải dùng thao tác phù hợp với ý định đó, chẳng hạn removeIf trên nguồn hỗ trợ, thay vì mong một remove theo giá trị tự xóa hết.

Nếu cần loại chính lần xuất hiện đang duyệt, iterator tường minh có thể cung cấp mục tiêu chính xác khi nguồn hỗ trợ xóa. Không thay thế tùy tiện bằng remove theo giá trị nếu có nhiều phần tử bằng nhau.

### 4.4. Không dùng List làm ràng buộc duy nhất

Các triển khai thông dụng như ArrayList và LinkedList cho phép phần tử trùng. Hợp đồng List mô tả đây là hành vi điển hình; một triển khai chuyên biệt vẫn có thể đặt giới hạn được công bố.

Điểm thiết kế thực tế là: **không chọn List rồi giả định nó tự chống trùng**. Nếu nghiệp vụ cần vừa thứ tự lần xuất hiện vừa kiểm tra mã duy nhất, phải xác định ràng buộc và cơ chế kiểm tra rõ ràng.

## 5. Thứ tự của List không đồng nghĩa đã được sắp xếp

Dãy:

```text
[C, A, C, B]
```

có thứ tự xác định dù không tăng dần.

### 5.1. Thứ tự theo vị trí

Đây là thứ tự đang có trong dãy. Khi chỉ nối thêm bằng add(value), phần tử mới ở cuối. Khi chèn tại một vị trí, dãy thay đổi theo yêu cầu chèn.

### 5.2. Thứ tự sắp xếp theo tiêu chí

Đây là kết quả của một quy tắc như theo tên, điểm hoặc thời gian. List không tự chọn quy tắc đó.

Nếu sort list bằng một comparator, thứ tự duyệt sau đó phản ánh dãy mới đã được sắp. Nếu thêm một phần tử bất kỳ vào cuối sau khi sort, list vẫn là một dãy có thứ tự theo vị trí nhưng có thể không còn tăng dần theo comparator.

### 5.3. Thứ tự không phải bất biến

Có thể đảo vị trí, đổi chỗ, chèn, xóa hoặc sắp xếp list nếu nguồn hỗ trợ.

“List có thứ tự” nghĩa là mỗi trạng thái của dãy có thứ tự được xác định để thao tác và duyệt. Nó không có nghĩa vị trí của một giá trị không bao giờ thay đổi.

Ví dụ, `Collections.reverse` đảo dãy hiện tại mà không tự sắp theo giá trị. Hợp đồng của thao tác này được mô tả trong [API Collections.reverse](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#reverse(java.util.List)).

## 6. Thứ tự duyệt gắn với dãy hiện tại

### 6.1. Duyệt tiến bằng iterator hoặc for-each

Iterator của List trả phần tử theo thứ tự của dãy. Vòng for-each tiến thông thường cũng phản ánh thứ tự đó.

Với:

```text
[X, M, C, B, X]
```

lượt duyệt tiến đi qua X, M, C, B rồi X. Lần xuất hiện cuối không bị bỏ vì bằng lần đầu.

Biến trong for-each là phần tử của lượt hiện tại, không phải chỉ số. Nếu cần cả vị trí để hiển thị, có thể dùng cách duyệt có theo dõi chỉ số phù hợp, nhưng không suy ra kiểu phần tử là một mã vị trí.

### 6.2. Duyệt theo chỉ số

Đoạn minh họa trong phương thức:

```java
for (int i = 0; i < values.size(); i++) {
    System.out.println(i + ": " + values.get(i));
}
```

Nó diễn đạt rõ vị trí đang đọc.

Tuy nhiên, interface List không bảo đảm mọi get(index) đều có chi phí hằng số. Việc duyệt bằng chỉ số lặp đi lặp lại có thể không phù hợp với một triển khai truy cập tuần tự.

ArrayList dùng cấu trúc hỗ trợ truy cập theo chỉ số hiệu quả; LinkedList có thể phải đi qua các nút để tới vị trí. Khi không cần chỉ số và không biết triển khai, iterator hoặc for-each thường thể hiện đúng ý định duyệt hơn. Xem [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) và [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

### 6.3. Duyệt ngược không nhất thiết sửa dãy

ListIterator hỗ trợ previous để duyệt ngược. Có thể bắt đầu tại ranh giới sau phần tử cuối bằng:

```java
ListIterator<String> iterator = values.listIterator(values.size());

while (iterator.hasPrevious()) {
    System.out.println(iterator.previous());
}
```

Chỉ đi ngược qua các phần tử không tự đảo cấu trúc list. Đây là thay đổi hướng duyệt, khác với gọi Collections.reverse để đổi dãy. Xem [API ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

## 7. Chương trình hoàn chỉnh về vị trí và thứ tự

Lưu vào **ListPositionDemo.java**. Chương trình tương thích Java 17 trở lên:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class ListPositionDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(List.of("C", "A", "C", "B"));

        System.out.println("Initial: " + values);
        System.out.println("Size: " + values.size());
        System.out.println("Index 2: " + values.get(2));
        System.out.println("First/last C: "
                + values.indexOf("C") + "/" + values.lastIndexOf("C"));

        values.add(1, "X");
        System.out.println("After insert: " + values);

        String previous = values.set(2, "M");
        System.out.println("Replaced value: " + previous);
        System.out.println("After set: " + values);

        String removed = values.remove(0);
        values.add("X");
        System.out.println("Removed at index 0: " + removed);
        System.out.println("Current: " + values);

        List<String> forward = new ArrayList<>();
        for (String value : values) {
            forward.add(value);
        }
        System.out.println("Forward traversal: " + forward);

        List<String> backward = new ArrayList<>();
        ListIterator<String> iterator = values.listIterator(values.size());
        while (iterator.hasPrevious()) {
            backward.add(iterator.previous());
        }
        System.out.println("Backward traversal: " + backward);

        List<String> sameSequence = new LinkedList<>(values);
        System.out.println("ArrayList equals LinkedList: "
                + values.equals(sameSequence));

        List<String> reversedCopy = new ArrayList<>(values);
        Collections.reverse(reversedCopy);
        System.out.println("Equals reversed sequence: "
                + values.equals(reversedCopy));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ListPositionDemo.java
java ListPositionDemo
```

Stdout:

```text
Initial: [C, A, C, B]
Size: 4
Index 2: C
First/last C: 0/2
After insert: [C, X, A, C, B]
Replaced value: A
After set: [C, X, M, C, B]
Removed at index 0: C
Current: [X, M, C, B, X]
Forward traversal: [X, M, C, B, X]
Backward traversal: [X, B, C, M, X]
ArrayList equals LinkedList: true
Equals reversed sequence: false
```

### 7.1. Vị trí và thay đổi dãy

Ban đầu C nằm ở 0 và 2. Chèn X tại 1 làm dãy tăng từ bốn lên năm phần tử.

Set tại 2 thay A bằng M và trả A. Nó không thêm vị trí thứ sáu.

Remove tại 0 trả C. Sau đó nối thêm X, kết quả có hai lần xuất hiện của X ở đầu và cuối.

### 7.2. Hai hướng duyệt

Lượt tiến thu đúng dãy hiện tại.

Lượt ngược bắt đầu ở ranh giới size và lấy previous liên tiếp, cho `[X, B, C, M, X]`. List nguồn vẫn là `[X, M, C, B, X]`; hướng duyệt không tự sửa nguồn.

### 7.3. List khác lớp triển khai vẫn có thể bằng nhau

ArrayList và LinkedList trong ví dụ chứa cùng dãy phần tử nên equals trả true.

Bản đảo có cùng các giá trị và số lần xuất hiện nhưng khác thứ tự, nên không bằng list ban đầu.

Điều này dẫn đến một đặc điểm quan trọng: equality của List mang ngữ nghĩa **dãy**, không chỉ ngữ nghĩa “có cùng tập giá trị”.

## 8. Thứ tự và số lần xuất hiện tham gia equality

Hai list bằng nhau khi cùng kích thước và các phần tử tương ứng ở cùng vị trí bằng nhau theo hợp đồng.

Ví dụ:

```text
[A, B, A] bằng [A, B, A]
[A, B, A] khác [A, A, B]
[A, B, A] khác [A, B]
```

Không cần hai list thuộc cùng một lớp triển khai. Nhưng thứ tự và số lần xuất hiện không thể bỏ qua.

Hệ quả thực tế:

- Khi kiểm thử một kết quả List, phải quyết định có cần xác nhận đúng thứ tự không.
- Nếu nghiệp vụ không quan tâm thứ tự, không nên dùng List.equals rồi ngạc nhiên vì kết quả false.
- Nếu chuyển List sang Set để so sánh, các phần tử trùng có thể bị gộp; phép chuyển đổi đó thay đổi câu hỏi đang được kiểm tra.
- Nếu hai list bằng nhau, hashCode của chúng phải tương thích theo hợp đồng; không nên tự thay equality bằng phép đếm phần tử duy nhất.

Các phương thức tìm phần tử, equals và hashCode của List được mô tả trong [API List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## 9. Chương trình hoàn chỉnh về trùng lặp và giới hạn của nguồn

Lưu vào **ListDuplicateDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ListDuplicateDemo {
    record Entry(String code) {}

    private static List<String> codes(List<Entry> entries) {
        return entries.stream().map(Entry::code).toList();
    }

    public static void main(String[] args) {
        Entry first = new Entry("A");
        Entry last = new Entry("A");
        List<Entry> entries =
                new ArrayList<>(List.of(first, new Entry("B"), last));

        System.out.println("Same reference: " + (first == last));
        System.out.println("Equal values: " + first.equals(last));
        System.out.println("Entries: " + codes(entries));
        System.out.println("First/last equal A: "
                + entries.indexOf(new Entry("A")) + "/"
                + entries.lastIndexOf(new Entry("A")));

        boolean removed = entries.remove(new Entry("A"));
        System.out.println("Removed by value: " + removed);
        System.out.println("After removal: " + codes(entries));

        List<String> nulls =
                new ArrayList<>(Arrays.asList("A", null, null));
        System.out.println("Null list size: " + nulls.size());
        System.out.println("First/last null: "
                + nulls.indexOf(null) + "/" + nulls.lastIndexOf(null));

        List<String> readOnly = List.of("A", "A", "B");
        System.out.println("Read-only duplicates: " + readOnly);

        try {
            readOnly.set(0, "C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Read-only set: " + ex.getClass().getSimpleName());
        }

        try {
            List.of("A", null);
        } catch (NullPointerException ex) {
            System.out.println("List.of null: " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ListDuplicateDemo.java
java ListDuplicateDemo
```

Stdout:

```text
Same reference: false
Equal values: true
Entries: [A, B, A]
First/last equal A: 0/2
Removed by value: true
After removal: [B, A]
Null list size: 3
First/last null: 1/2
Read-only duplicates: [A, A, B]
Read-only set: UnsupportedOperationException
List.of null: NullPointerException
```

### 9.1. Hai đối tượng nhưng cùng giá trị

`first` và `last` được tạo bằng hai lần new, nên `first == last` là false.

Equals của record so thành phần code, nên chúng bằng nhau. List vẫn giữ cả hai và indexOf/lastIndexOf tìm được ở hai vị trí 0 và 2.

Lệnh remove nhận một Entry mới bằng giá trị, loại lần xuất hiện đầu. Dãy còn B rồi A.

### 9.2. Null được tính như một phần tử khi nguồn hỗ trợ

ArrayList trong ví dụ chứa hai null, size là 3 và hai chỉ số null là 1 và 2.

Điều này không chứng minh mọi List đều chấp nhận null. List.of từ chối null ngay khi tạo trong ví dụ.

### 9.3. Có thứ tự và phần tử trùng không đòi list phải cho sửa

`List.of("A", "A", "B")` có một dãy xác định và giữ cả hai A. Tuy nhiên, nó không cho set, add hoặc remove.

Khả năng biểu diễn một dãy, chính sách null và khả năng sửa đổi là các đặc tính phải kiểm tra riêng. Không nên kết luận “khai báo List nên chắc chắn sửa được”.

## 10. Các ranh giới dễ nhầm

### 10.1. List có vị trí khác với Set có thứ tự duyệt

Một LinkedHashSet có thể giữ thứ tự thêm của các phần tử duy nhất, nhưng không trở thành List. Nó không cung cấp get(index) của List và không giữ nhiều phần tử bằng nhau theo ngữ nghĩa tập hợp.

Nếu chuyển `[A, B, A]` thành tập hợp duy nhất, dữ liệu về lần phát A thứ hai bị mất. Giữ thứ tự các giá trị còn lại không khôi phục được thông tin đó. Xem [API LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

### 10.2. List không đồng nghĩa ArrayList

List là hợp đồng. ArrayList là một cách tổ chức dữ liệu.

Các phép đọc theo vị trí và thứ tự dãy không yêu cầu mọi triển khai phải dùng mảng bên trong. Chọn triển khai còn cần dựa vào kiểu truy cập, cập nhật và yêu cầu đồng thời; bài này tập trung vào ngữ nghĩa chung của list.

### 10.3. Thứ tự của nguồn sao chép có ý nghĩa

Khi tạo một danh sách từ một Collection khác, thứ tự nhận được phụ thuộc thứ tự mà nguồn cung cấp trong phép sao chép.

Một ArrayList mới không thể tự khôi phục “thứ tự thêm ban đầu” nếu nguồn không còn giữ thông tin đó. Muốn một thứ tự nghiệp vụ cụ thể, phải cung cấp dữ liệu hoặc quy tắc sắp xếp tương ứng.

## 11. Lỗi thực hành thường gặp

| Lỗi | Vì sao sai | Cách nghĩ đúng |
| --- | --- | --- |
| Dùng get(size()) | Vị trí cuối là size - 1 | Kiểm tra rỗng và miền chỉ số |
| Dùng add(index, value) để thay phần tử | Add chèn một vị trí mới | Dùng set nếu cần thay tại chỗ |
| Lưu chỉ số như mã định danh | Chèn/xóa phía trước làm chỉ số đổi | Chỉ số thuộc trạng thái hiện tại |
| Nghĩ List tự loại trùng | Triển khai thông dụng giữ các lần xuất hiện | Chọn hoặc kiểm tra ràng buộc duy nhất riêng |
| Nghĩ remove(value) xóa mọi bản sao | Nó loại lần xuất hiện đầu phù hợp | Dùng thao tác lọc khi cần loại tất cả |
| Nghĩ có thứ tự nghĩa là đã tăng dần | Thứ tự dãy khác quy tắc sắp xếp | Sort khi có yêu cầu và comparator rõ |
| Nghĩ hai list cùng giá trị duy nhất là equals | List xét từng vị trí và số lần xuất hiện | So sánh đúng mô hình dữ liệu |
| Nghĩ get(index) luôn O(1) | Chi phí phụ thuộc triển khai | Chọn cách duyệt phù hợp |
| Nghĩ List nào cũng cho null và cho sửa | Những bảo đảm đó không đến từ tên kiểu | Đọc nguồn tạo và lớp cụ thể |

### Cẩn thận overload remove với số nguyên

Trong `List<Integer>`:

```java
numbers.remove(1);
```

chọn thao tác xóa theo chỉ số int, không có nghĩa “xóa giá trị Integer bằng 1”.

Muốn xóa theo giá trị có thể viết:

```java
numbers.remove(Integer.valueOf(1));
```

Hai cách đặt ra hai câu hỏi khác nhau. Khi cần xóa một lần xuất hiện đang được duyệt, chọn API duyệt có hỗ trợ thao tác phù hợp.

### Cẩn thận khi xóa và tiếp tục dùng chỉ số

Khi xóa một phần tử trong vòng lặp tăng chỉ số, phần tử phía sau có thể chuyển vào vị trí vừa xóa. Nếu tăng chỉ số ngay mà không thiết kế lại điều kiện, một phần tử có thể bị bỏ qua.

Đây là hệ quả trực tiếp của mô hình vị trí. Dùng removeIf hoặc iterator có hỗ trợ xóa thường rõ hơn khi mục tiêu là lọc dữ liệu. Không sửa cấu trúc list tùy tiện trong for-each rồi dựa vào việc một lần chạy không báo lỗi.

## 12. Cách chọn List theo nhu cầu dữ liệu

List thường phù hợp khi một hoặc nhiều điều sau đúng:

- Thứ tự các lần xuất hiện cần được giữ.
- Cùng một giá trị có thể xuất hiện nhiều lần với ý nghĩa riêng.
- Cần thao tác theo vị trí hiện tại.
- Cần trả một kết quả có thứ tự rõ ràng cho bên sử dụng.
- Equality theo cả dãy phản ánh đúng điều ứng dụng cần so sánh.

Nếu chỉ cần kiểm tra giá trị duy nhất hoặc tra cứu ổn định bằng khóa, hãy đánh giá một mô hình khác thay vì ép mọi yêu cầu vào chỉ số List.

Ngay cả khi chọn đúng interface, vẫn phải xác định nguồn có thể sửa hay không, chấp nhận null hay không và yêu cầu đồng thời ra sao.

## 13. Bài tập tự kiểm tra

1. Với `[A, B, A]`, nêu size, indexOf(A) và lastIndexOf(A).
2. Chèn X tại index 1 rồi xóa index 0. Hãy viết dãy và mọi chỉ số mới sau từng thao tác.
3. Giải thích khác biệt giữa add(1, X) và set(1, X) trên cùng một list có thể sửa.
4. Hai ArrayList và LinkedList chứa cùng dãy có thể bằng nhau không? Nếu đổi thứ tự một list thì sao?
5. Vì sao hai đối tượng khác tham chiếu nhưng bằng equals vẫn có thể cùng tồn tại trong list?
6. Đổi chương trình đầu để chỉ duyệt ngược nhưng không gọi Collections.reverse. Nguồn có bị đảo không?
7. Với một List.of giữ hai A, vì sao vừa có phần tử trùng vừa không cho sửa là hai đặc điểm không mâu thuẫn?
8. Nếu cần lưu một danh sách phát có bài hát lặp, điều gì bị mất khi chuyển nó thành Set?

Mô hình cần giữ là một dãy gồm các lần xuất hiện tại vị trí hiện tại. Truy cập, chèn, xóa, tìm kiếm theo giá trị, equality và lượt duyệt đều dựa trên mô hình đó, dù cách lưu trữ bên trong của từng lớp có thể khác nhau.
