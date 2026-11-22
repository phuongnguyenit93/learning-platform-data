# Tránh trạng thái dùng chung và tác dụng phụ trong Stream pipeline

Stream API giúp mô tả quá trình xử lý dữ liệu theo các bước như lọc, chuyển đổi và tổng hợp. Một pipeline dễ hiểu và đáng tin cậy khi mỗi bước chủ yếu nhận dữ liệu đầu vào, tính kết quả và trả kết quả tiếp theo. Nếu lambda sửa một biến bên ngoài, thay đổi nguồn dữ liệu hoặc phụ thuộc vào trạng thái có thể thay đổi trong lúc chạy, pipeline trở nên khó dự đoán. Rủi ro tăng rõ rệt khi chuyển từ stream tuần tự sang parallel stream.

Nguyên tắc thực hành là giữ các hàm truyền vào pipeline *stateless* và *non-interfering*, tránh dùng trạng thái mutable bên ngoài để tích lũy kết quả, và để các collector quản lý việc gom dữ liệu. Khi cần tác dụng phụ thật sự như ghi dữ liệu ra hệ thống bên ngoài, hãy đặt nó ở bước terminal phù hợp và kiểm soát thứ tự, lỗi và khả năng thực thi song song.

## 1. Pipeline thực thi như thế nào?

Một stream pipeline thường có ba phần:

1. **Nguồn dữ liệu (source):** collection, array, I/O source hoặc một nguồn tạo phần tử khác.
2. **Các intermediate operation:** `filter`, `map`, `flatMap`, `distinct`, `sorted`... Các bước này tạo pipeline tiếp theo và thường được thực thi lazy.
3. **Terminal operation:** `toList`, `collect`, `reduce`, `count`, `forEach`... Bước này kích hoạt quá trình xử lý và tạo kết quả hoặc tác dụng cuối cùng.

Ví dụ:

```java
List<String> result = names.stream()
        .filter(name -> !name.isBlank())
        .map(String::strip)
        .toList();
```

`filter` quyết định phần tử nào được giữ lại; `map` chuyển từng phần tử thành giá trị mới; `toList` thu kết quả. Hai lambda đầu không cần thay đổi collection nguồn hay một biến bên ngoài. Nhờ vậy, có thể đọc pipeline theo luồng dữ liệu từ trái sang phải.

Vì intermediate operation là lazy, chỉ khai báo pipeline chưa có nghĩa mọi lambda đã được chạy. Terminal operation quyết định việc duyệt và thực thi pipeline; một số terminal operation có thể dừng sớm khi đã đủ kết quả.

## 2. Stateless và non-interfering có ý nghĩa gì?

**Stateless (không phụ thuộc trạng thái thay đổi):** kết quả xử lý một phần tử không phụ thuộc vào trạng thái mutable bên ngoài hoặc vào việc phần tử khác đã được xử lý trước đó. Với cùng đầu vào, lambda nên tạo cùng kết quả theo logic của nó.

Ví dụ stateless:

```java
Predicate<String> nonBlank = value -> !value.isBlank();
Function<String, String> normalized = String::strip;
```

Ví dụ stateful:

```java
Set<String> seen = new HashSet<>();
List<String> unique = names.stream()
        .filter(seen::add)
        .toList();
```

Predicate `seen::add` thay đổi một `Set` bên ngoài và kết quả phụ thuộc vào phần tử đã gặp trước đó. Trong stream tuần tự, đoạn mã có thể tạo ra kết quả như mong muốn trong một số trường hợp, nhưng hành vi phụ thuộc trạng thái và không an toàn khi đổi sang parallel stream. Hãy dùng `distinct()` để diễn đạt mục đích loại phần tử trùng:

```java
List<String> unique = names.stream()
        .distinct()
        .toList();
```

**Non-interfering (không can thiệp nguồn):** lambda không sửa đổi nguồn stream trong lúc pipeline đang xử lý nguồn đó. Không thêm hoặc xóa phần tử khỏi collection nguồn từ bên trong `filter`, `map`, `peek` hay `forEach` của chính pipeline đang duyệt collection ấy.

Không nên nhầm *stateful lambda* với *stateful intermediate operation*. Những operation như `distinct()` hoặc `sorted()` có thể cần giữ trạng thái nội bộ để thực hiện đúng hợp đồng của API. Trạng thái này do implementation của Stream quản lý. Điều cần tránh là lambda tự sửa trạng thái dùng chung bên ngoài hoặc làm thay đổi nguồn dữ liệu.

## 3. Vì sao trạng thái dùng chung gây lỗi?

Xét một biến hoặc collection được khai báo bên ngoài pipeline rồi bị nhiều lambda cùng cập nhật. Với parallel stream, các phần tử có thể được xử lý đồng thời trên nhiều thread. Nếu các thread cùng sửa `ArrayList`, `HashMap`, bộ đếm hoặc một object mutable không có cơ chế đồng bộ phù hợp, chương trình có thể gặp race condition, mất cập nhật, kết quả không ổn định hoặc lỗi cấu trúc dữ liệu.

Ví dụ sau là cách làm không an toàn:

```java
List<String> customers = new ArrayList<>();
orders.parallelStream()
        .forEach(order -> customers.add(order.customer()));
```

`ArrayList` không hỗ trợ nhiều thread cùng thêm phần tử. Ngoài ra, thứ tự thêm có thể khác nhau giữa các lần chạy. Việc thay `ArrayList` bằng một collection thread-safe cũng chưa chắc giải quyết yêu cầu về thứ tự, tính duy nhất hay việc gom kết quả; trước hết hãy chọn cách biểu diễn kết quả phù hợp bằng collector.

Một lỗi khác là cập nhật biến đếm bên ngoài trong `map` hoặc `filter`: lambda không còn là phép biến đổi độc lập, và phép cập nhật có thể bị cạnh tranh giữa các thread. Nếu mục tiêu là đếm phần tử, dùng terminal operation `count()` hoặc một collector phù hợp.

## 4. Dùng collect thay cho biến mutable dùng chung

`collect()` được thiết kế cho việc gom các phần tử thành một kết quả. Với collector chuẩn, framework quản lý các vùng tích lũy trung gian và kết hợp chúng theo hợp đồng của collector, kể cả khi pipeline được thực thi song song và collector không yêu cầu một container dùng chung giữa các thread.

Ví dụ, thay vì cập nhật một `Map` bên ngoài trong `forEach`, dùng `groupingBy` và `summingInt`:

```java
Map<String, Integer> totals = orders.stream().collect(
        Collectors.groupingBy(
                Order::customer,
                LinkedHashMap::new,
                Collectors.summingInt(Order::amount)
        )
);
```

Collector tạo map kết quả, nhóm các đơn hàng theo khách hàng và cộng số tiền trong mỗi nhóm. Không cần tự quản lý `containsKey`, `put` hoặc trạng thái map ở bên ngoài lambda.

Nếu cần một collection kết quả có thể sửa, chỉ rõ implementation bằng `toCollection`:

```java
List<Order> editable = orders.stream()
        .filter(order -> order.amount() >= 100)
        .collect(Collectors.toCollection(ArrayList::new));
```

Điều này thể hiện rõ rằng kết quả cần là một `ArrayList` mutable. `Stream.toList()` trả về list không sửa được; `Collectors.toList()` không cam kết cụ thể implementation hoặc khả năng sửa. Khi khả năng mutable là một yêu cầu, `Collectors.toCollection(ArrayList::new)` rõ ràng hơn.

## 5. Chọn reduce hay collect

Dùng `reduce()` khi cần kết hợp các giá trị thành một kết quả bằng phép kết hợp có tính kết hợp (associative) và có identity phù hợp. Ví dụ tính tổng số tiền:

```java
int total = orders.parallelStream()
        .mapToInt(Order::amount)
        .sum();
```

Phép cộng số nguyên có identity là `0`, nên tổng có thể được tính từ các phần dữ liệu rồi kết hợp lại. `sum()`, `min()`, `max()` hoặc một `reduce` đúng hợp đồng phù hợp cho dạng tổng hợp giá trị này.

Không dùng `reduce()` với một accumulator mutable được chia sẻ hoặc identity mutable. Ví dụ, dùng cùng một `StringBuilder` làm identity rồi sửa nó trong accumulator có thể khiến các nhánh xử lý song song dùng chung object hoặc kết hợp kết quả sai.

Khi cần tích lũy vào một container mutable như `ArrayList`, `StringBuilder` hoặc `Map`, hãy dùng `collect()` với supplier, accumulator và combiner phù hợp, hoặc collector chuẩn. `collect()` được thiết kế riêng cho mutable reduction; `reduce()` được thiết kế cho phép kết hợp giá trị.

## 6. Tác dụng phụ ở terminal operation

Không phải mọi tác dụng phụ đều bị cấm. Chương trình có thể cần gửi thông điệp, ghi log, ghi file hoặc cập nhật hệ thống bên ngoài. Điểm quan trọng là hiểu rằng tác dụng phụ không nên được giấu trong một intermediate operation dùng để biến đổi dữ liệu.

`forEach()` là terminal operation dành cho việc thực hiện hành động trên các phần tử. Với parallel stream, hành động có thể chạy đồng thời và không bảo đảm encounter order. Chỉ dùng nó khi hành động độc lập giữa các phần tử hoặc đích nhận có cơ chế đồng bộ phù hợp.

`forEachOrdered()` giữ encounter order đối với stream có thứ tự, nhưng có thể làm giảm khả năng song song hóa. Dùng khi thứ tự tác động bên ngoài là một phần yêu cầu nghiệp vụ; không dùng chỉ để che một thiết kế đang phụ thuộc trạng thái dùng chung.

Trước khi thực hiện I/O hoặc gọi dịch vụ bên ngoài trong terminal action, hãy xem xét khả năng lỗi một phần, retry, tính idempotent và giới hạn tốc độ. Parallel stream không tự tạo ra giao dịch nguyên tử cho các tác động bên ngoài.

## 7. Không dùng peek cho logic nghiệp vụ

`peek()` chủ yếu hỗ trợ quan sát và gỡ lỗi luồng phần tử:

```java
List<String> normalized = names.stream()
        .peek(name -> System.out.println("Before: " + name))
        .map(String::strip)
        .toList();
```

Không dùng `peek()` để cập nhật cơ sở dữ liệu, tăng bộ đếm nghiệp vụ hoặc ghi trạng thái bắt buộc. Pipeline lazy và implementation có thể tối ưu việc xử lý; trong một số trường hợp có thể xác định kết quả terminal operation mà không cần duyệt mọi phần tử. Ví dụ `count()` trên nguồn có kích thước đã biết có thể bỏ qua một số intermediate operation không ảnh hưởng kết quả, nên không được dựa vào `peek()` để bảo đảm một hành động xảy ra.

Nếu hành động là yêu cầu bắt buộc, hãy đặt nó ở terminal operation hoặc trong một bước xử lý có hợp đồng thực thi rõ ràng.

## 8. Ví dụ hoàn chỉnh: pipeline không dùng trạng thái chia sẻ

Ví dụ dưới đây lọc đơn hàng, chuyển đổi thành nhãn, nhóm doanh thu theo khách hàng và tính tổng bằng parallel stream. Các phép biến đổi không sửa nguồn; việc gom nhóm do collector quản lý.

Tạo tệp `StreamPipelineSafety.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class StreamPipelineSafety {
    record Order(String customer, int amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("An", 120),
                new Order("Binh", 80),
                new Order("An", 50),
                new Order("Chi", 200)
        );

        List<String> qualified = orders.stream()
                .filter(order -> order.amount() >= 100)
                .map(order -> order.customer() + ":" + order.amount())
                .toList();
        System.out.println("Qualified: " + qualified);

        Map<String, Integer> totals = orders.stream().collect(
                Collectors.groupingBy(
                        Order::customer,
                        LinkedHashMap::new,
                        Collectors.summingInt(Order::amount)
                )
        );
        System.out.println("Totals: " + totals);

        int total = orders.parallelStream()
                .mapToInt(Order::amount)
                .sum();
        System.out.println("Total: " + total);

        List<Order> editable = orders.stream()
                .filter(order -> order.amount() >= 100)
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add(new Order("An", 30));
        System.out.println("Editable result size: " + editable.size());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 StreamPipelineSafety.java
java StreamPipelineSafety
```

Kết quả stdout:

```text
Qualified: [An:120, Chi:200]
Totals: {An=170, Binh=80, Chi=200}
Total: 450
Editable result size: 3
```

`LinkedHashMap` trong ví dụ giữ thứ tự nhóm theo lần xuất hiện đầu tiên trong stream tuần tự, giúp stdout ổn định. Phép tính tổng dùng parallel stream nhưng không phụ thuộc thứ tự vì phép cộng có tính kết hợp. Danh sách mutable được tạo riêng bằng collector; collection nguồn vẫn nguyên vẹn.

## 9. Checklist khi viết pipeline

1. Giữ `filter`, `map` và các behavioral parameter khác độc lập với trạng thái mutable bên ngoài.
2. Không sửa collection nguồn trong khi pipeline đang duyệt collection đó.
3. Không dùng một `ArrayList`, `HashMap` hoặc bộ đếm dùng chung để gom kết quả từ `parallelStream().forEach(...)`.
4. Dùng `distinct`, `groupingBy`, `mapping`, `summingInt`, `count` hoặc collector phù hợp thay cho tự quản lý trạng thái.
5. Dùng `reduce` cho phép kết hợp giá trị có identity và tính kết hợp; dùng `collect` cho mutable reduction.
6. Chỉ dùng `forEach` khi thực sự cần hành động ở terminal stage; xem xét thứ tự và tính an toàn khi chạy song song.
7. Dùng `peek` để gỡ lỗi, không để thực hiện logic nghiệp vụ bắt buộc.
8. Chỉ chuyển sang parallel stream khi công việc phù hợp, phép xử lý an toàn và chi phí song song có lợi; parallel không tự làm pipeline nhanh hơn.

Pipeline tốt mô tả dữ liệu đi qua các phép biến đổi rõ ràng. Khi tránh trạng thái dùng chung và tác dụng phụ trong intermediate operation, chương trình dễ kiểm tra hơn, ít phụ thuộc thứ tự thực thi và có thể chuyển sang parallel stream an toàn hơn khi các phép xử lý cùng đáp ứng yêu cầu của Stream API.