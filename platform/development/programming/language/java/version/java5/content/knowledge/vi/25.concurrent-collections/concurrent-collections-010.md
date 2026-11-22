# Iterator ảnh chụp của collection copy-on-write

Giả sử ứng dụng đang duyệt danh sách bên nhận thông báo, trong khi một luồng khác thêm hoặc gỡ một bên nhận. Ta muốn lượt duyệt tiếp tục với một danh sách ổn định, không phải khóa danh sách trong suốt thời gian gọi các bên nhận.

`CopyOnWriteArrayList` và `CopyOnWriteArraySet` hỗ trợ kiểu duyệt **ảnh chụp (snapshot iterator)**: iterator giữ một phiên bản cấu trúc collection tại lúc nó được tạo. Việc sửa collection sau đó không làm iterator đang có đổi sang phiên bản mới.

Bảo đảm này vẫn áp dụng trong Java hiện đại. Điều cần đánh đổi là chi phí các lần ghi và việc iterator có thể cố ý nhìn dữ liệu thành viên cũ.

## 1. Ảnh chụp được xác lập lúc nào?

Mốc quan trọng là lúc gọi `iterator()` hoặc `listIterator()`, không phải lúc bắt đầu gọi `next()`.

```text
T0: list chứa [A, B, C]
T1: tạo iterator I1
T2: xóa B, thay A bằng A2, thêm D vào list
T3: list hiện tại là [A2, C, D]
T4: I1 vẫn duyệt [A, B, C]
T5: tạo I2; I2 duyệt [A2, C, D]
```

Nếu việc tạo iterator chạy đồng thời với một cập nhật, không nên dự đoán trước nó sẽ bắt được phiên bản trước hay sau cập nhật chỉ từ thứ tự các dòng log. Sau khi đã nhận một phiên bản, lượt duyệt giữ phiên bản đó.

Trong vòng `for-each`, iterator được tạo khi bước vào vòng duyệt. Một lần `for-each` mới có thể thấy phiên bản mới hơn lần trước.

## 2. Vì sao sửa collection không phá lượt duyệt?

`CopyOnWriteArrayList` dùng một mảng nền. Khi cần cập nhật cấu trúc hoặc thay phần tử, lớp công bố một phiên bản mảng mới thay vì sửa phiên bản mà iterator cũ đang dùng.

Iterator giữ tham chiếu tới phiên bản đã nhận. Vì mảng phiên bản đó không bị đổi bởi các lần cập nhật collection sau này, iterator không cần chờ bên ghi chỉ để đi qua các phần tử của ảnh chụp.

Điểm dễ nhầm: **không phải mỗi lần gọi `iterator()` đều sao chép sâu toàn bộ danh sách**. Mô hình là giữ tham chiếu tới phiên bản mảng hiện hữu; chi phí sao chép gắn chủ yếu với các cập nhật. Hợp đồng được mô tả tại [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

`CopyOnWriteArraySet` dùng một `CopyOnWriteArrayList` nội bộ, nên iterator cũng dựa trên ảnh chụp mảng tại lúc tạo. Nó giữ ngữ nghĩa tập hợp không trùng, khác với danh sách cho phép phần tử lặp. [CopyOnWriteArraySet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CopyOnWriteArraySet.html).

## 3. Điều gì được nhìn thấy và không được nhìn thấy?

| Thay đổi sau khi iterator được tạo | Iterator cũ | Iterator tạo sau thay đổi |
|---|---|---|
| Thêm D | Không thấy D | Thấy D theo phiên bản mới |
| Xóa B | Vẫn có thể trả B từ ảnh chụp cũ | Không còn B |
| `set` vị trí của A thành A2 | Vẫn trả tham chiếu A cũ | Trả tham chiếu A2 mới |
| Sửa trường bên trong đối tượng A | Không phải ảnh chụp sâu của trường đó | Cũng cần tuân thủ hợp đồng đồng bộ hóa của đối tượng |

Ảnh chụp ổn định là ảnh chụp **các vị trí/tham chiếu thành viên**, không phải đóng băng toàn bộ đồ thị đối tượng.

Ví dụ một phần tử `Box` có trường `value`: iterator giữ cùng tham chiếu tới `Box`, nên một lần sửa trường không tạo ra `Box` cũ riêng cho iterator. Nếu đọc và sửa trường ở nhiều luồng, cần cơ chế đồng bộ hóa thích hợp; không được suy ra giá trị chắc chắn mới nhất chỉ vì collection là copy-on-write.

Với phần tử bất biến như `String`, người đọc thường dễ coi nội dung là ổn định hơn vì bản thân đối tượng cũng không thay đổi.

## 4. Chương trình chạy đầy đủ

Lưu thành `SnapshotIteratorDemo.java`. Ví dụ dùng một luồng ghi và chờ nó kết thúc trước khi in để mốc phiên bản và stdout rõ ràng.

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.concurrent.CopyOnWriteArrayList;

public class SnapshotIteratorDemo {
    static <E> List<E> collect(Iterator<E> iterator) {
        List<E> result = new ArrayList<>();
        while (iterator.hasNext()) {
            result.add(iterator.next());
        }
        return result;
    }

    static class Box {
        int value;
        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>(List.of("A", "B", "C"));
        Iterator<String> oldIterator = names.iterator();
        ListIterator<String> oldCursor = names.listIterator();

        Thread writer = new Thread(() -> {
            names.remove("B");
            names.set(0, "A2");
            names.add("D");
        }, "writer");
        writer.start();
        writer.join();

        System.out.println("old iterator: " + collect(oldIterator));
        System.out.println("current list: " + names);
        System.out.println("new iterator: " + collect(names.iterator()));
        System.out.println("old list iterator first: " + oldCursor.next());

        try {
            oldCursor.set("X");
        } catch (UnsupportedOperationException e) {
            System.out.println("listIterator.set: unsupported");
        }
        try {
            oldCursor.add("Y");
        } catch (UnsupportedOperationException e) {
            System.out.println("listIterator.add: unsupported");
        }
        try {
            oldCursor.remove();
        } catch (UnsupportedOperationException e) {
            System.out.println("iterator.remove: unsupported");
        }

        Box box = new Box(7);
        CopyOnWriteArrayList<Box> boxes =
                new CopyOnWriteArrayList<>(List.of(box));
        Iterator<Box> shallowSnapshot = boxes.iterator();
        box.value = 9; // Same thread: no concurrent field access in this demo.
        System.out.println("value through snapshot: "
                + shallowSnapshot.next().value);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 SnapshotIteratorDemo.java
java SnapshotIteratorDemo
```

Stdout:

```text
old iterator: [A, B, C]
current list: [A2, C, D]
new iterator: [A2, C, D]
old list iterator first: A
listIterator.set: unsupported
listIterator.add: unsupported
iterator.remove: unsupported
value through snapshot: 9
```

Giải thích:

1. Cả `oldIterator` và `oldCursor` được tạo trước khi luồng ghi chạy, nên giữ phiên bản `[A, B, C]`.
2. Sau `writer.join()`, luồng ghi đã hoàn tất và không còn bên khác sửa danh sách trong ví dụ. Danh sách hiện tại và iterator mới đều cho `[A2, C, D]`.
3. `oldCursor.next()` vẫn trả A, dù danh sách hiện tại đã thay vị trí đầu thành A2.
4. Các phương thức sửa thông qua iterator ném `UnsupportedOperationException`. Lỗi này khác `ConcurrentModificationException`; nó báo thao tác không được hỗ trợ.
5. `box.value = 9` và lần đọc tiếp theo đều ở luồng chính. Kết quả 9 chứng minh ảnh chụp không sao chép sâu `Box`, không phải một thí nghiệm về đọc/ghi trường thiếu đồng bộ giữa các luồng.

`join()` trong ví dụ giúp sắp mốc để quan sát rõ kết quả cuối của bên ghi. Bảo đảm iterator ảnh chụp không phụ thuộc việc bắt buộc chờ bên ghi xong mới được duyệt; nó cho phép lượt duyệt diễn ra đồng thời với các cập nhật.

## 5. Iterator chỉ đọc, collection vẫn có thể sửa

Trong `Iterator`, `remove()` là thao tác tùy chọn. `ListIterator` cũng có các thao tác tùy chọn `remove`, `set`, `add`; sự hiện diện của phương thức trên giao diện không có nghĩa mọi iterator đều hỗ trợ. Xem [Iterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html) và [ListIterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ListIterator.html).

Với iterator của collection copy-on-write:

- `Iterator.remove()` không được hỗ trợ.
- `ListIterator.remove()`, `set(...)`, `add(...)` không được hỗ trợ.
- Việc duyệt tới/lùi và đọc vị trí của `ListIterator` vẫn theo ảnh chụp mà nó giữ.

Muốn cập nhật, gọi phương thức trên collection hiện tại, chẳng hạn `list.remove(value)`, `list.add(value)` hoặc một thao tác hàng loạt phù hợp. Iterator cũ vẫn tiếp tục trên phiên bản cũ.

Không giả định chỉ số từ iterator cũ còn chỉ đúng phần tử trên danh sách hiện tại. Nếu một luồng đã thêm/xóa phía trước, `list.remove(index)` tính theo phiên bản mới có thể loại phần tử khác. Khi cần cập nhật một phần tử xác định, dùng định danh ổn định và giao thức kiểm tra điều kiện phù hợp thay vì dùng chỉ số cũ như một quyền giữ chỗ.

Nếu cần lọc nhiều phần tử, xem xét `removeIf` trên chính collection thay cho việc xóa từng phần tử trong vòng lặp. Điều này vẫn phải có nghĩa nghiệp vụ rõ ràng đối với trạng thái collection hiện tại và chi phí cập nhật.

## 6. Phân biệt ba kiểu iterator

| Kiểu duyệt | Ví dụ thường gặp | Khi collection đổi sau lúc tạo iterator |
|---|---|---|
| Phát hiện sửa đổi (fail-fast) | Iterator của `ArrayList` | Có thể phát hiện sửa cấu trúc và ném `ConcurrentModificationException`; không phải cơ chế đồng bộ hóa |
| Ảnh chụp | Iterator của `CopyOnWriteArrayList`/`Set` | Tiếp tục phiên bản cấu trúc lúc tạo, không thấy cập nhật collection sau đó |
| Yếu nhất quán (weakly consistent) | Nhiều collection đồng thời như `ConcurrentHashMap` | Có thể phản ánh một số cập nhật; không hứa một phiên bản cấu trúc cố định tại lúc tạo |

Đặc tính fail-fast được mô tả tại [ArrayList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html); đặc tính duyệt yếu nhất quán được tổng hợp tại [java.util.concurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html).

Điểm phân biệt không chỉ là “có ném ngoại lệ hay không”. Snapshot và weakly consistent đều có thể duyệt cùng lúc với cập nhật nhưng cung cấp ngữ nghĩa quan sát khác nhau.

Không xem việc không ném `ConcurrentModificationException` là chứng minh toàn bộ ứng dụng nhất quán. Một ảnh chụp của danh sách người nhận không tự là ảnh chụp đồng bộ với một bản đồ quyền hạn hoặc cấu hình khác đang thay đổi.

Ảnh chụp cũng không làm trạng thái con trỏ của cùng một iterator thành cơ chế chia việc cho nhiều luồng. Cách dùng dễ kiểm soát là mỗi lượt duyệt sở hữu iterator riêng.

## 7. Ứng dụng: danh sách bên nhận sự kiện

Copy-on-write thường phù hợp khi danh sách ít thay đổi nhưng được duyệt rất nhiều, chẳng hạn danh sách bên nhận sự kiện. Ý nghĩa mong muốn có thể là:

```text
Bắt đầu gửi một sự kiện → xác lập tập bên nhận cho lượt gửi đó.
Thêm/gỡ bên nhận trong lúc gửi → có hiệu lực ở các lượt duyệt sau.
```

Đoạn minh họa trong một lớp đã có collection và kiểu `Listener`:

```java
for (Listener listener : listeners) {
    listener.onEvent(event);
}
```

Nếu một bên nhận bị gỡ sau lúc iterator đã được tạo, nó vẫn có thể nhận sự kiện của lượt hiện tại. Đây là hệ quả có chủ đích của snapshot, không phải lỗi bộ nhớ.

Nếu yêu cầu nghiệp vụ là “sau khi lệnh gỡ trả về, tuyệt đối không được có bất kỳ callback nào tới bên nhận đó”, chỉ xóa khỏi collection copy-on-write chưa đủ. Cần giao thức bổ sung để phối hợp lượt gửi đang chạy, trạng thái kích hoạt hoặc thời điểm hoàn tất hủy đăng ký.

Tương tự, một bên nhận mới thêm giữa lượt gửi có thể bắt đầu nhận từ lượt sau. Hãy chọn kiểu collection khi ngữ nghĩa này phù hợp, không chỉ vì nó tránh ngoại lệ.

## 8. Chi phí sao chép và giữ phiên bản cũ

Copy-on-write chuyển chi phí sang phía ghi: những cập nhật làm thay đổi nội dung thường cần tạo và công bố mảng mới. Nếu danh sách lớn và bị thêm/xóa thường xuyên, tổng cấp phát, sao chép và thu gom rác có thể cao.

Iterator tồn tại lâu có thể tiếp tục giữ mảng phiên bản cũ cùng các tham chiếu phần tử trong mảng đó. Một phần tử đã bị xóa khỏi danh sách hiện tại chưa chắc được thu gom ngay nếu vẫn còn được giữ bởi ảnh chụp hoặc tham chiếu khác.

Ví dụ suy luận:

```text
I1 giữ phiên bản V1.
Bên ghi tạo V2, V3, V4.
Collection hiện tại dùng V4, nhưng I1 vẫn cần V1 để duyệt.
```

Không phải toàn bộ V2/V3 bắt buộc còn sống; phiên bản nào không còn tham chiếu phù hợp có thể được thu gom. Điều cần tránh là giữ nhiều iterator/ảnh chụp cũ không cần thiết rồi coi `clear()` trên collection hiện tại là giải phóng chắc chắn mọi phần tử.

Vì vậy, nên hoàn tất lượt duyệt và không lưu iterator lâu hơn mục đích sử dụng. Khi chọn collection, đo cả tỉ lệ đọc/ghi, kích thước danh sách và thời gian tồn tại của các ảnh chụp.

## 9. Tự kiểm tra

1. Tạo iterator rồi thêm một phần tử trước lần `next()` đầu: iterator có thấy phần tử mới không? — Không; mốc phiên bản đã được xác lập lúc tạo iterator.
2. Xóa phần tử khỏi danh sách hiện tại có khiến iterator cũ không trả nó nữa không? — Không; iterator vẫn có tham chiếu trong ảnh chụp cũ.
3. Snapshot có đóng băng mọi trường của một đối tượng có thể thay đổi không? — Không.
4. Có dùng `iterator.remove()` để cập nhật `CopyOnWriteArrayList` không? — Không; thao tác đó không được hỗ trợ.
5. Vì sao danh sách ít ghi, nhiều duyệt phù hợp hơn danh sách liên tục cập nhật? — Việc ghi phải trả chi phí sao chép để đổi lấy lượt duyệt ổn định.
