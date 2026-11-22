# Collections.unmodifiableList, unmodifiableSet và unmodifiableMap

## 1. Cung cấp quyền đọc qua một đường tham chiếu

Một lớp đang giữ danh sách, tập hợp hoặc map sửa được, nhưng muốn người nhận chỉ đọc qua kết quả được trả về. Ba phương thức trong bài tạo các view không cho sửa qua giao diện của chúng:

| Phương thức | Đối số | Kết quả |
|---|---|---|
| Collections.unmodifiableList(...) | List | List không cho sửa qua wrapper |
| Collections.unmodifiableSet(...) | Set | Set không cho sửa qua wrapper |
| Collections.unmodifiableMap(...) | Map | Map không cho sửa qua wrapper |

Wrapper là lớp bọc: nó cung cấp một đường truy cập khác lên cùng dữ liệu nguồn. Các thao tác đọc dựa trên nguồn; các thao tác sửa qua wrapper bị từ chối bằng UnsupportedOperationException.

Điểm cần nắm ngay từ đầu là **không cho sửa qua wrapper không đồng nghĩa dữ liệu nguồn không bao giờ đổi**. Nếu nơi khác còn giữ nguồn sửa được, nơi đó vẫn có thể thay đổi nguồn. View sẽ đọc dữ liệu nguồn theo hợp đồng của nó.

Một mô hình đơn giản:

```text
Chủ sở hữu ──→ collection nguồn sửa được
                         ↑
Người nhận ──→ wrapper đọc dữ liệu nguồn
              add/remove/... bị từ chối qua đường này
```

Các ví dụ đầy đủ trong bài dùng Java 17 trở lên. List được minh họa bằng ArrayList; Set và Map dùng LinkedHashSet/LinkedHashMap để thứ tự stdout được xác định rõ.

### 1.1. Vì sao dùng wrapper?

Wrapper hữu ích khi muốn cho người khác quan sát dữ liệu hiện tại nhưng giữ các thao tác cập nhật trong lớp chủ sở hữu. Nó cũng giúp diễn đạt rằng một kết quả không được sửa trực tiếp.

Ví dụ, một registry cho phép đăng ký bằng phương thức có kiểm tra điều kiện. Trả trực tiếp List nội bộ sẽ cho người gọi add mà bỏ qua điều kiện đó. Trả một view không cho sửa sẽ buộc các cập nhật collection qua API mà registry công bố.

Tuy vậy, vẫn phải xét các tham chiếu khác và trạng thái phần tử. Một List không cho add chưa tự ngăn người nhận sửa một đối tượng mutable được get từ List.

## 2. Hợp đồng chung cần phân biệt

### 2.1. Đọc từ nguồn, không sao chép toàn bộ dữ liệu

Ba phương thức unmodifiable trong bài tạo view được hỗ trợ bởi đối số. Chúng không có hợp đồng thu mọi phần tử vào một collection chứa riêng như new ArrayList<>(source).

Nếu nguồn thêm phần tử, xóa phần tử hoặc đổi một ánh xạ hợp lệ, việc đọc wrapper phản ánh nguồn theo hợp đồng. Không gọi wrapper là một snapshot cố định tại thời điểm bọc.

Không dựa vào danh tính đối tượng wrapper. API có thể trả lại một đối số đã không cho sửa phù hợp; điều cần dùng là hợp đồng, không phải kỳ vọng mỗi lần bọc chắc chắn tạo đối tượng khác theo ==.

Nguồn đối chiếu: [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html), các mục unmodifiableList, unmodifiableSet và unmodifiableMap.

### 2.2. Phương thức sửa vẫn xuất hiện ở mức kiểu

List vẫn khai báo add, set, remove; Map vẫn khai báo put và compute. Wrapper không tạo một giao diện Java mới chỉ có các phương thức đọc.

Vì vậy, mã gọi view.add có thể biên dịch rồi ném UnsupportedOperationException lúc chạy. Đổi kiểu tham chiếu hay thêm final trước biến không mở lại quyền sửa của wrapper.

final chỉ ngăn gán lại biến tham chiếu theo quy tắc ngôn ngữ. Nó không biến collection nguồn thành một đối tượng không đổi và không thay vai trò của unmodifiable wrapper.

### 2.3. Các đường sửa gián tiếp cũng cần được chặn

Chỉ chặn view.add là chưa đủ cho hợp đồng không cho sửa. Iterator có remove, List có ListIterator và subList, Map có keySet, values, entrySet cùng các Entry.

Các wrapper chuẩn trong bài bảo vệ cả những đường sửa qua các view hoặc iterator mà chúng trả về. Không xem iterator.remove hay entry.setValue như lối sửa hợp lệ thay thế một lệnh add/put bị cấm.

Các ví dụ tiếp theo kiểm tra những đường đi cụ thể bằng các lời gọi thực tế, rồi in nguồn để đối chiếu.

### 2.4. Hợp đồng nguồn vẫn có ý nghĩa

Wrapper không tự sắp xếp dữ liệu, không lọc null và không tạo tính duy nhất khác cho nguồn.

Một wrapper trên LinkedHashSet phản ánh thứ tự duyệt của LinkedHashSet. Bọc một HashSet không tự tạo cam kết thứ tự thêm. Tương tự, unmodifiableMap không biến HashMap thành map sắp theo khóa.

Đối số collection/map null bị từ chối bằng NullPointerException. Điều đó khác với phần tử, khóa hoặc giá trị null đã được một nguồn hợp lệ cho phép.

## 3. unmodifiableList: vẫn đọc theo chỉ số, không sửa qua List

unmodifiableList giữ giao diện List: có thể dùng get, size, contains, duyệt và lấy một khoảng con. Quyền đọc theo chỉ số không đồng nghĩa được set vào chỉ số đó.

Các thao tác sửa cần bị xét gồm add, remove, set, clear, thay hàng loạt phần tử và các đường sửa từ iterator/ListIterator. subList của wrapper cũng không mở quyền xóa một khoảng khỏi nguồn.

### 3.1. Chương trình 1: nguồn đổi, wrapper đọc thấy

Lưu vào `UnmodifiableListDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

public class UnmodifiableListDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B"));
        List<String> view = Collections.unmodifiableList(source);
        source.add("C");
        source.set(0, "A2");
        System.out.println("viewAfterSourceEdits=" + view);
        System.out.println("first=" + view.get(0));
        expectUnsupported("add", () -> view.add("D"));
        expectUnsupported("set", () -> view.set(0, "changed"));
        Iterator<String> cursor = view.iterator();
        System.out.println("iteratorNext=" + cursor.next());
        expectUnsupported("iteratorRemove", () -> cursor.remove());
        expectUnsupported("subListClear", () -> view.subList(1, 3).clear());
        expectUnsupported("removeIf", () -> view.removeIf(value -> value.equals("B")));
        System.out.println("sourceAfterRejectedEdits=" + source);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableListDemo.java
java UnmodifiableListDemo
```

Stdout:

```text
viewAfterSourceEdits=[A2, B, C]
first=A2
add=UnsupportedOperationException
set=UnsupportedOperationException
iteratorNext=A2
iteratorRemove=UnsupportedOperationException
subListClear=UnsupportedOperationException
removeIf=UnsupportedOperationException
sourceAfterRejectedEdits=[A2, B, C]
```

### 3.2. Hai đường truy cập có quyền khác nhau

source.add(C) và source.set(0,A2) được gọi qua ArrayList nguồn, nên thành công. viewAfterSourceEdits là `[A2, B, C]`; get(0) trả A2.

view.add và view.set ném UnsupportedOperationException vì được gọi qua wrapper. Cùng dữ liệu nguồn nhưng đường thao tác khác có quyền sửa khác.

### 3.3. Iterator và khoảng con không vượt qua giới hạn

cursor.next vẫn đọc A2, nhưng cursor.remove bị từ chối. Iterator được lấy từ wrapper không trao lại quyền xóa của ArrayList nguồn.

view.subList(1,3).clear cũng bị từ chối. Việc tạo một view con từ wrapper không làm khoảng con đó sửa được.

removeIf là một thao tác sửa theo điều kiện và cũng bị từ chối trong ví dụ. Nguồn sau những lời gọi bị chặn vẫn là A2,B,C.

Helper expectUnsupported chỉ phục vụ kiểm chứng: nếu lời gọi không ném ngoại lệ, nó báo AssertionError. Mã nghiệp vụ nên chọn đúng quyền thao tác từ đầu, không dùng ngoại lệ để dò rồi bỏ qua yêu cầu sửa.

## 4. unmodifiableSet: giữ hợp đồng tập hợp và chặn sửa

Set không có chỉ số như List. Wrapper vẫn cung cấp size, contains, phép duyệt và tính chất tập hợp theo nguồn. Nó không cho add, remove hoặc clear qua wrapper.

Nếu nguồn dùng đối tượng mutable làm phần tử, wrapper không tự đóng băng trạng thái của đối tượng đó. Đặc biệt, không được dựa vào wrapper để bảo vệ hợp đồng equals/hashCode của một phần tử đang ở trong tập băm.

Hợp đồng Set được mô tả tại [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### 4.1. Chương trình 2: nguồn và chính sách null

Lưu vào `UnmodifiableSetDemo.java`:

```java
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class UnmodifiableSetDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        Set<String> source = new LinkedHashSet<>(List.of("red", "blue"));
        Set<String> view = Collections.unmodifiableSet(source);
        System.out.println("containsRed=" + view.contains("red"));
        source.add("green");
        System.out.println("viewAfterSourceAdd=" + view);
        expectUnsupported("setAdd", () -> view.add("yellow"));
        expectUnsupported("setRemove", () -> view.remove("red"));
        expectUnsupported("setClear", () -> view.clear());
        Iterator<String> cursor = view.iterator();
        System.out.println("setIteratorNext=" + cursor.next());
        expectUnsupported("setIteratorRemove", () -> cursor.remove());
        source.add(null);
        System.out.println("viewAfterSourceNull=" + view);
        System.out.println("viewContainsNull=" + view.contains(null));
        System.out.println("sourceSize=" + source.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableSetDemo.java
java UnmodifiableSetDemo
```

Stdout:

```text
containsRed=true
viewAfterSourceAdd=[red, blue, green]
setAdd=UnsupportedOperationException
setRemove=UnsupportedOperationException
setClear=UnsupportedOperationException
setIteratorNext=red
setIteratorRemove=UnsupportedOperationException
viewAfterSourceNull=[red, blue, green, null]
viewContainsNull=true
sourceSize=4
```

### 4.2. Thứ tự trong output đến từ nguồn LinkedHashSet

source thêm red,blue, sau đó green. viewAfterSourceAdd là `[red, blue, green]`. Wrapper không sắp xếp theo chữ cái; nó đọc thứ tự của nguồn.

setAdd, setRemove, setClear và setIteratorRemove đều bị từ chối. contains và iterator.next vẫn đọc được dữ liệu.

### 4.3. Wrapper không biến một nguồn có null thành nguồn cấm null

LinkedHashSet nguồn cho null, nên source.add(null) thành công. Wrapper sau đó nhìn thấy null và contains(null) trả true; sourceSize là 4.

Không áp quy tắc “mọi collection không cho sửa đều cấm null” cho ba wrapper này. Các factory như Set.of hoặc Set.copyOf có hợp đồng null riêng; chúng không đồng nghĩa với việc bọc một Set đã có bằng unmodifiableSet.

Cũng không suy ra mọi nguồn đều chấp nhận truy vấn null. Quyền và hạn chế của nguồn thực tế vẫn cần được đọc theo API của nó.


## 5. unmodifiableMap phải bảo vệ cả ba collection view

Map có thể bị sửa không chỉ qua put/remove. keySet.remove có thể xóa ánh xạ theo khóa; values.remove có thể xóa một ánh xạ mang giá trị tương ứng; entrySet và Entry.setValue cũng có các thao tác sửa.

unmodifiableMap chặn sửa qua chính Map và qua những collection view mà nó cung cấp. Điều này giúp người nhận không lấy một view con rồi sửa map nguồn qua đường đó.

| Đường truy cập | Ví dụ thao tác đọc | Ví dụ thao tác sửa bị chặn |
|---|---|---|
| Map | get, containsKey, size | put, remove, clear, compute |
| keySet() | contains, iterator.next | remove, clear, iterator.remove |
| values() | contains, duyệt giá trị | remove, clear |
| entrySet() | duyệt cặp khóa–giá trị | remove, clear |
| Entry từ entrySet của wrapper | getKey, getValue | setValue |

Không đánh đồng việc chặn setValue với việc mọi đối tượng giá trị trở nên bất biến. getValue có thể trả một List mutable; thay nội dung List đó khác với yêu cầu thay ánh xạ trong Map.

Hợp đồng Map cùng các view được mô tả tại [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html). Hợp đồng wrapper cụ thể nằm ở [Collections.unmodifiableMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).

### 5.1. Phương thức có callback vẫn là thao tác sửa

compute, merge, replaceAll và các phương thức cập nhật tương tự không trở thành quyền đọc chỉ vì người gọi truyền một hàm.

Nếu ý định là tính một kết quả khác từ dữ liệu, hãy tạo kết quả riêng. Nếu ý định là cập nhật map, phải đi qua API có quyền sửa phù hợp. Không cố dùng một phương thức cập nhật khác để lách một put đã bị từ chối.

### 5.2. Không dựa vào một phép sửa “chắc không làm gì”

Các giao diện collection/map có những quy định riêng về thao tác tùy chọn và lời gọi không gây tác dụng thực tế. Các thuật toán như sort còn có thể có cách thực hiện khác nhau.

Vì vậy, không dùng remove một khóa không tồn tại, putAll rỗng hay sort một danh sách đã có thứ tự như phép kiểm tra đọc vô hại. Viết mã theo ý định đọc hoặc sửa; không dùng kết quả của một trường hợp không đổi dữ liệu để kết luận quyền sửa nói chung.

Ví dụ tiếp theo dùng các lời gọi sửa rõ ràng trên dữ liệu có sẵn để kiểm tra hợp đồng wrapper.

## 6. Chương trình 3: chặn sửa qua Map, view và Entry

Lưu vào `UnmodifiableMapDemo.java`. LinkedHashMap được dùng để thứ tự các ánh xạ khi in được xác định.

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class UnmodifiableMapDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("a", 1);
        source.put("b", 2);
        Map<String, Integer> view = Collections.unmodifiableMap(source);
        source.put("b", 20);
        source.put("c", 3);
        System.out.println("viewAfterSourcePut=" + view);
        System.out.println("getB=" + view.get("b"));
        expectUnsupported("mapPut", () -> view.put("d", 4));
        expectUnsupported("mapRemove", () -> view.remove("a"));
        expectUnsupported("mapCompute", () -> view.compute("a", (key, value) -> value + 1));
        expectUnsupported("keySetRemove", () -> view.keySet().remove("a"));
        expectUnsupported("valuesRemove", () -> view.values().remove(20));
        expectUnsupported("entrySetClear", () -> view.entrySet().clear());
        Map.Entry<String, Integer> entry = view.entrySet().iterator().next();
        System.out.println("entryBeforeSet=" + entry);
        expectUnsupported("entrySetValue", () -> entry.setValue(99));
        System.out.println("sourceAfterRejectedMapEdits=" + source);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableMapDemo.java
java UnmodifiableMapDemo
```

Stdout:

```text
viewAfterSourcePut={a=1, b=20, c=3}
getB=20
mapPut=UnsupportedOperationException
mapRemove=UnsupportedOperationException
mapCompute=UnsupportedOperationException
keySetRemove=UnsupportedOperationException
valuesRemove=UnsupportedOperationException
entrySetClear=UnsupportedOperationException
entryBeforeSet=a=1
entrySetValue=UnsupportedOperationException
sourceAfterRejectedMapEdits={a=1, b=20, c=3}
```

### 6.1. Cập nhật nguồn được đọc qua wrapper

Sau source.put(b,20) và source.put(c,3), wrapper đọc được `{a=1, b=20, c=3}`. get(b) trả 20.

Việc thay giá trị b ở nguồn không bị wrapper ngăn cản. Wrapper chỉ kiểm soát các thao tác gọi qua chính nó và những view bảo vệ mà nó trả về.

### 6.2. Các cách cập nhật khác nhau đều bị từ chối

mapPut, mapRemove và mapCompute đều ném UnsupportedOperationException. Không có việc dùng compute để mở lại quyền sửa một map bị bọc.

keySetRemove, valuesRemove và entrySetClear cũng bị từ chối. Đó là những đường có thể sửa một Map thông thường, nên không thể chỉ bảo vệ các phương thức trực tiếp trên Map rồi bỏ qua chúng.

### 6.3. Entry đọc được nhưng không setValue được

Entry đầu trong ví dụ là a=1. entry.setValue(99) bị chặn; sourceAfterRejectedMapEdits vẫn là `{a=1, b=20, c=3}`.

Entry này được lấy từ entrySet của wrapper và dùng ngay trong phép minh họa. Không tự coi mọi Entry là một snapshot có vòng đời vô hạn: hợp đồng của Entry còn phụ thuộc đường lấy nó. Điểm cần rút ra ở đây là wrapper không trao quyền sửa ánh xạ bằng setValue.

## 7. Chỉ đọc ở lớp ngoài chưa phải chỉ đọc mọi trạng thái

### 7.1. Một phần tử mutable vẫn có thể được sửa

List<StringBuilder> được bọc vẫn trả StringBuilder khi gọi get. Append trên StringBuilder không gọi add/remove/set của List.

Wrapper không có khả năng tự thay đổi toàn bộ API của mọi kiểu phần tử E. Muốn kiểm soát việc sửa trạng thái đó, cần mô hình phần tử bất biến, bản sao phần tử hoặc một cách cung cấp dữ liệu phù hợp khác.

Tương tự, Map không cho put vẫn có thể mang giá trị là List sửa được. Gọi map.get(key).add(x) sửa List giá trị, không thay ánh xạ của Map.

### 7.2. Sao chép trước khi bọc chỉ tách lớp được sao chép

Collections.unmodifiableList(new ArrayList<>(source)) tạo một cấu trúc List chứa riêng rồi bọc nó. Thêm/xóa trên source về sau không làm cấu trúc kết quả tự thay đổi.

Nhưng ArrayList mới vẫn chứa các tham chiếu phần tử đã có. Nếu phần tử là StringBuilder, cả nguồn lẫn kết quả có thể cùng nhìn thấy một lần append.

Đừng gọi cấu trúc này là deep copy tổng quát. Cần xét riêng các lớp dữ liệu có trạng thái có thể thay đổi.

### 7.3. Collection lồng nhau cần quyết định từng lớp

Với Map<String,List<String>>, muốn tách khỏi nguồn và chặn sửa qua cả Map lẫn List con, có thể:

1. Tạo Map chứa mới.
2. Tạo List mới cho mỗi giá trị.
3. Bọc từng List con.
4. Bọc Map ngoài.
5. Quản lý quyền sửa các cấu trúc chứa mới, không đưa tham chiếu mutable của chúng ra ngoài.

String trong ví dụ là bất biến nên không cần tạo thêm một String chỉ để chặn sửa nội dung nó. Nếu đổi thành List<MutablePermission>, sao chép và bọc List vẫn chưa tự bảo vệ MutablePermission.

Đây là một chính sách theo mô hình cụ thể. Không có quy tắc tự động rằng cứ thêm một wrapper ngoài cùng là mọi đường dữ liệu bên trong đều đã chỉ đọc.

## 8. Chương trình 4: tách cấu trúc chứa và bọc các lớp cần bảo vệ

Lưu vào `UnmodifiableLayersDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class UnmodifiableLayersDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<StringBuilder> source = new ArrayList<>(List.of(new StringBuilder("draft")));
        List<StringBuilder> detachedOuter =
                Collections.unmodifiableList(new ArrayList<>(source));
        source.add(new StringBuilder("extra"));
        detachedOuter.get(0).append("!");
        System.out.println("sourceSize=" + source.size());
        System.out.println("detachedSize=" + detachedOuter.size());
        System.out.println("sharedMutableElement=" + source.get(0));
        System.out.println("sameElement=" + (source.get(0) == detachedOuter.get(0)));

        Map<String, List<String>> roles = new LinkedHashMap<>();
        roles.put("admin", new ArrayList<>(List.of("read")));
        Map<String, List<String>> outerView = Collections.unmodifiableMap(roles);
        outerView.get("admin").add("write");
        System.out.println("sourceRolesAfterInnerEdit=" + roles.get("admin"));

        Map<String, List<String>> copied = new LinkedHashMap<>();
        roles.forEach((key, values) -> copied.put(key,
                Collections.unmodifiableList(new ArrayList<>(values))));
        Map<String, List<String>> readOnlyCopy = Collections.unmodifiableMap(copied);
        roles.get("admin").add("owner");
        System.out.println("sourceRolesAfterLaterEdit=" + roles.get("admin"));
        System.out.println("copiedRoles=" + readOnlyCopy.get("admin"));
        expectUnsupported("nestedListAdd", () -> readOnlyCopy.get("admin").add("blocked"));
        expectUnsupported("outerMapPut", () -> readOnlyCopy.put("guest", List.of("read")));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableLayersDemo.java
java UnmodifiableLayersDemo
```

Stdout:

```text
sourceSize=2
detachedSize=1
sharedMutableElement=draft!
sameElement=true
sourceRolesAfterInnerEdit=[read, write]
sourceRolesAfterLaterEdit=[read, write, owner]
copiedRoles=[read, write]
nestedListAdd=UnsupportedOperationException
outerMapPut=UnsupportedOperationException
```

### 8.1. List ngoài đã tách, StringBuilder vẫn chung

detachedOuter được tạo từ ArrayList mới. Sau source.add(extra), sourceSize là 2 còn detachedSize vẫn 1.

Tuy nhiên, append qua detachedOuter.get(0) làm source.get(0) in draft!. sameElement là true. Cấu trúc chứa riêng không tự nhân bản đối tượng phần tử.

### 8.2. Map ngoài không cho put nhưng List giá trị còn sửa được

outerView bọc roles. outerView.get(admin).add(write) thành công vì giá trị được trả về là ArrayList chưa được bọc.

sourceRolesAfterInnerEdit là read,write. Không có put nào gọi trên outerView trong thao tác này; hợp đồng chặn sửa Map không bị vượt qua, mà một đối tượng khác được sửa.

### 8.3. Bản sao hai lớp không theo thay đổi của nguồn cũ

copied tạo các List giá trị mới từ nội dung hiện tại, rồi từng List được bọc. readOnlyCopy bọc Map chứa những List đó.

Sau roles.get(admin).add(owner), nguồn cũ có read,write,owner nhưng copiedRoles vẫn chỉ read,write. List giá trị của kết quả không còn là List giá trị nguồn.

nestedListAdd bị chặn bởi wrapper List con; outerMapPut bị chặn bởi wrapper Map ngoài. Cần bảo vệ đúng lớp mà người nhận có thể tiếp cận.

### 8.4. Quyền sở hữu cấu trúc mới vẫn quan trọng

copied vẫn là một LinkedHashMap sửa được trong phạm vi chương trình. Nếu mã chủ sở hữu tiếp tục sửa copied, readOnlyCopy sẽ đọc thấy thay đổi đó.

Ví dụ không giữ một tham chiếu sửa được đến các ArrayList con được tạo trong biểu thức trước khi bọc. Trong API thực tế, hãy kiểm soát những tham chiếu này thay vì chỉ dựa vào tên biến readOnly.

Bốn ví dụ không dùng nhiều luồng; việc tách và bọc dữ liệu không tự cung cấp hợp đồng truy cập đồng thời.


## 9. Chọn view đang theo nguồn hay kết quả tách khỏi nguồn

### 9.1. Khi cần quan sát dữ liệu hiện tại

Dùng unmodifiableList(source), unmodifiableSet(source) hoặc unmodifiableMap(source) khi người nhận được phép thấy những cập nhật của nguồn nhưng không được tự sửa qua kết quả được cung cấp.

Chủ sở hữu vẫn cần giữ quyền cập nhật trong những phương thức phù hợp. Ví dụ, thêm một tên qua phương thức register có thể kiểm tra trùng hoặc điều kiện nghiệp vụ trước khi sửa nguồn.

Nếu đưa cả source sửa được ra ngoài ở một chỗ khác, wrapper ở getter không thu hồi quyền sửa mà tham chiếu source kia đã có. Cần xem toàn bộ đường cung cấp dữ liệu.

### 9.2. Khi cần một kết quả chứa độc lập

Có thể sao chép cấu trúc chứa trước rồi bọc. Các đoạn dưới đây là minh họa đặt trong phương thức đã có listSource kiểu List<String>, setSource kiểu Set<String>, mapSource kiểu Map<String,Integer> và các import java.util tương ứng; chúng không phải tệp Java độc lập.

```java
List<String> listResult =
        Collections.unmodifiableList(new ArrayList<>(listSource));

Set<String> setResult =
        Collections.unmodifiableSet(new LinkedHashSet<>(setSource));

Map<String, Integer> mapResult =
        Collections.unmodifiableMap(new LinkedHashMap<>(mapSource));
```

ArrayList mới tách các vị trí List khỏi nguồn. LinkedHashSet và LinkedHashMap mới thu dữ liệu theo thứ tự duyệt của nguồn tại lúc sao chép. Chúng không tự suy ra một thứ tự thêm đã bị nguồn bỏ qua, và cũng không tự sắp theo khóa hay giá trị.

Những thay đổi tiếp theo của collection nguồn cũ không làm cấu trúc chứa mới tự cập nhật. Tuy nhiên, các phần tử, khóa và giá trị được sao chép theo tham chiếu; nếu chúng mutable thì còn phải xét lớp dữ liệu đó.

### 9.3. So với các factory copyOf

List.copyOf, Set.copyOf và Map.copyOf cũng cung cấp kết quả không cho sửa với hợp đồng nội dung không theo các thay đổi collection nguồn sau đó. Chúng không phải các view sống giống ba wrapper bọc trực tiếp nguồn trong bài.

Nhưng không thay thế máy móc:

| Lựa chọn | Quan hệ với cấu trúc nguồn về sau | Null và thứ tự cần xét |
|---|---|---|
| Bọc trực tiếp bằng unmodifiable | Đọc theo nguồn đang được bọc | Phụ thuộc nguồn; không tự sắp xếp hoặc lọc null |
| Sao chép vào cấu trúc đã chọn rồi bọc | Cấu trúc mới tách khỏi nguồn cũ | Theo kiểu chứa được chọn; vẫn là sao chép nông phần tử |
| List.copyOf | Nội dung List kết quả không theo sửa cấu trúc nguồn về sau | Cấm phần tử null, giữ thứ tự của collection đầu vào |
| Set.copyOf | Tập kết quả không theo sửa cấu trúc nguồn về sau | Cấm null, không hứa thứ tự như LinkedHashSet |
| Map.copyOf | Các ánh xạ kết quả không theo sửa cấu trúc nguồn về sau | Cấm khóa/giá trị null, không hứa thứ tự như LinkedHashMap |

Các factory này vẫn có thể chứa đối tượng mutable được dùng chung. Chúng cũng có thể tận dụng một kết quả không cho sửa phù hợp, nên không hứa luôn cấp một đối tượng mới theo danh tính.

Nguồn đối chiếu: [List — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### 9.4. Giữ đúng giao diện mà API cần

Ba phương thức trong bài trả List, Set và Map. Nếu API còn cần hợp đồng SortedSet, NavigableSet, SortedMap hoặc NavigableMap, hãy chọn wrapper chuyên biệt tương ứng thay vì bọc thành Set/Map rồi ép kiểu để gọi các phương thức chuyên biệt.

Không ép một wrapper về ArrayList, LinkedHashSet hay LinkedHashMap để sửa. Wrapper không có hợp đồng là chính lớp cụ thể đó. Nếu người nhận cần một bản sửa được, tạo một bản chứa riêng theo yêu cầu thay vì cố mở quyền sửa của view.

### 9.5. Wrapper theo đối tượng nguồn, không theo tên biến

Từ quan hệ bọc đối tượng có thể suy ra: gán biến source sang một collection khác không làm wrapper cũ tự chuyển sang đối tượng mới.

Thay nội dung collection đang được bọc và thay một biến để trỏ đến collection khác là hai hành động khác nhau. Khi một lớp thay toàn bộ trường dữ liệu bằng collection mới, cần thiết kế rõ những view đã trả trước đó sẽ còn nhìn đối tượng cũ hay người nhận phải lấy kết quả mới.

## 10. Vòng đời, quyền sở hữu và truy cập đồng thời

### 10.1. Chỉ đọc không tự bảo đảm an toàn cho nhiều luồng

Wrapper không tự thêm đồng bộ cho ArrayList, LinkedHashSet hoặc LinkedHashMap nguồn. Nếu một nơi đọc wrapper còn nơi khác sửa nguồn đồng thời, vẫn phải tuân theo hợp đồng truy cập của nguồn và thiết kế phối hợp phù hợp.

Không coi UnsupportedOperationException là công cụ điều phối luồng. Nó từ chối một đường sửa không được hỗ trợ; nó không thay thế khóa, không tạo ảnh chụp nguyên tử và không làm nhiều lần đọc thành một giao dịch.

Nếu cần dữ liệu nhất quán tại một thời điểm, quá trình tạo bản sao cũng phải đọc nguồn trong điều kiện thích hợp. Bọc một nguồn đang thay đổi không giải quyết điều kiện đó.

### 10.2. Iterator không phải snapshot được tạo tự động

Iterator lấy từ wrapper đọc theo cơ chế của nguồn. Nếu nguồn có iterator fail-fast, sửa cấu trúc nguồn trong lúc đang duyệt có thể làm phép duyệt bị phát hiện lỗi.

Chặn iterator.remove chỉ giới hạn quyền xóa qua iterator đó; nó không đóng băng nguồn trong suốt vòng lặp. Không giữ iterator rồi sửa nguồn qua tham chiếu khác và suy ra đọc sẽ an toàn vì iterator đến từ wrapper.

Các chương trình đầy đủ trong bài sửa nguồn trước khi tạo iterator cần dùng, và không dựa vào cạnh tranh giữa các luồng.

### 10.3. Không cho sửa collection không bảo vệ khóa mutable

Nếu một đối tượng mutable được dùng làm phần tử Set hoặc khóa Map, thay trạng thái ảnh hưởng equals/hashCode có thể làm vi phạm hợp đồng cấu trúc chứa. Wrapper không tự khóa các trường hay phương thức sửa của đối tượng đó.

Một thiết kế dữ liệu chỉ đọc đủ cho nhu cầu thực tế thường cần cả quyền sở hữu nguồn rõ ràng và kiểu phần tử/khóa phù hợp. Không đo mức bảo vệ chỉ bằng việc một lệnh add bị từ chối.

### 10.4. Chi phí và thời gian sống cần được cân nhắc

Bọc trực tiếp không có ý nghĩa sao chép toàn bộ n phần tử sang cấu trúc chứa khác. Điều này phù hợp khi muốn một view tiếp tục quan sát dữ liệu đang được chủ sở hữu quản lý.

Sao chép trước khi bọc cần thu các tham chiếu hoặc ánh xạ vào cấu trúc chứa mới. Đổi lại, cấu trúc kết quả không còn bám vào các vị trí hay ánh xạ của collection nguồn cũ.

Không chọn chỉ theo tên “nhẹ” hay “an toàn”. Hãy xác định người nhận có được nhìn thấy cập nhật sau đó không, có giữ kết quả lâu không, và các đối tượng phần tử còn chia sẻ trạng thái nào.

## 11. Những lỗi thường gặp

| Cách hiểu hoặc cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Bọc xong thì source không sửa được nữa | Tham chiếu nguồn vẫn có quyền của nguồn | Quản lý các đường cung cấp source |
| Wrapper là snapshot | View đọc theo nguồn | Sao chép trước nếu cần tách cấu trúc chứa |
| Không add được nhưng set chắc được | set cũng là sửa List | Đọc hợp đồng quyền sửa, không chỉ kích thước |
| Dùng iterator.remove để thay view.remove | Iterator của wrapper không mở quyền xóa | Dùng API cập nhật có quyền hoặc sửa một bản sao |
| Xóa qua subList của wrapper | View con vẫn không cho sửa | Không coi view con là đường vượt quyền |
| Sửa map qua keySet/values/entrySet | Những đường đó cũng được bảo vệ | Cập nhật qua chủ sở hữu hoặc bản map khác |
| Dùng Entry.setValue vì Entry đọc được | Thay giá trị ánh xạ vẫn là thao tác sửa | Không dùng Entry của wrapper để cập nhật map |
| Map không cho put thì List giá trị cũng không add được | Hai đối tượng có quyền riêng | Bọc hoặc sao chép các lớp cần bảo vệ |
| List không cho sửa làm StringBuilder bên trong bất biến | Wrapper không đổi API của phần tử | Chọn phần tử bất biến hoặc bản sao phù hợp |
| Mọi collection chỉ đọc đều cấm null | Wrapper và factory có hợp đồng khác nhau | Xét nguồn và cách tạo kết quả |
| Wrapper thêm thứ tự ổn định cho HashSet/HashMap | Nó không đổi chính sách thứ tự của nguồn | Chọn cấu trúc có thứ tự khi đó là yêu cầu |
| final collection thay thế unmodifiable | final chỉ hạn chế gán lại biến | Tách quyền gán biến với quyền sửa đối tượng |
| Unmodifiable đồng nghĩa thread-safe | Không có bảo đảm đồng bộ tự động | Thiết kế truy cập theo hợp đồng nguồn |
| Ép wrapper về lớp nguồn để sửa | Lớp thực tế không được hứa là lớp nguồn | Tạo bản sửa được riêng khi cần |
| Gán source sang collection khác thì view cũ theo sang | Wrapper gắn với đối tượng đã được bọc | Quản lý vòng đời của view và trường nguồn |
| Chỉ kiểm tra size sau thao tác để đo bất biến | Phần tử hoặc giá trị có thể đổi mà size giữ nguyên | Kiểm tra cả trạng thái và quan hệ tham chiếu |

Không dùng catch chung Exception rồi bỏ qua để che một thao tác sửa bị từ chối. UnsupportedOperationException thường cho thấy mã gọi đang dùng một kết quả vượt quyền sửa mà hợp đồng cung cấp.

## 12. Tự kiểm tra và thực hành

### 12.1. Câu hỏi với đáp án

1. **unmodifiableList(source) có sao chép phần tử vào List mới độc lập không?** Không theo hợp đồng wrapper; nó cung cấp view đọc dữ liệu nguồn.
2. **source.add sau khi bọc có bị wrapper ngăn không?** Không. Lời gọi qua nguồn vẫn theo quyền của nguồn.
3. **Vì sao view.add biên dịch được nhưng lỗi lúc chạy?** Kiểu List có add; đối tượng wrapper không hỗ trợ thao tác sửa đó.
4. **Iterator từ wrapper có remove được nếu nguồn ArrayList sửa được không?** Không. Quyền xóa qua iterator của wrapper cũng bị chặn.
5. **Map.Entry từ entrySet của unmodifiableMap có setValue để sửa nguồn không?** Không qua đường được wrapper cung cấp.
6. **get(key).add trên một Map<String,List<String>> không cho put có thể thành công không?** Có, nếu List giá trị vẫn sửa được. Nó sửa đối tượng List, không gọi put trên Map.
7. **Bọc một LinkedHashSet có null có tự loại null không?** Không. Wrapper không tự lọc dữ liệu nguồn.
8. **Bọc một HashMap có tạo thứ tự khóa tăng dần không?** Không. Thứ tự vẫn theo hợp đồng nguồn.
9. **Sao chép List rồi bọc có làm StringBuilder phần tử được nhân bản không?** Không. Cấu trúc chứa riêng vẫn có thể giữ cùng tham chiếu phần tử.
10. **Unmodifiable có tự làm một phép duyệt an toàn khi luồng khác sửa nguồn không?** Không. Phải xét cơ chế truy cập của nguồn và cách phối hợp riêng.

### 12.2. Bài tập: so sánh view và bản sao chứa

Tạo ArrayList<String> chứa one,two. Tạo view bọc trực tiếp và một kết quả bọc ArrayList sao chép từ nguồn.

Thêm three qua nguồn. Kỳ vọng view nhìn one,two,three; kết quả chứa riêng vẫn one,two. Thử add qua cả hai kết quả và xác minh thao tác bị từ chối.

Thay kiểu phần tử thành StringBuilder rồi append qua kết quả chứa riêng. Giải thích vì sao kết quả có thể vẫn ảnh hưởng phần tử nguồn dù số vị trí đã độc lập.

### 12.3. Bài tập: bảo vệ đủ các đường Map

Tạo LinkedHashMap<String,Integer> có hai ánh xạ và bọc unmodifiableMap. Kiểm tra riêng put, remove, keySet.remove, values.remove và Entry.setValue từ entrySet.

Sau mỗi phép thử bị từ chối, đọc map nguồn để xác nhận ánh xạ không đổi. Các phép đọc get, containsKey và duyệt entry vẫn phải hoạt động theo dữ liệu nguồn.

Không thử những thao tác sai chỉ số hay một Entry ngoài vòng đời hợp lệ rồi quy mọi ngoại lệ cho wrapper.

### 12.4. Bài tập: thiết kế API trả Map của các List

Một lớp giữ Map<String,List<String>> chứa các nhóm quyền. Người nhận không được thêm/xóa nhóm, không được thêm/xóa quyền trong nhóm, và không được quan sát các sửa đổi về cấu trúc nguồn sau lúc nhận.

Thiết kế một kết quả có Map chứa riêng và các List giá trị riêng, bọc đúng hai lớp. Giữ rõ quyền sở hữu các cấu trúc mutable mới, rồi sửa nguồn cũ để kiểm tra kết quả không theo thay đổi đó.

Nếu thay String bằng một đối tượng Permission mutable, hãy nêu thêm trạng thái nào vẫn chưa được bảo vệ bởi chỉ sao chép và bọc các collection.

## 13. Nguồn đối chiếu và phạm vi kiểm chứng

- [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): hợp đồng ba wrapper unmodifiable, thao tác đọc dựa trên nguồn và thao tác sửa bị từ chối.
- [List — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): giao diện List, thao tác sửa, List.copyOf và giới hạn với phần tử mutable.
- [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): hợp đồng tập hợp, phần tử mutable, null và Set.copyOf.
- [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): collection view, thao tác cập nhật, khóa mutable và Map.copyOf.

Bốn chương trình đầy đủ đã biên dịch với `javac --release 17 -encoding UTF-8` và chạy trên Corretto JDK 17.0.15, cho đúng stdout được ghi. Ví dụ dùng LinkedHashSet/LinkedHashMap để cố định thứ tự duyệt cần in. Đoạn tạo ba kết quả ở phần lựa chọn view/bản sao là mã minh họa cần đặt trong ngữ cảnh có các biến nguồn và import phù hợp; nó không được trình bày như một tệp Java độc lập.
