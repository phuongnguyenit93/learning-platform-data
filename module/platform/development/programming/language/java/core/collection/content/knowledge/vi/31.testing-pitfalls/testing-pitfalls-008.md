# Lỗi khóa khả biến, comparator không nhất quán và phần tử “mất dấu”

Một collection có thể vẫn chứa đối tượng nhưng chương trình không tìm được nó bằng cách tra cứu thông thường. Hiện tượng này thường đến từ **quy tắc định danh đã thay đổi** hoặc **quy tắc so sánh không phù hợp**, chứ không nhất thiết do phần tử bị xóa khỏi bộ nhớ.

Bài học phân biệt ba cơ chế: (1) cấu trúc băm dùng `hashCode` và `equals`, (2) cấu trúc sắp xếp dùng `Comparator`/`Comparable`, và (3) đối tượng hoặc khóa thay đổi sau khi được đưa vào cấu trúc. Đây là các lỗi về *hợp đồng dữ liệu*; thay đổi thao tác tìm kiếm đơn lẻ không sửa được gốc rễ.

## 1. “Có trong cấu trúc” khác với “tìm được bằng quy tắc hiện tại”

Giả sử `Map` lưu một hồ sơ theo khóa đối tượng. Sau khi chèn, chương trình có thể đổi một trường của khóa. Mã tra cứu về sau tính toán dựa trên trạng thái mới, trong khi cấu trúc đã sắp xếp/lưu khóa theo trạng thái cũ. Kết quả có thể là `get` trả `null`, `containsKey` trả `false` hoặc `remove` không tìm được phần tử dù khi duyệt ta vẫn quan sát thấy tham chiếu đó.

Cần hỏi ba câu trước khi kết luận dữ liệu “biến mất”:

1. Đối tượng có thật sự bị loại khỏi collection hay chỉ không được tìm thấy?
2. Quy tắc `equals`, `hashCode`, hoặc `compare` có thay đổi từ lúc thêm tới lúc tìm không?
3. Cấu trúc dựa vào **băm**, **thứ tự so sánh**, hay chỉ **vị trí/chỉ số** để tra cứu?

`HashMap` và `HashSet` sử dụng băm để tổ chức và tìm phần tử. `TreeMap` và `TreeSet` dựa vào quan hệ thứ tự. `ArrayList` lại có cơ chế tìm theo `equals` qua việc duyệt các phần tử. Vì vậy cùng một sai sót có thể xuất hiện khác nhau tùy cấu trúc.

## 2. Khóa khả biến trong HashMap/HashSet

Điều kiện thiết yếu cho khóa băm là: **trong toàn bộ thời gian khóa nằm trong cấu trúc, các dữ liệu ảnh hưởng đến `equals` và `hashCode` phải ổn định**. Hai đối tượng bằng nhau theo `equals` phải có cùng `hashCode`; hai đối tượng có cùng mã băm thì *chưa chắc* bằng nhau.

Ví dụ kiểu khóa nguy hiểm:

```java
import java.util.Objects;

final class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey key
                && Objects.equals(code, key.code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}
```

Một tình huống lỗi điển hình là:

```java
MutableKey key = new MutableKey("alpha");
Map<MutableKey, String> map = new HashMap<>();
map.put(key, "Đã lưu");

key.code = "beta"; // thay đổi đầu vào của equals/hashCode
String result = map.get(key); // không còn có bảo đảm tra cứu như trước
```

Khi `put`, `HashMap` chọn vị trí lưu bằng giá trị băm thời điểm đó. Sau khi `code` đổi, mã băm có thể khác; yêu cầu tìm kiếm có thể đi tới vùng khác. **Không khẳng định mọi thay đổi đều gây `null`:** có thể tình cờ trùng vùng băm hoặc một trường không ảnh hưởng mã băm. Vấn đề là hợp đồng sử dụng đã không còn đáng tin và theo Javadoc `Map`, hành vi khi khóa thay đổi theo cách ảnh hưởng so sánh `equals` là không được xác định.

Với `HashSet`, phần tử đóng vai trò khóa của cấu trúc băm. Một phần tử có trường định danh bị sửa sau `add` cũng có thể không tìm/xóa được bằng quy tắc hiện tại. Gọi `remove` trước khi sửa, rồi `add` lại sau khi sửa là một cách hợp lệ **nếu** bạn bảo đảm thao tác đơn luồng hoặc đồng bộ đúng và không làm thay đổi định danh trong lúc nó đang nằm trong Set.

### Chọn khóa ổn định

Ưu tiên giá trị định danh bất biến, chẳng hạn một mã đã chuẩn hóa, `String`, `UUID` hoặc một `record` không giữ thành phần khả biến tham gia định danh:

```java
record CustomerKey(String tenant, String customerId) {}

Map<CustomerKey, String> customers = new HashMap<>();
customers.put(new CustomerKey("vn", "C-42"), "Lan");
System.out.println(customers.get(new CustomerKey("vn", "C-42")));
```

Đầu ra:

```text
Lan
```

Hai record khác nhau có cùng thành phần mang giá trị bằng nhau được so khớp đúng. Tuy nhiên, **`record` không tự làm bất biến sâu**: nếu một thành phần là `List` khả biến và nội dung list tham gia `equals`/`hashCode`, việc sửa list vẫn có thể phá quy tắc khóa. Hãy dùng thành phần bất biến hoặc tạo bản sao bất biến đúng chỗ.

## 3. Comparator “đánh đồng” hai giá trị khác nhau

Một `TreeSet` quyết định một phần tử mới có trùng với phần tử đã có hay không bằng kết quả `compare(a, b) == 0`. Nó không gọi `equals` như một bước kiểm tra trùng bổ sung. Nếu comparator chỉ xét một phần dữ liệu, hai phần tử thực sự khác nhau có thể bị xem là một.

Chương trình `ComparatorPitfallDemo.java`:

```java
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

public class ComparatorPitfallDemo {
    public static void main(String[] args) {
        Set<String> names = new TreeSet<>(
                Comparator.comparingInt(String::length)
        );
        System.out.println(names.add("Lan"));
        System.out.println(names.add("Min"));
        System.out.println(names.contains("Min"));
        System.out.println(names);
    }
}
```

Chạy:

```text
javac -encoding UTF-8 --release 17 ComparatorPitfallDemo.java
java -Dfile.encoding=UTF-8 ComparatorPitfallDemo
```

Đầu ra:

```text
true
false
true
[Lan]
```

`"Lan"` và `"Min"` dài bằng nhau, nên comparator trả `0`. `add("Min")` không thêm giá trị mới; `contains("Min")` lại là `true` vì tìm thấy một phần tử tương đương **theo comparator**. Như vậy `contains` không có nghĩa rằng chuỗi `"Min"` từng được lưu. Đây không phải lỗi ngẫu nhiên của JVM.

Nếu muốn sắp xếp tên theo độ dài nhưng vẫn phân biệt chuỗi khác nhau, thêm tiêu chí phụ:

```java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
Set<String> names = new TreeSet<>(byLengthThenText);
names.add("Lan");
names.add("Min");
System.out.println(names);
```

Đầu ra:

```text
[Lan, Min]
```

Tiêu chí phụ giúp tránh việc hai tên *khác nội dung* cùng độ dài bị gộp. Nếu mô hình nghiệp vụ coi hai chuỗi khác nhau theo chữ hoa/thường là cùng người, hãy định nghĩa **định danh nghiệp vụ** riêng; đừng ngầm suy rằng `Comparator.naturalOrder()` có cùng ý nghĩa với định danh người.

Với `TreeMap`, comparator cũng quyết định khóa nào được xem là tương đương. Nếu hai khóa so sánh bằng `0`, `put` khóa thứ hai có thể **cập nhật giá trị gắn với khóa hiện có**, thay vì tạo thêm entry mới. Điều này rất nguy hiểm nếu tác giả chỉ mong comparator chi phối cách hiển thị.

## 4. Comparator phải thỏa hợp đồng thứ tự

Một comparator hợp lệ không cần trả chính xác `-1` hoặc `1`; chỉ dấu âm, không hoặc dương có ý nghĩa. Nó phải bảo đảm:

- **Đối xứng về dấu:** dấu của `compare(a,b)` phải ngược dấu `compare(b,a)`.
- **Bắc cầu:** nếu `a > b` và `b > c` theo comparator thì `a > c`.
- **Nhất quán của nhóm bằng nhau:** nếu `compare(a,b)==0` thì với mọi `z`, dấu so sánh `a` với `z` và `b` với `z` phải giống nhau.
- Với `SortedSet`/`SortedMap`, nên **nhất quán với `equals`** nếu cần tuân thủ đầy đủ hợp đồng `Set`/`Map`.

Ví dụ sai dễ gặp:

```java
Comparator<Integer> wrong = (a, b) -> a - b;
```

Phép trừ có thể **tràn số**, dẫn tới dấu sai. Dùng `Integer.compare(a, b)`. Comparator viết kiểu “nếu một người ưu tiên thì đứng trước; nếu không thì đứng sau” mà không xử lý trường hợp ngang nhau thường phá đối xứng. Comparator phụ thuộc vào thời gian hiện tại, cấu hình thay đổi, hoặc trạng thái khả biến bên ngoài cũng không phù hợp để làm quy tắc ổn định cho `TreeSet`/`TreeMap`.

Một bộ sắp xếp không hợp đồng có thể cho kết quả sai và trong một số thuật toán sắp xếp có thể phát sinh `IllegalArgumentException` về vi phạm contract. **Không dựa vào việc có/không có ngoại lệ để chứng minh comparator đúng.**

## 5. Trường tham gia thứ tự cũng không nên thay đổi khi đang nằm trong TreeSet/TreeMap

`TreeSet` đặt phần tử vào cấu trúc cây dựa trên thứ tự tại thời điểm chèn. Nếu đối tượng đổi một trường mà comparator đang đọc, cấu trúc không tự dựng lại cây.

Ví dụ một `Task` có `priority` được chỉnh sau khi thêm vào `TreeSet<Task>`. Duyệt cây có thể cho thứ tự không còn đúng; `contains`/`remove` có thể không đi theo nhánh chứa đối tượng. Cũng như với khóa băm, không phải mọi lần sửa đều thể hiện lỗi ngay, nhưng việc sửa làm hỏng bất biến của cấu trúc.

Cách sửa theo từng nhu cầu:

| Nhu cầu | Mô hình phù hợp |
| --- | --- |
| Khóa nghiệp vụ ổn định, nội dung bản ghi thay đổi | Khóa `record`/ID bất biến → value khả biến trong `Map` |
| Cần cập nhật một phần tử trong tập có thứ tự | `remove` khi còn trạng thái cũ → tạo phần tử/khóa mới → `add` |
| Ưu tiên công việc liên tục thay đổi | Quản lý lại hàng đợi/cấu trúc theo chính sách cập nhật; không nghĩ `PriorityQueue` tự sắp lại khi sửa đối tượng |
| Chỉ cần danh sách hiển thị mới nhất | Giữ dữ liệu nguồn ổn định và tạo danh sách mới để `sort` khi cần |
| Muốn so sánh nhiều tiêu chí | Comparator đủ tiêu chí phân biệt theo đúng mô hình định danh |

**Chú ý:** `PriorityQueue` không đảm bảo tự điều chỉnh vị trí khi sửa độ ưu tiên của phần tử đã ở trong heap. Một bản ghi “thay đổi priority tại chỗ” có thể khiến `peek`/`poll` không còn phản ánh ưu tiên như mong đợi.

## 6. Cách điều tra khi phần tử “mất dấu”

1. **Chụp dữ liệu trước khi chèn:** trường tham gia `equals`/`hashCode`/`compare`, định danh và kết quả so sánh với khóa khác.
2. **Tách tra cứu khỏi duyệt:** với Map/Set, kiểm tra `get`/`contains` và đồng thời quan sát các entry qua phép duyệt (trong môi trường kiểm thử đơn luồng). Đừng sửa dữ liệu trong lúc kiểm tra.
3. **So sánh trạng thái hiện tại với snapshot:** một trường định danh bị cập nhật có thể giải thích việc băm/thứ tự thay đổi.
4. **Thử hai đối tượng khác tham chiếu nhưng cùng định danh:** chúng phải có kết quả `equals` và `hashCode` tương thích; trong cấu trúc sắp xếp, thử `compare` tương ứng.
5. **Tạo phép thử nhỏ tái hiện:** thêm hai chuỗi cùng độ dài vào TreeSet để xác minh điều kiện comparator; dùng lớp khóa khả biến trong test để chứng minh rủi ro.
6. **Đổi mô hình dữ liệu:** ưu tiên khóa bất biến, comparator ổn định và tách trường dùng sắp xếp khỏi trường chỉnh sửa thường xuyên.

Không dựa vào thứ tự in từ `HashMap` hoặc `HashSet` để xác định trạng thái đúng; các cấu trúc này không hứa giữ thứ tự chèn. Kiểm tra điều kiện dữ liệu bằng các phép khẳng định như `containsKey`, giá trị nhận được, và số lượng phần tử.

## 7. Bài tự kiểm tra

- Hai đối tượng có cùng `hashCode` nhưng `equals` trả `false` có là cùng khóa trong `HashMap` không? **Không.** Va chạm băm được xử lý bằng so khớp tương ứng.
- `TreeSet<String>` so theo độ dài và đã chứa `"Lan"`. Khi thêm `"Min"`, chuyện gì xảy ra? **Không thêm** vì comparator trả `0`; `contains("Min")` vẫn có thể trả `true`.
- Khi đổi giá trị `phone` của `Customer`, có luôn làm hỏng khóa trong `HashMap` không? **Không**, nếu `phone` không tham gia định nghĩa `equals`/`hashCode`; phải xem hợp đồng kiểu khóa.
- Có thể sửa mọi vấn đề bằng cách gọi `rehash` trên `HashMap` không? **Không** có API `rehash` công khai để người dùng tùy tiện “chữa” hợp đồng sai. Sửa thiết kế khóa và vòng đời cập nhật.
- Tại sao thêm `thenComparing` hữu ích? Vì tiêu chí bổ sung giúp phân biệt các trường hợp tiêu chí đầu cho kết quả `0`, miễn nó phù hợp định danh và thứ tự nghiệp vụ.

## Tài liệu tham khảo

- Javadoc `Map` (Java SE 21), mục cảnh báo khóa khả biến: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html
- Javadoc `SortedSet` (Java SE 21), điều kiện thứ tự nhất quán với equals: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html
- Javadoc `Comparator` (Java SE 21), quy tắc dấu và tính bắc cầu: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html
