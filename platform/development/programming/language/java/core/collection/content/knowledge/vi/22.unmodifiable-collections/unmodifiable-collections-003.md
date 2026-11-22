# Vì sao unmodifiable view vẫn thấy thay đổi từ nguồn

## 1. Một lối đọc bị chặn ghi, không phải dữ liệu được đóng băng

Giả sử một lớp giữ danh sách người đang tham gia phòng học. Lớp đó muốn cho nơi khác xem danh sách, nhưng mọi thao tác tham gia/rời phòng phải đi qua các phương thức nghiệp vụ của nó.

Collections.unmodifiableList(source) đáp ứng nhu cầu này: nơi nhận không được sửa danh sách qua kết quả trả về, trong khi chủ sở hữu source vẫn tiếp tục thêm hoặc xóa người. Khi đọc lại view sau các cập nhật tuần tự hợp lệ ở nguồn, nơi nhận thấy trạng thái mới.

Hai điều đó không mâu thuẫn. **unmodifiable mô tả thao tác không được phép qua một giao diện; view mô tả dữ liệu được đọc từ nguồn nào.**

Hãy phân biệt ba yêu cầu:

| Yêu cầu | Câu hỏi tương ứng |
|---|---|
| Chặn ghi qua một tham chiếu | Nơi giữ tham chiếu này có gọi add, remove, set, put… được không? |
| Tách khỏi thay đổi cấu trúc ở nguồn | Nguồn thêm/xóa/thay vị trí thì dữ liệu trả về có đổi theo không? |
| Giữ nguyên trạng thái của mọi phần tử | Nếu đối tượng bên trong thay thuộc tính, nơi đọc có thấy không? |

Một unmodifiable view chỉ trực tiếp giải quyết yêu cầu đầu tiên. Hai yêu cầu còn lại phụ thuộc có sao chép dữ liệu hay không và các đối tượng bên trong có thay đổi được hay không.

Bài này dùng các lớp bọc Collections.unmodifiableList, unmodifiableSet và unmodifiableMap làm mô hình chính. Các ví dụ đầy đủ chạy trên Java 17 trở lên. Mọi cập nhật ở ví dụ được thực hiện tuần tự trong một luồng; phần làm việc giữa nhiều luồng được phân tích riêng.

## 2. Cơ chế: lớp bọc đọc qua collection được bọc

### 2.1. Quan hệ với nguồn vẫn còn

Một view không cần quản lý một bộ phần tử độc lập. Nó giữ quan hệ với cấu trúc được bọc và chuyển các thao tác đọc thích hợp tới cấu trúc đó.

Về mặt ý tưởng, khi gọi view.size(), câu trả lời đến từ kích thước hiện tại của nguồn. Khi gọi view.get(i), giá trị đến từ phần tử hiện tại ở vị trí i của nguồn. Các thao tác sửa qua view bị chặn.

Đây là mô tả cơ chế, không phải mã nguồn triển khai phải giống hệt như vậy ở mọi JDK. Điều cần dựa vào là hợp đồng API: các truy vấn trên unmodifiableList và unmodifiableMap đọc xuyên qua cấu trúc được cung cấp. [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) và [unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)) nêu trực tiếp hành vi này.

Vì nguồn còn tồn tại và còn được sửa qua tham chiếu khác, lần đọc view sau đó thấy nguồn đã đổi. Không có tác vụ đồng bộ nội dung, gửi sự kiện hay sao chép lại âm thầm để đạt kết quả ấy; lớp bọc vốn đang đọc cùng dữ liệu.

### 2.2. Có hai đường truy cập với quyền khác nhau

Có thể hình dung:

- Chủ sở hữu giữ source, được sửa theo API của source.
- Nơi nhận giữ view, được đọc nhưng các thao tác cập nhật qua view bị từ chối.
- Cả hai đường truy cập cuối cùng vẫn liên quan đến cùng một cấu trúc dữ liệu.

Bọc source không biến bản thân source thành một collection không sửa được. Nó cũng không thu hồi các tham chiếu mutable đã được trao ra trước đó.

Nếu một đoạn code khác đã có source hoặc một view có thể ghi của source, đoạn code đó vẫn có thể thay đổi dữ liệu. Khi đánh giá quyền sở hữu, phải theo các tham chiếu thực tế, không chỉ nhìn tên biến readOnly.

### 2.3. Không phải mọi lớp bọc đều cần là đối tượng mới

Không dùng view != source làm định nghĩa của unmodifiable view. Một số lời gọi có thể tái sử dụng đối tượng đã đáp ứng hợp đồng. Chi tiết số lượng lớp bọc hoặc tên lớp nội bộ không quyết định việc có liên kết với nguồn.

Thử nghiệm đúng là quan sát quyền sửa và kết quả đọc sau khi nguồn thay đổi. So sánh tham chiếu, xem tên lớp runtime hay ép kiểu tới một lớp nội bộ không thay thế hợp đồng API.

Tài liệu [Collection — View Collections và Unmodifiable Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) là điểm tham chiếu để phân biệt nơi chứa dữ liệu với lớp cung cấp góc nhìn.

## 3. Chương trình với List: nguồn đổi, view đổi; bản sao giữ cấu trúc cũ

Chương trình tạo ba kết quả từ cùng một nguồn:

- view bọc trực tiếp source.
- copiedThenWrapped bọc một ArrayList đã sao chép.
- copiedByFactory được tạo bằng List.copyOf(source).

Nguồn chứa String bất biến để phần đầu chỉ tập trung vào thay đổi ở cấu trúc list.

Tệp **LiveListViewDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class LiveListViewDemo {
    private static void expectUOE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> copiedThenWrapped =
                Collections.unmodifiableList(new ArrayList<>(source));
        List<String> copiedByFactory = List.copyOf(source);

        source.set(0, "A2");
        source.add("C");
        System.out.println("view=" + view);
        System.out.println("copiedThenWrapped=" + copiedThenWrapped);
        System.out.println("copiedByFactory=" + copiedByFactory);
        expectUOE("viewAdd", () -> view.add("D"));
        expectUOE("viewSet", () -> view.set(0, "X"));
        Iterator<String> iterator = view.iterator();
        iterator.next();
        expectUOE("iteratorRemove", iterator::remove);

        List<String> current = source;
        List<String> fromCurrent = Collections.unmodifiableList(current);
        current = new ArrayList<>(List.of("X"));
        current.add("Y");
        System.out.println("reboundVariable=" + current);
        System.out.println("oldObjectView=" + fromCurrent);

        source.remove("B");
        System.out.println("afterSourceRemove=" + view);
        source.clear();
        System.out.println("afterSourceClear=" + view);
        source.add("NEW");
        System.out.println("afterSourceRefill=" + view);

        String[] array = {"red", "blue"};
        List<String> arrayView =
                Collections.unmodifiableList(Arrays.asList(array));
        array[0] = "green";
        System.out.println("arrayBacked=" + arrayView);

        CopyOnWriteArrayList<String> concurrentSource =
                new CopyOnWriteArrayList<>(List.of("old"));
        List<String> concurrentView =
                Collections.unmodifiableList(concurrentSource);
        Iterator<String> oldIterator = concurrentView.iterator();
        concurrentSource.add("new");
        List<String> oldIteration = new ArrayList<>();
        oldIterator.forEachRemaining(oldIteration::add);
        System.out.println("currentView=" + concurrentView);
        System.out.println("oldIterator=" + oldIteration);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LiveListViewDemo.java
java LiveListViewDemo
```

Stdout chính xác:

```text
view=[A2, B, C]
copiedThenWrapped=[A, B]
copiedByFactory=[A, B]
viewAdd=UnsupportedOperationException
viewSet=UnsupportedOperationException
iteratorRemove=UnsupportedOperationException
reboundVariable=[X, Y]
oldObjectView=[A2, B, C]
afterSourceRemove=[A2, C]
afterSourceClear=[]
afterSourceRefill=[NEW]
arrayBacked=[green, blue]
currentView=[old, new]
oldIterator=[old]
```

### 3.1. set cũng là thay đổi mà view đọc được

source.set(0,"A2") thay phần tử ở một vị trí nhưng không tăng kích thước. source.add("C") thêm một vị trí mới. view thấy cả hai kết quả và hiện [A2,B,C].

Vì vậy không giới hạn ý nghĩa “thay đổi từ nguồn” vào riêng thao tác thêm/xóa. Thay phần tử, đổi thứ tự hợp lệ hoặc thay giá trị ánh xạ cũng có thể làm kết quả đọc của view khác đi.

copiedThenWrapped vẫn là [A,B] vì nó đang bọc ArrayList khác, được tạo trước khi source đổi. copiedByFactory cũng giữ các phần tử của lần sao chép. Điểm tách liên kết là bước **sao chép cấu trúc**, không phải tên unmodifiable.

### 3.2. Các đường sửa của chính view bị chặn

view.add("D"), view.set(0,"X") và iterator.remove() đều gây UnsupportedOperationException. Với List, việc không cho sửa bao gồm cả thay một phần tử; đây không chỉ là danh sách kích thước cố định.

Iterator được lấy qua unmodifiable view không cung cấp một lối vòng để xóa nguồn. Tương tự, ListIterator của lớp bọc không cho sửa bằng add/set/remove theo giao diện ấy.

Nhưng không vì các thao tác này thất bại mà suy ra source.add(...) cũng phải thất bại. Chính source là đường cập nhật mà chủ sở hữu còn giữ.

### 3.3. Gán biến khác không đổi đối tượng mà view đang bọc

current ban đầu trỏ source. fromCurrent được tạo từ đối tượng mà current đang trỏ tới ở thời điểm gọi unmodifiableList.

Sau đó current được gán sang ArrayList mới [X,Y]. Việc gán này chỉ đổi giá trị của biến current. Nó không điều khiển fromCurrent chuyển sang bọc đối tượng mới. fromCurrent vẫn đọc list cũ, nên hiện [A2,B,C].

Đây là một chi tiết hữu ích khi đọc code:

- Sửa đối tượng nguồn đã bọc → view đọc thấy thay đổi hợp lệ của đối tượng đó.
- Gán một biến sang đối tượng khác → view cũ không tự chuyển mục tiêu.

Nếu cần một API luôn lấy collection hiện tại từ một trường có thể thay thế, đó là một thiết kế truy vấn khác. Đừng kỳ vọng một lớp bọc đã trả về sẽ tự theo biến của ứng dụng.

### 3.4. clear không ngắt liên kết

Sau source.clear(), view trở thành rỗng. Sau source.add("NEW"), chính view đó lại hiện NEW. Nó chưa trở thành một collection rỗng độc lập và cũng chưa bị “đóng” sau lần clear.

Một view rỗng chỉ đang nhìn thấy nguồn rỗng tại thời điểm đọc. Tính rỗng không nói gì về việc nguồn còn có thể thay đổi về sau.

### 3.5. Nguồn có thể nằm sau một view khác

arrayView bọc Arrays.asList(array), mà list này dựa trên mảng array. Khi array[0] được thay thành green, lớp bọc ngoài đọc xuyên qua list trung gian và thấy green.

Chuỗi ở đây là: unmodifiable view → list dựa trên mảng → mảng. Thêm một lớp bọc không cắt liên kết ở các lớp bên trong.

[Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)) trả danh sách kích thước cố định dựa trên mảng. Nó cho phép thay phần tử qua set khi chưa bị lớp bọc chặn, khác với một list không sửa được.

Phần CopyOnWriteArrayList ở cuối chương trình sẽ được giải thích ở mục iterator: view hiện tại và một iterator đã tạo trước đó không bắt buộc thể hiện cùng phiên bản dữ liệu.

## 4. Quy tắc tương tự với Set và Map

### 4.1. UnmodifiableSet vẫn dựa trên set nguồn

Collections.unmodifiableSet(sourceSet) chặn các cập nhật qua set trả về. Nếu chủ sở hữu thêm/xóa phần tử qua sourceSet theo cách hợp lệ, kết quả đọc từ view phản ánh set nguồn hiện tại.

Lớp bọc không tự tạo thứ tự mới. Nếu nguồn có thứ tự duyệt được bảo đảm, view đọc theo hợp đồng đó; nếu nguồn không cam kết thứ tự, việc bọc không làm thứ tự trở nên ổn định.

Với SortedSet hoặc NavigableSet, chọn lớp bọc tương ứng nếu API cần giữ các khả năng đọc về thứ tự/điều hướng. Các view con được trả về vẫn phải giữ việc chặn ghi theo hợp đồng lớp bọc. Nhưng phần tử mutable của set vẫn là vấn đề riêng, nhất là khi thay thuộc tính ảnh hưởng equals/hashCode hoặc Comparator.

### 4.2. UnmodifiableMap chặn cả đường ghi qua các collection view

Map có nhiều đường thay đổi ánh xạ: put/remove trực tiếp, xóa qua keySet/values, hoặc cập nhật entry khi entry hỗ trợ setValue.

Collections.unmodifiableMap phải chặn các đường ghi từ chính kết quả được trả ra. Nó không thể chỉ chặn put rồi để keySet().remove(...) xóa nguồn như một lối vòng.

Trong khi đó, chủ sở hữu source map vẫn có thể cập nhật ánh xạ. Các tập khóa và collection giá trị lấy từ view cũng tiếp tục là góc nhìn vào dữ liệu đang được quản lý.

## 5. Chương trình Map: các view đọc theo nguồn và bảo vệ đường cập nhật

Ví dụ dùng LinkedHashMap để thứ tự in theo thứ tự chèn được xác định. Các khóa String và giá trị Integer đều bất biến, tránh trộn lẫn với việc sửa thuộc tính đối tượng bên trong.

Tệp **LiveMapViewDemo.java**:

```java
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class LiveMapViewDemo {
    private static void expectUOE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("A", 10);
        source.put("B", 20);
        Map<String, Integer> view = Collections.unmodifiableMap(source);
        Set<String> keys = view.keySet();
        Collection<Integer> values = view.values();

        System.out.println("initial=" + view);
        source.put("C", 30);
        source.put("A", 11);
        source.remove("B");
        System.out.println("updated=" + view);
        System.out.println("capturedKeys=" + keys);
        System.out.println("capturedValues=" + values);

        Map.Entry<String, Integer> writableEntry =
                source.entrySet().iterator().next();
        writableEntry.setValue(12);
        System.out.println("afterSourceEntryUpdate=" + view);

        Map.Entry<String, Integer> readOnlyEntry =
                view.entrySet().iterator().next();
        expectUOE("mapPut", () -> view.put("D", 40));
        expectUOE("keyRemove", () -> keys.remove("A"));
        expectUOE("valueRemove", () -> values.remove(12));
        expectUOE("entrySetValue", () -> readOnlyEntry.setValue(99));
        System.out.println("afterBlockedWrites=" + source);

        source.clear();
        System.out.println("emptyView=" + view);
        System.out.println("emptyKeys=" + keys);
        source.put("N", 7);
        System.out.println("refilledView=" + view);
        System.out.println("refilledValues=" + values);
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 LiveMapViewDemo.java
java LiveMapViewDemo
```

Stdout chính xác:

```text
initial={A=10, B=20}
updated={A=11, C=30}
capturedKeys=[A, C]
capturedValues=[11, 30]
afterSourceEntryUpdate={A=12, C=30}
mapPut=UnsupportedOperationException
keyRemove=UnsupportedOperationException
valueRemove=UnsupportedOperationException
entrySetValue=UnsupportedOperationException
afterBlockedWrites={A=12, C=30}
emptyView={}
emptyKeys=[]
refilledView={N=7}
refilledValues=[7]
```

### 5.1. Thêm, thay giá trị và xóa đều đi qua nguồn

Khi nguồn thêm C, đổi giá trị A và xóa B, view hiện {A=11,C=30}. keys và values đã lấy từ view trước đó cũng hiện các khóa/giá trị đang có, chứ không giữ ảnh chụp lúc chúng được lấy.

writableEntry lấy từ source.entrySet() trong ví dụ LinkedHashMap này có thể cập nhật A thành 12. Đó vẫn là một đường ghi hợp lệ của nguồn, nên view đọc thấy A=12.

Không tổng quát khả năng setValue của entry nguồn thành tính chất của mọi loại Map.Entry trong Java. Một số entry từ API khác là ảnh chụp không cho cập nhật; bài này chỉ dùng đường được map cụ thể hỗ trợ.

### 5.2. Entry được trả từ lớp bọc không mở lại quyền ghi

readOnlyEntry lấy qua view.entrySet() không cho setValue(99). keys.remove("A") và values.remove(12) cũng bị chặn, giống view.put("D",40).

Cần phân biệt hai thao tác:

- entry.setValue(newValue) là thay giá trị của ánh xạ; lớp bọc map chặn đường ghi này.
- entry.getValue().someMutator() là gọi một phương thức trên đối tượng giá trị; nếu giá trị mutable, lớp bọc map không tự biến đối tượng ấy thành bất biến.

Chương trình dùng Integer nên không có phương thức sửa giá trị bên trong. Với List hoặc một đối tượng nghiệp vụ làm giá trị, phải phân tích thêm tầng đối tượng đó.

### 5.3. Những view đã lấy vẫn theo dữ liệu mới

Sau source.clear(), cả view và keys rỗng. Sau source.put("N",7), view hiện N=7 và values hiện 7.

Không cần lấy lại view.values() mới để nhìn thấy ánh xạ mới qua collection values cũ. Tuy nhiên, một iterator đã đi dở trên collection đó có quy tắc riêng; không dùng ví dụ này để suy rằng mọi iterator cũ đều tự theo dữ liệu mới.

## 6. Phần tử có thể đổi ngay cả qua view chỉ đọc

Lớp bọc điều khiển thao tác của collection. Nó không chặn mọi phương thức của mọi đối tượng mà collection trả về.

Nếu view.get(0) trả một Reading có trường value thay đổi được, câu lệnh view.get(0).value = 15 không gọi list.set(). Nó sửa chính Reading. Vì vậy không có lý do để lớp bọc list ném UnsupportedOperationException cho thao tác đó.

Tương tự, một list ngoài không cho sửa có thể chứa các list trong vẫn sửa được. Không có cơ chế tự bọc đệ quy mọi lớp dữ liệu bên trong.

### 6.1. Chương trình phân biệt ba tầng

Chương trình dưới đây so sánh:

- view của danh sách nguồn.
- shallowSnapshot là bản sao các tham chiếu phần tử bằng List.copyOf.
- detachedValues là danh sách các giá trị mới, mỗi giá trị là record chỉ chứa int.

Nửa sau dùng danh sách lồng nhau chứa String để làm rõ việc chỉ sao chép lớp ngoài.

Tệp **ReadOnlyLayersDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ReadOnlyLayersDemo {
    static final class Reading {
        int value;

        Reading(int value) {
            this.value = value;
        }
    }

    record ReadingSnapshot(int value) {}

    private static List<Integer> values(List<Reading> readings) {
        return readings.stream().map(r -> r.value).toList();
    }

    public static void main(String[] args) {
        List<Reading> source = new ArrayList<>();
        source.add(new Reading(10));
        source.add(new Reading(20));
        List<Reading> view = Collections.unmodifiableList(source);
        List<Reading> shallowSnapshot = List.copyOf(source);

        view.get(0).value = 15;
        System.out.println("sourceAfterElementEdit=" + values(source));
        System.out.println("snapshotAfterElementEdit=" + values(shallowSnapshot));

        source.set(0, new Reading(99));
        System.out.println("viewAfterReplacement=" + values(view));
        System.out.println("snapshotAfterReplacement=" + values(shallowSnapshot));

        List<ReadingSnapshot> detachedValues = source.stream()
                .map(r -> new ReadingSnapshot(r.value))
                .toList();
        source.get(0).value = 100;
        System.out.println("viewAfterLaterEdit=" + values(view));
        System.out.println("detachedValues=" +
                detachedValues.stream().map(ReadingSnapshot::value).toList());

        List<String> inner = new ArrayList<>(List.of("x"));
        List<List<String>> nestedSource = new ArrayList<>();
        nestedSource.add(inner);
        List<List<String>> outerView =
                Collections.unmodifiableList(nestedSource);
        List<List<String>> outerSnapshot = List.copyOf(nestedSource);

        outerView.get(0).add("y");
        List<List<String>> copiedBothLevels = nestedSource.stream()
                .map(List::copyOf)
                .toList();
        inner.add("z");
        System.out.println("nestedView=" + outerView);
        System.out.println("outerSnapshot=" + outerSnapshot);
        System.out.println("copiedBothLevels=" + copiedBothLevels);

        source.clear();
        System.out.println("viewAfterClear=" + values(view));
        System.out.println("shallowSnapshotAfterClear=" + values(shallowSnapshot));
        System.out.println("detachedAfterClear=" +
                detachedValues.stream().map(ReadingSnapshot::value).toList());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ReadOnlyLayersDemo.java
java ReadOnlyLayersDemo
```

Stdout chính xác:

```text
sourceAfterElementEdit=[15, 20]
snapshotAfterElementEdit=[15, 20]
viewAfterReplacement=[99, 20]
snapshotAfterReplacement=[15, 20]
viewAfterLaterEdit=[100, 20]
detachedValues=[99, 20]
nestedView=[[x, y, z]]
outerSnapshot=[[x, y, z]]
copiedBothLevels=[[x, y]]
viewAfterClear=[]
shallowSnapshotAfterClear=[15, 20]
detachedAfterClear=[99, 20]
```

### 6.2. Một bản sao nông vẫn có thể hiện thay đổi thuộc tính

Lúc đầu, view, shallowSnapshot và source đều giữ cùng Reading đầu tiên. Sửa value của Reading ấy thành 15 làm cả nguồn và shallowSnapshot đọc ra 15.

Sau đó source.set(0,new Reading(99)) thay tham chiếu ở nguồn. view đi theo vị trí của nguồn nên thấy 99. shallowSnapshot vẫn giữ tham chiếu tới Reading trước đó, nên thấy 15.

Hai dòng kết quả này chỉ ra hai nguyên nhân khác nhau làm dữ liệu nhìn thấy thay đổi:

1. Cấu trúc nguồn thay đổi phần tử/ánh xạ → live view đọc thấy.
2. Đối tượng phần tử dùng chung bị sửa → mọi nơi còn giữ đối tượng ấy có thể thấy trạng thái mới, kể cả bản sao nông.

Không kết luận rằng List.copyOf “vẫn là view sống của source” chỉ vì một đối tượng mutable trong bản sao đổi trạng thái.

### 6.3. Chuyển sang giá trị bất biến khi cần ảnh chụp trạng thái

detachedValues tạo ReadingSnapshot mới từ giá trị int đang đọc. ReadingSnapshot chỉ chứa int, nên trạng thái cần lưu không còn liên kết mutable với Reading nguồn.

Nguồn đổi value từ 99 thành 100 rồi bị clear, detachedValues vẫn lưu [99,20]. Đây là kết quả của phép ánh xạ giá trị rõ ràng cộng với cấu trúc kết quả không cho sửa; không phải tác dụng riêng của lớp bọc unmodifiable.

Không phải mọi record đều bất biến sâu. Nếu một record chứa List mutable và lưu nguyên tham chiếu đó, trạng thái bên trong vẫn có thể đổi. Ví dụ này chọn thành phần int để tránh sự nhập nhằng ấy.

### 6.4. Danh sách lồng nhau cần xét từng tầng

outerView.get(0).add("y") thành công vì danh sách trong chưa bị bọc và vẫn mutable. outerSnapshot tạo bằng List.copyOf(nestedSource) cũng giữ chính inner đó.

copiedBothLevels sao chép từng list trong bằng List.copyOf rồi thu các kết quả vào list ngoài không cho sửa. Khi inner gốc nhận z, outerView và outerSnapshot đều hiện x,y,z, còn copiedBothLevels giữ x,y.

Vì các phần tử cuối cùng là String bất biến, hai tầng sao chép ở mô hình cụ thể này đủ tách trạng thái cần lưu. Không gọi cách viết ấy là một thuật toán sao chép sâu cho mọi đồ thị tùy ý.

Stream.toList() được dùng trong ví dụ để tạo list kết quả không cho sửa; nó là một phép thu kết quả, không phải unmodifiable view tự theo danh sách nguồn. Hợp đồng ở [Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()) cần được đọc riêng với Collections.unmodifiableList.

## 7. Muốn nguồn đổi mà kết quả không đổi thì phải cắt liên kết phù hợp

### 7.1. Sao chép cấu trúc trước khi bọc

Với list, biểu thức Collections.unmodifiableList(new ArrayList<>(source)) có hai bước khác nhau:

1. new ArrayList<>(source) tạo list chứa các tham chiếu phần tử lúc sao chép.
2. unmodifiableList(...) chặn thao tác ghi qua kết quả trả về.

Các thay đổi cấu trúc về sau của source không làm list riêng đó đổi. Tuy nhiên, nếu vẫn có ai giữ tham chiếu mutable tới list riêng, họ có thể sửa nó và lớp bọc sẽ đọc thấy. Chính sách “ảnh chụp không ai thay đổi cấu trúc được” cần cả việc không rò rỉ đường ghi vào bản sao.

Khi tạo list riêng ngay trong biểu thức rồi chỉ trả lớp bọc, ứng dụng có thể giữ riêng quyền sở hữu cấu trúc ấy. Còn các phần tử vẫn là vấn đề sao chép nông đã thấy ở ReadOnlyLayersDemo.

### 7.2. List.copyOf là lựa chọn rõ cho ảnh chụp phần tử không null

List.copyOf(source) trả list không cho sửa và các thay đổi sau đó của collection đầu vào không phản ánh vào kết quả về mặt thêm/xóa/thay tham chiếu phần tử. Nó vẫn không tự nhân bản các đối tượng phần tử.

Phương thức không nhận phần tử null. Vì vậy, thay Collections.unmodifiableList(source) bằng List.copyOf(source) có thể thay đổi cả:

- Quan hệ theo dõi nguồn.
- Thời điểm sao chép dữ liệu.
- Chính sách null.
- Chi phí tạo kết quả.

Không dùng thay thế ấy như một “tối ưu không đổi hành vi” nếu API trước đó có chủ đích trả view sống hoặc hỗ trợ null.

Nếu hợp đồng cần giữ null ở các phần tử, một cách sao chép cấu trúc có thể là hàm minh họa sau. Đây là một phương thức cần đặt trong một lớp Java có import Collection, List, ArrayList và Collections; nó không phải chương trình main độc lập:

```java
static <T> List<T> snapshotAllowingNull(Collection<? extends T> source) {
    return Collections.unmodifiableList(new ArrayList<>(source));
}
```

Hàm chỉ cho phép null ở phần tử theo khả năng của ArrayList; tham chiếu source bằng null vẫn không hợp lệ. Nó không sao chép sâu phần tử.

List.copyOf có thể tái sử dụng một list đầu vào đã phù hợp trong một số trường hợp. Đó không phải lý do để kiểm tra bằng == hoặc suy rằng nó được phép trả một view còn theo cấu trúc mutable ở ngoài. Dựa vào hợp đồng kết quả, không dựa vào số lần cấp phát.

Xem [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) để đối chiếu bảo đảm tách khỏi cập nhật collection đầu vào và điều kiện null.

### 7.3. Map và Set cũng cần chọn cách sao chép đúng yêu cầu

Map.copyOf(sourceMap) tạo kết quả không cho sửa và không theo các cập nhật ánh xạ sau đó của map đầu vào; khóa và giá trị vẫn có thể dùng chung đối tượng. Nó không chấp nhận khóa/giá trị null và không phải lựa chọn mặc định để giữ một thứ tự duyệt tùy chỉnh của nguồn.

Nếu cần thứ tự chèn cụ thể của một LinkedHashMap tại thời điểm sao chép, có thể sao chép sang LinkedHashMap riêng rồi bọc unmodifiableMap. Nếu cần thứ tự Comparator và khả năng điều hướng của cây, cần chọn cấu trúc sao chép và lớp bọc giữ các khả năng đó.

Với Set, tách phần tử của cấu trúc nguồn không làm phần tử mutable trở thành khóa an toàn hoặc bất biến. Thay thuộc tính ảnh hưởng equals/hashCode/Comparator khi phần tử đang nằm trong set vẫn là vấn đề của mô hình dữ liệu.

Phân biệt ba mức để chọn:

| Kết quả | Theo thay đổi cấu trúc của source? | Có thể cùng phần tử mutable? |
|---|---|---|
| Collections.unmodifiableList(source) | Có, theo hợp đồng nguồn/view | Có |
| Collections.unmodifiableList(new ArrayList<>(source)) | Không theo source ban đầu | Có |
| List.copyOf(source) | Không theo collection đầu vào về cấu trúc | Có |
| Danh sách các giá trị bất biến được dựng riêng | Không theo cấu trúc nguồn | Chỉ còn dùng chung những gì mô hình giá trị cho phép |

## 8. Thiết kế API: công khai view hay công khai ảnh chụp?

Nếu một đối tượng nghiệp vụ muốn sở hữu danh sách nhưng cho nơi khác theo dõi trạng thái mới, trả view sống có thể là hành vi đúng. Nếu nơi gọi cần một kết quả cố định cho báo cáo, kiểm tra hoặc một bước xử lý, trả snapshot thường phù hợp hơn.

Nên thể hiện khác biệt trong tên hoặc tài liệu phương thức. Chỉ ghi “trả danh sách chỉ đọc” chưa đủ nói rõ nguồn thay đổi thì kết quả sẽ thế nào.

Lớp minh họa sau không có main, có thể lưu trong **TagCatalog.java**. Các phần tử String bất biến giúp tập trung vào quyền sở hữu cấu trúc:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

final class TagCatalog {
    private final List<String> tags;
    private final List<String> readOnlyTags;

    TagCatalog(Collection<String> initialTags) {
        tags = new ArrayList<>(List.copyOf(initialTags));
        readOnlyTags = Collections.unmodifiableList(tags);
    }

    void addTag(String tag) {
        tags.add(Objects.requireNonNull(tag));
    }

    List<String> tagsView() {
        return readOnlyTags;
    }

    List<String> tagsSnapshot() {
        return List.copyOf(tags);
    }
}
```

Trong constructor, dữ liệu đầu vào được sao chép và kiểm tra không có null qua List.copyOf, rồi đặt vào ArrayList riêng để TagCatalog còn có thể thêm tag. Việc nơi gọi sửa collection initialTags sau đó không sửa trực tiếp cấu trúc nội bộ.

tagsView() luôn trả một view của danh sách nội bộ. Một view đã nhận trước đó sẽ thấy tag được thêm hợp lệ qua addTag(). tagsSnapshot() trả một list giữ các phần tử của thời điểm gọi; thêm tag về sau không cập nhật snapshot đó.

Ở đây final giữ tham chiếu tags và readOnlyTags ổn định sau constructor. Nó không khiến nội dung tags bất biến: addTag vẫn làm tags đổi. Chặn ghi ở bên nhận đến từ lớp bọc, còn quyền cập nhật của TagCatalog là chủ đích thiết kế.

Lớp minh họa chưa thiết kế chính sách cho nhiều luồng. Nếu cần dùng đồng thời, phải bổ sung một hợp đồng đồng bộ hoặc xuất bản snapshot phù hợp; không có bảo đảm ấy chỉ vì trường là private final hoặc kết quả là unmodifiable.

### 8.1. Bọc đầu vào trực tiếp vẫn để người gửi giữ đường ghi

Một lỗi thiết kế phổ biến là lưu Collections.unmodifiableList(input) vào trường, rồi cho rằng cấu trúc từ đây chỉ do lớp mình kiểm soát. Người gửi vẫn có input mutable và có thể sửa nó.

Nếu mục tiêu là ngăn người gửi thay đổi cấu trúc nội bộ qua dữ liệu đã truyền vào, cần sao chép phòng vệ khi nhận đầu vào. Nếu mục tiêu là cố ý theo dõi input đang thay đổi, bọc trực tiếp có thể đúng, nhưng phải ghi rõ và chấp nhận quan hệ đó.

Không có một lựa chọn duy nhất đúng cho mọi getter hoặc constructor. Lựa chọn phụ thuộc hợp đồng sở hữu dữ liệu.

### 8.2. Bọc nhiều lần không làm dữ liệu độc lập hơn

Nếu lớp bọc mới vẫn đọc qua lớp bọc cũ, rồi lớp bọc cũ đọc nguồn mutable, nguồn cuối cùng vẫn là nơi lưu dữ liệu.

Bởi vậy, unmodifiableList(unmodifiableList(source)) không có ý nghĩa “đóng băng hai lần”. Một JDK còn có thể tái sử dụng lớp bọc đã phù hợp. Muốn cắt liên kết cần bước sao chép thật sự, không phải thêm số lớp bọc.

### 8.3. Nếu nguồn đã không còn thay đổi thì view có thể trông cố định

Collections.unmodifiableList(List.of("a","b")) không có nguồn mutable bên dưới để người giữ list ấy thay đổi cấu trúc qua API thông thường. Trong trường hợp đó dữ liệu không biến động về cấu trúc.

Điều này không đổi định nghĩa chung của unmodifiable view. Nó chỉ có nghĩa nguồn của trường hợp cụ thể cũng không cho sửa. Nếu phần tử là đối tượng mutable, trạng thái phần tử vẫn cần xét riêng.

## 9. View sống không đồng nghĩa iterator luôn sống

### 9.1. View và iterator là hai đối tượng với hợp đồng khác nhau

Một collection view có thể đọc trạng thái nguồn hiện tại mỗi lần truy vấn. Iterator được tạo ra để duyệt có thể giữ vị trí, trạng thái kiểm tra sửa đổi hoặc một ảnh chụp riêng.

Vì thế không suy luận rằng iterator đã tạo từ view phải nhìn thấy mọi phần tử vừa thêm vào nguồn. Lớp bọc unmodifiable chặn các phép sửa qua iterator; nó không thay iterator nguồn thành một cơ chế duyệt phiên bản mới hoàn toàn.

### 9.2. Ví dụ CopyOnWriteArrayList trong chương trình đầu

concurrentView bọc CopyOnWriteArrayList ban đầu chứa old. oldIterator được tạo trước khi nguồn thêm new.

Sau khi thêm, đọc concurrentView hiện [old,new]. Nhưng duyệt oldIterator chỉ có old. Không có luồng thứ hai trong ví dụ này: khác biệt đến từ hợp đồng iterator giữ ảnh chụp của CopyOnWriteArrayList.

[CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html) quy định iterator theo trạng thái mảng tại lúc tạo. Do đó “view tiếp tục theo nguồn” và “iterator đã lấy giữ phiên bản cũ” có thể cùng đúng.

### 9.3. Với ArrayList, iterator đang duyệt có thể bị vô hiệu

ArrayList có iterator phát hiện sửa đổi cấu trúc theo cơ chế fail-fast. Nếu chủ sở hữu sửa nguồn trong lúc nơi khác đang duyệt iterator của view, lớp bọc không làm việc sửa đó biến mất và không mặc định bảo vệ iterator.

ConcurrentModificationException có thể báo lỗi kiểu này, kể cả các thay đổi tuần tự do cùng một luồng gây ra qua tham chiếu khác. Cơ chế phát hiện là cố gắng bắt lỗi; không dùng ngoại lệ ấy làm công cụ đồng bộ hoặc điều kiện đúng của chương trình.

Không kết luận “chỉ đọc nên không thể có ConcurrentModificationException”. Bên đọc không ghi qua view nhưng bên khác vẫn có thể ghi vào nguồn.

## 10. Làm việc giữa nhiều luồng: chỉ đọc không tự bảo đảm thấy dữ liệu mới

Các chương trình trong bài cho thay đổi và đọc diễn ra tuần tự, nên dễ quan sát quan hệ nguồn/view. Khi có nhiều luồng, cần thêm một tầng hợp đồng.

Bọc một ArrayList trong unmodifiableList không tạo khóa, không tạo quan hệ công bố dữ liệu mới giữa các luồng và không biến ArrayList thành một collection đồng thời.

Không thể từ chữ “live” hứa rằng một luồng khác sẽ thấy mọi cập nhật ngay lập tức hoặc thấy một ảnh chụp nhất quán của nhiều thao tác.

Một thiết kế đồng thời cần xác định:

- Ai có quyền ghi và các bên đọc/ghi phối hợp bằng cơ chế nào.
- Một lần đọc cần một phần tử, nhiều thao tác nhất quán hay cả phiên bản cố định.
- Phần tử mutable được quản lý đồng thời ra sao.
- Khi tạo snapshot, quá trình đọc nguồn có được bảo vệ để không chụp trạng thái hỗn hợp hay không.

Collections.synchronizedList là một cơ chế khác với unmodifiableList. Nếu chọn lớp bọc synchronized, việc truy cập và duyệt phải tuân theo khóa của thiết kế đó; việc chồng thêm một lớp unmodifiable không cho phép tùy tiện khóa một đối tượng khác và coi đã đồng bộ với bên ghi.

Một collection đồng thời như CopyOnWriteArrayList cũng có hợp đồng riêng về thao tác và iterator, không mặc định phù hợp mọi tải ghi hoặc mọi phần tử mutable.

Các nguyên tắc truy cập của [Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)) và đặc tả của [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) giúp phân biệt trách nhiệm lớp bọc với trách nhiệm phối hợp giữa luồng.

## 11. View hợp thành vẫn chịu giới hạn của nguồn

### 11.1. Không chữa được điều kiện vô hiệu của subList

Nếu bọc unmodifiableList(source.subList(...)), lớp ngoài chặn ghi qua kết quả nhưng list bên trong vẫn là subList.

Hợp đồng List.subList quy định ngữ nghĩa của nó trở nên không xác định khi list nguồn bị sửa cấu trúc theo cách không đi qua subList. Vì vậy không hứa rằng mọi kiểu sửa cấu trúc của source đều làm lớp bọc subList trở thành một cửa sổ hợp lệ tự điều chỉnh.

Một lỗi cần tránh là lấy kết quả đúng của unmodifiableList(source) với toàn list rồi áp nguyên vào mọi chuỗi view con. Phải đọc hợp đồng của từng lớp trong chuỗi.

### 11.2. Phạm vi chỉ cho nhìn dữ liệu trong khoảng

Một unmodifiableNavigableSet bọc view phạm vi của TreeSet vẫn chỉ nhìn các phần tử thuộc khoảng. Nguồn thêm phần tử ngoài khoảng thì view không hiện phần tử đó; đây là điều kiện chọn dữ liệu của view trong, không phải bằng chứng lớp bọc đã tạo snapshot.

Tương tự, một unmodifiableMap bọc một subMap chỉ đọc các ánh xạ trong phạm vi khóa của subMap. Nguồn đổi ngoài phạm vi có thể không làm kết quả quan sát từ cửa sổ ấy đổi.

Tính sống phải được hiểu là đọc theo nguồn và điều kiện view đang có, không phải mọi cập nhật ở bất cứ đâu trong cấu trúc gốc đều xuất hiện.

### 11.3. Không giữ một entry qua mọi biến động rồi mặc định nó luôn hợp lệ

Map.Entry lấy từ iterator có những điều kiện sử dụng theo hợp đồng của Map và kiểu entry cụ thể. Lớp bọc không biến entry đã lấy thành một bộ theo dõi khóa có tuổi thọ vô hạn.

Khi cần đọc giá trị hiện tại của một khóa qua map view sau cập nhật, dùng thao tác truy vấn map phù hợp. Khi cần lưu ảnh chụp entry, tạo một biểu diễn dữ liệu riêng và xác định mức độ sao chép của khóa/giá trị.

Chương trình LiveMapViewDemo chỉ dùng entry ở những điểm cập nhật/đọc được kiểm soát; nó không dựa vào entry cũ sau khi nguồn bị clear rồi nạp lại.

## 12. Chi phí, vòng đời và cách kiểm tra hợp đồng

Lớp bọc trực tiếp không có ý nghĩa sao chép toàn bộ phần tử nguồn sang một cấu trúc độc lập. Đây là lợi ích khi muốn cho đọc trạng thái đang thay đổi mà không tạo snapshot sau mỗi lần yêu cầu.

Nhưng không có nghĩa mọi thao tác đọc đều rẻ như nhau. Duyệt n phần tử vẫn phải đọc n phần tử; tìm kiếm hoặc truy cập theo vị trí phụ thuộc cấu trúc nguồn và hợp đồng của nó. Lớp bọc không tự thay LinkedList thành ArrayList hoặc tạo chỉ mục mới.

Giữ một view còn giữ quan hệ với nguồn. Nếu view hoặc chuỗi view sống lâu hơn nhu cầu ban đầu, nó có thể kéo dài vòng đời của cấu trúc nguồn. Khi chỉ cần một phần dữ liệu lịch sử nhỏ và muốn tách vòng đời, sao chép phù hợp có thể tốt hơn việc giữ view.

Để kiểm tra đúng tính chất của một API chỉ đọc, không chỉ thử add rồi dừng. Một bộ kiểm tra hành vi nên có:

1. Thử một thao tác ghi thực sự qua kết quả và xác nhận bị từ chối theo hợp đồng.
2. Sửa nguồn qua đường được phép, rồi đọc lại kết quả để biết đó là live view hay snapshot.
3. Thử thay tham chiếu ở một vị trí nguồn, tách khỏi việc chỉ sửa thuộc tính của phần tử.
4. Nếu phần tử mutable, thử sửa thuộc tính để kiểm tra mức độc lập thực tế.
5. Với cấu trúc lồng nhau, kiểm tra cả tầng trong.
6. Nếu có iterator hoặc view con, kiểm tra theo hợp đồng riêng của chúng.
7. Nếu cần snapshot nhất quán giữa các luồng, kiểm chứng cơ chế phối hợp lúc tạo snapshot.

Không dùng một thao tác không làm thay đổi gì, chẳng hạn một lời gọi với dữ liệu rỗng, để phân loại mọi collection trong Java. Một số phép cập nhật không có hiệu lực có quy tắc ngoại lệ phụ thuộc hợp đồng cụ thể. Hãy chọn một thao tác ghi thực sự khi mục tiêu là kiểm chứng quyền ghi bị chặn.

## 13. Bài tập và lời giải

### Bài 1 — Bọc trực tiếp hay bọc sau sao chép?

Nguồn là ArrayList [1,2]. Tạo a = unmodifiableList(source) và b = unmodifiableList(new ArrayList<>(source)). Sau source.add(3), a và b hiện gì?

**Lời giải:** a hiện [1,2,3], b hiện [1,2]. a còn đọc cấu trúc source; b đọc một ArrayList khác đã có trước lần thêm. Cả hai đều không cho thêm phần tử qua chính tham chiếu kết quả.

### Bài 2 — Gán lại biến

x đang trỏ ArrayList [A]. v = unmodifiableList(x). Sau x = new ArrayList<>(List.of("B")), v hiện A hay B?

**Lời giải:** A. Lớp bọc đang giữ quan hệ với đối tượng được truyền vào lúc tạo, không theo tên biến x. Nếu đối tượng cũ bị sửa hợp lệ qua một tham chiếu khác, v mới đọc thấy các sửa đổi đó.

### Bài 3 — final có ngăn nguồn thay đổi không?

Một trường final List<String> source được khởi tạo bằng ArrayList. Một trường final khác bọc source bằng unmodifiableList. Lệnh source.add("new") trong lớp có bị chặn vì final không?

**Lời giải:** không. final chặn gán lại trường source sau khởi tạo theo quy tắc thông thường, không cấm thay đổi nội dung ArrayList. View đọc thấy phần tử mới; add qua view vẫn bị chặn.

### Bài 4 — Bản sao nông có phần tử mutable

source chứa một Account mutable có balance = 10. a là unmodifiable view, b là List.copyOf(source). Nếu source.get(0).balance = 20 thì a và b đọc balance bằng bao nhiêu? Sau khi source.set(0,new Account(30)) thì sao?

**Lời giải:** sau sửa thuộc tính, cả hai đọc 20 vì còn cùng Account. Sau thay tham chiếu, a đọc Account mới có 30, b giữ Account cũ có 20. Kết quả thứ nhất không chứng minh b là view của cấu trúc source.

### Bài 5 — Map.Entry có chặn hết trạng thái bên trong không?

m là unmodifiableMap của Map<String,List<String>>. So sánh khả năng m.entrySet().iterator().next().setValue(newList) và m.get("k").add("x"), giả sử giá trị hiện có là một ArrayList mutable.

**Lời giải:** setValue là thao tác thay ánh xạ qua entry của lớp bọc và bị chặn. add trên ArrayList giá trị vẫn có thể thành công, vì nó sửa đối tượng được trả ra chứ không gọi một phép ghi của map. Muốn chặn hoặc tách trạng thái đó phải thiết kế thêm ở tầng giá trị.

### Bài 6 — View rỗng

Sau khi tạo view, chủ sở hữu gọi source.clear(). Có thể xem view như một list rỗng cố định để cache lâu dài không?

**Lời giải:** không thể chỉ từ clear mà kết luận vậy. Nguồn có thể thêm dữ liệu về sau và cùng view đọc thấy lại. Nếu cần giữ kết quả rỗng của một thời điểm, phải lấy kết quả với hợp đồng snapshot phù hợp.

### Bài 7 — Iterator của CopyOnWriteArrayList

Tạo unmodifiable view của CopyOnWriteArrayList [a]. Lấy iterator i, rồi nguồn thêm b. Một lần đọc view và một lần duyệt i có bắt buộc cùng hiện a,b không?

**Lời giải:** không. View hiện tại có [a,b], còn i giữ ảnh chụp lúc tạo và duyệt [a]. Chặn ghi qua iterator và quy tắc iterator nhìn phiên bản nào là hai vấn đề riêng.

### Bài 8 — Đổi getter sang List.copyOf

Một getter trước đây trả live view của danh sách có thể chứa null. Có thể thay toàn bộ bằng List.copyOf mà không thông báo thay đổi hợp đồng không?

**Lời giải:** không. Kết quả sẽ không theo các cập nhật cấu trúc về sau như view trước đó, và dữ liệu có null có thể khiến lời gọi thất bại. Cần xác định lại hợp đồng, xử lý null và kiểm tra nơi gọi phụ thuộc tính sống.

### Bài 9 — Chọn hợp đồng cho báo cáo

Một báo cáo cần danh sách giao dịch đúng tại thời điểm bắt đầu tạo báo cáo. Dữ liệu nguồn vẫn tiếp tục được cập nhật. Chỉ trả unmodifiableList(source) đã đáp ứng chưa?

**Lời giải:** chưa. Nó chặn báo cáo sửa danh sách qua kết quả nhưng không tách các cập nhật nguồn. Cần tạo snapshot nhất quán trong điều kiện phối hợp đúng với bên ghi. Nếu giao dịch mutable và báo cáo cần trạng thái cố định của chúng, còn phải tạo giá trị/ảnh chụp thích hợp cho từng giao dịch.

## 14. Những điểm cần nhận ra khi đọc code thực tế

| Điều đang thấy trong code | Kết luận được phép rút ra | Điều còn phải kiểm tra |
|---|---|---|
| Collections.unmodifiableList(source) | Ghi qua lớp bọc bị chặn; đọc theo nguồn | Ai còn đường ghi vào nguồn? |
| Nguồn được sửa sau khi tạo view | View toàn nguồn có thể đọc trạng thái mới hợp lệ | Quy tắc iterator, luồng và view con |
| new ArrayList<>(source) rồi bọc | Cấu trúc riêng với source ban đầu | Bản sao có rò rỉ đường ghi; phần tử có dùng chung không? |
| List.copyOf(source) | Kết quả không theo thay đổi cấu trúc của collection đầu vào | Null, phần tử mutable và thời điểm sao chép |
| Trường nguồn là final | Tham chiếu trường có ràng buộc gán lại | Nội dung đối tượng vẫn có thể đổi |
| Các tầng ngoài đều unmodifiable | Chặn ghi qua các tầng đã bọc | Tầng trong chưa bọc và các đối tượng giá trị |
| Dữ liệu in giống lúc tạo view | Chưa quan sát thấy thay đổi | Nguồn có thực sự bị sửa, thay đổi có nằm trong phạm vi không? |
| Một iterator chỉ thấy dữ liệu cũ | Có thể là quy tắc iterator | Không kết luận cả view là snapshot chỉ từ iterator đó |
| Kết quả chỉ được đọc bởi nơi nhận | Nơi nhận không ghi qua tham chiếu ấy | Bên khác có ghi và có đồng bộ đúng không? |

Câu hỏi hữu ích nhất khi gặp một unmodifiable view là: **lớp bọc đang đọc từ đối tượng nào, và ai vẫn có thể sửa đối tượng đó hoặc các phần tử được chứa?** Từ câu trả lời ấy mới quyết định cần view sống, bản sao cấu trúc hay ảnh chụp giá trị.

## 15. Tài liệu đối chiếu

- [Collections — unmodifiableList, unmodifiableSet và unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).
- [Collection — View Collections và Unmodifiable Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).
- [List — copyOf và hợp đồng subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).
- [Map — collection views và copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).
- [CopyOnWriteArrayList — iterator giữ ảnh chụp](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).
