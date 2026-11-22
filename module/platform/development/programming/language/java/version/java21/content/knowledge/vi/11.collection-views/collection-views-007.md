# Quy tắc equals, hashCode và thứ tự của List, Set, Map

Trong Java, List, Set và Map có quy tắc bằng nhau khác nhau. List xem xét thứ tự phần tử; Set xem xét tập phần tử; Map xem xét các cặp key-value. Thứ tự duyệt của một collection có thể quan sát được trong lúc chạy, nhưng không phải lúc nào cũng tham gia vào equals() hoặc hashCode().

Hiểu rõ ba quy tắc này giúp tránh lỗi khi so sánh collection, dùng collection làm key của HashMap, lưu phần tử trong HashSet hoặc làm việc với các view có thể thay đổi theo collection nền.

## 1. Hợp đồng chung của equals() và hashCode()

Phương thức equals() xác định hai đối tượng có được xem là bằng nhau theo ý nghĩa của kiểu dữ liệu hay không. hashCode() trả về một giá trị int dùng trong các cấu trúc dựa trên bảng băm.

Hợp đồng quan trọng của Object:

- Nếu hai đối tượng bằng nhau theo equals(), chúng bắt buộc phải có cùng hashCode().
- Nếu hai đối tượng có cùng hashCode(), chúng không nhất thiết bằng nhau theo equals(); va chạm hash là hợp lệ.
- Khi thông tin được dùng trong equals() không thay đổi, kết quả hashCode() phải nhất quán trong cùng một lần thực thi chương trình.
- equals() phải có tính phản xạ, đối xứng, bắc cầu, nhất quán và trả về false khi so sánh với null.

Có thể ghi nhớ quan hệ bắt buộc như sau:

~~~text
a.equals(b) == true
        |
        +----> a.hashCode() == b.hashCode()

a.hashCode() == b.hashCode()
        |
        +----> Không suy ra a.equals(b)
~~~

Khi tự viết một class có equality theo giá trị, phải ghi đè equals() và hashCode() nhất quán. Chỉ ghi đè một trong hai có thể làm HashSet, HashMap hoặc các API collection hoạt động sai so với ý định.

## 2. List: thứ tự là một phần của equality

Hai List bằng nhau khi chúng có cùng số phần tử và các phần tử ở từng vị trí tương ứng bằng nhau theo equals(). Thứ tự vì vậy có ý nghĩa:

~~~java
import java.util.List;

List<String> first = List.of("red", "green", "blue");
List<String> second = List.of("red", "green", "blue");
List<String> reversed = List.of("blue", "green", "red");

System.out.println(first.equals(second));   // true
System.out.println(first.equals(reversed)); // false
~~~

Hai list đầu bằng nhau vì các phần tử tương ứng giống nhau theo thứ tự. List thứ ba chứa cùng các giá trị nhưng thứ tự khác, nên không bằng nhau.

Theo hợp đồng List, hashCode() được tính tuần tự từ đầu đến cuối. Công thức tương đương:

~~~java
int hash = 1;
for (E element : list) {
    hash = 31 * hash + (element == null ? 0 : element.hashCode());
}
~~~

Do công thức có xét thứ tự, hai list bằng nhau sẽ có cùng hash code. Đổi thứ tự phần tử thường làm thay đổi hash code, nhưng không được dùng hash code để kết luận hai list khác nhau vì vẫn có thể xảy ra va chạm.

List cho phép phần tử trùng và, tùy implementation, có thể cho phép null. Những đặc điểm này không thay đổi quy tắc equality theo vị trí.

## 3. Set: equality không phụ thuộc encounter order

Hai Set bằng nhau khi chúng có cùng kích thước và chứa cùng các phần tử theo equality của phần tử. Thứ tự duyệt không tham gia vào phép so sánh:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

Set<String> first = new LinkedHashSet<>(List.of("red", "green", "blue"));
Set<String> second = new LinkedHashSet<>(List.of("blue", "red", "green"));

System.out.println(first.equals(second)); // true
~~~

Hai set có thể duyệt theo thứ tự khác nhau nhưng vẫn bằng nhau vì chúng chứa cùng tập phần tử.

Set tính hash code bằng tổng hash code của các phần tử; thứ tự cộng không ảnh hưởng kết quả:

~~~java
int hash = 0;
for (E element : set) {
    hash += (element == null ? 0 : element.hashCode());
}
~~~

Vì vậy, các Set bằng nhau theo equals() sẽ có cùng hash code dù encounter order khác nhau. Set không cho phép hai phần tử bằng nhau cùng tồn tại theo hợp đồng của nó.

## 4. Map: equality dựa trên ánh xạ key-value

Hai Map bằng nhau khi chúng có cùng tập key và mỗi key ánh xạ tới value bằng nhau theo equals(). Thứ tự duyệt entry không ảnh hưởng đến equality:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> first = new LinkedHashMap<>();
first.put("An", 9);
first.put("Binh", 8);

Map<String, Integer> second = new LinkedHashMap<>();
second.put("Binh", 8);
second.put("An", 9);

System.out.println(first.equals(second)); // true
~~~

Hai map có thứ tự duyệt khác nhau nhưng vẫn bằng nhau vì các ánh xạ giống nhau.

hashCode() của Map bằng tổng hash code của các entry. Hash code của một entry được xác định bằng phép XOR giữa hash code của key và value:

~~~java
int entryHash = Objects.hashCode(key) ^ Objects.hashCode(value);
int mapHash = 0;
for (Map.Entry<K, V> entry : map.entrySet()) {
    mapHash += entry.hashCode();
}
~~~

Phép tính này không phụ thuộc thứ tự entry. Do đó, hai map bằng nhau theo equals() phải có cùng hash code dù được tạo theo thứ tự put khác nhau.

## 5. So sánh ba quy tắc

| Kiểu | Điều kiện equals() | hashCode() | Thứ tự có ảnh hưởng? |
|---|---|---|---|
| List | Cùng kích thước và phần tử tương ứng bằng nhau tại từng vị trí | Tính tuần tự từ phần tử đầu đến cuối | Có |
| Set | Cùng kích thước và cùng các phần tử | Tổng hash code của các phần tử | Không |
| Map | Cùng key và value tương ứng | Tổng hash code của các entry | Không |

Không nên nhầm equality với encounter order. Một LinkedHashSet có thể duyệt theo thứ tự chèn, một TreeSet có thể duyệt theo comparator, nhưng hai Set vẫn bằng nhau nếu chứa cùng phần tử. Tương tự, LinkedHashMap và TreeMap có thể có thứ tự entry khác nhau nhưng bằng nhau nếu có cùng ánh xạ.

## 6. Encounter order phụ thuộc kiểu collection

Interface cơ sở không phải lúc nào cũng cam kết thứ tự duyệt:

| Kiểu | Cam kết về thứ tự |
|---|---|
| List | Thứ tự phần tử là một phần của hợp đồng List |
| HashSet | Không bảo đảm thứ tự duyệt |
| LinkedHashSet | Duy trì encounter order, mặc định là thứ tự chèn |
| TreeSet | Duyệt theo thứ tự comparator |
| HashMap | Không bảo đảm thứ tự duyệt |
| LinkedHashMap | Duy trì thứ tự chèn hoặc thứ tự truy cập tùy cấu hình |
| TreeMap | Duyệt theo thứ tự comparator của key |

HashSet và HashMap có thể tình cờ hiển thị cùng một thứ tự trong một lần chạy, nhưng chương trình không được dựa vào thứ tự đó. Thứ tự có thể thay đổi theo dữ liệu, kích thước bảng, implementation hoặc phiên bản runtime.

Từ Java 21, các kiểu có encounter order xác định còn có thể được sử dụng qua SequencedCollection, SequencedSet và SequencedMap. Những interface này chuẩn hóa thao tác đầu/cuối và view đảo thứ tự; chúng không thay đổi quy tắc equals() và hashCode() của List, Set hoặc Map.

## 7. SortedSet và SortedMap: comparator cần nhất quán với equals

TreeSet và TreeMap dùng natural ordering hoặc Comparator để xác định vị trí và nhận diện phần tử/key tương đương trong cấu trúc sắp xếp. Với các kiểu này, comparator nên nhất quán với equals(): biểu thức compare(a, b) == 0 nên tương đương với a.equals(b).

Nếu comparator xem hai đối tượng là tương đương trong khi equals() xem chúng khác nhau, sorted collection vẫn có thể thực hiện các thao tác theo comparator, nhưng nó không còn tuân thủ đầy đủ hợp đồng chung của Set hoặc Map. Điều này có thể gây bất ngờ khi so sánh với HashSet hoặc HashMap, thậm chí làm mất tính đối xứng của equals().

Ví dụ, comparator không phân biệt chữ hoa/chữ thường xem "java" và "JAVA" là cùng vị trí:

~~~java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

Set<String> sorted = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
sorted.add("java");

Set<String> hashed = new HashSet<>();
hashed.add("JAVA");

System.out.println(sorted.contains("JAVA")); // true
System.out.println(sorted.equals(hashed));   // true trong ví dụ này
System.out.println(hashed.equals(sorted));   // false
~~~

Ví dụ này minh họa comparator không nhất quán với String.equals(). Không nên dùng cấu hình như vậy nếu collection cần tuân thủ đầy đủ hợp đồng Set. Hãy chọn comparator nhất quán với equals(), hoặc chuẩn hóa dữ liệu trước khi đưa vào collection.

## 8. Vì sao hashCode quan trọng với HashSet và HashMap?

Các collection dựa trên bảng băm dùng hashCode() để xác định vùng tìm kiếm, sau đó dùng equals() để phân biệt các đối tượng trong vùng đó. Có thể hình dung quá trình tra cứu như sau:

~~~text
Đối tượng cần tìm
       |
       v
   hashCode()
       |
       v
Chọn vùng/bucket
       |
       v
So sánh equals() với phần tử hoặc key trong bucket
       |
       v
Tìm thấy hoặc không tìm thấy
~~~

Nếu hai đối tượng bằng nhau nhưng có hash code khác nhau, chúng có thể được đặt vào các bucket khác nhau và HashSet/HashMap không tìm thấy đối tượng theo cách mong đợi. Đây là lý do equals() và hashCode() phải được ghi đè cùng nhau.

Một hash code tốt giúp phân bố dữ liệu đều hơn, giảm va chạm và cải thiện hiệu năng trung bình. Tuy nhiên, không có yêu cầu mọi đối tượng khác nhau phải có hash code khác nhau.

## 9. Không thay đổi trạng thái equality khi phần tử đang nằm trong hash collection

Không nên thay đổi các trường được dùng trong equals() hoặc hashCode() của một đối tượng sau khi đưa nó vào HashSet hoặc dùng làm key trong HashMap:

~~~java
import java.util.HashMap;
import java.util.Map;

final class UserKey {
    private String email;

    UserKey(String email) {
        this.email = email;
    }

    void setEmail(String email) {
        this.email = email;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof UserKey key
                && email.equals(key.email);
    }

    @Override
    public int hashCode() {
        return email.hashCode();
    }
}

Map<UserKey, String> sessions = new HashMap<>();
UserKey key = new UserKey("a@example.com");
sessions.put(key, "active");

key.setEmail("b@example.com");
// Tra cứu bằng key sau khi thay đổi có thể không tìm thấy entry đã lưu.
~~~

Sau khi email thay đổi, hash code của key cũng thay đổi. Entry vẫn nằm ở vị trí bucket được xác định bằng hash code cũ, trong khi thao tác tra cứu sử dụng hash code mới. Kết quả là get() hoặc remove() có thể không tìm thấy entry.

Giải pháp tốt là dùng key bất biến: các trường tham gia equals() và hashCode() không thay đổi trong suốt vòng đời key. Record thường phù hợp cho key theo giá trị:

~~~java
record UserKey(String email) {}
~~~

Record tự sinh equals() và hashCode() dựa trên các component. Tuy nhiên, tính bất biến của record chỉ là bất biến nông: nếu component tham chiếu tới một đối tượng mutable, trạng thái bên trong đối tượng đó vẫn có thể thay đổi.

## 10. Cẩn thận với array và component mutable

Array trong Java dùng equality theo identity: hai array có cùng nội dung vẫn không bằng nhau qua equals() mặc định của array. Vì vậy, record có component là array cũng không tự động so sánh nội dung sâu của array:

~~~java
record Payload(byte[] data) {}

Payload first = new Payload(new byte[] {1, 2});
Payload second = new Payload(new byte[] {1, 2});

System.out.println(first.equals(second)); // false
~~~

Nếu equality phải dựa trên nội dung array, hãy định nghĩa rõ equals() và hashCode() bằng Arrays.equals() và Arrays.hashCode(), đồng thời cân nhắc sao chép phòng vệ array khi nhận hoặc trả dữ liệu. Nếu component mutable tham gia equality, việc thay đổi nó cũng có thể làm hash code của record thay đổi.

## 11. View, wrapper không sửa đổi và bản sao

Một collection view có thể dùng chính equals() và hashCode() theo interface mà nó triển khai, nhưng nội dung của view có thể thay đổi khi collection nền thay đổi. Ví dụ, một key set của Map là Set; equality và hash code của nó dựa trên các key hiện có.

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 9);
scores.put("Binh", 8);

Set<String> keys = scores.keySet();
int oldHash = keys.hashCode();

scores.put("Chi", 10);
int newHash = keys.hashCode();
~~~

Sau khi map thay đổi, key set phản ánh key mới và hash code có thể thay đổi. Vì vậy, không dùng một view mutable hoặc backed view làm key trong HashMap hay phần tử trong HashSet nếu nội dung nền có thể thay đổi.

Phân biệt hai cách tạo collection không sửa đổi thường gặp:

- Collections.unmodifiableList(list) tạo wrapper chỉ đọc trên list nền; thay đổi trực tiếp list nền vẫn được phản ánh qua wrapper.
- List.copyOf(list) tạo một list không sửa đổi chứa các phần tử tại thời điểm gọi; các thay đổi cấu trúc về sau của list nguồn không được phản ánh vào bản copy.

Set.copyOf() và Map.copyOf() cung cấp cách tạo bản sao không sửa đổi tương ứng cho Set và Map. Đây đều là bản sao nông: đối tượng phần tử, key hoặc value mutable vẫn có thể thay đổi trạng thái nội tại. Không sửa đổi collection không tự động làm cho các phần tử trở nên bất biến.

## 12. Checklist khi triển khai equals() và hashCode()

- [ ] Xác định equality theo đúng ý nghĩa kiểu dữ liệu: theo vị trí cho List, theo thành viên cho Set, theo ánh xạ cho Map.
- [ ] Nếu ghi đè equals(), luôn ghi đè hashCode() tương ứng.
- [ ] Bảo đảm hai đối tượng bằng nhau luôn có cùng hash code.
- [ ] Không giả định hash code duy nhất hoặc dùng nó thay cho ID.
- [ ] Giữ ổn định các trường tham gia equality khi đối tượng được dùng làm phần tử của Set hoặc key của Map.
- [ ] Với TreeSet và TreeMap, chọn comparator nhất quán với equals().
- [ ] Không dựa vào thứ tự duyệt của HashSet hoặc HashMap.
- [ ] Kiểm tra cách xử lý array và component mutable trong record hoặc class theo giá trị.
- [ ] Không dùng backed view có thể thay đổi làm key hoặc phần tử trong hash collection.

Các quy tắc này giúp equality, hash-based lookup và encounter order được hiểu như ba khía cạnh liên quan nhưng riêng biệt. Khi thiết kế collection hoặc view, hãy xác định rõ dữ liệu nào quyết định equality, dữ liệu nào quyết định thứ tự và trạng thái nào có thể thay đổi trong thời gian đối tượng được lưu trữ.
