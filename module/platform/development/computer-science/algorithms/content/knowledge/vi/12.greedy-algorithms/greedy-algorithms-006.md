# Phân phòng cho các khoảng thời gian chồng lấn

**Phân phòng cho các khoảng thời gian chồng lấn** (*interval partitioning*, còn gọi là *minimum meeting rooms*) là bài toán **tham lam**: cho nhiều cuộc họp hoặc công việc, mỗi việc chiếm một khoảng thời gian, hãy phân chúng vào **ít phòng nhất** sao cho không có hai việc chồng lấn dùng chung một phòng.

Cách giải hiệu quả không cần thử tất cả cách gán phòng. Ta **sắp các khoảng theo thời điểm bắt đầu**, rồi giữ một **hàng đợi ưu tiên (min-heap)** sắp theo **thời điểm kết thúc của công việc gần nhất trong mỗi phòng**. Với một khoảng mới, nếu phòng kết thúc sớm nhất đã rảnh thì tái sử dụng phòng đó; nếu ngay cả phòng này chưa rảnh thì phải mở phòng mới. Chiến lược chạy trong **\(O(n\log n)\)** thời gian và cho **số phòng tối thiểu** dưới giả thiết mỗi công việc cần đúng một phòng và không được ngắt giữa chừng.

Điều quan trọng là phải xác định chính xác **thế nào là chồng lấn**, vì hai cuộc họp kết thúc/bắt đầu đúng cùng một mốc có thể dùng chung phòng hoặc không, tùy mô hình; sau đó cần chứng minh vì sao quyết định tham lam luôn tối ưu.

## 1. Phát biểu bài toán và quy ước khoảng thời gian

Cho \(n\) công việc \(I_i\), mỗi công việc có thời điểm bắt đầu \(s_i\) và kết thúc \(e_i\). Trong bài học này, ta dùng **khoảng nửa mở**:

\[
I_i=[s_i,e_i),\qquad s_i<e_i.
\]

Nghĩa là công việc **sử dụng phòng tại thời điểm bắt đầu**, nhưng **không sử dụng phòng tại thời điểm kết thúc**. Hai khoảng \([a,b)\) và \([c,d)\) chồng lấn khi:

\[
\max(a,c)<\min(b,d).
\]

Do đó \([9,11)\) và \([11,13)\) **không chồng lấn**: công việc thứ nhất kết thúc đúng lúc công việc thứ hai bắt đầu. Chúng có thể dùng cùng một phòng nếu không cần thời gian dọn dẹp/chuyển tiếp.

Một **phương án phân phòng hợp lệ** là ánh xạ mỗi công việc tới một mã phòng, bảo đảm với hai công việc bất kỳ dùng cùng phòng, khoảng của chúng không giao nhau. **Mục tiêu** là tối thiểu hóa số phòng khác nhau được sử dụng, không phải tổng thời lượng phòng hay tổng số giờ trống.

Ví dụ sáu cuộc họp:

| Công việc | Bắt đầu | Kết thúc | Khoảng nửa mở |
|---|---:|---:|---|
| A | 9 | 11 | [9,11) |
| B | 10 | 12 | [10,12) |
| C | 11 | 13 | [11,13) |
| D | 10 | 11 | [10,11) |
| E | 13 | 14 | [13,14) |
| F | 12 | 15 | [12,15) |

Tại thời điểm 10, ba công việc **A, B, D** cùng diễn ra. Vì một phòng không thể phục vụ hai công việc cùng lúc, **ít nhất ba phòng là bắt buộc**. Thuật toán tham lam sẽ tìm cách gán toàn bộ sáu công việc chỉ bằng ba phòng.

### Phân biệt với những bài toán gần giống

- **Chọn nhiều cuộc họp không trùng nhau nhất trong một phòng** (*interval scheduling*): một phòng cố định, được phép bỏ bớt công việc, mục tiêu là số công việc được nhận nhiều nhất. Quy tắc tham lam thường là **chọn công việc kết thúc sớm nhất**.
- **Phân tất cả công việc vào ít phòng nhất** (*interval partitioning*): không được bỏ công việc; mục tiêu là **số phòng tối thiểu**. Quy tắc ở đây là **xử lý công việc theo thời gian bắt đầu và tái sử dụng phòng rảnh sớm nhất**.
- **Có đúng \(R\) phòng và muốn nhận tối đa công việc**: được phép từ chối hoặc ưu tiên công việc; cần mô hình tối ưu khác.
- **Phòng có sức chứa, thiết bị hoặc địa điểm khác nhau**: không còn là bài toán thuần túy “mọi phòng giống nhau”; thuật toán cơ bản có thể không phù hợp.

Không nên đánh đồng các bài toán chỉ vì chúng đều liên quan tới khoảng thời gian.

## 2. Độ chồng lấn cực đại là cận dưới của số phòng

Tại một thời điểm \(t\), đặt:

\[
active(t)=|\{i\mid s_i\le t<e_i\}|.
\]

Đây là số công việc **đang chiếm phòng** tại thời điểm đó. Gọi:

\[
\omega=\max_t active(t)
\]

là **mức chồng lấn cực đại** (*maximum overlap*, còn gọi là *depth* của tập khoảng).

Tại thời điểm có \(\omega\) công việc đồng thời, không thể đặt hai công việc trong số đó vào cùng phòng. Vì vậy mọi phương án hợp lệ đều cần ít nhất \(\omega\) phòng:

\[
OPT\ge\omega.
\]

Ví dụ, tại \(t=10\), A=[9,11), B=[10,12), D=[10,11) đều hoạt động, nên \(\omega\ge3\). Ta có thể dựng phương án dùng ba phòng, từ đó suy ra \(\omega=OPT=3\) cho ví dụ.

**Cận dưới này giúp chứng minh tính tối ưu**: nếu thuật toán tham lam dùng nhiều nhất \(\omega\) phòng, không có thuật toán nào dùng ít hơn, nên thuật toán là tối ưu. Mục tiêu không chỉ là tạo một lịch không xung đột, mà còn đạt đúng cận dưới theo số công việc đồng thời.

## 3. Ý tưởng tham lam: phòng rảnh sớm nhất được xét trước

Sắp các công việc theo **thời điểm bắt đầu tăng dần**. Khi các công việc có cùng thời điểm bắt đầu, có thể phá hòa theo thời điểm kết thúc và chỉ số gốc để kết quả gán phòng nhất quán; **số phòng tối thiểu không phụ thuộc** cách phá hòa hợp lệ với các khoảng có độ dài dương.

Duy trì một **min-heap** chứa **một mục cho mỗi phòng đã tạo**:

\[
(\text{end},\ \text{roomId}).
\]

Mục này biểu diễn **thời điểm kết thúc của công việc được gán gần nhất vào phòng đó**. Heap luôn cho phép xem phòng có thời điểm kết thúc nhỏ nhất.

Với công việc mới \([s,e)\):

1. Nếu heap chưa có phòng, tạo phòng mới.
2. Nếu phòng ở đầu heap có **end \(\le s\)**, phòng này đã rảnh trước hoặc đúng lúc công việc mới bắt đầu. Lấy phòng đó khỏi heap để tái sử dụng.
3. Nếu **end \(>s\)** ở đầu heap, **mọi phòng đã tạo đều còn bận** tại thời điểm s. Buộc phải tạo phòng mới.
4. Ghi công việc vào phòng vừa chọn, rồi đưa mục **(e, roomId)** mới vào heap.

**Chỉ cần xét phòng có end nhỏ nhất.** Nếu phòng kết thúc sớm nhất cũng có end > s, mọi phòng khác có end không nhỏ hơn nên đều không thể nhận công việc mới. Ngược lại, nếu có phòng rảnh, phòng ở đầu heap chắc chắn rảnh. Không cần quét tất cả phòng.

**Lưu ý cấu trúc heap:** Trong cách cài này, heap lưu **một mục cho mọi phòng đã tạo**, kể cả phòng đang rảnh. Nó không phải danh sách chỉ gồm những cuộc họp đang diễn ra. Sau khi một cuộc họp kết thúc, mục của phòng vẫn ở heap với end cũ; khi tái sử dụng phòng, ta lấy mục đó ra và đưa end mới vào. Nhờ vậy:

- Kích thước heap luôn bằng **số phòng đã tạo**.
- Mỗi phòng xuất hiện đúng một lần trong heap.
- Mục đầu là **phòng sẵn sàng sớm nhất**, không nhất thiết là cuộc họp đang chạy.

Không được tùy tiện xóa mọi mục có end <= s rồi bỏ chúng đi: nếu không lưu lại các phòng rảnh ở cấu trúc khác, ta sẽ mất mã phòng để tái sử dụng.

## 4. Mã giả thuật toán phân phòng tối thiểu

~~~text
minRooms(intervals):
    kiểm tra mọi khoảng có start < end

    sort intervals theo (start tăng, end tăng, chỉ số gốc tăng)
    heap = min-heap theo (lastEnd, roomId)
    nextRoomId = 0

    for mỗi interval x theo thứ tự vừa sắp:
        if heap không rỗng AND heap.min.lastEnd <= x.start:
            roomId = heap.popMin().roomId
        else:
            nextRoomId++
            roomId = nextRoomId

        gán x vào roomId
        heap.push((x.end, roomId))

    return (nextRoomId, các phép gán công việc -> phòng)
~~~

Các mã phòng 1,2,3,... chỉ là **nhãn**. Nếu có nhiều phòng cùng rảnh, ta có thể chọn một phòng bất kỳ; dùng (end, roomId) làm thứ tự heap giúp kết quả dễ tái hiện, không ảnh hưởng tới số phòng tối ưu.

Nếu chỉ cần **số phòng**, không cần lưu toàn bộ danh sách gán trong đầu ra; tuy nhiên vẫn cần các mốc end trong heap. Nếu phải trả chính xác phòng của từng công việc, nên lưu **roomId** cùng end, không chỉ lưu thời điểm kết thúc.

### Vì sao không cấp phòng theo thứ tự đầu vào?

Nếu đầu vào không được sắp theo thời điểm bắt đầu, một công việc đến sau trong danh sách có thể lại bắt đầu **sớm hơn** những công việc đã xử lý; so sánh end với start của công việc tiếp theo khi đó không còn biểu diễn đúng lịch theo thời gian. Sắp theo start là bước thiết yếu để chứng minh rằng các phòng có end > s đang phục vụ những công việc thực sự chồng lấn tại s.

## 5. Mô phỏng sáu cuộc họp

Đầu vào theo thứ tự **A, B, C, D, E, F**, nhưng khi sắp theo \`start\`, rồi \`end\`, rồi vị trí gốc, ta xử lý:

\[
A(9,11),\ D(10,11),\ B(10,12),\
C(11,13),\ F(12,15),\ E(13,14).
\]

Heap hiển thị sau khi gán mỗi công việc, viết \`(end,room)\` và sắp để dễ quan sát:

| Lượt | Công việc | Quyết định | Heap sau khi gán | Số phòng |
|---:|---|---|---|---:|
| 1 | A [9,11) | Heap rỗng → tạo phòng **1** | (11,1) | 1 |
| 2 | D [10,11) | 11 > 10 → phòng 1 đang bận; tạo phòng **2** | (11,1), (11,2) | 2 |
| 3 | B [10,12) | 11 > 10 → cả hai phòng bận; tạo phòng **3** | (11,1), (11,2), (12,3) | 3 |
| 4 | C [11,13) | 11 <= 11 → tái sử dụng phòng **1** | (11,2), (12,3), (13,1) | 3 |
| 5 | F [12,15) | 11 <= 12 → tái sử dụng phòng **2** | (12,3), (13,1), (15,2) | 3 |
| 6 | E [13,14) | 12 <= 13 → tái sử dụng phòng **3** | (13,1), (14,3), (15,2) | 3 |

Kết quả theo **thứ tự đầu vào**:

| Công việc | Khoảng | Phòng |
|---|---|---:|
| A | [9,11) | 1 |
| B | [10,12) | 3 |
| C | [11,13) | 1 |
| D | [10,11) | 2 |
| E | [13,14) | 3 |
| F | [12,15) | 2 |

Các phòng có lịch sử dụng:

- **Phòng 1:** A [9,11) → C [11,13). Hai khoảng chỉ chạm biên, không chồng lấn.
- **Phòng 2:** D [10,11) → F [12,15). Có khoảng trống [11,12).
- **Phòng 3:** B [10,12) → E [13,14). Có khoảng trống [12,13).

Không có hai công việc cùng phòng chạy đồng thời. Tại t=10 có ba công việc A, B, D chồng lấn; do đó tối thiểu phải có ba phòng. Thuật toán dùng đúng ba phòng nên là **tối ưu**, không chỉ là “hợp lệ”.

## 6. Bất biến và chứng minh số phòng tối thiểu

Ta cần chứng minh **tính hợp lệ** và **tính tối ưu** của thuật toán tham lam.

### 6.1. Bất biến khi bắt đầu xử lý công việc kế tiếp

Sau khi gán một số công việc đã sắp theo start:

1. **Mọi công việc đã xét đều được gán đúng một phòng.**
2. **Không có hai công việc chồng lấn cùng phòng.**
3. **Heap chứa đúng một mục (lastEnd, roomId) cho mỗi phòng đã tạo**, trong đó lastEnd là thời điểm kết thúc của công việc được gán gần nhất vào phòng ấy.
4. **Số phòng đã tạo là số phòng nhỏ nhất có thể cần đối với tập các công việc đã xét**, điều này được chứng minh theo cận dưới ở phần tiếp theo.

Ban đầu chưa có công việc hay phòng, nên các bất biến đúng.

Khi xét công việc \([s,e)\), mọi công việc trước đó đều có thời điểm bắt đầu không lớn hơn s. Nếu có phòng với lastEnd <= s, công việc cuối ở phòng ấy đã kết thúc theo quy ước nửa mở. Vì các công việc trong phòng được phân theo thứ tự start, đặt công việc mới vào phòng đó không chồng lấn công việc trước; các bất biến hợp lệ vẫn đúng.

Nếu không có phòng nào rảnh, mở một phòng mới; hiển nhiên công việc không thể xung đột với công việc khác trong phòng mới.

### 6.2. Tại sao khi mở phòng mới là thực sự bắt buộc?

Giả sử trước một công việc mới bắt đầu tại s, đã có **r phòng**. Thuật toán chỉ mở phòng thứ r+1 khi **lastEnd > s ở mục nhỏ nhất của heap**.

Do heap được sắp theo end tăng, điều này có nghĩa **lastEnd > s ở tất cả r phòng**. Công việc cuối của từng phòng đều bắt đầu **không muộn hơn s** vì ta đã sắp dữ liệu theo start. Kết hợp với end > s, tại thời điểm s có **một công việc đang diễn ra trong mỗi phòng cũ**. Công việc mới cũng đang diễn ra ở s vì **s < e**.

Vậy ngay tại thời điểm s tồn tại **r+1 công việc chồng lấn đồng thời**. Không một phương án hợp lệ nào có thể xếp r+1 công việc đó vào chỉ r phòng:

\[
OPT \ge r+1.
\]

Do thuật toán vừa tạo phòng r+1, việc tăng số phòng là **bất khả tránh** đối với mọi lời giải. Nếu có ít nhất một phòng rảnh, thuật toán tái sử dụng và không tăng số phòng. Theo quy nạp, sau khi xử lý tất cả công việc, số phòng đã tạo là **tối thiểu**.

Lập luận này còn cho thấy thuật toán dùng chính xác:

\[
\boxed{\text{Số phòng tối thiểu}=\omega=\max_t active(t).}
\]

**Đây là chứng minh quyết định tham lam tối ưu**: lần nào tạo phòng mới cũng có một tập công việc chồng lấn chứng thực sự cần thiết của số phòng đó. Không cần quay lui hoặc thử hoán đổi lịch gán.

### 6.3. Vì sao lấy phòng kết thúc sớm nhất?

Tại một công việc bắt đầu s:

- Nếu **phòng kết thúc sớm nhất** còn bận, tất cả các phòng khác cũng còn bận → phải mở phòng.
- Nếu phòng đó đã rảnh, lấy nó để gán chắc chắn hợp lệ → không cần mở phòng.

Do đó xem **một** mục nhỏ nhất là đủ để quyết định có tăng số phòng hay không. Ta không nhất thiết tối ưu **thời gian rảnh tổng cộng** hay một tiêu chí phụ; thuật toán chỉ tối ưu **số phòng** theo đặc tả. Nếu có các ràng buộc thêm (thiết bị, ưu tiên, di chuyển giữa phòng), quyết định chọn phòng rảnh sớm nhất cần được xem xét lại.

## 7. Java 17+: phân phòng và trả lại mã phòng theo thứ tự gốc

Ví dụ Java sau minh họa thuật toán bằng \`PriorityQueue\`. Mỗi Booking có \`id\`, \`start\`, \`end\`; khoảng thời gian theo quy ước **[start,end)** và **start < end**. Thời gian được biểu diễn bằng số nguyên trừu tượng (ví dụ giờ hoặc số phút cùng một mốc), không phải chuỗi thời gian cần phân tích.

Ta giữ **vị trí gốc** của công việc để sau khi xử lý theo start vẫn trả danh sách gán phòng theo đúng thứ tự đầu vào. Việc phá hòa theo start, end và vị trí gốc khiến kết quả in ra **xác định**. Mỗi mục \`AvailableAt\` trong heap gồm thời điểm phòng sẽ rảnh và mã phòng.

Tạo tệp **MeetingRoomsGreedy.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class MeetingRoomsGreedy {
    record Booking(String id, int start, int end) {}
    record Assignment(String id, int room) {}
    record Schedule(int roomCount, List<Assignment> assignments) {}

    // Original position is preserved for stable reporting.
    private record Indexed(int originalIndex, Booking booking) {}

    // One entry per room: end time of the latest booking in that room.
    private record AvailableAt(int end, int room) {}

    static Schedule allocate(List<Booking> bookings) {
        Objects.requireNonNull(bookings, "bookings");

        List<Indexed> sorted = new ArrayList<>();
        int originalIndex = 0;
        for (Booking booking : bookings) {
            Objects.requireNonNull(booking, "booking");
            Objects.requireNonNull(booking.id(), "booking id");
            if (booking.start() >= booking.end()) {
                throw new IllegalArgumentException(
                    "Require start < end for every booking"
                );
            }
            sorted.add(new Indexed(originalIndex++, booking));
        }

        sorted.sort(
            Comparator.comparingInt(
                (Indexed x) -> x.booking().start()
            ).thenComparingInt(x -> x.booking().end())
             .thenComparingInt(Indexed::originalIndex)
        );

        PriorityQueue<AvailableAt> rooms = new PriorityQueue<>(
            Comparator.comparingInt(AvailableAt::end)
                      .thenComparingInt(AvailableAt::room)
        );

        Assignment[] byOriginalOrder = new Assignment[sorted.size()];
        int nextRoomId = 0;

        for (Indexed item : sorted) {
            Booking booking = item.booking();
            int roomId;

            // Endpoints may touch because intervals are [start, end).
            if (!rooms.isEmpty()
                    && rooms.peek().end() <= booking.start()) {
                roomId = rooms.remove().room();
            } else {
                roomId = ++nextRoomId;
            }

            byOriginalOrder[item.originalIndex()] =
                new Assignment(booking.id(), roomId);
            rooms.add(new AvailableAt(booking.end(), roomId));
        }

        return new Schedule(
            nextRoomId,
            List.copyOf(Arrays.asList(byOriginalOrder))
        );
    }

    public static void main(String[] args) {
        List<Booking> bookings = List.of(
            new Booking("A", 9, 11),
            new Booking("B", 10, 12),
            new Booking("C", 11, 13),
            new Booking("D", 10, 11),
            new Booking("E", 13, 14),
            new Booking("F", 12, 15)
        );

        Schedule schedule = allocate(bookings);
        System.out.println("Rooms: " + schedule.roomCount());
        for (Assignment a : schedule.assignments()) {
            System.out.println(a.id() + " -> room " + a.room());
        }

        Schedule adjacent = allocate(List.of(
            new Booking("X", 1, 3),
            new Booking("Y", 3, 5)
        ));
        System.out.println("Adjacent: " + adjacent.roomCount());

        Schedule overlap = allocate(List.of(
            new Booking("P", 1, 5),
            new Booking("Q", 2, 6),
            new Booking("R", 3, 7)
        ));
        System.out.println("All overlapping: " + overlap.roomCount());
        System.out.println("Empty: " + allocate(List.of()).roomCount());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac MeetingRoomsGreedy.java
java MeetingRoomsGreedy
~~~

**Stdout:**

~~~text
Rooms: 3
A -> room 1
B -> room 3
C -> room 1
D -> room 2
E -> room 3
F -> room 2
Adjacent: 1
All overlapping: 3
Empty: 0
~~~

### Giải thích mã

- \`Booking\`, \`Assignment\`, \`Schedule\`, \`Indexed\` và \`AvailableAt\` đều là **record** trong Java 17. \`Indexed\` giúp nhớ vị trí đầu vào, còn \`Assignment[]\` giúp ghi kết quả theo vị trí ấy.
- Việc gom vào \`ArrayList<Indexed>\` trước khi sắp giúp mã không yêu cầu danh sách đầu vào phải có truy cập ngẫu nhiên O(1); nó cũng không hoán đổi trực tiếp danh sách do người gọi cung cấp.
- Bộ so sánh \`Comparator.comparingInt\` và \`thenComparingInt\` tránh lấy hiệu hai thời điểm (có thể tràn int ở các giá trị lớn). Heap ưu tiên \`end\` nhỏ nhất rồi \`room\` nhỏ nhất.
- \`rooms.peek()\` xem phòng có thời điểm rảnh sớm nhất. Nếu end <= start, \`remove()\` lấy đúng một mục phòng cũ rồi \`add()\` thông tin end mới. Nếu không, tăng \`nextRoomId\` để tạo phòng.
- **Không cần xóa hết những phòng đã kết thúc.** Heap duy trì một mục cho **mỗi phòng** đã cấp, kể cả khi phòng hiện rảnh, giúp tái sử dụng đúng roomId.
- Đầu ra được tạo thành \`List.copyOf(Arrays.asList(byOriginalOrder))\`, là danh sách kết quả không cho sửa cấu trúc qua giao diện List. Với n=0, mảng rỗng và danh sách kết quả rỗng được xử lý bình thường; \`roomCount=0\`.
- Thuật toán không tạo ra một lịch theo thứ tự thời gian khi in ra, vì mã chủ ý trả **các công việc theo thứ tự input**. Nếu cần hiển thị lịch từng phòng theo thời gian, có thể gom các Assignment theo roomId rồi sắp theo start.
- \`id\` chỉ dùng để hiển thị; nếu muốn tra cứu công việc theo nhãn không mơ hồ, phía gọi nên cung cấp nhãn duy nhất. Hai nhãn giống nhau **không làm sai** phép phân phòng theo khoảng, nhưng làm báo cáo khó phân biệt.

Phần gán phòng phụ thuộc vào quy tắc phá hòa nếu có nhiều công việc cùng thời điểm bắt đầu và kết thúc. Các mã phòng cụ thể có thể khác khi thay đổi quy tắc, nhưng **số phòng tối thiểu** phải giữ nguyên.

## 8. Độ phức tạp thời gian và bộ nhớ

Đặt \(n\) là số công việc và \(R\) là số phòng thực tế thuật toán tạo ra, với \(R\le n\).

**Chi phí:**

1. Sao chép các công việc và chỉ số gốc vào danh sách: **O(n)**.
2. Sắp theo thời điểm bắt đầu, kết thúc và chỉ số: **O(n log n)** thời gian.
3. Với mỗi công việc, xem đầu heap O(1), lấy một mục O(log R) nếu tái sử dụng, và thêm một mục O(log R) hoặc O(1) khi heap chỉ có ít phần tử. Trên tất cả công việc: **O(n log R)** ở cận trên.
4. Ghi n phép gán phòng: **O(n)**.

Tổng chi phí cận trên:

\[
O(n\log n+n\log R)=O(n\log n)
\]

với \(n\ge2\). Với n=0 hoặc n=1, thời gian là hằng số/bậc tuyến tính theo việc đọc đầu vào. Nếu các khoảng **đã được đưa đến theo start tăng**, có thể bỏ chi phí sắp xếp và xử lý luồng với **O(n log R)** thời gian cho gán phòng, kèm bộ nhớ cho cấu trúc phòng.

**Bộ nhớ:**

- Heap lưu một mục cho mỗi phòng đã tạo: **O(R)**.
- Danh sách đã sắp và mảng/danh sách phép gán trong mã Java: **O(n)**.
- Tổng bộ nhớ ngoài đầu vào của chương trình minh họa: **O(n+R)=O(n)**. Nếu không cần lưu đầy đủ danh sách gán và đã có nguồn dữ liệu theo thứ tự start, có thể xử lý tuần tự với **O(R)** bộ nhớ làm việc.

Nếu chỉ cần **đếm số phòng tối thiểu**, cũng có thể tính **độ chồng lấn cực đại** bằng quét các mốc bắt đầu/kết thúc đã sắp. Nhưng giải pháp quét mốc chỉ trả số phòng, **không trực tiếp trả phòng nào cho mỗi công việc**. Heap với roomId giải quyết đồng thời việc đếm và gán.

## 9. Quy ước chạm biên, khoảng đóng và thời gian chuyển phòng

Quy tắc \`end <= start\` của bài học là **đúng với khoảng nửa mở [start,end)**. Nếu mô hình sử dụng **khoảng đóng [start,end]**, hai công việc chạm ở thời điểm t **vẫn chồng lấn**, vì cả hai đều chiếm phòng tại t. Khi đó muốn tái sử dụng phòng cần **end < start**. Không có một dấu so sánh đúng cho mọi bài toán; phải chọn dấu dựa trên đặc tả về thời điểm kết thúc.

| Quy ước | Hai khoảng [9,11] và [11,13] có chồng lấn? | Điều kiện tái sử dụng |
|---|---|---|
| **Nửa mở [s,e)** | Không | **end <= nextStart** |
| Đóng [s,e] | Có, tại t=11 | **end < nextStart** |
| Nửa mở, cần dọn phòng \(\delta>0\) sau cuộc họp | Chỉ tái sử dụng nếu đủ thời gian dọn | **end + \(\delta\) <= nextStart** |

Nếu thêm thời gian dọn \(\delta\), có thể coi thời điểm phòng sẵn sàng là **end + \(\delta\)** thay vì end; nhưng cần tránh **tràn số nguyên** khi cộng hoặc chuyển sang kiểu thời gian đủ rộng. Các công việc có thời gian dọn khác nhau sẽ đòi hỏi lưu thời điểm sẵn sàng riêng cho từng lần gán.

Đối với đầu vào dạng chuỗi ngày giờ, cần thống nhất **múi giờ**, định dạng, và mốc thời gian để so sánh; so sánh chuỗi giờ "9:00" và "10:00" bằng thứ tự từ điển tùy định dạng có thể sai. Trong mã Java, dùng \`int\` chỉ để tập trung vào thuật toán; ứng dụng thực tế có thể dùng \`Instant\`, \`LocalDateTime\` kèm quy tắc múi giờ, hoặc số phút/giây từ một epoch chung.

**Khoảng độ dài 0:** Nếu cho phép [s,s) theo mô hình tập hợp, đây là khoảng **rỗng**, không chiếm phòng. Ví dụ Java **từ chối** \`start >= end\` để mọi công việc đều có thời lượng dương và chứng minh “mở phòng mới → có thêm công việc đang chạy tại s” luôn áp dụng. Nếu đặc tả cho phép công việc thời lượng 0, phải xử lý chúng riêng (ví dụ không tiêu thụ phòng), không mặc nhiên đưa qua logic như khoảng dương.

## 10. Tính số phòng bằng sự kiện bắt đầu/kết thúc

Nếu **chỉ cần số phòng, không cần gán cụ thể**, có thể dùng cách quét sự kiện (*sweep line*). Tạo các mốc:

- Một sự kiện **bắt đầu** tại \`start\`: tăng số công việc đang hoạt động.
- Một sự kiện **kết thúc** tại \`end\`: giảm số công việc đang hoạt động.

Sắp các sự kiện tăng theo thời điểm. Với khoảng **[start,end)**, ở **cùng một thời điểm**, phải xử lý **kết thúc trước bắt đầu** để những công việc vừa kết thúc không bị đếm chồng với những công việc mới bắt đầu. Trong lúc quét, lấy giá trị lớn nhất của biến active; đó là \(\omega\), cũng chính là số phòng tối thiểu.

Ví dụ:

~~~text
A: [9,11)
B: [10,12)
C: [11,13)

t=9:  start A       -> active=1
t=10: start B       -> active=2
t=11: end A trước, start C sau
      active 2 -> 1 -> 2
t=12: end B         -> active=1
t=13: end C         -> active=0

Độ chồng lấn tối đa = 2 phòng.
~~~

Nếu đảo thứ tự và xử lý bắt đầu trước kết thúc ở t=11, có thể tạm đếm active=3 dù A và C không giao nhau theo [s,e), dẫn đến **đếm dư phòng**. Đây là lỗi xử lý hòa theo thời điểm phổ biến của sweep line.

Cách sweep line dùng **O(n log n)** thời gian để sắp các mốc và **O(n)** bộ nhớ để lưu các sự kiện (nếu không làm việc trực tiếp trên cấu trúc đầu vào). Nhưng nó không cung cấp **roomId** cho từng cuộc họp; để trả phòng cụ thể, dùng heap có mã phòng như phần 7.

## 11. Các trường hợp biên cần kiểm thử

| Trường hợp | Kỳ vọng đúng |
|---|---|
| Không có công việc | Số phòng tối thiểu bằng **0** |
| Một công việc có start < end | Cần đúng **1** phòng |
| Hai khoảng [1,3), [3,5) | Không chồng lấn; dùng **1** phòng |
| Hai khoảng [1,4), [2,5) | Chồng lấn; cần **2** phòng |
| Ba khoảng [1,5), [2,6), [3,7) | Cùng hoạt động tại t=3; cần **3** phòng |
| Nhiều công việc bắt đầu đồng thời | Mỗi công việc độ dài dương đều hoạt động tại thời điểm bắt đầu; cần đủ phòng |
| Khoảng rất dài chứa nhiều khoảng nhỏ | Phòng của khoảng dài bị chiếm suốt thời gian đó; các khoảng nhỏ được tái sử dụng phòng khác tùy thời điểm |
| Công việc xuất hiện không theo thứ tự start | Phải sắp trước hoặc dùng cấu trúc trực tuyến có bảo đảm thứ tự |
| Start = end | Ví dụ Java từ chối; nếu cho phép khoảng rỗng phải đổi cách xử lý |
| Start > end | Đầu vào không hợp lệ, phải từ chối |
| Có mốc thời gian âm | Thuật toán so sánh int vẫn có thể đúng nếu quy ước thời gian cho phép; chỉ cần start < end |
| Thời điểm rất lớn hoặc phải cộng thời gian dọn phòng | Dùng phép so sánh không tràn; nếu cộng độ trễ nên dùng kiểu số đủ rộng |
| Nhiều phòng kết thúc cùng giờ | Cùng rảnh; heap phá hòa theo roomId, không thay đổi số phòng |
| Đầu vào cần giữ nguyên | Mã Java sắp bản sao các cặp (vị trí,bản ghi), không sắp trực tiếp danh sách gốc |

Nếu chỉ có một phòng và các công việc đầu vào **tự thân không chồng lấn**, thuật toán luôn tái sử dụng đúng một roomId sau lần đầu. Nếu mọi công việc **đồng thời chồng lấn**, số phòng bằng n. Hai trường hợp cực trị này dễ dùng để kiểm tra cận dưới/cận trên của kết quả.

## 12. Những lỗi triển khai thường gặp

1. **Nhầm bài toán với chọn nhiều cuộc họp nhất:** phân phòng không được bỏ các công việc; phải gán tất cả và giảm số phòng.
2. **Không sắp theo start:** quyết định phòng rảnh có thể sai khi xử lý ngược thời gian.
3. **Dùng dấu end < start trong mô hình [s,e):** làm các khoảng chạm biên bị tính chồng lấn, gây thừa phòng.
4. **Dùng dấu end <= start trong mô hình [s,e] đóng:** cho phép hai khoảng cùng chiếm thời điểm biên trong một phòng.
5. **Chọn phòng bất kỳ mà không kiểm tra thời điểm rảnh:** có thể gán hai cuộc họp chồng lấn cùng phòng.
6. **Nhầm heap chỉ chứa cuộc họp đang hoạt động:** phiên bản lưu mã phòng cần giữ **một thời điểm sẵn sàng cho mọi phòng**, kể cả phòng rảnh.
7. **Xóa toàn bộ các mục đã rảnh khỏi heap nhưng không giữ mã phòng:** làm mất những phòng có thể tái sử dụng, dễ cấp phòng mới không cần thiết.
8. **Chỉ lưu end trong heap khi đề cần xuất roomId:** biết thời điểm rảnh chưa đủ để xác định phòng nào được gán.
9. **Không cập nhật end sau khi tái sử dụng phòng:** phòng có thể bị gán thêm công việc chồng lấn vì heap còn giữ thời điểm rảnh cũ.
10. **Không làm rõ trật tự khi nhiều start bằng nhau:** số phòng vẫn có thể đúng nhưng roomId đầu ra khó tái hiện, nhất là khi cần kiểm thử stdout.
11. **Cho rằng O(n) là thời gian tổng:** bước sắp và thao tác heap đưa tổng tới **O(n log n)** trong trường hợp thông thường.
12. **Đánh đồng kích thước heap với số công việc đang chạy:** heap có thể chứa phòng rảnh; kích thước heap bằng số phòng **đã tạo**, không phải số cuộc họp đồng thời ở thời điểm hiện tại.
13. **Đếm sai tại sự kiện cùng thời điểm trong sweep line:** với [s,e), phải xử lý end trước start.
14. **Không phân biệt bản ghi theo vị trí gốc:** sắp dữ liệu trước khi cấp phòng có thể thay đổi thứ tự báo cáo; cần lưu ID/vị trí để trả lại đúng công việc.
15. **Bỏ qua yêu cầu về dọn phòng/độ trễ giữa hai công việc:** trong thực tế phòng kết thúc họp lúc 11 có thể chưa sẵn sàng lúc 11.
16. **Áp dụng tham lam đơn giản cho phòng có ràng buộc riêng:** thiết bị, sức chứa, nhóm người, ưu tiên có thể biến bài toán thành dạng phân bổ tài nguyên khó hơn.

## 13. Bài tập tự luyện

**Bài 1 — Các khoảng chạm biên.** Với [1,3), [3,5), [5,7), cần ít nhất mấy phòng?

*Đáp án:* **1 phòng**. Mỗi khoảng kết thúc đúng khi khoảng kế tiếp bắt đầu; theo [s,e), chúng không chồng lấn.

**Bài 2 — Ba khoảng đồng thời.** Với [1,5), [2,6), [3,4), hãy tìm cận dưới số phòng và một phương án tối ưu.

*Đáp án:* Tại t=3, cả ba khoảng hoạt động nên cần **ít nhất 3 phòng**. Gán mỗi khoảng vào một phòng khác nhau đạt 3 phòng, nên tối ưu là **3**.

**Bài 3 — Có cần pop tất cả phòng đã rảnh?** Heap có các mục (5,1), (6,2), (9,3); công việc mới bắt đầu lúc 10 và kết thúc lúc 12. Phải làm gì?

*Đáp án:* Đủ để lấy **một** phòng rảnh sớm nhất, ví dụ phòng 1, rồi đưa (12,1) vào heap. Các phòng 2 và 3 vẫn nằm trong heap với mốc kết thúc cũ và có thể được tái sử dụng ở những công việc tiếp theo. Không xóa tất cả nếu chưa có cấu trúc khác để giữ roomId của phòng rảnh.

**Bài 4 — Chứng minh tham lam.** Khi công việc mới bắt đầu lúc s mà heap có r mục và mục nhỏ nhất có end > s, tại sao buộc phải mở phòng thứ r+1?

*Đáp án:* Tất cả r phòng có công việc trước đó bắt đầu không muộn hơn s và kết thúc sau s; tức đều bận tại s. Công việc mới cũng bắt đầu tại s và có thời lượng dương, tạo **r+1 công việc đồng thời**. Không thể gán chúng vào r phòng.

**Bài 5 — Quy tắc quét sự kiện.** Với A=[2,4), B=[4,6), nếu xử lý start trước end tại t=4 thì có thể tính sai điều gì?

*Đáp án:* Có thể tạm đếm hai công việc cùng chạy và báo cần 2 phòng, dù A đã kết thúc khi B bắt đầu. Với [s,e), phải xử lý **end trước start** ở cùng mốc.

**Bài 6 — Khác nhau về mục tiêu.** Với 100 cuộc họp, bài toán “giữ tối đa số cuộc họp trong một phòng” và “gán tất cả cuộc họp vào ít phòng nhất” có thể dùng cùng thuật toán chọn cuộc họp kết thúc sớm nhất không?

*Đáp án:* **Không.** Bài toán thứ nhất được phép bỏ cuộc họp và thường dùng tham lam chọn hoạt động kết thúc sớm. Bài toán thứ hai phải giữ **đủ 100 công việc**, sắp theo start rồi dùng heap các thời điểm phòng rảnh để giảm số phòng.

**Ghi nhớ:** Với các khoảng **[start,end)** có thời lượng dương, sắp theo **start tăng** và luôn xét **phòng có end nhỏ nhất**. Nếu **end <= start**, tái sử dụng phòng đó; nếu không, tạo phòng mới. Mỗi lần tạo phòng mới đều có bằng chứng tồn tại bấy nhiêu công việc chồng lấn tại cùng thời điểm, nên thuật toán đạt **số phòng tối thiểu bằng mức chồng lấn cực đại \(\omega\)**. Dùng min-heap để gán phòng trong **O(n log n)**, đồng thời bảo đảm không có hai khoảng chồng lấn trong cùng một phòng.