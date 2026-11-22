# subList và thay đổi cấu trúc qua view hoặc nguồn

## 1. Một khoảng nhìn lên danh sách, không phải bản sao

Khi cần xử lý một đoạn trong List, subList cho phép làm việc với khoảng đó qua một đối tượng List khác. Điểm quan trọng là **List được trả về là view được hỗ trợ bởi danh sách nguồn**. Nó không tự tạo một danh sách chứa độc lập.

Với nguồn A,B,C,D,E, lời gọi subList(1,4) nhìn thấy B,C,D:

```text
Chỉ số nguồn:   0   1   2   3   4
Nguồn:         A   B   C   D   E
                   └───────┘
View:              B   C   D
Chỉ số view:       0   1   2
```

Nếu nguồn cho sửa và view còn hợp lệ, set trong view thay tham chiếu ở vị trí tương ứng của nguồn. Thêm, xóa hoặc clear qua view cũng có thể thay đổi cấu trúc nguồn.

Ngược lại, tự thêm/xóa trực tiếp trên nguồn rồi tiếp tục dùng view cũ là tình huống khác: hợp đồng List không còn quy định hành vi của view đó khi cấu trúc nguồn bị sửa ngoài đường view.

Bài này tập trung vào quan hệ giữa nguồn, view, các thay đổi cấu trúc và bản sao. Các chương trình đầy đủ dùng Java 17 trở lên, với ArrayList làm nguồn chính để có hành vi kiểm chứng rõ ràng.

### 1.1. Các từ cần nắm trước

| Từ trong bài | Ý nghĩa |
|---|---|
| Nguồn, backing list | Danh sách hỗ trợ dữ liệu cho view |
| View | Đối tượng cho phép nhìn/thao tác trên một phần dữ liệu của nguồn |
| Khoảng nửa mở | Bao gồm đầu fromIndex, không bao gồm cuối toIndex |
| Thay đổi không thuộc cấu trúc | Ví dụ set thay phần tử tại vị trí có sẵn, không thêm/xóa vị trí |
| Thay đổi cấu trúc | Thêm/xóa làm đổi kích thước hoặc thay đổi gây ảnh hưởng tính đúng của phép duyệt |
| Bản sao cấu trúc chứa | List có vùng chứa riêng, không tiếp tục bám vào các vị trí của nguồn |
| Sao chép nông | Sao chép tham chiếu phần tử; đối tượng phần tử vẫn có thể được chia sẻ |
| Fail-fast | Phát hiện một số thay đổi không phù hợp và báo lỗi sớm; không phải cơ chế bảo đảm đồng thời |

## 2. Khoảng và chỉ số của subList

### 2.1. from được lấy, to không được lấy

Với `source.subList(fromIndex, toIndex)`, điều kiện khoảng là:

```text
0 <= fromIndex <= toIndex <= source.size()
Số phần tử ban đầu của view = toIndex - fromIndex
```

subList(1,4) lấy các chỉ số nguồn 1,2,3. Nó không lấy phần tử ở chỉ số 4.

subList(0,source.size()) nhìn toàn danh sách. subList(i,i) là khoảng rỗng hợp lệ khi i nằm từ 0 đến size. subList(size,size) cũng hợp lệ; đó là khoảng rỗng tại cuối nguồn.

Các điều kiện này nói về chỉ số, không phải tìm theo giá trị. subList không tự lọc mọi phần tử có giá trị nằm giữa hai số.

### 2.2. View đánh chỉ số lại từ 0

view.get(0) là phần tử đầu của khoảng, không nhất thiết là source.get(0). Trong ví dụ B,C,D, view.get(1) là C tại chỉ số nguồn 2.

Khi chèn vào một view ArrayList còn hợp lệ, vị trí chèn là vị trí tương đối trong view. view.add(0,x) chèn trước phần tử đầu của view; view.add(view.size(),x) chèn ở cuối view, ngay trước phần nguồn đứng sau khoảng nếu có.

Sau khi thêm/xóa qua view, kích thước và các chỉ số trong view thay đổi. Không tiếp tục dùng các chỉ số cũ mà không tính lại.

### 2.3. Không ép view thành một ArrayList độc lập

Kiểu trả về của subList là List<E>. Đối tượng view không có nghĩa là một ArrayList chứa riêng toàn bộ phần tử của khoảng.

Nếu cần một ArrayList độc lập về cấu trúc, tạo bằng constructor nhận Collection, chẳng hạn new ArrayList<>(view), trong lúc view còn hợp lệ. Ép kiểu không thực hiện sao chép và có thể gây ClassCastException.

Hợp đồng khoảng và quan hệ backing được mô tả tại [List.subList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## 3. Sửa nội dung và sửa cấu trúc qua đường nào?

### 3.1. set thay phần tử tại vị trí có sẵn

Với ArrayList, set thay tham chiếu tại một chỉ số mà không thêm/xóa vị trí. Khi nguồn và view còn hợp lệ:

- view.set(i,x) phản ánh lên vị trí tương ứng của nguồn.
- source.set(j,x) tại một vị trí trong khoảng phản ánh khi đọc view.
- set ngoài khoảng không làm một phần tử ngoài khoảng tự xuất hiện trong view.

Đây là quan hệ chia sẻ vị trí dữ liệu. Nó không có nghĩa view tự tìm lại một tập phần tử theo giá trị sau mọi thay đổi của nguồn.

### 3.2. Thêm/xóa qua view có thể sửa nguồn hợp lệ

Nếu nguồn hỗ trợ, view.add, view.remove và view.clear làm thay đổi nguồn. View đang thực hiện thao tác cập nhật kích thước tương ứng của chính nó.

clear trên view xóa phần hiện đang thuộc view, không xóa toàn bộ nguồn. Vì thế mẫu source.subList(from,to).clear() hữu ích khi cần loại bỏ một khoảng ngay trên nguồn.

Không có quy tắc “view không bao giờ được làm đổi size”. Điều cần xét là nguồn có hỗ trợ thao tác không và thay đổi có được thực hiện qua đường view phù hợp không.

### 3.3. Thêm/xóa trực tiếp trên nguồn là điều kiện khác

Khi backing list bị sửa cấu trúc bằng đường khác ngoài view đang dùng, hợp đồng subList không còn quy định hành vi của view đó. Không tiếp tục dựa vào size, get, vòng lặp hoặc toString của view cũ.

Điều này đúng ngay cả khi:

- Thêm ở cuối nguồn, ngoài khoảng của view.
- Xóa phần tử trước khoảng.
- Sửa qua một view anh em không chồng lấn.
- Xóa rồi thêm lại để size cuối bằng size ban đầu.
- Nguồn và view cùng được thao tác chỉ trong một luồng.

Không coi view là một cửa sổ tự động trượt để giữ cùng from/to hoặc tự tìm lại các đối tượng cũ sau thay đổi cấu trúc nguồn.

### 3.4. Đường đối tượng quan trọng hơn tên biến

Nếu alias và view trỏ đến cùng một đối tượng view, gọi alias.add vẫn là gọi qua view đó. Đổi tên biến không làm thao tác trở thành sửa nguồn bên ngoài.

Ngược lại, tạo hai subList riêng từ cùng nguồn là hai đối tượng view có trạng thái theo dõi riêng. Một thay đổi cấu trúc hợp lệ qua view thứ nhất không làm mọi view thứ hai tự đồng bộ và tiếp tục hợp lệ.

## 4. Chương trình 1: set, thêm, xóa và clear qua view

Lưu vào `SubListBasicsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListBasicsDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "C", "D", "E"));
        List<String> view = source.subList(1, 4);
        System.out.println("initialView=" + view);
        System.out.println("oldViewValue=" + view.set(1, "C2"));
        System.out.println("sourceAfterViewSet=" + source);
        source.set(1, "B2");
        System.out.println("viewAfterSourceSet=" + view);
        view.add(1, "X");
        System.out.println("sourceAfterViewAdd=" + source);
        System.out.println("viewAfterAdd=" + view);
        System.out.println("removedFromView=" + view.remove(2));
        System.out.println("sourceAfterViewRemove=" + source);
        view.clear();
        System.out.println("sourceAfterViewClear=" + source);
        System.out.println("clearedView=" + view);
        view.add("Y");
        System.out.println("sourceAfterReusingEmptyView=" + source);
        System.out.println("viewAfterReuse=" + view);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SubListBasicsDemo.java
java SubListBasicsDemo
```

Stdout:

```text
initialView=[B, C, D]
oldViewValue=C
sourceAfterViewSet=[A, B, C2, D, E]
viewAfterSourceSet=[B2, C2, D]
sourceAfterViewAdd=[A, B2, X, C2, D, E]
viewAfterAdd=[B2, X, C2, D]
removedFromView=C2
sourceAfterViewRemove=[A, B2, X, D, E]
sourceAfterViewClear=[A, E]
clearedView=[]
sourceAfterReusingEmptyView=[A, Y, E]
viewAfterReuse=[Y]
```

### 4.1. Hai đường set nhìn cùng vị trí

view ban đầu là B,C,D. view.set(1,C2) trả giá trị cũ C và làm nguồn thành A,B,C2,D,E.

source.set(1,B2) thay vị trí B trong nguồn. View đọc được B2,C2,D. Hai thao tác không thêm/xóa vị trí, nên ví dụ không làm view mất hiệu lực.

### 4.2. Chèn và xóa theo chỉ số của view

view.add(1,X) chèn X trước phần tử C2 của view. Nguồn thành A,B2,X,C2,D,E, còn view là B2,X,C2,D.

view.remove(2) xóa C2, không phải phần tử có chỉ số nguồn 2. Giá trị trả về xác nhận removedFromView là C2; nguồn còn A,B2,X,D,E.

### 4.3. clear chỉ xóa khoảng và view có thể còn được dùng

Lúc clear, view chứa B2,X,D. Xóa qua view làm nguồn còn A,E và view trở thành rỗng.

view.add(Y) sau đó vẫn hợp lệ trong ví dụ ArrayList này. Nó chèn tại vị trí của khoảng đã rỗng, làm nguồn thành A,Y,E. View không bị mất hiệu lực chỉ vì nó tự clear qua thao tác được hỗ trợ.

Đừng nhầm trường hợp này với source.clear() rồi tiếp tục dùng view cũ: clear trực tiếp trên nguồn là một thay đổi cấu trúc bên ngoài view.


## 5. View mất bảo đảm không có nghĩa luôn báo cùng một ngoại lệ

### 5.1. Hợp đồng và dấu hiệu phát hiện là hai tầng khác nhau

List.subList quy định rằng hành vi của view không còn được xác định nếu backing list bị sửa cấu trúc qua đường khác. Đây là điều người viết mã phải tránh.

ArrayList thường phát hiện một số trường hợp bằng cơ chế fail-fast và ném ConcurrentModificationException. Ngoại lệ này là dấu hiệu đã vi phạm cách sử dụng, không phải quyền cho phép sửa nguồn tùy ý rồi chờ thư viện “tự sửa view”.

Không biến một lần chạy chưa ném ngoại lệ thành bằng chứng view vẫn hợp lệ. Cũng không hứa mọi triển khai List sẽ ném đúng ngoại lệ tại cùng một phương thức sau thay đổi bên ngoài.

[ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) nêu giới hạn bảo đảm của fail-fast. [AbstractList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html) mô tả một cơ chế triển khai view theo dõi kích thước, độ lệch và số lần sửa đổi dự kiến.

### 5.2. Không chỉ nhìn size hiện tại

Một view có thể theo dõi lịch sử thay đổi cấu trúc, không chỉ so sánh kích thước cuối. Xóa một phần tử rồi thêm một phần tử khác để size trở về số cũ không làm view tự hợp lệ lại.

Ngoài thêm/xóa, cần đọc chính sách của thao tác và lớp cụ thể. Với ArrayList, tài liệu còn tính việc chủ động đổi kích thước mảng chứa vào thay đổi cấu trúc; chỉ so size không đủ làm phép kiểm tra an toàn.

set tại một vị trí có sẵn là trường hợp đã được phân biệt rõ. Đừng mở rộng kết luận “set được” thành “mọi thao tác không đổi size đều không ảnh hưởng view hoặc iterator”.

### 5.3. Sửa qua một view có thể làm view khác lỗi

Giả sử left và right là hai subList riêng của cùng một ArrayList. left.remove có thể là thao tác hợp lệ đối với left và cập nhật nguồn. Nhưng từ phía right, nguồn vừa bị sửa cấu trúc qua đường khác.

Hai khoảng không chồng nhau cũng không loại bỏ vấn đề này. View không phải một thuê bao độc lập tự tính lại mọi độ lệch sau sửa đổi của các view khác.

Tương tự, một iterator của nguồn tạo trước khi view.add vẫn có thể mất hiệu lực. “View vừa sửa còn dùng được” không có nghĩa mọi iterator hay view khác trên cùng nguồn đều dùng tiếp được.

### 5.4. ConcurrentModificationException không đòi phải có hai luồng

Tên ngoại lệ dễ khiến người học nghĩ chỉ đa luồng mới gặp lỗi. Một luồng tạo view, tự sửa nguồn rồi dùng view cũ cũng đủ tạo tình huống không phù hợp.

Vấn đề trước hết là có nhiều đường thao tác lên cùng cấu trúc chứa. Đồng bộ truy cập có thể giải quyết tranh chấp giữa các luồng, nhưng không tự thay đổi quy tắc hợp lệ của view sau sửa cấu trúc nguồn bên ngoài.

## 6. Chương trình 2: các cách làm view hoặc iterator cũ mất hiệu lực

Chương trình này **cố ý minh họa cách dùng không hợp lệ**. Các dòng ConcurrentModificationException bên dưới là kết quả quan sát với ArrayList trên JDK 17.0.15. Đây không phải cam kết rằng mọi List sẽ phát hiện cùng lỗi ở cùng thời điểm.

Mỗi trường hợp độc lập tạo một danh sách mới. Sau khi quan sát lỗi, chương trình không tiếp tục sử dụng view hoặc iterator đã lỗi.

Lưu vào `SubListInvalidationDemo.java`:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class SubListInvalidationDemo {
    static void expectConcurrent(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected ConcurrentModificationException");
        } catch (ConcurrentModificationException observed) {
            System.out.println(label + "=ConcurrentModificationException");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> view = source.subList(1, 3);
        source.add("E");
        System.out.println("sourceAfterOutsideAdd=" + source);
        expectConcurrent("oldViewGet", () -> view.get(0));

        List<String> sameSize = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> oldRange = sameSize.subList(1, 3);
        sameSize.remove(0);
        sameSize.add(0, "Z");
        System.out.println("sourceSameSize=" + sameSize.size());
        expectConcurrent("oldRangeSize", () -> oldRange.size());

        List<String> shared = new ArrayList<>(List.of("A", "B", "C", "D", "E", "F"));
        List<String> left = shared.subList(0, 2);
        List<String> right = shared.subList(3, 5);
        left.remove(0);
        System.out.println("sharedAfterLeftRemove=" + shared);
        System.out.println("leftStillUsable=" + left);
        expectConcurrent("rightGet", () -> right.get(0));

        List<String> root = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> rootIterator = root.iterator();
        List<String> current = root.subList(1, 3);
        current.add("D");
        System.out.println("currentView=" + current);
        expectConcurrent("oldRootIteratorNext", () -> rootIterator.next());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SubListInvalidationDemo.java
java SubListInvalidationDemo
```

Stdout:

```text
sourceAfterOutsideAdd=[A, B, C, D, E]
oldViewGet=ConcurrentModificationException
sourceSameSize=4
oldRangeSize=ConcurrentModificationException
sharedAfterLeftRemove=[B, C, D, E, F]
leftStillUsable=[B]
rightGet=ConcurrentModificationException
currentView=[B, C, D]
oldRootIteratorNext=ConcurrentModificationException
```

### 6.1. Thêm ngoài khoảng vẫn làm view cũ lỗi

view nhìn khoảng B,C của nguồn A,B,C,D. source.add(E) không chèn vào giữa B,C, nhưng vẫn sửa cấu trúc trực tiếp trên nguồn.

oldViewGet ném ConcurrentModificationException trong môi trường đã kiểm tra. Không có quy tắc cho phép dùng tiếp view chỉ vì E nằm sau khoảng.

### 6.2. Kích thước trở lại 4 không khôi phục view

sameSize ban đầu có 4 phần tử. remove(0) rồi add(0,Z) làm số phần tử cuối vẫn bằng 4. Tuy vậy oldRange được tạo trước chuỗi sửa cấu trúc, nên gọi size trên view đó vẫn bị phát hiện lỗi.

Không sửa chữa một view bằng cách cố khôi phục kích thước hay dữ liệu nguồn về “gần giống ban đầu”. Cần dừng dùng đối tượng view cũ.

### 6.3. View anh em không đồng bộ theo nhau

left ban đầu nhìn A,B, right nhìn D,E. left.remove(0) xóa A khỏi nguồn và left còn B.

leftStillUsable là `[B]` vì chính left thực hiện thao tác. rightGet báo lỗi vì right không phải đường thực hiện thay đổi cấu trúc. Không cần hai khoảng chồng lấn để gặp vấn đề này.

### 6.4. View hợp lệ không cứu iterator nguồn đã tạo trước

rootIterator được tạo trước current.add(D). current view vẫn dùng được và chứa B,C,D sau khi thêm qua nó.

rootIterator.next sau thay đổi bị phát hiện lỗi. Cần xét vòng đời của từng iterator riêng, không chỉ của đối tượng view.

## 7. Cần độc lập thì tạo bản sao khi view còn hợp lệ

### 7.1. Bản sao sửa được

new ArrayList<>(view) thu các phần tử hiện thấy trong view vào một cấu trúc ArrayList mới. Sau đó thêm/xóa trên nguồn không làm bản sao tự thay đổi kích thước hay vị trí theo nguồn.

Ngược lại, add/remove/set trên bản sao không tác động cấu trúc nguồn. Các phần tử được sao chép theo tham chiếu, nên đối tượng bên trong có thể vẫn được chia sẻ.

Tạo bản sao **trước** khi nguồn bị sửa ngoài view. new ArrayList<>(view) không phải công cụ chữa một view đã mất hiệu lực; thao tác sao chép cũng phải đọc view và có thể báo lỗi.

### 7.2. Kết quả không cho sửa

List.copyOf(view) tạo kết quả List không cho thêm, xóa hoặc thay phần tử. Những sửa đổi tiếp theo của collection nguồn không được phản ánh như một view sống lên kết quả này.

Không hứa mỗi lần copyOf luôn cấp một đối tượng hoàn toàn mới: API có thể tận dụng một List không cho sửa phù hợp. Điều cần dựa vào là hợp đồng nội dung kết quả, không phải so sánh danh tính đối tượng.

List.copyOf không nhận phần tử null. Đây là điều kiện cần xét nếu khoảng nguồn có null. new ArrayList<>(view) có thể dùng khi cần giữ null và muốn bản sao sửa được.

Nguồn đối chiếu: [List.copyOf — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

### 7.3. Không cho sửa không đồng nghĩa sao chép sâu

Nếu phần tử là StringBuilder, cả nguồn và bản sao nông có thể trỏ đến cùng StringBuilder. Thay cấu trúc List và thay trạng thái đối tượng phần tử là hai việc khác nhau.

Nếu cần toàn bộ dữ liệu độc lập sâu, phải định nghĩa cách nhân bản theo kiểu phần tử. Không thể suy ra cách sao chép sâu tổng quát chỉ từ List<E>.

### 7.4. Bọc unmodifiable không cắt quan hệ backing

Collections.unmodifiableList(view) chặn sửa qua wrapper, nhưng vẫn dựa trên view bên dưới. Nó không tạo bản sao, cũng không làm một view cũ trở lại hợp lệ sau sửa cấu trúc nguồn.

Nếu yêu cầu là giữ một phần dữ liệu lâu hơn vòng đời nguồn đang thay đổi, chọn bản sao phù hợp thay vì chỉ bọc quyền đọc.

## 8. Chương trình 3: nguồn thay đổi nhưng bản sao vẫn độc lập về cấu trúc

Lưu vào `SubListCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class SubListCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> view = source.subList(1, 3);
        List<String> copy = new ArrayList<>(view);
        List<String> frozen = List.copyOf(view);
        source.add("E");
        System.out.println("sourceAfterAdd=" + source);
        System.out.println("copyAfterSourceAdd=" + copy);
        System.out.println("frozenAfterSourceAdd=" + frozen);
        copy.set(0, "B2");
        copy.add("X");
        System.out.println("editedCopy=" + copy);
        System.out.println("sourceAfterCopyEdit=" + source);
        try {
            frozen.set(0, "changed");
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("frozenSet=UnsupportedOperationException");
        }

        StringBuilder value = new StringBuilder("shared");
        List<StringBuilder> builders = new ArrayList<>(List.of(value));
        List<StringBuilder> shallow = new ArrayList<>(builders.subList(0, 1));
        shallow.get(0).append("!");
        System.out.println("sourceMutableValue=" + builders.get(0));
        System.out.println("sameElement=" + (builders.get(0) == shallow.get(0)));

        List<String> nullable = new ArrayList<>(Arrays.asList("A", null, "C"));
        System.out.println("nullableCopy=" + new ArrayList<>(nullable.subList(1, 3)));
        try {
            List.copyOf(nullable.subList(1, 3));
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("nullableCopyOf=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SubListCopyDemo.java
java SubListCopyDemo
```

Stdout:

```text
sourceAfterAdd=[A, B, C, D, E]
copyAfterSourceAdd=[B, C]
frozenAfterSourceAdd=[B, C]
editedCopy=[B2, C, X]
sourceAfterCopyEdit=[A, B, C, D, E]
frozenSet=UnsupportedOperationException
sourceMutableValue=shared!
sameElement=true
nullableCopy=[null, C]
nullableCopyOf=NullPointerException
```

### 8.1. Hai kết quả được tạo trước khi sửa nguồn

view nhìn B,C. copy và frozen đều được tạo trong lúc view còn hợp lệ. source.add(E) sau đó sửa cấu trúc nguồn trực tiếp, nên chương trình không dùng lại view.

copyAfterSourceAdd và frozenAfterSourceAdd đều là `[B, C]`. Chúng không trở thành các khoảng tự động cập nhật của nguồn.

### 8.2. Quyền sửa kết quả khác nhau

copy.set và copy.add làm copy thành `[B2, C, X]`; nguồn vẫn A,B,C,D,E. frozen.set bị từ chối bằng UnsupportedOperationException.

Tên biến frozen chỉ giúp đọc ví dụ. Đặc tính không cho sửa đến từ List.copyOf; nó không đóng băng sâu mọi đối tượng phần tử.

### 8.3. Cùng StringBuilder thì cùng nhìn thay đổi

shallow nhận tham chiếu StringBuilder đã có trong nguồn. Append qua shallow làm sourceMutableValue thành shared!, còn sameElement là true.

Điều này không mâu thuẫn với việc cấu trúc chứa đã độc lập. Nếu thay tham chiếu ở một vị trí của bản sao, nguồn không bị set theo; nếu sửa chính đối tượng chung, những nơi trỏ đến nó cùng quan sát được trạng thái đó.

### 8.4. Null ảnh hưởng lựa chọn kiểu sao chép

Khoảng nullable.subList(1,3) có null,C. Constructor ArrayList giữ cả hai vị trí, nên nullableCopy là `[null, C]`.

List.copyOf cùng khoảng ném NullPointerException. Không dùng copyOf như một phép lọc null tự động; nếu chính sách nghiệp vụ cần loại hoặc xử lý null, phải làm rõ điều đó trước khi tạo kết quả.


## 9. View chỉ có các quyền thao tác mà nguồn hỗ trợ

### 9.1. ArrayList sửa được khác danh sách kích thước cố định

subList không tạo thêm quyền thay đổi cấu trúc nếu nguồn không hỗ trợ.

Arrays.asList trả List có kích thước cố định được hỗ trợ bởi mảng. Nó cho set nhưng không cho thêm/xóa làm đổi số phần tử. View của nó cũng không thể biến thành một khoảng thêm/xóa tự do.

Vì vậy cần tách hai câu hỏi:

1. Có được thay phần tử tại vị trí hiện có không?
2. Có được làm đổi số vị trí không?

Một nguồn có thể trả lời “có” cho set và “không” cho add/remove. Nguồn đối chiếu: [Arrays.asList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html).

### 9.2. List không cho sửa

List.of trả List không cho thêm, xóa hoặc thay phần tử. subList của nó cũng không mở thêm quyền sửa.

Với Collections.unmodifiableList(backing), wrapper chặn sửa qua wrapper. Nếu backing là ArrayList và có tham chiếu khác gọi set hợp lệ trên nguồn, view đọc vẫn có thể thấy thay đổi đó.

Không mô tả mọi đối tượng “không cho sửa” là dữ liệu bất biến sâu hoặc bản sao độc lập. Cần biết nó đến từ factory tạo nội dung không cho sửa hay từ wrapper còn dựa trên nguồn.

Hợp đồng wrapper được mô tả tại [Collections.unmodifiableList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).

### 9.3. Lỗi quyền sửa khác lỗi chỉ số và lỗi view cũ

| Điều kiện trong các ví dụ | Loại vấn đề |
|---|---|
| add vào view của Arrays.asList | Nguồn không hỗ trợ đổi kích thước |
| set qua view không cho sửa | Không có quyền thay phần tử qua đường đó |
| from âm hoặc to vượt size | Khoảng không hợp lệ |
| from lớn hơn to | Hai cận không đúng thứ tự |
| get dùng chỉ số bằng size của view | Chỉ số phần tử vượt khoảng |
| Dùng view cũ sau sửa cấu trúc nguồn bên ngoài | Đã vi phạm hợp đồng backing của subList |

Không catch tất cả lỗi rồi quy về “subList không dùng được”. Phải xác định sai khoảng, sai quyền hay sai vòng đời quan hệ với nguồn.

## 10. Chương trình 4: quyền sửa và giới hạn chỉ số

Lưu vào `SubListCapabilitiesDemo.java`. Phần kiểm tra cận dùng ArrayList, nên tên ngoại lệ chi tiết bên dưới được đối chiếu với hợp đồng của lớp này.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class SubListCapabilitiesDemo {
    static void expect(String label, Class<? extends RuntimeException> type,
                       Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected " + type.getSimpleName());
        } catch (RuntimeException observed) {
            if (!type.isInstance(observed)) {
                throw observed;
            }
            System.out.println(label + "=" + type.getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<String> fixed = Arrays.asList("A", "B", "C");
        List<String> fixedView = fixed.subList(1, 3);
        fixedView.set(0, "B2");
        System.out.println("fixedAfterSet=" + fixed);
        expect("fixedViewAdd", UnsupportedOperationException.class,
                () -> fixedView.add("D"));
        expect("fixedViewClear", UnsupportedOperationException.class,
                () -> fixedView.clear());

        List<String> constantView = List.of("A", "B", "C").subList(1, 3);
        expect("constantViewSet", UnsupportedOperationException.class,
                () -> constantView.set(0, "B2"));

        List<String> backing = new ArrayList<>(List.of("A", "B", "C"));
        List<String> readOnly = Collections.unmodifiableList(backing).subList(0, 2);
        expect("readOnlyRemove", UnsupportedOperationException.class,
                () -> readOnly.remove(0));
        backing.set(0, "A2");
        System.out.println("readOnlyAfterSourceSet=" + readOnly);

        ArrayList<String> checked = new ArrayList<>(List.of("A", "B", "C"));
        expect("negativeFrom", IndexOutOfBoundsException.class,
                () -> checked.subList(-1, 2));
        expect("pastEnd", IndexOutOfBoundsException.class,
                () -> checked.subList(0, 4));
        expect("reversedBounds", IllegalArgumentException.class,
                () -> checked.subList(2, 1));
        List<String> one = checked.subList(1, 2);
        expect("viewIndexPastEnd", IndexOutOfBoundsException.class,
                () -> one.get(1));
        System.out.println("emptyEndRange=" + checked.subList(3, 3));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SubListCapabilitiesDemo.java
java SubListCapabilitiesDemo
```

Stdout:

```text
fixedAfterSet=[A, B2, C]
fixedViewAdd=UnsupportedOperationException
fixedViewClear=UnsupportedOperationException
constantViewSet=UnsupportedOperationException
readOnlyRemove=UnsupportedOperationException
readOnlyAfterSourceSet=[A2, B]
negativeFrom=IndexOutOfBoundsException
pastEnd=IndexOutOfBoundsException
reversedBounds=IllegalArgumentException
viewIndexPastEnd=IndexOutOfBoundsException
emptyEndRange=[]
```

### 10.1. Nguồn cố định kích thước vẫn cho set

fixedView.set(0,B2) thay B trong nguồn, nên fixedAfterSet là `[A, B2, C]`. Nhưng add và clear cần đổi kích thước, nên bị từ chối bằng UnsupportedOperationException.

Không đánh đồng fixed-size với “không thể sửa bất kỳ điều gì”. set được còn add không được là hai điều kiện nhất quán của nguồn này.

### 10.2. View không cho sửa vẫn có thể thấy source.set

constantView đến từ List.of nên set bị từ chối. readOnly đến từ wrapper không cho sửa nên remove cũng bị từ chối.

backing.set(0,A2) thực hiện qua nguồn ArrayList, không qua readOnly. Đó là thay đổi không thêm/xóa vị trí, nên readOnly đọc được `[A2, B]` trong ví dụ. Wrapper không làm phần dữ liệu nhìn thấy trở thành một ảnh chụp cố định.

### 10.3. Khoảng nguồn khác chỉ số trong view

Với ArrayList checked có size bằng 3:

- subList(-1,2) và subList(0,4) vượt cận.
- subList(2,1) đảo thứ tự cận.
- subList(1,2) chỉ có một phần tử, nên get(1) vượt chỉ số của view.
- subList(3,3) là một khoảng rỗng hợp lệ ở cuối.

Các lỗi cận được thử trên dữ liệu chưa bị thay đổi cấu trúc ngoài view. Điều đó giúp tách lỗi chỉ số khỏi lỗi view đã mất hiệu lực.

## 11. Dùng view để thao tác một khoảng ngay trên nguồn

### 11.1. Thuật toán nhận List có thể nhận view

Khi một thuật toán nhận List và chỉ cần làm việc trên một đoạn, có thể truyền subList thay cho cả nguồn. Ví dụ, Collections.sort trên view hợp lệ sắp xếp đoạn đó, không tự sắp toàn bộ danh sách nguồn.

Đó là một cách mở rộng thao tác theo khoảng mà không cần viết lại thuật toán với from/to cho từng phương thức.

Điều kiện vẫn giữ nguyên: nguồn hỗ trợ những thao tác mà thuật toán cần; view còn hợp lệ; không có đường khác làm thay đổi cấu trúc nguồn ngoài sự phối hợp của thuật toán.

### 11.2. Xóa nhiều phần tử qua chính view

clear hoặc removeIf qua view sửa được có thể loại bỏ một phần dữ liệu nguồn. Các phần tử ngoài view không tự trở thành đối tượng của bộ lọc.

Khi thuật toán đang duyệt, không tự gọi thêm các thao tác cấu trúc từ bên ngoài cơ chế sửa được phép của phép duyệt. Một vòng for-each có iterator riêng; việc gọi view.remove tùy ý bên trong vòng đó không đồng nghĩa đang xóa qua iterator.

Nếu cần vừa duyệt vừa thêm/xóa tại vị trí con trỏ, một ListIterator do view cung cấp có thể phù hợp, miễn tuân theo vòng đời next/remove/add/set và khả năng của nguồn.

### 11.3. View lồng nhau cũng có vòng đời riêng

Có thể gọi subList trên một view. Chỉ số của view con được tính theo view cha, không trực tiếp theo nguồn gốc.

Trong ví dụ ArrayList tiếp theo, sửa qua view con cập nhật các view cha trong chuỗi đó và nguồn. Nhưng điều này không mở rộng thành bảo đảm mọi view anh em hoặc mọi view tạo riêng từ nguồn cũng còn hợp lệ.

Sau khi một view cha bị sửa cấu trúc bằng đường khác ngoài view con đang giữ, không tiếp tục dựa vào view con cũ. Khi có nhiều tầng view, cần quản lý rõ tầng nào còn được dùng sau mỗi thao tác.

## 12. Chương trình 5: sắp xếp khoảng, lọc, view con và ListIterator

Lưu vào `SubListRangeOperationsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.ListIterator;

public class SubListRangeOperationsDemo {
    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(9, 8, 7, 6, 5, 4));
        List<Integer> middle = source.subList(1, 5);
        Collections.sort(middle);
        System.out.println("sourceAfterRangeSort=" + source);
        middle.removeIf(value -> value % 2 == 0);
        System.out.println("sourceAfterRangeFilter=" + source);
        System.out.println("middleAfterFilter=" + middle);

        List<Integer> outer = source.subList(1, 3);
        List<Integer> inner = outer.subList(1, 2);
        inner.clear();
        System.out.println("sourceAfterInnerClear=" + source);
        System.out.println("outerAfterInnerClear=" + outer);
        System.out.println("innerAfterClear=" + inner);

        List<String> words = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> selected = words.subList(1, 3);
        ListIterator<String> cursor = selected.listIterator();
        System.out.println("cursorNext=" + cursor.next());
        cursor.remove();
        cursor.add("X");
        System.out.println("cursorNextAgain=" + cursor.next());
        cursor.set("C2");
        System.out.println("wordsAfterCursorEdits=" + words);
        System.out.println("selectedAfterCursorEdits=" + selected);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SubListRangeOperationsDemo.java
java SubListRangeOperationsDemo
```

Stdout:

```text
sourceAfterRangeSort=[9, 5, 6, 7, 8, 4]
sourceAfterRangeFilter=[9, 5, 7, 4]
middleAfterFilter=[5, 7]
sourceAfterInnerClear=[9, 5, 4]
outerAfterInnerClear=[5]
innerAfterClear=[]
cursorNext=B
cursorNextAgain=C
wordsAfterCursorEdits=[A, X, C2, D]
selectedAfterCursorEdits=[X, C2]
```

### 12.1. Chỉ khoảng giữa được sắp xếp và lọc

middle nhìn 8,7,6,5 trong nguồn 9,8,7,6,5,4. Sắp xếp qua middle làm nguồn thành `[9, 5, 6, 7, 8, 4]`: 9 và 4 ngoài khoảng không tham gia việc sắp xếp đó.

middle.removeIf loại số chẵn trong view, nên nguồn còn `[9, 5, 7, 4]`, middle còn `[5, 7]`. Đây là thay đổi cấu trúc thực hiện qua chính middle.

### 12.2. View con clear làm nguồn đổi

outer được tạo mới từ khoảng 5,7; inner nhìn phần tử 7 trong outer. inner.clear làm nguồn còn `[9, 5, 4]`, outer còn `[5]`, inner rỗng.

Những kết quả đó được kiểm tra trên chuỗi view ArrayList cụ thể. middle là một view tạo riêng trước đó, nên chương trình không dùng lại middle sau thay đổi cấu trúc qua inner. Không suy ra nó vẫn hợp lệ chỉ vì lúc trước nó cũng nhìn 5,7.

### 12.3. Sửa qua ListIterator của view

selected ban đầu nhìn B,C trong nguồn A,B,C,D. cursor.next lấy B, cursor.remove xóa B; cursor.add(X) chèn X tại vị trí con trỏ. Lần next tiếp theo lấy C, rồi cursor.set(C2) thay nó.

Nguồn thành `[A, X, C2, D]`, selected thành `[X, C2]`. Mã dùng các thao tác của chính cursor trong suốt phép duyệt; không xen một lệnh selected.add hoặc words.remove từ đường khác.

Không cần thêm một bản sao chỉ để thực hiện thao tác theo khoảng ngay trên nguồn, nếu chủ đích là sửa nguồn và vòng đời view được kiểm soát.

## 13. Chọn view hoặc bản sao theo thời gian sử dụng

### 13.1. View phù hợp khi muốn thao tác trực tiếp một khoảng

Ví dụ, cần xóa một khoảng một lần trong danh sách sửa được. Đoạn sau là minh họa đặt trong phương thức đã có items, start, end hợp lệ; nó không phải tệp Java độc lập:

```java
items.subList(start, end).clear();
```

Tác dụng là xóa ngay khoảng đó khỏi items. Không giữ thêm một view lâu dài nếu chỉ cần một thao tác khoảng duy nhất.

Một view ngắn hạn cũng phù hợp để tìm kiếm hay sắp xếp riêng một đoạn, khi tất cả đường sửa nguồn được phối hợp.

### 13.2. Bản sao phù hợp khi cần kết quả sống độc lập với cấu trúc nguồn

Nếu trả một phần dữ liệu cho nơi khác lưu giữ, trong khi nguồn còn tiếp tục thêm/xóa, nên cân nhắc một bản sao theo yêu cầu quyền sửa.

Đoạn minh họa dưới đây cần đặt trong phương thức có source, start, end và import ArrayList/List:

```java
List<String> result = new ArrayList<>(source.subList(start, end));
```

Chọn List.copyOf cho kết quả không cho sửa khi các phần tử không null. Cả hai lựa chọn vẫn cần giải quyết sao chép sâu riêng nếu trạng thái của phần tử có thể thay đổi.

Không có lựa chọn đúng chỉ theo tên “subList nhanh hơn”. Quyết định phải xét việc người nhận có muốn sửa nguồn không, nguồn có còn bị sửa ngoài view không và kết quả cần tồn tại bao lâu.

### 13.3. Đừng giữ một view nhỏ với giả định đã cắt rời nguồn lớn

View có thể còn giữ quan hệ tham chiếu tới cấu trúc nguồn. Một view chỉ vài phần tử không đồng nghĩa phần dữ liệu ngoài khoảng chắc chắn đã không còn được giữ sống.

Nếu cần một tập phần tử lưu lâu độc lập về cấu trúc chứa, tạo bản sao là cách thể hiện rõ ý định hơn. Dù vậy, các phần tử được chọn vẫn có thể tham chiếu tiếp đến những đối tượng khác; sao chép nông không tự giải quyết mọi quan hệ bộ nhớ trong đồ thị đối tượng.

### 13.4. Xử lý sau khi đã sửa cấu trúc nguồn bên ngoài

Dừng dùng view cũ. Nếu vẫn cần một khoảng của nguồn hiện tại, tính lại cận và tạo view mới hoặc bản sao mới từ nguồn hiện tại.

Cần phân biệt “cùng chỉ số hiện tại” với “cùng nhóm đối tượng cũ”. Sau khi nguồn bị thêm/xóa, giữ nguyên hai con số from/to có thể chọn dữ liệu khác trước.

Không catch ConcurrentModificationException rồi tiếp tục đọc view cũ. Cũng không catch rồi cố copy chính view đó để chữa lỗi: bản sao phải đọc dữ liệu hợp lệ mới có ý nghĩa.

## 14. Lỗi phổ biến và tiêu chí kiểm tra

| Lỗi | Hậu quả hoặc cách hiểu sai | Cách xử lý |
|---|---|---|
| Nghĩ subList là bản sao | Sửa view vô tình sửa nguồn | Chọn bản sao nếu cần cấu trúc độc lập |
| Nhầm toIndex được lấy vào khoảng | Lệch một phần tử | Dùng khoảng nửa mở [from,to) |
| Dùng chỉ số nguồn để remove trong view | Xóa sai phần tử hoặc vượt cận | Tính chỉ số tương đối của view |
| source.add ở ngoài khoảng rồi dùng view cũ | Hợp đồng view không còn được bảo đảm | Dừng dùng view, tạo kết quả mới từ nguồn hiện tại |
| Xóa rồi thêm lại cho size bằng cũ | Lịch sử sửa cấu trúc vẫn đã thay đổi | Không coi size là cách khôi phục view |
| Sửa qua view thứ nhất rồi dùng tiếp view anh em | View thứ hai không tự đồng bộ hợp lệ | Phối hợp vòng đời hoặc dùng bản sao |
| Nghĩ chỉ đa luồng mới có ConcurrentModificationException | Bỏ sót lỗi do nhiều tham chiếu trong cùng luồng | Kiểm tra mọi đường sửa cấu trúc |
| Mong chắc chắn luôn có ngoại lệ ngay khi sửa nguồn | Fail-fast không phải bảo đảm cho mọi trường hợp | Tránh cách dùng sai theo hợp đồng |
| Bọc unmodifiable để làm view độc lập | Wrapper vẫn dựa trên dữ liệu bên dưới | Dùng copy phù hợp nếu cần độc lập |
| Dùng List.copyOf cho khoảng có null | NullPointerException | Chọn chính sách null rõ ràng hoặc ArrayList khi phù hợp |
| Coi bản sao nông là sao chép sâu | Sửa đối tượng phần tử vẫn ảnh hưởng nơi khác | Thiết kế cách sao chép phần tử |
| add/remove trên view của Arrays.asList | Nguồn không hỗ trợ đổi kích thước | Tạo ArrayList nếu cần danh sách sửa kích thước được |
| Đổi cấu trúc nguồn qua view rồi dùng iterator nguồn cũ | Iterator có thể mất hiệu lực | Quản lý vòng đời iterator riêng |
| Vừa duyệt bằng iterator vừa sửa qua đường khác | Vi phạm chính sách sửa trong phép duyệt | Dùng đúng thao tác của iterator hoặc đổi cách xử lý |

Một bộ kiểm tra có ích nên bao gồm khoảng đầu/giữa/cuối, khoảng rỗng, nguồn chỉ có một phần tử, set từ hai phía, thêm/xóa/clear qua view, sửa nguồn bên ngoài, view anh em, các quyền sửa khác nhau và bản sao nông.

Khi kiểm tra dữ liệu nguồn sau mỗi thao tác, đừng vô tình đọc lại một view đã mất hiệu lực chỉ để in tiến độ. Ngay cả toString của một view cũ cũng không phải phép quan sát được miễn khỏi hợp đồng.

## 15. Tự kiểm tra và thực hành

### 15.1. Câu hỏi với đáp án

1. **subList(1,4) lấy bao nhiêu phần tử ban đầu?** Ba phần tử ở chỉ số nguồn 1,2,3.
2. **View có chỉ số bắt đầu từ fromIndex không?** Không. View đánh chỉ số lại từ 0.
3. **view.set thay nguồn không?** Có, khi thao tác được nguồn hỗ trợ và view còn hợp lệ; vị trí tương ứng trong nguồn được thay.
4. **source.set trong khoảng có thể phản ánh lên view không?** Có. Với ArrayList, thay phần tử tại vị trí có sẵn không phải thêm/xóa cấu trúc.
5. **view.add có luôn gây lỗi vì làm đổi size nguồn không?** Không. Trên nguồn hỗ trợ, thêm qua view có thể là thao tác hợp lệ và cập nhật kích thước view.
6. **source.add ở cuối ngoài khoảng có bảo đảm view cũ vẫn dùng được không?** Không. Đó vẫn là sửa cấu trúc ngoài đường view.
7. **Hai view không chồng lấn có thể dùng tiếp độc lập sau một view xóa phần tử không?** Không có bảo đảm như vậy; view còn lại có nguồn bị sửa qua đường khác.
8. **ConcurrentModificationException có chứng minh phải có nhiều luồng không?** Không. Một luồng với nhiều tham chiếu cũng có thể gây tình huống đó.
9. **Copy sau khi view đã lỗi có phải cách sửa không?** Không. Phải tạo bản sao từ dữ liệu còn hợp lệ, thường trước khi nguồn tiếp tục bị sửa cấu trúc.
10. **new ArrayList<>(view) có sao chép sâu StringBuilder không?** Không. Nó sao chép tham chiếu phần tử.
11. **subList(size,size) có hợp lệ không?** Có, đó là khoảng rỗng ở cuối nguồn nếu size được lấy trong ngữ cảnh còn hợp lệ.
12. **View của Arrays.asList có set được nhưng add không được không?** Có. Kích thước cố định khác với cấm mọi thao tác sửa.

### 15.2. Bài tập: tính chỉ số và tác dụng lên nguồn

Tạo ArrayList số 0,1,2,3,4,5; lấy view bằng subList(2,5). Dự đoán rồi chạy view.remove(1), view.add(0,9), view.clear.

Kỳ vọng: view ban đầu là 2,3,4. Xóa chỉ số view 1 làm nguồn còn 0,1,2,4,5. Thêm 9 ở đầu view làm nguồn thành 0,1,9,2,4,5. Clear view sau đó làm nguồn còn 0,1,5.

Giải thích vì sao remove(1) xóa số 3 chứ không phải số 1.

### 15.3. Bài tập: tách lỗi quyền và lỗi vòng đời

Tạo ba nguồn riêng: ArrayList sửa được, Arrays.asList và List.of. Với mỗi nguồn, lấy cùng khoảng không rỗng rồi thử set, add, clear trên view trong các phép thử độc lập.

Với ArrayList khác, tạo view rồi sửa cấu trúc trực tiếp nguồn và ngừng dùng view cũ trong mã đúng. Có thể viết một phép minh họa lỗi riêng để quan sát trên JDK đang dùng, nhưng không biến loại/thời điểm ngoại lệ thành bảo đảm chung cho List.

Kết quả cần trình bày theo hai trục: quyền thao tác của nguồn và tính hợp lệ của view tại thời điểm gọi.

### 15.4. Bài tập: thiết kế kết quả trả về

Một phương thức nhận List<String> và chọn một khoảng để trả về cho nơi gọi lưu lâu. Nguồn sẽ còn được thêm/xóa sau khi phương thức kết thúc.

Hãy chọn giữa subList, new ArrayList<>(subList) và List.copyOf(subList), rồi nêu rõ quyền sửa kết quả và chính sách null. Nếu cần kết quả độc lập về cấu trúc, không trả trực tiếp view.

Đổi kiểu phần tử sang một đối tượng có trạng thái có thể thay đổi. Nêu thêm điều gì còn chưa được giải quyết bởi bản sao nông.

## 16. Nguồn đối chiếu và phạm vi kiểm chứng

- [List — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): hợp đồng subList, khoảng nửa mở, thay đổi cấu trúc nguồn bên ngoài và copyOf.
- [ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): khả năng sửa, cận subList, thay đổi cấu trúc và giới hạn fail-fast.
- [AbstractList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html): một cơ chế view dựa trên độ lệch, kích thước và số lần sửa đổi dự kiến.
- [Arrays — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): List kích thước cố định được hỗ trợ bởi mảng từ asList.
- [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): wrapper unmodifiableList và các thuật toán nhận List.

Năm chương trình đầy đủ đã biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên Corretto JDK 17.0.15, cho đúng stdout được ghi. Các ngoại lệ ConcurrentModificationException trong chương trình minh họa lỗi là quan sát trên ArrayList của môi trường đó; quy tắc sử dụng đúng vẫn là tránh sửa cấu trúc nguồn bên ngoài view đang dùng. Hai đoạn ở phần lựa chọn view/bản sao được đánh dấu là minh họa, cần đặt trong phương thức có biến và import phù hợp.
