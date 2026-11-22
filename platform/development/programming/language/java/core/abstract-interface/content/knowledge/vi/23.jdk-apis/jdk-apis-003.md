# Comparable và Comparator: hai cách biểu diễn việc so sánh

Khi cần sắp xếp đối tượng trong Java, câu hỏi đầu tiên là: **thứ tự tự nhiên của kiểu này là gì, và có cần những thứ tự khác theo từng tình huống không?** Java cung cấp hai cơ chế chính để trả lời:

- `Comparable<T>` cho phép chính kiểu dữ liệu định nghĩa thứ tự tự nhiên của nó thông qua `compareTo`.
- `Comparator<T>` biểu diễn một quy tắc so sánh độc lập, có thể tạo nhiều cách sắp xếp cho cùng một kiểu dữ liệu.

Hai cơ chế đều trả về kết quả so sánh, nhưng khác nhau về nơi đặt quy tắc, khả năng thay đổi và cách kết hợp nhiều tiêu chí. Hiểu đúng chúng giúp sắp xếp danh sách, dùng API Collections và tránh lỗi với các cấu trúc dữ liệu có thứ tự.

## 1. Bài toán cần giải quyết

Giả sử ứng dụng quản lý sản phẩm. Mỗi sản phẩm có tên và giá. Có lúc ta muốn sắp xếp theo tên, lúc khác theo giá tăng dần, hoặc theo giá giảm dần rồi dùng tên để phân định các sản phẩm cùng giá.

Nếu viết riêng một thuật toán sắp xếp cho mỗi trường hợp, mã sẽ lặp lại và khó bảo trì. Thư viện Java đã có các thuật toán sắp xếp; ta chỉ cần cung cấp quy tắc so sánh phù hợp.

`Comparable` phù hợp khi kiểu có một thứ tự tự nhiên hợp lý, chẳng hạn số nguyên theo giá trị hoặc chuỗi theo thứ tự từ điển. `Comparator` phù hợp khi thứ tự phụ thuộc vào nhu cầu của nơi sử dụng, hoặc khi không thể hay không muốn sửa kiểu dữ liệu gốc.

## 2. Comparable và phương thức compareTo

`Comparable<T>` nằm trong `java.lang` nên không cần import. Kiểu triển khai interface này phải định nghĩa:

~~~java
public int compareTo(T other)
~~~

Giá trị trả về mang ý nghĩa:

| Kết quả | Ý nghĩa |
| --- | --- |
| Số âm | Đối tượng hiện tại đứng trước `other` |
| Số 0 | Hai đối tượng tương đương theo thứ tự tự nhiên |
| Số dương | Đối tượng hiện tại đứng sau `other` |

Không cần trả về chính xác `-1` hoặc `1`. Bất kỳ số nguyên âm, số 0 hoặc số nguyên dương nào cũng thể hiện được ba trạng thái đó. Người gọi nên kiểm tra dấu của kết quả thay vì giả định giá trị trả về chỉ có thể là -1, 0 hoặc 1.

Ví dụ, một kiểu `Product` có thể định nghĩa thứ tự tự nhiên theo tên:

~~~java
record Product(String name, int price) implements Comparable<Product> {
    @Override
    public int compareTo(Product other) {
        return this.name.compareTo(other.name);
    }
}
~~~

Trong ví dụ này, việc gọi `a.compareTo(b)` so sánh tên của hai sản phẩm. Các API có thể sử dụng thứ tự tự nhiên đó mà không cần nhận thêm một đối tượng so sánh. Với kiểu tự định nghĩa, hãy chọn thứ tự tự nhiên mà người dùng kiểu có thể dự đoán và giải thích được.

## 3. Comparator và quy tắc so sánh bên ngoài

`Comparator<T>` nằm trong `java.util`. Nó cung cấp phương thức:

~~~java
int compare(T left, T right)
~~~

Ý nghĩa dấu giống `compareTo`: âm nghĩa là `left` đứng trước `right`, 0 nghĩa là tương đương theo comparator đó, dương nghĩa là `left` đứng sau `right`.

Ví dụ comparator so sánh sản phẩm theo giá:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

Quy tắc này tồn tại độc lập với lớp `Product`. Cùng một danh sách có thể được sắp xếp theo tên, giá, ngày tạo hoặc một tiêu chí riêng mà không phải sửa định nghĩa `Product`. Đây là lợi ích chính của `Comparator` khi ứng dụng cần nhiều thứ tự khác nhau.

Một comparator thường được truyền vào các API như `list.sort(comparator)`, `Collections.sort(list, comparator)` hoặc `stream.sorted(comparator)`. Nếu kiểu đã triển khai `Comparable`, các API cũng có thể dùng thứ tự tự nhiên khi không truyền comparator.

## 4. Ví dụ Java 17+ chạy hoàn chỉnh

Chương trình sau minh họa cả hai cơ chế. `Product` định nghĩa thứ tự tự nhiên theo tên; các comparator bổ sung thứ tự theo giá tăng dần và giảm dần. Khi giá bằng nhau, `thenComparing` dùng tên làm tiêu chí tiếp theo.

~~~java
import java.util.Comparator;
import java.util.List;

record Product(String name, int price) implements Comparable<Product> {
    @Override
    public int compareTo(Product other) {
        return this.name.compareTo(other.name);
    }

    String label() {
        return name + ":" + price;
    }
}

public class ComparableComparatorDemo {
    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("Pen", 15),
            new Product("Notebook", 32),
            new Product("Pencil", 5),
            new Product("Marker", 15)
        );

        System.out.println("Original: " + labels(products));
        System.out.println("Natural order (name): "
            + labels(products.stream().sorted().toList()));

        Comparator<Product> byPriceThenName = Comparator
            .comparingInt(Product::price)
            .thenComparing(Product::name);
        System.out.println("By price ascending, then name: "
            + labels(products.stream().sorted(byPriceThenName).toList()));

        Comparator<Product> byPriceDescendingThenName = Comparator
            .comparingInt(Product::price).reversed()
            .thenComparing(Product::name);
        System.out.println("By price descending, then name: "
            + labels(products.stream().sorted(byPriceDescendingThenName).toList()));
    }

    private static List<String> labels(List<Product> products) {
        return products.stream().map(Product::label).toList();
    }
}
~~~

Lưu chương trình vào tệp `ComparableComparatorDemo.java`. Ví dụ sử dụng record và `Stream.toList()`, nên cần Java 17 trở lên.

~~~text
javac ComparableComparatorDemo.java
java ComparableComparatorDemo
~~~

Kết quả stdout:

~~~text
Original: [Pen:15, Notebook:32, Pencil:5, Marker:15]
Natural order (name): [Marker:15, Notebook:32, Pen:15, Pencil:5]
By price ascending, then name: [Pencil:5, Marker:15, Pen:15, Notebook:32]
By price descending, then name: [Notebook:32, Marker:15, Pen:15, Pencil:5]
~~~

Dòng thứ hai dùng `sorted()` không đối số, vì vậy Java sử dụng `Comparable` của `Product` và sắp xếp theo tên. Dòng thứ ba truyền comparator theo giá tăng dần; hai sản phẩm giá 15 được phân định theo tên, nên `Marker` đứng trước `Pen`. Dòng cuối đảo chiều tiêu chí giá nhưng vẫn giữ tên tăng dần khi giá bằng nhau.

`Stream.sorted()` tạo một luồng đã sắp xếp và không sửa danh sách nguồn. Nếu cần sắp xếp trực tiếp danh sách có thể thay đổi, dùng `products.sort(comparator)`; phương thức này thay đổi thứ tự phần tử trong chính danh sách.

## 5. Kết hợp nhiều tiêu chí bằng Comparator

`Comparator` có các phương thức tiện ích để xây dựng quy tắc dễ đọc, thay vì tự viết logic so sánh dài:

- `Comparator.comparing(Product::name)` so sánh theo khóa được trích xuất; khóa phải có thứ tự tự nhiên phù hợp.
- `Comparator.comparingInt(Product::price)` chuyên dùng cho khóa kiểu `int`; tương tự có `comparingLong` và `comparingDouble`.
- `thenComparing(...)` thêm tiêu chí phụ khi tiêu chí trước trả về 0.
- `reversed()` tạo comparator đảo ngược thứ tự của comparator hiện tại.
- `Comparator.nullsFirst(comparator)` và `nullsLast(comparator)` xác định vị trí của giá trị `null`.
- `Comparator.comparing(keyExtractor, keyComparator)` cho phép chỉ định cách so sánh khóa trích xuất.

Ví dụ sắp xếp theo bộ phận, sau đó theo họ tên, có thể diễn đạt bằng chuỗi `thenComparing`. Comparator sẽ dùng tiêu chí kế tiếp chỉ khi các tiêu chí trước coi hai đối tượng là ngang nhau.

Hãy chú ý vị trí của `reversed()`. Biểu thức `comparingInt(Product::price).reversed().thenComparing(Product::name)` có nghĩa giá giảm dần, sau đó tên tăng dần. Nếu đảo ngược toàn bộ comparator sau khi đã nối tên, cả thứ tự tên trong nhóm đồng giá cũng sẽ bị đảo.

Với khóa số, tránh viết `a.price() - b.price()` làm kết quả so sánh. Phép trừ số nguyên có thể tràn và tạo dấu sai. Hãy dùng `Integer.compare(a.price(), b.price())` hoặc `Comparator.comparingInt(...)` để diễn đạt ý định an toàn hơn.

## 6. Hợp đồng của phép so sánh

Một phép so sánh không chỉ cần cho ra thứ tự mong muốn ở một cặp phần tử; nó phải nhất quán trên toàn bộ dữ liệu. Các thuật toán sắp xếp và cấu trúc dữ liệu có thứ tự dựa vào các quy tắc này.

Với `compareTo` và `Comparator.compare`, hãy bảo đảm các tính chất chính:

1. **Tính đối xứng về dấu:** nếu so sánh `a` với `b` cho kết quả âm, so sánh `b` với `a` phải cho kết quả dương, và ngược lại. Nếu một bên là 0 thì chiều ngược lại cũng phải là 0.
2. **Tính bắc cầu:** nếu `a` đứng trước `b` và `b` đứng trước `c`, thì `a` phải đứng trước `c`.
3. **Tính nhất quán với phần tử thứ ba:** nếu `a` và `b` được xem là bằng nhau theo phép so sánh, việc so sánh chúng với `c` phải cho cùng quan hệ thứ tự.
4. **Xử lý null rõ ràng:** `Comparable` thông thường không hỗ trợ gọi `compareTo(null)` và sẽ ném `NullPointerException`. Comparator cũng có thể không chấp nhận `null`, trừ khi được xây dựng để xử lý trường hợp này.

Đối với `Comparable`, tài liệu Java khuyến nghị mạnh rằng `compareTo` nhất quán với `equals`, nghĩa là `a.compareTo(b) == 0` khi và chỉ khi `a.equals(b)` trả về true. Tuy nhiên, điều này không bắt buộc trong mọi kiểu; nếu hai khái niệm khác nhau, cần ghi rõ để người dùng hiểu hệ quả.

Với `Comparator`, việc nhất quán với `equals` cũng thường hữu ích, nhưng không bắt buộc. Comparator có thể chủ ý coi hai đối tượng khác nhau là tương đương theo một tiêu chí cụ thể, chẳng hạn chỉ so sánh họ tên mà bỏ qua mã định danh.

## 7. Tương tác với List, Stream, TreeSet và TreeMap

Lựa chọn comparator ảnh hưởng đến cách API sử dụng thứ tự:

- `List.sort(comparator)` sắp xếp trực tiếp danh sách có thể thay đổi. `Collections.sort(list)` dùng thứ tự tự nhiên, còn overload nhận comparator cho phép chọn thứ tự khác.
- `stream.sorted()` dùng thứ tự tự nhiên của các phần tử. `stream.sorted(comparator)` dùng comparator đã cung cấp và trả về luồng đã sắp xếp.
- `Arrays.sort(array)` có các overload dùng thứ tự tự nhiên hoặc comparator cho mảng tham chiếu.
- `TreeSet` và `TreeMap` dùng thứ tự tự nhiên hoặc comparator để tổ chức phần tử/khóa.

Cần đặc biệt lưu ý `TreeSet` và `TreeMap`. Trong các cấu trúc này, hai phần tử hoặc khóa được xem là cùng vị trí nếu phép so sánh trả về 0, dù `equals` có thể trả về false. Nếu comparator chỉ so sánh giá, hai sản phẩm khác tên nhưng cùng giá có thể bị xem là trùng trong `TreeSet` và một phần tử sẽ không được thêm như mong đợi.

Nếu cần lưu cả các đối tượng có cùng giá, hãy thêm tiêu chí phân biệt như mã định danh hoặc tên, miễn là tiêu chí đó phù hợp với yêu cầu dữ liệu. Trước khi dùng kiểu tự định nghĩa làm khóa trong cấu trúc có thứ tự, hãy kiểm tra hợp đồng so sánh và quyết định rõ thế nào là hai khóa tương đương.

## 8. Lỗi phổ biến và cách tránh

**Viết phép trừ để so sánh số.** Phép trừ có thể tràn số nguyên. Dùng `Integer.compare`, `Long.compare` hoặc các factory của `Comparator`.

**Cố gắng sửa kiểu thư viện để triển khai Comparable.** Không thể thêm `implements Comparable` vào kiểu nguồn mà mình không sở hữu. Hãy cung cấp `Comparator` từ bên ngoài.

**Dùng một thứ tự tự nhiên không hợp lý.** `Comparable` là cam kết của kiểu; nếu nhiều thứ tự có ý nghĩa tương đương, có thể chọn một thứ tự tự nhiên ổn định và để các thứ tự còn lại cho comparator.

**Cho rằng compare trả về -1, 0 hoặc 1.** Hãy kiểm tra dấu của kết quả, không kiểm tra bằng phép so sánh chính xác với -1 hoặc 1.

**Bỏ qua trường hợp bằng nhau.** Nếu hai sản phẩm cùng giá, comparator theo giá trả về 0. Nếu cần kết quả xác định hơn, thêm `thenComparing` theo tiêu chí phụ.

**Dùng Comparator không nhất quán.** Một comparator vi phạm tính bắc cầu hoặc thay đổi kết quả tùy trạng thái có thể làm sắp xếp sai hoặc gây `IllegalArgumentException` khi thuật toán phát hiện hợp đồng bị vi phạm.

**Nhầm sắp xếp với việc thay đổi danh sách nguồn.** `stream.sorted()` không sắp xếp tại chỗ danh sách ban đầu; `List.sort()` thì thay đổi danh sách đó. Chọn API theo việc có cần giữ nguyên thứ tự ban đầu hay không.

## 9. Nên chọn Comparable hay Comparator?

| Câu hỏi | Lựa chọn phù hợp |
| --- | --- |
| Kiểu dữ liệu có một thứ tự tự nhiên rõ ràng? | Triển khai `Comparable<T>` |
| Cần nhiều cách sắp xếp cho cùng một kiểu? | Tạo các `Comparator<T>` riêng |
| Kiểu đến từ thư viện và không sửa được? | Dùng `Comparator<T>` |
| Muốn kết hợp nhiều tiêu chí ngắn gọn? | Dùng `comparing` và `thenComparing` |
| Cần đảo chiều thứ tự? | Dùng `reversed()` tại đúng cấp tiêu chí |
| Dùng kiểu trong `TreeSet` hoặc `TreeMap`? | Kiểm tra ý nghĩa của kết quả so sánh bằng 0 và tính nhất quán với `equals` |

Hai cơ chế bổ trợ cho nhau. Một kiểu có thể triển khai `Comparable` cho thứ tự tự nhiên và đồng thời được sử dụng với nhiều comparator khác nhau trong từng màn hình hoặc nghiệp vụ. Không cần buộc mọi yêu cầu sắp xếp vào duy nhất một phương thức `compareTo`.

## 10. Ghi nhớ

`Comparable` đặt thứ tự tự nhiên bên trong kiểu dữ liệu qua `compareTo`. `Comparator` đặt quy tắc so sánh bên ngoài qua `compare`, nhờ đó cùng một tập dữ liệu có thể được sắp xếp theo nhiều tiêu chí. Cả hai phải tuân theo hợp đồng về dấu và tính bắc cầu; khi dùng nhiều tiêu chí, `thenComparing` giúp thể hiện thứ tự rõ ràng. Đặc biệt, hãy tránh phép trừ có nguy cơ tràn số, xử lý `null` theo chủ đích và kiểm tra hệ quả của kết quả 0 khi dùng cấu trúc dữ liệu có thứ tự.