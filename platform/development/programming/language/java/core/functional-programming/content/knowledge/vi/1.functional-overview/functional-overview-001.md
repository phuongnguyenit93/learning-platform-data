# Lập trình hàm là gì và giải quyết vấn đề nào trong Java?

## 1. Vấn đề xuất phát từ đâu?

Khi chương trình xử lý dữ liệu, ta thường phải lọc, biến đổi, tổng hợp rồi trả kết quả. Cách viết mệnh lệnh (*imperative*) mô tả từng bước thực thi: tạo biến kết quả, duyệt vòng lặp, kiểm tra điều kiện, thêm phần tử hoặc cộng dồn. Cách này hoàn toàn hợp lệ nhưng khi logic lớn dần, trạng thái có thể bị thay đổi ở nhiều vị trí. Người đọc phải theo dõi cả **giá trị đang được tính** lẫn **thời điểm biến bị sửa**.

Lập trình hàm (*functional programming*, FP) là một cách tổ chức chương trình lấy **hàm và phép biến đổi giá trị** làm trung tâm. Ta tìm cách diễn đạt dữ liệu đầu vào được chuyển thành đầu ra như thế nào; ưu tiên các hàm có kết quả dự đoán được, hạn chế việc thay đổi trạng thái chung và ghép các phép xử lý nhỏ thành quy trình rõ ràng.

Java là ngôn ngữ đa mô hình, chủ yếu dựa trên hướng đối tượng, nhưng hỗ trợ phong cách lập trình hàm qua lambda, method reference, functional interface, Stream API và nhiều API nhận hàm làm tham số. Viết Java theo phong cách hàm **không có nghĩa** mọi dòng phải dùng Stream, hay phải từ bỏ class và object.

## 2. Lập trình hàm khác cách mệnh lệnh ở điểm nào?

Giả sử cần lấy các tên không rỗng, bỏ khoảng trắng hai đầu và đổi thành chữ hoa:

**Cách mệnh lệnh:** tự điều khiển vòng lặp và thay đổi danh sách kết quả.

~~~java
List<String> result = new ArrayList<>();
for (String name : names) {
    String clean = name.trim();
    if (!clean.isEmpty()) {
        result.add(clean.toUpperCase(Locale.ROOT));
    }
}
~~~

**Cách diễn đạt theo phép biến đổi:** mô tả chuỗi thao tác lên dữ liệu.

~~~java
List<String> result = names.stream()
        .map(String::trim)
        .filter(name -> !name.isEmpty())
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();
~~~

Cả hai có thể tạo cùng giá trị. Bản thứ hai làm nổi bật các bước **map → filter → map → collect** và không cần tự quản lý danh sách kết quả. Tuy nhiên, vòng lặp vẫn có thể dễ hiểu hơn cho tác vụ rất ngắn hoặc khi cần thao tác trạng thái phức tạp. FP là cách tư duy và thiết kế, không phải cuộc thi dùng ít dòng code.

## 3. Các ý tưởng cốt lõi

### 3.1. Hàm thuần (pure function)

Một hàm được xem là thuần khi (1) cùng đầu vào trong cùng ngữ nghĩa luôn cho cùng đầu ra và (2) việc gọi nó không tạo tác dụng phụ quan sát được bên ngoài như sửa biến dùng chung, ghi file, gọi mạng hoặc in ra console.

~~~java
static long applyDiscount(long amountInDong) {
    return amountInDong * 90 / 100; // Giảm 10%, giả định amount không âm
}
~~~

Với đầu vào 200_000, hàm luôn trả 180_000. Người đọc có thể thay lời gọi bằng kết quả mà không đổi ý nghĩa chương trình trong ngữ cảnh tương ứng: tính chất đó gọi là **referential transparency** (tính thay thế bằng giá trị).

Ngược lại, hàm sau phụ thuộc trạng thái có thể đổi ở nơi khác và tạo tác dụng phụ:

~~~java
static int totalCalls = 0;

static long calculateAndCount(long amount) {
    totalCalls++;
    return amount * 90 / 100;
}
~~~

Kết quả số tiền có thể ổn định, nhưng toàn bộ hành vi hàm không thuần vì sửa biến totalCalls. Cũng cần phân biệt giữa **biến cục bộ** trong hàm (không nhất thiết gây tác dụng phụ ra ngoài) và **trạng thái chia sẻ** mà lời gọi làm thay đổi.

### 3.2. Bất biến (immutability)

Bất biến là ưu tiên tạo ra giá trị mới thay vì sửa giá trị cũ đang được nhiều phần chương trình tham chiếu. Cách này làm giảm số nơi phải theo dõi thay đổi, giúp kiểm thử và suy luận về đồng thời dễ hơn.

Trong Java, List.of(...) tạo danh sách không cho phép thêm/xóa phần tử; Stream.toList() (Java 16+) cũng trả về danh sách không thể thay đổi cấu trúc. Tuy nhiên, **danh sách không sửa được không đồng nghĩa các đối tượng bên trong bất biến**. Một record Java có các thành phần final nhưng chỉ bất biến nông: nếu nó chứa List hay đối tượng mutable thì nội dung bên trong vẫn có thể đổi.

Không phải mọi thay đổi trạng thái đều xấu. Cập nhật database, ghi log và xử lý giao diện là những tác dụng cần có. Điểm hữu ích là **cô lập phần có tác dụng phụ ở ranh giới** và giữ phần tính toán lõi đơn giản, có thể kiểm thử độc lập.

### 3.3. Hàm là đối tượng có thể truyền đi

Trong Java, ta có thể truyền hành vi thông qua **functional interface**: interface có đúng một phương thức trừu tượng theo quy tắc SAM (*single abstract method*). Lambda là cách ngắn gọn để cung cấp phần cài đặt cho giao diện đó.

Một số kiểu thường gặp trong java.util.function:

| Giao diện | Ý nghĩa | Phương thức chính |
| --- | --- | --- |
| Predicate<T> | Kiểm tra điều kiện T → boolean | test |
| Function<T,R> | Chuyển T → R | apply |
| Consumer<T> | Nhận T và thực hiện hành động, không trả kết quả | accept |
| Supplier<T> | Cung cấp T, không nhận đối số | get |
| UnaryOperator<T> | Chuyển T → T | apply |
| BinaryOperator<T> | Kết hợp hai giá trị T → T | apply |

Ví dụ:

~~~java
Predicate<String> nonBlank = s -> !s.isBlank();
Function<String, String> normalize = String::trim;
System.out.println(nonBlank.test(" Java ")); // true
System.out.println(normalize.apply(" Java ")); // Java
~~~

Một hàm **bậc cao** (*higher-order function*) là hàm nhận hàm khác làm đầu vào hoặc tạo ra hàm làm kết quả. Trong Java, filter nhận một Predicate; map nhận một Function. Chúng diễn đạt logic xử lý chung, còn hành vi cụ thể được truyền từ bên ngoài.

### 3.4. Ghép hàm (composition)

Có thể xây dựng xử lý phức tạp bằng cách kết hợp các phép biến đổi nhỏ:

~~~java
Function<String, String> trim = String::trim;
Function<String, String> upper = s -> s.toUpperCase(Locale.ROOT);
Function<String, String> normalize = trim.andThen(upper);
System.out.println(normalize.apply("  java  ")); // JAVA
~~~

Với Function, a.andThen(b) nghĩa là áp dụng a trước rồi b; a.compose(b) nghĩa là áp dụng b trước rồi a. Các phép ghép dễ suy luận nhất khi từng hàm không phụ thuộc tác dụng phụ và thứ tự ngầm.

### 3.5. Mô tả kết quả thay vì điều khiển từng bước

Phong cách *declarative* thường nói **muốn tính gì** qua filter, map, reduce, nhóm dữ liệu, thay vì tự chỉ định từng bước lặp và cập nhật biến. Trong Java, Stream là công cụ thường dùng cho việc này, nhưng hai khái niệm **lập trình hàm** và **Stream API** không đồng nhất: có thể viết hàm thuần mà không dùng Stream, cũng có thể viết Stream chứa tác dụng phụ và khó dự đoán.

## 4. Ví dụ hoàn chỉnh chạy với Java 17+

Ví dụ sau thực hiện ba việc: tính tổng đơn đã thanh toán, chuẩn hóa danh sách tên và ghép hai hàm. Dữ liệu chỉ được khai báo một lần; các bước tính toán không sửa nguồn.

Tạo file **FunctionalIntro.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.function.Function;

public class FunctionalIntro {
    record Order(String id, long amountInDong, boolean paid) {}

    static long paidTotal(List<Order> orders) {
        return orders.stream()
                .filter(Order::paid)
                .mapToLong(Order::amountInDong)
                .sum();
    }

    static List<String> validNames(List<String> names) {
        return names.stream()
                .map(String::trim)
                .filter(name -> !name.isEmpty())
                .map(name -> name.toUpperCase(Locale.ROOT))
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 120_000, true),
                new Order("B", 70_000, false),
                new Order("C", 80_000, true)
        );
        List<String> names = List.of(" An ", "Binh", " ", "Chi");

        System.out.println("Tổng đơn đã thanh toán: " + paidTotal(orders));
        System.out.println("Tên hợp lệ: " + validNames(names));

        Function<String, String> trim = String::trim;
        Function<String, String> upper =
                s -> s.toUpperCase(Locale.ROOT);
        Function<String, String> normalize = trim.andThen(upper);
        System.out.println("Chuẩn hóa: " + normalize.apply("  java  "));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FunctionalIntro.java
java FunctionalIntro
~~~

Kết quả:

~~~text
Tổng đơn đã thanh toán: 200000
Tên hợp lệ: [AN, BINH, CHI]
Chuẩn hóa: JAVA
~~~

**Giải thích:** filter(Order::paid) giữ các đơn có paid = true; mapToLong lấy số tiền và sum cộng hai khoản 120_000 + 80_000. validNames thực hiện lần lượt trim, loại tên rỗng rồi đổi chữ hoa theo Locale.ROOT để có kết quả ổn định trước sự khác biệt locale. andThen ghép hai Function theo đúng thứ tự.

paidTotal không sửa List đầu vào và luôn cho cùng kết quả với cùng nội dung đơn hàng. Nó **không tự động bảo đảm tính thuần** nếu danh sách hoặc phần tử được thiết kế để có thể bị sửa đồng thời. Ở ví dụ, List.of và record chỉ chứa String, long, boolean nên dữ liệu đầu vào phù hợp với cách suy luận bất biến.

## 5. FP giải quyết vấn đề thực tế nào?

1. **Giảm lỗi do trạng thái chia sẻ:** thay vì nhiều hàm âm thầm sửa cùng một biến, các phép biến đổi nhận đầu vào và trả đầu ra rõ ràng. Điều này đặc biệt có ích khi logic được gọi lại hoặc chạy đồng thời.
2. **Kiểm thử dễ và có tính tái lập:** một hàm tính tiền từ tham số có thể được kiểm tra bằng bảng input/output, không cần khởi động database, đồng hồ giả hay một hệ thống khác chỉ để tính phép toán.
3. **Tách chính sách nghiệp vụ khỏi cơ chế lặp:** lọc theo điều kiện, tính thuế, chuẩn hóa chuỗi, phân nhóm là các hàm nhỏ có thể tái sử dụng, thay vì chép lại vòng lặp lớn với nhiều nhánh.
4. **Đọc luồng xử lý dữ liệu dễ hơn:** pipeline mô tả trình tự rõ ràng của lọc, chiếu, nhóm, tổng hợp; người đọc thấy ý định xử lý mà không phải mô phỏng biến tạm ở từng vòng lặp.
5. **Giảm phụ thuộc thứ tự thực thi:** những phép toán độc lập, không có tác dụng phụ thường an toàn hơn khi đổi thứ tự hoặc chạy song song, dù việc song song hóa vẫn cần xem xét thứ tự đầu ra, tính kết hợp của phép gộp, dữ liệu nguồn và chi phí thực thi.

Ví dụ thiết kế dịch vụ đặt hàng: lấy dữ liệu và ghi kết quả trong lớp giao tiếp database là phần có tác dụng phụ; bên trong có thể có hàm tính phí vận chuyển, giảm giá và thành tiền chỉ dựa trên dữ liệu truyền vào. Khi giá chính sách thay đổi, có thể kiểm thử hàm tính toán riêng, không cần mô phỏng toàn bộ ứng dụng.

## 6. Khi áp dụng trong Java, cần hiểu đúng Stream

**Stream là một mô tả quá trình xử lý, không phải collection chứa sẵn kết quả.** Các thao tác trung gian như filter, map thường *lazy*: chúng tạo pipeline nhưng chưa thực hiện việc duyệt phần tử. Thao tác kết thúc như toList, count, sum, forEach mới khởi động xử lý. Một Stream thường chỉ dùng được một lần; muốn xử lý lại thì tạo Stream mới từ nguồn.

Hãy tránh việc lén thay đổi biến ngoài trong map/filter/forEach, chẳng hạn cộng vào một bộ đếm mutable từ lambda. Cách đó làm mất lợi ích suy luận, đặc biệt có thể gây race condition khi dùng parallelStream(). Thay vào đó, dùng sum, count, reduce hoặc collector phù hợp. Khi thu gộp song song, phép gộp cần đáp ứng các hợp đồng API, đặc biệt tính kết hợp và identity thích hợp; không phải cứ gọi parallel() là nhanh hay an toàn.

**Thứ tự:** pipeline có nguồn có thứ tự như List thường giữ thứ tự gặp phần tử đối với nhiều thao tác, nhưng một số phép toán và nguồn không bảo đảm thứ tự. Đừng phụ thuộc thứ tự ngầm khi dùng unordered collection, findAny hoặc luồng song song.

**Độ phức tạp:** mỗi filter/map vẫn cần xử lý phần tử liên quan. Chuỗi Stream không làm thuật toán từ O(n) biến thành O(1). Lambda, boxing, cấp phát và các bước trung gian có thể phát sinh chi phí; nên đo bằng benchmark phù hợp nếu hiệu năng là trọng tâm, thay vì mặc định Stream nhanh hơn vòng lặp.

**Giá trị null:** List.of không nhận phần tử null. Nếu nguồn có null, cần xác định quy ước dữ liệu và lọc/xử lý có chủ đích trước khi gọi phương thức trên phần tử; không giả định mọi phép map an toàn.

## 7. Khi nào nên và không nên ưu tiên?

**Nên cân nhắc phong cách hàm** khi xử lý danh sách, chuyển đổi DTO, kiểm tra điều kiện, tổng hợp số liệu, áp dụng quy tắc tính toán độc lập, hoặc xây dựng các bước nghiệp vụ dễ ghép và dễ kiểm thử.

**Không nên ép** mọi tác vụ vào chuỗi lambda dài. Logic cần nhiều nhánh điều khiển, xử lý tài nguyên, giao dịch có trạng thái, I/O hoặc vòng lặp hiệu năng cao đôi khi rõ ràng hơn với phương thức và câu lệnh thông thường. Cách phối hợp thực tế là để logic lõi nhận dữ liệu/trả giá trị, còn tầng ngoài chịu trách nhiệm tương tác với thế giới bên ngoài.

Cũng không nên biến mỗi dòng thành một method reference khó hiểu. Đặt tên rõ ràng cho phép biến đổi, tách pipeline dài thành hàm có nghĩa nghiệp vụ, và dùng vòng lặp khi đó là dạng dễ đọc nhất.

## 8. Các hiểu lầm và lỗi phổ biến

- **“Dùng lambda nghĩa là đã có FP”:** lambda có thể ghi file, sửa biến đối tượng hoặc phụ thuộc trạng thái toàn cục. Phải xem cả hành vi, không chỉ cú pháp.
- **“Hàm không có biến gán lại là pure”:** một hàm đọc thời gian hiện tại, gọi mạng hoặc viết log vẫn liên quan trạng thái/tác dụng phụ dù không đổi biến cục bộ.
- **“List bất biến thì toàn bộ dữ liệu bất biến”:** phần tử bên trong có thể mutable; record cũng chỉ bảo đảm bất biến nông.
- **“Stream luôn nhanh và chạy ngay”:** thao tác trung gian thường lazy; lợi ích chính ở đây là biểu đạt xử lý, không phải cam kết tốc độ.
- **“parallelStream tự động sửa vấn đề đồng thời”:** mã có trạng thái chia sẻ có thể chạy sai; overhead còn khiến khối lượng nhỏ chậm hơn.
- **“Có thể dùng Stream lại”:** sau thao tác kết thúc, Stream đã được tiêu thụ; hãy tạo pipeline mới.
- **“Lập trình hàm không được có I/O”:** ứng dụng cần I/O; điều cần làm là nhận diện và giới hạn tác dụng phụ ở vị trí phù hợp.

## 9. Tự kiểm tra kiến thức

1. Nếu hai lời gọi hàm nhận cùng tham số nhưng đọc một biến toàn cục có thể thay đổi, có thể coi hàm là thuần không? **Không:** kết quả còn phụ thuộc trạng thái ngoài tham số.
2. Vì sao việc trả List mới thường dễ kiểm thử hơn sửa List do nơi gọi sở hữu? **Vì** trạng thái trước lời gọi không bị thay đổi và kết quả được quan sát trực tiếp.
3. map và filter trên Stream thường chạy ở thời điểm nào? **Khi có thao tác kết thúc** yêu cầu đánh giá pipeline (trừ các tối ưu bỏ qua thao tác không cần thiết theo hợp đồng Stream).
4. Có phải mọi bài toán đều nên dùng Stream? **Không:** chọn biểu đạt làm ý định rõ nhất, cân nhắc xử lý trạng thái, độ dễ đọc và chi phí thực thi.

**Ghi nhớ:** Lập trình hàm giúp chia logic thành những phép biến đổi nhỏ, dự đoán được và dễ ghép. Giá trị thực tiễn trong Java nằm ở khả năng **giảm phụ thuộc vào trạng thái thay đổi, tăng khả năng kiểm thử và làm rõ luồng dữ liệu**; lambda và Stream chỉ là công cụ để thực hiện tư duy đó.
