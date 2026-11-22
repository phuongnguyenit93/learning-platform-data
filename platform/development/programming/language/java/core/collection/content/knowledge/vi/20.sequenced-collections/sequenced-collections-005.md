# reversed: view đảo thứ tự thay vì bản sao

## 1. Đảo cách nhìn dữ liệu là một quyết định khác với sao chép

Một danh sách sự kiện được lưu từ cũ tới mới nhưng màn hình cần đọc từ mới tới cũ. Có hai nhu cầu khác nhau:

- Nhìn cùng dữ liệu theo chiều ngược.
- Giữ một dãy riêng theo chiều ngược để dùng độc lập về sau.

Từ Java 21, reversed() cung cấp một **khung nhìn đảo thứ tự (reverse-ordered view)** cho các giao diện sequenced thích hợp. Nó không mặc định tạo một bản sao dữ liệu độc lập.

Với danh sách gốc a,b,c,d, có thể hình dung:

```text
cách nhìn gốc:       a → b → c → d
cách nhìn reversed:  d → c → b → a
                     cùng các phần tử của dữ liệu nền
```

Chỉ gọi reversed không tự đổi danh sách gốc thành d,c,b,a. Nó cung cấp một cách truy cập có chiều ngược.

Khi chương trình sửa được qua view, thay đổi có thể tác động dữ liệu nền theo hợp đồng. Nếu cần một dãy có các liên kết riêng, phải chủ động sao chép.

Bài phân biệt bốn khái niệm thường bị gộp:

| Khái niệm | Điều nó nói |
| --- | --- |
| Thứ tự gặp | Phần tử/ánh xạ được duyệt theo chiều nào |
| View | Một bề mặt truy cập gắn với dữ liệu nền |
| Bản sao cấu trúc | Một tập liên kết phần tử/ánh xạ riêng |
| Sao chép sâu | Tạo thêm dữ liệu phần tử theo mức độc lập do ứng dụng định nghĩa |

**Các ví dụ cần JDK 21 trở lên.** Chúng được biên dịch bằng --release 21 và chạy trên OpenJDK 24.0.2, không dùng preview.

## 2. Hợp đồng của reversed và cách hiểu phép sửa

### 2.1. Đầu và cuối đổi vai trò

`reversed` đảo encounter order, tức thứ tự gặp dữ liệu. Phần tử đầu ở view tương ứng phần tử cuối ở thứ tự gốc.

Với một List hỗ trợ các phép sửa được nêu, quan hệ theo cách nhìn là:

| Thao tác qua view đảo chiều | Vị trí tương ứng trong cách nhìn gốc |
| --- | --- |
| getFirst() | Phía cuối |
| getLast() | Phía đầu |
| set(0, value) | Thay phần tử cuối |
| addFirst(value) | Thêm về phía cuối |
| addLast(value) | Thêm về phía đầu |
| removeFirst() | Lấy và xóa phía cuối |
| removeLast() | Lấy và xóa phía đầu |

Bảng mô tả ý nghĩa của thứ tự, không khẳng định JVM bắt buộc gọi một tên hàm nội bộ nhất định.

Nếu List hiện có n phần tử và không có thay đổi chen giữa, phần tử ở chỉ số i của view tương ứng phần tử ở chỉ số n - 1 - i của danh sách gốc.

Vị trí chèn lại nằm giữa các phần tử: chèn tại chỉ số i của view tương ứng vị trí n - i trong cách nhìn gốc. Không dùng công thức truy cập n - 1 - i cho vị trí chèn.

### 2.2. Có một view không tự mở quyền sửa

Nếu triển khai cho sửa qua view, thay đổi được ghi xuyên về cấu trúc nền. Nhưng một danh sách không cho thêm/xóa vẫn có thể từ chối các thao tác ấy ở view.

Quyền set cũng có thể khác quyền thêm/xóa. Một danh sách cố định kích thước có thể thay phần tử nhưng không tăng/giảm số phần tử.

Ở mức [SequencedCollection Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html), khả năng thấy thay đổi từ dữ liệu nền qua view còn phụ thuộc triển khai. Không suy một cam kết phản ánh thay đổi tổng quát cho mọi lớp tùy biến chỉ từ chữ view.

Các ví dụ ArrayList và LinkedHashMap trong bài có sự liên hệ được giải thích cụ thể. Ứng dụng cần biết kiểu và hợp đồng mà nó dựa vào.

### 2.3. `reversed` không phải một phép sắp xếp

View đảo chiều thứ tự hiện tại. Một danh sách 8,2,5 cho thứ tự view 5,2,8, không phải tự động 2,5,8 hoặc 8,5,2.

Với cấu trúc sorted, view được xét theo quan hệ thứ tự đảo lại. Với map có thứ tự chèn, view nhìn các ánh xạ theo chiều ngược của thứ tự gặp.

Không áp một Comparator mới tùy ý chỉ vì muốn gọi reversed.

### 2.4. Kiểu trả về vẫn có thể giữ khả năng riêng

List.reversed trả List; Deque.reversed trả Deque; SortedSet.reversed và SortedMap.reversed giữ kiểu sorted tương ứng.

Qua List đảo chiều vẫn có chỉ số. Qua map đảo chiều vẫn thao tác theo khóa/ánh xạ. `reversed` không chuyển một map thành list.

Xem [List.reversed Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#reversed()) cho hợp đồng view và cách các thao tác nhạy với thứ tự được diễn giải.

## 3. Ví dụ 1: sửa qua List view và quan sát bản sao riêng

Lưu thành **ReversedListViewDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;

public class ReversedListViewDemo {
    public static void main(String[] args) {
        List<String> base = new ArrayList<>(List.of("a", "b", "c", "d"));
        List<String> view = base.reversed();
        List<String> copy = new ArrayList<>(view);
        System.out.println("base after creating view: " + base);
        System.out.println("view initially: " + view);
        System.out.println("copy initially: " + copy);

        view.set(1, "C");
        System.out.println("base after view set: " + base);
        view.addFirst("e");
        view.addLast("z");
        System.out.println("base after view end additions: " + base);
        System.out.println("view after end additions: " + view);

        System.out.println("view removeFirst: " + view.removeFirst());
        System.out.println("view removeLast: " + view.removeLast());
        System.out.println("base after view removals: " + base);
        base.addFirst("x");
        System.out.println("view after base addFirst: " + view);
        System.out.println("copy remains: " + copy);
        System.out.println("double reverse has base order: "
                + view.reversed().equals(base));

        List<String> duplicates = new ArrayList<>(List.of("x", "y", "x"));
        duplicates.reversed().remove("x");
        System.out.println("base after reversed remove x: " + duplicates);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 ReversedListViewDemo.java
java ReversedListViewDemo
```

Stdout:

```text
base after creating view: [a, b, c, d]
view initially: [d, c, b, a]
copy initially: [d, c, b, a]
base after view set: [a, b, C, d]
base after view end additions: [z, a, b, C, d, e]
view after end additions: [e, d, C, b, a, z]
view removeFirst: e
view removeLast: z
base after view removals: [a, b, C, d]
view after base addFirst: [d, C, b, a, x]
copy remains: [d, c, b, a]
double reverse has base order: true
base after reversed remove x: [x, y]
```

### 3.1. Tạo view không đảo dữ liệu gốc tại chỗ

Sau khi tạo view, base vẫn là a,b,c,d. View đọc theo d,c,b,a.

Copy được tạo bằng new ArrayList<>(view), nên lúc đầu cũng có d,c,b,a. Cùng dãy in ra không chứng minh view và copy có cùng chính sách chia sẻ.

Các lệnh tiếp theo mới làm sự khác nhau hiện rõ.

### 3.2. Set và hai phép thêm dùng hướng của view

View.set(1,"C") thay phần tử thứ hai theo chiều ngược, tức c ở vị trí gần cuối của base. Base trở thành a,b,C,d.

View.addFirst("e") đặt e ở cuối base. View.addLast("z") đặt z ở đầu base.

Vì vậy base là z,a,b,C,d,e, còn view đọc e,d,C,b,a,z. Không có hai bản danh sách tự đồng bộ bằng cách chép qua lại; chương trình đang dùng một view của cùng cấu trúc nền.

### 3.3. Xóa ở đầu/cuối cũng đổi hướng

`removeFirst` qua view lấy e, removeLast qua view lấy z. Base còn a,b,C,d.

Sau khi base được thêm x ở đầu, view trong ví dụ ArrayList này đọc d,C,b,a,x. Điều này giúp thấy sự chia sẻ không chỉ ở chiều sửa qua view.

Copy vẫn là d,c,b,a. Phép set hoặc thêm/xóa liên kết trong base không thay các liên kết đã chép vào copy.

### 3.4. Với phần tử trùng, “lần xuất hiện đầu” thuộc thứ tự đang nhìn

Danh sách riêng x,y,x có hai x. `remove`("x") qua view xét phía đầu của thứ tự đảo, nên nó xóa x ở cuối danh sách gốc.

Danh sách gốc còn x,y, không phải y,x.

Đây là lý do đổi chiều duyệt có thể đổi phần tử bị tác động bởi một thao tác nhạy với thứ tự, dù đối số truyền vào vẫn là cùng chuỗi "x".

### 3.5. Đảo hai lần và nhận dạng đối tượng là hai câu hỏi

Ví dụ xác nhận view.reversed có cùng thứ tự List với base bằng equals.

Không dùng kết quả này để suy mọi reversed().reversed() của mọi giao diện/triển khai đều bắt buộc trả một object là cùng một đối tượng với nguồn.

Hợp đồng mặc định của List có mô tả việc đảo view trở lại List nguồn; khi viết mã tổng quát, nên dựa vào ngữ nghĩa được kiểu cụ thể cam kết, không dựa vào tên lớp nội bộ hoặc số đối tượng view được tạo.

## 4. Phân biệt reversed, bản sao và đảo tại chỗ

### 4.1. Ba cách làm trả lời ba yêu cầu khác nhau

| Cách dùng với List | Kết quả chủ yếu |
| --- | --- |
| source.reversed() | Nhận view theo chiều ngược; không tự đảo source tại chỗ |
| new ArrayList<>(source.reversed()) | Tạo danh sách riêng chứa phần tử theo thứ tự view tại lần chép |
| List.copyOf(source.reversed()) | Tạo kết quả List không sửa được, giữ thứ tự phần tử đã lấy và không nhận null |
| Collections.reverse(source) | Đảo các vị trí trong chính danh sách được truyền vào nếu hỗ trợ thay phần tử |

Collections.reverse nhận List và trả void. Đây là thuật toán sửa tại chỗ, khác phương thức reversed trả view. Tài liệu [Collections.reverse Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#reverse(java.util.List)) nêu rõ sự khác biệt này.

Không chọn cách làm chỉ vì chúng đều có chữ reverse; cần xác định dữ liệu gốc có phải thay đổi hay không và kết quả có cần độc lập về cấu trúc hay không.

### 4.2. Bản sao cấu trúc vẫn có thể dùng chung phần tử

new ArrayList<>(view) chép các tham chiếu phần tử vào cấu trúc riêng. Nó không tự nhân bản mọi object phần tử.

Nếu phần tử là một Task có trường name thay đổi được, sửa chính Task ấy có thể được nhìn thấy qua cả nguồn, view lẫn bản sao đang giữ cùng Task.

Ngược lại, xóa một phần tử khỏi danh sách copy không tự xóa liên kết tương ứng trong base.

Muốn độc lập cả dữ liệu phần tử, cần chọn mô hình bất biến hoặc một chính sách sao chép sâu phù hợp. Không có một phép sao chép sâu tổng quát đúng cho mọi loại object chỉ bằng constructor ArrayList.

### 4.3. Không sửa được không có nghĩa là ảnh chụp độc lập

Collections.unmodifiableList tạo một view không cho người dùng sửa qua bề mặt ấy. Nếu danh sách nền còn thay đổi và view được gắn với nó, người đọc vẫn có thể thấy dữ liệu thay đổi.

List.copyOf lại có hợp đồng kết quả không phản ánh những thay đổi cấu trúc sau đó ở Collection nguồn. Tuy nhiên các object phần tử khả biến vẫn có thể được chia sẻ.

Hai lựa chọn khác nhau ở cả quyền sửa qua kết quả và quan hệ với cấu trúc nguồn. Tài liệu [List.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) và [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) là các hợp đồng cần đối chiếu.

### 4.4. Khi có null, cách chép cũng là một quyết định

Một ArrayList có thể giữ phần tử null; view đảo chiều có thể đọc null ấy nếu nó nằm ở vị trí đang hỏi.

List.copyOf không nhận phần tử null. Vì vậy đổi từ constructor ArrayList sang List.copyOf không chỉ là đổi quyền sửa; nó còn đổi điều kiện dữ liệu hợp lệ.

Không để một sự thay thế “cho gọn” vô tình tạo lỗi ở ranh giới dữ liệu.

## 5. Ví dụ 2: cấu trúc riêng, phần tử dùng chung và các mức hạn chế sửa

Lưu thành **ViewCopyAndElementSharing.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ViewCopyAndElementSharing {
    static final class Task {
        String name;

        Task(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        Task a = new Task("A");
        Task b = new Task("B");
        List<Task> base = new ArrayList<>(List.of(a, b));
        List<Task> view = base.reversed();
        List<Task> copy = new ArrayList<>(view);
        List<Task> frozen = List.copyOf(view);

        base.addLast(new Task("C"));
        System.out.println("view after adding C: " + view);
        System.out.println("copy after adding C: " + copy);
        System.out.println("frozen after adding C: " + frozen);

        a.name = "A*";
        System.out.println("base after element edit: " + base);
        System.out.println("copy after element edit: " + copy);
        System.out.println("frozen after element edit: " + frozen);
        copy.removeFirst();
        System.out.println("copy after removing its first: " + copy);
        System.out.println("base after copy removal: " + base);

        try {
            frozen.reversed().addFirst(new Task("D"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("unmodifiable reversed add: rejected");
        }

        String[] array = {"left", "right"};
        List<String> fixed = Arrays.asList(array);
        List<String> fixedView = fixed.reversed();
        fixedView.set(0, "RIGHT");
        System.out.println("array after reversed set: " + Arrays.toString(array));
        try {
            fixedView.addLast("extra");
        } catch (UnsupportedOperationException expected) {
            System.out.println("fixed-size reversed add: rejected");
        }

        List<Integer> changingBase = new ArrayList<>(List.of(1, 2));
        List<Integer> readOnlyView = Collections.unmodifiableList(changingBase.reversed());
        changingBase.addLast(3);
        System.out.println("unmodifiable view after source add: " + readOnlyView);

        List<Integer> inPlace = new ArrayList<>(List.of(1, 2, 3));
        Collections.reverse(inPlace);
        System.out.println("Collections.reverse changed list: " + inPlace);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 ViewCopyAndElementSharing.java
java ViewCopyAndElementSharing
```

Stdout:

```text
view after adding C: [C, B, A]
copy after adding C: [B, A]
frozen after adding C: [B, A]
base after element edit: [A*, B, C]
copy after element edit: [B, A*]
frozen after element edit: [B, A*]
copy after removing its first: [A*]
base after copy removal: [A*, B, C]
unmodifiable reversed add: rejected
array after reversed set: [left, RIGHT]
fixed-size reversed add: rejected
unmodifiable view after source add: [3, 2, 1]
Collections.reverse changed list: [3, 2, 1]
```

### 5.1. Thêm C phân biệt view với hai kết quả chép

Base ban đầu chứa Task A và B; cả view, copy và frozen được tạo trước khi thêm C.

Sau khi thêm C, view đọc C,B,A, còn copy và frozen vẫn có hai liên kết B,A. Điều này thể hiện độc lập cấu trúc của kết quả chép.

Tên frozen trong ví dụ chỉ là tên biến cho kết quả List.copyOf. Nó không có nghĩa mọi object được tham chiếu bên trong đã bất biến sâu.

### 5.2. Sửa A cho thấy phần tử vẫn có thể được chia sẻ

Đổi a.name thành A* làm cả base, copy và frozen in tên mới của cùng Task.

Sau đó copy.removeFirst chỉ bỏ liên kết tới B trong copy. Base vẫn giữ A*,B,C.

Cần phân biệt “sửa đối tượng B” với “bỏ B khỏi một danh sách”. Hai thao tác tác động hai tầng khác nhau.

### 5.3. Cố định kích thước không giống cấm mọi thay đổi

Arrays.asList tạo List cố định kích thước gắn với mảng. View đảo chiều của nó có thể dùng set thay phần tử cuối mảng, nên array trở thành left,RIGHT.

AddLast lại bị từ chối vì nó đòi tăng số phần tử.

Điều này đúng với hợp đồng [Arrays.asList Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)), không phải một quyền mới được view tự cấp.

### 5.4. View chỉ đọc vẫn nhìn thay đổi, còn reverse tại chỗ đổi nguồn

Biến readOnlyView không cho sửa qua lớp bao, nhưng khi changingBase thêm 3, nó đọc 3,2,1.

Phần inPlace là một danh sách riêng để minh họa Collections.reverse: chính danh sách ấy đổi từ 1,2,3 thành 3,2,1.

Hai dãy 3,2,1 có thể trông giống nhau ở đầu ra, nhưng một dãy đến từ cách nhìn ngược trên nguồn 1,2,3, còn dãy kia là dữ liệu đã bị đảo tại chỗ.

## 6. `reversed` trên Map, SortedSet và Deque

### 6.1. Map đảo thứ tự ánh xạ, không tráo key với value

Một SequencedMap có các view khóa, giá trị và entry. View map đảo chiều làm các view này được đọc theo encounter order đảo lại.

`get` và put vẫn làm việc theo khóa. Không biến key thành value, không sắp xếp riêng các value, không tạo một nhóm ánh xạ mới chỉ vì gọi reversed.

Với các thao tác đặt biên được hỗ trợ:

| Qua map view đảo chiều | Phía tương ứng trong map nền |
| --- | --- |
| firstEntry() | Ánh xạ cuối |
| lastEntry() | Ánh xạ đầu |
| putFirst(key, value) | Đặt về phía cuối |
| putLast(key, value) | Đặt về phía đầu |
| pollFirstEntry() | Lấy và xóa phía cuối |
| pollLastEntry() | Lấy và xóa phía đầu |

[SequencedMap Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html) mô tả hợp đồng đảo encounter order cho map và các view của nó.

### 6.2. Chính sách map cụ thể vẫn còn hiệu lực

LinkedHashMap mặc định trong ví dụ dùng thứ tự chèn. Sửa value của khóa b đang có không tự biến ánh xạ b thành khóa mới ở một vị trí khác.

Nếu dùng LinkedHashMap theo thứ tự truy cập, một phép truy cập như get có thể thay thứ tự theo chính sách map. View đảo chiều không đóng băng chính sách đó. Cần đọc hợp đồng của chế độ đang chọn, không chỉ nhìn kiểu SequencedMap.

Tài liệu [LinkedHashMap.reversed Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html#reversed()) còn nêu cụ thể việc sửa qua view được truyền tới map và sửa map được nhìn thấy qua view của triển khai này.

### 6.3. Đảo SortedMap/SortedSet vẫn giữ quy tắc sorted

View của TreeMap/TreeSet được xét theo thứ tự so sánh đảo lại. Nó vẫn không mở quyền đặt vị trí tùy ý.

`putFirst`/putLast của SortedMap và addFirst/addLast của SortedSet bị từ chối. Việc một khóa hoặc phần tử tình cờ sẽ nằm ở biên không biến thao tác đó thành được hỗ trợ.

`put`/add thông thường có thể sửa được trên view của những cấu trúc mutable ấy; vị trí được thứ tự so sánh quyết định.

Xem [SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html) và [SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html) của Java 21.

### 6.4. Deque đảo hướng hai đầu

Với Deque, head/tail đổi vai trò trong cách nhìn ngược. `removeFirst` qua view có thể lấy phần tử nằm ở phía cuối deque gốc.

Điều kiện rỗng và hợp đồng của từng phép vẫn cần được giữ. `getFirst` của deque rỗng ném NoSuchElementException; các API peek/poll có quy tắc khác.

View không tự cung cấp dữ liệu nếu nguồn đã bị xóa hết. Đối chiếu [Deque.reversed Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html#reversed()).

## 7. Ví dụ 3: view dùng chung ánh xạ và giữ giới hạn của cấu trúc nền

Lưu thành **ReversedMapAndEndViews.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.SequencedMap;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class ReversedMapAndEndViews {
    public static void main(String[] args) {
        SequencedMap<String, Integer> base = new LinkedHashMap<>();
        base.put("a", 1);
        base.put("b", 2);
        base.put("c", 3);
        SequencedMap<String, Integer> view = base.reversed();
        System.out.println("map view initially: " + new ArrayList<>(view.entrySet()));
        view.putFirst("d", 4);
        view.putLast("z", 0);
        view.put("b", 20);
        view.remove("a");
        System.out.println("base after view edits: " + new ArrayList<>(base.entrySet()));

        base.put("e", 5);
        System.out.println("view after base put: " + new ArrayList<>(view.entrySet()));
        System.out.println("view pollFirstEntry: " + view.pollFirstEntry());
        System.out.println("base remaining: " + new ArrayList<>(base.entrySet()));
        System.out.println("view values: " + new ArrayList<>(view.sequencedValues()));

        SortedMap<Integer, String> sorted = new TreeMap<>();
        sorted.put(1, "A");
        sorted.put(2, "B");
        sorted.put(3, "C");
        SortedMap<Integer, String> sortedView = sorted.reversed();
        try {
            sortedView.putFirst(4, "D");
        } catch (UnsupportedOperationException expected) {
            System.out.println("reversed SortedMap putFirst: rejected");
        }
        sortedView.put(4, "D");
        System.out.println("sorted base keys: " + new ArrayList<>(sorted.keySet()));
        System.out.println("sorted view keys: " + new ArrayList<>(sortedView.keySet()));

        SortedSet<Integer> set = new TreeSet<>(List.of(1, 2, 3));
        SortedSet<Integer> setView = set.reversed();
        try {
            setView.addFirst(4);
        } catch (UnsupportedOperationException expected) {
            System.out.println("reversed SortedSet addFirst: rejected");
        }
        setView.add(4);
        System.out.println("set base: " + new ArrayList<>(set));
        System.out.println("set view: " + new ArrayList<>(setView));

        Deque<String> deque = new ArrayDeque<>(List.of("front", "back"));
        Deque<String> dequeView = deque.reversed();
        System.out.println("reversed deque removeFirst: " + dequeView.removeFirst());
        System.out.println("deque remaining: " + new ArrayList<>(deque));
        deque.clear();
        try {
            dequeView.getFirst();
        } catch (NoSuchElementException expected) {
            System.out.println("empty reversed deque getFirst: NoSuchElementException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 ReversedMapAndEndViews.java
java ReversedMapAndEndViews
```

Stdout:

```text
map view initially: [c=3, b=2, a=1]
base after view edits: [z=0, b=20, c=3, d=4]
view after base put: [e=5, d=4, c=3, b=20, z=0]
view pollFirstEntry: e=5
base remaining: [z=0, b=20, c=3, d=4]
view values: [4, 3, 20, 0]
reversed SortedMap putFirst: rejected
sorted base keys: [1, 2, 3, 4]
sorted view keys: [4, 3, 2, 1]
reversed SortedSet addFirst: rejected
set base: [1, 2, 3, 4]
set view: [4, 3, 2, 1]
reversed deque removeFirst: back
deque remaining: [front]
empty reversed deque getFirst: NoSuchElementException
```

### 7.1. Các thao tác view tác động cùng map

Map nền bắt đầu có a=1,b=2,c=3. View đọc c=3,b=2,a=1.

`putFirst`("d",4) qua view đặt d về cuối base. `putLast`("z",0) qua view đặt z về đầu base.

`put`("b",20) đổi value của b; remove("a") bỏ ánh xạ a ở dữ liệu chung. Vì vậy base còn z=0,b=20,c=3,d=4.

Không cần một bước “đồng bộ bản sao” sau các thao tác này.

### 7.2. Thêm ở base rồi xóa ở đầu view

Khi base thêm e=5, view của LinkedHashMap trong ví dụ đọc e trước. `pollFirstEntry` trên view lấy và xóa e=5, tương ứng phía cuối thứ tự base.

Dãy value 4,3,20,0 đi cùng các ánh xạ d,c,b,z trong view. Các số không được sắp xếp tăng hoặc giảm theo giá trị số.

Nếu chương trình chỉ lấy value mà quên thứ tự đi cùng khóa, rất dễ diễn giải sai kết quả map đảo chiều.

### 7.3. Sorted view sửa được nhưng không nhận phép ép biên

SortedMap view từ chối putFirst(4,"D"), sau đó nhận put(4,"D"). Base có thứ tự khóa 1,2,3,4; view đọc 4,3,2,1.

SortedSet view cũng từ chối addFirst(4), nhưng add(4) thông thường thành công. Tập nền vẫn sắp theo thứ tự gốc, view thể hiện chiều đảo.

Cả hai thí nghiệm dùng phần tử mới ở đúng biên tự nhiên để tránh hiểu nhầm rằng chỉ cần chọn một giá trị “phù hợp” là ép vị trí được.

### 7.4. Deque view có cùng vòng đời dữ liệu nền trong ví dụ

`removeFirst` qua view lấy "back", nên deque gốc chỉ còn "front".

Sau deque.clear, getFirst qua view ném ngoại lệ vì dữ liệu nền đã rỗng. View không giữ một bản sao riêng của hai chuỗi để tiếp tục trả lại như lúc tạo.

## 8. Chi phí, quyền sở hữu và dữ liệu dùng chung

### 8.1. View không có nghĩa không tạo object nào

Một triển khai có thể tạo object view để chuyển các lời gọi sang dữ liệu nền theo hướng ngược. Không sao chép toàn bộ phần tử khác với không cấp phát bất kỳ object nào.

Không dựa vào số object được tạo, tên lớp triển khai của view hoặc phép so đồng nhất đối tượng bằng == như một bảo đảm hiệu năng của API tổng quát.

Hợp đồng reversed không áp một độ phức tạp duy nhất cho mọi collection, mọi thao tác và mọi lớp tùy biến.

### 8.2. Sao chép phải giữ dữ liệu riêng của cấu trúc kết quả

Một ArrayList mới chứa n phần tử cần giữ n tham chiếu phần tử trong cấu trúc của nó và phải lấy dữ liệu để chép.

Nếu chỉ cần duyệt ngược một lần trên một cấu trúc thích hợp, một view có thể diễn đạt nhu cầu mà không chủ động chép toàn bộ dữ liệu.

Nếu cần kết quả tách khỏi việc thêm/xóa ở nguồn, chi phí chép lại phục vụ một yêu cầu thật. Không bỏ bản sao chỉ để tối ưu mà làm mất tính ổn định được bên dùng trông đợi.

### 8.3. Trả view ra ngoài nghĩa là chia sẻ một quan hệ với nguồn

Nếu API trả một view sửa được của danh sách nội bộ, bên gọi có thể sửa dữ liệu nền qua bề mặt đó.

Bọc chỉ đọc có thể hạn chế quyền sửa qua giá trị trả về. Nó không mặc định làm nội dung trở thành ảnh chụp độc lập hoặc làm các phần tử bên trong bất biến.

Khi thiết kế kết quả trả về, nên trả lời rõ:

1. Bên nhận có được sửa cấu trúc không?
2. Bên nhận có được thấy những lần thêm/xóa ở nguồn về sau không?
3. Các object phần tử có được dùng chung không?
4. Có cần một phiên bản dữ liệu ổn định tại một thời điểm không?

Không dùng một kiểu List chung để che tất cả các quyết định ấy.

### 8.4. View không tự tách tuổi thọ khỏi nguồn

Một view gắn với dữ liệu nền có thể cần giữ liên hệ tới nguồn để thực hiện các lời gọi sau. Không suy rằng nguồn có thể được giải phóng độc lập chỉ vì đã giữ một biến view khác tên.

Nếu cần giữ riêng một tập kết quả mà không phụ thuộc cấu trúc nguồn, hãy chọn một cách chép phù hợp và xét cả dữ liệu phần tử được chia sẻ.

Đây là hệ quả của quyền sở hữu dữ liệu, không phải lý do mọi trường hợp đều phải sao chép.

### 8.5. Không có bảo đảm an toàn luồng mới

ArrayList không tự trở thành an toàn cho sửa đồng thời khi được nhìn qua reversed.

Nếu một luồng sửa nguồn trong lúc luồng khác duyệt view, phải tuân hợp đồng đồng thời/iterator của triển khai. Không nhận được ConcurrentModificationException không chứng minh cách truy cập ấy an toàn.

Sao chép từ nguồn đang bị sửa cũng không tự tạo một ảnh chụp nguyên tử. Muốn ảnh chụp nhất quán, cần quy trình đọc/công bố dữ liệu hoặc đồng bộ phối hợp đúng với các bên sửa.

View chỉ đọc cũng không phải một khóa đồng bộ và không tự đóng băng dữ liệu dùng chung.

## 9. Chọn view hay bản sao từ yêu cầu sử dụng

| Tình huống | Lựa chọn cần đánh giá |
| --- | --- |
| Duyệt các sự kiện hiện có theo chiều ngược, vẫn chấp nhận quan hệ với nguồn | `reversed` view của kiểu thích hợp |
| Sửa đầu của cách nhìn ngược và muốn cập nhật chính nguồn | View cho phép phép sửa tương ứng |
| Xuất một danh sách riêng giữ thứ tự đã đọc | Chép theo view, chẳng hạn một ArrayList mới |
| Trả kết quả không cho thêm/xóa/thay phần tử và không phản ánh sửa cấu trúc nguồn | List.copyOf nếu chính sách null và kiểu phần tử phù hợp |
| Cấm sửa qua một bề mặt nhưng vẫn muốn chia sẻ dữ liệu nền | View chỉ đọc với hợp đồng đã công bố |
| Độc lập cả dữ liệu phần tử khả biến | Dữ liệu bất biến hoặc chính sách sao chép sâu riêng |
| Muốn chính danh sách hiện tại đổi vị trí theo chiều ngược | Collections.reverse khi danh sách hỗ trợ thao tác cần thiết |

Không có một lựa chọn luôn đúng hơn. View phục vụ quan hệ chia sẻ có chủ đích; bản sao phục vụ nhu cầu độc lập có chủ đích.

Khi kết quả chỉ được dùng trong một phạm vi ngắn để đọc, view thường dễ diễn đạt. Khi kết quả đi qua ranh giới thời gian, tác vụ hoặc bên sở hữu, cần công bố chính sách ổn định và quyền sửa rõ hơn.

## 10. Cách kiểm tra mà không nhầm view với bản sao

### 10.1. Kiểm tra bằng thao tác phân biệt được hai mô hình

Chỉ so dãy in ra ngay sau khi tạo chưa đủ, vì view và copy có thể cùng in d,c,b,a.

Một kiểm tra có ý nghĩa cần xét những hành vi khác nhau:

- Tạo view có giữ nguyên cách nhìn gốc không?
- Sửa một vị trí qua view có tác động vị trí đối ứng ở nguồn không?
- Thêm/xóa ở hai đầu qua view có đúng hướng không?
- Bản sao cấu trúc có giữ các liên kết đã chép khi nguồn thêm/xóa không?
- Các phần tử khả biến có còn được chia sẻ không?
- View có giữ đúng giới hạn set/thêm/xóa của nguồn không?

Với map, kiểm tra cả thứ tự entry/key/value và việc một thao tác qua view cập nhật đúng ánh xạ nền.

### 10.2. Không dùng equals của mọi loại để chứng minh thứ tự

List.equals có ý nghĩa theo dãy. Nhưng Map.equals và Set.equals không tự so thứ tự gặp như List.

Một map hoặc set có thể bằng view đảo chiều theo hợp đồng ánh xạ/thành viên mà thứ tự duyệt vẫn ngược nhau.

Nếu đang kiểm tra thứ tự, chủ động đối chiếu dãy phần tử/entry theo cách duyệt, như các ArrayList tạo để in kết quả trong ví dụ. Đừng dùng một kết quả equals true làm chứng cứ rằng thứ tự không đổi.

### 10.3. Giữ điều kiện rỗng, null và thao tác tùy chọn trong bộ kiểm tra

Một nguồn rỗng, nguồn có một phần tử, nguồn có phần tử trùng và nguồn chứa null có thể làm lộ những giả định mà ví dụ nhiều phần tử khác nhau không cho thấy.

Với phép chèn chỉ số, cần phân biệt các chỉ số phần tử 0 tới n-1 với các vị trí chèn 0 tới n.

Với dữ liệu hạn chế sửa, kiểm tra riêng thay phần tử, thêm và xóa. Không suy từ một phép set thành công rằng add sẽ thành công, hoặc từ add bị từ chối rằng get không còn hoạt động.

Kiểm thử nên yêu cầu hành vi API đã công bố, không yêu cầu một tên lớp view, một địa chỉ object hay một chi tiết tối ưu nội bộ cụ thể.

## 11. Các lỗi phổ biến

| Cách hiểu | Điều cần sửa |
| --- | --- |
| `reversed` đã đảo source tại chỗ | Nó trả view đảo hướng; chỉ tạo view không tự đổi thứ tự gốc |
| Hai biến có cùng dãy ban đầu thì đều là bản sao | Cần kiểm tra quan hệ chia sẻ sau sửa đổi |
| AddFirst của view phải thêm đầu source | Hướng đầu/cuối đã đảo |
| Chỉ số truy cập và chỉ số chèn dùng cùng công thức | Truy cập dùng n-1-i, vị trí chèn dùng n-i trong mô hình List đã nêu |
| `remove` phần tử trùng luôn xóa cùng object như nguồn | Lần xuất hiện đầu được xác định theo thứ tự view |
| Copy ArrayList tự nhân bản mọi phần tử | Nó chép cấu trúc tham chiếu, không tự sao chép sâu |
| List.copyOf làm mọi phần tử bên trong bất biến | Phần tử khả biến vẫn có thể được dùng chung |
| View chỉ đọc là ảnh chụp độc lập | Quyền sửa qua view khác với quan hệ phản ánh dữ liệu nguồn |
| Fixed-size nghĩa không set được | Arrays.asList có thể thay phần tử nhưng không đổi kích thước |
| `reversed` mở khóa addFirst của SortedSet | Nó giữ giới hạn của mô hình sorted |
| Map đảo chiều là map hoán đổi key/value | Chỉ encounter order của ánh xạ bị đảo |
| View không cấp phát gì và mọi thao tác đều O(1) | API tổng quát không hứa điều ấy |
| Chép từ nguồn đang sửa luôn là ảnh chụp nguyên tử | Cần cơ chế nhất quán riêng |
| `reversed` tự bảo vệ an toàn luồng | Hợp đồng đồng thời của triển khai vẫn quyết định |

## 12. Bài tập tự kiểm tra

### Bài 1. Sau khi tạo view, nguồn có đổi không?

Base là 1,2,3. Chỉ gọi base.reversed và giữ kết quả, chưa sửa gì. Base có tự trở thành 3,2,1 không?

**Gợi ý trả lời:** Không. View đọc theo chiều ngược; cách nhìn gốc vẫn là 1,2,3.

### Bài 2. Thêm ở đầu view nằm ở đâu?

Một ArrayList a,b,c có view đảo chiều sửa được. View.addFirst("x") làm base thành dãy nào?

**Gợi ý trả lời:** Dãy base thành a,b,c,x. Phía đầu view tương ứng phía cuối base.

### Bài 3. Chỉ số 0 của view là vị trí nào?

Nguồn có n phần tử, không có thay đổi chen giữa. View.set(0, value) tác động chỉ số nào của List nguồn?

**Gợi ý trả lời:** Chỉ số n-1. Với phép chèn tại chỉ số 0 của view thì vị trí chèn đối ứng lại là n.

### Bài 4. Vì sao bản sao vẫn thấy Task đổi tên?

Copy được tạo bằng new ArrayList<>(view). Sửa một trường của chính Task đang được cả hai giữ. Có mâu thuẫn với việc copy có cấu trúc riêng không?

**Gợi ý trả lời:** Không. Cấu trúc riêng vẫn có thể giữ cùng tham chiếu Task; sao chép cấu trúc không phải sao chép sâu.

### Bài 5. Chỉ đọc có đồng nghĩa ổn định không?

Collections.unmodifiableList bọc một view gắn với nguồn còn thay đổi. Có thể coi nó là ảnh chụp độc lập không?

**Gợi ý trả lời:** Không. Nó hạn chế sửa qua bề mặt ấy, không tự tách dữ liệu nền.

### Bài 6. Có thể dùng List.copyOf khi có null không?

ArrayList nguồn chứa null và view đọc được phần tử ấy. Đổi sang List.copyOf(view) có luôn giữ cùng điều kiện hợp lệ không?

**Gợi ý trả lời:** Không. List.copyOf từ chối phần tử null.

### Bài 7. TreeMap view có nhận putFirst không?

Khóa mới sẽ là phần tử đầu của chiều ngược. Điều đó có làm putFirst trên SortedMap view được phép không?

**Gợi ý trả lời:** Không. SortedMap không hỗ trợ ép vị trí bằng putFirst/putLast; put thông thường mới đi qua quy tắc sắp xếp.

### Bài 8. Map view có xóa trên một bản riêng không?

`pollFirstEntry` trên view LinkedHashMap sửa được lấy một entry. Entry tương ứng ở map nền có còn vì “đó chỉ là view” không?

**Gợi ý trả lời:** Không. Phép xóa qua view được ghi xuyên tới map nền theo hợp đồng triển khai.

### Bài 9. Double reversed có cần so địa chỉ không?

Muốn kiểm tra một List đảo hai lần có khôi phục thứ tự gặp, có cần dùng == làm điều kiện đúng tổng quát không?

**Gợi ý trả lời:** Không. Hãy kiểm tra ngữ nghĩa theo hợp đồng cụ thể; không mở rộng một tối ưu nhận dạng object sang mọi giao diện và triển khai.

### Bài 10. Collections.reverse khác reversed ở điểm nào?

Một phương thức trả view, một phương thức sửa danh sách tại chỗ. Cần chọn gì nếu yêu cầu là giữ nguyên thứ tự nguồn và chỉ duyệt ngược?

**Gợi ý trả lời:** Đánh giá reversed view phù hợp; không dùng Collections.reverse trên nguồn khi không muốn đổi vị trí trong nguồn.

## 13. Tài liệu đối chiếu

- [SequencedCollection — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): view đảo thứ tự, các phép hai đầu và giới hạn của hợp đồng tổng quát.
- [List.reversed — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#reversed()): view List và ý nghĩa thao tác theo chiều ngược.
- [List.copyOf — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): kết quả không sửa được, thứ tự, null và quan hệ với nguồn.
- [Collections — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): reverse tại chỗ và các lớp bao chỉ đọc.
- [Arrays.asList — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)): List cố định kích thước gắn với mảng.
- [SequencedMap — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): thứ tự ánh xạ, các view và thao tác ở biên.
- [LinkedHashMap — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): chính sách encounter order và liên hệ giữa reversed view với map.
- [SortedMap — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html): view đảo chiều theo thứ tự khóa và giới hạn ép vị trí.
- [SortedSet — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html): view đảo chiều theo thứ tự phần tử và giới hạn ép vị trí.
- [Deque — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html): hai đầu của deque và reversed view.
- [ArrayList — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html): cấu trúc List và yêu cầu đồng bộ khi có truy cập sửa đồng thời.
