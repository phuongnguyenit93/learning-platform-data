# Ảnh chụp bất biến và sao chép khi ghi

Một ứng dụng có thể có hàng nghìn luồng đọc bảng cấu hình, trong khi chỉ thỉnh thoảng có luồng cập nhật cấu hình. Nếu mọi lượt đọc đều phải chờ khóa ghi, hiệu năng giảm dù phần lớn thời gian dữ liệu không thay đổi. **Ảnh chụp bất biến (immutable snapshot)** kết hợp với **sao chép khi ghi (copy-on-write, COW)** là một cách tổ chức dữ liệu phù hợp với kiểu tải **đọc nhiều, ghi ít**: mỗi lượt đọc sử dụng một phiên bản ổn định, còn lượt ghi chuẩn bị phiên bản mới rồi công bố nó.

Trong phạm vi cấu trúc dữ liệu, ý tưởng này áp dụng cho mảng, danh sách, bảng băm, cây và các cấu trúc lưu trữ theo phiên bản. Mấu chốt không chỉ là “sao chép dữ liệu”, mà là giữ đúng **bất biến** về phiên bản và điểm chuyển đổi giữa phiên bản cũ với phiên bản mới khi có nhiều luồng truy cập.

## 1. Vì sao cần một ảnh chụp bất biến?

Giả sử cấu hình đang dùng là `{host: "a.example", port: 80}`. Luồng ghi muốn chuyển sang `{host: "b.example", port: 443}`. Nếu luồng đọc truy cập trực tiếp hai trường trên một đối tượng đang bị sửa, nó có thể thấy `host` mới nhưng `port` cũ. Đây là một trạng thái trung gian không nằm trong cấu hình hợp lệ mà người quản trị muốn công bố.

Một **snapshot** là phiên bản dữ liệu biểu diễn trạng thái tại một thời điểm logic. Một **immutable snapshot** không thay đổi sau khi đã được công bố. Luồng đọc giữ tham chiếu đến phiên bản nào thì tiếp tục thấy dữ liệu của phiên bản đó, ngay cả khi có phiên bản mới hơn.

Ví dụ với bảng ánh xạ:

```text
Ban đầu:       current ──────> S0 = {host: "a.example", port: 80}
Luồng đọc R1:                  └──── giữ S0

Luồng ghi W:   tạo bản nháp từ S0, thay host và port
               công bố nguyên tử S1 = {host: "b.example", port: 443}

Sau công bố:   current ──────> S1
Luồng đọc R1:  vẫn đọc S0
Luồng đọc R2:  lấy current và đọc S1
```

Vì không ai sửa `S0` hoặc `S1` sau khi công bố, cả R1 và R2 đều đọc được một cấu hình nhất quán. **R1 có thể nhìn thấy dữ liệu cũ, nhưng không nhìn thấy một nửa bản cập nhật.** Đây là sự đánh đổi có chủ ý: một snapshot giữ tính ổn định, không tự động chạy theo trạng thái mới nhất.

Để đọc nhiều trường nhất quán với nhau, luồng đọc cần **lấy một snapshot một lần**, rồi tra tất cả trường trên cùng đối tượng đó. Nếu gọi hàm lấy snapshot riêng cho từng trường, hai lần gọi vẫn có thể trả về hai phiên bản khác nhau.

## 2. Sao chép khi ghi hoạt động thế nào?

Với COW, dữ liệu đang được người đọc sử dụng không bị sửa trực tiếp. Một lần cập nhật đi qua bốn giai đoạn:

1. **Đọc phiên bản hiện hành** (`S0`) từ tham chiếu gốc, thường gọi là `root` hoặc `current`.
2. **Tạo bản nháp riêng** từ `S0` và thực hiện tất cả thay đổi trên bản nháp; không để người đọc nhìn thấy bản nháp khi chưa hoàn tất.
3. **Đóng băng và công bố** phiên bản mới `S1` bằng một thao tác thay thế tham chiếu có bảo đảm nguyên tử và khả kiến bộ nhớ.
4. **Giữ phiên bản cũ khi còn người đọc sử dụng**; chỉ thu hồi bộ nhớ khi không còn ai cần phiên bản đó.

Đối với hệ thống có **một luồng ghi duy nhất**, cơ chế công bố thích hợp như một biến tham chiếu `volatile` trong Java có thể đủ để bảo đảm người đọc nhìn thấy đối tượng đã được khởi tạo đầy đủ. Khi **nhiều luồng cùng ghi**, thao tác “đọc phiên bản, tạo bản mới, công bố” còn phải giải quyết xung đột giữa các luồng ghi, thường bằng khóa hoặc **compare-and-set (CAS)**.

Có hai mức sao chép cần phân biệt:

| Cách tổ chức | Thao tác cập nhật | Đặc điểm |
| --- | --- | --- |
| **Sao chép toàn bộ** (full-copy COW) | Sao chép tất cả `n` phần tử, sửa bản sao, thay `root` | Dễ hiểu, phù hợp cấu trúc nhỏ và ít cập nhật; mỗi lần ghi thường tốn `O(n)` |
| **Sao chép đường đi** (path copying) | Tạo lại các nút nằm trên đường từ gốc đến phần tử thay đổi, chia sẻ các nhánh còn nguyên | Phù hợp cây bất biến và cấu trúc dữ liệu bền vững (*persistent data structure*); trên cây cân bằng, mỗi lần cập nhật thường tốn `O(log n)` |

Từ “copy-on-write” còn xuất hiện ở hệ điều hành và hệ thống tệp: hai bên có thể dùng chung các trang bộ nhớ hoặc khối dữ liệu cho đến khi có một bên ghi. **Đơn vị sao chép có thể là toàn bộ cấu trúc, một đường đi trong cây, hoặc một trang bộ nhớ**, nhưng nguyên tắc chung là không sửa nội dung mà phiên bản cũ vẫn đang dựa vào.

## 3. Các bất biến cần giữ

Để người đọc không phải khóa mà vẫn có snapshot đúng, thiết kế phải giữ đồng thời các điều kiện sau:

- **Bất biến phiên bản:** một đối tượng đã công bố không bao giờ bị thay đổi, kể cả thông qua tham chiếu khác trỏ đến nó.
- **Bản nháp riêng:** luồng ghi chỉ sửa dữ liệu do nó sở hữu; không để bản nháp rò rỉ sang các luồng đọc trước khi hoàn tất.
- **Công bố an toàn:** tham chiếu gốc chuyển từ phiên bản hoàn chỉnh này sang phiên bản hoàn chỉnh khác bằng cơ chế đồng bộ hóa thích hợp. Tham chiếu cập nhật nguyên tử thôi chưa đủ nếu ngôn ngữ không bảo đảm khả kiến của nội dung mới.
- **Cập nhật không bị mất:** nếu có nhiều luồng ghi, mỗi bản cập nhật phải được kết hợp với trạng thái vừa được công bố, hoặc phải phát hiện xung đột và thử lại.
- **Vòng đời phiên bản:** phiên bản cũ còn sống chừng nào còn có người đọc giữ nó; việc thu hồi phải an toàn đối với các tham chiếu đang tồn tại.

Lưu ý rằng **bất biến nông (shallow immutability)** có thể chưa đủ. Một `Map<String, List<String>>` không cho thêm/xóa khóa vẫn không phải snapshot thực sự bất biến nếu các `List<String>` bên trong tiếp tục bị sửa. Cần dùng giá trị bất biến, hoặc sao chép/đóng băng cả những đối tượng lồng nhau có thể thay đổi.

## 4. Ví dụ Java: bảng đếm có snapshot và CAS

Ví dụ sau dùng Java 17 trở lên. Mỗi luồng đọc lấy một `Map<String, Integer>` đã công bố. Khi tăng bộ đếm, luồng ghi sao chép bảng băm, thay số đếm, tạo bản đồ không thể sửa và dùng `compareAndSet` để công bố.

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class SnapshotCounters {
    private final AtomicReference<Map<String, Integer>> current =
            new AtomicReference<>(Map.of());

    // O(1): trả về đúng một phiên bản ổn định.
    public Map<String, Integer> snapshot() {
        return current.get();
    }

    public int count(String key) {
        Map<String, Integer> view = snapshot();
        return view.getOrDefault(key, 0);
    }

    public void increment(String key) {
        Objects.requireNonNull(key);

        while (true) {
            Map<String, Integer> before = current.get();
            Map<String, Integer> draft = new HashMap<>(before);
            draft.merge(key, 1, Integer::sum);
            Map<String, Integer> after = Map.copyOf(draft);

            if (current.compareAndSet(before, after)) {
                return; // Chỉ phiên bản đầy đủ mới được công bố.
            }
            // Có luồng khác vừa ghi: đọc lại phiên bản mới và thử lại.
        }
    }
}
```

Cách sử dụng:

```java
SnapshotCounters counters = new SnapshotCounters();
Map<String, Integer> oldView = counters.snapshot();

counters.increment("requests");
Map<String, Integer> newView = counters.snapshot();

System.out.println(oldView.getOrDefault("requests", 0)); // 0
System.out.println(newView.getOrDefault("requests", 0)); // 1
// oldView.put("requests", 2); // UnsupportedOperationException
```

Trong ví dụ này, `String` và `Integer` là các kiểu bất biến, nên `Map.copyOf` đủ để bảo vệ cả cấu trúc lẫn giá trị của snapshot. `AtomicReference.get()` có ngữ nghĩa đọc biến `volatile`; `compareAndSet()` vừa kiểm tra tham chiếu cũ, vừa công bố tham chiếu mới với các bảo đảm đồng bộ của Java Memory Model. Người đọc không cần khóa để duyệt hoặc tra cứu phiên bản mình đã lấy.

Một lần `increment` thành công có **điểm tuyến tính hóa (linearization point)** tại lệnh CAS thành công: trước thời điểm đó, người đọc có thể lấy phiên bản cũ; sau thời điểm đó, lượt lấy snapshot mới nhìn thấy phiên bản vừa công bố hoặc phiên bản mới hơn. Nếu muốn cập nhật hai trường phải nhất quán với nhau, hãy sửa **cả hai trên cùng bản nháp** rồi thực hiện **một** lần CAS, thay vì gọi hai lần cập nhật độc lập.

### Hai luồng ghi cùng lúc

Giả sử `S0` có `requests = 0`, hai luồng W1 và W2 cùng muốn tăng bộ đếm:

| Thời điểm | W1 | W2 |
| --- | --- | --- |
| `t0` | Đọc `S0`, tạo `S1` với giá trị `1` | Đọc `S0`, tạo `S2` với giá trị `1` |
| `t1` | `CAS(S0, S1)` thành công | `CAS(S0, S2)` thất bại vì `current` đã là `S1` |
| `t2` | Hoàn tất | Đọc `S1`, tạo `S3` với giá trị `2`, CAS thành công |

Kết quả cuối cùng là `requests = 2`. Nếu cả hai luồng chỉ dùng thao tác gán `current = newMap` sau khi sao chép, bản ghi của luồng công bố sau có thể **ghi đè bản cập nhật của luồng trước** và kết quả sai còn `1`. CAS tránh mất cập nhật bằng cách bắt luồng thua cuộc tính toán lại trên phiên bản mới nhất.

CAS có thể thất bại liên tiếp khi nhiều luồng cùng ghi. Vòng lặp trên bảo đảm tính đúng đắn nhưng không bảo đảm từng luồng luôn hoàn tất nhanh; chi phí sao chép và cấp phát tăng theo số lần thử lại. Ngoài ra, phép biến đổi thực hiện trong vòng CAS có thể được chạy lại, vì thế **không đặt tác dụng phụ không thể hoàn tác** (gửi thông báo, trừ tiền, ghi log nghiệp vụ một lần duy nhất) vào đoạn chuẩn bị bản nháp.

## 5. Chi phí thời gian và bộ nhớ

Với `n` phần tử trong bảng băm và giả sử hàm băm phân bố tốt:

| Thao tác | Full-copy COW trên bảng băm | Cây tìm kiếm cân bằng bất biến có chia sẻ cấu trúc |
| --- | --- | --- |
| Lấy snapshot (giữ tham chiếu gốc) | `O(1)` | `O(1)` |
| Đọc một khóa trong snapshot | `O(1)` trung bình; `O(n)` xấu nhất tùy triển khai | `O(log n)` |
| Cập nhật một khóa | `O(n)` cho một lần sao chép/công bố thành công | `O(log n)` nút mới trên đường đi |
| Dung lượng cấu trúc đang hoạt động | `O(n)` | `O(n)` |
| Giữ lại `k` phiên bản đầy đủ có kích thước xấp xỉ `n` | `O(kn)` trong trường hợp phải giữ đủ `k` bản sao | Khoảng `O(n + u log n)` với `u` lần cập nhật được giữ, nếu chia sẻ các nhánh không đổi |

Các con số trên mô tả **chi phí cấu trúc**, chưa tính dữ liệu lớn nằm bên trong phần tử, chi phí cấp phát, thu gom rác, tranh chấp CAS và độ trễ bộ nhớ. Với đoạn Java trên, `new HashMap<>(before)` và `Map.copyOf(draft)` đều có thể đi qua `O(n)` phần tử; vì thế một lần `increment` thành công vẫn là `O(n)`, còn khi CAS thất bại nhiều lần, tổng chi phí của một lời gọi có thể lớn hơn.

Với cách sao chép toàn bộ, nếu người đọc giữ nhiều snapshot lâu, bộ nhớ vẫn phải chứa các bản đồ cũ. Trong môi trường có bộ thu gom rác như Java, bản cũ được dọn khi không còn tham chiếu; điều đó không có nghĩa việc tạo nhiều phiên bản liên tiếp là miễn phí. Trong C/C++ hoặc các hệ thống kiểu RCU (*read-copy-update*), cơ chế thu hồi còn phải bảo đảm không giải phóng bộ nhớ khi người đọc vẫn đang sử dụng; thường cần quản lý theo epoch, grace period hoặc kỹ thuật tương đương.

## 6. Sao chép đường đi và chia sẻ cấu trúc

Nếu cấu trúc là cây tìm kiếm bất biến, không nhất thiết sao chép toàn bộ cây. Khi đổi một khóa, chỉ cần tạo lại các nút trên đường từ gốc đến nút bị tác động; nhánh không đổi được chia sẻ giữa hai phiên bản.

```text
Phiên bản S0:           8
                    /     \
                   4      12
                  / \     /  \
                 2   6   10  14

Đổi 6 thành 7: tạo gốc 8' và nhánh trái 4' chứa 7.
Nhánh phải có gốc 12 vẫn được S0 và S1 dùng chung.

Phiên bản S1:           8' ──────> nhánh 12 cũ
                     /
                    4'
                   /  \
             nhánh 2   7
                cũ
```

Nếu cây cân bằng có chiều cao `h = O(log n)`, phép cập nhật chỉ cần tạo `O(h)` nút mới; snapshot mới vẫn lấy được trong `O(1)` bằng cách giữ gốc mới. Kỹ thuật này tạo nên nhiều **cấu trúc dữ liệu bền vững (persistent data structures)**, trong đó các phiên bản cũ vẫn truy cập được. Từ *persistent* ở đây nghĩa là **giữ được phiên bản cũ sau cập nhật**, không đồng nghĩa dữ liệu tự động được ghi xuống đĩa.

Kỹ thuật chia sẻ cấu trúc đòi hỏi tính bất biến chặt chẽ: nếu một nút đang được S0 và S1 chia sẻ lại bị sửa tại chỗ, cả hai phiên bản có thể thay đổi. Đối với bảng băm bất biến có cấu trúc trie theo các phần của giá trị băm (ví dụ HAMT), nguyên tắc tương tự cho phép sao chép một số nút trên đường truy cập thay vì sao chép mọi cặp khóa–giá trị.

## 7. Đặt COW trong bức tranh truy cập đồng thời

| Phương án | Lợi thế chính | Giới hạn cần cân nhắc |
| --- | --- | --- |
| Khóa bảo vệ cấu trúc mutable | Cập nhật trực tiếp, ít sao chép; dễ giữ một vùng tới hạn nhất quán | Người đọc và người ghi có thể chờ nhau; thời gian giữ khóa quan trọng |
| Immutable snapshot + full-copy COW | Đọc phiên bản ổn định không phải khóa; mô hình đơn giản khi ít ghi | Mỗi lượt ghi tốn `O(n)`, có áp lực cấp phát và bộ nhớ cho bản cũ |
| Immutable snapshot + persistent tree/trie | Chia sẻ cấu trúc, hỗ trợ nhiều phiên bản hiệu quả hơn | Cài đặt phức tạp; chi phí con trỏ, phân bổ nút và hằng số có thể cao |
| RCU | Đọc rất nhẹ trong hệ thống đọc nhiều, đặc biệt ở mức hệ thống | Thu hồi bộ nhớ và điều phối vòng đời của phiên bản phức tạp |
| MVCC của cơ sở dữ liệu | Quản lý nhiều phiên bản và quy tắc đọc theo giao dịch | Cần thêm chính sách giao dịch, kiểm soát xung đột và dọn phiên bản |

COW kết hợp snapshot có nét tương đồng với RCU và MVCC vì đều giữ nhiều phiên bản trong một khoảng thời gian. Tuy vậy, **một `Map` bất biến được thay bằng CAS chưa tự cung cấp giao dịch MVCC**, cũng chưa giải quyết các quy tắc thu hồi bộ nhớ hay thời gian chờ của RCU. Khi lựa chọn kỹ thuật cần xác định chính xác yêu cầu nhất quán và môi trường thực thi.

**Thường phù hợp** với cấu hình ứng dụng, bảng định tuyến nhỏ, feature flags, danh sách quy tắc truy cập, từ điển tra cứu được làm mới định kỳ, hoặc cây cú pháp được nhiều luồng phân tích đọc song song. **Ít phù hợp** với bộ đếm tần suất cập nhật rất cao, bảng băm cực lớn thường xuyên ghi, hoặc thiết bị hạn chế bộ nhớ nhưng phải giữ nhiều phiên bản lâu dài. Với workload vừa đọc vừa ghi thường xuyên, cấu trúc concurrent chuyên dụng hoặc thiết kế phân vùng dữ liệu có thể tốt hơn.

## 8. Các lỗi thường gặp

**Nhầm “không sửa qua tham chiếu này” với “bất biến”.** Trong Java, `Collections.unmodifiableMap(source)` chỉ trả một view không cho sửa qua view; nếu nơi khác vẫn sửa `source`, người đọc view sẽ thấy thay đổi. `Map.copyOf(source)` tạo một ánh xạ không thể sửa qua API và tách khỏi các cập nhật cấu trúc về sau của `source`, nhưng vẫn cần kiểm tra các đối tượng giá trị lồng bên trong.

**Công bố tham chiếu tới bản nháp mutable.** Nếu luồng ghi đưa `HashMap` còn đang sửa vào `current`, việc thay tham chiếu nguyên tử không bảo vệ người đọc khỏi thay đổi đồng thời trong chính `HashMap`. Phải hoàn tất bản nháp và đóng băng phiên bản trước khi công bố.

**Lấy nhiều snapshot trong một lượt xử lý.** Đọc `host` trên snapshot A rồi đọc `port` trên snapshot B có thể trộn hai cấu hình hợp lệ thành một cặp không hợp lệ. Lấy một snapshot rồi dùng nó xuyên suốt lượt xử lý cần tính nhất quán.

**Chỉ dùng gán tham chiếu khi có nhiều writer.** Một phép gán có thể an toàn về khả kiến nhưng vẫn làm mất cập nhật nếu hai writer cùng tính bản mới từ một phiên bản cũ. Dùng CAS kèm tính lại khi thất bại, hoặc khóa để tuần tự hóa thao tác ghi.

**Giữ snapshot không giới hạn.** Một cache lịch sử hoặc luồng đọc chậm liên tục giữ tham chiếu sẽ khiến bộ nhớ của các phiên bản cũ chưa thể thu hồi. Cần giới hạn vòng đời snapshot và giám sát lượng bộ nhớ giữ lại.

## 9. Câu hỏi tự kiểm tra bằng tình huống

Xét một dịch vụ có 100.000 mục cấu hình, mỗi giây đọc 200.000 lần nhưng cập nhật hai lần. Trước khi chọn cách thiết kế, hãy xác định:

1. Cần nhất quán **từng khóa** hay phải nhất quán **một nhóm khóa**? Nếu là nhóm, chúng phải nằm trong một snapshot và được công bố cùng lúc.
2. Mỗi cập nhật sao chép 100.000 mục có đáp ứng yêu cầu độ trễ hay không? Nếu quá đắt, cân nhắc cây/trie bất biến có chia sẻ cấu trúc.
3. Một lượt đọc giữ snapshot trong bao lâu? Điều này quyết định số phiên bản cũ có thể đồng thời tồn tại và chi phí bộ nhớ.
4. Có một writer hay nhiều writer? Nếu nhiều, phép ghi cần khóa hoặc CAS với cơ chế thử lại để tránh mất cập nhật.

Điều cần nắm chắc là **ảnh chụp bất biến** quy định người đọc nhìn thấy phiên bản ổn định nào, còn **sao chép khi ghi** là một phương pháp tạo phiên bản mới mà không phá hỏng phiên bản cũ. Chỉ khi có cơ chế công bố an toàn, xử lý xung đột giữa các writer và quản lý vòng đời phiên bản, hai ý tưởng này mới tạo thành thiết kế truy cập đồng thời đúng đắn.
