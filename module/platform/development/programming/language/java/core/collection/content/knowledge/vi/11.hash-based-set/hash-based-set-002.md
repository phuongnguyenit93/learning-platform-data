# Thêm, tìm, xóa và điều kiện đạt hiệu năng mong đợi của Set dùng băm

## 1. HashSet giải quyết bài toán gì?

Một chương trình xử lý nhiều mã công việc thường phải trả lời liên tục: “mã này đã xuất hiện chưa?”, “đây có phải lần đầu nhận mã này không?” hoặc “mã này còn nằm trong nhóm đang chờ không?”.

Nếu tự duyệt toàn bộ danh sách cho mỗi câu hỏi, số lần so sánh có thể tăng theo số phần tử đã lưu. `HashSet<E>` tổ chức dữ liệu bằng băm để thu hẹp nơi cần tìm, thay vì buộc mỗi truy vấn phải quét mọi phần tử.

Ba thao tác trọng tâm là:

| Mục đích | Phương thức | Ý nghĩa giá trị trả về |
| --- | --- | --- |
| Thêm nếu chưa có | `boolean add(E value)` | true nếu tập có thêm phần tử |
| Kiểm tra có thuộc tập không | `boolean contains(Object value)` | true nếu tìm thấy phần tử phù hợp |
| Xóa nếu đang có | `boolean remove(Object value)` | true nếu tập có phần tử bị xóa |

Tài liệu `HashSet` mô tả các thao tác cơ bản có thời gian hằng số khi hàm băm phân bố phần tử phù hợp giữa các ngăn của bảng. Trong thực hành thường nói `add`, `contains`, `remove` có O(1) kỳ vọng; với thêm mới còn phải xét chi phí tăng dung lượng theo cách phân tích khấu hao.

Điều kiện phân bố băm là một phần của kết luận, không phải chi tiết có thể bỏ qua. O(1) kỳ vọng không có nghĩa mỗi lời gọi luôn mất đúng cùng số nano giây, không có va chạm, không phải cấp phát bộ nhớ hoặc không bao giờ tăng dung lượng. [HashSet: mô hình và hiệu năng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

Bài này tập trung vào `HashSet` trên Java 17+. Khi một biến chỉ có kiểu `Set`, cần biết đối tượng thực tế là gì trước khi suy ra mô hình hiệu năng. Giao diện `Set` không bắt buộc mọi triển khai phải dùng băm.

## 2. Mô hình tìm phần tử bằng băm

### 2.1. Bảng băm giúp thu hẹp vùng tìm

`HashSet` dùng một `HashMap` ở phía sau để quản lý các phần tử. Với người sử dụng tập, không cần tự thao tác trên map đó; điều cần hiểu là quan hệ giữa hai phương thức của phần tử:

- `hashCode()` giúp xác định vùng có thể chứa phần tử.
- `equals(...)` xác định hai giá trị có thực sự bằng nhau không.

Có thể hình dung một truy vấn bằng sơ đồ:

```text
giá trị cần tìm
    ↓
tính mã băm
    ↓
chọn ngăn (bucket) tương ứng trong bảng
    ↓
đối chiếu các ứng viên trong vùng đó
    ↓
phân biệt bằng nhau bằng quy tắc equals
    ↓
tìm thấy / không tìm thấy
```

Đây là mô hình để suy luận, không phải công thức tính chỉ số ngăn hoặc mô tả bắt buộc của mọi phiên bản JDK.

Một `HashSet` không sắp xếp phần tử theo giá trị để thực hiện các thao tác trên. Nó cũng không có chỉ số để người dùng yêu cầu “xóa phần tử ở vị trí 3”. Nếu cần loại bỏ một giá trị, truyền chính giá trị truy vấn vào `remove`.

### 2.2. Trùng mã băm chưa phải trùng phần tử

Hai đối tượng khác nhau có thể có cùng mã băm. Đó là **va chạm băm (hash collision)**.

Ví dụ, hai khóa công việc `id=10` và `id=20` có thể bị một hàm băm kém đưa tới cùng vùng. Tập vẫn cần dùng quy tắc bằng nhau để giữ chúng là hai phần tử nếu chúng không bằng nhau.

Do đó:

```text
equals true  → bắt buộc cùng hashCode
cùng hashCode → chưa đủ để kết luận equals true
```

Nếu chỉ có một vài va chạm trong một bảng được phân bố tốt, cơ chế này vẫn hữu ích. Nếu gần như mọi khóa dồn vào cùng một vùng, việc thu hẹp vùng tìm mất phần lớn lợi ích.

Cùng mã băm không làm tập tự bỏ mất các khóa khác nhau. Ngược lại, định nghĩa sai `equals` có thể làm các giá trị mà nghiệp vụ muốn giữ riêng bị xem là trùng. Tính đúng của quy tắc bằng nhau phải được giải quyết trước khi tối ưu phân bố băm. [Object: hợp đồng equals và hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)

## 3. Đọc đúng kết quả add, contains và remove

### 3.1. add trả lời tập có nhận thêm một phần tử không

Với `HashSet` có quy tắc phần tử ổn định:

- Chưa có phần tử bằng giá trị cần thêm: tập thêm phần tử, kích thước tăng 1, trả về `true`.
- Đã có phần tử bằng giá trị đó: tập không thêm bản sao, kích thước không đổi, trả về `false`.

Hai đối tượng được tạo riêng vẫn có thể là một giá trị đối với tập. Vì vậy, “đã dùng `new` lần nữa” không phải lý do để mong kích thước tăng.

Khi chỉ muốn xử lý lần đầu gặp một mã, dùng trực tiếp kết quả `add`:

```java
// Đoạn minh họa: seen là HashSet<String> do luồng hiện tại quản lý.
if (seen.add(code)) {
    System.out.println("Lần đầu gặp mã: " + code);
}
```

Không cần viết trước `if (!seen.contains(code))` rồi mới `seen.add(code)`. Cách đó thường làm thêm một lần tra cứu mà `add` vốn đã phải thực hiện.

### 3.2. contains là phép đọc, không lấy phần tử ra khỏi tập

`contains(value)` trả về `boolean`, không phải phần tử đang lưu hoặc vị trí phần tử. Nó không thay đổi kích thước tập.

Đối số là `Object`. Ví dụ, với một `HashSet<Integer>` chứa `1`, gọi `contains(1L)` vẫn có thể biên dịch, nhưng `Long` có giá trị `1L` không bằng `Integer` có giá trị `1`.

Không tự suy ra rằng mọi kiểu giá trị “trông giống nhau” trong giao diện người dùng sẽ được tập coi là bằng nhau. Kiểu và cách chuẩn hóa giá trị truy vấn phải khớp quy tắc định danh đang dùng.

### 3.3. remove trả lời có phần tử bị xóa không

`remove(value)` xóa phần tử bằng giá trị truy vấn nếu có và trả về `true`. Nếu không có, tập giữ nguyên và trả về `false`.

Nếu chỉ cần xóa rồi báo tập có thay đổi không:

```java
// Đoạn minh họa: pending là HashSet<TaskId> có thể sửa đổi.
if (pending.remove(taskId)) {
    System.out.println("Đã bỏ công việc khỏi nhóm đang chờ");
}
```

Không cần `contains` trước mỗi lần `remove`. Kết quả xóa đã trả lời việc tập có thay đổi không.

| Lời gọi với một giá trị hợp lệ | Trước thao tác | Kết quả | Sau thao tác |
| --- | --- | --- | --- |
| `add(x)` | Chưa có x | `true` | Có x; size tăng 1 |
| `add(x)` | Đã có giá trị bằng x | `false` | Giữ nguyên |
| `contains(x)` | Có giá trị bằng x | `true` | Giữ nguyên |
| `contains(x)` | Không có x | `false` | Giữ nguyên |
| `remove(x)` | Có giá trị bằng x | `true` | Không còn x; size giảm 1 |
| `remove(x)` | Không có x | `false` | Giữ nguyên |

Bảng giả định phần tử không bị sửa theo cách làm thay đổi quy tắc bằng nhau trong khi đang nằm trong tập và không có tác nhân khác sửa tập trong lúc đang xét.

Gọi trực tiếp `add` hoặc `remove` giúp tránh một phép tra cứu thừa; nó không tự làm `HashSet` an toàn cho nhiều luồng cùng sửa đổi. `HashSet` không cung cấp cơ chế đồng bộ sẵn. [Các thao tác và giới hạn đồng bộ của HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

## 4. Chương trình đầy đủ: thêm trùng, tìm theo giá trị và xóa

Lưu mã vào **HashSetOperationsDemo.java**:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class HashSetOperationsDemo {
    private record TaskId(String value) {
    }

    public static void main(String[] args) {
        Set<TaskId> pending = new HashSet<>();
        TaskId original = new TaskId("t-10");
        TaskId sameValue = new TaskId("t-10");

        System.out.println("same reference: " + (original == sameValue));
        System.out.println("add first: " + pending.add(original));
        System.out.println("add equal key: " + pending.add(sameValue));
        System.out.println("size after duplicate: " + pending.size());
        System.out.println("contains equal key: "
                + pending.contains(new TaskId("t-10")));
        System.out.println("contains missing key: "
                + pending.contains(new TaskId("t-99")));
        System.out.println("remove equal key: "
                + pending.remove(new TaskId("t-10")));
        System.out.println("remove again: "
                + pending.remove(new TaskId("t-10")));
        System.out.println("empty: " + pending.isEmpty());

        Set<String> tags = new HashSet<>();
        System.out.println("add null: " + tags.add(null));
        System.out.println("add null again: " + tags.add(null));
        System.out.println("contains null: " + tags.contains(null));
        System.out.println("remove null: " + tags.remove(null));

        Set<String> seen = new HashSet<>();
        for (String value : List.of("java", "sql", "java", "http", "sql")) {
            if (seen.add(value)) {
                System.out.println("first encounter: " + value);
            }
        }
        System.out.println("distinct values: " + seen.size());
    }
}
```

Biên dịch theo mức Java 17 và chạy:

```shell
javac --release 17 -encoding UTF-8 HashSetOperationsDemo.java
java HashSetOperationsDemo
```

Stdout:

```text
same reference: false
add first: true
add equal key: false
size after duplicate: 1
contains equal key: true
contains missing key: false
remove equal key: true
remove again: false
empty: true
add null: true
add null again: false
contains null: true
remove null: true
first encounter: java
first encounter: sql
first encounter: http
distinct values: 3
```

Cách đọc kết quả:

1. Hai `TaskId("t-10")` khác tham chiếu nhưng bằng nhau theo giá trị thành phần record.
2. Thêm đối tượng đầu thành công; thêm đối tượng bằng nó không làm kích thước tăng.
3. Có thể dùng một khóa mới tạo nhưng bằng giá trị để tìm hoặc xóa khóa đang lưu.
4. Lần xóa thứ hai trả về `false` vì phần tử đã bị xóa.
5. `HashSet` cho phép `null`, nhưng vẫn chỉ có tối đa một phần tử `null`.
6. Vòng lặp dùng `seen.add(value)` để phát hiện lần đầu gặp từng giá trị.

Ba dòng `first encounter` xuất hiện theo thứ tự duyệt **danh sách đầu vào**. Chương trình in ngay khi `add` trả về `true`; nó không duyệt `HashSet` để in kết quả. Vì vậy, stdout đó không có nghĩa `HashSet` giữ thứ tự chèn.

Record `TaskId` dùng một thành phần `String` bất biến, nên phù hợp để làm khóa giá trị đơn giản trong ví dụ. Không suy ra rằng mọi record đều tự có các thành phần bất biến.

## 5. Điều kiện thứ nhất: equals và hashCode phải đúng, ổn định

### 5.1. Đối tượng bằng nhau phải có cùng mã băm

Nếu viết một lớp mà `equals` cho rằng hai mã công việc bằng nhau nhưng `hashCode` cho ra hai kết quả khác nhau, chương trình đã vi phạm hợp đồng đối tượng.

Khi đó, một phép tìm có thể bắt đầu ở vùng khác với vùng đã dùng lúc chèn. Tăng dung lượng, giảm hệ số tải hoặc viết thêm `contains` trước `remove` không sửa được lỗi hợp đồng này.

Nếu tự định nghĩa `equals`, cần đồng thời thiết kế `hashCode` từ dữ liệu tương ứng. Nếu dùng một kiểu giá trị có sẵn, cần hiểu quy tắc bằng nhau của kiểu đó.

### 5.2. Không thay đổi dữ liệu nhận diện khi phần tử đang ở trong tập

Giả sử một đối tượng dùng trường `code` để tính cả `equals` và `hashCode`. Sau khi đối tượng được thêm vào tập, chương trình đổi `code`.

Từ đó, mã băm và ý nghĩa bằng nhau của đối tượng có thể khác lúc nó được đặt vào cấu trúc. Dù vẫn giữ đúng tham chiếu đối tượng, không thể suy luận rằng `contains` hoặc `remove` sẽ hoạt động như với một khóa ổn định.

Hợp đồng `Set` không quy định hành vi khi một phần tử bị thay đổi theo cách ảnh hưởng đến phép bằng nhau trong khi nó vẫn là phần tử của tập. Không dùng một stdout tình cờ trên một JDK để biến trường hợp này thành quy tắc có thể dựa vào. [Set: phần tử có thể sửa đổi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

Ưu tiên khóa bất biến. Nếu nghiệp vụ cần đổi định danh, hãy thiết kế rõ quy trình xóa khóa cũ trước khi đổi rồi thêm khóa mới, cùng cách xử lý nếu khóa mới đã tồn tại. Đây là một chuỗi thao tác cần được quản lý, không phải “cập nhật vị trí trong bảng băm” mà tập tự làm khi trường thay đổi.

### 5.3. Quy tắc nhận diện phải khớp dữ liệu thực tế

Một hệ thống có thể quyết định mã `"TASK-1"` và `"task-1"` là cùng một mã hoặc là hai mã khác nhau. `HashSet<String>` mặc định không tự chọn quy tắc nghiệp vụ không phân biệt hoa thường.

Nếu cần chuẩn hóa, thực hiện theo một quy tắc thống nhất tại ranh giới tạo giá trị. Dùng cùng dạng chuẩn khi thêm, tìm và xóa. Tránh việc chỉ chuẩn hóa ở một phía rồi xem kết quả không tìm thấy là vấn đề hiệu năng.

Không đưa những trường chỉ phục vụ hiển thị vào quy tắc định danh nếu chúng không có ý nghĩa định danh. Ngược lại, không bỏ một trường quan trọng chỉ để giảm chi phí tính băm; điều đó có thể làm hai giá trị cần phân biệt bị xem là một.

## 6. Điều kiện thứ hai: mã băm phải phân bố phù hợp

### 6.1. Đúng hợp đồng chưa đủ để chạy nhanh

Một hàm `hashCode` luôn trả về `7` vẫn đáp ứng yêu cầu “hai đối tượng bằng nhau phải cùng mã băm”. Nhưng mọi đối tượng khác nhau cũng bị đưa tới cùng một vùng băm.

Hàm đó có thể đúng về hợp đồng mã băm nhưng rất kém về phân bố. Đây là hai tiêu chí khác nhau:

| Tiêu chí | Câu hỏi cần trả lời |
| --- | --- |
| Tính đúng | Hai giá trị bằng nhau có cùng mã băm không? |
| Chất lượng phân bố | Các giá trị khác nhau trong dữ liệu thực tế có bị dồn vào quá ít ngăn không? |
| Chi phí tính toán | Tính mã băm và so sánh bằng nhau có đắt không? |
| Tính ổn định | Dữ liệu liên quan có giữ nguyên khi đối tượng đang trong tập không? |

Một công thức có nhiều trường không tự bảo đảm phân bố tốt. Nếu dữ liệu thực tế tập trung vào một vài mẫu mà công thức xử lý kém, vẫn có thể tạo nhiều va chạm.

### 6.2. Tăng capacity không cứu được một hàm băm hằng

Nếu tất cả khóa đều có cùng mã băm, việc tạo thêm nhiều ngăn trống không tự làm các khóa tách đều ra những ngăn đó. Nguyên nhân nằm ở thông tin băm của khóa.

Tài liệu `HashMap`, cấu trúc nền của `HashSet`, cảnh báo rằng nhiều khóa cùng `hashCode` làm giảm hiệu năng. Nó có các cơ chế hỗ trợ xử lý va chạm trong một số trường hợp, nhưng đó không phải lý do để bỏ qua chất lượng băm. [HashMap: va chạm và chi phí tìm kiếm](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

Không mặc định rằng mọi trường hợp nhiều va chạm đều được cứu thành O(1), hoặc rằng mọi `HashSet` trên mọi JDK có cùng một cận O(log n) cho tất cả khóa. Hợp đồng hiệu năng thông thường vẫn gắn với giả định phân bố phù hợp.

Chương trình va chạm ở phần sau dùng khóa có mã băm hằng để chứng minh rằng **tập vẫn cần phân biệt bằng nhau đúng**. Chương trình không đo thời gian và không chứng minh cách băm đó đủ nhanh cho một khối lượng dữ liệu lớn.

### 6.3. Chi phí khóa không biến mất nhờ ký hiệu O(1)

Gọi một thao tác là O(1) theo số phần tử `n` không có nghĩa mọi công việc bên trong đều miễn phí.

Có thể suy nghĩ về một lời gọi theo các thành phần:

```text
chi phí thao tác
    = chi phí tính hashCode của khóa
    + chi phí tìm trong vùng ứng viên
    + chi phí các phép equals cần thiết
    + chi phí thay đổi cấu trúc hoặc cấp phát nếu có
```

Đây là phân rã để phân tích, không phải công thức thời gian chính xác.

Nếu `hashCode` phải duyệt một cấu trúc dài theo độ dài khóa `k`, hoặc `equals` phải so sánh nhiều dữ liệu, độ dài khóa trở thành một yếu tố riêng. Không gộp cả `n` và `k` rồi kết luận thao tác “luôn hằng số”.

Tránh thiết kế `hashCode`/`equals` có công việc không liên quan đến định danh, chẳng hạn truy cập mạng hay đọc tệp. Các phương thức nhận diện nên có ý nghĩa ổn định và chi phí có thể kiểm soát.

## 7. Điều kiện thứ ba: hiểu capacity, load factor và việc tăng dung lượng

### 7.1. Ba đại lượng khác nhau

Trong ngữ cảnh bảng băm:

- `size` là số phần tử đang lưu.
- `capacity` là số ngăn của bảng nền.
- `load factor`, thường gọi là hệ số tải, liên quan tới mức đầy được cho phép trước khi bảng tăng dung lượng.

`size()` không trả về capacity. Tham số truyền vào `new HashSet<>(initialCapacity)` cũng không phải kích thước tối đa mà tập được phép chứa.

Java 17 có các cách tạo phổ biến:

```java
Set<String> defaults = new HashSet<>();
Set<String> withHint = new HashSet<>(1_334);
Set<String> withLoadFactor = new HashSet<>(1_334, 0.75f);
```

Các biến trên đều bắt đầu là tập rỗng. Các con số trong hàm tạo không thêm sẵn bất kỳ phần tử nào.

Hàm tạo mặc định của `HashSet` dùng các tham số khởi tạo mặc định của bảng nền là capacity `16` và load factor `0.75`. Điều này không có nghĩa tập chỉ chứa được 16 phần tử. [Các hàm tạo HashSet trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

### 7.2. Tăng dung lượng làm một số lần thêm tốn nhiều việc hơn

Về mô hình được tài liệu bảng nền mô tả, khi số mục vượt quá tích capacity và load factor, bảng tăng dung lượng và xây dựng lại cấu trúc lưu tương ứng. Vì nhiều phần tử đã có phải được tổ chức lại, một lần thêm gây tăng dung lượng có thể tốn nhiều việc hơn một lần thêm thông thường.

Đó là lý do phân biệt:

- **Kỳ vọng theo phân bố băm:** vùng tìm nhỏ khi các khóa được phân bố phù hợp.
- **Khấu hao qua nhiều lần thêm:** chi phí những lần tăng dung lượng được phân bổ khi phân tích một chuỗi thao tác, thay vì khẳng định mọi lần thêm riêng lẻ đều rẻ như nhau.

Từ “khấu hao” không có nghĩa chương trình trả một khoản thời gian cố định sau mỗi lần thêm, mà là cách phân tích tổng công việc của một chuỗi thao tác. Nếu ứng dụng quan tâm độ trễ của từng yêu cầu riêng, các lần tăng dung lượng vẫn cần được xét.

Ví dụ mô hình với capacity `16` và load factor `0.75` cho ngưỡng liên quan tới `16 × 0.75 = 12`. Đừng biến phép nhân minh họa này thành cách đọc chính xác bộ nhớ hoặc quy luật mọi chi tiết nội bộ của tất cả JDK.

### 7.3. Ước lượng theo số phần tử khác nhau

Nếu biết sẽ giữ khoảng `1_000` phần tử **khác nhau**, có thể dùng ước lượng:

```text
capacity hint ≈ ceil(expectedDistinct / loadFactor)

Với expectedDistinct = 1_000 và loadFactor = 0.75:
    ceil(1_000 / 0.75) = 1_334
```

Vì vậy, trong ví dụ có giới hạn nhỏ, rõ ràng:

```java
int expectedDistinct = 1_000;
int capacityHint = (int) Math.ceil(expectedDistinct / 0.75d);

Set<Integer> values = new HashSet<>(capacityHint, 0.75f);
```

Đây là giá trị gợi ý cho hàm tạo, không phải lời khẳng định rằng bảng thực tế có đúng `1_334` ngăn, cũng không phải cách đo bộ nhớ cấp phát.

Không dùng nguyên phép ép kiểu trên như một hàm tổng quát cho mọi giá trị đầu vào khổng lồ. Với dữ liệu không giới hạn, còn cần xét miền số, giới hạn dung lượng và bộ nhớ thực tế. Trong chương trình minh họa, con số cố định `1_000` đủ nhỏ để phép tính rõ ràng và không có vấn đề tràn phạm vi.

Tập loại trùng, nên số phần tử lưu được quyết định bởi số giá trị khác nhau, không phải tổng số bản ghi đã đi qua. Một triệu bản ghi chỉ có một nghìn mã khác nhau là tình huống khác với một triệu mã khác nhau.

### 7.4. Load factor là sự đánh đổi, không phải nút “càng nhỏ càng nhanh”

Giảm hệ số tải có thể làm bảng thưa hơn nhưng tốn nhiều không gian hơn. Tăng hệ số tải có thể giảm chi phí không gian tương đối nhưng làm tìm kiếm nặng hơn. Giá trị mặc định `0.75` là lựa chọn cân bằng được tài liệu bảng nền mô tả. [HashMap: capacity, load factor và tăng dung lượng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

Không chọn capacity cực lớn chỉ để tránh mọi khả năng tăng dung lượng. Điều đó có thể làm lãng phí bộ nhớ và ảnh hưởng việc duyệt toàn bộ tập. Cũng không chỉnh hệ số tải để bù cho một `hashCode` sai hoặc có phân bố rất kém.

Hãy bắt đầu từ cấu hình thông thường, số phần tử khác nhau dự kiến và kiểu thao tác thực tế. Chỉ thay đổi cấu hình khi đã xác định được lợi ích và chi phí liên quan.

## 8. Chương trình đầy đủ: va chạm băm và gợi ý dung lượng

Lưu mã vào **HashCollisionDemo.java**:

```java
import java.util.HashSet;
import java.util.Set;

public class HashCollisionDemo {
    private record DistributedKey(int id) {
    }

    private static final class CollisionKey {
        private final int id;

        private CollisionKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof CollisionKey key && id == key.id;
        }

        @Override
        public int hashCode() {
            return 7;
        }
    }

    public static void main(String[] args) {
        Set<DistributedKey> distributed = new HashSet<>(128);
        Set<CollisionKey> colliding = new HashSet<>(128);
        for (int id = 0; id < 100; id++) {
            distributed.add(new DistributedKey(id));
            colliding.add(new CollisionKey(id));
        }

        System.out.println("distributed size: " + distributed.size());
        System.out.println("colliding size: " + colliding.size());
        System.out.println("distributed contains 40: "
                + distributed.contains(new DistributedKey(40)));
        System.out.println("colliding contains 40: "
                + colliding.contains(new CollisionKey(40)));
        System.out.println("colliding contains 999: "
                + colliding.contains(new CollisionKey(999)));
        System.out.println("colliding add duplicate: "
                + colliding.add(new CollisionKey(40)));
        System.out.println("colliding remove 40: "
                + colliding.remove(new CollisionKey(40)));
        System.out.println("colliding contains removed: "
                + colliding.contains(new CollisionKey(40)));
        System.out.println("colliding remaining: " + colliding.size());

        int expectedDistinct = 1_000;
        int capacityHint = (int) Math.ceil(expectedDistinct / 0.75d);
        Set<Integer> sized = new HashSet<>(capacityHint, 0.75f);
        for (int value = 0; value < expectedDistinct; value++) {
            sized.add(value);
        }
        System.out.println("capacity hint: " + capacityHint);
        System.out.println("sized count: " + sized.size());
        System.out.println("sized contains 999: " + sized.contains(999));
        System.out.println("sized remove 999: " + sized.remove(999));
        System.out.println("sized final count: " + sized.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashCollisionDemo.java
java HashCollisionDemo
```

Stdout:

```text
distributed size: 100
colliding size: 100
distributed contains 40: true
colliding contains 40: true
colliding contains 999: false
colliding add duplicate: false
colliding remove 40: true
colliding contains removed: false
colliding remaining: 99
capacity hint: 1334
sized count: 1000
sized contains 999: true
sized remove 999: true
sized final count: 999
```

Hai kiểu khóa trong chương trình có cùng ý nghĩa định danh là trường `id`, nhưng chất lượng mã băm khác nhau:

- `DistributedKey` là record chỉ có một thành phần `int`; với dãy mã trong ví dụ, nó cung cấp mã băm theo thành phần.
- `CollisionKey` chủ động trả về cùng số `7` cho mọi mã, dù `equals` vẫn phân biệt các mã khác nhau.

Cả hai tập đều giữ được 100 phần tử. Điều đó chứng minh va chạm không đồng nghĩa với việc các phần tử bị coi là trùng. Tìm khóa có mặt, từ chối thêm trùng, xóa và kiểm tra sau xóa vẫn có ý nghĩa đúng.

**Không có số đo thời gian nào trong stdout.** Không thể dùng việc hai tập có cùng số phần tử và cùng kết quả truy vấn để kết luận chúng có hiệu năng như nhau.

Hai tập đầu được tạo với gợi ý `128`, nhưng chương trình không kiểm tra hoặc khẳng định số lần tăng dung lượng của chúng. Một tham số dung lượng không phải bằng chứng thực nghiệm về mọi chi tiết cấp phát.

Phần cuối tính gợi ý `1_334` cho `1_000` phần tử khác nhau, thêm chúng rồi kiểm tra một giá trị. Số `1_000` được in là `size`; số `1_334` được in là biến đầu vào do chương trình tính. Chúng không phải hai cách đọc cùng một thuộc tính của tập.

Hai chương trình trong bài đã được biên dịch bằng `--release 17` và chạy để đối chiếu đúng stdout. Tùy chọn này kiểm tra mức ngôn ngữ/API và sinh bytecode tương thích Java 17; nó không có nghĩa JVM đang thực thi chính là JDK 17.

## 9. Chọn luồng xử lý để hưởng lợi từ tập băm

### 9.1. Nhiều truy vấn nên dùng lại một tập đã xây dựng

Giả sử có `n` mã hợp lệ và cần kiểm tra `m` mã đầu vào. Nếu với mỗi truy vấn lại quét tuần tự mọi mã hợp lệ, số lần kiểm tra có thể tăng theo `m × n`.

Một phương án là xây dựng tập băm một lần, rồi dùng lại cho các truy vấn:

```java
// Đoạn minh họa; validIds và requests là các tập hợp đầu vào đã có.
Set<String> allowed = new HashSet<>(validIds);

for (String requestId : requests) {
    if (allowed.contains(requestId)) {
        System.out.println("Mã hợp lệ: " + requestId);
    }
}
```

Với giả định mã băm phân bố phù hợp và chi phí khóa được xem là hằng số, việc xây dựng và thực hiện các truy vấn có thể được phân tích theo công việc kỳ vọng gần O(n + m), thay cho một thuật toán quét O(mn).

Nhưng nếu tạo lại `new HashSet<>(validIds)` bên trong mỗi lượt truy vấn, chương trình liên tục trả chi phí xây dựng tập. Lợi ích của cấu trúc dữ liệu có thể bị mất ở cách tổ chức luồng xử lý.

Cũng cần tính tới bộ nhớ bổ sung và thời gian tồn tại của tập. Dùng tập băm cho một truy vấn duy nhất trên một đầu vào rất nhỏ chưa chắc đem lại lợi ích đáng kể. Chọn theo số lần truy vấn và quy mô dữ liệu thực tế.

### 9.2. Tránh lặp lại phép tìm không cần thiết

| Yêu cầu | Cách viết trực tiếp |
| --- | --- |
| Chỉ xử lý lần đầu gặp giá trị | Dùng giá trị trả về của `add` |
| Chỉ xóa nếu có và biết có thay đổi không | Dùng giá trị trả về của `remove` |
| Chỉ cần kiểm tra, không sửa tập | Dùng `contains` |
| Cần lấy đối tượng đang lưu theo khóa | Xem lại mô hình dữ liệu; `contains` không trả đối tượng |

Nếu cần ánh xạ từ một mã tới dữ liệu liên quan, một `Map` có thể biểu đạt nhu cầu phù hợp hơn việc liên tục tìm thủ công trong `Set`. Quyết định đó xuất phát từ yêu cầu truy cập dữ liệu, không phải chỉ từ tên cấu trúc.

### 9.3. Tránh giữ tập tăng mãi ngoài yêu cầu

Một tập “đã thấy” cần có phạm vi rõ ràng: trong một lô dữ liệu, một phiên xử lý hay toàn bộ tiến trình.

Nếu bài toán chỉ cần loại trùng trong một lô nhưng tập được giữ qua vô hạn lô, số phần tử khác nhau và bộ nhớ tiếp tục tăng. Khi đó, vấn đề không chỉ là chọn capacity ban đầu. Cần xác định lúc nào dữ liệu hết hiệu lực và được loại bỏ theo đúng yêu cầu.

Không tự xóa tùy ý chỉ để giảm bộ nhớ nếu việc xóa làm mất ý nghĩa “đã xử lý”. Vòng đời dữ liệu là một phần của thiết kế bài toán.

## 10. Chi phí duyệt toàn bộ khác với chi phí tìm một phần tử

`contains(x)` tận dụng băm để thu hẹp vùng tìm. Một vòng `for-each` đi qua toàn bộ tập không có cùng mô hình công việc.

Với `HashSet`, tài liệu mô tả thời gian duyệt tỷ lệ với tổng **size + capacity** của bảng nền. Vì vậy, một tập rất thưa có thể làm việc duyệt kém hiệu quả hơn dự đoán chỉ từ `size()`. [HashSet: chi phí iteration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

Điều này giải thích vì sao cấp capacity quá lớn hoặc chọn load factor quá thấp có thể không phù hợp khi chương trình thường xuyên duyệt toàn bộ tập.

Nếu yêu cầu cần giữ thứ tự chèn và duyệt nhiều, `LinkedHashSet` là một lựa chọn cần cân nhắc: nó giữ liên kết phục vụ thứ tự duyệt, có chi phí bộ nhớ riêng, và việc duyệt tỷ lệ với số phần tử thay vì capacity theo mô tả của lớp. Nó vẫn dựa vào băm cho các thao tác thành viên và vẫn cần quy tắc `equals`/`hashCode` phù hợp. [LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

Không thay cấu trúc chỉ để làm output của một ví dụ “đẹp hơn” rồi suy ra đó là lựa chọn nhanh nhất cho mọi tải công việc. Cần biết chương trình chủ yếu tìm thành viên, thêm/xóa hay duyệt toàn bộ.

Khi cần xóa trong lúc duyệt một `HashSet`, dùng cơ chế được hỗ trợ như `Iterator.remove` hoặc một thao tác lọc phù hợp. Không vừa `for-each` vừa tự gọi `set.remove` rồi dựa vào việc “lần này không có ngoại lệ”. Điều này liên quan đến tính đúng của quá trình duyệt, không phải tối ưu băm.

## 11. Kiểm chứng tính đúng và đánh giá hiệu năng là hai việc khác nhau

Các chương trình trong bài kiểm chứng được các hành vi như thêm trùng, tìm theo khóa bằng nhau, xóa và xử lý va chạm. Chúng không phải phép đo hiệu năng.

Một phép đo có ý nghĩa cần xác định câu hỏi cụ thể, chẳng hạn:

- `contains` với khóa có mặt khác với khóa vắng mặt ra sao?
- `add` phần tử mới khác với `add` giá trị đã tồn tại ra sao?
- Khi phần tử tăng từ một nghìn lên nhiều hơn, chi phí thay đổi thế nào?
- Tải chủ yếu tra cứu hay thường xuyên gây tăng dung lượng?
- Mã băm của dữ liệu đại diện có phân bố phù hợp không?
- Độ dài và cấu trúc của khóa có thay đổi theo quy mô không?

Không đo thời gian bằng cách đặt `println` trong phần đang muốn so sánh rồi xem đó là thời gian của riêng `contains`. Công việc in output cũng trở thành một phần của phép đo.

Cũng cần tránh việc đo `add` lặp đi lặp lại cùng một giá trị nhưng lại mô tả kết quả như chi phí thêm nhiều phần tử mới. Sau lần đầu, tải công việc đã đổi thành thử thêm trùng. Với `remove`, nếu không chuẩn bị lại dữ liệu, sau một lần xóa các lần tiếp theo có thể chỉ là xóa giá trị vắng mặt.

Khi cần một phép đo nhỏ có kiểm soát trên JVM, có thể dùng [OpenJDK JMH](https://github.com/openjdk/jmh) và đọc các mẫu đi kèm. Công cụ hỗ trợ xây dựng, chạy và phân tích phép đo; vẫn phải thiết kế dữ liệu và thao tác đúng với câu hỏi cần trả lời.

Một bản mô tả kết quả nên nêu tối thiểu phiên bản JDK, cấu hình tập, quy mô và dạng dữ liệu, kiểu thao tác, tỷ lệ tìm thấy/không tìm thấy và cách tách chuẩn bị dữ liệu khỏi thao tác được đo. Không biến một con số trên một máy thành thời gian được bảo đảm bởi API.

## 12. Những lỗi thường gặp khi mong đợi HashSet chạy nhanh

| Hiện tượng hoặc giả định | Điểm cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Tìm/xóa bằng một đối tượng bằng giá trị nhưng không ra kết quả như dự kiến | equals/hashCode có đúng và nhất quán không? | Sửa hợp đồng nhận diện trước |
| Sửa trường mã rồi không tìm lại được ổn định | Khóa có thay đổi khi đang trong tập không? | Dùng định danh bất biến hoặc quy trình cập nhật rõ |
| Tập có nhiều khóa nhưng mọi hashCode như nhau | Phân bố băm kém | Thiết kế mã băm phù hợp với dữ liệu |
| Tăng capacity rất nhiều mà va chạm vẫn tập trung | Có phải hashCode hằng hoặc quá ít giá trị không? | Không dùng capacity để che lỗi phân bố |
| Một số lần add chậm hơn nhiều | Có tăng dung lượng hoặc cấp phát không? | Xem cấu hình và đặc điểm tải, phân biệt từng lần với khấu hao |
| Nghĩ new HashSet(1000) chỉ chứa được 1000 phần tử | Nhầm gợi ý dung lượng với giới hạn số phần tử | Tách size, capacity và ngưỡng tăng |
| Tập ít phần tử nhưng duyệt tốn việc | Capacity có quá lớn so với size không? | Cân nhắc cấu hình và mô hình duyệt |
| Luôn contains trước add/remove | Đang lặp lại việc tìm kiếm | Dùng cờ kết quả của thao tác sửa đổi |
| Thấy stdout cùng thứ tự nên cho rằng HashSet giữ thứ tự chèn | Phụ thuộc một quan sát không được bảo đảm | Chọn cấu trúc có hợp đồng thứ tự khi cần |
| Một phép đo rất nhanh nên kết luận mọi thao tác đều O(1) | Có đo đúng thao tác và dữ liệu đại diện không? | Tách tính đúng, phép đo và phân tích độ phức tạp |
| Đã dùng add trực tiếp nên tưởng an toàn khi nhiều luồng cùng sửa | Nhầm ít lời gọi với cơ chế đồng bộ | Thiết kế truy cập đồng thời phù hợp |

Nếu hiệu năng không như mong đợi, trước tiên hãy xác nhận dữ liệu đang đúng. Sau đó mới kiểm tra phân bố băm, chi phí khóa, tăng dung lượng, số lần xây dựng tập và kiểu thao tác thực tế. Chỉnh một tham số mà chưa biết công việc nào đang tốn thời gian thường không giải quyết được nguyên nhân.

## 13. Tự luyện và đối chiếu

### Bài 1: theo dõi kết quả và kích thước

Với một `HashSet<String>` mới tạo, thực hiện:

```java
set.add("a");
set.add(new String("a"));
set.contains("a");
set.remove("a");
set.remove("a");
```

Đối chiếu:

| Thao tác | Kết quả | size sau thao tác |
| --- | --- | --- |
| `add("a")` | `true` | 1 |
| `add(new String("a"))` | `false` | 1 |
| `contains("a")` | `true` | 1 |
| `remove("a")` | `true` | 0 |
| `remove("a")` | `false` | 0 |

Cần giải thích vì sao một lần `new` không tạo phần tử mới trong tập khi hai chuỗi bằng nhau theo giá trị.

### Bài 2: tính đúng hay chất lượng băm?

Một lớp khóa có `equals` đúng theo mã và `hashCode` luôn trả `0`.

1. Nó có nhất thiết vi phạm điều kiện “bằng nhau phải cùng mã băm” không?
2. Những khóa khác nhau có bắt buộc bị loại trùng không?
3. Có thể dựa vào hàm băm đó để mong đợi phân bố tốt không?
4. Tăng initial capacity có tự sửa được việc mọi khóa cùng mã băm không?

Đối chiếu: không nhất thiết vi phạm điều kiện đó; các khóa khác nhau vẫn được phân biệt bằng `equals`; phân bố rất kém; tăng capacity không tự tạo thêm thông tin phân biệt trong mã băm.

### Bài 3: ước lượng dung lượng

Dự kiến giữ `750` phần tử khác nhau với load factor `0.75`. Theo phép ước lượng trong bài, giá trị gợi ý là:

```text
ceil(750 / 0.75) = 1_000
```

Hãy nêu hai điều không thể kết luận từ con số đó.

Gợi ý: không thể nói tập đã có 1.000 phần tử, và cũng không thể nói bảng thực tế chắc chắn có đúng 1.000 ngăn. Đây là đầu vào cấu hình, không phải kết quả quan sát cấu trúc nội bộ.

Nếu có 50.000 bản ghi nhưng chỉ 750 mã khác nhau, hãy giải thích vì sao số giá trị khác nhau mới liên quan trực tiếp đến số phần tử mà tập giữ.

### Bài 4: sửa một phép đo sai câu hỏi

Một vòng lặp gọi một triệu lần `set.add("java")` rồi báo “đã đo thêm một triệu phần tử”.

Điểm sai: nếu tập ban đầu chưa có chuỗi đó, chỉ lần đầu là thêm phần tử mới. Các lần còn lại thử thêm giá trị đã có.

Muốn đo thêm mới, cần chuẩn bị dữ liệu có các giá trị khác nhau và kiểm soát trạng thái tập cho mỗi phép đo. Muốn đo thêm trùng, có thể dùng dữ liệu đã có nhưng phải mô tả đúng tải công việc đó. Việc chuẩn bị dữ liệu, tăng dung lượng và công việc đo phải được phân biệt theo câu hỏi cần trả lời.

## 14. Tài liệu tra cứu

- [HashSet Java 17 — thao tác, hiệu năng, thứ tự, null và hàm tạo](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
- [HashMap Java 17 — cấu trúc nền, capacity, load factor và va chạm](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)
- [Object — hợp đồng equals/hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
- [Set — giới hạn khi phần tử thay đổi phép bằng nhau](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)
- [LinkedHashSet — đánh đổi về thứ tự và chi phí duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)
- [OpenJDK JMH — công cụ xây dựng phép đo trên JVM](https://github.com/openjdk/jmh)
