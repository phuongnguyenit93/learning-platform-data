# Arrays.asList và danh sách kích thước cố định dùng chung mảng

## 1. Một cách nhìn List vào chính các ô của mảng

Một API đang có mảng String, trong khi một đoạn xử lý khác muốn nhận List. Nếu nhu cầu là thao tác với các phần tử đang nằm trong mảng mà không cần tăng hay giảm số vị trí, `Arrays.asList` cung cấp một cầu nối phù hợp.

Điểm cần hiểu ngay từ đầu là **List trả về dùng chung mảng nền**. Khi truyền một mảng tham chiếu phù hợp vào phương thức, các phần tử không tự được chuyển sang một vùng chứa ArrayList độc lập. List là một khung nhìn (view) cho phép truy cập dữ liệu theo giao diện List.

Có thể hình dung mảng có ba ô: ô 0, ô 1, ô 2. Cách truy cập bằng mảng dùng `array[index]`; cách truy cập qua view dùng `list.get(index)` hoặc `list.set(index, value)`. Chúng vẫn làm việc với các vị trí lưu phần tử của cùng mảng nền.

Hai đặc điểm phải được tách riêng:

- **Kích thước cố định:** List có số vị trí tương ứng với chiều dài mảng, không hỗ trợ thao tác làm số vị trí thay đổi.
- **Phần tử có thể được thay:** việc đặt một tham chiếu khác vào vị trí hiện có vẫn được hỗ trợ nếu đáp ứng ràng buộc kiểu của mảng.

Vì vậy, kích thước cố định không có nghĩa là chỉ đọc, cũng không có nghĩa là bất biến. Sự khác biệt này ảnh hưởng đến quyền sửa, sao chép dữ liệu, việc truyền tham số và cách chọn một List cho bước xử lý tiếp theo.

Bài học bắt đầu bằng quan hệ hai chiều giữa mảng và view, rồi kiểm chứng những thao tác được hỗ trợ. Sau đó mới xét varargs, mảng nguyên thủy, lựa chọn bản sao và ràng buộc kiểu mảng. Người học cần biết tham chiếu, mảng, List, get/set và ngoại lệ cơ bản.

Các chương trình đều độc lập, dùng Java 17; tên tệp, lệnh biên dịch và stdout được ghi kèm từng chương trình. Các ví dụ chỉ dùng thư viện chuẩn Java.

## 2. Hợp đồng của Arrays.asList

Chữ ký phương thức là `static <T> List<T> asList(T... array)`. Cú pháp varargs cho phép truyền một mảng phù hợp hoặc nhiều đối số phần tử; kết quả có giao diện List.

| Thuộc tính | Ý nghĩa khi dùng |
| --- | --- |
| Thứ tự | Theo các vị trí của mảng tham số |
| Kích thước | Cố định bằng số phần tử của mảng tham số |
| Quan hệ với mảng | Thay phần tử ở một bên được nhìn thấy ở bên kia |
| Thay phần tử | Có, trong phạm vi chỉ số và kiểu lưu trữ hợp lệ |
| Thêm/xóa vị trí | Không hỗ trợ |
| Phần tử null | Có thể có trong mảng tham chiếu |
| Chính mảng đầu vào null | Không phải đầu vào hợp lệ |
| Kiểu trả về | List; không cam kết là java.util.ArrayList |

Phương thức không loại trùng. Nếu mảng có cùng một giá trị tại nhiều vị trí, List vẫn có từng vị trí tương ứng. Mảng rỗng hợp lệ tạo List rỗng có kích thước cố định bằng 0.

Các chỉ số dùng trong get/set vẫn từ 0 đến size - 1. “Không cho thay kích thước” không làm chỉ số ngoài phạm vi trở thành hợp lệ. Một List ba phần tử chỉ có các vị trí 0, 1 và 2 để thay phần tử.

Không ép kết quả thành `java.util.ArrayList` để có các khả năng của ArrayList. Hợp đồng được trả ra là List với hành vi đã nêu. Khi cần một ArrayList độc lập, hãy tạo nó bằng hàm khởi tạo nhận Collection.

Tài liệu chính thức: [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)). Mô tả “dùng chung mảng” là một phần quan trọng của hợp đồng, không phải một chi tiết tình cờ được phát hiện trong công cụ gỡ lỗi.

## 3. Thí nghiệm thay phần tử theo cả hai chiều

Lưu thành `ArrayBackedViewDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class ArrayBackedViewDemo {
    public static void main(String[] args) {
        String[] source = {"red", "green", "blue"};
        List<String> view = Arrays.asList(source);

        String old = view.set(1, "lime");
        System.out.println("old=" + old);
        System.out.println("arrayAfterSet=" + Arrays.toString(source));

        source[2] = "navy";
        System.out.println("viewAfterArrayEdit=" + view);
        System.out.println("size=" + view.size());

        source = new String[]{"new"};
        System.out.println("reassignedVariable=" + Arrays.toString(source));
        System.out.println("viewStillOnOriginal=" + view);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ArrayBackedViewDemo.java
java ArrayBackedViewDemo
```

Stdout:

```text
old=green
arrayAfterSet=[red, lime, blue]
viewAfterArrayEdit=[red, lime, navy]
size=3
reassignedVariable=[new]
viewStillOnOriginal=[red, lime, navy]
```

Lời gọi `view.set(1, "lime")` thay ô thứ hai và trả lại phần tử cũ green. Mảng source ngay lập tức có lime ở vị trí ấy. Tiếp theo, việc gán navy vào `source[2]` được quan sát qua view mà không cần gọi lại Arrays.asList.

Hai lần sửa tác động theo hai hướng nhưng có cùng nguyên nhân: mảng và List đang cùng cung cấp đường truy cập đến các vị trí phần tử của mảng nền. Không có bước đồng bộ dữ liệu thủ công nào trong chương trình.

Đoạn cuối gán biến source sang một mảng mới chỉ có một phần tử. View vẫn hiển thị ba phần tử của mảng ban đầu. Phải phân biệt:

| Thao tác | Đối tượng nào thay đổi? |
| --- | --- |
| `source[2] = "navy"` | Một ô trong mảng mà source đang trỏ đến |
| `source = new String[]{"new"}` | Giá trị tham chiếu của riêng biến source |

Gán lại biến không thay đổi mảng cũ và không làm view chuyển sang mảng mới. View đã giữ quan hệ với đối tượng mảng được truyền lúc tạo, không giữ một cơ chế theo dõi biến cục bộ của người gọi.

Nếu mảng ban đầu còn được nhìn thấy qua view, nó vẫn là đối tượng dữ liệu đang được sử dụng dù biến nguồn đã chuyển hướng. Điều này cũng giúp giải thích vì sao tạo view không là một phép sao chép dùng để bảo vệ dữ liệu khỏi mọi tham chiếu bên ngoài.

## 4. Kích thước cố định vẫn cho phép nhiều thao tác sửa

`set` thay phần tử tại một vị trí có sẵn nên không cần đổi chiều dài mảng. Một số thao tác khác cũng chỉ cần thay hoặc sắp lại những tham chiếu trong các vị trí hiện có.

Chẳng hạn, sắp xếp làm thứ tự thay đổi nhưng không tạo thêm vị trí. `List.replaceAll` dùng kết quả của một hàm để thay từng phần tử, cũng không cần tăng kích thước. `ListIterator.set` thay phần tử vừa được bộ duyệt trả về.

Ngược lại, thêm một phần tử mới, xóa một phần tử đang có hoặc xóa toàn bộ một List không rỗng đều đòi thay số vị trí. List từ Arrays.asList không hỗ trợ những yêu cầu này.

Lưu thành `FixedSizeOperationsDemo.java`:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;

public class FixedSizeOperationsDemo {
    public static void main(String[] args) {
        List<String> values = Arrays.asList("C", "A", "B");
        ListIterator<String> cursor = values.listIterator();
        cursor.next();
        cursor.set("D");
        System.out.println("afterIteratorSet=" + values);

        values.sort(Comparator.naturalOrder());
        System.out.println("afterSort=" + values);
        values.replaceAll(value -> value.toLowerCase(Locale.ROOT));
        System.out.println("afterReplaceAll=" + values);

        try {
            values.add("E");
        } catch (UnsupportedOperationException e) {
            System.out.println("add=UnsupportedOperationException");
        }
        try {
            values.remove(0);
        } catch (UnsupportedOperationException e) {
            System.out.println("remove=UnsupportedOperationException");
        }
        try {
            values.clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("clear=UnsupportedOperationException");
        }
        System.out.println("afterAttempts=" + values);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 FixedSizeOperationsDemo.java
java FixedSizeOperationsDemo
```

Stdout:

```text
afterIteratorSet=[D, A, B]
afterSort=[A, B, D]
afterReplaceAll=[a, b, d]
add=UnsupportedOperationException
remove=UnsupportedOperationException
clear=UnsupportedOperationException
afterAttempts=[a, b, d]
```

Bộ duyệt lấy phần tử đầu rồi thay C thành D. Sau đó List được sắp xếp thành A, B, D và chuyển các chuỗi sang chữ thường. Những thao tác này thành công vì chúng chỉ thay nội dung các vị trí đã tồn tại.

Ba ca tiếp theo chủ động yêu cầu đổi kích thước nên đều bị từ chối. Sau các lần thử, nội dung vẫn là a, b, d. Phần bắt ngoại lệ giúp chương trình quan sát nhiều ca, không phải là một chiến lược để API thật đoán quyền sửa bằng cách thử ngẫu nhiên.

Đừng kết luận rằng mọi phương thức có chữ remove luôn cho cùng một kết quả bất kể đối số. Một lời gọi không tìm thấy mục tiêu có thể không cần thay kích thước. Muốn kiểm tra khả năng xóa, chọn một mục thực sự đang tồn tại như chương trình đã làm.

Cũng đừng xem khả năng sắp xếp hoặc thay phần tử là quyền bảo vệ độc lập với nguồn: nếu List đang dựa trên mảng của một thành phần khác, các phép biến đổi ấy có thể sửa chính dữ liệu của thành phần đó.

## 5. Varargs quyết định mảng nào đang làm nền cho List

Chữ ký `asList(T... array)` dùng tham số số lượng biến đổi. Khi truyền vài đối số rời như hai String, Java chuẩn bị một mảng tham số chứa các String đó. View vẫn có kích thước cố định dù người gọi không tự khai báo một biến mảng.

Khi truyền một `String[]` cho lời gọi có T là String, chính mảng String ấy là mảng tham số phù hợp; List có từng String làm phần tử. Nếu ghi rõ T là `String[]`, thì một phần tử lại là cả mảng String, còn mảng varargs ở tầng ngoài cao hơn.

Mảng nguyên thủy tạo thêm một điểm cần phân biệt: `int[]` là một đối tượng mảng nhưng không là `Integer[]`. Java không tự đóng gói cả mảng int thành mảng Integer để tạo List chứa từng số.

Lưu thành `AsListArrayShapesDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class AsListArrayShapesDemo {
    public static void main(String[] args) {
        List<String> fromArguments = Arrays.asList("left", "right");
        System.out.println("fromArguments=" + fromArguments);

        String[] words = {"sun", "moon"};
        List<String> wordView = Arrays.asList(words);
        List<String[]> oneArray = Arrays.<String[]>asList(words);
        System.out.println("wordCount=" + wordView.size());
        System.out.println("arrayCount=" + oneArray.size());
        System.out.println("sameArray=" + (oneArray.get(0) == words));

        int[] raw = {10, 20};
        List<int[]> primitiveView = Arrays.asList(raw);
        System.out.println("primitiveListSize=" + primitiveView.size());
        System.out.println("samePrimitiveArray=" + (primitiveView.get(0) == raw));
        raw[0] = 99;
        System.out.println("primitiveElement="
                + Arrays.toString(primitiveView.get(0)));

        Integer[] boxed = {10, 20};
        List<Integer> boxedView = Arrays.asList(boxed);
        System.out.println("boxedListSize=" + boxedView.size());
        System.out.println("boxedView=" + boxedView);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AsListArrayShapesDemo.java
java AsListArrayShapesDemo
```

Stdout:

```text
fromArguments=[left, right]
wordCount=2
arrayCount=1
sameArray=true
primitiveListSize=1
samePrimitiveArray=true
primitiveElement=[99, 20]
boxedListSize=2
boxedView=[10, 20]
```

Kết quả cần được đọc theo kiểu của **một phần tử List**:

| Biến | Kiểu phần tử | Số phần tử trong ví dụ |
| --- | --- | --- |
| `fromArguments` | String | Hai |
| `wordView` | String | Hai |
| `oneArray` | `String[]` | Một |
| `primitiveView` | `int[]` | Một |
| `boxedView` | Integer | Hai |

Lời gọi `Arrays.<String[]>asList(words)` chủ động giữ words như một phần tử mảng. Dòng `sameArray=true` xác nhận không có bản sao sâu của words được tạo ra.

Đối với raw, List có một phần tử là chính `int[]`, nên `primitiveListSize` bằng một, không bằng hai. Việc sửa raw ở vị trí đầu được nhìn thấy khi đọc mảng lấy từ phần tử List. Mảng Integer ở cuối lại phù hợp với một dãy phần tử Integer, nên List có hai vị trí riêng.

Nếu yêu cầu là `List<Integer>` từ một `int[]`, cần một bước lấy từng giá trị và đóng gói phù hợp. Đừng dùng phép ép kiểu để giả định `int[]` đã là `Integer[]`, và đừng dự đoán size chỉ bằng số dấu ngoặc nhọn trong dữ liệu nguồn.

Khi List chứa mảng, dùng `Arrays.toString` trên mảng phần tử để quan sát các giá trị bên trong. Chuỗi in mặc định của đối tượng mảng không giúp chứng minh rằng các số đã được chuyển thành các phần tử Integer riêng.

## 6. Tạo bản sao khi cần tách phần chứa khỏi mảng

Có ba yêu cầu thường gặp khi bắt đầu từ một view Arrays.asList:

1. Cần List riêng có thể thêm/xóa.
2. Cần ảnh chụp chỉ đọc, không đi theo các lần thay ô mảng về sau.
3. Chỉ cần chặn sửa qua một đường List nhưng vẫn muốn nhìn dữ liệu đang theo nguồn.

Những yêu cầu này khác nhau. Constructor `new ArrayList<>(view)` tạo phần chứa riêng và cho phép đổi kích thước. `List.copyOf(view)` chốt dữ liệu thành List không cho sửa phần chứa, với điều kiện không có null. `Collections.unmodifiableList(view)` chỉ chặn sửa qua lớp bọc; view bên dưới vẫn liên hệ với mảng.

Lưu thành `AsListCopyChoicesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class AsListCopyChoicesDemo {
    public static void main(String[] args) {
        String[] source = {"one", "two"};
        List<String> view = Arrays.asList(source);
        List<String> editableCopy = new ArrayList<>(view);
        List<String> snapshot = List.copyOf(view);
        List<String> readOnlyView = Collections.unmodifiableList(view);

        view.set(0, "changed");
        editableCopy.add("three");
        System.out.println("view=" + view);
        System.out.println("editableCopy=" + editableCopy);
        System.out.println("snapshot=" + snapshot);
        System.out.println("readOnlyView=" + readOnlyView);
        System.out.println("source=" + Arrays.toString(source));

        StringBuilder[] builders = {new StringBuilder("draft")};
        List<StringBuilder> shallowCopy =
                new ArrayList<>(Arrays.asList(builders));
        builders[0].append("-edit");
        System.out.println("sharedElement=" + shallowCopy.get(0));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AsListCopyChoicesDemo.java
java AsListCopyChoicesDemo
```

Stdout:

```text
view=[changed, two]
editableCopy=[one, two, three]
snapshot=[one, two]
readOnlyView=[changed, two]
source=[changed, two]
sharedElement=draft-edit
```

Các kết quả được tạo trước khi view đổi phần tử đầu. Sau khi đổi:

- View và source cùng có changed ở vị trí đầu.
- EditableCopy vẫn giữ one, two, rồi cho phép bổ sung three vào bản riêng.
- Snapshot vẫn giữ one, two.
- ReadOnlyView hiện changed, two vì lớp bọc đọc xuyên view đang dùng chung mảng.

Khả năng sửa qua một đường truy cập và việc dữ liệu có theo nguồn là hai chiều cần xét độc lập. Không thể dùng một thao tác add bị chặn để chứng minh rằng nguồn không còn thay đổi được nội dung mà người nhận nhìn thấy.

Đối tượng StringBuilder ở cuối chương trình minh họa một giới hạn khác. ArrayList mới tách các vị trí chứa tham chiếu khỏi mảng ban đầu, nhưng vẫn giữ cùng StringBuilder. Nội dung draft-edit được quan sát ở bản sao vì đối tượng phần tử vẫn dùng chung.

Do đó, “bản sao riêng” trong ngữ cảnh này trước hết là bản sao của phần chứa. Nếu cần độc lập cả trạng thái phần tử, hãy chọn phần tử bất biến hoặc một cách chuyển đổi/sao chép phần tử phù hợp với mô hình dữ liệu.

Một cách tạo List vẫn cố định kích thước nhưng tách các ô khỏi mảng nguồn là tạo một mảng sao chép trước rồi lấy view trên mảng mới. Cách đó vẫn không tự sao chép sâu đối tượng phần tử. Không cần đổi mọi yêu cầu thành ArrayList nếu chính yêu cầu là có một dãy ô cố định riêng.

Đối chiếu khả năng thêm/xóa của [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) và hợp đồng ảnh chụp của [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) khi lựa chọn kết quả cần dùng.

## 7. Null và kiểu mảng thực tế vẫn là ràng buộc

Arrays.asList nhận được phần tử null trong mảng tham chiếu. Điều đó khác với việc chính mảng truyền vào là null. Cần ghi rõ tầng dữ liệu đang nói đến.

Ngoài ra, mảng Java giữ kiểu thành phần thực tế ở thời điểm chạy. Một biến `Number[]` có thể đang tham chiếu một đối tượng `Integer[]`. Giao diện List được suy ra từ kiểu biến mảng không làm mảng nền mất kiểm tra kiểu khi ghi phần tử.

Lưu thành `AsListTypeConstraintsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class AsListTypeConstraintsDemo {
    public static void main(String[] args) {
        List<String> nullable = Arrays.asList("A", null);
        nullable.set(0, null);
        System.out.println("nullable=" + nullable);
        System.out.println("oneNullSize="
                + Arrays.asList((String) null).size());
        try {
            Arrays.asList((String[]) null);
        } catch (NullPointerException e) {
            System.out.println("nullArray=NullPointerException");
        }

        Integer[] storage = {1, 2};
        Number[] wider = storage;
        List<Number> numberView = Arrays.asList(wider);
        numberView.set(0, 3);
        System.out.println("afterInteger=" + Arrays.toString(storage));
        try {
            numberView.set(1, 2.5);
        } catch (ArrayStoreException e) {
            System.out.println("doubleStore=ArrayStoreException");
        }
        System.out.println("afterRejectedStore=" + Arrays.toString(storage));

        List<Number> independent = new ArrayList<>(numberView);
        independent.set(1, 2.5);
        System.out.println("independent=" + independent);
        System.out.println("storage=" + Arrays.toString(storage));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AsListTypeConstraintsDemo.java
java AsListTypeConstraintsDemo
```

Stdout:

```text
nullable=[null, null]
oneNullSize=1
nullArray=NullPointerException
afterInteger=[3, 2]
doubleStore=ArrayStoreException
afterRejectedStore=[3, 2]
independent=[3, 2.5]
storage=[3, 2]
```

### 7.1. Phần tử null khác mảng null

List nullable có hai vị trí. Vị trí thứ hai đã null, vị trí thứ nhất được set thành null nên kết quả là hai phần tử null. `Arrays.asList((String) null)` tạo một List có một phần tử null.

Trong khi đó, `Arrays.asList((String[]) null)` truyền chính mảng null và gây lỗi. Không dùng null trần rồi mặc định Java sẽ hiểu là “một phần tử null”; viết rõ kiểu khi cần phân biệt ý định.

### 7.2. Kiểu khai báo rộng không đổi kiểu của mảng đã tạo

Storage là một `Integer[]`. Biến wider có kiểu `Number[]` nhưng vẫn giữ cùng đối tượng đó. Đây là một khả năng của hệ thống kiểu mảng, không phải phép chuyển `List<Integer>` thành `List<Number>`.

NumberView được tạo qua biến wider và có kiểu `List<Number>`. Khi thay bằng số 3, giá trị Integer phù hợp với mảng nền nên thành công. Khi thay bằng 2.5, giá trị Double phù hợp với kiểu Number ở lúc biên dịch nhưng không thể được lưu trong `Integer[]` thực tế; phép ghi bị chặn bằng ArrayStoreException.

`ArrayList<Number>` độc lập ở cuối có phần chứa riêng, nên có thể giữ Double và không sửa storage. Chương trình không dùng kiểu thô hay ép kiểu List để tạo khác biệt này.

Điểm cần nhớ là: List từ Arrays.asList vẫn chịu những ràng buộc lưu trữ của mảng nền. Nếu cần một phần chứa Number riêng có khả năng nhận các kiểu con Number khác, hãy tạo phần chứa phù hợp thay vì nghĩ việc khai báo biến rộng đã biến đổi mảng.

Quy tắc kiểm tra khi ghi mảng tham chiếu được giải thích trong [JLS 17, Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5).

## 8. Chọn Arrays.asList khi nào?

Arrays.asList hữu ích khi đang có một mảng và muốn làm việc bằng giao diện List mà vẫn chấp nhận dùng chung các vị trí lưu phần tử. Ví dụ, một đoạn xử lý cần đọc theo List hoặc thay các phần tử trong một dãy có độ dài cố định.

Cần xác định trước ba yêu cầu:

1. Có cần thêm/xóa vị trí không?
2. Có muốn sửa qua List ảnh hưởng đến mảng không?
3. Có cần bảo vệ cả trạng thái của đối tượng phần tử không?

| Yêu cầu | Lựa chọn phù hợp về phần chứa | Điểm cần xét thêm |
| --- | --- | --- |
| List dùng chung mảng, không cần đổi số vị trí | `Arrays.asList(array)` | Phép set có thể sửa mảng |
| List riêng có thể thêm/xóa | `new ArrayList<>(Arrays.asList(array))` | Phần tử có thể vẫn dùng chung |
| List chỉ đọc đã chốt từ view | `List.copyOf(Arrays.asList(array))` | Không nhận phần tử null; không sao chép sâu |
| Chặn sửa qua List nhưng vẫn theo dữ liệu mảng | Lớp bọc chỉ đọc trên view | Nguồn mảng còn có thể đổi dữ liệu quan sát được |
| Dãy ô cố định riêng | Sao chép mảng rồi tạo view trên mảng mới | Phần tử đối tượng vẫn cần chính sách riêng |

Nếu phương thức nhận một List rồi định gọi add hoặc remove, việc truyền trực tiếp Arrays.asList có thể không đáp ứng yêu cầu. Không suy từ kiểu khai báo List rằng mọi thao tác tùy chọn đều được hỗ trợ. Hợp đồng phương thức nhận cần nêu rõ quyền sửa mong đợi.

Nếu phương thức định sắp xếp hoặc thay phần tử, view có thể đáp ứng về khả năng thao tác nhưng sẽ tác động lên mảng của bên gọi. Trường hợp chỉ muốn tính ra một kết quả đã biến đổi mà giữ nguồn cũ, nên chuẩn bị phần chứa riêng.

Nếu API trả Arrays.asList của một mảng nội bộ, người nhận có đường set vào mảng ấy. Bản thân từ “kích thước cố định” không đủ để gọi đầu ra là chỉ đọc. Ngược lại, bọc chỉ đọc cũng không hứa dữ liệu cố định nếu chủ sở hữu tiếp tục sửa mảng.

Không cần tạo bản sao trong mọi trường hợp. Chia sẻ dữ liệu có thể chính là mục tiêu của một view. Điều cần làm là công bố đúng quan hệ với nguồn và không hứa mức độc lập mà cách triển khai chưa cung cấp.

Các chương trình trong bài chạy một luồng để quan sát rõ quan hệ dữ liệu. Việc mảng và view dùng chung phần tử không tự tạo một cơ chế phối hợp truy cập khi nhiều luồng cùng đọc/ghi.

## 9. Chẩn đoán lỗi theo đúng tầng dữ liệu

| Tình huống | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Add hoặc xóa phần tử đang có bị chặn | List cố định số vị trí | Tạo phần chứa có thể thay kích thước nếu cần |
| Set qua List làm mảng nguồn đổi | Đúng hợp đồng dùng chung mảng | Dùng bản sao nếu không muốn sửa nguồn |
| Gán biến mảng sang mảng mới nhưng List cũ không đổi nền | Biến đã đổi tham chiếu, view vẫn giữ mảng cũ | Tạo view mới từ mảng mới nếu đó là mục tiêu |
| `int[]` cho List có một phần tử | Một phần tử có kiểu `int[]` | Chuyển từng số nếu cần `List<Integer>` |
| Gọi với null gây lỗi thay vì có một phần tử null | Null đang được hiểu là mảng tham số | Ghi kiểu rõ để diễn đạt đúng tầng |
| Set Double qua `List<Number>` gây ArrayStoreException | Mảng nền thực tế có kiểu hẹp hơn | Chọn phần chứa độc lập đáp ứng kiểu Number |
| Đã tạo ArrayList mới nhưng đối tượng phần tử vẫn đổi | Sao chép phần chứa còn chia sẻ phần tử | Dùng phần tử bất biến hoặc sao chép/chuyển đổi phù hợp |
| Ép kết quả sang java.util.ArrayList bị lỗi | Kiểu triển khai không được hợp đồng đó hứa | Làm việc qua List hoặc tạo ArrayList thật |

Khi quan sát một lỗi, nên in hoặc kiểm tra cả mảng lẫn List trước–sau thao tác. Để phân biệt view và bản sao, thay một ô mảng sau khi tạo kết quả rồi đọc kết quả. Để phân biệt sao chép nông và độc lập trạng thái, cần kiểm tra việc sửa chính đối tượng phần tử.

Không dựa duy nhất vào tên lớp thấy trong công cụ gỡ lỗi hoặc một phép so sánh định danh. Một List khác đối tượng vẫn có thể là view của cùng mảng. Một ArrayList mới có phần chứa riêng vẫn có thể giữ các đối tượng phần tử dùng chung.

Với thao tác cần thay đổi kích thước, kiểm tra một ca có thay đổi thực sự. Một lời gọi xóa giá trị không tồn tại hoặc xử lý dữ liệu rỗng không phải phép chứng minh chung rằng List cho phép xóa phần tử.

## 10. Thực hành dự đoán và kiểm chứng

### Bài 1: Theo dõi hai đường sửa

Tạo mảng `[north, south]` và một List view. Thay vị trí 0 bằng east qua List, rồi thay vị trí 1 bằng west qua mảng.

Tiêu chí đạt: cả hai cách đọc cùng hiện east, west; kích thước List vẫn bằng hai. Giải thích bằng quan hệ với các ô mảng, không bằng một bước sao chép dữ liệu giữa hai đối tượng.

### Bài 2: Biến tham chiếu và đối tượng mảng

Sau khi tạo view trên mảng hai phần tử, gán biến mảng sang một mảng mới có ba phần tử.

Dự đoán size của view cũ và kiểm chứng. View cũ vẫn có hai vị trí vì nó tiếp tục liên hệ với mảng ban đầu. Muốn nhìn mảng mới qua List, phải tạo kết quả từ mảng mới.

### Bài 3: Chọn quyền sửa đúng

Một phương thức cần thêm một mục vào List nhận được. Người gọi đang có `String[]` và dùng Arrays.asList.

Hãy chọn cách chuẩn bị đầu vào để phương thức thêm được mà không thay số vị trí của mảng gốc. Một ArrayList riêng từ view đáp ứng quyền thêm; cần giải thích rằng đây là bản riêng của phần chứa.

### Bài 4: Từng số hay một mảng số?

Có `int[]` gồm ba số. Hãy dự đoán kiểu phần tử và size khi gọi Arrays.asList trên mảng đó. So sánh với một `Integer[]` cũng gồm ba số.

Tiêu chí đạt: `int[]` tạo một phần tử mảng trong List của lời gọi tương ứng; `Integer[]` tạo các vị trí Integer riêng. Không dùng một phép ép kiểu để coi hai loại mảng là như nhau.

### Bài 5: Chỉ đọc có theo nguồn không?

Từ cùng một view, tạo một lớp bọc chỉ đọc và một List.copyOf với dữ liệu không null. Thay một ô mảng sau khi tạo cả hai.

Dự đoán kết quả: lớp bọc vẫn nhìn thấy giá trị mới qua view; ảnh chụp giữ giá trị đã lấy lúc tạo. Giải thích rằng cả hai đều chặn sửa qua List nhưng quan hệ với nguồn khác nhau.

### Bài 6: Phần tử có trạng thái riêng

Mảng chứa một StringBuilder. Tạo một ArrayList mới từ Arrays.asList của mảng, rồi sửa StringBuilder bằng append.

Tiêu chí đạt: nhận ra phần chứa mới không tự nhân bản builder. Đề xuất chuyển thành String hoặc một kiểu giá trị phù hợp nếu đầu ra cần giữ nội dung văn bản ổn định.

### Bài 7: Kiểu mảng ở thời điểm chạy

Một `Integer[]` được giữ qua biến `Number[]` rồi dùng để tạo `List<Number>`. Thử thay một vị trí bằng Integer và một vị trí bằng Double.

Tiêu chí đạt: phân biệt kiểm tra kiểu ở lời gọi Java với kiểm tra kiểu thành phần mảng khi lưu. So sánh với một `ArrayList<Number>` độc lập để giải thích nguyên nhân của ArrayStoreException.

## 11. Các câu hỏi tự kiểm tra

1. **Arrays.asList có tạo một ArrayList có thể tăng kích thước không?** Không. Nó trả List kích thước cố định dùng chung mảng tham số.
2. **Kích thước cố định có cấm set không?** Không. Vị trí hiện có vẫn thay phần tử được nếu chỉ số và kiểu lưu trữ hợp lệ.
3. **Sửa mảng sau khi tạo view có được thấy ở List không?** Có, khi sửa các ô của chính mảng nền đó.
4. **Gán lại biến mảng có làm view chuyển nguồn không?** Không. View liên hệ với đối tượng mảng cũ, không theo dõi biến.
5. **`int[]` có tự thành `List<Integer>` không?** Không. Cần đọc kiểu varargs và thực hiện bước chuyển từng giá trị nếu đó là yêu cầu.
6. **Mảng null và mảng có phần tử null có giống nhau không?** Không. Một bên thiếu đối tượng mảng hợp lệ, bên kia là dữ liệu phần tử trong mảng.
7. **Tạo ArrayList từ view bảo vệ đến đâu?** Tách phần chứa để có thể thêm/xóa riêng; đối tượng phần tử có thể vẫn được chia sẻ.
8. **List.copyOf và lớp bọc chỉ đọc trên view khác nhau ở đâu?** Một bên chốt dữ liệu phần chứa, một bên tiếp tục đọc qua view đang theo nguồn.
9. **Vì sao `List<Number>` vẫn có thể không lưu được Double trong ví dụ?** Vì mảng nền thực tế là `Integer[]` và vẫn kiểm tra kiểu thành phần khi ghi.
10. **Một lựa chọn API tốt cần xác định gì?** Quyền thay phần tử, quyền thay kích thước, quan hệ với mảng nguồn và mức độc lập của trạng thái phần tử.

