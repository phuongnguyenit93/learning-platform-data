# ToIntFunction, ToLongFunction và ToDoubleFunction trong Java

## Mục tiêu học tập

Trong Java 8, gói **java.util.function** cung cấp nhiều giao diện hàm chuẩn để biểu diễn phép biến đổi dữ liệu. Ba giao diện **ToIntFunction<T>**, **ToLongFunction<T>** và **ToDoubleFunction<T>** có cùng ý tưởng: nhận **một giá trị kiểu T** và trả về **một giá trị nguyên thủy** tương ứng là **int**, **long** hoặc **double**.

Bài học này giúp bạn hiểu đúng chữ ký và kiểu đích của ba giao diện, viết lambda/method reference tương thích, phân biệt chúng với Function<T,R> và các giao diện bắt đầu bằng Int/Long/Double, áp dụng với **Stream.mapToInt/mapToLong/mapToDouble**, **Comparator.comparingInt/comparingLong/comparingDouble**, **Collectors.summingInt/summingLong/summingDouble**, đồng thời tránh lỗi ép kiểu, tràn số, mất chính xác và tác dụng phụ.

Các kiến thức này vẫn được sử dụng trong Java hiện đại. Các ví dụ hoàn chỉnh bên dưới dùng cú pháp và API có từ Java 8, do đó chạy được trên JDK 8, 17, 21 và những phiên bản tương thích mới hơn.

## 1. Ba giao diện cung cấp kết quả nguyên thủy

Cả ba đều là **functional interface**: chúng có đúng một phương thức trừu tượng cần được lambda triển khai. Chữ ký cốt lõi:

| Giao diện | Phương thức chức năng (SAM) | Đầu vào | Kết quả |
| --- | --- | --- | --- |
| **ToIntFunction<T>** | **int applyAsInt(T value)** | T | int |
| **ToLongFunction<T>** | **long applyAsLong(T value)** | T | long |
| **ToDoubleFunction<T>** | **double applyAsDouble(T value)** | T | double |

Chữ **To** biểu thị hướng chuyển đổi **từ đối tượng/giá trị kiểu T sang một kiểu nguyên thủy**. T là một kiểu tham chiếu hợp lệ trong generics: String, Product, Order, Integer hoặc một kiểu do ứng dụng tự định nghĩa. Kết quả là primitive nên không cần viết **Integer**, **Long** hay **Double** ở vị trí kiểu trả về.

Ví dụ ngắn:

~~~java
ToIntFunction<String> length = text -> text.length();
ToLongFunction<String> doubledLength =
    text -> 2L * text.length();
ToDoubleFunction<String> halfLength =
    text -> text.length() / 2.0;
~~~

Ba dòng này là **đoạn minh họa**, cần **import java.util.function.ToIntFunction**, **ToLongFunction**, **ToDoubleFunction** và đặt trong một phương thức/lớp phù hợp; đây chưa phải chương trình độc lập.

Lời gọi đúng tương ứng:

~~~java
int count = length.applyAsInt("Java");         // 4
long twice = doubledLength.applyAsLong("Java"); // 8L
double half = halfLength.applyAsDouble("Java"); // 2.0
~~~

Không gọi **apply(...)** như Function<T,R>. Tên phương thức SAM của mỗi giao diện là **applyAsInt**, **applyAsLong** hoặc **applyAsDouble**, và chúng nhận đúng **một** đối số.

**Kết luận quan trọng:** phần thân lambda xác định phép tính; **giao diện đích** xác định kiểu đầu vào và primitive phải được trả về. Dấu mũi tên **->** tự nó không cho biết kết quả phải là int, long hay double.

## 2. Cấu trúc lambda và suy luận kiểu

Một lambda có đúng một tham số có thể viết với hoặc không với ngoặc tròn khi để Java suy luận kiểu:

~~~java
ToIntFunction<String> a = s -> s.length();
ToIntFunction<String> b = (s) -> s.length();
ToIntFunction<String> c = (String s) -> s.length();
~~~

Ba biểu thức trên đều hợp lệ và cho cùng kết quả với đầu vào không null. Kiểu của **s** là **String** do kiểu đích **ToIntFunction<String>** quyết định.

Nếu ghi rõ kiểu tham số, phải viết **(String s) -> ...**; dạng **String s -> ...** không hợp lệ. Trường hợp giao diện nhận một tham số không được viết lambda không tham số **() -> ...** hoặc hai tham số **(a,b) -> ...**.

Dạng biểu thức và dạng khối:

~~~java
ToLongFunction<String> sizeA = s -> s.length();

ToLongFunction<String> sizeB = s -> {
    long result = s.length();
    return result;
};
~~~

Trong dạng biểu thức, Java dùng giá trị biểu thức làm kết quả. Trong dạng khối, khi phương thức đích yêu cầu giá trị, cần **return** trên mọi đường đi kết thúc bình thường. Với ví dụ trên, int từ **String.length()** được **mở rộng tự động sang long**; không cần ép kiểu thủ công.

Có thể dùng method reference khi đã có phương thức phù hợp:

~~~java
ToIntFunction<String> length = String::length;
~~~

**String::length** phù hợp SAM **int applyAsInt(String)**: tham số String trở thành đối tượng nhận lời gọi length(), và kết quả int được trả về. Method reference cũng cần **kiểu đích**, không phải chỉ riêng lambda mới cần.

## 3. Vì sao nên dùng kiểu trả về nguyên thủy?

So sánh hai hợp đồng:

~~~java
Function<String, Integer> boxed = String::length;
ToIntFunction<String> primitive = String::length;
~~~

Đây là đoạn minh họa, cần import hai giao diện khi dùng riêng.

Cả hai lấy độ dài chuỗi. Nhưng **Function<String,Integer>.apply(...)** có kiểu kết quả **Integer** (wrapper), còn **ToIntFunction<String>.applyAsInt(...)** có kiểu kết quả **int** nguyên thủy.

Khi một phép tính sinh hàng triệu kết quả int và cần tính tổng, việc xử lý primitive có thể giảm nhu cầu **boxing/unboxing** và làm việc hiệu quả với **IntStream**. Sự khác biệt hữu ích trong pipeline tính toán, nhưng không nên khẳng định mọi đoạn mã primitive luôn chạy nhanh hơn: hiệu năng thực tế còn phụ thuộc trình biên dịch JIT, kích thước dữ liệu, nguồn dữ liệu và phép tính. Muốn quyết định dựa trên hiệu năng, hãy đo với công cụ benchmark thích hợp (ví dụ JMH).

**Giới hạn quan trọng:** đầu vào vẫn là **T**. Nếu khai báo **ToIntFunction<Integer>**, giá trị đầu vào vẫn là Integer wrapper; chỉ kiểu **kết quả** của applyAsInt là primitive int. Ba giao diện này **không tự tránh boxing ở đầu vào** khi T là wrapper.

Các trường hợp nên dùng:

- Lấy **số lượng**, **độ dài**, **tuổi**, **mã thứ tự nguyên** từ đối tượng: ToIntFunction<T>.
- Lấy **số byte**, **thời điểm dạng epoch milli**, **bộ đếm lớn** từ đối tượng: ToLongFunction<T>.
- Lấy **khối lượng**, **điểm trung bình**, **tỷ lệ**, **tọa độ hoặc phép đo thực** từ đối tượng: ToDoubleFunction<T>.

Kiểu dữ liệu phải phù hợp với ngữ nghĩa và miền giá trị. Một con số lớn không nên nhét vào int chỉ vì phần thân lambda viết ngắn hơn. Với dữ liệu tài chính cần chính xác theo hệ thập phân, **double** thường không phải lựa chọn lưu trữ phù hợp; xem phần về độ chính xác bên dưới.

## 4. Ví dụ Java hoàn chỉnh: trích xuất ba loại thông tin

Tạo tệp **PrimitiveExtractorsDemo.java**. Lớp Shipment giữ số kiện dạng int, dung lượng byte dạng long và khối lượng dạng double. Ba giao diện cùng nhận đầu vào kiểu Shipment nhưng trả về kiểu khác nhau.

~~~java
import java.util.function.ToDoubleFunction;
import java.util.function.ToIntFunction;
import java.util.function.ToLongFunction;

public class PrimitiveExtractorsDemo {
    static final class Shipment {
        private final String code;
        private final int units;
        private final long bytes;
        private final double weightKg;

        Shipment(String code, int units, long bytes, double weightKg) {
            this.code = code;
            this.units = units;
            this.bytes = bytes;
            this.weightKg = weightKg;
        }

        int getUnits() {
            return units;
        }

        long getBytes() {
            return bytes;
        }

        double getWeightKg() {
            return weightKg;
        }
    }

    public static void main(String[] args) {
        Shipment shipment =
            new Shipment("BX-1", 4, 3_100_000_000L, 2.5);

        ToIntFunction<Shipment> unitCount = Shipment::getUnits;

        ToLongFunction<Shipment> byteCount =
            s -> s.getBytes();

        ToDoubleFunction<Shipment> weight = Shipment::getWeightKg;

        ToDoubleFunction<Shipment> weightPerUnit =
            s -> s.getWeightKg() / s.getUnits();

        System.out.println("Số kiện: " +
            unitCount.applyAsInt(shipment));
        System.out.println("Số byte: " +
            byteCount.applyAsLong(shipment));
        System.out.println("Khối lượng (kg): " +
            weight.applyAsDouble(shipment));
        System.out.println("Kg mỗi kiện: " +
            weightPerUnit.applyAsDouble(shipment));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrimitiveExtractorsDemo.java
java PrimitiveExtractorsDemo
~~~

Kết quả:

~~~text
Số kiện: 4
Số byte: 3100000000
Khối lượng (kg): 2.5
Kg mỗi kiện: 0.625
~~~

Giải thích:

1. **ToIntFunction<Shipment>** lấy số kiện, dùng **applyAsInt** và trả int.
2. **ToLongFunction<Shipment>** lấy số byte; giá trị **3_100_000_000L** lớn hơn giới hạn dương của int, nên sử dụng **long** và hậu tố literal **L** là có ý nghĩa.
3. **ToDoubleFunction<Shipment>** lấy khối lượng thực và tính 2.5 / 4 = 0.625.
4. Cùng kiểu đầu vào Shipment không có nghĩa các giao diện có cùng kiểu trả về. Chọn loại dựa trên dữ liệu mà API cần.
5. **code** là thuộc tính bổ sung của đối tượng minh họa; không ảnh hưởng tới các kết quả được in.

Việc khởi tạo các function **không gọi** phương thức getUnits, getBytes hay getWeightKg. Mỗi lần gọi **applyAsX(shipment)**, phần thân của function tương ứng mới được thực hiện. Các function **không tự ghi nhớ kết quả**, không tự chạy bất đồng bộ và không tự biến dữ liệu Shipment thành bất biến.

## 5. Chuyển đổi số: widening, narrowing và các bẫy

Kiểu trả về phải tương thích với primitive mà SAM yêu cầu. Java có các phép **mở rộng nguyên thủy (widening primitive conversion)** hợp lệ, ví dụ **int -> long**, **int -> double**, **long -> double**. Một phép mở rộng có thể hợp lệ về cú pháp nhưng không phải luôn giữ trọn độ chính xác.

Ví dụ hợp lệ:

~~~java
ToLongFunction<String> charsAsLong = s -> s.length();
ToDoubleFunction<String> charsAsDouble = s -> s.length();
~~~

**String.length()** trả int; Java có thể tự mở rộng int sang long hoặc double cho kết quả. Với toàn bộ miền int, chuyển int sang double giữ chính xác giá trị nguyên, vì double có đủ bit độ chính xác cho miền int. Ngược lại, chuyển một **long** rất lớn sang double có thể làm tròn, do double không biểu diễn chính xác mọi số nguyên 64 bit.

Ví dụ không hợp lệ nếu không chuyển đổi rõ ràng:

~~~java
// ToIntFunction<String> invalid = s -> s.length() / 2.0;
~~~

Đây là dòng cố ý để trong comment. Phép chia cho 2.0 trả double, nhưng **applyAsInt** đòi int. Java không tự thu hẹp double thành int. Không nên ép kiểu chỉ để làm trình biên dịch im lặng: ép từ double về int có thể bỏ phần thập phân, bão hòa ở giới hạn khi vượt miền và có quy tắc riêng với NaN. Phải xác định yêu cầu nghiệp vụ về làm tròn trước khi quyết định.

Nếu thực sự cần kết quả nguyên, dùng một công thức đúng bản chất:

~~~java
ToIntFunction<String> halfTruncated = s -> s.length() / 2;
ToDoubleFunction<String> halfExact = s -> s.length() / 2.0;
~~~

Với độ dài 5, biểu thức thứ nhất là **2** (chia nguyên), biểu thức thứ hai là **2.5**. Đây không phải sự khác nhau do ToIntFunction tự làm tròn, mà do **kiểu toán hạng và quy tắc phép chia**.

**Các lưu ý chọn kiểu:**

- **int** là 32 bit có dấu. Tổng số lượng lớn có thể vượt miền int.
- **long** là 64 bit có dấu, thích hợp cho bộ đếm/dung lượng lớn hơn, nhưng vẫn có thể tràn khi cộng hoặc nhân.
- **double** là dấu phẩy động nhị phân 64 bit; phù hợp nhiều phép đo, không đại diện chính xác cho mọi số thập phân. Các giá trị đặc biệt có **NaN**, **Infinity** và **-Infinity**.
- **ToDoubleFunction<T>** không tự chuẩn hóa NaN, làm tròn theo yêu cầu nghiệp vụ, hay bảo đảm tổng chính xác tuyệt đối.
- Nếu đầu vào có thể null, lambda truy cập phương thức như **s.length()** sẽ ném NullPointerException trừ khi tự xử lý null.

## 6. Ba hàm này trong Stream.mapToInt, mapToLong và mapToDouble

Đây là nhóm API quan trọng nhất sử dụng ba giao diện trên. Một **Stream<T>** chứa phần tử kiểu tham chiếu T, và có thể chuyển thành luồng primitive bằng:

| API | Tham số là giao diện nào? | Kiểu Stream kết quả |
| --- | --- | --- |
| **Stream<T>.mapToInt(...)** | ToIntFunction<? super T> | IntStream |
| **Stream<T>.mapToLong(...)** | ToLongFunction<? super T> | LongStream |
| **Stream<T>.mapToDouble(...)** | ToDoubleFunction<? super T> | DoubleStream |

Ba luồng primitive có sẵn các thao tác như **sum()**, **average()**, **summaryStatistics()**, **min()**, **max()**, **count()**. Chúng giảm nhu cầu boxing ở các giá trị kết quả trung gian so với việc dùng Stream<Integer>, Stream<Long> hay Stream<Double> trong nhiều pipeline số học.

Ví dụ ý tưởng:

~~~java
int total = orders.stream()
    .mapToInt(order -> order.getQuantity())
    .sum();

long bytes = orders.stream()
    .mapToLong(order -> order.getBytes())
    .sum();

double weight = orders.stream()
    .mapToDouble(order -> order.getWeightKg())
    .sum();
~~~

Đây là **các đoạn API minh họa**, giả định **orders** là danh sách các đối tượng có ba phương thức tương ứng. Đoạn không chạy độc lập nếu chưa định nghĩa kiểu Order và biến orders.

Sự chuyển đổi ở đây là: **Stream<Order> -> IntStream/LongStream/DoubleStream**. Bản thân **Order** vẫn là đối tượng; phần kết quả của ánh xạ là primitive.

### Stream là lazy đến khi có terminal operation

Việc khai báo:

~~~java
IntStream quantities = orders.stream()
    .mapToInt(order -> order.getQuantity());
~~~

chỉ xây pipeline; với một nguồn List thông thường, việc lấy quantity sẽ được thực hiện khi có terminal operation như **sum()**, **toArray()** hoặc **forEach()**. Một Stream chỉ sử dụng được cho **một lần tiêu thụ**; sau khi đã chạy terminal operation, muốn tính thêm thống kê phải tạo pipeline mới hoặc lưu kết quả phù hợp.

Không nên đặt tác dụng phụ quan trọng bên trong các ToIntFunction/ToLongFunction/ToDoubleFunction dùng cho Stream. Tùy tối ưu hóa và short-circuit, một số phần tử có thể không cần xử lý; trên parallel stream, thứ tự và luồng thực thi cũng có thể khác. Hãy giữ các phép trích xuất dữ liệu **độc lập, không sửa trạng thái chung** nếu có thể.

## 7. Ví dụ Java hoàn chỉnh: tổng hợp số lượng, byte và giá trị đo

Tạo tệp **PrimitiveStreamsDemo.java**:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Locale;
import java.util.function.ToDoubleFunction;
import java.util.function.ToIntFunction;
import java.util.function.ToLongFunction;

public class PrimitiveStreamsDemo {
    static final class Item {
        final String name;
        final int quantity;
        final long bytes;
        final double unitPrice;

        Item(String name, int quantity, long bytes, double unitPrice) {
            this.name = name;
            this.quantity = quantity;
            this.bytes = bytes;
            this.unitPrice = unitPrice;
        }
    }

    public static void main(String[] args) {
        List<Item> items = Arrays.asList(
            new Item("A", 3, 1_500_000_000L, 12.5),
            new Item("B", 2, 2_000_000_000L, 40.0),
            new Item("C", 1,   700_000_000L, 100.0)
        );

        ToIntFunction<Item> quantity = item -> item.quantity;
        ToLongFunction<Item> byteCount = item -> item.bytes;
        ToDoubleFunction<Item> lineValue =
            item -> item.quantity * item.unitPrice;

        int totalItems = items.stream()
            .mapToInt(quantity)
            .sum();

        long totalBytes = items.stream()
            .mapToLong(byteCount)
            .sum();

        double totalValue = items.stream()
            .mapToDouble(lineValue)
            .sum();

        IntSummaryStatistics stats = items.stream()
            .mapToInt(quantity)
            .summaryStatistics();

        double meanUnitPrice = items.stream()
            .mapToDouble(item -> item.unitPrice)
            .average()
            .orElse(0.0);

        System.out.println("Tổng số lượng: " + totalItems);
        System.out.println("Tổng số byte: " + totalBytes);
        System.out.println("Tổng giá trị: " + totalValue);
        System.out.println("Min/Max số lượng: " +
            stats.getMin() + "/" + stats.getMax());
        System.out.printf(Locale.ROOT,
            "Giá đơn vị trung bình: %.2f%n", meanUnitPrice);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrimitiveStreamsDemo.java
java PrimitiveStreamsDemo
~~~

Kết quả:

~~~text
Tổng số lượng: 6
Tổng số byte: 4200000000
Tổng giá trị: 217.5
Min/Max số lượng: 1/3
Giá đơn vị trung bình: 50.83
~~~

Phân tích:

- **ToIntFunction<Item>** trích số lượng 3, 2, 1; **IntStream.sum()** trả 6. **summaryStatistics()** tổng hợp min = 1 và max = 3.
- **ToLongFunction<Item>** trích các số byte và dùng long để giữ tổng 4_200_000_000, vượt miền giá trị int.
- **ToDoubleFunction<Item>** tính lần lượt 3×12.5 = 37.5; 2×40.0 = 80.0; 1×100.0 = 100.0, tổng = 217.5.
- **average()** trên DoubleStream trả **OptionalDouble**, vì Stream có thể rỗng. **orElse(0.0)** là chính sách dự phòng của ví dụ, không phải quy tắc phổ quát cho một tập dữ liệu rỗng.
- **Locale.ROOT** và định dạng hai chữ số sau dấu thập phân giúp đầu ra minh họa có cách hiển thị ổn định; logic nghiệp vụ thực tế phải quyết định chính sách làm tròn.

**Cảnh báo về tiền tệ:** chương trình dùng **double unitPrice** chỉ để minh họa phép trích xuất/số học primitive. Với tiền thật cần chính xác theo thập phân, hãy dùng **BigDecimal** hoặc số nguyên theo đơn vị nhỏ nhất (nếu miền giá trị và quy tắc tính phù hợp), không mặc nhiên dùng double để cộng dồn số tiền.

## 8. Các bộ so sánh Comparator.comparingInt/Long/Double

Không chỉ Stream, API **Comparator** cũng nhận ba kiểu extractor này. Các phương thức static của Comparator trong Java 8:

~~~java
Comparator<T> c1 = Comparator.comparingInt(extractor);
Comparator<T> c2 = Comparator.comparingLong(extractor);
Comparator<T> c3 = Comparator.comparingDouble(extractor);
~~~

Đây là **sơ đồ kiểu**, không phải mã độc lập: **extractor** phải là ToIntFunction/ToLongFunction/ToDoubleFunction phù hợp với kiểu T. Java suy luận T từ ngữ cảnh và extractor.

Các phương thức giúp xây quy tắc thứ tự bằng khóa primitive, tránh việc dùng phép trừ để so sánh. Ví dụ viết **(a,b) -> a.age - b.age** có thể tràn int và sai thứ tự; **Comparator.comparingInt(Person::getAge)** rõ ràng hơn và dùng phép so sánh đúng hợp đồng.

Có thể ghép tiêu chí bằng **thenComparing(...)**, dùng **reversed()** để đảo thứ tự và xây bộ so sánh nhiều trường. Chú ý đảo cả comparator đã ghép khác với chỉ đảo một thành phần của thứ tự.

Khi dùng **comparingDouble**, các giá trị NaN, vô cực và số âm 0.0 có thứ tự theo quy tắc so sánh của Double. Nếu ứng dụng cần coi NaN là không hợp lệ hoặc muốn gom các trường hợp đặc biệt, hãy xác định và kiểm tra quy tắc nghiệp vụ trước khi sắp xếp.

## 9. Collectors.summingInt/Long/Double và hàm trích khóa

Java 8 cũng có các collector:

- **Collectors.summingInt(ToIntFunction<? super T>)**: lấy int từ mỗi phần tử và tổng hợp thành Integer.
- **Collectors.summingLong(ToLongFunction<? super T>)**: lấy long từ mỗi phần tử và tổng hợp thành Long.
- **Collectors.summingDouble(ToDoubleFunction<? super T>)**: lấy double từ mỗi phần tử và tổng hợp thành Double.
- Các collector như **averagingInt**, **averagingLong**, **averagingDouble**, **summarizingInt**, **summarizingLong**, **summarizingDouble** cũng nhận extractor kiểu nguyên thủy tương ứng, nhưng kiểu kết quả cuối là Double hoặc đối tượng thống kê theo hợp đồng từng collector.

Mặc dù extractor trả primitive, **collect(...) trả về kiểu đối tượng** do collector định nghĩa. Vì vậy đừng hiểu rằng không có boxing nào xảy ra trong toàn bộ pipeline; ưu điểm của extractor primitive chủ yếu nằm ở thao tác trích giá trị và các bước tính toán trung gian.

Có thể dùng **Collectors.groupingBy(...)** kết hợp **Collectors.summingInt(...)** để tính tổng số lượng theo nhóm, hoặc **groupingBy** với **summarizingDouble** để tổng hợp thống kê theo một thuộc tính. Khi cần một phép tổng đơn giản trên toàn bộ Stream, **mapToInt(...).sum()** thường dễ đọc hơn.

**Cẩn trọng với tràn số:** sum trên int có thể tràn. Các phép tổng trên long cũng có giới hạn. Nếu cần miền không giới hạn, hãy dùng kiểu dữ liệu/thao tác thích hợp hơn, ví dụ BigInteger cho số nguyên lớn hoặc BigDecimal khi có yêu cầu chính xác thập phân.

## 10. Ví dụ Java hoàn chỉnh: Comparator và Collector dùng cùng các extractor

Tạo tệp **PrimitiveApiIntegrationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class PrimitiveApiIntegrationDemo {
    static final class Member {
        private final String name;
        private final int age;
        private final long bytes;
        private final double score;

        Member(String name, int age, long bytes, double score) {
            this.name = name;
            this.age = age;
            this.bytes = bytes;
            this.score = score;
        }

        String getName() {
            return name;
        }

        int getAge() {
            return age;
        }

        long getBytes() {
            return bytes;
        }

        double getScore() {
            return score;
        }
    }

    private static String names(List<Member> members) {
        return members.stream()
            .map(Member::getName)
            .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        List<Member> members = new ArrayList<>(Arrays.asList(
            new Member("An", 30, 6_000_000_000L, 4.2),
            new Member("Binh", 24, 2_000_000_000L, 4.8),
            new Member("Chi", 24, 4_000_000_000L, 4.6)
        ));

        Comparator<Member> ageThenScore =
            Comparator.comparingInt(Member::getAge)
                .thenComparing(
                    Comparator.comparingDouble(Member::getScore)
                        .reversed())
                .thenComparing(Member::getName);

        members.sort(ageThenScore);
        System.out.println("Theo tuổi/điểm: " + names(members));

        members.sort(
            Comparator.comparingLong(Member::getBytes).reversed());
        System.out.println("Byte giảm dần: " + names(members));

        int sumAges = members.stream()
            .collect(Collectors.summingInt(Member::getAge));

        long sumBytes = members.stream()
            .collect(Collectors.summingLong(Member::getBytes));

        double averageScore = members.stream()
            .collect(Collectors.averagingDouble(Member::getScore));

        System.out.println("Tổng tuổi: " + sumAges);
        System.out.println("Tổng byte: " + sumBytes);
        System.out.printf(Locale.ROOT,
            "Điểm trung bình: %.2f%n", averageScore);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrimitiveApiIntegrationDemo.java
java PrimitiveApiIntegrationDemo
~~~

Kết quả:

~~~text
Theo tuổi/điểm: Binh, Chi, An
Byte giảm dần: An, Chi, Binh
Tổng tuổi: 78
Tổng byte: 12000000000
Điểm trung bình: 4.53
~~~

Điểm cần hiểu:

1. **Comparator.comparingInt(Member::getAge)** cần ToIntFunction<Member> để lấy tuổi. Hai người bằng tuổi được so tiếp bằng điểm giảm dần thông qua **comparingDouble(...).reversed()**; sau đó mới xét tên.
2. **Comparator.comparingLong(Member::getBytes)** chọn byte dạng long làm khóa; reversed() tạo thứ tự giảm dần.
3. **Collectors.summingInt**, **summingLong**, **averagingDouble** nhận method reference trích kiểu nguyên thủy tương ứng. Kết quả cuối là tổng/giá trị trung bình của toàn bộ nhóm.
4. Các method reference **Member::getAge**, **Member::getBytes** và **Member::getScore** chỉ có một đối số về mặt functional interface: một đối tượng Member dùng để gọi phương thức instance tương ứng.
5. **List.sort** thay đổi thứ tự của danh sách đang chứa phần tử; các phép tổng không phụ thuộc thứ tự trong ví dụ vì dữ liệu cố định và các phép tính nhỏ, nhưng không nên suy rộng điều đó thành mọi phép cộng double đều bất biến về sai số khi đổi thứ tự.

### Ghép comparator đúng chiều

Không nên nhầm:

~~~java
Comparator<Member> allReversed =
    Comparator.comparingInt(Member::getAge)
        .thenComparingDouble(Member::getScore)
        .reversed();
~~~

với:

~~~java
Comparator<Member> ageAscScoreDesc =
    Comparator.comparingInt(Member::getAge)
        .thenComparing(
            Comparator.comparingDouble(Member::getScore).reversed());
~~~

Đây là các đoạn minh họa cần khai báo Member và import Comparator. Biểu thức đầu **đảo cả tuổi lẫn điểm** theo quy tắc ghép; biểu thức thứ hai giữ tuổi tăng dần nhưng điểm giảm dần trong nhóm cùng tuổi. Trong ví dụ hoàn chỉnh, chúng ta dùng cách thứ hai.

## 11. Phân biệt với IntFunction, LongFunction, DoubleFunction và các operator

Tên gần giống nhau là nguồn lỗi phổ biến nhất. Hãy đọc kỹ **vị trí** primitive trong chữ ký:

| Giao diện | SAM | Ý nghĩa |
| --- | --- | --- |
| **ToIntFunction<T>** | int applyAsInt(T value) | T -> int |
| **ToLongFunction<T>** | long applyAsLong(T value) | T -> long |
| **ToDoubleFunction<T>** | double applyAsDouble(T value) | T -> double |
| **IntFunction<R>** | R apply(int value) | int -> R |
| **LongFunction<R>** | R apply(long value) | long -> R |
| **DoubleFunction<R>** | R apply(double value) | double -> R |
| **IntUnaryOperator** | int applyAsInt(int operand) | int -> int |
| **LongUnaryOperator** | long applyAsLong(long operand) | long -> long |
| **DoubleUnaryOperator** | double applyAsDouble(double operand) | double -> double |
| **IntToLongFunction** | long applyAsLong(int value) | int -> long |
| **IntToDoubleFunction** | double applyAsDouble(int value) | int -> double |
| **LongToDoubleFunction** | double applyAsDouble(long value) | long -> double |

Ví dụ:

~~~java
ToIntFunction<String> length = String::length;
IntFunction<String> label = n -> "ID-" + n;
IntUnaryOperator doubleIt = n -> 2 * n;
~~~

Ba dòng là đoạn minh họa; cần import các interface. Trong trường hợp đầu, **đầu vào** là String, **đầu ra** là int. Trường hợp thứ hai nhận int rồi tạo String. Trường hợp cuối nhận int và trả int.

**ToIntFunction<Integer> khác IntUnaryOperator:** giao diện đầu nhận Integer **tham chiếu** và trả int; giao diện sau nhận int **nguyên thủy** và trả int. Nếu pipeline đã là IntStream và muốn biến đổi từng int, **IntUnaryOperator** phù hợp với **IntStream.map(...)** hơn ToIntFunction<Integer>.

Khi xử lý **LongStream.mapToDouble(...)**, API nhận LongToDoubleFunction, **không phải ToDoubleFunction<Long>**, vì đầu vào của stream đó là long primitive. Nhìn vào **kiểu phần tử nguồn** trước khi chọn functional interface.

## 12. Phân biệt result boxing với input boxing

Ví dụ:

~~~java
ToIntFunction<Integer> plusOne = number -> number + 1;
IntUnaryOperator plusOnePrimitive = number -> number + 1;
~~~

Cả hai cùng tính cộng 1 theo ý tưởng, nhưng:

- **ToIntFunction<Integer>** nhận **Integer**; toán tử cộng một thực hiện unboxing nếu cần. Đối số null sẽ gây NullPointerException khi unboxing.
- **IntUnaryOperator** nhận int nên không có giá trị null kiểu primitive; phù hợp với IntStream.
- Kết quả của cả hai đều là int.

Lợi ích tránh boxing của ToIntFunction nằm ở việc tạo **primitive result**. Không nên nói rằng nó hoàn toàn loại bỏ boxing cho mọi trường hợp. Nhiều ứng dụng dùng **Stream<Product>** và trích khóa int từ từng Product; khi đó bản thân Product vốn đã là đối tượng và không liên quan đến boxing của int input.

## 13. Lỗi phổ biến và cách khắc phục

| Viết sai hoặc suy luận sai | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Dùng **apply()** trên ToIntFunction | SAM là applyAsInt(T) | Dùng **applyAsInt(value)** |
| Dùng **applyAsInt** trên ToLongFunction | SAM là applyAsLong(T) | Dùng **applyAsLong(value)** |
| Viết **() -> 5** cho ToIntFunction<String> | SAM nhận đúng một tham số | Viết **s -> 5** hoặc chọn IntSupplier nếu không cần đầu vào |
| Viết **(a,b) -> a+b** cho ToDoubleFunction<Order> | SAM nhận đúng một tham số | Đưa phép tính về một đối tượng đầu vào hoặc dùng BiFunction thích hợp |
| Dùng **ToIntFunction<String> f = s -> s.length()/2.0** | Biểu thức trả double, không tự thu hẹp về int | Dùng chia nguyên cho int, hoặc đổi sang ToDoubleFunction |
| Dùng ToIntFunction để trả số byte có thể trên 2,147,483,647 | int không đủ miền giá trị | Dùng ToLongFunction và long |
| Tưởng ToIntFunction<Integer> có đầu vào primitive | T của generics là Integer tham chiếu | Chọn IntUnaryOperator nếu cần int -> int |
| Tưởng ToLongFunction<T> là long -> T | Đảo chiều chức năng | Giao diện đó là T -> long; long -> R là LongFunction<R> |
| Dùng **(a,b) -> a.age-b.age** để so sánh | Trừ int có thể tràn | Dùng Comparator.comparingInt hoặc Integer.compare |
| Dùng double để lưu/cộng số tiền cần chính xác | Số thập phân thường không biểu diễn chính xác bằng binary floating point | Xem BigDecimal hoặc đơn vị nguyên |
| Chạy sum() trên int khi tổng có thể lớn | Có thể tràn int mà không báo lỗi | Chọn long/BigInteger hoặc phép cộng có kiểm tra |
| Cho rằng mapToInt sinh ngay mọi kết quả | Stream thường lazy | Nhận diện terminal operation |
| Tái sử dụng một Stream sau sum() | Stream chỉ được tiêu thụ một lần | Tạo pipeline mới |
| Chèn tác dụng phụ vào extractor dùng song song | Có thể gây race và phụ thuộc thứ tự | Ưu tiên extractor thuần, dữ liệu ổn định |
| Mong một lambda tự bắt checked IOException | SAM không khai báo throws checked exception | Xử lý tại chỗ hoặc thiết kế API phù hợp |

### Ngoại lệ, biến bị bắt giữ và tính an toàn

Các phương thức **applyAsInt**, **applyAsLong**, **applyAsDouble** không khai báo **throws IOException**. Một lambda được gán cho các giao diện này không thể ném thẳng checked exception chưa xử lý; không nên dùng cách bọc lỗi tùy tiện để che giấu hợp đồng.

Lambda có thể truy cập biến cục bộ bên ngoài nếu biến đó là **final hoặc effectively final**; quy tắc áp dụng cho biến, không tự biến đối tượng được tham chiếu thành immutable. Nếu nhiều luồng cùng gọi function chứa trạng thái mutable chung, cần xem xét an toàn đồng thời. Các extractor đơn giản chỉ đọc trường bất biến hoặc trạng thái ổn định thường dễ hiểu và dễ kiểm tra hơn.

## 14. Một số câu hỏi thực hành

**Bài 1 — Chọn giao diện.** Có kiểu Invoice với **getLineCount(): int**, **getFileSize(): long**, **getRatio(): double**. Hãy khai báo ba extractor tương ứng.

Đáp án gợi ý (đoạn minh họa cần lớp Invoice phù hợp):

~~~java
ToIntFunction<Invoice> lines = Invoice::getLineCount;
ToLongFunction<Invoice> bytes = Invoice::getFileSize;
ToDoubleFunction<Invoice> ratio = Invoice::getRatio;
~~~

**Bài 2 — Đọc kết quả.** Cho:

~~~java
ToIntFunction<String> length = String::length;
ToLongFunction<String> scaled = s -> 1_000_000_000L * s.length();
ToDoubleFunction<String> average = s -> s.length() / 2.0;
~~~

Dự đoán kết quả khi truyền chuỗi "Java". Đáp án: **4**, **4000000000L**, **2.0**. Lưu ý hằng **1_000_000_000L** khiến phép nhân dùng long; nếu dùng int literal và toán hạng int trong phép nhân, kết quả có thể tràn trước khi được gán cho long.

**Bài 3 — Từ Stream<T> sang stream primitive.** Với danh sách có qty = 2, 3, 5, cần tính tổng. Viết:

~~~java
int total = items.stream()
    .mapToInt(item -> item.getQuantity())
    .sum();
~~~

Đáp án là **10**, nếu items chứa đúng ba phần tử và getQuantity trả các số ấy. Đoạn minh họa giả định biến items và phương thức tồn tại.

**Bài 4 — Kiểm tra hướng mũi tên.** Để biến một số int thành chuỗi "N-7", bạn chọn ToIntFunction<String> hay IntFunction<String>? Đáp án: **IntFunction<String>** vì đầu vào primitive int, đầu ra String. Nếu biến chuỗi "N-7" thành số nguyên, phải xác định cách parse đầu vào và có thể chọn ToIntFunction<String> nếu kết quả mong muốn là int.

**Bài 5 — Sắp xếp.** Bạn có List<Person> và muốn tuổi tăng dần, điểm giảm dần khi cùng tuổi. Hãy dùng:

~~~java
Comparator<Person> comparator =
    Comparator.comparingInt(Person::getAge)
        .thenComparing(
            Comparator.comparingDouble(Person::getScore).reversed());
~~~

Đây là đoạn minh họa cần Person và import Comparator. Giải thích vì sao đặt **reversed()** lên toàn bộ comparator sẽ đảo cả thứ tự tuổi.

**Bài 6 — Dữ liệu tiền.** Vì sao ToDoubleFunction<Order> để tính tiền có thể không đủ cho sổ kế toán? Vì **double có sai số dấu phẩy động**, không tự bảo đảm số chữ số thập phân, quy tắc làm tròn hoặc tính đúng theo đơn vị tiền. Trong hệ thống cần độ chính xác thập phân, hãy thiết kế giá trị tiền bằng BigDecimal/đơn vị nguyên theo hợp đồng nghiệp vụ thay vì mặc định dùng double.

**Bài 7 — Không có boxing ở đâu?** Với ToIntFunction<Integer>, phần nào chắc chắn là primitive? Đáp án: **giá trị trả về từ applyAsInt** là int. Đầu vào generic Integer vẫn là một đối tượng tham chiếu và có thể bị unboxing khi dùng phép toán.

## Tổng kết

**ToIntFunction<T>**, **ToLongFunction<T>** và **ToDoubleFunction<T>** cùng nhận một tham số kiểu T nhưng trả về primitive **int**, **long** và **double** thông qua **applyAsInt**, **applyAsLong**, **applyAsDouble**. Chúng là lựa chọn tự nhiên khi cần trích một đại lượng số từ đối tượng và đưa đại lượng đó vào **IntStream**, **LongStream**, **DoubleStream**, comparator hoặc collector.

Để chọn đúng, hãy kiểm tra **kiểu phần tử đầu vào**, **miền giá trị kết quả**, **độ chính xác mong muốn** và **chữ ký của API nhận function**. Kiểu nguyên thủy giúp biểu đạt dữ liệu rõ ràng và có thể giảm boxing ở đầu ra, nhưng không tự giải quyết tràn số, sai số double, null đầu vào, ngoại lệ hay an toàn đa luồng.