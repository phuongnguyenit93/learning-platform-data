# putIfAbsent, remove có điều kiện và replace có điều kiện

## 1. Vì sao cần gộp kiểm tra với cập nhật?

Trong mã nhiều luồng, “kiểm tra thấy đúng rồi mới sửa” gồm hai lời gọi thường không tạo thành một thao tác nguyên tử. Ví dụ:

```java
// Minh hoa khong an toan neu can bao dam chi chen khi chua co.
if (!map.containsKey(key)) {
    map.put(key, candidate);
}
```

Hai luồng có thể cùng thấy khóa chưa tồn tại. Hoặc sau khi một luồng đọc giá trị cũ, luồng khác đã thay nó trước khi lệnh xóa hay ghi tiếp theo diễn ra.

Các thao tác có điều kiện của `ConcurrentMap` giải quyết một nhóm tình huống cụ thể: **kiểm tra điều kiện hiện tại và thực hiện thay đổi tương ứng trong cùng một thao tác nguyên tử**.

Trong module skip list đồng thời, ta dùng chúng qua `ConcurrentNavigableMap` với triển khai `ConcurrentSkipListMap`. Thứ tự khóa vẫn được giữ, còn việc chèn, thay hay xóa có điều kiện tuân thủ hợp đồng đồng thời. Xem [ConcurrentMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

## 2. Bảng hợp đồng và giá trị trả về

Với `ConcurrentSkipListMap<K, V>`, khóa và giá trị lưu trong map không được null:

| API | Điều kiện để thay đổi | Thay đổi | Kết quả trả về |
| --- | --- | --- | --- |
| `putIfAbsent(k, v)` | Chưa có ánh xạ cho k | Chèn `k -> v` | Giá trị trước đó, hoặc null nếu vừa chèn |
| `remove(k, expected)` | Có khóa và giá trị hiện tại bằng expected | Xóa ánh xạ | true nếu đã xóa, false nếu không |
| `replace(k, expected, replacement)` | Có khóa và giá trị hiện tại bằng expected | Thay bằng replacement | true nếu đã thay, false nếu không |

So sánh giá trị mong đợi dùng ý nghĩa của `equals`, không yêu cầu hai biến trỏ đến cùng một đối tượng. Hợp đồng nguyên tử và kết quả từng phương thức được xác nhận tại [ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

Ba lời gọi không cùng kiểu kết quả. Đặc biệt `putIfAbsent` trả **V**, không trả boolean.

### putIfAbsent không ghi đè giá trị đã có

Nếu map chưa có khóa 1:

```java
State previous = states.putIfAbsent(1, candidate);
boolean installed = previous == null;
```

Trong ví dụ dùng `ConcurrentSkipListMap`, null nghĩa là lời gọi vừa chèn thành công. Nếu trả một giá trị khác null, map đã có ánh xạ; giá trị đó là kết quả cần xem xét thay vì giả định candidate đã được dùng.

### remove có điều kiện không xóa trạng thái mới hơn

Nếu đang đọc `RUNNING`, nhưng trước khi xóa đã có luồng đổi thành `DONE`, `remove(key, expectedRunning)` sẽ không xóa ánh xạ DONE nếu hai trạng thái không bằng nhau.

Thay `remove(key, expected)` bằng `remove(key)` làm mất bước bảo vệ bằng giá trị mong đợi.

### replace có điều kiện chỉ thay trạng thái còn khớp

`replace(key, expected, replacement)` thành công khi ánh xạ hiện tại vẫn bằng expected tại thao tác nguyên tử đó. Nếu đã đổi hoặc biến mất, trả false và giữ nguyên dữ liệu tại lời gọi thất bại ấy.

Không được bỏ qua boolean rồi tiếp tục xử lý như thể mình đã cập nhật thành công.

## 3. Phân biệt hai overload của replace

Ngoài overload ba đối số còn có:

```java
V replace(K key, V newValue);
```

Overload hai đối số chỉ yêu cầu **khóa đang tồn tại**. Nó không kiểm tra giá trị cũ có đúng điều mà nơi gọi đã đọc trước đó hay không.

| Lời gọi | Điều kiện | Kết quả |
| --- | --- | --- |
| `replace(k, newValue)` | k đang có ánh xạ | Trả giá trị cũ; null nếu không có ánh xạ |
| `replace(k, expected, newValue)` | k có ánh xạ và giá trị khớp expected | Trả boolean |

Cả hai không tự chèn khi khóa vắng mặt. Nếu cần “chèn nếu chưa có”, đó là mục tiêu của `putIfAbsent`. Xem [các overload replace trong ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

## 4. Ví dụ đầy đủ: chuyển trạng thái và loại thao tác cũ

Tệp `ConditionalMapUpdates.java` chạy trên Java 17+.

Giá trị là một record bất biến gồm `phase` và `version`. Hai luồng cùng thử chuyển khóa 1 từ `NEW, phiên bản 0` sang `RUNNING, phiên bản 1`. Không có thao tác đặt lại NEW trong giai đoạn tranh chấp, nên chỉ một replace thành công.

```java
import java.util.concurrent.ConcurrentNavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ConditionalMapUpdates {
    private record State(String phase, long version) {}

    private static Thread claimant(
            ConcurrentNavigableMap<Integer, State> states,
            CountDownLatch start,
            AtomicInteger successfulClaims) {
        return new Thread(() -> {
            try {
                start.await();
                boolean changed = states.replace(
                        1, new State("NEW", 0), new State("RUNNING", 1));
                if (changed) {
                    successfulClaims.incrementAndGet();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentNavigableMap<Integer, State> states =
                new ConcurrentSkipListMap<>();

        State previous = states.putIfAbsent(1, new State("NEW", 0));
        System.out.println("first insertion=" + (previous == null));
        previous = states.putIfAbsent(1, new State("OTHER", 99));
        System.out.println("second insertion=" + (previous == null));
        System.out.println("existing state=" + previous);

        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger successfulClaims = new AtomicInteger();
        Thread a = claimant(states, start, successfulClaims);
        Thread b = claimant(states, start, successfulClaims);
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        if (successfulClaims.get() != 1) {
            throw new AssertionError("Exactly one claim was expected");
        }
        System.out.println("successful claims=" + successfulClaims.get());
        System.out.println("after claim=" + states.get(1));

        System.out.println("remove stale NEW="
                + states.remove(1, new State("NEW", 0)));
        System.out.println("finish expected RUNNING="
                + states.replace(1, new State("RUNNING", 1),
                                    new State("DONE", 2)));
        System.out.println("remove stale RUNNING="
                + states.remove(1, new State("RUNNING", 1)));
        System.out.println("remove expected DONE="
                + states.remove(1, new State("DONE", 2)));
        System.out.println("remove absent="
                + states.remove(1, new State("DONE", 2)));
        System.out.println("replace absent="
                + states.replace(1, new State("NEW", 3)));

        states.putIfAbsent(1, new State("NEW", 3));
        System.out.println("old version replace="
                + states.replace(1, new State("NEW", 0),
                                    new State("RUNNING", 1)));
        System.out.println("current version replace="
                + states.replace(1, new State("NEW", 3),
                                    new State("RUNNING", 4)));
        System.out.println("final state=" + states.get(1));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 ConditionalMapUpdates.java
java ConditionalMapUpdates
```

Kết quả chính xác:

```text
first insertion=true
second insertion=false
existing state=State[phase=NEW, version=0]
successful claims=1
after claim=State[phase=RUNNING, version=1]
remove stale NEW=false
finish expected RUNNING=true
remove stale RUNNING=false
remove expected DONE=true
remove absent=false
replace absent=null
old version replace=false
current version replace=true
final state=State[phase=RUNNING, version=4]
```

## 5. Diễn giải cơ chế của ví dụ

### Chèn lần đầu và chèn trùng

Lần đầu chưa có khóa 1 nên chèn thành công. Lần hai đề nghị `OTHER,99` nhưng không ghi đè `NEW,0`; giá trị trả về cho biết ánh xạ đã tồn tại.

Chỉ kiểm tra map cuối cùng có khóa là chưa đủ để biết lời gọi nào đã thắng. Chương trình kiểm tra trực tiếp kết quả của phương thức.

### Hai luồng cạnh tranh một chuyển trạng thái

Mỗi luồng tạo một đối tượng `new State("NEW", 0)` riêng làm expected. Chúng không dùng cùng tham chiếu với đối tượng đã lưu.

Record so sánh bằng nhau theo các thành phần, nên expected vẫn khớp `NEW,0`. Luồng thành công đầu tiên đổi thành `RUNNING,1`; luồng còn lại không còn thấy expected phù hợp và nhận false.

Bảo đảm một lần chuyển đến từ phép replace nguyên tử. `CountDownLatch` chỉ phối hợp thời điểm cho các luồng bắt đầu, không thay thế cơ chế nguyên tử của map. `AtomicInteger` dùng để đếm kết quả từ hai luồng mà không làm bộ đếm tự có lỗi tranh chấp.

Chương trình đợi cả hai luồng bằng `join()` trước khi in trạng thái và chạy các bước còn lại. Nó không phụ thuộc luồng A hay B được CPU chạy trước.

### Thao tác cũ không xóa trạng thái mới

Sau khi đã là RUNNING, xóa với expected NEW trả false. Sau khi chuyển sang DONE, xóa với expected RUNNING cũng trả false.

Lần xóa đúng DONE thành công; lần xóa lại khi đã vắng mặt trả false. Overload replace hai đối số trên khóa đã vắng mặt trả null, không chèn mới.

### Phiên bản giúp phân biệt hai lần cùng tên trạng thái

Khóa sau đó được đăng ký lại với `NEW,3`. Một thao tác cũ còn nhớ `NEW,0` không thay được trạng thái mới, dù tên phase cùng là NEW.

Khi expected đúng `NEW,3`, phép chuyển sang RUNNING,4 thành công. Điều này cho thấy điều kiện `equals` phải chứa đủ thông tin mà quy tắc nghiệp vụ cần bảo vệ.

## 6. Giới hạn của phép so sánh giá trị

Nếu giá trị chỉ là String `"NEW"`, một lịch sử có thể là:

```text
NEW -> RUNNING -> NEW
```

Một luồng đọc NEW từ lần đầu rồi chậm lại. Khi nó thử `replace(key, "NEW", ...)`, giá trị hiện tại lại là NEW nên điều kiện có thể khớp. Phương thức chỉ xét giá trị hiện tại; nó không tự ghi nhớ lịch sử đã đi qua RUNNING.

Đây thường được gọi là vấn đề trạng thái quay lại giá trị cũ (ABA). Trong mô hình có yêu cầu phân biệt các thế hệ, một giá trị bất biến kèm phiên bản hoặc mã thế hệ riêng giúp làm rõ điều kiện.

Phiên bản không được map tự tăng. Ứng dụng phải bảo đảm quy tắc cấp phiên bản đúng, có trong phép bằng, và không tái sử dụng một phiên bản cũ theo cách làm mất sự phân biệt. Ví dụ dùng các số nhỏ cố định để minh họa; hệ thống thật còn phải xác định quy tắc khi tái tạo khóa, khởi động lại và hết miền giá trị.

Không nên dùng đối tượng expected có các trường liên tục bị sửa ngoài map. Điều đó làm ý nghĩa của phép bằng khó kiểm soát và map không tự đồng bộ mọi thay đổi bên trong giá trị. Giá trị bất biến thường giúp suy luận các chuyển trạng thái rõ hơn.

## 7. Thất bại có điều kiện là một nhánh bình thường

Kết quả false có thể có nghĩa khóa đã vắng mặt hoặc giá trị hiện tại không còn khớp. Không suy ra chính xác trạng thái mới chỉ từ boolean.

Nơi gọi thường cần chọn một trong những hướng sau theo nghiệp vụ:

- Dừng vì một luồng khác đã hoàn thành việc mong muốn.
- Đọc lại trạng thái để hiển thị hoặc quyết định hành động tiếp.
- Tính lại giá trị mới từ trạng thái vừa đọc rồi thử lại với điều kiện mới.
- Báo xung đột hoặc chuyển sang cơ chế phối hợp rộng hơn.

Nếu thử lại, phải hiểu điều kiện được kiểm tra lại trên dữ liệu nào. Lặp mãi với cùng expected cũ không tự sửa được một xung đột đã xảy ra.

Không thực hiện một tác động bên ngoài khó hoàn tác rồi mới kiểm tra xem replace có thành công không. Khi dùng kết quả cập nhật để quyết định xử lý, chỉ đi theo nhánh thành công khi thực sự nhận true.

Tuy vậy, việc thắng một chuyển trạng thái trong map cũng không tự bảo đảm một quy trình ngoài map chạy đúng một lần qua mọi lỗi tiến trình. Yêu cầu phục hồi và tính bền vững là một lớp thiết kế khác.

## 8. putIfAbsent không làm việc khởi tạo trở nên lười

Trong lời gọi:

```java
// Minh hoa: createValue() duoc danh gia truoc khi goi putIfAbsent.
Value previous = map.putIfAbsent(key, createValue());
```

Java phải tính đối số `createValue()` trước khi gọi phương thức. Vì vậy hai luồng vẫn có thể cùng tạo candidate, dù chỉ một candidate được chèn.

Nếu candidate nắm tài nguyên, cần xử lý tài nguyên của candidate thua theo hợp đồng sở hữu của ứng dụng. Đừng hiểu “chỉ một ánh xạ được chèn” thành “chỉ một lần khởi tạo diễn ra”.

Các API như `computeIfAbsent` phục vụ một cách diễn đạt khác, nhưng hợp đồng gọi hàm phụ thuộc triển khai. Riêng `ConcurrentSkipListMap` không bảo đảm hàm được áp dụng đúng một lần một cách nguyên tử chỉ khi vắng mặt. Không chuyển các tác động không thể lặp tùy ý vào hàm rồi dựa trên một giả định sai. Xem [ConcurrentSkipListMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

## 9. Những bảo đảm không được suy rộng

### Nguyên tử một ánh xạ không phải giao dịch nhiều khóa

Một `replace` thành công chỉ giải quyết chuyển đổi cụ thể cho một khóa. Chuỗi “trừ ở khóa A rồi cộng ở khóa B” không tự nguyên tử trên cả hai khóa.

Tương tự, `get`, kiểm tra một điều kiện ngoài map rồi `replace` không biến mọi điều kiện liên quan thành một bước. Cần xác định dữ liệu nào nằm trong expected và dữ liệu nào vẫn nằm ngoài phép cập nhật nguyên tử.

### Trả true không giữ trạng thái mãi mãi

Ngay sau một replace thành công, luồng khác có thể thực hiện một cập nhật hợp lệ tiếp theo. Kết quả true xác nhận lời gọi đã thực hiện thay đổi theo điều kiện của nó, không cấp quyền sở hữu vĩnh viễn đối với khóa.

### Tính nguyên tử thuộc hợp đồng triển khai đồng thời

Bài dùng `ConcurrentSkipListMap` qua giao diện đồng thời. Không áp dụng các bảo đảm ấy chỉ vì một map thường có phương thức cùng tên.

Các default method trên `Map` không mặc định có cùng bảo đảm nguyên tử như hợp đồng của `ConcurrentMap`; triển khai giao diện đồng thời phải đáp ứng bảo đảm cần thiết. Xem [ConcurrentMap và các phương thức kế thừa](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

### Null và thứ tự khóa

`ConcurrentSkipListMap` không lưu khóa hoặc giá trị null. `putIfAbsent` không dùng null làm một giá trị candidate hợp lệ; replace cũng cần tuân theo các ràng buộc tham số của lớp.

Khóa phải so sánh được theo thứ tự tự nhiên hoặc comparator cấu hình. Tính nguyên tử của cập nhật không sửa được một comparator sai hay một khóa bị thay đổi các trường quyết định thứ tự trong khi còn nằm trong map.

## 10. Kiểm thử và thực hành

Bộ kiểm thử nên đánh giá cả kết quả trả về và ánh xạ sau thao tác:

1. Khóa vắng: `putIfAbsent` chèn; remove có điều kiện trả false; replace không tự chèn.
2. Khóa có giá trị đúng expected: remove hoặc replace thành công.
3. Khóa có giá trị khác expected: thao tác thất bại và không ghi đè giá trị mới.
4. Hai đối tượng giá trị khác tham chiếu nhưng bằng nhau: điều kiện vẫn có thể khớp.
5. Hai luồng cùng chuyển từ một trạng thái, không có bước đặt lại trạng thái ấy: chỉ một lần thành công.
6. Cùng phase nhưng khác version: expected cũ không được phép sửa trạng thái thế hệ mới.
7. Candidate được tạo nhưng không chèn: xác minh quy tắc sở hữu tài nguyên nếu có.

Bài tập: thêm giai đoạn cho hai luồng cùng thử `remove(key, expected)` trên một ánh xạ cố định, không có luồng đăng ký lại trong giai đoạn ấy. Đếm số lần trả true và giải thích vì sao chỉ có một lần xóa thành công. Sau đó phân tích điều gì thay đổi nếu cho phép một luồng chèn lại cùng giá trị giữa hai lần remove.
