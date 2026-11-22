# Mô hình hóa trạng thái nghiệp vụ bằng enum và EnumMap

## 1. Từ tên trạng thái đến quy tắc chuyển trạng thái

Một đối tượng nghiệp vụ thường chỉ được phép ở một trong số hữu hạn trạng thái: đơn hàng đang soạn, đã xác nhận, đã gửi hoặc đã hủy. Nếu dùng chuỗi tùy ý, lỗi chính tả và giá trị không hợp lệ có thể đi sâu vào hệ thống. `enum` giúp biểu diễn tập trạng thái được phép ở mức kiểu dữ liệu.

Tuy nhiên, có một giá trị enum hợp lệ chưa đủ để việc chuyển trạng thái là hợp lệ. “Đã gửi” và “đã hủy” đều là trạng thái có thật, nhưng một quy trình có thể không cho phép chuyển trực tiếp từ đã gửi sang đã hủy.

Tách hai phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `enum OrderState` | Những trạng thái nào tồn tại trong mô hình |
| Bảng chuyển trạng thái | Từ mỗi trạng thái được chuyển đến những trạng thái nào |
| Đối tượng `Order` | Giữ trạng thái hiện tại của từng đơn và thực thi quy tắc khi thay đổi |

`EnumMap` phù hợp để tra quy tắc theo khóa enum; `EnumSet` phù hợp chứa tập đích enum. Hai kiểu này vẫn được hỗ trợ trên JDK hiện đại. [API EnumMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumMap.html), [API EnumSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html).

## 2. Định nghĩa phạm vi nghiệp vụ trước khi viết bảng

Bài thực hành chọn quy trình đơn giản sau:

| Trạng thái | Ý nghĩa | Đích được phép |
| --- | --- | --- |
| `DRAFT` | Đơn đang được soạn | `CONFIRMED`, `CANCELLED` |
| `CONFIRMED` | Đơn đã xác nhận, chưa gửi | `SHIPPED`, `CANCELLED` |
| `SHIPPED` | Đơn đã gửi | Không có trong phạm vi ví dụ |
| `CANCELLED` | Đơn đã hủy | Không có trong phạm vi ví dụ |

Đây là quy tắc của mô hình minh họa, không phải quy tắc chung cho mọi hệ thống bán hàng. Hoàn trả hàng, hoàn tiền hoặc mở lại đơn không thuộc mô hình này. Nếu cần chúng, phải xác định lại quy trình thay vì tự cho phép “quay về enum đứng trước”.

Trong phạm vi bài học, `SHIPPED` và `CANCELLED` là trạng thái kết thúc vì không có cạnh chuyển ra. Tính kết thúc đến từ quy tắc nghiệp vụ, không phải do tên hoặc vị trí khai báo enum.

```text
DRAFT -------> CONFIRMED -------> SHIPPED
  |                 |
  +-----------------+----------> CANCELLED
```

Sơ đồ thể hiện quan hệ được phép; nó không biểu diễn mọi điều kiện cần kiểm tra như quyền người thao tác hoặc dữ liệu vận chuyển.

## 3. enum biểu diễn kiểu, không giữ dữ liệu riêng của từng đơn

Khai báo trạng thái:

```java
enum OrderState {
    DRAFT, CONFIRMED, SHIPPED, CANCELLED
}
```

Có thể so sánh các giá trị cùng kiểu enum bằng `==`. Tên biến, tham số và trường có kiểu `OrderState` sẽ tránh nhận tùy tiện một chuỗi khác vào luồng xử lý nội bộ.

Một điều quan trọng là mỗi hằng enum là một đối tượng dùng chung. Không đặt trạng thái hiện tại của một đơn hàng, mã khách hàng hoặc dữ liệu có thể thay đổi theo từng đơn vào trường của hằng enum. Mỗi `Order` phải có trường `state` riêng; enum chỉ biểu diễn loại trạng thái.

`ordinal()` trả vị trí khai báo, không phải thứ tự nghiệp vụ. Không dùng `next.ordinal() > current.ordinal()` để cho phép chuyển, không dùng `ordinal() + 1` để tìm trạng thái kế tiếp và không dùng số thứ tự ấy làm mã lưu trữ bền vững. Chèn hoặc đổi thứ tự hằng sẽ làm ý nghĩa vị trí thay đổi. [API Enum.ordinal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#ordinal()).

## 4. EnumMap và EnumSet tạo thành bảng quy tắc rõ ràng

Cấu trúc định hướng:

```java
EnumMap<OrderState, Set<OrderState>> rules = new EnumMap<>(OrderState.class);
```

Khóa là trạng thái hiện tại; giá trị là tập trạng thái đích. Ví dụ `rules.get(CONFIRMED)` trả tập chứa `SHIPPED` và `CANCELLED` trong mô hình đang dùng.

Một `EnumMap` chỉ dùng khóa của một kiểu enum. Nó duyệt khóa theo thứ tự khai báo và không cho khóa `null`; giá trị `null` vẫn được phép theo API. Trong mô hình quy tắc này, ta chủ động không sử dụng giá trị `null` để tránh nhầm “chưa khai báo quy tắc” với “trạng thái không có đích”. [API EnumMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumMap.html).

Với trạng thái kết thúc, khai báo một tập rỗng rõ ràng. `EnumSet.noneOf(OrderState.class)` tạo được tập rỗng mà vẫn biết kiểu enum. Không dùng một tập `null` và chờ mã kiểm tra tự hiểu.

Thứ tự duyệt ổn định hữu ích cho in báo cáo hoặc trình bày quy tắc, nhưng không tự có nghĩa là thứ tự đi qua quy trình. Tương tự, `EnumSet.range(...)` dựa trên thứ tự enum, không phải phép tìm các trạng thái có thể đi tới trong đồ thị nghiệp vụ.

## 5. Chương trình Java 17+ chạy đầy đủ

Chương trình sau có bảng chuyển trạng thái tập trung, khai báo đầy đủ mỗi trạng thái và bảo vệ cả map lẫn các tập đích khỏi sửa qua API công khai. Phương thức chuyển kiểm tra trước, chỉ cập nhật khi hợp lệ.

Lưu thành `OrderStateDemo.java`:

```java
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class OrderStateDemo {
    enum OrderState { DRAFT, CONFIRMED, SHIPPED, CANCELLED }

    private static final Map<OrderState, Set<OrderState>> RULES = buildRules();

    private static Set<OrderState> targets(OrderState... states) {
        EnumSet<OrderState> result = EnumSet.noneOf(OrderState.class);
        Collections.addAll(result, states);
        return Collections.unmodifiableSet(result);
    }

    private static Map<OrderState, Set<OrderState>> buildRules() {
        EnumMap<OrderState, Set<OrderState>> rules = new EnumMap<>(OrderState.class);
        rules.put(OrderState.DRAFT, targets(OrderState.CONFIRMED, OrderState.CANCELLED));
        rules.put(OrderState.CONFIRMED, targets(OrderState.SHIPPED, OrderState.CANCELLED));
        rules.put(OrderState.SHIPPED, targets());
        rules.put(OrderState.CANCELLED, targets());
        if (!rules.keySet().equals(EnumSet.allOf(OrderState.class))) {
            throw new IllegalStateException("Missing transition rule");
        }
        return Collections.unmodifiableMap(rules);
    }

    static final class Order {
        private OrderState state = OrderState.DRAFT;

        synchronized OrderState state() {
            return state;
        }

        synchronized void transitionTo(OrderState next) {
            Objects.requireNonNull(next, "next");
            if (!RULES.get(state).contains(next)) {
                throw new IllegalStateException(state + " -> " + next);
            }
            state = next;
        }
    }

    public static void main(String[] args) {
        Order order = new Order();
        System.out.println("start=" + order.state());
        order.transitionTo(OrderState.CONFIRMED);
        System.out.println("afterConfirm=" + order.state());
        order.transitionTo(OrderState.SHIPPED);
        System.out.println("afterShip=" + order.state());
        try {
            order.transitionTo(OrderState.CANCELLED);
        } catch (IllegalStateException rejected) {
            System.out.println("rejected=" + rejected.getMessage());
        }
        System.out.println("unchanged=" + order.state());
        System.out.println("rulesCovered=" + RULES.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 OrderStateDemo.java
java OrderStateDemo
```

Stdout:

```text
start=DRAFT
afterConfirm=CONFIRMED
afterShip=SHIPPED
rejected=SHIPPED -> CANCELLED
unchanged=SHIPPED
rulesCovered=4
```

Không cần thư viện ngoài hoặc framework. `rejected` là kết quả từ một yêu cầu chuyển không được phép trong mô hình; không phải JVM tự biết quy tắc đơn hàng. Chính `transitionTo()` và bảng `RULES` thực thi điều đó.

## 6. Đọc cơ chế của ví dụ theo từng trách nhiệm

### Xây dựng bảng một lần

`buildRules()` tạo `EnumMap` với kiểu khóa tường minh, điền một hàng cho mọi trạng thái rồi kiểm tra độ phủ. Nếu thêm một hằng enum nhưng quên khai báo hàng tương ứng, bước kiểm tra sẽ báo thiếu quy tắc khi khởi tạo lớp.

Độ phủ không chứng minh quy tắc đúng: vẫn có thể khai báo một cạnh không được nghiệp vụ cho phép. Nó giúp biến lỗi bỏ sót thành lỗi rõ ràng thay vì một `NullPointerException` phát sinh muộn trong xử lý đơn hàng.

### Dùng tập rỗng cho trạng thái kết thúc

`targets()` không nhận phần tử tạo một `EnumSet` rỗng. Vì vậy, `RULES.get(SHIPPED).contains(next)` luôn trả `false` với mọi đích trong mô hình. Không cần một nhánh đặc biệt đặt tên trạng thái kết thúc rải rác trong nhiều phương thức.

### Kiểm tra rồi mới cập nhật

`transitionTo(next)` thực hiện ba bước trong cùng phạm vi kiểm soát:

1. Từ chối đích `null`.
2. Kiểm tra cạnh từ trạng thái hiện tại tới đích.
3. Chỉ gán `state = next` nếu cạnh hợp lệ.

Khi bị từ chối, trường trạng thái không thay đổi. Không viết mã gán trước rồi cố khôi phục trong `catch`, vì cách đó làm việc giữ bất biến phức tạp hơn và có thể để phần khác quan sát trạng thái sai.

Trong ví dụ, chuyển sang chính trạng thái hiện tại cũng bị từ chối vì không có cạnh tự nối. Nếu nghiệp vụ muốn thao tác lặp lại có tính lũy đẳng, cần xác định quy tắc đó riêng, không tự bỏ qua mọi trường hợp trùng trạng thái.

## 7. static final không đồng nghĩa toàn bộ cấu trúc bất biến

Nếu chỉ khai báo:

```java
private static final EnumMap<OrderState, EnumSet<OrderState>> rules =
        new EnumMap<>(OrderState.class);
```

`final` ngăn gán lại biến `rules`, nhưng không ngăn `put()`, `clear()` hoặc sửa một `EnumSet` đang nằm trong map. Đoạn này chỉ minh họa khác biệt, không phải bảng hoàn chỉnh thay cho chương trình ở trên.

Trong chương trình đầy đủ:

- `targets()` tạo tập đích rồi bọc bằng `Collections.unmodifiableSet(...)`.
- `buildRules()` giữ map xây dựng ở phạm vi cục bộ, sau đó bọc bằng `Collections.unmodifiableMap(...)`.
- Không trả ra tham chiếu có thể sửa của các cấu trúc nền.

Bọc chỉ map ngoài mà để tập bên trong sửa được vẫn có thể làm quy tắc thay đổi ngoài ý muốn. Sao chép nông map cũng không tự sao chép các giá trị tập hợp bên trong.

`EnumMap` tự nó không phải map đồng bộ. Việc dùng một bảng được xây dựng xong, công bố an toàn và không thay đổi khác với dùng nó như một nơi lưu trạng thái đang cập nhật đồng thời. [API EnumMap về đồng bộ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumMap.html).

## 8. Bảng đích chưa thay cho mọi điều kiện nghiệp vụ

Bảng trong bài trả lời: “Từ trạng thái này, về mặt cấu trúc quy trình có thể đi tới trạng thái nào?” Nó không trả lời toàn bộ những câu hỏi sau:

| Điều kiện bổ sung | Ví dụ |
| --- | --- |
| Quyền thực hiện | Người gọi có được xác nhận hoặc hủy đơn này không? |
| Dữ liệu cần có | Có địa chỉ hợp lệ hoặc thông tin giao nhận chưa? |
| Điều kiện tại thời điểm thao tác | Hàng còn sẵn, phiên bản đơn còn đúng hay đã có cập nhật khác? |
| Tác động liên quan | Giữ hàng, gửi thông báo, ghi lịch sử chuyển trạng thái |

Đặt các kiểm tra này tại lớp điều phối/đối tượng nghiệp vụ phù hợp và đảm bảo chúng nhất quán với việc cập nhật. Không biến map trạng thái thành nơi cất tùy tiện mọi dependency dịch vụ.

Một API nghiệp vụ thường có các hành động rõ nghĩa như `confirm()` hoặc `ship()`, rồi mới quyết định chuyển trạng thái. Điều này giúp tránh để bên gọi đặt trực tiếp một trạng thái đích nhằm bỏ qua kiểm tra của hành động. Hàm `transitionTo()` công khai trong bài phục vụ quan sát cơ chế; thiết kế sản phẩm có thể thu hẹp quyền truy cập của nó.

Nếu hành động, điều kiện và kết quả trở nên phức tạp, có thể mở rộng thành bảng theo sự kiện, ví dụ `EnumMap<State, EnumMap<Event, Rule>>`, hoặc dùng thiết kế hành vi khác. Chỉ mở rộng khi mô hình cần; quy trình bốn trạng thái không buộc phải dùng một framework máy trạng thái.

## 9. Đồng thời và lưu trữ phải giữ được phép chuyển nguyên tử

Hai phương thức của `Order` được đánh dấu `synchronized` để việc đọc và chuỗi kiểm tra–gán của cùng một đối tượng được bảo vệ trong một JVM. Nó không biến mọi trạng thái của ứng dụng thành an toàn luồng và không khóa được một đơn tương ứng nằm trong tiến trình khác.

Trong hệ thống lưu cơ sở dữ liệu, hai yêu cầu có thể đọc cùng một trạng thái cũ từ hai bản đối tượng khác nhau. Cần chiến lược cập nhật nguyên tử phù hợp, chẳng hạn giao dịch/khóa hoặc kiểm tra phiên bản. Nếu cập nhật thất bại vì xung đột, phải đọc lại và đánh giá quy tắc theo trạng thái mới; không ghi đè mù quáng kết quả của bên khác.

Không dùng `EnumMap<OrderState, Order>` làm nơi giữ mọi đơn hàng: khóa của map đó chỉ là trạng thái, nên một lần `put` cùng khóa sẽ thay giá trị trước. Bảng quy tắc và kho lưu đối tượng có mục đích khác nhau. Kho đơn hàng thường được tra theo mã định danh đơn; mỗi đơn có trạng thái riêng.

## 10. Biên API và cơ sở dữ liệu cần mã có hợp đồng

Bên ngoài JVM thường gửi/nhận chuỗi hoặc mã. Chuyển đổi tại biên vào kiểu enum và xử lý giá trị không biết rõ ràng; không để một giá trị lạ tự thành `DRAFT` rồi tiếp tục quy trình.

`Enum.valueOf()` yêu cầu tên hằng phù hợp chính xác và ném lỗi với tên không có trong kiểu. Nếu tên Java chính là hợp đồng API/lưu trữ, đổi tên hằng sẽ ảnh hưởng tương thích. Nếu muốn tách tên mã nguồn khỏi hợp đồng, định nghĩa mã ổn định và phép ánh xạ tường minh, kèm cách xử lý mã chưa biết. [API Enum.valueOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)).

Không dùng `ordinal()` làm mã lưu trữ lâu dài. Cũng không dùng `toString()` đã được đổi để hiển thị bản dịch làm mã trao đổi. Nhãn tiếng Việt cho người dùng và mã trạng thái ổn định là hai trách nhiệm khác nhau.

Thêm một trạng thái mới cần xem cả quy tắc chuyển, dữ liệu đã lưu, API cũ, báo cáo và giao diện. Một bảng đủ khóa chỉ là một kiểm tra kỹ thuật trong thay đổi đó.

## 11. Thực hành kiểm chứng mô hình

Không chỉ thử đường đi thành công. Các tình huống có giá trị học tập gồm:

| Tình huống | Kỳ vọng theo mô hình hiện tại |
| --- | --- |
| `DRAFT -> CONFIRMED -> SHIPPED` | Hợp lệ |
| `DRAFT -> CANCELLED` | Hợp lệ |
| `DRAFT -> SHIPPED` | Từ chối vì bỏ qua xác nhận |
| `SHIPPED -> CANCELLED` | Từ chối và giữ `SHIPPED` |
| `CANCELLED -> CONFIRMED` | Từ chối |
| Đích `null` | Từ chối đầu vào không hợp lệ |
| Thêm hằng enum nhưng không thêm hàng quy tắc | Bước kiểm tra độ phủ báo thiếu |
| Tạo hai đơn và chuyển một đơn | Đơn còn lại giữ trạng thái riêng |

Bài tập mở rộng:

1. Thêm trạng thái `DELIVERED` với quy tắc `SHIPPED -> DELIVERED`; cập nhật bảng và giải thích trạng thái nào còn là kết thúc.
2. Tạo hai `Order`; hủy một đơn và xác nhận đơn kia, kiểm tra không có dữ liệu chung trong hằng enum.
3. Thiết kế hành động `ship()` yêu cầu thông tin giao nhận hợp lệ trước khi chuyển. Xác định rõ lỗi dữ liệu, lỗi quyền và lỗi chuyển trạng thái.
4. Thử một yêu cầu lặp lại sau khi đơn đã được xác nhận. Quyết định nó bị từ chối hay được coi là cùng một thao tác đã hoàn tất; ghi rõ hợp đồng thay vì tự thêm cạnh tự nối.

Mục tiêu là có một tập trạng thái rõ nghĩa, quy tắc tập trung và mọi thay đổi trạng thái đi qua điểm kiểm soát. `enum` và `EnumMap` cung cấp kiểu dữ liệu phù hợp; tính đúng nghiệp vụ đến từ mô hình và cách thực thi quy tắc.
