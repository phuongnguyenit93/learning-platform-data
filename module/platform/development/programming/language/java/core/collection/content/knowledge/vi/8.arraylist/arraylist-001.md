# Cấu trúc mảng động và phân biệt size với capacity

## 1. ArrayList giải quyết vấn đề gì của mảng?

Một mảng Java có độ dài cố định sau khi tạo. Với `new String[4]`, đối tượng mảng có đúng bốn vị trí; không thể đổi thuộc tính `length` của chính mảng đó thành tám.

`ArrayList<E>` cung cấp một danh sách có thể thêm và xóa phần tử mà người dùng không phải tự quản lý mảng nền. Khi cần chỗ lớn hơn, nó có thể tạo một mảng khác, chuyển các tham chiếu sang đó và dùng mảng mới làm nơi lưu trữ.

Từ “động” nói về cách cấu trúc danh sách quản lý chỗ chứa trong quá trình sử dụng. Nó không có nghĩa một đối tượng mảng Java tự thay đổi được độ dài.

Có hai đại lượng riêng:

- **Kích thước logic, `size`**: số phần tử hiện thuộc danh sách.
- **Sức chứa của mảng nền, `capacity`**: số vị trí mà mảng nội bộ dành để chứa phần tử trước khi phải tăng chỗ chứa.

Một cách hình dung là dãy vị trí đã được dành chỗ, trong đó chỉ một đoạn đầu đang thuộc danh sách. Có chỗ dự phòng không đồng nghĩa các vị trí dự phòng đã trở thành phần tử.

`ArrayList` là một triển khai của `List`; `size()`, thứ tự phần tử và truy cập theo chỉ số là phần của giao diện danh sách. Capacity gắn với cách triển khai bằng mảng của `ArrayList`, không phải khái niệm mà mọi `List` đều phải cung cấp. [ArrayList trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

## 2. size và capacity khác nhau ở đâu?

| Câu hỏi | size | capacity |
|---|---|---|
| Đang có bao nhiêu phần tử trong danh sách? | Trả lời câu hỏi này | Không trả lời câu hỏi này |
| Được dùng để xác định chỉ số đọc/thay phần tử hợp lệ? | Có | Không |
| Có API đọc trực tiếp trong ArrayList? | Có: `size()` | Không có phương thức công khai `capacity()` |
| Có tính phần tử mang giá trị `null`? | Có | Đếm chỗ chứa, không đếm giá trị khác `null` |
| Thêm phần tử có làm tăng? | Tăng theo số phần tử được thêm | Chỉ cần tăng nếu chỗ chứa chưa đủ |
| Xóa phần tử có làm giảm? | Giảm theo số phần tử bị xóa | Không nhất thiết giảm theo |
| Cấp chỗ dự phòng có tạo phần tử? | Không | Có thể làm tăng chỗ chứa |
| Thu gọn chỗ dự phòng có xóa phần tử? | Không | Có thể giảm tới bằng size |

Quan hệ cần giữ là:

```text
0 <= size <= capacity
```

Ví dụ khái niệm: danh sách có `size = 3`, mảng nền có `capacity = 6`.

```text
Chỉ số mảng:       0       1       2       3       4       5
                 +-------+-------+-------+-------+-------+-------+
Mảng nền:        |  A    | null  |  C    | trống | trống | trống |
                 +-------+-------+-------+-------+-------+-------+
Phần của List:   <---------- size = 3 ---------->
Toàn mảng nền:   <---------------- capacity = 6 ---------------->
```

Trong hình, “trống” chỉ là nhãn giải thích các ô nằm ngoài phần logic của danh sách. Nó không phải một giá trị Java đặc biệt. Các ô dự phòng của mảng tham chiếu có thể cũng mang giá trị `null`; `ArrayList` phân biệt vùng có phần tử bằng `size`, không bằng cách tìm ô `null` đầu tiên.

Vì vậy, `[A, null, C]` có ba phần tử. `null` ở chỉ số 1 vẫn là một phần tử thật của danh sách và vẫn chiếm một vị trí logic.

## 3. Mảng nền chứa gì?

Trong OpenJDK 17, `ArrayList` dùng một mảng `Object[]` để giữ các tham chiếu và một trường số nguyên để theo dõi số phần tử. Đây là mô tả triển khai giúp giải thích cơ chế, không phải quyền truy cập trực tiếp vào các trường nội bộ.

Với `ArrayList<Person>`, các ô mảng giữ tham chiếu đến đối tượng `Person`; bản thân toàn bộ đối tượng `Person` không bị nhét vào từng ô như một khối dữ liệu nằm liền nhau. Khi nói mảng có các vị trí liên tiếp, cần phân biệt vị trí chứa tham chiếu với vị trí thực tế của các đối tượng được tham chiếu trên heap.

Với `ArrayList<Integer>`, các giá trị số được biểu diễn bằng đối tượng bao `Integer` khi cần boxing. Cấu trúc này không tương đương với một `int[]` về cách lưu trữ và chi phí bộ nhớ.

Khi mảng nền được thay bằng mảng lớn hơn:

- Thứ tự logic của các phần tử được giữ.
- Các tham chiếu phần tử được chuyển sang chỗ chứa mới.
- Những đối tượng phần tử không tự được sao chép sâu hoặc tạo lại.
- Các biến khác đang tham chiếu đến cùng đối tượng phần tử vẫn tham chiếu đối tượng đó.

Hệ quả quan trọng: capacity tính bằng **số ô chứa tham chiếu**, không tính bằng byte và không cho biết tổng bộ nhớ của mọi đối tượng trong danh sách. Tổng bộ nhớ còn phụ thuộc bố cục đối tượng, tham chiếu, căn chỉnh và các đối tượng phần tử. [Triển khai ArrayList của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java).

## 4. Cấp capacity trước không tạo ra phần tử

### 4.1. new ArrayList<>(n) vẫn có size bằng 0

Đoạn minh họa bên trong một phương thức:

```java
ArrayList<String> names = new ArrayList<>(100);

System.out.println(names.size());    // 0
System.out.println(names.isEmpty()); // true
```

Đối số 100 là capacity ban đầu, không phải số phần tử ban đầu. Các lời gọi sau vẫn sai ngay lúc này:

```java
names.get(0);      // IndexOutOfBoundsException
names.set(0, "An"); // IndexOutOfBoundsException
```

Đây là các dòng minh họa lỗi độc lập, không phải phần tiếp tục chạy sau khi dòng đầu đã ném ngoại lệ. Chỉ số đọc hoặc thay thế phải thỏa `0 <= index < size()`; capacity không nới phạm vi này.

Muốn tạo phần tử đầu tiên, gọi `names.add("An")`. Sau đó `size()` mới là 1 và `get(0)`, `set(0, ...)` mới hợp lệ.

Đối số `initialCapacity` của hàm dựng phải không âm. Giá trị 0 tạo danh sách rỗng vẫn thêm được về sau; giá trị âm gây `IllegalArgumentException`.

Capacity ban đầu cũng không phải giới hạn số lượng phần tử tối đa. Một `new ArrayList<>(2)` vẫn có thể chứa hơn hai phần tử; danh sách sẽ tăng chỗ chứa khi cần, nếu việc cấp phát có thể thực hiện.

### 4.2. add và set có nhiệm vụ khác nhau

| Thao tác | Vai trò | Tác động đến size |
|---|---|---|
| `add(value)` | Thêm phần tử ở cuối | Tăng một |
| `add(index, value)` | Chèn phần tử tại vị trí hợp lệ | Tăng một |
| `set(index, value)` | Thay một phần tử đã tồn tại | Không đổi |
| `get(index)` | Đọc một phần tử đã tồn tại | Không đổi |

Với `add(index, value)`, vị trí chèn cho phép `0 <= index <= size()`. Cho phép chèn ngay sau phần tử cuối không có nghĩa cho phép chèn vào một chỉ số bất kỳ nhỏ hơn capacity.

Ví dụ, danh sách rỗng có capacity 100 cho phép `add(0, "A")`, nhưng không cho phép `add(50, "A")`. Nó không tự tạo 50 phần tử trung gian để lấp khoảng trống.

### 4.3. Nếu thật sự cần n vị trí logic

Có bài toán cần tạo sẵn danh sách chứa `n` phần tử `null` rồi thay từng vị trí. Khi đó phải tạo phần tử, không chỉ cấp capacity.

Đoạn minh họa, cần import `java.util.Collections`:

```java
ArrayList<String> slots =
        new ArrayList<>(Collections.nCopies(3, (String) null));

slots.set(2, "LAST");

// slots = [null, null, LAST]
// slots.size() = 3
```

Ở đây danh sách thực sự có ba phần tử. Hàm dựng `ArrayList(Collection)` nhận một collection để lấy các phần tử ban đầu, khác với hàm dựng `ArrayList(int)` chỉ nhận capacity ban đầu.

Không cần lấp `null` chỉ để chuẩn bị thêm dữ liệu ở cuối. Nếu mục tiêu là nạp lần lượt bằng `add`, cấp capacity hợp lý rồi thêm phần tử thường diễn đạt đúng ý định hơn.

## 5. Cơ chế tăng mảng khi thêm phần tử

### 5.1. Khi còn chỗ trống

Nếu `size < capacity`, thêm ở cuối có thể dùng ô tại chỉ số `size` của mảng nền:

```text
Trước: size = 3, capacity = 6
       [A, B, C, trống, trống, trống]

Thêm D:
       [A, B, C, D, trống, trống]
Sau:  size = 4, capacity = 6
```

Kích thước logic tăng, nhưng không cần thay mảng chỉ vì một phần tử vừa được thêm.

### 5.2. Khi mảng đã đầy

Nếu `size == capacity` và cần thêm một phần tử:

1. Tính sức chứa mới đủ đáp ứng yêu cầu.
2. Cấp mảng mới.
3. Sao chép các ô cần giữ từ mảng cũ sang mảng mới.
4. Chuyển danh sách sang sử dụng mảng mới.
5. Đặt phần tử mới vào vị trí cuối và cập nhật size.

Đây là mô tả cơ chế, không phải mã nguồn đầy đủ của `ArrayList`. Triển khai thực còn xử lý tăng theo lô, giới hạn độ dài mảng và trường hợp cấp phát không thực hiện được.

```text
Trước khi thêm:
size = 4
mảng cũ, capacity = 4: [A, B, C, D]

Sau khi tăng chỗ và thêm E:
size = 5
mảng mới, ví dụ capacity = 6: [A, B, C, D, E, trống]
```

Số 6 trong hình minh họa một lần tăng có thể xảy ra; không phải cam kết rằng mọi lần tăng đều cho đúng con số đó.

Trong lúc thay mảng, mảng cũ và mảng mới có thể cùng tồn tại tạm thời. Vì thế, thao tác tăng có chi phí cấp phát và sao chép; mức bộ nhớ tạm dùng có thể lớn hơn kích thước của riêng mảng cuối cùng.

### 5.3. Chính sách tăng trưởng là chi tiết triển khai

API của `ArrayList` bảo đảm tăng chỗ chứa tự động và chi phí thêm cuối theo nghĩa khấu hao. API không quy định rằng capacity phải nhân đôi hay luôn tăng đúng 50%.

Trong nhánh OpenJDK 17 được tham khảo, mức tăng ưu tiên thường bằng một nửa capacity cũ. Kích thước mới còn phải đáp ứng mức tối thiểu đang cần và các giới hạn khác. Với các giá trị nhỏ, thêm lần lượt và bắt đầu từ capacity 4, một diễn tiến điển hình là:

| Trạng thái | size | Capacity theo chính sách OpenJDK 17 đang mô tả |
|---|---|---|
| Vừa tạo `new ArrayList<>(4)` | 0 | 4 |
| Đã thêm bốn phần tử | 4 | 4 |
| Thêm phần tử thứ năm | 5 | 6 |
| Thêm phần tử thứ sáu | 6 | 6 |
| Thêm phần tử thứ bảy | 7 | 9 |

Đây là bảng phân tích triển khai, không phải kết quả từ một phương thức công khai đọc capacity. Không viết kiểm thử nghiệp vụ buộc các capacity trung gian phải bằng 4, 6, 9. [Cơ chế grow trong OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java), [tính độ dài mới trong ArraysSupport](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/jdk/internal/util/ArraysSupport.java).

Hàm dựng rỗng cũng cần được đọc đúng lớp thông tin: Javadoc mô tả capacity ban đầu mặc định là 10, nhưng OpenJDK 17 trì hoãn việc cấp mảng cho trường hợp rỗng mặc định. Lần thêm thông thường đầu tiên mới thực hiện chính sách cấp chỗ ban đầu đó. Không suy từ số 10 rằng mọi danh sách vừa gọi `new ArrayList<>()` đã lập tức sở hữu một mảng riêng có mười ô.

Chi tiết cấp phát muộn không thay đổi điều người dùng quan sát qua `List`: trước lần thêm đầu tiên, danh sách vẫn rỗng và size vẫn bằng 0.

## 6. Vì sao thêm cuối là O(1) khấu hao?

Một lần thêm cuối khi còn chỗ thường chỉ cần ghi tham chiếu và tăng size. Một lần thêm khi phải tăng mảng có thể phải sao chép số lượng ô tỉ lệ với mảng cũ, nên lần thêm đó có thể tốn `O(n)`.

**Khấu hao (amortized)** xem tổng chi phí trên cả một dãy thao tác, không nói rằng từng lần gọi đều có chi phí bằng nhau.

Nếu mảng tăng theo một tỉ lệ lớn hơn 1 thay vì chỉ tăng một ô, giữa hai lần tăng có nhiều lần thêm không cần sao chép. Tổng lượng sao chép qua một dãy thêm dài được chặn bởi một hằng số nhân với số phần tử được thêm, trong điều kiện sử dụng thông thường của phân tích.

Một mô hình toán học dễ nhìn là tăng gấp đôi: tổng các mức cũ `1 + 2 + 4 + ...` nhỏ hơn một hằng số nhân với mức cuối. Đây là mô hình giải thích tổng chi phí, không khẳng định `ArrayList` Java đang tăng gấp đôi.

Kết quả:

- Thêm `n` phần tử ở cuối có tổng chi phí `O(n)` theo bảo đảm khấu hao.
- Chi phí bình quân khấu hao cho một lần thêm cuối là `O(1)`.
- Một lần thêm riêng lẻ vẫn có thể chậm hơn vì cấp phát và sao chép.
- Khấu hao không phải cam kết độ trễ cố định cho từng lời gọi.

Capacity dư đổi một phần bộ nhớ lấy việc giảm tần suất cấp mảng mới. Nếu tăng đúng một ô mỗi khi đầy, gần như mỗi lần thêm lại phải sao chép danh sách đang lớn dần, dẫn đến tổng chi phí kiểu `1 + 2 + ... + n`, tức `O(n²)`.

### 6.1. Capacity dư không loại bỏ chi phí dịch phần tử

| Thao tác trên ArrayList | Cơ chế chính | Chi phí thường dùng để phân tích |
|---|---|---|
| `size()`, `isEmpty()` | Đọc trạng thái kích thước | `O(1)` |
| `get(i)`, `set(i, value)` | Truy cập trực tiếp vị trí sau kiểm tra biên | `O(1)` |
| `add(value)` ở cuối | Ghi cuối; đôi khi tăng mảng | `O(1)` khấu hao, một lần có thể `O(n)` |
| Chèn ở đầu hoặc giữa | Dịch các phần tử phía sau; có thể tăng mảng | `O(n)` trong trường hợp xấu |
| Xóa ở đầu hoặc giữa theo chỉ số | Dịch phần tử phía sau sang trái | `O(n)` trong trường hợp xấu |
| Xóa phần tử cuối theo chỉ số | Bỏ tham chiếu cuối và giảm size | `O(1)` |
| `clear()` | Bỏ các tham chiếu thuộc vùng logic | `O(n)` với `n = size` trước khi xóa |

Nếu đã cấp capacity 10.000 rồi chèn vào đầu danh sách có 5.000 phần tử, việc dịch 5.000 phần tử vẫn còn. Cấp trước capacity giúp tránh tăng mảng, không biến chèn giữa thành một phép ghi duy nhất.

Tương tự, xóa theo giá trị có thể phải tìm phần tử trước khi xóa. Đừng dùng độ phức tạp của xóa cuối theo chỉ số để mô tả mọi dạng `remove`.

## 7. ensureCapacity: dự phòng chỗ, không đổi nội dung

Đoạn minh họa:

```java
ArrayList<String> names = new ArrayList<>();
names.ensureCapacity(1_000);

// names.size() vẫn là 0
// names vẫn là []
```

`ensureCapacity(minCapacity)` yêu cầu danh sách chuẩn bị chỗ cho ít nhất số phần tử được chỉ định khi cần. Nó không thêm các phần tử `null`, không trả một danh sách mới và không đổi thứ tự phần tử hiện có.

Không hiểu nó thành “đặt capacity chính xác bằng tham số”. Nếu danh sách đã có capacity lớn hơn, không cần thu nhỏ; khi phải tăng, triển khai có thể chọn sức chứa lớn hơn mức tối thiểu.

Các trường hợp hợp lý:

- Biết khá chắc số phần tử sẽ nạp trong một đợt, có thể cấp capacity từ hàm dựng.
- Đang có một `ArrayList` và biết sắp thêm nhiều phần tử, có thể gọi `ensureCapacity` trước đợt thêm.
- Muốn giảm số lần cấp mảng lại và sao chép trong lúc nạp dữ liệu.

Đừng gọi `ensureCapacity` với một con số cực lớn chỉ vì “để khỏi tăng nữa”. Phần chỗ dự phòng vẫn có chi phí bộ nhớ và có thể làm việc cấp phát thất bại. Ước lượng nên dựa trên khối lượng dữ liệu có lý do, không dựa trên giới hạn số nguyên lớn nhất.

Capacity không phải giới hạn nghiệp vụ. Nếu chỉ được nhận tối đa 100 mục, phải kiểm tra quy tắc đó trước khi thêm; `new ArrayList<>(100)` không chặn mục thứ 101. [ArrayList.ensureCapacity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#ensureCapacity(int)).

### 7.1. Phương thức capacity thuộc kiểu ArrayList

Nếu khai báo:

```java
List<String> names = new ArrayList<>();
```

thì qua kiểu `List`, không thể gọi trực tiếp `names.ensureCapacity(...)` hoặc `names.trimToSize()`; hai phương thức này không nằm trong giao diện `List`.

Khi một đoạn mã thật sự cần kiểm soát chỗ chứa của `ArrayList`, có thể giữ biến cục bộ mang kiểu `ArrayList`. Ở ranh giới API chỉ cần các thao tác danh sách, kiểu `List` vẫn giúp diễn đạt đúng khả năng cần dùng. Không ép kiểu mọi danh sách sang `ArrayList` chỉ để can thiệp capacity, vì đối tượng thực tế có thể là một triển khai khác.

## 8. Xóa phần tử và thu nhỏ mảng là hai việc riêng

### 8.1. remove làm giảm size

Ví dụ khái niệm:

```text
Trước:
size = 4, capacity = 6
[A, B, C, D, trống, trống]

Xóa B ở chỉ số 1:
size = 3, capacity vẫn = 6
[A, C, D, trống, trống, trống]
```

Các phần tử phía sau được dịch sang trái. Trong triển khai OpenJDK, ô cuối không còn thuộc vùng logic được đặt về `null` để mảng không giữ thừa tham chiếu đến phần tử.

Việc bỏ tham chiếu từ danh sách không có nghĩa đối tượng bị hủy ngay. Nếu nơi khác vẫn giữ tham chiếu, đối tượng vẫn được dùng bình thường; nếu không còn tham chiếu giữ sống, việc thu hồi còn do bộ gom rác quản lý.

### 8.2. clear làm size về 0 nhưng giữ chỗ chứa để tái sử dụng

Trong OpenJDK 17, `clear()` bỏ các tham chiếu phần tử và đặt size về 0, nhưng không tự thay mảng nền bằng một mảng nhỏ chỉ vì danh sách đã rỗng.

Điều này hữu ích nếu danh sách sẽ được nạp lại nhiều lần với quy mô tương tự. Giữ chỗ chứa giúp tránh phải cấp lại mảng từ đầu sau mỗi đợt.

Nhưng nếu một danh sách từng rất lớn, sau `clear()` nó vẫn có thể giữ một mảng nền lớn. Cần phân biệt hai loại dữ liệu:

- Các đối tượng phần tử cũ không còn được danh sách giữ chỉ vì từng có trong danh sách.
- Mảng nền chứa các ô dự phòng vẫn có thể còn được danh sách giữ.

Không dùng `clear()` như một lời hứa rằng mọi bộ nhớ liên quan đã được trả ngay. [remove, clear và trimToSize trong mã OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java).

### 8.3. trimToSize thu capacity về size hiện tại

`trimToSize()` thu capacity của `ArrayList` về kích thước logic hiện tại. Nội dung và size không thay đổi.

Đoạn minh họa:

```java
ArrayList<String> names = new ArrayList<>(1_000);
names.add("An");
names.add("Binh");

names.trimToSize();

// size vẫn là 2; nội dung vẫn [An, Binh].
// Capacity sau trim bằng size hiện tại.
```

Thao tác này có thể cần tạo mảng mới và sao chép các tham chiếu đang dùng. Nó không làm danh sách trở thành bất biến và không đặt giới hạn số phần tử vĩnh viễn. Nếu tiếp tục thêm khi mảng đã đầy, danh sách lại tăng chỗ chứa.

Đừng đặt `trimToSize()` sau mỗi lần `add`. Việc liên tục ép capacity sát size rồi lại thêm có thể buộc cấp phát và sao chép lặp đi lặp lại, phá lợi ích của chỗ dự phòng.

Một thời điểm có thể cân nhắc là sau đợt nạp/xóa lớn, khi biết danh sách sẽ được giữ lâu và ít thêm phần tử nữa. Quyết định cần cân bằng bộ nhớ, số lần sao chép và mẫu sử dụng. [ArrayList.trimToSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#trimToSize()).

## 9. Chương trình đầy đủ: size, chỉ số và các thao tác capacity

Các đoạn ngắn ở trên minh họa bên trong phương thức và cần import thích hợp. Chương trình sau là tệp độc lập, dùng API có trong Java 17.

Lưu thành `SizeCapacityDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;

public class SizeCapacityDemo {
    private static void show(String step, ArrayList<String> values) {
        System.out.println(step + ": size = " + values.size()
                + ", values = " + values);
    }

    public static void main(String[] args) {
        ArrayList<String> values = new ArrayList<>(5);
        show("new ArrayList<>(5)", values);
        System.out.println("empty = " + values.isEmpty());

        try {
            values.get(0);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("get(0) -> IndexOutOfBoundsException");
        }
        try {
            values.set(0, "A");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("set(0) -> IndexOutOfBoundsException");
        }

        values.ensureCapacity(12);
        show("after ensureCapacity(12)", values);

        values.add("A");
        values.add(null);
        values.add("C");
        show("after three adds", values);
        System.out.println("toArray().length = " + values.toArray().length);

        String old = values.set(1, "B");
        System.out.println("set returned = " + old);
        show("after set(1, B)", values);

        values.add(1, "X");
        show("after add(1, X)", values);

        String removed = values.remove(2);
        System.out.println("removed = " + removed);
        show("after remove(2)", values);

        values.trimToSize();
        show("after trimToSize()", values);

        values.clear();
        show("after clear()", values);

        values.trimToSize();
        values.add("Z");
        show("after empty trim and add", values);

        ArrayList<String> slots =
                new ArrayList<>(Collections.nCopies(3, (String) null));
        show("three real null elements", slots);
        slots.set(2, "LAST");
        show("after slots.set(2, LAST)", slots);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SizeCapacityDemo.java
java SizeCapacityDemo
```

Kết quả chuẩn:

```text
new ArrayList<>(5): size = 0, values = []
empty = true
get(0) -> IndexOutOfBoundsException
set(0) -> IndexOutOfBoundsException
after ensureCapacity(12): size = 0, values = []
after three adds: size = 3, values = [A, null, C]
toArray().length = 3
set returned = null
after set(1, B): size = 3, values = [A, B, C]
after add(1, X): size = 4, values = [A, X, B, C]
removed = B
after remove(2): size = 3, values = [A, X, C]
after trimToSize(): size = 3, values = [A, X, C]
after clear(): size = 0, values = []
after empty trim and add: size = 1, values = [Z]
three real null elements: size = 3, values = [null, null, null]
after slots.set(2, LAST): size = 3, values = [null, null, LAST]
```

Các quan sát cần rút ra:

1. Capacity ban đầu là 5 nhưng danh sách rỗng. `get(0)` và `set(0, ...)` không được phép.
2. Sau `ensureCapacity(12)`, nội dung và size vẫn không đổi.
3. Ba lời gọi `add` tạo ba phần tử, kể cả phần tử `null`.
4. `set` thay `null` bằng `B`, trả giá trị cũ là `null` và không tăng size.
5. `add(1, "X")` chèn một phần tử mới nên size tăng.
6. `remove(2)` xóa một phần tử nên size giảm.
7. `trimToSize` không thay đổi nội dung. Sau khi rỗng và thu gọn, danh sách vẫn thêm lại được.
8. Danh sách tạo từ ba `null` thực sự có ba phần tử, nên `set(2, ...)` hợp lệ.

Chương trình cố ý không in capacity nội bộ vì `ArrayList` không cung cấp API công khai để đọc nó. Kết quả kiểm tra những điều người gọi có thể dựa vào: số phần tử, nội dung và tính hợp lệ của thao tác.

### 9.1. toArray().length không phải phép đọc capacity

Trong chương trình, `values.toArray().length` là 3 vì danh sách có ba phần tử. `toArray()` trả một mảng chứa các phần tử logic; nó không trao mảng nền để quan sát chỗ dự phòng.

Vì vậy, không viết `list.toArray().length` rồi gắn nhãn “capacity”. Thao tác này còn tạo một mảng kết quả riêng, có chi phí không cần thiết nếu chỉ muốn biết số phần tử.

Cũng không dùng số lượng giá trị khác `null` để suy ra size hoặc capacity. Một danh sách có thể chứa nhiều phần tử `null` hợp lệ.

## 10. Chương trình đầy đủ: thay mảng không nhân bản phần tử

Lưu thành `ArrayListReferenceDemo.java`:

```java
import java.util.ArrayList;

public class ArrayListReferenceDemo {
    private static final class Item {
        private String name;

        private Item(String name) {
            this.name = name;
        }

        private void rename(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        ArrayList<Item> items = new ArrayList<>(1);
        Item first = new Item("A");
        items.add(first);

        items.ensureCapacity(100);
        System.out.println("after reserve: same first = "
                + (items.get(0) == first));
        System.out.println("after reserve: size = " + items.size());

        items.add(new Item("B"));
        items.trimToSize();
        System.out.println("after trim: same first = "
                + (items.get(0) == first));
        System.out.println("after trim: items = " + items);

        first.rename("A*");
        System.out.println("after rename: items = " + items);

        Item removed = items.remove(0);
        System.out.println("removed is first = " + (removed == first));
        System.out.println("remaining items = " + items);

        items.clear();
        System.out.println("after clear: size = " + items.size());
        System.out.println("external reference = " + first);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ArrayListReferenceDemo.java
java ArrayListReferenceDemo
```

Kết quả chuẩn:

```text
after reserve: same first = true
after reserve: size = 1
after trim: same first = true
after trim: items = [A, B]
after rename: items = [A*, B]
removed is first = true
remaining items = [B]
after clear: size = 0
external reference = A*
```

Ở đây capacity ban đầu chỉ là 1; `ensureCapacity(100)` dự phòng chỗ lớn hơn. Dù có thay mảng nền, phần tử đầu vẫn là đúng đối tượng `first`, thể hiện bằng kết quả `==` là `true`.

Sau khi thêm phần tử thứ hai rồi thu gọn, tham chiếu đến phần tử đầu vẫn được giữ. Đổi tên qua biến `first` khiến danh sách cũng nhìn thấy tên mới, vì hai đường truy cập đang chỉ đến cùng đối tượng.

Cuối cùng, `remove` và `clear` không làm biến `first` ở bên ngoài biến mất. Biến đó vẫn tham chiếu đến đối tượng `Item` tên `A*`. Đây là bằng chứng về quan hệ tham chiếu, không phải phép đo thời điểm bộ gom rác chạy.

## 11. Đọc và sử dụng capacity đúng trong thực tế

### 11.1. Khi đã biết số lượng dữ liệu sẽ nạp

Đoạn minh họa:

```java
int expectedCount = 5_000;
ArrayList<String> rows = new ArrayList<>(expectedCount);

for (int i = 0; i < expectedCount; i++) {
    rows.add("row-" + i);
}
```

Capacity giúp giảm việc tăng mảng trong giai đoạn nạp. Nó không tạo sẵn chuỗi, không tránh chi phí tạo từng chuỗi và không bảo đảm toàn bộ tác vụ chỉ tốn một lần cấp phát. Ngoài mảng nền còn có các đối tượng phần tử và các chi phí khác.

Nếu số lượng chỉ là một ước lượng, danh sách vẫn có thể tăng thêm khi thực tế vượt dự kiến. Nếu ước lượng quá cao, có thể lãng phí nhiều ô dự phòng.

### 11.2. Khi tái sử dụng theo nhiều đợt

Nếu mỗi đợt có quy mô tương tự, giữ một `ArrayList` rồi `clear()` giữa các đợt có thể tận dụng mảng đã cấp. Nếu các đợt sau nhỏ hơn nhiều và danh sách được giữ lâu, cân nhắc thu gọn tại một ranh giới phù hợp.

Không có một quy tắc “luôn trim” hay “không bao giờ trim” đúng cho mọi chương trình. Quan sát lượng dữ liệu, thời gian giữ danh sách và chi phí cấp phát trước khi tối ưu.

### 11.3. Capacity không cung cấp an toàn luồng hoặc bảo đảm không lỗi

Có sẵn chỗ trống không làm `ArrayList` an toàn cho nhiều luồng cùng sửa. `size`, dữ liệu mảng và các thay đổi cấu trúc vẫn cần được quản lý theo chính sách đồng thời phù hợp.

Tăng capacity cũng không bảo đảm mọi lần thêm tương lai thành công: phần tử có thể tiếp tục tăng, tài nguyên có giới hạn, và mã xung quanh có thể có lỗi khác. Không coi con số dự phòng là một bằng chứng đầy đủ về hiệu năng hay tính đúng đắn.

## 12. Những hiểu nhầm cần sửa

| Hiểu nhầm | Điều thực sự xảy ra | Cách viết hoặc đọc đúng |
|---|---|---|
| `new ArrayList<>(100)` có 100 phần tử | Size ban đầu là 0 | Dùng `add` để tạo phần tử |
| Capacity 100 thì `get(99)` luôn hợp lệ | Phạm vi đọc dựa vào size | Kiểm tra `0 <= index < size()` |
| Có thể dùng `set` để thêm vào ô dự phòng | `set` chỉ thay phần tử đã có | Dùng `add` nếu cần tăng size |
| Capacity là giới hạn số phần tử tối đa | Nó là chỗ chứa hiện tại, có thể tăng | Viết quy tắc giới hạn riêng nếu cần |
| Có `null` thì danh sách chưa có phần tử ở đó | `null` có thể là phần tử hợp lệ | Size là số phần tử logic, không phải số phần tử khác `null` |
| Mọi lần thêm đều `O(1)` | Một số lần phải tăng và sao chép | Phân biệt một lần gọi với chi phí khấu hao |
| Còn capacity nên chèn giữa là `O(1)` | Vẫn phải dịch các phần tử phía sau | Phân tích cả dịch chuyển lẫn tăng mảng |
| Xóa làm capacity tự giảm tương ứng | Size giảm nhưng mảng có thể giữ nguyên | Chỉ thu gọn khi có lý do phù hợp |
| `clear()` trả ngay toàn bộ bộ nhớ đã dùng | Bỏ phần tử và giữ mảng nền để tái sử dụng | Phân biệt phần tử, mảng nền và việc thu hồi bởi GC |
| `trimToSize()` làm danh sách không thêm được nữa | Danh sách vẫn tăng khi thêm tiếp | Trim là tối ưu chỗ chứa tại thời điểm gọi |
| `toArray().length` là capacity | Đó là độ dài mảng kết quả của các phần tử | Dùng `size()` khi cần số phần tử |
| Capacity của Java luôn nhân đôi hoặc luôn nhân 1,5 | Hệ số cụ thể không thuộc bảo đảm API | Dựa vào hợp đồng thay vì con số trung gian |

## 13. Tự kiểm tra bằng một chuỗi thao tác

Giả sử bắt đầu với `ArrayList<String> values = new ArrayList<>(8);`. Không dùng reflection hoặc truy cập mảng nội bộ.

| Bước | Thao tác | Size sau bước | Điều có thể kết luận về chỗ chứa |
|---|---|---|---|
| 1 | Tạo danh sách | 0 | Có capacity ban đầu 8; chưa có phần tử |
| 2 | Thêm ba phần tử | 3 | Không cần vượt chỗ chứa 8 |
| 3 | Thay phần tử ở chỉ số 1 bằng `set` | 3 | Không cần tăng mảng chỉ để thay tham chiếu |
| 4 | Xóa phần tử ở chỉ số 0 | 2 | Xóa không tự thu mảng theo từng phần tử |
| 5 | `ensureCapacity(12)` | 2 | Chuẩn bị ít nhất chỗ chứa yêu cầu, không tạo thêm phần tử |
| 6 | `trimToSize()` | 2 | Capacity được thu về 2 |
| 7 | Thêm một phần tử | 3 | Phải có chỗ cho ít nhất ba phần tử; không dựa vào một hệ số cố định |
| 8 | `clear()` | 0 | Không còn phần tử logic; mảng nền có thể còn được giữ |

Các câu hỏi kiểm tra thêm:

1. Sau bước 1, `values.set(0, "A")` có hợp lệ không?
2. Sau bước 2, nếu một phần tử là `null`, size có còn bằng 3 không?
3. Sau bước 5, `values.get(10)` có hợp lệ không?
4. Sau bước 6, vì sao thêm phần tử mới có thể cần thay mảng?
5. Nếu một biến khác còn giữ đối tượng đã bị xóa khỏi danh sách, đối tượng đó có tự mất đi ngay không?

Đáp án:

1. Không, vì chưa có phần tử ở chỉ số 0.
2. Có; `null` vẫn được tính là một phần tử.
3. Không; size vẫn là 2 dù đã dự phòng chỗ.
4. Vì capacity bằng size hiện tại là 2, không còn ô dự phòng cho phần tử thứ ba.
5. Không; đối tượng vẫn có thể được dùng qua tham chiếu bên ngoài.

Khi phân tích một thao tác trên `ArrayList`, hãy tách ba câu hỏi: số phần tử logic có đổi không, mảng nền có cần đổi chỗ chứa không, và các phần tử có cần dịch vị trí không. Cách đọc này giúp dự đoán đúng cả hành vi chỉ số lẫn chi phí của cấu trúc mảng động.
