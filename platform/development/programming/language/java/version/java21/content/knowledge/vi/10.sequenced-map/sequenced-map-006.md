# sequencedKeySet, sequencedValues và sequencedEntrySet

Trong Java 21, SequencedMap cung cấp ba phương thức để lấy các view có thứ tự của key, value và entry: sequencedKeySet(), sequencedValues() và sequencedEntrySet(). Mỗi view giữ cùng encounter order với map, đồng thời công khai các thao tác đầu/cuối và đảo thứ tự thông qua các interface sequenced tương ứng.

Các view này được liên kết với map nền. Khi map thay đổi, nội dung và thứ tự mà view quan sát được cũng thay đổi; khi thực hiện thao tác xóa được hỗ trợ qua view, ánh xạ tương ứng bị xóa khỏi map.

## 1. Ba view và kiểu trả về

Ba phương thức có kiểu trả về khác nhau vì key, value và entry có những quy tắc riêng:

| Phương thức | Kiểu trả về | Đặc điểm |
|---|---|---|
| sequencedKeySet() | SequencedSet<K> | Tập key duy nhất theo encounter order của map |
| sequencedValues() | SequencedCollection<V> | Các value theo encounter order; value có thể trùng nhau |
| sequencedEntrySet() | SequencedSet<Map.Entry<K, V>> | Tập entry theo encounter order; mỗi key xuất hiện tối đa một lần |

Cả ba phương thức thuộc java.util.SequencedMap, có từ Java 21. Điểm khác biệt so với keySet(), values() và entrySet() là kiểu trả về của các phương thức sequenced thể hiện trực tiếp hợp đồng thứ tự và cho phép gọi các thao tác của SequencedSet hoặc SequencedCollection.

Ba view dùng cùng thứ tự mà map định nghĩa. Nếu map là LinkedHashMap theo thứ tự chèn, chúng phản ánh thứ tự chèn. Nếu map là TreeMap, chúng phản ánh thứ tự key theo comparator. Vì vậy, thứ tự view không phải lúc nào cũng là thứ tự các lệnh put đã được gọi.

## 2. Lấy và duyệt các view

Ví dụ sau dùng LinkedHashMap để encounter order dễ quan sát:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.SequencedCollection;
import java.util.SequencedMap;
import java.util.SequencedSet;

public class SequencedMapViews {
    public static void main(String[] args) {
        SequencedMap<String, Integer> scores = new LinkedHashMap<>();
        scores.put("An", 9);
        scores.put("Binh", 8);
        scores.put("Chi", 10);

        SequencedSet<String> keys = scores.sequencedKeySet();
        SequencedCollection<Integer> values = scores.sequencedValues();
        SequencedSet<Map.Entry<String, Integer>> entries =
                scores.sequencedEntrySet();

        System.out.println(keys);    // [An, Binh, Chi]
        System.out.println(values);  // [9, 8, 10]
        System.out.println(entries); // [An=9, Binh=8, Chi=10]

        System.out.println(keys.getFirst());     // An
        System.out.println(values.getLast());    // 10
        System.out.println(entries.getFirst());  // An=9
    }
}
~~~

keys và entries là các set nên không có phần tử trùng theo quy tắc của Set. values là một collection, không phải set: nếu nhiều key cùng ánh xạ tới một value, giá trị đó xuất hiện nhiều lần trong view.

Các view cũng có thể duyệt bằng vòng lặp hoặc Stream như những collection thông thường. Thứ tự duyệt là encounter order của map tại thời điểm duyệt.

## 3. Thao tác ở đầu và cuối

Do kiểu trả về là sequenced, có thể dùng các phương thức đầu/cuối trên từng view:

~~~java
SequencedSet<String> keys = scores.sequencedKeySet();
SequencedCollection<Integer> values = scores.sequencedValues();
SequencedSet<Map.Entry<String, Integer>> entries =
        scores.sequencedEntrySet();

String firstKey = keys.getFirst();
Integer lastValue = values.getLast();
Map.Entry<String, Integer> firstEntry = entries.getFirst();

System.out.println(firstKey);
System.out.println(lastValue);
System.out.println(firstEntry);
~~~

Các thao tác xóa ở hai đầu cũng tác động đến map nền:

~~~java
String removedKey = keys.removeFirst();
Integer removedValue = values.removeLast();
Map.Entry<String, Integer> removedEntry = entries.removeFirst();
~~~

Mỗi lệnh trên xóa phần tử tương ứng khỏi view và xóa ánh xạ liên quan khỏi map. Với sequencedValues(), nếu nhiều entry có cùng value thì removeFirst() hoặc removeLast() xóa ánh xạ tương ứng với lần xuất hiện đầu tiên hoặc cuối cùng của value theo encounter order.

Các lệnh xóa ở ví dụ là những thao tác riêng biệt. Khi chạy liên tiếp trên cùng một map, mỗi lệnh sẽ nhìn thấy thứ tự và nội dung sau những thay đổi của lệnh trước.

## 4. Các view là backed view

View không phải bản sao độc lập. Có thể giữ một view rồi tiếp tục cập nhật map:

~~~java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 9);
scores.put("Binh", 8);

SequencedSet<String> keys = scores.sequencedKeySet();
SequencedCollection<Integer> values = scores.sequencedValues();

scores.putLast("Chi", 10);

System.out.println(keys);   // [An, Binh, Chi]
System.out.println(values); // [9, 8, 10]

keys.remove("Binh");

System.out.println(scores); // {An=9, Chi=10}
~~~

Khi thêm hoặc cập nhật ánh xạ qua map, các view phản ánh thay đổi đó. Khi xóa key qua keys, ánh xạ tương ứng bị xóa khỏi scores, và view values cùng entry cũng phản ánh kết quả.

Điều này hữu ích khi một phương thức chỉ cần đọc hoặc loại bỏ key, value hay entry theo thứ tự mà không cần nhận hoặc thao tác trực tiếp trên toàn bộ map.

## 5. Đảo thứ tự bằng reversed()

Các view sequenced có phương thức reversed(). Phương thức này trả về view theo encounter order ngược và vẫn liên kết với cấu trúc dữ liệu gốc:

~~~java
SequencedSet<String> keys = scores.sequencedKeySet();
SequencedCollection<Integer> values = scores.sequencedValues();
SequencedSet<Map.Entry<String, Integer>> entries =
        scores.sequencedEntrySet();

System.out.println(keys.reversed());
System.out.println(values.reversed());
System.out.println(entries.reversed());
~~~

Với map có thứ tự [An, Binh, Chi], các view đảo lần lượt quan sát key [Chi, Binh, An], value và entry theo thứ tự tương ứng. Không cần sao chép các phần tử sang collection mới chỉ để duyệt ngược.

Map cũng có reversed(). View đảo của map và các view đảo của key, value, entry đều thể hiện cùng một hướng encounter order:

~~~java
SequencedMap<String, Integer> reverseMap = scores.reversed();

System.out.println(reverseMap.sequencedKeySet());
System.out.println(reverseMap.sequencedValues());
System.out.println(reverseMap.sequencedEntrySet());
~~~

Vì đây là các view, những thay đổi được hỗ trợ qua view đảo vẫn tác động đến map nền. Hướng đầu/cuối được hiểu theo thứ tự mà view đang công bố.

## 6. Thay đổi dữ liệu qua map và qua view

Các view cho phép quan sát và xóa phần tử, nhưng không cung cấp đủ dữ liệu để tạo một ánh xạ mới. Do đó, thao tác thêm phần tử qua các view không được hỗ trợ:

~~~java
keys.add("Dung"); // UnsupportedOperationException
values.add(7);    // UnsupportedOperationException
entries.add(Map.entry("Dung", 7)); // UnsupportedOperationException
~~~

Muốn thêm một ánh xạ, hãy gọi put, putFirst hoặc putLast trên map. Muốn thay value của một key, gọi put(key, newValue):

~~~java
scores.putLast("Dung", 7);
scores.put("An", 10);
~~~

Sau các lệnh này, các view đang được giữ sẽ phản ánh nội dung và encounter order mới. Với sequencedEntrySet(), không nên dựa vào Map.Entry.setValue() để thay đổi map vì khả năng hỗ trợ thao tác đó phụ thuộc hợp đồng của entry được trả về. Dùng map.put(key, value) là cách rõ ràng để cập nhật ánh xạ.

Các thao tác xóa qua view vẫn có thể không được hỗ trợ nếu map nền là map bất biến hoặc view chỉ đọc. Kiểu trả về sequenced không đồng nghĩa với việc map có thể sửa đổi.

## 7. Value trùng nhau và thao tác xóa

Một điểm cần chú ý là sequencedValues() là SequencedCollection, không phải SequencedSet. Một map có thể có nhiều key cùng value:

~~~java
SequencedMap<String, String> states = new LinkedHashMap<>();
states.put("job-1", "READY");
states.put("job-2", "RUNNING");
states.put("job-3", "READY");

SequencedCollection<String> values = states.sequencedValues();
System.out.println(values); // [READY, RUNNING, READY]

values.removeFirst();
System.out.println(states); // {job-2=RUNNING, job-3=READY}
~~~

removeFirst() loại bỏ lần xuất hiện đầu tiên của READY theo encounter order, tức entry có key job-1. Entry job-3 vẫn còn. Tương tự, removeLast() loại bỏ lần xuất hiện cuối cùng của value được chọn.

Khi cần biết chính xác key nào sẽ bị xóa, nên thao tác qua sequencedEntrySet() hoặc lấy key ở đầu/cuối rồi gọi map.remove(key). Không nên suy ra key chỉ từ value nếu value có thể trùng.

## 8. Những lưu ý về thứ tự và trạng thái map

- **Thứ tự phụ thuộc implementation:** LinkedHashMap theo thứ tự chèn, LinkedHashMap cấu hình access-order có thể đổi encounter order sau thao tác truy cập, còn TreeMap sắp xếp theo comparator của key.
- **View không đóng băng thứ tự:** khi map nền thay đổi, view tiếp tục phản ánh trạng thái mới. Không xem view như snapshot tại thời điểm gọi phương thức.
- **Không thêm qua view:** key set, values và entry set không thể tự tạo một ánh xạ mới; hãy thêm qua map.
- **Xóa phụ thuộc khả năng sửa đổi:** map bất biến hoặc view chỉ đọc không hỗ trợ xóa qua view.
- **Collection rỗng:** các phương thức getFirst() và getLast() của view ném NoSuchElementException nếu view không có phần tử.
- **Value có thể trùng:** sequencedValues() giữ từng lần xuất hiện theo thứ tự, không loại bỏ value trùng.

Với TreeMap, các view sequenced tuân theo thứ tự comparator. Việc đảo view làm đảo hướng duyệt; nó không biến map thành map theo thứ tự chèn.

## 9. Chọn view theo mục đích

| Mục đích | View phù hợp |
|---|---|
| Duyệt hoặc lấy key đầu/cuối | sequencedKeySet() |
| Duyệt value theo thứ tự, kể cả khi có giá trị trùng | sequencedValues() |
| Xử lý key và value cùng nhau theo thứ tự | sequencedEntrySet() |
| Xóa key ở đầu/cuối | sequencedKeySet().removeFirst() hoặc removeLast() |
| Xóa value ở lần xuất hiện đầu/cuối | sequencedValues().removeFirst() hoặc removeLast() |
| Xóa ánh xạ đầu/cuối và nhận cả key-value | sequencedEntrySet().removeFirst() hoặc removeLast() |
| Duyệt ngược | Gọi reversed() trên view hoặc map |
| Thêm hoặc cập nhật ánh xạ | Gọi put, putFirst hoặc putLast trên map |

Khi một API chỉ cần làm việc với danh sách key, dãy value hoặc tập entry có thứ tự, hãy nhận trực tiếp kiểu view tương ứng. Cách này giữ rõ ý định của mã và tận dụng được các thao tác đầu/cuối mà SequencedMap chuẩn hóa từ Java 21.
