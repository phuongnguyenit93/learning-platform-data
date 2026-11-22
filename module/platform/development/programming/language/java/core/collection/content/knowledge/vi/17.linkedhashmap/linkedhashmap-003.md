# Chế độ access-order và các thao tác làm đổi thứ tự

## 1. Khi “đọc dữ liệu” cũng thay đổi lịch sử sử dụng

Giả sử chương trình giữ các mục đã dùng gần đây. Sau khi thêm a, b, c, người dùng đọc lại a. Nếu muốn biết mục nào lâu chưa được dùng, thứ tự chèn a,b,c không còn đủ: a vừa được sử dụng, còn b mới là mục ít được truy cập gần đây nhất.

LinkedHashMap có **chế độ thứ tự truy cập (access-order)** để duy trì thứ tự này.

Trong chế độ ấy, dãy duyệt đi từ entry ít được truy cập gần đây nhất tới entry được truy cập gần đây nhất. Một thao tác được tính là truy cập có thể đưa entry liên quan về cuối dãy.

Điểm cần học không chỉ là “get chuyển khóa xuống cuối”. Phải biết:

- Thao tác nào được tính là truy cập.
- Điều kiện nào khiến thao tác thành công, bỏ qua, chèn mới hoặc xóa ánh xạ.
- Khi nào dữ liệu không đổi nhưng thứ tự vẫn đổi.
- Vì sao truy cập trong lúc duyệt có thể làm iterator mất hiệu lực.

Bài này xét các API có trong Java 17. Phần giải thích đường thực thi dùng nguồn OpenJDK 17u; các chương trình được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. Cờ biên dịch chọn mức API/bytecode đích, không thay phiên bản JVM chạy chương trình.

## 2. Bật chế độ và đọc đúng hai đầu của dãy

Tạo map bằng constructor ba tham số:

```java
Map<String, Integer> recent = new LinkedHashMap<>(16, 0.75f, true);
```

Đây là đoạn khai báo minh họa trong ngữ cảnh đã import Map và LinkedHashMap.

| Tham số | Vai trò |
| --- | --- |
| 16 | Yêu cầu dung lượng ban đầu |
| 0.75f | Load factor |
| true | Chọn access-order |

Nếu tham số cuối là false, hoặc dùng constructor thông thường như new LinkedHashMap<>(), map theo thứ tự chèn.

### 2.1. Đầu cũ hơn, cuối mới hơn

Với dãy a,b,c:

```text
đầu                                          cuối
ít được truy cập gần đây nhất  →  được truy cập gần đây nhất
a                 → b       → c
```

Get a thành công:

```text
trước: a → b → c
sau:   b → c → a
```

Không cần thêm lại a hay thay giá trị để ghi nhận lần truy cập này.

### 2.2. Thứ tự tương đối, không phải bộ đếm hay đồng hồ

Access-order không lưu số lần truy cập để sắp theo tần suất. Một khóa đọc một lần ngay lúc này có thể đứng sau khóa đã đọc cả nghìn lần trước đó.

Nó cũng không tự tạo thời điểm hết hạn. Việc một entry nằm đầu chỉ cho biết quan hệ trong lịch sử truy cập mà map ghi nhận, không cho biết entry đã cũ bao nhiêu giây.

### 2.3. Có truy cập không đồng nghĩa dãy luôn khác đi

Nếu a đã ở cuối, get a vẫn là một truy cập hợp lệ nhưng không có vị trí nào mới hơn để chuyển tới. Dãy quan sát có thể giữ nguyên.

Vì vậy cần phân biệt hai câu hỏi:

1. Thao tác có thuộc loại truy cập entry không?
2. Thứ tự trước và sau có thực sự khác nhau không?

Trong cài đặt OpenJDK 17u, afterNodeAccess chỉ nối lại liên kết khi entry chưa ở cuối. Không dùng chi tiết này để dựa vào việc iterator “có thể vẫn dùng được” sau một số lần get.

## 3. Mô hình thực hiện: tìm entry rồi cập nhật vị trí

Bảng băm vẫn phục vụ tìm khóa. Access-order không biến get thành việc quét từ đầu danh sách để tìm phần tử.

Khi đường thao tác xác định một entry được truy cập, cơ chế thứ tự có thể:

1. Gỡ entry khỏi vị trí hiện tại.
2. Nối hai hàng xóm cũ với nhau.
3. Đặt entry ấy ở cuối.
4. Giữ đầu và cuối của chuỗi nhất quán.

Nếu entry đã ở cuối thì không cần nối lại dãy.

Trong mã nguồn được đối chiếu, vai trò này nằm ở afterNodeAccess của [LinkedHashMap OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/LinkedHashMap.java). Đây là giải thích cài đặt; mã ứng dụng sử dụng các thao tác công khai, không gọi hàm nội bộ.

Điều quan trọng là vị trí entry có thể đổi ngay cả khi khóa, giá trị và size đều không đổi.

## 4. Get, getOrDefault, put và putIfAbsent

Tài liệu lớp liệt kê các thao tác tạo truy cập và những điều kiện liên quan. Đối chiếu [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html) thay vì suy luận từ tên “đọc” hoặc “ghi”.

### 4.1. Get trúng khóa và get không có khóa

| Trạng thái | Kết quả dữ liệu | Ảnh hưởng thứ tự |
| --- | --- | --- |
| Khóa tồn tại với giá trị không null | Trả giá trị | Entry được truy cập, về cuối nếu chưa ở cuối |
| Khóa tồn tại với giá trị null | Trả null | Entry vẫn tồn tại và được truy cập |
| Khóa không tồn tại | Trả null | Không có entry để đưa về cuối |

Do đó, chỉ nhìn giá trị trả về null không thể kết luận thứ tự có bị tác động hay không.

Không có “entry của khóa thiếu” tự được tạo ra khi gọi get.

### 4.2. GetOrDefault phân biệt không có khóa với giá trị null

Nếu khóa có trong map, getOrDefault trả giá trị đang gắn với nó và ghi nhận truy cập, kể cả giá trị ấy là null.

Nếu khóa không có, phương thức trả giá trị dự phòng; nó không thêm ánh xạ mới và không ghi một entry thiếu vào lịch sử.

Giá trị dự phòng không phải giá trị sẽ tự lưu vào map.

### 4.3. Put khóa cũ có thể đổi thứ tự dù giá trị giữ nguyên

Trong access-order, put vào một khóa đang tồn tại là truy cập entry đó. Dù giá trị mới bằng giá trị cũ, entry vẫn có thể về cuối.

Điều này khác map theo thứ tự chèn: ở chế độ chèn, put khóa cũ giữ vị trí cũ.

Nếu khóa chưa tồn tại, put thêm entry mới ở cuối. Map vừa có dữ liệu mới vừa có vị trí mới.

### 4.4. PutIfAbsent không nhất thiết là “không làm gì”

Khi khóa đã có giá trị không null, putIfAbsent có thể không thay giá trị. Tuy nhiên entry vẫn được tính là truy cập trong cấu trúc access-order.

Ví dụ dãy a,b,c và a=1. PutIfAbsent("a", 99) trả 1, không thay thành 99, nhưng dãy có thể thành b,c,a.

Nếu khóa đang gắn null, phương thức có thể gắn giá trị cung cấp vào đó; entry cũng được truy cập. Nếu khóa chưa có, nó tạo entry mới ở cuối.

Trong cài đặt được đối chiếu, cả trường hợp entry null được putIfAbsent lại bằng null cũng đi qua đường truy cập. Trả về null không phải một dấu hiệu chung cho “không có tác động”.

## 5. Replace có điều kiện, setValue và replaceAll

### 5.1. Replace chỉ tạo truy cập khi việc thay được thực hiện

Với replace(key, newValue):

- Có entry cho key: thực hiện thay giá trị và truy cập entry.
- Không có key: không thay, không tạo entry để truy cập.

Với replace(key, expectedValue, newValue):

- Khóa tồn tại và giá trị cũ khớp điều kiện: thay và truy cập entry.
- Điều kiện không khớp hoặc không có khóa: không thay, không đưa khóa về cuối.

Một phép thay thành chính giá trị đang có vẫn là phép thay được thực hiện nếu điều kiện khớp. Không cần giá trị mới phải khác theo equals thì entry mới được truy cập.

Giá trị trả về của replace(key, newValue) có thể là null khi giá trị cũ là null. Muốn hiểu tác động phải biết có entry hay không, không chỉ nhìn kết quả trả về.

### 5.2. Entry.setValue không phải map.put

Lấy một Map.Entry từ entrySet rồi gọi setValue thay giá trị qua view. Tài liệu LinkedHashMap không tính thao tác trên collection view là truy cập entry làm đổi access-order.

Vì vậy cùng ý định “đổi giá trị” có thể có tác động khác nhau tới lịch sử tùy API được dùng.

Chọn theo ý nghĩa cần có, không cố thay một API bằng API khác chỉ vì chúng có vẻ cho cùng giá trị cuối.

### 5.3. ReplaceAll không tương đương chuỗi replace theo từng khóa

Trong cài đặt LinkedHashMap được đối chiếu, replaceAll đi theo các entry và thay giá trị; nó không tự biến mỗi entry thành một truy cập đưa về cuối.

Điều này còn đòi hỏi hàm truyền vào không có tác dụng phụ làm thay đổi cấu trúc hoặc gọi những thao tác truy cập gây nối lại dãy.

Câu “replaceAll giữ thứ tự” trong ví dụ phía dưới nói về hàm thuần tính giá trị mới từ đối số. Nếu chính hàm gọi map.get, map.put hoặc sửa map theo đường khác, phải xét cả tác dụng phụ ấy.

## 6. Ví dụ Java 17: đọc, ghi có điều kiện và thay qua view

Lưu thành **AccessOrderBasics.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;

public class AccessOrderBasics {
    static void show(String label, Map<String, Integer> map) {
        System.out.println(label + ": " + new ArrayList<>(map.keySet()));
    }

    public static void main(String[] args) {
        Map<String, Integer> map = new LinkedHashMap<>(16, 0.75f, true);
        map.put("a", 1);
        map.put("b", 2);
        map.put("c", 3);
        map.put("d", 4);
        show("initial", map);

        System.out.println("contains a: " + map.containsKey("a"));
        show("after contains", map);
        System.out.println("get b: " + map.get("b"));
        show("after get b", map);
        System.out.println("get missing: " + map.get("missing"));
        show("after missing", map);
        System.out.println("default a: " + map.getOrDefault("a", -1));
        show("after default a", map);

        System.out.println("old c: " + map.put("c", 30));
        show("after put c", map);
        System.out.println("existing b: " + map.putIfAbsent("b", 200));
        show("after putIfAbsent b", map);
        System.out.println("failed replace d: " + map.replace("d", 999, 40));
        show("after failed replace", map);
        System.out.println("successful replace d: " + map.replace("d", 4, 40));
        show("after successful replace", map);

        Map.Entry<String, Integer> first = map.entrySet().iterator().next();
        first.setValue(11);
        show("after entry setValue", map);
        System.out.println("values after setValue: " + new ArrayList<>(map.values()));
        map.replaceAll((key, value) -> value + 1);
        show("after replaceAll", map);
        System.out.println("values after replaceAll: " + new ArrayList<>(map.values()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AccessOrderBasics.java
java AccessOrderBasics
```

Stdout trên môi trường đã nêu:

```text
initial: [a, b, c, d]
contains a: true
after contains: [a, b, c, d]
get b: 2
after get b: [a, c, d, b]
get missing: null
after missing: [a, c, d, b]
default a: 1
after default a: [c, d, b, a]
old c: 3
after put c: [d, b, a, c]
existing b: 2
after putIfAbsent b: [d, a, c, b]
failed replace d: false
after failed replace: [d, a, c, b]
successful replace d: true
after successful replace: [a, c, b, d]
after entry setValue: [a, c, b, d]
values after setValue: [11, 30, 2, 40]
after replaceAll: [a, c, b, d]
values after replaceAll: [12, 31, 3, 41]
```

### 6.1. Vì sao putIfAbsent làm b về cuối?

B vẫn có giá trị 2, không phải 200. Nhưng nó vừa được truy cập bởi putIfAbsent. Cần quan sát cả giá trị lẫn dãy khóa để thấy đầy đủ tác động.

### 6.2. Hai lần replace khác nhau ở điều kiện

Lần thay d với giá trị mong đợi 999 thất bại. D không được đưa về cuối.

Lần thay với giá trị mong đợi 4 thành công, d thành 40 và được đưa về cuối.

### 6.3. Quan sát không làm nhiễu lịch sử

Hàm show tạo ArrayList từ keySet. Duyệt view theo cách này không gọi get cho từng khóa, nên việc in dãy không tự đưa các khóa về cuối.

SetValue thay giá trị entry đầu là a thành 11. ReplaceAll tăng các giá trị nhưng không tự tạo lịch sử truy cập mới. Những dòng values kiểm tra nội dung thay đổi mà không dùng các lệnh get gây tác động thêm.

## 7. Compute và merge: xét đường thực thi, không chỉ tên phương thức

Các phương thức này có thể dùng ánh xạ sẵn có, tính lại giá trị, thêm mới, bỏ qua hoặc xóa. Vì vậy một bảng chỉ ghi “compute luôn đưa khóa xuống cuối” là thiếu điều kiện.

Bảng sau mô tả các nhánh chính, với hàm truyền vào không tự sửa hay truy cập map:

| Thao tác | Nhánh thực thi | Tác động tới vị trí |
| --- | --- | --- |
| computeIfAbsent | Đã có giá trị không null | Dùng entry hiện có và ghi nhận truy cập |
| computeIfAbsent | Tính được giá trị không null cho khóa mới | Thêm entry cuối dãy |
| computeIfAbsent | Điền giá trị không null cho entry đang null | Cập nhật và truy cập entry |
| computeIfPresent | Có giá trị không null, hàm trả không null | Cập nhật và truy cập entry |
| computeIfPresent | Hàm trả null | Xóa ánh xạ, không còn entry ấy để đặt cuối |
| compute | Hàm trả không null, đã có entry | Cập nhật và truy cập entry |
| compute | Hàm trả không null, chưa có entry | Thêm entry cuối dãy |
| compute | Hàm trả null | Không tạo entry mới; nếu có ánh xạ thì xóa |
| merge | Giữ/cập nhật ánh xạ với kết quả không null | Entry hiện có được truy cập hoặc entry mới được thêm cuối |
| merge | Hàm gộp trả null | Xóa ánh xạ |

Nếu một entry đã ở cuối thì nhánh truy cập có thể không tạo khác biệt trong dãy quan sát. Nếu bị xóa, thứ tự tương đối của các entry còn lại được giữ.

### 7.1. Không đổi giá trị vẫn có thể là truy cập

Compute("a", (key, value) -> value) với a đang có giá trị không null vẫn sử dụng và cập nhật ánh xạ theo đường ấy. Giá trị cuối giống trước không có nghĩa entry giữ nguyên vị trí.

Tương tự, computeIfAbsent trên một ánh xạ đã có giá trị không null không gọi hàm tạo giá trị, nhưng vẫn ghi nhận việc dùng entry hiện có.

### 7.2. Trả null có nhiều ý nghĩa

Null từ get có thể là giá trị của một entry đang tồn tại.

Null từ một hàm tính lại có thể yêu cầu không tạo mới hoặc xóa ánh xạ, tùy phương thức.

Không lấy cùng một quy tắc thứ tự áp cho mọi kết quả null. Hãy xác định ánh xạ trước, nhánh phương thức và ánh xạ sau.

### 7.3. Nhánh bỏ qua với entry đang null cần đọc chi tiết

Trong nguồn [HashMap OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java), nơi triển khai các phương thức được LinkedHashMap kế thừa:

- ComputeIfPresent không gọi hàm tính lại nếu giá trị hiện có là null; nhánh bỏ qua ấy không gọi afterNodeAccess.
- ComputeIfAbsent với entry đang null và hàm trả null giữ ánh xạ null; đường trả về này cũng không gọi afterNodeAccess.

Đây là **phân tích nhánh cài đặt cụ thể**, được kiểm tra thêm trong chương trình tiếp theo trên môi trường đã nêu. Không suy từ phần liệt kê khái quát các họ phương thức ở Javadoc thành một cam kết rằng mọi lần gọi tên compute đều phải di chuyển entry, bất kể điều kiện null hoặc nhánh bỏ qua.

Khi ứng dụng dựa vào từng nhánh như vậy để định nghĩa lịch sử sử dụng, cần ghi rõ trường hợp và phiên bản được kiểm chứng. Nếu muốn một quy tắc đơn giản hơn, có thể chủ động không dùng giá trị null trong mô hình ứng dụng; đó là lựa chọn thiết kế riêng, không phải hạn chế bắt buộc của LinkedHashMap.

### 7.4. Hàm tính lại không nên tự làm nhiễu thứ tự

Không gọi lại map.get trên chính map để lấy một giá trị mà hàm đã được nhận qua đối số. Trong access-order, lời gọi đó có thể sửa liên kết, kể cả không thay giá trị.

Các phương thức compute/merge có giới hạn đối với việc sửa map trong hàm tính lại. Một tác dụng phụ làm đổi cấu trúc có thể bị phát hiện và gây lỗi, đồng thời làm lập luận về thứ tự khó đúng hơn.

Nếu hàm thuần ném ngoại lệ, đừng ghi nhận như một lần cập nhật thành công. Nếu hàm đã có tác dụng phụ trước khi ném, không được giả định hệ thống sẽ tự hoàn tác toàn bộ tác dụng ấy.

## 8. Ví dụ Java 17: các nhánh tính lại và null

Mỗi dòng của chương trình bắt đầu với **một map mới**, theo dãy a,b,c. Tham số nullAtA chọn a=1 hoặc a=null.

Nhờ khởi tạo lại từng trường hợp, kết quả không bị ảnh hưởng bởi lịch sử từ dòng thử nghiệm trước.

Lưu thành **AccessOrderRemapping.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;

public class AccessOrderRemapping {
    static void test(String label, boolean nullAtA,
            Function<Map<String, Integer>, Object> operation) {
        Map<String, Integer> map = new LinkedHashMap<>(16, 0.75f, true);
        map.put("a", nullAtA ? null : 1);
        map.put("b", 2);
        map.put("c", 3);

        Object result = operation.apply(map);
        System.out.println(label + " => result=" + result
                + "; keys=" + new ArrayList<>(map.keySet())
                + "; values=" + new ArrayList<>(map.values()));
    }

    public static void main(String[] args) {
        test("absent hit", false, m -> m.computeIfAbsent("a", key -> 99));
        test("absent new", false, m -> m.computeIfAbsent("d", key -> 9));
        test("present update", false, m -> m.computeIfPresent("a", (key, value) -> value + 10));
        test("present remove", false, m -> m.computeIfPresent("a", (key, value) -> null));
        test("compute unchanged", false, m -> m.compute("a", (key, value) -> value));
        test("compute missing null", false, m -> m.compute("x", (key, value) -> null));
        test("merge update", false, m -> m.merge("a", 10, Integer::sum));
        test("merge remove", false, m -> m.merge("a", 10, (oldValue, added) -> null));
        test("get mapped null", true, m -> m.get("a"));
        test("default mapped null", true, m -> m.getOrDefault("a", -1));
        test("present mapped null", true, m -> m.computeIfPresent("a", (key, value) -> 9));
        test("absent null result", true, m -> m.computeIfAbsent("a", key -> null));
        test("absent fills null", true, m -> m.computeIfAbsent("a", key -> 9));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AccessOrderRemapping.java
java AccessOrderRemapping
```

Stdout:

```text
absent hit => result=1; keys=[b, c, a]; values=[2, 3, 1]
absent new => result=9; keys=[a, b, c, d]; values=[1, 2, 3, 9]
present update => result=11; keys=[b, c, a]; values=[2, 3, 11]
present remove => result=null; keys=[b, c]; values=[2, 3]
compute unchanged => result=1; keys=[b, c, a]; values=[2, 3, 1]
compute missing null => result=null; keys=[a, b, c]; values=[1, 2, 3]
merge update => result=11; keys=[b, c, a]; values=[2, 3, 11]
merge remove => result=null; keys=[b, c]; values=[2, 3]
get mapped null => result=null; keys=[b, c, a]; values=[2, 3, null]
default mapped null => result=null; keys=[b, c, a]; values=[2, 3, null]
present mapped null => result=null; keys=[a, b, c]; values=[null, 2, 3]
absent null result => result=null; keys=[a, b, c]; values=[null, 2, 3]
absent fills null => result=9; keys=[b, c, a]; values=[2, 3, 9]
```

### 8.1. Những trường hợp dùng entry hiện có

Absent hit dùng a=1 mà không cần gọi hàm tạo 99, nhưng a vẫn được đưa cuối.

Compute unchanged trả lại chính giá trị hiện có, nhưng dãy vẫn thành b,c,a.

Hai ví dụ cho thấy không thể lấy việc “giá trị chưa đổi” làm tiêu chí quyết định thứ tự.

### 8.2. Những trường hợp xóa hoặc không tạo ánh xạ

Present remove và merge remove bỏ a khỏi map, nên kết quả còn b,c.

Compute missing null không tạo x, do đó dãy a,b,c giữ nguyên. Không có một entry x để xếp thành mới nhất.

### 8.3. Nhận diện null qua trạng thái, không qua mỗi kết quả trả về

Get mapped null và default mapped null đều trả null, nhưng a đang tồn tại nên về cuối: b,c,a.

Present mapped null và absent null result cũng trả null, nhưng ở những nhánh bỏ qua/không điền giá trị của cài đặt đã giải thích, dãy vẫn là a,b,c.

Absent fills null tính được 9, cập nhật a và đưa a về cuối.

Các dòng thuộc nhánh null đặc biệt cần được đọc cùng phạm vi cài đặt và môi trường của bài. Chúng không phải lý do dùng một quy tắc tùy đoán như “null luôn giữ thứ tự” hoặc “null luôn làm truy cập”.

## 9. PutAll tạo một chuỗi truy cập theo thứ tự nguồn

PutAll không chỉ thêm những khóa còn thiếu. Với access-order, ánh xạ đã có trong map đích cũng được xử lý như một truy cập tương ứng.

Tài liệu lớp xác định các truy cập được thực hiện theo thứ tự entrySet của map nguồn.

Giả sử đích đang có a,b,c,d và nguồn đưa ra c,a,e:

| Bước | Ánh xạ được xử lý | Thứ tự đích sau bước |
| --- | --- | --- |
| Bắt đầu | Chưa xử lý | a,b,c,d |
| 1 | c | a,b,d,c |
| 2 | a | b,d,c,a |
| 3 | e mới | b,d,c,a,e |

B và d không được xử lý bởi đợt putAll này nên vẫn đứng trước các entry vừa được đưa về cuối, theo thứ tự tương đối của chúng.

### 9.1. Nguồn không có hợp đồng thứ tự làm kết quả khó dự đoán hơn

Nếu nguồn là LinkedHashMap theo thứ tự chèn c,a,e, có cơ sở dùng đúng trình tự ấy để lập bảng.

Nếu nguồn là một Map không bảo đảm thứ tự, không tự giả định putAll sẽ đi theo thứ tự chữ cái hay lịch sử mà dữ liệu từng được tạo. Đích ghi nhận những entry theo lượt nguồn thực sự đưa ra.

Muốn kết quả có quy tắc riêng, phải kiểm soát thứ tự nguồn hoặc chủ động chuẩn bị dãy cập nhật.

### 9.2. Thêm mới và truy cập lại đều có vai trò

Khóa e mới nằm cuối vì vừa được thêm. C và a đã có vẫn đổi vị trí vì đợt putAll truy cập lại chúng.

Không dùng cách hiểu “chỉ những khóa mới mới ảnh hưởng thứ tự” cho một map access-order.

Không dùng chính map đang đổi thứ tự làm nguồn để tự lập luận rằng việc sao chép lên nó chắc chắn vô hại. Lượt duyệt nguồn và các truy cập vào đích cần được xem cùng nhau.

## 10. Các thao tác không tự đưa entry về cuối

Bảng dưới nói về **bản thân thao tác**, không bao gồm tác dụng phụ của mã người dùng tự gọi thêm:

| Thao tác | Có tự ghi nhận truy cập để làm mới vị trí không? |
| --- | --- |
| containsKey | Không |
| containsValue | Không |
| size, isEmpty | Không |
| Duyệt keySet, values, entrySet | Không |
| Lấy khóa/giá trị từ một Map.Entry | Không |
| Entry.setValue qua view | Không |
| ForEach với hàm chỉ dùng đối số để xử lý | Không |
| ReplaceAll với hàm thuần tính giá trị mới | Không tự tạo từng truy cập như replace |
| Replace có điều kiện thất bại | Không |
| Get hoặc getOrDefault không tìm thấy khóa | Không có entry để làm mới |

### 10.1. Không truy cập lại không có nghĩa không sửa map

Remove xóa ánh xạ, clear làm map rỗng. Những thao tác này thay đổi cấu trúc nhưng không phải một lần làm mới vị trí của entry bị xóa.

Xóa qua view cũng có tác dụng thật lên map. Nó không tự biến các entry còn lại thành những entry vừa được truy cập.

Vì vậy cần phân biệt ba loại tác động:

- Cập nhật nội dung khóa–giá trị.
- Thêm/xóa ánh xạ.
- Thay đổi vị trí theo lịch sử truy cập.

Một phương thức có thể liên quan tới hơn một loại, hoặc không liên quan loại nào.

### 10.2. Mã quan sát có thể gián tiếp tạo truy cập

Một hàm ghi log tự viết như “duyệt keySet, gọi map.get(key), in giá trị” có thể làm đổi thứ tự. Nguyên nhân là các lệnh get được gọi thêm, không phải keySet tự tính truy cập.

Tương tự, một hàm được truyền cho forEach có thể tự gọi get hoặc put. Khi đó phải xét các lệnh ấy; không dùng tên forEach để kết luận toàn bộ đoạn mã không có tác động.

Muốn chỉ quan sát ánh xạ trong một lượt duyệt, lấy cả khóa lẫn giá trị từ entrySet và tránh gọi lại các API làm mới vị trí.

### 10.3. Chụp danh sách khóa không đóng băng map

New ArrayList<>(map.keySet()) chụp dãy khóa vào một danh sách. Sau đó get từng khóa vẫn là truy cập trên map.

Duyệt danh sách chụp có thể tránh một số vấn đề do iterator của map bị nối lại dãy trong cùng luồng, nhưng không biến các get thành thao tác trung lập với lịch sử.

Cũng không tạo ảnh chụp nhất quán nhiều luồng chỉ bằng câu lệnh sao chép danh sách khóa mà không có sự phối hợp phù hợp.

## 11. Iterator: size không đổi vẫn có thể mất hiệu lực

Ở access-order, đổi thứ tự là một dạng thay đổi cấu trúc. Vì thế một get thành công có thể ảnh hưởng iterator đang giữ.

Mẫu dễ sai:

```java
for (String key : recent.keySet()) {
    Integer value = recent.get(key);
    System.out.println(value);
}
```

Đây là **đoạn minh họa cần tránh**, không phải chương trình độc lập được đề nghị sử dụng. Nó đang duyệt map rồi truy cập lại chính map qua get.

Nếu get đưa entry chưa ở cuối về cuối, iterator được tạo trước đó có thể phát hiện thay đổi và ném ConcurrentModificationException.

### 11.1. Duyệt entrySet để lấy dữ liệu đã có trong entry

Nếu chỉ cần đọc mọi cặp, dùng:

```java
for (Map.Entry<String, Integer> entry : recent.entrySet()) {
    String key = entry.getKey();
    Integer value = entry.getValue();
    System.out.println(key + "=" + value);
}
```

Đây là mẫu trong ngữ cảnh có recent và các import phù hợp. Lấy value từ entry không tạo thêm một truy cập lên map.

Nếu cần xóa trong lượt duyệt, xem thao tác remove của chính iterator theo hợp đồng của nó. Đừng sửa cấu trúc tùy ý qua map rồi tiếp tục dùng iterator cũ.

### 11.2. Fail-fast là chẩn đoán lỗi, không phải điều kiện nghiệp vụ

Cơ chế phát hiện được thực hiện theo khả năng. Không viết logic kiểu “nếu không có ConcurrentModificationException thì vòng lặp chắc an toàn”.

Ví dụ get entry đang ở cuối có thể không nối lại dãy trong một cài đặt, nhưng điều đó không tạo một cách dùng iterator ổn định cho mọi lịch sử.

ConcurrentModificationException cũng không chỉ liên quan nhiều luồng. Một luồng có thể tự làm iterator mất hiệu lực bằng cách đổi cấu trúc ngoài đường được phép.

## 12. Ví dụ Java 17: putAll, vòng đọc đúng và iterator bị ảnh hưởng

Lưu thành **AccessOrderBulkAndIteration.java**:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.StringJoiner;

public class AccessOrderBulkAndIteration {
    public static void main(String[] args) {
        Map<String, Integer> map = new LinkedHashMap<>(16, 0.75f, true);
        map.put("a", 1);
        map.put("b", 2);
        map.put("c", 3);
        map.put("d", 4);

        Map<String, Integer> incoming = new LinkedHashMap<>();
        incoming.put("c", 30);
        incoming.put("a", 10);
        incoming.put("e", 5);
        map.putAll(incoming);
        System.out.println("after putAll: " + new ArrayList<>(map.keySet()));

        StringJoiner joined = new StringJoiner("; ");
        for (Map.Entry<String, Integer> entry : map.entrySet()) {
            joined.add(entry.getKey() + "=" + entry.getValue());
        }
        System.out.println("safe entries: " + joined);
        System.out.println("after safe loop: " + new ArrayList<>(map.keySet()));

        Iterator<String> iterator = map.keySet().iterator();
        System.out.println("iterator first: " + iterator.next());
        System.out.println("get c during iteration: " + map.get("c"));
        System.out.println("after get c: " + new ArrayList<>(map.keySet()));
        try {
            System.out.println("iterator next: " + iterator.next());
        } catch (ConcurrentModificationException expected) {
            System.out.println("observed iterator: ConcurrentModificationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AccessOrderBulkAndIteration.java
java AccessOrderBulkAndIteration
```

Stdout quan sát trong môi trường đã nêu:

```text
after putAll: [b, d, c, a, e]
safe entries: b=2; d=4; c=30; a=10; e=5
after safe loop: [b, d, c, a, e]
iterator first: b
get c during iteration: 30
after get c: [b, d, a, e, c]
observed iterator: ConcurrentModificationException
```

### 12.1. PutAll đúng theo trình tự c,a,e

Kết quả b,d,c,a,e khớp bảng phân tích. Giá trị c thành 30 và a thành 10, e được thêm bằng 5.

Vòng entrySet lấy khóa và giá trị trực tiếp. Dãy sau vòng ấy vẫn là b,d,c,a,e.

### 12.2. Một get làm iterator cũ mất hiệu lực

Iterator đã trả b. Sau đó get c đưa c ra cuối, làm dãy thành b,d,a,e,c. Size vẫn bằng 5 nhưng các liên kết thứ tự đã đổi.

Trên môi trường chạy được ghi rõ, lần next tiếp theo quan sát ConcurrentModificationException. Dòng observed là kết quả của thí nghiệm chẩn đoán; không biến việc ném ngoại lệ trong mọi tình huống sai thành bảo đảm tuyệt đối.

Ví dụ cố ý bắt lỗi để chương trình kết thúc có kiểm soát và giải thích nguyên nhân. Trong mã thực tế, sửa cách duyệt hoặc mô hình cập nhật, không dùng catch để tiếp tục iterator đã mất hiệu lực.

## 13. Hệ quả khi dùng access-order trong ứng dụng

### 13.1. Phải xác định “dùng một mục” nghĩa là gì

Nếu kiểm tra tồn tại bằng containsKey thì mục không được làm mới. Nếu lấy giá trị bằng get thì mục được truy cập.

Nếu putIfAbsent tìm thấy dữ liệu đã có, nó vẫn có thể làm mới vị trí dù không thay nội dung. Nếu replace có điều kiện thất bại thì không.

Những khác biệt này ảnh hưởng cách diễn giải đầu dãy. Chọn API phải phù hợp với ý nghĩa “sử dụng” trong bài toán, không chỉ với kiểu giá trị trả về.

### 13.2. Không tự có giới hạn, hết hạn hoặc tính an toàn đồng thời

Access-order cung cấp lịch sử tương đối của các entry. Nó không tự giới hạn số ánh xạ, tự xóa theo thời gian hoặc tự phối hợp nhiều luồng.

Cơ chế loại entry, nếu cần, là một chính sách bổ sung. Không kết luận cứ bật true là đã có một cache hoàn chỉnh.

### 13.3. Get có thể là thao tác sửa cấu trúc

Nếu một thiết kế khóa đồng bộ phân loại mọi get là đọc thuần túy, thiết kế ấy cần được xem lại khi dùng access-order. Hai luồng cùng get có thể cùng tác động chuỗi thứ tự.

LinkedHashMap không tự đồng bộ. Dùng một cơ chế phối hợp phù hợp cho cả các thao tác đổi thứ tự, các lượt duyệt và những chuỗi thao tác cần tính nhất quán.

Không dùng fail-fast để thay vai trò của cơ chế phối hợp.

### 13.4. Sao chép không tự giữ chế độ

New LinkedHashMap<>(source) tạo một map theo thứ tự chèn, nhận dãy mà nguồn đưa ra lúc sao chép. Nó không tự bật accessOrder=true chỉ vì source đang ở chế độ truy cập.

Nếu cần map mới cũng duy trì truy cập, phải tạo nó bằng cấu hình mong muốn rồi đưa các ánh xạ vào theo trình tự phù hợp.

Việc sao chép ánh xạ không tự là bản sao sâu của khóa và giá trị, cũng không tự tạo một ảnh chụp nhất quán khi nguồn đang bị sửa đồng thời.

## 14. Cách kiểm thử thứ tự có chủ đích

Một kiểm thử tốt mô tả rõ:

1. Chế độ của map.
2. Dữ liệu và dãy trước thao tác.
3. Thao tác cùng điều kiện của nó.
4. Giá trị trả về, ánh xạ còn lại và dãy sau thao tác.
5. Môi trường khi đang kiểm tra một nhánh cài đặt cụ thể.

Để kiểm tra dãy khóa, so sánh List được tạo từ keySet. Chỉ kiểm tra Map.equals hoặc keySet.equals không xác nhận thứ tự.

Hãy dùng dữ liệu có ít nhất vài entry và chọn khóa chưa ở cuối. Nếu mọi phép thử đều truy cập entry cuối, nhiều lỗi về kỳ vọng thứ tự sẽ bị che mất vì dãy không có gì để đổi.

Với các nhánh có điều kiện, thử cả thành công và thất bại. Với null, phân biệt khóa thiếu, khóa đang null, kết quả tính lại null và việc xóa ánh xạ.

Hàm quan sát trong bài chỉ duyệt view. Nếu bài kiểm thử dùng get để kiểm tra giá trị, chính lời kiểm tra ấy có thể đổi trạng thái trước phép kiểm tra kế tiếp. Có thể kiểm tra thứ tự trước, hoặc dùng dãy entry/values phù hợp mà không phát sinh thêm truy cập.

Đối với chương trình có nhiều thao tác liên tiếp, ghi lại lịch sử từng bước hoặc khởi tạo map mới cho mỗi trường hợp như chương trình thứ hai. Đừng để một bước xác minh ẩn trở thành nguyên nhân làm kết quả sau khó giải thích.

## 15. Lỗi phổ biến và cách sửa

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Access-order là thứ tự số lần truy cập nhiều nhất | Đây là thứ tự tương đối theo lần truy cập gần nhất được ghi nhận |
| Get luôn chỉ đọc cấu trúc | Get trúng entry có thể nối lại dãy |
| Get trả null chắc không đổi gì | Có thể đã truy cập entry mang giá trị null |
| Put cùng giá trị không tác động thứ tự | Entry cũ vẫn có thể được làm mới |
| PutIfAbsent không thêm thì là thao tác trung lập | Trường hợp đã có giá trị vẫn có thể tạo truy cập |
| Replace thất bại cũng đưa khóa về cuối | Chỉ phép thay được thực hiện mới ghi nhận truy cập theo quy tắc replace |
| Mọi lần gọi compute đều có cùng tác động | Xét nhánh dùng, tạo, bỏ qua, xóa và các điều kiện null |
| SetValue và put giống nhau về lịch sử | Thao tác qua entry view không tự tạo truy cập như put |
| PutAll chỉ tác động khóa mới | Nó còn truy cập lại ánh xạ có sẵn theo thứ tự nguồn |
| Size giữ nguyên thì iterator còn hợp lệ | Đổi thứ tự cũng có thể là thay đổi cấu trúc |
| In dữ liệu không thể làm thay đổi map | Hàm in tự gọi get có thể làm mới lịch sử |
| Không có ngoại lệ nghĩa là cách dùng chắc đúng | Fail-fast chỉ hỗ trợ chẩn đoán theo khả năng |
| Constructor sao chép giữ nguyên access-order | Constructor nhận Map tạo chế độ thứ tự chèn |
| Bật access-order là có cache đầy đủ | Cần chính sách dung lượng, hết hạn và phối hợp nếu bài toán yêu cầu |

## 16. Bài tập tự kiểm tra có lời giải

### Bài 1: Truy cập lại một khóa

Map access-order có a,b,c. Get a thành công rồi get c thành công. Dãy cuối là gì?

**Lời giải:** sau get a là b,c,a; sau get c là b,a,c.

### Bài 2: Không tìm thấy khóa

Từ a,b,c, gọi getOrDefault("x", -1). Kết quả và thứ tự là gì?

**Lời giải:** trả -1; không thêm x, dãy vẫn a,b,c.

### Bài 3: Không thay giá trị

Từ a=1,b=2,c=3, gọi putIfAbsent("a", 99). Có giữ nguyên giá trị và thứ tự không?

**Lời giải:** giá trị a giữ 1 và phương thức trả 1, nhưng dãy thành b,c,a nếu a chưa ở cuối.

### Bài 4: Replace cùng giá trị

Từ a=1,b=2,c=3, gọi replace("a", 1, 1). Có cần giá trị mới khác giá trị cũ thì a mới được làm mới không?

**Lời giải:** không. Điều kiện khớp nên phép thay được thực hiện; a có thể được đưa cuối dù vẫn bằng 1.

### Bài 5: Bỏ qua giá trị null

Map có a=null,b=2,c=3. Trong đường cài đặt đã đối chiếu, computeIfPresent("a", (key, value) -> value + 1) có gọi hàm và đưa a về cuối không?

**Lời giải:** không. Nhánh này bỏ qua vì giá trị hiện có là null, không gọi hàm tính lại và không gọi afterNodeAccess. Đây là trường hợp cần đọc theo phạm vi cài đặt của bài.

### Bài 6: Hàm gộp trả null

Từ a=1,b=2,c=3, merge a với một giá trị không null nhưng hàm gộp trả null. A có trở thành entry cuối không?

**Lời giải:** ánh xạ a bị xóa; dãy còn b,c. Không có entry a để giữ ở cuối.

### Bài 7: Nguồn putAll

Đích đang a,b,c,d. Nguồn đưa b rồi a. Giả sử đợt cập nhật không xóa hay thêm khóa nào, dãy cuối là gì?

**Lời giải:** xử lý b tạo a,c,d,b; xử lý a tiếp theo tạo c,d,b,a.

### Bài 8: Chỉ đọc dữ liệu khi duyệt

Cần xuất các cặp đang có mà không làm mới lịch sử. Chọn keySet cộng get hay entrySet cộng getValue?

**Lời giải:** dùng entrySet và lấy khóa/giá trị từ entry. KeySet cộng get có thể đổi thứ tự và ảnh hưởng iterator đang duyệt map.

### Bài 9: Kiểm thử che mất thay đổi

Tất cả phép thử get đều chọn entry cuối. Dãy không đổi có chứng minh get không được tính là truy cập không?

**Lời giải:** không. Entry cuối đã ở vị trí mới nhất. Phải thử khóa ở đầu hoặc giữa để quan sát việc di chuyển.

### Bài 10: Quan sát có tác dụng phụ

Một bài kiểm thử kiểm tra giá trị bằng get("a") trước khi kiểm tra dãy. Có thể chính bước kiểm tra ấy làm kết quả dãy thay đổi không?

**Lời giải:** có. Với access-order, get có tác dụng lên lịch sử. Cần thiết kế bước xác minh không làm nhiễu trạng thái đang muốn kiểm tra.

## 17. Tài liệu đối chiếu

- [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): chế độ truy cập, danh sách thao tác, putAll, replace, view và giới hạn fail-fast.
- [LinkedHashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/LinkedHashMap.java): get, getOrDefault, afterNodeAccess, replaceAll và iterator.
- [HashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java): các nhánh putIfAbsent, replace, compute và merge được kế thừa.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): điều kiện giá trị null, hàm tính lại, ánh xạ và các view.

Khi dùng access-order, hãy xem thứ tự như một phần trạng thái mà thao tác có thể thay đổi. Muốn dự đoán đúng, cần xét loại API, điều kiện thực thi và cả những lời gọi quan sát hoặc hàm tính lại được thêm vào xung quanh.
