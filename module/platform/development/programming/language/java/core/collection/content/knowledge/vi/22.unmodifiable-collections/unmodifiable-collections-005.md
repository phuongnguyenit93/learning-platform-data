# List.copyOf, Set.copyOf và Map.copyOf

## 1. Bắt đầu từ nhu cầu chốt dữ liệu để đọc

Một phương thức nhận danh sách cấu hình từ bên ngoài và lưu lại để dùng về sau. Nếu lưu thẳng tham chiếu đầu vào, bên gọi vẫn có thể thêm, xóa hoặc thay phần tử bằng biến họ đang giữ. Nếu chỉ đưa một lớp bọc chỉ đọc ra ngoài, việc sửa qua lớp bọc bị chặn, nhưng dữ liệu bên dưới vẫn có thể thay đổi qua nguồn. Khi yêu cầu là “giữ tập dữ liệu đã nhận, không đi theo các lần sửa cấu trúc sau đó của nguồn”, cần một ranh giới mạnh hơn.

Ba phương thức tạo tĩnh (static factory) `List.copyOf`, `Set.copyOf` và `Map.copyOf` phục vụ ranh giới này. Chúng nhận một collection hoặc map đã có và trả về kết quả không cho phép sửa cấu trúc qua API của kết quả. Nguồn vẫn có thể sửa được nếu chính kiểu nguồn hỗ trợ; việc nguồn thêm/xóa/thay tham chiếu phần tử hoặc thêm/xóa/thay ánh xạ sau khi sao chép không làm thay đổi phần chứa của kết quả.

Có thể gọi kết quả là **ảnh chụp cấu trúc**: chốt những tham chiếu phần tử, hoặc những liên kết khóa–giá trị, được lấy từ đầu vào. Cách gọi này giúp tách hai câu hỏi:

- Collection kết quả chứa những phần tử nào, theo thứ tự nào nếu có?
- Các đối tượng mà collection đang tham chiếu có còn tự thay đổi được hay không?

`copyOf` giải quyết câu hỏi thứ nhất theo hợp đồng của List, Set hoặc Map. Nó không tự sao chép toàn bộ trạng thái bên trong từng đối tượng để giải quyết câu hỏi thứ hai.

Ví dụ, danh sách chứa `String` thường dễ dùng làm dữ liệu ổn định vì `String` là bất biến. Danh sách chứa `StringBuilder` vẫn có thể hiển thị văn bản khác khi một builder được sửa. Cả hai danh sách đều có thể không hỗ trợ `add`, `remove` và `set`; điểm khác biệt nằm ở đối tượng phần tử.

Bài này đi theo thứ tự: phân biệt ba hình dạng dữ liệu; hiểu quy tắc null, trùng lặp và thứ tự; kiểm chứng từng factory; sau đó xác định mức bảo vệ cần có khi dùng trong hàm khởi tạo hoặc kết quả trả về. Người học cần biết collection có thể chứa tham chiếu đến đối tượng và nắm các thao tác cơ bản của `ArrayList`, `Set`, `Map`.

## 2. Ba chữ ký, ba ý nghĩa sao chép

Các phương thức `copyOf` này có từ Java 10. Toàn bộ chương trình trong bài dùng Java 17, được lưu thành từng tệp độc lập theo tên lớp `public`. Các lệnh `javac --release 17` và `java` cần chạy bằng JDK 17 hoặc mới hơn phù hợp.

| Lời gọi | Đầu vào | Kiểu kết quả | Điều được giữ |
| --- | --- | --- | --- |
| `List.copyOf(collection)` | `Collection<? extends E>` | `List<E>` | Phần tử theo thứ tự duyệt đầu vào, gồm cả phần tử lặp |
| `Set.copyOf(collection)` | `Collection<? extends E>` | `Set<E>` | Mỗi giá trị phân biệt theo ngữ nghĩa tập hợp, không có bảo đảm thứ tự duyệt |
| `Map.copyOf(map)` | `Map<? extends K, ? extends V>` | `Map<K, V>` | Các ánh xạ khóa–giá trị, không có bảo đảm thứ tự duyệt |

`List.copyOf` không chỉ nhận một List: một Set cũng là Collection. Tuy vậy, kết quả List chỉ chốt thứ tự mà nguồn đã cung cấp lúc duyệt. Nó không tự biến một nguồn không có thứ tự được bảo đảm thành quy tắc sắp xếp có ý nghĩa cho nghiệp vụ.

`Set.copyOf` cũng nhận được List. Đây là điểm hữu ích khi cần chuyển từ dữ liệu có thể lặp sang một tập hợp chỉ đọc. Việc loại trùng là một lựa chọn mô hình dữ liệu: số lần xuất hiện không còn được biểu diễn trong kết quả. Nếu tần suất quan trọng, không dùng Set để thay cho danh sách đầu vào.

`Map.copyOf` nhận Map vì nó cần quan hệ giữa khóa và giá trị. Một danh sách các giá trị riêng lẻ không đủ thông tin để suy ra khóa; một danh sách các cặp có thể lặp khóa còn cần quy tắc xử lý xung đột trước khi tạo Map.

Phân biệt `of` và `copyOf`: `List.of("A", "B")` tạo dữ liệu từ các đối số phần tử; `List.copyOf(existing)` lấy phần tử từ một Collection đã có. Nếu `existing` là một List, `List.of(existing)` tạo danh sách có một phần tử là chính List đó, không trải các phần tử bên trong. Không thay hai lời gọi cho nhau chỉ vì chúng cùng trả về List chỉ đọc.

Tài liệu API gốc mô tả chữ ký và phiên bản của từng phương thức: [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), [Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)), [Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)).

## 3. List.copyOf: giữ thứ tự, giữ phần tử lặp, chặn thay thế

Đối với danh sách, vị trí là một phần của dữ liệu. Từ nguồn có thứ tự `[A, B, A]`, kết quả phải biểu diễn ba vị trí đó theo đúng thứ tự nguồn đã duyệt. Hai lần xuất hiện của `A` không bị gộp; `size()` vẫn bằng ba.

Sau khi có kết quả, ba loại sửa đều bị chặn:

- Thêm phần tử làm tăng số vị trí.
- Xóa phần tử làm giảm số vị trí.
- Thay phần tử ở một vị trí bằng `set`, dù kích thước không đổi.

Điểm cuối phân biệt danh sách không sửa được với danh sách chỉ cố định kích thước. Một List không hỗ trợ thêm/xóa chưa chắc đã cấm `set`. Đừng dùng việc `add` ném ngoại lệ làm bằng chứng rằng mọi List khác cũng có hợp đồng giống `List.copyOf`.

Giả sử `source` là `ArrayList` và đã được chép sang `snapshot`. Lời gọi `source.set(0, "Z")` thay tham chiếu mà nguồn lưu ở vị trí đầu; nó không thay tham chiếu đang được kết quả lưu ở vị trí tương ứng. Tương tự, `source.add("C")` không thêm phần tử vào kết quả. Đây là sự độc lập của cấu trúc chứa.

Nếu phần tử đầu là một đối tượng có thể sửa, lời gọi một phương thức sửa trên đối tượng đó là chuyện khác. `source.get(0).append(...)` không thay vị trí hay tham chiếu của nguồn; nó sửa chính đối tượng đang được cả hai bên giữ. Phần 9 và 10 sẽ kiểm chứng ranh giới này.

Đầu vào List không được null, và không được có phần tử null. List rỗng hợp lệ: một danh sách không chứa phần tử khác với việc không có đối tượng List nào.

## 4. Thí nghiệm List: ảnh chụp và lớp bọc chỉ đọc

Lưu chương trình thành `ListCopyOfDemo.java`. Chương trình tạo một nguồn, một lớp bọc chỉ đọc của nguồn và hai ảnh chụp: một từ nguồn, một từ chính lớp bọc. Việc lấy ảnh chụp từ lớp bọc vẫn phải cho kết quả độc lập với thay đổi cấu trúc về sau của dữ liệu bên dưới.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListCopyOfDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        List<String> snapshotFromView = List.copyOf(view);

        source.set(0, "Z");
        source.add("C");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);
        System.out.println("snapshotFromView=" + snapshotFromView);
        System.out.println("emptySize=" + List.copyOf(List.of()).size());

        try {
            snapshot.set(0, "X");
        } catch (UnsupportedOperationException e) {
            System.out.println("set=UnsupportedOperationException");
        }

        List<String> withNull = new ArrayList<>();
        withNull.add(null);
        try {
            List.copyOf(withNull);
        } catch (NullPointerException e) {
            System.out.println("nullElement=NullPointerException");
        }

        try {
            List.<String>copyOf(null);
        } catch (NullPointerException e) {
            System.out.println("nullSource=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ListCopyOfDemo.java
java ListCopyOfDemo
```

Stdout:

```text
source=[Z, B, A, C]
view=[Z, B, A, C]
snapshot=[A, B, A]
snapshotFromView=[A, B, A]
emptySize=0
set=UnsupportedOperationException
nullElement=NullPointerException
nullSource=NullPointerException
```

Đọc kết quả theo ba thời điểm. Ban đầu, cả nguồn và các kết quả đều nhìn thấy `A, B, A`. Hai lời gọi sửa được thực hiện trên `source` sau khi cả hai ảnh chụp đã tạo xong. Khi in, nguồn và `view` cùng hiện `Z, B, A, C`, còn hai ảnh chụp vẫn hiện `A, B, A`.

Dòng `snapshotFromView` tránh một hiểu nhầm thường gặp: “đầu vào đã chỉ đọc thì cứ trả lại nó”. Một lớp bọc đang đọc xuyên qua nguồn có thể tiếp tục thay đổi phần nội dung quan sát được. Kết quả của `copyOf` phải đáp ứng hợp đồng chốt cấu trúc, dù đầu vào được truyền qua biến có giao diện chỉ đọc.

Lời gọi `snapshot.set(0, "X")` bị chặn ngay cả khi không làm thay đổi kích thước. Hai ca null được chuẩn bị riêng để xác định đúng nơi lỗi xảy ra: `ArrayList` trong ví dụ cho phép thêm null; ngoại lệ được quan sát ở `List.copyOf(withNull)`. Nếu dùng một factory vốn đã cấm null để chuẩn bị dữ liệu, chương trình có thể lỗi trước khi thực sự đi đến `copyOf`.

Phần bắt ngoại lệ chỉ giúp thí nghiệm chạy tiếp để quan sát nhiều ca. Trong thiết kế API thật, nên công bố điều kiện đầu vào và xử lý dữ liệu không hợp lệ ở ranh giới thích hợp; không dùng ngoại lệ như cách suy đoán ngẫu nhiên khả năng của mọi List.

## 5. Set.copyOf: loại trùng là thay đổi ý nghĩa dữ liệu

Một Set trả lời câu hỏi “giá trị này có xuất hiện không?”, không lưu số lần xuất hiện như List. Nếu nguồn có `beta, alpha, beta`, tập hợp kết quả có hai giá trị phân biệt. Đây là hành vi bình thường của `Set.copyOf`, không phải lỗi dữ liệu trùng.

Cần phân biệt rõ với `Set.of`. Truyền hai phần tử bằng nhau vào `Set.of` gây `IllegalArgumentException`, còn `Set.copyOf` nhận Collection có phần tử trùng và giữ lại một đại diện trong nhóm các phần tử bằng nhau. Không suy từ tên “factory chỉ đọc” rằng mọi factory xử lý đầu vào trùng theo cùng một cách.

Nếu hai đối tượng được `equals` xem là bằng nhau nhưng chứa thêm thông tin khác, không dựa vào việc đại diện giữ lại là đối tượng đầu tiên hay cuối cùng. Ví dụ, hai đối tượng mã hàng cùng mã định danh nhưng khác phần mô tả có thể được xem là bằng nhau theo quy tắc lớp. Nếu cần chọn mô tả mới nhất, phải xử lý quy tắc đó trước; `Set.copyOf` không là công cụ chọn bản ghi thắng theo thời gian.

Kết quả không cam kết thứ tự chèn hay thứ tự sắp xếp của nguồn. Một nguồn `LinkedHashSet` có thứ tự riêng hoặc `TreeSet` có bộ so sánh riêng không biến kết quả `Set.copyOf` thành loại tập hợp chuyên biệt tương ứng.

Trong thí nghiệm tiếp theo, việc in thông qua `new TreeSet<>(snapshot)` chỉ tạo một cách trình bày theo thứ tự chữ để stdout dễ kiểm tra. Nó không chứng minh `snapshot` tự có thứ tự đó. Khi so sánh tập hợp trong kiểm tra chương trình, hãy kiểm tra phần tử và quan hệ bằng nhau; chỉ kiểm tra thứ tự khi API đã cam kết thứ tự.

## 6. Thí nghiệm Set: loại trùng và quy tắc đầu vào

Lưu thành `SetCopyOfDemo.java`. Nguồn được cố ý chọn là List để số lần lặp còn quan sát được trước khi chuyển sang Set.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SetCopyOfDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("beta", "alpha", "beta"));
        Set<String> snapshot = Set.copyOf(source);

        System.out.println("sourceSize=" + source.size());
        System.out.println("snapshotSize=" + snapshot.size());
        System.out.println("snapshotForDisplay=" + new TreeSet<>(snapshot));

        source.clear();
        source.add("gamma");
        System.out.println("sourceNow=" + source);
        System.out.println("snapshotAfterChange=" + new TreeSet<>(snapshot));

        try {
            snapshot.add("delta");
        } catch (UnsupportedOperationException e) {
            System.out.println("add=UnsupportedOperationException");
        }

        try {
            Set.of("beta", "beta");
        } catch (IllegalArgumentException e) {
            System.out.println("ofDuplicate=IllegalArgumentException");
        }

        List<String> withNull = new ArrayList<>();
        withNull.add("alpha");
        withNull.add(null);
        try {
            Set.copyOf(withNull);
        } catch (NullPointerException e) {
            System.out.println("nullElement=NullPointerException");
        }

        try {
            Set.<String>copyOf(null);
        } catch (NullPointerException e) {
            System.out.println("nullSource=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SetCopyOfDemo.java
java SetCopyOfDemo
```

Stdout:

```text
sourceSize=3
snapshotSize=2
snapshotForDisplay=[alpha, beta]
sourceNow=[gamma]
snapshotAfterChange=[alpha, beta]
add=UnsupportedOperationException
ofDuplicate=IllegalArgumentException
nullElement=NullPointerException
nullSource=NullPointerException
```

`sourceSize=3` và `snapshotSize=2` là bằng chứng về việc đổi hình dạng dữ liệu. Sau `source.clear()` và `source.add("gamma")`, kết quả vẫn chứa `alpha` và `beta`; việc nguồn đổi không làm tập kết quả đi theo.

Lời gọi `snapshot.add("delta")` cố thêm một giá trị mới nên minh họa trực tiếp việc chặn sửa. Ca `Set.of("beta", "beta")` được tách riêng và in tên khác để tránh gán ngoại lệ của `of` cho `copyOf`.

Với dữ liệu null, Set không có chính sách “bỏ qua phần tử không hợp lệ”. Cả null trong Collection và null thay cho chính Collection đều gây lỗi. Nếu yêu cầu nghiệp vụ là loại bỏ null, đó phải là bước chuẩn hóa có chủ đích trước khi gọi factory, và cần xác định liệu loại bỏ có làm mất thông tin quan trọng hay không.

Phần in đã dùng cách sắp xếp riêng. Không bỏ `TreeSet` rồi tiếp tục đòi stdout thô của Set phải đúng `[alpha, beta]` trên mọi lần chạy hoặc mọi JDK.

## 7. Map.copyOf: chốt liên kết khóa–giá trị

Đối với Map, phải bảo vệ cả tập khóa lẫn giá trị được gắn với từng khóa. Nếu nguồn ban đầu chứa `alpha -> 1` và `beta -> 2`, rồi nguồn đổi `beta` sang `20`, kết quả đã tạo vẫn gắn `beta` với `2`. Một khóa mới được thêm vào nguồn cũng không tự xuất hiện trong kết quả.

Không thể sửa Map kết quả bằng `put`, `remove`, `replace` hoặc các phương thức thay đổi ánh xạ khác. Các đường đi gián tiếp qua `keySet`, `values`, `entrySet` cũng không là lối vòng để thay đổi Map. Trong thí nghiệm, việc xóa khóa qua `keySet` và gọi `setValue` trên một Entry đều bị chặn.

Cần đọc chính xác “không sửa giá trị qua Map”. Nếu một giá trị là List, việc thay List được gắn với khóa là thay ánh xạ của Map. Gọi `add` trên List đã lấy ra lại là sửa đối tượng giá trị. Hai thao tác này thuộc hai đối tượng khác nhau; Map chỉ đọc không tự biến List bên trong thành List chỉ đọc.

Map kết quả không nhận khóa null hoặc giá trị null. Quy tắc của nguồn có thể rộng hơn: một `HashMap` dùng làm nguồn vẫn có thể cho phép các dữ liệu ấy, nhưng không vì thế mà việc chuyển sang `Map.copyOf` hợp lệ.

`Map.copyOf` cũng không mang theo thứ tự duyệt của `LinkedHashMap` hay bộ so sánh của `TreeMap` như một cam kết của kết quả. Nếu báo cáo cần thứ tự khóa, hãy xây dựng rõ một bước trình bày theo thứ tự. Nếu chính API cần các thao tác của `SortedMap` hoặc `NavigableMap`, kiểu `Map` trả về từ factory không thay thế được hợp đồng đó.

Với nguồn Map thông thường có quy tắc khóa nhất quán với `equals`, mỗi khóa đã có tối đa một ánh xạ. Khi đưa dữ liệu thô có nhiều bản ghi cùng khóa vào Map, quyết định giữ bản nào xảy ra ở bước xây dựng Map nguồn. `Map.copyOf` không nhận một hàm gộp và không tự suy ra chính sách “mới nhất thắng”.

## 8. Thí nghiệm Map: nguồn thay đổi, kết quả giữ ánh xạ cũ

Lưu thành `MapCopyOfDemo.java`. `TreeMap` trong các dòng in chỉ được dùng để định thứ tự hiển thị; nó không là kiểu thực tế được yêu cầu từ `Map.copyOf`.

```java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public class MapCopyOfDemo {
    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("beta", 2);
        source.put("alpha", 1);
        Map<String, Integer> snapshot = Map.copyOf(source);

        source.put("beta", 20);
        source.put("gamma", 3);
        System.out.println("sourceForDisplay=" + new TreeMap<>(source));
        System.out.println("snapshotForDisplay=" + new TreeMap<>(snapshot));
        System.out.println("oldBeta=" + snapshot.get("beta"));

        try {
            snapshot.put("delta", 4);
        } catch (UnsupportedOperationException e) {
            System.out.println("put=UnsupportedOperationException");
        }

        try {
            snapshot.keySet().remove("alpha");
        } catch (UnsupportedOperationException e) {
            System.out.println("keySetRemove=UnsupportedOperationException");
        }

        try {
            snapshot.entrySet().iterator().next().setValue(99);
        } catch (UnsupportedOperationException e) {
            System.out.println("entrySetValue=UnsupportedOperationException");
        }

        Map<String, Integer> nullKey = new HashMap<>();
        nullKey.put(null, 1);
        try {
            Map.copyOf(nullKey);
        } catch (NullPointerException e) {
            System.out.println("nullKey=NullPointerException");
        }

        Map<String, Integer> nullValue = new HashMap<>();
        nullValue.put("alpha", null);
        try {
            Map.copyOf(nullValue);
        } catch (NullPointerException e) {
            System.out.println("nullValue=NullPointerException");
        }

        try {
            Map.<String, Integer>copyOf(null);
        } catch (NullPointerException e) {
            System.out.println("nullSource=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 MapCopyOfDemo.java
java MapCopyOfDemo
```

Stdout:

```text
sourceForDisplay={alpha=1, beta=20, gamma=3}
snapshotForDisplay={alpha=1, beta=2}
oldBeta=2
put=UnsupportedOperationException
keySetRemove=UnsupportedOperationException
entrySetValue=UnsupportedOperationException
nullKey=NullPointerException
nullValue=NullPointerException
nullSource=NullPointerException
```

Sau khi nguồn thay giá trị của `beta` và thêm `gamma`, bản trình bày nguồn hiện `beta=20` cùng khóa mới. Bản trình bày kết quả vẫn hiện `beta=2` và không có `gamma`. Dòng `oldBeta=2` kiểm tra trực tiếp ánh xạ nên không phụ thuộc thứ tự duyệt.

Ba ca sửa đi qua ba đường khác nhau:

| Đường gọi | Đối tượng nhận thao tác | Điều bị yêu cầu thay đổi |
| --- | --- | --- |
| `snapshot.put(...)` | Map kết quả | Thêm một ánh xạ |
| `snapshot.keySet().remove(...)` | View tập khóa | Xóa ánh xạ mang khóa tương ứng |
| `snapshot.entrySet().iterator().next().setValue(...)` | Entry lấy từ kết quả | Thay giá trị trong một ánh xạ |

Cả ba đều bị từ chối. Ca Entry không cần dự đoán khóa nào xuất hiện đầu tiên: tất cả Entry được lấy từ kết quả này đều không cho phép thay giá trị qua `setValue`.

Hai nguồn có null được tạo riêng bằng `HashMap`, mỗi nguồn chỉ kiểm tra một loại vi phạm. Bằng cách đó, `nullKey` và `nullValue` trong stdout chỉ ra đúng điều kiện đang được kiểm tra. Ca null cho cả Map là điều kiện thứ ba, độc lập với khóa và giá trị.

Đọc một Map chỉ đọc vẫn có thể trả ra đối tượng có thể sửa. Trong ví dụ này các khóa là `String`, giá trị là `Integer`, nên không có phép sửa trạng thái bên trong chúng như với một List giá trị. Cần xem kiểu dữ liệu thực tế trước khi kết luận về mức độ bất biến.

## 9. Giới hạn sao chép nông và quyền sở hữu dữ liệu

“Sao chép nông” nghĩa là tạo ranh giới ở phần chứa nhưng vẫn giữ những tham chiếu đối tượng đã lấy từ nguồn. Ba factory không biết cách tạo một bản sao độc lập cho mọi lớp do ứng dụng định nghĩa. Không có một quy tắc chung đúng cho mọi đồ thị đối tượng, kết nối tài nguyên hoặc mối liên hệ giữa các đối tượng.

Có thể hình dung một List có hai tầng:

1. Tầng danh sách: các vị trí và tham chiếu được lưu ở từng vị trí.
2. Tầng phần tử: trạng thái bên trong các đối tượng mà các tham chiếu trỏ đến.

`List.copyOf` bảo vệ tầng danh sách trong kết quả. Để bảo vệ tầng phần tử, cần đối tượng bất biến hoặc một chính sách chuyển đổi/sao chép phù hợp. Nếu phần tử lại là collection, phải quyết định bảo vệ thêm tầng đó.

Map có thêm sự phân biệt giữa khóa và giá trị. `Map.copyOf` chốt các cặp tham chiếu khóa–giá trị. Nó không gọi một thao tác “sao chép sâu” lên từng khóa hay giá trị. Một `Map<String, List<String>>` có thể không cho phép đổi List gắn với khóa nhưng vẫn cho phép sửa List đang được gắn, nếu List ấy vốn là `ArrayList`.

Với Set và khóa Map, đối tượng có thể sửa còn liên quan đến ngữ nghĩa nhận diện. Nếu thay đổi trạng thái tham gia `equals` hoặc `hashCode` sau khi đưa vào tập hợp hoặc làm khóa, có thể vi phạm điều kiện sử dụng của cấu trúc. Không dùng việc “collection ngoài chỉ đọc” để suy ra rằng sửa các trường ấy là an toàn. Chọn khóa và phần tử có ngữ nghĩa bằng nhau ổn định trong suốt thời gian sử dụng.

Không phải lúc nào cũng cần sao chép sâu. Một cấu hình gồm `Map<String, List<String>>` có thể được bảo vệ đủ bằng cách chụp từng List bên trong rồi chụp Map bên ngoài, vì String không có trạng thái sửa được. Với `Map<String, List<Customer>>`, cách đó vẫn giữ cùng các Customer. Phải xác định chính xác tầng dữ liệu nào cần độc lập.

“Quyền sở hữu” trong ngữ cảnh này là quy ước ai được giữ và sửa dữ liệu nào. `copyOf` giúp một đối tượng tiếp nhận collection đầu vào mà không tiếp tục trao quyền sửa danh sách hay ánh xạ nội bộ cho bên truyền vào. Nó không tự thu hồi mọi tham chiếu đến các đối tượng phần tử mà bên ngoài đã giữ.

## 10. Thí nghiệm quyền sở hữu: phần tử chung, collection lồng và hàm khởi tạo

Lưu thành `CopyOfOwnershipDemo.java`. Chương trình gồm ba ca độc lập:

- List chứa builder cho thấy tham chiếu phần tử vẫn dùng chung.
- Map chứa List cho thấy khác biệt giữa chụp Map ngoài và chụp thêm các List trong.
- `Catalog` tiếp nhận List tên để giữ cấu hình riêng, không đi theo việc bên gọi thêm tên vào đầu vào.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CopyOfOwnershipDemo {
    static final class Catalog {
        private final List<String> names;

        Catalog(Collection<String> input) {
            names = List.copyOf(input);
        }

        List<String> names() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<StringBuilder> source =
                new ArrayList<>(List.of(new StringBuilder("draft")));
        List<StringBuilder> shallow = List.copyOf(source);
        source.get(0).append("-edited");
        System.out.println("sameElement=" + (source.get(0) == shallow.get(0)));
        System.out.println("shallowText=" + shallow.get(0));

        List<String> permissions = new ArrayList<>(List.of("read"));
        Map<String, List<String>> sourceMap = new HashMap<>();
        sourceMap.put("admin", permissions);
        Map<String, List<String>> outerOnly = Map.copyOf(sourceMap);

        Map<String, List<String>> staged = new HashMap<>();
        sourceMap.forEach((key, value) -> staged.put(key, List.copyOf(value)));
        Map<String, List<String>> nestedSnapshot = Map.copyOf(staged);

        permissions.add("write");
        System.out.println("outerOnly=" + outerOnly.get("admin"));
        System.out.println("nestedSnapshot=" + nestedSnapshot.get("admin"));
        sourceMap.put("admin", new ArrayList<>(List.of("replacement")));
        System.out.println("sourceMapping=" + sourceMap.get("admin"));
        System.out.println("oldMapping=" + outerOnly.get("admin"));

        List<String> input = new ArrayList<>(List.of("Java"));
        Catalog catalog = new Catalog(input);
        input.add("SQL");
        System.out.println("catalogNames=" + catalog.names());
        try {
            catalog.names().add("HTTP");
        } catch (UnsupportedOperationException e) {
            System.out.println("catalogAdd=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CopyOfOwnershipDemo.java
java CopyOfOwnershipDemo
```

Stdout:

```text
sameElement=true
shallowText=draft-edited
outerOnly=[read, write]
nestedSnapshot=[read]
sourceMapping=[replacement]
oldMapping=[read, write]
catalogNames=[Java]
catalogAdd=UnsupportedOperationException
```

Dòng `sameElement=true` so sánh hai tham chiếu phần tử, không so sánh định danh của hai collection. `shallowText=draft-edited` xuất hiện vì cả nguồn lẫn kết quả giữ cùng builder. Không có `add` hay `set` nào được thực hiện trên `shallow`.

Ở ca Map lồng, hai kết quả được tạo khi danh sách quyền mới chỉ chứa `read`. Sau đó `permissions.add("write")` sửa List cũ:

- `outerOnly` vẫn giữ tham chiếu đến List cũ ấy, nên đọc được `[read, write]`.
- `nestedSnapshot` giữ List chỉ đọc đã chụp trước đó, nên đọc được `[read]`.

Tiếp theo, nguồn thay toàn bộ List được gắn với khóa `admin` bằng một List khác chứa `replacement`. `outerOnly` không theo ánh xạ mới; nó tiếp tục giữ List cũ `[read, write]`. Hai dòng `sourceMapping` và `oldMapping` cho thấy đồng thời hai tính chất: ánh xạ đã được chốt, còn đối tượng giá trị cũ thì vẫn có thể từng bị sửa.

Biến `staged` là một Map tạm để thu các List đã chụp. Sau khi hoàn tất bước chuẩn bị, `Map.copyOf(staged)` chốt lớp ngoài. Đây là quy trình hai tầng cụ thể cho kiểu dữ liệu trong ví dụ, không phải thuật toán sao chép sâu dùng được cho mọi loại đối tượng.

Với `Catalog`, trường `names` là `final`, nhưng chính `List.copyOf(input)` mới tách danh sách nội bộ khỏi các thay đổi danh sách đầu vào. Nếu chỉ gán `names = input`, từ khóa `final` vẫn không ngăn `input.add("SQL")` sửa nội dung danh sách mà đối tượng đang giữ.

Hàm `names()` có thể trả lại trường `names` trong thiết kế này vì collection đã chốt và các phần tử String là bất biến. Không cần tạo một ảnh chụp mới ở mỗi lần đọc chỉ để chống thao tác thêm/xóa từ bên gọi. Nếu sau này thay kiểu phần tử bằng đối tượng có thể sửa, phải đánh giá lại hợp đồng trả về; giữ nguyên tên phương thức không giữ nguyên mức độ bảo vệ.

## 11. Bằng nhau về dữ liệu không đồng nghĩa với cùng đối tượng

Tên `copyOf` không hứa rằng mỗi lời gọi đều cấp phát một collection mới có định danh khác. Khi đầu vào đã đáp ứng điều kiện thích hợp, triển khai có thể tận dụng một kết quả chỉ đọc đã có. Tối ưu này không làm thay đổi hợp đồng quan sát được về dữ liệu.

Vì vậy, không thiết kế mã dựa trên hai suy luận sau:

- “Đã gọi copy thì `result != input` chắc chắn đúng.”
- “Đầu vào chỉ đọc thì `result == input` chắc chắn đúng.”

Khi muốn kiểm tra dữ liệu, dùng ngữ nghĩa phù hợp: List xét phần tử và thứ tự, Set xét tập phần tử, Map xét các ánh xạ. Khi muốn kiểm tra việc tách khỏi nguồn, sửa nguồn theo hợp đồng cho phép rồi quan sát kết quả. Hai chương trình đầu đã làm điều đó mà không cần biết tên lớp triển khai của kết quả.

Các kết quả factory là đối tượng dựa trên giá trị: không chọn chúng làm đối tượng khóa đồng bộ hóa hay dựa vào định danh để điều khiển nghiệp vụ. Dùng một đối tượng khóa riêng khi thiết kế thực sự cần đồng bộ hóa, với cơ chế quản lý rõ ràng.

Điểm này cũng giải thích tại sao không ép kiểu kết quả thành `ArrayList`, `HashSet` hoặc `HashMap`. Factory cung cấp giao diện được công bố, không cung cấp lời hứa rằng tên implementation tương ứng với tên cấu trúc nguồn. Sửa mã bằng cách bỏ ép kiểu và lập trình theo hợp đồng cần dùng; nếu cần một bản sao có thể sửa, chủ động tạo kiểu có thể sửa.

Không suy từ việc có thể tái sử dụng sang kết luận rằng `copyOf` luôn rẻ hoặc luôn không cấp phát. Với nguồn có thể sửa, việc tạo dữ liệu độc lập có thể cần duyệt nguồn và giữ các tham chiếu riêng. Dùng phép đo với dữ liệu thực tế khi chi phí sao chép ảnh hưởng đến đường chạy quan trọng; không đặt giả định định danh vào thuật toán.

## 12. Chọn công cụ theo quyền sửa và mức phụ thuộc nguồn

Trước khi chọn phương thức, mô tả hợp đồng bằng một câu cụ thể: “người nhận được sửa không?”, “nguồn sửa thì kết quả có đi theo không?”, “đối tượng phần tử có được dùng chung không?”. Một từ “bất biến” đứng riêng thường chưa đủ để trả lời cả ba.

| Nhu cầu | Hướng lựa chọn | Điều còn phải xem |
| --- | --- | --- |
| Bên nhận được sửa một List riêng | `new ArrayList<>(source)` | Phần tử vẫn có thể dùng chung |
| Bên nhận chỉ được đọc và cần thấy thay đổi từ List nguồn | `Collections.unmodifiableList(source)` | Nguồn bên dưới vẫn có thể thay đổi |
| Bên nhận chỉ đọc một danh sách đã chốt | `List.copyOf(source)` | Không nhận null; không sao chép sâu |
| Bên nhận chỉ cần các giá trị phân biệt đã chốt | `Set.copyOf(source)` | Mất số lần lặp; không cam kết thứ tự |
| Bên nhận chỉ đọc các ánh xạ đã chốt | `Map.copyOf(source)` | Không nhận khóa/giá trị null; giá trị bên trong có thể sửa |
| Bên nhận cần thứ tự hoặc giao diện chuyên biệt | Chọn cấu trúc và lớp bọc phù hợp với hợp đồng đó | Phải nêu rõ việc có tiếp tục phụ thuộc nguồn hay không |

Bảng dùng List để minh họa khác biệt giữa constructor sao chép, lớp bọc và factory. Với Set và Map, cũng cần phân biệt khả năng sửa và quan hệ với nguồn; không lựa chọn chỉ dựa trên việc tên phương thức có chữ `copy` hay `unmodifiable`.

Lớp bọc có thể rất phù hợp nếu mục tiêu là cung cấp một cửa sổ đọc vào dữ liệu đang được chủ sở hữu quản lý. `copyOf` phù hợp khi muốn phát hành một tập dữ liệu đã chốt cho người nhận. Đây là hai hợp đồng khác nhau mà một thiết kế có thể cần ở các vị trí khác nhau.

Nếu cần một List kết quả có thể sửa tiếp, không thử sửa `List.copyOf` rồi bắt ngoại lệ để chuyển hướng. Tạo thẳng bản sao có thể sửa. Nếu cần sắp xếp rồi phát hành chỉ đọc, thực hiện bước sắp xếp trên dữ liệu có thể sửa trước khi chụp kết quả; không gọi thao tác sắp xếp trên List đã chốt và kỳ vọng factory sẽ tự chuyển chế độ.

Nếu cần bảo toàn thứ tự chèn của tập hợp hoặc map như một phần API, không dùng Set/Map `copyOf` để hứa thứ tự đó. Có thể chuẩn bị một cấu trúc riêng có thứ tự rồi bọc chỉ đọc, với điều kiện không còn đường sửa nguồn làm thay đổi dữ liệu đã công bố. Cách chuẩn bị phải phản ánh đúng hợp đồng của ứng dụng, không chỉ đúng hình thức tên lớp.

Đối chiếu mô tả việc truy vấn đọc xuyên qua nguồn của lớp bọc trong [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) để thấy rõ vì sao một view chỉ đọc vẫn khác một tập dữ liệu đã chốt.

## 13. Null, dữ liệu rỗng và trách nhiệm kiểm tra

Ba factory đều nhận dữ liệu rỗng hợp lệ. List rỗng, Set rỗng và Map rỗng vẫn là đối tượng có hợp đồng rõ ràng. Việc có cho phép “không có dữ liệu” trong nghiệp vụ không nhất thiết phải biểu diễn bằng null.

| Trường hợp | List.copyOf | Set.copyOf | Map.copyOf |
| --- | --- | --- | --- |
| Chính đối tượng đầu vào là null | `NullPointerException` | `NullPointerException` | `NullPointerException` |
| Đầu vào rỗng hợp lệ | Chấp nhận | Chấp nhận | Chấp nhận |
| Có phần tử null | `NullPointerException` | `NullPointerException` | Xem riêng khóa và giá trị |
| Có khóa null | Không áp dụng | Không áp dụng | `NullPointerException` |
| Có giá trị null | Không áp dụng | Không áp dụng | `NullPointerException` |

Quy tắc null của factory là một điều kiện kỹ thuật. Quy tắc nghiệp vụ có thể mạnh hơn: chuỗi không được rỗng, mã phải tồn tại, danh sách không được vượt giới hạn, hoặc một người dùng không được có quyền trùng. `copyOf` không thay thế những kiểm tra ấy.

Ví dụ, `Set.copyOf` có thể loại trùng thành công, nhưng điều đó không có nghĩa dữ liệu trùng luôn được chấp nhận trong nghiệp vụ. Nếu yêu cầu là báo lỗi khi nhập lặp quyền, chuyển sang Set mà không kiểm tra có thể che giấu lỗi đầu vào. Nếu yêu cầu là tập quyền duy nhất, loại trùng lại có thể đúng. Mô tả mục tiêu trước rồi mới dùng cơ chế.

Ngược lại, không nên âm thầm chuyển mọi null đầu vào thành một collection rỗng nếu hai trạng thái mang ý nghĩa khác nhau. “Không có mục nào” và “bên gọi quên cung cấp dữ liệu” có thể cần cách xử lý khác. Đặt quy tắc này ở API tiếp nhận để người gọi hiểu trách nhiệm của mình.

Khi factory ném ngoại lệ trong ví dụ, việc thực thi thoát khỏi lời gọi đó; không có một kết quả “sao chép một phần” được trả cho biến nhận. Những chương trình trên chỉ bắt loại ngoại lệ dự kiến để quan sát từng trường hợp, không biến null thành dữ liệu hợp lệ.

## 14. Dùng copyOf ở ranh giới đối tượng và kết quả trả về

Một quy trình thường dễ đọc là: tiếp nhận dữ liệu; chuẩn hóa hoặc kiểm tra theo yêu cầu; dựng dữ liệu trung gian nếu cần; chốt collection; công bố kết quả. Đặt bước chốt ở nơi quyền sở hữu thay đổi giúp người đọc biết bên nào còn được quyền sửa phần chứa.

Trong hàm khởi tạo, `Catalog` ở phần 10 là một ví dụ nhỏ. Đối tượng không muốn cấu hình thay đổi chỉ vì bên gọi tiếp tục sửa List họ truyền vào. Việc chụp đầu vào ngay tại thời điểm tiếp nhận tạo một ranh giới dễ kiểm chứng. Trường `final` sau đó diễn tả rằng chính tham chiếu trường không được gán lại.

Ở phương thức trả về, có hai tình huống:

- Đối tượng đã giữ sẵn một collection chốt và mức bảo vệ phần tử phù hợp. Có thể trả kết quả đã có, như `Catalog.names()`.
- Đối tượng đang quản lý dữ liệu thay đổi, còn người gọi cần một kết quả riêng cho lần yêu cầu hiện tại. Chụp dữ liệu tại ranh giới trả về, với chính sách phần tử phù hợp.

Không dùng một tên phương thức như `getItems` để mặc định rằng cả hai tình huống có cùng hành vi. Tài liệu hợp đồng nên nói rõ người nhận có thấy các thay đổi về sau của chủ sở hữu hay không.

Với map lồng, hãy kiểm tra cả đầu vào và đường truy cập đầu ra. Chụp Map ngoài nhưng trả List giá trị có thể sửa vẫn cho người nhận quyền sửa List đó. Nếu mục tiêu là cấu hình chỉ đọc hai tầng, cần chụp từng List, sau đó chụp Map; nếu phần tử List là đối tượng có thể sửa, tiếp tục đánh giá tầng ấy.

Ảnh chụp cấu trúc không tự cung cấp một giao thức đồng bộ hóa với luồng đang ghi nguồn. Chỉ riêng lời gọi `copyOf` không thiết lập khóa chung với những đường sửa khác trong ứng dụng. Nếu nhiều luồng có thể sửa nguồn lúc lấy dữ liệu, cần một quy tắc phối hợp phù hợp với loại nguồn và yêu cầu nhất quán. Không suy từ “kết quả không sửa được” sang “quá trình đọc đầu vào luôn là ảnh chụp nguyên tử”.

Tương tự, không xem việc gọi factory nhiều lần là cách quản lý phiên bản nghiệp vụ. Nếu mỗi bản cấu hình cần số phiên bản, thời điểm có hiệu lực hoặc quan hệ với dữ liệu khác, mô hình hóa các thông tin đó riêng. `copyOf` chỉ là một bước xây dựng phần dữ liệu collection trong mô hình ấy.

## 15. Chẩn đoán những hiểu nhầm thường gặp

| Quan sát hoặc giả định | Cách đọc đúng và hướng sửa |
| --- | --- |
| Gọi `set` trên kết quả List và nhận ngoại lệ | Kết quả chặn thay phần tử, không chỉ chặn đổi kích thước; tạo bản sao có thể sửa nếu đó là yêu cầu |
| Đổi nguồn mà view chỉ đọc vẫn đổi theo | View có thể đọc xuyên nguồn; chọn ảnh chụp nếu cần chốt dữ liệu |
| Sửa builder rồi văn bản trong List copy cũng đổi | Phần tử dùng chung; chọn phần tử bất biến hoặc chuyển đổi/sao chép phần tử |
| List ba phần tử thành Set hai phần tử | Giá trị trùng đã được gộp; dùng List nếu phải giữ số lần xuất hiện |
| Kỳ vọng Set.copyOf ném lỗi vì phần tử trùng | Quy tắc này khác Set.of; kiểm tra tính duy nhất riêng nếu nghiệp vụ yêu cầu lỗi |
| Thứ tự Set hoặc Map kết quả khác nguồn | Factory không hứa bảo toàn thứ tự đó; chọn một hợp đồng có thứ tự rõ ràng |
| Ép kết quả thành implementation nguồn | Factory chỉ cam kết giao diện và hành vi công bố; bỏ phụ thuộc tên lớp |
| Dùng == để chứng minh đã chép | Định danh không chứng minh độc lập dữ liệu; kiểm tra hành vi với thay đổi nguồn |
| Map ngoài chỉ đọc nhưng List giá trị vẫn sửa được | Cần bảo vệ tầng List nếu không muốn trao quyền sửa nó |
| Đặt trường final nhưng dữ liệu vẫn thay đổi | Final chặn gán lại trường; cần quản lý đối tượng được tham chiếu |

Khi thấy lỗi, xác định chính đối tượng nhận thao tác sửa. `map.put(key, list)` tác động lên Map; `map.get(key).add(value)` tác động lên List; `map.get(key).get(0).setName(...)` tác động lên một đối tượng phần tử sâu hơn nữa. Cách phân tầng này giúp tìm đúng nơi cần thay đổi thiết kế, thay vì thêm một lớp bọc ngoài rồi hy vọng mọi trạng thái bên trong cũng được bảo vệ.

Không rút ra hợp đồng từ một lần in. Một thứ tự duyệt tình cờ, một phép so sánh định danh hoặc tên lớp thấy trong debugger có thể là đặc điểm triển khai. Các ca kiểm chứng nên tập trung vào yêu cầu đã công bố: phần tử/ánh xạ, quyền sửa, quan hệ với nguồn và mức chia sẻ đối tượng.

## 16. Thực hành có tiêu chí quan sát

### Bài 1: Chốt kết quả tìm kiếm

Một phương thức đang dựng List mã sản phẩm, có thể có cùng một mã xuất hiện hai lần. Người nhận phải nhìn thấy đúng thứ tự kết quả tìm kiếm và không được thêm/xóa/thay phần tử.

Hãy chọn factory, nêu chính sách null và viết kiểm tra bằng cách sửa List nguồn sau khi tạo kết quả. Tiêu chí đạt: thứ tự và hai lần xuất hiện được giữ; thay List nguồn không đổi kết quả; thao tác sửa trên kết quả bị chặn. Hướng lựa chọn là `List.copyOf`, vì số vị trí và thứ tự còn thuộc yêu cầu.

### Bài 2: Tập quyền duy nhất

Đầu vào là List quyền dạng String, trong đó có quyền lặp do nhiều nhóm cấp cùng một quyền. Kết quả chỉ cần trả lời có quyền hay không; không có yêu cầu thứ tự.

Hãy xác định có nên báo lỗi khi lặp hay chấp nhận gộp. Nếu nghiệp vụ cho phép gộp, `Set.copyOf` biểu diễn đúng tập quyền duy nhất. Kiểm tra nội dung bằng quan hệ tập hợp, không viết kiểm tra đòi một chuỗi in theo thứ tự cụ thể.

Nếu yêu cầu đổi thành “gặp quyền lặp phải báo lỗi”, chỉ gọi `Set.copyOf` chưa đủ. Cần bổ sung kiểm tra dữ liệu đầu vào; không đổi sang `Set.of(list)` và tưởng rằng List sẽ được tự trải thành các quyền.

### Bài 3: Bảng cấu hình có giá trị lồng

Nguồn là `Map<String, List<String>>`, khóa là tên tính năng, giá trị là các tên môi trường. Người nhận không được thay ánh xạ hoặc sửa các List môi trường. Mọi tên là String không null.

Hãy mô tả quy trình hai tầng và kiểm chứng hai đường sửa khác nhau: đổi List được gắn trong Map nguồn; thêm phần tử vào List cũ. Tiêu chí đạt: cả hai đường sửa nguồn không làm thay đổi dữ liệu đã công bố. Quy trình ở phần 10 cung cấp một cách làm cho đúng hình dạng dữ liệu này.

### Bài 4: Kết quả có yêu cầu thứ tự khóa

Một báo cáo phải duyệt các mục theo thứ tự chèn đã xác định. Có người đề xuất chuyển `LinkedHashMap` thành `Map.copyOf` rồi coi thứ tự vẫn được giữ vì nguồn có thứ tự.

Hãy chỉ ra phần cam kết còn thiếu và chọn cách biểu diễn đáp ứng thứ tự. Tiêu chí đạt là nói rõ thứ tự nằm trong hợp đồng của cấu trúc nào và việc bên ngoài có còn giữ đường sửa cấu trúc đó hay không. Chỉ kiểm tra một lần in đúng không đủ để chứng minh thiết kế.

### Bài 5: Đổi kiểu phần tử trong Catalog

Thay danh sách tên String bằng danh sách đối tượng có phương thức sửa tên. Hàm khởi tạo vẫn dùng `List.copyOf`.

Dự đoán điều gì được bảo vệ và điều gì còn được chia sẻ. Tiêu chí đạt: phân biệt việc thay một vị trí trong List với việc sửa tên trên đối tượng ở vị trí đó; đề xuất đối tượng bất biến hoặc cách sao chép phù hợp nếu cần ổn định tên.

## 17. Tự kiểm tra trước khi áp dụng

1. **Ba factory có luôn tạo đối tượng collection mới không?** Không. Hợp đồng dữ liệu không phụ thuộc việc cấp phát mới hay tận dụng kết quả thích hợp đã có. Không kiểm tra đúng/sai bằng định danh.
2. **List.copyOf có loại phần tử trùng không?** Không. Nó giữ các phần tử theo thứ tự duyệt nguồn. Set.copyOf mới biểu diễn các giá trị phân biệt.
3. **Set.copyOf có chọn đại diện đầu tiên của các phần tử bằng nhau không?** Không có cam kết ấy. Nếu cần quy tắc chọn bản ghi, thực hiện quy tắc rõ ràng trước khi tạo tập kết quả.
4. **Map.copyOf có giữ thứ tự của LinkedHashMap không?** Không có bảo đảm thứ tự duyệt tương ứng. Đặt yêu cầu thứ tự vào hợp đồng và chọn công cụ thích hợp.
5. **Nguồn chứa null nhưng tự cho phép null thì sao?** Quy tắc nguồn không thay đổi quy tắc factory. Xử lý null theo hợp đồng tiếp nhận trước khi chụp nếu cần.
6. **Map.copyOf có làm List giá trị thành chỉ đọc không?** Không. Nó chốt các ánh xạ; cần xử lý List ở tầng trong riêng.
7. **Lớp bọc chỉ đọc và ảnh chụp khác nhau ở đâu?** Lớp bọc có thể tiếp tục đọc qua nguồn; ảnh chụp copyOf không đi theo việc nguồn thêm/xóa/thay phần tử hoặc ánh xạ sau khi sao chép.
8. **Khi nào có thể trả trực tiếp collection đã chốt từ một trường?** Khi quyền sửa và mức chia sẻ phần tử đáp ứng hợp đồng của đối tượng. Với String bất biến trong Catalog, điều kiện này rõ ràng hơn với phần tử có thể sửa.
9. **Vì sao stdout của Set và Map trong bài phải qua cấu trúc sắp xếp?** Để trình bày ổn định khi kiểm chứng dữ liệu; không gán cho kết quả factory một thứ tự mà API không hứa.
10. **Kiểm tra nào chứng minh độc lập với nguồn tốt hơn so sánh ==?** Tạo kết quả, sửa nguồn theo cách được phép, rồi kiểm tra phần tử hoặc ánh xạ trong kết quả vẫn như yêu cầu. Kiểm tra thêm riêng việc dùng chung đối tượng phần tử khi mức bất biến có liên quan.

