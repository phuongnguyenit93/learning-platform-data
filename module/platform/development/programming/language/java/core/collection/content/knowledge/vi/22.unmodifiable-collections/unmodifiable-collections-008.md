# Bảo vệ dữ liệu khi nhận tham số hoặc trả về collection từ API

## 1. Collection đi qua API mang theo cả quyền sửa

Một lớp có danh sách thành viên và yêu cầu danh sách luôn có ít nhất một người. Hàm khởi tạo kiểm tra đầu vào không rỗng rồi lưu List nhận được. Vài dòng sau, bên gọi xóa List bằng biến họ vẫn giữ. Danh sách bên trong lớp cũng rỗng, dù không có phương thức xóa thành viên nào của lớp được gọi.

Vấn đề nằm ở tham chiếu dùng chung. Trong Java, truyền một biến tham chiếu vào phương thức tạo ra một bản sao của **giá trị tham chiếu**, không tự tạo bản sao đối tượng mà nó trỏ đến. Hai biến có thể cùng dẫn đến một List. Tương tự, trả về tham chiếu đến List nội bộ có thể cho người nhận một đường sửa trạng thái của đối tượng.

API trong bài là bề mặt lớp và phương thức mà các thành phần Java dùng để làm việc với nhau. Khi một collection đi qua bề mặt ấy, hợp đồng cần trả lời:

- Phương thức chỉ đọc dữ liệu trong lúc chạy hay giữ nó để dùng về sau?
- Bên nhận được sửa collection hay chỉ đọc?
- Thay đổi ở một bên có xuất hiện ở bên kia không?
- Phần tử bên trong là dữ liệu bất biến hay đối tượng còn có thể sửa?

**Bảo vệ dữ liệu** ở đây là duy trì những quy tắc mà chủ sở hữu đã cam kết, đồng thời cấp đúng quyền truy cập cho bên sử dụng. Một collection chỉ đọc giải quyết quyền sửa phần chứa; một bản sao giải quyết một mức phụ thuộc tham chiếu; đối tượng phần tử có thể cần một quyết định riêng.

Bài học bắt đầu bằng một trường hợp lộ tham chiếu, xây dựng cách tiếp nhận an toàn, rồi so sánh ba chính sách trả về. Sau đó mới xử lý đối tượng phần tử và collection lồng nhau. Mục tiêu là chọn hợp đồng phù hợp và kiểm chứng nó, thay vì thêm lớp bọc vào mọi chỗ mà không biết đang bảo vệ điều gì.

Kiến thức cần có là tham chiếu đối tượng, trường `private final`, thao tác List/Set/Map và ngoại lệ cơ bản. Tất cả chương trình dưới đây độc lập, chạy bằng Java 17; lưu mỗi chương trình theo đúng tên tệp được ghi trước mã.

## 2. Ba khái niệm giúp đọc đúng ranh giới dữ liệu

### 2.1. Nhiều đường dẫn đến cùng một đối tượng

Tình trạng nhiều tham chiếu cùng trỏ đến một đối tượng thường gọi là dùng chung tham chiếu (aliasing). Nếu đối tượng đó cho phép sửa, một đường dẫn có thể sửa dữ liệu mà đường khác đang quan sát.

Biến tham số là biến riêng của phương thức, nhưng đối tượng nhận được chưa chắc là đối tượng riêng. Gán lại biến tham số không gán lại biến bên gọi; gọi `clear` trên đối tượng List qua biến tham số vẫn tác động lên List dùng chung.

Một trường `private` ngăn mã bên ngoài truy cập trực tiếp trường bằng tên. Nó không thu hồi những tham chiếu đến đối tượng mà bên ngoài đã có. Một trường `final` không cho gán lại tham chiếu trường sau khi khởi tạo theo quy tắc ngôn ngữ. Nó không cấm các phương thức sửa trên đối tượng được tham chiếu.

### 2.2. Quy tắc luôn đúng của đối tượng

Điều kiện như “danh sách thành viên không rỗng” là một bất biến của đối tượng (invariant): điều lớp muốn giữ đúng ở các thời điểm quan sát hợp lệ. Nếu getter cho phép người nhận gọi `clear` lên List thật, người nhận có thể phá điều kiện đó mà không đi qua logic của lớp.

Vì thế, bảo vệ collection liên quan trực tiếp đến tính đóng gói. Đặt trường là private chỉ là bước kiểm soát đường truy cập; thiết kế tham số, kết quả và phần tử mới quyết định có còn đường sửa trạng thái ngoài ý muốn hay không.

### 2.3. Ba mức độc lập

| Mức cần xét | Câu hỏi kiểm tra | Ví dụ |
| --- | --- | --- |
| Phần chứa | Bên ngoài còn thêm/xóa/thay phần tử hoặc ánh xạ nội bộ được không? | Getter trả thẳng ArrayList nội bộ |
| Quan hệ với nguồn | Nguồn thay đổi thì kết quả đã nhận có đổi theo không? | View chỉ đọc so với ảnh chụp |
| Trạng thái phần tử | Đối tượng được lấy ra có còn sửa trạng thái chung được không? | List chỉ đọc chứa đối tượng có setter |

Một giải pháp có thể đáp ứng mức này mà chưa đáp ứng mức khác. Nói rõ mức cần bảo vệ giúp tránh cả thiếu bảo vệ lẫn sao chép không cần thiết.

## 3. Thí nghiệm lộ tham chiếu ở cả đầu vào và đầu ra

Chương trình này cố ý giữ một thiết kế sai với yêu cầu “không rỗng”. Lưu thành `UnsafeReferenceDemo.java` để quan sát nguyên nhân, không dùng lớp Roster này làm mẫu thiết kế.

```java
import java.util.ArrayList;
import java.util.List;

public class UnsafeReferenceDemo {
    static final class Roster {
        private final List<String> members;

        Roster(List<String> input) {
            if (input.isEmpty()) {
                throw new IllegalArgumentException("At least one member");
            }
            members = input;
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("An", "Binh"));
        Roster roster = new Roster(input);
        System.out.println("initial=" + roster.members());

        input.clear();
        System.out.println("afterInputClear=" + roster.members());

        roster.members().add("Injected");
        System.out.println("inputAfterGetterAdd=" + input);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 UnsafeReferenceDemo.java
java UnsafeReferenceDemo
```

Stdout:

```text
initial=[An, Binh]
afterInputClear=[]
inputAfterGetterAdd=[Injected]
```

Lúc khởi tạo, đầu vào hợp lệ và getter hiện hai thành viên. Sau `input.clear()`, lớp không được hỏi ý kiến nhưng dữ liệu nội bộ đã thành rỗng. Điều kiện được kiểm tra ở hàm khởi tạo không còn đúng vì lớp tiếp tục phụ thuộc vào List thuộc quyền sửa của bên gọi.

Sau đó `roster.members().add("Injected")` đi theo chiều ngược lại. Getter trả tham chiếu đến cùng List, nên thao tác thêm qua kết quả cũng xuất hiện ở biến `input`. Cả hai chiều cùng có nguyên nhân là không thiết lập ranh giới quyền sở hữu.

Từ khóa `final` trong chương trình không hề bị vi phạm. Trường `members` vẫn trỏ đến đúng List ban đầu; chỉ nội dung List thay đổi. Đây là lý do cần kiểm tra hành vi thật thay vì nhìn khai báo trường rồi kết luận đối tượng bất biến.

Chỉ sửa getter thành một lớp bọc chỉ đọc vẫn chưa xử lý đường `input.clear()`. Chỉ sao chép đầu vào thành một ArrayList riêng nhưng tiếp tục trả thẳng ArrayList đó cũng chưa xử lý đường sửa qua getter. Phải xem cả hai ranh giới.

## 4. Tiếp nhận tham số: giữ dữ liệu mình đã kiểm tra

Nếu lớp cần giữ một danh sách độc lập để dùng lâu dài, một quy trình rõ ràng là:

1. Tạo dữ liệu riêng ở mức cần bảo vệ.
2. Kiểm tra các điều kiện nghiệp vụ trên chính dữ liệu sẽ giữ.
3. Chỉ gán trường khi quá trình chuẩn bị và kiểm tra đã thành công.
4. Cung cấp đầu ra không mở lại đường sửa ngoài hợp đồng.

Với List tên String, `List.copyOf(input)` phù hợp cho bước đầu vì kết quả không hỗ trợ sửa phần chứa và không đi theo việc đầu vào thêm/xóa/thay tham chiếu phần tử về sau. String là bất biến nên việc dùng chung các String không mở thêm quyền sửa tên.

Kiểm tra trên bản đã chụp giúp tránh mô hình “kiểm tra đối tượng bên ngoài, rồi giữ một dữ liệu có thể khác dữ liệu đã kiểm tra”. Tuy nhiên, việc chụp không tự khóa nguồn đang được một luồng khác sửa. Hợp đồng tiếp nhận vẫn cần quy tắc phối hợp nếu việc sửa đồng thời có thể xảy ra.

Đây là nguyên tắc thiết kế ranh giới, không phải yêu cầu luôn sao chép mọi tham số. Một phương thức chỉ tính toán trong thời gian gọi có thể không cần giữ bản sao khi hợp đồng cho phép đọc trực tiếp. Một thao tác được thiết kế để sửa List do bên gọi đưa vào cũng có thể hợp lệ, miễn hành vi ấy được công bố. Cần sao chép khi mức phụ thuộc và quyền sửa của dữ liệu đầu vào không đáp ứng yêu cầu của đối tượng nhận.

Hướng dẫn của Oracle phân biệt rõ việc sao chép dữ liệu có thể sửa ở đầu vào và đầu ra, đồng thời nhấn mạnh sử dụng bản đã bảo vệ cho logic kiểm tra: [Secure Coding Guidelines, mục 6 về khả năng thay đổi dữ liệu](https://www.oracle.com/java/technologies/javase/seccodeguide.html#6).

## 5. Thí nghiệm nhận List tên và công bố kết quả chỉ đọc

Lưu thành `DefensiveRosterDemo.java`. Lớp này công bố chính sách: danh sách không null, không chứa null, có ít nhất một tên, tên không toàn khoảng trắng; thứ tự và số lần xuất hiện được giữ như đầu vào.

```java
import java.util.ArrayList;
import java.util.List;

public class DefensiveRosterDemo {
    static final class Roster {
        private final List<String> members;

        Roster(List<String> input) {
            List<String> captured = List.copyOf(input);
            if (captured.isEmpty()) {
                throw new IllegalArgumentException("At least one member");
            }
            if (captured.stream().anyMatch(String::isBlank)) {
                throw new IllegalArgumentException("Blank member");
            }
            members = captured;
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("An", "Binh"));
        Roster roster = new Roster(input);
        input.clear();
        System.out.println("afterInputClear=" + roster.members());

        try {
            roster.members().clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("getterClear=UnsupportedOperationException");
        }
        System.out.println("afterGetterAttempt=" + roster.members());

        try {
            new Roster(List.of());
        } catch (IllegalArgumentException e) {
            System.out.println("emptyInput=IllegalArgumentException");
        }

        try {
            new Roster(List.of(" "));
        } catch (IllegalArgumentException e) {
            System.out.println("blankInput=IllegalArgumentException");
        }

        List<String> withNull = new ArrayList<>();
        withNull.add(null);
        try {
            new Roster(withNull);
        } catch (NullPointerException e) {
            System.out.println("nullMember=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 DefensiveRosterDemo.java
java DefensiveRosterDemo
```

Stdout:

```text
afterInputClear=[An, Binh]
getterClear=UnsupportedOperationException
afterGetterAttempt=[An, Binh]
emptyInput=IllegalArgumentException
blankInput=IllegalArgumentException
nullMember=NullPointerException
```

Hàm khởi tạo giữ `captured`, không giữ `input`. Khi bên gọi xóa nguồn sau khi khởi tạo, danh sách thành viên vẫn như lúc tiếp nhận. Khi người nhận gọi `clear` qua getter, kết quả không cho phép thao tác đó.

Có thể trả trực tiếp trường `members` trong thiết kế này vì trường đã chứa List chốt và phần tử là String. Không cần tạo thêm ArrayList ở mỗi lần đọc để bảo vệ cùng một quyền sửa. Cách này không dựa vào việc phương thức tạo có tạo đối tượng mới trong mọi trường hợp; nó dựa vào hợp đồng dữ liệu được trả về.

Các ca không hợp lệ được tách theo trách nhiệm:

- Không có thành viên và tên toàn khoảng trắng vi phạm điều kiện do lớp đặt ra.
- Phần tử null vi phạm điều kiện của phương thức tạo được dùng khi tiếp nhận.
- List nguồn rỗng vẫn là dữ liệu kỹ thuật hợp lệ đối với phương thức tạo, nhưng không hợp lệ đối với Roster này.

Việc chọn loại ngoại lệ và thông báo nên nhất quán với API thực tế. Ví dụ không âm thầm biến danh sách rỗng thành danh sách mặc định, không lọc bỏ tên lỗi và không thay đổi tên bằng cách cắt khoảng trắng. Nếu cần chuẩn hóa, phải xác định và công bố đó là bước riêng trong hợp đồng.

Đọc hợp đồng chụp và quy tắc null tại [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)). Phương thức này có từ Java 10; các chương trình trong bài dùng JDK 17.

## 6. Trả collection: chọn đúng một hợp đồng có thể giải thích

Khi trả về collection, có ít nhất ba hợp đồng hữu ích. Không phải hợp đồng nào cũng phù hợp với mọi đối tượng.

| Hợp đồng trả về | Bên nhận sửa phần chứa được không? | Chủ sở hữu thay nguồn thì kết quả cũ thế nào? | Cách làm cho List String |
| --- | --- | --- | --- |
| View chỉ đọc đang theo nguồn | Không qua view | Có thể thấy thay đổi của nguồn | `Collections.unmodifiableList(internal)` |
| Ảnh chụp chỉ đọc | Không | Không đi theo các lần sửa phần chứa của nguồn sau khi chụp | `List.copyOf(internal)` |
| Bản sao riêng có thể chỉnh sửa | Có, trên bản riêng | Không đi theo thay đổi phần chứa của nguồn | `new ArrayList<>(internal)` |

Một view chỉ đọc có thể phù hợp cho màn hình cần quan sát dữ liệu đang được chủ sở hữu quản lý. Một ảnh chụp phù hợp cho kết quả cần ổn định trong một quá trình xử lý. Một bản sao có thể sửa phù hợp khi người nhận cần lọc, sắp xếp hoặc bổ sung vào dữ liệu riêng mà không cập nhật chủ sở hữu.

Từ “chỉ đọc” cần chỉ rõ nó nói về quyền sửa qua đối tượng trả về. Nó không tự hứa rằng mọi lần đọc đều cho cùng dữ liệu. View có thể cấm `add` nhưng vẫn hiện thêm mục mới do chủ sở hữu thêm qua một phương thức hợp lệ.

Nếu chủ sở hữu cần giữ quy tắc nghiệp vụ khi dữ liệu thay đổi, nên cho phép thay đổi qua các phương thức có nghĩa như `addTask`, `removeMember` hoặc `replacePermissions`. Các phương thức ấy có thể kiểm tra điều kiện trước khi thay đổi. Trả thẳng một List nội bộ rồi yêu cầu bên gọi “đừng sửa sai” bỏ qua cơ hội giữ quy tắc đó ở chính đối tượng có trách nhiệm.

Lưu thành `ReturnPolicyDemo.java`. Chương trình dùng String để tách câu chuyện quyền sửa phần chứa khỏi câu chuyện trạng thái phần tử.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class ReturnPolicyDemo {
    static final class TaskBoard {
        private final List<String> tasks = new ArrayList<>();

        void addTask(String task) {
            Objects.requireNonNull(task, "task");
            if (task.isBlank()) {
                throw new IllegalArgumentException("Blank task");
            }
            tasks.add(task);
        }

        List<String> readView() {
            return Collections.unmodifiableList(tasks);
        }

        List<String> readSnapshot() {
            return List.copyOf(tasks);
        }

        List<String> editableCopy() {
            return new ArrayList<>(tasks);
        }
    }

    public static void main(String[] args) {
        TaskBoard board = new TaskBoard();
        board.addTask("learn");
        List<String> view = board.readView();
        List<String> snapshot = board.readSnapshot();
        List<String> editable = board.editableCopy();

        board.addTask("practice");
        editable.add("local-only");
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);
        System.out.println("editable=" + editable);
        System.out.println("board=" + board.readSnapshot());

        try {
            view.add("blocked");
        } catch (UnsupportedOperationException e) {
            System.out.println("viewAdd=UnsupportedOperationException");
        }

        try {
            snapshot.add("blocked");
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshotAdd=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ReturnPolicyDemo.java
java ReturnPolicyDemo
```

Stdout:

```text
view=[learn, practice]
snapshot=[learn]
editable=[learn, local-only]
board=[learn, practice]
viewAdd=UnsupportedOperationException
snapshotAdd=UnsupportedOperationException
```

Sau lần gọi `addTask("practice")`, `view` nhìn thấy hai mục vì nó theo List nội bộ. `snapshot` vẫn có một mục. `editable` cũng không nhận mục mới của chủ sở hữu nhưng cho phép thêm `local-only` vào bản riêng.

Dòng `board` xác nhận việc sửa bản riêng không cập nhật đối tượng TaskBoard. Hai ca ngoại lệ lại xác nhận view và ảnh chụp đều chặn thao tác thêm qua kết quả, dù quan hệ của chúng với nguồn khác nhau.

Các tên `readView`, `readSnapshot` và `editableCopy` trong ví dụ cố ý thể hiện chính sách. API thật có thể chọn cách đặt tên khác, nhưng tài liệu không nên để người nhận phải thử sửa hoặc quan sát debugger mới biết quyền của mình.

Hành vi đọc xuyên qua nguồn của lớp bọc được mô tả tại [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)). Sự phân biệt collection chỉ đọc, view và dữ liệu phần tử được trình bày trong [hợp đồng Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## 7. Kiểu giao diện giúp tách bản triển khai, không tự tạo quyền chỉ đọc

Nhận tham số dưới kiểu `List<String>` thay vì bắt buộc `ArrayList<String>` giúp API diễn đạt nhu cầu danh sách mà không ràng buộc một bản triển khai. Tuy vậy, List vẫn có các phương thức sửa; chữ ký kiểu không tự cam kết khả năng sửa thực tế hay việc chuyển quyền sở hữu.

Chọn giao diện theo dữ liệu cần biểu diễn:

- Cần vị trí, thứ tự và số lần lặp: List.
- Cần tập giá trị phân biệt: Set.
- Cần liên kết khóa–giá trị: Map.
- Chỉ cần đọc một nhóm phần tử mà không đòi vị trí: có thể nhận Collection hoặc Iterable nếu phù hợp với cách sử dụng.

Không đổi List thành Set chỉ vì muốn bảo vệ dữ liệu. Loại trùng có thể làm mất thông tin, chẳng hạn số lần một sản phẩm xuất hiện trong dữ liệu đầu vào. Tương tự, không chọn một phương thức tạo không bảo đảm thứ tự rồi vẫn hứa thứ tự của một cấu trúc nguồn chuyên biệt.

Kiểu wildcard như `List<? extends Item>` có thể giới hạn việc thêm một Item cụ thể ở thời điểm biên dịch. Nó không là kiểu List chỉ đọc: những thao tác như `clear` vẫn thuộc API, và các Item lấy ra vẫn có thể có phương thức sửa. Giới hạn kiểu và quyền sửa đối tượng là hai khía cạnh khác nhau.

Trả về Iterable thay cho List có thể thu hẹp bề mặt phương thức mà người nhận thấy. Nhưng nếu đối tượng thực tế vẫn là collection nội bộ có thể sửa, việc đổi kiểu khai báo không tạo bản sao hay thu hồi tham chiếu. Không dùng việc “người gọi không nhìn thấy add trong chữ ký này” làm bằng chứng cho mức độ bảo vệ dữ liệu.

Với một API chỉ cần trả số lượng, giá trị tính toán hoặc một thông tin nhỏ, có thể trả trực tiếp kết quả đó thay vì công bố cả collection nội bộ. Thiết kế theo nhu cầu sử dụng thường giảm số đường truy cập cần quản lý.

## 8. Bảo vệ List ngoài chưa bảo vệ đối tượng phần tử

Giả sử báo cáo chứa các dòng hàng. List không được sửa, nhưng mỗi dòng vẫn là đối tượng có `setQuantity`. Người nhận có thể không xóa được dòng nhưng vẫn đổi số lượng trên dòng đã lấy ra. Nếu dòng đó còn được đối tượng khác dùng, thay đổi sẽ xuất hiện ở cả hai nơi.

Có ba hướng lựa chọn tùy hợp đồng:

1. Dùng đối tượng phần tử bất biến để có thể chia sẻ an toàn về trạng thái.
2. Sao chép phần tử thành đối tượng riêng, nếu người nhận được sửa bản riêng.
3. Chuyển dữ liệu sang một dạng giá trị chỉ chứa các thông tin cần công bố.

Hướng thứ ba thường phù hợp cho kết quả đọc. Nó còn giúp tránh công bố cả phương thức sửa hoặc dữ liệu không cần thiết của đối tượng nghiệp vụ nội bộ.

Lưu thành `ElementBoundaryDemo.java`. `Line` là đối tượng có thể sửa; `LineSnapshot` chỉ giữ mã String và số lượng int. `ShallowReport` cố ý mới bảo vệ List ngoài; `Report` tạo dữ liệu giá trị riêng trước khi chốt danh sách.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ElementBoundaryDemo {
    static final class Line {
        private final String sku;
        private int quantity;

        Line(String sku, int quantity) {
            this.sku = Objects.requireNonNull(sku, "sku");
            setQuantity(quantity);
        }

        String sku() {
            return sku;
        }

        int quantity() {
            return quantity;
        }

        void setQuantity(int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("Positive quantity required");
            }
            this.quantity = quantity;
        }
    }

    record LineSnapshot(String sku, int quantity) {
        LineSnapshot {
            Objects.requireNonNull(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException("Positive quantity required");
            }
        }
    }

    static final class ShallowReport {
        private final List<Line> lines;

        ShallowReport(List<Line> input) {
            lines = List.copyOf(input);
        }

        List<Line> lines() {
            return lines;
        }
    }

    static final class Report {
        private final List<LineSnapshot> lines;

        Report(List<Line> input) {
            List<LineSnapshot> captured = new ArrayList<>();
            for (Line line : input) {
                Objects.requireNonNull(line, "line");
                captured.add(new LineSnapshot(line.sku(), line.quantity()));
            }
            lines = List.copyOf(captured);
        }

        List<LineSnapshot> lines() {
            return lines;
        }
    }

    public static void main(String[] args) {
        Line original = new Line("P1", 2);
        List<Line> input = new ArrayList<>(List.of(original));
        ShallowReport shallow = new ShallowReport(input);
        Report report = new Report(input);

        original.setQuantity(7);
        System.out.println("shallowQuantity=" + shallow.lines().get(0).quantity());
        System.out.println("reportQuantity=" + report.lines().get(0).quantity());

        shallow.lines().get(0).setQuantity(9);
        System.out.println("originalQuantity=" + original.quantity());
        System.out.println("reportAfterEdit=" + report.lines().get(0).quantity());

        input.clear();
        System.out.println("reportSize=" + report.lines().size());
        try {
            report.lines().clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("reportClear=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ElementBoundaryDemo.java
java ElementBoundaryDemo
```

Stdout:

```text
shallowQuantity=7
reportQuantity=2
originalQuantity=9
reportAfterEdit=2
reportSize=1
reportClear=UnsupportedOperationException
```

Sau khi sửa `original` từ số lượng 2 thành 7, báo cáo sao chép nông đọc được 7. Báo cáo đã chuyển sang `LineSnapshot` vẫn giữ 2. Khi sửa qua dòng lấy từ `shallow.lines()` thành 9, đối tượng `original` cũng đổi theo. Một lần nữa, không có thao tác sửa List ngoài nào được thực hiện.

`Report` lấy các giá trị cần thiết rồi dựng đối tượng `LineSnapshot` riêng. Việc xóa List đầu vào sau đó không xóa dòng trong báo cáo; việc cố xóa qua List đầu ra bị chặn. Hai chiều được bảo vệ ở cả phần chứa và mức trạng thái mà báo cáo cần giữ.

Record trong ví dụ là cú pháp gọn cho một nhóm giá trị. Các thành phần của nó được lưu bằng trường final và có phương thức đọc như `sku()`, `quantity()`. Trong trường hợp cụ thể này, String bất biến và int là giá trị nguyên thủy, nên không có đối tượng con có thể sửa để bị lộ ra.

Không suy rộng rằng mọi record đều tự bất biến sâu. Nếu một thành phần record là List có thể sửa, record vẫn cần xử lý ranh giới List đầu vào/đầu ra. Trường final không thay thế chính sách đối với đối tượng được tham chiếu. Có thể đối chiếu quy tắc trường và phương thức truy cập record trong [JLS 17, Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).

Cách tạo bản giá trị ở đây phù hợp với Line đang có. Nó không tự sao chép một đồ thị đối tượng bất kỳ, không giữ mọi quan hệ định danh giữa các phần tử và không đảm bảo đọc nguyên tử nhiều trường đang bị luồng khác thay đổi. Những yêu cầu đó phải được thiết kế riêng nếu mô hình có chúng.

## 9. Collection lồng nhau cần xét từng tầng có quyền sửa

Một cấu hình `Map<String, Set<String>>` có ít nhất hai tầng collection:

- Map quyết định vai trò nào được gắn với Set nào.
- Set quyết định những quyền nào thuộc vai trò đó.

Chỉ chụp hoặc bọc Map ngoài chưa chặn việc thêm quyền vào một Set đã được giữ chung. Chỉ bọc Set rồi giữ nguồn Map bên ngoài cũng chưa chặn việc thay Set gắn với một vai trò. Mục tiêu bảo vệ hai tầng cần xử lý cả hai đường.

Lưu thành `NestedPolicyDemo.java`. Hợp đồng của ví dụ là chốt bảng vai trò và các tập quyền tại thời điểm tiếp nhận, không cho người nhận sửa qua đầu ra; vai trò không có trong bảng trả tập rỗng. Khóa và quyền là String, nên không có tầng đối tượng giá trị có thể sửa sâu hơn.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class NestedPolicyDemo {
    static final class AccessPolicy {
        private final Map<String, Set<String>> roles;

        AccessPolicy(Map<String, Set<String>> input) {
            Objects.requireNonNull(input, "input");
            Map<String, Set<String>> captured = new HashMap<>();
            input.forEach((role, permissions) -> {
                Objects.requireNonNull(role, "role");
                if (role.isBlank()) {
                    throw new IllegalArgumentException("Blank role");
                }
                Set<String> values = Set.copyOf(permissions);
                if (values.stream().anyMatch(String::isBlank)) {
                    throw new IllegalArgumentException("Blank permission");
                }
                captured.put(role, values);
            });
            roles = Map.copyOf(captured);
        }

        Set<String> permissionsFor(String role) {
            Objects.requireNonNull(role, "role");
            return roles.getOrDefault(role, Set.of());
        }

        Map<String, Set<String>> snapshot() {
            return roles;
        }
    }

    public static void main(String[] args) {
        Set<String> permissions = new HashSet<>(Set.of("read", "write"));
        Map<String, Set<String>> input = new HashMap<>();
        input.put("editor", permissions);
        AccessPolicy policy = new AccessPolicy(input);

        permissions.add("delete");
        input.clear();
        System.out.println("editorForDisplay="
                + new TreeSet<>(policy.permissionsFor("editor")));
        System.out.println("missingEmpty="
                + policy.permissionsFor("missing").isEmpty());

        try {
            policy.permissionsFor("editor").clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("permissionClear=UnsupportedOperationException");
        }

        try {
            policy.snapshot().put("admin", Set.of("all"));
        } catch (UnsupportedOperationException e) {
            System.out.println("mapPut=UnsupportedOperationException");
        }

        System.out.println("editorAfterAttempts="
                + new TreeSet<>(policy.permissionsFor("editor")));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NestedPolicyDemo.java
java NestedPolicyDemo
```

Stdout:

```text
editorForDisplay=[read, write]
missingEmpty=true
permissionClear=UnsupportedOperationException
mapPut=UnsupportedOperationException
editorAfterAttempts=[read, write]
```

Trong hàm khởi tạo, mỗi Set quyền được chụp trước khi đưa vào Map tạm. Khi toàn bộ đầu vào đã được chuẩn bị và kiểm tra, Map tạm được chụp thành trường `roles`. Trường chỉ nhận kết quả đã hoàn tất; không công bố Map đang được điền dở.

Sau khi tạo chính sách, chương trình thực hiện hai thay đổi đầu vào khác loại: thêm `delete` vào Set cũ và xóa Map nguồn. Kết quả vẫn có hai quyền `read`, `write` cho `editor`. Các lần cố xóa tập quyền hoặc thêm ánh xạ qua kết quả đều bị chặn.

Việc in dùng `TreeSet` để có thứ tự hiển thị ổn định, không phải để ngầm hứa rằng Set chốt sẽ duyệt theo thứ tự chữ. Khi kết quả có yêu cầu thứ tự thực sự, phải chọn và công bố hợp đồng có thứ tự ngay trong thiết kế.

Map tạm và Set chốt tạo được mức bảo vệ đủ cho hình dạng dữ liệu của ví dụ. Nếu giá trị đổi thành `Set<Permission>` với đối tượng Permission có thể sửa, cần tiếp tục đánh giá quyền sửa ở tầng đó. Không áp dụng một công thức “bọc hai lần” mà bỏ qua kiểu phần tử thực tế.

Chi tiết phương thức tạo dùng trong ví dụ: [Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)) và [Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)). Cả hai từ chối null theo hợp đồng tương ứng và không cung cấp cơ chế sao chép sâu đối tượng.

## 10. Ghi hợp đồng để người gọi không phải đoán

Một API trả `List<T>` vẫn còn nhiều điều cần nói ngoài kiểu T. Hợp đồng có thể trình bày bằng Javadoc hoặc tài liệu phương thức, nhưng nên dùng những phát biểu kiểm chứng được.

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ diễn đạt rõ |
| --- | --- | --- |
| Thời gian giữ đầu vào | Chỉ đọc trong lúc gọi hay giữ sau khi gọi? | Lớp lưu ảnh chụp các tên đã nhận |
| Quyền sửa nguồn | Bên gọi còn được dùng và sửa nguồn sau khi gọi không? | Sửa phần chứa của nguồn sau khi hoàn tất không đổi danh sách đã lưu |
| Quyền sửa kết quả | Kết quả có cho thêm/xóa/thay phần tử không? | Kết quả không hỗ trợ thao tác sửa List |
| Quan hệ với trạng thái hiện tại | Kết quả cũ có nhận thay đổi mới từ chủ sở hữu không? | Kết quả là ảnh chụp của lần lấy dữ liệu |
| Phần tử | Chia sẻ đối tượng hay tạo dữ liệu giá trị riêng? | Kết quả chứa các LineSnapshot độc lập với Line đầu vào |
| Dữ liệu không hợp lệ | Null, rỗng, phần tử lỗi được xử lý thế nào? | Null bị từ chối, danh sách rỗng gây lỗi điều kiện nghiệp vụ |
| Thứ tự và trùng lặp | Có giữ vị trí và số lần xuất hiện không? | List giữ thứ tự đầu vào và cho phép tên lặp |
| Truy cập đồng thời | Bên gọi được sửa nguồn trong khi phương thức đọc không? | Việc sửa đồng thời phải tuân theo cơ chế phối hợp đã nêu |

Đối với `Roster` ở phần 5, mô tả đầy đủ có thể là: “Tiếp nhận một List tên không null, không chứa null, không rỗng và không có tên toàn khoảng trắng. Lớp giữ thứ tự cùng các lần xuất hiện trong List tại lúc tiếp nhận. Thay đổi phần chứa của List đầu vào sau khi hàm khởi tạo hoàn tất không làm thay đổi danh sách đã lưu. Kết quả đọc không cho phép sửa List.”

Đối với `TaskBoard.readView()`, cần thêm ý rằng người nhận có thể thấy dữ liệu do TaskBoard cập nhật về sau. Nếu thay bằng lời hứa “kết quả cố định”, bản triển khai dùng lớp bọc đang theo nguồn sẽ không đáp ứng hợp đồng dù mọi lần gọi `add` qua view đều bị chặn.

Không cần công bố tên lớp triển khai nếu đó không phải phần có ý nghĩa của API. Lời hứa “luôn trả ArrayList” vừa không mô tả đầy đủ quyền sửa vừa làm người dùng phụ thuộc vào một lựa chọn có thể không cần thiết. Công bố khả năng, thứ tự, mức độc lập và chính sách lỗi thường hữu ích hơn.

Hợp đồng cũng giúp xem xét thay đổi phiên bản. Đổi một getter từ bản sao có thể sửa sang kết quả chỉ đọc có thể làm mã bên gọi bắt đầu nhận ngoại lệ. Đổi từ ảnh chụp sang view có thể làm dữ liệu cũ đổi theo trạng thái mới. Không coi những thay đổi ấy chỉ là tối ưu nội bộ nếu hành vi đã được công bố khác đi.

## 11. Giữ đường thay đổi hợp lệ ở phía chủ sở hữu

Khi lớp quản lý dữ liệu thay đổi, không nhất thiết biến toàn bộ đối tượng thành bất biến. Có thể giữ collection nội bộ có thể sửa, nhưng chỉ mở những thao tác đáp ứng quy tắc của lớp.

Ví dụ, thay vì trả List thật để bên gọi tự thêm thành viên, lớp có thể cung cấp `addMember(name)`. Thay vì để bên gọi xóa tùy ý, lớp có thể kiểm tra trước xem việc xóa có làm danh sách rỗng hay không. Đầu ra đọc khi ấy được chọn là view hoặc ảnh chụp tùy yêu cầu.

Đối với một thao tác nhận cả collection để thay thế trạng thái, nên chuẩn bị dữ liệu mới ở biến cục bộ trước. Hoàn tất việc kiểm tra và tạo mức bảo vệ cần thiết rồi mới thay trạng thái đang giữ. Nếu dữ liệu không hợp lệ ở mục cuối, tránh để đối tượng đã cập nhật một phần các mục trước đó mà không có hợp đồng cho phép kết quả dở dang.

Phải xét cả những đường ra ngoài getter:

- Trả `keySet`, `values` hoặc `entrySet` của Map nội bộ có thể công bố view liên quan đến Map.
- Trả một phần List bằng `subList` có thể tiếp tục liên hệ với List nguồn.
- Gửi collection hoặc đối tượng phần tử cho một hàm xử lý do bên ngoài cung cấp cũng trao một đường giữ tham chiếu.
- Một bộ duyệt có khả năng xóa có thể là đường sửa ngay cả khi API không trả trực tiếp List.

Giải pháp phụ thuộc hợp đồng của từng đường. Nếu đường đó chỉ nên cung cấp dữ liệu đọc, đưa ra biểu diễn đã được bảo vệ ở mức cần thiết. Nếu bên nhận được thay đổi, hướng thay đổi về thao tác mà chủ sở hữu kiểm soát hoặc một bản riêng được phép sửa.

Ví dụ, gọi một hàm xử lý ngoài bằng List chỉ đọc chứa Line có setter vẫn cho hàm ấy giữ và sửa Line. Không giới hạn việc kiểm tra ở từ khóa `return`; cần theo dõi mọi nơi tham chiếu nội bộ được chuyển sang thành phần khác.

Không chuyển trực tiếp collection có thể sửa thuộc một chủ sở hữu khác vào trường của mình rồi mặc định bên kia sẽ không sửa nữa. Nếu có thỏa thuận chuyển quyền sở hữu, thỏa thuận phải rõ và có khả năng duy trì. Trong mã Java thông thường, cơ chế tham chiếu không tự vô hiệu hóa biến mà phía chuyển vẫn đang giữ.

## 12. Giới hạn của sao chép và chi phí cần cân nhắc

Sao chép bảo vệ mức độc lập đã chọn, không thay thế mọi cơ chế quản lý trạng thái.

**Về truy cập đồng thời:** List nguồn có thể sửa không mặc nhiên an toàn để đọc trong khi một luồng khác ghi. Bản sao tạo xong có thể không còn theo nguồn, nhưng quá trình lấy dữ liệu vẫn phải tuân theo hợp đồng đồng bộ hóa của nguồn. Không dựa vào việc đôi lúc thấy hoặc không thấy `ConcurrentModificationException` để kết luận quá trình đọc đúng. Hợp đồng Collection dành trách nhiệm chính sách đồng bộ hóa cho từng bản triển khai.

**Về nhiều trường liên quan:** Chuyển một đối tượng có thể sửa sang dữ liệu giá trị có thể đọc nhiều trường ở các thời điểm khác nhau. Nếu yêu cầu các trường phải phản ánh cùng một trạng thái nghiệp vụ, chủ sở hữu cần cung cấp cách lấy trạng thái nhất quán hoặc phối hợp việc sửa. Vòng lặp sao chép phần tử tự nó không thiết lập yêu cầu này.

**Về mức sâu:** Sao chép một tầng chưa đảm bảo độc lập toàn bộ đồ thị. Với quan hệ dùng chung, vòng tham chiếu hoặc tài nguyên có vòng đời riêng, cần một chính sách phù hợp. Không gọi đệ quy “copy mọi thứ” khi chưa xác định phần nào là giá trị, phần nào là tài nguyên và phần nào cần giữ quan hệ định danh.

**Về chi phí:** Tạo bản sao có thể cần duyệt dữ liệu, cấp phát và giữ thêm tham chiếu. Nếu trạng thái đã là dữ liệu chốt phù hợp, có thể trả lại kết quả đó thay vì dựng một bản sao ở mỗi getter. Nếu kết quả cần thay đổi theo thời gian, cân nhắc tạo ảnh chụp tại những thời điểm có ý nghĩa và tái sử dụng trong phạm vi hợp đồng cho phép.

Không loại bỏ bước bảo vệ chỉ vì thấy cấp phát trong công cụ đo hiệu năng mà chưa hiểu yêu cầu quyền sở hữu. Cũng không sao chép nhiều lần qua mọi lớp trung gian khi các lớp đã chia sẻ một giá trị bất biến phù hợp. Tối ưu dựa trên đường dùng dữ liệu và phép đo, đồng thời giữ nguyên những hành vi mà API hứa.

Các ví dụ trong bài chạy một luồng để quan sát rõ từng đường thay đổi. Chúng chứng minh quan hệ dữ liệu ở những thao tác đã nêu, không là một thiết kế đồng bộ hóa hoàn chỉnh.

## 13. Kiểm chứng bằng hành vi thay vì định danh

Một bài kiểm tra tốt cố sửa qua từng đường mà hợp đồng nói đã được chặn hoặc đã tách. Không chỉ kiểm tra nội dung ngay sau hàm khởi tạo, vì lúc ấy cả thiết kế lộ tham chiếu cũng có thể cho kết quả đúng.

| Đường kiểm tra | Cách gây thay đổi | Điều cần quan sát theo hợp đồng |
| --- | --- | --- |
| Đầu vào sau khi tiếp nhận | Thêm/xóa/thay tham chiếu phần tử trong nguồn | Dữ liệu riêng đã chốt không đổi |
| Kết quả chỉ đọc | Gọi thao tác sửa có tác dụng thực sự | Bị từ chối; dữ liệu chủ sở hữu vẫn đúng |
| Bản sao chỉnh sửa được | Sửa bản trả về | Thay đổi chỉ thuộc bản riêng |
| View đang theo nguồn | Cập nhật qua phương thức của chủ sở hữu | View thấy dữ liệu mới theo hợp đồng |
| Phần tử có thể sửa | Gọi setter qua tham chiếu nguồn hoặc kết quả | Mức dùng chung/độc lập đúng như công bố |
| Collection lồng | Sửa từng tầng bằng tham chiếu còn giữ | Các tầng đã hứa bảo vệ không đổi |
| Dữ liệu không hợp lệ | Null, rỗng hoặc mục lỗi | Lỗi rõ ràng; không công bố trạng thái dở dang |

Không dùng `result != input` làm bằng chứng duy nhất cho sự độc lập. Hai collection khác đối tượng vẫn có thể dùng chung phần tử có thể sửa; hai kết quả phương thức tạo cũng không nhất thiết cần khác định danh để đáp ứng đúng hợp đồng.

Khi kiểm tra List, thứ tự và số lần xuất hiện thường thuộc dữ liệu cần so sánh. Với Set hoặc Map không hứa thứ tự, so sánh phần tử hay ánh xạ; đừng buộc thứ tự chuỗi in. Thí nghiệm NestedPolicyDemo cố ý sắp xếp riêng lúc in để stdout ổn định.

Khi kiểm tra quyền sửa, chọn thao tác rõ ràng có yêu cầu thay đổi, như thêm một phần tử mới hoặc xóa một mục đang tồn tại. Không suy ra quy tắc cho mọi collection từ những thao tác không có tác dụng như thêm một collection rỗng, vì hợp đồng chung có chỗ cho khác biệt về ngoại lệ trong các trường hợp này.

Cuối cùng, kiểm tra trạng thái sau lần sửa bị từ chối hoặc sau đầu vào không hợp lệ. Câu hỏi quan trọng không chỉ là “có ngoại lệ không?” mà còn là “đối tượng có còn giữ đúng các quy tắc đã cam kết không?”.

## 14. Thực hành thiết kế và tự giải thích

### Bài 1: Danh sách người nhận thông báo

Một lớp nhận `List<String>` người nhận, giữ để dùng nhiều lần và yêu cầu không rỗng. Người gọi vẫn muốn dùng List nguồn cho công việc khác.

Hãy nêu chính sách tiếp nhận và đầu ra. Sau khi tạo đối tượng, xóa List nguồn và thử xóa qua getter. Tiêu chí đạt: đối tượng vẫn giữ danh sách hợp lệ; người gọi hiểu rằng sửa nguồn không cập nhật lớp, và đầu ra có quyền sửa rõ ràng. Có thể dùng mô hình tiếp nhận của DefensiveRosterDemo nếu phần tử vẫn là String.

### Bài 2: Báo cáo cho phép xử lý riêng

Phương thức trả kết quả để người nhận tự sắp xếp và lọc, nhưng không được cập nhật dữ liệu nội bộ của dịch vụ.

Hãy chọn bản sao có thể sửa, xác định phần tử có được dùng chung không và kiểm tra việc xóa một mục khỏi kết quả không xóa mục nội bộ. Nếu phần tử có setter và người nhận cũng được sửa chúng trên bản riêng, sao chép phần chứa thôi chưa đủ; cần quyết định cách tạo dữ liệu phần tử riêng.

### Bài 3: Giao diện quan sát trạng thái mới

Một thành phần muốn quan sát các mục mới được chủ sở hữu thêm vào nhưng không được tự thêm/xóa.

Hãy thiết kế một view chỉ đọc và tài liệu nói rõ quan hệ với nguồn. Tiêu chí đạt: cập nhật qua phương thức của chủ sở hữu xuất hiện ở view; sửa qua view bị chặn; nếu có nhiều luồng, cơ chế phối hợp không bị bỏ qua. Không mô tả kết quả này là ảnh chụp cố định.

### Bài 4: Map chứa danh sách địa chỉ

Nguồn là `Map<String, List<Address>>`; Address là đối tượng có thể sửa. Kết quả phải là báo cáo không đổi khi nguồn hoặc một Address bên ngoài thay đổi.

Hãy vẽ bằng lời ba tầng cần bảo vệ: ánh xạ Map, các List và trạng thái Address. Tiêu chí đạt: đề xuất dữ liệu địa chỉ bất biến hoặc dữ liệu giá trị riêng, chốt các List tương ứng rồi chốt Map. Không xem một lần `Map.copyOf` là đủ cho cả ba tầng.

### Bài 5: Phương thức thay toàn bộ cấu hình

Một đối tượng đang có cấu hình hợp lệ. Phương thức thay thế nhận một collection mới nhưng mục cuối vi phạm điều kiện.

Hãy mô tả thứ tự chuẩn bị, kiểm tra và cập nhật để cấu hình cũ không bị thay đổi một phần khi có lỗi. Nêu nơi hoàn tất bảo vệ dữ liệu mới trước khi công bố. Nếu thao tác có yêu cầu đồng thời, tách yêu cầu cập nhật nhất quán ấy khỏi việc chỉ tạo collection chỉ đọc.

### Các câu hỏi tự kiểm tra

- **Vì sao private final chưa đủ?** Private kiểm soát truy cập trường, final kiểm soát gán lại trường; cả hai không tự cấm sửa đối tượng còn được tham chiếu từ nơi khác.
- **Sao chép đầu vào rồi trả thẳng một ArrayList nội bộ có giải quyết đủ hai chiều không?** Chưa. Người nhận vẫn có thể sửa trạng thái qua đầu ra.
- **Bọc List đầu vào chỉ đọc rồi giữ lớp bọc có chốt dữ liệu không?** Chưa. Nếu nguồn bên dưới còn được sửa, lớp bọc có thể tiếp tục thấy thay đổi.
- **Khi nào trả lại collection đã giữ là phù hợp?** Khi collection và mức chia sẻ phần tử đã đáp ứng hợp đồng đầu ra, như Roster chứa List chốt các String.
- **Đổi kiểu trả về thành Iterable có tự tạo bản sao không?** Không. Kiểu khai báo và quan hệ tham chiếu là hai vấn đề khác nhau.
- **Điều gì quan trọng hơn một công thức bọc hay sao chép cố định?** Xác định ai được sửa tầng dữ liệu nào, ở thời điểm nào, rồi kiểm chứng đúng những đường thay đổi ấy.

