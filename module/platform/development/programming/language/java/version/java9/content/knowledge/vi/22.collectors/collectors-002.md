# Phân biệt lọc trước groupingBy với lọc bên trong nhóm

Khi dùng Stream API để nhóm dữ liệu, vị trí đặt điều kiện lọc có thể làm thay đổi cấu trúc kết quả. Lọc stream trước khi gọi `groupingBy` có thể loại bỏ hoàn toàn một nhóm nếu mọi phần tử của nhóm đó đều không đạt điều kiện. Dùng collector `filtering` bên trong `groupingBy` thì key của nhóm vẫn được tạo từ dữ liệu nguồn, còn collector phía dưới chỉ nhận những phần tử đạt điều kiện.

`Collectors.filtering` được bổ sung từ Java 9. Nó hữu ích khi muốn giữ lại các nhóm đã xuất hiện trong nguồn, kể cả khi một nhóm không có phần tử nào vượt qua điều kiện lọc.

## 1. Hai vị trí đặt điều kiện lọc

Giả sử có danh sách đơn hàng. Mỗi đơn hàng thuộc một phòng ban và có trạng thái được duyệt hoặc chưa được duyệt. Yêu cầu là nhóm các sản phẩm theo phòng ban, chỉ lấy đơn đã được duyệt.

**Lọc trước khi nhóm**

```java
orders.stream()
        .filter(Order::approved)
        .collect(groupingBy(Order::department));
```

`filter` chạy trên toàn bộ stream trước. Chỉ đơn hàng đã được duyệt mới đi tới `groupingBy`. Nếu một phòng ban không có đơn nào được duyệt, không có phần tử nào của phòng ban đó đến bước nhóm, vì vậy key của phòng ban không xuất hiện trong Map kết quả.

**Lọc bên trong từng nhóm**

```java
orders.stream()
        .collect(groupingBy(
                Order::department,
                filtering(Order::approved, toList())
        ));
```

Ở đây `groupingBy` phân loại từng đơn hàng theo phòng ban trước. Collector `filtering` nằm ở vị trí downstream nên chỉ quyết định đơn hàng nào được đưa vào collector `toList` của từng nhóm. Nếu phòng ban đã có đơn trong nguồn nhưng không có đơn nào được duyệt, Map vẫn có key của phòng ban đó và giá trị là danh sách rỗng.

## 2. Ví dụ đầy đủ chạy được

Ví dụ dùng `record` để biểu diễn đơn hàng. `record` có từ Java 16; `Collectors.filtering` có từ Java 9. Có thể biên dịch ví dụ bằng JDK 17 trở lên.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static java.util.stream.Collectors.counting;
import static java.util.stream.Collectors.filtering;
import static java.util.stream.Collectors.groupingBy;
import static java.util.stream.Collectors.mapping;
import static java.util.stream.Collectors.toList;

public class Main {
    record Order(String department, String item, boolean approved) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("North", "Keyboard", true),
                new Order("North", "Mouse", false),
                new Order("South", "Monitor", false),
                new Order("East", "Laptop", true),
                new Order("East", "Dock", false)
        );

        Map<String, List<String>> filteredBeforeGrouping = orders.stream()
                .filter(Order::approved)
                .collect(groupingBy(
                        Order::department,
                        LinkedHashMap::new,
                        mapping(Order::item, toList())
                ));

        Map<String, List<String>> filteredInsideGroup = orders.stream()
                .collect(groupingBy(
                        Order::department,
                        LinkedHashMap::new,
                        filtering(
                                Order::approved,
                                mapping(Order::item, toList())
                        )
                ));

        Map<String, Long> approvedCountByDepartment = orders.stream()
                .collect(groupingBy(
                        Order::department,
                        LinkedHashMap::new,
                        filtering(Order::approved, counting())
                ));

        System.out.println("Filter trước groupingBy: " + filteredBeforeGrouping);
        System.out.println("filtering bên trong nhóm: " + filteredInsideGroup);
        System.out.println("Số đơn được duyệt theo nhóm: " + approvedCountByDepartment);
        System.out.println("Có key South ở cách 1: "
                + filteredBeforeGrouping.containsKey("South"));
        System.out.println("Có key South ở cách 2: "
                + filteredInsideGroup.containsKey("South"));
        System.out.println("Nhóm South cách 2 rỗng: "
                + filteredInsideGroup.get("South").isEmpty());
    }
}
```

Lưu thành `Main.java` rồi chạy:

```bash
javac --release 17 Main.java
java Main
```

Kết quả stdout:

```text
Filter trước groupingBy: {North=[Keyboard], East=[Laptop]}
filtering bên trong nhóm: {North=[Keyboard], South=[], East=[Laptop]}
Số đơn được duyệt theo nhóm: {North=1, South=0, East=1}
Có key South ở cách 1: false
Có key South ở cách 2: true
Nhóm South cách 2 rỗng: true
```

Trong dữ liệu nguồn:

- North có một đơn được duyệt (Keyboard) và một đơn chưa được duyệt (Mouse).
- South chỉ có một đơn chưa được duyệt (Monitor).
- East có một đơn được duyệt (Laptop) và một đơn chưa được duyệt (Dock).

Kết quả cho thấy:

1. Lọc trước khi nhóm loại đơn hàng South trước khi `groupingBy` nhận dữ liệu. Vì vậy key `South` không được tạo.
2. Lọc bên trong nhóm vẫn để `groupingBy` nhận đơn hàng South và tạo nhóm tương ứng. Collector `filtering` loại Monitor khỏi downstream `toList`, nên giá trị của nhóm là `[]`.
3. Khi downstream là `counting()`, nhóm South vẫn có mặt với giá trị `0`. Điều này hữu ích khi lập báo cáo số lượng theo từng nhóm.

Ví dụ truyền `LinkedHashMap::new` làm map factory để thứ tự key trong output ổn định theo lần đầu xuất hiện trong dữ liệu. Nếu dùng overload đơn giản `groupingBy(classifier, downstream)`, không nên phụ thuộc vào thứ tự duyệt key của Map kết quả.

## 3. Hiểu đúng vai trò của downstream filtering

`groupingBy` nhận một classifier để xác định key cho mỗi phần tử và một downstream collector để tích lũy các phần tử trong từng nhóm.

Dạng tổng quát:

```java
groupingBy(classifier, downstream)
```

`filtering` tạo một downstream collector có nhiệm vụ kiểm tra predicate trước khi chuyển phần tử cho collector tiếp theo:

```java
filtering(predicate, downstream)
```

Khi kết hợp:

```java
groupingBy(classifier, filtering(predicate, downstream))
```

quá trình xử lý về mặt logic là:

1. Nhận một phần tử từ stream nguồn.
2. Chạy classifier để xác định nhóm của phần tử.
3. Chuyển phần tử vào downstream collector của nhóm tương ứng.
4. `filtering` kiểm tra predicate.
5. Nếu predicate đúng, chuyển phần tử đến collector tiếp theo; nếu sai, không tích lũy phần tử đó.

Vì collector của nhóm được tạo từ việc nhóm các phần tử nguồn, nhóm vẫn có thể tồn tại dù `filtering` không chuyển phần tử nào đến collector cuối.

Điểm này khác với `stream.filter` ở đầu pipeline: phần tử bị loại tại đó không còn đến `groupingBy` và không thể tạo key cho nhóm.

## 4. So sánh kết quả trong các tình huống

| Tình huống của một nhóm trong nguồn | Lọc trước `groupingBy` | `filtering` downstream |
|---|---|---|
| Có phần tử đạt điều kiện | Nhóm xuất hiện với các phần tử đạt điều kiện | Nhóm xuất hiện với các phần tử đạt điều kiện |
| Có phần tử nguồn nhưng không phần tử nào đạt điều kiện | Nhóm không xuất hiện | Nhóm xuất hiện; giá trị phụ thuộc downstream, ví dụ list rỗng hoặc count bằng 0 |
| Không có phần tử nào thuộc key đó trong nguồn | Nhóm không xuất hiện | Nhóm cũng không xuất hiện |
| Tất cả phần tử của nguồn đều bị loại | Map có thể rỗng | Map cũng rỗng nếu nguồn không tạo ra bất kỳ nhóm nào |

Một điểm cần phân biệt: `filtering` downstream chỉ giữ các key đã được classifier tạo ra từ ít nhất một phần tử nguồn. Nó không tự tạo những nhóm chưa từng xuất hiện trong nguồn.

Ví dụ, nếu báo cáo phải luôn có đủ các phòng ban North, South, East, West kể cả khi nguồn không có đơn hàng của West, cả hai cách trên đều chưa đủ. Cần có danh sách nhóm chuẩn hoặc nguồn dữ liệu danh mục phòng ban, sau đó khởi tạo kết quả cho các nhóm đó và bổ sung kết quả tổng hợp tương ứng.

## 5. Có thể kết hợp filtering với nhiều downstream collector

`filtering` không bị giới hạn ở `toList`. Nó có thể bọc một collector downstream khác để tính toán trên những phần tử đạt điều kiện trong từng nhóm.

**Đếm phần tử đạt điều kiện**

```java
Map<String, Long> approvedCounts = orders.stream()
        .collect(groupingBy(
                Order::department,
                filtering(Order::approved, counting())
        ));
```

Mỗi nhóm có số đơn được duyệt. Nhóm đã xuất hiện trong nguồn nhưng không có đơn được duyệt sẽ có giá trị `0L`.

**Chuyển đổi dữ liệu rồi thu thập thành danh sách**

```java
Map<String, List<String>> approvedItems = orders.stream()
        .collect(groupingBy(
                Order::department,
                filtering(
                        Order::approved,
                        mapping(Order::item, toList())
                )
        ));
```

`filtering` quyết định đơn hàng nào được giữ. `mapping` chuyển đơn hàng thành tên sản phẩm. `toList` thu thập các tên sản phẩm vào danh sách của nhóm.

**Tính tổng theo nhóm**

Nếu `Order` có thêm thuộc tính số tiền `amount`, có thể kết hợp `filtering` với `summingInt`:

```java
Map<String, Integer> approvedTotals = orders.stream()
        .collect(groupingBy(
                Order::department,
                filtering(
                        Order::approved,
                        summingInt(Order::amount)
                )
        ));
```

Đây là một pipeline fragment dùng cùng nguồn `orders` ở ví dụ trước và giả định record `Order` có accessor `amount()`. Nhóm không có đơn được duyệt vẫn có thể có key và tổng bằng `0`. Tương tự, có thể dùng `averagingInt`, `maxBy`, `minBy` hoặc một collector tùy chỉnh phù hợp với kiểu kết quả cần tính.

Khi lồng collector, đọc từ ngoài vào trong: `groupingBy` quyết định nhóm; `filtering` quyết định phần tử được chuyển tiếp; collector trong cùng thực hiện phép tổng hợp cuối.

## 6. Chọn cách đặt filter theo yêu cầu nghiệp vụ

Dùng lọc trước `groupingBy` khi chỉ muốn báo cáo các nhóm có ít nhất một phần tử vượt qua điều kiện. Ví dụ: danh sách các phòng ban có đơn hàng đã duyệt, hoặc chỉ thống kê những khách hàng có giao dịch hợp lệ.

Dùng `filtering` bên trong `groupingBy` khi muốn giữ các nhóm có dữ liệu nguồn nhưng có thể không có phần tử đạt điều kiện. Ví dụ: báo cáo mọi phòng ban đã phát sinh đơn hàng, kèm số đơn đã duyệt; phòng ban chưa có đơn được duyệt vẫn phải hiển thị với số lượng 0.

Có thể chọn theo câu hỏi:

- Kết quả có được phép bỏ nhóm nếu nhóm không có phần tử đạt điều kiện không? Nếu có, lọc trước có thể phù hợp.
- Có cần giữ key nhóm đã xuất hiện trong nguồn và biểu diễn nhóm không có kết quả bằng list rỗng hoặc số 0 không? Dùng `filtering` downstream.
- Có cần hiển thị cả những nhóm chưa từng xuất hiện trong nguồn không? Cần bổ sung danh mục nhóm hoặc nguồn chuẩn; `filtering` không giải quyết việc này.

## 7. Lỗi thường gặp

- **Cho rằng hai cách chỉ khác vị trí viết code:** chúng có thể tạo ra Map với tập key khác nhau, ảnh hưởng trực tiếp đến báo cáo và xử lý tiếp theo.
- **Dùng filter trước rồi mong nhóm rỗng vẫn tồn tại:** các phần tử bị loại không đến `groupingBy`. Dùng `filtering` downstream nếu cần giữ key đã xuất hiện.
- **Cho rằng downstream filtering tạo mọi nhóm có thể có:** nó chỉ giữ nhóm có ít nhất một phần tử nguồn được phân loại vào key đó.
- **Đặt filtering ở ngoài groupingBy:** `filtering` là collector, được dùng trong `collect`; thao tác lọc stream ở đầu pipeline là `filter`.
- **Nhầm list rỗng với key không tồn tại:** kiểm tra `containsKey` để phân biệt nhóm không có trong Map và nhóm có trong Map nhưng không có phần tử phù hợp.
- **Quên chọn downstream phù hợp:** `filtering(predicate, toList())` cho danh sách rỗng khi không có phần tử đạt điều kiện; `filtering(predicate, counting())` cho số 0.
- **Dựa vào thứ tự key của Map mặc định:** nếu output cần thứ tự ổn định, chỉ định map factory như `LinkedHashMap::new` hoặc sắp xếp rõ ràng khi trình bày kết quả.

## 8. Checklist khi thiết kế grouping pipeline

- Điều kiện áp dụng cho toàn stream trước khi phân nhóm hay áp dụng riêng trong từng nhóm?
- Nhóm không có phần tử phù hợp có cần tiếp tục xuất hiện không?
- Nhóm chưa từng có phần tử trong nguồn có cần xuất hiện không?
- Downstream cần trả danh sách, số lượng, tổng, trung bình hay một cấu trúc khác?
- Có yêu cầu về thứ tự key hoặc thứ tự phần tử trong kết quả không?
- Predicate và classifier có tránh side effect để pipeline hoạt động ổn định không?

`filter` và `Collectors.filtering` đều lọc phần tử theo predicate, nhưng vị trí của chúng quyết định việc nhóm được tạo ra như thế nào. Lọc trước `groupingBy` chỉ nhóm dữ liệu còn lại sau lọc; dùng `filtering` downstream giữ những nhóm đã xuất hiện trong nguồn ngay cả khi không có phần tử nào vượt qua điều kiện. Chọn đúng cách giúp kết quả tổng hợp phản ánh chính xác yêu cầu nghiệp vụ.
