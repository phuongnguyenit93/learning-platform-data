# Thứ tự duyệt và quy tắc null của EnumSet

## 1. EnumSet giữ thành viên theo một kiểu enum có thứ tự tự nhiên

`EnumSet<E>` là tập chuyên dùng cho các hằng của một kiểu enum. Nó không giữ lịch sử thêm phần tử như một danh sách; các phần tử được duyệt theo **thứ tự khai báo hằng trong kiểu enum**.

Ví dụ:

```java
enum Stage {
    QUEUED, PROCESSING, DONE, FAILED
}
```

Dù thêm `FAILED` trước rồi mới thêm `QUEUED`, một tập chứa hai hằng đó vẫn duyệt `QUEUED` trước `FAILED`. Nó cũng không tự sắp theo bảng chữ cái, tên hiển thị hay mức ưu tiên của nghiệp vụ.

Quy tắc thứ tự được công bố trong hợp đồng [EnumSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html), không chỉ là kết quả tình cờ của một lần chạy. Các ví dụ trong bài dùng cú pháp Java hiện hành và chạy bằng JDK 17 trở lên.

## 2. Thứ tự thêm, thứ tự khai báo và thứ tự tên khác nhau

```java
EnumSet<Stage> stages = EnumSet.noneOf(Stage.class);
stages.add(Stage.FAILED);
stages.add(Stage.QUEUED);
stages.add(Stage.DONE);
```

Đoạn lệnh này đặt trong một phương thức và cần `import java.util.EnumSet;`. Ba thứ tự có thể được phân biệt:

| Cách nhìn | Thứ tự tương ứng |
| --- | --- |
| Lịch sử thêm trong mã trên | `FAILED, QUEUED, DONE` |
| Duyệt EnumSet theo khai báo | `QUEUED, DONE, FAILED` |
| Sắp theo tên chữ cái của các hằng đang có | `DONE, FAILED, QUEUED` |

Hằng `PROCESSING` không có trong tập nên không được trả về, dù nằm giữa các hằng khác trong khai báo enum.

`for-each` dùng iterator của tập, nên trong một lần duyệt không có sửa đổi đồng thời, nó quan sát thứ tự khai báo của những phần tử đang có. Việc in tập bằng `toString()` cũng đi theo thứ tự duyệt của tập trong ví dụ.

Xóa `QUEUED` rồi thêm lại không đưa nó xuống cuối như thể có lịch sử chèn. Khi nằm trong tập, vị trí duyệt của nó vẫn theo khai báo enum. Thêm một hằng đã có cũng không tạo phần tử trùng vì `EnumSet` là tập.

## 3. Muốn một thứ tự khác thì tạo biểu diễn phù hợp

`EnumSet` không nhận một `Comparator` để đổi thứ tự duyệt của chính nó. Nếu cần trình bày theo tên, mức ưu tiên hoặc một thứ tự cấu hình riêng, có thể giữ `EnumSet` cho việc kiểm tra thành viên rồi tạo một danh sách trình bày:

```java
List<Stage> ordered = new ArrayList<>(stages);
ordered.sort(Comparator.comparing(Stage::name));
```

Đoạn này cần các import `List`, `ArrayList`, `Comparator`. Nó tạo và sắp xếp một danh sách riêng; không làm thứ tự tự nhiên của enum hoặc cách duyệt `EnumSet` thay đổi.

Nếu thứ tự là ưu tiên nghiệp vụ, dùng thông tin ưu tiên được thiết kế rõ thay vì coi “hằng khai báo trước” mặc nhiên ưu tiên cao. Đổi thứ tự khai báo sẽ đổi thứ tự tự nhiên, nên cần xem tác động khi dữ liệu hiển thị hoặc kiểm thử đang dựa vào nó.

Thứ tự ổn định trong một phiên bản cũng không biến `ordinal()` thành mã trao đổi bền vững. Vị trí khai báo, nhãn hiển thị và định danh dữ liệu là những hợp đồng khác nhau.

Tự nhiên của enum liên hệ với thứ tự khai báo theo hợp đồng [Enum.compareTo](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#compareTo(E)).

## 4. EnumSet không chứa phần tử null

Một tập enum chỉ giữ những hằng thực sự của kiểu enum đó. `null` không phải một hằng enum và không được lưu làm phần tử.

Phân biệt ba trạng thái:

| Trạng thái | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tập rỗng hợp lệ | `EnumSet.noneOf(Stage.class)` | Có đối tượng tập, biết kiểu Stage, không có thành viên |
| Biến tham chiếu rỗng | `EnumSet<Stage> stages = null` | Chưa có đối tượng tập để gọi thao tác |
| Tập chứa phần tử null | Thử `stages.add(null)` | Không hợp lệ với EnumSet |

Không dùng `null` để đại diện “không chọn hằng nào” bên trong tập. Nếu ý nghĩa là không chọn phần tử, một `EnumSet` rỗng thường đã biểu diễn đúng.

Nếu nghiệp vụ có một trạng thái `UNKNOWN` thực sự, có thể định nghĩa nó thành một hằng enum theo thiết kế. Hằng đó không đồng nghĩa `null`: nó có tên, vị trí khai báo và tham gia những thao tác như `allOf` hoặc `complementOf` như mọi hằng khác.

## 5. Thêm null bị từ chối, kiểm tra hoặc xóa null không gây lỗi

| Thao tác trên một EnumSet hợp lệ | Kết quả liên quan null |
| --- | --- |
| `set.add(null)` | Ném `NullPointerException` |
| `EnumSet.of((Stage) null)` | Ném `NullPointerException` |
| `set.contains(null)` | `false` vì tập không chứa null |
| `set.remove(null)` | `false`, tập không thay đổi |
| Gọi thao tác trên biến set đang bằng null | Gây `NullPointerException` do không có đối tượng nhận lời gọi |

Đây là hai nhóm hợp đồng khác nhau. Thêm phần tử cần bảo đảm phần tử hợp lệ để lưu, nên `null` bị từ chối. Kiểm tra hoặc yêu cầu xóa một giá trị không tồn tại không cần biến giá trị đó thành thành viên hợp lệ.

Vì thế không suy từ việc `contains(null)` không lỗi rằng `add(null)` cũng hợp lệ; cũng không cần tự ném lỗi trước mọi lời gọi `contains` chỉ vì đối số có thể bằng `null`.

Quy tắc chèn, kiểm tra và xóa null được nêu rõ trong tài liệu [EnumSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html).

### Nguồn collection có null

Nếu xây tập từ một collection chứa `null`, không thể dùng `EnumSet` để giữ nguyên phần tử ấy. Cần một chính sách dữ liệu: từ chối, hoặc lọc nếu việc bỏ phần tử thiếu thật sự là yêu cầu được thiết kế.

Không mặc định việc gặp ngoại lệ ở giữa một thao tác thêm nhiều phần tử sẽ hoàn tác mọi cập nhật đã thực hiện. Nếu cần chỉ công bố kết quả khi toàn bộ nguồn hợp lệ, hãy dựng một tập tạm, xác thực và chỉ thay thế kết quả hiện hành sau khi dựng thành công.

Một tập tạm thất bại không làm thay đổi tập hiện hành nếu trước đó ta chưa gán hoặc chia sẻ nó ra ngoài. Đây là cách tổ chức cập nhật ở tầng ứng dụng, không phải giao dịch rollback tự động của `EnumSet`.

## 6. Chương trình chạy đầy đủ

Lưu thành `EnumSetOrderNullDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;

public class EnumSetOrderNullDemo {
    enum Stage {
        QUEUED, PROCESSING, DONE, FAILED
    }

    static EnumSet<Stage> checkedCopy(Collection<Stage> source) {
        Objects.requireNonNull(source, "source");
        EnumSet<Stage> result = EnumSet.noneOf(Stage.class);
        for (Stage stage : source) {
            result.add(Objects.requireNonNull(stage, "stage"));
        }
        return result;
    }

    public static void main(String[] args) {
        EnumSet<Stage> stages = EnumSet.noneOf(Stage.class);
        stages.add(Stage.FAILED);
        stages.add(Stage.QUEUED);
        stages.add(Stage.DONE);
        System.out.println("stored order=" + stages);

        List<Stage> visited = new ArrayList<>();
        for (Stage stage : stages) {
            visited.add(stage);
        }
        System.out.println("for-each order=" + visited);

        stages.remove(Stage.QUEUED);
        stages.add(Stage.QUEUED);
        System.out.println("after re-add=" + stages);

        List<Stage> alphabetical = new ArrayList<>(stages);
        alphabetical.sort(Comparator.comparing(Stage::name));
        System.out.println("alphabetical copy=" + alphabetical);
        System.out.println("enum set unchanged=" + stages);

        System.out.println("contains null=" + stages.contains(null));
        System.out.println("remove null=" + stages.remove(null));
        try {
            stages.add(null);
        } catch (NullPointerException expected) {
            System.out.println("add null=rejected");
        }

        try {
            EnumSet.of((Stage) null);
        } catch (NullPointerException expected) {
            System.out.println("factory null=rejected");
        }

        Collection<Stage> invalidInput = Arrays.asList(Stage.PROCESSING, null);
        try {
            EnumSet<Stage> replacement = checkedCopy(invalidInput);
            stages = replacement;
        } catch (NullPointerException expected) {
            System.out.println("invalid input=rejected before replacement");
        }
        System.out.println("current set=" + stages);
        System.out.println("empty set size=" + EnumSet.noneOf(Stage.class).size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror EnumSetOrderNullDemo.java
java EnumSetOrderNullDemo
```

Stdout:

```text
stored order=[QUEUED, DONE, FAILED]
for-each order=[QUEUED, DONE, FAILED]
after re-add=[QUEUED, DONE, FAILED]
alphabetical copy=[DONE, FAILED, QUEUED]
enum set unchanged=[QUEUED, DONE, FAILED]
contains null=false
remove null=false
add null=rejected
factory null=rejected
invalid input=rejected before replacement
current set=[QUEUED, DONE, FAILED]
empty set size=0
```

Thứ tự thêm không quyết định thứ tự duyệt. Việc tạo danh sách sắp theo tên không đổi tập gốc. Hai phép truy vấn/xóa `null` trả `false`, còn thêm hoặc tạo từ một hằng `null` bị từ chối.

`checkedCopy` xác thực nguồn và từng phần tử bằng `Objects.requireNonNull`, dựng tập tạm rồi mới trả về. Vì đầu vào mẫu có `null`, phép gán thay tập hiện hành chưa diễn ra; tập hiện hành giữ nguyên.

Khối `catch` trong ví dụ dùng để quan sát các hợp đồng. Trong ứng dụng, cần chọn cách báo lỗi đầu vào phù hợp tại biên nhận dữ liệu, không âm thầm coi một tập thất bại là một tập hợp lệ khác.

## 7. Duyệt khi tập đang bị sửa: biết giới hạn của iterator

Iterator của `EnumSet` được mô tả là **nhất quán yếu** (weakly consistent): nó không ném `ConcurrentModificationException` và có thể phản ánh hoặc không phản ánh các thay đổi xảy ra trong lúc duyệt.

Điều đó không có nghĩa iterator luôn giữ một ảnh chụp cố định, cũng không có nghĩa mọi phần tử thêm mới chắc chắn sẽ được duyệt. Nếu thuật toán yêu cầu một tập thành viên xác định tại thời điểm bắt đầu, cần tổ chức ảnh chụp và giao thức truy cập phù hợp thay vì suy đoán từ một lần thử.

Đặc biệt, không thấy `ConcurrentModificationException` không chứng minh an toàn luồng. `EnumSet` không tự đồng bộ hóa; nếu nhiều luồng cùng truy cập và có luồng sửa, phải tuân thủ cơ chế bảo vệ được thiết kế cho dữ liệu đó.

Vì hợp đồng khi có cập nhật cho phép nhiều mức quan sát, bài này không khẳng định một stdout cố định cho một vòng duyệt đang thêm/xóa thành viên. Ví dụ chạy giữ tập không đổi trong chính vòng duyệt để kiểm tra rõ thứ tự tự nhiên.

## 8. Các lỗi suy luận thường gặp

### “Nó được thêm cuối nên phải được duyệt cuối”

Không đúng với EnumSet. Nếu cần giữ thứ tự thao tác thêm, hãy dùng một cấu trúc hoặc một mô hình dữ liệu phục vụ yêu cầu đó, không cố biến lịch sử thêm thành thứ tự tự nhiên của enum.

### “Set thì không được dựa vào bất kỳ thứ tự nào”

Phải đọc hợp đồng loại Set cụ thể. `EnumSet` có thứ tự duyệt được quy định. Tuy vậy, công bố một giá trị dưới kiểu `Set<E>` không tự chuyển các bảo đảm của EnumSet sang mọi kiểu Set khác có thể được trả về trong tương lai.

Nếu thứ tự là một phần của API, cần diễn đạt hợp đồng đó rõ và kiểm tra cách tạo giá trị thực tế.

### “null sẽ được xếp đầu hoặc cuối”

`EnumSet` không có bước sắp vị trí cho một phần tử `null` vì nó không cho lưu phần tử ấy. Những comparator có chính sách cho `null` ở cấu trúc khác không thay đổi hợp đồng của EnumSet.

### “Một tập rỗng cũng giống một biến tập null”

Tập rỗng là một giá trị có thể duyệt, hỏi kích thước, thêm thành viên hợp lệ và mang thông tin kiểu enum. Biến `null` không có đối tượng để thực hiện những việc đó. Đổi hai trạng thái cho nhau tùy tiện có thể làm API khó sử dụng hoặc gây lỗi.

### “Không có CME nên có thể sửa từ nhiều luồng”

Không đúng. Chính sách iterator và giao thức an toàn luồng là hai khía cạnh riêng. Cần giữ rõ yêu cầu dữ liệu nào được nhìn thấy trong một lần duyệt và ai được quyền thay đổi nó trong thời gian đó.

## 9. Những điểm nên kiểm tra ở API sử dụng EnumSet

- Thứ tự đầu ra mong muốn có thật sự là thứ tự khai báo enum hay cần một thứ tự trình bày khác?
- Đổi thứ tự hoặc thêm hằng enum có làm thay đổi một hợp đồng hiển thị/kiểm thử đang được công bố không?
- “Không có phần tử” được biểu diễn bằng tập rỗng hay một trạng thái thiếu dữ liệu riêng có chủ đích?
- Đầu vào có `null` bị từ chối hay được lọc theo một quy tắc rõ?
- Nếu phải dựng lại toàn bộ tập, kết quả mới chỉ được công bố sau khi kiểm tra thành công hay đang sửa dần tập hiện hành?
- Có cập nhật trong lúc duyệt hoặc nhiều luồng truy cập khiến yêu cầu quan sát phải được thiết kế riêng không?

Các câu hỏi này giúp áp dụng đúng thứ tự và chính sách null, không thay thế việc đọc hợp đồng nghiệp vụ của tập đang dùng.

## 10. Tự kiểm tra

1. Thêm FAILED trước rồi QUEUED có làm FAILED được duyệt trước trong enum của bài không?
2. Xóa một hằng rồi thêm lại có đưa nó xuống cuối EnumSet không?
3. `contains(null)` và `add(null)` có cùng kết quả xử lý không?
4. `EnumSet.noneOf(Stage.class)` khác gì một biến `EnumSet<Stage>` bằng null?
5. Iterator không ném ConcurrentModificationException có phải là ảnh chụp bất biến hay an toàn luồng không?

Đáp án:

1. Không. QUEUED đứng trước trong khai báo enum nên được duyệt trước khi cả hai đều có trong tập.
2. Không. Khi có mặt, nó vẫn theo thứ tự khai báo.
3. Không. Kiểm tra trả false; thêm bị từ chối bằng NullPointerException.
4. Một bên là đối tượng tập rỗng hợp lệ có kiểu phần tử; một bên không có đối tượng tập.
5. Không. Iterator nhất quán yếu và EnumSet không tự đồng bộ hóa.

Hãy đọc thứ tự duyệt từ khai báo enum và đọc chính sách null theo từng thao tác. Hai hợp đồng rõ ràng này giúp tránh nhầm một tập enum với danh sách lịch sử chèn hoặc một vùng chứa cho cả giá trị thiếu.
