# Giới hạn của lớp bọc khi collection gốc vẫn có thể bị sửa trực tiếp

## 1. Lớp bọc thường là một view, không phải bản sao

Các tiện ích như `Collections.unmodifiableList`, `synchronizedList` và `checkedList` tạo một lớp bọc quanh collection khác. Collection bên trong thường được gọi là collection nền hoặc backing collection.

Có thể hình dung:

```text
tham chiếu gốc ────────────────┐
                             ▼
                       collection nền
                             ▲
tham chiếu lớp bọc ── quy tắc của lớp bọc
```

Hai tham chiếu có thể đi tới cùng dữ liệu. Lớp bọc áp dụng quy tắc cho các thao tác đi qua nó; nó không tự thu hồi những tham chiếu khác đã được chia sẻ.

Vì vậy, cần phân biệt:

- Quyền thao tác qua một tham chiếu.
- Khả năng thay đổi dữ liệu qua mọi tham chiếu đang tồn tại.
- Việc collection có sao chép cấu trúc hay không.
- Việc các đối tượng phần tử có thể thay đổi hay không.

Những cơ chế này vẫn được sử dụng trong Java hiện đại. Bài dùng ví dụ Java 17+.

## 2. Ba loại lớp bọc và đường truy cập có thể đi vòng

| Lớp bọc | Quy tắc khi đi qua lớp bọc | Điều không tự được bảo đảm |
| --- | --- | --- |
| `unmodifiable...` | Chặn thao tác sửa qua view | Collection nền không bị bên khác sửa |
| `synchronized...` | Đồng bộ các thao tác theo giao thức của wrapper | Truy cập trực tiếp nền cũng tuân theo cùng khóa |
| `checked...` | Kiểm tra kiểu động ở các điểm thêm/thay thế phù hợp | Nội dung không bị chèn sai qua tham chiếu nền khác |

Không nên coi một wrapper là “rào chắn toàn cục” bao quanh đối tượng gốc. Nó là một đường truy cập có thêm hành vi.

Chất lượng bảo vệ phụ thuộc vào việc ứng dụng còn để lộ những đường truy cập nào khác.

## 3. Unmodifiable view vẫn thấy thay đổi ở collection nền

Ví dụ:

```java
List<String> source = new ArrayList<>();
source.add("A");

List<String> view = Collections.unmodifiableList(source);
source.add("B");
```

Lúc này view nhìn thấy `[A, B]`. View không phải snapshot của source tại thời điểm tạo.

Lời gọi `view.add("C")` bị chặn bằng UnsupportedOperationException, nhưng `source.add("B")` vẫn hợp lệ vì đi qua tham chiếu gốc.

Đây có thể là thiết kế có chủ ý: bên đọc nhận một view chỉ đọc của dữ liệu được chủ sở hữu cập nhật. Nhưng nếu hợp đồng nói “danh sách cố định tại thời điểm trả về”, unmodifiable view của một nguồn còn thay đổi không đáp ứng hợp đồng đó.

Thay đổi nền trong khi duyệt view cũng có thể làm iterator mất tính hợp lệ. Iterator của view không tạo một bản chụp độc lập; không dựa vào ConcurrentModificationException như một cam kết phát hiện mọi thay đổi đồng thời.

## 4. Snapshot cấu trúc khác với bất biến sâu

Nếu cần một danh sách tách khỏi các thay đổi cấu trúc về sau của source, có thể dùng:

```java
List<String> snapshot = List.copyOf(source);
```

Snapshot không phản chiếu việc source thêm, xóa hoặc thay một vị trí về sau. List.copyOf có thể tái sử dụng một đối tượng list phù hợp trong một số trường hợp; điều quan trọng là hợp đồng kết quả, không phải bảo đảm tạo một instance mới ở mọi lời gọi.

Tuy vậy, đó vẫn là sao chép nông đối với phần tử. Nếu phần tử là một StringBuilder hoặc đối tượng nghiệp vụ có thể sửa, list snapshot có thể giữ cùng tham chiếu phần tử với source.

Muốn dữ liệu trả ra bất biến sâu phải có chính sách riêng, chẳng hạn dùng phần tử bất biến hoặc sao chép đúng các đối tượng có thể thay đổi. Chỉ bọc hoặc sao chép cấu trúc list chưa đủ.

Ngoài ra, List.copyOf không cho phép phần tử null. Nếu cần giữ null và vẫn muốn bản sao cấu trúc có view không sửa được, có thể cân nhắc:

```java
List<String> snapshot =
        Collections.unmodifiableList(new ArrayList<>(source));
```

Bản sao ArrayList bên trong phải không bị lộ ra ngoài. Các phần tử vẫn là sao chép nông.

## 5. Chương trình đầy đủ: view, snapshot và phần tử dùng chung

Lưu thành `CollectionWrapperLimitsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CollectionWrapperLimitsDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.add("C");
        } catch (UnsupportedOperationException exception) {
            System.out.println("view write=blocked");
        }

        StringBuilder shared = new StringBuilder("item");
        List<StringBuilder> items = new ArrayList<>();
        items.add(shared);

        List<StringBuilder> itemView =
                Collections.unmodifiableList(items);
        List<StringBuilder> itemSnapshot = List.copyOf(items);

        shared.append("-changed");

        System.out.println("element view=" + itemView);
        System.out.println("element snapshot=" + itemSnapshot);

        demonstrateCheckedBypass();
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void demonstrateCheckedBypass() {
        List<String> original = new ArrayList<>();
        List<String> checked =
                Collections.checkedList(original, String.class);

        checked.add("ok");

        List rawChecked = checked;
        try {
            rawChecked.add(Integer.valueOf(42));
        } catch (ClassCastException exception) {
            System.out.println("checked path=blocked");
        }

        List rawOriginal = original;
        rawOriginal.add(Integer.valueOf(42));
        System.out.println("checked size=" + checked.size());

        try {
            String value = checked.get(1);
            System.out.println("unexpected value=" + value);
        } catch (ClassCastException exception) {
            System.out.println("typed read=ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 CollectionWrapperLimitsDemo.java
java CollectionWrapperLimitsDemo
```

Kết quả:

```text
source=[A, B]
view=[A, B]
snapshot=[A]
view write=blocked
element view=[item-changed]
element snapshot=[item-changed]
checked path=blocked
checked size=2
typed read=ClassCastException
```

Phần dùng raw type cố ý tái hiện một đường truy cập không an toàn để thấy giới hạn của checked wrapper. Cảnh báo chỉ được tắt trong phương thức minh họa đó; đây không phải hướng dẫn dùng raw type trong mã mới.

Kết quả cho thấy checked wrapper chặn phần tử sai kiểu khi thêm qua chính wrapper, nhưng không thể chặn lệnh ghi trực tiếp vào original. Lỗi bộc lộ khi bên đọc tin rằng phần tử là String.

## 6. Checked wrapper không tự làm sạch dữ liệu đã có

Checked wrapper hữu ích khi muốn phát hiện lỗi kiểu gần nơi ghi, nhất là tại ranh giới với mã không bảo đảm generic. Nhưng có hai giới hạn:

1. Collection nền đã phải đáp ứng giả định về kiểu khi tạo wrapper.
2. Từ thời điểm đó, mọi thay đổi cần đi qua đường có kiểm tra.

Không dùng checkedList để kết luận một collection đã có nội dung tùy ý sẽ tự được quét, chuyển đổi hoặc làm sạch.

Nó cũng không xác thực mọi điều kiện nghiệp vụ. Một String rỗng vẫn là String; kiểm tra Class không thay thế quy tắc tên hợp lệ, phạm vi số hoặc tính duy nhất của mã.

Với generic lồng nhau, Class ở runtime còn không mô tả đầy đủ các tham số kiểu đã bị xóa. Không coi checked wrapper là bộ kiểm tra sâu tự động cho mọi List<List<String>> hoặc đồ thị dữ liệu.

## 7. Synchronized wrapper cần mọi bên dùng cùng giao thức

Ví dụ:

```java
List<String> original = new ArrayList<>();
List<String> shared = Collections.synchronizedList(original);
```

Nếu mọi bên chỉ sử dụng shared theo hợp đồng của lớp bọc, các thao tác được đồng bộ hóa theo giao thức đó.

Nhưng nếu một luồng gọi `shared.add(...)` trong khi luồng khác gọi `original.add(...)` không cùng khóa, lớp bọc không ngăn được race condition. Cấu trúc nền vẫn bị sửa từ bên ngoài cơ chế bảo vệ.

Duyệt bằng iterator, spliterator hoặc stream cần tuân theo hướng dẫn khóa của synchronized wrapper. Ví dụ với iterator:

```java
synchronized (shared) {
    for (String value : shared) {
        System.out.println(value);
    }
}
```

Đoạn này minh họa giao thức đúng cho việc duyệt. Nó không biến các truy cập original không tuân khóa ở nơi khác thành an toàn.

Cũng không tạo hai wrapper độc lập rồi giả định chúng dùng chung khóa chỉ vì cùng bọc một collection:

```java
List<String> first = Collections.synchronizedList(original);
List<String> second = Collections.synchronizedList(original);
```

Hai đường truy cập có monitor khác nhau theo cách sử dụng thông thường. Khóa first không tự loại trừ thao tác qua second. Tốt hơn là chỉ tạo và chia sẻ một wrapper chính thức, đồng thời giữ nền không bị lộ.

## 8. Nhiều lớp bọc không tự loại bỏ tham chiếu cùng nguồn cũ

Ví dụ:

```java
List<String> checked =
        Collections.checkedList(original, String.class);
List<String> readOnly =
        Collections.unmodifiableList(checked);
```

Qua readOnly, thao tác thêm bị chặn. Qua checked, thao tác ghi hợp lệ vẫn có thể sửa nền. Qua original, các quy tắc của cả hai wrapper có thể bị đi vòng.

Thứ tự ghép wrapper có thể ảnh hưởng hành vi mà bên gọi quan sát và giao thức khóa cần dùng. Khi một wrapper đồng bộ bị đặt bên trong wrapper khác, không nên tùy tiện khóa đối tượng ngoài rồi coi đó là monitor mà wrapper trong dùng.

Thay vì ghép nhiều lớp rồi trông chờ một sự bảo vệ không được công bố, hãy thiết kế rõ:

- Ai giữ collection nền?
- Ai được cập nhật?
- Ai chỉ được quan sát?
- Tham chiếu nào được chia sẻ?
- Thao tác nhiều bước nào cần nguyên tử?
- Bản sao được tạo ở thời điểm nào và dưới giao thức nào?

## 9. Bảo vệ biên giới API bằng quyền sở hữu dữ liệu rõ ràng

Một cách thực tế:

1. Giữ collection nội bộ private.
2. Không trả tham chiếu nền cho bên ngoài.
3. Nếu cho phép cập nhật, cung cấp các phương thức miền có kiểm tra và giao thức đồng bộ phù hợp.
4. Nếu trả live view, công bố rằng view phản chiếu cập nhật.
5. Nếu trả snapshot, sao chép cấu trúc và xem xét tính thay đổi của phần tử.
6. Nếu nhận collection từ bên gọi, cân nhắc sao chép phòng vệ thay vì giữ trực tiếp một đối tượng mà bên gọi vẫn sửa được.

Ví dụ constructor giữ `Collections.unmodifiableList(input)` vẫn cho bên gọi sửa input và làm thay đổi dữ liệu bên trong lớp. Nếu hợp đồng yêu cầu trạng thái tách biệt, cần sao chép phù hợp lúc nhận dữ liệu.

Ngay cả bước sao chép cũng không tự là snapshot nguyên tử nếu một luồng khác đang sửa nguồn. Với dữ liệu chia sẻ, việc chụp bản sao phải diễn ra theo cơ chế đồng bộ hoặc hợp đồng snapshot của nguồn.

## 10. Những hiểu nhầm thường gặp

| Hiểu nhầm | Điều thực tế |
| --- | --- |
| Unmodifiable có nghĩa không ai sửa được dữ liệu | Chỉ chặn thao tác sửa qua view đó |
| Có snapshot list là mọi phần tử bất biến | Phần tử có thể vẫn được dùng chung |
| Synchronized wrapper bảo vệ mọi tham chiếu cùng nguồn của nền | Các tham chiếu cùng nguồn khác phải tuân cùng giao thức |
| Checked wrapper bảo đảm không bao giờ có sai kiểu | Đường ghi vào nền có thể phá giả định |
| Bọc thêm một lớp sẽ thu hồi quyền của tham chiếu cùng nguồn cũ | Tham chiếu cũ vẫn tồn tại và vẫn có khả năng thao tác |
| Copy collection là tự động an toàn khi có luồng sửa nguồn | Cần cơ chế chụp nhất quán phù hợp |

## 11. Thực hành

1. Trong chương trình, thêm lời gọi source.set(0, ...) sau khi tạo view và snapshot. Dự đoán bên nào nhìn thấy thay đổi vị trí.
2. Thay StringBuilder bằng một lớp bất biến, rồi giải thích tại sao sao chép nông có thể đủ cho hợp đồng đó.
3. Loại bỏ rawOriginal khỏi ví dụ checked wrapper. Giải thích điều kiện nào giúp kiểm tra kiểu động giữ được giả định.
4. Vẽ các tham chiếu cùng nguồn của một collection trong API của mình; đánh dấu đường nào đi qua kiểm tra/khóa và đường nào đi vòng.
5. Với mỗi phương thức trả collection, ghi rõ nó trả live view hay snapshot và phần tử có được chia sẻ hay không.

## Tài liệu đối chiếu

- [Collections — Unmodifiable, synchronized và checked wrappers](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).
- [List.copyOf — Danh sách không sửa được và quan hệ với nguồn](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
