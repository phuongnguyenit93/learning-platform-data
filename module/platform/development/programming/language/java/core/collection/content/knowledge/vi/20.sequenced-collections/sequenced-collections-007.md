# SequencedMap: firstEntry, lastEntry, pollFirstEntry và pollLastEntry

## 1. Làm việc với hai đầu của một map có thứ tự

Một Map lưu các ánh xạ từ khóa sang giá trị. Khi map có thứ tự gặp được xác định, còn có thể hỏi: ánh xạ nào đứng đầu, ánh xạ nào đứng cuối, và có cần lấy ánh xạ đó ra khỏi map hay chỉ xem?

Từ Java 21, `SequencedMap<K, V>` cung cấp hợp đồng chung cho map có thứ tự gặp, gọi là encounter order. Bốn phương thức trong bài chia thành hai nhóm:

- firstEntry và lastEntry: đọc một ánh xạ ở đầu/cuối.
- pollFirstEntry và pollLastEntry: lấy và xóa một ánh xạ ở đầu/cuối, nếu thao tác xóa được hỗ trợ.

Kết quả là `Map.Entry<K, V>`, tức một cặp khóa và giá trị. Đây không phải chỉ một giá trị V, cũng không phải cả map.

Ví dụ, LinkedHashMap theo thứ tự thêm khóa đang chứa B=20, A=10, C=30. firstEntry là B=20; lastEntry là C=30. Chúng không tự chọn A vì A nhỏ nhất theo chữ cái, cũng không chọn giá trị 10 vì nhỏ nhất theo số.

Điều cần luôn xác định trước khi dùng API là **thứ tự của map đến từ đâu**. Cùng một lời gọi firstEntry, LinkedHashMap theo thứ tự thêm có thể trả ánh xạ thêm sớm nhất còn tồn tại; TreeMap có thể trả ánh xạ có khóa đứng đầu theo Comparator.

### 1.1. Kiến thức đầu vào và phiên bản

Cần biết cách khai báo generic, put/get của Map và cách đọc getKey/getValue của Map.Entry. Không cần tạo một lớp Entry riêng để dùng bốn phương thức này.

Tất cả chương trình đầy đủ trong bài cần JDK 21 trở lên. Chúng dùng --release 21 và không cần bật preview.

Tên bốn phương thức đã có trên NavigableMap trước Java 21, ví dụ TreeMap đã hỗ trợ từ Java 6. Java 21 bổ sung SequencedMap làm giao diện chung và cho phép dùng cùng nhóm thao tác với những map như LinkedHashMap. Không hiểu rằng mọi lời gọi firstEntry trên TreeMap chỉ mới xuất hiện từ Java 21.

## 2. Đọc đúng hợp đồng của bốn phương thức

| Phương thức | Kết quả khi có ánh xạ | Làm thay đổi số ánh xạ? | Khi map sửa được đang rỗng |
|---|---|---|---|
| firstEntry() | Entry của ánh xạ đầu | Không xóa | Trả null |
| lastEntry() | Entry của ánh xạ cuối | Không xóa | Trả null |
| pollFirstEntry() | Entry của ánh xạ đầu vừa được xóa | Giảm một ánh xạ | Trả null |
| pollLastEntry() | Entry của ánh xạ cuối vừa được xóa | Giảm một ánh xạ | Trả null |

Hai phương thức poll là thao tác tùy chọn. Một đối tượng không hỗ trợ xóa có thể ném UnsupportedOperationException. Điều kiện đó phải được xét riêng với tình huống rỗng.

Các entry do bốn phương thức này trả về là **snapshot của ánh xạ tại lúc gọi**. Chúng không phải các entry cho phép sửa map bằng setValue. Phần sau sẽ giải thích vì sao snapshot cũng không có nghĩa sao chép sâu mọi đối tượng khóa và giá trị.

Hợp đồng được mô tả tại [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

### 2.1. poll không phải đọc rồi giữ nguyên dữ liệu

Sau pollFirstEntry thành công trên map không rỗng, ánh xạ vừa nhận không còn trong map đó. Giá trị và khóa vẫn có thể được tham chiếu từ Entry trả về, nhưng quan hệ khóa–giá trị đã bị loại khỏi map.

Nếu chỉ muốn xem trước, chọn firstEntry hoặc lastEntry. Không dùng poll để in thử đầu/cuối rồi ngạc nhiên khi dữ liệu bị mất khỏi cấu trúc chứa.

poll ở đây cũng không phải một lệnh đợi có dữ liệu. Trên map sửa được rỗng, nó trả null theo hợp đồng; không chờ một luồng khác thêm ánh xạ.

### 2.2. Một ánh xạ duy nhất là cả đầu lẫn cuối

Nếu map chỉ có A=10, firstEntry và lastEntry cùng mô tả ánh xạ đó. Không suy ra phải có hai ánh xạ khác nhau để hai phương thức này hoạt động.

Poll một trong hai đầu sẽ làm map rỗng. Lần poll tiếp theo trên map sửa được trả null, không trả lại ánh xạ cũ.

Không kiểm tra hai entry snapshot có phải cùng một đối tượng bằng == để xác nhận cùng ánh xạ. Thông tin cần sử dụng là khóa và giá trị; API không hứa tái sử dụng cùng đối tượng Entry cho các lần gọi.

### 2.3. null của Entry khác null của giá trị

Nếu firstEntry trả null, không có ánh xạ đầu để đọc. Nhưng một Entry không null có thể mang giá trị null nếu map cho phép.

Vì vậy phải kiểm tra bản thân entry trước khi gọi getValue. Không dùng `entry.getValue() == null` làm phép kiểm tra map rỗng: nó có thể là một ánh xạ hợp lệ, và còn gây NullPointerException nếu entry thực sự là null.

LinkedHashMap còn cho phép khóa null. Một entry có cả khóa null lẫn giá trị null vẫn là một Entry tồn tại; nó khác kết quả null biểu thị không còn ánh xạ.

## 3. Thứ tự nào quyết định đầu và cuối?

### 3.1. Ba chính sách thường gặp

| Đối tượng thực tế | Thứ tự cần hiểu | Đầu/cuối thường biểu thị |
|---|---|---|
| LinkedHashMap mặc định | Thứ tự thêm khóa | Ánh xạ thêm sớm nhất/muộn nhất còn tồn tại |
| LinkedHashMap với accessOrder=true | Thứ tự truy cập theo hợp đồng của lớp | Ít được truy cập gần đây nhất/gần đây nhất |
| TreeMap | Thứ tự khóa tự nhiên hoặc Comparator | Khóa đứng đầu/cuối theo phép so sánh |
| View reversed của một map phù hợp | Chiều ngược của thứ tự map nguồn | Đầu của view là cuối theo chiều nguồn |

Không lấy tên firstEntry để suy ra thứ tự tăng dần của khóa, thời gian tạo hay độ ưu tiên nghiệp vụ. Những ý nghĩa đó phải đến từ cấu trúc và cách sử dụng map.

Với LinkedHashMap mặc định, cập nhật giá trị bằng put cho một khóa đã có không tự chuyển khóa xuống cuối. Với chế độ access-order, các thao tác truy cập được lớp quy định có thể đổi thứ tự. Cần xác định đúng chế độ trước khi dùng hai đầu để chọn đối tượng cần xử lý.

### 3.2. Kiểu khai báo ảnh hưởng lời gọi ở mức biên dịch

Đối tượng LinkedHashMap có thể được giữ trong biến Map hoặc SequencedMap. Nếu biến chỉ có kiểu Map, trình biên dịch chỉ cung cấp hợp đồng Map; không tự cho gọi firstEntry vì đối tượng thực tế có thứ tự.

Khai báo SequencedMap khi API của chương trình thực sự cần thao tác theo thứ tự. Điều này diễn tả rõ hơn việc truyền một Map bất kỳ rồi ép kiểu bên trong.

HashMap không được biến thành SequencedMap chỉ bằng ép kiểu. Tạo một LinkedHashMap mới từ một map khác là tạo cấu trúc mới, và thứ tự thu vào còn phụ thuộc thứ tự duyệt của nguồn. Không lấy một Map có thứ tự không được bảo đảm làm đầu vào rồi gán ý nghĩa nghiệp vụ chắc chắn cho “ánh xạ đầu”.

### 3.3. Thứ tự được dùng cho ánh xạ, không chỉ cho khóa riêng lẻ

Một Entry luôn ghép khóa với giá trị tương ứng. Nếu cần lấy đầu map để xử lý cả hai, firstEntry hoặc pollFirstEntry giúp nhận đúng cặp trong một kết quả.

Không lấy “khóa đầu” từ một lần đọc rồi “giá trị đầu” từ một lần đọc độc lập khi dữ liệu có thể đổi giữa các lần đọc. Ngay cả một Entry snapshot cũng không cung cấp thêm bảo đảm đồng thời cho toàn map; vấn đề phối hợp truy cập sẽ được tách riêng ở phần áp dụng.

## 4. Chương trình 1: xem và lấy ra là hai hành động khác nhau

Lưu chương trình đầy đủ vào `SequencedMapEndsDemo.java`. Các lệnh put được viết tuần tự để thứ tự thêm khóa rõ ràng.

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class SequencedMapEndsDemo {
    public static void main(String[] args) {
        SequencedMap<String, Integer> map = new LinkedHashMap<>();
        map.put("B", 20);
        map.put("A", 10);
        map.put("C", 30);
        System.out.println("initial=" + map);
        System.out.println("first=" + map.firstEntry());
        System.out.println("last=" + map.lastEntry());
        System.out.println("sizeAfterReads=" + map.size());
        System.out.println("pollFirst=" + map.pollFirstEntry());
        System.out.println("afterPollFirst=" + map);
        System.out.println("pollLast=" + map.pollLastEntry());
        System.out.println("afterPollLast=" + map);
        System.out.println("singleFirst=" + map.firstEntry());
        System.out.println("singleLast=" + map.lastEntry());
        System.out.println("pollSingle=" + map.pollFirstEntry());
        System.out.println("emptyFirst=" + map.firstEntry());
        System.out.println("emptyLast=" + map.lastEntry());
        System.out.println("emptyPollFirst=" + map.pollFirstEntry());
        System.out.println("emptyPollLast=" + map.pollLastEntry());
        System.out.println("emptySize=" + map.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 SequencedMapEndsDemo.java
java SequencedMapEndsDemo
```

Stdout:

```text
initial={B=20, A=10, C=30}
first=B=20
last=C=30
sizeAfterReads=3
pollFirst=B=20
afterPollFirst={A=10, C=30}
pollLast=C=30
afterPollLast={A=10}
singleFirst=A=10
singleLast=A=10
pollSingle=A=10
emptyFirst=null
emptyLast=null
emptyPollFirst=null
emptyPollLast=null
emptySize=0
```

### 4.1. B là đầu vì được thêm trước

initial là `{B=20, A=10, C=30}`. B đứng đầu dù A nhỏ hơn theo chữ cái. Hai lần đọc trả B=20 và C=30, còn sizeAfterReads vẫn là 3.

Dạng in Entry trong chương trình là khóa=giá trị. Chuỗi `first=B=20` bao gồm nhãn first, rồi biểu diễn Entry B=20; không phải có hai ánh xạ.

### 4.2. Poll xóa đúng một ánh xạ tại đầu được chọn

pollFirstEntry lấy B=20 ra, nên map còn A=10,C=30. pollLastEntry sau đó lấy C=30, nên còn A=10.

Nếu đảo thứ tự gọi các phương thức poll, trạng thái trung gian cần được tính lại. Mỗi lần poll làm việc trên trạng thái hiện tại của map, không dựa vào một danh sách đầu/cuối được chụp sẵn lúc bắt đầu chương trình.

### 4.3. Một phần tử rồi rỗng

Khi chỉ còn A=10, cả singleFirst và singleLast cùng in A=10. pollSingle lấy ánh xạ đó ra.

Sau đó cả bốn phương thức đều in null với LinkedHashMap sửa được trong ví dụ, và emptySize là 0. Không có NoSuchElementException chỉ vì gọi bốn API này trên map sửa được đang rỗng.


## 5. Entry trả về là snapshot của ánh xạ

### 5.1. Cặp tham chiếu tại thời điểm gọi

Snapshot ở đây có nghĩa Entry ghi nhận khóa và giá trị của ánh xạ tại thời điểm phương thức được gọi. Sau đó map có thể cập nhật sang một giá trị khác hoặc xóa ánh xạ; Entry đã nhận không trở thành một cửa sổ tự động đọc lại giá trị mới.

Ví dụ:

```text
Lúc đọc:
map:       task → queued
snapshot:  task → queued

Sau put(task, running):
map:       task → running
snapshot:  task → queued
```

Nếu cần trạng thái hiện tại, phải đọc lại map bằng API phù hợp. Không giữ snapshot trong một biến rồi kỳ vọng lần gọi getValue sau đó luôn phản ánh dữ liệu mới nhất của map.

Đối với pollFirstEntry và pollLastEntry, snapshot càng cần được hiểu rõ: ánh xạ đã bị xóa khỏi map, nhưng kết quả trả về còn giữ thông tin để người gọi xử lý.

### 5.2. Không dùng setValue để cập nhật map

Entry nhận từ bốn phương thức này không hỗ trợ sửa map bằng setValue. Trong các triển khai chuẩn được kiểm tra trong bài, gọi setValue trên entry đó ném UnsupportedOperationException.

Điều này không chứng minh map nguồn không sửa được. LinkedHashMap nguồn vẫn có thể put hoặc remove; chỉ đối tượng Entry snapshot không phải đường sửa map.

Muốn cập nhật một khóa, gọi API cập nhật của map theo chính sách nghiệp vụ. Cần nhớ rằng một snapshot có thể đã cũ: nếu khóa đã bị xóa, put dùng khóa từ snapshot sẽ thêm lại ánh xạ. Không thay thế kiểm tra trạng thái hiện tại bằng một entry giữ từ trước.

### 5.3. Snapshot không phải bản sao sâu của khóa và giá trị

Entry có thể giữ cùng tham chiếu tới một đối tượng giá trị có thể thay đổi. Nếu V là List và nội dung List được sửa, getValue của snapshot vẫn trỏ tới List đó và có thể thấy nội dung mới.

Hai việc khác nhau:

- Map thay tham chiếu giá trị của một khóa sang đối tượng khác.
- Chương trình sửa chính đối tượng giá trị đang được cả map lẫn snapshot tham chiếu.

Trong trường hợp đầu, snapshot giữ tham chiếu cũ. Trong trường hợp sau, cùng một đối tượng được nhìn thấy từ nhiều nơi. Không mô tả snapshot Entry như việc đóng băng toàn bộ cây đối tượng bên trong.

### 5.4. Không đồng nhất mọi nguồn tạo Map.Entry

Một Entry nhận khi duyệt entrySet có hợp đồng kết nối với map trong phạm vi phép duyệt; setValue còn tùy khả năng của map. Nó khác nhóm snapshot của firstEntry/lastEntry/pollFirstEntry/pollLastEntry.

Ngay cả `sequencedEntrySet().getFirst()` cũng không được giao diện SequencedMap hứa cùng hợp đồng snapshot/setValue như firstEntry. Đừng thay một cách lấy entry bằng cách khác chỉ vì cả hai trả Map.Entry và có từ First.

Tài liệu [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html) tách rõ các nguồn Entry này. Khi thiết kế mã sửa dữ liệu, phải đọc hợp đồng của đường tạo entry cụ thể.

## 6. Chương trình 2: snapshot, giá trị có thể thay đổi và null

Lưu vào `SequencedMapSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.SequencedMap;

public class SequencedMapSnapshotDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        SequencedMap<String, String> map = new LinkedHashMap<>();
        map.put("task", "queued");
        Map.Entry<String, String> snapshot = map.firstEntry();
        expectUnsupported("snapshotSetValue", () -> snapshot.setValue("forced"));
        map.put("task", "running");
        System.out.println("snapshotAfterPut=" + snapshot);
        System.out.println("currentEntry=" + map.firstEntry());
        Map.Entry<String, String> removed = map.pollLastEntry();
        System.out.println("removed=" + removed);
        System.out.println("snapshotAfterRemoval=" + snapshot);
        System.out.println("mapAfterRemoval=" + map);
        expectUnsupported("removedSetValue", () -> removed.setValue("changed"));

        SequencedMap<String, List<String>> mutable = new LinkedHashMap<>();
        List<String> steps = new ArrayList<>(List.of("start"));
        mutable.put("job", steps);
        Map.Entry<String, List<String>> shallow = mutable.firstEntry();
        steps.add("finish");
        System.out.println("snapshotSharedValue=" + shallow.getValue());
        System.out.println("sameValueReference=" + (shallow.getValue() == steps));

        SequencedMap<String, String> nullable = new LinkedHashMap<>();
        nullable.put(null, null);
        Map.Entry<String, String> nullMapping = nullable.pollFirstEntry();
        System.out.println("hasNullMapping=" + (nullMapping != null));
        System.out.println("nullKey=" + nullMapping.getKey());
        System.out.println("nullValue=" + nullMapping.getValue());
        System.out.println("afterNullMappingPoll=" + nullable.pollFirstEntry());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 SequencedMapSnapshotDemo.java
java SequencedMapSnapshotDemo
```

Stdout:

```text
snapshotSetValue=UnsupportedOperationException
snapshotAfterPut=task=queued
currentEntry=task=running
removed=task=running
snapshotAfterRemoval=task=queued
mapAfterRemoval={}
removedSetValue=UnsupportedOperationException
snapshotSharedValue=[start, finish]
sameValueReference=true
hasNullMapping=true
nullKey=null
nullValue=null
afterNullMappingPoll=null
```

### 6.1. Snapshot giữ giá trị queued khi map chuyển sang running

snapshot được lấy lúc map chứa task=queued. setValue qua snapshot bị từ chối. Sau put(task,running), snapshotAfterPut vẫn in task=queued, trong khi currentEntry đọc mới là task=running.

pollLastEntry trả task=running và làm map rỗng. snapshot cũ vẫn in task=queued; nó không biến thành null khi ánh xạ nguồn bị xóa. Entry removed cũng không hỗ trợ setValue để tạo hay sửa lại ánh xạ.

### 6.2. Đối tượng List vẫn được chia sẻ

mutable chứa job trỏ đến List steps. shallow ghi nhận cùng tham chiếu List. Sau khi thêm finish vào steps, snapshotSharedValue in `[start, finish]`.

sameValueReference là true. Kết quả này phù hợp với snapshot của cặp tham chiếu, không phải sao chép sâu các phần tử của List. Nếu cần dữ liệu độc lập sâu, phải thiết kế sao chép theo kiểu giá trị, không dựa vào tên snapshot của Entry.

### 6.3. Ánh xạ null vẫn trả một Entry tồn tại

nullable có một ánh xạ với khóa null và giá trị null. pollFirstEntry trả một Entry không null nên hasNullMapping là true; getKey và getValue của nó đều là null.

Sau khi đã lấy ánh xạ này ra, lần poll tiếp theo mới trả null. Như vậy có thể phân biệt:

```text
Entry không null, value null → có ánh xạ, giá trị là null
Entry null                 → không có ánh xạ để trả về
```

Không gọi getKey/getValue trước khi kiểm tra entry trong mã có thể gặp map rỗng.

## 7. Đầu và cuối đổi vai trò trên reversed

reversed trả một view nhìn theo thứ tự ngược. Trong view này, đầu theo chiều nguồn trở thành cuối và cuối theo chiều nguồn trở thành đầu.

Trên view ngược sửa được của LinkedHashMap, có thể dự đoán:

| Lời gọi trên view ngược | Ánh xạ được chọn theo chiều map nguồn |
|---|---|
| firstEntry() | Ánh xạ cuối |
| lastEntry() | Ánh xạ đầu |
| pollFirstEntry() | Lấy và xóa ánh xạ cuối |
| pollLastEntry() | Lấy và xóa ánh xạ đầu |

Bảng nói về ánh xạ được chọn và tác dụng lên dữ liệu, không hứa hai lời gọi riêng trả cùng đối tượng Entry theo ==. Nếu dữ liệu thay đổi giữa các lần gọi, còn phải xét trạng thái mới.

[LinkedHashMap.reversed — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html) cho phép thay đổi qua view này và phản ánh thay đổi vào map nguồn. Đây là view có dữ liệu chung, không phải bản sao được tự động tạo ra để người gọi có thể poll thoải mái mà không ảnh hưởng nguồn.

## 8. Chương trình 3: lấy qua view ngược tác động lên map gốc

Lưu vào `SequencedMapReverseDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class SequencedMapReverseDemo {
    public static void main(String[] args) {
        SequencedMap<String, Integer> forward = new LinkedHashMap<>();
        forward.put("a", 1);
        forward.put("b", 2);
        forward.put("c", 3);
        forward.put("d", 4);
        SequencedMap<String, Integer> reverse = forward.reversed();
        System.out.println("forward=" + forward);
        System.out.println("reverse=" + reverse);
        System.out.println("reverseFirst=" + reverse.firstEntry());
        System.out.println("reverseLast=" + reverse.lastEntry());
        System.out.println("reversePollFirst=" + reverse.pollFirstEntry());
        System.out.println("forwardAfterFirstPoll=" + forward);
        System.out.println("reversePollLast=" + reverse.pollLastEntry());
        System.out.println("forwardAfterLastPoll=" + forward);
        System.out.println("forwardPollFirst=" + forward.pollFirstEntry());
        System.out.println("reverseNow=" + reverse);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 SequencedMapReverseDemo.java
java SequencedMapReverseDemo
```

Stdout:

```text
forward={a=1, b=2, c=3, d=4}
reverse={d=4, c=3, b=2, a=1}
reverseFirst=d=4
reverseLast=a=1
reversePollFirst=d=4
forwardAfterFirstPoll={a=1, b=2, c=3}
reversePollLast=a=1
forwardAfterLastPoll={b=2, c=3}
forwardPollFirst=b=2
reverseNow={c=3}
```

### 8.1. Hai hướng nhìn cùng bốn ánh xạ

forward ban đầu là a=1,b=2,c=3,d=4; reverse hiển thị d=4,c=3,b=2,a=1. reverseFirst trả d=4, reverseLast trả a=1.

Đọc đầu/cuối không tạo thêm ánh xạ và không xóa. Nhưng khi poll qua reverse, hướng chọn đầu/cuối đã đảo.

### 8.2. Poll trên view là sửa dữ liệu nguồn

reverse.pollFirstEntry lấy d=4, nên forward chỉ còn a,b,c. reverse.pollLastEntry tiếp theo lấy a=1, nên forward còn b,c.

forward.pollFirstEntry sau đó lấy b=2. reverseNow chỉ còn c=3 vì nó nhìn cùng map nguồn, theo chiều ngược.

Nếu cần một tập dữ liệu để tiêu thụ độc lập, phải tạo một map chứa riêng với chính sách thứ tự được chọn. Chỉ gọi reversed không cung cấp sự độc lập đó.

## 9. TreeMap dùng cùng bốn phương thức nhưng đầu phụ thuộc Comparator

TreeMap sắp các khóa theo thứ tự tự nhiên hoặc Comparator. Nó không giữ thứ tự lần thêm khóa như LinkedHashMap mặc định.

Với khóa số tự nhiên, ánh xạ đầu có khóa nhỏ nhất. Với Comparator.reverseOrder, đầu theo thứ tự map có khóa lớn nhất theo cách so số thông thường. Không gọi đó là “sai thứ tự”: chính Comparator giảm đã định nghĩa cách xếp.

Cũng không tự chọn entry theo giá trị V. Một map có giá trị one,two,three vẫn được TreeMap sắp theo khóa K, trừ khi ứng dụng chủ động thiết kế một mô hình khác.

[TreeMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html) và [NavigableMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html) là nguồn đối chiếu cho các thao tác trên tập khóa được sắp xếp này.

## 10. Chương trình 4: đầu theo Comparator giảm

Lưu vào `SequencedMapSortedDemo.java`:

```java
import java.util.Comparator;
import java.util.SequencedMap;
import java.util.TreeMap;

public class SequencedMapSortedDemo {
    public static void main(String[] args) {
        SequencedMap<Integer, String> sorted =
                new TreeMap<>(Comparator.reverseOrder());
        sorted.put(2, "two");
        sorted.put(1, "one");
        sorted.put(3, "three");
        System.out.println("sorted=" + sorted);
        System.out.println("first=" + sorted.firstEntry());
        System.out.println("last=" + sorted.lastEntry());
        System.out.println("pollFirst=" + sorted.pollFirstEntry());
        System.out.println("pollLast=" + sorted.pollLastEntry());
        System.out.println("remaining=" + sorted);
        System.out.println("remainingFirst=" + sorted.firstEntry());
        System.out.println("remainingLast=" + sorted.lastEntry());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 SequencedMapSortedDemo.java
java SequencedMapSortedDemo
```

Stdout:

```text
sorted={3=three, 2=two, 1=one}
first=3=three
last=1=one
pollFirst=3=three
pollLast=1=one
remaining={2=two}
remainingFirst=2=two
remainingLast=2=two
```

### 10.1. Thứ tự put không quyết định thứ tự của TreeMap

Mã thêm khóa 2, rồi 1, rồi 3. Map in theo thứ tự 3,2,1 do Comparator.reverseOrder. firstEntry trả 3=three; lastEntry trả 1=one.

Nếu chỉ đổi kiểu khai báo từ TreeMap sang SequencedMap, thứ tự thực tế không đổi. SequencedMap tạo một hợp đồng chung để gọi, không thay thế Comparator của đối tượng.

### 10.2. Poll không đòi quyền đặt vị trí tường minh

pollFirstEntry xóa khóa 3; pollLastEntry xóa khóa 1; còn khóa 2. TreeMap sửa được hỗ trợ các thao tác xóa này.

Điều đó khác yêu cầu đặt một ánh xạ tùy ý vào đầu bằng putFirst. Một TreeMap có thể hỗ trợ lấy/xóa hai đầu trong khi không hỗ trợ định vị tường minh. Không suy ra mọi thao tác của SequencedMap đều có cùng mức hỗ trợ chỉ vì một thao tác poll đã chạy được.

Khi còn một ánh xạ, remainingFirst và remainingLast đều là 2=two. Nguyên tắc đầu/cuối cùng một ánh xạ giống ví dụ LinkedHashMap, còn chính sách xác định thứ tự thì khác.


## 11. Thứ tự truy cập và quyền xóa là hai điều kiện riêng

### 11.1. LinkedHashMap theo thứ tự truy cập

Với constructor đặt accessOrder=true, các ánh xạ được duy trì theo thứ tự truy cập theo hợp đồng của LinkedHashMap. Một lần get thành công có thể chuyển ánh xạ được truy cập về cuối của chiều map nguồn.

firstEntry và lastEntry không tạo một lượt truy cập kiểu get. Vì vậy có thể xem hai đầu mà không làm ánh xạ vừa xem tự chuyển vị trí do cơ chế access-order.

Trong cách dùng không chủ động định vị lại, đầu map là ứng viên ít được truy cập gần đây nhất. Có thể dùng firstEntry để xem, hoặc pollFirstEntry để lấy và loại ứng viên đó. Hai API không tự biến map thành một cache hoàn chỉnh: giới hạn dung lượng, điều kiện loại bỏ và cách xử lý tài nguyên vẫn do chương trình quyết định.

Nếu mã còn gọi putFirst/putLast để điều chỉnh vị trí tường minh, phải xét thứ tự hiện tại sau những thao tác đó. Không tự gán một dấu thời gian nghiệp vụ cho đầu/cuối chỉ dựa vào tên access-order.

Các quy tắc tạo lượt truy cập được mô tả tại [LinkedHashMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

### 11.2. View không cho sửa có thể đọc nhưng không poll

Collections.unmodifiableSequencedMap trả một view giữ hợp đồng SequencedMap nhưng không cho sửa qua view. firstEntry và lastEntry có thể dùng để đọc; các thao tác poll bị từ chối bằng UnsupportedOperationException.

Không thử poll như phép đọc vô hại để kiểm tra map có rỗng hay không. Trên một map sửa được, phép thử đó thật sự xóa dữ liệu; trên một view không cho sửa, nó có thể ném ngoại lệ. Chọn đúng nhóm API theo ý định.

View không cho sửa cũng không phải bản sao dữ liệu. Tập ánh xạ nguồn vẫn có thể được sửa qua một tham chiếu khác; việc đọc qua view sẽ đọc dữ liệu nguồn theo hợp đồng của wrapper.

Nguồn đối chiếu: [Collections.unmodifiableSequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

## 12. Chương trình 5: đọc hai đầu, truy cập và view không cho sửa

Lưu vào `SequencedMapPolicyDemo.java`:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class SequencedMapPolicyDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        LinkedHashMap<String, Integer> access = new LinkedHashMap<>(16, 0.75f, true);
        access.put("A", 1);
        access.put("B", 2);
        access.put("C", 3);
        System.out.println("initial=" + access);
        System.out.println("firstBeforeGet=" + access.firstEntry());
        System.out.println("lastBeforeGet=" + access.lastEntry());
        System.out.println("afterEndReads=" + access);
        System.out.println("getA=" + access.get("A"));
        System.out.println("afterGetA=" + access);
        System.out.println("firstAfterGet=" + access.firstEntry());
        System.out.println("pollLeastRecent=" + access.pollFirstEntry());
        System.out.println("afterPoll=" + access);

        SequencedMap<String, Integer> readOnly =
                Collections.unmodifiableSequencedMap(access);
        System.out.println("readOnlyFirst=" + readOnly.firstEntry());
        expectUnsupported("readOnlyPollFirst", () -> readOnly.pollFirstEntry());
        expectUnsupported("readOnlyPollLast", () -> readOnly.pollLastEntry());
        access.put("D", 4);
        System.out.println("readOnlyAfterSourcePut=" + readOnly);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 SequencedMapPolicyDemo.java
java SequencedMapPolicyDemo
```

Stdout:

```text
initial={A=1, B=2, C=3}
firstBeforeGet=A=1
lastBeforeGet=C=3
afterEndReads={A=1, B=2, C=3}
getA=1
afterGetA={B=2, C=3, A=1}
firstAfterGet=B=2
pollLeastRecent=B=2
afterPoll={C=3, A=1}
readOnlyFirst=C=3
readOnlyPollFirst=UnsupportedOperationException
readOnlyPollLast=UnsupportedOperationException
readOnlyAfterSourcePut={C=3, A=1, D=4}
```

### 12.1. Xem hai đầu không làm A trở thành vừa được truy cập

Map bắt đầu theo thứ tự A,B,C. firstBeforeGet là A=1 và lastBeforeGet là C=3. afterEndReads vẫn hiển thị A,B,C.

Sau get(A), kết quả đọc là 1 và thứ tự thành B,C,A. Lúc này firstAfterGet là B=2. pollLeastRecent lấy B=2 ra, còn C,A.

Nếu đổi map sang chế độ mặc định theo thứ tự thêm khóa, không được mặc nhiên giữ dự đoán “get(A) làm A đi cuối”. Cần kiểm tra đúng constructor.

### 12.2. Chặn quyền sửa qua view không chặn tham chiếu nguồn

readOnly đọc được C=3 nhưng cả hai lời gọi poll đều bị từ chối. Helper chỉ bắt đúng UnsupportedOperationException để xác nhận điều kiện này; nó không che các lỗi khác bằng một catch chung.

Sau access.put(D,4) qua tham chiếu nguồn, readOnly nhìn thấy C,A,D. View này không cung cấp một lịch sử cố định của các ánh xạ tại lúc được tạo.

### 12.3. Kiểm tra từng loại thay đổi

Trong chương trình có ba hành động riêng:

1. Đọc entry ở hai đầu: không xóa và không tạo lượt truy cập của LinkedHashMap.
2. get(A) trong access-order: cập nhật thứ tự gặp của ánh xạ.
3. pollFirstEntry: xóa một ánh xạ tại đầu hiện tại.

Nếu chỉ so kích thước, hành động thứ hai sẽ bị bỏ sót vì số ánh xạ không đổi. Khi cần kiểm chứng đầu/cuối, hãy kiểm tra cả thứ tự chứ không chỉ size.

## 13. Mẫu áp dụng và giới hạn thực tế

### 13.1. Chỉ xem trước một ánh xạ

Đoạn sau là mã minh họa đặt trong một phương thức đã có biến pending kiểu SequencedMap<String,Integer> và import Map. Nó không phải tệp Java độc lập:

```java
Map.Entry<String, Integer> next = pending.firstEntry();
if (next != null) {
    System.out.println(next.getKey() + ":" + next.getValue());
}
```

Việc kiểm tra next khác null cho phép xử lý cả trường hợp giá trị Integer trong một ánh xạ hợp lệ là null. Mã không gọi phương thức trên một Entry rỗng.

Không đọc firstEntry rồi mặc nhiên tin nó vẫn là đầu sau những thay đổi tiếp theo của chương trình. Snapshot ghi nhận thông tin lúc gọi, không giữ vị trí của ánh xạ trong map.

### 13.2. Tiêu thụ lần lượt theo thứ tự hiện tại

Trong cùng ngữ cảnh có biến pending là map sửa được, đoạn minh họa này lấy lần lượt các ánh xạ ra khỏi đầu:

```java
Map.Entry<String, Integer> next;
while ((next = pending.pollFirstEntry()) != null) {
    System.out.println(next.getKey() + ":" + next.getValue());
}
```

Dùng chính kết quả poll để vừa kiểm tra còn dữ liệu vừa lấy cặp khóa–giá trị. Không cần một lần isEmpty riêng chỉ để quyết định có được đọc kết quả hay không.

Điều kiện của mẫu là chương trình cho phép xóa ánh xạ trước khi xử lý. Nếu công việc bên trong thất bại, ánh xạ đã bị lấy khỏi map; vòng lặp không có cơ chế xác nhận thành công, khôi phục hay thử lại. Những yêu cầu đó phải được thiết kế riêng.

Mẫu phù hợp với nguồn hữu hạn và điều kiện truy cập đã được kiểm soát. Nếu nơi khác liên tục thêm dữ liệu, không có bảo đảm vòng lặp sẽ kết thúc chỉ vì ban đầu map có một số ánh xạ hữu hạn.

### 13.3. Không biến cặp thao tác thành một giao dịch bằng suy đoán

SequencedMap không tự bảo đảm mọi triển khai an toàn cho nhiều luồng hoặc mọi thao tác kết hợp đều nguyên tử.

Một lần firstEntry rồi một lần pollFirstEntry là hai lời gọi. Nếu có thay đổi xen giữa, ánh xạ được xem trước có thể khác ánh xạ thực tế bị lấy ra. Ngay cả khi chỉ gọi poll, tính an toàn và nguyên tử khi nhiều luồng cùng thao tác phải được xác định theo lớp cụ thể; giao diện SequencedMap không đủ để kết luận.

LinkedHashMap và TreeMap trong các ví dụ không được dùng như cấu trúc tự đồng bộ. Nếu nhiều luồng chia sẻ chúng, phải thiết kế phối hợp truy cập thích hợp; không dựa vào snapshot Entry hay một ngoại lệ kiểm tra sửa đổi để thay thế việc đó.

### 13.4. Không poll trong lúc đang duyệt bằng iterator khác

Một vòng for-each qua entrySet dùng iterator. Poll map từ bên trong vòng đó là một đường sửa cấu trúc khác. Với LinkedHashMap hoặc TreeMap, điều này có thể làm phép duyệt vi phạm quy tắc sửa dữ liệu và gặp ConcurrentModificationException.

Nếu mục đích là tiêu thụ từ hai đầu, dùng vòng lặp poll riêng với quyền truy cập phù hợp. Nếu mục đích là duyệt và xóa qua iterator, tuân theo hợp đồng iterator của lớp đó. Không trộn hai cơ chế sửa một cách tùy ý.

Các ví dụ stdout cố định trong bài không phụ thuộc vào cạnh tranh giữa các luồng hay thứ tự phát hiện sửa đổi.

### 13.5. Không gán một chi phí chung chỉ từ giao diện

SequencedMap mô tả ý nghĩa đầu/cuối và kết quả trả về, không hứa mọi triển khai có cùng chi phí.

LinkedHashMap và TreeMap dùng các cấu trúc khác nhau. Một lớp tùy chỉnh còn có thể dựa vào triển khai mặc định qua iterator. Chọn cấu trúc theo cả chính sách thứ tự lẫn yêu cầu hiệu năng; không suy ra O(1) cho mọi firstEntry hoặc pollLastEntry chỉ vì tên phương thức ngắn.

Tương tự, snapshot trả về là một Entry, không phải một thao tác sao chép toàn bộ map hoặc nhân bản sâu mọi khóa/giá trị.

## 14. Các lỗi thường gặp

| Cách dùng hoặc kết luận | Vấn đề | Điều cần làm |
|---|---|---|
| Dùng poll để xem thử đầu map | Ánh xạ bị xóa nếu được hỗ trợ | Dùng firstEntry hoặc lastEntry |
| Mong firstEntry luôn có khóa nhỏ nhất | Thứ tự phụ thuộc map và Comparator | Xác định chính sách thứ tự thực tế |
| Gọi getValue ngay trên kết quả firstEntry | Kết quả có thể null khi rỗng | Kiểm tra Entry trước |
| Xem value null như không còn ánh xạ | Một ánh xạ hợp lệ có thể mang null | Phân biệt Entry null với value null |
| Dùng setValue trên snapshot để cập nhật map | Đây không phải entry sửa map | Dùng API cập nhật của map theo trạng thái hiện tại |
| Mong snapshot giữ giá trị mới nhất sau put | Snapshot ghi nhận ánh xạ lúc gọi | Đọc lại nếu cần thông tin hiện tại |
| Nghĩ snapshot sao chép sâu List giá trị | Tham chiếu List có thể còn được chia sẻ | Thiết kế bản sao giá trị nếu cần độc lập |
| Poll qua reversed rồi mong map gốc nguyên | View sửa được dùng chung dữ liệu | Tạo cấu trúc chứa riêng nếu cần tiêu thụ độc lập |
| Cho rằng mọi Entry lấy từ view đều giống firstEntry | Hợp đồng kết nối/setValue tùy đường lấy entry | Đọc hợp đồng API tạo entry |
| Mong poll đợi đến khi có ánh xạ | Đây không phải thao tác chờ | Xử lý kết quả rỗng theo hợp đồng |
| Kết luận có SequencedMap thì chắc poll được | Poll là thao tác tùy chọn | Kiểm tra hợp đồng quyền sửa |
| Dùng firstEntry rồi remove như một thao tác nguyên tử chung | Có thể có thay đổi xen giữa | Thiết kế đồng bộ hoặc chọn cấu trúc có hợp đồng phù hợp |
| Chỉ kiểm tra size của map access-order | Thứ tự có thể đổi mà size giữ nguyên | Kiểm tra cả thứ tự gặp |
| Mong Map.equals kiểm tra thứ tự giống nhau | Map so sánh các ánh xạ, không dùng thứ tự làm điều kiện equals | Kiểm tra dãy khóa/entry theo thứ tự khi đó là yêu cầu |

## 15. Tự kiểm tra và thực hành

### 15.1. Câu hỏi với đáp án

1. **firstEntry và pollFirstEntry khác nhau ở đâu?** Cùng chọn đầu hiện tại theo thứ tự của map; firstEntry chỉ đọc, pollFirstEntry còn xóa ánh xạ nếu thao tác được hỗ trợ.
2. **Khi map sửa được rỗng, bốn phương thức trả gì?** Trả null. Riêng khả năng không hỗ trợ thao tác xóa phải được xét độc lập với trạng thái rỗng.
3. **Một Entry không null có value null có chứng minh map rỗng không?** Không. Nó mô tả một ánh xạ có giá trị null.
4. **Snapshot được lấy lúc task=queued; sau put(task,running) snapshot có tự chuyển sang running không?** Không. Đọc lại map mới lấy thông tin của ánh xạ cập nhật.
5. **Vì sao sửa List qua một tham chiếu khác vẫn có thể thấy trong snapshot?** Snapshot giữ tham chiếu giá trị, không sao chép sâu đối tượng List.
6. **Có dùng setValue trên entry của firstEntry để sửa map được không?** Không theo hợp đồng snapshot này; các ví dụ chuẩn ném UnsupportedOperationException.
7. **pollFirstEntry trên view ngược của LinkedHashMap lấy phía nào của nguồn?** Phía cuối theo chiều map nguồn, đồng thời xóa ánh xạ đó khỏi nguồn.
8. **TreeMap với Comparator giảm có đầu mang khóa nhỏ nhất theo cách so số thông thường không?** Không. Ví dụ khóa 1,2,3 có đầu là 3 khi Comparator là reverseOrder.
9. **firstEntry trên LinkedHashMap access-order có tạo lượt truy cập như get không?** Không. Một lần get thành công có thể thay thứ tự theo cơ chế của lớp, còn thao tác xem entry ở hai đầu không tạo lượt truy cập đó.
10. **Entry snapshot có làm một chuỗi xem rồi xóa trở nên nguyên tử không?** Không. Cần hợp đồng đồng thời và cách phối hợp riêng.
11. **View unmodifiableSequencedMap có phải bản sao cố định không?** Không. Nó chặn sửa qua view, còn có thể nhìn thấy thay đổi của nguồn.
12. **Vì sao một biến Map trỏ tới LinkedHashMap vẫn không trực tiếp gọi được firstEntry ở mức biên dịch?** Kiểu khai báo Map không cung cấp phương thức đó; cần một kiểu API thể hiện hợp đồng thứ tự phù hợp.

### 15.2. Bài tập: dự đoán trạng thái sau mỗi poll

Tạo LinkedHashMap mặc định, lần lượt put K2=20, K1=10, K3=30.

Dự đoán rồi chạy: firstEntry, lastEntry, pollLastEntry, pollFirstEntry, firstEntry. Kỳ vọng các kết quả lần lượt là K2=20, K3=30, K3=30, K2=20, K1=10; cuối cùng map còn đúng K1=10.

Đổi hai lời gọi poll sang thao tác trên reversed và dự đoán lại trước khi chạy. Cần giải thích bằng chiều thứ tự, không chỉ sửa nhãn First thành Last theo thói quen.

### 15.3. Bài tập: snapshot với hai loại thay đổi

Tạo SequencedMap<String,List<String>> chứa một List có hai phần tử. Lấy firstEntry, rồi lần lượt:

1. Thay nội dung của chính List ban đầu.
2. put một List hoàn toàn khác vào cùng khóa.

Quan sát snapshot ở mỗi bước. Kỳ vọng bước 1 được nhìn thấy vì cùng đối tượng List; bước 2 không làm snapshot tự trỏ sang List mới.

Thử setValue trên snapshot và xác minh thao tác bị từ chối. Không dùng kết quả snapshot đó để kết luận map không sửa được.

### 15.4. Bài tập: chính sách thứ tự và quyền sửa

Dùng cùng tập ánh xạ số cho LinkedHashMap theo thứ tự thêm, LinkedHashMap access-order và TreeMap với Comparator giảm.

Giữ một bản in thứ tự trước/sau get một khóa, rồi kiểm tra firstEntry và lastEntry. Sau đó bọc một map bằng unmodifiableSequencedMap và thử riêng hai thao tác poll trên map còn dữ liệu.

Điều cần giải thích: đầu/cuối phụ thuộc chính sách, còn việc poll được hay không phụ thuộc quyền sửa; hai yếu tố này không thay thế cho nhau.

## 16. Nguồn đối chiếu và phạm vi kiểm chứng

- [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): hợp đồng bốn phương thức, snapshot Entry, view ngược và ý nghĩa thứ tự của ánh xạ.
- [LinkedHashMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): thứ tự thêm, thứ tự truy cập, các thao tác tạo lượt truy cập và reversed.
- [NavigableMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html): nguồn gốc các API đầu/cuối trên map sắp xếp, có từ Java 6.
- [TreeMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html): thứ tự theo khóa/Comparator và các entry snapshot.
- [Map.Entry — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.Entry.html): sự khác nhau giữa entry từ phép duyệt và entry không kết nối với map.
- [Collections — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): unmodifiableSequencedMap và quyền sửa qua view.

Năm chương trình đầy đủ đã biên dịch với `javac --release 21 -encoding UTF-8` và chạy trên JDK 21.0.9, cho đúng stdout được ghi. Các đoạn ở phần mẫu áp dụng được đánh dấu là minh họa, cần đặt trong phương thức có sẵn biến pending và import tương ứng. Chúng không được trình bày như tệp Java độc lập.
