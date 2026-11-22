# Chia sẻ đối tượng và tác động của thay đổi trạng thái trong Java

Một đối tượng có thể được nhiều thành phần của chương trình **cùng sử dụng**. Điều này rất hữu ích khi tất cả cần làm việc trên một trạng thái chung; nhưng nếu đối tượng có thể thay đổi (*mutable*), thao tác ở một nơi có thể tạo ra kết quả bất ngờ ở nơi khác.

Bài này tập trung vào ba câu hỏi thực tế:

1. **Ai đang giữ tham chiếu tới đúng instance được thay đổi?**
2. **Ai có quyền cập nhật trạng thái, và các bên còn lại quan sát thay đổi khi nào?**
3. **Khi nào cần chia sẻ trạng thái đang sống (*live state*), khi nào cần một ảnh chụp (*snapshot*) độc lập?**

Phép gán `b = a` sao chép giá trị tham chiếu; nó không nhân bản object. Tuy nhiên, chỉ biết có nhiều alias là chưa đủ để thiết kế an toàn: cần hiểu **đường đi của tác động thay đổi** qua nhiều đối tượng và hợp đồng giữa các thành phần.

## 1. Một thay đổi có thể lan qua các thành phần mà không cần gọi trực tiếp nhau

Giả sử ứng dụng điều khiển nhiệt độ phòng có hai giao diện:

- `MobileControl` thay đổi nhiệt độ mục tiêu.
- `WallDisplay` hiển thị nhiệt độ mục tiêu hiện tại.
- Cả hai được khởi tạo với **cùng một `TemperaturePolicy`**, là đối tượng nắm trạng thái và kiểm tra giá trị hợp lệ.

Khi điện thoại thay đổi mục tiêu từ 22°C lên 24°C, màn hình tường **không cần được truyền một bản sao mới của policy**. Lần tiếp theo `WallDisplay` đọc đối tượng được chia sẻ, nó thấy 24°C.

Điểm tinh tế: việc thay đổi object **không tự động ép giao diện vẽ lại**. Trong ví dụ, `render()` phải được gọi lại; UI thực tế cần cơ chế thông báo, event, polling hoặc cập nhật trạng thái phù hợp để biết lúc nào render.

~~~mermaid
flowchart LR
    M["MobileControl"] -->|giữ tham chiếu| P["TemperaturePolicy<br/>target = 24"]
    W["WallDisplay"] -->|giữ tham chiếu| P
    M -. "changeTarget(24)" .-> P
    P -. "lần đọc tiếp theo" .-> W
~~~

Mũi tên biểu diễn **quan hệ tham chiếu và thao tác trên object**. Chúng không phải khẳng định về cách JVM bố trí bộ nhớ.

## 2. Ví dụ Java hoàn chỉnh: trạng thái sống, snapshot và gán lại tham chiếu

Lưu vào `SharingScenario.java`, chạy với JDK 17+:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SharingScenario {
    static final class TemperaturePolicy {
        private int targetCelsius;
        private final List<String> history = new ArrayList<>();

        TemperaturePolicy(int initial) {
            validate(initial);
            targetCelsius = initial;
        }

        private static void validate(int value) {
            if (value < 16 || value > 30) {
                throw new IllegalArgumentException(
                        "Mục tiêu phải trong khoảng 16..30");
            }
        }

        void setTarget(int newValue) {
            validate(newValue);
            int oldValue = targetCelsius;
            targetCelsius = newValue;
            history.add(oldValue + " -> " + newValue);
        }

        int getTarget() {
            return targetCelsius;
        }

        List<String> getHistorySnapshot() {
            return List.copyOf(history);
        }
    }

    static final class MobileControl {
        private final TemperaturePolicy policy;

        MobileControl(TemperaturePolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        void changeTarget(int value) {
            policy.setTarget(value);
        }
    }

    static final class WallDisplay {
        private final TemperaturePolicy policy;

        WallDisplay(TemperaturePolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        String render() {
            return "Mục tiêu: " + policy.getTarget() + "°C";
        }

        boolean uses(TemperaturePolicy other) {
            return policy == other;
        }
    }

    public static void main(String[] args) {
        TemperaturePolicy shared = new TemperaturePolicy(22);
        MobileControl mobile = new MobileControl(shared);
        WallDisplay wall = new WallDisplay(shared);

        String oldRenderedText = wall.render(); // Ảnh chụp dạng String
        List<String> oldHistory = shared.getHistorySnapshot();

        mobile.changeTarget(24);

        System.out.println(wall.uses(shared)); // true
        System.out.println(oldRenderedText);
        System.out.println(wall.render());
        System.out.println(oldHistory);
        System.out.println(shared.getHistorySnapshot());

        // Gán lại biến cục bộ mobile không thay reference trong wall.
        TemperaturePolicy replacement = new TemperaturePolicy(18);
        mobile = new MobileControl(replacement);
        mobile.changeTarget(19);

        System.out.println(wall.render());
        System.out.println(replacement.getTarget());
    }
}
~~~

Chạy:

~~~bash
javac SharingScenario.java
java SharingScenario
~~~

Kết quả:

~~~text
true
Mục tiêu: 22°C
Mục tiêu: 24°C
[]
[22 -> 24]
Mục tiêu: 24°C
19
~~~

### Vì sao kết quả này đúng?

**Lần khởi tạo:** `shared`, field `policy` của `mobile` và field `policy` của `wall` đều trỏ tới cùng một `TemperaturePolicy`. Các đối tượng giao diện là hai instance khác nhau; **policy** mới là đối tượng được chia sẻ.

**Lần cập nhật đầu tiên:** `mobile.changeTarget(24)` gọi `setTarget(24)` trên chính policy ấy. `wall.render()` đọc trường mới, vì thế trả `"Mục tiêu: 24°C"`. Không có `new TemperaturePolicy` trong quá trình cập nhật này.

**Snapshot:** `oldRenderedText` là giá trị `String` đã được tạo lúc mục tiêu còn là 22. `String` bất biến, nên chuỗi này vẫn là `"Mục tiêu: 22°C"`. `oldHistory` là một snapshot cấu trúc của danh sách ở thời điểm còn trống, vì `List.copyOf` không phản ánh phần tử được thêm sau đó vào `history`. Các phần tử `String` ở đây cũng bất biến.

**Lần gán lại:** sau khi `mobile = new MobileControl(replacement)`, chỉ biến `mobile` ở `main` trỏ đến một bộ điều khiển khác. `wall` tiếp tục giữ policy cũ ở mức 24, còn policy mới tăng từ 18 lên 19. Việc gán lại một biến không cập nhật mọi tham chiếu khác trong chương trình.

## 3. Lập bảng tác động: đối tượng nào thật sự bị sửa?

| Thời điểm | Thao tác | Policy cũ mà `wall` giữ | Policy mới | Văn bản `oldRenderedText` |
|---|---|---:|---:|---|
| Khởi tạo | `new TemperaturePolicy(22)` | 22 | Chưa có | "Mục tiêu: 22°C" |
| Sau điện thoại đổi | `mobile.changeTarget(24)` | 24 | Chưa có | "Mục tiêu: 22°C" |
| Tạo bộ điều khiển khác | `mobile = new MobileControl(replacement)` | 24 | 18 | "Mục tiêu: 22°C" |
| Điện thoại đổi lần nữa | `mobile.changeTarget(19)` | 24 | 19 | "Mục tiêu: 22°C" |

Bảng này tách hai loại trạng thái:

- **Trạng thái đang sống:** `wall.render()` lấy dữ liệu từ đối tượng `TemperaturePolicy` đang được `wall` tham chiếu **tại thời điểm gọi**.
- **Giá trị đã chụp:** `oldRenderedText` và `oldHistory` giữ dữ liệu tại thời điểm lấy snapshot; chúng không tự cập nhật theo policy.

Khi debug, thay vì hỏi mơ hồ “vì sao màn hình sai?”, hãy xác định: **màn hình đang trỏ tới policy nào, đang dùng dữ liệu mới đọc hay dữ liệu được cache trước đó?**

## 4. Chia sẻ trực tiếp và chia sẻ qua cấu trúc lồng nhau

Chia sẻ không chỉ xảy ra qua `TemperaturePolicy b = a`. Một instance cũng có thể đi qua constructor, getter, tham số phương thức hoặc collection.

~~~java
final class Device {
    final TemperaturePolicy policy;

    Device(TemperaturePolicy policy) {
        this.policy = policy;
    }
}

TemperaturePolicy policy = new TemperaturePolicy(22);
Device heater = new Device(policy);
Device airConditioner = new Device(policy);

heater.policy.setTarget(23);
System.out.println(airConditioner.policy.getTarget()); // 23
~~~

Đoạn trên là minh họa ngắn đặt trong ngữ cảnh có thể truy cập các lớp ở ví dụ chính. **Hai `Device` khác nhau** vẫn giữ cùng đối tượng con `TemperaturePolicy`. Vì vậy không thể suy ra rằng “đã tạo hai đối tượng cha thì mọi trạng thái bên trong đều độc lập”.

Ngược lại, nếu mỗi thiết bị có một policy mới:

~~~java
Device heater = new Device(new TemperaturePolicy(22));
Device airConditioner = new Device(new TemperaturePolicy(22));
~~~

thì thay đổi policy của máy sưởi không làm đổi policy của máy lạnh. Hai đối tượng có cùng dữ liệu ban đầu vẫn có **danh tính khác nhau**.

### Collection và registry cũng có thể giữ alias

~~~java
Map<String, TemperaturePolicy> registry = new HashMap<>();
registry.put("living-room", policy);

TemperaturePolicy fromRegistry = registry.get("living-room");
System.out.println(fromRegistry == policy); // true
~~~

Đoạn này cần `import java.util.Map;` và `import java.util.HashMap;`, với biến `policy` đã khai báo. `Map.put/get` lưu và trả về **tham chiếu tới phần tử**, không tự nhân bản `TemperaturePolicy`.

Nếu sau đó `registry.put("living-room", new TemperaturePolicy(18))`, map trỏ sang policy mới tại key đó; một `WallDisplay` đã giữ tham chiếu tới policy cũ **không tự chuyển theo**. Đây là lỗi phổ biến khi thay đối tượng trong registry/cache nhưng các thành phần khác vẫn giữ tham chiếu cũ.

## 5. Ai sở hữu trạng thái? Hợp đồng quan trọng hơn cú pháp

Khi truyền một đối tượng mutable giữa các thành phần, hãy nói rõ **ai được sửa** và **ai chỉ được quan sát**.

| Kiểu hợp đồng | Ý nghĩa | Hệ quả người gọi cần biết |
|---|---|---|
| **Live shared object** | Hai bên giữ đúng một instance mutable | Mutation ở một bên có thể xuất hiện khi bên kia đọc lại |
| **Read-only API trên live object** | Bên nhận chỉ được gọi phương thức đọc; nơi khác vẫn có thể sửa object | Kết quả đọc ở hai thời điểm vẫn có thể khác |
| **Snapshot giá trị** | Bên nhận giữ dữ liệu tại một thời điểm | Giá trị cũ không tự phản ánh cập nhật mới |
| **Independent mutable copy** | Bên nhận sở hữu bản sao các thành phần mutable cần thiết | Mutation của bản sao không ảnh hưởng dữ liệu nguồn trong phạm vi đã tách |
| **Immutable value object** | Dữ liệu không thay đổi sau khởi tạo | An toàn hơn khi chia sẻ; cập nhật thường trả giá trị khác |

Ví dụ `getHistorySnapshot()` ở chương trình chính trả `List.copyOf(history)` vì lịch sử gồm `String` bất biến. Nếu lịch sử chứa đối tượng phần tử mutable, snapshot danh sách **không bảo đảm snapshot sâu của phần tử**. Muốn tách biệt hoàn toàn, cần một copy strategy phù hợp với các đối tượng con như bài *Sao chép nông và sao chép sâu* đã phân tích.

Hãy tránh tên API mơ hồ kiểu `getData()` nếu người dùng không biết nhận một view đang sống, một bản sao hay một giá trị bất biến. Có thể chọn tên thể hiện ý định như `getHistorySnapshot()`, `currentTarget()`, `withUpdatedTarget(...)` và ghi rõ khả năng mutation trong tài liệu.

## 6. Thay đổi trạng thái không đồng nghĩa tự động phát ra thông báo

Ví dụ `WallDisplay.render()` đọc dữ liệu hiện hành mỗi lần gọi; nhưng nếu màn hình chỉ render **một lần** và giữ chuỗi đó trong cache, thay đổi policy không khiến chuỗi cũ biến thành chuỗi mới.

Trong ứng dụng tương tác, có thể cần một trong những cơ chế sau:

- Giao diện chủ động **đọc lại** khi người dùng mở trang hoặc bấm Refresh.
- Bên cập nhật **phát sự kiện** chứa dữ liệu thay đổi, bên quan tâm đăng ký nhận.
- Một state manager quản lý subscription và thông báo khi state được cập nhật.
- Dịch vụ khác truy xuất trạng thái mới qua API hoặc message, thay vì dựa vào tham chiếu chung trong cùng JVM.

Chia sẻ tham chiếu chỉ cho phép nhiều thành phần **truy cập cùng trạng thái** trong một tiến trình; nó không tự tạo cơ chế reactive UI, không tự thông báo qua mạng và không làm hai JVM chia sẻ một Java object.

Khi dùng event, hãy xác định event mang một snapshot bất biến hay tham chiếu đến object mutable: nếu chỉ chuyển cùng tham chiếu, nội dung có thể thay đổi **sau thời điểm phát sự kiện**, khiến người nhận quan sát giá trị khác dự kiến.

## 7. Rủi ro ngoài ý muốn và cách giảm tác dụng phụ

Một số vấn đề phát sinh trực tiếp từ shared mutable state:

**Sửa dữ liệu mà caller không biết.** Một helper `normalize(profile)` nhận `Profile` rồi sửa trực tiếp field có thể khiến đoạn code gọi helper quan sát profile đổi trạng thái. Nếu helper thực sự có quyền sửa, nên ghi rõ trong API; nếu chỉ chuẩn hóa dữ liệu để kiểm tra, hãy trả giá trị mới hoặc thao tác trên bản sao.

**Rò rỉ tham chiếu nội bộ.** Getter trả thẳng `List` mutable khiến code ngoài bỏ qua quy tắc `addItem/removeItem`. Trả danh sách unmodifiable chỉ chặn thao tác qua view; nếu có tham chiếu khác sửa list gốc, view vẫn có thể đổi. Snapshot với dữ liệu bất biến hoặc API truy vấn chuyên biệt là lựa chọn khác.

**Thay reference ở một nơi nhưng không thay ở nơi khác.** `registry.put(key, replacement)` cập nhật registry; các object đã cache `oldReference` vẫn nhìn vào instance cũ. Cần chiến lược cập nhật tham chiếu nhất quán hoặc một holder/service ổn định mà các bên cùng truy vấn.

**Giữ chia sẻ không có chủ đích quá lâu.** Một thành phần còn giữ tham chiếu có thể khiến trạng thái vẫn reachable dù phần khác đã bỏ nó. Đây là vấn đề vòng đời/ownership, không nên cố “giải phóng object” bằng `a = null` và giả định mọi alias khác biến mất.

Cần chọn thiết kế dựa trên **ý định nghiệp vụ**. Chia sẻ cùng đối tượng cài đặt service/cấu hình có thể đúng; sao chép máy móc mọi object có thể vừa tốn bộ nhớ vừa phá hỏng quan hệ chia sẻ mà hệ thống cần.

## 8. Khi nhiều luồng cùng thay đổi một object

Các ví dụ trước thực thi tuần tự trong **một luồng**; aliasing và tác động lan truyền đã tồn tại. Khi hai luồng đồng thời cập nhật cùng đối tượng mutable, cần xét thêm **atomicity** và **visibility**.

~~~java
class UnsafeCounter {
    private int value;

    void increment() {
        value++; // Read -> calculate -> write, không nguyên tử.
    }

    int getValue() {
        return value;
    }
}
~~~

Nếu hai luồng đều gọi `increment()`, cả hai có thể đọc cùng giá trị cũ rồi ghi trùng kết quả, dẫn tới **lost update**. Từ khóa `private` không giải quyết race condition.

Với **một bộ đếm độc lập**, có thể dùng:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class SafeCounter {
    private final AtomicInteger value = new AtomicInteger();

    void increment() {
        value.incrementAndGet();
    }

    int current() {
        return value.get();
    }
}
~~~

Nhưng với **nhiều field có invariant chung**, chỉ biến từng field thành atomic/volatile có thể vẫn để lộ trạng thái trung gian không hợp lệ. Ví dụ khoảng nhiệt độ phải thỏa `min <= max` có thể đóng gói như một giá trị bất biến rồi thay tham chiếu nguyên khối:

~~~java
record TemperatureRange(int min, int max) {
    TemperatureRange {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
    }
}

final class RangeConfiguration {
    private volatile TemperatureRange current =
            new TemperatureRange(18, 26);

    TemperatureRange snapshot() {
        return current;
    }

    void replace(int min, int max) {
        current = new TemperatureRange(min, max);
    }
}
~~~

Đây là một ví dụ về **đọc snapshot nhất quán của một cặp giá trị** nhờ đối tượng bất biến và phép gán tham chiếu `volatile`. Nếu nhiều người ghi cần tránh ghi đè nhau hoặc thực hiện update dựa trên giá trị cũ, vẫn cần đồng bộ hoặc compare-and-set phù hợp. Không suy ra mọi nghiệp vụ đa luồng đã an toàn chỉ vì dùng immutable record.

## 9. Phương pháp truy vết tác động trạng thái

Khi gặp bug “tôi chỉ sửa A mà B cũng thay đổi”, hãy ghi bốn cột sau:

| Bước | Ai thực hiện? | Tham chiếu đang trỏ tới instance nào? | Trạng thái quan sát được |
|---|---|---|---|
| T0 | `main` tạo `shared` | `wall.policy → Policy #1` | target = 22 |
| T1 | `mobile.changeTarget(24)` | `mobile.policy → Policy #1` | target = 24 |
| T2 | `wall.render()` | `wall.policy → Policy #1` | hiển thị 24 |
| T3 | `mobile` gán sang controller khác | controller mới → Policy #2 | Policy #1 vẫn 24 |
| T4 | controller mới thay Policy #2 | controller mới → Policy #2 | #2 = 19; #1 = 24 |

Sau đó kiểm tra lần lượt: (1) lệnh nào thực sự tạo `new` instance, (2) lệnh nào chỉ sao chép/gán lại tham chiếu, (3) phương thức nào sửa trạng thái, (4) ai đang giữ dữ liệu snapshot, (5) nếu có nhiều luồng, có thiếu cơ chế đồng bộ hay không.

Với debugger, có thể đặt breakpoint ở `TemperaturePolicy.setTarget` và `WallDisplay.render`; kiểm tra **identity** của object được gọi, call stack và các field trước/sau. Log nên ghi tên đối tượng nghiệp vụ hoặc correlation ID theo yêu cầu, không dựa vào `identityHashCode` như mã duy nhất.

## 10. Bài tập và đáp án

**Bài 1 — Hiệu ứng lên các thành phần:** Hai `WallDisplay` cùng nhận một `TemperaturePolicy`. Một `MobileControl` thay target từ 20 thành 25. Khi hai màn hình gọi `render()` lại, chúng hiển thị gì?

**Đáp án:** Cả hai hiển thị 25°C nếu vẫn tham chiếu đúng instance được thay đổi và không áp dụng logic biến đổi khác. Nội dung render đã lưu trước đó không tự đổi.

**Bài 2 — Snapshot có tự cập nhật không?** `List<String> history = policy.getHistorySnapshot();` được gọi khi lịch sử rỗng. Sau đó thêm một thay đổi vào policy. `history.size()` là bao nhiêu?

**Đáp án:** 0. Danh sách kết quả là snapshot cấu trúc tại thời điểm lấy, không phản ánh các phần tử thêm sau đó vào list nguồn.

**Bài 3 — Thay thế trong map:** `WallDisplay` đã lưu `Policy #1`; map `registry` thay key bằng `Policy #2`. Không thay field của `WallDisplay`. Màn hình đọc object nào?

**Đáp án:** Vẫn đọc `Policy #1`. Map và màn hình giữ **hai biến tham chiếu độc lập**; gán lại giá trị tại key của map không tự đổi field trong màn hình.

**Bài 4 — Thiết kế hợp đồng:** Một dịch vụ muốn cho các màn hình thấy thay đổi cấu hình mới nhất nhưng không được tự ý sửa cấu hình. Nên cung cấp API nào?

**Gợi ý:** Cung cấp một service/holder làm chủ mutation, API truy vấn trạng thái hiện hành hoặc snapshot bất biến, và cơ chế thông báo phù hợp để trigger refresh. Không công khai tham chiếu mutable cho mọi caller. Nếu nhiều luồng, kiểm soát visibility và tính nguyên tử của state.

**Bài 5 — Đồng thời:** Vì sao `volatile int count` chưa đủ làm cho `count++` nguyên tử?

**Đáp án:** `volatile` giúp visibility cho đọc/ghi field, nhưng `count++` gồm đọc, cộng và ghi riêng; hai luồng có thể chen ngang. Dùng atomic increment hoặc khóa khi cần tăng an toàn.

## Ghi nhớ

**Chia sẻ object** là nhiều thành phần có đường tham chiếu tới đúng một instance. Nếu instance mutable, thay đổi qua một đường có thể được quan sát qua đường khác khi đọc lại. Muốn quản lý tác động có chủ đích, cần xác định **owner của trạng thái**, hợp đồng live reference hay snapshot, thời điểm cập nhật giao diện và cơ chế đồng bộ khi nhiều luồng cùng làm việc.