# Dung lượng dự phòng, nút liên kết và bộ nhớ cho từng phần tử

## 1. Vì sao cùng số phần tử nhưng bộ nhớ khác nhau?

Một collection không chỉ gồm dữ liệu mà người dùng đưa vào. Nó còn cần cấu trúc để giữ các tham chiếu, tìm phần tử và thực hiện thao tác thêm/xóa. Hai danh sách cùng chứa 100.000 đối tượng có thể khác đáng kể về số byte và số đối tượng phụ trợ.

Để đọc đúng chi phí bộ nhớ, hãy tách ba lớp:

1. **Đối tượng collection**: các trường như số phần tử, tham chiếu đến mảng hoặc nút đầu/cuối.
2. **Cấu trúc lưu trữ**: mảng tham chiếu, ô dự phòng, nút liên kết hoặc bảng bucket.
3. **Đối tượng dữ liệu**: các đối tượng được tham chiếu tới, kể cả những đối tượng nằm sâu hơn trong đồ thị dữ liệu.

Bài này đi từ sức chứa của mảng đến chi phí nút, rồi xây dựng cách tính và đo bộ nhớ cho mỗi phần tử. Mục tiêu là giải thích được bộ nhớ đang nằm ở đâu; không học thuộc một con số byte cho mọi JVM.

## 2. `size`, sức chứa và phần dự phòng

Với danh sách dựa trên mảng, gọi:

- `n = size()`: số phần tử đang thuộc danh sách.
- `c`: sức chứa (capacity), tức số ô của mảng lưu trữ.
- `c - n`: số ô dự phòng chưa dùng.
- `n / c`: tỷ lệ sử dụng sức chứa, khi `c > 0`.

Ví dụ `n = 100.000`, `c = 150.000`: còn 50.000 ô dự phòng; phần dự phòng bằng 50% số phần tử đang dùng nhưng chỉ bằng khoảng 33,3% sức chứa. Hai tỷ lệ có mẫu số khác nhau nên không được gọi lẫn nhau.

Một ô trong `Object[]` chứa **tham chiếu**, không chứa toàn bộ đối tượng. Ô chưa dùng thường chứa `null`; nó vẫn chiếm chỗ trong mảng, nhưng không đồng nghĩa có một đối tượng dữ liệu đã được tạo sẵn. Đặt trước sức chứa một triệu ô không tạo trước một triệu `String`, `Integer` hoặc đối tượng nghiệp vụ.

Sơ đồ minh họa, không mô tả địa chỉ thật:

```text
ArrayList
  |
  +--> Object[]: [ref A][ref B][ref A][null][null]
                    |      |      |
                    +------|------+--> đối tượng A
                           +---------> đối tượng B

size = 3; sức chứa = 5; số đối tượng dữ liệu khác nhau = 2
```

Việc cùng một tham chiếu xuất hiện nhiều lần làm tăng số phần tử và số ô đang dùng, nhưng không sao chép đối tượng dữ liệu.

## 3. `ArrayList`: đổi phần dự phòng lấy ít lần cấp phát hơn

`ArrayList` sử dụng mảng có thể mở rộng. Khi còn chỗ, thêm cuối chủ yếu ghi một tham chiếu vào ô tiếp theo; khi hết chỗ, việc tăng sức chứa có thể cần mảng mới và sao chép tham chiếu. Phần dự phòng giúp nhiều lần thêm sau đó tránh phải thay mảng.

API bảo đảm sức chứa đủ cho số phần tử; không quy định một hệ số tăng cố định cho mọi phiên bản. Không xây logic ứng dụng dựa trên nhận định “luôn tăng đúng 1,5 lần”. [Tài liệu `ArrayList`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).

### 3.1. Chọn thời điểm cấp phát

- Biết gần đúng số phần tử cuối cùng: truyền sức chứa ban đầu hoặc gọi `ensureCapacity` trước một đợt thêm lớn.
- Chưa biết quy mô: để danh sách tăng tự động thường đơn giản hơn; đo trước khi đặt một mức dự phòng lớn cho mọi danh sách.
- Có nhiều danh sách nhỏ hoặc rỗng: chi phí cố định của từng collection và từng mảng có thể quan trọng hơn chi phí mỗi phần tử ở danh sách lớn.

Ở OpenJDK 21, constructor không đối số dùng một mảng rỗng chung và hoãn cấp phát mảng riêng đến khi cần. Vì vậy không suy từ mô tả sức chứa mặc định rằng mọi danh sách rỗng đã giữ riêng mười ô. Đây là chi tiết triển khai cần gắn với phiên bản khi phân tích heap.

### 3.2. Xóa phần tử và thu nhỏ mảng là hai việc khác nhau

Trong OpenJDK 21, xóa phần tử khỏi `ArrayList` bỏ tham chiếu không còn dùng ở phần đuôi sau khi dịch chuyển; `clear()` bỏ các tham chiếu phần tử nhưng giữ mảng hiện có. Vì thế `size() == 0` chưa chứng minh mảng dự phòng đã được giải phóng.

`trimToSize()` yêu cầu sức chứa về số phần tử hiện tại. Nó có thể tạo và sao chép sang mảng nhỏ hơn; không nên gọi sau mỗi lần `add` trong một vòng lặp. Cách đó có thể làm mất lợi ích của tăng trưởng có dự phòng và khiến tổng lượng sao chép tăng mạnh.

Thu nhỏ sau một đợt dữ liệu lớn có thể hợp lý nếu danh sách sẽ sống lâu với ít phần tử. Nếu sắp nạp lại quy mô tương tự, giữ mảng lại có thể tiết kiệm cấp phát. [Mã nguồn `ArrayList` của OpenJDK 21](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/ArrayList.java).

### 3.3. Bộ nhớ ổn định và bộ nhớ tại thời điểm mở rộng

Giả sử cần thay mảng cũ sức chứa `c` bằng mảng mới sức chứa `c'`. Trong lúc sao chép, hai mảng có thể cùng tồn tại. Phần lưu trữ đỉnh khi đó gần với tổng hai mảng, cộng các đối tượng liên quan, thay vì chỉ mảng mới.

Sau thao tác, mảng cũ chỉ trở thành đối tượng có thể được bộ gom rác thu hồi khi không còn được giữ lại; bộ nhớ tiến trình không nhất thiết giảm ngay. Cần phân biệt:

- **Bộ nhớ đang được giữ**: cấu trúc vẫn còn sống sau khi thao tác xong.
- **Lượng cấp phát trong một khoảng thời gian**: gồm cả các mảng cũ đã bị thay thế.
- **Mức đỉnh**: lượng bộ nhớ cần đồng thời trong giai đoạn chuyển đổi.

Đặt trước sức chứa phù hợp có thể giảm số lần thay mảng và lượng cấp phát tạm, nhưng đặt quá cao làm tăng phần giữ lại không dùng.

## 4. `LinkedList`: không có mảng dự phòng nhưng có nút cho từng phần tử

Trong OpenJDK 21, mỗi phần tử `LinkedList` đi qua một đối tượng nút riêng. Một nút giữ tham chiếu dữ liệu, nút kế tiếp và nút trước đó. Ngoài ba tham chiếu còn có phần đầu đối tượng (object header) và khoảng đệm do căn chỉnh (alignment). [Mã nguồn `LinkedList`](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/LinkedList.java).

```text
LinkedList
  first -------------------------------------------+
  last ---------------------------------------+    |
                                              |    v
null <--> [prev | item A | next] <--> [prev | item B | next] <--> null
           đối tượng nút 1             đối tượng nút 2
                     |                           |
                     v                           v
                đối tượng A                 đối tượng B
```

Dù `item` là `null`, nút chứa phần tử đó vẫn tồn tại. Nếu cùng một đối tượng được thêm `n` lần, danh sách vẫn cần `n` nút; chỉ đối tượng dữ liệu được dùng chung.

“Không có ô dự phòng” không kéo theo “ít bộ nhớ hơn”. Danh sách mảng thường trả chi phí vài byte tham chiếu cho một ô; danh sách liên kết trả chi phí một đối tượng nút hoàn chỉnh cho mỗi phần tử. Nhiều đối tượng nhỏ còn làm tăng công việc cấp phát và theo dõi của bộ gom rác.

Các ô mảng nằm liên tiếp về mặt bố trí mảng, còn đối tượng dữ liệu không nhất thiết nằm cạnh nhau. Với danh sách liên kết, duyệt cần lần theo tham chiếu giữa các nút; tính cục bộ bộ nhớ thường kém thuận lợi hơn. Đây là yếu tố cần đo theo tải thực tế, không phải bảo đảm thời gian chạy trên mọi máy.

Cũng không được chọn `LinkedList` chỉ vì nghe “chèn/xóa O(1)”: phải có sẵn vị trí nút thông qua thao tác phù hợp, chẳng hạn iterator đã đứng đúng chỗ. Truy cập bằng chỉ số vẫn phải tìm vị trí trước. [Tài liệu `LinkedList`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedList.html).

## 5. `HashMap`: trả cả bảng bucket lẫn nút ánh xạ

Một ánh xạ khóa–giá trị khác một phần tử danh sách. Khi báo bộ nhớ mỗi phần tử cho map, nên ghi rõ đơn vị là **mỗi ánh xạ**.

Ở OpenJDK 21, cấu trúc điển hình gồm đối tượng map, một mảng tham chiếu bucket và các nút giữ mã băm, khóa, giá trị, liên kết. Bucket trống vẫn chiếm một ô mảng. Một bucket có thể chứa nhiều nút; vì vậy số bucket trống không thể suy bằng `số bucket - số ánh xạ` như ô dự phòng của `ArrayList`. [Mã nguồn `HashMap`](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/HashMap.java).

Gọi `b` là số bucket, `n` là số ánh xạ, `f` là hệ số tải (load factor). `n / b` mô tả tải trung bình, không phải tỷ lệ bucket có dữ liệu. Với giả định thông thường và chưa chạm giới hạn kích thước, vượt ngưỡng theo `b × f` dẫn đến mở rộng bảng. Giá trị mặc định của `f` là `0.75`.

Ví dụ mô hình: `b = 1.024`, `f = 0.75` cho ngưỡng 768 ánh xạ. Đặt `new HashMap<>(1_000)` không có nghĩa chắc chắn chứa 1.000 ánh xạ mà không mở rộng; tham số constructor là yêu cầu sức chứa, không phải số ánh xạ dự kiến. API Java 19+ có `HashMap.newHashMap(expectedMappings)` dành cho số ánh xạ dự kiến; ví dụ chạy Java 17 phải dùng constructor phù hợp.

Chọn bảng rất lớn giảm áp lực mở rộng nhưng giữ thêm ô bucket, và duyệt map còn chịu ảnh hưởng của cả số bucket lẫn số ánh xạ. Không tùy tiện giảm hệ số tải chỉ để “nhanh hơn”. [Tài liệu `HashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).

Một mô hình nút thông thường cũng không bao quát mọi trường hợp: bucket có thể dùng nút cây với nhiều trường hơn; cấu trúc duy trì thứ tự có thể cần liên kết phụ. Muốn biết chi phí thực tế phải nhận diện đúng lớp triển khai và dạng nút đang có.

## 6. Xây mô hình bộ nhớ mỗi phần tử

### 6.1. Công thức trước, số byte sau

Đặt:

- `S_list`, `S_linked`, `S_map`: kích thước riêng của đối tượng collection tương ứng.
- `A(c)`: kích thước toàn bộ mảng gồm `c` tham chiếu, đã tính đầu mảng và căn chỉnh.
- `N_linked`: kích thước một nút danh sách liên kết.
- `N_map`: kích thước một nút map thông thường.
- `D`: tổng kích thước các đối tượng dữ liệu khác nhau mà phép tính quyết định đưa vào.

Với cấu trúc đã được cấp phát và bỏ qua các đối tượng phụ khác, mô hình đơn giản là:

```text
ArrayList:   M_structure ≈ S_list   + A(c)
LinkedList:  M_structure ≈ S_linked + n × N_linked
HashMap:     M_structure ≈ S_map    + A(b) + n × N_map

M_graph ≈ M_structure + D
bytes_per_element = M_structure / n       (n > 0)
```

Đây là mô hình cho các cấu trúc thông thường, không phải công thức chính xác cho mọi trạng thái rỗng, view được tạo thêm, nút cây hoặc collection tùy biến. Phải định nghĩa `D` trước khi cộng để tránh tính hai lần đối tượng dùng chung.

Chi phí trung bình chia tổng cho `n` khác chi phí tăng thêm của một thao tác `add`. Một lần thêm có thể không tạo mảng; lần kế tiếp có thể kích hoạt cấp phát một mảng lớn. Khi `n = 0`, không báo “byte mỗi phần tử” bằng phép chia này; hãy báo tổng chi phí của collection rỗng.

### 6.2. Ví dụ có giả định công khai

Xét một **mô hình minh họa**, không phải số đo trên máy người đọc:

- Tham chiếu 4 byte; đầu đối tượng 12 byte; đầu mảng tham chiếu 16 byte.
- Kích thước đối tượng/mảng được làm tròn lên bội số 8 byte.
- Nút `LinkedList` gồm đầu đối tượng và ba tham chiếu, nên trong mô hình là 24 byte.
- `n = 100.000`, sức chứa `ArrayList` được giả sử là `c = 150.000`.
- Chưa tính đối tượng dữ liệu và phần cố định của hai collection.

| Phần được tính | Phép tính theo mô hình | Kết quả |
| --- | --- | --- |
| Mảng tham chiếu của `ArrayList` | Làm tròn `16 + 150.000 × 4` | 600.016 byte |
| Trong đó, các ô dự phòng | `50.000 × 4` | 200.000 byte |
| Các nút của `LinkedList` | `100.000 × 24` | 2.400.000 byte |
| Mảng chia cho số phần tử đang dùng | `600.016 / 100.000` | Khoảng 6 byte/phần tử |
| Các nút chia cho số phần tử | `2.400.000 / 100.000` | 24 byte/phần tử |

Dù mảng có phần dự phòng khá lớn, chi phí cấu trúc trong mô hình vẫn thấp hơn phần nút liên kết. Không chuyển kết quả này thành kết luận “mọi `ArrayList` tốn đúng 6 byte/phần tử”: đổi sức chứa, số phần tử, độ rộng tham chiếu hoặc căn chỉnh sẽ đổi kết quả.

Căn chỉnh cũng khiến số byte không luôn tăng đều từng tham chiếu. Một mảng thêm một ô có thể nằm trong khoảng đệm đang có; thêm ô khác lại vượt sang bội số căn chỉnh tiếp theo. JOL minh họa cách xem đầu đối tượng, trường và căn chỉnh trong [ví dụ cơ bản chính thức](https://raw.githubusercontent.com/openjdk/jol/master/jol-samples/src/main/java/org/openjdk/jol/samples/JOLSample_01_Basic.java).

### 6.3. Chi phí dữ liệu và tự đóng hộp

`ArrayList<Integer>` giữ các tham chiếu tới `Integer`; `int[]` giữ trực tiếp các giá trị `int`. Vì vậy hai cấu trúc có cùng số lượng số nguyên chưa có cùng mô hình bộ nhớ.

Khi tự đóng hộp (autoboxing), không được mặc định mỗi vị trí luôn tạo một `Integer` mới. `Integer.valueOf` có bộ đệm cho một miền giá trị; tham chiếu còn có thể được chia sẻ chủ động. Trái lại, dữ liệu lớn có thể bao gồm nhiều đối tượng khác nhau. [Tài liệu `Integer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#valueOf(int)).

Nếu dữ liệu mỗi phần tử giữ nhiều chuỗi, mảng hoặc đồ thị con lớn, `D` có thể chiếm phần chủ yếu. Khi đó tối ưu vài ô tham chiếu chưa chắc giải quyết được vấn đề bộ nhớ. Hãy đo cả cấu trúc và dữ liệu để biết phần nào đáng tối ưu.

## 7. Thí nghiệm Java 17+: sức chứa không phải số phần tử

Lưu chương trình đầy đủ sau thành `CapacityDemo.java`:

```java
import java.util.ArrayList;

public class CapacityDemo {
    public static void main(String[] args) {
        ArrayList<StringBuilder> values = new ArrayList<>(8);
        System.out.println("initial size=" + values.size());

        StringBuilder shared = new StringBuilder("A");
        values.add(shared);
        values.add(shared);
        values.add(shared);

        values.ensureCapacity(100);
        System.out.println("after reserve size=" + values.size());
        System.out.println("same object=" + (values.get(0) == values.get(1)));

        values.remove(2);
        shared.append("B");
        System.out.println("after remove size=" + values.size());
        System.out.println("values=" + values);

        values.clear();
        System.out.println("after clear size=" + values.size());

        values.trimToSize();
        System.out.println("after trim size=" + values.size());
        System.out.println("outside reference=" + shared);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CapacityDemo.java
java CapacityDemo
```

Kết quả stdout:

```text
initial size=0
after reserve size=3
same object=true
after remove size=2
values=[AB, AB]
after clear size=0
after trim size=0
outside reference=AB
```

Giải thích theo đúng điều đã quan sát:

- Constructor có sức chứa 8 vẫn tạo danh sách với `size() == 0`.
- `ensureCapacity(100)` không thêm phần tử; danh sách vẫn có ba vị trí.
- Ba lần `add(shared)` dùng cùng đối tượng. Sau khi xóa một vị trí và sửa `shared`, hai vị trí còn lại cùng hiển thị `AB`.
- `clear()` và `trimToSize()` đều cho `size() == 0`; chỉ nhìn kết quả `size()` không thể phân biệt mảng đang lớn hay đã thu nhỏ.
- Biến `shared` bên ngoài vẫn giữ đối tượng sau khi xóa khỏi danh sách. Xóa tham chiếu trong collection không đồng nghĩa đối tượng dữ liệu phải được thu hồi.

`ArrayList` không có phương thức công khai `capacity()`. Chương trình trên kiểm chứng ngữ nghĩa số phần tử và tham chiếu; nó không in số byte, không đo dung lượng thật của mảng và không chứng minh thời điểm bộ gom rác thu hồi đối tượng.

## 8. Đo đúng: đối tượng riêng, đồ thị có thể đi tới và bộ nhớ giữ lại

Ba khái niệm cần phân biệt khi xem công cụ:

| Khái niệm | Câu hỏi cần trả lời | Điểm dễ nhầm |
| --- | --- | --- |
| Kích thước riêng (shallow size) | Bản thân một đối tượng chiếm bao nhiêu byte? | Đo riêng `ArrayList` chưa tính mảng phía sau |
| Kích thước đồ thị có thể đi tới | Từ collection có thể lần theo tham chiếu tới các đối tượng nào? | Dữ liệu dùng chung cũng có thể được tính vào đồ thị |
| Bộ nhớ giữ lại (retained size) | Những đối tượng nào sẽ có thể được thu hồi nếu bỏ đối tượng gốc này, xét toàn bộ các gốc giữ sống khác? | Không thể suy chỉ từ tổng đồ thị của một collection |

JOL hỗ trợ xem bố trí đối tượng và tổng dung lượng của đồ thị. Để so sánh cấu trúc, có thể cho hai collection cùng giữ một đối tượng dùng chung nhiều lần. Cách này hạn chế việc số đối tượng dữ liệu khác nhau che khuất chi phí mảng và nút. Nó không đại diện cho mọi tải dữ liệu thực tế. [Dự án JOL của OpenJDK](https://github.com/openjdk/jol).

### 8.1. Chương trình đo với JOL

Ví dụ đầy đủ dưới đây cần thư viện `org.openjdk.jol:jol-core` có trên classpath. Các lệnh giả sử tệp thư viện đã được chuẩn bị dưới tên `jol-core.jar`. Lưu mã thành `MemoryProbe.java`:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import org.openjdk.jol.info.ClassLayout;
import org.openjdk.jol.info.GraphLayout;
import org.openjdk.jol.vm.VM;

public class MemoryProbe {
    public static void main(String[] args) {
        int count = 10_000;
        Object shared = new Object();
        ArrayList<Object> array = new ArrayList<>(20_000);
        LinkedList<Object> linked = new LinkedList<>();

        for (int i = 0; i < count; i++) {
            array.add(shared);
            linked.add(shared);
        }

        System.out.println(VM.current().details());
        System.out.println("ArrayList object only:");
        System.out.println(ClassLayout.parseInstance(array).toPrintable());
        System.out.println("ArrayList reachable graph:");
        System.out.println(GraphLayout.parseInstance((Object) array).toFootprint());
        System.out.println("LinkedList reachable graph:");
        System.out.println(GraphLayout.parseInstance((Object) linked).toFootprint());

        array.trimToSize();
        System.out.println("ArrayList reachable graph after trim:");
        System.out.println(GraphLayout.parseInstance((Object) array).toFootprint());
    }
}
```

Trên Windows:

```shell
javac --release 17 -cp jol-core.jar MemoryProbe.java
java -cp ".;jol-core.jar" MemoryProbe
```

Trên Linux/macOS, dùng dấu `:` giữa các phần của classpath:

```shell
java -cp ".:jol-core.jar" MemoryProbe
```

Không có một bảng stdout byte cố định áp dụng cho mọi môi trường. Đọc kết quả theo các kiểm tra sau:

1. Phần `ClassLayout` chỉ nói về đối tượng `ArrayList` gốc; đừng lấy nó làm toàn bộ chi phí danh sách.
2. Trong footprint của danh sách mảng, tìm mảng tham chiếu và kích thước của nó; so sánh trước/sau `trimToSize`.
3. Trong footprint của danh sách liên kết, tìm số đối tượng nút; với 10.000 phần tử, cấu trúc OpenJDK thông thường có 10.000 nút.
4. Đối tượng `shared` chỉ được đếm một lần trong từng đồ thị dù có nhiều đường tham chiếu tới nó. Cộng hai báo cáo riêng sẽ đếm nó hai lần nếu đang muốn tính tổng hợp nhất của cả hai đồ thị.
5. Nếu JOL cảnh báo không xác định được thông tin JVM hoặc chỉ ước tính một số thuộc tính, đọc cảnh báo và kiểm chứng cấu hình trước khi dùng kết quả như số đo chính xác.

Vì cả `array` và `linked` giữ `shared`, đối tượng đó không được giữ sống độc quyền bởi một danh sách. Tổng đồ thị mà JOL đi tới không tự động bằng retained size. Phân tích retained size cần công cụ phân tích heap có ngữ cảnh các tham chiếu giữ sống và quan hệ thống trị (dominator).

### 8.2. Ghi điều kiện đo để người khác tái lập

Ghi phiên bản JDK/JVM, kiến trúc, tùy chọn tham chiếu nén, căn chỉnh, công cụ và phiên bản công cụ; đồng thời ghi `n`, sức chứa dự kiến, tỷ lệ xóa, dữ liệu dùng chung hay riêng, có tính dữ liệu hay chỉ cấu trúc. Chạy phép so sánh trong cùng điều kiện.

Không lấy `Runtime.totalMemory() - Runtime.freeMemory()` trước/sau một lần `add` rồi kết luận số byte của một phần tử. Heap còn có hoạt động của JVM, thư viện, thời điểm gom rác và vùng nhớ được giữ để tái sử dụng. Gọi `System.gc()` cũng không biến phép trừ đó thành phép đo kích thước đối tượng chính xác.

Nếu vấn đề là nhiều cấp phát trong một luồng xử lý, cần theo dõi lượng cấp phát và hoạt động GC theo tải đại diện. Nếu vấn đề là heap còn sống quá lớn sau xử lý, cần xem cấu trúc đang giữ lại và các đường tham chiếu. Hai vấn đề có thể cần cách tối ưu khác nhau.

## 9. Chọn cấu trúc và dự phòng theo tình huống

| Tình huống | Hướng kiểm tra | Đánh đổi cần nhớ |
| --- | --- | --- |
| Biết gần đúng số phần tử và chủ yếu thêm cuối/duyệt | Đặt sức chứa `ArrayList` theo quy mô hợp lý | Giảm thay mảng nhưng giữ ô dự phòng nếu ước lượng quá cao |
| Danh sách từng rất lớn, sau đó nhỏ và sống lâu | Đo phần mảng giữ lại, cân nhắc `trimToSize` sau giai đoạn thu nhỏ | Thu nhỏ có thể sao chép; sắp tăng lại thì lợi ích có thể mất |
| Đang dùng `LinkedList` vì muốn tránh ô thừa | So chi phí nút, số đối tượng và kiểu thao tác thật | Tránh ô thừa nhưng trả chi phí nút cho từng vị trí |
| Hàng đợi/ngăn xếp không cần chứa `null` | Đo thêm phương án `ArrayDeque` dựa trên mảng | Không cần nút cho từng phần tử nhưng vẫn có sức chứa và mở rộng |
| Map có nhiều ánh xạ | Tính cả bảng bucket và nút, chọn sức chứa theo số ánh xạ dự kiến | Bucket và ngưỡng tải không cùng nghĩa với phần tử danh sách |
| Khối lượng lớn dữ liệu số nguyên thủy | So sánh mô hình mảng nguyên thủy và collection kiểu bọc | Phải giữ đúng yêu cầu API, thao tác và cách biểu diễn dữ liệu |

Phương án `ArrayDeque` ở đây dựa trên việc triển khai dùng mảng vòng; nó không chấp nhận phần tử `null`. Cần giữ đúng yêu cầu chức năng trước khi so bộ nhớ. [Mã nguồn `ArrayDeque`](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/ArrayDeque.java).

## 10. Tự kiểm tra

1. Một `ArrayList` có 1.000 phần tử và sức chứa 1.600 có bao nhiêu ô dự phòng? Có thể kết luận có 1.600 đối tượng dữ liệu không?
2. Vì sao danh sách liên kết không cần dự phòng mà vẫn có thể tốn nhiều bộ nhớ hơn danh sách mảng?
3. Hai collection cùng giữ một đối tượng lớn: có được cộng hai tổng đồ thị riêng để suy ra lượng bộ nhớ khác nhau của cả hai không?
4. Sau `clear()`, số phần tử bằng 0. Cần kiểm tra gì trước khi kết luận bộ nhớ đã được trả lại?
5. Một báo cáo nói “8 byte/phần tử” nhưng không nêu JVM, sức chứa và có tính dữ liệu hay không. Vì sao chưa đủ để dùng ra quyết định?

Gợi ý đối chiếu:

1. Có 600 ô dự phòng; số đối tượng dữ liệu khác nhau phụ thuộc tham chiếu trùng, `null` và dữ liệu thực tế.
2. Mỗi nút cần đầu đối tượng, liên kết và căn chỉnh; các phần đó có thể lớn hơn phần ô dự phòng của mảng.
3. Không; cần hợp nhất theo danh tính đối tượng để tránh tính trùng, và phân biệt tổng đồ thị với bộ nhớ giữ lại độc quyền.
4. Kiểm tra mảng/bảng còn được collection giữ hay không, dữ liệu còn được nơi khác tham chiếu không, và đang nói tới heap sống, heap đã cấp cho JVM hay bộ nhớ tiến trình.
5. Con số chưa xác định mẫu số, phạm vi đo và giả định bố trí; không thể so công bằng với một cấu trúc khác.
