# EnumMap: ánh xạ với khóa enum

## 1. Khi miền khóa là một tập hằng đã biết

Giả sử chương trình có ba giai đoạn `PLANNED`, `RUNNING`, `DONE`. Mỗi giai đoạn cần một nhãn hiển thị, số lượng công việc hoặc danh sách dữ liệu liên quan. Đây là một quan hệ **mỗi khóa enum ánh xạ đến một giá trị**, chứ không chỉ là một tập các giai đoạn đang được chọn.

`EnumMap<K,V>` là cách triển khai `Map` chuyên dùng khi toàn bộ khóa thuộc **một kiểu enum**. Ta vẫn dùng những thao tác quen thuộc như `put`, `get`, `remove`, `containsKey`, nhưng cấu trúc biết trước miền hằng của kiểu khóa.

Ví dụ, với `EnumMap<Stage, String>`, khóa là các hằng của `Stage`, còn giá trị là chuỗi. Với `EnumMap<Stage, List<Task>>`, cùng miền khóa đó được dùng để chia các công việc thành nhóm. Kiểu giá trị không bị giới hạn là enum; chỉ kiểu khóa có ràng buộc này.

Ba điều cần nắm trước khi viết mã:

1. Một EnumMap chỉ nhận khóa của một kiểu enum đã xác định khi tạo map.
2. Thứ tự duyệt là thứ tự khai báo hằng enum, không phải thứ tự gọi put.
3. Biết toàn bộ miền khóa không có nghĩa map đã chứa mapping cho mọi hằng.

Bài học sẽ bắt đầu từ một map rỗng, quan sát các thao tác và chính sách null, rồi đi đến sao chép, view và ứng dụng đếm/nhóm dữ liệu. Các chương trình đầy đủ dùng Java 17 trở lên.

## 2. Mối quan hệ giữa enum, EnumMap và Map

### 2.1. Khóa là hằng enum, không phải tên chuỗi của hằng

Với khai báo `enum Stage { PLANNED, RUNNING, DONE }`, các khóa hợp lệ của map giai đoạn là `Stage.PLANNED`, `Stage.RUNNING`, `Stage.DONE`. Chuỗi `"RUNNING"` không phải cùng kiểu với `Stage.RUNNING`.

`EnumMap` không tự chuyển chuỗi người dùng nhập thành hằng enum. Nếu đầu vào đến từ chuỗi, việc phân tích và kiểm tra giá trị phải xảy ra ở ranh giới đầu vào theo quy tắc ứng dụng. Không thay toàn bộ khóa bằng chuỗi chỉ để né việc mô hình hóa miền dữ liệu.

Hằng enum có định danh ổn định trong chính kiểu enum đó. Hai enum khác nhau có thể cùng khai báo tên `RUNNING` nhưng các hằng không vì thế trở thành cùng một khóa. Một EnumMap cho Stage không phải map chung cho mọi enum có tên hằng giống nhau.

### 2.2. Ràng buộc kiểu khóa

Chữ ký lớp là `EnumMap<K extends Enum<K>, V>`. Điều đó buộc K là kiểu enum thích hợp. Cách khởi tạo thường dùng, minh họa bên trong một phương thức, là:

```java
EnumMap<Stage, String> labels = new EnumMap<>(Stage.class);
```

`Stage.class` là đối tượng `Class` mô tả kiểu enum, không phải một khóa đang được chèn. Constructor dùng thông tin đó ngay cả khi map chưa có entry nào.

Nếu chỉ cần công bố khả năng ánh xạ cho phần mã sử dụng, có thể khai báo biến theo interface:

```java
// Minh họa, với Stage đã được khai báo.
Map<Stage, String> labels = new EnumMap<>(Stage.class);
```

Đối tượng vẫn là EnumMap và vẫn duyệt theo thứ tự khai báo enum. Kiểu biến Map cho biết phần mã sử dụng đang cần các thao tác map chung; nó không thay đổi cách đối tượng thực tế lưu và duyệt dữ liệu.

### 2.3. Không trộn nhiều kiểu enum trong một EnumMap

Generics thông thường giúp phát hiện việc truyền sai kiểu khóa ngay lúc biên dịch. Không bỏ generics hoặc dùng raw type để chèn một enum không thuộc miền khóa. Việc ép kiểu không biến hằng của enum khác thành hằng hợp lệ của enum mà map đã chọn.

Đối với việc tìm kiếm bằng `get(Object)` hay `containsKey(Object)`, một đối tượng không phải khóa của miền này không tự được diễn giải từ tên của nó. API nhận Object không có nghĩa map trở thành một bảng tra cứu chuỗi hoặc một kho khóa tùy ý.

Nếu phải lấy kiểu enum từ một hằng ở mã tổng quát, API thích hợp là `getDeclaringClass()`. Không mặc định `constant.getClass()` luôn chính là lớp enum khai báo, vì một hằng có phần thân riêng có thể có lớp thực thi riêng. Với mã cụ thể như các ví dụ, truyền trực tiếp `Stage.class` là rõ ràng nhất. Có thể đối chiếu tại [Enum — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html).

## 3. Cơ chế và thứ tự duyệt

### 3.1. Miền enum hữu hạn giúp dùng biểu diễn chuyên biệt

Tài liệu [EnumMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html) mô tả cách biểu diễn nội bộ dựa trên mảng. Vì map biết một kiểu enum và tập hằng của kiểu đó, nó có thể liên kết mỗi hằng với vị trí tương ứng trong cấu trúc chuyên biệt.

Điều này khác với việc phải hỗ trợ các đối tượng khóa tùy ý như một map tổng quát. Người dùng không cần tự tạo mảng rồi tự dùng `ordinal()` ở mọi nơi để tìm ô chứa giá trị. EnumMap cung cấp hợp đồng Map đầy đủ cho việc thêm, xóa, kiểm tra tồn tại và các view.

`ordinal()` là vị trí hằng trong khai báo enum và được thiết kế cho các cấu trúc chuyên biệt như thế này. Không vì hiểu cơ chế bên trong mà dùng ordinal làm mã nghiệp vụ hoặc định danh lưu trữ dài hạn: thay thứ tự khai báo có thể làm các số vị trí thay đổi.

### 3.2. Thứ tự là thứ tự khai báo, không phải chữ cái hoặc lần chèn

Với `Stage { PLANNED, RUNNING, DONE }`, thứ tự duyệt các khóa đang có luôn bám theo chuỗi khai báo đó. Dù chèn DONE trước, PLANNED sau và RUNNING cuối, map vẫn duyệt PLANNED, RUNNING, DONE.

Các view `keySet()`, `values()`, `entrySet()` đều phản ánh thứ tự khóa này. View giá trị được duyệt theo khóa tương ứng; nó không tự sắp các chuỗi hoặc các con số giá trị.

`EnumMap` không có constructor nhận comparator để chọn lại thứ tự. Có thứ tự duyệt không có nghĩa nó triển khai `SortedMap` hay `NavigableMap`; không có các phép như `lowerKey`, `subMap` hay `descendingMap` chỉ vì kết quả in nhìn có trật tự.

Nếu một màn hình cần thứ tự trình bày khác thứ tự enum, hãy xác định thứ tự trình bày riêng cho lượt xuất dữ liệu. Không đổi thứ tự khai báo enum một cách tùy tiện chỉ để tác động đến một dòng hiển thị mà chưa xét các nơi khác phụ thuộc nó.

### 3.3. Map ban đầu vẫn rỗng

`new EnumMap<>(Stage.class)` chỉ xác định miền khóa. Nó không tự thêm ba mapping và không tự gán giá trị mặc định cho các hằng.

Nếu mới put RUNNING, kích thước là một và chỉ RUNNING xuất hiện khi duyệt. Biết rằng PLANNED và DONE là những khóa có thể dùng khác với việc map đang có dữ liệu cho chúng.

## 4. Chương trình 1: tạo map và quan sát các thao tác

Lưu chương trình đầy đủ vào `EnumMapBasicsDemo.java`:

```java
import java.util.EnumMap;
import java.util.Map;

public class EnumMapBasicsDemo {
    enum Stage { PLANNED, RUNNING, DONE }

    public static void main(String[] args) {
        EnumMap<Stage, String> labels = new EnumMap<>(Stage.class);
        System.out.println("initialSize=" + labels.size());
        labels.put(Stage.DONE, "finished");
        labels.put(Stage.PLANNED, "waiting");
        labels.put(Stage.RUNNING, "working");
        System.out.println("labels=" + labels);
        System.out.println("keys=" + labels.keySet());
        System.out.println("values=" + labels.values());
        System.out.println("oldValue=" + labels.put(Stage.RUNNING, "active"));
        System.out.println("sizeAfterUpdate=" + labels.size());
        System.out.println("running=" + labels.get(Stage.RUNNING));
        for (Map.Entry<Stage, String> entry : labels.entrySet()) {
            System.out.println(entry.getKey() + ":" + entry.getValue());
        }
        System.out.println("removed=" + labels.remove(Stage.PLANNED));
        System.out.println("remaining=" + labels);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumMapBasicsDemo.java
java EnumMapBasicsDemo
```

Stdout:

```text
initialSize=0
labels={PLANNED=waiting, RUNNING=working, DONE=finished}
keys=[PLANNED, RUNNING, DONE]
values=[waiting, working, finished]
oldValue=working
sizeAfterUpdate=3
running=active
PLANNED:waiting
RUNNING:active
DONE:finished
removed=waiting
remaining={RUNNING=active, DONE=finished}
```

### 4.1. Thứ tự chèn và thứ tự kết quả

`initialSize=0` xác nhận constructor không tạo mapping cho tất cả hằng. Các lời gọi put theo thứ tự DONE, PLANNED, RUNNING nhưng dòng `labels` và `keys` vẫn theo khai báo PLANNED, RUNNING, DONE.

`values=[waiting, working, finished]` đi cùng thứ tự khóa. Nó không được sắp theo thứ tự chữ cái của chuỗi và cũng không theo thời điểm chuỗi được đưa vào map.

### 4.2. Cập nhật cùng khóa và loại mapping

`put(Stage.RUNNING, "active")` trả giá trị cũ `working`. Map vẫn có ba mapping; khóa RUNNING không bị tạo thêm một bản thứ hai và không chuyển xuống cuối như thứ tự chèn.

Vòng duyệt entry cho thấy giá trị mới active nằm đúng tại RUNNING. `remove(Stage.PLANNED)` trả waiting và loại mapping đó, sau đó map chỉ còn RUNNING và DONE theo đúng thứ tự tương đối vốn có.

Những quy tắc cơ bản vẫn là Map: một khóa tương ứng nhiều nhất một mapping; put khóa đã có thay giá trị; remove loại mapping chứ không xóa hằng enum khỏi ngôn ngữ hay khỏi kiểu Stage.

## 5. Null và việc thiếu mapping

### 5.1. Không nhận khóa null nhưng nhận giá trị null

EnumMap từ chối `put(null, value)` bằng `NullPointerException`. Null không phải hằng của kiểu enum mà map đã chọn.

Tuy nhiên, map cho phép mapping có giá trị null. Vì vậy, sau `put(Day.MON, null)`, khóa MON vẫn đang có mapping và được tính vào `size()`.

Các thao tác kiểm tra hoặc loại khóa null không có cùng hành vi với chèn khóa null: với EnumMap, `containsKey(null)` trả false, `get(null)` trả null và `remove(null)` trả null. Không suy ra rằng mọi phương thức nhận null đều nhất thiết ném lỗi, cũng không suy ra từ việc get(null) chạy được rằng put(null, ...) được phép.

### 5.2. Ba trạng thái cần phân biệt

| Trạng thái theo một khóa enum hợp lệ | `get(key)` | `containsKey(key)` | Có tính vào size không? |
|---|---|---|---|
| Chưa có mapping | null | false | Không |
| Có mapping với giá trị null | null | true | Có |
| Có mapping với giá trị khác null | Giá trị đó | true | Có |

`getOrDefault` chỉ dùng mặc định khi không có mapping. Nó không thay giá trị null của một mapping đang tồn tại bằng mặc định.

Ngược lại, các phương thức như `putIfAbsent`, `computeIfAbsent`, `merge` có các quy tắc riêng liên quan đến giá trị null. Không thể dùng một câu “có khóa rồi thì mọi thao tác đều giữ nguyên” để mô tả tất cả chúng. Trong ví dụ tiếp theo, putIfAbsent sẽ xem mapping giá trị null là trường hợp có thể đặt giá trị.

### 5.3. Đủ khóa và đủ giá trị là hai yêu cầu khác nhau

Nếu ứng dụng đòi hỏi mọi ngày đều có cấu hình, cần kiểm tra tất cả hằng có mapping. Nếu còn đòi hỏi cấu hình khác null, phải kiểm tra thêm điều kiện giá trị.

Một EnumMap có số mapping bằng số hằng của miền khóa đã có mapping cho mọi hằng, nhưng vẫn có thể có giá trị null. Ngược lại, các mapping hiện có đều khác null chưa chứng minh mọi hằng đã được phủ.

## 6. Chương trình 2: giá trị null và kiểm tra độ phủ khóa

Lưu vào `EnumMapNullCoverageDemo.java`. `EnumSet` được dùng để tính các ngày chưa có mapping; nó không thay thế EnumMap chứa lịch.

```java
import java.util.EnumMap;
import java.util.EnumSet;

public class EnumMapNullCoverageDemo {
    enum Day { MON, TUE, WED }

    public static void main(String[] args) {
        EnumMap<Day, String> schedule = new EnumMap<>(Day.class);
        schedule.put(Day.MON, null);
        schedule.put(Day.WED, "work");
        System.out.println("monGet=" + schedule.get(Day.MON));
        System.out.println("monPresent=" + schedule.containsKey(Day.MON));
        System.out.println("tueGet=" + schedule.get(Day.TUE));
        System.out.println("tuePresent=" + schedule.containsKey(Day.TUE));
        System.out.println("size=" + schedule.size());
        System.out.println("monDefault=" + schedule.getOrDefault(Day.MON, "off"));
        System.out.println("tueDefault=" + schedule.getOrDefault(Day.TUE, "off"));
        System.out.println("nullGet=" + schedule.get(null));
        System.out.println("nullPresent=" + schedule.containsKey(null));
        System.out.println("nullRemove=" + schedule.remove(null));
        try {
            schedule.put(null, "invalid");
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("nullPut=NullPointerException");
        }
        EnumSet<Day> missing = EnumSet.allOf(Day.class);
        missing.removeAll(schedule.keySet());
        System.out.println("missingMappings=" + missing);
        System.out.println("oldNullValue=" + schedule.putIfAbsent(Day.MON, "study"));
        System.out.println("afterPutIfAbsent=" + schedule);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumMapNullCoverageDemo.java
java EnumMapNullCoverageDemo
```

Stdout:

```text
monGet=null
monPresent=true
tueGet=null
tuePresent=false
size=2
monDefault=null
tueDefault=off
nullGet=null
nullPresent=false
nullRemove=null
nullPut=NullPointerException
missingMappings=[TUE]
oldNullValue=null
afterPutIfAbsent={MON=study, WED=work}
```

### 6.1. MON có mapping, TUE không có mapping

Cả `monGet` lẫn `tueGet` đều in null, nhưng `monPresent=true` còn `tuePresent=false`. `size=2` đếm MON và WED.

`monDefault=null` vì MON đã có mapping null. `tueDefault=off` vì TUE chưa có mapping. Đây là khác biệt thiết yếu khi viết cấu hình mặc định hoặc kiểm tra dữ liệu thiếu.

### 6.2. Tính tập khóa còn thiếu

`EnumSet.allOf(Day.class)` tạo tập tất cả hằng Day. Loại các khóa đang có trong schedule để lại `[TUE]`. MON không bị đánh dấu thiếu mapping dù giá trị của nó là null.

Nếu quy tắc là mọi ngày phải có chuỗi lịch khác null, phép kiểm tra này chưa đủ; cần xét giá trị của từng ngày. EnumMap không tự biết một giá trị null có hợp lệ về nghiệp vụ hay không.

### 6.3. putIfAbsent với giá trị cũ null

`putIfAbsent(Day.MON, "study")` trả null và đặt MON thành study. Số mapping không tăng vì MON đã có; nội dung giá trị thay đổi vì chính sách của putIfAbsent áp dụng cả trường hợp khóa đang ánh xạ tới null.

Khi quyết định cho phép giá trị null trong API của ứng dụng, phải tính cả ảnh hưởng lên các phương thức Map được dùng thêm. Một lớp bọc có thể chọn cấm giá trị null để hợp đồng đơn giản hơn, nhưng đó là chính sách bổ sung của ứng dụng, không phải giới hạn vốn có của EnumMap.

## 7. Chọn đúng constructor khi tạo hoặc sao chép

### 7.1. Biết trước kiểu khóa: truyền Class của enum

Constructor `EnumMap(Class<K> keyType)` tạo map rỗng với miền khóa đã xác định. Đây là lựa chọn rõ ràng khi khởi tạo cấu hình, bảng nhãn hoặc nhóm dữ liệu mới.

Không có constructor không đối số kiểu `new EnumMap<Stage, String>()`. Thông tin generic trong mã nguồn không tự thay thế được thông tin Class cần ở lúc chạy để cấu trúc biết miền hằng.

`Stage.class` có thể dùng dù chưa có bất kỳ mapping hay hằng nào được đưa vào map. Một kiểu enum không khai báo hằng nào cũng có thể có một EnumMap rỗng theo kiểu đó; biết kiểu và có phần tử là hai vấn đề riêng.

### 7.2. Sao chép từ EnumMap

Constructor nhận một EnumMap lấy được kiểu khóa từ chính map nguồn, nên map nguồn rỗng vẫn hợp lệ. Nó tạo cấu trúc map mới ban đầu có cùng mapping nếu có.

Điều này hữu ích khi muốn một bản cấu hình có thể sửa độc lập về mapping với bản hiện tại. Tuy nhiên, giá trị là đối tượng có thể thay đổi thì các bản map vẫn có thể chia sẻ tham chiếu; constructor không sao chép sâu dữ liệu bên trong giá trị.

`clone()` của EnumMap cũng được mô tả là bản sao nông. Trong các ví dụ, constructor copy được dùng để ý định tạo một map mới hiện rõ ngay tại nơi khai báo.

### 7.3. Sao chép từ Map tổng quát

Constructor `EnumMap(Map<K, ? extends V> source)` có hai trường hợp:

| Đối tượng nguồn thực tế | Có thể rỗng không? | Cách xác định miền enum |
|---|---|---|
| Là một EnumMap | Có | Lấy kiểu khóa đã được EnumMap nguồn giữ |
| Là map khác, chẳng hạn HashMap | Không | Cần ít nhất một mapping để xác định kiểu enum từ khóa |

Vì vậy, không đúng khi nói mọi constructor nhận Map đều từ chối map rỗng. Một biến được khai báo là Map nhưng đang trỏ đến EnumMap rỗng vẫn được xử lý như nguồn EnumMap.

Ngược lại, một `HashMap<Size, String>` rỗng vẫn không cung cấp một khóa thực tế để suy ra enum ở lúc chạy, dù người viết mã nhìn thấy Size trong generic. Constructor ném `IllegalArgumentException` thay vì tự đoán kiểu.

### 7.4. Khi nguồn có thể rỗng, truyền kiểu rõ ràng rồi putAll

Nếu hàm đã biết kiểu khóa Size nhưng nhận một Map nguồn có thể rỗng, có thể tạo `new EnumMap<>(Size.class)` trước rồi `putAll(source)`. Việc chép một nguồn rỗng vào map đã biết miền khóa là hợp lệ.

Đây là cách tách hai trách nhiệm: xác định miền khóa bằng Class, sau đó đưa các mapping hiện có vào. Không cần thêm một mapping giả chỉ để làm constructor suy ra kiểu.

## 8. Chương trình 3: các trường hợp constructor và tính độc lập

Lưu chương trình đầy đủ vào `EnumMapConstructorsDemo.java`:

```java
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Map;

public class EnumMapConstructorsDemo {
    enum Size { SMALL, MEDIUM, LARGE }

    public static void main(String[] args) {
        EnumMap<Size, String> empty = new EnumMap<>(Size.class);
        EnumMap<Size, String> directCopy = new EnumMap<>(empty);
        Map<Size, String> emptyAsMap = empty;
        EnumMap<Size, String> runtimeEnumCopy = new EnumMap<>(emptyAsMap);
        System.out.println("emptyDirectCopy=" + directCopy.size());
        System.out.println("emptyRuntimeEnumCopy=" + runtimeEnumCopy.size());
        try {
            new EnumMap<Size, String>(new HashMap<Size, String>());
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("emptyHashCopy=IllegalArgumentException");
        }
        Map<Size, String> source = new HashMap<>();
        source.put(Size.LARGE, "L");
        source.put(Size.SMALL, "S");
        EnumMap<Size, String> inferred = new EnumMap<>(source);
        System.out.println("inferred=" + inferred);
        source.put(Size.SMALL, "S2");
        inferred.put(Size.MEDIUM, "M");
        System.out.println("sourceSmall=" + source.get(Size.SMALL));
        System.out.println("copiedSmall=" + inferred.get(Size.SMALL));
        System.out.println("sourceHasMedium=" + source.containsKey(Size.MEDIUM));
        System.out.println("independentCopy=" + inferred);
        EnumMap<Size, String> explicit = new EnumMap<>(Size.class);
        explicit.putAll(new HashMap<Size, String>());
        System.out.println("explicitWithEmptySource=" + explicit.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumMapConstructorsDemo.java
java EnumMapConstructorsDemo
```

Stdout:

```text
emptyDirectCopy=0
emptyRuntimeEnumCopy=0
emptyHashCopy=IllegalArgumentException
inferred={SMALL=S, LARGE=L}
sourceSmall=S2
copiedSmall=S
sourceHasMedium=false
independentCopy={SMALL=S, MEDIUM=M, LARGE=L}
explicitWithEmptySource=0
```

### 8.1. Hai cách chép EnumMap rỗng đều chạy được

`emptyDirectCopy=0` là bản sao từ biến EnumMap. `emptyRuntimeEnumCopy=0` là bản sao từ biến Map đang trỏ đến chính EnumMap rỗng. Cả hai thành công vì đối tượng nguồn giữ được miền Size.

`emptyHashCopy=IllegalArgumentException` cho thấy trường hợp khác: HashMap rỗng không giữ miền enum theo cơ chế chuyên biệt đó để EnumMap suy ra.

### 8.2. Nguồn không rỗng được chép theo thứ tự enum

Nguồn HashMap có SMALL và LARGE. Khi tạo inferred, map mới có `{SMALL=S, LARGE=L}` theo thứ tự khai báo Size, không phụ thuộc thứ tự duyệt của HashMap nguồn. Ví dụ không in cả HashMap để tránh dùng một thứ tự mà HashMap không bảo đảm.

Sau đó, sửa SMALL trong source thành S2 không thay mapping SMALL trong bản sao. Thêm MEDIUM vào inferred không tự thêm MEDIUM vào source. Dòng `independentCopy` cho đủ ba mapping theo thứ tự SMALL, MEDIUM, LARGE.

Cuối cùng, tạo map có Size.class rồi putAll một HashMap rỗng cho kích thước 0, hoàn toàn hợp lệ. Cách này cũng dùng được khi nguồn có dữ liệu phù hợp.

## 9. Các view của EnumMap

### 9.1. keySet, values, entrySet nhìn cùng dữ liệu

Các view của EnumMap là các cửa nhìn liên kết với map, không phải collection sao chép. Một lần thêm hoặc loại mapping trong map sẽ được phản ánh khi xem các view đã lấy trước đó.

| View | Phần tử | Thứ tự duyệt |
|---|---|---|
| `keySet()` | Hằng enum đang có mapping | Thứ tự khai báo enum |
| `values()` | Giá trị của các mapping | Theo thứ tự khóa tương ứng |
| `entrySet()` | Cặp khóa–giá trị | Theo thứ tự khóa enum |

Map không tự chứa mọi hằng thì keySet cũng không tự là tập tất cả hằng. Khi cần toàn miền, dùng `values()` của kiểu enum hoặc một EnumSet tất cả hằng; đừng nhầm `Stage.values()` với `labels.values()`.

### 9.2. Xóa qua view tác động đến map

`keys.remove(enumKey)` loại mapping của khóa đó. `values.remove(value)` loại một mapping có giá trị tương ứng theo hành vi collection view, không có nghĩa xóa mọi mapping cùng giá trị. `clear()` qua một view hỗ trợ xóa sẽ làm các mapping tương ứng rời map.

View khóa không hỗ trợ `add` hay `addAll`. Một khóa riêng không mô tả giá trị cần gán cho mapping. Muốn thêm, dùng `put` với cả khóa và giá trị. Không suy ra rằng map sửa được thì mọi phương thức sửa của mọi view đều được hỗ trợ.

### 9.3. Cập nhật qua entry đang duyệt

Trong một lượt duyệt `entrySet()` của EnumMap, có thể dùng `entry.setValue(newValue)` để cập nhật giá trị của mapping tương ứng. Khi làm vậy, khóa vẫn là cùng hằng enum và thứ tự không đổi.

Không giữ một entry lấy từ iterator rồi mặc định nó là một bản sao bền vững sau các lần thay đổi cấu trúc. Nếu cần ghi nhớ dữ liệu độc lập, hãy sao chép thành dữ liệu có hợp đồng phù hợp thay vì dựa vào vòng đời kết nối không được thiết kế cho mục đích đó.

## 10. Chương trình 4: view liên kết, cập nhật entry và Map.equals

Lưu vào `EnumMapViewsDemo.java`. Mọi thao tác được thực hiện tuần tự; ví dụ không dựa vào việc iterator có nhìn thấy hay bỏ qua thay đổi cấu trúc xen giữa.

```java
import java.util.Collection;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class EnumMapViewsDemo {
    enum Mode { FAST, SAFE, DEBUG }

    public static void main(String[] args) {
        EnumMap<Mode, Integer> map = new EnumMap<>(Mode.class);
        map.put(Mode.DEBUG, 30);
        map.put(Mode.SAFE, 10);
        map.put(Mode.FAST, 10);
        Set<Mode> keys = map.keySet();
        Collection<Integer> values = map.values();
        System.out.println("initial=" + map);
        System.out.println("removeSafe=" + keys.remove(Mode.SAFE));
        System.out.println("removeValue10=" + values.remove(10));
        System.out.println("afterViewRemovals=" + map);
        map.put(Mode.SAFE, 20);
        System.out.println("sameKeyView=" + keys);
        System.out.println("sameValueView=" + values);
        for (Map.Entry<Mode, Integer> entry : map.entrySet()) {
            entry.setValue(entry.getValue() + 1);
        }
        System.out.println("afterEntryUpdate=" + map);
        try {
            keys.add(Mode.FAST);
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("keyAdd=UnsupportedOperationException");
        }
        Map<Mode, Integer> hash = new HashMap<>(map);
        System.out.println("enumEqualsHash=" + map.equals(hash));
        System.out.println("hashEqualsEnum=" + hash.equals(map));
        EnumMap<Mode, Integer> copy = new EnumMap<>(map);
        map.clear();
        System.out.println("keyViewAfterClear=" + keys);
        System.out.println("valueViewAfterClear=" + values);
        System.out.println("copyAfterClear=" + copy);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumMapViewsDemo.java
java EnumMapViewsDemo
```

Stdout:

```text
initial={FAST=10, SAFE=10, DEBUG=30}
removeSafe=true
removeValue10=true
afterViewRemovals={DEBUG=30}
sameKeyView=[SAFE, DEBUG]
sameValueView=[20, 30]
afterEntryUpdate={SAFE=21, DEBUG=31}
keyAdd=UnsupportedOperationException
enumEqualsHash=true
hashEqualsEnum=true
keyViewAfterClear=[]
valueViewAfterClear=[]
copyAfterClear={SAFE=21, DEBUG=31}
```

### 10.1. Xóa qua khóa và qua giá trị

Map được chèn DEBUG, SAFE, FAST nhưng in `{FAST=10, SAFE=10, DEBUG=30}`. Xóa SAFE qua keys loại đúng mapping SAFE=10.

Sau đó, values chỉ còn một giá trị 10 ứng với FAST. `values.remove(10)` loại mapping đó, để map chỉ còn DEBUG=30. Lệnh này không trả giá trị bị xóa mà trả boolean cho biết collection đã thay đổi.

Thêm SAFE=20 qua map làm các view cũ in `[SAFE, DEBUG]` và `[20, 30]`, phản ánh trạng thái mới theo thứ tự enum.

### 10.2. Thay giá trị không đổi khóa

Vòng duyệt entry cộng một vào từng giá trị hiện có, tạo `{SAFE=21, DEBUG=31}`. Đây là cập nhật hai giá trị đang có, không tạo hai khóa mới hoặc làm đầy mọi hằng còn thiếu. FAST vẫn chưa có mapping.

`keys.add(Mode.FAST)` bị từ chối bằng `UnsupportedOperationException`. Muốn thêm FAST cần chỉ rõ giá trị bằng một lệnh put.

### 10.3. Bằng nhau với map khác và bản sao

HashMap được tạo từ map hiện tại có cùng các mapping nên hai chiều equals đều true. Phép bằng nhau của Map không đòi hai đối tượng cùng cách triển khai, và cũng không kiểm tra cùng thứ tự duyệt.

EnumMap copy được tạo trước clear giữ SAFE=21 và DEBUG=31. Sau `map.clear()`, các view cũ của map gốc rỗng nhưng copy còn dữ liệu. View và bản sao là hai quan hệ khác nhau.

## 11. Iterator nhất quán yếu không có nghĩa map an toàn cho nhiều luồng

Iterator từ các collection view của EnumMap được mô tả là **nhất quán yếu (weakly consistent)**: nó không ném `ConcurrentModificationException`, và có thể có hoặc không phản ánh các sửa đổi xảy ra trong lúc lượt duyệt đang diễn ra.

Không nên viết một ví dụ có thêm/xóa xen giữa rồi đưa ra một stdout duy nhất như bảo đảm cho mọi môi trường nếu hợp đồng cho phép nhiều khả năng quan sát. Các ví dụ ở đây giữ thao tác theo giai đoạn rõ ràng để kết quả xác định.

Việc không có ngoại lệ không chứng minh map đã có cơ chế đồng bộ. EnumMap không tự đồng bộ cho truy cập nhiều luồng. Nếu có luồng sửa trong khi các luồng khác dùng cùng map, cần một thiết kế phối hợp toàn bộ các đường truy cập.

Đặc biệt, những chuỗi như kiểm tra thiếu rồi put, hoặc lấy số đếm rồi cộng và ghi lại, không tự trở thành nguyên tử vì cấu trúc là EnumMap. Các phương thức mặc định Map như merge hay computeIfAbsent trên cấu trúc này cũng không tự mang bảo đảm cập nhật đồng thời của một concurrent map.

Nếu chương trình cần một bản dữ liệu nhất quán để xử lý, việc tạo bản sao cũng phải diễn ra dưới điều kiện truy cập phù hợp. Sao chép trong khi nguồn bị sửa mà không phối hợp không tự tạo một giao dịch chụp dữ liệu.

## 12. Ứng dụng: đếm và nhóm dữ liệu theo enum

### 12.1. Số đếm đầy đủ và nhóm chỉ tạo khi cần

Một luồng sự kiện có mức LOW, MEDIUM, HIGH thường cần hai dạng dữ liệu:

- Số đếm cho mọi mức, kể cả mức chưa xuất hiện.
- Danh sách thông điệp ở những mức thật sự có sự kiện.

Cả hai dùng miền khóa Severity nhưng có chính sách khởi tạo khác. Map đếm được điền 0 cho tất cả hằng ngay từ đầu. Map nhóm bắt đầu rỗng và chỉ tạo danh sách khi gặp mức tương ứng.

Lưu chương trình đầy đủ vào `EnumMapGroupingDemo.java`:

```java
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;

public class EnumMapGroupingDemo {
    enum Severity { LOW, MEDIUM, HIGH }
    record Event(Severity severity, String message) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event(Severity.HIGH, "server"),
                new Event(Severity.LOW, "typo"),
                new Event(Severity.HIGH, "disk"));
        EnumMap<Severity, Integer> counts = new EnumMap<>(Severity.class);
        for (Severity severity : Severity.values()) {
            counts.put(severity, 0);
        }
        EnumMap<Severity, List<String>> groups = new EnumMap<>(Severity.class);
        for (Event event : events) {
            counts.merge(event.severity(), 1, Integer::sum);
            groups.computeIfAbsent(event.severity(), key -> new ArrayList<>())
                    .add(event.message());
        }
        System.out.println("counts=" + counts);
        System.out.println("groups=" + groups);
        System.out.println("independentLists="
                + (groups.get(Severity.LOW) != groups.get(Severity.HIGH)));
        for (Severity severity : Severity.values()) {
            System.out.println(severity + ": count=" + counts.get(severity)
                    + ", messages=" + groups.getOrDefault(severity, List.of()));
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumMapGroupingDemo.java
java EnumMapGroupingDemo
```

Stdout:

```text
counts={LOW=1, MEDIUM=0, HIGH=2}
groups={LOW=[typo], HIGH=[server, disk]}
independentLists=true
LOW: count=1, messages=[typo]
MEDIUM: count=0, messages=[]
HIGH: count=2, messages=[server, disk]
```

### 12.2. Tại sao MEDIUM vẫn được in dù không có sự kiện?

Dữ liệu đầu vào chỉ có HIGH, LOW, HIGH. Vòng lặp qua `Severity.values()` đã tạo mapping đếm cho cả LOW, MEDIUM, HIGH, nên kết quả đếm có MEDIUM=0.

Map groups không được điền sẵn mọi khóa. `computeIfAbsent` chỉ tạo danh sách cho LOW và HIGH khi gặp sự kiện. Vì chưa có MEDIUM, groups không chứa khóa này. Khi trình bày kết quả, `getOrDefault(severity, List.of())` cung cấp danh sách rỗng để đọc.

Map đếm và map nhóm không mâu thuẫn. Chúng có cùng miền khóa nhưng được dùng để biểu diễn hai loại thông tin với chính sách thiếu mapping khác nhau.

### 12.3. merge cập nhật số đếm

`counts.merge(severity, 1, Integer::sum)` cộng một vào số đếm khác null đang có. Trong ví dụ, mọi mức đã được khởi tạo bằng 0, nên sau ba sự kiện ta có LOW=1, MEDIUM=0, HIGH=2.

Theo hợp đồng Map, nếu một khóa chưa có hoặc đang gắn với null, merge dùng giá trị được cung cấp để thiết lập mapping thay vì gọi hàm gộp như trường hợp giá trị khác null. Giá trị truyền làm đối số merge trong ví dụ là 1, khác null.

Việc dùng merge ở đây làm rõ thao tác cập nhật trong mã tuần tự. Nó không biến EnumMap thành một cấu trúc cập nhật đồng thời nguyên tử.

### 12.4. Mỗi nhóm cần một danh sách riêng

`key -> new ArrayList<>()` tạo danh sách mới khi một mức chưa có danh sách khác null. Các sự kiện HIGH được thêm vào cùng danh sách của HIGH theo thứ tự xuất hiện: server rồi disk.

`independentLists=true` chứng minh LOW và HIGH không trỏ cùng một danh sách. Nếu dùng một danh sách mutable chung làm giá trị cho mọi khóa, thêm thông điệp cho một mức sẽ làm các mức khác nhìn thấy cùng thông điệp qua tham chiếu chung.

`List.of()` trong getOrDefault chỉ dùng làm kết quả rỗng để đọc khi thiếu nhóm. Nó không được put vào groups rồi gọi add, và không được dùng thay cho ArrayList cần thay đổi.

Thứ tự khóa LOW, MEDIUM, HIGH do enum quyết định; thứ tự thông điệp bên trong từng List do cách xử lý dữ liệu đầu vào quyết định. EnumMap không tự sắp xếp phần tử bên trong giá trị.

## 13. Chọn đúng cấu trúc cho miền enum

| Nhu cầu | Cấu trúc phù hợp để cân nhắc | Điều cần phân biệt |
|---|---|---|
| Mỗi hằng enum gắn một giá trị | `EnumMap<E,V>` | Có quan hệ khóa–giá trị |
| Chỉ ghi nhận những hằng nào được chọn | `EnumSet<E>` | Chỉ cần có/không, không có giá trị V riêng |
| Khóa thuộc nhiều loại hoặc miền khóa mở | Map tổng quát theo yêu cầu | Không phải miền khóa của một enum duy nhất |
| Cần tra lân cận hoặc phạm vi theo comparator riêng | Map có thứ tự điều hướng phù hợp | EnumMap không cung cấp API NavigableMap |

EnumMap thường là điểm bắt đầu hợp lý khi yêu cầu đúng là ánh xạ theo một kiểu enum. Biểu diễn mảng giúp tận dụng miền khóa hữu hạn; các thao tác cơ bản có chi phí hằng số theo mô tả triển khai. Tuy nhiên, không được biến điều này thành khẳng định mọi chương trình đều nhanh hơn mọi cách dùng HashMap.

Việc duyệt, sao chép hoặc xử lý các giá trị lớn vẫn có chi phí riêng. Một EnumMap chứa danh sách dài không làm công việc trên các danh sách trở thành hằng số. Khi hiệu năng là yêu cầu cụ thể, cần đo đúng thao tác và dữ liệu sử dụng.

### 13.1. Bảng ánh xạ không tự kiểm tra tính đầy đủ như một biểu thức lựa chọn

EnumMap thích hợp cho bảng nhãn, cấu hình theo trạng thái, nhóm dữ liệu và có thể cả bảng hằng enum ánh xạ đến hàm xử lý. Tuy nhiên, tạo map không khiến trình biên dịch buộc mọi hằng phải có mapping.

Khi thêm một hằng enum mới, bảng ánh xạ có thể vẫn biên dịch nhưng thiếu cấu hình cho hằng đó. Nếu API yêu cầu bảng đầy đủ, hãy kiểm tra miền hằng tại lúc khởi tạo hoặc bằng phép kiểm tra phù hợp, thay vì chờ đến khi get trả null ở một đường xử lý hiếm gặp.

### 13.2. Quyền sửa và chia sẻ dữ liệu

Khai báo biến là `Map` không làm dữ liệu chỉ đọc. Trả trực tiếp EnumMap hoặc view khóa cho nơi khác có thể trao quyền sửa hoặc xóa mapping. Nếu API cần quyền đọc giới hạn hoặc một bản dữ liệu riêng, phải thiết kế kết quả trả về theo đúng yêu cầu đó.

Cũng cần phân biệt thay mapping với thay đối tượng giá trị. Một bản copy EnumMap độc lập về cấu trúc vẫn có thể giữ cùng List hoặc đối tượng cấu hình với nguồn. Khi cần tách cả dữ liệu mutable, phải sao chép giá trị theo hợp đồng của kiểu đó.

## 14. Kiểm tra một bảng EnumMap

### 14.1. Các kiểm tra đáng làm

1. Map tạo bằng Class ban đầu rỗng và nhận đúng miền enum.
2. Chèn theo thứ tự bất kỳ nhưng duyệt theo thứ tự khai báo.
3. Put cùng khóa trả giá trị cũ, không tăng size và không đổi thứ tự.
4. Khóa null bị từ chối khi chèn; giá trị null được biểu diễn khác với thiếu mapping.
5. Nếu bảng cần đầy đủ, mọi hằng có mapping và thỏa điều kiện giá trị của ứng dụng.
6. Sao chép từ EnumMap rỗng thành công, từ map tổng quát rỗng được xử lý bằng cách xác định Class rõ ràng.
7. Xóa qua view có ảnh hưởng nguồn đúng như hợp đồng; bản sao không tự cập nhật theo nguồn.
8. Với nhóm dữ liệu, các khóa không vô tình dùng chung một collection mutable.

Kiểm tra thứ tự bằng danh sách khóa theo thứ tự duyệt. Map.equals hay Set.equals kiểm tra các mapping hoặc tập phần tử, không phải thứ tự.

Không dùng việc iterator không ném ConcurrentModificationException để kiểm tra an toàn nhiều luồng. Không dựa vào một kết quả quan sát sửa đổi xen giữa mà hợp đồng nhất quán yếu cho phép có hoặc không nhìn thấy.

### 14.2. Lưu ý khi dùng giá trị số

Ví dụ view cộng một vào các Integer đã được khởi tạo khác null. Nếu ứng dụng cho phép giá trị null, phép toán số có thể cần chính sách riêng trước khi Java tự mở hộp Integer. Việc EnumMap cho phép null không tự cung cấp một giá trị số mặc định.

Trong ví dụ đếm, điền số 0 cho mọi mức là một quyết định biểu diễn rõ ràng, không phải hành vi tự động của constructor.

## 15. Lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách xử lý |
|---|---|---|
| EnumMap nhận mọi enum trong cùng một map | Sai miền khóa | Xác định một kiểu enum duy nhất |
| Tên chuỗi của hằng là khóa enum | Không tra được theo ý định hoặc sai kiểu | Chuyển và kiểm tra đầu vào trước khi dùng hằng |
| Generic đủ để dùng constructor không đối số | Không có constructor phù hợp | Truyền Class của enum |
| Map biết miền enum nên đã có đủ mapping | Get trả null, size nhỏ hơn mong đợi | Chủ động khởi tạo hoặc kiểm tra độ phủ |
| Thứ tự duyệt theo các lần put | Dự đoán sai kết quả | Theo thứ tự khai báo enum |
| Có thứ tự nên có comparator/subMap | Dùng nhầm API | Phân biệt EnumMap với SortedMap/NavigableMap |
| Get null nghĩa là thiếu khóa | Bỏ sót mapping giá trị null | Dùng containsKey khi cần phân biệt |
| getOrDefault thay mọi giá trị null | Mặc định không được dùng như dự đoán | Hiểu nó chỉ áp dụng khi thiếu mapping |
| Mọi Map rỗng đều copy sang EnumMap được | IllegalArgumentException với nguồn không phải EnumMap | Truyền Class rồi putAll |
| Mọi constructor nhận Map đều từ chối nguồn rỗng | Bỏ sót nguồn thực tế là EnumMap | Đọc đúng trường hợp suy ra miền khóa |
| KeySet là tập độc lập | Remove làm mất mapping nguồn | Tạo bản sao collection nếu cần độc lập |
| Copy map tạo bản sao sâu mọi giá trị | Chia sẻ dữ liệu mutable ngoài ý định | Xác định cách sao chép giá trị |
| Iterator không ném lỗi nghĩa là an toàn cho nhiều luồng | Có thể có truy cập trạng thái không được phối hợp | Thiết kế đồng bộ theo yêu cầu nhiều luồng |

## 16. Tự kiểm tra

### Câu hỏi

1. Vì sao cần `Stage.class` khi tạo một EnumMap rỗng?
2. Chèn DONE trước PLANNED có làm DONE được duyệt trước không?
3. Sau put một hằng hai lần, size có tự tăng hai đơn vị không?
4. EnumMap có thể chứa khóa null không? Có thể chứa giá trị null không?
5. Get trả null có đủ để phân biệt MON thiếu mapping và MON có giá trị null không?
6. `getOrDefault` trên mapping null trả mặc định hay null?
7. Vì sao chép HashMap rỗng gây lỗi nhưng chép EnumMap rỗng không gây lỗi tương tự?
8. Một biến Map đang trỏ EnumMap rỗng có chép được bằng constructor nhận Map không?
9. Iterator nhất quán yếu có bảo đảm nhìn thấy mọi thay đổi diễn ra trong lượt duyệt không?
10. EnumSet và EnumMap khác nhau ở vai trò nào?

### Đáp án

1. Class cung cấp miền enum ở lúc chạy dù chưa có khóa để suy ra.
2. Không; thứ tự khai báo hằng quyết định thứ tự duyệt.
3. Không; lần sau thay giá trị của cùng mapping.
4. Không nhận khóa null khi put; nhận giá trị null.
5. Không; cần kiểm tra containsKey hoặc một hợp đồng không có giá trị null của lớp bọc.
6. Null, vì mapping đang tồn tại.
7. EnumMap nguồn đã giữ kiểu khóa; HashMap rỗng không có mapping để constructor suy ra kiểu enum.
8. Có, vì constructor nhận diện trường hợp đối tượng nguồn thực tế là EnumMap.
9. Không; có thể thấy hoặc không thấy sửa đổi. Điều đó cũng không làm map tự đồng bộ.
10. EnumSet lưu những hằng có mặt; EnumMap lưu quan hệ từ mỗi hằng đang có mapping đến một giá trị.

## 17. Thực hành có kết quả đối chiếu

### Bài 1: thứ tự không phụ thuộc lần chèn

Khai báo `enum Color { RED, GREEN, BLUE }`. Chèn BLUE=3, RED=1 rồi GREEN=2 vào một EnumMap. Dự đoán thứ tự keySet trước khi chạy.

Kết quả đối chiếu là `[RED, GREEN, BLUE]`. Sau đó cập nhật RED thành 10: kích thước vẫn ba, thứ tự vẫn vậy, chỉ giá trị RED đổi.

### Bài 2: đủ khóa nhưng chưa đủ giá trị

Tạo map cho Color và put cả ba khóa, trong đó GREEN có giá trị null. Tính tập hằng chưa có mapping bằng EnumSet.allOf rồi removeAll keySet.

Kết quả đối chiếu: tập thiếu mapping rỗng nhưng vẫn có một giá trị null. Nếu yêu cầu mọi màu có nhãn khác null, phép kiểm tra độ phủ phải đi kèm kiểm tra giá trị.

### Bài 3: nguồn có thể rỗng

Viết một hàm nhận Map<Color,String> có thể rỗng. Khởi tạo EnumMap bằng Color.class rồi putAll nguồn. Chạy với nguồn rỗng và nguồn chỉ có BLUE.

Kết quả đối chiếu: trường hợp rỗng trả map size 0; trường hợp có BLUE trả đúng một mapping BLUE. Không cần chèn dữ liệu giả để xác định kiểu khóa.

### Bài 4: nhóm dữ liệu khi đầu vào rỗng

Trong chương trình 5, thay events bằng danh sách rỗng rồi dự đoán counts, groups và phần in theo mọi Severity.

Kết quả đối chiếu: counts vẫn có LOW=0, MEDIUM=0, HIGH=0 vì đã khởi tạo toàn miền; groups rỗng vì chưa có mức nào cần danh sách. Mỗi dòng trình bày có count=0 và messages=[]. Điều này xác nhận sự khác nhau giữa điền sẵn giá trị mặc định và tạo nhóm khi cần.

## 18. Môi trường chạy và tài liệu

Năm chương trình trong bài độc lập, dùng cú pháp và API tương thích Java 17. Chúng đã được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên JDK 24.0.2; stdout được đối chiếu từ các lần chạy đó. Mỗi lớp public được lưu trong tệp trùng tên, không dùng thư viện ngoài.

- [EnumMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html): miền khóa enum, constructor, thứ tự, null, view và iterator.
- [Enum — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html): định danh hằng, thứ tự khai báo, ordinal và getDeclaringClass.
- [EnumSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html): tập hằng chuyên biệt và phép tạo toàn miền.
- [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): mapping, null, getOrDefault, putIfAbsent, computeIfAbsent và merge.
