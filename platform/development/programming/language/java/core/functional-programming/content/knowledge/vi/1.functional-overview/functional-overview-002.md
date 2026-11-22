# Từ mô tả từng bước tới mô tả phép biến đổi dữ liệu trong Java

## 1. Tư duy từng bước và tư duy biến đổi

Hãy xét yêu cầu: từ danh sách đơn hàng, chỉ lấy sản phẩm của **đơn đã thanh toán và số lượng dương**; chuẩn hóa tên bằng cách bỏ khoảng trắng hai đầu, đổi thành chữ hoa; loại tên trùng và sắp xếp để hiển thị.

Có hai cách diễn đạt:

- **Imperative (mô tả từng bước):** tạo danh sách kết quả, duyệt từng đơn hàng, kiểm tra điều kiện, lấy tên, thêm nếu chưa tồn tại, cuối cùng sắp xếp. Người đọc theo dõi vòng lặp, nhánh điều kiện và trạng thái danh sách biến đổi qua thời gian.
- **Declarative (mô tả phép biến đổi):** từ các đơn hàng, **lọc** đơn hợp lệ → **chiếu** sang tên sản phẩm → **chuẩn hóa** → **loại trùng** → **sắp xếp** → **thu thập kết quả**. Người đọc nhìn thấy quy tắc chuyển dữ liệu đầu vào thành dữ liệu đầu ra.

Cách diễn đạt thứ hai gần với các khái niệm của lập trình hàm; Java cung cấp lambda, method reference, functional interface và Stream API để thực hiện. Tuy nhiên, Java là ngôn ngữ đa mô hình: một vòng lặp rõ ràng đôi khi vẫn phù hợp hơn Stream.

Điểm cần thay đổi trước hết là cách đặt câu hỏi: **“Dữ liệu cần trở thành gì qua mỗi bước?”**, sau đó mới đến “Dùng cú pháp Java nào?”. Declarative không có nghĩa là bỏ qua thuật toán hay hiệu năng; nó là cách đặt quy tắc nghiệp vụ ở vị trí dễ thấy.

## 2. Phân tích đầu vào, đầu ra và hợp đồng dữ liệu

Trước khi viết pipeline, xác định:

1. **Nguồn:** danh sách Order; có null không, dữ liệu lấy từ bộ nhớ hay hệ thống ngoài?
2. **Điều kiện lựa chọn:** đơn phải thanh toán và số lượng lớn hơn 0.
3. **Biến đổi:** từ Order thành String rồi chuẩn hóa nội dung String.
4. **Ràng buộc kết quả:** tên không trùng, sắp xếp theo quy tắc đã chọn; có cần danh sách cho phép sửa không?
5. **Tác động phụ:** bài toán chỉ tính toán kết quả hay còn cập nhật cơ sở dữ liệu, ghi tệp, gọi dịch vụ?
6. **Lỗi dữ liệu:** tên null, khoảng trắng, dữ liệu trùng, số tiền âm, giá trị thiếu được xử lý theo quy tắc nào?

Tư duy gần với hàm **f(input) → output**: đầu vào và quy tắc xác định kết quả, không phụ thuộc trạng thái ẩn. Ta thường ưu tiên hàm biến đổi ít tác động phụ để dễ đọc, kiểm thử và tái sử dụng. **Lambda không tự động là hàm thuần**; lambda vẫn có thể thay đổi trạng thái đối tượng bên ngoài.

Một pipeline minh họa:

~~~text
List<Order>
    ↓ filter: đơn đã trả tiền
    ↓ filter: số lượng dương
    ↓ map: Order → tên sản phẩm
    ↓ map: chuẩn hóa tên
    ↓ distinct: tên không trùng
    ↓ sorted: thứ tự xác định
List<String>
~~~

Mỗi bước nên có một mục đích nghiệp vụ rõ. Trình tự cũng có ý nghĩa: chuẩn hóa **trước** khi loại trùng sẽ gộp các tên chỉ khác khoảng trắng hoặc chữ hoa/thường.

## 3. Ví dụ đầy đủ: hai cách giải cùng một bài toán

Tạo tệp **TransformData.java** (JDK 17 trở lên):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

record Order(String customer, String product,
             int quantity, int unitPrice, boolean paid) {}

public class TransformData {
    static List<String> imperative(List<Order> orders) {
        List<String> names = new ArrayList<>();

        for (Order order : orders) {
            if (!order.paid() || order.quantity() <= 0) {
                continue;
            }

            String name = order.product()
                    .strip()
                    .toUpperCase(Locale.ROOT);

            if (!names.contains(name)) {
                names.add(name);
            }
        }

        Collections.sort(names);
        return names;
    }

    static List<String> declarative(List<Order> orders) {
        return orders.stream()
                .filter(Order::paid)
                .filter(order -> order.quantity() > 0)
                .map(Order::product)
                .map(String::strip)
                .map(name -> name.toUpperCase(Locale.ROOT))
                .distinct()
                .sorted()
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("Lan", " Sách ", 2, 120, true),
                new Order("Minh", "Bút", 3, 15, true),
                new Order("Lan", "SÁCH", 1, 120, true),
                new Order("An", "Vở", 1, 30, false),
                new Order("Minh", "Bút", 0, 15, true),
                new Order("An", " Tẩy ", 1, 5, true)
        );

        System.out.println(imperative(orders));
        System.out.println(declarative(orders));
    }
}
~~~

Biên dịch và chạy trong terminal có JDK 17+:

~~~bash
javac -encoding UTF-8 TransformData.java
java TransformData
~~~

Stdout:

~~~text
[BÚT, SÁCH, TẨY]
[BÚT, SÁCH, TẨY]
~~~

Hai cách cùng loại đơn chưa thanh toán, đơn số lượng bằng 0, chuẩn hóa cùng quy tắc, loại trùng và sắp xếp. Điểm khác biệt nằm ở việc **bản imperative tự quản lý danh sách trung gian**, còn bản Stream **nối các thao tác phản ánh mục đích xử lý**.

Bảng đối chiếu các phép biến đổi:

| Thao tác Stream | Công việc | Kiểu phần tử sau thao tác |
| --- | --- | --- |
| **orders.stream()** | Lấy nguồn dữ liệu | Order |
| **filter(Order::paid)** | Giữ đơn đã thanh toán | Order |
| **filter(o -> o.quantity() > 0)** | Giữ đơn có số lượng dương | Order |
| **map(Order::product)** | Lấy tên từ Order | String |
| **map(String::strip)** | Loại khoảng trắng ở rìa | String |
| **map(name -> name.toUpperCase(Locale.ROOT))** | Chuẩn hóa chữ hoa | String |
| **distinct()** | Loại tên trùng | String |
| **sorted()** | Sắp xếp theo thứ tự tự nhiên | String |
| **toList()** | Tạo danh sách kết quả | List<String> |

**Order::paid** là method reference, ở đây tương đương **order -> order.paid()**. Tương tự, **String::strip** biểu đạt phép gọi **name -> name.strip()** trên từng chuỗi.

Lưu ý về phạm vi dữ liệu ví dụ: chương trình giả định **product != null**. Nếu nguồn thực tế có null, cần chính sách rõ ràng và kiểm tra trước khi gọi **strip()**. **Locale.ROOT** làm phép chuyển chữ hoa độc lập với locale mặc định; **sorted()** mặc định so sánh String theo thứ tự tự nhiên Unicode, không có nghĩa là sắp xếp theo bảng chữ cái tiếng Việt. Để sắp xếp theo quy tắc ngôn ngữ cụ thể, hãy chọn Comparator/Collator phù hợp với yêu cầu.

## 4. Pipeline Stream thực thi như thế nào?

**Source** cung cấp phần tử (chẳng hạn **List.stream()**, **Stream.of(...)**). Stream không phải một collection mới có thể duyệt lại tùy ý.

**Intermediate operations** như **filter**, **map**, **distinct**, **sorted** chủ yếu trả về Stream mô tả bước xử lý tiếp theo. Các bước này **lười thực thi**: khi chỉ tạo pipeline, Java thường chưa duyệt nguồn để tính đầu ra.

**Terminal operations** như **toList**, **collect**, **count**, **reduce**, **findFirst**, **anyMatch**, **forEach** kích hoạt quá trình đánh giá pipeline. Một Stream đã tiêu thụ không dùng lại để chạy pipeline lần hai; hãy gọi **stream()** lại trên nguồn khi cần.

Phân biệt các nhóm thao tác:

- **filter** giữ hoặc bỏ phần tử dựa trên **Predicate<T>**; kiểu phần tử không đổi.
- **map** chuyển phần tử qua **Function<T,R>**; kiểu đầu ra có thể khác kiểu đầu vào.
- **distinct** dùng quy tắc bằng nhau của phần tử (liên quan **equals/hashCode**) để loại trùng; là thao tác có trạng thái.
- **sorted** sắp xếp theo natural order hoặc Comparator; cần xử lý nhiều phần tử nên có chi phí khác với **map** thuần túy.
- **findFirst**, **anyMatch** có thể dừng sớm khi đã đủ kết quả; không được giả định mọi terminal operation luôn đi hết nguồn.
- **Stream.toList()** (Java 16+) trả danh sách không cho phép thêm/xóa/sửa phần tử bằng các thao tác cập nhật List. Nếu cần danh sách mutable, chọn **collect(Collectors.toCollection(ArrayList::new))**.

**Stream không mặc nhiên nhanh hơn vòng lặp.** Đánh giá chi phí duyệt, bộ nhớ trung gian, boxing, sorting và lượng dữ liệu bằng phép đo phù hợp. Mục tiêu đầu tiên ở đây là diễn đạt đúng và dễ kiểm tra logic biến đổi.

## 5. map hay flatMap?

**map** biến mỗi phần tử thành một giá trị mới. Nếu phần tử mới là List, kết quả ở mức Stream sẽ là Stream<List<T>>. **flatMap** được dùng khi mỗi phần tử tạo một Stream con và ta muốn ghép các Stream con thành một luồng phẳng.

Ví dụ đoạn mã sau đặt trong một phương thức có import **java.util.List**:

~~~java
List<List<String>> groups = List.of(
        List.of("java", "stream"),
        List.of("lambda")
);

List<String> tags = groups.stream()
        .flatMap(List::stream)
        .toList();

System.out.println(tags); // [java, stream, lambda]
~~~

Nếu thay bằng **map(List::stream)**, mỗi phần tử kết quả lại là một Stream. Hãy dùng **flatMap** khi việc làm phẳng đúng với đầu ra nghiệp vụ, chẳng hạn danh sách đơn hàng → các dòng hàng của tất cả đơn.

## 6. Biến đổi để tổng hợp dữ liệu

Không phải tất cả bài toán đều kết thúc bằng List. Ví dụ: “Chỉ xét giao dịch đã thanh toán, tính **tổng tiền theo khách hàng**”. Cách mô tả theo phép biến đổi là **lọc giao dịch → nhóm theo khách hàng → tính tổng từng nhóm**.

Tạo tệp **SummarizePaidSales.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Sale(String buyer, int amount, boolean paid) {}

public class SummarizePaidSales {
    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("Lan", 120, true),
                new Sale("Minh", 50, false),
                new Sale("Lan", 80, true),
                new Sale("An", 40, true),
                new Sale("An", 20, false)
        );

        Map<String, Integer> totalByBuyer = sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::buyer,
                        TreeMap::new,
                        Collectors.summingInt(Sale::amount)
                ));

        System.out.println(totalByBuyer);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SummarizePaidSales.java
java SummarizePaidSales
~~~

Stdout:

~~~text
{An=40, Lan=200}
~~~

**groupingBy** dùng **Sale::buyer** làm khóa nhóm, còn **summingInt** cộng trường amount trong mỗi nhóm. **TreeMap::new** cho thứ tự khóa xác định. Không nên dựa vào thứ tự hiển thị khi dùng Map không có hợp đồng thứ tự như HashMap.

Trong dự án thực tế, hãy định nghĩa rõ đơn vị tiền, cách làm tròn và khả năng tràn số; **int** chỉ là dữ liệu số đơn giản cho ví dụ. Có thể dùng giá trị nguyên theo đơn vị nhỏ nhất hoặc **BigDecimal** theo đặc tả miền nghiệp vụ.

Bài học về cách nghĩ: thay vì bắt đầu bằng thao tác **khởi tạo Map, kiểm tra khóa, cộng vào giá trị cũ**, hãy xác định trước **phạm vi giao dịch, khóa phân nhóm và phép tổng hợp**. Các Collector chính là cách triển khai ba quy tắc đó.

## 7. Quy trình chuyển mã từng bước sang mã biến đổi

1. **Ghi hợp đồng đầu vào/đầu ra:** loại dữ liệu, số lượng, null, thứ tự, việc loại trùng, có cho phép thay đổi kết quả không.
2. **Tách hành vi nghiệp vụ khỏi chi tiết điều khiển:** một điều kiện thường thành **filter**; một phép chuyển phần tử thành **map**; việc nhóm/tổng thành **collect** hoặc collector tương ứng.
3. **Sắp xếp các phép biến đổi đúng nghĩa:** chuẩn hóa trước loại trùng; giữ lọc trước xử lý tốn chi phí nếu không làm thay đổi kết quả; không hoán đổi bước chỉ vì muốn viết gọn.
4. **Tách side effect:** tính kết quả riêng trước khi ghi tệp, lưu database hoặc gọi dịch vụ; những bước tạo side effect có thể cần vòng lặp và xử lý lỗi rõ ràng.
5. **Đặt tên quy tắc phức tạp:** nếu lambda khó đọc, dùng phương thức như **isEligibleOrder** hay **normalizeProductName**.
6. **So sánh hành vi bản cũ và bản mới:** kiểm thử đầu vào rỗng, chỉ phần tử bị loại, tên trùng khác cách viết, null, thứ tự, lỗi và bất biến trạng thái.
7. **Đo trước khi tối ưu:** một dòng Stream ngắn hơn không bảo đảm hiệu quả CPU/bộ nhớ hơn.

Khi viết pipeline dài, hãy đọc từ trái sang phải và thử diễn đạt mỗi bước bằng một câu tiếng Việt. Nếu hai hoặc ba bước có phụ thuộc nghiệp vụ khó giải thích, cân nhắc tách thành phương thức có tên rõ nghĩa.

## 8. Lỗi thường gặp

| Lỗi | Vì sao có vấn đề | Hướng xử lý |
| --- | --- | --- |
| Dùng **map** để thêm phần tử vào List mutable bên ngoài | Có tác động phụ, mã khó suy luận và nguy hiểm khi song song hóa | Dùng map tạo giá trị rồi thu bằng terminal operation |
| Bỏ qua các phần tử null | Có thể phát sinh NullPointerException ở method reference/call | Xác định chính sách và lọc bằng **Objects::nonNull** ở nơi phù hợp |
| Đưa **distinct** trước chuẩn hóa | Các chuỗi khác hình thức có thể còn trùng sau chuẩn hóa | Giữ thứ tự phản ánh nghiệp vụ |
| Dùng **peek** để cập nhật trạng thái bắt buộc | Side effect trong peek không phải cơ chế đáng tin để thực hiện nghiệp vụ | Chỉ dùng peek khi quan sát/debug phù hợp; dùng collector hoặc vòng lặp cho việc cập nhật cần thiết |
| Dùng lại Stream đã kết thúc | Có thể nhận **IllegalStateException** | Tạo Stream mới |
| Giả sử **toList()** luôn sửa được | Thêm/xóa gây **UnsupportedOperationException** | Dùng mutable collector khi cần |
| Dựa vào thứ tự mặc định của **groupingBy** | Map kết quả có thể không bảo đảm thứ tự muốn hiển thị | Cung cấp Map supplier có quy tắc thứ tự |
| Mặc định **parallelStream()** nhanh và an toàn | Overhead và cập nhật trạng thái chung có thể gây lỗi/giảm hiệu năng | Ưu tiên tuần tự; chỉ thử parallel sau khi đo và xét thread safety |

Một lambda có thể bắt tham chiếu tới đối tượng mutable. Mã như **parallelStream().forEach(item -> sharedList.add(item))** với ArrayList chia sẻ là thiết kế không an toàn; không được suy ra thread safety từ cú pháp functional.

Cũng cần phân biệt **thứ tự dữ liệu** với **thứ tự áp dụng thao tác**. Pipeline declarative vẫn có ý nghĩa về trình tự. **filter → map → distinct** có thể cho kết quả khác **distinct → filter → map**, tùy thuộc dữ liệu và quy tắc bằng nhau; chỉ đổi thứ tự khi đã chứng minh tính tương đương.

## 9. Chọn cách viết thích hợp

**Stream phù hợp** khi bài toán là lọc, chuyển kiểu, chuẩn hóa, gom nhóm, tính tổng hoặc biến đổi từ một tập dữ liệu sang tập khác. Những thao tác này có thể ghép thành chuỗi quy tắc độc lập tương đối dễ đọc.

**Vòng lặp phù hợp** khi thuật toán mang nhiều trạng thái phụ thuộc lẫn nhau qua từng bước, cần thoát hoặc tiếp tục theo nhiều nhánh phức tạp, cập nhật tại chỗ, thực hiện I/O có trình tự hoặc khi vòng lặp thể hiện thuật toán rõ hơn. Không có yêu cầu chuyển mọi vòng **for** thành Stream.

Một người viết Java vững sẽ chọn theo **hợp đồng đầu ra, sự rõ ràng, độ đúng, khả năng kiểm thử và hiệu năng đã đo**. Lập trình hàm cung cấp cách nghĩ mạnh về biến đổi dữ liệu; nó không thay thế mọi kỹ thuật imperative.

## 10. Câu hỏi tự kiểm tra

1. Trong ví dụ tên sản phẩm, vì sao **distinct()** phải nằm sau chuẩn hóa nếu muốn coi “ Sách ” và “SÁCH” là một tên?
2. Vì sao **filter(Order::paid)** giữ kiểu **Order**, còn **map(Order::product)** đổi kiểu phần tử thành **String**?
3. Trong bài toán tổng tiền, bước nào quyết định giao dịch hợp lệ, bước nào chọn khóa nhóm, bước nào thực hiện phép cộng?
4. Nếu tên sản phẩm có thể null, bạn cần thêm quy tắc gì và kiểm tra tại vị trí nào?
5. Khi kết quả phải cho phép thêm phần tử, vì sao bạn cần thay đổi cách thu danh sách sau pipeline?
6. Hãy tự viết lại một vòng lặp lọc dữ liệu đang dùng, rồi kiểm tra tính tương đương trên trường hợp đầu vào rỗng, trùng, và dữ liệu biên.

Nắm được cách nói **nguồn → quy tắc chọn → phép biến đổi → cấu trúc đầu ra** là nền tảng để dùng lambda và Stream một cách có chủ đích, thay vì chỉ thay vòng lặp bằng cú pháp ngắn hơn.