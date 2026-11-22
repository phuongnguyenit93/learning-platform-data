# `CopyOnWriteArrayList` và chi phí sao chép khi ghi

## 1. Đổi chi phí ghi lấy một cách duyệt ổn định

`CopyOnWriteArrayList<E>` là một danh sách an toàn khi nhiều luồng cùng truy cập. Ý tưởng chính là giữ một phiên bản mảng cho việc đọc; khi nội dung danh sách thay đổi, tạo và công bố phiên bản mảng mới thay vì sửa mảng mà những iterator hiện có đang dùng.

Cách này phù hợp với những dữ liệu được duyệt rất nhiều nhưng thay đổi ít, chẳng hạn một danh sách nhỏ các bên nhận sự kiện. Mỗi lần phát sự kiện cần duyệt ổn định; việc đăng ký hoặc hủy đăng ký xảy ra thưa hơn nhiều.

Điều được đánh đổi là chi phí: một thay đổi nhỏ có thể phải sao chép tham chiếu của cả danh sách. Vì vậy, “an toàn khi nhiều luồng truy cập” không có nghĩa đây là lựa chọn mặc định cho mọi danh sách dùng chung.

[Java SE `CopyOnWriteArrayList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html) mô tả cơ chế sao chép khi thay đổi và iterator theo ảnh chụp (snapshot). Bài dùng các API vẫn áp dụng trên Java hiện hành, với ví dụ chạy trên Java 17+.

## 2. Mảng cũ cho người đang đọc, mảng mới cho thay đổi tiếp theo

Giả sử danh sách đang biểu diễn:

```text
phiên bản mảng V1: [A, B]
                   ↑
               iterator cũ
```

Một luồng gọi `add(C)`. Sau khi cập nhật được công bố:

```text
iterator cũ ─────→ V1: [A, B]

danh sách hiện tại → V2: [A, B, C]
                           ↑
                   iterator được tạo mới
```

Iterator cũ tiếp tục nhìn V1; nó không bị buộc chuyển sang V2 ở giữa lần duyệt. Việc tạo iterator kiểu này giữ tham chiếu tới phiên bản mảng, không phải mỗi iterator lại tự sao chép toàn bộ phần tử ngay khi được tạo.

Các thao tác ghi phải phối hợp với nhau để công bố cập nhật đúng. Không hiểu copy-on-write là mọi luồng ghi tự sao chép độc lập rồi tùy ý thay mảng, vì như vậy có thể mất cập nhật. Bên sử dụng dựa vào hợp đồng an toàn của lớp, không cần tự quản lý các phiên bản mảng nội bộ.

Khi một iterator được tạo trước một cập nhật, việc nó vẫn nhìn thấy danh sách cũ là hành vi có chủ ý. Đó không phải một lỗi “chưa nhìn thấy bộ nhớ mới” cần chữa bằng cách thêm `sleep` hoặc đọc lại `size()` trong vòng lặp.

## 3. Chi phí sao chép khi ghi tăng theo số phần tử

Với danh sách có khoảng `n` phần tử, một lần thêm hoặc loại phần tử làm thay đổi mảng thường phải tạo mảng khác và sao chép số tham chiếu tỷ lệ với `n`. Một lần thay phần tử ở chỉ số bằng `set` cũng không có mô hình chi phí giống việc ghi trực tiếp vào một `ArrayList` do một luồng sở hữu.

| Hoạt động | Điều cần dự trù |
| --- | --- |
| `get(index)` | Truy cập phần tử theo chỉ số, không sao chép cả danh sách cho mỗi lần đọc |
| Tạo iterator | Giữ phiên bản mảng tại lúc tạo |
| Duyệt hết iterator | Đi qua các phần tử của phiên bản đó |
| `add`, `remove` làm thay đổi nội dung | Cấp phát mảng và sao chép tham chiếu theo kích thước danh sách; tìm kiếm/xê dịch có thể có thêm chi phí |
| Nhiều luồng cùng ghi | Có phối hợp giữa các bên ghi; không loại bỏ tranh chấp ghi |

Không lấy bảng này làm cam kết mỗi lời gọi đều cấp phát một mảng. Một thao tác không làm thay đổi nội dung, chẳng hạn xóa một phần tử vốn không có, có thể không cần sao chép; triển khai cũng có thể tối ưu một số trường hợp. Điều phải lập ngân sách là đặc điểm chi phí của các thay đổi thực sự.

### Nhiều thay đổi nhỏ có thể tạo lượng sao chép lớn

Ví dụ danh sách thường quanh 10.000 phần tử, có 1.000 thay đổi cần sao chép mỗi giây. Chỉ riêng phần sao chép đã có thể liên quan cỡ 10 triệu tham chiếu mỗi giây. Nếu giả định mỗi tham chiếu là 4 hoặc 8 byte, đó là cỡ 40–80 MB dữ liệu tham chiếu trước khi tính header mảng và các chi phí khác.

Đây là ước lượng mô hình, không phải kết quả đo và không phải kích thước tham chiếu cố định của mọi JVM. Nó cho thấy vì sao danh sách dài kết hợp nhiều lần ghi có thể làm tăng cấp phát, công việc của bộ thu gom rác và độ trễ của bên ghi.

### Cân nhắc cập nhật theo lô khi ý nghĩa nghiệp vụ cho phép

```java
list.addAll(batch);
```

Một lần thêm theo lô thường tránh việc tạo lần lượt nhiều phiên bản mảng như vòng lặp gọi `add` cho từng phần tử. Nếu thêm `m` phần tử vào danh sách ban đầu có `n` phần tử bằng từng lần `add`, lượng tham chiếu phải sao chép tích lũy có thể tăng theo cỡ `m × n + m²`, thay vì một lượt xử lý theo cỡ `n + m` cho thêm theo lô.

Đây là phân tích chi phí điển hình của cách sao chép, không thay cho đo đạc triển khai cụ thể. Cũng cần xét ý nghĩa: một lần thêm theo lô công bố cả đợt thay đổi khác với nhiều lần thêm mà luồng đọc có thể quan sát các trạng thái trung gian.

## 4. Iterator là ảnh chụp của danh sách tại lúc tạo

Iterator cũ không phản ánh các phần tử được thêm, bị xóa hoặc bị thay thế sau thời điểm tạo nó. Nó không dùng `ConcurrentModificationException` để phản ứng với các thay đổi đó.

Ví dụ về một dòng thời gian:

1. Danh sách là `[A, B]`; tạo iterator `old`.
2. Luồng khác thêm `C`, xóa `A`, thay `B` bằng `B2`.
3. Danh sách hiện tại là `[B2, C]`.
4. Duyệt `old` vẫn nhận `A`, rồi `B`.

Các thao tác thay đổi qua chính iterator không được hỗ trợ:

- `Iterator.remove()` ném `UnsupportedOperationException`.
- Các thao tác `set` và `add` của `ListIterator` cũng không được hỗ trợ.

Muốn sửa danh sách, dùng phương thức của danh sách. Nhưng sửa danh sách không làm iterator đang duyệt đổi sang một phiên bản mới. Nếu muốn một lần duyệt khác nhìn thấy cập nhật, tạo iterator mới theo thời điểm phù hợp.

Bảo đảm này cũng không nói rằng có thể chia sẻ một iterator cho nhiều luồng và cho các luồng gọi `next()` tùy ý. An toàn của collection và quy tắc sử dụng một đối tượng iterator là hai vấn đề khác nhau.

## 5. Ví dụ Java 17+ chạy được

Lưu thành `CopyOnWriteDemo.java`. Luồng chính tạo iterator trước; luồng ghi thay đổi danh sách; sau khi xác nhận luồng ghi xong, luồng chính đọc iterator cũ. Cách sắp xếp này tạo stdout xác định mà không đoán lịch chạy bằng `sleep`.

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.FutureTask;

public class CopyOnWriteDemo {
    public static void main(String[] args) throws Exception {
        CopyOnWriteArrayList<String> list =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> old = list.iterator();

        FutureTask<Void> update = new FutureTask<>(() -> {
            list.add("C");
            list.remove("A");
            list.set(0, "B2");
            return null;
        });
        Thread writer = new Thread(update, "writer");
        writer.start();
        update.get();
        writer.join();

        List<String> oldView = new ArrayList<>();
        old.forEachRemaining(oldView::add);
        System.out.println("old iterator: " + oldView);
        System.out.println("current list: " + list);

        try {
            old.remove();
        } catch (UnsupportedOperationException ex) {
            System.out.println("iterator remove: "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("add existing B2: " + list.addIfAbsent("B2"));
        System.out.println("add new D: " + list.addIfAbsent("D"));
        System.out.println("after registration: " + list);

        StringBuilder shared = new StringBuilder("before");
        CopyOnWriteArrayList<StringBuilder> values =
                new CopyOnWriteArrayList<>();
        values.add(shared);
        Iterator<StringBuilder> shallowSnapshot = values.iterator();
        shared.replace(0, shared.length(), "after");
        System.out.println("shared element: " + shallowSnapshot.next());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CopyOnWriteDemo.java
java CopyOnWriteDemo
```

Stdout:

```text
old iterator: [A, B]
current list: [B2, C]
iterator remove: UnsupportedOperationException
add existing B2: false
add new D: true
after registration: [B2, C, D]
shared element: after
```

Đọc kết quả theo hai lớp:

- Ba thay đổi của luồng ghi không ảnh hưởng nội dung danh sách mà iterator `old` đang duyệt.
- Dòng cuối cho thấy ảnh chụp không sao chép sâu đối tượng `StringBuilder`. Phần này chỉ sửa và đọc trong luồng chính, không khẳng định `StringBuilder` an toàn khi nhiều luồng cùng sửa.

`FutureTask.get()` chuyển lỗi của tác vụ ghi về luồng chính nếu có; `join()` xác nhận luồng ghi đã kết thúc. `ArrayList` dùng để gom `oldView` chỉ do luồng chính truy cập, nên không có yêu cầu phải biến nó thành collection đồng thời.

## 6. Sao chép mảng tham chiếu, không sao chép sâu phần tử

Đây là khác biệt dễ bị bỏ sót nhất khi nói “snapshot”. Hai phiên bản mảng có thể cùng trỏ đến một đối tượng phần tử:

```text
mảng V1[0] ──┐
             ├──→ cùng một đối tượng có thể sửa
mảng V2[0] ──┘
```

Nếu trường bên trong đối tượng đó bị sửa, ảnh chụp của danh sách không tự giữ lại toàn bộ dữ liệu cũ của đối tượng. Nó chỉ giữ tập tham chiếu và thứ tự tham chiếu của phiên bản mảng.

Vì vậy, cần cân nhắc một trong các cách:

- Dùng phần tử bất biến khi phù hợp.
- Thay cả phần tử bằng một đối tượng mới thay vì sửa đối tượng đã chia sẻ.
- Để bản thân đối tượng phần tử có cơ chế đồng bộ phù hợp nếu thật sự cần sửa dùng chung.

Đưa một đối tượng đã được khởi tạo vào danh sách có bảo đảm hiển thị bộ nhớ theo hợp đồng collection đồng thời. Các thay đổi không đồng bộ vào trường đối tượng sau đó vẫn phải được giải quyết riêng; copy-on-write ở cấp mảng không tự làm các trường ấy thành `volatile` hoặc nguyên tử.

Lớp này cho phép phần tử `null`, nhưng ứng dụng có thể cấm ở ranh giới riêng. Ví dụ một danh sách bên nhận sự kiện cần gọi phương thức trên từng phần tử thường không nên nhận `null` chỉ vì collection cho phép.

## 7. Iterator tồn tại lâu có thể giữ phiên bản cũ trong bộ nhớ

Sau khi danh sách công bố mảng mới, một iterator còn được giữ lại vẫn có thể giữ mảng cũ. Mảng cũ tiếp tục giữ các tham chiếu tới phần tử của nó, kể cả phần tử đã bị xóa khỏi danh sách hiện tại.

Thu gom rác không loại bỏ một phiên bản vẫn còn có thể được truy cập qua các tham chiếu đang sống. Khi có nhiều iterator ở nhiều thời điểm và chúng tồn tại lâu, nhiều phiên bản mảng cùng các đối tượng chúng giữ có thể đồng thời còn trong heap.

Không phải mỗi lần ghi đều giữ mọi phiên bản mãi mãi. Phiên bản không còn được danh sách hoặc bất kỳ đối tượng nào tham chiếu có thể được thu gom. Vấn đề là vòng đời tham chiếu, không phải một bộ lịch sử vô hạn do lớp chủ động lưu.

Do đó cần tránh giữ iterator trong trường dùng chung hoặc một tác vụ chờ lâu nếu không thật sự cần. Khi đo bộ nhớ, hãy xem cả tốc độ tạo mảng mới và các phiên bản còn được giữ, thay vì chỉ nhìn `list.size()` hiện tại.

## 8. Nhiều thao tác vẫn có thể có khoảng đua

An toàn của từng phương thức không biến chuỗi sau thành nguyên tử:

```java
if (!listeners.contains(listener)) {
    listeners.add(listener);
}
```

Hai luồng có thể cùng thấy chưa có rồi cùng thêm. Nếu ý định là chỉ thêm khi chưa có, `CopyOnWriteArrayList` có `addIfAbsent(listener)`. Nó trả `true` nếu đã thêm, `false` nếu không cần thêm vì có phần tử được xem là bằng nhau.

Tuy nhiên, danh sách vẫn cho phép trùng phần tử qua `add`. Dùng `addIfAbsent` ở một chỗ không ép mọi nơi khác phải tuân theo quy tắc duy nhất. Ý nghĩa bằng nhau cũng phụ thuộc `equals`, nên các trường ảnh hưởng việc so sánh cần có thiết kế ổn định.

Một khoảng đua khác:

```java
if (!list.isEmpty()) {
    Object first = list.get(0);
}
```

Luồng khác có thể xóa phần tử giữa hai bước, làm `get(0)` không còn hợp lệ. Tương tự, vòng lặp dùng `size()` rồi gọi nhiều `get(i)` riêng có thể đọc từ nhiều phiên bản, hoặc gặp chỉ số không còn tồn tại.

Nếu yêu cầu là duyệt một phiên bản ổn định, dùng iterator/for-each phù hợp với hợp đồng snapshot. Nếu cần một chuỗi sửa phức tạp nguyên tử theo nghiệp vụ, phải có thiết kế phối hợp riêng. `synchronized(list)` chỉ điều phối những bên cũng lấy đúng khóa ngoài đó; các lời gọi bình thường từ nơi khác không tự tuân theo khóa của ứng dụng.

## 9. Ví dụ bên nhận sự kiện: gỡ đăng ký chưa chắc hủy lần gọi đang diễn ra

Một tình huống phù hợp là phát sự kiện qua danh sách nhỏ:

```java
for (Listener listener : listeners) {
    listener.onEvent(event);
}
```

Đây là đoạn minh họa ứng dụng, giả định `Listener`, `event` và `listeners` đã được khai báo. For-each tạo iterator nên lần phát hiện tại dùng phiên bản danh sách tại lúc bắt đầu duyệt.

Nếu một luồng khác hủy đăng ký bằng `listeners.remove(listener)`, các lần duyệt được tạo sau cập nhật có thể không còn thấy phần tử đó. Nhưng một lần duyệt cũ vẫn có thể gọi nó từ ảnh chụp cũ. Tương tự, bên mới được đăng ký giữa lượt phát không bắt buộc nhận sự kiện của lượt đang diễn ra.

Nếu yêu cầu là “sau khi hủy đăng ký trả về thì không còn lời gọi nào được phép thực hiện”, chỉ xóa khỏi `CopyOnWriteArrayList` chưa đủ. Cần cơ chế phối hợp với các lời gọi đang diễn ra, chẳng hạn quản lý trạng thái hoạt động và việc đợi các lời gọi kết thúc theo thiết kế rõ ràng.

Collection cũng không làm phương thức `onEvent` tự an toàn nếu nhiều luồng phát sự kiện đồng thời. Thứ tự gọi, lỗi trong callback và việc chạy lâu của một bên nhận đều là trách nhiệm của cơ chế phát sự kiện.

## 10. Chọn theo tỷ lệ đọc/ghi và ý nghĩa của lần duyệt

| Nhu cầu | Điểm cần cân nhắc |
| --- | --- |
| Danh sách nhỏ, duyệt liên tục, rất ít thay đổi, chấp nhận một lần duyệt thấy phiên bản cũ | `CopyOnWriteArrayList` có thể phù hợp |
| Danh sách lớn, thêm/xóa liên tục | Chi phí sao chép và cấp phát có thể quá cao |
| Cần hàng công việc với thao tác chờ và lấy phần tử | Xem mô hình hàng đợi phù hợp, không dùng danh sách chỉ vì nó an toàn đa luồng |
| Cần sửa nhiều bước và nhìn một trạng thái đang được bảo vệ chung | Cân nhắc thiết kế khóa hoặc trạng thái bất biến có quản lý riêng |

`Collections.synchronizedList` là một phương án khác khi muốn đồng bộ trên danh sách, nhưng cách duyệt phải tuân theo quy tắc khóa mà wrapper yêu cầu. [Tài liệu `Collections.synchronizedList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)) nêu việc phải đồng bộ thủ công khi duyệt. Không thay một loại bằng loại kia mà giữ nguyên mọi giả định về iterator.

Khi đánh giá hiệu năng, đo kích thước danh sách, số lần ghi mỗi giây, số lượt duyệt, thời gian giữ iterator, tốc độ cấp phát và độ trễ ghi. Không dùng nhận xét “đọc nhiều” nếu danh sách quá lớn hoặc số lần ghi tuyệt đối vẫn rất cao.

## 11. Tự kiểm tra

1. Vì sao thêm một phần tử có thể tốn công sao chép cả danh sách tham chiếu?
2. Iterator được tạo trước một lần xóa có thể vẫn trả phần tử đã xóa không?
3. Vì sao snapshot của danh sách không bảo vệ dữ liệu cũ bên trong một phần tử có thể sửa?
4. `addIfAbsent` có làm cả danh sách thành một tập hợp không cho trùng trong mọi trường hợp không?
5. Vì sao một iterator tồn tại lâu có thể giữ đối tượng mà danh sách hiện tại đã không còn chứa?
6. Vì sao hủy đăng ký một bên nhận chưa chắc chặn được lời gọi từ một lượt phát đang diễn ra?

Gợi ý: (1) Để công bố mảng mới mà giữ mảng cũ cho các lần đọc hiện có. (2) Có, nó giữ phiên bản trước khi xóa. (3) Chỉ tham chiếu được giữ, không sao chép sâu đối tượng. (4) Không, nơi khác vẫn có thể dùng `add`. (5) Mảng snapshot vẫn giữ tham chiếu tới đối tượng đó. (6) Lượt phát có thể đã tạo iterator trước khi thao tác gỡ xảy ra.
