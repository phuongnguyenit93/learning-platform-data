# So sánh mảng với collection: kích thước, kiểu và thao tác

Mảng và collection đều có thể quản lý nhiều giá trị, nhưng chúng tổ chức dữ liệu và cung cấp thao tác theo những hợp đồng khác nhau. Việc chọn đúng mô hình giúp tránh những lỗi như coi dung lượng dự phòng là số phần tử, xóa nhầm theo chỉ số hoặc tưởng một danh sách được tạo từ mảng có thể tự tăng kích thước.

Ba câu hỏi dẫn đường cho bài này:

1. **Kích thước:** số vị trí lưu trữ có thay đổi không, và số phần tử đang được quản lý là bao nhiêu?
2. **Kiểu:** phần tử là giá trị nguyên thủy hay đối tượng; kiểm tra kiểu diễn ra khi biên dịch hay khi chạy?
3. **Thao tác:** cần lấy theo vị trí, thêm, xóa, tìm, sắp xếp hay chuyển đổi giữa các dạng dữ liệu?

Các ví dụ hoàn chỉnh sử dụng API Java 17. Chúng được biên dịch với `--release 17` và đã chạy để kiểm tra stdout.

## 1. Hai mô hình cần hình dung

### Mảng: một số vị trí được xác định khi tạo

Khai báo `new String[3]` tạo một đối tượng mảng có ba vị trí. Các vị trí được truy cập bằng chỉ số từ `0` đến `2`. Độ dài đó được giữ suốt vòng đời của đối tượng mảng.

Các vị trí luôn tồn tại sau khi mảng được tạo, kể cả khi bạn chưa gán dữ liệu riêng cho chúng. Java khởi tạo phần tử bằng giá trị mặc định của kiểu:

| Kiểu phần tử | Ví dụ giá trị mặc định |
| --- | --- |
| `int` | `0` |
| `boolean` | `false` |
| Kiểu tham chiếu như `String` | `null` |

Nếu chỉ hai vị trí đang chứa dữ liệu có ý nghĩa nghiệp vụ, chương trình phải tự phân biệt “độ dài mảng là ba” với “đang có hai bản ghi hợp lệ”.

### Collection: một nhóm phần tử với hợp đồng thao tác

`Collection<E>` là giao diện chung của nhiều kiểu tập hợp trong `java.util`. Một collection cho biết số phần tử hiện có qua `size()`; loại tập hợp cụ thể quy định thứ tự, trùng lặp và các thao tác được hỗ trợ.

Khi cần so sánh trực tiếp với mảng có chỉ số, `List<E>` là ví dụ gần gũi. `ArrayList<E>` là một lớp triển khai danh sách có khả năng thay đổi số phần tử.

Tuy nhiên:

- `Collection` rộng hơn `List`; một `Set` không cung cấp `get(index)`.
- Một collection có thể không hỗ trợ thêm hoặc xóa.
- `Map` thuộc hệ thống Java Collections Framework nhưng không kế thừa `Collection`.

Vì vậy, câu “collection thay đổi kích thước được” cần được gắn với loại và đối tượng thực tế. Với `ArrayList` khả biến, điều đó đúng; với danh sách từ `List.of`, việc thêm hoặc xóa bị cấm.

## 2. Bảng so sánh nền tảng

| Tiêu chí | Mảng | Collection |
| --- | --- | --- |
| Ví dụ kiểu | `int[]`, `String[]` | `Collection<String>`, `List<Integer>`, `Set<String>` |
| Đại lượng đếm | Thuộc tính `length` của mảng | Phương thức `size()` của collection |
| Số vị trí/phần tử | Độ dài đối tượng mảng cố định | Số phần tử có thể thay đổi nếu đối tượng hỗ trợ |
| Kiểu nguyên thủy | Có thể chứa trực tiếp `int`, `double`, ... | Tham số kiểu dùng kiểu tham chiếu như `Integer`, `Double` |
| Truy cập theo chỉ số | `array[index]` | Có ở `List` qua `get(index)`, không có ở mọi `Collection` |
| Thay một phần tử | Gán vào vị trí hợp lệ | `List.set` nếu được hỗ trợ |
| Thêm hoặc xóa phần tử | Tự tổ chức dữ liệu hoặc tạo mảng khác | Có thao tác trong hợp đồng; khả năng thực thi phụ thuộc đối tượng |
| Quy tắc trùng lặp | Các vị trí có thể chứa cùng giá trị | Theo loại tập hợp; `List` thường cho trùng, `Set` bảo đảm duy nhất theo quy tắc của nó |
| Công cụ thao tác | Cú pháp mảng và `java.util.Arrays` | Phương thức của giao diện/lớp và các công cụ phù hợp |
| Thông tin kiểu lúc chạy | Mảng giữ kiểu phần tử thực tế | Generics chủ yếu kiểm tra lúc biên dịch, có cơ chế xóa kiểu |

Bảng không có nghĩa một bên luôn tốt hơn. Ví dụ, việc cần thao tác thêm/xóa thường xuyên khác với việc cần lưu một khối số nguyên có số vị trí đã biết.

## 3. Kích thước, số phần tử và capacity

### Độ dài của mảng không tự tăng

Đoạn minh họa trong một phương thức:

```java
int[] scores = new int[3];
```

`scores.length` là `3`. Gán `scores[0] = 10` chỉ thay dữ liệu của một vị trí, không thay độ dài. Truy cập `scores[3]` vượt giới hạn và gây `ArrayIndexOutOfBoundsException`.

Có thể tạo một mảng lớn hơn bằng `Arrays.copyOf` rồi gán lại biến:

```java
int[] scores = {10, 20, 30};
scores = Arrays.copyOf(scores, 5);
```

Đoạn này cần `import java.util.Arrays;`. Nó tạo **đối tượng mảng khác** rồi cho biến `scores` tham chiếu tới mảng mới. Đối tượng mảng ban đầu không bị kéo dài. Hai vị trí mới của mảng số nguyên được điền giá trị mặc định `0`.

Nếu một biến khác vẫn tham chiếu tới mảng cũ, biến đó vẫn thấy mảng ba phần tử.

### Size và capacity của ArrayList khác nhau

Với:

```java
List<String> values = new ArrayList<>(3);
```

- `3` là dung lượng dự phòng ban đầu được yêu cầu cho cấu trúc lưu trữ.
- `values.size()` vẫn là `0`.
- Chưa có phần tử ở chỉ số `0`.
- `values.set(0, "A")` sẽ không tạo phần tử mới; chỉ số đó chưa hợp lệ.
- `values.add("A")` mới thêm phần tử đầu tiên.

`ArrayList` quản lý một vùng lưu trữ nội bộ. Khi cần, nó có thể tăng dung lượng và chuyển dữ liệu. Người sử dụng không phải tự theo dõi mảng bên trong.

`Collection` không cung cấp khái niệm capacity chung cho mọi kiểu tập hợp. Cũng không nên dựa vào một hệ số tăng dung lượng cụ thể để viết logic nghiệp vụ.

### Chương trình hoàn chỉnh

Tạo tệp **`ArrayAndListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArrayAndListDemo {
    public static void main(String[] args) {
        String[] unusedSlots = new String[3];
        String[] array = {"A", "B", "C"};
        List<String> list = new ArrayList<>(3);

        System.out.println("default array = " + Arrays.toString(unusedSlots));
        System.out.println("array.length = " + array.length);
        System.out.println("list.size before add = " + list.size());

        list.add("A");
        list.add("B");
        list.add("C");
        list.add("D");
        System.out.println("list.size after add = " + list.size());

        array[1] = "X";
        list.set(1, "X");
        list.remove("C");

        System.out.println("array = " + Arrays.toString(array));
        System.out.println("list = " + list);
        System.out.println("list.size after remove = " + list.size());
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ArrayAndListDemo.java
java -Dfile.encoding=UTF-8 ArrayAndListDemo
```

Stdout:

```text
default array = [null, null, null]
array.length = 3
list.size before add = 0
list.size after add = 4
array = [A, X, C]
list = [A, X, D]
list.size after remove = 3
```

Những điểm quan sát được:

1. Mảng mới có ba phần tử tham chiếu, đều là `null`.
2. Danh sách dự phòng chỗ cho ba phần tử vẫn có kích thước ban đầu bằng không.
3. Sau bốn lần `add`, danh sách chứa bốn phần tử.
4. Gán `array[1]` và gọi `list.set(1, ...)` đều thay phần tử đã tồn tại.
5. `list.remove("C")` làm giảm số phần tử từ bốn xuống ba; mảng vẫn có độ dài ba.

Số `3` ở cuối hai mô hình tình cờ bằng nhau, nhưng quá trình thay đổi dữ liệu và hợp đồng thao tác khác nhau.

## 4. Kiểu phần tử và kiểm tra kiểu

### Mảng chứa trực tiếp được giá trị nguyên thủy

```java
int[] quantities = {2, 4, 6};
String[] labels = {"small", "medium"};
```

Hai đoạn này minh họa mảng nguyên thủy và mảng tham chiếu.

Với generics, khai báo `List<int>` không hợp lệ. Ta dùng kiểu bao:

```java
List<Integer> quantities = new ArrayList<>();
quantities.add(2);
```

Các dòng về `List` cần những import tương ứng trong `java.util`. Giá trị `int` có thể được tự đóng hộp thành `Integer` khi thêm.

Hệ quả:

- `int[]` chứa các giá trị số nguyên trực tiếp.
- `List<Integer>` quản lý các tham chiếu đến đối tượng `Integer`.
- Một danh sách cho phép `null` có thể chứa phần tử không thể mở hộp thành `int`.
- Mô hình bộ nhớ và chi phí không giống nhau.

Không nên đổi mảng nguyên thủy sang collection chỉ để thống nhất cú pháp mà bỏ qua những khác biệt này.

### Mảng tham chiếu có tính hiệp biến

Trong Java, có thể gán một `String[]` cho biến `Object[]`:

```java
Object[] values = new String[1];
```

Biến được khai báo là `Object[]`, nhưng đối tượng thực tế vẫn là `String[]`. Khi gán một `Integer` vào mảng đó, Java kiểm tra kiểu phần tử lúc chạy và ném `ArrayStoreException`.

Sự cho phép gán giữa các kiểu mảng theo quan hệ kiểu con được gọi là **hiệp biến (covariance)**. Nó đem lại tính linh hoạt nhưng cần kiểm tra khi lưu phần tử.

### Generics có quy tắc gán khác

Đoạn dưới **cố tình không biên dịch**:

```java
List<Object> values = new ArrayList<String>();
```

`List<String>` không phải kiểu con của `List<Object>`. Nếu phép gán được cho phép, mã dùng biến `List<Object>` có thể thêm một đối tượng không phải chuỗi vào danh sách chuỗi.

Các kiểu tham số hóa như `List<T>` có tính **bất biến (invariance)** đối với tham số kiểu. Khi cần nhận nhiều kiểu phần tử trong một API, Java có wildcard như `? extends ...` hoặc `? super ...`, với các giới hạn đọc/ghi riêng. Đó là một lựa chọn thiết kế kiểu, không phải lý do dùng kiểu thô để bỏ kiểm tra.

### Thông tin kiểu lúc chạy khác nhau

- Một mảng `String[]` giữ kiểu thành phần thực tế để kiểm tra khi lưu.
- Một `List<String>` dùng generics để kiểm tra phần lớn việc sử dụng kiểu ở bước biên dịch.
- Khi dùng kiểu thô hoặc ép kiểu không an toàn, có thể phá vỡ bảo đảm của generics và gặp `ClassCastException` khi lấy dữ liệu.

Xóa kiểu không có nghĩa “generics không an toàn”. Nó giải thích vì sao cần giữ kiểm tra kiểu lúc biên dịch và tránh thao tác không an toàn.

## 5. Đóng hộp và bẫy mảng nguyên thủy

`Arrays.asList` nhận các đối số theo một kiểu tham chiếu. Một `int[]` tự nó là một đối tượng, nên lời gọi `Arrays.asList(intArray)` tạo danh sách có **một phần tử là cả mảng**, chứ không tạo danh sách các số đã đóng hộp.

Chương trình sau còn minh họa kiểm tra kiểu của mảng và lỗi mở hộp `null`.

Tạo tệp **`ArrayTypeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArrayTypeDemo {
    public static void main(String[] args) {
        Object[] values = new String[1];
        try {
            values[0] = Integer.valueOf(7);
        } catch (ArrayStoreException exception) {
            System.out.println("array store: " + exception.getClass().getSimpleName());
        }

        int[] numbers = {2, 4, 6};
        List<int[]> oneArray = Arrays.asList(numbers);
        System.out.println("asList(int[]).size = " + oneArray.size());
        System.out.println("same array = " + (oneArray.get(0) == numbers));

        List<Integer> boxed = new ArrayList<>();
        for (int number : numbers) {
            boxed.add(number);
        }
        System.out.println("boxed = " + boxed);
        System.out.println("boxed.size = " + boxed.size());

        List<Integer> withNull = Arrays.asList(1, null, 3);
        try {
            int number = withNull.get(1);
            System.out.println(number);
        } catch (NullPointerException exception) {
            System.out.println("unboxing: " + exception.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ArrayTypeDemo.java
java -Dfile.encoding=UTF-8 ArrayTypeDemo
```

Stdout:

```text
array store: ArrayStoreException
asList(int[]).size = 1
same array = true
boxed = [2, 4, 6]
boxed.size = 3
unboxing: NullPointerException
```

Giải thích:

1. Đối tượng `String[]` từ chối lưu một `Integer`, dù biến có kiểu `Object[]`.
2. `oneArray` có kiểu `List<int[]>`, kích thước bằng `1`.
3. Phần tử duy nhất của danh sách chính là tham chiếu tới `numbers`.
4. Vòng lặp chủ động thêm từng giá trị `int` vào `List<Integer>`, tạo ba phần tử qua đóng hộp.
5. Lấy `null` từ `List<Integer>` rồi gán cho biến `int` cần mở hộp, nên gây `NullPointerException`.

Chọn cách chuyển đổi theo kết quả mong muốn. “Danh sách các mảng” và “danh sách các số” là hai mô hình khác nhau.

## 6. So sánh các thao tác thường dùng

Với collection, cột cuối cần được đọc theo đúng giao diện: thao tác chỉ số thuộc `List`, không phải mọi `Collection`.

| Mục đích | Mảng | Collection hoặc List phù hợp |
| --- | --- | --- |
| Đếm | `array.length` | `group.size()` |
| Kiểm tra rỗng | `array.length == 0` | `group.isEmpty()` |
| Lấy theo vị trí | `array[index]` | `list.get(index)` |
| Thay phần tử đã có | `array[index] = value` | `list.set(index, value)` nếu hỗ trợ |
| Thêm phần tử | Tự quản lý chỗ trống hoặc tạo mảng mới | `add`, hoặc `List.add(index, value)` nếu hỗ trợ |
| Xóa theo giá trị | Tự tìm và tổ chức lại dữ liệu | `remove(value)` theo hợp đồng |
| Tìm sự tồn tại | Viết vòng lặp hoặc dùng công cụ phù hợp | `contains(value)` |
| Duyệt phần tử | for, for-each | for-each; iterator và các cơ chế của loại cụ thể |
| Sắp xếp tại chỗ | `Arrays.sort(array)` | `list.sort(comparator)` khi được hỗ trợ |
| Hiển thị nội dung | `Arrays.toString(array)` cho mảng một chiều | Các lớp tập hợp thông dụng có biểu diễn qua `toString()` |
| So sánh nội dung | `Arrays.equals(a, b)` cho mảng một chiều phù hợp | Theo hợp đồng `equals` của loại tập hợp |

### Thay phần tử khác với thêm phần tử

Với mảng, gán vào một vị trí không tạo thêm vị trí mới. Với danh sách, `set` thay phần tử còn `add` thêm phần tử. Hai thao tác không thể thay thế nhau.

Trong một danh sách có thứ tự, thêm hoặc xóa ở giữa còn có thể làm thay đổi chỉ số của các phần tử phía sau. Khi lưu một chỉ số để sử dụng về sau, cần tính đến khả năng cấu trúc đã thay đổi.

### Xóa phần tử số nguyên có hai cách hiểu

`List<Integer>` có thể gặp nhầm lẫn giữa:

- `remove(int index)`: xóa theo chỉ số.
- `remove(Object value)`: xóa theo giá trị.

Ví dụ minh họa đặt trong một phương thức:

```java
List<Integer> byIndex = new ArrayList<>(List.of(1, 2, 1));
byIndex.remove(1); // Xóa phần tử ở chỉ số 1: giá trị 2.

List<Integer> byValue = new ArrayList<>(List.of(1, 2, 1));
byValue.remove(Integer.valueOf(1)); // Xóa một lần xuất hiện của giá trị 1.
```

Sau đó `byIndex` chứa `[1, 1]`, còn `byValue` chứa `[2, 1]`. Đây là khác biệt do nạp chồng phương thức và kiểu đối số.

### Quy tắc bằng nhau khác nhau

Gọi `a.equals(b)` trên hai mảng không so từng phần tử như `Arrays.equals(a, b)`; mảng sử dụng quy tắc đồng nhất đối tượng cho `equals`.

Đối với danh sách, hợp đồng `List.equals` xét phần tử tương ứng và thứ tự. Đối với tập hợp, hợp đồng `Set.equals` xét thành viên theo quy tắc tập hợp.

Không nên suy ra một quy tắc `equals` theo nội dung duy nhất cho mọi kiểu `Collection`. Cần xem hợp đồng của loại tập hợp đang dùng. Với mảng lồng nhau, khi cần so sánh sâu, phải chọn công cụ phù hợp như `Arrays.deepEquals`.

## 7. Từ mảng sang danh sách: góc nhìn hay bản sao?

Đây là nơi các khái niệm “cố định kích thước”, “không sửa đổi được” và “độc lập dữ liệu” thường bị nhầm.

Giả sử `source` là một `String[]` không chứa `null`:

| Cách tạo | Thêm/xóa phần tử | Thay phần tử bằng set | Quan hệ với mảng nguồn |
| --- | --- | --- | --- |
| `Arrays.asList(source)` | Không | Có | Góc nhìn được chống lưng bởi mảng nguồn |
| `new ArrayList<>(Arrays.asList(source))` | Có | Có | Cấu trúc danh sách được sao chép |
| `List.copyOf(Arrays.asList(source))` | Không | Không | Snapshot không phản ánh thay đổi cấu trúc/phần tử của nguồn sau khi tạo |

Ở đây, “snapshot” có nghĩa danh sách kết quả giữ tập phần tử ở thời điểm tạo theo hợp đồng. Không nên suy luận rằng lời gọi luôn cấp phát một đối tượng mới trong mọi trường hợp đầu vào.

### Arrays.asList là danh sách cố định kích thước

Với một mảng tham chiếu, danh sách từ `Arrays.asList` có cùng số phần tử với mảng:

- `set` cập nhật một vị trí và có thể được quan sát từ mảng.
- Thay một phần tử trong mảng cũng được quan sát từ danh sách.
- `add` hoặc `remove` làm thay đổi số phần tử nên không được hỗ trợ.

Nó là **góc nhìn (view)** cùng dữ liệu nền, không phải một `java.util.ArrayList` có khả năng tự tăng kích thước.

### Danh sách không sửa đổi được có chính sách khác

`List.of(...)` và `List.copyOf(...)` trả về danh sách không cho phép sửa đổi. Những lời gọi thay đổi như `add`, `remove`, `set` không được hỗ trợ; các cách tạo này cũng không chấp nhận phần tử `null`.

Tính không sửa đổi được của danh sách chỉ nói về cấu trúc và các phần tử được lưu ở các vị trí của nó. Nếu phần tử là một đối tượng khả biến, dữ liệu bên trong đối tượng đó vẫn có thể thay đổi.

Các cách sao chép thông dụng trong phần này đều là **sao chép nông (shallow copy)** đối với đối tượng phần tử: chúng sao chép các tham chiếu, không tự nhân bản toàn bộ đồ thị đối tượng.

## 8. Chương trình hoàn chỉnh: phân biệt view, copy và snapshot

Tạo tệp **`ArrayViewCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArrayViewCopyDemo {
    public static void main(String[] args) {
        String[] source = {"red", "blue"};
        List<String> view = Arrays.asList(source);
        List<String> copy = new ArrayList<>(view);

        view.set(0, "green");
        copy.add("black");

        List<String> snapshot = List.copyOf(view);
        source[1] = "white";

        System.out.println("source = " + Arrays.toString(source));
        System.out.println("view = " + view);
        System.out.println("copy = " + copy);
        System.out.println("snapshot = " + snapshot);

        try {
            view.add("yellow");
        } catch (UnsupportedOperationException exception) {
            System.out.println("view.add: " + exception.getClass().getSimpleName());
        }

        try {
            snapshot.set(0, "yellow");
        } catch (UnsupportedOperationException exception) {
            System.out.println("snapshot.set: " + exception.getClass().getSimpleName());
        }

        String[] exported = view.toArray(String[]::new);
        exported[0] = "detached";

        System.out.println("exported = " + Arrays.toString(exported));
        System.out.println("source after export = " + Arrays.toString(source));
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ArrayViewCopyDemo.java
java -Dfile.encoding=UTF-8 ArrayViewCopyDemo
```

Stdout:

```text
source = [green, white]
view = [green, white]
copy = [red, blue, black]
snapshot = [green, blue]
view.add: UnsupportedOperationException
snapshot.set: UnsupportedOperationException
exported = [detached, white]
source after export = [green, white]
```

### Theo dõi từng biến

- `view.set(0, "green")` thay phần tử trong dữ liệu dùng chung với `source`.
- `copy` được tạo trước thay đổi đó, nên vẫn giữ `"red"` ở vị trí đầu. Việc `copy.add("black")` chỉ tăng danh sách bản sao.
- `snapshot` được tạo sau lần thay đầu tiên, nên giữ `[green, blue]`.
- `source[1] = "white"` tác động đến `view` nhưng không đổi tập phần tử của `copy` hoặc `snapshot`.
- `view.add` thất bại vì kích thước gắn với mảng cố định.
- `snapshot.set` thất bại vì danh sách không cho phép sửa đổi.
- Mảng `exported` do `toArray` tạo ra có cấu trúc riêng; gán lại `exported[0]` không thay phần tử của `source`.

Các phần tử đều là `String`, một kiểu bất biến. Khi thay chuỗi ở một vị trí, chương trình thay tham chiếu của vị trí đó. Nếu dùng phần tử là đối tượng khả biến, việc sửa bên trong đối tượng chung vẫn có thể được nhìn thấy từ nhiều cấu trúc.

## 9. Từ collection sang mảng

### Dùng kiểu mảng phù hợp

Với một `Collection<String>`, có thể viết:

```java
String[] result = values.toArray(String[]::new);
```

Đây là đoạn minh họa cần một biến `values` đã được khai báo và chứa các phần tử hợp lệ. Cú pháp `String[]::new` cung cấp cách tạo mảng đúng kiểu. Các phần tử được đưa vào theo thứ tự duyệt của collection, nếu collection có cam kết thứ tự.

Một cách khác là:

```java
String[] result = values.toArray(new String[0]);
```

Cả hai lựa chọn này tránh nhầm kiểu mảng kết quả. Chương trình hoàn chỉnh ở phần trước dùng cách thứ nhất.

### Không ép Object[] thành String[] theo kiểu suy đoán

`values.toArray()` không có đối số trả về `Object[]`. Không nên viết:

```java
String[] result = (String[]) values.toArray();
```

Đoạn này có thể biên dịch nhưng mảng kết quả thực tế là `Object[]`, nên phép ép sang `String[]` gây `ClassCastException`. Việc các phần tử đang là chuỗi không làm đổi kiểu thực của đối tượng mảng.

### Trở lại mảng nguyên thủy cần chuyển từng giá trị

Từ một `List<Integer>`, việc gọi `toArray` không tạo trực tiếp được `int[]`. Cần chuyển từng giá trị, ví dụ bằng vòng lặp và mở hộp hoặc công cụ chuyển đổi phù hợp.

Khi mở hộp, phải xác định cách xử lý `null`. Đừng để một giả định “mọi phần tử đều có số” chỉ được phát hiện bằng ngoại lệ lúc chương trình đang chạy.

## 10. Chi phí và cách chọn cấu trúc

Mảng và collection không thể được xếp hạng bằng một câu “cái nào nhanh hơn”.

### Những chi phí cần nhìn vào

- **Lưu số nguyên thủy:** `int[]` tránh mô hình đối tượng bao của `List<Integer>`.
- **Thay đổi số phần tử:** `ArrayList` quản lý tăng dung lượng; một số lần thêm có thể phải chuyển dữ liệu.
- **Thêm/xóa giữa danh sách:** `ArrayList` thường cần dịch chuyển các phần tử phía sau.
- **Tìm theo giá trị:** duyệt mảng hay duyệt danh sách có thể phải kiểm tra nhiều phần tử.
- **Tập hợp có cấu trúc tìm kiếm riêng:** có những lựa chọn tối ưu cho tìm hoặc tính duy nhất, với chi phí và quy tắc khác.
- **Sao chép và chuyển đổi:** thêm cấp phát, đọc dữ liệu và có thể phát sinh đóng hộp hoặc mở hộp.

Cả truy cập chỉ số của mảng và `ArrayList.get` đều có chi phí không tăng theo số phần tử trong mô hình sử dụng thông thường. Điều đó không làm mọi thao tác của chúng có cùng chi phí.

Cũng không thể suy ra rằng tất cả collection truy cập chỉ số hiệu quả như nhau hoặc đều hỗ trợ chỉ số. Hãy đọc đặc điểm của lớp cụ thể và đo đạc nếu hiệu năng là yêu cầu thực tế.

### Một quy trình lựa chọn

1. **Xác định ý nghĩa dữ liệu.** Một vectơ số có độ dài cố định khác với giỏ hàng có số dòng thay đổi.
2. **Xác định kiểu phần tử.** Có cần lưu trực tiếp giá trị nguyên thủy không?
3. **Xác định quy tắc nhóm.** Có cần trùng lặp, thứ tự, chỉ số hay tính duy nhất?
4. **Xác định thao tác chủ yếu.** Đọc, duyệt, tìm, thêm cuối, thêm giữa hoặc xóa?
5. **Xác định khả năng sửa đổi.** Dữ liệu là bản sao độc lập, góc nhìn dùng chung hay snapshot?
6. **Kiểm tra hợp đồng nơi nhận dữ liệu.** API yêu cầu mảng hay một giao diện tập hợp?
7. **Đánh giá đồng thời và chi phí.** Không mặc định mảng hoặc `ArrayList` tự bảo vệ trước các truy cập sửa đổi đồng thời.

Ví dụ định hướng:

| Tình huống | Lựa chọn nên xét |
| --- | --- |
| Lưu một khối số nguyên với số vị trí xác định | `int[]` |
| Danh sách dòng dữ liệu được thêm/xóa và có thứ tự | `List` với lớp triển khai phù hợp |
| Tập mã không được trùng | `Set` |
| Tra dữ liệu theo khóa | `Map` |
| Gọi một API nhận tham số mảng | Chuyển sang mảng đúng kiểu ở ranh giới API |

Tên gọi “danh sách” trong yêu cầu thường ngày không đủ để quyết định cấu trúc. Quy tắc và thao tác mới là dữ liệu cần dùng để chọn.

## 11. Các lỗi dễ mắc

### Nhầm capacity với size

`new ArrayList<>(100)` tạo một danh sách rỗng với yêu cầu dung lượng ban đầu; nó không tạo một trăm phần tử `null`. Hãy dùng `add` để tạo phần tử.

### Gán null để coi là đã xóa khỏi mảng

`array[index] = null` chỉ thay giá trị vị trí đó. `array.length` không giảm. Nếu dùng mảng như một vùng chứa có phần đang hoạt động, phải tự cập nhật quy tắc và số phần tử đang dùng.

### Tin mọi collection đều có get(index)

`get` là thao tác của `List`. Khi đoạn mã chỉ có `Collection<E>`, cần làm việc theo hợp đồng chung hoặc lựa chọn lại kiểu tham số theo đúng nhu cầu.

### Tin mọi danh sách từ mảng đều tự tăng được

`Arrays.asList` tạo danh sách cố định kích thước. Khi cần thêm/xóa, tạo collection khả biến phù hợp, chẳng hạn `new ArrayList<>(...)`.

### Dùng Arrays.asList để tự động đóng hộp một int[]

Lời gọi này tạo `List<int[]>` có một phần tử. Hãy kiểm tra kiểu khai báo và số phần tử thay vì chỉ nhìn tên hàm.

### Đánh đồng bản sao cấu trúc với bản sao sâu

Mảng mới hoặc danh sách mới có thể vẫn tham chiếu tới cùng đối tượng phần tử. Cần chính sách sao chép riêng nếu muốn phần tử cũng độc lập.

### Nhầm cố định kích thước với không sửa đổi được

Danh sách từ `Arrays.asList` cho phép `set`; danh sách từ `List.of` không cho phép `set`. Cả hai đều không thêm/xóa được, nhưng mức cho phép thay đổi không giống nhau.

## 12. Thực hành kiểm chứng

### Bài 1: dự đoán size và nội dung

Sửa `ArrayAndListDemo`:

1. Đổi dung lượng ban đầu của `ArrayList` thành `1`.
2. Giữ nguyên các lần `add`, `set` và `remove`.
3. Dự đoán có bao nhiêu phần tử sau bốn lần thêm.
4. Chạy và đối chiếu với kết quả ban đầu.

Dung lượng dự phòng ban đầu không phải giới hạn số phần tử của `ArrayList`. Với các thao tác được giữ nguyên, số phần tử sau thêm vẫn là `4`.

### Bài 2: theo dõi dữ liệu dùng chung

Trong `ArrayViewCopyDemo`, đổi:

```java
source[1] = "white";
```

thành:

```java
source[0] = "orange";
```

Trước khi chạy, viết nội dung dự đoán của `source`, `view`, `copy` và `snapshot`. Giải thích dự đoán dựa trên thời điểm tạo và quan hệ dùng chung, thay vì học thuộc stdout.

### Bài 3: chọn kiểu và thao tác

Với từng yêu cầu sau, hãy xác định cấu trúc, kiểu phần tử và cách thêm/xóa:

- Lưu 24 nhiệt độ theo từng giờ trong một ngày.
- Lưu các dòng sản phẩm trong một giỏ hàng được chỉnh sửa.
- Lưu những mã sản phẩm đã được đánh dấu, không chấp nhận trùng.
- Trả một mảng chuỗi cho API cũ từ dữ liệu đang có trong collection.

Hãy chỉ ra thao tác nào thay giá trị, thao tác nào thay số phần tử, trường hợp nào cần chuyển đổi và liệu có dữ liệu dùng chung sau chuyển đổi hay không.
